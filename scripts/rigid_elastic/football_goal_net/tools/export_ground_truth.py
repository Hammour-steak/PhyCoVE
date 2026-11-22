"""Write cases/<case>/ground_truth_transforms.json of a published suite from the native states.

Runs inside Blender 4.3.2 (factory startup; the camera is built by appearance/camera.py, the same
module the renderer uses):

    <blender> -b --factory-startup --python-exit-code 1 \
        --python scripts/rigid_elastic/football_goal_net/tools/export_ground_truth.py -- \
        --suite renders/pcve_suites/pcve_football_goal_net_suite [--cases ...]

Nothing is authored. Per case the tool reads assets/scenes/football_goal_net/native/<case>/simulation.npz
(481 states at 120 Hz, sha256 recorded in the accepted canonical_export_manifest.json) and writes the 96 frame states
t = i/24 s (native index 5i; video frame i+1), exactly the states the renderer binds to those frames.
The football is a rigid body (position, wxyz quaternion, linear and angular velocity). The goal net
is deformable: presence, node count, centroid, bounding box and maximum node displacement from
frame 1 (full node arrays stay in the native npz named in "native_source"). The turf is a deformable
ground: the minimum relative height of its 14,458 solver samples. The camera record takes the aperture
and focus from the case's native_metadata/render_setup.json when the suite has one (the render
report of the published video) and checks its pose against appearance/camera.py.

Output format pcve_ground_truth/1 (layout A of eval/metrics/common/traj_lib.py): frames[i][<object>] holds present,
location, quaternion_xyzw and matrix_world; the goal net is tracked by its node centroid (identity rotation).
A timed edit (edit_vocab.TIMED_DSL) reads the merged native solve in the suite's inputs/native_timed/<case>/
(physics/solve_timed.py): its samples before the edit frame are the accepted source samples.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
SCENE_DIR = HERE.parent
sys.path[:0] = [str(SCENE_DIR), str(SCENE_DIR / "appearance")]
from tools.retained import CASES, REPO, catalog_id, full_input, native_sha256, read, sha  # noqa: E402
import edit_vocab  # noqa: E402
TIMED = tuple(edit_vocab.TIMED_DSL)

WIDTH, HEIGHT, FPS, FRAMES, STEP = 1280, 720, 24, 96, 5
BALL_RADIUS_M, BALL_MASS_KG = 0.11, 0.43


def rows(matrix):
    return [[float(v) for v in row] for row in matrix]


def quaternion_matrix(q):
    w, x, y, z = (float(v) for v in q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def camera_record(setup):
    import importlib.util
    spec = importlib.util.spec_from_file_location("football_camera", SCENE_DIR / "appearance/camera.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = WIDTH, HEIGHT, 100
    cam, _ = module.apply(bpy, scene, "wide", 4.0)
    data = cam.data
    matrix = np.array(cam.matrix_world)
    f_stop, focus = data.dof.aperture_fstop, data.dof.focus_distance
    source = "appearance/camera.py"
    if setup is not None:
        rendered = setup["shared"]["camera"]
        if np.max(np.abs(np.array(rendered["matrix_world"]) - matrix)) > 1e-5 or abs(rendered["lens_mm"] - data.lens) > 1e-9:
            raise RuntimeError("Rendered camera differs from appearance/camera.py")
        f_stop, focus = rendered["f_stop"], rendered["focus_distance_m"]
        source = "appearance/camera.py pose; aperture/focus from native_metadata/render_setup.json"
    focal = data.lens / data.sensor_width * WIDTH
    return {"name": "fixed pitchside telephoto camera", "matrix_world": rows(matrix),
            "intrinsics": [[focal, 0, WIDTH / 2 - data.shift_x * WIDTH], [0, focal, HEIGHT / 2 + data.shift_y * WIDTH], [0, 0, 1]],
            "lens_mm": data.lens, "sensor_width_mm": data.sensor_width, "sensor_fit": data.sensor_fit,
            "shift": [data.shift_x, data.shift_y], "clip_m": [data.clip_start, data.clip_end],
            "depth_of_field": {"enabled": True, "focus_distance_m": focus, "f_stop": f_stop},
            "eye_m": module.RECIPE["eye_m"], "target_m": module.RECIPE["target_m"],
            "convention": "Blender camera: looks along its local -Z, +Y up; intrinsics in pixels, origin top-left",
            "trajectory": "fixed", "source": source}


def rel(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def export(case, camera, suite):
    timed = edit_vocab.timed_schedule(case) if case in TIMED else None
    raw = (suite / "inputs/native_timed" / case if timed else full_input(case)) / "simulation.npz"
    digest = sha(raw)
    if not timed and digest != native_sha256(case):
        raise RuntimeError(f"{case}: native state differs from the pinned cache")
    with np.load(raw, allow_pickle=False) as z:
        times = z["times"]
        if len(times) != 481 or np.max(np.abs(times - np.arange(481) / 120)) > 1e-9:
            raise RuntimeError(f"{case}: unexpected native clock")
        idx = np.arange(FRAMES) * STEP
        ball, quat = z["ball_positions"][idx], z["ball_orientations"][idx]
        vel, omega = z["ball_velocities"][idx], z["ball_angular_velocity"][idx]
        net_present = bool(z["net_present"])
        board_present = bool(z["training_rebound_board_present"])
        net = z["net_positions"][idx] if net_present else None
        turf = z["turf_control_scale"][idx]
    if net_present != (case != "remove_net") or board_present:
        raise RuntimeError(f"{case}: unexpected presence flags")
    frames = []
    for i in range(FRAMES):
        matrix = np.eye(4)
        matrix[:3, :3] = quaternion_matrix(quat[i])
        matrix[:3, 3] = ball[i]
        w, x, y, zq = (float(v) for v in quat[i])
        entry = {"frame_index": i + 1, "time_sec": float(times[idx[i]]), "camera_matrix_world": camera["matrix_world"],
                 "football": {"present": True, "location": [float(v) for v in ball[i]], "quaternion_xyzw": [x, y, zq, w],
                              "matrix_world": rows(matrix), "linear_velocity": [float(v) for v in vel[i]],
                              "angular_velocity": [float(v) for v in omega[i]]}}
        if net_present:
            points = net[i].astype(np.float64)
            c = [float(v) for v in points.mean(axis=0)]
            entry["goal_net"] = {"present": True, "location": c, "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
                                 "matrix_world": [[1.0, 0.0, 0.0, c[0]], [0.0, 1.0, 0.0, c[1]], [0.0, 0.0, 1.0, c[2]], [0.0, 0.0, 0.0, 1.0]],
                                 "vertex_count": int(points.shape[0]), "bbox_min_m": [float(v) for v in points.min(axis=0)],
                                 "bbox_max_m": [float(v) for v in points.max(axis=0)],
                                 "max_vertex_displacement_from_frame_1_m": float(np.linalg.norm(points - net[0], axis=1).max()),
                                 "native_index": int(idx[i])}
        else:
            entry["goal_net"] = {"present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
        entry["turf_min_relative_height"] = float(turf[i].min()) if turf.shape[1] else 1.0
        frames.append(entry)
    net_rest = net[0] if net_present else None
    objects = {
        "football": {"object_name": "football", "kind": "rigid", "present": True,
                     "mass": BALL_MASS_KG if not timed else {"before_edit": BALL_MASS_KG, "after_edit": timed[0]["params"]["ball_mass_kg"],
                                                             "edit_frame": timed[0]["frame"]},
                     "radius": BALL_RADIUS_M, "description": "thin-shell ball, I = 2 m R^2 / 3 (strict_edit_plan.json material_mapping)"},
        "goal_net": {"object_name": "goal_net", "kind": "deformable", "present": net_present,
                     **({"dimensions": [float(v) for v in net_rest.max(axis=0) - net_rest.min(axis=0)]} if net_present else {}),
                     "description": "4 mm hexagonal-mesh strands and 6 mm support cords, solver nodes (net_positions); location = node centroid"},
        "turf": {"object_name": "turf", "kind": "deformable", "tracked": False,
                 "description": "viscoelastic turf foundation (ground); frames carry turf_min_relative_height of its 14,458 solver samples"},
    }
    how = ("frame i = native 120 Hz state 5(i-1) (t=(i-1)/24) of the CPU solve the video replays; football = rigid body "
           "pose and velocities; goal net = node centroid; camera rebuilt with appearance/camera.py and checked against the render")
    if timed:
        how += (f"; timed edit at frame {timed[0]['frame']}: native samples before the edit tick are the accepted source "
                "samples, later samples continue the solver from its lossless checkpoint at the edit tick with the edited mass")
    record = {
        "schema_version": 3, "format_version": "pcve_ground_truth/1", "scene": "football_goal_net", "case_id": catalog_id(case),
        "fps": FPS, "frame_start": 1, "frame_end": FRAMES, "units": "m",
        "camera": {"resolution": [WIDTH, HEIGHT], "projection": "perspective", "lens_mm": camera["lens_mm"],
                   "sensor_width_mm": camera["sensor_width_mm"], "sensor_fit": camera["sensor_fit"],
                   "shift_x": camera["shift"][0], "shift_y": camera["shift"][1], "matrix_world": camera["matrix_world"],
                   "name": camera["name"], "clip_m": camera["clip_m"], "depth_of_field": camera["depth_of_field"],
                   "eye_m": camera["eye_m"], "target_m": camera["target_m"], "convention": camera["convention"],
                   "trajectory": "fixed", "camera_source": camera["source"]},
        "objects": objects,
        "coordinate_system": "metres; x along the goal line (posts at x = +-3.66), y into the goal (goal line y = 0), z up",
        "frames": frames,
        "source": {"how": how, "files": [rel(raw)], "sha256": {rel(raw): digest}, "native_case_id": case,
                   "native_fps": 120, "native_samples": 481,
                   "generator": "scripts/rigid_elastic/football_goal_net/tools/export_ground_truth.py",
                   "material_calibrated": False},
    }
    target = suite / "cases" / catalog_id(case) / "ground_truth_transforms.json"
    if not target.parent.is_dir():
        raise RuntimeError(f"Missing suite case folder {target.parent}")
    target.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return {"case": catalog_id(case), "frames": len(frames), "net_present": net_present, "board_present": board_present,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", type=Path, required=True)
    p.add_argument("--cases", nargs="+", choices=CASES + TIMED, default=list(CASES + TIMED))
    args = p.parse_args(argv)
    suite = args.suite.resolve()
    report = []
    for case in args.cases:
        setup_file = suite / "cases" / catalog_id(case) / "native_metadata/render_setup.json"
        camera = camera_record(read(setup_file) if setup_file.is_file() else None)
        report.append(export(case, camera, suite))
    print("GROUND_TRUTH_EXPORT " + json.dumps(report), flush=True)


main()
