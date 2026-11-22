"""Canonical curling source/edit pipeline: solve, preview, render and verify."""
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
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from pcve_assets import blender
from scene_config import SCENE, scenario, signature
from simulate_curling_collision import simulate, write_json, export_csv
from physics.validate_curling_collision import validate
from edit_vocab import EDIT_CASES, edit_record, edit_summary

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root",type=Path,required=True)
    parser.add_argument("--stage",choices=["all","simulate","preview","render","verify"],default="all")
    parser.add_argument("--cases",nargs="+",choices=["source",*EDIT_CASES],default=["source"])
    parser.add_argument("--blender",type=Path,default=blender())
    parser.add_argument("--threads-native",type=int,default=64)
    parser.add_argument("--device",choices=["cpu","gpu"],default="cpu")
    parser.add_argument("--skip-existing",action="store_true")
    parser.add_argument("--config-json",type=Path)
    args = parser.parse_args()
    cfg = scenario(json.loads(args.config_json.read_text()) if args.config_json else None)
    out = args.out_root.expanduser().resolve()
    manifest_path = out/"suite_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["configuration"]!=cfg:
            raise ValueError("Changed inputs require a fresh output root")
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError("Refusing an existing unowned output root")
        manifest = {"schema_version":3,"suite_name":"pcve_"+SCENE+"_suite","scene":SCENE,
            "interaction_category":"rigid_rigid","configuration":cfg,"configuration_sha256":signature(cfg),
            "source_case_id":"source","source":None,"edits":[],"requested_scope":" + ".join(args.cases),
            "resolution":[1280,720],"fps":24,"duration_sec":4.0,"total_frames":96,
            "samples":cfg["render"]["samples"],"playback_rate":1.0,"status":"running"}
        write_json(manifest_path,manifest)
    for case_id in args.cases:
        folder = out/"cases"/case_id
        record_edit = None if case_id=="source" else edit_record(case_id)
        case_cfg = cfg if record_edit is None else record_edit["configuration"]
        path = folder/"physics_transforms.json"
        if args.stage in ["all","simulate"]:
            if path.exists() and not args.skip_existing:
                raise FileExistsError(path)
            if not path.exists():
                result = simulate(case_cfg,case_id)
                write_json(path,result)
                export_csv(folder/"trajectory.csv",result)
                write_json(folder/"contacts.json",result["contact_events"])
        result = json.loads(path.read_text())
        if result["configuration"]!=case_cfg:
            raise ValueError("Physics cache configuration differs")
        validation = validate(result)
        write_json(folder/"physics_validation.json",validation)
        if not validation["accepted"]:
            raise RuntimeError(validation)
        write_json(folder/"settings.json",case_cfg)
        if record_edit is None:
            write_json(folder/"prompts.json",{"schema_version":2,"case_id":"source","source_case_id":"source",
            "prompts":{"vague":{"zh":"室内冰壶场上，红把手冰壶先撞蓝把手冰壶，蓝壶滑行后再撞黄把手冰壶。",
                "en":"On indoor curling ice, a red-handled granite stone strikes a blue-handled stone, which slides and then strikes a yellow-handled stone."},
                "quantitative":{"zh":"三只直径 29 cm、质量各 19.5 kg 的花岗岩冰壶在室内冰面上沿一条直线排列，相邻两壶之间的初始间隙为 69 cm 和 85 cm。红把手冰壶以 1.25 m/s 的初速度向右滑出，蓝把手冰壶和黄把手冰壶在被撞前静止。红壶先正面撞上蓝壶，蓝壶滑行后再正面撞上黄壶，冰壶只平移、不旋转。冰壶之间的恢复系数为 0.82，冰面动摩擦系数为 0.018。",
                    "en":"Three granite curling stones, each 29 cm across and 19.5 kg, stand in a straight line on indoor ice with initial gaps of 69 cm and 85 cm between neighbours. The red-handled stone slides to the right at 1.25 m/s, while the blue-handled and yellow-handled stones rest until struck. The red stone hits the blue stone head-on, and the blue stone slides on and hits the yellow stone head-on. The stones translate without spinning. Stone-to-stone restitution is 0.82 and the ice's kinetic friction coefficient is 0.018."}}})
        else:
            summary = edit_summary(result)
            write_json(folder/"scenario_overrides.json",{"physics":record_edit["scenario_override"]})
            write_json(folder/"prompts.json",{"schema_version":2,"case_id":case_id,"source_case_id":"source",
                "edit_dsl":record_edit["edit_dsl"],"edit_summary":summary,"applies_from_frame":record_edit["applies_from_frame"],
                "physics_diff":record_edit["physics_diff"],"prompts":record_edit["prompts"]})
        previous = manifest.get("source") if record_edit is None else next((e for e in manifest["edits"] if e["case_id"]==case_id),None)
        record = previous or {"case_id":case_id,"kind":"source" if record_edit is None else "edit","source_case_id":"source","case_dir":str(folder)}
        if record_edit is not None:
            record.update(edit_dsl=record_edit["edit_dsl"],edit_summary=summary,physics_diff=record_edit["physics_diff"],prompts=record_edit["prompts"])
        record.update(status="physics_accepted",simulation_wall_sec=result["simulation_wall_sec"],observed_outcome=validation,
            outputs={key:str(folder/name) for key,name in [("video","video.mp4"),("scene",SCENE+".blend"),
                ("physics","physics_transforms.json"),("trajectory","trajectory.csv"),("contacts","contacts.json"),
                ("ground_truth","ground_truth_transforms.json"),("scenario_metadata","scenario_metadata.json")]})
        if record_edit is None:
            manifest["source"] = record
        elif previous is None:
            manifest["edits"].append(record)
        write_json(manifest_path,manifest)
        if args.stage in ["all","preview","render"]:
            mode = "frames" if args.stage=="preview" else "animation"
            command = [str(args.blender),"-b","-t",str(args.threads_native),"--python-exit-code","1","--python",
                str(HERE/("render_"+SCENE+".py")),"--","--physics-json",str(path),"--out-dir",str(folder),
                "--mode",mode,"--device",args.device,"--threads-native",str(args.threads_native)]
            if args.skip_existing:
                command.append("--skip-existing")
            begin = time.perf_counter()
            with (folder/("render_"+mode+".log")).open("w") as log:
                subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            record[mode+"_pipeline_sec"] = time.perf_counter()-begin
        if args.stage in ["all","render","verify"]:
            subprocess.run([sys.executable,str(ROOT/"scripts/pcve_verify_video.py"),str(folder/"video.mp4"),
                "--out",str(folder/"video_validation.json"),"--resolution","1280","720","--fps","24","--frames","96"],check=True)
            record["status"] = manifest["status"] = "technically_verified_pending_visual_review"
        else:
            manifest["status"] = "preview_completed" if args.stage=="preview" else "physics_accepted"
        if record_edit is None:
            manifest["source"] = record
        write_json(manifest_path,manifest)
    write_json(out/"implementation_manifest.json",{"configuration":cfg,"runtime_python":sys.executable,"python_version":sys.version,
        "asset_policy":"Sketchfab Curling Stone by FilinMX (CC BY-NC 4.0), user-downloaded GLB; normalized to SI; handle and cap geometry retained, granite body lathed from the measured profile, procedural polished granite and plain polymer. Original closed two-sheet 3D club without lettering or brand marks, glossy pebbled ice with a seeded wear map, ceiling battens, lit gallery, a fixed low f/3.2 perspective and a compositor-only camera finish. See asset_manifest.json for attribution, hashes and dependencies.",
        "physics_cache":str(path),"physics_cache_sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    print(manifest_path)

if __name__ == "__main__":
    main()
