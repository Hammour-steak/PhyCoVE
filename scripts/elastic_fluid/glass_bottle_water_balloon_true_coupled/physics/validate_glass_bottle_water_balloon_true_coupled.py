"""Read-only validation of actual simulation, surfaces, annotations and videos."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from balloon_config import SIM_PRESET, SOURCE_CASE_ID, READ_ONLY_OUTPUTS, digest, read_json, write_json, verify_files
from simulate_glass_bottle_water_balloon_true_coupled import elastic_coefficients
from edit_vocab import make_plans
from render_glass_bottle_water_balloon_true_coupled import verify_video

def check_simulation(case,plan):
    config=read_json(case/"sim/membrane.json")
    expected={**SIM_PRESET,**plan["physics"]}
    read_only=any(p.resolve()==case.resolve() or p.resolve() in case.resolve().parents for p in READ_ONLY_OUTPUTS)
    if read_only and "water_retention" not in config["args"]:
        expected.pop("water_retention")
    for key,value in expected.items():
        actual=config["args"].get(key,1.0 if key=="elastic_modulus_scale" else None)
        if actual!=value:
            raise RuntimeError(f"{plan['case_id']}: actual simulation {key}={config['args'].get(key)}; expected {value}")
    if "elastic_modulus_scale" in config["args"]:
        coefficients=elastic_coefficients(SimpleNamespace(**expected))
        if config.get("material_parameters")!=coefficients:
            raise RuntimeError("Resolved elastic coefficients do not match the uniform modulus scale")
    if config["rows"] and "poured_ml" in config["rows"][0]:
        previous_spill=0.0
        for row in config["rows"]:
            if abs(row["poured_ml"]-row["water_ml"]-row["spilled_ml"])>1e-7:
                raise RuntimeError("Poured water != retained water + cumulative overflow")
            if row["spilled_ml"]<previous_spill-1e-7 or row["water_ml"]<0 or row["capacity_ml"]<0:
                raise RuntimeError("Invalid water/overflow balance")
            previous_spill=row["spilled_ml"]
            if config["args"].get("water_retention")=="retain_all":
                if row["spilled_ml"]!=0.0 or abs(row["poured_ml"]-row["water_ml"])>1e-7:
                    raise RuntimeError("No-overflow model discarded injected water")
                if row["retention_capacity_deficit_ml"]>0.1:
                    raise RuntimeError("Retained water does not fit the deformed membrane within 0.1 mL tolerance")
    timed_path=config["args"]["timed_edits_json"]
    if bool(timed_path)!=bool(plan["timed_edits"]):
        raise RuntimeError("Actual timed schedule missing or unexpected")
    if timed_path and read_json(Path(timed_path))!=plan["timed_edits"]:
        raise RuntimeError("Actual timed schedule differs from the edit plan")
    with np.load(case/"sim/membrane.npz") as cache:
        trajectory=cache["trajectory"]
        if len(trajectory)!=96 or not np.isfinite(trajectory).all() or len(config["rows"])!=96:
            raise RuntimeError("Incomplete/nonfinite physical trajectory")
        pinned=cache["pinned"]
        if not np.array_equal(trajectory[:,pinned],np.broadcast_to(cache["rest"][pinned],trajectory[:,pinned].shape)):
            raise RuntimeError("Pinned membrane vertices moved")
        if len(cache["water_level"])!=96 or not np.isfinite(cache["water_level"]).all():
            raise RuntimeError("Invalid physical water levels")
    return config

def check_surfaces(case):
    surface=read_json(case/"surfaces/surface_report.json")
    if [r["frame"] for r in surface["water"]]!=list(range(1,97)) or surface["frames_with_water_outside_latex"]:
        raise RuntimeError("Missing surface frames or reported water outside latex")
    with np.load(case/"sim/membrane.npz") as sim, np.load(case/"surfaces/balloon_visual.npz") as visual:
        if not np.array_equal(sim["trajectory"],visual["outer_vertices"]) or not np.array_equal(sim["faces"],visual["outer_faces"]):
            raise RuntimeError("Displayed latex does not match the physical cache")
        if not np.array_equal(sim["water_level"].astype(np.float32),np.load(case/"surfaces/water_level.npy")):
            raise RuntimeError("Displayed water level differs from the simulation")
    for row in surface["water"]:
        with np.load(case/"surfaces/water"/f"water_{row['frame']:04d}.npz") as water:
            if not np.isfinite(water["vertices"]).all() or len(water["vertices"])!=row["water_vertices"]:
                raise RuntimeError("Invalid water surface cache")
        if row["water_vertices_outside_latex"] or row["max_signed_distance_to_latex_mm"]>0:
            raise RuntimeError("Water containment report failed")
    return surface

def validate_case(case,plan,source_case=None):
    case=Path(case)
    sim=check_simulation(case,plan)
    surface=check_surfaces(case)
    if plan["timed_edits"] and source_case is not None:
        prefix=plan["timed_edits"][0]["frame"]-1
        with np.load(case/"sim/membrane.npz") as edited, np.load(Path(source_case)/"sim/membrane.npz") as source:
            for key in ("trajectory","water_level"):
                if not np.array_equal(edited[key][:prefix],source[key][:prefix]):
                    raise RuntimeError("Timed edit changed states before its intervention")
    probe=verify_video(case/"video.mp4")
    if sim["args"].get("water_retention")=="retain_all":
        proxy=case/"render/overflow_visualization.json"
        if not proxy.is_file():
            raise RuntimeError("Missing explicit no-overflow rendering receipt")
        proxy_report=read_json(proxy)
        if not proxy_report.get("disabled") or proxy_report["object_count"]!=0:
            raise RuntimeError("Unexpected exterior water objects in a retain-all case")
    if max(r["spilled_ml"] for r in sim["rows"])>1e-3:
        overflow=read_json(case/"render/overflow_visualization.json")
        if len(overflow["rows"])!=96 or overflow["object_count"]==0:
            raise RuntimeError("Discharged water has no overflow visualization")
        for physical,shown in zip(sim["rows"],overflow["rows"]):
            if abs(physical["spilled_ml"]*1e-6-shown["spilled_m3"])>1e-10:
                raise RuntimeError("Displayed overflow does not match the discharge records")
            if abs(shown["on_jar_m3"]+shown["puddle_m3"]-shown["spilled_m3"])>1e-10:
                raise RuntimeError("Overflow transit/collection ledger is not conservative")
            if shown["puddle_m3"]>1e-9 and abs(shown["measured_puddle_mesh_m3"]-shown["puddle_m3"])>1e-8:
                raise RuntimeError("Collected-water display volume differs from the ledger")
    receipt=case/"render_receipt.json"
    if receipt.exists():
        r=read_json(receipt)
        if r["video_sha256"]!=digest(case/"video.mp4") or r["inputs"]["simulation_sha256"]!=digest(case/"sim/membrane.npz"):
            raise RuntimeError("Render receipt does not match the physical/video data")
        verify_files(case/"surfaces",r["inputs"]["surface_files"])
        verify_files(case/"render",r["render_files"])
    nonempty=[r for r in surface["water"] if r["water_vertices"]]
    return {"status":"technical_checks_passed_visual_review_required","video_sha256":digest(case/"video.mp4"),
        "simulation_sha256":digest(case/"sim/membrane.npz"),"probe":probe,"water_inside_latex_all_reported_frames":True,
        "closest_reported_water_to_latex_mm":max((r["max_signed_distance_to_latex_mm"] for r in nonempty),default=None),
        "actual_physics":plan["physics"],"actual_timed_edits":plan["timed_edits"],"last_measurement":sim["rows"][-1]}

def validate_suite(root,selected=None,write=False):
    root=Path(root)
    selected=selected or make_plans()
    read_only=any(root.resolve()==p.resolve() for p in READ_ONLY_OUTPUTS) and (root/"suite_manifest.json").is_file()
    if read_only:
        if write:
            raise RuntimeError("Accepted outputs are read-only")
        manifest=read_json(root/"suite_manifest.json")
        ids={p["case_id"] for p in selected}
        selected=[p for p in [manifest["source"],*manifest["edits"]] if p["case_id"] in ids]
    results={p["case_id"]:validate_case(root/"cases"/p["case_id"],p,root/"cases"/SOURCE_CASE_ID) for p in selected}
    result={"status":"technical_checks_passed_visual_review_required","cases":results,"read_only_accepted_outputs":read_only,
        "limits":["Water is a solved incompressible volume/hydrostatic load, not a particle-based Navier-Stokes/CFD solver.",
            "The displayed free-fall stream is geometric, with no resolved impact splashes.",
            "Reorganization and technical checks do not constitute a new visual/experimental acceptance."]}
    if write:
        write_json(root/"validation.json",result)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite-root","--out-root",type=Path,required=True)
    p.add_argument("--out-json",type=Path,help="optional explicit report destination; default is read-only")
    args=p.parse_args()
    result=validate_suite(args.suite_root)
    if args.out_json:
        write_json(args.out_json,result)
    print({"status":result["status"],"case_ids":list(result["cases"])})

if __name__=="__main__":
    main()
