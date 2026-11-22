"""Genesis DFSPH tea pour: fixed-mass particles emitted only at the spout.

No cup-height, desired cup amount, fill mesh, or post-step position projection.
The active-particle convergence normalization and single force integration
follow PCVE's existing Genesis faucet solver; installed packages are untouched.
"""
import argparse
import inspect
import json
import time
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("case", type=Path)
parser.add_argument("--frames", type=int, default=96)
parser.add_argument("--diameter", type=float)
parser.add_argument("--substeps", type=int, default=4)
parser.add_argument("--max-density-error", type=float, default=.05)
parser.add_argument("--max-divergence-error", type=float, default=.05)
parser.add_argument("--domain-half", type=float)
parser.add_argument("--surface-friction", type=float, default=.1)
parser.add_argument("--gamma", type=float, default=0.)
parser.add_argument("--coaster", action="store_true")
parser.add_argument("--support-contact-skin", type=float, default=0.,
                    help="Finite particle/reconstructed-surface contact offset in metres, table and coaster only")
parser.add_argument("--watch-ids", type=Path)
parser.add_argument("--watch-frames", type=int, nargs=2, default=(13,32))
args = parser.parse_args()
case = args.case.resolve()
frames_dir = case / "particles"
if frames_dir.exists() and any(frames_dir.iterdir()):
    raise RuntimeError("Refusing to overwrite a populated particle cache")
frames_dir.mkdir(parents=True, exist_ok=True)
config = json.loads((case / "input_config.json").read_text())
physics = config["physics"]
fps, steps_per_frame = 24, 32
dt = 1. / (fps * steps_per_frame)
velocity = np.asarray(physics["velocity_m_s"], dtype=float)
speed = float(np.linalg.norm(velocity))
direction = velocity / speed
# One regular particle layer advances past the physical nozzle per solver step.
# This avoids native emitter length-rounding bursts; it is a constant input.
particle_size = speed * dt
diameter = args.diameter if args.diameter is not None else 9 * particle_size
source_center = np.asarray(physics["outlet_world_m"]) - .5 * particle_size * direction

import genesis as gs
import genesis.engine.simulator as simulator
from genesis.engine.solvers.sph_solver import SPHSolver

class EmittedTeaSPH(SPHSolver):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.active_count = 0
        self.divergence_stats = {"calls":0,"max_residual_kg_m3_s":0.,"iteration_cap_hits":0}
        self.density_stats = {"calls":0,"max_residual_kg_m3":0.,"iteration_cap_hits":0}

    def _divergence_solver_iteration(self):
        self._kernel_divergence_solver_iteration()
        self._kernel_compute_density_time_derivative()
        value = self._kernel_compute_density_error(0.) / max(self.active_count, 1)
        self.last_divergence_error = float(value)
        self.divergence_stats["calls"] += 1
        return value

    def _density_solve_iteration(self):
        self._kernel_density_solve_iteration()
        self._kernel_compute_density_star()
        value = self._kernel_compute_density_error(self._density0) / max(self.active_count, 1)
        self.last_density_error = float(value)
        self.density_stats["calls"] += 1
        return value

    def _divergence_solve(self, f):
        before = self.divergence_stats["calls"]
        super()._divergence_solve(f)
        self.divergence_stats["iteration_cap_hits"] += int(self.divergence_stats["calls"] - before >= self._df_max_div_iters)
        self.divergence_stats["max_residual_kg_m3_s"] = max(self.divergence_stats["max_residual_kg_m3_s"], self.last_divergence_error)

    def _density_solve(self, f):
        before = self.density_stats["calls"]
        super()._density_solve(f)
        self.density_stats["iteration_cap_hits"] += int(self.density_stats["calls"] - before >= self._df_max_den_iters)
        self.density_stats["max_residual_kg_m3"] = max(self.density_stats["max_residual_kg_m3"], self.last_density_error)

    def substep_pre_coupling(self, f):
        if not self.active_count:
            return
        self._kernel_reorder_particles(f)
        self._kernel_compute_rho(f)
        self._kernel_compute_DFSPH_factor(f)
        self._divergence_solve(f)
        # Native1.4.3 also advects using the preceding substep's acceleration
        # here. The established PCVE faucet path applies this step's forces
        # once below, avoiding double gravity/force integration.
        self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
        self._kernel_predict_velocity(f)
        self._density_solve(f)

    def substep_post_coupling(self, f):
        if self.active_count:
            super().substep_post_coupling(f)
            if getattr(self,"watch_enabled",False) and self.watch_start<=self.watch_frame<=self.watch_end:
                # Read-only getters after native advection/copy. No force,
                # position, velocity, active flag, or random state is changed.
                entity=self.watch_entity
                positions=entity.get_particles_pos().reshape(-1,3)[self.watch_tensor].detach().cpu().numpy().copy()
                velocities=entity.get_particles_vel().reshape(-1,3)[self.watch_tensor].detach().cpu().numpy().copy()
                time_s=(self.watch_frame-1)/24+(self.watch_substep+1)*self._substep_dt
                self.watch_records.append((time_s,self.watch_frame,self.active_count,positions,velocities))
        if getattr(self,"watch_enabled",False):
            self.watch_substep+=1

