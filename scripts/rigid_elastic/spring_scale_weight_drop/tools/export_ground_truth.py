"""Ground truth (pcve_ground_truth/1) of spring_scale_weight_drop from the native caches.

    python3 scripts/rigid_elastic/spring_scale_weight_drop/tools/export_ground_truth.py --out DIR [--cases CASE ...]
        [--input-root ROOT] [--timed-root ROOT]

Writes DIR/<suite case>/ground_truth_transforms.json (source, edit_<native case>); it never writes into the published
suite. Frame i is native sample i-1 (t = (i-1)/24 s) of cases/<case>/native_dynamics.npz: the weight (centre of its
machined envelope) and the pan (centre of the felt-pad top) are rigid vertical translations of the rendered bodies, the
spring is the centroid of the rendered helix tube (coil_vertices of appearance/render_spring.py, read from that file
without Blender) and the camera is the fixed camera of the published source render report. Whole-clip cases read
--input-root (default: the accepted delivery); the timed case reads --timed-root/cases/<case>/ (a simulate output root)
or, by default, its published suite case's native_metadata/. Needs numpy.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import math
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
CASE_DIR = HERE.parent
for _path in (CASE_DIR, CASE_DIR.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from edit_vocab import CASE_DSL, TIMED_DSL  # noqa: E402
from physics.scene import DELIVERY  # noqa: E402
from scene_paths import REPO, SCENE, suite  # noqa: E402

RENDERER = CASE_DIR / "appearance/render_spring.py"
FORMAT = "pcve_ground_truth/1"
HOW = ("Native RK4 states at t=(i-1)/24 (native_dynamics.npz frame i, the frames the video renders); weight and pan are "
       "rigid vertical translations of the rendered bodies; spring centroid from the renderer helix geometry; camera from "
       "the source render report (fixed camera, identical in every case).")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def relative(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def renderer_function(name):
    """A numpy-only function of appearance/render_spring.py, compiled from its source (that module needs Blender)."""
    tree = ast.parse(RENDERER.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {"np": np, "math": math}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(RENDERER), "exec"), namespace)
    return namespace[name]


coil_vertices = renderer_function("coil_vertices")


def weight_envelope():
    """Height and radius of the weight's envelope: the lathe profile of render_spring.weight_profile, scaled to 0.1 kg of brass."""
    profile = np.array([(0, 0), (.0148, 0), (.016, .001), (.016, .012), (.015, .013), (.005, .013), (.0045, .015),
                        (.0075, .016), (.0075, .020), (.0065, .021), (0, .021)], dtype=float)
    volume = sum(math.pi * (b[1] - a[1]) * (a[0]**2 + a[0] * b[0] + b[0]**2) / 3 for a, b in zip(profile[:-1], profile[1:]))
    height = float(.021 * (.1 / 8500) / volume)
    rendered, _ = renderer_function("weight_profile")()
    if abs(height - float(rendered[:, 1].max())) > 1e-15 or abs(float(rendered[:, 0].max()) - .016) > 1e-15:
        raise RuntimeError("appearance/render_spring.py weight_profile changed; update weight_envelope")
    return height, .016


def translation(point):
    return [[1., 0., 0., float(point[0])], [0., 1., 0., float(point[1])], [0., 0., 1., float(point[2])], [0., 0., 0., 1.]]


