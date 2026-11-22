"""Two-way rigid-ice / DFSPH coupling with Akinci boundary particles and equal-and-opposite impulses.

The ice surface is sampled with ghost particles that move rigidly with the Genesis link. They enter the fluid's
density, DFSPH factor and velocity-divergence terms with Akinci boundary volumes psi = 1 / sum_k W, and receive
the mirrored pressure (k_i only, as in Bender & Koschier's DFSPH). Every pressure velocity change a ghost causes in
a fluid particle is returned to the ice as the opposite impulse (force and torque about the COM) through the rigid
solver's coupling wrench, which it consumes in the next substep. Genesis's native rigid<->SPH response is disabled
for the ice (needs_coup=False); the mug keeps its native velocity projection. The stale WCSPH velocity advection of
Genesis 1.4.3's DFSPH substep (double gravity) is not run.

Optional implicit viscosity (CONFIG["implicit_nu"] > 0, material mu ~ 0): between the explicit non-pressure step and
the density solve, the fluid and the ice velocities solve one SPD system (I - dt nu L) v = v*, with L the same
projected SPH Laplacian Genesis uses explicitly (L(v)_i = sum_j 10 V W'(r) r / (r^2 + 0.01 h^2) (x^ x^T)(v_i - v_j);
no-slip on the ice, slip on the mug), by conjugate gradients with a 3x3 block-Jacobi preconditioner. It is
unconditionally stable, so a 1.45 m^2/s coffee (explicit limit ~3e-8 s) runs at the normal substep.
The split is incremental (as in incremental pressure-correction schemes): v* also holds the velocity change the
density solve and the mug's projection gave each particle after the previous substep's viscosity, and the ice's v*
is the velocity the rigid solver will give it, with gravity and the previous density solve's wrench; the estimate is
taken out again after the solve. Without it the solve sees the liquid falling under this substep's gravity before its
support arrives, drags the no-slip ice down with it, and the ice creeps into a 1.45 m^2/s liquid at ~g dt (2-4 mm/s)
whatever the viscosity.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import numpy as np
import quadrants as qd
import genesis as gs
from scipy.spatial import cKDTree
from genesis.engine.solvers.sph_solver import SPHSolver
from genesis.utils import array_class
from genesis.utils.geom import qd_transform_by_trans_quat_fast

CONFIG = {}


def sample_box_surface(side, spacing):
    n = max(2, int(round(side / spacing)) + 1)
    g = np.linspace(-side / 2, side / 2, n)
    A, B = np.meshgrid(g, g, indexing="ij")
    faces = []
    for ax in range(3):
        o = [i for i in range(3) if i != ax]
        for s in (-1.0, 1.0):
            P = np.zeros((A.size, 3))
            P[:, o[0]] = A.ravel(); P[:, o[1]] = B.ravel(); P[:, ax] = s * side / 2
            faces.append(P)
    return np.unique(np.round(np.concatenate(faces), 10), axis=0)


def boundary_volumes(points, support):
    h = support; k = 8.0 / np.pi / h ** 3
    psi = np.zeros(len(points))
    for i, nb in enumerate(cKDTree(points).query_ball_point(points, h)):
        q = np.linalg.norm(points[nb] - points[i], axis=1) / h
        w = np.where(q <= 0.5, k * (6 * q ** 3 - 6 * q ** 2 + 1), 2 * k * (1 - q) ** 3)
        psi[i] = 1.0 / w.sum()
    return psi


def make_solver():
    import dfsph_coffee_ice_drop as _cp

    @qd.data_oriented
    class IceBoundarySPH(_cp.make_xsph_solver(SPHSolver)):
        def build(self):
            super().build()
            if not self.is_active:
                return
            self.n_fluid = int(CONFIG["n_fluid"])
            self.n_ghost = self._n_particles - self.n_fluid
            assert self.n_ghost == len(CONFIG["ghost_local"]) and self._B == 1
            self.ice_link = int(CONFIG["link_idx"])
            self.orig_id = qd.field(gs.qd_int, shape=(self._n_particles, self._B))
            self.g_local = qd.Vector.field(3, gs.qd_float, shape=(self.n_ghost,))
            self.g_psi = qd.field(gs.qd_float, shape=(self.n_ghost,))
            self.g_local.from_numpy(np.asarray(CONFIG["ghost_local"], np.float32))
            self.g_psi.from_numpy(np.asarray(CONFIG["ghost_psi"], np.float32))
            self.force_sum = qd.Vector.field(3, gs.qd_float, shape=(self._B,))
            self.iter_counts = [0, 0, 0]  # divergence iterations, density iterations, substeps
            self.visc_nu = float(CONFIG.get("implicit_nu", 0.0))
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
                # the ice's 6 rigid velocity DOFs join the same CG system (index 0 = linear V, 1 = angular W)
                ice = (2, self._B)
                self.ice_x = qd.Vector.field(3, gs.qd_float, shape=ice)
                self.ice_b = qd.Vector.field(3, gs.qd_float, shape=ice)
                self.ice_r = qd.Vector.field(3, gs.qd_float, shape=ice)
                self.ice_z = qd.Vector.field(3, gs.qd_float, shape=ice)
                self.ice_p = qd.Vector.field(3, gs.qd_float, shape=ice)
                self.ice_Ap = qd.Vector.field(3, gs.qd_float, shape=ice)
                self.ice_D = qd.Matrix.field(3, 3, gs.qd_float, shape=ice)
                self.ice_Minv = qd.Matrix.field(3, 3, gs.qd_float, shape=ice)
                self.ice_v0 = qd.Vector.field(3, gs.qd_float, shape=ice)
                self.ice_mass = float(CONFIG["ice_mass"]); self.ice_inertia = float(CONFIG["ice_inertia"])
                # incremental split: per-particle velocity change after the viscous solve (density solve + mug
                # projection, indexed by original particle id) and the velocity it was measured from (reordered index)
                self.vis_est = qd.Vector.field(3, gs.qd_float, shape=shape)
                self.vis_out = qd.Vector.field(3, gs.qd_float, shape=shape)
            # the density solve's force and torque on the ice in the last substep (the ice's estimate)
            self.den_f = qd.Vector.field(3, gs.qd_float, shape=(self._B,))
            self.den_t = qd.Vector.field(3, gs.qd_float, shape=(self._B,))

        # ---------------------------------------------------------------- helpers
        @qd.func
        def _xsph_fluid(self, j, i_b):
            return self.orig_id[j, i_b] < self.n_fluid

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
                    self.g_local[g], links_state.pos[self.ice_link, i_b], links_state.quat[self.ice_link, i_b]
                )
                self.particles[i, i_b].pos = pos
                self.particles[i, i_b].vel = self.sim.rigid_solver._func_vel_at_point(
                    pos_world=pos, link_idx=self.ice_link, i_b=i_b, links_state=links_state
                )
                self.particles[i, i_b].acc = qd.Vector.zero(gs.qd_float, 3)

        @qd.kernel
        def kernel_orig_ids(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng[i_p, i_b].active:
                    self.orig_id[self.particles_ng[i_p, i_b].reordered_idx, i_b] = i_p

        @qd.kernel
        def kernel_fix_ghosts(self, drho: qd.f32, zero_factor: qd.i32, zero_acc: qd.i32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] >= self.n_fluid:
                    self.particles_reordered[i_p, i_b].drho = drho
                    if zero_factor:
                        self.particles_reordered[i_p, i_b].dfsph_factor = 0.0
                    if zero_acc:
                        self.particles_reordered[i_p, i_b].acc = qd.Vector.zero(gs.qd_float, 3)

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
        def _kernel_compute_density_star(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    if self.orig_id[i_p, i_b] >= self.n_fluid:
                        self.particles_reordered[i_p, i_b].drho = 1.0
                    else:
                        delta = gs.qd_float(0.0)
                        self.sh.for_all_neighbors(
                            i_p, self.particles_reordered.pos, self._support_radius, delta,
                            self._task_compute_density_star, i_b,
                        )
                        drho = self.particles_reordered[i_p, i_b].rho / self._density0 + self._substep_dt * delta
                        self.particles_reordered[i_p, i_b].drho = qd.max(drho, 1.0)

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

        # ---------------------------------------------------------------- pressure iterations with ice feedback
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
            elif qd.abs(ret.k_i) > self._df_eps:
                dv = -ret.scale * ret.k_i * grad_p_j
                ret.dv += dv
                ret.imp += dv
                ret.tq += (self.particles_reordered[j, i_b].pos - ret.com).cross(dv)

        @qd.kernel
        def kernel_pressure_iteration(self, offset: qd.f32, scale: qd.f32, links_state: array_class.LinksState):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    k_i = (self.particles_reordered[i_p, i_b].drho - offset) * self.particles_reordered[i_p, i_b].dfsph_factor
                    ret = qd.Struct(
                        dv=qd.Vector.zero(gs.qd_float, 3), k_i=k_i, offset=offset, scale=scale,
                        imp=qd.Vector.zero(gs.qd_float, 3), tq=qd.Vector.zero(gs.qd_float, 3),
                        com=links_state.root_COM[self.ice_link, i_b],
                    )
                    self.sh.for_all_neighbors(
                        i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_pressure_iteration, i_b
                    )
                    self.particles_reordered.vel[i_p, i_b] = self.particles_reordered.vel[i_p, i_b] + ret.dv
                    if ret.imp.norm_sqr() > 0.0:
                        # opposite impulse on the ice, spread over this substep as a force
                        coef = -self.particles_info_reordered[i_p, i_b].mass / self._substep_dt
                        force = coef * ret.imp
                        links_state.cfrc_coupling_vel[self.ice_link, i_b] -= force
                        links_state.cfrc_coupling_ang[self.ice_link, i_b] -= coef * ret.tq
                        self.force_sum[i_b] += force
                        if offset > 0.5:  # density solve
                            self.den_f[i_b] += force
                            self.den_t[i_b] += coef * ret.tq

        def _divergence_solve(self, f):
            ls = self.sim.rigid_solver.dyn_state.links
            self._kernel_compute_density_time_derivative()
            self.kernel_fix_ghosts(0.0, 0, 0)
            eta = (1.0 / self._substep_dt) * self._df_max_error_div * 0.01 * self._density0
            it = 0
            while it < self._df_max_div_iters:
                self.kernel_pressure_iteration(0.0, 1.0, ls)
                self._kernel_compute_density_time_derivative()
                self.kernel_fix_ghosts(0.0, 0, 0)
                err = self._kernel_compute_density_error(0.0) / self.n_fluid
                it += 1
                if err <= eta:
                    break
            self.iter_counts[0] += it

        def _density_solve(self, f):
            ls = self.sim.rigid_solver.dyn_state.links
            self.den_f.fill(0); self.den_t.fill(0)
            self._kernel_compute_density_star()
            self._kernel_multiply_time_step(self.particles_reordered.dfsph_factor, 1.0 / self._substep_dt ** 2)
            eta = self._df_max_error_den * 0.01 * self._density0
            it = 0
            while it < self._df_max_den_iters:
                self.kernel_pressure_iteration(1.0, self._substep_dt, ls)
                self._kernel_compute_density_star()
                err = self._kernel_compute_density_error(self._density0) / self.n_fluid
                it += 1
                if err <= eta:
                    break
            self.iter_counts[1] += it

        # ---------------------------------------------------------------- implicit viscosity (monolithic with the ice)
        # Minimises E = 1/2 sum_i m |x_i - v*_i|^2 + 1/2 M |V - V*|^2 + 1/2 I |W - W*|^2
        #             + 1/2 a m [ sum_fluid pairs coef |n.(x_i - x_j)|^2 + sum_(i,g) coef |n.(x_i - V - W x r_g)|^2 ]
        # (a = dt nu, coef = -10 V_j W'(r) r / (r^2 + 0.01 h^2) >= 0): the projected SPH viscosity of Genesis, implicit,
        # with no-slip on the ice whose velocity is solved together with the fluid. Its gradient system is SPD; the ice's
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
                        self.ice_D[0, i_b] += k * P
                        self.ice_D[1, i_b] += k * (R.transpose() @ P @ R)

        @qd.kernel
        def kernel_visc_setup(self, a: qd.f32, links_state: array_class.LinksState):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                v = self.particles_reordered[i_p, i_b].vel
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    m = self.particles_info_reordered[i_p, i_b].mass
                    ret = qd.Struct(D=qd.Matrix.zero(gs.qd_float, 3, 3), ma=m * a, com=links_state.root_COM[self.ice_link, i_b])
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_visc_setup, i_b)
                    self.vis_Minv[i_p, i_b] = (m * (qd.Matrix.identity(gs.qd_float, 3) + a * ret.D)).inverse()
                    self.vis_x[i_p, i_b] = v; self.vis_b[i_p, i_b] = m * v; self.vis_p[i_p, i_b] = v
                else:
                    self.vis_Minv[i_p, i_b] = qd.Matrix.zero(gs.qd_float, 3, 3)
                    self.vis_x[i_p, i_b] = v; self.vis_b[i_p, i_b] = qd.Vector.zero(gs.qd_float, 3)
                    self.vis_p[i_p, i_b] = qd.Vector.zero(gs.qd_float, 3)

        @qd.kernel
        def kernel_ice_setup(self, links_state: array_class.LinksState):
            for i_b in range(self._B):
                # the ice's velocity after the rigid solver's next substep: gravity, this substep's divergence-solve
                # wrench (cfrc_coupling holds minus the force) and the last density solve's wrench as the estimate of
                # this one's (the cube's inertia is isotropic)
                dt = self._substep_dt
                F = self.den_f[i_b] - links_state.cfrc_coupling_vel[self.ice_link, i_b]
                T = self.den_t[i_b] - links_state.cfrc_coupling_ang[self.ice_link, i_b]
                V0 = links_state.cd_vel[self.ice_link, i_b] + dt * (self._gravity[i_b] + F / self.ice_mass)
                W0 = links_state.cd_ang[self.ice_link, i_b] + dt * T / self.ice_inertia
                self.ice_v0[0, i_b] = V0; self.ice_v0[1, i_b] = W0
                self.ice_x[0, i_b] = V0; self.ice_x[1, i_b] = W0
                self.ice_p[0, i_b] = V0; self.ice_p[1, i_b] = W0
                self.ice_b[0, i_b] = self.ice_mass * V0; self.ice_b[1, i_b] = self.ice_inertia * W0
                self.ice_Minv[0, i_b] = (self.ice_mass * qd.Matrix.identity(gs.qd_float, 3) + self.ice_D[0, i_b]).inverse()
                self.ice_Minv[1, i_b] = (self.ice_inertia * qd.Matrix.identity(gs.qd_float, 3) + self.ice_D[1, i_b]).inverse()

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
                        vg = self.ice_p[0, i_b] + self.ice_p[1, i_b].cross(rg)
                        rel = coef * nrm.dot(self.vis_p[i, i_b] - vg) * nrm
                        ret.acc += rel
                        t = -ret.ma * rel                     # dE/dV contribution: m a coef P (v_g - p_i)
                        self.ice_Ap[0, i_b] += t
                        self.ice_Ap[1, i_b] += rg.cross(t)

        @qd.kernel
        def kernel_visc_apply(self, a: qd.f32, links_state: array_class.LinksState):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                out = qd.Vector.zero(gs.qd_float, 3)
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    m = self.particles_info_reordered[i_p, i_b].mass
                    ret = qd.Struct(acc=qd.Vector.zero(gs.qd_float, 3), ma=m * a, com=links_state.root_COM[self.ice_link, i_b])
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret, self._task_visc_apply, i_b)
                    out = m * self.vis_p[i_p, i_b] + m * a * ret.acc
                self.vis_Ap[i_p, i_b] = out

        @qd.kernel
        def kernel_ice_Ap_begin(self):
            for i_b in range(self._B):
                self.ice_Ap[0, i_b] = self.ice_mass * self.ice_p[0, i_b]
                self.ice_Ap[1, i_b] = self.ice_inertia * self.ice_p[1, i_b]

        def visc_apply(self, a, ls):
            self.kernel_ice_Ap_begin()
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
                r = self.ice_b[k, i_b] - self.ice_Ap[k, i_b]
                z = self.ice_Minv[k, i_b] @ r
                self.ice_r[k, i_b] = r; self.ice_z[k, i_b] = z; self.ice_p[k, i_b] = z
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
                s_ += self.ice_b[k, i_b].dot(self.ice_Minv[k, i_b] @ self.ice_b[k, i_b])
            return s_

        @qd.kernel
        def kernel_visc_dot_pAp(self) -> qd.f32:
            s_ = gs.qd_float(0.0)
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                s_ += self.vis_p[i_p, i_b].dot(self.vis_Ap[i_p, i_b])
            for k, i_b in qd.ndrange(2, self._B):
                s_ += self.ice_p[k, i_b].dot(self.ice_Ap[k, i_b])
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
                self.ice_x[k, i_b] += alpha * self.ice_p[k, i_b]
                r = self.ice_r[k, i_b] - alpha * self.ice_Ap[k, i_b]
                z = self.ice_Minv[k, i_b] @ r
                self.ice_r[k, i_b] = r; self.ice_z[k, i_b] = z
                rz += r.dot(z)
            return rz

        @qd.kernel
        def kernel_visc_new_direction(self, beta: qd.f32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                self.vis_p[i_p, i_b] = self.vis_z[i_p, i_b] + beta * self.vis_p[i_p, i_b]
            for k, i_b in qd.ndrange(2, self._B):
                self.ice_p[k, i_b] = self.ice_z[k, i_b] + beta * self.ice_p[k, i_b]

        @qd.kernel
        def kernel_visc_store(self, links_state: array_class.LinksState):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self.orig_id[i_p, i_b] < self.n_fluid:
                    self.particles_reordered[i_p, i_b].vel = self.vis_x[i_p, i_b]
            for i_b in range(self._B):
                # the ice's viscous momentum change, applied by the rigid solver in its next substep, which then ends at
                # the solved velocity plus this density solve's wrench minus its estimate
                F = self.ice_mass * (self.ice_x[0, i_b] - self.ice_v0[0, i_b]) / self._substep_dt
                T = self.ice_inertia * (self.ice_x[1, i_b] - self.ice_v0[1, i_b]) / self._substep_dt
                links_state.cfrc_coupling_vel[self.ice_link, i_b] -= F
                links_state.cfrc_coupling_ang[self.ice_link, i_b] -= T
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
            self.ice_D.fill(0)
            self.kernel_visc_setup(a, ls)
            self.kernel_ice_setup(ls)
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

        def substep_pre_coupling(self, f):
            if not self.is_active:
                return
            self.kernel_place_ghosts(self.sim.rigid_solver.dyn_state.links)
            self._kernel_reorder_particles(f)
            self.kernel_orig_ids()
            self._kernel_compute_rho(f)
            self._kernel_compute_DFSPH_factor(f)
            self.kernel_fix_ghosts(0.0, 1, 1)
            self._divergence_solve(f)
            self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
            self.kernel_fix_ghosts(0.0, 1, 1)
            self._kernel_predict_velocity(f)
            if self.visc_nu > 0:
                if self.visc_on:
                    self.kernel_visc_add_estimate(1.0)
                    self.implicit_viscosity()
                    self.kernel_visc_add_estimate(-1.0)
                self.kernel_visc_save_out()
            self._density_solve(f)
            self._xsph_pre()
            self.iter_counts[2] += 1

        def substep_post_coupling(self, f):
            if self.is_active and self.visc_nu > 0:
                self.kernel_visc_measure_estimate()   # after the density solve and the coupler's mug projection
            super().substep_post_coupling(f)

    return IceBoundarySPH


def plane_psi_scale(particle_size, ghost_spacing, rest_spacing_ratio=0.9283):
    """Scale for psi = 1/sum W so that a fluid lattice layer resting half a rest spacing off a flat ghost sheet has
    exactly rest density. Akinci's psi assumes the sheet stands in for the whole missing half-space; with Genesis's
    V = 0.8 d^3 (support 2d) the fluid side already supplies 0.825 there, and unscaled ghosts hold the liquid ~1 d off
    the ice, adding ~30 % to the displaced volume."""
    d = particle_size; h = 2 * d; k = 8.0 / np.pi / h ** 3; V = 0.8 * d ** 3; s = rest_spacing_ratio * d

    def W(r):
        q = r / h
        return np.where(q <= 0.5, k * (6 * q ** 3 - 6 * q ** 2 + 1), np.where(q <= 1, 2 * k * (1 - q) ** 3, 0.0))

    g = np.arange(-6 * d, 6 * d + 1e-12, ghost_spacing)
    GX, GY = np.meshgrid(g, g)
    G = np.stack([GX.ravel(), GY.ravel(), np.zeros(GX.size)], 1)
    psi = 1.0 / W(np.linalg.norm(G - G[np.argmin(np.linalg.norm(G, axis=1))], axis=1)).sum()
    f = np.arange(-4 * d, 4 * d + 1e-12, s)
    z0 = 0.5 * s
    FX, FY, FZ = np.meshgrid(f, f, np.arange(6) * s + z0)
    F = np.stack([FX.ravel(), FY.ravel(), FZ.ravel()], 1)
    x = np.array([0.0, 0.0, z0])
    fluid = V * W(np.linalg.norm(F - x, axis=1)).sum()
    ghost = psi * W(np.linalg.norm(G - x, axis=1)).sum()
    return (1.0 - fluid) / ghost


def sample_box_shell(side, particle_size, layers=3, rest_spacing_ratio=0.9283):
    """Ghosts on the ice's own rest lattice: cell centres of an n^3 grid (n = side / rest spacing), outer `layers`
    shells only, so the outermost ghosts sit half a spacing inside every face and a fluid particle meeting the ice
    sees the same density as inside the liquid. psi = the fluid particle volume, rescaled for the grid's spacing."""
    n = max(2, int(round(side / (rest_spacing_ratio * particle_size))))
    sp = side / n
    c = -side / 2 + (np.arange(n) + 0.5) * sp
    X, Y, Z = np.meshgrid(c, c, c, indexing="ij")
    idx = np.stack(np.meshgrid(np.arange(n), np.arange(n), np.arange(n), indexing="ij"), -1).reshape(-1, 3)
    depth = np.minimum(idx, n - 1 - idx).min(axis=1)
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)[depth < layers]
    psi = np.full(len(P), 0.8 * particle_size ** 3 * (sp / (rest_spacing_ratio * particle_size)) ** 3)
    return P, psi
