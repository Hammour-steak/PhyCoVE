"""Free 6-DOF hollow-sphere rigid body, one initial velocity, genuine Bullet contacts."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END

import argparse
import csv
import importlib.metadata
import json
import math
import platform
import time
from pathlib import Path
import pybullet as p
from scene_config import scenario, signature, colliders, collider_mesh, SUPPORTED_CASES

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n")

def norm(v):
    return math.sqrt(sum(x*x for x in v))

def simulate(cfg, record=True):
    start = time.perf_counter()
    ph, sq, rd = [cfg[k] for k in ("physics", "simulation_quality", "render")]
    ball, stairs = ph["ball"], ph["stairs"]
    fps, nframes = rd["fps"], round(rd["fps"]*rd["duration_sec"])
    sub = sq["substeps_per_frame"]
    dt = 1/(fps*sub)
    stride = max(1, round(1/(dt*sq["trajectory_hz"])))
    r, m = ball["radius_m"], ball["mass_kg"]
    inertia = ball["inertia_factor"]*m*r*r
    cid = p.connect(p.DIRECT)
    try:
        p.setGravity(*ph["gravity"], physicsClientId=cid)
        p.setTimeStep(dt, physicsClientId=cid)
        p.setPhysicsEngineParameter(fixedTimeStep=dt, numSolverIterations=sq["solver_iterations"],
            contactBreakingThreshold=sq["contact_breaking_threshold_m"], contactSlop=sq["contact_slop_m"],
            restitutionVelocityThreshold=sq["restitution_velocity_threshold_m_per_s"],
            useSplitImpulse=int(sq["use_split_impulse"]),
            splitImpulsePenetrationThreshold=sq["split_impulse_penetration_threshold_m"],
            deterministicOverlappingPairs=1, enableConeFriction=1, physicsClientId=cid)
        label, geometry = {}, colliders(cfg)
        for c in geometry:
            vertices, _ = collider_mesh(c, sq["edge_arc_segments"])
            shape = p.createCollisionShape(p.GEOM_MESH, vertices=vertices, physicsClientId=cid)
            body = p.createMultiBody(0.0, shape, useMaximalCoordinates=True, physicsClientId=cid)
            p.changeDynamics(body, -1, restitution=stairs["restitution"], lateralFriction=stairs["lateral_friction"],
                contactProcessingThreshold=sq["contact_processing_threshold_m"],
                collisionMargin=sq["collision_margin_m"], physicsClientId=cid)
            label[body] = c["id"]
        sphere = p.createCollisionShape(p.GEOM_SPHERE, radius=r, physicsClientId=cid)
        b = p.createMultiBody(m, sphere, basePosition=ball["initial_position_m"],
                             baseOrientation=ball["initial_quaternion_xyzw"], useMaximalCoordinates=True, physicsClientId=cid)
        p.changeDynamics(b, -1, mass=m, restitution=ball["restitution"], lateralFriction=ball["lateral_friction"],
            rollingFriction=ball["rolling_friction"], spinningFriction=ball["spinning_friction"],
            linearDamping=ball["linear_damping"], angularDamping=ball["angular_damping"],
            localInertiaDiagonal=[inertia]*3, collisionMargin=0.0,
            contactProcessingThreshold=sq["contact_processing_threshold_m"],
            activationState=p.ACTIVATION_STATE_DISABLE_SLEEPING, physicsClientId=cid)
        # The ONLY resetBaseVelocity call in scene simulation. Never set poses or forces in the loop.
        p.resetBaseVelocity(b, ball["initial_velocity_m_per_s"], ball["initial_angular_velocity_rad_per_s"], physicsClientId=cid)
        actual_dynamics = p.getDynamicsInfo(b, -1, physicsClientId=cid)
        assert abs(actual_dynamics[0]-m)<1e-12 and all(abs(v-inertia)<1e-12 for v in actual_dynamics[2])
        p.performCollisionDetection(physicsClientId=cid)
        initial_clearances = {label[o]: min(q[8] for q in p.getClosestPoints(b,o,10,physicsClientId=cid)) for o in label}
        assert min(initial_clearances.values()) > 0, initial_clearances
        frames, samples, events, raw_contacts = [], [], [], []
        active, prev = {}, None
        max_penetration, max_energy_gain, max_flight_residual, max_gap_impulse = 0.0, 0.0, 0.0, 0.0
        max_speed, max_omega, floor_rolling_time = 0.0, 0.0, None
        resting_run = 0

        def pose(t):
            xyz, q = p.getBasePositionAndOrientation(b, physicsClientId=cid)
            v, w = p.getBaseVelocity(b, physicsClientId=cid)
            assert all(math.isfinite(x) for x in (*xyz,*q,*v,*w)), "Nonfinite solver state"
            energy = 0.5*m*sum(x*x for x in v) + 0.5*inertia*sum(x*x for x in w) + m*9.81*xyz[2]
            return {"time_sec": t, "location": list(xyz), "quaternion_xyzw": list(q),
                    "linear_velocity": list(v), "angular_velocity": list(w), "mechanical_energy_J": energy}

        for step in range(nframes*sub+1):
            t = step*dt
            if step:
                p.stepSimulation(physicsClientId=cid)
            state = pose(t)
            contacts = [cp for cp in p.getContactPoints(bodyA=b,physicsClientId=cid) if cp[9] > sq["contact_force_threshold_N"]]
            contact_ids = {label[cp[2]] for cp in contacts}
            max_speed = max(max_speed, norm(state["linear_velocity"]))
            max_omega = max(max_omega, norm(state["angular_velocity"]))
            if prev:
                max_energy_gain = max(max_energy_gain, state["mechanical_energy_J"]-prev["mechanical_energy_J"])
                if not contacts and not prev["contact_ids"]:
                    residual = norm([state["linear_velocity"][i]-prev["linear_velocity"][i]-ph["gravity"][i]*dt for i in range(3)])
                    max_flight_residual = max(max_flight_residual, residual)
            for cp in contacts:
                object_id = label[cp[2]]
                max_penetration = max(max_penetration, -cp[8])
                max_gap_impulse = max(max_gap_impulse, cp[8])
                if object_id not in active:
                    normal = list(cp[7])
                    pre_v = prev["linear_velocity"] if prev else state["linear_velocity"]
                    event = {"event_index": len(events), "collider_id": object_id, "time_sec": t,
                             "frame_float": t*fps+1, "position_on_static_m": list(cp[6]),
                             "ball_center_m": state["location"], "contact_normal": normal,
                             "surface": "tread" if normal[2] > .98 else "edge_or_riser",
                             "pre_linear_velocity": pre_v, "post_linear_velocity": state["linear_velocity"],
                             "pre_angular_velocity": prev["angular_velocity"] if prev else state["angular_velocity"],
                             "post_angular_velocity": state["angular_velocity"],
                             "pre_normal_speed_m_per_s": -sum(pre_v[i]*normal[i] for i in range(3)),
                             "post_normal_speed_m_per_s": sum(state["linear_velocity"][i]*normal[i] for i in range(3)),
                             "max_normal_force_N": 0.0, "normal_impulse_Ns": 0.0,
                             "initial_signed_gap_m": cp[8],
                             "min_signed_gap_m": cp[8], "max_signed_gap_m": cp[8],
                             "end_time_sec": t, "rebound_apex_center_z_m": state["location"][2],
                             "rebound_apex_time_sec": t, "rebound_apex_xy_m": state["location"][:2]}
                    events.append(event)
                    active[object_id] = event
                ev = active[object_id]
                ev["end_time_sec"] = t
                ev["max_normal_force_N"] = max(ev["max_normal_force_N"], cp[9])
                ev["normal_impulse_Ns"] += cp[9]*dt
                ev["min_signed_gap_m"] = min(ev["min_signed_gap_m"], cp[8])
                ev["max_signed_gap_m"] = max(ev["max_signed_gap_m"], cp[8])
                if record:
                    raw_contacts.append({"time_sec": t, "collider_id": object_id, "position_m": list(cp[6]),
                        "normal": list(cp[7]), "signed_gap_m": cp[8], "normal_force_N": cp[9]})
            for key in list(active):
                if key not in contact_ids:
                    del active[key]
            if events:
                ev = events[-1]
                if state["location"][2] > ev["rebound_apex_center_z_m"]:
                    ev.update(rebound_apex_center_z_m=state["location"][2], rebound_apex_time_sec=t,
                              rebound_apex_xy_m=state["location"][:2])
            if "lower_platform" in contact_ids and abs(state["linear_velocity"][2]) < 0.02 and abs(state["linear_velocity"][0]-r*state["angular_velocity"][1]) < 0.02:
                resting_run += 1
                if resting_run > round(.10/dt) and floor_rolling_time is None:
                    floor_rolling_time = t-resting_run*dt
            else:
                resting_run = 0
            state["contact_ids"] = sorted(contact_ids)
            if record and step % stride == 0:
                samples.append(state)
            if record and step % sub == 0 and step < nframes*sub:
                frames.append({"frame_index": step//sub+1, **state})
            prev = state
        by_id = {c["id"]:c for c in geometry}
        for i, ev in enumerate(events):
            ev["rebound_height_above_contact_m"] = max(0, ev["rebound_apex_center_z_m"]-ev["ball_center_m"][2])
            ev["rebound_height_above_tread_m"] = ev["rebound_apex_center_z_m"]-r-by_id[ev["collider_id"]]["zmax"]
            ev["next_landing"] = {k: events[i+1][k] for k in ("collider_id", "time_sec", "position_on_static_m")} if i+1<len(events) else None
            ev["major_impact"] = ev["pre_normal_speed_m_per_s"]>.2 and ev["post_normal_speed_m_per_s"]>.08
        main = [e for e in events if e["major_impact"]]
        return {"schema_version": 1, "scene": "stair_ball_bounce", "category": "rigid_rigid",
            "simulator": "PyBullet", "solver_version": importlib.metadata.version("pybullet"), "python_version": platform.python_version(),
            "configuration": cfg, "configuration_sha256": signature(cfg), "physics_dt": dt,
            "fps": fps, "frame_start": 1, "frame_end": nframes, "duration_sec": rd["duration_sec"],
            "colliders": geometry, "initial_clearance_m": initial_clearances,
            "inertia_kg_m2": [inertia]*3, "restitution_combination": "ball * stairs",
            "effective_restitution": ball["restitution"]*stairs["restitution"],
            "constraints": [], "external_forces": [], "prescribed_motion": False,
            "velocity_initialization_count": 1, "frames": frames, "trajectory_samples": samples,
            "contact_events": events, "raw_contacts": raw_contacts,
            "quality": {"max_penetration_m": max_penetration, "max_positive_contact_gap_m": max_gap_impulse,
                "max_single_step_energy_gain_J": max_energy_gain, "max_free_flight_velocity_residual_m_per_s": max_flight_residual,
                "max_speed_m_per_s": max_speed, "max_angular_speed_rad_per_s": max_omega,
                "major_contact_order": [e["collider_id"] for e in main],
                "lower_platform_rolling_start_sec": floor_rolling_time},
            "final_state": state, "simulation_wall_sec": time.perf_counter()-start}
    finally:
        p.disconnect(cid)

def export_csv(path, result):
    fields = ["time_sec", "x_m", "y_m", "z_m", "qx", "qy", "qz", "qw", "vx", "vy", "vz", "wx", "wy", "wz", "contact_ids"]
    with Path(path).open("w", newline="") as f:
        writer = csv.writer(f); writer.writerow(fields)
        for s in result["trajectory_samples"]:
            writer.writerow([s["time_sec"], *s["location"], *s["quaternion_xyzw"], *s["linear_velocity"], *s["angular_velocity"], ";".join(s["contact_ids"])])

def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--case", choices=SUPPORTED_CASES, default="source")
    a.add_argument("--scenario-overrides-json", type=Path)
    a.add_argument("--substeps", type=int)
    args = a.parse_args()
    cfg = scenario(json.loads(args.scenario_overrides_json.read_text()) if args.scenario_overrides_json else {}, case=args.case)
    if args.substeps:
        cfg["simulation_quality"]["substeps_per_frame"] = args.substeps
    result = simulate(cfg)
    write_json(args.out, result)
    export_csv(args.out.with_name("trajectory.csv"), result)
    write_json(args.out.with_name("contacts.json"), result["contact_events"])
    print(json.dumps({"output": str(args.out), "quality": result["quality"], "simulation_wall_sec": result["simulation_wall_sec"]}, indent=2))

if __name__ == "__main__":
    main()
