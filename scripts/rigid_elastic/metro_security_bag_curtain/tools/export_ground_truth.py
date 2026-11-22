"""Ground truth (pcve_ground_truth/1) of every case of a suite: written to --out, or recomputed and compared (--check).

Per-frame object transforms come only from the native states that the videos replay
(assets/scenes/metro_security_bag_curtain/native/<tag>/<case>/states.npz; a timed edit's merged states are in
the suite's inputs/native_timed/<case>/); the camera comes from the case's render report (the camera is fixed).
Nothing is interpolated or authored. Layout A of eval/metrics/common/traj_lib.py: frames[i][<object>] holds present,
location, quaternion_xyzw and matrix_world; the curtain is tracked by its vertex centroid.

    python3 scripts/rigid_elastic/metro_security_bag_curtain/tools/export_ground_truth.py \
        (--out DIR | --check) [--suite DIR] [--native DIR] [--timed-native DIR] [--cases source ...]

--suite (default: the published suite) is read for the render reports and the timed merged states.
--out writes DIR/<suite case>/ground_truth_transforms.json; without --out the files are written into --suite
itself, which is refused for the published suites under renders/pcve_suites/ (a suite being assembled is fine).
--check recomputes every file and fails if its frames, camera or objects differ from the one in --suite; the
"source" record (where a file was made, with machine paths) is not compared.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]
from scene_paths import NATIVE, REPO, SCENE, SUITE, ensure_numpy_runtime  # noqa: E402

ensure_numpy_runtime()
import numpy as np  # noqa: E402

FPS = 24
FRAMES = 96
RESOLUTION = [1280, 720]
CATALOG = {"source": "source", "young_modulus_x100": "edit_young_modulus_x100", "belt_speed_x2": "edit_belt_speed_x2",
           "friction_x0p02": "edit_friction_x0p02", "delete_curtain": "edit_delete_curtain",
           "delete_curtain_at_frame_12": "edit_delete_curtain_at_frame_12"}
TIMED = ("delete_curtain_at_frame_12",)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rel(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def mat(rows):
    return [[float(v) for v in row] for row in rows]


def rigid_matrix(root, pitch):
    """Blender bag root: translation to the bottom-centre root, rotation about +y by the native pitch."""
    c, s = math.cos(pitch), math.sin(pitch)
    return [[c, 0.0, s, float(root[0])], [0.0, 1.0, 0.0, float(root[1])], [-s, 0.0, c, float(root[2])], [0.0, 0.0, 0.0, 1.0]]


def build(case, native_root, report, catalog_id=None):
    """pcve_ground_truth/1 (evaluator layout A: frames[i][<object>] = {present, location, quaternion_xyzw, matrix_world}).

    catalog_id: the suite case id of a case outside CATALOG (default CATALOG[case])."""
    folder = native_root / case
    config = json.loads((folder / "simulation_config.json").read_text())
    p = config["physics"]
    states = np.load(folder / "states.npz", allow_pickle=False)
    times = states["times"]
    assert len(times) >= FRAMES and all(abs(times[i] - i / FPS) < 1e-9 for i in range(FRAMES))
    roots, pitch_state = states["bag_positions"], states["bag_rigid"]
    root_vel, rigid_vel = states["bag_linear_velocity"], states["bag_rigid_velocity"]
    nbags = roots.shape[1]
    positions, strip_ids, rest = states["positions"], states["strip_ids"], states["rest_positions"]
    # Curtain on screen per frame: the physics flag, or a timed DELETE's per-frame record.
    shown = (states["curtain_present_per_frame"][:FRAMES].astype(bool) if "curtain_present_per_frame" in states.files
             else np.full(FRAMES, bool(p["curtain_present"][0])))
    bags = ["bag", "second_bag"][:nbags]
    absent = [] if p.get("bag_present", [1])[0] else ["bag"]   # DELETE bag: the backpack is recorded as absent
    assert not (absent and nbags), "a deleted backpack has no native rigid state"
    cam = report["camera"]
    assert [cam["width"], cam["height"]] == RESOLUTION, cam
    camera = {"resolution": RESOLUTION, "projection": "perspective", "lens_mm": float(cam["lens_mm"]),
              "sensor_width_mm": float(cam["sensor_width_mm"]), "sensor_fit": "HORIZONTAL", "shift_x": 0.0, "shift_y": 0.0,
              "matrix_world": mat(cam["matrix_world"]), "trajectory": "fixed",
              "convention": "Blender camera: looks along local -Z, +Y up"}
    objects = {}
    for b, name in enumerate(bags):
        mass = p["bag_mass_kg"] if b == 0 else p["second_bag_mass_kg"]
        objects[name] = {"object_name": name, "kind": "rigid", "present": True, "mass": float(mass),
                         "dimensions": [float(v) for v in p["bag_dimensions_m"]],
                         "origin": "bottom centre of the bag (contact root); +z through the centre of mass"}
    for name in absent:
        objects[name] = {"object_name": name, "kind": "rigid", "present": False, "mass": float(p["bag_mass_kg"]),
                         "dimensions": [float(v) for v in p["bag_dimensions_m"]],
                         "origin": "bottom centre of the bag (contact root); +z through the centre of mass"}
    objects["exit_curtain"] = {"object_name": "exit_curtain", "kind": "deformable", "present": bool(shown[0]),
                               "dimensions": [float(v) for v in rest.max(0) - rest.min(0)],
                               "strip_count": int(p["strip_count"]), "vertex_count": int(positions.shape[1]),
                               "location_semantics": "centroid of all strip-shell vertices (every vertex is on the surface)"}
    objects["conveyor"] = {"object_name": "conveyor belt", "kind": "kinematic", "tracked": False,
                           "belt_surface_velocity_m_s": [float(p["belt_speed_m_s"]), 0.0, 0.0],
                           "belt_top_z_m": float(p["belt_height_m"]), "belt_end_x_m": float(p["belt_end_x_m"])}
    frames = []
    for f in range(FRAMES):
        entry = {"frame_index": f + 1, "time_sec": f / FPS, "camera_matrix_world": camera["matrix_world"]}
        for b, name in enumerate(bags):
            theta = float(pitch_state[f, b, 2])
            entry[name] = {
                "present": True,
                "location": [float(v) for v in roots[f, b]],
                "quaternion_xyzw": [0.0, math.sin(theta / 2), 0.0, math.cos(theta / 2)],
                "matrix_world": rigid_matrix(roots[f, b], theta),
                "rotation_euler": [0.0, theta, 0.0],
                "linear_velocity": [float(v) for v in root_vel[f, b]],
                "angular_velocity": [0.0, float(rigid_vel[f, b, 2]), 0.0],
                "center_of_mass": [float(pitch_state[f, b, 0]), float(roots[f, b, 1]), float(pitch_state[f, b, 1])]}
        for name in absent:
            entry[name] = {"present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
        if shown[f]:
            x = positions[f]
            c = [float(v) for v in x.mean(0)]
            entry["exit_curtain"] = {
                "present": True, "location": c, "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
                "matrix_world": [[1.0, 0.0, 0.0, c[0]], [0.0, 1.0, 0.0, c[1]], [0.0, 0.0, 1.0, c[2]], [0.0, 0.0, 0.0, 1.0]],
                "vertex_bbox_min": [float(v) for v in x.min(0)], "vertex_bbox_max": [float(v) for v in x.max(0)],
                "strip_centroids": [[float(v) for v in x[strip_ids == k].mean(0)] for k in range(int(p["strip_count"]))],
                "max_displacement_from_rest_m": float(np.linalg.norm(x - rest, axis=1).max())}
        else:
            entry["exit_curtain"] = {"present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
        frames.append(entry)
    files = [folder / "states.npz", folder / "simulation_config.json"]
    timed = config.get("timed_edits")
    how = ("frame i = native 24 Hz state i-1 (t=(i-1)/24) of the float64 CPU solve the video replays; bag = Blender root "
           "'bag' (bottom-centre contact root, pitch about +y); curtain = vertex centroid; camera from the case's render report")
    if timed:
        how += (f"; timed edit at frame {timed[0]['frame']}: frames 1..{timed[0]['frame'] - 1} are the source states, later "
                "frames continue the solver from the exact source state of the edit frame")
    return {"schema_version": 3, "format_version": "pcve_ground_truth/1", "scene": SCENE, "case_id": catalog_id or CATALOG[case],
            "fps": FPS, "frame_start": 1, "frame_end": FRAMES, "units": "m",
            "camera": camera, "objects": objects, "frames": frames,
            "source": {"how": how, "files": [rel(x) for x in files], "sha256": {rel(x): sha(x) for x in files},
                       "native_case_id": case, "exporter": rel(Path(__file__)),
                       "world": "Blender world, z up; belt runs along +x"}}


def _without_source(text):
    return {key: value for key, value in json.loads(text).items() if key != "source"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", type=Path, default=SUITE)
    ap.add_argument("--native", type=Path, default=NATIVE)
    ap.add_argument("--timed-native", type=Path, default=SUITE / "inputs" / "native_timed",
                    help="merged native states of the timed edits (<dir>/<case>/states.npz)")
    ap.add_argument("--cases", nargs="+", choices=tuple(CATALOG), default=list(CATALOG))
    ap.add_argument("--report-name", default="native_metadata/render_report.json",
                    help="render report inside each case folder that carries the camera")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", type=Path, help="write <out>/<suite case>/ground_truth_transforms.json")
    a = ap.parse_args()
    published = (REPO / "renders" / "pcve_suites").resolve()
    if not a.check and a.out is None and (a.suite.resolve() == published or published in a.suite.resolve().parents):
        ap.error("the published suites are read only: give --out <new folder> (or --check)")
    rows = []
    for case in a.cases:
        folder = a.suite / "cases" / CATALOG[case]
        report = json.loads((folder / a.report_name).read_text())
        text = json.dumps(build(case, a.timed_native if case in TIMED else a.native, report), indent=1) + "\n"
        target = folder / "ground_truth_transforms.json"
        if a.out is not None and not a.check:
            target = a.out / CATALOG[case] / "ground_truth_transforms.json"
            target.parent.mkdir(parents=True, exist_ok=True)
        if a.check:
            # "source" records where a file was made (the published files name another machine's paths).
            if not target.is_file() or _without_source(target.read_text()) != _without_source(text):
                raise SystemExit(f"ground truth differs from the native states: {target}")
        else:
            target.write_text(text)
        rows.append({"case": CATALOG[case], "file": rel(target), "sha256": hashlib.sha256(text.encode()).hexdigest()})
    print(json.dumps({"checked" if a.check else "written": rows}, indent=1))


if __name__ == "__main__":
    main()
