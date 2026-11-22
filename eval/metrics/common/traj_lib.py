"""Ground-truth helpers for the simulated cases: read ground_truth_transforms.json, bring its object layouts to one
form, and project object origins into the image.

The ground truth does not use one schema. Three layouts appear across the scenes, so everything goes through
normalise() first:

  A  nested dict     frame["mallet_0"]        = {present, matrix_world, ...}
  B  prefix-flat     frame["ball_matrix_world"], frame["ball_location"], ...
  C  list            frame["stones"]          = [{matrix_world, ...}, ...]
                     names come from gt["objects"]["stones"][i]["object_name"]

Projection is exact, since the camera matrices are in the ground truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

META = {"frame_index", "time_sec", "camera_matrix_world",
        "camera_world_to_camera_matrix"}


# ------------------------------------------------------------------ normalise
def _apparent_radius(spec) -> float | None:
    """Half the largest full dimension of a shape record, or None.

    The metric's scale is "how big does this look on screen", so a sphere, a
    cylinder and a box all have to reduce to one number, and every spelling
    the generators use has to land here:

      radius / r / radius_m_scene_units   round things, doubled to a diameter
      edge                                mahjong_dice's cubes
      hx, hy, hz / half_extents           half extents, doubled
      dimensions / dimensions_scene_units full sides
      width / height / thickness / length full sides
      h                                   a cylinder's height

    A cylinder carries both a radius and a height and the larger is what fills
    the mask, so everything is converted to FULL dimensions, maxed, and halved.
    """
    if not isinstance(spec, dict):
        return None
    full: list[float] = []
    for kk in ("radius", "r", "radius_m_scene_units"):
        v = spec.get(kk)
        if isinstance(v, (int, float)) and v:
            full.append(2.0 * float(v))
    for kk in ("edge", "width", "height", "thickness", "length", "h"):
        v = spec.get(kk)
        if isinstance(v, (int, float)) and v:
            full.append(float(v))
    for kk in ("dimensions", "dimensions_scene_units"):
        full += [float(d) for d in (spec.get(kk) or [])
                 if isinstance(d, (int, float)) and d]
    full += [2.0 * float(d) for d in (spec.get("half_extents") or [])
             if isinstance(d, (int, float)) and d]
    full += [2.0 * float(spec[kk]) for kk in ("hx", "hy", "hz")
             if isinstance(spec.get(kk), (int, float)) and spec.get(kk)]
    return max(full) / 2.0 if full else None


def normalise(gt: dict) -> dict[str, dict]:
    """-> {object_name: {"mw": (T,4,4) with NaN when absent, "radius": float|None}}"""
    frames = gt["frames"]
    T = len(frames)
    top = gt.get("objects", {})
    out: dict[str, dict] = {}

    def put(name, t, mw, present=True):
        rec = out.setdefault(name, {"mw": np.full((T, 4, 4), np.nan), "radius": None})
        if present and mw is not None:
            rec["mw"][t] = np.asarray(mw, dtype=np.float64)

    for t, fr in enumerate(frames):
        for k, v in fr.items():
            if k in META:
                continue
            # B first: "<name>_matrix_world" -- its value is a 4x4 nested list,
            # so testing isinstance(list) before this would swallow it.
            if k.endswith("_matrix_world"):
                put(k[: -len("_matrix_world")], t, v, True)
                continue
            # C: list of per-object dicts
            if isinstance(v, list):
                meta = top.get(k) or []
                for i, item in enumerate(v):
                    if not isinstance(item, dict):
                        continue
                    nm = None
                    if i < len(meta) and isinstance(meta[i], dict):
                        nm = meta[i].get("object_name")
                    nm = nm or f"{k}_{i}"
                    alive = item.get("present", item.get("active", True))
                    put(nm, t, item.get("matrix_world"), alive)
            # A: nested dict carrying matrix_world
            elif isinstance(v, dict) and "matrix_world" in v:
                alive = v.get("present", v.get("active", True))
                put(k, t, v.get("matrix_world"), alive)

    # A DELETE case does not stop writing matrices: pool_collision's removed
    # cue ball still has a matrix_world on every frame, and only
    # objects.cue_ball.present / physics.objects.cue_ball.active say it was
    # never rendered. Left alone, the removed object looks present and gets
    # scored against a trajectory that is not on screen.
    phys_objs = (gt.get("physics", {}) or {}).get("objects", {}) or {}
    for k, meta in top.items():
        entries = meta if isinstance(meta, list) else [meta]
        for i, m in enumerate(entries):
            if not isinstance(m, dict):
                continue
            names = [m.get("object_name"),
                     f"{k}_{i}" if isinstance(meta, list) else k]
            pm = phys_objs.get(k) if isinstance(phys_objs.get(k), dict) else {}
            dead = (m.get("present") is False or m.get("active") in (0, False)
                    or pm.get("active") in (0, False))
            if not dead:
                continue
            for nm in names:
                if nm in out:
                    out[nm]["mw"][:] = np.nan

    # radii, where the ground truth bothers to record them
    geo = gt.get("physics", {}).get("geometry", {}) or {}
    generic_r = next((float(v) for kk, v in geo.items()
                      if "radius" in kk.lower() and isinstance(v, (int, float))), None)

    def _fill(candidates, r):
        """First writer wins, so the passes below run most-specific first."""
        if not isinstance(r, (int, float)) or not r:
            return
        for nm in candidates:
            if nm in out and out[nm]["radius"] is None:
                out[nm]["radius"] = float(r)

    # The name a track is filed under is the frame key for layouts A/B
    # ("ball") but object_name for layout C ("bowling_pin_0"), and the two
    # disagree -- bowling's ball is objects["ball"] with object_name
    # "bowling_ball". Try every spelling, or the radius is silently dropped.
    for k, meta in top.items():
        entries = meta if isinstance(meta, list) else [meta]
        for i, m in enumerate(entries):
            if not isinstance(m, dict):
                continue
            _fill((m.get("object_name"),
                   f"{k}_{i}" if isinstance(meta, list) else k),
                  _apparent_radius(m))

    # physics.objects records sizes too, and for half the scenes it is the only
    # place they appear: objects.soccer_ball has no radius at all while
    # physics.objects.soccer_ball.radius is 0.11.
    phys = (gt.get("physics", {}) or {}).get("objects", {}) or {}
    for key, tgt in _physics_map(gt, list(out)).items():
        _fill(tgt, _apparent_radius(phys.get(key)))

    # A third spelling, and for dining_chain the only one: physics.objects is
    # empty there and the shapes live in physics.objects_geometry, keyed by the
    # render name -- {"cup": {"kind": "cyl", "r": 0.044, "h": 0.16}}. Without
    # this pass that whole scene has no radius at all.
    for key, spec in ((gt.get("physics", {}) or {}).get(
            "objects_geometry", {}) or {}).items():
        meta = top.get(key)
        if isinstance(meta, list):
            names = _group_names(meta, key)
        else:
            names = [key] + ([meta.get("object_name")]
                             if isinstance(meta, dict) else [])
        _fill([n for n in names if n], _apparent_radius(spec))

    for rec in out.values():
        if rec["radius"] is None:
            rec["radius"] = generic_r
    return out


def _group_names(meta: list, key: str) -> list[str]:
    return [(m.get("object_name") or f"{key}_{i}") if isinstance(m, dict)
            else f"{key}_{i}" for i, m in enumerate(meta)]


def _physics_map(gt: dict, names: list[str]) -> dict[str, list[str]]:
    """-> {physics.objects key: the render names it describes, in index order}.

    physics.objects and the rendered object list are written by different parts
    of the generator and do not have to agree. Four spellings occur:

      cue_ball:  {mass: ...}                 key is the render name
      dominoes:  {masses: [...], ...}        group of arrays, index -> name
      mallet_masses: [...]                   bare array, index -> name
      ball:      {mass: ...}                 ramp_collision's falling_marble,
                                             which physics calls something else
    """
    top = gt.get("objects", {}) or {}
    phys = (gt.get("physics", {}) or {}).get("objects", {}) or {}
    out: dict[str, list[str]] = {}
    used: set[str] = set()

    for k, v in phys.items():
        if k in names:
            out[k] = [k]
            used.add(k)
        elif isinstance(top.get(k), list):
            g = [n for n in _group_names(top[k], k) if n in names]
            if g:
                out[k] = g
                used.update(g)
        elif isinstance(top.get(k), dict) and top[k].get("object_name") in names:
            out[k] = [top[k]["object_name"]]
            used.add(out[k][0])
        elif isinstance(v, list) and len(v) == len(names):
            out[k] = list(names)          # bare parallel array, positional

    free = [n for n in names if n not in used]
    for k, v in phys.items():             # group of arrays under a different key
        if k in out or not isinstance(v, dict):
            continue
        n_arr = v.get("count") or max((len(x) for x in v.values()
                                       if isinstance(x, list)), default=0)
        cands = [kk for kk, meta in top.items()
                 if isinstance(meta, list) and len(meta) == n_arr
                 and all(n in free for n in _group_names(meta, kk))]
        if n_arr > 1 and len(cands) == 1:
            out[k] = _group_names(top[cands[0]], cands[0])
            free = [n for n in free if n not in out[k]]
    # Last resort, and only when it is unambiguous: one physics body with a
    # mass left over, one rendered object left over, so they are each other.
    rest = [k for k, v in phys.items()
            if k not in out and isinstance(v, dict) and "mass" in v]
    if len(rest) == 1 and len(free) == 1:
        out[rest[0]] = free
    return out


# ------------------------------------------------------------------ projection
class Camera:
    def __init__(self, cam: dict):
        self.W, self.H = cam["resolution"]
        # dining_chain omits sensor_width_mm; 36 mm is the Blender default.
        self.ortho = cam.get("projection") == "orthographic"
        if self.ortho:
            # Orthographic (pendulum_box_collision): ortho_scale metres span the
            # fitted side, so every depth maps at the same pixels per metre.
            fitted = self.H if (cam.get("sensor_fit", "AUTO") == "VERTICAL"
                                or (cam.get("sensor_fit", "AUTO") == "AUTO" and self.H > self.W)) else self.W
            self.fx = fitted / float(cam["ortho_scale"])
        else:
            self.fx = cam["lens_mm"] / cam.get("sensor_width_mm", 36.0) * self.W
        self.cx, self.cy = self.W / 2.0, self.H / 2.0
        # Blender lens shift is measured in units of the fitted sensor side (the
        # width for AUTO/HORIZONTAL fit of a landscape frame). +shift_x moves the
        # frame right and +shift_y moves it up, so a fixed point's image moves
        # the other way. Ground truth without shift fields is unaffected.
        fit = cam.get("sensor_fit", "AUTO")
        side = self.H if fit == "VERTICAL" or (fit == "AUTO" and self.H > self.W) else self.W
        self.cx -= float(cam.get("shift_x") or 0.0) * side
        self.cy += float(cam.get("shift_y") or 0.0) * side

    def project(self, P, cam_mw):
        Rt = np.linalg.inv(np.asarray(cam_mw, dtype=np.float64))
        x, y, z = (Rt @ np.array([*P, 1.0]))[:3]
        if z >= 0:
            return None
        if self.ortho:
            return self.fx * x + self.cx, self.cy - self.fx * y, 1.0
        return self.fx * (x / -z) + self.cx, self.cy - self.fx * (y / -z), -z


def projected_track(gt: dict, obj: str, objs: dict | None = None,
                    camera_from: dict | None = None):
    """-> uv (T,2) NaN where absent, present (T,), radius_px (T,).

    camera_from views another clip's world trajectory through THIS clip's
    camera. ball_block re-randomises camera position and focal length for
    every edited render, so projecting an edited trajectory with its own
    camera and comparing it against a prediction -- which inherits the source
    clip's camera -- would measure the viewpoint change, not the physics.
    """
    objs = objs if objs is not None else normalise(gt)
    rec = objs[obj]
    cam_src = camera_from if camera_from is not None else gt
    cam = Camera(cam_src["camera"])
    r_world = rec["radius"]
    uv = np.full((len(gt["frames"]), 2), np.nan)
    pres = np.zeros(len(gt["frames"]), bool)
    rad = np.full(len(gt["frames"]), np.nan)
    cam_frames = cam_src["frames"]
    for t, fr in enumerate(gt["frames"]):
        mw = rec["mw"][t]
        if not np.isfinite(mw).all():
            continue
        cf = cam_frames[t] if t < len(cam_frames) else cam_frames[-1]
        got = cam.project(mw[:3, 3], cf["camera_matrix_world"])
        if got is None:
            continue
        u, v, depth = got
        uv[t] = [u, v]; pres[t] = True
        if r_world:
            rad[t] = r_world * cam.fx / depth
    return uv, pres, rad


def in_frame(uv: np.ndarray, resolution, radius_px: float = 0.0,
             margin_radii: float = 0.0):
    """-> (fully_inside, centre_inside). Both (T,) bool.

    An object straddling the border is the awkward case: its centre is still in
    the image, but the mask is cut off by the edge, so the centroid gets pulled
    inward while the ground-truth ORIGIN is not pulled anywhere. Comparing the
    two then measures the crop. `margin_radii` keeps only frames where the whole
    object clears the border.
    """
    W, H = resolution
    mg = float(margin_radii) * float(radius_px)
    centre = ((uv[:, 0] >= 0) & (uv[:, 0] < W)
              & (uv[:, 1] >= 0) & (uv[:, 1] < H))
    full = ((uv[:, 0] >= mg) & (uv[:, 0] < W - mg)
            & (uv[:, 1] >= mg) & (uv[:, 1] < H - mg))
    return full & centre, centre


def load_gt(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))
