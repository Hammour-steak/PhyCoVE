"""Solve actual sphere/floor rigid contacts and export poses and collision evidence."""
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
from scene_config import SCENE, CASES, scenario, signature

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

def simulate(cfg):
    import pybullet as p
    start = time.perf_counter()
    ph, sq, rd = (cfg[k] for k in ("physics", "simulation_quality", "render"))
    ball, floor = ph["ball"], ph["floor"]
    sub, fps, count = sq["substeps_per_frame"], rd["fps"], rd["total_frames"]
    dt = 1.0 / (fps * sub)
    stride = max(1, round(1.0 / (dt * sq["trajectory_hz"])))
    radius, mass = ball["radius_m"], ball["mass_kg"]
    inertia = ball["inertia_factor"] * mass * radius * radius
    cid = p.connect(p.DIRECT)
    try:
        p.setGravity(*ph["gravity"], physicsClientId=cid)
        p.setTimeStep(dt, physicsClientId=cid)
        p.setPhysicsEngineParameter(fixedTimeStep=dt, numSolverIterations=sq["solver_iterations"],
            contactSlop=sq["contact_slop_m"], contactBreakingThreshold=sq["contact_breaking_threshold_m"],
            restitutionVelocityThreshold=sq["restitution_velocity_threshold_m_per_s"],
            useSplitImpulse=int(sq["use_split_impulse"]),
            splitImpulsePenetrationThreshold=sq["split_impulse_penetration_threshold_m"],
            contactERP=sq["contact_erp"],
            deterministicOverlappingPairs=1,
            physicsClientId=cid)
        half = [v / 2 for v in floor["dimensions_m"]]
        fshape = p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid)
        ground = p.createMultiBody(0.0, fshape, basePosition=[0, 0, floor["top_z_m"] - half[2]], physicsClientId=cid)
        p.changeDynamics(ground, -1, restitution=floor["restitution"], lateralFriction=floor["lateral_friction"],
                         rollingFriction=0.0, spinningFriction=0.0, physicsClientId=cid)
        if not ball.get("present",True):
            frames=[]
            for step in range(count*sub+1):
                if step:p.stepSimulation(physicsClientId=cid)
                if step%sub==0 and step<count*sub:
                    frames.append({"frame_index":step//sub+1,"time_sec":step*dt,"object_present":False,"objects":[]})
            return {"schema_version":1,"scene":SCENE,"category":"rigid_rigid","case_id":"remove_ball",
                "simulator":"PyBullet","solver_version":importlib.metadata.version("pybullet"),"python_version":platform.python_version(),
                "configuration":cfg,"configuration_sha256":signature(cfg),"physics_dt_sec":dt,"fps":fps,"frame_start":1,"frame_end":count,
                "duration_sec":rd["duration_sec"],"sample_time_convention":"frame f samples t=(f-1)/fps; 96 frame exposures encode 4 seconds",
                "prescribed_motion":False,"constraints":[],"external_forces":[],"velocity_initialization_count":0,
                "actual_body_count":p.getNumBodies(physicsClientId=cid),"dynamic_body_count":0,
                "actual_ball_mass_kg":None,"actual_ball_inertia_kg_m2":None,"effective_restitution":None,
                "frames":frames,"trajectory_samples":[],"contact_events":[],
                "applied_edits":[{"operation":"delete","object_id":"B01","frame":1,"time_sec":0.0,"body_created":False}],
                "quality":{"minimum_bottom_clearance_m":None,"maximum_free_flight_velocity_residual_m_per_s":None,"maximum_horizontal_drift_m":None},
                "final_state":{"time_sec":count*sub*dt,"objects":[]},"simulation_wall_sec":time.perf_counter()-start}
        shape = p.createCollisionShape(p.GEOM_SPHERE, radius=radius, physicsClientId=cid)
        q = ball["initial_quaternion_xyzw"]
        q = [v / math.sqrt(sum(a*a for a in q)) for v in q]
        body = p.createMultiBody(mass, shape, basePosition=ball["initial_position_m"], baseOrientation=q,
                                useMaximalCoordinates=True, physicsClientId=cid)
        p.changeDynamics(body, -1, mass=mass, localInertiaDiagonal=[inertia]*3,
            restitution=ball["restitution"], lateralFriction=ball["lateral_friction"],
            rollingFriction=ball["rolling_friction"], spinningFriction=ball["spinning_friction"],
            linearDamping=ball["linear_damping"], angularDamping=ball["angular_damping"],
            collisionMargin=0.0, activationState=p.ACTIVATION_STATE_DISABLE_SLEEPING, physicsClientId=cid)
        p.resetBaseVelocity(body, ball["initial_velocity_m_per_s"],
                            ball["initial_angular_velocity_rad_per_s"], physicsClientId=cid)
        actual = p.getDynamicsInfo(body, -1, physicsClientId=cid)
        samples, frames, events = [], [], []
        applied_edits=[]
        commanded_restitution=ball["restitution"]
        schedule={}
        for edit in ph.get("timed_edits",[]):
            frame=edit["frame"];params=edit["params"]
            if not isinstance(frame,int) or not 2<=frame<=count or set(params)!={"ball_restitution"}:
                raise ValueError("Only in-clip timed restitution edits are supported")
            if not 0<=params["ball_restitution"]<=1:raise ValueError("Restitution must be in [0,1]")
            at_step=(frame-1)*sub
            if at_step in schedule:raise ValueError("Duplicate timed edit step")
            schedule[at_step]=edit
        def native_state():
            xyz,q=p.getBasePositionAndOrientation(body,physicsClientId=cid)
            v,w=p.getBaseVelocity(body,physicsClientId=cid)
            return {"location":list(xyz),"quaternion_xyzw":list(q),"linear_velocity":list(v),"angular_velocity":list(w)}
        previous = None
        was_touching = False
        max_flight_residual = 0.0
        min_clearance = float("inf")
        for step in range(count * sub + 1):
            if step:
                p.stepSimulation(physicsClientId=cid)
            t = step * dt
            if step in schedule:
                edit=schedule[step];before=native_state()
                old_restitution=commanded_restitution
                native_query_before=p.getDynamicsInfo(body,-1,physicsClientId=cid)[5]
                p.changeDynamics(body,-1,restitution=edit["params"]["ball_restitution"],physicsClientId=cid)
                commanded_restitution=edit["params"]["ball_restitution"]
                applied_edits.append({"object_id":ball["id"],"frame":edit["frame"],"time_sec":t,"solver_step":step,
                    "commanded_before_restitution":old_restitution,"commanded_after_restitution":commanded_restitution,
                    "native_restitution_query_before":native_query_before,"native_restitution_query_after":p.getDynamicsInfo(body,-1,physicsClientId=cid)[5],
                    "native_restitution_query_note":"PyBullet 3.2.7 maximal-coordinate getDynamicsInfo returns zero here; verify actual restitution from post-edit contact velocities.",
                    "state_before":before,"state_after":native_state(),"velocity_or_pose_reset":False})
            xyz, orientation = p.getBasePositionAndOrientation(body, physicsClientId=cid)
            v, w = p.getBaseVelocity(body, physicsClientId=cid)
            contacts = [c for c in p.getContactPoints(bodyA=body, bodyB=ground, physicsClientId=cid) if c[9] > 0.01]
            touching = bool(contacts)
            clear = xyz[2] - radius - floor["top_z_m"]
            min_clearance = min(min_clearance, clear)
            state = {"time_sec": t, "location": list(xyz), "quaternion_xyzw": list(orientation),
                     "linear_velocity": list(v), "angular_velocity": list(w),
                     "bottom_clearance_m": clear, "contact": touching,
                     "mechanical_energy_J": mass * -ph["gravity"][2] * (xyz[2] - radius - floor["top_z_m"])
                           + 0.5 * mass * sum(a*a for a in v) + 0.5 * inertia * sum(a*a for a in w)}
            if not all(math.isfinite(a) for a in (*xyz, *v, *w, *orientation)):
                raise RuntimeError("Nonfinite rigid-body state")
            if previous and not touching and not was_touching:
                residual = max(abs(v[i] - previous["linear_velocity"][i] - ph["gravity"][i]*dt) for i in range(3))
                max_flight_residual = max(max_flight_residual, residual)
            if touching and not was_touching:
                cp = contacts[0]
                pre = previous["linear_velocity"] if previous else v
                events.append({"event_index": len(events)+1, "object_ids": [ball["id"], floor["id"]],
                    "time_sec": t, "frame_float": 1+t*fps, "contact_position_m": list(cp[6]),
                    "contact_normal": list(cp[7]), "signed_gap_m": cp[8],
                    "pre_velocity_m_per_s": list(pre), "post_velocity_m_per_s": list(v),
                    "measured_restitution": v[2]/(-pre[2]) if pre[2] < -0.01 else None,
                    "major_impact": pre[2] < -0.15 and v[2] > 0.06,
                    "normal_impulse_Ns": 0.0, "apex_bottom_height_m": max(0.0, clear), "apex_time_sec": t})
            if events:
                event = events[-1]
                if touching:
                    event["normal_impulse_Ns"] += sum(c[9] for c in contacts)*dt
                if clear > event["apex_bottom_height_m"]:
                    event.update(apex_bottom_height_m=clear, apex_time_sec=t)
            if step % stride == 0:
                samples.append(state)
            if step % sub == 0 and step < count*sub:
                frames.append({"frame_index": step//sub+1, **state})
            previous, was_touching = state, touching
        for i, e in enumerate(events):
            e["next_contact_time_sec"] = events[i+1]["time_sec"] if i+1 < len(events) else None
            e["complete_rebound"] = e["next_contact_time_sec"] is not None
            e["contact_interval_sec"] = e["next_contact_time_sec"]-e["time_sec"] if e["next_contact_time_sec"] else None
        return {"schema_version": 1, "scene": SCENE, "category": "rigid_rigid", "case_id": "source",
            "simulator": "PyBullet", "solver_version": importlib.metadata.version("pybullet"),
            "python_version": platform.python_version(), "configuration": cfg, "configuration_sha256": signature(cfg),
            "physics_dt_sec": dt, "fps": fps, "frame_start": 1, "frame_end": count,
            "duration_sec": rd["duration_sec"], "sample_time_convention": "frame f samples t=(f-1)/fps; 96 frame exposures encode 4 seconds",
            "prescribed_motion": False, "constraints": [], "external_forces": [], "velocity_initialization_count": 1,
            "restitution_combination": "e_contact = e_B01 * e_F01; F01=1 normalizes the aggregate collision coefficient",
            "effective_restitution": ball["restitution"] * floor["restitution"],
            "applied_edits":applied_edits,
            "actual_body_count":p.getNumBodies(physicsClientId=cid),"dynamic_body_count":1,
            "final_commanded_effective_restitution":commanded_restitution*floor["restitution"],
            "actual_ball_mass_kg": actual[0], "actual_ball_inertia_kg_m2": list(actual[2]),
            "frames": frames, "trajectory_samples": samples, "contact_events": events,
            "quality": {"minimum_bottom_clearance_m": min_clearance,
                        "maximum_free_flight_velocity_residual_m_per_s": max_flight_residual,
                        "maximum_horizontal_drift_m": max(math.dist(s["location"][:2], ball["initial_position_m"][:2]) for s in samples)},
            "final_state": state, "simulation_wall_sec": time.perf_counter()-start}
    finally:
        p.disconnect(cid)

def export_csv(path, result):
    with Path(path).open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_sec", "x_m", "y_m", "z_m", "vx_m_per_s", "vy_m_per_s", "vz_m_per_s", "bottom_clearance_m", "mechanical_energy_J", "contact"])
        for s in result["trajectory_samples"]:
            writer.writerow([s["time_sec"], *s["location"], *s["linear_velocity"], s["bottom_clearance_m"], s["mechanical_energy_J"], s["contact"]])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config-json", type=Path)
    parser.add_argument("--case",choices=list(CASES),default="source")
    args = parser.parse_args()
    cfg = scenario(json.loads(args.config_json.read_text()) if args.config_json else None,case=args.case)
    if args.out.exists():
        raise FileExistsError(f"Refusing to replace physics: {args.out}")
    result = simulate(cfg)
    result["case_id"] = args.case
    write_json(args.out, result)
    export_csv(args.out.with_name("trajectory.csv"), result)
    write_json(args.out.with_name("contacts.json"), result["contact_events"])
    from physics.validate_basketball_court_bounce import validate
    report = validate(result,args.case)
    write_json(args.out.with_name("physics_validation.json"), report)
    if not report["accepted"]:
        raise RuntimeError(report)
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
