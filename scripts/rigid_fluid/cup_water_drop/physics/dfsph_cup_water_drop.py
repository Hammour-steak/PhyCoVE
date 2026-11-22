"""Genesis 1.4.3 DFSPH patches for physical gravity integration, XSPH, and partial-wetting surface tension."""
import numpy as np
import quadrants as qd
import genesis as gs

# Compile-time solver controls (set via install_* before scene.build)
XSPH_EPS = 0.0
XSPH_MODE = "position"
DIV_NMIN = 20
ST_GAMMA = 0.0
ST_WALL_WEIGHT = 0.55   # Glazed porcelain partial wetting (~50-55 deg contact angle; 1.0 = superhydrophilic 0 deg)


def install_dfsph_gravity_fix():
    """Drop Genesis 1.4.3's duplicate WCSPH _kernel_advect_velocity inside DFSPH substep_pre_coupling.

    Genesis 1.4.3 runs _kernel_advect_velocity with the previous substep's non-pressure acceleration
    and then _kernel_predict_velocity with the current substep's, causing free liquid to fall at 2 g.
    """
    from genesis.engine.solvers.sph_solver import SPHSolver

    def substep_pre_coupling(self, f):
        if self.is_active:
            self._kernel_reorder_particles(f)
            if self._pressure_solver == "WCSPH":
                self._kernel_compute_rho(f)
                self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
                self._kernel_compute_pressure_forces(f)
                self._kernel_advect_velocity(f)
            else:
                self._kernel_compute_rho(f)
                self._kernel_compute_DFSPH_factor(f)
                self._divergence_solve(f)
                self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
                if hasattr(self, "surface_tension"):
                    self.surface_tension()
                self._kernel_predict_velocity(f)
                self._density_solve(f)

    SPHSolver.substep_pre_coupling = substep_pre_coupling


