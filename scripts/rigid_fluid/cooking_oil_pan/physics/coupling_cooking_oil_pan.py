"""DFSPH with static boundary particles that carry their own pressure (split density solve, implicit viscosity).

Here the boundary is the frying pan, which does not move: its ghosts sit on a fixed carrier link
(CONFIG["ghost_fixed"]), so only the liquid side of the scheme acts. CONFIG["body_mass"] and
CONFIG["body_inertia"] are the mass and inertia of the coupled rigid body.
The solid is filled (outer layers) with ghost particles that move rigidly with the Genesis link. They enter the
liquid's density and velocity-divergence sums, and each ghost has its own incompressibility constraint and pressure (its
Jacobi diagonal holds only its liquid neighbours, since it does not move): a liquid particle that slides into the solid
raises the ghosts' densities, whatever happens to its own. With mirrored pressure alone (k_i, Akinci / Bender &
Koschier) the wall pushes only through the particle's own pressure, and a particle that leaves the liquid behind it at
the rate it enters the solid keeps its density and is not pushed back: a liquid column stopped by a floor drives its
bottom layer into the floor that way.
The density solve is split (see split_density_solve): the compression this substep's motion would add is removed from
the velocities, the compression that already exists only from the positions, so a density error never turns into
kinetic energy. Every pressure velocity change a ghost causes in a liquid particle is returned to the body as the
opposite impulse (force and torque about the COM) through the rigid solver's coupling wrench, which it consumes in the
next substep. Genesis's native rigid<->SPH response is disabled for the body (needs_coup=False). The stale WCSPH
velocity advection of Genesis 1.4.3's DFSPH substep (double gravity) is not run.

Optional implicit viscosity (CONFIG["implicit_nu"] > 0, material mu ~ 0): between the explicit non-pressure step and
the density solve, the fluid and the body velocities solve one SPD system (I - dt nu L) v = v*, with L the same
projected SPH Laplacian Genesis uses explicitly (L(v)_i = sum_j 10 V W'(r) r / (r^2 + 0.01 h^2) (x^ x^T)(v_i - v_j)),
by conjugate gradients with a 3x3 block-Jacobi preconditioner. It is unconditionally stable, so a very viscous liquid
runs at the normal substep. The split is incremental (as in incremental pressure-correction schemes): v* also holds the
velocity change the density solve and the boundary projection gave each particle after the previous substep's
viscosity, and the body's v* is the velocity the rigid solver will give it, with gravity and the previous density
solve's wrench; the estimate is taken out again after the solve.
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
from genesis.utils.geom import qd_transform_by_trans_quat_fast

CONFIG = {}


def make_solver():
    import pcve_dfsph_patches as _cp

    @qd.data_oriented
    class GhostBoundarySPH(_cp.make_xsph_solver(SPHSolver)):
        def build(self):
            super().build()
            if not self.is_active:
                return
            self.n_fluid = int(CONFIG["n_fluid"])
            self.n_ghost = self._n_particles - self.n_fluid
            assert self.n_ghost == len(CONFIG["ghost_local"]) and self._B == 1
            self.body_link = int(CONFIG["link_idx"])
            self.orig_id = qd.field(gs.qd_int, shape=(self._n_particles, self._B))
            self.g_local = qd.Vector.field(3, gs.qd_float, shape=(self.n_ghost,))
            self.g_psi = qd.field(gs.qd_float, shape=(self.n_ghost,))
            self.g_local.from_numpy(np.asarray(CONFIG["ghost_local"], np.float32))
            self.g_psi.from_numpy(np.asarray(CONFIG["ghost_psi"], np.float32))
            self.force_sum = qd.Vector.field(3, gs.qd_float, shape=(self._B,))
            # worst-particle error: DFSPH's average-error test is met while a thin compressed layer (a liquid column
            # stopped by the cup floor) is still crushed, so both must pass (fractions of rest density, per dt for div)
            self.err_max = qd.field(gs.qd_float, shape=())
            self.max_err_den = float(CONFIG.get("max_density_error_max", 0.01))
            self.max_err_div = float(CONFIG.get("max_divergence_error_max", 0.01))
            # the momentum (velocity) part of the split density solve: the compression a particle may still gain per
            # substep. Whatever it leaves is removed from the positions, without the momentum, so it must be small
            # against the compression an impact brings per substep (v dt / d, ~15% at 2.4 m/s): the stop of a column
            # then reaches its top through the pressure within the substep, as in an incompressible liquid
            self.max_err_mom = float(CONFIG.get("momentum_error_max", 5e-4))
            self.max_err_mom_avg = float(CONFIG.get("momentum_error_avg", 5e-5))
            self.max_iters_mom = int(CONFIG.get("momentum_max_iters", 5000))
            # the position part only restores volume (no energy either way): a looser average than the momentum part
            self.max_err_pos_avg = float(CONFIG.get("position_error_avg", 5e-4))
            self.iter_counts = [0, 0, 0, 0]  # divergence, density (momentum) iterations, substeps, position iterations
            self.visc_nu = float(CONFIG.get("implicit_nu", 0.0))
            # ghost_fixed: the ghosts' link does not move (cup, support and table here); its velocity is zero in
            # the viscosity solve, which then holds no rigid unknowns and no gravity estimate
            self.ghost_fixed = bool(CONFIG.get("ghost_fixed", False))
            self.visc_on = True  # the driver switches it off while the resting liquid settles (viscosity does nothing there)
            self.visc_stats = [0, 0, 0.0]  # CG iterations, solves, worst final relative residual
            if self.visc_nu > 0:
                shape = (self._n_particles, self._B)
                self.vis_x = qd.Vector.field(3, gs.qd_float, shape=shape)
                self.vis_b = qd.Vector.field(3, gs.qd_float, shape=shape)
                self.vis_r = qd.Vector.field(3, gs.qd_float, shape=shape)
                self.vis_z = qd.Vector.field(3, gs.qd_float, shape=shape)
                self.vis_p = qd.Vector.field(3, gs.qd_float, shape=shape)
                self.vis_Ap = qd.Vector.field(3, gs.qd_float, shape=shape)
                self.vis_Minv = qd.Matrix.field(3, 3, gs.qd_float, shape=shape)
                # the body's 6 rigid velocity DOFs join the same CG system (index 0 = linear V, 1 = angular W)
                body = (2, self._B)
                self.body_x = qd.Vector.field(3, gs.qd_float, shape=body)
                self.body_b = qd.Vector.field(3, gs.qd_float, shape=body)
                self.body_r = qd.Vector.field(3, gs.qd_float, shape=body)
                self.body_z = qd.Vector.field(3, gs.qd_float, shape=body)
                self.body_p = qd.Vector.field(3, gs.qd_float, shape=body)
                self.body_Ap = qd.Vector.field(3, gs.qd_float, shape=body)
                self.body_D = qd.Matrix.field(3, 3, gs.qd_float, shape=body)
                self.body_Minv = qd.Matrix.field(3, 3, gs.qd_float, shape=body)
                self.body_v0 = qd.Vector.field(3, gs.qd_float, shape=body)
                self.body_mass = float(CONFIG["body_mass"]); self.body_inertia = float(CONFIG["body_inertia"])
                # incremental split: per-particle velocity change after the viscous solve (density solve + mug
                # projection, indexed by original particle id) and the velocity it was measured from (reordered index)
                self.vis_est = qd.Vector.field(3, gs.qd_float, shape=shape)
                self.vis_out = qd.Vector.field(3, gs.qd_float, shape=shape)
            # the density solve's force and torque on the body in the last substep (the body's estimate)
            self.den_f = qd.Vector.field(3, gs.qd_float, shape=(self._B,))
            self.den_t = qd.Vector.field(3, gs.qd_float, shape=(self._B,))
            # split density solve: the velocity the momentum solve leaves, and the position-only correction on top of it
            self.v_keep = qd.Vector.field(3, gs.qd_float, shape=(self._n_particles, self._B))
            self.dv_pos = qd.Vector.field(3, gs.qd_float, shape=(self._n_particles, self._B))
            self.v_nb = qd.Vector.field(3, gs.qd_float, shape=(self._n_particles, self._B))
            # no-slip walls: the liquid's viscosity also acts against the ghosts' (wall) velocity
            self.ghost_noslip = bool(CONFIG.get("ghost_noslip", False))
            # per-ghost multiplier of that wall viscosity: contact-line friction of a wetted surface (1: the liquid's own)
            self.g_visc = qd.field(gs.qd_float, shape=(self.n_ghost,))
            self.g_visc.from_numpy(np.asarray(CONFIG.get("ghost_viscosity_factor", np.ones(self.n_ghost)), np.float32))
            # contact-line friction (1/s) of each ghost's surface: resists a free-surface liquid particle sliding along it
            self.g_cl = qd.field(gs.qd_float, shape=(self.n_ghost,))
            g_cl = np.asarray(CONFIG.get("contact_line_friction", np.zeros(self.n_ghost)), np.float32)
            self.g_cl.from_numpy(g_cl)
            self.cl_on = bool((g_cl > 0).any())
            # Navier-slip wall friction (1/s) per ghost: drag on the liquid's full velocity relative to the wall, weighted by
            # the wall's kernel share (contact-line friction of a wetted surface; the projected SPH viscosity above hardly
            # resists a film sliding along a wall below it)
            self.g_drag = qd.field(gs.qd_float, shape=(self.n_ghost,))
            self.g_drag.from_numpy(np.asarray(CONFIG.get("ghost_drag", np.zeros(self.n_ghost)), np.float32))
            # wetting of each ghost's surface for the surface tension (1: fully wetted, (1 + cos theta) / 2 in general)
            self.g_wet = qd.field(gs.qd_float, shape=(self.n_ghost,))
            self.g_wet.from_numpy(np.asarray(CONFIG.get("ghost_wetting", np.ones(self.n_ghost)), np.float32))
            # inflow buffer: a liquid particle moves at inlet_v until inlet_t (it is still inside the pour opening), so
            # the opening holds the stream back as the liquid in a real spout does
            self.inlet_t = qd.field(gs.qd_float, shape=(self.n_fluid,))
            self.inlet_t.fill(-1.0)
            self.inlet_v = qd.Vector.field(3, gs.qd_float, shape=(self.n_fluid,))

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
        def is_ghost(self, i, i_b):
            return self.orig_id[i, i_b] >= self.n_fluid

        @qd.func
        def vol(self, j, i_b):
            v = self._particle_volume
            if self.orig_id[j, i_b] >= self.n_fluid:
                v = self.g_psi[self.orig_id[j, i_b] - self.n_fluid]
            return v

        @qd.kernel
        def kernel_place_ghosts(self, links_state: array_class.LinksState):
            for g, i_b in qd.ndrange(self.n_ghost, self._B):
                i = self.n_fluid + g
                pos = qd_transform_by_trans_quat_fast(
                    self.g_local[g], links_state.pos[self.body_link, i_b], links_state.quat[self.body_link, i_b]
                )
                self.particles[i, i_b].pos = pos
                self.particles[i, i_b].vel = self.sim.rigid_solver._func_vel_at_point(
                    pos_world=pos, link_idx=self.body_link, i_b=i_b, links_state=links_state
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
            """Jacobi diagonal of a ghost's constraint, of the same form as a liquid particle's (|sum_j V gradW|^2 + the
            liquid neighbours' sum_j |V gradW|^2). With the liquid term alone, a liquid particle touching a wall region
            where it is the ghosts' only liquid neighbour (a thin stream over a rim, a drop landing) is pushed off by every
            one of those ghosts, each correcting the whole error: the Jacobi iteration overshoots by the number of ghosts
            and diverges. Ghosts without liquid neighbours carry no pressure."""
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
                    if velocity_only:   # only the compression this substep's motion would add beyond max(rho, 1)
                        drho = 1.0 + qd.max(rho + self._substep_dt * delta - qd.max(rho, 1.0), 0.0)
                    self.particles_reordered[i_p, i_b].drho = drho

        # ---------------------------------------------------------------- non-pressure forces (fluid only)
        @qd.func
        def _task_compute_non_pressure_forces(self, i, j, ret: qd.template(), i_b: qd.i32):
            if self.orig_id[i, i_b] < self.n_fluid and self.orig_id[j, i_b] < self.n_fluid:
                d_ij = self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
                dist = d_ij.norm()
                gamma_i = self.particles_info_reordered[i, i_b].gamma
                mass_i = self.particles_info_reordered[i, i_b].mass
                mu_i = self.particles_info_reordered[i, i_b].mu
                mass_j = self.particles_info_reordered[j, i_b].mass
                effective_dist = dist if dist > self._particle_size else self._particle_size
                ret -= gamma_i / mass_i * mass_j * d_ij * self.cubic_kernel(effective_dist)
                v_ij = (self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel).dot(d_ij)
                rho_j = self.particles_reordered[j, i_b].rho
                ret += (10.0 * mu_i * (mass_j / rho_j) * v_ij / (dist ** 2 + 0.01 * self._support_radius ** 2)
                        * self.cubic_kernel_derivative(d_ij))
            elif qd.static(self.ghost_noslip) and self.orig_id[i, i_b] < self.n_fluid:
                d_ij = self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
                v_ij = (self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel).dot(d_ij)
                ret += (10.0 * self.particles_info_reordered[i, i_b].mu * self.g_visc[self.orig_id[j, i_b] - self.n_fluid]
                        * self.vol(j, i_b) * v_ij
                        / (d_ij.norm_sqr() + 0.01 * self._support_radius ** 2) * self.cubic_kernel_derivative(d_ij))
                ret -= (self.g_drag[self.orig_id[j, i_b] - self.n_fluid] * self.vol(j, i_b) * self.cubic_kernel(d_ij.norm())
                        * (self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel))

        # ---------------------------------------------------------------- pressure iterations with body feedback
        @qd.func
        def _task_pressure_iteration(self, i, j, ret: qd.template(), i_b):
            grad_p_j = -self.vol(j, i_b) * self.cubic_kernel_derivative(
                self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
            )
            if self.orig_id[j, i_b] < self.n_fluid:
                k_j = (self.particles_reordered[j, i_b].drho - ret.offset) * self.particles_reordered[j, i_b].dfsph_factor
                k_sum = ret.k_i + k_j
                if qd.abs(k_sum) > self._df_eps:
                    ret.dv -= ret.scale * k_sum * grad_p_j
            else:   # ghost: its own pressure as well as the particle's; only the particle moves
                k_sum = ret.k_i + (self.particles_reordered[j, i_b].drho - ret.offset) * self.particles_reordered[j, i_b].dfsph_factor
                if qd.abs(k_sum) > self._df_eps:
                    dv = -ret.scale * k_sum * grad_p_j
                    ret.dv += dv
                    ret.imp += dv
                    ret.tq += (self.particles_reordered[j, i_b].pos - ret.com).cross(dv)

        @qd.kernel
        def kernel_pressure_iteration(self, offset: qd.f32, scale: qd.f32, impulses: qd.i32,
                                      links_state: array_class.LinksState):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    k_i = (self.particles_reordered[i_p, i_b].drho - offset) * self.particles_reordered[i_p, i_b].dfsph_factor
                    ret = qd.Struct(
                        dv=qd.Vector.zero(gs.qd_float, 3), k_i=k_i, offset=offset, scale=scale,
                        imp=qd.Vector.zero(gs.qd_float, 3), tq=qd.Vector.zero(gs.qd_float, 3),
                        com=links_state.root_COM[self.body_link, i_b],
                    )
                    self.sh.for_all_neighbors(
                        i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_pressure_iteration, i_b
                    )
                    self.particles_reordered.vel[i_p, i_b] = self.particles_reordered.vel[i_p, i_b] + ret.dv
                    if impulses and ret.imp.norm_sqr() > 0.0:
                        # opposite impulse on the body, spread over this substep as a force
                        coef = -self.particles_info_reordered[i_p, i_b].mass / self._substep_dt
                        force = coef * ret.imp
                        links_state.cfrc_coupling_vel[self.body_link, i_b] -= force
                        links_state.cfrc_coupling_ang[self.body_link, i_b] -= coef * ret.tq
                        self.force_sum[i_b] += force
                        if offset > 0.5:  # density solve
                            self.den_f[i_b] += force
                            self.den_t[i_b] += coef * ret.tq

        @qd.kernel
        def kernel_density_error_max(self, offset: qd.f32):
            self.err_max[None] = 0.0
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    qd.atomic_max(self.err_max[None], self._density0 * self.particles_reordered[i_p, i_b].drho - offset)

        def _divergence_solve(self, f):
            ls = self.sim.rigid_solver.dyn_state.links
            self._kernel_compute_density_time_derivative()
            eta = (1.0 / self._substep_dt) * self._df_max_error_div * 0.01 * self._density0
            it = 0
            while it < self._df_max_div_iters:
                self.kernel_pressure_iteration(0.0, 1.0, 1, ls)
                self._kernel_compute_density_time_derivative()
                err = self._kernel_compute_density_error(0.0) / self.n_fluid
                it += 1
                if err <= eta:
                    self.kernel_density_error_max(0.0)
                    if self.err_max[None] <= self.max_err_div * self._density0 / self._substep_dt:
                        break
            self.iter_counts[0] += it

        def _density_solve(self, f, velocity_only, impulses):
            """DFSPH density solve; the caller has scaled dfsph_factor by 1 / dt^2."""
            ls = self.sim.rigid_solver.dyn_state.links
            if impulses:
                self.den_f.fill(0); self.den_t.fill(0)
            self._kernel_compute_density_star(velocity_only)
            eta = (self.max_err_mom_avg if velocity_only else self.max_err_pos_avg) * self._density0
            worst = self.max_err_mom if velocity_only else self.max_err_den
            max_it = self.max_iters_mom if velocity_only else self._df_max_den_iters
            it = 0
            while it < max_it:
                self.kernel_pressure_iteration(1.0, self._substep_dt, impulses, ls)
                self._kernel_compute_density_star(velocity_only)
                err = self._kernel_compute_density_error(self._density0) / self.n_fluid
                it += 1
                if err <= eta:
                    self.kernel_density_error_max(self._density0)
                    if self.err_max[None] <= worst * self._density0:
                        break
            return it

        # ---------------------------------------------------------------- implicit viscosity (monolithic with the body)
        # Minimises E = 1/2 sum_i m |x_i - v*_i|^2 + 1/2 M |V - V*|^2 + 1/2 I |W - W*|^2
        #             + 1/2 a m [ sum_fluid pairs coef |n.(x_i - x_j)|^2 + sum_(i,g) coef |n.(x_i - V - W x r_g)|^2 ]
        # (a = dt nu, coef = -10 V_j W'(r) r / (r^2 + 0.01 h^2) >= 0): the projected SPH viscosity of Genesis, implicit,
        # with no-slip on the body whose velocity is solved together with the fluid. Its gradient system is SPD; the body's
        # momentum change M (V - V*), I (W - W*) is exactly the viscous impulse the fluid gave it, returned through the
        # rigid coupling wrench. V*, W* are the velocities the rigid solver would reach without it in its next substep.
        # The cup and saucer stay slip (fluid neighbours only).
        @qd.func
        def kernel_dw(self, r):
            h = self._support_radius
            k = 8.0 / np.pi / h ** 3
            q = r / h
            res = gs.qd_float(0.0)
            if q <= 1.0:
                if q <= 0.5:
                    res = 6.0 * k * q * (3.0 * q - 2.0) / h
                else:
                    res = -6.0 * k * (1.0 - q) ** 2 / h
            return res

        @qd.func
        def visc_coef(self, r, vol):
            return -10.0 * vol * self.kernel_dw(r) * r / (r * r + 0.01 * self._support_radius ** 2)

        @qd.func
        def skew(self, v):
            return qd.Matrix([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]], dt=gs.qd_float)

        @qd.func
        def _task_visc_setup(self, i, j, ret: qd.template(), i_b):
            if j != i:
                xij = self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
                r = xij.norm()
                if r > 1e-9:
                    nrm = xij / r
                    coef = self.visc_coef(r, self.vol(j, i_b))
                    P = nrm.outer_product(nrm)
                    ret.D += coef * P
                    if self.orig_id[j, i_b] >= self.n_fluid:
                        R = self.skew(self.particles_reordered[j, i_b].pos - ret.com)
                        k = ret.ma * coef
                        self.body_D[0, i_b] += k * P
                        self.body_D[1, i_b] += k * (R.transpose() @ P @ R)

        @qd.kernel
        def kernel_visc_setup(self, a: qd.f32, links_state: array_class.LinksState):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                v = self.particles_reordered[i_p, i_b].vel
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    m = self.particles_info_reordered[i_p, i_b].mass
                    ret = qd.Struct(D=qd.Matrix.zero(gs.qd_float, 3, 3), ma=m * a, com=links_state.root_COM[self.body_link, i_b])
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_visc_setup, i_b)
                    self.vis_Minv[i_p, i_b] = (m * (qd.Matrix.identity(gs.qd_float, 3) + a * ret.D)).inverse()
                    self.vis_x[i_p, i_b] = v; self.vis_b[i_p, i_b] = m * v; self.vis_p[i_p, i_b] = v
                else:
                    self.vis_Minv[i_p, i_b] = qd.Matrix.zero(gs.qd_float, 3, 3)
                    self.vis_x[i_p, i_b] = v; self.vis_b[i_p, i_b] = qd.Vector.zero(gs.qd_float, 3)
                    self.vis_p[i_p, i_b] = qd.Vector.zero(gs.qd_float, 3)

        @qd.kernel
        def kernel_body_setup(self, links_state: array_class.LinksState):
            for i_b in range(self._B):
                # the body's velocity after the rigid solver's next substep: gravity, this substep's divergence-solve
                # wrench (cfrc_coupling holds minus the force) and the last density solve's wrench as the estimate of
                # this one's (the cube's inertia is isotropic)
                dt = self._substep_dt
                F = self.den_f[i_b] - links_state.cfrc_coupling_vel[self.body_link, i_b]
                T = self.den_t[i_b] - links_state.cfrc_coupling_ang[self.body_link, i_b]
                V0 = links_state.cd_vel[self.body_link, i_b] + dt * (self._gravity[i_b] + F / self.body_mass)
                W0 = links_state.cd_ang[self.body_link, i_b] + dt * T / self.body_inertia
                if qd.static(self.ghost_fixed):
                    V0 = qd.Vector.zero(gs.qd_float, 3); W0 = qd.Vector.zero(gs.qd_float, 3)
                self.body_v0[0, i_b] = V0; self.body_v0[1, i_b] = W0
                self.body_x[0, i_b] = V0; self.body_x[1, i_b] = W0
                self.body_p[0, i_b] = V0; self.body_p[1, i_b] = W0
                self.body_b[0, i_b] = self.body_mass * V0; self.body_b[1, i_b] = self.body_inertia * W0
                self.body_Minv[0, i_b] = (self.body_mass * qd.Matrix.identity(gs.qd_float, 3) + self.body_D[0, i_b]).inverse()
                self.body_Minv[1, i_b] = (self.body_inertia * qd.Matrix.identity(gs.qd_float, 3) + self.body_D[1, i_b]).inverse()
                if qd.static(self.ghost_fixed):
                    self.body_Minv[0, i_b] = qd.Matrix.zero(gs.qd_float, 3, 3)
                    self.body_Minv[1, i_b] = qd.Matrix.zero(gs.qd_float, 3, 3)

        @qd.func
        def _task_visc_apply(self, i, j, ret: qd.template(), i_b):
            if j != i:
                xij = self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
                r = xij.norm()
                if r > 1e-9:
                    nrm = xij / r
                    coef = self.visc_coef(r, self.vol(j, i_b))
                    if self.orig_id[j, i_b] < self.n_fluid:
                        ret.acc += coef * nrm.dot(self.vis_p[i, i_b] - self.vis_p[j, i_b]) * nrm
                    else:
                        rg = self.particles_reordered[j, i_b].pos - ret.com
                        vg = self.body_p[0, i_b] + self.body_p[1, i_b].cross(rg)
                        rel = coef * nrm.dot(self.vis_p[i, i_b] - vg) * nrm
                        ret.acc += rel
                        t = -ret.ma * rel                     # dE/dV contribution: m a coef P (v_g - p_i)
                        self.body_Ap[0, i_b] += t
                        self.body_Ap[1, i_b] += rg.cross(t)

        @qd.kernel
        def kernel_visc_apply(self, a: qd.f32, links_state: array_class.LinksState):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                out = qd.Vector.zero(gs.qd_float, 3)
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    m = self.particles_info_reordered[i_p, i_b].mass
                    ret = qd.Struct(acc=qd.Vector.zero(gs.qd_float, 3), ma=m * a, com=links_state.root_COM[self.body_link, i_b])
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_visc_apply, i_b)
                    out = m * self.vis_p[i_p, i_b] + m * a * ret.acc
                self.vis_Ap[i_p, i_b] = out

        @qd.kernel
        def kernel_body_Ap_begin(self):
            for i_b in range(self._B):
                self.body_Ap[0, i_b] = self.body_mass * self.body_p[0, i_b]
                self.body_Ap[1, i_b] = self.body_inertia * self.body_p[1, i_b]

        def visc_apply(self, a, ls):
            self.kernel_body_Ap_begin()
            self.kernel_visc_apply(a, ls)

        @qd.kernel
        def kernel_visc_init_residual(self) -> qd.f32:
            rz = gs.qd_float(0.0)
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                r = self.vis_b[i_p, i_b] - self.vis_Ap[i_p, i_b]
                z = self.vis_Minv[i_p, i_b] @ r
                self.vis_r[i_p, i_b] = r; self.vis_z[i_p, i_b] = z; self.vis_p[i_p, i_b] = z
                rz += r.dot(z)
            for k, i_b in qd.ndrange(2, self._B):
                r = self.body_b[k, i_b] - self.body_Ap[k, i_b]
                z = self.body_Minv[k, i_b] @ r
                self.body_r[k, i_b] = r; self.body_z[k, i_b] = z; self.body_p[k, i_b] = z
                rz += r.dot(z)
            return rz

        @qd.kernel
        def kernel_visc_bMb(self) -> qd.f32:
            """|b|^2 in the preconditioner metric: the scale for the stopping test (the initial residual, from the warm
            start x0 = v*, is already small, so a test relative to it would never converge)"""
            s_ = gs.qd_float(0.0)
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                s_ += self.vis_b[i_p, i_b].dot(self.vis_Minv[i_p, i_b] @ self.vis_b[i_p, i_b])
            for k, i_b in qd.ndrange(2, self._B):
                s_ += self.body_b[k, i_b].dot(self.body_Minv[k, i_b] @ self.body_b[k, i_b])
            return s_

        @qd.kernel
        def kernel_visc_dot_pAp(self) -> qd.f32:
            s_ = gs.qd_float(0.0)
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                s_ += self.vis_p[i_p, i_b].dot(self.vis_Ap[i_p, i_b])
            for k, i_b in qd.ndrange(2, self._B):
                s_ += self.body_p[k, i_b].dot(self.body_Ap[k, i_b])
            return s_

        @qd.kernel
        def kernel_visc_step(self, alpha: qd.f32) -> qd.f32:
            rz = gs.qd_float(0.0)
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                self.vis_x[i_p, i_b] += alpha * self.vis_p[i_p, i_b]
                r = self.vis_r[i_p, i_b] - alpha * self.vis_Ap[i_p, i_b]
                z = self.vis_Minv[i_p, i_b] @ r
                self.vis_r[i_p, i_b] = r; self.vis_z[i_p, i_b] = z
                rz += r.dot(z)
            for k, i_b in qd.ndrange(2, self._B):
                self.body_x[k, i_b] += alpha * self.body_p[k, i_b]
                r = self.body_r[k, i_b] - alpha * self.body_Ap[k, i_b]
                z = self.body_Minv[k, i_b] @ r
                self.body_r[k, i_b] = r; self.body_z[k, i_b] = z
                rz += r.dot(z)
            return rz

        @qd.kernel
        def kernel_visc_new_direction(self, beta: qd.f32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                self.vis_p[i_p, i_b] = self.vis_z[i_p, i_b] + beta * self.vis_p[i_p, i_b]
            for k, i_b in qd.ndrange(2, self._B):
                self.body_p[k, i_b] = self.body_z[k, i_b] + beta * self.body_p[k, i_b]

        @qd.kernel
        def kernel_visc_store(self, links_state: array_class.LinksState):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    self.particles_reordered[i_p, i_b].vel = self.vis_x[i_p, i_b]
            for i_b in range(self._B):
                # the body's viscous momentum change, applied by the rigid solver in its next substep, which then ends at
                # the solved velocity plus this density solve's wrench minus its estimate
                F = self.body_mass * (self.body_x[0, i_b] - self.body_v0[0, i_b]) / self._substep_dt
                T = self.body_inertia * (self.body_x[1, i_b] - self.body_v0[1, i_b]) / self._substep_dt
                links_state.cfrc_coupling_vel[self.body_link, i_b] -= F
                links_state.cfrc_coupling_ang[self.body_link, i_b] -= T
                self.force_sum[i_b] += F

        @qd.kernel
        def kernel_visc_add_estimate(self, sign: qd.f32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    self.particles_reordered[i_p, i_b].vel += sign * self.vis_est[self.orig_id[i_p, i_b], i_b]

        @qd.kernel
        def kernel_visc_save_out(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                self.vis_out[i_p, i_b] = self.particles_reordered[i_p, i_b].vel

        @qd.kernel
        def kernel_visc_measure_estimate(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    self.vis_est[self.orig_id[i_p, i_b], i_b] = self.particles_reordered[i_p, i_b].vel - self.vis_out[i_p, i_b]

        def implicit_viscosity(self, tol=1e-4, max_iter=600):
            ls = self.sim.rigid_solver.dyn_state.links
            a = self._substep_dt * self.visc_nu
            self.body_D.fill(0)
            self.kernel_visc_setup(a, ls)
            self.kernel_body_setup(ls)
            self.visc_apply(a, ls)                         # A x0 (p holds x0)
            rz = float(self.kernel_visc_init_residual())
            rz0 = max(float(self.kernel_visc_bMb()), 1e-30)
            it = 0; rel = 1.0
            while it < max_iter:
                rel = (max(rz, 0.0) / rz0) ** 0.5
                if rel < tol or rz <= 0.0:
                    break
                self.visc_apply(a, ls)                     # A p
                pAp = float(self.kernel_visc_dot_pAp())
                if pAp <= 0:
                    break
                rz_new = float(self.kernel_visc_step(rz / pAp))
                it += 1
                self.kernel_visc_new_direction(rz_new / rz)
                rz = rz_new
            self.kernel_visc_store(ls)
            self.visc_stats[0] += it; self.visc_stats[1] += 1; self.visc_stats[2] = max(self.visc_stats[2], rel)

        @qd.func
        def _task_contact_line(self, i, j, ret: qd.template(), i_b):
            if self.orig_id[j, i_b] >= self.n_fluid:
                lam = self.g_cl[self.orig_id[j, i_b] - self.n_fluid]
                if lam > 0.0:
                    w = self.vol(j, i_b) * self.cubic_kernel(
                        (self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos).norm())
                    ret.w += w
                    ret.lw += lam * w
                    ret.v += w * self.particles_reordered[j, i_b].vel

        @qd.kernel
        def kernel_contact_line_friction(self, n_ref: qd.f32):
            """Contact-line friction. A liquid edge on a partially wetting solid moves against a dissipation 100-1000 times
            the liquid's viscosity, concentrated where liquid, solid and air meet (contact-angle hysteresis, pinning). It is
            what stops a spreading puddle at its capillary thickness; without it a 1 mm-particle sheet spreads to a single
            particle layer and dewets into a lace of drops. Applied (implicitly) to a liquid particle's velocity relative to
            the wall, weighted by its wall kernel share (1 at contact) and by how much it is a free-surface particle (the
            surface-tension normal |n|, 0 inside the liquid): it acts on the contact line and on films a few particles
            thick, not on the bulk of a puddle or a stream."""
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    ret = qd.Struct(w=gs.qd_float(0.0), lw=gs.qd_float(0.0), v=qd.Vector.zero(gs.qd_float, 3))
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret,
                                              self._task_contact_line, i_b)
                    if ret.w > 0.0:
                        chi = qd.min(self.st_n[i_p, i_b].norm() / n_ref, 1.0)
                        share = qd.min(ret.w / 0.5, 1.0)
                        v_wall = ret.v / ret.w
                        rate = self._substep_dt * (ret.lw / ret.w) * chi * share
                        self.particles_reordered[i_p, i_b].vel = v_wall + (self.particles_reordered[i_p, i_b].vel - v_wall) / (1.0 + rate)

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
            """Take the position correction out of the velocity again, and make it inelastic: the velocity component
            against the correction, up to its size, is removed (never added). Otherwise a motion that the position part
            undoes every substep is never seen by the momentum part and persists: a resting column kept ~4 cm/s of
            downward velocity while being lifted back by the same amount each substep. The approach is measured
            relative to the particle's neighbours (Galilean invariant): measured absolutely, every correction of a
            liquid in free fall or in a moving stream would brake or kick the whole body."""
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    dvp = self.dv_pos[i_p, i_b]
                    v = self.particles_reordered[i_p, i_b].vel - dvp
                    m = dvp.norm()
                    if m > 0.0:
                        n = dvp / m
                        a = (v - self.v_nb[i_p, i_b]).dot(n)
                        if a < 0.0:
                            v -= qd.max(a, -m) * n
                    self.particles_reordered[i_p, i_b].vel = v

        def split_density_solve(self, f):
            """DFSPH's density solve removes the whole density error of a particle within one substep through its velocity,
            and the velocity stays: like Baumgarte stabilisation of a rigid contact, a compressed layer (a column stopped
            by the mug floor, whose reaction reaches the mug one substep late) springs back with the energy of the
            correction, the liquid rebounds and the free surface at the walls is shot off at several m/s.
            Split as in implicit density projection (Kugelstadt et al. 2019): the compression this substep's motion would
            add is removed from the velocity (with the equal and opposite impulse on the mug); the compression that
            already exists is removed from the positions only, without changing any velocity or momentum."""
            self._kernel_multiply_time_step(self.particles_reordered.dfsph_factor, 1.0 / self._substep_dt ** 2)
            self.iter_counts[1] += self._density_solve(f, 1, 1)
            self.kernel_save_vel()
            self.iter_counts[3] += self._density_solve(f, 0, 0)
            self.kernel_store_dv_pos()
            self.kernel_neighbour_velocity()

        @qd.kernel
        def kernel_inlet(self, t: qd.f32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                o = self.orig_id[i_p, i_b]
                if self.particles_ng_reordered[i_p, i_b].active and o < self.n_fluid:
                    if t < self.inlet_t[o]:
                        self.particles_reordered[i_p, i_b].vel = self.inlet_v[o]

        def substep_pre_coupling(self, f):
            if not self.is_active:
                return
            self.kernel_place_ghosts(self.sim.rigid_solver.dyn_state.links)
            self._kernel_reorder_particles(f)
            self.kernel_orig_ids()
            self.kernel_inlet(self._sim.cur_t)
            self._kernel_compute_rho(f)
            self._kernel_compute_DFSPH_factor(f)
            self.kernel_ghost_factor()
            self.kernel_ghost_acc()
            self._divergence_solve(f)
            self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
            self.surface_tension()
            self.kernel_ghost_acc()
            self._kernel_predict_velocity(f)
            if self.cl_on:
                self.kernel_contact_line_friction(0.5)
            if self.visc_nu > 0:
                if self.visc_on:
                    self.kernel_visc_add_estimate(1.0)
                    self.implicit_viscosity()
                    self.kernel_visc_add_estimate(-1.0)
                self.kernel_visc_save_out()
            self.split_density_solve(f)
            self._xsph_pre()
            self.iter_counts[2] += 1

        def substep_post_coupling(self, f):
            if not self.is_active:
                return
            if self.visc_nu > 0:
                self.kernel_visc_measure_estimate()   # after the density solve and the coupler's mug projection
            self.kernel_inlet(self._sim.cur_t)         # the buffer moves with the inlet velocity, whatever pulls on it
            self._kernel_advect_position(f)           # the position correction moves the particles ...
            self.kernel_remove_dv_pos()               # ... but is not kept in their velocity
            self._kernel_copy_from_reordered(f)

    return GhostBoundarySPH
