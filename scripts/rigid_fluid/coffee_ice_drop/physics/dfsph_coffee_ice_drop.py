"""Optional patch of Genesis's rigid<->SPH response: drop the collision reaction on movable rigids.

Genesis applies both an SPH pressure force (Archimedes, see _func_collide_with_rigid_geom_robust) and the
reaction of the particle velocity projection to a movable rigid. At rest the projection keeps catching the
rigid as gravity pulls it into the fluid, so its reaction supports the body a second time and a 920 kg/m^3
cube floats only ~36 % submerged instead of 89 %. With mode "pressure" the projection still moves the
particles, but only the pressure force acts on the rigid.
"""
import quadrants as qd
import genesis as gs
from genesis.engine.couplers.legacy_coupler import LegacyCoupler
from genesis.utils import array_class


def install(mode: str):
    if mode == "both":
        return

    @qd.func
    def _func_collide_in_rigid_geom(self, pos_world, vel, mass, normal_rigid, influence, geom_idx, i_b,
                                    geoms_info: array_class.GeomsInfo, links_state: array_class.LinksState,
                                    rigid_info: array_class.RigidInfo):
        vel_rigid = self.rigid_solver._func_vel_at_point(
            pos_world=pos_world, link_idx=geoms_info.link_idx[geom_idx], i_b=i_b, links_state=links_state
        )
        rvel = vel - vel_rigid
        rvel_normal_magnitude = rvel.dot(normal_rigid)
        if rvel_normal_magnitude < 0:
            rvel_tan = rvel - rvel_normal_magnitude * normal_rigid
            rvel_tan_norm = rvel_tan.norm(gs.EPS)
            rvel_tan = (rvel_tan / rvel_tan_norm
                        * qd.max(0, rvel_tan_norm + rvel_normal_magnitude * geoms_info.coup_friction[geom_idx]))
            rvel_normal = -normal_rigid * rvel_normal_magnitude * geoms_info.coup_restitution[geom_idx]
            vel = vel_rigid + (rvel_tan + rvel_normal) * influence + rvel * (1 - influence)
        return vel

    LegacyCoupler._func_collide_in_rigid_geom = _func_collide_in_rigid_geom


def install_collision_only():
    """Keep Genesis's momentum-exchange collision (with its reaction on the rigid) and drop the separate
    pressure-force term, whose DFSPH pressure estimate is ~2x hydrostatic in this setup."""
    import genesis.utils.sdf as sdf

    @qd.func
    def _func_collide_with_rigid_geom_robust(self, pos_world, vel, mass, pressure, normal_prev, geom_idx, batch_idx,
                                             geoms_state: array_class.GeomsState, geoms_info: array_class.GeomsInfo,
                                             links_state: array_class.LinksState, links_info: array_class.LinksInfo,
                                             rigid_info: array_class.RigidInfo, sdf_info: array_class.SDFInfo,
                                             collider_static_config: qd.template()):
        signed_dist = sdf.sdf_func_world(geom_idx, batch_idx, pos_world, geoms_state, geoms_info, sdf_info)
        normal_rigid = sdf.sdf_func_normal_world(
            geom_idx, batch_idx, pos_world, geoms_state, geoms_info, rigid_info, sdf_info, collider_static_config
        )
        influence = qd.min(qd.exp(-signed_dist / max(1e-10, geoms_info.coup_softness[geom_idx])), 1)
        if influence > 0.1:
            vel = self._func_collide_in_rigid_geom(
                pos_world, vel, mass, normal_rigid, influence, geom_idx, batch_idx, geoms_info, links_state, rigid_info
            )
        return vel, normal_rigid

    LegacyCoupler._func_collide_with_rigid_geom_robust = _func_collide_with_rigid_geom_robust


def install_dfsph_gravity_fix():
    """Genesis 1.4.3's DFSPH substep runs _kernel_advect_velocity (the WCSPH integration step) with the previous
    substep's non-pressure acceleration and then _kernel_predict_velocity with the current one, so gravity,
    viscosity and cohesion act twice: a free blob falls at 2 g. Drop the stale advection (as the pool scene's
    pressure-boundary operator already does)."""
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
                self._kernel_predict_velocity(f)
                self._density_solve(f)

    SPHSolver.substep_pre_coupling = substep_pre_coupling





# resting-noise controls (set before scene.build; read as compile-time constants)
XSPH_EPS = 0.0          # XSPH strength
XSPH_MODE = "position"  # "position": Monaghan's XSPH, only the advection velocity is smoothed (no momentum change,
                        #             no added viscosity); "velocity": smooths the velocity itself (dissipative)
DIV_NMIN = 20           # Genesis skips the divergence correction for particles with fewer neighbours (free surface)


def make_xsph_solver(base):
    """SPH solver with optional XSPH smoothing and a configurable free-surface neighbour threshold for the divergence
    solve. Genesis's DFSPH leaves ~1 cm/s of incoherent particle noise in still liquid (loose tolerances, and surface
    particles with < 20 neighbours are never divergence-corrected); it makes a mirror-like surface and a floating body
    shimmer."""
    import genesis as gs

    @qd.data_oriented
    class XSPHSolver(base):
        @qd.func
        def _xsph_fluid(self, j, i_b):
            return True

        @qd.func
        def _task_xsph(self, i, j, ret: qd.template(), i_b):
            if self._xsph_fluid(j, i_b):
                r = (self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos).norm()
                ret += self._particle_volume * self.cubic_kernel(r) * (
                    self.particles_reordered[j, i_b].vel - self.particles_reordered[i, i_b].vel)

        @qd.kernel
        def _kernel_xsph(self, eps: qd.f32, apply_to_velocity: qd.i32):
            """acc <- eps * sum_j V (v_j - v_i) W (acc is free after the density solve); optionally add it to vel."""
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                dv = qd.Vector.zero(gs.qd_float, 3)
                if self.particles_ng_reordered[i_p, i_b].active and self._xsph_fluid(i_p, i_b):
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, dv, self._task_xsph, i_b)
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
                    self.sh.for_all_neighbors(i_p, self.particles_reordered.pos, self._support_radius, ret,
                                              self._task_compute_density_time_derivative, i_b)
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


def install_xsph(eps):
    install_quiet(xsph=eps, mode="velocity")
