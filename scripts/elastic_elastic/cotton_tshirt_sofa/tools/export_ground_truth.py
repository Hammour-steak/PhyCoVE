"""Ground truth (pcve_ground_truth/1) of the suite cases from the native caches.

    python tools/export_ground_truth.py --suite SUITE --native DIR [--out DIR] [--timed-native DIR] [--cases CASE ...]

--suite is read for the camera (and the timed merged solves); --out writes DIR/<suite case>/ground_truth_transforms.json.
Without --out the files go into --suite/cases/<case>/, which is refused for the published suites under
renders/pcve_suites/ (a suite being assembled is fine).

Per case the native 24 Hz deformation cache the video replays (--native/<case>/deformation.npz, the accepted
delivery's cases; a timed edit's merged solve in --timed-native/<case>/simulation.npz) gives, for video frame i
(native sample i-1, t=(i-1)/24 s), the centroid of the T-shirt shell vertices (all are surface vertices) and of
the seat cushion's surface vertices (seat_topology.npz faces). Both are deformable: identity rotation and a
translation-only matrix_world (layout A of eval/metrics/common/traj_lib.py). The fixed camera is the render camera
recorded in the case's native ground truth (presentation.json location/target/lens 46 mm); nothing is authored.
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np

HERE = Path(__file__).resolve().parent
CASES = ("source", "stiff_shirt", "heavy_shirt", "low_friction", "remove_seat")
TIMED = ("low_friction_at_frame_10",)
CATALOG = {c: "source" if c == "source" else "edit_" + c for c in CASES + TIMED}
FPS, FRAMES = 24, 96


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def centroid_entry(points):
    c = [float(v) for v in points.astype(np.float64).mean(0)]
    return {"present": True, "location": c, "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
            "matrix_world": [[1.0, 0.0, 0.0, c[0]], [0.0, 1.0, 0.0, c[1]], [0.0, 0.0, 1.0, c[2]], [0.0, 0.0, 0.0, 1.0]],
            "bbox_min": [float(v) for v in points.min(0)], "bbox_max": [float(v) for v in points.max(0)]}


def export(case, native, timed_native, suite, camera_case, out=None):
    timed = case in TIMED
    cache = (timed_native / case / "simulation.npz") if timed else (native / case / "deformation.npz")
    topo_dir = native / "source"
    with np.load(cache, allow_pickle=False) as z:
        data = {k: z[k] for k in z.files}
    times = data["times"]
    if len(times) != FRAMES or np.abs(times - np.arange(FRAMES) / FPS).max() > 1e-9:
        raise RuntimeError(f"{case}: cache is not 96 samples at 24 Hz")
    shirt_rest = np.load(topo_dir / "shirt_topology.npz")["rest_positions"]
    seat_topo = np.load(topo_dir / "seat_topology.npz")
    seat_surface = np.unique(seat_topo["faces"])
    seat = "seat_positions" in data
    old = json.loads((suite / "cases" / CATALOG[camera_case] / "native_metadata" / "ground_truth_transforms.json").read_text())
    cam = old["camera"]
    if cam["resolution"] != [1280, 720]:
        raise RuntimeError("camera resolution")
    objects = {"shirt": {"object_name": "shirt", "kind": "deformable", "present": True,
                         "dimensions": [float(v) for v in shirt_rest.max(0) - shirt_rest.min(0)],
                         "material": "cotton jersey", "vertices": int(data["shirt_positions"].shape[1]),
                         "location_semantics": "centroid of the shell vertices"},
               "seat": {"object_name": "seat", "kind": "deformable", "present": seat,
                        "dimensions": [float(v) for v in seat_topo["rest_positions"].max(0) - seat_topo["rest_positions"].min(0)],
                        "material": "upholstery foam", "surface_vertices": int(len(seat_surface)),
                        "location_semantics": "centroid of the seat cushion's surface vertices"}}
    frames = []
    for i in range(FRAMES):
        entry = {"frame_index": i + 1, "time_sec": float(times[i]), "camera_matrix_world": cam["matrix_world"],
                 "shirt": centroid_entry(data["shirt_positions"][i])}
        entry["seat"] = centroid_entry(data["seat_positions"][i][seat_surface]) if seat else {
            "present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
        frames.append(entry)
    files = [cache, topo_dir / "seat_topology.npz", topo_dir / "shirt_topology.npz"]
    how = ("frame i = native sample i-1 (t=(i-1)/24) of the libuipc 0.0.28 solve the video replays (float32 cache); "
           "shirt = shell vertex centroid, seat = surface vertex centroid; camera = camera of the accepted render (camera_record)")
    if timed:
        cfg = json.loads((timed_native / case / "simulation_config.json").read_text())["timed_continuation"]
        how += (f"; timed edit at frame {cfg['edit_frame']}: samples 1..{cfg['edit_frame'] - 1} are the retained source cache, "
                "later samples continue the solver from the stored source state of the edit frame with the edited friction")
    gt = {"schema_version": 1, "format_version": "pcve_ground_truth/1", "scene": "cotton_tshirt_sofa", "case_id": CATALOG[case],
          "fps": FPS, "frame_start": 1, "frame_end": FRAMES, "units": "m",
          "camera": {"resolution": [1280, 720], "projection": "perspective", "lens_mm": cam["lens_mm"],
                     "sensor_width_mm": cam["sensor_width_mm"], "sensor_fit": "AUTO", "shift_x": 0.0, "shift_y": 0.0,
                     "matrix_world": cam["matrix_world"], "trajectory": "fixed",
                     "convention": "Blender camera: looks along its local -Z, +Y up"},
          "objects": objects, "frames": frames,
          "source": {"how": how, "files": [str(f) for f in files], "sha256": {str(f): sha(f) for f in files},
                     "native_case_id": case, "camera_record": f"cases/{CATALOG[camera_case]}/native_metadata/ground_truth_transforms.json",
                     "generator": "scripts/elastic_elastic/cotton_tshirt_sofa/tools/export_ground_truth.py"}}
    target = (out / CATALOG[case] if out else suite / "cases" / CATALOG[case]) / "ground_truth_transforms.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name("." + target.name + ".writing")
    tmp.write_text(json.dumps(gt, indent=1) + "\n", encoding="utf-8")
    tmp.replace(target)
    return {"case": CATALOG[case], "file": str(target), "seat": seat}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--suite", type=Path, required=True)
    p.add_argument("--native", type=Path, required=True, help="accepted delivery cases folder (<case>/deformation.npz): renders/cotton_tshirt_sofa/accepted_delivery/benchmark_increment/scenes/cotton_tshirt_sofa/cases")
    p.add_argument("--timed-native", type=Path, help="merged timed solves (<case>/simulation.npz); default SUITE/inputs/native_timed")
    p.add_argument("--cases", nargs="+", choices=CASES + TIMED, default=list(CASES + TIMED))
    p.add_argument("--out", type=Path, help="write <out>/<suite case>/ground_truth_transforms.json")
    a = p.parse_args()
    published = (HERE.parents[3] / "renders" / "pcve_suites").resolve()
    if a.out is None and (a.suite.resolve() == published or published in a.suite.resolve().parents):
        p.error("the published suites are read only: give --out <new folder>")
    timed_native = a.timed_native or a.suite / "inputs" / "native_timed"
    for case in a.cases:
        print(json.dumps(export(case, a.native, timed_native, a.suite, "source", a.out)), flush=True)


if __name__ == "__main__":
    main()
