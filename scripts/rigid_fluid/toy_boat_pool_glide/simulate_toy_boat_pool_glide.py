"""Genesis 1.4.3 toy boat gliding across a round inflatable kiddie pool.

A free rigid toy tug floats in the pool's Genesis DFSPH water and is released
with a horizontal velocity; drag, the bow wave, the wake and any bump against
the wall all come from the native two-way rigid/SPH coupler (with the
project's pressure-force patch, which is what makes floating bodies buoyant at
rest).

World coordinates are the render's: the pool stands on z = 0, centred on the
origin, with its inner floor and inner wall taken from
`prepare_assets_toy_boat_pool_glide.py`.  The water is held by the domain
floor and by a vertical cylinder at the rings' inner radius at the waterline,
imposed in the advection step; a ring of fixed boxes along it gives the boat
something to bump into.  (Clamping to the rings' undulating profile instead
pumps energy into the water at every slope and blows up within a frame.)

`settle` lets the water come to rest around the boat held fixed at its
floating pose; `run` releases the boat with its initial velocity from that
state.

PCVE edits come in through the CLI (liquid density and viscosity, boat mass
and speed, boat / water presence) and, for edits that take effect part-way,
`--timed-edits-json`: a schedule `[{"frame": n, "params": {...}}]` applied at
frame n, before that frame's state is read.  Supported keys are `boat_mass` (updates live link masses and inertia without changing pose or velocity)
and `boat_presence: [0]` (removes the boat). Unknown keys are rejected.

A timed edit continues the accepted source run instead of re-solving its prefix: `run --resume-from <source run>
--resume-frame k` copies the source's frames 1..k-1, restores its saved frame-k state (water positions and velocities,
boat pose and velocity), applies the edits scheduled for frame k at that instant and simulates frames k+1.. from there.
The saved water velocities are float16, so the restored state matches the source to that precision; the handoff errors
are written to resume_handoff.json.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'simulate')
# PCVE_UNIFIED_ENTRY_END

import argparse
import json
import math
import shutil
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
POOL_PROFILE = ROOT / "assets/sketchfab/inflatable_swimming_pool/prepared/pool_profile.json"
BOAT_COLLIDER = ROOT / "assets/sketchfab/toy_ship/prepared/boat_collider.obj"

FPS = 24
SEED = 20261023
GRAVITY = 9.81
WATER_RHO = 998.0  # baseline liquid; the boat's mass is defined in it, whatever liquid a case uses
WATER_NU = 1.004e-6
PARK_Z = 3.0  # where a removed boat waits, far above the pool and outside the SPH domain

POOL = json.loads(POOL_PROFILE.read_text())
FLOOR_Z = POOL["inner_floor_z_m"]
WALL_PROFILE = np.array(POOL["inner_wall_profile_z_r_m"], dtype=np.float64)  # (z, inner radius) rows
WALL_TOP = float(WALL_PROFILE[-1, 0])
# The simulated wall: the rings' inner radius where the authored water plane meets them.
WALL_RADIUS = float(np.interp(POOL["authored_water_z_m"], WALL_PROFILE[:, 0], WALL_PROFILE[:, 1]))
WALL_BOX_THICKNESS = 0.05
WALL_BOX_SEGMENTS = 48
# Settled depth / sampled column height; measured with the default dx (0.1641 m settles to 0.1245 m).
SETTLED_FRACTION = 0.759
# The coupler floats the hull higher than Archimedes: a mass that displaces a 20 mm draft rests at
# 14.8 mm (measured).  The boat is placed at that rest draft so it does not pop up on release.
COUPLER_REST_DRAFT_RATIO = 0.0148 / 0.020


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("settle", "run"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--water-state", type=Path)
    parser.add_argument("--frames", type=int, default=96)
    parser.add_argument("--dx", type=float, default=0.005)
    parser.add_argument("--steps-per-frame", type=int, default=16)
    parser.add_argument("--substeps", type=int, default=4)
    parser.add_argument("--fluid-drag-rate", type=float, default=0.0,
                        help="additional stationary-medium linear resistance gamma in 1/s; acceleration -gamma*v, distinct from viscosity")
    parser.add_argument("--settle-frames", type=int, default=60)
    parser.add_argument("--fluid-damping", type=float, default=0.95)
    parser.add_argument("--water-level", type=float, default=POOL["authored_water_z_m"],
                        help="settled still-water surface, world z in m (default: the asset's water plane)")
    parser.add_argument("--fill-height", type=float,
                        help="height of the sampled water column above the floor; it compacts as it settles "
                             "(default depth / SETTLED_FRACTION)")
    # Defaults are the accepted source: 1.80 m pool, ~36 mm rest draft, 0.9 m/s push, no wall contact.
    parser.add_argument("--boat-draft", type=float, default=0.052,
                        help="still-water draft that sets the boat's mass, m (ignored with --boat-mass)")
    parser.add_argument("--boat-mass", type=float)
    parser.add_argument("--boat-start", type=float, nargs=2, default=(-0.58, -0.12), metavar=("X", "Y"))
    parser.add_argument("--boat-heading-deg", type=float, default=8.0)
    parser.add_argument("--preroll-frames", type=int, default=8,
                        help="hidden frames in which the boat is pushed (horizontal velocity ramped 0 -> speed) "
                             "before it is released at frame 1; heave, pitch and roll stay free")
    parser.add_argument("--boat-speed", type=float, default=0.90, help="initial horizontal speed along the heading, m/s")
    parser.add_argument("--water-density", type=float, default=WATER_RHO, help="liquid density, kg/m^3")
    parser.add_argument("--water-viscosity", type=float, default=WATER_NU, help="liquid kinematic viscosity, m^2/s")
    parser.add_argument("--hull-viscous-shear", action="store_true", help="scene-local two-way tangential viscous hull boundary")
    parser.add_argument("--single-force-integration", action="store_true", help="integrate non-pressure acceleration once per DFSPH substep")
    parser.add_argument("--record-coupling-forces", action="store_true", help="record per-frame hull impulse components for diagnostics")
    parser.add_argument("--hull-pressure-mode", choices=("projected", "hydrostatic"), default="projected", help="pressure boundary closure; hydrostatic avoids reusing density-projection corrections as explicit wall pressure")
    parser.add_argument("--initial-draft-ratio", type=float, default=COUPLER_REST_DRAFT_RATIO, help="fraction of Archimedes draft used for the settled initial pose")
    parser.add_argument("--pool-no-slip", action="store_true", help="viscous shear against stationary pool floor and cylindrical wall")
    parser.add_argument("--quasistatic-planar-drag", action="store_true", help="reduced-order dissipative planar resistance instead of two-way horizontal SPH feedback")
    parser.add_argument("--boat-presence", type=int, choices=(0, 1), default=1)
    parser.add_argument("--water-presence", type=int, choices=(0, 1), default=1)
    parser.add_argument("--timed-edits-json", type=Path, help="schedule of part-way edits (see the module docstring)")
    parser.add_argument("--resume-from", type=Path,
                        help="run mode: finished run (particles/, simulation_report.json) whose frame --resume-frame this run continues")
    parser.add_argument("--resume-frame", type=int,
                        help="frame whose saved state starts this run; earlier frames are copied from --resume-from")
    args = parser.parse_args()
    if (args.resume_from is None) != (args.resume_frame is None):
        raise ValueError("--resume-from and --resume-frame go together")
    if args.resume_from is not None and not (args.mode == "run" and 1 < args.resume_frame <= args.frames):
        raise ValueError(f"--resume-frame applies to run mode and must be in 2..{args.frames}")
    if args.water_density <= 0 or args.water_viscosity < 0 or args.dx <= 0:
        raise ValueError("density and spacing must be positive, viscosity nonnegative")
    if not math.isfinite(args.fluid_drag_rate) or args.fluid_drag_rate < 0:
        raise ValueError("fluid drag rate must be nonnegative and finite")
    if args.fluid_drag_rate and not (args.single_force_integration and args.quasistatic_planar_drag):
        raise ValueError("additional medium resistance requires the explicitly labelled hybrid model and single-force integrator")
    # Genesis SPH uses support_radius=2*dx and an explicit viscosity stability bound.
    # Keep its substep dt below 90% of that bound; spatial resolution stays unchanged.
    args.requested_steps_per_frame = args.steps_per_frame
    if args.water_viscosity > 0:
        stable_dt = 0.01 * (2 * args.dx)**2 / args.water_viscosity
        safety = 0.45 if args.water_viscosity >= 0.005 and not args.single_force_integration else 0.90
        required = math.ceil(1.0 / (FPS * args.substeps * safety * stable_dt))
        args.steps_per_frame = max(args.steps_per_frame, 4 * math.ceil(required / 4))
    args.timed_edits = load_timed_edits(args.timed_edits_json, args.frames)
    return args


def load_timed_edits(path, frames):
    if path is None:
        return []
    schedule = json.loads(Path(path).read_text())
    for entry in schedule:
        if not 1 < int(entry["frame"]) <= frames:
            raise ValueError(f"timed edit frame {entry['frame']} outside 2..{frames}")
        unknown = set(entry["params"]) - {"boat_presence", "boat_mass"}
        if unknown:
            raise ValueError(f"timed edit keys this simulation cannot apply: {sorted(unknown)}")
        if "boat_presence" in entry["params"] and entry["params"]["boat_presence"] != [0]:
            raise ValueError("timed boat_presence must remove the boat: [0]")
        if "boat_mass" in entry["params"] and (not math.isfinite(float(entry["params"]["boat_mass"])) or float(entry["params"]["boat_mass"]) <= 0):
            raise ValueError("timed boat_mass must be positive and finite")
    return schedule


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def load_hull():
    import trimesh

    return trimesh.load(BOAT_COLLIDER, force="mesh").convex_hull


def volume_below(hull, z):
    """Volume of a convex hull below the plane at height z: the hull of its vertices below the plane
    plus the points where its edges cross it."""
    from scipy.spatial import ConvexHull

    v = hull.vertices
    points = [v[v[:, 2] <= z]]
    a, b = v[hull.edges_unique[:, 0]], v[hull.edges_unique[:, 1]]
    crossing = (a[:, 2] - z) * (b[:, 2] - z) < 0
    t = (z - a[crossing, 2]) / (b[crossing, 2] - a[crossing, 2])
    points.append(a[crossing] + t[:, None] * (b[crossing] - a[crossing]))
    points = np.concatenate(points)
    return ConvexHull(points).volume if len(points) >= 4 and np.ptp(points[:, 2]) > 1e-9 else 0.0


def boat_mass_and_draft(hull, args, tolerance=1e-5):
    """The boat's mass (--boat-mass, or the mass that floats at --boat-draft in the baseline water) and the
    Archimedes draft (bisection on the hull) at which that mass floats in this case's liquid."""
    keel = float(hull.bounds[0, 2])
    mass = args.boat_mass if args.boat_mass is not None else WATER_RHO * volume_below(hull, keel + args.boat_draft)
    target = mass / args.water_density
    if hull.volume < target:
        # A negatively buoyant case has no equilibrium draft. Start it at the source held pose;
        # a real support is removed at release and the free rigid/SPH body is allowed to sink.
        return mass, args.boat_draft
    a, b = keel, float(hull.bounds[1, 2])
    while b - a > tolerance:
        mid = 0.5 * (a + b)
        a, b = (mid, b) if volume_below(hull, mid) < target else (a, mid)
    return mass, 0.5 * (a + b) - keel


