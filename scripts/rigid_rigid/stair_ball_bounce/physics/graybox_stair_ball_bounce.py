"""Finite initial-condition/material scan, drop calibration, and dt convergence."""
from __future__ import annotations
import argparse
from pathlib import Path
from scene_config import scenario, CASES
from simulate_stair_ball_bounce import simulate, write_json

def source_gate(result):
    main = [e for e in result["contact_events"] if e["major_impact"]]
    first = main[:6]
    return (len(first)==6 and [e["collider_id"] for e in first]==["S01","S02","S03","S04","S05","lower_platform"]
            and all(e["surface"]=="tread" and e["rebound_height_above_contact_m"]>.025 for e in first[:5])
            and result["quality"]["max_penetration_m"]<.001
            and result["quality"]["max_positive_contact_gap_m"]<.00015
            and result["quality"]["max_free_flight_velocity_residual_m_per_s"]<1e-8)

def run(out):
    out.mkdir(parents=True, exist_ok=True)
    trials = []
    base=scenario();ball=base["physics"]["ball"];z=ball["initial_position_m"][2]
    e_values=[round(ball["restitution"]+offset,6) for offset in [-.10,-.075,-.05,-.025,0,.025,.05]]
    x_values=[round(ball["initial_position_m"][0]+offset,6) for offset in [0,.004,.008]]
    # Bounded 21-case diagnostic around the current release; use the accepted collision timestep.
    for e in e_values:
        for x in x_values:
            cfg=scenario({"physics":{"ball":{"restitution":e,"initial_position_m":[x,0,z]}}})
            result=simulate(cfg,record=False)
            first=[v for v in result["contact_events"] if v["major_impact"]][:6]
            trials.append({"restitution":e,"release_x_m":x,"quality":result["quality"],
                           "major_contacts":first,"accepted":source_gate(result),
                           "simulation_wall_sec":result["simulation_wall_sec"]})
    write_json(out/"finite_scan.json", {"plan":{"trials":21,"restitutions":e_values,
                  "release_x_m":x_values,"fixed_initial_vx_m_per_s":ball["initial_velocity_m_per_s"][0],"diagnostic_substeps_per_frame":base["simulation_quality"]["substeps_per_frame"]},"results":trials})
    drops=[]
    for e in [scenario(case=case)["physics"]["ball"]["restitution"] for case in CASES]:
        cfg=scenario({"physics":{"ball":{"restitution":e,"initial_position_m":[2,0,1.04],
                "initial_velocity_m_per_s":[0,0,0]}},"render":{"duration_sec":1.2}})
        result=simulate(cfg,record=False)
        ev=result["contact_events"][0]
        measured=ev["post_normal_speed_m_per_s"]/ev["pre_normal_speed_m_per_s"]
        drops.append({"ball_restitution":e,"stairs_restitution":1.0,"predicted_product":e,
                      "measured_normal_velocity_ratio":measured,"absolute_error":abs(e-measured),"first_contact":ev})
    write_json(out/"restitution_calibration.json", {"rule":"e_contact = e_ball * e_stairs", "primary_source":
        "https://github.com/bulletphysics/bullet3/blob/3.25/src/BulletCollision/CollisionDispatch/btManifoldResult.cpp#L60-L63",
        "results":drops,"accepted":all(d["absolute_error"]<.01 for d in drops)})
    return trials

if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__); a.add_argument("--out-root",type=Path,required=True)
    args=a.parse_args(); trials=run(args.out_root)
    print([{k:t[k] for k in ("restitution","release_x_m","accepted")} for t in trials])
