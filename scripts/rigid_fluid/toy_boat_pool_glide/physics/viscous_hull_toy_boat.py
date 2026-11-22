"""Scene-local viscosity-dependent hull shear; does not edit installed Genesis.

This is an approximate finite-volume no-slip boundary closure using the existing
SDF kernel plane integral. It is Newtonian viscosity, not a calibrated mud/yield-
stress model. The original pressure and collision treatment is retained below.
"""
import quadrants as qd
import genesis as gs
import genesis.utils.sdf as sdf
from genesis.utils import array_class
from genesis.engine.couplers.legacy_coupler import LegacyCoupler

@qd.data_oriented
class HullViscousCoupler(LegacyCoupler):
    record_forces = False
    pressure_mode = "projected"
    water_level = 0.0
    quasistatic_planar_drag = False
    drag_radius = 0.0

    def build(self):
        self._hull_nu = float(self.sph_solver.entities[0].material.mu)
        self._record_forces = self.record_forces
        self._hydrostatic_pressure = self.pressure_mode == "hydrostatic"
        self._rho = float(self.sph_solver.entities[0].material.rho)
        self._surface_z = self.water_level
        self._qs_drag = self.quasistatic_planar_drag
        self._drag_r = self.drag_radius
        self.hull_impulses = qd.Vector.field(3, dtype=qd.f64, shape=4)
        self.drag_work = qd.field(dtype=qd.f64, shape=())
        super().build()

    def couple(self, f):
        super().couple(f)
        if self._qs_drag:
            self._kernel_planar_resistance(self.rigid_solver.dyn_state.links,
                                           self.rigid_solver.dyn_info.geoms,
                                           self.rigid_solver.rigid_info)

    @qd.func
    def _body_force(self, force):
        if qd.static(self._qs_drag):
            force = qd.Vector([0.0, 0.0, force[2]])
        return force

    @qd.func
    def _apply_hull_force(self, link_idx, batch_idx, pos_world, force, links_state: array_class.LinksState):
        self.rigid_solver._func_apply_coupling_force(link_idx, batch_idx, pos_world,
                                                   self._body_force(force), links_state)

    @qd.kernel
    def _kernel_planar_resistance(self, links_state: array_class.LinksState,
                                 geoms_info: array_class.GeomsInfo, rigid_info: array_class.RigidInfo):
        for i_g, i_b in qd.ndrange(self.rigid_solver.n_geoms, self.sph_solver._B):
            if geoms_info.needs_coup[i_g]:
                i_l = geoms_info.link_idx[i_g]
                v = links_state.cd_vel[i_l, i_b]
                planar = qd.Vector([v[0], v[1], 0.0])
                speed = planar.norm()
                reynolds = 2.0*self._drag_r*speed/qd.max(self._hull_nu, 1e-12)
                # Equal-displacement sphere, Schiller-Naumann finite-Re drag.
                # This is a reduced-order hull approximation in still far-field
                # fluid, not a resolved horizontal fluid/body pressure solve.
                factor = 1.0 + 0.15*reynolds**0.687
                if reynolds >= 1000.0:
                    factor = 0.44*reynolds/24.0
                coefficient = 6.0*3.141592653589793*self._rho*self._hull_nu*self._drag_r*factor
                force = -coefficient*planar
                self.rigid_solver._func_apply_coupling_force(i_l, i_b, links_state.root_COM[i_l,i_b], force, links_state)
                angular = links_state.cd_ang[i_l,i_b]
                rotational_coefficient = 8.0*3.141592653589793*self._rho*self._hull_nu*self._drag_r**3
                links_state.cfrc_coupling_ang[i_l,i_b] += rotational_coefficient*angular
                if qd.static(self._record_forces):
                    self.hull_impulses[3] += force*rigid_info.substep_dt[None]
                    self.drag_work[None] += (force.dot(planar)-rotational_coefficient*angular.dot(angular))*rigid_info.substep_dt[None]

    @qd.func
    def _func_collide_in_rigid_geom(self, pos_world, vel, mass, normal_rigid, influence,
                                   geom_idx, i_b, geoms_info: array_class.GeomsInfo,
                                   links_state: array_class.LinksState, rigid_info: array_class.RigidInfo):
        rigid_vel = self.rigid_solver._func_vel_at_point(pos_world=pos_world,
            link_idx=geoms_info.link_idx[geom_idx], i_b=i_b, links_state=links_state)
        relative = vel-rigid_vel
        normal_speed = relative.dot(normal_rigid)
        if normal_speed < 0:
            tangent = relative-normal_speed*normal_rigid
            tangent_norm = tangent.norm(gs.EPS)
            tangent = tangent/tangent_norm*qd.max(0, tangent_norm+normal_speed*geoms_info.coup_friction[geom_idx])
            normal = -normal_rigid*normal_speed*geoms_info.coup_restitution[geom_idx]
            before = vel
            vel = rigid_vel+(tangent+normal)*influence+relative*(1-influence)
            self._apply_hull_force(geoms_info.link_idx[geom_idx], i_b, pos_world,
                                  -mass*(vel-before)/rigid_info.substep_dt[None], links_state)
        return vel

    @qd.func
    def _func_collide_with_rigid_geom_robust(
        self,
        pos_world,
        vel,
        mass,
        pressure,
        normal_prev,
        geom_idx,
        batch_idx,
        geoms_state: array_class.GeomsState,
        geoms_info: array_class.GeomsInfo,
        links_state: array_class.LinksState,
        links_info: array_class.LinksInfo,
        rigid_info: array_class.RigidInfo,
        sdf_info: array_class.SDFInfo,
        collider_static_config: qd.template(),
    ):
        """
        Similar to _func_collide_with_rigid_geom, but additionally handles potential side flip due to penetration.
        """
        signed_dist = sdf.sdf_func_world(geom_idx, batch_idx, pos_world, geoms_state, geoms_info, sdf_info)
        normal_rigid = sdf.sdf_func_normal_world(
            geom_idx, batch_idx, pos_world, geoms_state, geoms_info, rigid_info, sdf_info, collider_static_config
        )

        # bigger coup_softness implies that the coupling influence extends further away from the object.
        influence = qd.min(qd.exp(-signed_dist / max(1e-10, geoms_info.coup_softness[geom_idx])), 1)

        # if normal_rigid.dot(normal_prev) < 0: # side flip due to penetration
        #     influence = 1.0
        #     normal_rigid = normal_prev
        if influence > 0.1:
            vel_before_collision = vel
            vel = self._func_collide_in_rigid_geom(
                pos_world, vel, mass, normal_rigid, influence, geom_idx, batch_idx, geoms_info, links_state, rigid_info
            )
            if qd.static(self._record_forces):
                self.hull_impulses[0] += self._body_force(-mass * (vel - vel_before_collision))

        # Static fluid pressure pushes on the geom even at rest, where the velocity-gated collision response above
        # transfers nothing; this is what makes submerged geoms buoyant. Mirroring the particle pressure across the
        # surface and integrating the symmetric pressure force over the truncated kernel support yields the factor
        # 2 * sigma(signed_dist), with sigma the kernel plane integral (see cubic_kernel_plane_integral in
        # sph_solver.py). Sigma integrates to 1/2 across the support band, so a covering particle layer transmits
        # exactly p per unit area: Archimedes buoyancy with no tuning constant. Fixed links are exempt: they cannot
        # respond to the force, and the reaction is a conservative stiff kick that keeps fluid resting on them
        # ringing forever, pumped by the acoustic pressure fluctuations of the fluid.
        link_idx = geoms_info.link_idx[geom_idx]
        I_l = [link_idx, batch_idx] if qd.static(self.rigid_solver._options.batch_links_info) else link_idx
        wall_pressure = pressure
        if qd.static(self._hydrostatic_pressure):
            # Hydrostatic support is separated from dynamic momentum exchange.
            # The incompressibility multiplier includes initial density-error
            # correction proportional to 1/dt^2; applying it again as an explicit
            # wall force can launch the body. Dynamic impact remains in the
            # two-way no-penetration collision above; tangential traction below.
            wall_pressure = self._rho * 9.81 * qd.max(self._surface_z - pos_world[2], 0.0)
        if signed_dist < self.sph_solver._support_radius and wall_pressure > 0 and not links_info.is_fixed[I_l]:
            pressure_force = (
                -2.0
                * wall_pressure
                * self.sph_solver._particle_volume
                * self.sph_solver.cubic_kernel_plane_integral(signed_dist)
                * normal_rigid
            )
            self._apply_hull_force(link_idx, batch_idx, pos_world, pressure_force, links_state)
            if qd.static(self._record_forces):
                self.hull_impulses[1] += self._body_force(pressure_force) * rigid_info.substep_dt[None]
            vel = vel - pressure_force * (rigid_info.substep_dt[None] / mass)

        # Finite-volume tangential no-slip traction on the SDF support layer.
        # A_i = 2*V_i*sigma(s); shear stress = rho*nu*(u_wall-u_fluid)/ell.
        # Exponential relaxation integrates the local viscous ODE without overshoot.
        # Equal and opposite impulse is applied at the same point, conserving
        # linear and angular momentum. Bulk SPH viscosity remains unchanged.
        if signed_dist < self.sph_solver._support_radius:
            nu = self._hull_nu
            ell = qd.max(signed_dist, 0.5 * self.sph_solver._particle_size)
            rate = 2.0 * nu * self.sph_solver.cubic_kernel_plane_integral(signed_dist) / ell
            alpha = 1.0 - qd.exp(-rate * rigid_info.substep_dt[None])
            wall_vel = self.rigid_solver._func_vel_at_point(
                pos_world=pos_world, link_idx=link_idx, i_b=batch_idx, links_state=links_state)
            relative = wall_vel - vel
            tangent = relative - relative.dot(normal_rigid) * normal_rigid
            delta_vel = alpha * tangent
            vel += delta_vel
            if qd.static(self._record_forces):
                self.hull_impulses[2] += self._body_force(-mass * delta_vel)
            self._apply_hull_force(
                link_idx, batch_idx, pos_world,
                -mass * delta_vel / rigid_info.substep_dt[None], links_state)

        # attraction force
        # if 0.001 < signed_dist < 0.01:
        #     vel = vel - normal_rigid * 0.1 * signed_dist

        return vel, normal_rigid