def create_solver(SPHSolver, gs, qd, single_force_integration=False, pool_no_slip=False, fluid_drag_rate=0.0):
    """DFSPH with the pool's round wall imposed in the advection step.

    Coupled wall boxes alone leak (particles tunnel through while the column
    compacts).  Clamping each particle inside the cylinder (as
    bowling_ball_pool_drop does with its planes) holds the water exactly.
    """

    @qd.data_oriented
    class RoundPoolSPH(SPHSolver):

        def build(self):
            super().build()
            self._wall_nu = float(self.entities[0].material.mu) if self.is_active else 0.0
            self._medium_decay = math.exp(-fluid_drag_rate*self._substep_dt)

        def substep_pre_coupling(self, f):
            if not single_force_integration or self._pressure_solver != "DFSPH":
                return super().substep_pre_coupling(f)
            if self.is_active:
                self._kernel_reorder_particles(f)
                self._kernel_compute_rho(f)
                self._kernel_compute_DFSPH_factor(f)
                self._divergence_solve(f)
                if fluid_drag_rate > 0:
                    self._kernel_medium_resistance()
                # DFSPH divergence iterations already update velocity. Applying
                # _kernel_advect_velocity here would add the previous substep's
                # gravity/viscosity again before the fresh non-pressure kick.
                self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
                self._kernel_predict_velocity(f)
                if pool_no_slip:
                    self._kernel_pool_viscous_shear()
                self._density_solve(f)

        @qd.kernel
        def _kernel_medium_resistance(self):
            # Exact integration of dv/dt=-gamma*v as an operator-split step.
            # No coordinates or surface geometry are changed. This transfers
            # momentum/energy to an unresolved stationary medium, not to water.
            # 0 < decay <= 1 guarantees that this step cannot add kinetic energy.
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p,i_b].active:
                    self.particles_reordered[i_p,i_b].vel *= self._medium_decay

        @qd.kernel
        def _kernel_pool_viscous_shear(self):
            # Same finite-volume Newtonian wall traction as the hull boundary,
            # applied to the stationary domain. Only tangential motion is damped.
            # The fixed pool receives the opposite momentum; the normal boundary
            # is still enforced by the existing floor and cylindrical wall.
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    p = self.particles_reordered[i_p, i_b].pos
                    v = self.particles_reordered[i_p, i_b].vel
                    floor_dist = qd.max(p[2] - FLOOR_Z, 0.0)
                    if floor_dist < self._support_radius:
                        rate = 2.0*self._wall_nu*self.cubic_kernel_plane_integral(floor_dist)/qd.max(floor_dist, .5*self._particle_size)
                        decay = qd.exp(-rate*self._substep_dt)
                        v[0] *= decay
                        v[1] *= decay
                    r = qd.sqrt(p[0]*p[0] + p[1]*p[1])
                    wall_dist = qd.max(WALL_RADIUS-r, 0.0)
                    if wall_dist < self._support_radius and r > 0:
                        n = qd.Vector([p[0]/r,p[1]/r,0.0])
                        rate = 2.0*self._wall_nu*self.cubic_kernel_plane_integral(wall_dist)/qd.max(wall_dist, .5*self._particle_size)
                        v -= (1.0-qd.exp(-rate*self._substep_dt))*(v-v.dot(n)*n)
                    self.particles_reordered[i_p,i_b].vel = v

        @qd.kernel
        def _kernel_advect_position(self, f: qd.i32):
            for i_p, i_b in qd.ndrange(self._n_particles, self._B):
                if self.particles_ng_reordered[i_p, i_b].active:
                    vel = self.particles_reordered[i_p, i_b].vel
                    pos = self.particles_reordered[i_p, i_b].pos + self._substep_dt * vel
                    pos, vel = self.boundary.impose_pos_vel(pos, vel)
                    limit = WALL_RADIUS - 0.5 * self._particle_size
                    r = qd.sqrt(pos[0] * pos[0] + pos[1] * pos[1])
                    if r > limit:
                        nx = pos[0] / r
                        ny = pos[1] / r
                        pos[0] = nx * limit
                        pos[1] = ny * limit
                        outward = vel[0] * nx + vel[1] * ny
                        if outward > 0:
                            vel[0] -= outward * nx
                            vel[1] -= outward * ny
                    self.particles_reordered[i_p, i_b].vel = vel
                    self.particles_reordered[i_p, i_b].pos = pos

    return RoundPoolSPH


