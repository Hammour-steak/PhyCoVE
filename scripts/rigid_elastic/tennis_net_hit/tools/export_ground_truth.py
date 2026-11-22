"""Write cases/<case>/ground_truth_transforms.json of the suite from the native GT arrays.

Runs inside Blender 4.3.2 so the camera comes from the packed court scene itself:

    <blender> -b assets/scenes/tennis_net_hit/inputs/scene.blend --disable-autoexec --python-exit-code 1 \
        --python scripts/rigid_elastic/tennis_net_hit/tools/export_ground_truth.py -- --suite <suite dir> [--cases ...]

Nothing is authored. Per case the tool reads physics/<case>/ground_truth_24fps.npz, a member of
renders/tennis_net_hit/accepted/worker_tars/<worker>/<case>_artifacts.tar kept extracted at
renders/tennis_net_hit/accepted/physics/<case>/, checks it against the tar index
(<case>_files.json) and against physics_reports/<case>/qualification.json, and writes the 96 frame-centre
states (t = i/24 s, i = 0..95; video frame i+1). The ball is a rigid body (position, wxyz quaternion,
velocity). The net and the centre strap are deformable: their node/skin-vertex centroid and bounding
box are given per frame; full vertex arrays stay in the native NPZ named in "native_source". The files are
written in the pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py), converted from that per-frame record
without resampling; the ball keeps its render object name physical_ball.
"""
import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
SCENE_DIR = HERE.parent
sys.path[:0] = [str(SCENE_DIR / "physics"), str(SCENE_DIR.parents[1])]
from common import CASES, DATA, worker_tars  # noqa: E402
from pcve_ground_truth import from_schema3, write  # noqa: E402

WIDTH, HEIGHT, FPS, FRAMES = 1280, 720, 24, 96
BALL_RADIUS_M, BALL_MASS_KG = 0.0335, 0.0576


def catalog_id(case):
    return "source" if case == "source" else "edit_" + case


