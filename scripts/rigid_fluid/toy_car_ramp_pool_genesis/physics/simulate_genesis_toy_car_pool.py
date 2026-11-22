"""Genesis 1.4.3 rigid-car + DFSPH shallow-pool simulation.

The orange track, pool floor and four pool walls are fixed Genesis rigid
bodies.  The toy car is a free rigid cuboid with the measured mass and size.
Water is Genesis DFSPH and uses the native two-way rigid/SPH coupler, including
the pressure-force patch present in the project's Genesis environment.
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
from pathlib import Path

import numpy as np

FPS = 24
SEED = 20261021
GRAVITY = 9.81

CAR_SIZE = np.array((0.160, 0.071, 0.055), dtype=np.float64)
CAR_MASS = 0.420
CAR_DENSITY = CAR_MASS / float(np.prod(CAR_SIZE))
RAMP_ANGLE_DEG = 18.0
RAMP_START_X = -1.00
RAMP_END_X = -0.20
RAMP_DECK_CENTER_END_Z = 0.217
RAMP_WIDTH = 0.205
RAMP_THICKNESS = 0.008

DOMAIN_LOWER = (-0.25, -0.44, 0.0)
DOMAIN_UPPER = (1.31, 0.44, 0.52)
WATER_XY_CENTER = (0.54, 0.0)
WATER_XY_SIZE = (1.28, 0.60)
WATER_BOTTOM = 0.030


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("settle", "run"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--water-state", type=Path)
    parser.add_argument("--frames", type=int, default=96)
    parser.add_argument("--dx", type=float, default=0.015)
    parser.add_argument("--steps-per-frame", type=int, default=8)
    parser.add_argument("--substeps", type=int, default=4)
    parser.add_argument("--settle-frames", type=int, default=24)
    parser.add_argument("--fluid-damping", type=float, default=0.985)
    parser.add_argument("--preview-frames", type=int, default=0)
    parser.add_argument("--water-height", type=float, default=0.075)
    return parser.parse_args()


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def ramp_center():
    angle = math.radians(RAMP_ANGLE_DEG)
    length = (RAMP_END_X - RAMP_START_X) / math.cos(angle)
    x = 0.5 * (RAMP_START_X + RAMP_END_X)
    z = RAMP_DECK_CENTER_END_Z + (RAMP_END_X - x) * math.tan(angle)
    return (x, 0.0, z), (length, RAMP_WIDTH, RAMP_THICKNESS)


def ramp_surface_z(x):
    angle = math.radians(RAMP_ANGLE_DEG)
    return RAMP_DECK_CENTER_END_Z + (RAMP_END_X - x) * math.tan(angle) + 0.5 * RAMP_THICKNESS / math.cos(angle)


def add_fixed_box(scene, gs, name, center, size, friction, coupling=True):
    entity = scene.add_entity(
        morph=gs.morphs.Box(pos=center, size=size, fixed=True, visualization=False),
        material=gs.materials.Rigid(
            rho=900.0,
            friction=friction,
            needs_coup=coupling,
            coup_friction=0.10,
            coup_softness=0.004,
            coup_restitution=0.0,
            sdf_cell_size=0.004,
            sdf_min_res=24,
            sdf_max_res=96,
        ),
    )
    return entity


def build_scene(args, car_fixed):
    import genesis as gs

    gs.init(backend=gs.cuda, precision="32", seed=SEED, logging_level="warning")
    step_dt = 1.0 / (FPS * args.steps_per_frame)
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(
            dt=step_dt,
            substeps=args.substeps,
            gravity=(0.0, 0.0, -GRAVITY),
            floor_height=-0.10,
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
            lower_bound=DOMAIN_LOWER,
            upper_bound=DOMAIN_UPPER,
            max_divergence_error=0.1,
            max_density_error_percent=0.05,
        ),
        coupler_options=gs.options.LegacyCouplerOptions(
            rigid_mpm=False,
            rigid_sph=True,
            rigid_pbd=False,
            rigid_fem=False,
            mpm_sph=False,
            mpm_pbd=False,
            fem_mpm=False,
            fem_sph=False,
        ),
        show_viewer=False,
    )

    # Closed pool collision tub.  Boxes overlap at the corners so neither the
    # shallow water nor the car can escape through a numerical seam.
    add_fixed_box(scene, gs, "pool_bottom", (0.53, 0.0, 0.015), (1.56, 0.88, 0.03), 0.45)
    add_fixed_box(scene, gs, "pool_side_a", (0.51, 0.39, 0.105), (1.46, 0.10, 0.21), 0.45)
    add_fixed_box(scene, gs, "pool_side_b", (0.51, -0.39, 0.105), (1.46, 0.10, 0.21), 0.45)
    add_fixed_box(scene, gs, "pool_far", (1.26, 0.0, 0.105), (0.10, 0.88, 0.21), 0.45)
    add_fixed_box(scene, gs, "pool_near", (-0.21, 0.0, 0.105), (0.08, 0.88, 0.21), 0.45)

    rc, rs = ramp_center()
    ramp = scene.add_entity(
        morph=gs.morphs.Box(pos=rc, size=rs, euler=(0.0, RAMP_ANGLE_DEG, 0.0), fixed=True, visualization=False),
        material=gs.materials.Rigid(
            rho=900.0,
            friction=0.07,
            needs_coup=False,
            coup_friction=0.0,
            coup_softness=0.002,
            sdf_cell_size=0.003,
            sdf_min_res=24,
            sdf_max_res=96,
        ),
    )

    angle = math.radians(RAMP_ANGLE_DEG)
    contact_x = -0.94
    surface = np.array((contact_x, 0.0, ramp_surface_z(contact_x)), dtype=np.float64)
    normal = np.array((math.sin(angle), 0.0, math.cos(angle)), dtype=np.float64)
    car_center = surface + normal * (0.5 * CAR_SIZE[2] + 0.001)
    car = scene.add_entity(
        morph=gs.morphs.Box(
            pos=tuple(car_center),
            size=tuple(CAR_SIZE),
            euler=(0.0, RAMP_ANGLE_DEG, 0.0),
            fixed=car_fixed,
            visualization=False,
        ),
        material=gs.materials.Rigid(
            rho=CAR_DENSITY,
            friction=0.10,
            friction_rolling=0.0003,
            friction_torsional=0.001,
            needs_coup=not car_fixed,
            coup_friction=0.10,
            coup_softness=0.003,
            coup_restitution=0.0,
            sdf_cell_size=0.003,
            sdf_min_res=28,
            sdf_max_res=96,
        ),
    )

    if not 0.03 <= args.water_height <= 0.17:
        raise ValueError("--water-height must be between 0.03 and 0.17 m")
    water_center = (*WATER_XY_CENTER, WATER_BOTTOM + 0.5 * args.water_height)
    water_size = (*WATER_XY_SIZE, args.water_height)
    water = scene.add_entity(
        morph=gs.morphs.Box(pos=water_center, size=water_size),
        material=gs.materials.SPH.Liquid(rho=998.0, mu=1.004e-6, gamma=0.0, sampler="regular"),
        surface=gs.surfaces.Default(color=(0.2, 0.6, 1.0, 1.0), vis_mode="particle"),
    )
    tick = time.monotonic()
    scene.build(n_envs=0)
    return gs, scene, car, water, time.monotonic() - tick, car_center, water_center, water_size


def particle_state(entity):
    pos = entity.get_particles_pos().cpu().numpy().reshape(-1, 3).astype(np.float32)
    vel = entity.get_particles_vel().cpu().numpy().reshape(-1, 3).astype(np.float32)
    return pos, vel


def rigid_state(car):
    pos = car.get_pos().cpu().numpy().reshape(-1, 3)[0].astype(np.float64)
    quat = car.get_quat().cpu().numpy().reshape(-1, 4)[0].astype(np.float64)
    vel = car.get_vel().cpu().numpy().reshape(-1, 3)[0].astype(np.float64)
    ang = car.get_ang().cpu().numpy().reshape(-1, 3)[0].astype(np.float64)
    return pos, quat, vel, ang


def settle(args):
    args.out.mkdir(parents=True, exist_ok=False)
    gs, scene, car, water, build_seconds, car_center, water_center, water_size = build_scene(args, car_fixed=True)
    samples = []
    for frame in range(1, args.settle_frames + 1):
        for _ in range(args.steps_per_frame):
            scene.step()
        pos, vel = particle_state(water)
        vel *= args.fluid_damping
        water.set_particles_vel(vel)
        speed = np.linalg.norm(vel, axis=1)
        if frame == 1 or frame % 6 == 0 or frame == args.settle_frames:
            row = {"frame": frame, "max_speed": float(speed.max()), "p99_speed": float(np.percentile(speed, 99)),
                   "z_min": float(pos[:, 2].min()), "z_max": float(pos[:, 2].max())}
            samples.append(row)
            print("SETTLE", json.dumps(row), flush=True)
    pos, vel = particle_state(water)
    np.savez_compressed(
        args.out / "water_state.npz",
        water_pos=pos,
        water_vel=np.zeros_like(vel),
        dx=args.dx,
        water_height=args.water_height,
    )
    report = {"solver": "Genesis 1.4.3 native rigid + DFSPH", "mode": "settle", "build_seconds": build_seconds,
              "water_particles": len(pos), "car_center": car_center.tolist(),
              "water_initial_center_m": list(water_center), "water_initial_size_m": list(water_size),
              "samples": samples}
    save_json(args.out / "settle_report.json", report)


def run(args):
    if args.water_state is None:
        raise ValueError("--water-state is required for run mode")
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "particles").mkdir()
    gs, scene, car, water, build_seconds, car_center, water_center, water_size = build_scene(args, car_fixed=False)
    with np.load(args.water_state) as state:
        if not math.isclose(float(state["dx"]), args.dx):
            raise ValueError("water state particle spacing mismatch")
        if "water_height" in state and not math.isclose(float(state["water_height"]), args.water_height):
            raise ValueError("water state height mismatch")
        water.set_particles_pos(state["water_pos"])
        water.set_particles_vel(state["water_vel"])
    frames = min(args.frames, args.preview_frames) if args.preview_frames else args.frames
    rows = []
    writer = None
    started = time.monotonic()
    for frame in range(1, frames + 1):
        tick = time.monotonic()
        if frame > 1:
            for _ in range(args.steps_per_frame):
                scene.step()
        pos, vel = particle_state(water)
        cpos, quat, cvel, cang = rigid_state(car)
        if writer is not None:
            writer.join()
        target = args.out / "particles" / f"frame_{frame:04d}.npz"
        writer = threading.Thread(
            target=np.savez_compressed,
            args=(target,),
            kwargs={"water_pos": pos, "water_vel": vel.astype(np.float16), "car_pos": cpos,
                    "car_quat_wxyz": quat, "car_vel": cvel, "car_ang": cang},
        )
        writer.start()
        speed = np.linalg.norm(vel, axis=1)
        row = {"frame": frame, "time_s": (frame - 1) / FPS, "car_pos": cpos.tolist(),
               "car_quat_wxyz": quat.tolist(), "car_vel": cvel.tolist(), "car_ang": cang.tolist(),
               "water_z_max": float(pos[:, 2].max()), "water_speed_max": float(speed.max()),
               "water_speed_p99": float(np.percentile(speed, 99)), "compute_seconds": time.monotonic() - tick}
        rows.append(row)
        if frame == 1 or frame % 4 == 0:
            print("FRAME", frame, "car", np.round(cpos, 4).tolist(), "v", np.round(cvel, 3).tolist(),
                  "water zmax", round(row["water_z_max"], 4), flush=True)
        if not np.isfinite(pos).all() or not np.isfinite(cpos).all():
            raise RuntimeError("non-finite Genesis state")
    if writer is not None:
        writer.join()
    report = {
        "status": "complete",
        "solver": "Genesis 1.4.3 native rigid body + DFSPH liquid with two-way rigid_sph coupling",
        "coupling": "Genesis native two-way rigid/SPH momentum transfer and pressure buoyancy",
        "physics": {"car_mass_kg": CAR_MASS, "car_size_m": CAR_SIZE.tolist(), "water_density_kg_m3": 998.0,
                    "water_kinematic_viscosity_m2_s": 1.004e-6, "gravity_m_s2": GRAVITY},
        "numerics": {"fps": FPS, "frames": frames, "dx_m": args.dx, "steps_per_frame": args.steps_per_frame,
                     "substeps_per_step": args.substeps},
        "build_seconds": build_seconds,
        "simulation_seconds": time.monotonic() - started,
        "water_particles": int(len(pos)),
        "water_initial_center_m": list(water_center),
        "water_initial_size_m": list(water_size),
        "initial_car_center": car_center.tolist(),
        "frames": rows,
    }
    save_json(args.out / "simulation_report.json", report)
    print("GENESIS_DONE", json.dumps({"frames": frames, "seconds": report["simulation_seconds"]}), flush=True)


def main():
    args = parse_args()
    if args.mode == "settle":
        settle(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
