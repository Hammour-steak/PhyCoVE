"""Bounded physics experiments; source entry pose is frozen after the offset scan."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from scene_config import scenario,signature
from simulate_bowling import simulate,dump

def run_one(job):
    name,cfg,folder=job;result=simulate(cfg,record=False)
    summary={"case":name,"configuration":cfg,"configuration_sha256":signature(cfg),"quality":result["quality"],
       "contacts":result["contact_events"],"times":result["tilt_threshold_times_sec"],"final_state":result["final_state"],
       "actual_dynamics":result["actual_dynamics"],"simulation_wall_sec":result["simulation_wall_sec"]}
    dump(Path(folder)/f"{name}.json",summary)
    return summary

def run(folder,phase):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);jobs=[]
    if phase=="offset":
        for offset in [-.045,-.030,-.020,-.010,.010,.020,.030,.045]:
            cfg=scenario({"physics":{"ball":{"initial_position_m":[-2.5,offset,.1075]}}})
            jobs.append((f"offset_{offset:+.3f}",cfg,str(folder)))
    elif phase=="edits":
        for m in [.10,.25,.50,1.,2.]:
            jobs.append((f"ball_mass_{m:g}",scenario({"physics":{"ball":{"mass_kg":m}}}),str(folder)))
        for m in [3.,6.,10.,15.,25.]:
            jobs.append((f"P01_mass_{m:g}",scenario({"physics":{"pins":{"masses_kg":[m,1.5,1.5]}}}),str(folder)))
        jobs.append(("remove_P01",scenario(case="edit_remove_P01"),str(folder)))
        for i in range(3):
            for friction in [1.2,2.5]:
                fr=[.36]*3;fr[i]=friction
                jobs.append((f"P{i+1:02}_friction_{friction:g}",scenario({"physics":{"pins":{"frictions":fr}}}),str(folder)))
    else:raise ValueError(phase)
    with ProcessPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(run_one,jobs))
    dump(folder/"scan_report.json",{"phase":phase,"source_configuration":scenario(),"results":results})
    for r in results:
        q=r["quality"]
        print(r["case"],"toppled",q["toppled_count"],"contacts",[("/".join(c["objects"]),round(c["first_time_sec"],4)) for c in r["contacts"]],"final_ball",r["final_state"]["objects"]["B01"]["location"],"max_pen",q["max_penetration_m"],flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out",type=Path,required=True);p.add_argument("--phase",choices=["offset","edits"],required=True)
    a=p.parse_args();run(a.out,a.phase)
