"""Source-gated, independently simulated and rendered PCVE rigid-rigid suite."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=="__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,"build_pcve")
# PCVE_UNIFIED_ENTRY_END
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from scene_config import CASES,scenario,signature,differences,ASSET_MANIFEST_PATHS
from simulate_opposing_pendulum_collision import simulate,write_json,export_csv
from validate_opposing_pendulum_collision import validate
from edit_vocab import edit_info

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def load(path):return json.loads(path.read_text())

def checked(path,case,source=None):
    r=load(path);report=validate(r,case,source);write_json(path.with_name("physics_validation.json"),report)
    if not report["accepted"]:raise RuntimeError(f"Physics rejected {case}: {[k for k,v in report['checks'].items() if not v]}")
    return r

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--out-root",type=Path,required=True)
    ap.add_argument("--stage",choices=["all","graybox","simulate","render","verify"],default="all")
    ap.add_argument("--cases",nargs="+",choices=list(CASES),default=list(CASES))
    ap.add_argument("--blender",type=Path,default=blender())
    ap.add_argument("--threads-native",type=int,default=6);ap.add_argument("--device",choices=["auto","cpu"],default="auto");ap.add_argument("--skip-existing",action="store_true")
    a=ap.parse_args();out=a.out_root.expanduser().resolve()
    if a.stage=="graybox":
        from graybox_opposing_pendulum_collision import run
        run(out/"graybox");return
    cfg=scenario();manifest_path=out/"suite_manifest.json"
    if manifest_path.exists():
        manifest=load(manifest_path);assert manifest["configuration"]==cfg,"Changed inputs require a new isolated output root"
    else:
        if out.exists() and any(out.iterdir()):raise FileExistsError("Nonempty unrecognized output root")
        manifest={"schema_version":1,"scene":"opposing_pendulum_collision","interaction_category":"rigid_rigid","configuration":cfg,
            "source":None,"edits":[],"status":"running","formal_settings_note":"{}x{}, {} fps, {:g} s, {} frames, {} Cycles samples, 1x playback".format(*cfg["render"]["resolution"],cfg["render"]["fps"],cfg["render"]["duration_sec"],round(cfg["render"]["fps"]*cfg["render"]["duration_sec"]),cfg["render"]["samples"])}
        write_json(manifest_path,manifest)
    sourcepath=out/"cases/source/physics_transforms.json"
    if a.stage in ["all","simulate"] and not(a.skip_existing and sourcepath.exists()):
        r=simulate(cfg);write_json(sourcepath,r);export_csv(sourcepath.with_name("trajectory.csv"),r)
    source=checked(sourcepath,"source");assert source["configuration"]==cfg
    for case in a.cases:
        folder=out/"cases"/case;folder.mkdir(parents=True,exist_ok=True);path=folder/"physics_transforms.json";expected=scenario(case)
        if a.stage in ["all","simulate"] and case!="source" and not(a.skip_existing and path.exists()):
            r=simulate(expected);write_json(path,r);export_csv(folder/"trajectory.csv",r)
        result=checked(path,case,source if case!="source" else None);assert result["configuration"]==expected
        write_json(folder/"settings.json",expected);write_json(folder/"contacts.json",{"events":result["contact_events"]})
        write_json(folder/"prompts.json",{"schema_version":1,"case_id":case,"source_case_id":"source",**edit_info(case)})
        write_json(folder/"config_diff.json",{"before":cfg,"after":expected,"differences":differences(cfg,expected)})
        record={"case_id":case,"case_dir":str(folder),"status":"physics_accepted","simulation_wall_sec":result["simulation_wall_sec"],
            "first_collision_sec":next((e["time_sec"] for e in result["contact_events"] if e["kind"]=="ball_ball"),None),
            "first_rebound":result["first_rebound"],"effective_contacts":result["effective_contacts"],"physics_override":CASES[case]}
        if a.stage in ["all","render"] and not(a.skip_existing and (folder/"video_validation.json").is_file()):
            command=[str(a.blender.expanduser().resolve()),"-b","-t",str(int(os.environ.get("OMP_NUM_THREADS",a.threads_native))),"--python-exit-code","1",
                "--python",str(HERE/"render_opposing_pendulum_collision.py"),"--","--physics-json",str(path),"--out-dir",str(folder),"--mode","animation","--device",a.device]
            if a.skip_existing:command.append("--skip-existing")
            with (folder/"render.log").open("w") as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
        if a.stage in ["all","render","verify"]:
            subprocess.run([sys.executable,str(ROOT/"scripts/pcve_verify_video.py"),str(folder/"video.mp4"),"--out",str(folder/"video_validation.json"),
                "--resolution",*[str(v) for v in cfg["render"]["resolution"]],"--fps",str(cfg["render"]["fps"]),"--frames",str(round(cfg["render"]["fps"]*cfg["render"]["duration_sec"]))],check=True)
            record["status"]="technically_verified_pending_visual_review"
            record["render_report"]=load(folder/"render_report.json")
        record["outputs"]={k:str(folder/f) for k,f in [("video","video.mp4"),("physics","physics_transforms.json"),("trajectory","trajectory.csv"),
            ("scene","opposing_pendulum_collision.blend"),("ground_truth","ground_truth_transforms.json"),("contacts","contacts.json")]}
        if case=="source":manifest["source"]=record
        else:manifest["edits"]=[e for e in manifest["edits"] if e["case_id"]!=case]+[record]
        write_json(manifest_path,manifest);print(case,record["status"],flush=True)
    write_json(out/"implementation_manifest.json",{"configuration_sha256":signature(cfg),"runtime_python":sys.executable,"python_version":sys.version,
        "asset_manifests":[str(ROOT/path) for path in ASSET_MANIFEST_PATHS],
        "assets":"CC0 BlenderKit steel table base and sliding window (rear, two left-wall and one front-wall window), photographed Poly Haven timber top, scanned Poly Haven plywood base board, scanned Poly Haven wood_floor planks, Poly Haven drawer_cabinet with wicker_basket_01 and potted_plant_04, Poly Haven potted_plant_01, white-stucco maps and the exterior HDRI seen through the windows; scene-specific aluminium-extrusion stand with cast brackets, plain solid ABS balls, braided cord with knots, glass-and-brass hourglass, notebook and CC0 measuring tape with its printed label painted out. Every texture is packed in each blend.",
        "limitations":["Uniform rigid-sphere resin approximation, explicit pair impulse contact; no measured real-to-sim calibration", "Massless endpoint cords, quasi-static visual sag; cord bending and cord self contact are not simulated", "Four-second fixed-camera observation window"]})

if __name__=="__main__":main()
