"""Tea counterfactuals: fixed-resolution inlet speed and actual particle deletion.

No cup-height, desired cup amount, fill mesh, or post-step position projection.
The active-particle convergence normalization and single force integration
follow PCVE's existing Genesis faucet solver; installed packages are untouched.

A timed edit continues the accepted source instead of re-solving its prefix:
--resume-from <source case> --resume-frame K copies the source's particle files
for frames 1..K-1, loads its state after frame K-1 (positions, velocities,
active set, emitter position; DFSPH keeps no other state between substeps),
checks the handoff bit for bit and simulates frames K..96 with the edit.
"""
import argparse
import inspect
import json
import math
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
parser.add_argument("--speed-scale", type=float, choices=(.5, 1., 2.), default=1.)
parser.add_argument("--delete-at-sec", type=float)
parser.add_argument("--stop-flow-at-sec", type=float,
                    help="Set inlet velocity and its volume flux to zero; retain and simulate every emitted particle")
parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
parser.add_argument("--resume-from", type=Path,
                    help="Accepted case directory (e.g. the accepted source run) whose particles/frame_####.npz this run continues")
parser.add_argument("--resume-frame", type=int,
                    help="First frame this run simulates. The state saved after frame resume_frame-1 (solver time "
                         "(resume_frame-1)/24 s) is the initial state; frames before it are the resumed case's own files")
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
baseline_speed = float(np.linalg.norm(velocity))
speed = baseline_speed * args.speed_scale
direction = velocity / baseline_speed
velocity = velocity * args.speed_scale
delete_frame = None if args.delete_at_sec is None else math.ceil(args.delete_at_sec*fps)+1
stop_flow_frame = None if args.stop_flow_at_sec is None else math.ceil(args.stop_flow_at_sec*fps)+1
if args.stop_flow_at_sec is not None and args.stop_flow_at_sec < 0:
    raise ValueError("Flow-stop time must be nonnegative")
if delete_frame is not None and stop_flow_frame is not None:
    raise ValueError("Deletion and inlet stopping are separate edits")
emission_end_frame = min(84, delete_frame-1 if delete_frame is not None else 84,
                         stop_flow_frame-1 if stop_flow_frame is not None else 84)
if args.delete_at_sec is not None and args.delete_at_sec < 0:
    raise ValueError("Deletion time must be nonnegative")
if (args.resume_from is None) != (args.resume_frame is None):
    raise ValueError("--resume-from and --resume-frame go together")
first_frame = 1
if args.resume_from is not None:
    # A branch continues an accepted run: everything before the branch is that run's own state.
    if args.speed_scale != 1. or delete_frame is not None:
        raise ValueError("Only an unscaled run without deletion can continue another case")
    if not 1 < args.resume_frame <= args.frames:
        raise ValueError(f"--resume-frame must be in 2..{args.frames}")
    if stop_flow_frame is not None and args.resume_frame > stop_flow_frame:
        raise ValueError("The branch must start no later than the edit it carries")
    first_frame = args.resume_frame
# Freeze baseline particle spacing/aperture. Native slab length and emission
# cadence follow edited speed, changing mass flux with fixed nozzle geometry.
particle_size = baseline_speed * dt
diameter = args.diameter if args.diameter is not None else 9 * particle_size
source_center = np.asarray(physics["outlet_world_m"]) - .5 * max(particle_size, speed*dt) * direction

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
gs.init(backend=getattr(gs,args.device), precision="32", seed=20261026, logging_level="warning")
import genesis.utils.particle as pu
import trimesh

collider = trimesh.load(case / "cup_collider.obj", force="mesh", process=False)
if not collider.is_watertight or not collider.is_winding_consistent or collider.volume <= 0:
    raise RuntimeError("Actual cup collider must be closed with positive consistent winding")
layer = pu.cylinder_to_particles(p_size=particle_size, radius=diameter/2,
                                 height=particle_size, sampler="regular")