simulator.SPHSolver = EmittedTeaSPH
gs.init(backend=gs.cuda, precision="32", seed=20261026, logging_level="warning")
import genesis.utils.particle as pu
import trimesh

collider = trimesh.load(case / "cup_collider.obj", force="mesh", process=False)
if not collider.is_watertight or not collider.is_winding_consistent or collider.volume <= 0:
    raise RuntimeError("Actual cup collider must be closed with positive consistent winding")
layer = pu.cylinder_to_particles(p_size=particle_size, radius=diameter/2,
                                 height=particle_size, sampler="regular")
per_step = len(layer)
expected_emitted = per_step * steps_per_frame * 72
capacity = expected_emitted + 8 * per_step
lower = (-args.domain_half, -args.domain_half, -.012) if args.domain_half else (-.075, -.065, -.012)
upper = (args.domain_half, args.domain_half, .16) if args.domain_half else (.075, .065, .16)
scene = gs.Scene(
    sim_options=gs.options.SimOptions(dt=dt, substeps=args.substeps, gravity=tuple(physics["gravity_m_s2"])),
    sph_options=gs.options.SPHOptions(particle_size=particle_size, pressure_solver="DFSPH",
        lower_bound=lower, upper_bound=upper,
        max_divergence_error=args.max_divergence_error, max_density_error_percent=args.max_density_error,
        max_divergence_solver_iterations=100, max_density_solver_iterations=100),
    coupler_options=gs.options.LegacyCouplerOptions(rigid_sph=True, rigid_mpm=False,
        rigid_pbd=False,rigid_fem=False,mpm_sph=False,mpm_pbd=False,fem_mpm=False,fem_sph=False),
    show_viewer=False)
cup_material = gs.materials.Rigid(needs_coup=True, coup_friction=.05,
    coup_softness=.0003, coup_restitution=0., sdf_cell_size=.0004, sdf_min_res=128, sdf_max_res=256)
scene.add_entity(morph=gs.morphs.Mesh(file=str(case / "cup_collider.obj"), fixed=True,
    decimate=False, convexify=False), material=cup_material)
assert 0. <= args.support_contact_skin <= particle_size
scene.add_entity(morph=gs.morphs.Plane(pos=(0.,0.,args.support_contact_skin)), material=gs.materials.Rigid(needs_coup=True,
    coup_friction=args.surface_friction,coup_softness=.0003,coup_restitution=0.))
if args.coaster:
    scene.add_entity(morph=gs.morphs.Mesh(file=str(case / "coaster_world.obj"), fixed=True,
        pos=(0.,0.,args.support_contact_skin),
        decimate=False, convexify=False), material=gs.materials.Rigid(needs_coup=True,
        coup_friction=args.surface_friction, coup_softness=.0003, coup_restitution=0.,
        sdf_cell_size=.00025, sdf_min_res=64, sdf_max_res=256))
emitter = scene.add_emitter(max_particles=capacity,
    material=gs.materials.SPH.Liquid(rho=physics["density_kg_m3"],
        mu=physics["kinematic_viscosity_m2_s"], gamma=args.gamma, sampler="regular"))
started = time.monotonic()
scene.build(n_envs=0)
build_seconds = time.monotonic()-started
solver = scene.sim.sph_solver
if args.watch_ids:
    import torch
    value=json.loads(args.watch_ids.read_text())
    watch_ids=np.asarray(value if isinstance(value,list) else value["exterior_ids_without_observed_over_rim"],dtype=np.int64)
    if not len(watch_ids) or watch_ids.min()<0 or watch_ids.max()>=capacity:
        raise RuntimeError("Invalid diagnostic particle IDs")
    solver.watch_enabled=True
    solver.watch_start,solver.watch_end=args.watch_frames
    solver.watch_ids=watch_ids
    solver.watch_tensor=torch.as_tensor(watch_ids,dtype=torch.long,device=gs.device)
    solver.watch_entity=emitter.entity
    solver.watch_records=[]