def add_fixed_box(scene, gs, center, size, euler=(0.0, 0.0, 0.0)):
    return scene.add_entity(
        morph=gs.morphs.Box(pos=center, size=size, euler=euler, fixed=True, visualization=False),
        material=gs.materials.Rigid(
            rho=900.0,
            friction=0.45,
            needs_coup=False,  # the water is held by the solver's wall clamp
            sdf_cell_size=0.004,
            sdf_min_res=24,
            sdf_max_res=96,
        ),
    )


def add_pool(scene, gs):
    """Floor slab and a ring of boxes along the inner wall, for the boat's rigid contacts only."""
    outer = WALL_RADIUS + WALL_BOX_THICKNESS
    add_fixed_box(scene, gs, (0.0, 0.0, FLOOR_Z - 0.015), (2 * outer, 2 * outer, 0.03))
    chord = 2.0 * outer * math.tan(math.pi / WALL_BOX_SEGMENTS) * 1.15
    height = WALL_TOP - FLOOR_Z
    for i in range(WALL_BOX_SEGMENTS):
        a = 2.0 * math.pi * i / WALL_BOX_SEGMENTS
        c = WALL_RADIUS + 0.5 * WALL_BOX_THICKNESS
        add_fixed_box(scene, gs, (c * math.cos(a), c * math.sin(a), FLOOR_Z + 0.5 * height),
                      (WALL_BOX_THICKNESS, chord, height), euler=(0.0, 0.0, math.degrees(a)))