def entry(present, matrix):
    if not present:
        return {"present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
    return {"present": True, "location": [matrix[0][3], matrix[1][3], matrix[2][3]], "quaternion_xyzw": [0., 0., 0., 1.],
            "matrix_world": matrix}


def case_folder(native, input_root, timed_root):
    if native in TIMED_DSL:
        return timed_root / "cases" / native if timed_root else suite() / "cases" / f"edit_{native}" / "native_metadata"
    return input_root / "cases" / native


def camera(input_root):
    report = json.loads((suite() / "cases/source/native_metadata/render_report.json").read_text(encoding="utf-8"))["camera"]
    delivered = input_root / "cases/source/camera.json"
    if delivered.is_file():
        recorded = json.loads(delivered.read_text(encoding="utf-8"))["camera_to_world_blender_4x4"]
        if not np.allclose(np.array(report["matrix_world"]), np.array(recorded), atol=1e-6):
            raise RuntimeError("The source render report and the delivered camera differ")
    matrix = [[float(v) for v in row] for row in report["matrix_world"]]
    return {"resolution": [1280, 720], "projection": "perspective", "lens_mm": float(report["lens_mm"]),
            "sensor_width_mm": float(report["sensor_width_mm"]), "sensor_fit": "AUTO", "shift_x": 0., "shift_y": 0.,
            "matrix_world": matrix}


def build(native, input_root=DELIVERY, timed_root=None):
    """The ground truth document of one native case."""
    folder = case_folder(native, Path(input_root), Path(timed_root) if timed_root else None)
    physics = json.loads((folder / "physics.json").read_text(encoding="utf-8"))
    p = physics["physics"]
    with np.load(folder / "native_dynamics.npz", allow_pickle=False) as z:
        native_data = {key: z[key] for key in ("frame_times_s", "coil_node_z_m", "pan_pad_top_z_m", "weight_bottom_z_m")}
    if not np.allclose(native_data["frame_times_s"][:96], np.arange(96) / 24, atol=1e-12):
        raise RuntimeError(f"{native}: native samples are not on the 24 fps clock")
    cam = camera(Path(input_root))
    height, radius = weight_envelope()
    # DELETE spring: physics.json carries spring_present false (absent from the published cases' physics).
    spring = bool(p.get("spring_present", True))
    rest = coil_vertices(native_data["coil_node_z_m"][0], p)
    lo, hi = rest.min(0), rest.max(0)
    objects = {
        "weight": {"object_name": "Native freely falling calibration weight", "kind": "rigid", "present": bool(p["weight_present"]),
                   "dimensions": [2 * radius, 2 * radius, height], "radius": radius,
                   "origin": "centre of the machined weight envelope (Blender group origin is the base centre; +h/2 along z)"},
        "pan": {"object_name": "Native guided carriage and suspended pan", "kind": "rigid", "present": True,
                "dimensions": [2 * p["pan_radius_m"], 2 * p["pan_radius_m"], p["pan_wall_height_m"]],
                "origin": "centre of the felt pad top in the suspended pan; the carriage, pointer and pan move together by the native travel"},
        "spring": {"object_name": "Native steel helix - 28 massive turns", "kind": "deformable", "present": spring,
                   "dimensions": [float(x) for x in hi - lo],
                   "location_definition": "centroid of the rendered helix tube vertices (render_spring.coil_vertices of the native coil nodes)"},
    }
    frames = []
    for i in range(96):
        frame = {"frame_index": i + 1, "time_sec": i / 24, "camera_matrix_world": [list(row) for row in cam["matrix_world"]]}
        frame["weight"] = entry(bool(p["weight_present"]),
                                translation((0., 0., float(native_data["weight_bottom_z_m"][i]) + height / 2)))
        frame["pan"] = entry(True, translation((0., 0., float(native_data["pan_pad_top_z_m"][i]))))
        frame["spring"] = entry(spring, translation(coil_vertices(native_data["coil_node_z_m"][i], p).mean(0)) if spring else None)
        frames.append(frame)
    files = [folder / "native_dynamics.npz", folder / "physics.json",
             suite() / "cases/source/native_metadata/render_report.json", RENDERER]
    source = {"how": HOW, "files": [relative(f) for f in files], "sha256": {relative(f): sha(f) for f in files if f.suffix not in (".py", ".json")},
              "tool": relative(__file__)}
    if native in TIMED_DSL:
        source["timed_edit"] = physics["timed_edit"]
    case_id = "source" if native == "source" else f"edit_{native}"
    return {"schema_version": 1, "format_version": FORMAT, "scene": SCENE, "case_id": case_id, "fps": 24,
            "frame_start": 1, "frame_end": 96, "units": "m", "camera": cam, "objects": objects, "frames": frames,
            "source": source}


def dumps(document):
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="new directory: <out>/<suite case>/ground_truth_transforms.json")
    parser.add_argument("--cases", nargs="+", choices=[*CASE_DSL, *TIMED_DSL], default=[*CASE_DSL, *TIMED_DSL])
    parser.add_argument("--input-root", type=Path, default=DELIVERY, help="native caches of the whole-clip cases (<root>/cases/<case>/)")
    parser.add_argument("--timed-root", type=Path, help="simulate output root of the timed case (default: its suite native_metadata/)")
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    published = suite().resolve()
    if out == published or published in out.parents:
        parser.error("Write ground truth outside the published suite")
    for native in args.cases:
        document = build(native, args.input_root, args.timed_root)
        target = out / document["case_id"] / "ground_truth_transforms.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dumps(document), encoding="utf-8")
        print(json.dumps({"case": native, "file": str(target), "sha256": sha(target)}))


if __name__ == "__main__":
    main()
