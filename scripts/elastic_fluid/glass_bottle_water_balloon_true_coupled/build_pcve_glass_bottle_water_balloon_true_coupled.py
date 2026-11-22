"""Public source/edit pipeline: prepare -> simulate -> surface -> render -> verify."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
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
from pathlib import Path
import sys
import time
from balloon_config import (HERE, STEM, SPEC, DEFAULT_OUT, READ_ONLY_OUTPUTS, SOURCE_CASE_ID, FIXED_SIM_ARGS,
    BASELINE_PHYSICS, KITCHEN, default_blender, read_json, write_json, ensure_json, run, digest, files_manifest, verify_files)
from edit_vocab import make_plans
from validate_glass_bottle_water_balloon_true_coupled import check_simulation, check_surfaces, validate_case, validate_suite

def select_plans(values):
    all_plans=make_plans()
    wanted={value for item in values for value in item.split(",")}
    unknown=wanted-{p["case_id"] for p in all_plans}-{"all"}
    if unknown:
        raise ValueError("Unknown case IDs: "+", ".join(sorted(unknown)))
    return [p for p in all_plans if "all" in wanted or p["case_id"]==SOURCE_CASE_ID or p["case_id"] in wanted]

def sim_command(args,plan,case):
    command=[args.python,str(HERE/("simulate_"+STEM+".py")),"--out",str(case/"sim"),*FIXED_SIM_ARGS,
        "--flow-l-min",str(plan["physics"]["flow_l_min"]),"--edge-stiffness",str(plan["physics"]["edge_stiffness"]),
        "--elastic-modulus-scale",str(plan["physics"]["elastic_modulus_scale"])]
    if plan["timed_edits"]:
        command += ["--timed-edits-json",str(case/"timed_edits.json")]
    return command

def surface_command(args,case):
    return [args.python,str(HERE/("surface_"+STEM+".py")),"--run",str(case/"sim"),"--out",str(case/"surfaces")]

def render_command(args,case):
    command=[args.python,str(HERE/("render_"+STEM+".py")),"--case-dir",str(case),
        "--blender",args.blender,"--kitchen",str(args.kitchen),"--gpu",args.gpu]
    if args.skip_existing:
        command.append("--skip-existing")
    return command

def prepare(root,selected):
    for plan in selected:
        case=root/"cases"/plan["case_id"]
        if plan["kind"]=="edit":
            prompt={"schema_version":2,**{key:copy.deepcopy(plan[key]) for key in
                ("case_id","source_case_id","edit_dsl","edit_summary","applies_from_frame","physics_diff","prompts")}}
            overrides=plan["scenario_override"]
        else:
            prompt={"schema_version":2,"case_id":plan["case_id"],"kind":"source","edit_dsl":None,
                "prompts":{"vague":{"zh":"厨房龙头向玻璃罐内的蓝色气球灌水。",
                    "en":"A kitchen tap fills a blue balloon inside a glass jar."},
                    "quantitative":{"zh":"从第 2 帧开始，以 4.5 L/min 向敞口气球灌水，乳胶边弹簧刚度为 25 N/m。",
                    "en":"From frame 2, pour 4.5 L/min into the open balloon, with 25 N/m latex edge stiffness."}}}
            overrides={}
        ensure_json(case/"prompts.json",prompt)
        ensure_json(case/"scenario_overrides.json",{"physics":overrides})
        ensure_json(case/"scene_spec.json",SPEC)
        if plan["timed_edits"]:
            ensure_json(case/"timed_edits.json",plan["timed_edits"])

def simulate(args,plan,case):
    receipt=case/"simulation_receipt.json"
    if args.skip_existing and receipt.exists():
        check_simulation(case,plan)
        verify_files(case/"sim",read_json(receipt)["files"])
        return read_json(receipt)["seconds"]
    seconds=run(sim_command(args,plan,case),case/"simulate.log")
    check_simulation(case,plan)
    write_json(receipt,{"files":files_manifest(case/"sim"),"physics":plan["physics"],"timed_edits":plan["timed_edits"],"seconds":seconds})
    return seconds

def surface(args,plan,case):
    check_simulation(case,plan)
    receipt=case/"surface_receipt.json"
    expected=digest(case/"sim/membrane.npz")
    if args.skip_existing and receipt.exists():
        previous=read_json(receipt)
        if previous["simulation_sha256"]!=expected:
            raise RuntimeError("Surface receipt references a different simulation")
        verify_files(case/"surfaces",previous["files"])
        check_surfaces(case)
        return previous["seconds"]
    seconds=run(surface_command(args,case),case/"surface.log")
    check_surfaces(case)
    write_json(receipt,{"simulation_sha256":expected,"files":files_manifest(case/"surfaces"),"seconds":seconds,
        "voxel_m":.0006,"inset_m":.001})
    return seconds

def metadata(case,plan):
    config=read_json(case/"sim/membrane.json")
    write_json(case/"scenario_metadata.json",{"schema_version":1,"scene_id":SPEC["scene_id"],"case_id":plan["case_id"],
        "material_revision":SPEC["material_revision"],
        "edit_catalog_revision":SPEC.get("edit_catalog_revision"),
        "physics":plan["physics"],"timed_edits":plan["timed_edits"],"actual_simulation_args":config["args"],
        "material_parameters":config.get("material_parameters"),
        "simulation_sha256":digest(case/"sim/membrane.npz"),"appearance":SPEC["render"],"solver":SPEC["solver"]})
    write_json(case/"ground_truth.json",{"schema_version":1,"units":"m, kg, s","frame_index_base":1,
        "fps":24,"frame_count":96,"sample_times_s":[i/24 for i in range(96)],
        "balloon":{"cache":"sim/membrane.npz","position_key":"trajectory","rest_key":"rest",
            "topology_key":"faces","pin_mask_key":"pinned","positions_are":"float32 vertex positions; velocities were not saved"},
        "water":{"cache":"sim/membrane.npz","height_key":"water_level","measurements":"sim/membrane.json",
            "surface_cache":"surfaces/water/water_<frame:04d>.npz"}})

def manifest(root,selected):
    records=[]
    statuses={}
    for plan in selected:
        case=root/"cases"/plan["case_id"]
        record=copy.deepcopy(plan)
        record.update(case_dir=str(case),outputs={key:str(case/relative) for key,relative in
            {"video":"video.mp4","prompts":"prompts.json","scenario_overrides":"scenario_overrides.json",
             "scenario_metadata":"scenario_metadata.json","ground_truth":"ground_truth.json","simulation":"sim/membrane.npz"}.items()
            if (case/relative).is_file()})
        records.append(record)
        if (case/"case_status.json").is_file():
            statuses[plan["case_id"]]=read_json(case/"case_status.json")
    write_json(root/"suite_manifest.json",{"schema_version":3,"scene_id":SPEC["scene_id"],"scene_version":SPEC["version"],
        "material_revision":SPEC["material_revision"],
        "edit_catalog_revision":SPEC.get("edit_catalog_revision"),
        "baseline_physics":BASELINE_PHYSICS,"source":records[0],"edits":records[1:],"case_status":statuses,
        "completed_case_ids":[key for key,value in statuses.items() if value.get("status")=="complete"],
        "all_cases_complete":len(statuses)==len(selected) and all(v.get("status")=="complete" for v in statuses.values()),
        "visual_review_required":True,"coupling":SPEC["solver"],"fps":24,"frames":96,"resolution":[1280,720],"samples":96})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root","--suite-root",type=Path,default=DEFAULT_OUT)
    p.add_argument("--stage",choices=("prepare","simulate","surface","render","validate","all"),default="all")
    p.add_argument("--cases",nargs="+",default=["all"],help="case IDs, comma-separated IDs or all; source is always included")
    p.add_argument("--python",default=sys.executable)
    p.add_argument("--blender",default=default_blender())
    p.add_argument("--kitchen",type=Path,default=KITCHEN)
    p.add_argument("--gpu",default="auto")
    p.add_argument("--skip-existing",action="store_true")
    p.add_argument("--dry-run",action="store_true",help="print commands only; do not create files or select a GPU")
    args=p.parse_args()
    args.out_root=args.out_root.expanduser().resolve()
    selected=select_plans(args.cases)
    if args.dry_run:
        print(json.dumps({"stage":args.stage,"out_root":str(args.out_root),"plans":selected,
            "commands":{plan["case_id"]:{"simulate":sim_command(args,plan,args.out_root/"cases"/plan["case_id"]),
                "surface":surface_command(args,args.out_root/"cases"/plan["case_id"]),
                "render":render_command(args,args.out_root/"cases"/plan["case_id"])} for plan in selected}},indent=2,ensure_ascii=False))
        return
    if args.stage=="validate":
        print(validate_suite(args.out_root,selected,write=False)["status"])
        return
    if any(args.out_root==root.resolve() or root.resolve() in args.out_root.parents for root in READ_ONLY_OUTPUTS):
        p.error("The original accepted suite is read-only; choose a fresh --out-root or --stage validate")
    prepare(args.out_root,selected)
    try:
        for plan in selected:
            case=args.out_root/"cases"/plan["case_id"]
            if args.stage in ("simulate","all"):
                simulate(args,plan,case)
            if args.stage in ("surface","all"):
                surface(args,plan,case)
            if (case/"sim/membrane.json").exists():
                metadata(case,plan)
            if args.stage in ("render","all"):
                run(render_command(args,case),case/f"render_driver_{time.time_ns()}.log")
                verified=validate_case(case,plan,args.out_root/"cases"/SOURCE_CASE_ID)
                write_json(case/"case_status.json",{"status":"complete","acceptance":verified["status"],"verification":verified})
        if args.stage=="all":
            validate_suite(args.out_root,selected,write=True)
    finally:
        manifest(args.out_root,selected)
    print("SUITE",args.out_root/"suite_manifest.json")

if __name__=="__main__":
    main()