per_step = len(layer)
expected_emitted = int(per_step * steps_per_frame * 72 * args.speed_scale)
capacity = expected_emitted + 8 * per_step
active_pour_frames = max(0, emission_end_frame-12)
expected_actual_emitted = int(per_step*steps_per_frame*active_pour_frames*args.speed_scale)
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
    "particles_per_emission_layer":per_step,"particles_per_frame":int(per_step*steps_per_frame*args.speed_scale),
    "speed_scale":args.speed_scale,"baseline_speed_m_s":baseline_speed,
    "deletion_sec":args.delete_at_sec,"deletion_frame":delete_frame,
    "stop_flow_sec":args.stop_flow_at_sec,"stop_flow_frame":stop_flow_frame,
    "velocity_after_flow_stop_m_s":[0.,0.,0.] if stop_flow_frame is not None else None,
    "flow_stop_semantics":"At the beginning of the event frame set inlet velocity and mass/volume flux to zero. Keep every existing particle active and continue the same SPH solve.",
    "execution_backend":args.device,
    "deletion_semantics":"Deactivate all tea particles at the beginning of the display frame and disable all subsequent emission",
    "expected_actual_emitted_particles":expected_actual_emitted,
    "constant_mass_flux_kg_s":per_step/dt*mass_per_particle_kg*args.speed_scale,
    "constant_rest_volume_flux_ml_s":per_step/dt*volume_per_particle_ml*args.speed_scale,
    "source_on_frames":[13,emission_end_frame],"expected_total_emitted_particles":expected_emitted,
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
    "invariants":["No cup-volume or height target supplied to solver","No particle recycling; only the explicitly requested existence intervention deletes particles",
                  "No post-step particle position edits","Only physical spout emits",
                  "Fixed source speed, aperture, material and static cup throughout each active pour; baseline particle size and time steps unchanged"],
    "timing":{"build_seconds":build_seconds},
    "installed_sph_source":inspect.getfile(SPHSolver)}
if args.resume_from is not None:
    experiment["after"]["resumed_from"] = {"case":str(args.resume_from.resolve()),"first_simulated_frame":first_frame,
        "initial_state_file":str(args.resume_from.resolve()/"particles"/f"frame_{first_frame-1:04d}.npz"),
        "initial_state_solver_time_s":(first_frame-1)/fps,
        "semantics":"Frames before first_simulated_frame are the resumed case's own particle files; its state after frame "
                    "first_simulated_frame-1 (positions, velocities, active set and emitter position) is the initial state."}
    # validate_tea_edit.py checks the copied particle (and surface) prefix byte for byte when this is present.
    experiment["cache_branch"] = {"method":"Exact accepted particle prefix for frames 1..%d; the solver state after frame %d "
                                           "is the initial state of the continued DFSPH solve that carries the edit from frame %d."
                                           % (first_frame-1, first_frame-1, first_frame),
        "source":str(args.resume_from.resolve()),"source_last_frame":first_frame-1,"resume_frame":first_frame,
        "resimulation_before_branch_reused":False,
        "reason":"CUDA reductions are not bitwise deterministic; continuing the accepted state keeps the prefix exact."}
(case/"experiment.json").write_text(json.dumps(experiment,indent=2)+"\n")
print("GENESIS_BUILD="+json.dumps(experiment["after"]),flush=True)


def audit_row(frame, positions, velocities, inlet_velocity, new_particles, deleted_this_frame, removed, wall_seconds):
    z = positions[:,2]
    below_rim = (z>=physics["cup_floor_m"]-particle_size) & (z<physics["cup_rim_m"])
    return {"frame":frame,"time_s":(frame-1)/fps,"solver_snapshot_time_s":frame/fps,
            "inlet_command_velocity_m_s":inlet_velocity.tolist(),
            "inlet_command_speed_m_s":float(np.linalg.norm(inlet_velocity)),
            "inlet_volume_flux_ml_s":(experiment['after']['constant_rest_volume_flux_ml_s'] if 13<=frame<=emission_end_frame else 0.),
            "active_particles":len(positions),"deleted_this_frame":deleted_this_frame,
            "cumulative_deleted_particles":removed,
            "new_particles":new_particles,
            "total_rest_volume_ml":len(positions)*volume_per_particle_ml,
            "below_rim_particle_rest_volume_ml":int(below_rim.sum())*volume_per_particle_ml,
            "below_floor_particle_count":int((z<physics["cup_floor_m"]-particle_size).sum()),
            "maximum_speed_m_s":float(np.linalg.norm(velocities,axis=1).max()) if len(positions) else 0.,
            "bounds_m":[positions.min(0).tolist(),positions.max(0).tolist()] if len(positions) else None,
            "frame_wall_seconds":wall_seconds}


