"""Finite isolated mass, restitution and timestep experiments; no art inputs changed."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import json
from pathlib import Path
from scene_config import scenario,differences
from simulate_twin_ramp_collision import simulate,write_json,export_csv

def summarize(r):
    e=r["contact_events"]
    return {"first_contact_sec":e[0]["time_sec"] if e else None,
        "collision_position_m":e[0]["position_m"] if e else None,
        "measured_restitution":e[0]["measured_normal_restitution"] if e else None,
        "velocity_before":{k:v["linear_velocity"][0] for k,v in e[0]["before"].items()} if e else {},
        "velocity_after":{k:v["linear_velocity"][0] for k,v in e[0]["after"].items()} if e else {},
        "first_rebound":r["first_rebound"],"turns":r["ramp_turning_points"],"quality":r["quality"],"wall_sec":r["simulation_wall_sec"]}

def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);base=scenario();rows=[]
    experiments=[("source",{}),*[(f"mass_{m:g}",{"physics":{"balls":{"B_left":{"mass_kg":m}}}}) for m in [.09375,.105,.1125,.12,.15,.225,.3,.45]],
        *[(f"restitution_{e:g}",{"physics":{"balls":{k:{"restitution":e} for k in ["B_left","B_right"]}}}) for e in [.8,.65,.55,.4,.25]],
        ("remove_right",{"physics":{"balls":{"B_right":{"present":False}}}}),
        # Half and double the formal step rate.
        *[(f"substeps_{s}",{"simulation_quality":{"substeps_per_frame":s}}) for s in [base["simulation_quality"]["substeps_per_frame"]//2,base["simulation_quality"]["substeps_per_frame"]*2]]]
    for name,override in experiments:
        cfg=scenario(overrides=override);r=simulate(cfg);dest=out/name
        write_json(dest/"physics_transforms.json",r);export_csv(dest/"trajectory.csv",r)
        row={"experiment":name,"before":base,"after":cfg,"differences":differences(base,cfg),"summary":summarize(r)}
        write_json(dest/"experiment.json",row);rows.append(row)
        print(name,json.dumps(row["summary"],ensure_ascii=False),flush=True)
    write_json(out/"parameter_scan.json",rows)
    return rows

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--out-root",type=Path,required=True);run(p.parse_args().out_root)
