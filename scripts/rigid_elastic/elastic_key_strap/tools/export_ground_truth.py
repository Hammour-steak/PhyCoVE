"""Ground truth (pcve_ground_truth/1) of each case of a video suite from the native caches.

    python tools/export_ground_truth.py --out DIR [--cases CASE ...] [--suite DIR]

--suite (default: the published suite of scene_manifest.json) is read for the render camera and the timed merged
solve; --out writes DIR/<catalog id>/ground_truth_transforms.json. Without --out the files go into the suite,
which is refused for the published suites under renders/pcve_suites/ (tools/publish_suite.py writes into the
suite it is assembling).

Run with the scene's Python (numpy, scipy: .venv-rigid-elastic). For every case the accepted native solve
(`assets/scenes/elastic_key_strap/native_solves/cases/<case>/simulation.npz`, 97 states at 24 Hz) gives, per video
frame f = 1..96 (native state f-1, t = (f-1)/24 s), the world pose of the keyring and the two keys (MuJoCo body
frames: the ring centre and the ball-joint pivots; a key tag body is exported too when a solve has one) and the
silicone strap's mid-surface vertices.
Linear and angular velocities are the solver's own joint velocities (qvel) mapped to world frame through the
model's kinematic tree (free joint for the ring, ball joints for the keys); the layout is checked by
rebuilding every stored body pose from qpos, and the ring velocity is checked against the 240 Hz trace.
The fixed camera is the one recorded by the renderer in `cases/<case>/native_metadata/native_replay_audit.json`.
Nothing is authored. Output: `<out>/<catalog id>/ground_truth_transforms.json` or `<suite>/cases/<catalog id>/...` (layout A
of eval/metrics/common/traj_lib.py: frames[i][<object>] = present, location, quaternion_xyzw, matrix_world), 96 frames.
The strap is tracked by the centroid of its mid-surface vertices (identity rotation). A timed edit
(keys_mass_5x_at_frame_24) reads the merged native solve in inputs/native_timed/<case>/ of the suite it writes to.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

import numpy as np
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parent
CASE_DIR = HERE.parent
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]
from scene_paths import CASES, CATALOG, REPO, SCENE, TIMED_CASES, cache_dir, media  # noqa: E402

FPS, FRAMES, WIDTH, HEIGHT = 24, 96, 1280, 720
# Key bodies hang from the keyring at fixed pivots (physics/physics_model.py build_model, identical in every case).
KEY_PIVOT = {"key1": (-0.0065, -0.003, -0.009), "key2": (0.0065, 0.003, -0.009)}
KEY_REST_EULER_XYZ = {"key1": (0.025, -0.15, -0.04), "key2": (-0.025, 0.22, 0.04)}
KEY_MASS_SHARE = {"key1": 0.48, "key2": 0.52}
TOL_POSE = 1e-9


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rot(q_wxyz):
    q = np.asarray(q_wxyz, dtype=float)
    return Rotation.from_quat([q[1], q[2], q[3], q[0]])


def matrix(position, q_wxyz):
    m = np.eye(4)
    m[:3, :3] = rot(q_wxyz).as_matrix()
    m[:3, 3] = position
    return m.tolist()


def camera_record(audit_path):
    audit = json.loads(Path(audit_path).read_text())
    cam = audit["camera"]
    mw = np.array(cam["matrix_world"], dtype=float).reshape(4, 4)
    width, height = int(cam["width"]), int(cam["height"])
    if (width, height) != (WIDTH, HEIGHT):
        raise RuntimeError(f"camera recorded for {width}x{height}")
    fit = cam.get("sensor_fit", "AUTO")
    if fit not in ("AUTO", "HORIZONTAL"):
        raise RuntimeError("intrinsics below assume a horizontal sensor fit")
    shift = [float(cam.get("shift_x", 0.0)), float(cam.get("shift_y", 0.0))]
    fx = cam["lens"] / cam["sensor_width"] * width
    intrinsics = [[fx, 0.0, width / 2 - shift[0] * width], [0.0, fx, height / 2 + shift[1] * width], [0.0, 0.0, 1.0]]
    return mw.tolist(), {
        "matrix_world": mw.tolist(), "intrinsics": intrinsics, "lens_mm": cam["lens"],
        "sensor_width_mm": cam["sensor_width"], "sensor_fit": fit, "shift": shift,
        "clip": [cam.get("clip_start", 0.01), cam.get("clip_end", 30.0)],
        "convention": "Blender camera: looks along its local -Z, +Y up; world Z up, metres; wall plane y = 0.205, cabinet top z = 0.86",
        "trajectory": "fixed"}


def kinematics(z, config):
    """World poses and velocities of the rigid bodies from qpos/qvel; checked against the stored body poses."""
    names = [str(n) for n in z["body_names"]]
    nodes = 2 * config["mesh_rows"] if config["strap_present"][0] else 0
    qp, qv = z["qpos"], z["qvel"]
    o, v = 3 * nodes, 3 * nodes
    expected_nq = 3 * nodes + 7 + 4 * (len(names) - 1)
    if qp.shape[1] != expected_nq or qv.shape[1] != expected_nq - 1 - (len(names) - 1):
        raise RuntimeError(f"unexpected joint layout {qp.shape} {qv.shape} for {names}")
    ring_p, ring_q = qp[:, o:o + 3], qp[:, o + 3:o + 7]
    ring_v, ring_w_local = qv[:, v:v + 3], qv[:, v + 3:v + 6]
    out = {"keyring": {"p": ring_p, "q": ring_q, "v": ring_v,
                       "w": np.einsum("tij,tj->ti", rot_batch(ring_q), ring_w_local)}}
    fob_pivot = None  # pivots below are in the ring body frame
    if config["fob_present"][0]:
        ring_rest = np.array([0.0, config["anchor_m"][1], config["anchor_m"][2] - config["strap_length_m"] - config["ring_radius_m"]])
        ring_initial = ring_rest + np.array([config["initial_lateral_m"], 0.0, config["initial_lift_m"]])
        fob_pivot = tuple(np.array(config["fob_initial_location_m"]) - ring_initial)
    R_ring = rot_batch(ring_q)
    w_ring = out["keyring"]["w"]
    for k, name in enumerate(names[1:]):
        qa, va = o + 7 + 4 * k, v + 6 + 3 * k
        if name in KEY_PIVOT:
            pivot = np.array(KEY_PIVOT[name])
            e = KEY_REST_EULER_XYZ[name]
            q0 = Rotation.from_euler("xyz", e).as_quat()
            local_q = np.array([q0[3], q0[0], q0[1], q0[2]])
        elif name == "brass_fob":
            pivot, local_q = np.array(fob_pivot), np.array([1.0, 0.0, 0.0, 0.0])
        else:
            raise RuntimeError(f"unknown body {name}")
        q_ball = qp[:, qa:qa + 4]
        q_world = quat_mul(quat_mul(ring_q, np.broadcast_to(local_q, ring_q.shape)), q_ball)
        r = np.einsum("tij,j->ti", R_ring, pivot)
        p_world = ring_p + r
        w_world = w_ring + np.einsum("tij,tj->ti", rot_batch(q_world), qv[:, va:va + 3])
        out[name] = {"p": p_world, "q": q_world, "v": ring_v + np.cross(w_ring, r), "w": w_world}
    worst = 0.0
    for i, name in enumerate(names):
        worst = max(worst, float(np.abs(out[name]["p"] - z["body_positions"][:, i]).max()))
        dq = np.abs(np.einsum("ti,ti->t", out[name]["q"] / np.linalg.norm(out[name]["q"], axis=1)[:, None],
                              z["body_quaternions"][:, i]))
        worst = max(worst, float(np.abs(1.0 - dq).max()))
    if worst > TOL_POSE * 1e3:
        raise RuntimeError(f"qpos layout does not reproduce the stored body poses ({worst:.3g})")
    return names, out, worst


def rot_batch(q):
    q = np.asarray(q, dtype=float)
    return Rotation.from_quat(np.c_[q[:, 1:], q[:, :1]]).as_matrix()


def quat_mul(a, b):
    w1, x1, y1, z1 = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    w2, x2, y2, z2 = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2], axis=-1)


def rel(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def export(case, suite, audit=None, out_root=None, folder=None):
    # A timed case's merged native solve is kept with its suite (for the published suite this is cache_dir(case)).
    # folder: the native solve of a case outside the published catalog (e.g. a DELETE case).
    folder = folder or (suite / "inputs" / "native_timed" / case if case in TIMED_CASES else cache_dir(case))
    cache = folder / "simulation.npz"
    config = json.loads((folder / "resolved_config.json").read_text())
    report = json.loads((folder / "physics_audit.json").read_text())
    with np.load(cache) as f:
        z = {k: f[k] for k in f.files}
    if len(z["times"]) != FRAMES + 1 or np.abs(z["times"] - np.arange(FRAMES + 1) / FPS).max() > 1e-12:
        raise RuntimeError(f"{case}: cache is not 97 states at 24 Hz")
    ring = bool(config.get("keyring_present", [1])[0])   # DELETE keyring: no ring, keys or tag in the solve
    if ring:
        names, kin, pose_error = kinematics(z, config)
        trace = np.load(folder / "trace_240hz.npz")["values"]
        t240, ring240 = trace[:, 0], trace[:, 1:4]
        fd = np.gradient(ring240, t240, axis=0)
        idx = np.searchsorted(t240, z["times"][:FRAMES] - 1e-12)
        dev = np.linalg.norm(fd[idx] - kin["keyring"]["v"][:FRAMES], axis=1)
        ring_velocity_check = {"median": float(np.median(dev)), "p90": float(np.percentile(dev, 90)), "max": float(dev.max()),
                               "note": "central difference of the 240 Hz ring trace; the maxima sit at strap snap-taut and contact instants"}
    else:
        if len(z["body_names"]):
            raise RuntimeError(f"{case}: keyring_present = [0] but the solve has rigid bodies")
        names, kin, pose_error, ring_velocity_check = [], {}, 0.0, None
    strap = bool(config["strap_present"][0])
    fob = bool(config["fob_present"][0])
    target = suite / "cases" / CATALOG.get(case, "edit_" + case)
    audit = Path(audit or target / "native_metadata" / "native_replay_audit.json")
    cam_matrix, camera = camera_record(audit)
    timed = config.get("timed_edits")
    keys_mass = config["keys_mass_kg"]
    def mass_note(base):
        return base if not timed else {"before_edit": base, "after_edit": base * timed[0]["params"]["keys_mass_kg"] / keys_mass,
                                       "edit_frame": timed[0]["frame"]}
    objects = {
        "keyring": {"object_name": "keyring", "kind": "rigid", "present": True, "mass": config["ring_mass_kg"],
                    "radius": config["ring_radius_m"], "note": "steel split ring; body frame at the ring centre, ring plane x-z"},
        "key1": {"object_name": "key1", "kind": "rigid", "present": True, "member_of": "keys",
                 "mass": mass_note(keys_mass * KEY_MASS_SHARE["key1"]), "length": 0.059, "material": "nickel-plated key",
                 "note": "body frame at its ball-joint pivot on the ring"},
        "key2": {"object_name": "key2", "kind": "rigid", "present": True, "member_of": "keys",
                 "mass": mass_note(keys_mass * KEY_MASS_SHARE["key2"]), "length": 0.054, "material": "brass key",
                 "note": "body frame at its ball-joint pivot on the ring"},
    }
    if not ring:
        for name in objects:
            objects[name] = {"object_name": name, "kind": "rigid", "present": False, "note": "deleted with the keyring (DELETE keyring)"}
    if fob:
        objects["brass_fob"] = {"object_name": "brass_fob", "kind": "rigid", "present": True, "mass": config["fob_mass_kg"],
                                "dimensions": [0.016, 0.003, 0.028], "note": "brass key tag on the keyring; body frame at its ball-joint pivot"}
    rest = z["reference"]
    objects["strap"] = {"object_name": "strap", "kind": "deformable", "present": strap,
                        "dimensions": (rest.max(0) - rest.min(0)).tolist(),
                        **({"rest_length_m": config["strap_length_m"], "width_m": config["strap_width_m"],
                            "thickness_m": config["strap_thickness_m"], "young_modulus_pa": config["strap_young_modulus_pa"],
                            "viscosity_pa_s": config["strap_viscosity_pa_s"], "density_kg_m3": config["strap_density_kg_m3"],
                            "anchor_m": config["anchor_m"], "mid_surface_vertices": int(z["strap_vertices"].shape[1]),
                            "location_semantics": "centroid of the mid-surface vertices (simulation.npz strap_vertices)"}
                           if strap else {})}
    frames = []
    for f in range(1, FRAMES + 1):
        i = f - 1
        entry = {"frame_index": f, "time_sec": float(z["times"][i]), "camera_matrix_world": cam_matrix}
        for name in ("keyring", "key1", "key2", "brass_fob"):
            if not ring and name in objects:
                entry[name] = {"present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
            if name not in names:
                continue
            k = kin[name]
            q = k["q"][i] / np.linalg.norm(k["q"][i])
            entry[name] = {"present": True, "location": k["p"][i].tolist(), "quaternion_xyzw": [q[1], q[2], q[3], q[0]],
                           "matrix_world": matrix(k["p"][i], q), "linear_velocity": k["v"][i].tolist(),
                           "angular_velocity": k["w"][i].tolist()}
        if strap:
            xyz = z["strap_vertices"][i]
            rows = xyz.reshape(-1, 2, 3).mean(axis=1)
            c = xyz.mean(axis=0).tolist()
            entry["strap"] = {"present": True, "location": c, "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
                              "matrix_world": [[1.0, 0.0, 0.0, c[0]], [0.0, 1.0, 0.0, c[1]], [0.0, 0.0, 1.0, c[2]], [0.0, 0.0, 0.0, 1.0]],
                              "bbox_min": xyz.min(axis=0).tolist(), "bbox_max": xyz.max(axis=0).tolist(),
                              "centreline_length_m": float(np.linalg.norm(np.diff(rows, axis=0), axis=1).sum()),
                              "top_end": rows[0].tolist(), "bottom_end": rows[-1].tolist()}
        else:
            entry["strap"] = {"present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
        frames.append(entry)
    how = ("frame i = native state i-1 (t=(i-1)/24) of the MuJoCo 3.3.7 CPU solve the video replays; rigid bodies are the "
           "MuJoCo body frames (ring centre, key ball-joint pivots) rebuilt from qpos; strap = mid-surface vertex centroid")
    if timed:
        how += (f"; timed edit at frame {timed[0]['frame']}: frames 1..{timed[0]['frame'] - 1} are the source solve, later frames "
                "continue it from the exact source qpos/qvel with the edited key mass")
    files = [cache, folder / "resolved_config.json"]
    gt = {"schema_version": 3, "format_version": "pcve_ground_truth/1", "scene": SCENE, "case_id": CATALOG.get(case, "edit_" + case),
          "fps": FPS, "frame_start": 1, "frame_end": FRAMES, "units": "m",
          "camera": {"resolution": [WIDTH, HEIGHT], "projection": "perspective", "lens_mm": camera["lens_mm"],
                     "sensor_width_mm": camera["sensor_width_mm"], "sensor_fit": camera["sensor_fit"],
                     "shift_x": camera["shift"][0], "shift_y": camera["shift"][1], "matrix_world": cam_matrix,
                     "clip": camera["clip"], "convention": camera["convention"], "trajectory": "fixed"},
          "objects": objects, "frames": frames,
          "source": {"how": how, "files": [rel(x) for x in files], "sha256": {rel(x): sha256(x) for x in files},
                     "native_case_id": case, "solver": report.get("solver"), "camera_record": rel(audit),
                     "velocities": "solver joint velocities (qvel) mapped to world frame; body-origin linear velocity",
                     "generator": "scripts/rigid_elastic/elastic_key_strap/tools/export_ground_truth.py",
                     "max_pose_rebuild_error": pose_error, "ring_velocity_vs_240hz_trace_m_s": ring_velocity_check},
          "notes": "Native synthetic trajectory in SI units; world Z up. Material values are nominal "
                   "(uncalibrated silicone); keys collide through convex hulls of their meshes."}
    out = (out_root / CATALOG.get(case, "edit_" + case) if out_root else target) / "ground_truth_transforms.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name("." + out.name + ".writing")
    tmp.write_text(json.dumps(gt, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out)
    return {"case": case, "file": str(out), "pose_rebuild_error": pose_error,
            "ring_velocity_vs_trace": ring_velocity_check}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", nargs="+", choices=CASES + TIMED_CASES, default=list(CASES + TIMED_CASES))
    p.add_argument("--suite", type=Path, help="video suite root; default: the canonical suite of scene_manifest.json")
    p.add_argument("--out", type=Path, help="write <out>/<catalog id>/ground_truth_transforms.json")
    a = p.parse_args()
    suite = (a.suite or media()).resolve()
    published = (CASE_DIR.parents[2] / "renders" / "pcve_suites").resolve()
    if a.out is None and (suite == published or published in suite.parents):
        p.error("the published suites are read only: give --out <new folder>")
    for case in a.cases:
        print(json.dumps(export(case, suite, out_root=a.out)), flush=True)


if __name__ == "__main__":
    main()
