"""Write ground_truth_transforms.json (pcve_ground_truth/1) of suite cases from their native solves.

    python3 tools/export_ground_truth.py --suite DIR [--cases CASE ...] [--native CASE=SOLVE_DIR|accepted ...] [--blender BIN]

DIR is a suite being assembled (tools/publish_suite.py passes its staging folder); the published suite is refused, it
is only replaced by tools/publish_suite.py --publish. Every case runs Blender (CPU) with this file inside it:

* Accepted whole-clip solve (default for stiff_foam, light_ball, viscous_foam and remove_foam): Blender opens the
  accepted packed scene accepted_solves/packed/<case>.blend, into which that cache is baked. Every frame is checked against
  the cache (2e-6 m, 1e-5 rad); the ball, platen and flag poses are the scene's world matrices.
* Any other solve (--native CASE=SOLVE_DIR; default for source and light_ball_at_frame_8: the published re-solve in
  cases/<case_id>/native_metadata): SOLVE_DIR/simulation.npz and config.json (physics/physics.py output). The poses
  are computed from the cache the way appearance/scene.py bakes them (ball: translation (x, 0, z) and rotation about
  +y by its spin; platen: translation (0, 0, z); flag: rotation about +y by minus its lift angle at the hinge). Blender
  opens the accepted source packed scene for the camera and the hinge point, and the formulas are first checked
  against the accepted source cache baked into that scene (2e-6).
* --native CASE=accepted selects the first mode for the source as well.

Frame i is native sample 4(i-1) of the 96 Hz cache (t = (i-1)/24), 96 frames. The foam block is the centroid of its FEM
surface nodes with a translation-only matrix (present: false without foam). The camera is fixed (packed scene).
Output: DIR/cases/<case_id>/ground_truth_transforms.json.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CASE_DIR = HERE.parent
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]

SCENE = "silicone_block_chain"
CUP, BALL, FLAG = "Physical guided cup", "Steel marble", "Passive revolute flag"
CARRIER = "Native FEM carrier"
STRIDE, FRAMES, FPS = 4, 96, 24
TOL_M, TOL_RAD = 2e-6, 1e-5
FORMAT_VERSION = "pcve_ground_truth/1"
OBJECTS = {
    "guided_platen": {"object_name": CUP, "kind": "rigid", "present": True, "dimensions": [0.080, 0.074, 0.016],
                      "origin": "platen bottom centre (the cup object origin); dimensions are the approximate envelope of platen and cup"},
    "hinged_flag": {"object_name": FLAG, "kind": "rigid", "present": True, "dimensions": [0.070, 0.022, 0.002],
                    "origin": "hinge axis point"},
}
FOAM_DEFINITION = "centroid of the surface nodes of the native FEM foam mesh of the frame"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(4 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def label(path, suite):
    """A recorded file name: relative to the suite being written or to the repository, else absolute."""
    from scene_paths import REPO
    path = Path(path).resolve()
    for root in (Path(suite).resolve(), REPO.resolve()):
        if root in path.parents:
            return str(path.relative_to(root))
    return str(path)


def matrix(obj):
    return [[float(v) for v in row] for row in obj.matrix_world]


def mat_list(m):
    return [[float(m[i][j]) for j in range(4)] for i in range(4)]


def translation(p):
    return [[1., 0., 0., float(p[0])], [0., 1., 0., float(p[1])], [0., 0., 1., float(p[2])], [0., 0., 0., 1.]]


def quat_xyzw(m):
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


def entry(present, m=None):
    if not present or m is None:
        return {"present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
    m = mat_list(m)
    return {"present": True, "location": [m[0][3], m[1][3], m[2][3]], "quaternion_xyzw": quat_xyzw(m), "matrix_world": m}


def ry(angle):
    import numpy as np
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def formula_poses(cache, i, hinge):
    """Ball, platen and flag world matrices of native sample i, as appearance/scene.py bakes them."""
    import numpy as np
    plate, x, z, angle = (float(v) for v in cache["states"][i])
    ball = np.eye(4)
    ball[:3, :3] = ry(float(cache["ball_spin_rad"][i]))
    ball[:3, 3] = (x, 0., z)
    flag = np.eye(4)
    flag[:3, :3] = ry(-angle)
    flag[:3, 3] = hinge
    return ball, translation((0., 0., plate)), flag


def load_cache(path):
    import numpy as np
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def foam_track(cache):
    """Per-frame foam entries and the rest dimensions of the surface nodes (None without foam)."""
    import numpy as np
    if cache["elastic_positions"].size == 0:
        return [entry(False)] * FRAMES, None
    surface = np.unique(cache["elastic_faces"].ravel())
    track = []
    for f in range(FRAMES):
        item = entry(True, translation(cache["elastic_positions"][STRIDE * f][surface].mean(axis=0)))
        item["quaternion_xyzw"] = [0., 0., 0., 1.]
        track.append(item)
    return track, [float(v) for v in np.ptp(cache["elastic_rest"][surface], axis=0)]


def in_blender(case, out, native, suite):
    import bpy
    import numpy as np
    from scene_paths import cache as accepted_cache, catalog_id, packed

    scene = bpy.context.scene
    opened = Path(bpy.data.filepath).resolve()
    expected = packed("source" if native else case).resolve()
    if opened != expected:
        raise RuntimeError(f"open {expected}, not {opened}")
    cam = scene.camera
    if cam.data.sensor_fit not in ("AUTO", "HORIZONTAL") or (scene.render.resolution_x, scene.render.resolution_y) != (1280, 720):
        raise RuntimeError("expected a 1280x720 render with a horizontal sensor fit")
    camera = {"resolution": [1280, 720], "projection": "perspective", "lens_mm": float(cam.data.lens),
              "sensor_width_mm": float(cam.data.sensor_width), "sensor_fit": cam.data.sensor_fit,
              "shift_x": float(cam.data.shift_x), "shift_y": float(cam.data.shift_y), "matrix_world": matrix(cam)}
    cup, ball, flag = (bpy.data.objects[n] for n in (CUP, BALL, FLAG))
    worst = 0.0
    if native is None:
        solve = accepted_cache(case).parent
    else:
        solve = Path(native).resolve()
        # The formulas against the accepted source cache baked into this scene.
        reference = load_cache(accepted_cache("source"))
        scene.frame_set(1)
        hinge = list(flag.matrix_world.translation)
        for f in range(1, FRAMES + 1):
            scene.frame_set(f)
            for obj, pose in zip((ball, cup, flag), formula_poses(reference, STRIDE * (f - 1), hinge)):
                worst = max(worst, float(np.abs(np.array(matrix(obj)) - np.array(mat_list(pose))).max()))
        if worst >= TOL_M:
            raise RuntimeError(f"bake formulas differ from the accepted source scene by {worst}")
    config = json.loads((solve / "config.json").read_text())
    cache_path = solve / "simulation.npz"
    if config["case"] != case or config["cache_sha256"] != sha256(cache_path):
        raise RuntimeError(f"{solve} does not hold the solve of {case}")
    data = load_cache(cache_path)
    if np.abs(data["times"][np.arange(FRAMES) * STRIDE] - np.arange(FRAMES) / FPS).max() > 1e-9:
        raise RuntimeError("the cache is not sampled at (i-1)/24 every fourth sample")
    physics = config["physics"]
    ball_on = bool(physics.get("ball_present", [1])[0])   # DELETE steel_ball: present false
    foam, dimensions = foam_track(data)
    if native is None and (CARRIER in bpy.data.objects) != (dimensions is not None):
        raise RuntimeError("packed scene and native cache disagree on the foam block")
    rigid = {"steel_ball": [], "guided_platen": [], "hinged_flag": []}
    for f in range(1, FRAMES + 1):
        i = STRIDE * (f - 1)
        if native is None:
            scene.frame_set(f)
            plate, x, zb, angle = (float(v) for v in data["states"][i])
            errors = {"m": max(abs(cup.matrix_world.translation.z - plate), abs(ball.matrix_world.translation.x - x),
                               abs(ball.matrix_world.translation.y), abs(ball.matrix_world.translation.z - zb)),
                      "rad": max(abs(flag.rotation_euler.y + angle), abs(ball.rotation_euler.y - float(data["ball_spin_rad"][i])))}
            if dimensions is not None:
                carrier = bpy.data.objects[CARRIER]
                mesh = carrier.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
                co = np.empty(len(mesh.vertices) * 3)
                mesh.vertices.foreach_get("co", co)
                carrier.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
                m = np.array(carrier.matrix_world)
                errors["m"] = max(errors["m"], float(np.max(np.abs(co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
                                                                   - data["elastic_positions"][i]))))
            if errors["m"] > TOL_M or errors["rad"] > TOL_RAD:
                raise RuntimeError(f"frame {f}: packed scene differs from the cache ({errors})")
            worst = max(worst, errors["m"])
            poses = (matrix(ball), matrix(cup), matrix(flag))
        else:
            poses = formula_poses(data, i, hinge)
        for name, pose in zip(rigid, poses):
            rigid[name].append(entry(name != "steel_ball" or ball_on, pose))
    ball_record = {"object_name": BALL, "kind": "rigid", "present": True, "radius": physics["ball_radius_m"],
                   "mass_kg": physics["ball_mass_kg"]}
    if native is not None:
        ball_record["inner_radius_m"] = config["ball_inner_radius_m"]
    if not ball_on:
        ball_record = {"object_name": BALL, "kind": "rigid", "present": False}
    objects = {"steel_ball": ball_record, **json.loads(json.dumps(OBJECTS)),
               "foam_block": {"object_name": CARRIER, "kind": "deformable", "present": dimensions is not None,
                              "location_definition": FOAM_DEFINITION}}
    if dimensions is not None:
        objects["foam_block"]["dimensions"] = dimensions
    files = [cache_path, solve / "config.json"] + ([] if native else [packed(case)])
    source = {"how": ("Native 96 Hz cache, frame i = sample 4(i-1) (t=(i-1)/24); " +
                      ("poses computed from the cache as appearance/scene.py bakes them; hinge point and camera of the "
                       "accepted source packed scene." if native else
                       "ball, platen and flag poses are the world matrices of the accepted packed scene, checked against "
                       "the cache every frame; camera of the packed scene.") +
                      " Foam: centroid of the FEM surface nodes."),
              "files": [label(p, suite) for p in files], "sha256": {label(p, suite): sha256(p) for p in files if p.suffix != ".json"},
              "tool": "scripts/rigid_elastic/silicone_block_chain/tools/export_ground_truth.py",
              ("formula_check_vs_packed_scene_max_abs" if native else "max_scene_vs_cache_error_m"): worst}
    if config.get("timed_edit"):
        source["timed_edit"] = config["timed_edit"]
    frames = []
    for f in range(FRAMES):
        frame = {"frame_index": f + 1, "time_sec": f / FPS, "camera_matrix_world": mat_list(camera["matrix_world"])}
        frame.update({name: track[f] for name, track in rigid.items()})
        frame["foam_block"] = foam[f]
        frames.append(frame)
    gt = {"schema_version": 3, "format_version": FORMAT_VERSION, "scene": SCENE, "case_id": catalog_id(case),
          "fps": FPS, "frame_start": 1, "frame_end": FRAMES, "units": "m", "camera": camera, "objects": objects,
          "frames": frames, "source": source}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name("." + out.name + ".writing")
    tmp.write_text(json.dumps(gt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(out)
    print("GT_OK", case, out, worst, flush=True)


def main():
    from scene_paths import CASES, SUITE_SOLVES, TIMED_CASES, blender_runtime, catalog_id, media, packed, published_native
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--suite", type=Path, required=True, help="suite being assembled (not the published suite)")
    p.add_argument("--cases", nargs="+", choices=[*CASES, *TIMED_CASES], default=[*CASES, *TIMED_CASES])
    p.add_argument("--native", nargs="+", default=[], metavar="CASE=SOLVE_DIR|accepted",
                   help="solve folder (simulation.npz, config.json) of a case; default: the published re-solve for "
                        + ", ".join(SUITE_SOLVES) + ", the accepted packed scene for the others")
    p.add_argument("--blender", type=Path)
    a = p.parse_args()
    suite = a.suite.resolve()
    if suite == media().resolve():
        p.error("write into a staging suite; tools/publish_suite.py --publish replaces the published suite")
    native = dict(item.split("=", 1) for item in a.native)
    for case in a.cases:
        solve = native.get(case) or (published_native(case) if case in SUITE_SOLVES else None)
        if solve == "accepted":
            if case not in CASES:
                p.error(f"{case} has no accepted cache")
            solve = None
        out = suite / "cases" / catalog_id(case) / "ground_truth_transforms.json"
        command = [str(blender_runtime(a.blender)), "-b", "--factory-startup", str(packed("source" if solve else case)),
                   "--python-exit-code", "1", "--python", str(Path(__file__).resolve()), "--",
                   "--case", case, "--out", str(out), "--suite", str(suite), *(["--native", str(solve)] if solve else [])]
        subprocess.run(command, check=True, env={**os.environ, "CUDA_VISIBLE_DEVICES": ""})


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        main()
    else:
        argv = sys.argv[sys.argv.index("--") + 1:]
        q = argparse.ArgumentParser()
        q.add_argument("--case", required=True)
        q.add_argument("--out", type=Path, required=True)
        q.add_argument("--suite", type=Path, required=True)
        q.add_argument("--native", type=Path)
        args = q.parse_args(argv)
        in_blender(args.case, args.out, args.native, args.suite)
