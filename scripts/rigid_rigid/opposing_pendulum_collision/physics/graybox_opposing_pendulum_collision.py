"""Finite isolated mass/restitution scans and numerical/solver verification."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import json
from pathlib import Path
from scene_config import scenario,differences
from simulate_opposing_pendulum_collision import simulate,write_json,export_csv
from validate_opposing_pendulum_collision import validate,ball_events
from rigid_solver import Body,World

def solver_checks():
    cfg=scenario();sq=cfg["simulation_quality"];ph=cfg["physics"]
    out={}
    for ratio in [1.,1.5,3.,5.]:
        bs=[]
        for i,(name,x,v) in enumerate([("B_left",-.029999,1.5),("B_right",.029999,-1.5)]):
            spec=dict(ph["balls"][name]);spec["mass_kg"]*=ratio if i==0 else 1
            spec["initial_linear_velocity"]=[v,0.,0.];spec["linear_drag_per_s"]=0.;spec["angular_drag_per_s"]=0.
            bs.append(Body(name,spec,[x,0,1],[0.,0.,0.,1.],None))
        testph=dict(ph);testph["gravity"]=[0.,0.,0.];testph["contacts"]={**ph["contacts"],"ball_ball":{"restitution":.9,"friction":0.}}
        world=World(bs,[],testph,sq,1.e-4);world.step();e=.9;m1,m2=ratio,1.;u1,u2=1.5,-1.5
        expected=[((m1-e*m2)*u1+(1+e)*m2*u2)/(m1+m2),((1+e)*m1*u1+(m2-e*m1)*u2)/(m1+m2)]
        out[f"analytic_1d_impact_mass_ratio_{ratio}"]={"passed":max(abs(b.v[0]-v) for b,v in zip(bs,expected))<1.e-12,
            "expected_vx":expected,"actual_vx":[b.v[0] for b in bs]}
    spec=dict(ph["balls"]["B_left"]);spec["initial_linear_velocity"]=[0.,0.,.2];spec["linear_drag_per_s"]=0.
    rope=ph["ropes"]["B_left"];b=Body("B_left",spec,[-.03,0.,1.2],[0,0,0,1],rope)
    testph=dict(ph);testph["gravity"]=[0.,0.,0.];world=World([b],[],testph,sq,1.e-4)
    for _ in range(50):world.step()
    out["slack_rope_transmits_no_push"]={"passed":b.rope_impulse==0 and abs(b.v[2]-.2)<1.e-14,"final_velocity":b.v.tolist(),"rope_impulse_Ns":b.rope_impulse}
    spec=dict(spec);spec["initial_linear_velocity"]=[0.,.07,0.]
    b=Body("B_left",spec,[-.03,0,1.0],[0,0,0,1],rope);world=World([b],[],ph,sq,1.e-4)
    for _ in range(500):world.step()
    out["out_of_plane_motion_is_not_locked"]={"passed":abs(b.p[1])>.003,"final_y_m":b.p[1]}
    return {"accepted":all(v["passed"] for v in out.values()),"checks":out}

def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);tests=solver_checks();write_json(out/"solver_checks.json",tests)
    if not tests["accepted"]:raise RuntimeError("Solver analytic/slack checks failed")
    summary=[]
    def trial(label,cfg,case="source",source=None):
        folder=out/label;path=folder/"physics_transforms.json"
        if path.exists():
            r=json.loads(path.read_text());assert r["configuration"]==cfg
        else:
            r=simulate(cfg);write_json(path,r);export_csv(folder/"trajectory.csv",r)
        report=validate(r,case,source);write_json(folder/"physics_validation.json",report)
        write_json(folder/"config_diff.json",{"before":scenario(),"after":cfg,"differences":differences(scenario(),cfg)})
        es=ball_events(r);row={"label":label,"accepted":report["accepted"],"wall_sec":r["simulation_wall_sec"],
            "collision_time_sec":es[0]["time_sec"] if es else None,
            "post_collision_vx":{n:v[0] for n,v in es[0]["post_linear_velocities"].items()} if es else {},
            "rebound_heights_m":{n:v["height_above_initial_lowest_center_m"] if v else None for n,v in r["first_rebound"].items()},
            "quality":r["quality"]};summary.append(row);write_json(out/"scan_summary.json",summary)
        print(json.dumps({k:row[k] for k in ["label","accepted","collision_time_sec","post_collision_vx","rebound_heights_m"]}),flush=True)
        return r
    source=trial("source",scenario())
    if not validate(source)["accepted"]:raise RuntimeError("Source must pass before edits")
    formal=source["configuration"]["simulation_quality"]["substeps_per_frame"]
    # Half and double the formal step rate.
    for sub in [formal//2,formal*2]:trial(f"quality_substeps_{sub}",scenario(overrides={"simulation_quality":{"substeps_per_frame":sub}}))
    for ratio in [1.25,1.5,2.,3.,4.]:
        trial(f"mass_ratio_{ratio}",scenario(overrides={"physics":{"balls":{"B_left":{"mass_kg":.12*ratio}}}}),"edit_heavy_left",source)
    for e in [.65,.40,.25,.10]:
        trial(f"restitution_{e}",scenario(overrides={"physics":{"contacts":{"ball_ball":{"restitution":e}}}}),"edit_low_restitution",source)
    for case in ["edit_remove_right","edit_remove_left_rope"]:trial(case,scenario(case),case,source)
    base=next(r for r in summary if r["label"]==f"quality_substeps_{formal//2}");fine=next(r for r in summary if r["label"]=="source")
    write_json(out/"numerical_convergence.json",{"before_substeps":formal//2,"after_substeps":formal,
        "collision_time_difference_sec":fine["collision_time_sec"]-base["collision_time_sec"],
        "first_apex_height_difference_m":fine["rebound_heights_m"]["B_left"]-base["rebound_heights_m"]["B_left"],
        "accepted":abs(fine["rebound_heights_m"]["B_left"]-base["rebound_heights_m"]["B_left"])<.0002,
        f"substeps_{formal*2}":next(r for r in summary if r["label"]==f"quality_substeps_{formal*2}"),
        f"substeps_{formal}":fine})

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument("--out-root",type=Path,required=True);a=ap.parse_args();run(a.out_root)