def make_xsph_solver(base):
    """Extend SPHSolver with Akinci et al. (2013) cohesion/curvature surface tension and optional XSPH."""

    @qd.data_oriented
    class XSPHSolver(base):
        @qd.func
        def _xsph_fluid(self, j, i_b):
            return True

        def build(self):
            super().build()
            if self.is_active and ST_GAMMA > 0:
                self.st_n = qd.Vector.field(3, gs.qd_float, shape=(self._n_particles, self._B))

        @qd.func
        def _task_st_normal(self, i, j, ret: qd.template(), i_b):
            w = gs.qd_float(1.0)
            if not self._xsph_fluid(j, i_b):
                w = gs.qd_float(ST_WALL_WEIGHT)
            ret += w * self._particle_volume * self.cubic_kernel_derivative(
                self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
            )

        @qd.kernel
        def kernel_st_normal(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                n = qd.Vector.zero(gs.qd_float, 3)
                if self.particles_ng_reordered[i_p, i_b].active and self._xsph_fluid(i_p, i_b):
                    self.sh.for_all_neighbors(
                        i_p, self.particles_reordered.pos, self._support_radius, n, self._task_st_normal, i_b
                    )
                self.st_n[i_p, i_b] = self._support_radius * n

        @qd.func
        def _task_st_force(self, i, j, ret: qd.template(), i_b):
            d = self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
            r = d.norm()
            h = self._support_radius
            if r > 1e-9 and r <= h:
                c = (h - r) ** 3 * r ** 3
                if 2.0 * r <= h:
                    c = 2.0 * c - h ** 6 / 64.0
                c *= 32.0 / (np.pi * h ** 9)
                k = 2.0 * self._density0 / (self.particles_reordered[i, i_b].rho + self.particles_reordered[j, i_b].rho)
                if self._xsph_fluid(j, i_b):
                    a = self.particles_info_reordered[j, i_b].mass * c * d / r + (self.st_n[i, i_b] - self.st_n[j, i_b])
                    ret -= k * a
                else:
                    a = gs.qd_float(ST_WALL_WEIGHT) * self.particles_info_reordered[j, i_b].mass * c * d / r
                    ret -= k * a

        @qd.kernel
        def kernel_st_force(self, gamma: qd.f32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active and self._xsph_fluid(i_p, i_b):
                    p_i = self.particles_reordered[i_p, i_b].pos
                    # Smoothly turn off free-air spherical cohesion for landed thin films on tabletop (z < 3.5 mm)
                    w_air = gs.qd_float(1.0)
                    if p_i[2] < 0.0035 and (p_i[0] * p_i[0] + p_i[1] * p_i[1]) > 0.042 * 0.042:
                        w_air = qd.max((p_i[2] - 0.0012) / 0.0023, 0.0)
                    if w_air > 0.0:
                        a = qd.Vector.zero(gs.qd_float, 3)
                        self.sh.for_all_neighbors(
                            i_p, self.particles_reordered.pos, self._support_radius, a, self._task_st_force, i_b
                        )
                        self.particles_reordered[i_p, i_b].acc += (gamma * w_air) * a

        def surface_tension(self):
            if ST_GAMMA > 0:
                self.kernel_st_normal()
                self.kernel_st_force(ST_GAMMA)

        @qd.func
        def _task_xsph(self, i, j, ret: qd.template(), i_b):
            if self._xsph_fluid(j, i_b):
                r = (self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos).norm()
                ret += self._particle_volume * self.cubic_kernel(r) * (
                    self.particles_reordered[j, i_b].vel - self.particles_reordered[i, i_b].vel
                )

        @qd.kernel
        def _kernel_xsph(self, eps: qd.f32, apply_to_velocity: qd.i32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                dv = qd.Vector.zero(gs.qd_float, 3)
                if self.particles_ng_reordered[i_p, i_b].active and self._xsph_fluid(i_p, i_b):
                    self.sh.for_all_neighbors(
                        i_p, self.particles_reordered.pos, self._support_radius, dv, self._task_xsph, i_b
                    )
                self.particles_reordered[i_p, i_b].acc = eps * dv
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if apply_to_velocity and self.particles_ng_reordered[i_p, i_b].active and self._xsph_fluid(i_p, i_b):
                    self.particles_reordered[i_p, i_b].vel += self.particles_reordered[i_p, i_b].acc

        def _xsph_pre(self):
            if XSPH_EPS > 0:
                self._kernel_xsph(XSPH_EPS, int(XSPH_MODE == "velocity"))

        @qd.kernel
        def _kernel_advect_position_xsph(self, f: qd.i32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    pos = self.particles_reordered[i_p, i_b].pos
                    vel = self.particles_reordered[i_p, i_b].vel
                    new_pos = pos + self._substep_dt * (vel + self.particles_reordered[i_p, i_b].acc)
                    corrected_pos, corrected_vel = self.boundary.impose_pos_vel(new_pos, vel)
                    self.particles_reordered[i_p, i_b].vel = corrected_vel
                    self.particles_reordered[i_p, i_b].pos = corrected_pos

        @qd.kernel
        def _kernel_compute_density_time_derivative(self):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    ret = qd.Struct(drho=0.0, num_neighbors=0)
                    self.sh.for_all_neighbors(
                        i_p, self.particles_reordered.pos, self._support_radius, ret,
                        self._task_compute_density_time_derivative, i_b,
                    )
                    drho = qd.max(ret.drho, 0.0)
                    if ret.num_neighbors < qd.static(DIV_NMIN):
                        drho = 0.0
                    self.particles_reordered[i_p, i_b].drho = drho

        def substep_pre_coupling(self, f):
            super().substep_pre_coupling(f)
            if self.is_active:
                self._xsph_pre()

        def substep_post_coupling(self, f):
            if self.is_active and XSPH_EPS > 0 and XSPH_MODE == "position":
                self._kernel_advect_position_xsph(f)
                self._kernel_copy_from_reordered(f)
            else:
                super().substep_post_coupling(f)

    return XSPHSolver


def install_quiet(xsph=0.0, mode="position", div_nmin=20):
    global XSPH_EPS, XSPH_MODE, DIV_NMIN
    XSPH_EPS, XSPH_MODE, DIV_NMIN = float(xsph), mode, int(div_nmin)


def install_surface_tension(gamma, wall_weight=0.55):
    global ST_GAMMA, ST_WALL_WEIGHT
    ST_GAMMA = float(gamma)
    ST_WALL_WEIGHT = float(wall_weight)
