"""Write ground_truth_transforms.json for cabinet_towel_pinch cases from their native solver output.

Every per-frame value comes from the case's native libuipc cache (assets scenes/cabinet_towel_pinch/
native/<case>/cache.npz: times, positions and velocities of the towel shell vertices, vertex_masses,
rigid_names, rigid_transforms and rigid_velocities) and its simulation_config.json; rigid body shapes
come from <body>_geometry.npz beside the cache. The fixed camera is the one of the saved scenes
(appearance/render_view.camera_for(LAYOUT): location, target, 29.5 mm lens on a 36 mm sensor),
which the current look keeps unchanged. Nothing is authored.

Bodies: `cotton_hand_towel` (deformable shell; per frame its vertex centroid and bounds, mass centre
and mass-weighted velocity), `cabinet_door` and `doorstop` (affine rigid bodies; matrix_world is the
native transform applied to the body's world-placed rest geometry, location is the world position of
the body's volume centroid, linear_velocity that point's velocity, and the door adds its hinge angle),
and the fixed `cabinet` carcass.

    python3 tools/export_ground_truth.py --case source --out OUT.json
    python3 tools/export_ground_truth.py --suite renders/pcve_suites/pcve_cabinet_towel_pinch_suite [--cases ...]

The files are written in the pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py): the native record above,
converted without resampling; rigid bodies are located at their volume centroid, the towel at its vertex centroid,
and the fixed carcass is left out.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]

from scene_paths import CASES, CATALOG, NATIVE  # noqa: E402
from pcve_ground_truth import from_schema3, write  # noqa: E402

SCENE = "cabinet_towel_pinch"
WIDTH, HEIGHT, SENSOR_MM = 1280, 720, 36.0
NAMES = {"door": "cabinet_door", "doorstop": "doorstop", "cabinet": "cabinet"}


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def camera(layout: dict) -> tuple[np.ndarray, float]:
    """Camera matrix_world as Blender builds it: -Z towards the target, +Y as close to world +Z as possible."""
    sys.path.insert(0, str(CASE_DIR / "appearance"))
    from render_view import camera_for
    view = camera_for(layout)
    location = np.asarray(view["location_m"], float)
    forward = np.asarray(view["target_m"], float) - location
    z = -forward / np.linalg.norm(forward)
    x = np.cross([0.0, 0.0, 1.0], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    matrix = np.eye(4)
    matrix[:3, 0], matrix[:3, 1], matrix[:3, 2], matrix[:3, 3] = x, y, z, location
    return matrix, float(view["lens_mm"])


def volume_centroid(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tri = vertices[faces]
    volume = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    return (volume[:, None] * tri.sum(axis=1) / 4.0).sum(axis=0) / volume.sum()


def native_record(native: Path) -> dict:
    """Per-frame native record of one case (the input of pcve_ground_truth.from_schema3)."""
    config = json.loads((native / "simulation_config.json").read_text(encoding="utf-8"))
    with np.load(native / "cache.npz") as archive:
        cache = {key: archive[key] for key in archive.files}
    times = cache["times"]
    if config["scene_id"] != SCENE or len(times) != 96:
        raise ValueError(f"Not a 96-sample {SCENE} solve: {native}")
    physics = config["physics"]
    matrix, lens = camera(config["layout"])
    focal = lens / SENSOR_MM * WIDTH
    names = cache["rigid_names"].tolist()
    centroids = {}
    for name in names:
        with np.load(native / f"{name}_geometry.npz") as geometry:
            centroids[name] = volume_centroid(geometry["vertices"], geometry["faces"])
    masses = cache["vertex_masses"].astype(float)
    towel_present = bool(physics.get("towel_present", [1])[0])   # DELETE towel: absent in every frame
    objects = {
        "cotton_hand_towel": dict(present=False, deformable=True) if not towel_present else
                             dict(present=True, deformable=True, mass=float(masses.sum()),
                                  surface_vertex_count=int(cache["positions"].shape[1]),
                                  surface_fields="surface_centroid / surface_bbox_min / surface_bbox_max: mean and "
                                  "axis-aligned bounds of the simulated towel shell vertices (cache.npz positions); "
                                  "center_of_mass / linear_velocity: vertex_masses-weighted, world metres and m/s"),
        "cabinet": dict(present=True, deformable=False, static=True),
    }
    if "door" in names:
        objects["cabinet_door"] = dict(present=True, deformable=False, mass=physics["door_mass"],
                                       hinge_axis="vertical line x = 0, y = %g m" % config["layout"]["hinge_axis_y"])
    else:
        objects["cabinet_door"] = dict(present=False, deformable=False)
    if "doorstop" in names:
        objects["doorstop"] = dict(present=True, deformable=False, mass=physics["stop_mass"])
    gt = dict(schema_version=3, scene_id=SCENE, interaction_category="rigid_elastic", case_id=config["case_id"],
              fps=24, resolution=[WIDTH, HEIGHT], frame_start=1, frame_end=len(times),
              camera=dict(matrix_world=matrix.tolist(),
                          intrinsics=[[focal, 0, WIDTH / 2], [0, focal, HEIGHT / 2], [0, 0, 1]],
                          lens_mm=lens, sensor_width_mm=SENSOR_MM, shift=[0.0, 0.0], trajectory="fixed"),
              objects=objects, units="metres, seconds, kilograms",
              source=dict(native_cache=f"native/{config['case_id']}/cache.npz", solver=config["solver"]),
              frames=[])
    for i, t in enumerate(times):
        x = cache["positions"][i]
        v = cache["velocities"][i]
        frame_objects = {
            "cotton_hand_towel": dict(present=False, deformable=True) if not towel_present else
                                 dict(present=True, deformable=True, deformation_frame_index=i,
                                      matrix_world=np.eye(4).tolist(),
                                      surface_centroid=x.mean(axis=0).tolist(),
                                      surface_bbox_min=x.min(axis=0).tolist(),
                                      surface_bbox_max=x.max(axis=0).tolist(),
                                      center_of_mass=(masses @ x / masses.sum()).tolist(),
                                      linear_velocity=(masses @ v / masses.sum()).tolist()),
            "cabinet": dict(present=True, deformable=False, matrix_world=np.eye(4).tolist()),
        }
        for name in names:
            if name not in ("door", "doorstop"):
                continue
            k = names.index(name)
            T = cache["rigid_transforms"][i, k]
            V = cache["rigid_velocities"][i, k]
            point = np.append(centroids[name], 1.0)
            row = dict(present=True, deformable=False, matrix_world=T.tolist(), location=(T @ point)[:3].tolist(),
                       linear_velocity=(V @ point)[:3].tolist())
            if name == "door":
                row["hinge_angle_rad"] = math.atan2(T[1, 0], T[0, 0])
            frame_objects[NAMES[name]] = row
        if "door" not in names:
            frame_objects["cabinet_door"] = dict(present=False, deformable=False)
        gt["frames"].append(dict(frame_index=i + 1, time_sec=float(t), camera_matrix_world=matrix.tolist(),
                                 objects=frame_objects))
    return gt


def ground_truth(native: Path, case: str) -> dict:
    """pcve_ground_truth/1 record of one case: the native record converted without resampling."""
    layout = json.loads((native / "simulation_config.json").read_text(encoding="utf-8"))["layout"]
    door = ([layout["door_width"], layout["door_thickness"], layout["door_height"]],
            "door_width/door_thickness/door_height of the native simulation_config.json layout")
    sizes = {"cabinet_door": door}
    physics = json.loads((native / "simulation_config.json").read_text(encoding="utf-8"))["physics"]
    if not physics.get("towel_present", [1])[0]:
        with np.load(native / "cache.npz") as archive:
            x = archive["positions"][0]
        sizes["cotton_hand_towel"] = ((x.max(0) - x.min(0)).tolist(),
                                      "bounding box of the towel's pre-settled seed shape (the towel is absent in this case)")
    return from_schema3(native_record(native), SCENE, CATALOG.get(case, "edit_" + case), skip=["cabinet"], sizes=sizes,
                        tool=f"scripts/rigid_elastic/{SCENE}/tools/export_ground_truth.py",
                        files=[native / "cache.npz", native / "simulation_config.json"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--native", type=Path, help="native output dir (default: the accepted native state of --case)")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--suite", type=Path, help="write cases/<catalog id>/ground_truth_transforms.json in this suite")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    if args.suite:
        for case in args.cases:
            target = args.suite / "cases" / CATALOG[case] / "ground_truth_transforms.json"
            write(target, ground_truth(NATIVE / case, case))
            print("wrote", target)
        return
    if not (args.case and args.out):
        parser.error("give --case and --out, or --suite")
    write(args.out, ground_truth(args.native or NATIVE / args.case, args.case))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