def native_arrays(case):
    tars = worker_tars()
    member = f"physics/{case}/ground_truth_24fps.npz"
    index = {r["path"]: r for r in json.loads((tars / f"{case}_files.json").read_text())["files"]}
    row = index[member]
    qual = json.loads((DATA / "physics_reports" / case / "qualification.json").read_text())
    if row["sha256"] != qual["ground_truth_sha256"]:
        raise RuntimeError(f"{case}: tar index and qualification name different GT arrays")
    # The member is kept extracted beside the delivery; "tar" below records the archive it came from.
    payload = (DATA / member).read_bytes()
    if hashlib.sha256(payload).hexdigest() != row["sha256"] or len(payload) != row["bytes"]:
        raise RuntimeError(f"{case}: extracted GT does not match the tar index")
    with np.load(io.BytesIO(payload), allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    source = {"tar": str((tars / f"{case}_artifacts.tar").relative_to(DATA.parents[2])), "member": member,
              "sha256": row["sha256"], "bytes": row["bytes"]}
    return arrays, qual, source


def quaternion_matrix(q):
    w, x, y, z = (float(v) for v in q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rows(matrix):
    return [[float(v) for v in row] for row in matrix]


def camera_record(scene):
    cam = scene.camera
    data = cam.data
    if data.type != "PERSP" or data.sensor_fit not in ("AUTO", "HORIZONTAL"):
        raise RuntimeError("Expected a horizontally fitted perspective camera")
    focal = data.lens / data.sensor_width * WIDTH
    longer = max(WIDTH, HEIGHT)
    cx = WIDTH / 2 - data.shift_x * longer
    cy = HEIGHT / 2 + data.shift_y * longer
    return {"name": cam.name, "matrix_world": rows(cam.matrix_world),
            "intrinsics": [[focal, 0, cx], [0, focal, cy], [0, 0, 1]],
            "lens_mm": data.lens, "sensor_width_mm": data.sensor_width, "sensor_fit": data.sensor_fit,
            "shift": [data.shift_x, data.shift_y], "clip_m": [data.clip_start, data.clip_end],
            "depth_of_field": {"enabled": data.dof.use_dof, "focus_distance_m": data.dof.focus_distance,
                               "f_stop": data.dof.aperture_fstop},
            "convention": "Blender camera: looks along its local -Z, +Y up; intrinsics in pixels, origin top-left",
            "trajectory": "fixed"}


def deformable(points, first):
    if points.shape[0] == 0:
        return {"present": False, "deformable": True}
    low, high = points.min(axis=0), points.max(axis=0)
    return {"present": True, "deformable": True, "vertex_count": int(points.shape[0]),
            "centroid_m": [float(v) for v in points.mean(axis=0)],
            "bbox_min_m": [float(v) for v in low], "bbox_max_m": [float(v) for v in high],
            "max_vertex_displacement_from_frame_1_m": float(np.linalg.norm(points - first, axis=1).max())}


def export(case, camera, suite):
    arrays, qual, source = native_arrays(case)
    times = arrays["times"]
    if len(times) != FRAMES or np.max(np.abs(times - np.arange(FRAMES) / FPS)) > 1e-10:
        raise RuntimeError(f"{case}: native GT is not sampled at the 96 frame centres")
    ball = arrays["ball_positions"]
    if ball.tolist() != qual["native_ball_positions_m"]:
        raise RuntimeError(f"{case}: GT ball positions differ from the qualification record")
    net, strap = arrays["net_positions"], arrays["strap_surface_positions"]
    present = net.shape[1] > 0
    if present != (case != "remove_entire_net"):
        raise RuntimeError(f"{case}: unexpected net presence")
    frames = []
    for i in range(FRAMES):
        matrix = np.eye(4)
        matrix[:3, :3] = quaternion_matrix(arrays["ball_quaternions"][i])
        matrix[:3, 3] = ball[i]
        frames.append({
            "frame_index": i + 1, "time_sec": float(times[i]), "camera_matrix_world": camera["matrix_world"],
            "objects": {
                "tennis_ball": {"present": True, "matrix_world": rows(matrix), "location": [float(v) for v in ball[i]],
                                "quaternion_wxyz": [float(v) for v in arrays["ball_quaternions"][i]],
                                "linear_velocity": [float(v) for v in arrays["ball_velocities"][i]]},
                "tennis_net": {**deformable(net[i], net[0]), "deformation_frame_index": i} if present else
                              {"present": False, "deformable": True},
                "center_strap": {**deformable(strap[i], strap[0]), "deformation_frame_index": i} if present else
                                {"present": False, "deformable": True},
            }})
    record = {
        "schema_version": 3, "scene_id": "tennis_net_hit", "interaction_category": "rigid_elastic",
        "case_id": catalog_id(case), "native_case_id": case, "fps": FPS, "resolution": [WIDTH, HEIGHT],
        "frame_start": 1, "frame_end": FRAMES, "camera": camera,
        "objects": {
            "tennis_ball": {"present": True, "mass": BALL_MASS_KG, "radius_m": BALL_RADIUS_M, "rigid": True},
            "tennis_net": {"present": present, "deformable": True,
                           "description": "polyethylene mesh, steel headline, bindings and headband nodes (net_positions)"},
            "center_strap": {"present": present, "deformable": True,
                             "description": "finite folded centre-strap skin vertices (strap_surface_positions)"},
        },
        "coordinate_system": "metres; x along the net, y shot direction (net plane y=0, camera at y=+3.6), z up",
        "time_sampling": "frame k shows the native state at t=(k-1)/24 s",
        "native_ground_truth_sha256": qual["ground_truth_sha256"], "native_source": source,
        "generator": "scripts/rigid_elastic/tennis_net_hit/tools/export_ground_truth.py",
        "material_calibrated": False,
        "frames": frames,
    }
    target = suite / "cases" / catalog_id(case) / "ground_truth_transforms.json"
    if not target.parent.is_dir():
        raise RuntimeError(f"Missing suite case folder {target.parent}")
    write(target, from_schema3(record, "tennis_net_hit", catalog_id(case), names={"tennis_ball": "physical_ball"},
                               tool=record["generator"]))
    return {"case": catalog_id(case), "file": str(target), "frames": len(frames), "net_present": present,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", type=Path, required=True)
    p.add_argument("--cases", nargs="+", choices=tuple(CASES), default=list(CASES))
    args = p.parse_args(argv)
    scene = bpy.context.scene
    ball = bpy.data.objects["physical_ball"]
    if ball.parent is not None or tuple(ball.scale) != (1.0, 1.0, 1.0):
        raise RuntimeError("physical_ball must be an unparented, unscaled root (its world matrix is the body pose)")
    camera = camera_record(scene)
    report = [export(case, camera, args.suite.resolve()) for case in args.cases]
    print("GROUND_TRUTH_EXPORT " + json.dumps(report), flush=True)


main()
