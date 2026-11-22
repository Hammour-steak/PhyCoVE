"""Write ground_truth_transforms.json for gym_landing_mat cases from their native solver output.

Every per-frame value comes from the native libuipc cache of the case (cache.npz:
times, body_transforms/body_velocities, cloth_positions, obstacle_transforms/
obstacle_velocities) and its simulation_config.json; the fixed camera and the
static object records come from the case's reference render
(ground_truth_transforms.json beside the accepted render), whose camera the
current look keeps unchanged. Nothing is authored.

The native record has the layout appearance/render_replay.py writes, plus three
per-frame fields for the deformable landing mat, measured on the simulated
cover-shell vertices: surface_centroid, surface_bbox_min, surface_bbox_max. The
files are written in the pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py),
converted from that record without resampling.

    python3 tools/export_ground_truth.py --case source --out OUT.json
    python3 tools/export_ground_truth.py --case add_path_obstacle --simulation SIM_DIR --reference-main MAIN_DIR --out OUT.json
    python3 tools/export_ground_truth.py --all --suite renders/pcve_suites/pcve_gym_landing_mat_suite
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]

from scene_inputs import CASES, accepted_case, reference_main  # noqa: E402
from pcve_ground_truth import from_schema3, write  # noqa: E402

CATALOG = {case: "source" if case == "source" else "edit_" + case for case in CASES}


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def native_record(simulation: Path, reference: Path) -> dict:
    """Per-frame native record of one case (the input of pcve_ground_truth.from_schema3)."""
    config = json.loads((simulation / "simulation_config.json").read_text(encoding="utf-8"))
    with np.load(simulation / "cache.npz") as archive:
        cache = {key: archive[key] for key in archive.files}
    if config["scene_id"] != "gym_landing_mat" or len(cache["times"]) != 96:
        raise ValueError(f"Not a 96-sample gym_landing_mat solve: {simulation}")
    gt = json.loads((reference / "ground_truth_transforms.json").read_text(encoding="utf-8"))
    camera = np.asarray(gt["camera"]["matrix_world"], dtype=float)
    active = bool(config["physics"]["active"][0])
    mat = bool(config["physics"]["active"][1])  # False when the landing mat is deleted (no foam core, no cover)
    obstacle = bool(cache["path_obstacle_present"][0])
    gt["frames"] = []
    gt["objects"]["medicine_ball"]["mass"] = config["physics"]["body_mass"]
    gt["objects"]["medicine_ball"]["present"] = active
    if mat:
        gt["objects"]["landing_mat"]["surface_vertex_count"] = int(cache["cloth_positions"].shape[1])
        gt["objects"]["landing_mat"]["surface_fields"] = (
            "surface_centroid / surface_bbox_min / surface_bbox_max: mean and axis-aligned bounds of the "
            "simulated cover-shell vertices (cache.npz cloth_positions), world metres")
    else:
        gt["objects"]["landing_mat"] = {k: v for k, v in gt["objects"]["landing_mat"].items()
                                        if k not in ("dimensions", "dimensions_m", "rest_dimensions_m", "envelope_m")}
        gt["objects"]["landing_mat"]["present"] = False
    for i, t in enumerate(cache["times"]):
        surface = cache["cloth_positions"][i]
        frame = dict(frame_index=i + 1, time_sec=float(t), camera_matrix_world=camera.tolist(), objects={
            "medicine_ball": dict(present=active, matrix_world=cache["body_transforms"][i].tolist(),
                                  location=cache["body_transforms"][i, :3, 3].tolist(),
                                  linear_velocity=cache["body_velocities"][i, :3, 3].tolist()),
            "landing_mat": dict(present=True, deformable=True, deformation_frame_index=i,
                                matrix_world=np.eye(4).tolist(),
                                surface_centroid=surface.mean(axis=0).tolist(),
                                surface_bbox_min=surface.min(axis=0).tolist(),
                                surface_bbox_max=surface.max(axis=0).tolist())
                           if mat else dict(present=False, deformable=True)})
        if obstacle:
            frame["objects"]["gym_water_bottle"] = dict(
                present=True, deformable=False, matrix_world=cache["obstacle_transforms"][i].tolist(),
                location=cache["obstacle_transforms"][i, :3, 3].tolist(),
                linear_velocity=cache["obstacle_velocities"][i, :3, 3].tolist())
        gt["frames"].append(frame)
    if len(gt["frames"]) != gt["frame_end"] - gt["frame_start"] + 1:
        raise ValueError("Frame count differs from the declared frame range")
    return gt


def ground_truth(simulation: Path, reference: Path, case: str) -> dict:
    """pcve_ground_truth/1 record of one case: the native record converted without resampling."""
    specs = json.loads((CASE_DIR / "physics/scene_specs.json").read_text(encoding="utf-8"))["gym_landing_mat"]["physics"]
    bottle = specs["gym_water_bottle_radius"] * 2
    sizes = {"medicine_ball": ({"radius": specs["body_radius"]}, "physics/scene_specs.json body_radius"),
             "gym_water_bottle": ([bottle, bottle, specs["gym_water_bottle_length"]],
                                  "physics/scene_specs.json gym_water_bottle_radius/length")}
    return from_schema3(native_record(simulation, reference), "gym_landing_mat", CATALOG.get(case, "edit_" + case), sizes=sizes,
                        tool="scripts/rigid_elastic/gym_landing_mat/tools/export_ground_truth.py",
                        files=[simulation / "cache.npz", simulation / "simulation_config.json",
                               reference / "ground_truth_transforms.json"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--all", action="store_true", help="every case, into --suite cases/<catalog id>/")
    parser.add_argument("--simulation", type=Path, help="native output dir (default: accepted delivery)")
    parser.add_argument("--reference-main", type=Path, help="reference render dir with the camera record")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--suite", type=Path)
    args = parser.parse_args()
    if args.all == bool(args.case):
        parser.error("give --case or --all")
    if args.all:
        if not args.suite:
            parser.error("--all needs --suite")
        for case in CASES:
            target = args.suite / "cases" / CATALOG[case] / "ground_truth_transforms.json"
            write(target, ground_truth(accepted_case(case) / "simulation", reference_main(case), case))
            print("wrote", target)
        return
    if not args.out:
        parser.error("--case needs --out")
    write(args.out, ground_truth(args.simulation or accepted_case(args.case) / "simulation",
                                 args.reference_main or reference_main(args.case), args.case))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
