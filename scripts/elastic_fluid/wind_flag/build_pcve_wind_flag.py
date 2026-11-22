"""Public PCVE entry point: approved source plus five independent edits."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'build_pcve')
# PCVE_UNIFIED_ENTRY_END
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from wind_flag_config import (HERE, ROOT, SPEC, ASSETS, RUNTIME_DEPS, SOURCE_ID, CASE_MAP,
    choose_gpu, default_blender, digest, read_json, write_json, ensure_json, copy_verified)
from edit_vocab import plans
from validate_wind_flag import validate


def case_dir(args, case_id):
    return args.out_root/"cases"/case_id


def run(args, label, command, gpu=False):
    env=dict(os.environ)
    if gpu:
        env["CUDA_VISIBLE_DEVICES"]=choose_gpu(args.gpu)
    logs=args.out_root/"logs"
    logs.mkdir(parents=True,exist_ok=True)
    log=logs/f"{label}_{time.time_ns()}.log"
    print("START",label,flush=True)
    with log.open("xb") as stream:
        subprocess.run(command,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,check=True)
    print("DONE",label,flush=True)


def prepare(args, selected):
    for plan in selected:
        case=case_dir(args,plan["case_id"])
        case.mkdir(parents=True,exist_ok=True)
        prompt={"schema_version":2,"case_id":plan["case_id"],"kind":plan["kind"],
            "source_case_id":SOURCE_ID,"edit_dsl":plan["edit_dsl"],"prompts":plan["prompts"],
            "applies_from_frame":plan["applies_from_frame"],"physics_diff":plan["physics_diff"]}
        if plan["kind"]=="edit":
            prompt["edit_summary"]=plan["edit_summary"]
        ensure_json(case/"prompts.json",prompt)
        ensure_json(case/"scenario_overrides.json",{"physics":plan["physics_override"]})
        ensure_json(case/"scene_spec.json",SPEC)


def import_approved(args, selected, assets):
    manifest_hash=digest(args.asset_dir/"asset_manifest.json")
    for plan in selected:
        case=case_dir(args,plan["case_id"])
        accepted=assets["approved_cases"][plan["native_case"]]
        source=args.asset_dir/accepted["path"]
        for relative,expected in accepted["files"].items():
            copy_verified(source/relative,case/relative,expected)
        ensure_json(case/"import_receipt.json",{"source":"hash-verified approved assets", "native_case":plan["native_case"],
            "asset_manifest_sha256":manifest_hash,"files":accepted["files"]})
        ensure_json(case/"render_receipt.json",{"cache_sha256":digest(case/"simulation/genesis_flag_cache.npz"),
            "video_sha256":digest(case/"video.mp4"),"frame_range":[1,96],"resolution":[1280,720],
            "fps":24,"render_samples":64,"diagnostic_partial_or_preview":False,"reused_approved_render":True})


def sim_command(args, plan):
    case=case_dir(args,plan["case_id"])
    return [args.python,"-u",str(HERE/"simulate_wind_flag.py"),"--out-dir",str(case/"simulation"),
        "--case",plan["native_case"],"--checkpoint",str(args.asset_dir/"initial_state.npz"),
        "--ipc-deps",str(args.ipc_deps),"--scenario-overrides-json",str(case/"scenario_overrides.json")]


def simulate(args, selected):
    by_native={p["native_case"]:p for p in selected}
    source=by_native["source"]
    timed=by_native.get("wind_drop_at_2s")
    source_done=(case_dir(args,SOURCE_ID)/"simulation/simulation_report.json").exists()
    timed_done=timed and (case_dir(args,timed["case_id"])/"simulation/simulation_report.json").exists()
    if source_done and timed and not timed_done:
        raise RuntimeError("A native timed continuation must be built together with source in a fresh output root; do not splice independent trajectories")
    if not source_done:
        command=sim_command(args,source)
        if timed:
            command += ["--emit-timed-branch","--timed-branch-out",str(case_dir(args,timed["case_id"])/"simulation")]
        run(args,"simulate_source_and_timed" if timed else "simulate_source",command,gpu=True)
    elif not args.skip_existing:
        raise RuntimeError("Source simulation exists; use --skip-existing or a fresh --out-root")
    for plan in selected:
        if plan["native_case"] in ("source","wind_drop_at_2s"):
            continue
        report=case_dir(args,plan["case_id"])/"simulation/simulation_report.json"
        if report.exists() and args.skip_existing:
            continue
        run(args,"simulate_"+plan["native_case"],sim_command(args,plan),gpu=True)


def metadata(args, selected):
    for plan in selected:
        case=case_dir(args,plan["case_id"])
        config_path=case/"simulation/resolved_config.json"
        if not config_path.is_file():
            continue
        config=read_json(config_path)
        with np.load(case/"simulation/genesis_flag_cache.npz") as cache:
            count=len(cache["vertices"])
            pins=cache["pinned"].tolist()
        write_json(case/"ground_truth.json",{"schema_version":1,"units":"m, s, kg, Pa", "frame_index_base":1,
            "time_s":[i/config["quality"]["fps"] for i in range(count)],
            "objects":{"flag":{"type":"deformable_triangle_shell","cache":"simulation/genesis_flag_cache.npz",
                "position_key":"physical_positions","velocity_key":"physical_velocities","topology_key":"physical_faces",
                "rest_position_key":"rest_positions","pinned_vertices":pins},"pole":{"type":"fixed_rigid_mesh","scene":"scene.blend"}},
            "air_force_model":config["physics"]["air"],"initial_state_sha256":config["initial_state_sha256"]})
        actual={"schema_version":1,"scene_id":"wind_flag","interaction_category":"elastic_fluid","case_id":plan["case_id"],
            "seed":4090,"physics":config["physics"],"simulation_quality":config["quality"],
            "appearance":SPEC["appearance"],"render":SPEC["render"],"runtime":config["runtime"],"coupling":SPEC["coupling"],
            "initial_state_sha256":config["initial_state_sha256"],"simulation_cache_sha256":digest(case/"simulation/genesis_flag_cache.npz")}
        if plan["native_case"]=="wind_drop_at_2s":
            actual["timed_edit"]={"trigger_frame":49,"trigger_time_s":2,"first_potentially_changed_state_frame":50,
                "physical_prefix_samples_inclusive":49,"continuation":"Native IPC World.dump/recover; after reaching t=2, before advancing further"}
        write_json(case/"scenario_metadata.json",actual)


def render(args, selected):
    for plan in selected:
        case=case_dir(args,plan["case_id"])
        command=[args.python,str(HERE/"render_wind_flag.py"),"--simulation-dir",str(case/"simulation"),
            "--out-dir",str(case),"--blender",args.blender,"--gpu",args.gpu,"--asset-dir",str(args.render_assets)]
        if args.skip_existing:
            command.append("--skip-existing")
        run(args,"render_"+plan["native_case"],command)


def audit(args, selected):
    # Imported evidence is reused only while the scene and every accepted
    # input/output file still match the approved manifest exactly.
    fresh=False
    for plan in selected:
        case=case_dir(args,plan["case_id"])
        imported=(case/"import_receipt.json").exists()
        fresh |= not imported
        if not imported:
            run(args,"contact_"+plan["native_case"],[args.blender,"-b","-t","2","--python-exit-code","1","--python",
                str(HERE/"appearance/audit_contact_wind_flag.py"),"--","--root",str(args.out_root/"cases"),"--case",plan["case_id"],
                "--out",str(case/"contact_audit.json")])
    if fresh:
        run(args,"appearance",[args.blender,"-b","-t","2","--python-exit-code","1","--python",str(HERE/"appearance/audit_appearance_wind_flag.py"),
            "--",str(args.out_root/"cases"),*[p["case_id"] for p in selected]])


def suite_manifest(args, selected, status, validation=None):
    records=[]
    for plan in selected:
        case=case_dir(args,plan["case_id"])
        record=copy.deepcopy(plan)
        record.update(case_dir=str(case),status=(validation or {}).get("cases",{}).get(plan["case_id"],{}).get("status",status))
        outputs={"video":"video.mp4","prompts":"prompts.json","scenario_overrides":"scenario_overrides.json",
                 "scenario_metadata":"scenario_metadata.json","ground_truth":"ground_truth.json","physics_edit":"physics_edit.json",
                 "simulation_cache":"simulation/genesis_flag_cache.npz","scene":"scene.blend"}
        record["outputs"]={k:str(case/v) for k,v in outputs.items() if (case/v).is_file()}
        records.append(record)
    write_json(args.out_root/"suite_manifest.json",{"schema_version":3,"suite_name":"pcve_wind_flag_suite","scene_id":"wind_flag",
        "interaction_category":"elastic_fluid","status":status,"baseline_physics":SPEC["physics"],"total_frames":96,
        "fps":24,"duration_sec":4,"resolution":[1280,720],"samples":64,"coupling":SPEC["coupling"],
        "asset_manifest":str(args.asset_dir/"asset_manifest.json"),"asset_manifest_sha256":digest(args.asset_dir/"asset_manifest.json"),
        "source":records[0],"edits":records[1:]})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root","--suite-root",dest="out_root",type=Path,default=ROOT/"renders/wind_flag/suite_build")
    p.add_argument("--stage",choices=("prepare","simulate","render","validate","all"),default="all")
    p.add_argument("--cases",nargs="+",choices=list(CASE_MAP),default=list(CASE_MAP))
    p.add_argument("--import-approved",action="store_true",help="Use hash-checked accepted caches and videos, with no resimulation or rerender")
    p.add_argument("--skip-existing",action="store_true")
    p.add_argument("--asset-dir",type=Path,default=ASSETS)
    p.add_argument("--render-assets",type=Path,default=ROOT/"assets/blenderkit/un_ceremonial_flag")
    p.add_argument("--ipc-deps",type=Path,default=RUNTIME_DEPS)
    p.add_argument("--python",default=sys.executable)
    p.add_argument("--blender",default=default_blender())
    p.add_argument("--gpu",default="auto")
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    if args.import_approved and args.stage not in ("all","prepare","validate"):
        p.error("--import-approved is for all/prepare/validate; use fresh output roots for recomputation")
    args.out_root=args.out_root.expanduser().resolve()
    args.asset_dir=args.asset_dir.expanduser().resolve()
    selected=[plan for plan in plans() if plan["case_id"]==SOURCE_ID or plan["case_id"] in args.cases]
    if args.dry_run:
        print(json.dumps({"stage":args.stage,"out_root":str(args.out_root),"import_approved":args.import_approved,
            "plans":selected,"commands":[sim_command(args,p) for p in selected if p["native_case"]!="wind_drop_at_2s"],
            "timed_continuation":"Source command additionally uses --emit-timed-branch --timed-branch-out <timed case>/simulation"},indent=2,ensure_ascii=False))
        return
    assets=read_json(args.asset_dir/"asset_manifest.json")
    assert assets["approved_material_edit_E_Pa"]==1e8
    assert digest(args.asset_dir/"initial_state.npz")==assets["initial_state_sha256"]
    prepare(args,selected)
    suite_manifest(args,selected,"prepared")
    if args.import_approved:
        import_approved(args,selected,assets)
    elif args.stage in ("simulate","all"):
        simulate(args,selected)
    metadata(args,selected)
    if not args.import_approved and args.stage in ("render","all"):
        for relative,expected in assets["external_assets"].items():
            render_relative=Path(relative).relative_to("assets/blenderkit/un_ceremonial_flag")
            assert digest(args.render_assets/render_relative)==expected,"Changed render asset: "+relative
        render(args,selected)
    if args.stage in ("all","validate"):
        audit(args,selected)
        result=validate(args.out_root,args.asset_dir,[plan["case_id"] for plan in selected])
        suite_manifest(args,selected,result["status"],result)
    else:
        suite_manifest(args,selected,"prepared" if args.stage=="prepare" else args.stage+"_completed")
    print("SUITE_MANIFEST",args.out_root/"suite_manifest.json",flush=True)


if __name__=="__main__":
    main()
