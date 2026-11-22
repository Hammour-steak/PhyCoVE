"""Write ground_truth_transforms.json for scarf_chair_slip cases from their native solver output.

Every per-frame value comes from the case's native libuipc cache (assets scenes/scarf_chair_slip/native/
<case>/cache.npz: times, positions and velocities of the scarf shell vertices, vertex_masses, rigid_names,
rigid_transforms and rigid_velocities) and its simulation_config.json. The chair's rest shape is the solver's
collision mesh (assets scenes/scarf_chair_slip/prepared_chair/chair_collision_closed.npz raised by the
layout's ground clearance), the book's rest shape is the configured box. The fixed camera is the one of the
current look (appearance/view.py). Nothing is authored.

Bodies: `cotton_scarf` (deformable shell; per frame its vertex centroid and bounds, mass centre and
mass-weighted velocity), `wooden_chair` and `hardcover_book` (affine rigid bodies; matrix_world is the native
transform applied to the body's world-placed rest geometry, location is the world position of the body's
volume centroid, linear_velocity that point's velocity) and the static `floor` (plane z = 0).

    python3 tools/export_ground_truth.py --case source --out OUT.json
    python3 tools/export_ground_truth.py --suite renders/pcve_suites/pcve_scarf_chair_slip_suite [--cases ...]

The files are written in the pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py): the native record above,
converted without resampling; rigid bodies are located at their volume centroid, the scarf at its vertex centroid,
and the floor is left out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR / "appearance"), str(CASE_DIR.parents[1])]

from scene_paths import ASSETS, CASES, CATALOG, NATIVE  # noqa: E402
from view import CAMERA  # noqa: E402
from pcve_ground_truth import from_schema3, write  # noqa: E402

SCENE = "scarf_chair_slip"
WIDTH, HEIGHT = 1280, 720
NAMES = {"chair": "wooden_chair", "landing_book": "hardcover_book"}


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def camera() -> np.ndarray:
    """Camera matrix_world as Blender builds it: -Z towards the target, +Y as close to world +Z as possible."""
    location = np.asarray(CAMERA["location_m"], float)
    forward = np.asarray(CAMERA["target_m"], float) - location
    z = -forward / np.linalg.norm(forward)
    x = np.cross([0.0, 0.0, 1.0], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    matrix = np.eye(4)
    matrix[:3, 0], matrix[:3, 1], matrix[:3, 2], matrix[:3, 3] = x, y, z, location
    return matrix


def volume_centroid(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tri = vertices[faces]
    volume = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    return (volume[:, None] * tri.sum(axis=1) / 4.0).sum(axis=0) / volume.sum()


def chair_dimensions(layout: dict) -> list:
    """Axis-aligned extent of the chair collision mesh."""
    with np.load(ASSETS / layout["chair_geometry_dir"] / layout["chair_collision_file"]) as chair:
        vertices = chair["vertices"].astype(float)
    return (vertices.max(axis=0) - vertices.min(axis=0)).tolist()


def rest_centroids(config: dict) -> dict:
    layout, physics = config["layout"], config["physics"]
    result = {}
    with np.load(ASSETS / layout["chair_geometry_dir"] / layout["chair_collision_file"]) as chair:
        vertices = chair["vertices"].astype(float).copy()
        vertices[:, 2] += layout["chair_ground_clearance"]
        result["chair"] = volume_centroid(vertices, chair["faces"])
    result["landing_book"] = np.asarray(physics["book_location"], float)
    return result


def native_record(native: Path) -> dict:
    """Per-frame native record of one case (the input of pcve_ground_truth.from_schema3)."""
    config = json.loads((native / "simulation_config.json").read_text(encoding="utf-8"))
    with np.load(native / "cache.npz") as archive:
        cache = {key: archive[key] for key in archive.files}
    times = cache["times"]
    if config["scene_id"] != SCENE or len(times) != 96:
        raise ValueError(f"Not a 96-sample {SCENE} solve: {native}")
    physics, layout = config["physics"], config["layout"]
    matrix = camera()
    lens, sensor = CAMERA["lens_mm"], CAMERA["sensor_width_mm"]
    focal = lens / sensor * WIDTH
    names = cache["rigid_names"].tolist()
    centroids = rest_centroids(config)
    masses = cache["vertex_masses"].astype(float)
    objects = {
        "cotton_scarf": dict(present=True, deformable=True, mass=float(masses.sum()),
                             material_size_m=[layout["width"], config["material_length_m"]],
                             thickness_m=physics["scarf_thickness"],
                             surface_vertex_count=int(cache["positions"].shape[1]),
                             surface_fields="surface_centroid / surface_bbox_min / surface_bbox_max: mean and "
                             "axis-aligned bounds of the simulated scarf shell vertices (cache.npz positions, body and "
                             "fringe); center_of_mass / linear_velocity: vertex_masses-weighted, world metres and m/s"),
        "wooden_chair": (dict(present=True, deformable=False, mass=physics["chair_mass"])
                         if "chair" in names else dict(present=False, deformable=False)),
        "floor": dict(present=True, deformable=False, static=True, plane="z = 0"),
    }
    if "landing_book" in names:
        objects["hardcover_book"] = dict(present=True, deformable=False, mass=physics["book_mass"],
                                         dimensions_m=physics["book_dimensions"])
    gt = dict(schema_version=3, scene_id=SCENE, interaction_category="rigid_elastic", case_id=config["case_id"],
              fps=24, resolution=[WIDTH, HEIGHT], frame_start=1, frame_end=len(times),
              camera=dict(matrix_world=matrix.tolist(),
                          intrinsics=[[focal, 0, WIDTH / 2], [0, focal, HEIGHT / 2], [0, 0, 1]],
                          lens_mm=lens, sensor_width_mm=sensor, sensor_fit="HORIZONTAL", shift=list(CAMERA["shift"]),
                          location_m=list(CAMERA["location_m"]), target_m=list(CAMERA["target_m"]),
                          trajectory="fixed"),
              objects=objects, units="metres, seconds, kilograms; Z up",
              source=dict(native_cache=f"native/{config['case_id']}/cache.npz", solver=config["solver"]),
              frames=[])
    for i, t in enumerate(times):
        x = cache["positions"][i]
        v = cache["velocities"][i]
        frame_objects = {
            "cotton_scarf": dict(present=True, deformable=True, deformation_frame_index=i,
                                 matrix_world=np.eye(4).tolist(),
                                 surface_centroid=x.mean(axis=0).tolist(),
                                 surface_bbox_min=x.min(axis=0).tolist(),
                                 surface_bbox_max=x.max(axis=0).tolist(),
                                 center_of_mass=(masses @ x / masses.sum()).tolist(),
                                 linear_velocity=(masses @ v / masses.sum()).tolist()),
            "floor": dict(present=True, deformable=False, matrix_world=np.eye(4).tolist()),
        }
        for name in names:
            k = names.index(name)
            T = cache["rigid_transforms"][i, k]
            V = cache["rigid_velocities"][i, k]
            point = np.append(centroids[name], 1.0)
            frame_objects[NAMES[name]] = dict(present=True, deformable=False, matrix_world=T.tolist(),
                                              location=(T @ point)[:3].tolist(),
                                              linear_velocity=(V @ point)[:3].tolist())
        if "chair" not in names:
            frame_objects["wooden_chair"] = dict(present=False, deformable=False)
        gt["frames"].append(dict(frame_index=i + 1, time_sec=float(t), camera_matrix_world=matrix.tolist(),
                                 objects=frame_objects))
    return gt


def ground_truth(native: Path, case: str) -> dict:
    """pcve_ground_truth/1 record of one case: the native record converted without resampling."""
    layout = json.loads((native / "simulation_config.json").read_text(encoding="utf-8"))["layout"]
    chair = (chair_dimensions(layout), "chair collision mesh bounding box (assets/scenes/scarf_chair_slip/"
             f"{layout['chair_geometry_dir']}/{layout['chair_collision_file']})")
    return from_schema3(native_record(native), SCENE, CATALOG[case], skip=["floor"], sizes={"wooden_chair": chair},
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