def build_scene(args, boat_fixed):
    import genesis as gs

    hull = load_hull()
    mass, draft = boat_mass_and_draft(hull, args)
    depth = args.water_level - FLOOR_Z
    fill = args.fill_height or depth / SETTLED_FRACTION

    gs.init(backend=gs.cuda, precision="32", seed=SEED, logging_level="warning")
    import quadrants as qd
    import genesis.engine.simulator as simulator
    from genesis.engine.solvers.sph_solver import SPHSolver

    if args.hull_viscous_shear:
        from viscous_hull_toy_boat import HullViscousCoupler
        HullViscousCoupler.record_forces = args.record_coupling_forces
        HullViscousCoupler.pressure_mode = args.hull_pressure_mode
        HullViscousCoupler.water_level = args.water_level
        HullViscousCoupler.quasistatic_planar_drag = args.quasistatic_planar_drag
        HullViscousCoupler.drag_radius = (3.0*mass/(4.0*math.pi*args.water_density))**(1.0/3.0)
        simulator.LegacyCoupler = HullViscousCoupler
    elif args.record_coupling_forces:
        raise ValueError("--record-coupling-forces requires --hull-viscous-shear")
    if args.pool_no_slip and not args.single_force_integration:
        raise ValueError("--pool-no-slip requires --single-force-integration")
    simulator.SPHSolver = create_solver(SPHSolver, gs, qd, args.single_force_integration, args.pool_no_slip, args.fluid_drag_rate)
    step_dt = 1.0 / (FPS * args.steps_per_frame)
    reach = WALL_RADIUS + 0.02
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(
            dt=step_dt,
            substeps=args.substeps,
            gravity=(0.0, 0.0, -GRAVITY),
            floor_height=FLOOR_Z - 0.10,
            requires_grad=False,
        ),
        rigid_options=gs.options.RigidOptions(
            dt=step_dt / args.substeps,
            enable_collision=True,
            enable_joint_limit=True,
        ),
        sph_options=gs.options.SPHOptions(
            particle_size=args.dx,
            pressure_solver="DFSPH",
            # The domain floor is the pool floor (particles tunnel through a thin floor box).
            lower_bound=(-reach, -reach, FLOOR_Z),
            upper_bound=(reach, reach, WALL_TOP + 0.10),
            max_divergence_error=0.1,
            max_density_error_percent=0.05,
        ),
        coupler_options=gs.options.LegacyCouplerOptions(
            rigid_mpm=False, rigid_sph=True, rigid_pbd=False, rigid_fem=False,
            mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False,
        ),
        show_viewer=False,
    )
    add_pool(scene, gs)

    keel = float(hull.bounds[0, 2])
    rest_draft = draft * args.initial_draft_ratio
    if args.water_presence:
        pos = (args.boat_start[0], args.boat_start[1], args.water_level - rest_draft - keel)
    else:  # an empty pool: the boat sits on the floor
        rest_draft = 0.0
        pos = (args.boat_start[0], args.boat_start[1], FLOOR_Z + 0.001 - keel)
    euler = (0.0, 0.0, args.boat_heading_deg)
    boat = None if not args.boat_presence else scene.add_entity(
        morph=gs.morphs.Mesh(file=str(BOAT_COLLIDER), pos=pos, euler=euler, fixed=boat_fixed,
                             convexify=True, visualization=False),
        material=gs.materials.Rigid(
            rho=mass / hull.volume,
            friction=0.30,
            needs_coup=True,  # also while held fixed in settle, so the water settles around the hull
            coup_friction=0.05,
            coup_softness=0.002,
            coup_restitution=0.0,
            sdf_cell_size=0.002,
            sdf_min_res=32,
            sdf_max_res=128,
        ),
    )

    water = None if not args.water_presence else scene.add_entity(
        morph=gs.morphs.Cylinder(pos=(0.0, 0.0, FLOOR_Z + 0.5 * fill),
                                 radius=WALL_RADIUS - 0.5 * args.dx, height=fill),
        material=gs.materials.SPH.Liquid(rho=args.water_density, mu=args.water_viscosity, gamma=0.0,
                                         sampler="regular"),
        surface=gs.surfaces.Default(color=(0.2, 0.6, 1.0, 1.0), vis_mode="particle"),
    )
    tick = time.monotonic()
    scene.build(n_envs=0)
    if boat is not None and not boat_fixed:
        boat.set_mass(mass)
    info = {"boat_mass_kg": mass, "draft_m": draft if mass <= args.water_density*hull.volume else None, "placed_rest_draft_m": rest_draft, "hull_volume_m3": float(hull.volume), "boat_start_m": list(pos),
            "boat_euler_deg": list(euler), "water_level_m": args.water_level, "floor_z_m": FLOOR_Z,
            "fill_height_m": fill, "build_seconds": time.monotonic() - tick, "hull": hull,
            "boat_presence": [args.boat_presence], "water_presence": [args.water_presence],
            "water_density_kg_m3": args.water_density, "water_kinematic_viscosity_m2_s": args.water_viscosity,
            "hull_viscous_shear": bool(args.hull_viscous_shear),
            "negative_buoyancy": bool(mass > args.water_density * hull.volume),
            "max_archimedes_buoyancy_kg": float(args.water_density * hull.volume),
            "equilibrium_draft_exists": bool(mass <= args.water_density * hull.volume),
            "preroll_vertical_support": bool(mass > args.water_density * hull.volume or
                                             (args.water_viscosity >= 0.005 and not args.single_force_integration))}
    return gs, scene, boat, water, info


def public(info):
    return {k: v for k, v in info.items() if k != "hull"}


def surface_level(positions, dx, exclude_center=None, exclude_radius=0.0):
    """Median top of the water columns on a dx grid (away from the wall and the hull), plus half a particle."""
    keep = np.hypot(positions[:, 0], positions[:, 1]) < WALL_RADIUS - 3 * dx
    if exclude_center is not None:
        keep &= np.hypot(positions[:, 0] - exclude_center[0], positions[:, 1] - exclude_center[1]) > exclude_radius
    p = positions[keep]
    cell = np.floor(p[:, :2] / dx).astype(np.int64)
    key = cell[:, 0] * 100000 + cell[:, 1]
    order = np.argsort(key, kind="stable")
    key, z = key[order], p[order, 2]
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    return float(np.median(np.maximum.reduceat(z, starts)) + 0.5 * dx)


