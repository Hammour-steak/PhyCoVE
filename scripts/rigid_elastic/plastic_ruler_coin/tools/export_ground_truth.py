"""Write ground_truth_transforms.json for each case of the video suite from the native solves.

    .venv-rigid-elastic/bin/python tools/export_ground_truth.py --suite DIR [--cases source ...]

Per case the source is the accepted native solve (assets scenes/plastic_ruler_coin/accepted/physics/<case>): 97 states at
t = i/24 s, video frame f = state f - 1 (no interpolation). The fixed camera is the one the case's video was rendered
with: `<suite>/cases/<id>/native_metadata/camera.json` written by appearance/realism.py, or, for videos made with the
camera of the accepted delivery, its evaluated camera record (renders/plastic_ruler_coin/accepted/.../
camera_metadata.json). When the case folder holds the render receipts (native_metadata/render_replay.jsonl), every
frame's coin matrices are checked against them. Nothing is authored. Output: pcve_ground_truth/1
(scripts/pcve_ground_truth.py), 96 frames at 24 fps, converted from the per-frame native record without resampling.
The ruler is deformable and is located by the centroid of the physical strip surface (317.5 x 31 x 1.6 mm,
reconstructed from the centreline like physics/export_surface.py); the book on the clamped end is static scenery and
is left out.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
CASE_DIR = HERE.parent
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]
from scene_paths import CASES, CATALOG, DELIVERED_SUITE, REPO, cache_dir  # noqa: E402
from pcve_ground_truth import from_schema3, write  # noqa: E402

FRAMES, FPS = 96, 24
BOOK = {"bbox_min": [-0.200, -0.0875, 0.7616], "bbox_max": [0.000, 0.0875, 0.8216]}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rel(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO)) if REPO in path.parents else str(path)


def coin_matrix(x, z, angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, 0, -s, x], [0, 1, 0, 0], [s, 0, c, z], [0, 0, 0, 1]], float)


def load_camera(case, folder):
    own = folder / "native_metadata" / "camera.json"
    if own.is_file():
        cam = json.loads(own.read_text())
        source = rel(own)
        sensor_width, shift, lens, fit = cam["sensor_width_mm"], cam["shift"], cam["lens_mm"], cam["sensor_fit"]
        clip = cam.get("clip")
    else:
        delivered = DELIVERED_SUITE / "cases" / case / "camera_metadata.json"
        cam = json.loads(delivered.read_text())
        source = rel(delivered) + " (camera of the delivered suite)"
        sensor_width, shift, lens, fit = cam["sensor_width_mm"], [cam["shift_x"], cam["shift_y"]], cam["lens_mm"], cam["sensor_fit"]
        clip = None
    w, h = cam["resolution"]
    if fit not in ("AUTO", "HORIZONTAL") or w < h:
        raise RuntimeError("intrinsics below assume a horizontal sensor fit")
    fx = lens / sensor_width * w
    record = {"matrix_world": cam["matrix_world"],
              "intrinsics": [[fx, 0, w / 2 - shift[0] * w], [0, fx, h / 2 + shift[1] * w], [0, 0, 1]],
              "lens_mm": lens, "sensor_width_mm": sensor_width, "shift": shift,
              "convention": "Blender camera: looks along its local -Z, +Y up; world z up, metres; desk top at z = 0.760",
              "trajectory": "fixed"}
    if clip:
        record["clip"] = clip
    return record, [w, h], source


def strip_surface(cfg, sfree, curve):
    """Physical strip surface (both faces, 7 lines across the width) of one state, world metres."""
    s = np.r_[np.linspace(-cfg["ruler_clamped_length_m"], 0, 81)[:-1], sfree]
    free = s >= 0
    x, z, theta = s.copy(), np.full(len(s), cfg["ruler_midplane_z_m"]), np.zeros(len(s))
    x[free] = np.interp(s[free], sfree, curve[:, 0])
    z[free] = np.interp(s[free], sfree, curve[:, 1])
    theta[free] = np.interp(s[free], sfree, curve[:, 2])
    ys = np.linspace(-cfg["ruler_width_m"] / 2, cfg["ruler_width_m"] / 2, 7)
    points = []
    for sign in (-1, 1):
        off = sign * cfg["ruler_thickness_m"] / 2
        px, pz = x - np.sin(theta) * off, z + np.cos(theta) * off
        points.append(np.stack(np.broadcast_arrays(px[:, None], ys[None, :], pz[:, None]), -1).reshape(-1, 3))
    return np.concatenate(points)


def export(case, suite, cache=None, catalog_id=None):
    """cache / catalog_id: the solve folder and suite case id of a case outside CASES (default: the accepted solve)."""
    catalog_id = catalog_id or CATALOG[case]
    cache = Path(cache) if cache else cache_dir(case)
    folder = suite / "cases" / catalog_id
    out = folder / "ground_truth_transforms.json"
    config = json.loads((cache / "simulation_config.json").read_text())
    cfg = config["physics"]
    ruler_present = bool(cfg.get("ruler_present", [1])[0])   # DELETE ruler: no strip; the book lies on the desk
    book = BOOK if ruler_present else {"bbox_min": [-0.200, -0.0875, 0.7600], "bbox_max": [0.000, 0.0875, 0.8200]}
    npz = cache / "simulation.npz"
    with np.load(npz) as z:
        data = {k: z[k] for k in z.files}
    if not np.allclose(data["times"], np.arange(FRAMES + 1) / FPS, atol=1e-13, rtol=0):
        raise RuntimeError("native states are not at i/24 s")
    present = [bool(v) for v in data["present"]]
    camera, resolution, camera_source = load_camera(case, folder)
    receipts = {}
    journal = folder / "native_metadata" / "render_replay.jsonl"
    if journal.is_file():
        for line in journal.read_text().splitlines():
            entry = json.loads(line)
            receipts[entry["frame"]] = entry
    report = folder / "native_metadata" / "render_report.json"
    if not receipts and report.is_file():
        receipts = {e["frame"]: e for e in json.loads(report.read_text()).get("replay", [])}
    stations = list(range(0, len(data["arc_length"]), 10))
    coin_ids = ("coin", "second_coin")
    objects = {
        "coin": {"present": present[0], "kind": "rigid",
                 **({"mass": cfg["coin_mass_kg"], "radius_m": cfg["coin_radius_m"], "thickness_m": cfg["coin_thickness_m"],
                     "motion": "planar in the x-z plane (y = 0) with pitch about +y; local +z is the face normal"} if present[0] else {})},
        "second_coin": {"present": present[1], "kind": "rigid",
                        **({"mass": cfg["second_coin_mass_kg"], "radius_m": cfg["second_coin_radius_m"],
                            "thickness_m": cfg["second_coin_thickness_m"],
                            "motion": "planar in the x-z plane (y = 0) with pitch about +y; local +z is the face normal"} if present[1] else {})},
        "ruler": {"present": ruler_present, "deformable": True,
                  **({} if ruler_present else {"rest_dimensions_m": [cfg["ruler_clamped_length_m"] + cfg["ruler_free_length_m"],
                                                                 cfg["ruler_width_m"], cfg["ruler_thickness_m"]]}),
                  "length_m": cfg["ruler_clamped_length_m"] + cfg["ruler_free_length_m"], "width_m": cfg["ruler_width_m"],
                  "thickness_m": cfg["ruler_thickness_m"], "overhang_m": cfg["ruler_free_length_m"],
                  "clamped_length_m": cfg["ruler_clamped_length_m"], "young_modulus_pa": cfg["ruler_young_modulus_pa"],
                  "density_kg_m3": cfg["ruler_density_kg_m3"],
                  "clamp": "x <= 0 (under the book, on the desk top) is fixed; the free part x > 0 bends in the x-z plane",
                  "fields": "centreline_xz: solver centreline (x, z) at arc lengths centreline_s_m; free_end_*: last "
                            "station; surface_*: centroid and axis-aligned bounds of the strip's two faces "
                            "(7 lines across the width), world metres",
                  "centreline_s_m": [float(data["arc_length"][i]) for i in stations]},
        "book": {"present": True, "kind": "static", "mass": cfg["book_mass_kg"], **book,
                 "note": "holds the ruler down; not simulated (the clamp is the boundary condition)"},
    }
    frames, worst = [], 0.0
    for f in range(1, FRAMES + 1):
        i = f - 1
        entry = {}
        for b, name in enumerate(coin_ids):
            if not present[b]:
                entry[name] = {"present": False}
                continue
            x, zc, angle = (float(v) for v in data["coin_states"][i, b])
            vx, vz, omega = (float(v) for v in data["coin_velocities"][i, b])
            m = coin_matrix(x, zc, angle)
            if f in receipts and receipts[f]["coin_matrices"][b] is not None:
                err = float(np.max(np.abs(np.array(receipts[f]["coin_matrices"][b]) - m)))
                worst = max(worst, err)
                if err > 2e-6:
                    raise RuntimeError(f"{case} frame {f}: rendered {name} differs from the cache by {err:.3g}")
            entry[name] = {"present": True, "matrix_world": m.tolist(), "location": [x, 0.0, zc],
                           "pitch_rad": angle, "linear_velocity": [vx, 0.0, vz], "angular_velocity": [0.0, -omega, 0.0]}
        curve = data["beam_curves"][i]
        if not ruler_present:
            entry["ruler"] = {"present": False, "deformable": True}
            entry["book"] = {"present": True, "matrix_world": np.eye(4).tolist()}
            frames.append({"frame_index": f, "time_sec": float(data["times"][i]), "camera_matrix_world": camera["matrix_world"],
                           "objects": entry})
            continue
        surface = strip_surface(cfg, data["arc_length"], curve)
        entry["ruler"] = {"present": True, "deformable": True, "deformation_frame_index": i,
                          "matrix_world": np.eye(4).tolist(),
                          "centreline_xz": [[float(curve[k, 0]), float(curve[k, 1])] for k in stations],
                          "free_end_location": [float(curve[-1, 0]), 0.0, float(curve[-1, 1])],
                          "free_end_angle_rad": float(curve[-1, 2]),
                          "surface_centroid": surface.mean(0).tolist(),
                          "surface_bbox_min": surface.min(0).tolist(), "surface_bbox_max": surface.max(0).tolist()}
        entry["book"] = {"present": True, "matrix_world": np.eye(4).tolist()}
        frames.append({"frame_index": f, "time_sec": float(data["times"][i]), "camera_matrix_world": camera["matrix_world"],
                       "objects": entry})
    gt = {"schema_version": 3, "scene_id": "plastic_ruler_coin", "interaction_category": "rigid_elastic",
          "case_id": catalog_id, "native_case_id": case, "fps": FPS, "resolution": resolution,
          "frame_start": 1, "frame_end": FRAMES, "camera": camera, "objects": objects, "frames": frames,
          "source": {"native_cache": rel(npz), "native_cache_sha256": sha256(npz), "camera": camera_source,
                     "sampling": "video frame f = native state f - 1 (t = (f - 1) / 24 s); no interpolation",
                     "generator": "scripts/rigid_elastic/plastic_ruler_coin/tools/export_ground_truth.py",
                     "render_receipts_checked": len(receipts), "max_coin_matrix_vs_receipt": worst},
          "notes": "Native synthetic trajectory in SI units (x along the ruler, out from the desk edge at x = 0; z up). "
                   "Material, friction and contact values are nominal, not calibrated."}
    write(out, from_schema3(gt, "plastic_ruler_coin", catalog_id, skip=["book"],
                            tool=gt["source"]["generator"], files=[npz, cache / "simulation_config.json"]))
    print("GT_OK", case, out, "receipts", len(receipts), "max_err", worst, flush=True)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    p.add_argument("--suite", type=Path, required=True,
                   help="video suite root; cases/<id>/ground_truth_transforms.json are written in the pcve_ground_truth/1 layout")
    a = p.parse_args()
    suite = a.suite.resolve()
    for case in a.cases:
        export(case, suite)


if __name__ == "__main__":
    main()
