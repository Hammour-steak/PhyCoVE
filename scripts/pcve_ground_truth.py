"""Ground truth in the pcve_ground_truth/1 layout (read by eval/metrics/common/traj_lib.py).

Scene exporters first collect a per-frame native record in the schema-3 layout
(frames[i]["objects"][<name>] with matrix_world, location and, for deformable bodies, a surface or
vertex centroid; camera with lens, sensor or intrinsics, shift and matrix_world) and turn it into the
published layout with `from_schema3`. Nothing is resampled: frame i of the result is frame i of the
record, whose time must be (i - 1) / 24 s.

Rigid bodies: location = the recorded body centre ("location", else the matrix translation),
quaternion_xyzw = the nearest rotation to the recorded matrix_world, matrix_world = [that rotation |
location]. Deformable bodies: location = the recorded surface or vertex centroid, unit rotation, a
translation-only matrix_world and dimensions = the bounding box at the first frame the body is present.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

FORMAT_VERSION = "pcve_ground_truth/1"
FPS, FRAMES, WIDTH, HEIGHT = 24, 96, 1280, 720
REPO = Path(__file__).resolve().parents[1]

CENTROID_KEYS = ("surface_centroid", "centroid_m", "centroid", "vertex_centroid")
BBOX_KEYS = (("surface_bbox_min", "surface_bbox_max"), ("bbox_min_m", "bbox_max_m"), ("bbox_min", "bbox_max"),
             ("vertex_bbox_min", "vertex_bbox_max"), ("coil_bbox_min", "coil_bbox_max"))
CENTROID_TEXT = {
    "surface_centroid": "centroid of the solver surface vertices (old field surface_centroid)",
    "centroid_m": "centroid of the native vertex/node positions (old field centroid_m)",
    "centroid": "centroid of the native surface/node positions (old field centroid)",
    "vertex_centroid": "centroid of the band vertices (old field vertex_centroid)",
    "coil_bbox": "centre of the coil bounding box (old fields coil_bbox_min/max; the helix vertex centroid is not stored)",
}
RECORD_KEYS = ("source", "sources", "native_source", "native_cache", "native_ground_truth_sha256",
               "coordinate_system", "coordinate_frame", "world", "time_sampling", "frame_time", "generator")


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _rel(path) -> str:
    path = Path(path).resolve()
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _quat_xyzw(R):
    R = np.asarray(R, float)
    R = R / np.linalg.norm(R, axis=0)
    t = np.trace(R)
    if t > 0:
        q = 0.5 / math.sqrt(t + 1.0)
        w, x, y, z = 0.25 / q, (R[2, 1] - R[1, 2]) * q, (R[0, 2] - R[2, 0]) * q, (R[1, 0] - R[0, 1]) * q
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        q = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w, x, y, z = (R[2, 1] - R[1, 2]) / q, 0.25 * q, (R[0, 1] + R[1, 0]) / q, (R[0, 2] + R[2, 0]) / q
    elif R[1, 1] > R[2, 2]:
        q = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w, x, y, z = (R[0, 2] - R[2, 0]) / q, (R[0, 1] + R[1, 0]) / q, 0.25 * q, (R[1, 2] + R[2, 1]) / q
    else:
        q = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w, x, y, z = (R[1, 0] - R[0, 1]) / q, (R[0, 2] + R[2, 0]) / q, (R[1, 2] + R[2, 1]) / q, 0.25 * q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    q = [x / n, y / n, z / n, w / n]
    if q[3] < 0:
        q = [-c for c in q]
    return q


def _f3(v):
    return [float(c) for c in v]


def _rows(m):
    return [[float(c) for c in r] for r in np.asarray(m, float)]


def _deformable_location(entry):
    for k in CENTROID_KEYS:
        if isinstance(entry.get(k), list) and len(entry[k]) == 3:
            return _f3(entry[k]), k
    if isinstance(entry.get("coil_bbox_min"), list):
        return _f3((np.asarray(entry["coil_bbox_min"]) + np.asarray(entry["coil_bbox_max"])) / 2), "coil_bbox"
    return None, None


def _bbox(entry):
    for a, b in BBOX_KEYS:
        if isinstance(entry.get(a), list) and isinstance(entry.get(b), list):
            return np.asarray(entry[a], float), np.asarray(entry[b], float)
    return None


def _size(meta, first, kind, key, sizes, notes):
    for k in ("radius_m", "radius"):
        if isinstance(meta.get(k), (int, float)) and kind == "rigid":
            r = float(meta[k])
            h = meta.get("height_m") or meta.get("thickness_m")
            return {"dimensions": [2 * r, 2 * r, float(h)]} if h else {"radius": r}
    for k in ("dimensions_m", "dimensions", "rest_dimensions_m", "envelope_m"):
        if isinstance(meta.get(k), list) and len(meta[k]) == 3:
            return {"dimensions": _f3(meta[k])}
    if key in sizes:
        value, source = sizes[key]
        notes.append(f"{key}: size from {source}")
        return dict(value) if isinstance(value, dict) else {"dimensions": [float(c) for c in value]}
    if kind == "deformable" and first is not None:
        bb = _bbox(first)
        if bb is not None:
            return {"dimensions": _f3(bb[1] - bb[0])}
    return None


def _camera(old, case_id, notes):
    cam = old["camera"]
    lens = float(cam["lens_mm"])
    fx = float(cam["intrinsics"][0][0]) if cam.get("intrinsics") else None
    sw = cam.get("sensor_width_mm")
    if sw is None:
        sw = round(lens * WIDTH / fx, 6)
        notes.append(f"camera.sensor_width_mm {sw} derived from the recorded intrinsics (fx={fx})")
    sw = float(sw)
    if fx is not None and abs(fx - lens / sw * WIDTH) > 1e-3 * fx:
        raise ValueError(f"{case_id}: intrinsics fx {fx} disagree with lens/sensor {lens}/{sw}")
    if fx is not None and abs(float(cam["intrinsics"][0][2]) - WIDTH / 2) > 1e-6:
        raise ValueError(f"{case_id}: principal point is not the image centre")
    shift = cam.get("shift") or [0.0, 0.0]
    resolution = cam.get("resolution") or old.get("resolution")
    if resolution is not None and list(resolution) != [WIDTH, HEIGHT]:
        raise ValueError(f"{case_id}: resolution {resolution}")
    camera = {"resolution": [WIDTH, HEIGHT], "projection": "perspective", "lens_mm": lens, "sensor_width_mm": sw,
              "sensor_fit": str(cam.get("sensor_fit") or "AUTO").upper(), "shift_x": float(shift[0]),
              "shift_y": float(shift[1]), "matrix_world": _rows(cam["matrix_world"]),
              "convention": "Blender camera: looks along its local -Z, +Y up"}
    if cam.get("name"):
        camera["name"] = cam["name"]
    return camera


def from_schema3(old: dict, scene: str, case_id: str, *, skip=(), names=None, sizes=None, deformable=(),
                 tool=None, files=(), how=None) -> dict:
    """pcve_ground_truth/1 record of one case from its schema-3 native record.

    case_id: the case folder in the video suite (source / edit_<name>). skip: static scenery that no
    edit names, left out. names: rendered object name per body when it differs from the key. sizes:
    {key: (value, source text)} for bodies whose record has no size, value either {"radius": r} or
    [x, y, z]. deformable: keys to treat as deformable even when the record has no centroid field.
    files: the native inputs, recorded with their sha256.
    """
    names, sizes, skip = names or {}, sizes or {}, set(skip)
    if old.get("schema_version") != 3:
        raise ValueError(f"{case_id}: not a schema-3 native record")
    fr = old["frames"]
    if len(fr) != FRAMES:
        raise ValueError(f"{case_id}: {len(fr)} frames, expected {FRAMES}")
    for i, f in enumerate(fr):
        if f["frame_index"] != i + 1 or abs(f["time_sec"] - i / FPS) > 1e-6:
            raise ValueError(f"{case_id}: frame {i + 1} index/time {f['frame_index']} {f['time_sec']}")
    notes = []
    camera = _camera(old, case_id, notes)
    keys = []
    for f in fr:
        for k in f["objects"]:
            if k not in keys and k not in skip:
                keys.append(k)
    meta_all = old.get("objects") or {}
    kinds, locsrc, maxdiff = {}, {}, {}
    for k in keys:
        meta = meta_all.get(k) or {}
        entries = [f["objects"].get(k) for f in fr]
        is_deformable = any(isinstance(e, dict) and (e.get("deformable") or _deformable_location(e)[0] is not None
                                                     and "location" not in e) for e in entries)
        kinds[k] = "deformable" if is_deformable or meta.get("deformable") or k in deformable else "rigid"
    frames = []
    for i, f in enumerate(fr):
        nf = {"frame_index": i + 1, "time_sec": i / FPS, "camera_matrix_world": _rows(f["camera_matrix_world"])}
        for k in keys:
            e = f["objects"].get(k)
            if e is None or e.get("present") is False:
                nf[k] = {"present": False, "location": None, "quaternion_xyzw": None, "matrix_world": None}
                continue
            if kinds[k] == "rigid":
                if "matrix_world" not in e:
                    raise ValueError(f"{case_id}/{k}: rigid entry without matrix_world at frame {i + 1}")
                M = np.asarray(e["matrix_world"], float)
                U, S, Vt = np.linalg.svd(M[:3, :3])
                R = U @ Vt
                if np.linalg.det(R) < 0:
                    raise ValueError(f"{case_id}/{k}: reflected matrix_world at frame {i + 1}")
                if np.max(np.abs(S - 1)) > 1e-4:
                    notes.append(f"{k}: old matrix_world is not a pure rotation (singular values up to "
                                 f"{float(np.max(np.abs(S - 1))):.2g} off 1); nearest rotation used")
                loc = M[:3, 3]
                if isinstance(e.get("location"), list):
                    maxdiff[k] = max(maxdiff.get(k, 0.0), float(np.max(np.abs(np.asarray(e["location"]) - M[:3, 3]))))
                    loc = np.asarray(e["location"], float)
                Mn = np.eye(4)
                Mn[:3, :3], Mn[:3, 3] = R, loc
                rec = {"present": True, "location": _f3(loc), "quaternion_xyzw": _quat_xyzw(R), "matrix_world": _rows(Mn)}
                for vk in ("linear_velocity", "angular_velocity"):
                    if isinstance(e.get(vk), list):
                        rec[vk] = _f3(e[vk])
                nf[k] = rec
            else:
                loc, src = _deformable_location(e)
                if loc is None:
                    raise ValueError(f"{case_id}/{k}: deformable entry without a centroid at frame {i + 1}: {sorted(e)}")
                locsrc[k] = src
                M = np.eye(4)
                M[:3, 3] = loc
                rec = {"present": True, "location": loc, "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0], "matrix_world": _rows(M)}
                bb = _bbox(e)
                if bb is not None:
                    rec["bbox_min"], rec["bbox_max"] = _f3(bb[0]), _f3(bb[1])
                nf[k] = rec
        frames.append(nf)
    objects = {}
    for k in keys:
        meta = meta_all.get(k) or {}
        first = fr[0]["objects"].get(k)
        first_present = next((f["objects"][k] for f in fr if isinstance(f["objects"].get(k), dict)
                              and f["objects"][k].get("present") is not False), None)
        size = _size(meta, first_present, kinds[k], k, sizes, notes)
        o = {"object_name": names.get(k, k), "kind": kinds[k],
             "present": bool(isinstance(first, dict) and first.get("present") is not False)}
        if size:
            o.update(size)
        else:
            notes.append(f"{k}: no size recorded")
        if kinds[k] == "deformable":
            o["location_definition"] = CENTROID_TEXT.get(locsrc.get(k), "n/a (never present)")
            o["dimensions_definition"] = ("rest_dimensions_m of the old record" if "rest_dimensions_m" in meta
                                          else "axis-aligned bounding box at the first frame the body is present")
        for mk in ("mass", "label", "description", "added_by_edit", "static", "fixed"):
            if mk in meta:
                o[mk] = meta[mk]
        objects[k] = o
    for k, d in maxdiff.items():
        if d > 1e-6:
            notes.append(f"{k}: old matrix_world is the transform applied to world-placed rest geometry; its "
                         f"translation differs from the recorded body centre (\"location\") by up to {d:.3g} m, "
                         "so matrix_world = [rotation of the old matrix | location]")
    files = [Path(p) for p in files]
    return {
        "schema_version": old.get("schema_version", 1), "format_version": FORMAT_VERSION,
        "scene": scene, "case_id": case_id, "fps": FPS, "frame_start": 1, "frame_end": FRAMES, "units": "m",
        "camera": camera, "objects": objects, "frames": frames,
        "source": {
            "how": how or ("Native per-frame record converted without resampling (frame i = native state at "
                           "t=(i-1)/24 s, checked). Rigid bodies: location = recorded body centre (\"location\", "
                           "else the matrix translation), quaternion_xyzw = rotation of the recorded matrix_world, "
                           "matrix_world = [that rotation | location]. Deformable bodies: location = recorded "
                           "surface/vertex centroid, unit rotation, translation-only matrix_world, dimensions = "
                           "first-frame bounding box. Static scenery that no edit names is left out: "
                           + (", ".join(sorted(skip)) or "none") + "."),
            "tool": tool,
            "files": [_rel(p) for p in files],
            "sha256": {_rel(p): sha256(p) for p in files},
            "native_record": {k: old[k] for k in RECORD_KEYS if k in old},
            "notes": sorted(set(notes)),
        },
    }


def check(gt: dict, where="") -> None:
    """Raise unless gt is a 96-frame, 24 fps pcve_ground_truth/1 record."""
    problems = []
    if gt.get("format_version") != FORMAT_VERSION:
        problems.append(f"format_version {gt.get('format_version')!r}")
    if gt.get("fps") != FPS or gt.get("frame_start") != 1 or gt.get("frame_end") != FRAMES:
        problems.append("fps/frame range")
    frames = gt.get("frames")
    if not isinstance(frames, list) or len(frames) != FRAMES:
        problems.append("frame count")
    elif any(f.get("frame_index") != i + 1 or abs(f.get("time_sec", -1) - i / FPS) > 1e-6 for i, f in enumerate(frames)):
        problems.append("frame clock")
    camera = gt.get("camera") or {}
    if camera.get("resolution") != [WIDTH, HEIGHT] or not isinstance(camera.get("sensor_width_mm"), (int, float)):
        problems.append("camera")
    if not gt.get("objects"):
        problems.append("no objects")
    if problems:
        raise ValueError(f"{where or gt.get('case_id')}: not {FORMAT_VERSION}: {', '.join(problems)}")


def check_suite(suite) -> int:
    """check() every cases/<id>/ground_truth_transforms.json of a suite; returns the number checked."""
    n = 0
    for case in sorted(p for p in (Path(suite) / "cases").iterdir() if p.is_dir()):
        path = case / "ground_truth_transforms.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        check(json.loads(path.read_text(encoding="utf-8")), str(path))
        n += 1
    return n


def write(path, gt: dict) -> Path:
    """check() and write atomically (indent 1, as the published suites); creates the parent folder."""
    check(gt, str(path))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".writing")
    tmp.write_text(json.dumps(gt, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