def clear_hull_column(pos, hull, boat_pos, heading_deg, top, dx):
    """Move the particles sampled inside the hull's footprint above its keel (inside it or on its deck)
    to a lattice over the rim zone of the column, clear of the hull, from where they fall in during settle."""
    from scipy.spatial import Delaunay

    c, s = math.cos(math.radians(heading_deg)), math.sin(math.radians(heading_deg))
    rel = pos[:, :2] - np.asarray(boat_pos[:2])
    local = np.stack((c * rel[:, 0] + s * rel[:, 1], -s * rel[:, 0] + c * rel[:, 1]), axis=1)
    footprint = Delaunay(hull.vertices[:, :2])
    hit = (footprint.find_simplex(local) >= 0) & (pos[:, 2] > boat_pos[2] + hull.bounds[0, 2] - dx)
    count = int(hit.sum())
    targets = []
    layer = 0
    while len(targets) < count:
        z = top + dx * (layer + 1)
        for r in np.arange(WALL_RADIUS - 1.0 * dx, WALL_RADIUS - 0.10, -dx):
            n = int(2 * math.pi * r / dx)
            a = np.arange(n) * 2 * math.pi / n + 0.5 * layer
            ring = np.stack((r * np.cos(a), r * np.sin(a), np.full(n, z)), axis=1)
            clear = np.hypot(ring[:, 0] - boat_pos[0], ring[:, 1] - boat_pos[1]) > 0.5 * hull.extents[0] + 0.06
            targets.extend(ring[clear])
        layer += 1
    pos = pos.copy()
    pos[hit] = np.asarray(targets[:count], dtype=np.float32)
    return pos, count


def particle_state(entity):
    if entity is None:  # no water in this case
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32)
    pos = entity.get_particles_pos().cpu().numpy().reshape(-1, 3).astype(np.float32)
    vel = entity.get_particles_vel().cpu().numpy().reshape(-1, 3).astype(np.float32)
    return pos, vel


def rigid_state(boat):
    if boat is None:
        return np.zeros(3), np.array((1.0, 0.0, 0.0, 0.0)), np.zeros(3), np.zeros(3)
    pos = boat.get_pos().cpu().numpy().reshape(-1, 3)[0].astype(np.float64)
    quat = boat.get_quat().cpu().numpy().reshape(-1, 4)[0].astype(np.float64)
    vel = boat.get_vel().cpu().numpy().reshape(-1, 3)[0].astype(np.float64)
    ang = boat.get_ang().cpu().numpy().reshape(-1, 3)[0].astype(np.float64)
    return pos, quat, vel, ang


def outside_wall(pos):
    return int((np.hypot(pos[:, 0], pos[:, 1]) > WALL_RADIUS + 0.005).sum())


def settle(args):
    args.out.mkdir(parents=True, exist_ok=False)
    gs, scene, boat, water, info = build_scene(args, boat_fixed=True)
    pos, _ = particle_state(water)
    if args.water_state is not None:
        with np.load(args.water_state) as state:
            if not math.isclose(float(state["dx"]), args.dx):
                raise ValueError("water state particle spacing mismatch")
            pos = state["water_pos"].astype(np.float32)
        water.set_particles_pos(pos)
        water.set_particles_vel(np.zeros_like(pos))
    moved = 0
    if water is not None and boat is not None:
        pos, moved = clear_hull_column(pos, info["hull"], info["boat_start_m"], args.boat_heading_deg,
                                       FLOOR_Z + info["fill_height_m"], args.dx)
        water.set_particles_pos(pos)
    print("SETTLE moved", moved, "particles out of the hull column", flush=True)
    samples = []
    for frame in range(1, (args.settle_frames if water is not None else 0) + 1):
        for _ in range(args.steps_per_frame):
            scene.step()
        pos, vel = particle_state(water)
        if not (np.isfinite(pos).all() and np.isfinite(vel).all()):
            raise RuntimeError(f"non-finite water state in settle frame {frame}")
        vel *= args.fluid_damping
        water.set_particles_vel(vel)
        speed = np.linalg.norm(vel, axis=1)
        if frame == 1 or frame % 6 == 0 or frame == args.settle_frames:
            row = {"frame": frame, "max_speed": float(speed.max()), "p99_speed": float(np.percentile(speed, 99)),
                   "z_max": float(pos[:, 2].max()),
                   "surface_level": surface_level(pos, args.dx, info["boat_start_m"], 0.15),
                   "outside_wall": outside_wall(pos)}
            samples.append(row)
            print("SETTLE", json.dumps(row), flush=True)
    pos, vel = particle_state(water)
    np.savez_compressed(args.out / "water_state.npz", water_pos=pos, water_vel=np.zeros_like(vel), dx=args.dx,
                        water_level=args.water_level, boat_start=np.array(info["boat_start_m"]))
    save_json(args.out / "settle_report.json", {
        "solver": "Genesis 1.4.3 native rigid + DFSPH", "mode": "settle", **public(info),
        "moved_out_of_hull_column": moved, "water_particles": len(pos), "samples": samples,
        "initial_water_state": str(args.water_state) if args.water_state is not None else None,
        "single_force_integration": args.single_force_integration,
        "hull_pressure_mode": args.hull_pressure_mode,
        "initial_draft_ratio": args.initial_draft_ratio,
    })


def same_value(a, b, atol=0.0):
    if isinstance(a, (str, bool)) or isinstance(b, (str, bool)) or a is None or b is None:
        return a == b
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return a.shape == b.shape and np.allclose(a, b, rtol=1e-9, atol=atol)


# The held start pose comes from a draft bisection with a 1e-5 m tolerance; the branch restores the saved pose anyway.
RESUME_TOLERANCE = {"boat_start_m": 1e-5}


