"""Free six-DOF PyBullet cascade; Blender only replays the solved poses.

Compatible per-tile list flags with the original domino_chain interface.
No constraints, external forces, scripted tipping, or prescribed velocities.
"""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END

import argparse
import copy
import hashlib
import importlib.metadata
import json
import math
import platform
import time
from pathlib import Path

# scene_spec.json is the single SI-unit source of truth for the five-tile card-table scene.
SPEC = json.loads((Path(__file__).resolve().parent / "scene_spec.json").read_text())
BASELINE_PHYSICS = SPEC["physics"]
SIMULATION_QUALITY = SPEC["simulation_quality"]
APPEARANCE = SPEC["appearance"]
RENDER = SPEC["render"]


def merge(base, updates):
    result = copy.deepcopy(base)
    for key, value in updates.items():
        if key not in result:
            raise ValueError(f"Unknown configuration key: {key}")
        if isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def scenario(overrides=None):
    cfg = {"physics": copy.deepcopy(BASELINE_PHYSICS),
           "simulation_quality": copy.deepcopy(SIMULATION_QUALITY),
           "appearance": copy.deepcopy(APPEARANCE), "render": copy.deepcopy(RENDER)}
    updates = copy.deepcopy(overrides or {})
    timed = updates.get("physics", {}).pop("timed_edits", None)
    cfg = merge(cfg, updates)
    if timed is not None:
        cfg["physics"]["timed_edits"] = timed
    return cfg


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def differences(before, after, prefix=""):
    if isinstance(before, dict) and isinstance(after, dict):
        out = {}
        for key in sorted(before.keys() | after.keys()):
            out.update(differences(before.get(key), after.get(key), f"{prefix}.{key}".strip(".")))
        return out
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        out = {}
        for index, (old, new) in enumerate(zip(before, after)):
            out.update(differences(old, new, f"{prefix}.{index}"))
        return out
    return {} if before == after else {prefix: {"from": before, "to": after}}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def simulate(cfg, *, record_frames=True):
    import pybullet as p
    begin = time.perf_counter()
    ph, sq, render = (cfg[k] for k in ("physics", "simulation_quality", "render"))
    count = ph["domino_count"]
    assert count == 5, "The public scene has exactly D01--D05."
    for key in ("domino_masses", "domino_frictions", "domino_restitutions", "domino_active"):
        assert len(ph[key]) == count
    assert all(m > 0 for m in ph["domino_masses"]), "No fixed/zero-mass dominoes."
    assert all(f >= 0 for f in ph["domino_frictions"])
    fps = int(render["fps"])
    frame_end = round(render["duration_sec"] * fps)
    assert abs(frame_end - render["duration_sec"] * fps) < 1e-8
    substeps = int(sq["substeps_per_frame"])
    dt = 1.0 / (fps * substeps)
    scheduled = {}
    for edit in ph.get("timed_edits", []):
        frame = int(edit["frame"])
        if not 2 <= frame <= frame_end:
            raise ValueError("Timed removals must occur after frame 1 and within the clip")
        params = edit["params"]
        if set(params) != {"domino_active"} or len(params["domino_active"]) != count:
            raise ValueError("This scene supports timed presence removal only")
        if any(v not in (0, 1) for v in params["domino_active"]):
            raise ValueError("Presence values must be 0 or 1")
        scheduled.setdefault((frame - 1) * substeps, []).append(edit)
    sample_every = max(1, round(1.0 / (240.0 * dt)))
    thick, width, height = (ph["domino_" + k] for k in ("thickness", "width", "height"))
    spacing, floor_z = ph["domino_spacing"], ph["floor_z"]
    critical = math.degrees(math.atan(thick / height))
    theta = math.radians(ph["push_angle_deg"])
    assert ph["push_angle_deg"] > critical
    initial_locations, initial_orientations = [], []
    for i in range(count):
        x = (i - (count - 1) / 2) * spacing
        if i == 0:
            # Rotate about the front bottom edge, preserving exact table contact.
            initial_locations.append([x + thick/2 - thick/2*math.cos(theta) + height/2*math.sin(theta),
                                      0.0, floor_z + thick/2*math.sin(theta) + height/2*math.cos(theta)])
            initial_orientations.append(p.getQuaternionFromEuler([0, theta, 0]))
        else:
            initial_locations.append([x, 0.0, floor_z + height/2])
            initial_orientations.append([0, 0, 0, 1])

    client = p.connect(p.DIRECT)
    try:
        p.resetSimulation(physicsClientId=client)
        p.setGravity(*ph["gravity"], physicsClientId=client)
        p.setTimeStep(dt, physicsClientId=client)
        p.setPhysicsEngineParameter(
            fixedTimeStep=dt, numSolverIterations=sq["solver_iterations"],
            contactBreakingThreshold=sq["contact_breaking_threshold_m"],
            contactSlop=sq["contact_slop_m"],
            restitutionVelocityThreshold=sq["restitution_velocity_threshold_m_per_s"],
            deterministicOverlappingPairs=1, enableConeFriction=1, physicsClientId=client)
        floor_shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.6, 0.325, 0.014], physicsClientId=client)
        floor = p.createMultiBody(0, floor_shape, -1, [0, 0, floor_z-0.014], physicsClientId=client)
        p.changeDynamics(floor, -1, lateralFriction=ph["floor_friction"],
                         restitution=ph["floor_restitution"], collisionMargin=sq["collision_margin_m"], physicsClientId=client)
        shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=[thick/2, width/2, height/2], physicsClientId=client)
        bodies, labels = [], {floor: "desk"}
        for i in range(count):
            if not ph["domino_active"][i]:
                bodies.append(None)
                continue
            body = p.createMultiBody(ph["domino_masses"][i], shape, -1,
                                     initial_locations[i], initial_orientations[i], physicsClientId=client)
            p.changeDynamics(body, -1, lateralFriction=ph["domino_frictions"][i],
                             restitution=ph["domino_restitutions"][i],
                             linearDamping=ph["linear_damping"], angularDamping=ph["angular_damping"],
                             spinningFriction=0.0, rollingFriction=0.0,
                             collisionMargin=sq["collision_margin_m"], physicsClientId=client)
            bodies.append(body)
            labels[body] = f"D{i+1:02}"

        # Query geometry at t=0 independently of the first dynamic step.
        p.performCollisionDetection(physicsClientId=client)
        initial_contacts = [list(cp[8:10]) for cp in p.getContactPoints(physicsClientId=client)]
        initial_pair_clearance = {}
        for i in range(count):
            for j in range(i+1, count):
                if bodies[i] is not None and bodies[j] is not None:
                    points = p.getClosestPoints(bodies[i], bodies[j], distance=0.2, physicsClientId=client)
                    initial_pair_clearance[f"D{i+1:02}-D{j+1:02}"] = min(cp[8] for cp in points)
        assert all(v > 0 for v in initial_pair_clearance.values())

        trajectory_samples = []
        contacts, events, frames = {}, {f"D{i+1:02}": {} for i in range(count)}, []
        max_tilt, max_speed, max_base_slide = [0.0]*count, [0.0]*count, [0.0]*count
        final, tail_speeds, max_penetration = None, [], 0.0
        worst_contact = None
        interventions = []
        min_d02_d04_gap = math.inf
        tail_bounds = [[math.inf]*4+[-math.inf]*4 for _ in range(count)]

        def poses(t):
            result = []
            for i, body in enumerate(bodies):
                if body is None:
                    result.append({"object_id": f"D{i+1:02}", "present": False,
                                   "location": initial_locations[i], "quaternion_xyzw": initial_orientations[i],
                                   "linear_velocity": [0.0]*3, "angular_velocity": [0.0]*3, "tilt_deg": 0.0})
                    continue
                loc, quat = p.getBasePositionAndOrientation(body, physicsClientId=client)
                vel, omega = p.getBaseVelocity(body, physicsClientId=client)
                r = p.getMatrixFromQuaternion(quat)
                tilt = math.degrees(math.acos(max(-1, min(1, r[8]))))
                max_tilt[i] = max(max_tilt[i], tilt)
                max_speed[i] = max(max_speed[i], norm(vel))
                ev = events[f"D{i+1:02}"]
                for threshold in [0.5, 2, critical, 45, 80]:
                    if tilt >= threshold and str(threshold) not in ev:
                        ev[str(threshold)] = t
                if tilt < 45:
                    edge_x = loc[0] + r[0]*thick/2 - r[2]*height/2
                    edge_y = loc[1] + r[3]*thick/2 - r[5]*height/2
                    initial_edge_x = (i-(count-1)/2)*spacing + thick/2
                    max_base_slide[i] = max(max_base_slide[i], math.hypot(edge_x-initial_edge_x, edge_y))
                result.append({"object_id": f"D{i+1:02}", "present": True,
                               "location": list(loc), "quaternion_xyzw": list(quat),
                               "linear_velocity": list(vel), "angular_velocity": list(omega), "tilt_deg": tilt})
            return result

        step_count = (frame_end-1)*substeps
        for step in range(step_count+1):
            t = step*dt
            if step:
                p.stepSimulation(physicsClientId=client)
                for cp in p.getContactPoints(physicsClientId=client):
                    if -cp[8] > max_penetration:
                        max_penetration = -cp[8]
                        worst_contact = {"time_sec": t, "objects": [labels[cp[1]], labels[cp[2]]],
                                         "penetration_m": -cp[8]}
                    if cp[9] <= 1e-7:
                        continue
                    a, b = sorted([labels[cp[1]], labels[cp[2]]])
                    pair = f"{a}-{b}"
                    if pair not in contacts:
                        contacts[pair] = {"objects": [a, b], "first_time_sec": t,
                                          "first_position_on_b_m": list(cp[6]), "max_normal_force_N": 0.0}
                    contacts[pair]["last_time_sec"] = t
                    contacts[pair]["max_normal_force_N"] = max(contacts[pair]["max_normal_force_N"], cp[9])
            for edit in scheduled.get(step, []):
                for i, active in enumerate(edit["params"]["domino_active"]):
                    if active and bodies[i] is None:
                        raise ValueError("A timed removal cannot re-add a deleted domino")
                    if not active and bodies[i] is not None:
                        body = bodies[i]
                        location, quaternion = p.getBasePositionAndOrientation(body, physicsClientId=client)
                        velocity, omega = p.getBaseVelocity(body, physicsClientId=client)
                        interventions.append({"kind": "DELETE", "object_id": f"D{i+1:02}",
                                              "frame_index": int(edit["frame"]), "time_sec": t,
                                              "state_before_removal": {"location": list(location), "quaternion_xyzw": list(quaternion),
                                                                       "linear_velocity": list(velocity), "angular_velocity": list(omega)}})
                        p.removeBody(body, physicsClientId=client)
                        bodies[i] = None
            current = poses(t)
            if bodies[1] is not None and bodies[3] is not None and not ph["domino_active"][2]:
                points = p.getClosestPoints(bodies[1], bodies[3], distance=0.2, physicsClientId=client)
                if points:
                    min_d02_d04_gap = min(min_d02_d04_gap, min(cp[8] for cp in points))
            if t >= (frame_end-1)/fps - 0.5:
                tail_speeds.append(max((norm(v["linear_velocity"])+height*norm(v["angular_velocity"]) for v in current if v["present"]), default=0))
                for i, v in enumerate(current):
                    if not v["present"]:
                        continue
                    values = v["location"] + [v["tilt_deg"]]
                    for k, value in enumerate(values):
                        tail_bounds[i][k] = min(tail_bounds[i][k], value)
                        tail_bounds[i][k+4] = max(tail_bounds[i][k+4], value)
            if record_frames and step % sample_every == 0:
                trajectory_samples.append({"frame_index": step/substeps+1, "time_sec":t, "dominoes":current})
            if step % substeps == 0 and record_frames:
                frames.append({"frame_index": step//substeps+1, "time_sec": t, "dominoes": current})
            final = current

        domino_contacts = sorted([c for c in contacts.values() if "desk" not in c["objects"]], key=lambda c: c["first_time_sec"])
        early = []
        for i in range(1, count):
            if bodies[i] is None:
                continue
            received = min((c["first_time_sec"] for c in domino_contacts if f"D{i+1:02}" in c["objects"]), default=math.inf)
            onset = events[f"D{i+1:02}"].get("0.5", math.inf)
            if onset < received-dt:
                early.append(f"D{i+1:02}")
        q = {"max_tilt_deg_per_domino": max_tilt,
             "final_tilt_deg_per_domino": [v["tilt_deg"] if v["present"] else None for v in final],
             "toppled_count": sum(tilt > 45 and bool(ph["domino_active"][i]) for i, tilt in enumerate(max_tilt)),
             "max_linear_speed_m_per_s": max_speed, "base_slide_before_45deg_m": max_base_slide,
             "max_penetration_m": max_penetration,
             "worst_contact": worst_contact,
             "tail_max_equivalent_speed_m_per_s": max(tail_speeds),
              "tail_position_range_m": [math.sqrt(sum((b[k+4]-b[k])**2 for k in range(3))) if final[i]["present"] else 0 for i,b in enumerate(tail_bounds)],
              "tail_tilt_range_deg": [b[7]-b[3] if final[i]["present"] else 0 for i,b in enumerate(tail_bounds)],
             "premature_tipping_ids": early,
             "min_D02_D04_clearance_m": None if math.isinf(min_d02_d04_gap) else min_d02_d04_gap}
        result = {"schema_version": 3, "simulator": "pybullet", "solver_version": importlib.metadata.version("pybullet"),
                "python_version": platform.python_version(), "platform": platform.platform(),
                "configuration": cfg, "configuration_sha256": signature(cfg),
                "fps": fps, "frame_start": 1, "frame_end": frame_end,
                "duration_sec": render["duration_sec"], "physics_dt": dt,
                "critical_angle_deg": critical, "initial_locations": initial_locations,
                "initial_orientations_xyzw": initial_orientations,
                "initial_pair_clearance_m": initial_pair_clearance,
                "initial_max_penetration_m": max([-c[0] for c in initial_contacts]+[0.0]),
                "initial_linear_velocities": [[0.0]*3 for _ in bodies],
                "initial_angular_velocities": [[0.0]*3 for _ in bodies],
                "constraints": [], "external_forces": [], "prescribed_motion": False,
                "contact_events": domino_contacts, "all_contacts": contacts,
                "tilt_threshold_times_sec": events, "quality": q,
                "final_state": final, "frames": frames, "trajectory_samples": trajectory_samples, "simulation_wall_sec": time.perf_counter()-begin}
        if interventions:
            result["interventions"] = interventions
        return result
    finally:
        p.disconnect(client)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenario-overrides-json", type=Path)
    parser.add_argument("--fps", type=int)
    parser.add_argument("--duration-sec", type=float)
    parser.add_argument("--substeps", type=int)
    parser.add_argument("--domino-count", type=int)
    parser.add_argument("--domino-spacing", type=float)
    parser.add_argument("--domino-thickness", type=float)
    parser.add_argument("--domino-width", type=float)
    parser.add_argument("--domino-height", type=float)
    parser.add_argument("--domino-mass", type=float)
    parser.add_argument("--domino-friction", type=float)
    parser.add_argument("--domino-restitution", type=float)
    parser.add_argument("--floor-friction", type=float)
    parser.add_argument("--push-angle-deg", type=float)
    parser.add_argument("--domino-masses", nargs="+", type=float)
    parser.add_argument("--domino-frictions-list", nargs="+", type=float)
    parser.add_argument("--domino-restitutions-list", nargs="+", type=float)
    parser.add_argument("--domino-active", nargs="+", type=int)
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = scenario(json.loads(args.scenario_overrides_json.read_text()) if args.scenario_overrides_json else None)
    for key in ("fps", "duration_sec"):
        if getattr(args, key) is not None:
            cfg["render"][key] = getattr(args, key)
    if args.substeps is not None:
        cfg["simulation_quality"]["substeps_per_frame"] = args.substeps
    for key in ("domino_count", "domino_spacing", "domino_thickness", "domino_width", "domino_height", "floor_friction", "push_angle_deg", "domino_masses", "domino_active"):
        if getattr(args, key) is not None:
            cfg["physics"][key] = getattr(args, key)
    for scalar, plural in [("mass", "masses"), ("friction", "frictions"), ("restitution", "restitutions")]:
        val = getattr(args, "domino_"+scalar)
        if val is not None:
            cfg["physics"]["domino_"+plural] = [val]*5
    for singular, key in [("frictions", "domino_frictions_list"), ("restitutions", "domino_restitutions_list")]:
        if getattr(args, key) is not None:
            cfg["physics"]["domino_"+singular] = getattr(args, key)
    result = simulate(cfg)
    write_json(args.out, result)
    print(json.dumps(result["quality"], ensure_ascii=False))


if __name__ == "__main__":
    main()
