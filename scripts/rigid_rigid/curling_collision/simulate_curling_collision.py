"""Solve constrained rigid contacts, without authored impact times or motion curves."""
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
import bisect
import csv
import json
import math
from pathlib import Path
import platform
import time
from scene_config import SCENE, scenario, signature

SOLVER_VERSION = "pcve-exact-1d-impulse/1.1"

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n")

def positive_contact_root(gap, relative_v, relative_a, eps):
    """First future closing contact in the current constant-acceleration interval."""
    if abs(relative_a) < eps:
        return -gap/relative_v if relative_v < -eps and gap > eps else math.inf
    discriminant = relative_v*relative_v-2*relative_a*gap
    if discriminant < 0:
        return math.inf
    roots = [(-relative_v-s*math.sqrt(max(0, discriminant)))/relative_a for s in [1, -1]]
    return min((r for r in roots if r > eps and relative_v+relative_a*r < -eps), default=math.inf)

def simulate(cfg, case_id="source"):
    begin = time.perf_counter()
    ph, sq, rd = (cfg[k] for k in ["physics", "simulation_quality", "render"])
    ids, masses = ph["object_ids"], ph["mass_kg"]
    diameter, deceleration = 2*ph["radius_m"], ph["gravity_m_per_s2"]*ph["ice_kinetic_friction"]
    eps, duration = sq["event_time_tolerance_sec"], rd["duration_sec"]
    x, v, t = list(ph["initial_x_m"]), list(ph["initial_velocity_m_per_s"]), 0.0
    segments, events, stops = [], [], []
    count = len(ids)
    while t < duration-eps:
        # Coulomb friction always opposes motion.  Source trajectories move
        # only to +X, but a light striker can rebound from a heavier target;
        # signed friction keeps that counterfactual physical and finite.
        a = [-math.copysign(deceleration,s) if abs(s) > eps else 0.0 for s in v]
        candidates = [(duration-t, "end", None)]
        candidates += [(abs(v[i])/deceleration, "stop", i) for i in range(count) if abs(v[i]) > eps]
        for i in range(count-1):
            gap = x[i+1]-x[i]-diameter
            hit = positive_contact_root(gap, v[i+1]-v[i], a[i+1]-a[i], eps)
            candidates.append((hit, "collision", i))
        h, kind, index = min(candidates, key=lambda q:q[0])
        segments.append({"start_sec":t, "end_sec":t+h, "x_m":x[:], "vx_m_per_s":v[:], "ax_m_per_s2":a[:]})
        x = [x[i]+v[i]*h+0.5*a[i]*h*h for i in range(count)]
        v = [v[i]+a[i]*h for i in range(count)]
        t += h
        if kind == "stop":
            v[index] = 0.0
            stops.append({"object_id":ids[index], "time_sec":t, "x_m":x[index]})
        elif kind == "collision":
            i, j = index, index+1
            before = v[:]
            impulse = (1+ph["stone_pair_restitution"])*(v[i]-v[j])/(1/masses[i]+1/masses[j])
            v[i] -= impulse/masses[i]
            v[j] += impulse/masses[j]
            p0 = masses[i]*before[i]+masses[j]*before[j]
            p1 = masses[i]*v[i]+masses[j]*v[j]
            ke0 = 0.5*(masses[i]*before[i]**2+masses[j]*before[j]**2)
            ke1 = 0.5*(masses[i]*v[i]**2+masses[j]*v[j]**2)
            events.append({"event_index":len(events)+1, "object_ids":[ids[i],ids[j]],
                "time_sec":t, "frame_float":1+t*rd["fps"],
                "contact_position_m":[x[i]+ph["radius_m"],ph["track_y_m"],ph["com_height_m"]],
                "signed_gap_m":x[j]-x[i]-diameter, "normal_impulse_Ns":impulse,
                "pre_velocity_m_per_s":{ids[k]:before[k] for k in range(count)},
                "post_velocity_m_per_s":{ids[k]:v[k] for k in range(count)},
                "momentum_before_kg_m_per_s":p0, "momentum_after_kg_m_per_s":p1,
                "kinetic_energy_before_J":ke0, "kinetic_energy_after_J":ke1,
                "energy_dissipated_J":ke0-ke1,
                "measured_restitution":(v[j]-v[i])/(before[i]-before[j])})
        if len(events)+len(stops) > sq["maximum_events"]:
            raise RuntimeError("Event budget exceeded")
    starts = [s["start_sec"] for s in segments]
    def sample(at):
        seg = segments[min(len(segments)-1,bisect.bisect_right(starts,at+eps)-1)]
        elapsed = at-seg["start_sec"]
        bodies = {}
        for i, name in enumerate(ids):
            px = seg["x_m"][i]+seg["vx_m_per_s"][i]*elapsed+0.5*seg["ax_m_per_s2"][i]*elapsed*elapsed
            speed = seg["vx_m_per_s"][i]+seg["ax_m_per_s2"][i]*elapsed
            if abs(speed) < eps:
                speed = 0.0
            bodies[name] = {"location":[px,ph["track_y_m"],ph["com_height_m"]],
                "quaternion_xyzw":[0.0,0.0,0.0,1.0],"linear_velocity":[speed,0.0,0.0],
                "angular_velocity":[0.0,0.0,0.0], "bottom_clearance_m":0.0}
        return {"time_sec":at, "bodies":bodies,
            "kinetic_energy_J":sum(0.5*masses[i]*bodies[name]["linear_velocity"][0]**2 for i,name in enumerate(ids))}
    times = {i/sq["trajectory_hz"] for i in range(round(duration*sq["trajectory_hz"])+1)}
    times.update(e["time_sec"] for e in events)
    times.update(e["time_sec"] for e in stops)
    samples = [sample(at) for at in sorted(times)]
    frames = [{"frame_index":i+1,**sample(i/rd["fps"])} for i in range(rd["total_frames"])]
    return {"schema_version":1, "scene":SCENE, "category":"rigid_rigid", "case_id":case_id,
        "simulator":"Exact event-driven constrained rigid-body impulse solver", "solver_version":SOLVER_VERSION,
        "python_version":platform.python_version(),"configuration":cfg,"configuration_sha256":signature(cfg),
        "fps":rd["fps"],"frame_start":1,"frame_end":rd["total_frames"],"duration_sec":duration,
        "sample_time_convention":"frame f samples t=(f-1)/fps; 96 frame exposures encode exactly 4 seconds",
        "prescribed_motion":False,"authored_collision_times":False,
        "constraints":[{"object_id":name,"allowed_dof":["translation_x"],"locked_dof":["translation_y","translation_z","rotation_x","rotation_y","rotation_z"]} for name in ids],
        "force_model":{"gravity_normal_balance":True,"kinetic_friction_deceleration_m_per_s2":deceleration,"air_drag":False},
        "velocity_initialization_count":1,"contact_events":events,"stop_events":stops,
        "analytic_segments":segments,"frames":frames,"trajectory_samples":samples,
        "final_state":sample(duration),"simulation_wall_sec":time.perf_counter()-begin}

def export_csv(path, result):
    with Path(path).open("w",newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["time_sec","object_id","x_m","y_m","z_m","vx_m_per_s","vy_m_per_s","vz_m_per_s","qx","qy","qz","qw"])
        for s in result["trajectory_samples"]:
            for name,b in s["bodies"].items():
                writer.writerow([s["time_sec"],name,*b["location"],*b["linear_velocity"],*b["quaternion_xyzw"]])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--config-json",type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    result = simulate(scenario(json.loads(args.config_json.read_text()) if args.config_json else None))
    write_json(args.out,result)
    export_csv(args.out.with_name("trajectory.csv"),result)
    write_json(args.out.with_name("contacts.json"),result["contact_events"])
    from physics.validate_curling_collision import validate
    report = validate(result)
    write_json(args.out.with_name("physics_validation.json"),report)
    print(json.dumps(report,indent=2))
    if not report["accepted"]:
        raise RuntimeError(report)

if __name__ == "__main__":
    main()
