"""Per-frame ground truth of every case of a spring_car_collision suite (no Blender needed).

    python tools/export_ground_truth.py --suite <suite folder> [--camera-json <render_metadata.json>]

Every state comes from the accepted MuJoCo solve of the case
(assets/scenes/spring_car_collision/native_cases/<case>/trajectory.npz and
scene_params.json): car chassis, the four wheels, the wooden block and the
added block as world matrices with their solver velocities, and the spring as
a reduced axial state (length, compression, energy, pusher pose) plus the
bounds of the coil it renders as. Video frame i (1..96) is native sample i-1
at t = (i-1)/24 s, the samples the renderer keys. The fixed camera comes from
the renderer's own record (render_metadata.json "camera"): the per-case copy in
cases/<case>/native_metadata/, else --camera-json. Nothing is estimated from pixels. The files are written in the
pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py), converted from that per-frame native record without
resampling; the table top is static scenery and is left out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
CASE_DIR = HERE.parent
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]
import scene_config as cfg  # noqa: E402
from pcve_ground_truth import from_schema3, write  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(matrix):
    return [[float(v) for v in row] for row in np.asarray(matrix)]


def vec(values):
    return [float(v) for v in np.asarray(values).reshape(-1)]


def quaternion_wxyz(matrix):
    r = np.asarray(matrix)[:3, :3]
    c = np.array([1 + np.trace(r), 1 + r[0, 0] - r[1, 1] - r[2, 2], 1 - r[0, 0] + r[1, 1] - r[2, 2], 1 - r[0, 0] - r[1, 1] + r[2, 2]])
    i = int(np.argmax(c))
    q = np.zeros(4)
    q[i] = np.sqrt(max(c[i], 0.0)) / 2
    d = 4 * q[i]
    if i == 0:
        q[1:] = [(r[2, 1] - r[1, 2]) / d, (r[0, 2] - r[2, 0]) / d, (r[1, 0] - r[0, 1]) / d]
    elif i == 1:
        q[[0, 2, 3]] = [(r[2, 1] - r[1, 2]) / d, (r[0, 1] + r[1, 0]) / d, (r[0, 2] + r[2, 0]) / d]
    elif i == 2:
        q[[0, 1, 3]] = [(r[0, 2] - r[2, 0]) / d, (r[0, 1] + r[1, 0]) / d, (r[1, 2] + r[2, 1]) / d]
    else:
        q[[0, 1, 2]] = [(r[1, 0] - r[0, 1]) / d, (r[0, 2] + r[2, 0]) / d, (r[1, 2] + r[2, 1]) / d]
    q /= np.linalg.norm(q)
    return vec(q if q[0] >= 0 else -q)


def camera_block(record):
    cam = record.get("camera", record)
    k = cam["intrinsics"]
    matrix = k["matrix"] if isinstance(k, dict) else k
    return {"matrix_world": rows(cam["matrix_world"]), "intrinsics": [[float(v) for v in r] for r in matrix],
            "intrinsics_convention": "pixels, origin top-left, y down; camera looks along -Z of matrix_world (Blender)",
            "lens_mm": float(cam["lens_mm"]), "sensor_width_mm": float(cam.get("sensor_width_mm", 36.0)),
            "sensor_fit": cam.get("sensor_fit", "HORIZONTAL"), "shift": [float(v) for v in cam.get("shift", [0.0, 0.0])],
            "clip": [float(cam.get("clip_start_m", 0.002)), float(cam.get("clip_end_m", 20.0))],
            "resolution": [int(v) for v in cam["resolution"]], "trajectory": "fixed",
            "depth_of_field": {"enabled": bool(cam.get("depth_of_field", False)),
                               "focus_distance_m": cam.get("focus_distance_m"), "fstop": cam.get("aperture_fstop")}}


def rigid(matrix, velocity):
    return {"present": True, "matrix_world": rows(matrix), "location": vec(np.asarray(matrix)[:3, 3]),
            "rotation_quaternion_wxyz": quaternion_wxyz(matrix),
            "linear_velocity": vec(velocity[:3]), "angular_velocity": vec(velocity[3:6])}


def coil_bounds(p, length):
    """Axis-aligned bounds of the rendered helix (constant mean diameter, wire diameter)."""
    x0 = float(p["spring_anchor_x_m"])
    r = float(p["spring_mean_diameter_m"]) / 2 + float(p["spring_wire_diameter_m"]) / 2
    z = float(p["spring_axis_z_m"])
    return [x0, -r, z - r], [x0 + float(length), r, z + r]


def export(case, suite, camera_record):
    native = cfg.native_case(case)
    cache_path = native / "trajectory.npz"
    p = json.loads((native / "scene_params.json").read_text(encoding="utf-8"))
    with np.load(cache_path, allow_pickle=False) as z:
        c = {k: z[k] for k in z.files}
    times = np.asarray(c["times"], float)
    if len(times) != cfg.FRAMES or not np.allclose(times, np.arange(cfg.FRAMES) / cfg.FPS, atol=1e-9):
        raise ValueError(f"{case}: native samples are not t = (i-1)/24 s, i = 1..96")
    flag = lambda key: bool(np.asarray(c.get(key, False)).reshape(-1)[0])
    spring_on, block_on, extra_on = flag("spring_present"), flag("block_present"), flag("obstacle_present")
    car_on = flag("car_present") if "car_present" in c else True
    camera = camera_block(camera_record)
    objects = {
        "car": ({"present": True, "rigid": True, "mass": float(p["car_mass_kg"]),
                 "dimensions_m": [float(p["car_length_m"]), float(p["car_width_m"]), float(p["car_height_m"])],
                 "wheel_radius_m": float(p["wheel_radius_m"]), "wheel_order": [str(w) for w in c["wheel_order"]],
                 "frame": "matrix_world is the chassis root (x forward, z up); wheel matrices are separate"}
                if car_on else {"present": False}),
        "block": ({"present": True, "rigid": True, "mass": float(p["block_mass_kg"]),
                   "dimensions_m": vec(p["block_size_m"])} if block_on else {"present": False}),
        "obstacle_block": ({"present": True, "rigid": True, "mass": float(p["obstacle_mass_kg"]),
                            "dimensions_m": vec(p["obstacle_size_m"]), "added_by_edit": True} if extra_on
                           else {"present": False}),
        "spring": ({"present": True, "deformable": True, "free_length_m": float(p["spring_rest_length_m"]),
                    "mean_diameter_m": float(p["spring_mean_diameter_m"]), "wire_diameter_m": float(p["spring_wire_diameter_m"]),
                    "active_turns": int(p["spring_active_turns"]), "young_modulus_pa": float(p["spring_young_modulus_pa"]),
                    "axial_stiffness_n_m": float(p["spring_stiffness_n_m"]), "anchor_x_m": float(p["spring_anchor_x_m"]),
                    "state_fields": "length_m / compression_m / elastic_energy_j from the solver's axial spring state; "
                                    "pusher_matrix_world is the moving pusher plate; coil_bbox_* bound the rendered helix"}
                   if spring_on else {"present": False}),
        "table": {"present": True, "fixed": True, "plane": "z = 0 (table top)"},
    }
    frames = []
    for i, t in enumerate(times):
        if car_on:
            state = {"car": rigid(c["car_transforms"][i], c["car_velocities"][i])}
            state["car"]["wheels"] = [{"matrix_world": rows(c["wheel_transforms"][i, w]),
                                       "angle_rad": float(c["wheel_angles"][i, w]),
                                       "angular_velocity_rad_s": float(c["wheel_angular_velocities"][i, w])} for w in range(4)]
        else:
            state = {"car": {"present": False}}
        state["block"] = rigid(c["block_transforms"][i], c["block_velocities"][i]) if block_on else {"present": False}
        state["obstacle_block"] = (rigid(c["obstacle_transforms"][i], c["obstacle_velocities"][i]) if extra_on
                                   else {"present": False})
        if spring_on:
            lo, hi = coil_bounds(p, c["spring_length"][i])
            spring = {"present": True, "deformable": True, "deformation_frame_index": i,
                      "length_m": float(c["spring_length"][i]), "compression_m": float(c["spring_compression"][i]),
                      "elastic_energy_j": float(c["spring_energy_j"][i]), "coil_bbox_min": lo, "coil_bbox_max": hi}
            if "spring_plate_transforms" in c:
                spring["pusher_matrix_world"] = rows(c["spring_plate_transforms"][i])
                spring["location"] = vec(np.asarray(c["spring_plate_transforms"][i])[:3, 3])
            if "spring_velocity_m_s" in c:
                spring["axial_velocity_m_s"] = float(c["spring_velocity_m_s"][i])
            state["spring"] = spring
        else:
            state["spring"] = {"present": False}
        frames.append({"frame_index": i + 1, "time_sec": float(t), "native_state_index": i,
                       "camera_matrix_world": camera["matrix_world"], "objects": state})
    record = {"schema_version": 3, "scene_id": cfg.SCENE, "case_id": case, "interaction_category": cfg.CATEGORY,
              "fps": cfg.FPS, "resolution": camera["resolution"], "frame_start": 1, "frame_end": len(frames),
              "coordinate_system": "right-handed, Z up, metres, seconds; x along the launch direction, table top z = 0",
              "camera": camera, "objects": objects, "frames": frames,
              "source": {"cache_sha256": sha(cache_path), "scene_params_sha256": sha(native / "scene_params.json"),
                         "native_case": str(native.relative_to(cfg.REPO)) if native.is_relative_to(cfg.REPO) else str(native),
                         "native_sample_hz": cfg.FPS, "native_state_stride": 1,
                         "camera_record": camera_record.get("_path"),
                         "generator": "scripts/rigid_elastic/spring_car_collision/tools/export_ground_truth.py"}}
    out = Path(suite) / "cases" / cfg.CATALOG[case] / "ground_truth_transforms.json"
    write(out, from_schema3(record, cfg.SCENE, cfg.CATALOG[case], skip=["table"], tool=record["source"]["generator"],
                            files=[cache_path, native / "scene_params.json"]))
    return {"case": case, "out": str(out), "frames": len(frames), "cache_sha256": record["source"]["cache_sha256"]}


def camera_for(case, suite, fallback):
    local = Path(suite) / "cases" / cfg.CATALOG[case] / "native_metadata" / "render_metadata.json"
    path = local if local.is_file() else fallback
    if path is None:
        raise SystemExit(f"{case}: no render_metadata.json in the suite; pass --camera-json")
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    record["_path"] = str(Path(path).resolve().relative_to(cfg.REPO)) if Path(path).resolve().is_relative_to(cfg.REPO) else str(path)
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", type=Path, required=True,
                    help="suite folder to write into (cases/<id>/ground_truth_transforms.json, pcve_ground_truth/1)")
    ap.add_argument("--camera-json", type=Path)
    ap.add_argument("--cases", nargs="+", choices=cfg.CASES, default=list(cfg.CASES))
    a = ap.parse_args()
    for case in a.cases:
        print(json.dumps(export(case, a.suite, camera_for(case, a.suite, a.camera_json))), flush=True)


if __name__ == "__main__":
    main()
