"""Solve both toy impacts and export actual rigid poses, velocities and contact impulses."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END

import argparse
import csv
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import time

from scene_config import SCENE, SUPPORTED_CASES, body_present, scenario, signature


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def simulate(cfg, case_id="source"):
    import pybullet as p
    start = time.perf_counter()
    ph, sq, rd = (cfg[key] for key in ("physics", "simulation_quality", "render"))
    sub, fps, count = sq["substeps_per_frame"], rd["fps"], rd["total_frames"]
    dt = 1.0 / (fps * sub)
    stride = max(1, round(1.0 / (dt * sq["trajectory_hz"])))
    cid = p.connect(p.DIRECT)
    try:
        p.setGravity(*ph["gravity"], physicsClientId=cid)
        p.setTimeStep(dt, physicsClientId=cid)
        p.setPhysicsEngineParameter(fixedTimeStep=dt, numSolverIterations=sq["solver_iterations"],
            contactSlop=sq["contact_slop_m"], contactBreakingThreshold=sq["contact_breaking_threshold_m"],
            restitutionVelocityThreshold=sq["restitution_velocity_threshold_m_per_s"],
            useSplitImpulse=int(sq["use_split_impulse"]),
            splitImpulsePenetrationThreshold=sq["split_impulse_penetration_threshold_m"],
            contactERP=sq["contact_erp"], deterministicOverlappingPairs=1, physicsClientId=cid)
        half = [v / 2 for v in ph["floor"]["dimensions_m"]]
        shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid)
        ground = p.createMultiBody(0, shape, basePosition=[0, 0, ph["floor"]["top_z_m"] - half[2]], physicsClientId=cid)
        p.changeDynamics(ground, -1, restitution=ph["floor"]["restitution"],
                         lateralFriction=ph["floor"]["lateral_friction"],
                         rollingFriction=0, spinningFriction=0, physicsClientId=cid)
        bodies, actual = {}, {}
        for name in ("ball", "box", "football"):
            item = ph[name]
            if not body_present(cfg, name, 0):
                continue
            if "radius_m" in item:
                shape = p.createCollisionShape(p.GEOM_SPHERE, radius=item["radius_m"], physicsClientId=cid)
            else:
                shape = p.createCollisionShape(p.GEOM_BOX,
                    halfExtents=[v / 2 for v in item["dimensions_m"]], physicsClientId=cid)
            body = p.createMultiBody(item["mass_kg"], shape, basePosition=item["initial_position_m"],
                baseOrientation=item["initial_quaternion_xyzw"], useMaximalCoordinates=True, physicsClientId=cid)
            dynamics = dict(mass=item["mass_kg"], restitution=item["restitution"], lateralFriction=item["lateral_friction"],
                rollingFriction=item["rolling_friction"], spinningFriction=item["spinning_friction"],
                linearDamping=item["linear_damping"], angularDamping=item["angular_damping"], collisionMargin=0,
                activationState=p.ACTIVATION_STATE_DISABLE_SLEEPING)
            if "radius_m" in item:
                inertia = item["inertia_factor"] * item["mass_kg"] * item["radius_m"] ** 2
                dynamics["localInertiaDiagonal"] = [inertia] * 3
            p.changeDynamics(body, -1, **dynamics, physicsClientId=cid)
            p.resetBaseVelocity(body, item.get("initial_velocity_m_per_s", [0, 0, 0]),
                                item.get("initial_angular_velocity_rad_per_s", [0, 0, 0]), physicsClientId=cid)
            bodies[name] = body
            info = p.getDynamicsInfo(body, -1, physicsClientId=cid)
            aabb = p.getAABB(body, -1, physicsClientId=cid)
            actual[name] = {"mass_kg": info[0], "inertia_kg_m2": list(info[2]),
                            "lateral_friction": info[1], "requested_restitution": item["restitution"],
                            # Bullet's maximal-coordinate btRigidBody getter
                            # omits m_restitution (server processor rigid-body
                            # branch). Its slot can contain stale data. Check
                            # restitution through the measured normal response.
                            "restitution_readback": None,
                            "restitution_readback_note": "getDynamicsInfo does not populate restitution for btRigidBody; solver application is checked through impact response.",
                            "rolling_friction": info[6], "spinning_friction": info[7],
                            "collision_geometry_type": p.GEOM_SPHERE if "radius_m" in item else p.GEOM_BOX,
                            "initial_collision_aabb_m": [list(v) for v in aabb]}

        def snapshot(time_sec):
            now = {"time_sec": time_sec, "objects": {}, "mechanical_energy_J": 0.0}
            for name, body in bodies.items():
                xyz, q = p.getBasePositionAndOrientation(body, physicsClientId=cid)
                v, w = p.getBaseVelocity(body, physicsClientId=cid)
                local_w = p.rotateVector(p.invertTransform([0, 0, 0], q)[1], w)
                mass = actual[name]["mass_kg"]
                item = {"id": ph[name]["id"], "location": list(xyz), "quaternion_xyzw": list(q),
                        "linear_velocity": list(v), "angular_velocity": list(w)}
                now["objects"][name] = item
                rest_height = ph[name].get("radius_m", ph[name].get("dimensions_m", [0, 0, 0])[2] / 2)
                now["mechanical_energy_J"] += max(0, mass * -ph["gravity"][2] * (xyz[2] - rest_height - ph["floor"]["top_z_m"]))
                now["mechanical_energy_J"] += 0.5 * mass * sum(a * a for a in v)
                now["mechanical_energy_J"] += 0.5 * sum(i * a * a for i, a in zip(actual[name]["inertia_kg_m2"], local_w))
                if not all(math.isfinite(a) for a in (*xyz, *q, *v, *w)):
                    raise RuntimeError(f"Nonfinite rigid state at t={time_sec} for {name}: {xyz}, {q}, {v}, {w}; dynamics={actual}")
            return now

        removal = ph["football"].get("remove_at_sec")
        removal_step = round(removal / dt) if removal is not None else None
        if removal is not None and abs(removal_step * dt - removal) > 1e-10:
            raise ValueError("The removal time must be an exact solver step")
        samples, frames, events, interventions = [], [], [], []
        previous, live = None, {}
        minimum_gap = 0.0
        max_energy = 0.0
        for step in range(count * sub + 1):
            if step:
                p.stepSimulation(physicsClientId=cid)
            # Integrate the unchanged world up to the intervention time, remove
            # only the target body, and then expose the state at that time.
            # Frame 49 samples t=2 exactly. No other state is reset or re-solved.
            if step == removal_step:
                before = snapshot(step * dt)
                removed = before["objects"].get("football")
                if "football" in bodies:
                    p.removeBody(bodies.pop("football"), physicsClientId=cid)
                if "football" in live:
                    live.pop("football")["termination"] = {"reason": "body_removed", "time_sec": step * dt}
                after = snapshot(step * dt)
                interventions.append({"operation": "DELETE", "object_id": ph["football"]["id"],
                    "target": "football", "time_sec": step * dt, "solver_step": step,
                    "frame_float": 1 + step * dt * fps, "body_was_created": removed is not None,
                    "removed_state": removed, "before_state": before, "after_state": after,
                    "removed_mechanical_energy_J": before["mechanical_energy_J"] - after["mechanical_energy_J"],
                    "continuation_policy": "Same solver world; no reset, impulse or pose correction for surviving bodies."})
            now = snapshot(step * dt)
            max_energy = max(max_energy, now["mechanical_energy_J"])
            for name in bodies:
                for cp in p.getContactPoints(bodyA=bodies[name], bodyB=ground, physicsClientId=cid):
                    minimum_gap = min(minimum_gap, cp[8])
            for other in ("box", "football"):
                if other not in bodies or "ball" not in bodies:
                    continue
                points = p.getContactPoints(bodyA=bodies["ball"], bodyB=bodies[other], physicsClientId=cid)
                contacts = [cp for cp in points if cp[9] > 0.005]
                for cp in points:
                    minimum_gap = min(minimum_gap, cp[8])
                if contacts and other not in live:
                    cp = max(contacts, key=lambda c: c[9])
                    event = {"event_index": len(events) + 1, "pair": ["ball", other],
                        "object_ids": [ph["ball"]["id"], ph[other]["id"]],
                        "time_sec": now["time_sec"], "frame_float": 1 + now["time_sec"] * fps,
                        "contact_position_m": list(cp[6]), "contact_normal": list(cp[7]),
                        "signed_gap_m": cp[8], "normal_impulse_Ns": 0.0,
                        "pre_state": previous or now, "first_post_state": now, "last_contact_state": now}
                    events.append(event)
                    live[other] = event
                if contacts:
                    live[other]["normal_impulse_Ns"] += sum(cp[9] for cp in contacts) * dt
                    live[other]["last_contact_state"] = now
                elif other in live:
                    live[other]["separation_state"] = now
                    del live[other]
            if step % stride == 0:
                samples.append(now)
            if step % sub == 0 and step < count * sub:
                frames.append({"frame_index": step // sub + 1, **now})
            previous = now

        return {"schema_version": 2, "scene": SCENE, "category": "rigid_rigid", "case_id": case_id,
            "simulator": "PyBullet", "solver_version": importlib.metadata.version("pybullet"),
            "python_version": platform.python_version(), "configuration": cfg,
            "configuration_sha256": signature(cfg), "physics_dt_sec": dt, "fps": fps,
            "frame_start": 1, "frame_end": count, "duration_sec": rd["duration_sec"],
            "sample_time_convention": "Frame f samples t=(f-1)/fps; 96 frame exposures encode exactly 4 seconds.",
            "prescribed_motion": False, "constraints": [], "external_forces": [],
            "velocity_initialization_count_per_body": 1, "actual_dynamics": actual,
            "velocity_initialization_counts": {name: 1 for name in actual},
            "object_lifecycle": {name: {"id": ph[name]["id"], "created": name in actual,
                "present_from_sec": 0.0 if name in actual else None,
                "remove_at_sec": ph[name].get("remove_at_sec")} for name in ("ball", "box", "football")},
            "intervention_events": interventions,
            "contact_combination": "Bullet restitution and lateral friction multiply per-body values. Combined rolling friction uses rho_A*mu_B + rho_B*mu_A; edits leave the configured rolling parameters unchanged.",
            "frames": frames, "trajectory_samples": samples, "contact_events": events,
            "quality": {"minimum_signed_contact_gap_m": minimum_gap,
                        "maximum_mechanical_energy_J": max_energy},
            "final_state": now, "simulation_wall_sec": time.perf_counter() - start}
    finally:
        p.disconnect(cid)


def export_csv(path, result):
    with Path(path).open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["time_sec", "object_id", "x_m", "y_m", "z_m", "qx", "qy", "qz", "qw",
                         "vx_m_per_s", "vy_m_per_s", "vz_m_per_s", "wx_rad_per_s", "wy_rad_per_s", "wz_rad_per_s"])
        for state in result["trajectory_samples"]:
            for item in state["objects"].values():
                writer.writerow([state["time_sec"], item["id"], *item["location"], *item["quaternion_xyzw"],
                                 *item["linear_velocity"], *item["angular_velocity"]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config-json", type=Path)
    parser.add_argument("--case-id", choices=SUPPORTED_CASES, default="source")
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    override = json.loads(args.config_json.read_text()) if args.config_json else None
    cfg = scenario(override, case=args.case_id)
    result = simulate(cfg, args.case_id)
    write_json(args.out, result)
    export_csv(args.out.with_name("trajectory.csv"), result)
    write_json(args.out.with_name("contacts.json"), result["contact_events"])
    write_json(args.out.with_name("interventions.json"), result["intervention_events"])
    from physics.validate_ball_box_rebound import validate
    source = simulate(scenario(override)) if args.case_id != "source" else None
    report = validate(result, source=source)
    write_json(args.out.with_name("physics_validation.json"), report)
    print(json.dumps(report, indent=2))
    if not report["accepted"]:
        raise RuntimeError("Physics acceptance failed; see physics_validation.json")


if __name__ == "__main__":
    main()