def resume_state(args, scene, boat, water, info):
    """Restore the saved frame-k state of the run this one continues (see the module docstring).

    Water positions are float32 in the cache and come back bit for bit; water velocities are float16 there, so the
    restored velocities are the saved float16 values. Native DFSPH also carries each particle's last non-pressure
    acceleration into the next substep, which set_particles_* clears: it is recomputed from the restored state with the
    solver's own kernels. Not restored: the rigid coupling wrench accumulated in the last substep (consumed by the next
    rigid substep) and the constraint solver's warm start; their effect is what a control continuation measures.
    """
    source = args.resume_from.resolve()
    report = json.loads((source / "simulation_report.json").read_text())
    numerics, physics = report["numerics"], report["physics"]
    expected = {
        "dx_m": (numerics["dx_m"], args.dx),
        "steps_per_frame": (numerics["steps_per_frame"], args.steps_per_frame),
        "substeps": (numerics["substeps_per_step"], args.substeps),
        "fps": (numerics["fps"], FPS),
        "preroll_frames": (physics["preroll_push_frames"], args.preroll_frames),
        "water_density_kg_m3": (physics["water_density_kg_m3"], args.water_density),
        "water_kinematic_viscosity_m2_s": (physics["water_kinematic_viscosity_m2_s"], args.water_viscosity),
        "additional_medium_drag_rate_s_inv": (physics.get("additional_medium_drag_rate_s_inv", 0.0), args.fluid_drag_rate),
        "boat_presence": (physics.get("boat_presence", [1]), [args.boat_presence]),
        "water_presence": (physics.get("water_presence", [1]), [args.water_presence]),
        "boat_mass_kg": (report["boat_mass_kg"], info["boat_mass_kg"]),
        "boat_start_m": (report["boat_start_m"], info["boat_start_m"]),
        "water_level_m": (report["water_level_m"], args.water_level),
        "hull_viscous_shear": (report.get("hull_viscous_shear", False), bool(args.hull_viscous_shear)),
        "single_force_integration": (numerics.get("single_force_integration", False), bool(args.single_force_integration)),
        "hull_pressure_mode": (numerics.get("hull_pressure_mode", "projected"), args.hull_pressure_mode),
        "pool_no_slip": (numerics.get("pool_no_slip", False), bool(args.pool_no_slip)),
        "quasistatic_planar_drag": (numerics.get("quasistatic_planar_drag", False), bool(args.quasistatic_planar_drag)),
    }
    differ = {k: v for k, v in expected.items() if not same_value(*v, atol=RESUME_TOLERANCE.get(k, 0.0))}
    if differ:
        raise ValueError(f"the resumed run has other physics or numerics: {differ}")
    k = args.resume_frame
    if any(int(e["frame"]) <= k for e in physics.get("timed_edits", [])):
        raise ValueError("the resumed run was already edited before the branch frame")
    state_file = source / "particles" / f"frame_{k:04d}.npz"
    with np.load(state_file) as state:
        saved = {name: state[name] for name in state.files}
    if boat is not None and not bool(saved.get("boat_active", True)):
        raise ValueError("cannot continue a run whose boat was removed")
    # The solver clock of frame k: the hidden push, then k-1 frames.
    pushes = args.preroll_frames * args.steps_per_frame if boat is not None else 0
    scene.sim._cur_substep_global = (pushes + (k - 1) * args.steps_per_frame) * args.substeps
    handoff = {"resumed_run": str(source), "state_file": str(state_file), "frame": k, "time_s": (k - 1) / FPS,
               "solver_substep_counter": int(scene.sim._cur_substep_global)}
    if water is not None:
        pos = saved["water_pos"].astype(np.float32)
        vel = saved["water_vel"].astype(np.float32)
        if len(pos) != water.n_particles:
            raise ValueError(f"saved water has {len(pos)} particles, the scene {water.n_particles}")
        water.set_particles_pos(pos)
        water.set_particles_vel(vel)  # also clears the particle acceleration
        sph = scene.sim.sph_solver
        if not args.single_force_integration:
            f = scene.sim.cur_substep_local
            sph._kernel_reorder_particles(f)
            sph._kernel_compute_rho(f)
            sph._kernel_compute_non_pressure_forces(f, scene.sim.cur_t)
            sph._kernel_copy_from_reordered(f)
        back_pos, back_vel = particle_state(water)
        acc = sph.particles.acc.to_numpy().reshape(-1, 3)
        handoff.update(
            water_particles=int(len(pos)),
            water_position_max_abs_error_m=float(np.abs(back_pos - pos).max()),
            water_velocity_max_abs_error_vs_saved_m_s=float(np.abs(back_vel - vel).max()),
            # float16 rounding: half an ulp, 2^-11 relative for normal values and 2^-25 absolute below 2^-14
            water_velocity_float16_rounding_bound_m_s=float(np.maximum(np.abs(vel) * 2.0**-11, 2.0**-25).max()),
            water_speed_max_m_s=float(np.linalg.norm(vel, axis=1).max()),
            restored_particle_acceleration_mean_m_s2=acc.mean(0).tolist())
    if boat is not None:
        boat.set_pos(saved["boat_pos"])
        boat.set_quat(saved["boat_quat_wxyz"])
        # get_vel/get_ang report the authored origin's world velocity; solve for the dof velocity that gives both.
        target = np.r_[saved["boat_vel"], saved["boat_ang"]].astype(np.float64)
        jacobian = np.zeros((6, 6))
        for i in range(6):
            unit = np.zeros(6)
            unit[i] = 1.0
            boat.set_dofs_velocity(unit)
            _, _, lin, ang = rigid_state(boat)
            jacobian[:, i] = np.r_[lin, ang]
        boat.set_dofs_velocity(np.linalg.solve(jacobian, target))
        bpos, bquat, bvel, bang = rigid_state(boat)
        handoff.update(
            boat_position_max_abs_error_m=float(np.abs(bpos - saved["boat_pos"]).max()),
            boat_quaternion_max_abs_error=float(np.abs(bquat - saved["boat_quat_wxyz"]).max()),
            boat_velocity_max_abs_error_m_s=float(np.abs(bvel - saved["boat_vel"]).max()),
            boat_angular_velocity_max_abs_error_rad_s=float(np.abs(bang - saved["boat_ang"]).max()))
    handoff["not_restored"] = ["rigid coupling wrench accumulated in the last substep of the saved frame (consumed by the next rigid substep)",
                               "rigid constraint solver warm start"]
    limits = {"water_position_max_abs_error_m": 1e-8, "water_velocity_max_abs_error_vs_saved_m_s": 1e-8,
              "boat_position_max_abs_error_m": 1e-6, "boat_quaternion_max_abs_error": 1e-6,
              "boat_velocity_max_abs_error_m_s": 1e-5, "boat_angular_velocity_max_abs_error_rad_s": 1e-5}
    over = {key: handoff[key] for key, limit in limits.items() if key in handoff and not handoff[key] < limit}
    if over:
        raise RuntimeError(f"handoff state differs from the saved frame: {over}")
    print("RESUMED", json.dumps(handoff), flush=True)
    return report, handoff