rows = {}
started = time.monotonic()
removed_particles = 0
emission_steps = 0
handoff = None
if args.resume_from is not None:
    import shutil
    import torch
    resumed = args.resume_from.resolve()
    resumed_experiment = json.loads((resumed/"experiment.json").read_text())
    if resumed_experiment["before"] != experiment["before"]:
        raise RuntimeError("The resumed case has other physical inputs")
    mine = json.loads(json.dumps(experiment["after"]))
    same_numerics = ("particle_size_m","particle_volume_ml","particle_mass_kg","step_dt_s","substeps","substep_dt_s",
                     "source_diameter_m","source_center_m","source_speed_m_s","source_direction","capacity_particles",
                     "water_mu_m2_s","gamma","max_density_error_percent","max_divergence_error","domain_bounds_m",
                     "landing_surface_friction","coaster_collision","support_contact_skin_m","native_patches",
                     "collider_positive_volume_m3","collider_coupling_softness_m","collider_sdf_cell_size_m")
    differ = [k for k in same_numerics if resumed_experiment["after"].get(k) != mine.get(k)]
    if differ:
        raise RuntimeError(f"The resumed case was solved with other numerics: {differ}")
    previous = first_frame-1
    with np.load(resumed/"particles"/f"frame_{previous:04d}.npz") as state:
        pos0, vel0, ids0 = state["pos"], state["vel"], state["particle_ids"]
    emitted0 = per_step*steps_per_frame*max(0, min(previous, emission_end_frame)-12)
    if len(ids0) != emitted0 or not np.array_equal(ids0, np.arange(emitted0, dtype=ids0.dtype)):
        raise RuntimeError(f"The resumed state is not the emitted prefix 0..{emitted0}: {len(ids0)} particles")
    entity = emitter.entity
    if emitted0:
        index = torch.arange(0, emitted0, dtype=gs.tc_int, device=gs.device)
        # Same calls as Emitter.emit; set_particles_pos zeroes velocity, so velocity goes second.
        entity.set_particles_pos(pos0, index)
        entity.set_particles_vel(vel0, index)
        entity.set_particles_active(gs.ACTIVE, index)
    emitter._next_particle = emitted0
    emission_steps = max(0, min(previous, emission_end_frame)-12)*steps_per_frame
    solver.active_count = emitted0
    scene.sim._cur_substep_global = previous*steps_per_frame*args.substeps
    back_pos = entity.get_particles_pos().cpu().numpy().reshape(-1,3)
    back_vel = entity.get_particles_vel().cpu().numpy().reshape(-1,3)
    back_active = entity.get_particles_active().cpu().numpy().reshape(-1).astype(bool)
    handoff = {"resumed_case":str(resumed),"state_file":str(resumed/"particles"/f"frame_{previous:04d}.npz"),
               "state_solver_time_s":previous/fps,"first_simulated_frame":first_frame,"particles":int(emitted0),
               "position_max_abs_error_m":float(np.abs(back_pos[:emitted0]-pos0).max()) if emitted0 else 0.,
               "velocity_max_abs_error_m_s":float(np.abs(back_vel[:emitted0]-vel0).max()) if emitted0 else 0.,
               "emitted_prefix_active":bool(back_active[:emitted0].all()),"rest_inactive":bool(not back_active[emitted0:].any()),
               "sim_substep_counter":int(scene.sim._cur_substep_global)}
    if not (handoff["position_max_abs_error_m"] < 1e-8 and handoff["velocity_max_abs_error_m_s"] < 1e-8
            and handoff["emitted_prefix_active"] and handoff["rest_inactive"]):
        raise RuntimeError(f"Handoff state differs from the resumed case: {handoff}")
    (case/"resume_handoff.json").write_text(json.dumps(handoff,indent=2)+"\n")
    print("RESUMED="+json.dumps(handoff),flush=True)
    for frame in range(1, first_frame):
        source_file = resumed/"particles"/f"frame_{frame:04d}.npz"
        shutil.copy2(source_file, frames_dir/source_file.name)
        with np.load(frames_dir/source_file.name) as state:
            positions, velocities = state["pos"], state["vel"]
        new_particles = per_step*steps_per_frame if 13<=frame<=emission_end_frame else 0
        row = audit_row(frame, positions, velocities, velocity.copy(), new_particles, 0, 0, 0.)
        row["copied_from_resumed_case"] = str(source_file)
        rows[str(frame)] = row