volume_per_particle_ml = float(solver.particle_volume * 1e6)
mass_per_particle_kg = float(solver.particle_volume * physics["density_kg_m3"])
experiment = {"before":config, "after":{
    "solver":"Genesis1.4.3 DFSPH", "particle_size_m":particle_size,
    "particle_volume_ml":volume_per_particle_ml,"particle_mass_kg":mass_per_particle_kg,
    "step_dt_s":dt,"substeps":args.substeps,"substep_dt_s":dt/args.substeps,
    "source_diameter_m":diameter,"source_center_m":source_center.tolist(),
    "source_speed_m_s":speed,"source_direction":direction.tolist(),
    "particles_per_emission":per_step,"particles_per_frame":per_step*steps_per_frame,
    "constant_mass_flux_kg_s":per_step/dt*mass_per_particle_kg,
    "constant_rest_volume_flux_ml_s":per_step/dt*volume_per_particle_ml,
    "source_on_frames":[13,84],"expected_total_emitted_particles":expected_emitted,
    "capacity_particles":capacity,"water_mu_m2_s":physics["kinematic_viscosity_m2_s"],"gamma":args.gamma,
    "max_density_error_percent":args.max_density_error,
    "max_divergence_error":args.max_divergence_error,
    "domain_bounds_m":[lower, upper], "landing_surface_friction":args.surface_friction,
    "coaster_collision":args.coaster,
    "support_contact_skin_m":args.support_contact_skin,
    "support_contact_skin_note":"Numerical finite-particle contact skin on fixed table/coaster. Visual meshes and actual cup collider unchanged. Applied before simulation, never as a particle/mesh post-correction.",
    "native_patches":["Convergence averages over actual emitted active particles, not inactive capacity",
                      "Apply current nonpressure acceleration once per substep, as PCVE faucet solver"],
    "collider_closed":bool(collider.is_watertight),"collider_positive_volume_m3":float(collider.volume),
    "collider_coupling_softness_m":.0003,"collider_sdf_cell_size_m":.0004},
    "invariants":["No cup-volume or height target supplied to solver","No particle recycling or deletion",
                  "No post-step particle position edits","Only physical spout emits",
                  "Fixed source speed, aperture, material and static cup throughout pour"],
    "timing":{"build_seconds":build_seconds},
    "installed_sph_source":inspect.getfile(SPHSolver)}
(case/"experiment.json").write_text(json.dumps(experiment,indent=2)+"\n")
print("GENESIS_BUILD="+json.dumps(experiment["after"]),flush=True)
rows = {}
started = time.monotonic()
for frame in range(1,args.frames+1):
    tick = time.monotonic()
    solver.watch_frame=frame
    solver.watch_substep=0
    emitted_before = emitter.next_particle
    for step in range(steps_per_frame):
        if 13 <= frame <= 84:
            previous = emitter.next_particle
            emitter.emit(droplet_shape="circle",droplet_size=diameter,
                         pos=tuple(source_center),direction=tuple(direction),speed=speed)
            if emitter.next_particle-previous != per_step:
                raise RuntimeError("Native emitter changed its fixed physical particle flux or recycled particles")
        solver.active_count = emitter.next_particle
        if solver.active_count:
            scene.step()
        else:
            # No liquid exists. Advancing the empty scene keeps the physical clock.
            scene.step()
    positions_all = emitter.entity.get_particles_pos().cpu().numpy().reshape(-1,3)
    velocities_all = emitter.entity.get_particles_vel().cpu().numpy().reshape(-1,3)
    active = emitter.entity.get_particles_active().cpu().numpy().reshape(-1).astype(bool)
    positions, velocities = positions_all[active], velocities_all[active]
    if len(positions) != emitter.next_particle or not np.isfinite(positions).all() or not np.isfinite(velocities).all():
        raise RuntimeError("Lost/nonfinite/duplicated particles")
    np.savez_compressed(frames_dir/f"frame_{frame:04d}.npz",pos=positions,vel=velocities,
                        particle_ids=np.flatnonzero(active).astype(np.int32))
    z = positions[:,2]
    below_rim = (z>=physics["cup_floor_m"]-particle_size) & (z<physics["cup_rim_m"])
    row = {"frame":frame,"time_s":frame/fps,"active_particles":len(positions),
           "new_particles":emitter.next_particle-emitted_before,
           "total_rest_volume_ml":len(positions)*volume_per_particle_ml,
           "below_rim_particle_rest_volume_ml":int(below_rim.sum())*volume_per_particle_ml,
           "below_floor_particle_count":int((z<physics["cup_floor_m"]-particle_size).sum()),
           "maximum_speed_m_s":float(np.linalg.norm(velocities,axis=1).max()) if len(positions) else 0.,
           "bounds_m":[positions.min(0).tolist(),positions.max(0).tolist()] if len(positions) else None,
           "frame_wall_seconds":time.monotonic()-tick}
    rows[str(frame)] = row
    (case/"particle_audit.json").write_text(json.dumps({"frames":rows,"experiment":str(case/"experiment.json")},indent=2)+"\n")
    print("FRAME="+json.dumps(row),flush=True)
elapsed = time.monotonic()-started
if args.watch_ids:
    records=solver.watch_records
    np.savez_compressed(case/"substep_particle_watch.npz",ids=watch_ids,
        times=np.asarray([r[0] for r in records]),frames=np.asarray([r[1] for r in records]),
        active_counts=np.asarray([r[2] for r in records]),
        positions=np.stack([r[3] for r in records]),velocities=np.stack([r[4] for r in records]))
(case/"simulation_result.json").write_text(json.dumps({"frames":args.frames,
    "build_seconds":build_seconds,"simulation_seconds":elapsed,
    "total_emitted_particles":emitter.next_particle,"no_recycling":emitter.next_particle<capacity,
    "completed":True,"density_solver":solver.density_stats,
    "divergence_solver":solver.divergence_stats},indent=2)+"\n")
print("GENESIS_DONE="+json.dumps({"frames":args.frames,"simulation_seconds":elapsed}),flush=True)
