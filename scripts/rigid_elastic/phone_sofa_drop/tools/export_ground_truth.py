#!/usr/bin/env python3
"""Write ground_truth_transforms.json for one case from its native solver cache (no Blender).

  export_ground_truth.py --case CASE --out FILE [--clock 4s|3s]

--clock 4s (default, the current suite): 1280x720, 24 FPS, frames 1-96; frame f shows the native
  240 Hz state 10 (f - 1), i.e. t = (f - 1) / 24, from assets/scenes/phone_sofa_drop/solves_4s_240hz/<case>/
  simulation_dense.npz. Written in the pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py): the
  per-frame native record converted without resampling.
--clock 3s: the accepted 30 FPS clock of the 0-3 s reference caches (frames 1-91, t = (f - 1) / 30) from
  assets/scenes/phone_sofa_drop/solves_3s_30hz/<case>/simulation.npz. pcve_ground_truth/1 is fixed at 24 FPS and
  96 frames, so this clock writes the native per-frame record itself (schema_version 3).

Everything is read, nothing is fitted: the phone pose is the solver's rigid-body transform (the
same matrix Blender plays back on "phone | rigid COM root"), velocities are the solver's, the
deformable cushion and the added pillow are summarised per frame by the centroid and the
axis-aligned bounds of their solver surface vertices, plus the index of the full state in the
cache. The camera is the fixed camera of the packed scenes (identical in all six cases).
Needs numpy (.venv-rigid-elastic).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

SCENE = Path(__file__).resolve().parents[1]
SCRIPTS = SCENE.parents[1]
sys.path.insert(0, str(SCRIPTS))
from pcve_assets import asset  # noqa: E402
from pcve_ground_truth import from_schema3, write  # noqa: E402

SPEC = json.loads((SCENE / "scene_spec.json").read_text(encoding="utf-8"))
CASES = ("source", *SPEC["edit_dsl"])
CLOCKS = {
    "4s": {"cache": "solves_4s_240hz/{case}/simulation_dense.npz", "fps": 24, "frames": 96, "rate": 240},
    "3s": {"cache": "solves_3s_30hz/{case}/simulation.npz", "fps": 30, "frames": 91, "rate": 30},
}
CAMERA_SOURCE = "packed/source/ground_truth_transforms.json"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            h.update(block)
    return h.hexdigest()


def r(values, digits=7):
    return [round(float(v), digits) for v in values]


def camera():
    packed = json.loads(asset(f"scenes/phone_sofa_drop/{CAMERA_SOURCE}").read_text(encoding="utf-8"))["camera"]
    cam = {k: packed[k] for k in ("matrix_world", "intrinsics", "lens_mm", "sensor_width_mm", "location", "target",
                                   "focus_target", "fstop")}
    cam.update(shift=[0.0, 0.0], resolution=[1280, 720], sensor_fit="AUTO",
               trajectory="fixed; identical in all six cases", source=f"assets/scenes/phone_sofa_drop/{CAMERA_SOURCE}")
    return cam


def summary(points):
    return {"centroid": r(points.mean(0)), "bbox_min": r(points.min(0)), "bbox_max": r(points.max(0))}


def export(case, out, clock="4s"):
    c = CLOCKS[clock]
    cache_path = asset("scenes/phone_sofa_drop/" + c["cache"].format(case=case))
    z = np.load(cache_path, allow_pickle=False)
    times = z["times"]
    stride = c["rate"] // c["fps"]
    if len(times) < (c["frames"] - 1) * stride + 1:
        raise ValueError(f"{case}: cache too short for the {clock} clock")
    phys = {**SPEC["baseline"], **SPEC["cases"][case]}
    cushion = bool(z["cushion_present"])
    pillow = bool(z["pillow_present"])
    T, lin, ang = z["phone_transforms"], z["phone_linear_velocity"], z["phone_angular_velocity"]
    surf = z["surface_positions"] if cushion else None
    pil = z["pillow_render_boundary_positions"] if pillow else None
    cam = camera()
    gt = {
        "schema_version": 3,
        "scene_id": "phone_sofa_drop",
        "case_id": case,
        "interaction_category": "rigid_elastic",
        "fps": c["fps"],
        "resolution": [1280, 720],
        "frame_start": 1,
        "frame_end": c["frames"],
        "time_convention": f"frame f shows t = (f - 1) / {c['fps']} s",
        "units": {"length": "m", "time": "s", "mass": "kg", "angle": "rad"},
        "coordinate_frame": "Blender world, z up; phone matrix_world is its rigid-body centre-of-mass frame",
        "camera": cam,
        "native_cache": {"path": "assets/scenes/phone_sofa_drop/" + c["cache"].format(case=case),
                         "sha256": sha(cache_path), "state_rate_hz": c["rate"], "states_per_frame": stride},
        "objects": {
            "phone": {"present": bool(z["phone_present"]), "deformable": False, "mass": phys["phone_mass_kg"],
                      "dimensions": SPEC["phone_dimensions_m"], "contact_friction": phys["phone_contact_friction"]},
            "cushion": {"present": cushion, "deformable": True,
                        "young_modulus": phys["cushion_young_modulus_pa"],
                        "summary": "centroid and axis-aligned bounds of the solver surface vertices"},
            "landing_pillow": {"present": pillow, "deformable": True,
                               **({"young_modulus": phys["pillow_young_modulus_pa"],
                                   "summary": "centroid and axis-aligned bounds of the rendered boundary vertices"}
                                  if pillow else {})},
        },
        "frames": [],
    }
    for f in range(1, c["frames"] + 1):
        k = (f - 1) * stride
        t = float(times[k])
        if abs(t - (f - 1) / c["fps"]) > 1e-9:
            raise ValueError(f"{case}: frame {f} is not on the native state t = {(f - 1) / c['fps']}")
        row = {"frame_index": f, "time_sec": round(t, 9), "state_index": k,
               "camera_matrix_world": cam["matrix_world"],
               "objects": {
                   "phone": {"present": True, "matrix_world": [r(v, 9) for v in T[k]],
                             "location": r(T[k][:3, 3], 9), "linear_velocity": r(lin[k]),
                             "angular_velocity": r(ang[k])},
                   "cushion": {"present": cushion, "deformable": True,
                               **({"deformation_state_index": k, **summary(surf[k])} if cushion else {})},
                   "landing_pillow": {"present": pillow, "deformable": True,
                                      **({"deformation_state_index": k, **summary(pil[k])} if pillow else {})},
               }}
        gt["frames"].append(row)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if clock == "4s":
        write(out, from_schema3(gt, "phone_sofa_drop", "source" if case == "source" else f"edit_{case}",
                                tool="scripts/rigid_elastic/phone_sofa_drop/tools/export_ground_truth.py",
                                files=[cache_path, asset(f"scenes/phone_sofa_drop/{CAMERA_SOURCE}")]))
    else:
        out.write_text(json.dumps(gt, indent=1) + "\n", encoding="utf-8")
    return {"case": case, "clock": clock, "frames": len(gt["frames"]), "out": str(out), "sha256": sha(out)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", choices=CASES, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--clock", choices=tuple(CLOCKS), default="4s")
    a = p.parse_args()
    print(json.dumps(export(a.case, a.out, a.clock)))


if __name__ == "__main__":
    main()
