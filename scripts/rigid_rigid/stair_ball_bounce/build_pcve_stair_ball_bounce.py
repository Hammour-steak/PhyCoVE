"""Source-gated PCVE suite with declared restitution, velocity or friction edits."""
from __future__ import annotations
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=="__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
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
import time
sys.path.insert(0,str(Path(__file__).resolve().parent/"physics"))
from scene_config import CASES,SUPPORTED_CASES,scenario,signature,merge,edited_ball_fields
from simulate_stair_ball_bounce import simulate,write_json,export_csv
from validate_stair_ball_bounce import validate
from edit_vocab import edit_info

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def checked(path,case,source=None):
    result=json.loads(path.read_text());report=validate(result,case,source)
    write_json(path.with_name("physics_validation.json"),report)
    if not report["accepted"]:raise RuntimeError(f"Physics rejected {case}: {[k for k,v in report['checks'].items() if not v]}")
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root",type=Path,required=True)
    p.add_argument("--stage",choices=["all","graybox","simulate","render","verify"],default="all")
    p.add_argument("--cases",nargs="+",choices=SUPPORTED_CASES,default=list(CASES))
    p.add_argument("--blender",type=Path,default=blender())
    p.add_argument("--threads-native",type=int,default=8);p.add_argument("--device",choices=["auto","cpu"],default="auto")
    p.add_argument("--skip-existing",action="store_true")
    p.add_argument("--appearance-json",type=Path,help="Common appearance override for source and every selected edit; no physical changes")
    a=p.parse_args();out=a.out_root.expanduser().resolve();out.mkdir(parents=True,exist_ok=True)
    if a.stage=="graybox":
        from graybox_stair_ball_bounce import run
        run(out/"graybox");return
    appearance_override=json.loads(a.appearance_json.read_text()) if a.appearance_json else {}
    if appearance_override and set(appearance_override)!={"appearance"}:raise ValueError("The shared view override may contain only appearance")
    cfg=scenario(appearance_override);manifest_path=out/"suite_manifest.json"
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text());assert manifest["configuration"]==cfg,"Choose a fresh root for different inputs"
        manifest["schema_version"]=3
    else:
        if any(out.iterdir()):raise FileExistsError("Output root is nonempty and does not belong to this scene")
        manifest={"schema_version":3,"suite_name":"pcve_stair_ball_bounce_suite","scene":"stair_ball_bounce","interaction_category":"rigid_rigid",
            "configuration":cfg,"source":None,"edits":[],"resolution":cfg["render"]["resolution"],"fps":cfg["render"]["fps"],
            "duration_sec":cfg["render"]["duration_sec"],"samples":cfg["render"]["samples"],"total_frames":round(cfg["render"]["fps"]*cfg["render"]["duration_sec"]),
            "source_case_id":"source","playback_rate":1.0,"solver":"PyBullet 3.2.7 independent 6-DOF btRigidBody, split penetration impulses, hollow-sphere inertia",
            "restitution_combination":"e_contact = e_ball * e_stairs; stairs fixed at 1.0 (combiner normalization, not a physical claim about bare wood)",
            "friction_combination":"Bullet lateral = clamp(mu_ball * mu_stairs, -10, 10); rolling = clamp(rho_ball * mu_stairs + rho_stairs * mu_ball, -10, 10). Static rho and spin friction are zero. Each edit declares either one changed coefficient or the user-requested paired lateral/rolling friction group.",
            "formal_settings_note":"1280x720, 24 fps, 96 frames, Cycles 64 samples retained; identical 4 s duration for all cases (benchmark media contract).","status":"running"}
        write_json(manifest_path,manifest)
    src_dir=out/"cases/source";src_file=src_dir/"physics_transforms.json"
    if a.stage in ["all","simulate"]:
        if not(a.skip_existing and src_file.exists()):
            r=simulate(cfg);write_json(src_file,r);export_csv(src_dir/"trajectory.csv",r);write_json(src_dir/"contacts.json",r["contact_events"])
    source=checked(src_file,"source")
    for case in a.cases:
        folder=out/"cases"/case;folder.mkdir(parents=True,exist_ok=True);path=folder/"physics_transforms.json"
        expected=scenario(appearance_override,case=case);info=edit_info(case) if case!="source" else None
        if info:
            assert merge(cfg,info["physics_override"])==expected
            write_json(folder/"scenario_overrides.json",info["physics_override"])
            write_json(folder/"prompts.json",{"schema_version":2,"case_id":case,"source_case_id":"source",**info})
        else:
            diameter_cm=2*cfg["physics"]["ball"]["radius_m"]*100
            release_vx=cfg["physics"]["ball"]["initial_velocity_m_per_s"][0]
            write_json(folder/"prompts.json",{"schema_version":2,"case_id":"source","prompts":{
                "vague":{"zh":"彩色玩具皮球在家中木质楼梯上逐级弹跳，下到平台后继续衰减弹跳和滚动。",
                         "en":"A colorful toy ball bounces down a wooden staircase at home, then makes diminishing bounces and rolls on the lower landing."},
                "quantitative":{"zh":f"直径 {diameter_cm:g} cm、质量 40 g 的彩色中空玩具球从最上面一级台阶上方 15 cm 处以 {release_vx:g} m/s 水平释放，初始自转为零，在正常重力下依次弹过五级木质台阶并落到下层平台。",
                "en":f"A {diameter_cm:g} cm, 40 g hollow colorful toy ball begins 15 cm above the top step at a horizontal speed of {release_vx:g} m/s with zero initial spin, freely bounces down five wooden steps under normal gravity, then lands and rolls on the lower platform."}}})
        if a.stage in ["all","simulate"] and case!="source" and not(a.skip_existing and path.exists()):
            r=simulate(expected);write_json(path,r);export_csv(folder/"trajectory.csv",r);write_json(folder/"contacts.json",r["contact_events"])
        result=checked(path,case,source if case!="source" else None)
        assert result["configuration"]==expected
        write_json(folder/"settings.json",expected)
        record={"case_id":case,"kind":"source" if case=="source" else "edit","source_case_id":"source","case_dir":str(folder),
            "status":"physics_accepted","quality":result["quality"],"simulation_wall_sec":result["simulation_wall_sec"]}
        if case=="source":record["description"]=json.loads((folder/"prompts.json").read_text())["prompts"]
        if info:record.update(info)
        main_contacts=[e for e in result["contact_events"] if e["major_impact"]]
        record["observed_outcome"]={"first_rebound_height_m":main_contacts[0]["rebound_height_above_contact_m"],
            "major_step_contact_order":[e["collider_id"] for e in main_contacts if e["collider_id"].startswith("S")],
            "first_lower_platform_contact_sec":next(e["time_sec"] for e in main_contacts if e["collider_id"]=="lower_platform"),
            "lower_platform_rolling_start_sec":result["quality"]["lower_platform_rolling_start_sec"]}
        if info:
            changed_values={field:expected['physics']['ball'][field] for field in edited_ball_fields(case)}
            record["edit_summary"]=f"B01 declared changed inputs: {changed_values}. Measured first major rebound: {record['observed_outcome']['first_rebound_height_m']:.6f} m; major step order: {record['observed_outcome']['major_step_contact_order']}."
        if a.stage in ["all","render"]:
            cmd=[str(a.blender.expanduser().resolve()),"-b","-t",str(int(os.environ.get("OMP_NUM_THREADS",a.threads_native))),"--python-exit-code","1","--python",str(HERE/"render_stair_ball_bounce.py"),"--",
                 "--physics-json",str(path),"--out-dir",str(folder),"--mode","animation","--device",a.device]
            if a.skip_existing:cmd.append("--skip-existing")
            if not(a.skip_existing and (folder/"video_validation.json").is_file()):
                begin=time.perf_counter()
                with (folder/"render.log").open("w") as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
                record["render_pipeline_sec"]=time.perf_counter()-begin
        if a.stage in ["all","render","verify"]:
            subprocess.run([sys.executable,str(ROOT/"scripts/pcve_verify_video.py"),str(folder/"video.mp4"),"--out",str(folder/"video_validation.json"),
                "--resolution",*[str(x) for x in cfg["render"]["resolution"]],"--fps",str(cfg["render"]["fps"]),"--frames",str(round(cfg["render"]["fps"]*cfg["render"]["duration_sec"]))],check=True)
            record["status"]="technically_verified_pending_visual_review"
        record["outputs"]={k:str(folder/f) for k,f in [("video","video.mp4"),("physics","physics_transforms.json"),("trajectory","trajectory.csv"),
            ("contacts","contacts.json"),("ground_truth","ground_truth_transforms.json"),("scene","stair_ball_bounce.blend"),("scenario_metadata","scenario_metadata.json")]}
        if case=="source":manifest["source"]=record
        else:manifest["edits"]=[e for e in manifest["edits"] if e["case_id"]!=case]+[record]
        write_json(manifest_path,manifest);print(case,record["status"],flush=True)
    write_json(out/"implementation_manifest.json",{"configuration":cfg,"configuration_sha256":signature(cfg),"runtime_python":sys.executable,"python_version":sys.version,
        "asset_manifests":[str(ROOT/"assets/polyhaven"/cfg["appearance"]["wood"]["asset"]/"asset_manifest.json")]+[str(ROOT/"assets/polyhaven"/n/"asset_manifest.json") for n in
            ["sunny_rose_garden","potted_plant_04","hanging_picture_frame_02"]],
        "asset_policy":"Authored 3D architecture and procedural PVC; documented CC0 Poly Haven maps, HDRI and props packed in every .blend."})

if __name__=="__main__":main()