def run(args):
    if args.water_state is None and args.resume_from is None:
        raise ValueError("--water-state is required for run mode")
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "particles").mkdir()
    gs, scene, boat, water, info = build_scene(args, boat_fixed=False)
    heading = math.radians(args.boat_heading_deg)
    v0 = (args.boat_speed * math.cos(heading), args.boat_speed * math.sin(heading), 0.0)
    if args.resume_from is not None:
        source_report, handoff = resume_state(args, scene, boat, water, info)
        released = np.asarray(source_report["physics"]["released_at_m"])
        released_v = np.asarray(source_report["physics"]["released_velocity_m_s"])
        first = args.resume_frame
    else:
        source_report, handoff, first = None, None, 1
        released, released_v = release(args, scene, boat, water, info, heading, v0)
    print("RELEASED at", np.round(released, 4).tolist(), "v", np.round(released_v, 3).tolist(), flush=True)
    edits_at = {int(e["frame"]): e["params"] for e in args.timed_edits}
    removal = {f for f, params in edits_at.items() if params.get("boat_presence") == [0]}
    mass_changes = []
    visual_size = json.loads((ROOT / "assets/sketchfab/toy_ship/prepared/boat_frame.json").read_text())["size_m"]
    visual_corners = np.array([(x,y,z) for x in (-visual_size[0]/2,visual_size[0]/2)
                               for y in (-visual_size[1]/2,visual_size[1]/2) for z in (0,visual_size[2])])
    boat_active = boat is not None
    removed_at = None

    def park(boat):
        boat.set_pos(np.array((0.0, 0.0, PARK_Z)))
        boat.set_dofs_velocity(np.zeros(6))

    rows = []
    if args.resume_from is not None:
        # Frames before the branch are the resumed run's own files and measurements.
        for frame in range(1, first):
            src = args.resume_from.resolve() / "particles" / f"frame_{frame:04d}.npz"
            shutil.copy2(src, args.out / "particles" / src.name)
            row = dict(source_report["frames"][frame - 1])
            assert row["frame"] == frame
            row.setdefault("boat_active", True)
            row.setdefault("boat_mass_kg", info["boat_mass_kg"])
            row["copied_from_resumed_run"] = str(src)
            rows.append(row)
        save_json(args.out / "resume_handoff.json", handoff)
    writer = None
    started = time.monotonic()
    for frame in range(first, args.frames + 1):
        tick = time.monotonic()
        if args.record_coupling_forces:
            scene.sim._coupler.hull_impulses.fill(0)
            scene.sim._coupler.drag_work.fill(0)
        params = edits_at.get(frame, {})
        if "boat_mass" in params and boat_active:
            before_pos, before_quat, before_vel, _ = rigid_state(boat)
            old_mass = float(boat.get_mass().cpu().numpy().reshape(-1)[0])
            boat.set_mass(float(params["boat_mass"]))
            actual_mass = float(boat.get_mass().cpu().numpy().reshape(-1)[0])
            after_pos, after_quat, after_vel, _ = rigid_state(boat)
            assert math.isclose(actual_mass,float(params["boat_mass"]),rel_tol=1e-5)
            # set_mass recomputes the link state; on a restored state that can move the float32 readings by an ulp
            jump = {"position_m": float(np.abs(after_pos-before_pos).max()), "quaternion": float(np.abs(after_quat-before_quat).max()),
                    "velocity_m_s": float(np.abs(after_vel-before_vel).max())}
            assert jump["position_m"] < 1e-6 and jump["quaternion"] < 1e-6 and jump["velocity_m_s"] < 1e-5, jump
            change={"frame":frame,"from_kg":old_mass,"to_kg":actual_mass,"pose_and_velocity_preserved":True,"max_abs_jump":jump}
            mass_changes.append(change)
            print("MASS_EDIT",json.dumps(change),flush=True)
        if frame > first:
            for _ in range(args.steps_per_frame):
                if boat is not None and not boat_active:
                    park(boat)
                scene.step()
        if frame in removal and boat_active:
            park(boat)
            boat_active, removed_at = False, frame
        pos, vel = particle_state(water)
        bpos, quat, bvel, bang = rigid_state(boat)
        if writer is not None:
            writer.join()
        writer = threading.Thread(
            target=np.savez_compressed,
            args=(args.out / "particles" / f"frame_{frame:04d}.npz",),
            kwargs={"water_pos": pos, "water_vel": vel.astype(np.float16), "boat_pos": bpos,
                    "boat_quat_wxyz": quat, "boat_vel": bvel, "boat_ang": bang, "boat_active": boat_active},
        )
        writer.start()
        speed = np.linalg.norm(vel, axis=1)
        w,x,y,z = quat
        rotation=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                           [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                           [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
        visual_world=visual_corners @ rotation.T + bpos
        row = {"frame": frame, "time_s": (frame - 1) / FPS, "boat_pos": bpos.tolist(),
               "boat_quat_wxyz": quat.tolist(), "boat_vel": bvel.tolist(), "boat_ang": bang.tolist(),
               "boat_active": boat_active,
               "boat_mass_kg": float(boat.get_mass().cpu().numpy().reshape(-1)[0]) if boat is not None else None,
               "boat_visual_top_z_m": float(visual_world[:,2].max()) if boat_active else None,
               "boat_visual_bottom_z_m": float(visual_world[:,2].min()) if boat_active else None,
               "fully_submerged": bool(visual_world[:,2].max() < args.water_level-0.003) if boat_active else False,
               "water_z_max": float(pos[:, 2].max()) if len(pos) else None,
               "water_speed_max": float(speed.max()) if len(pos) else None,
               "water_speed_p99": float(np.percentile(speed, 99)) if len(pos) else None,
               "compute_seconds": time.monotonic() - tick}
        if args.record_coupling_forces:
            impulses = scene.sim._coupler.hull_impulses.to_numpy()
            row["coupling_impulses_Ns"] = dict(zip(("collision", "pressure", "viscous_shear", "quasistatic_drag"), impulses.tolist()))
            row["quasistatic_drag_work_J"] = float(scene.sim._coupler.drag_work[None])
        rows.append(row)
        if frame == first or frame % 4 == 0:
            save_json(args.out / "progress.json", {"frames_completed":frame,"frames_target":args.frames,"latest":row,
                "first_frame":rows[0],"mass_changes":mass_changes,"elapsed_seconds":time.monotonic()-started})
            print("FRAME", frame, "boat", np.round(bpos, 4).tolist(), "v", np.round(bvel, 3).tolist(),
                  "quat", np.round(quat, 3).tolist(), "water zmax", row["water_z_max"], flush=True)
        if not np.isfinite(pos).all() or not np.isfinite(bpos).all():
            raise RuntimeError("non-finite Genesis state")
    if writer is not None:
        writer.join()
    save_json(args.out / "simulation_report.json", {
        "status": "complete",
        "solver": ("Genesis 1.4.3 hybrid: dynamic rigid body with quasi-static planar drag, vertical SPH coupling, and body-driven fluid" if args.quasistatic_planar_drag else "Genesis 1.4.3 native rigid body + DFSPH liquid with two-way rigid_sph coupling"),
        "physics": {"boat_collider": str(BOAT_COLLIDER.relative_to(ROOT)), "boat_initial_velocity_m_s": list(v0),
                    "additional_medium_drag_rate_s_inv": args.fluid_drag_rate,
                    "water_density_kg_m3": args.water_density, "water_kinematic_viscosity_m2_s": args.water_viscosity,
                    "boat_presence": [args.boat_presence], "water_presence": [args.water_presence],
                    "timed_edits": args.timed_edits, "boat_removed_at_frame": removed_at, "mass_changes":mass_changes,
                    "gravity_m_s2": GRAVITY, "pool_profile": str(POOL_PROFILE.relative_to(ROOT)),
                    "preroll_push_frames": args.preroll_frames, "released_at_m": np.asarray(released).tolist(),
                    "released_velocity_m_s": np.asarray(released_v).tolist()},
        "numerics": {"fps": FPS, "frames": args.frames, "dx_m": args.dx, "steps_per_frame": args.steps_per_frame,
                     "medium_drag_integration": "exact exponential velocity decay before non-pressure forces; first-order operator splitting" if args.fluid_drag_rate else None,
                     "medium_drag_substep_velocity_factor": math.exp(-args.fluid_drag_rate/(FPS*args.steps_per_frame*args.substeps)),
                     "single_force_integration": args.single_force_integration,
                     "record_coupling_forces": args.record_coupling_forces,
                     "hull_pressure_mode": args.hull_pressure_mode,
                     "pool_no_slip": args.pool_no_slip,
                     "quasistatic_planar_drag": args.quasistatic_planar_drag,
                     "drag_equivalent_sphere_radius_m": (3.0*info["boat_mass_kg"]/(4.0*math.pi*args.water_density))**(1.0/3.0) if args.quasistatic_planar_drag else None,
                     "substeps_per_step": args.substeps, "requested_steps_per_frame":args.requested_steps_per_frame,
                     "viscosity_stability_dt_s":(0.01*(2*args.dx)**2/args.water_viscosity if args.water_viscosity else None)},
        **public(info),
        "resumed_from": handoff, "first_simulated_frame": first,
        "simulation_seconds": time.monotonic() - started,
        "water_particles": int(len(pos)),
        "frames": rows,
    })
    print("GENESIS_DONE", json.dumps({"frames": args.frames, "seconds": time.monotonic() - started}), flush=True)


def release(args, scene, boat, water, info, heading, v0):
    """Load the settled water and push the boat up to speed; returns the release pose and velocity."""
    with np.load(args.water_state) as state:
        if not math.isclose(float(state["dx"]), args.dx):
            raise ValueError("water state particle spacing mismatch")
        if not math.isclose(float(state["water_level"]), args.water_level):
            raise ValueError("water state level mismatch")
        if not np.allclose(state["boat_start"], info["boat_start_m"]):
            raise ValueError("water state was settled around a different boat pose")
        if (len(state["water_pos"]) > 0) != (water is not None):
            raise ValueError("water state and --water-presence disagree")
        if water is not None:
            water.set_particles_pos(state["water_pos"])
            water.set_particles_vel(state["water_vel"])
    # A hand pushes the boat up to speed and lets go: released at full speed in still water, the hull
    # slams the water and throws a 14 cm sheet.  The push prescribes only the horizontal velocity (it is
    # the same whatever the boat's mass), so the bow wave and wake are already formed at frame 1.
    pushes = args.preroll_frames * args.steps_per_frame if boat is not None else 0
    for k in range(pushes):
        t = (k + 1) / pushes
        ramp = t * t * (3 - 2 * t)
        if info["preroll_vertical_support"]:
            # A hand holds the loaded boat at the same source waterline during the hidden push.
            current, _, _, _ = rigid_state(boat)
            current[2] = info["boat_start_m"][2]
            boat.set_pos(current)
            boat.set_quat(np.array((math.cos(heading/2), 0, 0, math.sin(heading/2))))
            boat.set_dofs_velocity(np.array((v0[0]*ramp, v0[1]*ramp, 0, 0, 0, 0)))
        else:
            boat.set_dofs_velocity(np.array((v0[0] * ramp, v0[1] * ramp)), dofs_idx_local=[0, 1])
        scene.step()
    if pushes == 0 and boat is not None:
        boat.set_dofs_velocity(np.array((*v0, 0.0, 0.0, 0.0)))
    released, _, released_v, _ = rigid_state(boat)
    return released, released_v


def main():
    args = parse_args()
    if args.mode == "settle":
        settle(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
