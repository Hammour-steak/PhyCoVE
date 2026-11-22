"""Two-way rigid bodies / DFSPH with boundary particles that carry their own pressure, for any number of bodies.

Every solid (the static bathtub, the float, the car) is a shell of ghost particles on the liquid's rest lattice, moving
rigidly with its Genesis link. They enter the liquid's density and velocity-divergence sums and each ghost has its own
incompressibility constraint and pressure. The density solve is split (split_density_solve): the compression this
substep's motion would add is removed from the velocities, the compression that already exists only from the positions,
so a density error never turns into kinetic energy. Every pressure velocity change a ghost causes in a liquid particle
goes back to that ghost's body as the opposite force and torque about its COM, through the rigid solver's coupling
wrench, which it consumes in the next substep. Genesis's native rigid<->SPH response is off (needs_coup=False), and so is
the stale WCSPH velocity advection of Genesis 1.4.3's DFSPH substep, which gives water 2 g.

A light body on a lot of water is unstable if it only gets the pressure in the next substep (the added-mass instability:
the pressure answers the body's acceleration as -m_A a_n, so m a_(n+1) = F - m_A a_n grows by m_A / m per substep, and the
0.15 kg float holds m_A ~ 11 kg). So the pressure iterations also move the bodies (strong coupling): after each iteration a
body's velocity relaxes towards its predicted velocity plus the impulse so far over its mass, and its ghosts follow. Water
then can push a body up to its own speed but not beyond, and a body cannot run away from it. The prediction holds gravity
and the contact force the rigid solver gave the body one substep ago (clipped: it stands for a car resting on the float, not
for the impact, which the rigid contact itself resolves); without it the float would answer a car's weight as if it held
only its own. The rigid solver gets the total impulse as usual, through its coupling wrench, in its next substep.

A rigid contact cannot see the water behind the float: a car's nose would spin the bare 0.15 kg float at hundreds of rad/s
within a substep, before any pressure answers. So the rigid solver holds the float at a mass body_m that includes about 1 kg
of the ~11 kg of water it pushes (body_m_true is its real mass): that changes its heave period by ~3 %. While it floats, an
upward force (body_m - body_m_true) g s keeps its weight at the true one; s follows the fluid force, so out of the water s = 0
and it falls at g.

The momentum solve is warm-started. Jacobi iterations carry pressure one neighbourhood at a time, so from zero they cannot
build the hydrostatic pressure of a 30 cm column within a substep; the average-error test passes anyway and the whole column
keeps falling at a few cm/s while the position solve lifts it back. Each particle keeps a pressure estimate k_bar (k = -p /
rho0, by particle id) and the solve starts from omega k_bar. The estimate rises slowly and falls fast, so it follows the
hydrostatic pressure but not an impact's spike: re-applying a spike would be a second impact.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import numpy as np
import quadrants as qd
import genesis as gs
from genesis.engine.solvers.sph_solver import SPHSolver
from genesis.utils import array_class
from genesis.utils.geom import qd_inv_quat, qd_transform_by_quat, qd_transform_by_trans_quat_fast

CONFIG = {}


def make_solver():
    import pcve_dfsph_patches as _cp

    @qd.data_oriented
    class GhostBodiesSPH(_cp.make_xsph_solver(SPHSolver)):
        def build(self):
            super().build()
            if not self.is_active:
                return
            self.n_fluid = int(CONFIG["n_fluid"])
            self.n_ghost = self._n_particles - self.n_fluid
            assert self.n_ghost == len(CONFIG["ghost_local"]) and self._B == 1
            links = list(CONFIG["body_links"])
            self.n_body = len(links)
            self.body_link = qd.field(gs.qd_int, shape=(self.n_body,))
            self.body_link.from_numpy(np.asarray(links, np.int32))
            self.g_body = qd.field(gs.qd_int, shape=(self.n_ghost,))
            self.g_body.from_numpy(np.asarray(CONFIG["ghost_body"], np.int32))
            self.orig_id = qd.field(gs.qd_int, shape=(self._n_particles, self._B))
            self.g_local = qd.Vector.field(3, gs.qd_float, shape=(self.n_ghost,))
            self.g_psi = qd.field(gs.qd_float, shape=(self.n_ghost,))
            self.g_local.from_numpy(np.asarray(CONFIG["ghost_local"], np.float32))
            self.g_psi.from_numpy(np.asarray(CONFIG["ghost_psi"], np.float32))
            self.body_com = qd.Vector.field(3, gs.qd_float, shape=(self.n_body, self._B))
            self.body_f = qd.Vector.field(3, gs.qd_float, shape=(self.n_body, self._B))   # m dv / dt over the liquid
            self.body_t = qd.Vector.field(3, gs.qd_float, shape=(self.n_body, self._B))
            self.body_force_log = np.zeros((self.n_body, 3))                              # force on each body, summed over substeps
            # strong coupling: mass (0: static), inverse inertia (link frame), relaxation per body; current velocity iterate
            self.body_m = qd.field(gs.qd_float, shape=(self.n_body,))
            self.body_m.from_numpy(np.asarray(CONFIG["body_mass"], np.float32))
            self.body_m_true = qd.field(gs.qd_float, shape=(self.n_body,))
            self.body_m_true.from_numpy(np.asarray(CONFIG.get("body_mass_true", CONFIG["body_mass"]), np.float32))
            self.body_s = qd.field(gs.qd_float, shape=(self.n_body, self._B))
            self.body_s.fill(1.0)
            self.body_Iinv = qd.Vector.field(3, gs.qd_float, shape=(self.n_body,))
            self.body_omega = qd.field(gs.qd_float, shape=(self.n_body,))
            self.body_omega.from_numpy(np.asarray(CONFIG["body_omega"], np.float32))
            self.body_fc_max = qd.field(gs.qd_float, shape=(self.n_body,))
            self.body_fc_max.from_numpy(np.asarray(CONFIG["body_contact_max"], np.float32))
            for name in ("body_V", "body_W", "body_V0", "body_W0", "body_If", "body_It", "body_Vr_prev", "body_Wr_prev", "body_fc", "body_tc", "body_Fp", "body_Tp"):
                setattr(self, name, qd.Vector.field(3, gs.qd_float, shape=(self.n_body, self._B)))
            self.body_measure = 0                                                          # 0: the velocities were just set by hand
            self.body_force_n = 0
            # worst-particle error: DFSPH's average-error test is met while a thin compressed layer is still crushed, so both
            # must pass (fractions of rest density, per dt for the divergence)
            self.err_max = qd.field(gs.qd_float, shape=())
            self.max_err_den = float(CONFIG.get("max_density_error_max", 0.01))
            self.max_err_div = float(CONFIG.get("max_divergence_error_max", 1e9))
            # the momentum part of the split solve: the compression a particle may still gain per substep
            self.max_err_mom = float(CONFIG.get("momentum_error_max", 5e-4))
            self.max_err_mom_avg = float(CONFIG.get("momentum_error_avg", 5e-5))
            self.max_iters_mom = int(CONFIG.get("momentum_max_iters", 5000))
            self.max_err_pos_avg = float(CONFIG.get("position_error_avg", 5e-4))
            self.iter_counts = [0, 0, 0, 0]  # divergence, density (momentum) iterations, substeps, position iterations
            self.v_keep = qd.Vector.field(3, gs.qd_float, shape=(self._n_particles, self._B))
            self.dv_pos = qd.Vector.field(3, gs.qd_float, shape=(self._n_particles, self._B))
            self.v_nb = qd.Vector.field(3, gs.qd_float, shape=(self._n_particles, self._B))
            self.k_bar = qd.field(gs.qd_float, shape=(self._n_particles, self._B))
            self.k_acc = qd.field(gs.qd_float, shape=(self._n_particles, self._B))
            self.k_w = qd.field(gs.qd_float, shape=(self._n_particles, self._B))
            self.warm_omega = float(CONFIG.get("warm_omega", 0.95))
            self.warm_rise = float(CONFIG.get("warm_rise", 0.0))
            self.warm_fall = float(CONFIG.get("warm_fall", 0.2))
            self.still_speed = float(CONFIG.get("still_speed", 0.2))
            self.rho_interior = float(CONFIG.get("rho_interior", 0.95))
            self.compaction_rate = float(CONFIG.get("compaction_rate", 0.03))
            self.speed_cap = float(CONFIG.get("speed_cap", 7.0))
            self.worst_iters = int(CONFIG.get("worst_iters", 60))
            self.worst_iters_pos = int(CONFIG.get("worst_iters_pos", 15))
            self.g_wet = qd.field(gs.qd_float, shape=(self.n_ghost,))
            self.g_wet.from_numpy(np.asarray(CONFIG.get("ghost_wetting", np.ones(self.n_ghost)), np.float32))

        # ---------------------------------------------------------------- helpers
        @qd.func
        def _xsph_fluid(self, j, i_b):
            return self.orig_id[j, i_b] < self.n_fluid

        @qd.func
        def _wet(self, j, i_b):
            w = gs.qd_float(1.0)
            if self.orig_id[j, i_b] >= self.n_fluid:
                w = self.g_wet[self.orig_id[j, i_b] - self.n_fluid]
            return w

        @qd.func
        def vol(self, j, i_b):
            v = self._particle_volume
            if self.orig_id[j, i_b] >= self.n_fluid:
                v = self.g_psi[self.orig_id[j, i_b] - self.n_fluid]
            return v

        @qd.kernel
        def kernel_place_ghosts(self, links_state: array_class.LinksState):
            for b, i_b in qd.ndrange(self.n_body, self._B):
                self.body_com[b, i_b] = links_state.root_COM[self.body_link[b], i_b]
            for g, i_b in qd.ndrange(self.n_ghost, self._B):
                i = self.n_fluid + g
                link = self.body_link[self.g_body[g]]
                pos = qd_transform_by_trans_quat_fast(self.g_local[g], links_state.pos[link, i_b], links_state.quat[link, i_b])
                self.particles[i, i_b].pos = pos
                self.particles[i, i_b].vel = self.sim.rigid_solver._func_vel_at_point(
                    pos_world=pos, link_idx=link, i_b=i_b, links_state=links_state
                )
                self.particles[i, i_b].acc = qd.Vector.zero(gs.qd_float, 3)

        @qd.kernel
        def kernel_orig_ids(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng[i_p, i_b].active:
                    self.orig_id[self.particles_ng[i_p, i_b].reordered_idx, i_b] = i_p

        @qd.kernel
        def kernel_ghost_acc(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] >= self.n_fluid:
                    self.particles_reordered[i_p, i_b].acc = qd.Vector.zero(gs.qd_float, 3)

        @qd.func
        def _task_ghost_factor(self, i, j, ret: qd.template(), i_b):
            g = self.vol(j, i_b) * self.cubic_kernel_derivative(
                self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos)
            ret.g += g
            if self.orig_id[j, i_b] < self.n_fluid:
                ret.s += g.norm_sqr()

        @qd.kernel
        def kernel_ghost_factor(self):
            """Jacobi diagonal of a ghost's constraint, of the same form as a liquid particle's. Ghosts without liquid
            neighbours carry no pressure."""
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] >= self.n_fluid:
                    ret = qd.Struct(s=gs.qd_float(0.0), g=qd.Vector.zero(gs.qd_float, 3))
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_ghost_factor, i_b)
                    factor = gs.qd_float(0.0)
                    if ret.s > 0.0:
                        factor = -1.0 / (ret.g.norm_sqr() + ret.s)
                    self.particles_reordered[i_p, i_b].dfsph_factor = factor

        # ---------------------------------------------------------------- density and factor
        @qd.func
        def _task_compute_rho(self, i, j, ret: qd.template(), i_b):
            ret += self.vol(j, i_b) * self.cubic_kernel(
                (self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos).norm()
            )

        @qd.func
        def _task_compute_DFSPH_factor(self, i, j, ret: qd.template(), i_b):
            grad_j = -self.vol(j, i_b) * self.cubic_kernel_derivative(
                self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
            )
            if self.orig_id[j, i_b] < self.n_fluid:
                ret[3] += grad_j.norm_sqr()
            for ii in qd.static(range(3)):
                ret[ii] -= grad_j[ii]

        @qd.func
        def _task_compute_density_time_derivative(self, i, j, ret: qd.template(), i_b):
            ret.drho += self.vol(j, i_b) * (
                self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel
            ).dot(self.cubic_kernel_derivative(self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos))
            ret.num_neighbors += 1

        @qd.func
        def _task_compute_density_star(self, i, j, ret: qd.template(), i_b):
            ret += self.vol(j, i_b) * (
                self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel
            ).dot(self.cubic_kernel_derivative(self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos))

        @qd.kernel
        def _kernel_compute_density_star(self, velocity_only: qd.i32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:   # ghosts too: their constraint keeps liquid out
                    delta = gs.qd_float(0.0)
                    self.sh.for_all_neighbors(
                        i_p, self.particles_reordered.pos, self._support_radius, delta, self._task_compute_density_star, i_b
                    )
                    rho = self.particles_reordered[i_p, i_b].rho / self._density0
                    drho = qd.max(rho + self._substep_dt * delta, 1.0)
                    if velocity_only:
                        # the compression this substep's motion would add. A particle near rest density counts all of it: if it
                        # could first close its small deficit (rho < 1), a column would fall freely in that gap, every substep
                        # (gravity still closes it, slowly: stirred water would otherwise keep the volume its disorder gave it)
                        base = qd.max(rho, 1.0)
                        if rho > self.rho_interior:
                            base = qd.min(base, rho + self._substep_dt * self.compaction_rate)
                        drho = 1.0 + qd.max(rho + self._substep_dt * delta - base, 0.0)
                    self.particles_reordered[i_p, i_b].drho = drho

        # ---------------------------------------------------------------- non-pressure forces (liquid only)
        @qd.func
        def _task_compute_non_pressure_forces(self, i, j, ret: qd.template(), i_b: qd.i32):
            if self.orig_id[i, i_b] < self.n_fluid and self.orig_id[j, i_b] < self.n_fluid:
                d_ij = self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
                dist = d_ij.norm()
                mu_i = self.particles_info_reordered[i, i_b].mu
                mass_j = self.particles_info_reordered[j, i_b].mass
                v_ij = (self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel).dot(d_ij)
                rho_j = self.particles_reordered[j, i_b].rho
                ret += (10.0 * mu_i * (mass_j / rho_j) * v_ij / (dist ** 2 + 0.01 * self._support_radius ** 2)
                        * self.cubic_kernel_derivative(d_ij))

        # ---------------------------------------------------------------- pressure iterations with body feedback
        @qd.func
        def _task_pressure_iteration(self, i, j, ret: qd.template(), i_b):
            grad_p_j = -self.vol(j, i_b) * self.cubic_kernel_derivative(
                self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
            )
            o = self.orig_id[j, i_b]
            k_sum = ret.k_i + (self.particles_reordered[j, i_b].drho - ret.offset) * self.particles_reordered[j, i_b].dfsph_factor
            if qd.abs(k_sum) > self._df_eps:
                dv = -ret.scale * k_sum * grad_p_j
                ret.dv += dv
                if o >= self.n_fluid and ret.impulses:     # a ghost's pressure moves only the particle: the body takes the opposite
                    b = self.g_body[o - self.n_fluid]
                    f = ret.m_dt * dv
                    self.body_f[b, i_b] += f
                    self.body_t[b, i_b] += (self.particles_reordered[j, i_b].pos - self.body_com[b, i_b]).cross(f)

        @qd.kernel
        def kernel_pressure_iteration(self, offset: qd.f32, scale: qd.f32, impulses: qd.i32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    k_i = (self.particles_reordered[i_p, i_b].drho - offset) * self.particles_reordered[i_p, i_b].dfsph_factor
                    ret = qd.Struct(dv=qd.Vector.zero(gs.qd_float, 3), k_i=k_i, offset=offset, scale=scale, impulses=impulses,
                                    m_dt=self.particles_info_reordered[i_p, i_b].mass / self._substep_dt)
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_pressure_iteration, i_b)
                    self.particles_reordered.vel[i_p, i_b] = self.particles_reordered.vel[i_p, i_b] + ret.dv

        # ---------------------------------------------------------------- warm start of the momentum solve
        @qd.kernel
        def kernel_warm_load(self, omega: qd.f32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                self.k_acc[i_p, i_b] = 0.0
                self.k_w[i_p, i_b] = 0.0
                if self.particles_ng_reordered[i_p, i_b].active:
                    self.k_w[i_p, i_b] = omega * self.k_bar[self.orig_id[i_p, i_b], i_b]

        @qd.func
        def _task_warm_start(self, i, j, ret: qd.template(), i_b):
            grad_p_j = -self.vol(j, i_b) * self.cubic_kernel_derivative(
                self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
            )
            dv = -ret.scale * (ret.k_i + self.k_w[j, i_b]) * grad_p_j
            ret.dv += dv
            o = self.orig_id[j, i_b]
            if o >= self.n_fluid:
                b = self.g_body[o - self.n_fluid]
                f = ret.m_dt * dv
                self.body_f[b, i_b] += f
                self.body_t[b, i_b] += (self.particles_reordered[j, i_b].pos - self.body_com[b, i_b]).cross(f)

        @qd.kernel
        def kernel_warm_start(self, scale: qd.f32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    ret = qd.Struct(dv=qd.Vector.zero(gs.qd_float, 3), k_i=self.k_w[i_p, i_b], scale=scale,
                                    m_dt=self.particles_info_reordered[i_p, i_b].mass / self._substep_dt)
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_warm_start, i_b)
                    self.particles_reordered.vel[i_p, i_b] = self.particles_reordered.vel[i_p, i_b] + ret.dv

        @qd.kernel
        def kernel_k_accumulate(self, offset: qd.f32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    self.k_acc[i_p, i_b] += (self.particles_reordered[i_p, i_b].drho - offset) * self.particles_reordered[i_p, i_b].dfsph_factor

        @qd.kernel
        def kernel_warm_store(self, rise: qd.f32, fall: qd.f32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    o = self.orig_id[i_p, i_b]
                    total = self.k_w[i_p, i_b] + self.k_acc[i_p, i_b]
                    kb = self.k_bar[o, i_b]
                    if total < kb:     # k is negative: more pressure than the estimate
                        kb = qd.max(total, kb - rise)
                    else:
                        kb += fall * (total - kb)
                    self.k_bar[o, i_b] = kb

        @qd.func
        def _comp(self, b, i_b):
            """minus the upward force that keeps a floating body's weight at its true mass (cfrc_coupling sign)"""
            return (self.body_m[b] - self.body_m_true[b]) * self.body_s[b, i_b] * self._gravity[i_b]

        @qd.kernel
        def kernel_flush_wrench(self, links_state: array_class.LinksState):
            """cfrc_coupling holds minus the force on the link; the rigid solver consumes it in its next substep"""
            for b, i_b in qd.ndrange(self.n_body, self._B):
                link = self.body_link[b]
                links_state.cfrc_coupling_vel[link, i_b] += self.body_If[b, i_b] + self._comp(b, i_b)
                links_state.cfrc_coupling_ang[link, i_b] += self.body_It[b, i_b]

        def flush_wrench(self):
            self.body_force_log -= self.body_If.to_numpy().reshape(self.n_body, 3)
            self.kernel_flush_wrench(self.sim.rigid_solver.dyn_state.links)

        # ---------------------------------------------------------------- strong coupling of the bodies
        @qd.kernel
        def kernel_body_begin(self, measure: qd.i32, links_state: array_class.LinksState):
            """start of a substep: the rigid solver's velocities, and the contact force they imply"""
            for b, i_b in qd.ndrange(self.n_body, self._B):
                self.body_If[b, i_b] = qd.Vector.zero(gs.qd_float, 3)
                self.body_It[b, i_b] = qd.Vector.zero(gs.qd_float, 3)
                if self.body_m[b] > 0.0:
                    link = self.body_link[b]
                    v = links_state.cd_vel[link, i_b]
                    w = links_state.cd_ang[link, i_b]
                    q = links_state.quat[link, i_b]
                    fc = qd.Vector.zero(gs.qd_float, 3)
                    tc = qd.Vector.zero(gs.qd_float, 3)
                    if measure:
                        a = (v - self.body_Vr_prev[b, i_b]) / self._substep_dt
                        fc = self.body_m[b] * (a - self._gravity[i_b]) - self.body_Fp[b, i_b]
                        al = qd_transform_by_quat((w - self.body_Wr_prev[b, i_b]) / self._substep_dt, qd_inv_quat(q))
                        tl = al / self.body_Iinv[b]
                        tc = qd_transform_by_quat(tl, q) - self.body_Tp[b, i_b]
                        lim = self.body_fc_max[b]
                        n = fc.norm()
                        if n > lim:
                            fc *= lim / n
                        n = tc.norm()
                        if n > 0.1 * lim:
                            tc *= 0.1 * lim / n
                    self.body_fc[b, i_b] = fc
                    self.body_tc[b, i_b] = tc
                    self.body_Vr_prev[b, i_b] = v
                    self.body_Wr_prev[b, i_b] = w
                    self.body_V0[b, i_b] = v
                    self.body_W0[b, i_b] = w
                    self.body_V[b, i_b] = v
                    self.body_W[b, i_b] = w

        @qd.kernel
        def kernel_body_predict(self, links_state: array_class.LinksState):
            """before the density solve: the velocity the rigid solver would reach without further pressure"""
            for b, i_b in qd.ndrange(self.n_body, self._B):
                if self.body_m[b] > 0.0:
                    q = links_state.quat[self.body_link[b], i_b]
                    dv = self._substep_dt * (self._gravity[i_b] + (self.body_fc[b, i_b] - self._comp(b, i_b)) / self.body_m[b])
                    dw = self._substep_dt * qd_transform_by_quat(self.body_Iinv[b] * qd_transform_by_quat(self.body_tc[b, i_b], qd_inv_quat(q)), q)
                    self.body_V0[b, i_b] += dv
                    self.body_W0[b, i_b] += dw
                    self.body_V[b, i_b] += dv
                    self.body_W[b, i_b] += dw

        @qd.kernel
        def kernel_body_iterate(self, links_state: array_class.LinksState):
            """after a pressure iteration: bank its impulse and relax each body's velocity towards prediction + impulse / mass"""
            for b, i_b in qd.ndrange(self.n_body, self._B):
                self.body_If[b, i_b] += self.body_f[b, i_b]
                self.body_It[b, i_b] += self.body_t[b, i_b]
                self.body_f[b, i_b] = qd.Vector.zero(gs.qd_float, 3)
                self.body_t[b, i_b] = qd.Vector.zero(gs.qd_float, 3)
                if self.body_m[b] > 0.0:
                    q = links_state.quat[self.body_link[b], i_b]
                    vt = self.body_V0[b, i_b] - self._substep_dt * self.body_If[b, i_b] / self.body_m[b]
                    wt = self.body_W0[b, i_b] - self._substep_dt * qd_transform_by_quat(
                        self.body_Iinv[b] * qd_transform_by_quat(self.body_It[b, i_b], qd_inv_quat(q)), q)
                    self.body_V[b, i_b] += self.body_omega[b] * (vt - self.body_V[b, i_b])
                    self.body_W[b, i_b] += self.body_omega[b] * (wt - self.body_W[b, i_b])

        @qd.kernel
        def kernel_ghost_velocity(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                o = self.orig_id[i_p, i_b]
                if self.particles_ng_reordered[i_p, i_b].active and o >= self.n_fluid:
                    b = self.g_body[o - self.n_fluid]
                    if self.body_m[b] > 0.0:
                        r = self.particles_reordered[i_p, i_b].pos - self.body_com[b, i_b]
                        self.particles_reordered[i_p, i_b].vel = self.body_V[b, i_b] + self.body_W[b, i_b].cross(r)

        @qd.kernel
        def kernel_body_end(self):
            """the wrench handed to the rigid solver, for the next substep's contact estimate"""
            for b, i_b in qd.ndrange(self.n_body, self._B):
                self.body_Fp[b, i_b] = -self.body_If[b, i_b] - self._comp(b, i_b)
                self.body_Tp[b, i_b] = -self.body_It[b, i_b]
                if self.body_m_true[b] > 0.0:
                    w = self.body_m_true[b] * self._gravity[i_b].norm()
                    self.body_s[b, i_b] += 0.05 * (qd.min(self.body_If[b, i_b].norm() / w, 1.0) - self.body_s[b, i_b])

        @qd.kernel
        def kernel_density_error_max(self, offset: qd.f32):
            self.err_max[None] = 0.0
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    qd.atomic_max(self.err_max[None], self._density0 * self.particles_reordered[i_p, i_b].drho - offset)

        def _divergence_solve(self, f):
            self._kernel_compute_density_time_derivative()
            eta = (1.0 / self._substep_dt) * self._df_max_error_div * 0.01 * self._density0
            it = 0
            while it < self._df_max_div_iters:
                self.kernel_pressure_iteration(0.0, 1.0, 1)
                self.kernel_body_iterate(self.sim.rigid_solver.dyn_state.links)
                self.kernel_ghost_velocity()
                self._kernel_compute_density_time_derivative()
                err = self._kernel_compute_density_error(0.0) / self.n_active_fluid
                it += 1
                if err <= eta:
                    self.kernel_density_error_max(0.0)
                    if self.err_max[None] <= self.max_err_div * self._density0 / self._substep_dt:
                        break
            self.iter_counts[0] += it

        def _density_solve(self, f, velocity_only, impulses):
            """DFSPH density solve; the caller has scaled dfsph_factor by 1 / dt^2."""
            self._kernel_compute_density_star(velocity_only)
            eta = (self.max_err_mom_avg if velocity_only else self.max_err_pos_avg) * self._density0
            worst = self.max_err_mom if velocity_only else self.max_err_den
            max_it = self.max_iters_mom if velocity_only else self._df_max_den_iters
            it = 0
            while it < max_it:
                if impulses:
                    self.kernel_k_accumulate(1.0)
                self.kernel_pressure_iteration(1.0, self._substep_dt, impulses)
                if impulses:
                    self.kernel_body_iterate(self.sim.rigid_solver.dyn_state.links)
                    self.kernel_ghost_velocity()
                self._kernel_compute_density_star(velocity_only)
                err = self._kernel_compute_density_error(self._density0) / self.n_active_fluid
                it += 1
                if err <= eta:
                    # the worst-particle test has a time limit: a few particles trapped between a body and the floor can never meet it
                    self.kernel_density_error_max(self._density0)
                    if self.err_max[None] <= worst * self._density0 or it >= (self.worst_iters if velocity_only else self.worst_iters_pos):
                        break
            return it

        @qd.kernel
        def kernel_save_vel(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                self.v_keep[i_p, i_b] = self.particles_reordered[i_p, i_b].vel

        @qd.kernel
        def kernel_store_dv_pos(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                self.dv_pos[i_p, i_b] = qd.Vector.zero(gs.qd_float, 3)
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    self.dv_pos[i_p, i_b] = self.particles_reordered[i_p, i_b].vel - self.v_keep[i_p, i_b]

        @qd.func
        def _task_v_nb(self, i, j, ret: qd.template(), i_b):
            w = self.cubic_kernel((self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos).norm())
            ret.w += w
            ret.v += w * self.v_keep[j, i_b]

        @qd.kernel
        def kernel_neighbour_velocity(self):
            """Kernel-weighted mean momentum-solve velocity of each liquid particle's neighbours (liquid and ghosts)."""
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    ret = qd.Struct(w=gs.qd_float(0.0), v=qd.Vector.zero(gs.qd_float, 3))
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_v_nb, i_b)
                    self.v_nb[i_p, i_b] = self.v_keep[i_p, i_b]
                    if ret.w > 0.0:
                        self.v_nb[i_p, i_b] = ret.v / ret.w

        @qd.kernel
        def kernel_remove_dv_pos(self):
            """Take the position correction out of the velocity again, and make it inelastic: the velocity component against
            the correction, up to its size, is removed (never added). Otherwise a motion the position part undoes every
            substep is never seen by the momentum part and persists. The approach is measured relative to the particle's
            neighbours, so the correction neither brakes nor kicks a liquid in free fall."""
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    dvp = self.dv_pos[i_p, i_b]
                    v = self.particles_reordered[i_p, i_b].vel - dvp
                    m = dvp.norm()
                    if m > 0.0:
                        n = dvp / m
                        # the frame the approach is measured in: the neighbours' for moving liquid, the tub's for still water
                        # (a column falling as one has no approach to its neighbours, only to the floor far below)
                        ref = self.v_nb[i_p, i_b] * qd.min(self.v_nb[i_p, i_b].norm() / self.still_speed, 1.0)
                        a = (v - ref).dot(n)
                        if a < 0.0:
                            v -= qd.max(a, -m) * n
                    self.particles_reordered[i_p, i_b].vel = v

        @qd.kernel
        def kernel_speed_cap(self, vmax: qd.f32):
            """water squeezed between a body and the tub floor is the only thing that outruns this, one particle at a time"""
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    v = self.particles_reordered[i_p, i_b].vel
                    n = v.norm()
                    if n > vmax:
                        self.particles_reordered[i_p, i_b].vel = v * (vmax / n)

        def split_density_solve(self, f):
            """Split as in implicit density projection (Kugelstadt et al. 2019): the compression this substep's motion would
            add is removed from the velocity (with the equal and opposite impulse on the bodies); the compression that
            already exists is removed from the positions only, without changing any velocity or momentum."""
            self._kernel_multiply_time_step(self.particles_reordered.dfsph_factor, 1.0 / self._substep_dt ** 2)
            self.kernel_warm_load(self.warm_omega)
            self.kernel_warm_start(self._substep_dt)
            self.kernel_body_iterate(self.sim.rigid_solver.dyn_state.links)
            self.kernel_ghost_velocity()
            self.iter_counts[1] += self._density_solve(f, 1, 1)
            self.kernel_warm_store(self.warm_rise, self.warm_fall)
            self.kernel_save_vel()
            self.iter_counts[3] += self._density_solve(f, 0, 0)
            self.kernel_store_dv_pos()
            self.kernel_neighbour_velocity()

        @qd.kernel
        def kernel_count_fluid(self) -> qd.i32:
            n = 0
            for i_p, i_b in qd.ndrange(self.n_fluid, self._B):
                if self.particles_ng[i_p, i_b].active:
                    n += 1
            return n

        def substep_pre_coupling(self, f):
            if not self.is_active:
                return
            ls = self.sim.rigid_solver.dyn_state.links
            self.kernel_place_ghosts(ls)
            self.kernel_body_begin(self.body_measure, ls)
            self.body_measure = 1
            self._kernel_reorder_particles(f)
            self.kernel_orig_ids()
            self.n_active_fluid = max(1, int(self.kernel_count_fluid()))
            self._kernel_compute_rho(f)
            self._kernel_compute_DFSPH_factor(f)
            self.kernel_ghost_factor()
            self.kernel_ghost_acc()
            self._divergence_solve(f)
            self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
            self.surface_tension()
            self.kernel_ghost_acc()
            self._kernel_predict_velocity(f)
            self.kernel_body_predict(ls)
            self.kernel_ghost_velocity()
            self.split_density_solve(f)
            self.flush_wrench()
            self.kernel_body_end()
            self.body_force_n += 1
            self._xsph_pre()
            self.iter_counts[2] += 1

        def substep_post_coupling(self, f):
            if not self.is_active:
                return
            self.kernel_speed_cap(self.speed_cap)
            self._kernel_advect_position(f)           # the position correction moves the particles ...
            self.kernel_remove_dv_pos()               # ... but is not kept in their velocity
            self.kernel_speed_cap(self.speed_cap)
            self._kernel_copy_from_reordered(f)

    return GhostBodiesSPH