for frame in range(first_frame,args.frames+1):
    tick = time.monotonic()
    inlet_velocity = np.zeros(3) if stop_flow_frame is not None and frame>=stop_flow_frame else velocity.copy()
    inlet_speed = float(np.linalg.norm(inlet_velocity))
    solver.watch_frame=frame
    solver.watch_substep=0
    emitted_before = emitter.next_particle
    deleted_this_frame = 0
    if frame == delete_frame:
        deleted_this_frame = emitter.next_particle
        emitter.entity.set_particles_active(False)
        removed_particles = emitter.next_particle
        solver.active_count = 0
        assert not emitter.entity.get_particles_active().any()
    for step in range(steps_per_frame):
        if 13 <= frame <= emission_end_frame and inlet_speed>0:
            emitter.emit(droplet_shape="circle",droplet_size=diameter,
                         pos=tuple(source_center),direction=tuple(direction),speed=inlet_speed)
            emission_steps += 1
            expected = int(math.floor(emission_steps * args.speed_scale + 1e-8))*per_step
            if emitter.next_particle != expected:
                raise RuntimeError(f"Native emitter mass flux mismatch: {emitter.next_particle} != {expected}")
        solver.active_count = emitter.next_particle - removed_particles
        if solver.active_count:
            scene.step()
        else:
            # No liquid exists. Advancing the empty scene keeps the physical clock.
            scene.step()
    positions_all = emitter.entity.get_particles_pos().cpu().numpy().reshape(-1,3)
    velocities_all = emitter.entity.get_particles_vel().cpu().numpy().reshape(-1,3)
    active = emitter.entity.get_particles_active().cpu().numpy().reshape(-1).astype(bool)
    positions, velocities = positions_all[active], velocities_all[active]
    if len(positions) != emitter.next_particle - removed_particles or not np.isfinite(positions).all() or not np.isfinite(velocities).all():
        raise RuntimeError("Lost/nonfinite/duplicated particles")
    np.savez_compressed(frames_dir/f"frame_{frame:04d}.npz",pos=positions,vel=velocities,
                        particle_ids=np.flatnonzero(active).astype(np.int32))
    row = audit_row(frame, positions, velocities, inlet_velocity, emitter.next_particle-emitted_before,
                    deleted_this_frame, removed_particles, time.monotonic()-tick)
    rows[str(frame)] = row
    (case/"particle_audit.json").write_text(json.dumps({"frames":rows,"experiment":str(case/"experiment.json")},indent=2)+"\n")
    print("FRAME="+json.dumps(row),flush=True)
elapsed = time.monotonic()-started
assert emitter.next_particle == expected_actual_emitted
if delete_frame is not None and delete_frame <= args.frames:
    assert solver.active_count == 0
if args.watch_ids:
    records=solver.watch_records
    np.savez_compressed(case/"substep_particle_watch.npz",ids=watch_ids,
        times=np.asarray([r[0] for r in records]),frames=np.asarray([r[1] for r in records]),
        active_counts=np.asarray([r[2] for r in records]),
        positions=np.stack([r[3] for r in records]),velocities=np.stack([r[4] for r in records]))
(case/"simulation_result.json").write_text(json.dumps({"frames":args.frames,
    "build_seconds":build_seconds,"simulation_seconds":elapsed,
    "total_emitted_particles":emitter.next_particle,"no_recycling":emitter.next_particle<capacity,
    "expected_total_emitted_particles":expected_actual_emitted,"deleted_particles":removed_particles,
    "deletion_frame":delete_frame,"deletion_sec":args.delete_at_sec,
    "stop_flow_frame":stop_flow_frame,"stop_flow_sec":args.stop_flow_at_sec,
    "retained_particles_after_stop":solver.active_count if stop_flow_frame is not None else None,
    "execution_backend":args.device,"resumed_from":handoff,
    "completed":True,"density_solver":solver.density_stats,
    "divergence_solver":solver.divergence_stats},indent=2)+"\n")
print("GENESIS_DONE="+json.dumps({"frames":args.frames,"simulation_seconds":elapsed}),flush=True)
