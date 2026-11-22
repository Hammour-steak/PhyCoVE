"""Write ground_truth_transforms.json for silicone_bag_can cases from their native solver output.

Every per-frame value comes from the case's native libuipc cache (assets scenes/silicone_bag_can/native/<case>/
simulation.npz: times, bag_positions, bag_velocities, bag_rest_positions, bag_faces, bag_vertex_thickness_m,
rigid_body_ids, can_transforms, can_velocities, can_vertices, can_faces) and its simulation_config.json. The
fixed camera is the one recorded in the render reports of the stored delivery (camera_matrix, camera_lens_mm,
photography.sensor_width_mm; identical in all six cases, no lens shift), which the current look keeps unchanged
(appearance/realism.py asserts it). Nothing is authored.

Bodies: `silicone_bag` (deformable NeoHookean shell; per frame its vertex centroid and bounds, centre of mass and
mass-weighted velocity, with the solver's lumped vertex masses: rest triangle area x mean local wall thickness x
density / 3), `metal_can` and, in add_second_can, `second_metal_can` (affine rigid bodies; matrix_world is the
native transform of the can, whose rest mesh is centred on its origin, location the world position of its volume
centroid, linear_velocity that point's velocity and angular_velocity from the rotational part of the native
transform rate). The bag hangs from two fixed hooks; video frame i (1..96) is native state i-1 at t = (i-1)/24 s.

    python3 tools/export_ground_truth.py --case source --out OUT.json
    python3 tools/export_ground_truth.py --suite renders/pcve_suites/pcve_silicone_bag_can_suite [--cases ...]

The files are written in the pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py): the native record above,
converted without resampling; the cans are located at their volume centroid and the bag at its vertex centroid.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]

from scene_paths import CASES, CATALOG, DELIVERY, NATIVE, SCENE_ID  # noqa: E402
from pcve_ground_truth import from_schema3, write  # noqa: E402

WIDTH, HEIGHT = 1280, 720
NAMES = {"can": "metal_can", "second_can": "second_metal_can"}


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def camera() -> dict:
    """The fixed camera of the accepted render reports (the same matrix and lens in every case)."""
    rows = [json.loads((DELIVERY / "cases" / case / "render_report.json").read_text(encoding="utf-8")) for case in CASES]
    first = rows[0]
    for row in rows[1:]:
        if row["camera_matrix"] != first["camera_matrix"] or row["camera_lens_mm"] != first["camera_lens_mm"]:
            raise ValueError("The accepted render reports disagree on the camera")
    lens = float(first["camera_lens_mm"])
    sensor = float(first["photography"]["sensor_width_mm"])
    focal = lens / sensor * WIDTH
    return dict(matrix_world=first["camera_matrix"], intrinsics=[[focal, 0, WIDTH / 2], [0, focal, HEIGHT / 2], [0, 0, 1]],
                lens_mm=lens, sensor_width_mm=sensor, sensor_fit="horizontal", shift=[0.0, 0.0],
                clip_start_m=0.1, trajectory="fixed")


def volume_centroid(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tri = vertices[faces]
    volume = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    return (volume[:, None] * tri.sum(axis=1) / 4.0).sum(axis=0) / volume.sum()


def lumped_masses(cache: dict, density: float) -> np.ndarray:
    """Vertex masses exactly as physics/solver.py lumps them."""
    rest, faces, thickness = cache["bag_rest_positions"], cache["bag_faces"], cache["bag_vertex_thickness_m"]
    q = rest[faces]
    area = 0.5 * np.linalg.norm(np.cross(q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]), axis=1)
    masses = np.zeros(len(rest))
    np.add.at(masses, faces.ravel(), np.repeat(area * thickness[faces].mean(axis=1) * density / 3, 3))
    return masses


def angular_velocity(T: np.ndarray, V: np.ndarray) -> list:
    """Skew part of dR/dt R^T for an affine body (its 3x3 block is a rotation up to solver tolerance)."""
    W = V[:3, :3] @ np.linalg.inv(T[:3, :3])
    W = 0.5 * (W - W.T)
    return [float(W[2, 1]), float(W[0, 2]), float(W[1, 0])]


def native_record(native: Path) -> dict:
    """Per-frame native record of one case (the input of pcve_ground_truth.from_schema3)."""
    config = json.loads((native / "simulation_config.json").read_text(encoding="utf-8"))
    with np.load(native / "simulation.npz") as archive:
        cache = {key: archive[key] for key in archive.files}
    times = cache["times"]
    if len(times) != 97 or not np.allclose(times, np.arange(97) / 24, atol=1e-12):
        raise ValueError(f"Not a 97-state, 24 Hz silicone_bag_can solve: {native}")
    physics = config["physics"]
    case = config["case"]
    ids = [str(x) for x in cache["rigid_body_ids"]]
    centroid = volume_centroid(cache["can_vertices"], cache["can_faces"])
    bag = cache["bag_positions"].shape[1] > 0
    objects = {}
    if bag:
        masses = lumped_masses(cache, physics["bag_density_kg_m3"])
        if abs(masses.sum() - config["bag_mass_kg"]) > 1e-9:
            raise ValueError("Lumped bag mass differs from the solver's record")
        objects["silicone_bag"] = dict(
            present=True, deformable=True, mass=float(masses.sum()), surface_vertex_count=int(cache["bag_positions"].shape[1]),
            young_modulus_pa=physics["bag_young_modulus_pa"], wall_thickness_m=physics["bag_thickness_m"],
            handle_thickness_m=physics["bag_handle_thickness_m"], fixed_vertex_count=int(cache["bag_fixed_mask"].sum()),
            surface_fields="surface_centroid / surface_bbox_min / surface_bbox_max: mean and axis-aligned bounds of the "
                           "simulated shell vertices (simulation.npz bag_positions); center_of_mass / linear_velocity: "
                           "weighted by the solver's lumped vertex masses; world metres and m/s")
    else:
        objects["silicone_bag"] = dict(present=False, deformable=True)
    for identity in ("can", "second_can"):
        if identity in ids:
            prefix = "" if identity == "can" else "second_"
            objects[NAMES[identity]] = dict(present=True, deformable=False, mass=physics[prefix + "can_mass_kg"],
                                            radius_m=physics[prefix + "can_radius_m"], height_m=physics[prefix + "can_height_m"])
        elif identity == "can":                                  # DELETE can: present false
            objects[NAMES[identity]] = dict(present=False, deformable=False)
    first = camera()
    gt = dict(schema_version=3, scene_id=SCENE_ID, interaction_category="rigid_elastic", case_id=case,
              fps=24, resolution=[WIDTH, HEIGHT], frame_start=1, frame_end=96, camera=first, objects=objects,
              units="metres, seconds, kilograms",
              frame_time="video frame i (1..96) shows native state i-1 at t = (i-1)/24 s",
              source=dict(native_cache=f"assets/scenes/{SCENE_ID}/native/{case}/simulation.npz", solver=config["solver"]),
              frames=[])
    for i in range(96):
        frame_objects = {}
        if bag:
            x = cache["bag_positions"][i]
            v = cache["bag_velocities"][i]
            frame_objects["silicone_bag"] = dict(
                present=True, deformable=True, deformation_frame_index=i, matrix_world=np.eye(4).tolist(),
                surface_centroid=x.mean(axis=0).tolist(), surface_bbox_min=x.min(axis=0).tolist(),
                surface_bbox_max=x.max(axis=0).tolist(), center_of_mass=(masses @ x / masses.sum()).tolist(),
                linear_velocity=(masses @ v / masses.sum()).tolist())
        else:
            frame_objects["silicone_bag"] = dict(present=False, deformable=True)
        for identity in ids:
            k = ids.index(identity)
            T = cache["can_transforms"][i, k]
            V = cache["can_velocities"][i, k]
            point = np.append(centroid, 1.0)
            frame_objects[NAMES[identity]] = dict(present=True, deformable=False, matrix_world=T.tolist(),
                                                  location=(T @ point)[:3].tolist(), linear_velocity=(V @ point)[:3].tolist(),
                                                  angular_velocity=angular_velocity(T, V))
        if "can" not in ids:
            frame_objects[NAMES["can"]] = dict(present=False, deformable=False)
        gt["frames"].append(dict(frame_index=i + 1, time_sec=float(times[i]), camera_matrix_world=first["matrix_world"],
                                 objects=frame_objects))
    return gt


def ground_truth(native: Path, case: str) -> dict:
    """pcve_ground_truth/1 record of one case: the native record converted without resampling."""
    return from_schema3(native_record(native), SCENE_ID, CATALOG[case],
                        tool=f"scripts/rigid_elastic/{SCENE_ID}/tools/export_ground_truth.py",
                        files=[native / "simulation.npz", native / "simulation_config.json"])


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
