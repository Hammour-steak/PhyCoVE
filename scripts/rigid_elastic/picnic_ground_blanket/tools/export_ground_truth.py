"""Export ground_truth_transforms.json (pcve_ground_truth/1) of one case from its native libuipc state.

Frame i (1..96) is native cache sample i-1, t = (i-1)/24 s, the state the video renders. The orange is a rigid
body with its native affine world transform (location, quaternion_xyzw of its rotation part, matrix_world;
present: false in delete_actor). The blanket and the grass layer are deformable: location is the centroid of
their vertices in that frame (blanket mid-surface; top surface of the FEM grass layer), the quaternion is the
identity and matrix_world a pure translation; dimensions are the extent in frame 1. The camera is the fixed
calibration recorded in scene_manifest.json, which the renderer checks against the packed scene on every frame.
This is the layout eval/metrics/common/traj_lib.py reads.

Needs numpy (for example .venv-rigid-elastic/bin/python). Usage:
    python tools/export_ground_truth.py --case source --out ground_truth_transforms.json
    python tools/export_ground_truth.py --case mass_double_at_frame_12 --native DIR --out ground_truth_transforms.json
    python tools/export_ground_truth.py --case source --compare renders/pcve_suites/pcve_picnic_ground_blanket_suite
The timed edit has no accepted state in the asset store: --native names its solve (simulate output).
--compare checks a fresh export against the suite's file (everything except the "source" record).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

CASE_DIR = Path(__file__).resolve().parents[1]
REPO = CASE_DIR.parents[2]
for _path in (CASE_DIR, REPO / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scene_inputs import CASES, CATALOG, SCENE, TIMED_CASES, native  # noqa: E402

MANIFEST_PATH = CASE_DIR / "scene_manifest.json"
FORMAT = "pcve_ground_truth/1"
SCHEMA_VERSION = 3
FPS = 24
FRAMES = 96
RESOLUTION = [1280, 720]
HOW = ("Native libuipc states at t=(i-1)/24 (cache sample i-1, the frames the video renders); orange = native affine "
       "body transform; camera = the fixed calibration of scene_manifest.json that the renderer checks every frame.")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def matrix(m):
    return [[float(m[i][j]) for j in range(4)] for i in range(4)]


def quaternion_xyzw(m):
    """Unit quaternion (x, y, z, w; w >= 0) of the 3x3 part of a world matrix."""
    r = [[float(m[i][j]) for j in range(3)] for i in range(3)]
    trace = r[0][0] + r[1][1] + r[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        w, x, y, z = .25 * s, (r[2][1] - r[1][2]) / s, (r[0][2] - r[2][0]) / s, (r[1][0] - r[0][1]) / s
    elif r[0][0] > r[1][1] and r[0][0] > r[2][2]:
        s = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2
        w, x, y, z = (r[2][1] - r[1][2]) / s, .25 * s, (r[0][1] + r[1][0]) / s, (r[0][2] + r[2][0]) / s
    elif r[1][1] > r[2][2]:
        s = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2
        w, x, y, z = (r[0][2] - r[2][0]) / s, (r[0][1] + r[1][0]) / s, .25 * s, (r[1][2] + r[2][1]) / s
    else:
        s = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2
        w, x, y, z = (r[1][0] - r[0][1]) / s, (r[0][2] + r[2][0]) / s, (r[1][2] + r[2][1]) / s, .25 * s
    n = math.sqrt(x * x + y * y + z * z + w * w)
    q = [x / n, y / n, z / n, w / n]
    return [-v for v in q] if q[3] < 0 else q


def rigid(present, m=None):
    if not present or m is None:
        return {"present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
    m = matrix(m)
    return {"present": True, "location": [m[0][3], m[1][3], m[2][3]], "quaternion_xyzw": quaternion_xyzw(m), "matrix_world": m}


def deformable(points):
    c = np.asarray(points, dtype=np.float64).mean(axis=0)
    translation = [[1., 0., 0., float(c[0])], [0., 1., 0., float(c[1])], [0., 0., 1., float(c[2])], [0., 0., 0., 1.]]
    entry = rigid(True, translation)
    entry["quaternion_xyzw"] = [0., 0., 0., 1.]
    return entry


def native_dir_of(case, native_dir=None):
    if native_dir is not None:
        return Path(native_dir)
    if case in TIMED_CASES:
        raise ValueError(f"{case} has no accepted state in the asset store; pass its solve directory")
    return native(case)


def build(case, native_dir=None):
    folder = native_dir_of(case, native_dir)
    config = json.loads((folder / "simulation_config.json").read_text(encoding="utf-8"))
    if config["scene_id"] != SCENE or config["case"] != case:
        raise ValueError(f"{folder} holds {config['scene_id']}/{config['case']}, not {SCENE}/{case}")
    physics = config["physics"]
    cache_path = folder / "cache.npz"
    with np.load(cache_path, allow_pickle=False) as cache:
        times = cache["times"]
        body = cache["body_transforms"]
        cloth = cache["cloth_positions"]
        grass = cache["solid_positions"][:, cache["cover_volume_vertex_ids"]]
        if bool(cache["path_obstacle_present"][0]):
            raise ValueError(f"{case}: the native state contains the picnic-cup ADD object (in no published case)")
    if len(times) != FRAMES or not np.allclose(times, np.arange(FRAMES) / FPS, rtol=0, atol=1e-9):
        raise ValueError("The native cache is not sampled at i/24 s, i=0..95")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cam = manifest["camera"]
    camera = {"resolution": RESOLUTION, "projection": "perspective", "lens_mm": float(cam["lens_mm"]),
              "sensor_width_mm": float(cam["sensor_width_mm"]), "sensor_fit": "AUTO",
              "shift_x": float(cam["shift"][0]), "shift_y": float(cam["shift"][1]), "matrix_world": matrix(cam["matrix_world"])}
    orange = bool(physics["active"][0])
    blanket = bool(physics["active"][1])  # False when the blanket is deleted (no cloth shell in the cache)
    objects = {
        "mandarin_orange": {"object_name": "mandarin_orange", "kind": "rigid", "present": orange,
                            "radius": physics["body_radius"], "mass_kg": physics["body_mass"]},
        "cotton_blanket": {"object_name": "picnic_ground_blanket | actual physical surface", "kind": "deformable", "present": True,
                           "dimensions": [float(x) for x in np.ptp(cloth[0], axis=0)],
                           "location_definition": "centroid of the native cloth mid-surface vertices of the frame"} if blanket else
                          {"object_name": "picnic_ground_blanket | actual physical surface", "kind": "deformable", "present": False,
                           "location_definition": "n/a (never present)"},
        "grass_thatch": {"object_name": "grass_thatch (FEM grass layer; rendered blades follow its top surface)", "kind": "deformable",
                         "present": True, "dimensions": [float(x) for x in np.ptp(grass[0], axis=0)],
                         "location_definition": "centroid of the top-surface vertices of the native FEM grass layer of the frame"},
    }
    frames = []
    for i in range(FRAMES):
        frames.append({"frame_index": i + 1, "time_sec": i / FPS, "camera_matrix_world": camera["matrix_world"],
                       "mandarin_orange": rigid(orange, body[i]), "cotton_blanket": deformable(cloth[i]) if blanket else rigid(False),
                       "grass_thatch": deformable(grass[i])})
    files = [cache_path, folder / "simulation_config.json", MANIFEST_PATH]
    source = {"how": HOW, "files": [relative(p) for p in files], "sha256": {relative(p): sha256(p) for p in files if p.suffix != ".json"},
              "tool": relative(Path(__file__))}
    if config.get("timed_edit"):
        source["timed_edit"] = config["timed_edit"]
    return {"schema_version": SCHEMA_VERSION, "format_version": FORMAT, "scene": SCENE, "case_id": CATALOG.get(case, "edit_" + case), "fps": FPS,
            "frame_start": 1, "frame_end": FRAMES, "units": "m", "camera": camera, "objects": objects, "frames": frames,
            "source": source}


def dumps(data):
    return json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def write(case, out, native_dir=None):
    data = build(case, native_dir)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(data), encoding="utf-8")
    return data


def compare(case, suite, native_dir=None):
    """Differences between a fresh export and the suite's ground truth, ignoring the "source" record."""
    fresh = json.loads(dumps(build(case, native_dir)))
    published = json.loads((Path(suite) / "cases" / CATALOG[case] / "ground_truth_transforms.json").read_text(encoding="utf-8"))
    return sorted(key for key in set(fresh) | set(published) if key != "source" and fresh.get(key) != published.get(key))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=CASES + TIMED_CASES, required=True)
    parser.add_argument("--native", type=Path, help="Native state directory (default: the asset store; required for the timed edit)")
    parser.add_argument("--out", type=Path, help="Write the ground truth here")
    parser.add_argument("--compare", type=Path, metavar="SUITE", help="Compare a fresh export with SUITE/cases/<case>/ground_truth_transforms.json")
    args = parser.parse_args()
    if args.out is None and args.compare is None:
        parser.error("pass --out and/or --compare")
    result = {"case": args.case}
    if args.out is not None:
        result["frames"] = len(write(args.case, args.out, args.native)["frames"])
        result["out"] = str(args.out)
    if args.compare is not None:
        result["differing_keys"] = compare(args.case, args.compare, args.native)
    print(json.dumps(result))
    if result.get("differing_keys"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
