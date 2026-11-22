"""Build source-gated basketball object, mass and restitution edits with the unified PCVE interface."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__,"build_pcve")
# PCVE_UNIFIED_ENTRY_END
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from pcve_assets import blender
from scene_config import SCENE, CASES, scenario, signature
from simulate_basketball_court_bounce import simulate, write_json, export_csv
from physics.validate_basketball_court_bounce import validate
from edit_vocab import edit_info

def read(path):
    return json.loads(Path(path).read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_physics(folder,result):
    write_json(folder/"physics_transforms.json",result)
    export_csv(folder/"trajectory.csv",result)
    write_json(folder/"contacts.json",result["contact_events"])

def source_prompts():
    return {
        "vague":{"zh":"橙色篮球在室内木质篮球场原地落下，连续作逐渐降低的反弹。",
                 "en":"An orange basketball drops vertically onto an indoor wooden basketball court and makes progressively smaller bounces."},
        "quantitative":{"zh":"直径 24 cm、质量 0.625 kg 的橙色刚性篮球从球底离地 1.5 m 处静止释放，恢复系数为 0.76，在 9.81 m/s² 重力下碰撞木地板并在原地逐次衰减反弹。",
                        "en":"A 24 cm, 0.625 kg orange rigid basketball with restitution 0.76 is released from rest with its bottom 1.5 m above a wooden court under 9.81 m/s² gravity. It bounces in place, each bounce lower than the last."}}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root",type=Path,required=True)
    p.add_argument("--stage",choices=["all","simulate","preview","render","verify"],default="all")
    p.add_argument("--cases",nargs="+",choices=list(CASES),default=list(CASES))
    p.add_argument("--blender",type=Path,default=blender())
    p.add_argument("--threads-native",type=int,default=64)
    p.add_argument("--device",choices=["cpu","gpu"],default="cpu")
    p.add_argument("--skip-existing",action="store_true")
    p.add_argument("--config-json",type=Path)
    p.add_argument("--reuse-physics-json",type=Path,
                   help="Reuse the accepted source trajectory only; every edit is independently solved")
    a=p.parse_args()
    override=read(a.config_json) if a.config_json else {}
    cfg=scenario(override)
    # The declared edit prompts refer to this source coefficient.
    if any(c!="source" for c in a.cases) and cfg["physics"]["ball"]["restitution"]!=0.76:
        raise ValueError("Declared edits require source restitution 0.76")
    out=a.out_root.expanduser().resolve()
    manifest_path=out/"suite_manifest.json"
    if manifest_path.exists():
        manifest=read(manifest_path)
        if manifest["configuration"]!=cfg:raise ValueError("Choose a fresh output root for changed inputs")
    else:
        if out.exists() and any(out.iterdir()):raise FileExistsError("Refusing an existing unowned output root")
        manifest={"schema_version":3,"suite_name":"pcve_"+SCENE+"_suite","scene":SCENE,
                  "interaction_category":"rigid_rigid","configuration":cfg,"configuration_sha256":signature(cfg),
                  "source_case_id":"source","source":None,"edits":[],"requested_scope":"source and declared object, mass and restitution edits",
                  "resolution":cfg["render"]["resolution"],"fps":cfg["render"]["fps"],
                  "duration_sec":cfg["render"]["duration_sec"],"total_frames":cfg["render"]["total_frames"],
                  "samples":cfg["render"]["samples"],"playback_rate":1.0,"status":"running"}
        write_json(manifest_path,manifest)
    src_dir=out/"cases/source"
    src_path=src_dir/"physics_transforms.json"
    if a.stage in ["all","simulate"]:
        if src_path.exists() and not a.skip_existing:raise FileExistsError(src_path)
        if not src_path.exists():
            if a.reuse_physics_json:
                result=read(a.reuse_physics_json)
                for group in ["physics","simulation_quality"]:
                    if result["configuration"][group]!=cfg[group]:
                        raise ValueError("Source trajectory reuse must preserve "+group)
                if result["fps"]!=cfg["render"]["fps"] or result["frame_end"]!=cfg["render"]["total_frames"]:
                    raise ValueError("A reused source trajectory must preserve frame times")
                result["appearance_revision_reference"]={
                    "physics_json":str(a.reuse_physics_json.resolve()),
                    "file_sha256":sha(a.reuse_physics_json),
                    "trajectory_reused_without_resimulation":True}
                result["configuration"]=cfg;result["configuration_sha256"]=signature(cfg)
                result["case_id"]="source"
            else:result=simulate(cfg)
            save_physics(src_dir,result)
    source=read(src_path)
    if source["configuration"]!=cfg:raise ValueError("Source cache configuration differs")
    source_validation=validate(source,"source")
    write_json(src_dir/"physics_validation.json",source_validation)
    if not source_validation["accepted"]:raise RuntimeError("Source physics gate failed")
    selected=list(dict.fromkeys(a.cases))
    for case in selected:
        folder=out/"cases"/case
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/"physics_transforms.json"
        expected=scenario(override,case=case)
        info=edit_info(case) if case!="source" else None
        if case!="source" and a.stage in ["all","simulate"]:
            if path.exists() and not a.skip_existing:raise FileExistsError(path)
            if not path.exists():
                result=simulate(expected);result["case_id"]=case
                result["edit_reference"]={
                    "source_physics_json":str(src_path),"source_sha256":sha(src_path),
                    "target_field":info["target_field"],"from":info["before_value"],
                    "to":info["after_value"],"applies_from_frame":info["applies_from_frame"],
                    "applies_at_time_sec":info["applies_at_time_sec"],"independent_solver_run":True}
                save_physics(folder,result)
        result=read(path)
        if result["configuration"]!=expected:raise ValueError("Physics cache configuration differs: "+case)
        validation=validate(result,case,source if case!="source" else None)
        write_json(folder/"physics_validation.json",validation)
        if not validation["accepted"]:raise RuntimeError({case:validation})
        write_json(folder/"settings.json",expected)
        prompts={"schema_version":2,"case_id":case,"kind":"source" if case=="source" else "edit","source_case_id":"source"}
        if info:
            prompts.update(info)
            write_json(folder/"scenario_overrides.json",info["physics_override"])
            write_json(folder/"physics_diff.json",info["physics_diff"])
        else:prompts["prompts"]=source_prompts()
        write_json(folder/"prompts.json",prompts)
        record={"case_id":case,"kind":prompts["kind"],"source_case_id":"source","case_dir":str(folder),
                "status":"physics_accepted","simulation_wall_sec":result["simulation_wall_sec"],
                "observed_outcome":validation,
                "outputs":{key:str(folder/name) for key,name in [
                    ("video","video.mp4"),("scene",SCENE+".blend"),("physics","physics_transforms.json"),
                    ("trajectory","trajectory.csv"),("contacts","contacts.json"),
                    ("ground_truth","ground_truth_transforms.json"),("scenario_metadata","scenario_metadata.json")]}}
        if info:record.update(info)
        else:record["description"]=prompts["prompts"]
        if a.stage in ["all","preview","render"]:
            mode="frames" if a.stage=="preview" else "animation"
            cmd=[str(a.blender),"-b","-Y","-t",str(a.threads_native),"--python-exit-code","1",
                 "--python",str(HERE/("render_"+SCENE+".py")),"--","--physics-json",str(path),
                 "--out-dir",str(folder),"--mode",mode,"--device",a.device,"--threads-native",str(a.threads_native)]
            if a.skip_existing:cmd.append("--skip-existing")
            begin=time.perf_counter()
            with (folder/("render_"+mode+".log")).open("w") as log:
                subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            record[mode+"_pipeline_sec"]=time.perf_counter()-begin
        if a.stage in ["all","render","verify"]:
            subprocess.run([sys.executable,str(ROOT/"scripts/pcve_verify_video.py"),str(folder/"video.mp4"),
                            "--out",str(folder/"video_validation.json"),"--resolution","1280","720",
                            "--fps","24","--frames","96"],check=True)
            record["status"]="technically_verified_pending_visual_review"
        elif a.stage=="preview":record["status"]="preview_completed"
        if case=="source":manifest["source"]=record
        else:manifest["edits"]=[e for e in manifest["edits"] if e["case_id"]!=case]+[record]
        manifest["status"]=record["status"]
        write_json(manifest_path,manifest)
        print(case,record["status"],flush=True)
    write_json(out/"implementation_manifest.json",{
        "configuration":cfg,"runtime_python":sys.executable,"python_version":sys.version,
        "asset_policy":"Shared accepted "+cfg["appearance"]["preset"]+" geometry, materials, camera and lighting; packed registered assets.",
        "source_physics_cache":str(src_path),"source_physics_cache_sha256":sha(src_path),
        "case_ids":["source"]+[e["case_id"] for e in manifest["edits"]],"supported_case_ids":list(CASES),
        "edit_targets":sorted({e["target_field"] for e in manifest["edits"]})})
    print(manifest_path)
if __name__=="__main__":main()
