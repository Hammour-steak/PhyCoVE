# -*- coding: utf-8 -*-
"""Region quantities shared by cf/scoring/cf_sim.py and cf/tracking/liquid_regions.py.
Every thing in a scene is a region per frame: rigid and deformable objects = their SAM 2 mask (the same masks whose
centroids give position tracks), liquids = change region (liquid_regions.py). Quantity families: position (from the
validated position track, in cf_sim.py), shape (from the mask; position-free unless the object has no position
track), amount (liquids). Same rule everywhere: score = clip(dP/dG, -1, 1), a quantity is kept only when the
re-encoded target copy reproduces it (>= 0.5) and the re-encoded source copy does not (|.| < 0.5)."""
import numpy as np


def score(qp, qs, qg, overshoot="none"):
    p = (qp - qs) / (qg - qs)
    if overshoot == "soft" and p > 1:
        p = max(0.0, 2.0 - p)
    return float(np.clip(p, -1, 1))


def transform_stats(s, Ai):
    """shape stats (N,7: area, cx, cy, x5, x95, y5, y95 at 640x360) measured on a raw prediction frame ->
    source frame with the affine Ai (2x3, pred -> source): box corners mapped, area scaled by |det|"""
    s = np.array(s, np.float32, copy=True)
    ok = np.isfinite(s).all(1)
    if not ok.any():
        return s
    A = Ai[:2, :2]; b = Ai[:2, 2]
    c = s[ok][:, 1:3] @ A.T + b
    xs = np.stack([s[ok][:, 3], s[ok][:, 4], s[ok][:, 3], s[ok][:, 4]], 1); ys = np.stack([s[ok][:, 5], s[ok][:, 5], s[ok][:, 6], s[ok][:, 6]], 1)
    X = xs * A[0, 0] + ys * A[0, 1] + b[0]; Y = xs * A[1, 0] + ys * A[1, 1] + b[1]
    s[ok, 0] = s[ok, 0] * abs(np.linalg.det(A)); s[ok, 1:3] = c
    s[ok, 3], s[ok, 4], s[ok, 5], s[ok, 6] = X.min(1), X.max(1), Y.min(1), Y.max(1)
    return s


def shape_q(s, t0, tc, with_pos):
    """height / width / area over the last 5 frames and smallest height; with_pos adds top, bottom, lowest reach and
    x centre (only for regions with no position track)"""
    if s is None:
        return None
    s = np.asarray(s, float)[t0:tc]
    if len(s) < 4:
        return None
    h, w = s[:, 6] - s[:, 5], s[:, 4] - s[:, 3]
    nm = lambda a: float(np.nanmean(a)) if np.isfinite(a).any() else np.nan
    q = {"height_end": nm(h[-5:]), "width_end": nm(w[-5:]), "area_end": nm(s[-5:, 0]),
         "height_min": float(np.nanmin(h)) if np.isfinite(h).any() else np.nan}
    if with_pos:
        q.update({"top_end": nm(s[-5:, 5]), "bottom_end": nm(s[-5:, 6]), "cx_end": nm(s[-5:, 1]),
                  "bottom_max": float(np.nanmax(s[:, 6])) if np.isfinite(s[:, 6]).any() else np.nan})
    return q


def shape_thr(k, a, b):
    return max(100.0, 0.10 * max(abs(a), abs(b))) if k == "area_end" else 8.0


def shape_ok(sp, ss, sg, t0, tc):
    """is the prediction's mask on the object? (a seed prompt on an object the model deleted segments the wall)"""
    if sp is None:
        return False, "shape_missing"
    sp, ss, sg = (np.asarray(x, float)[t0:tc] for x in (sp, ss, sg))
    fp, fs, fg = (np.isfinite(x).all(1) for x in (sp, ss, sg))
    if fp.sum() < 0.7 * min(fs.sum(), fg.sum()):
        return False, "shape_mask_gaps"
    a0p = sp[fp][0, 0] if fp.any() else np.nan; a0s = ss[fs][0, 0] if fs.any() else np.nan
    if np.isfinite(a0p) and np.isfinite(a0s) and not (0.25 <= a0p / max(a0s, 1.0) <= 4.0):
        return False, "shape_area_t0"
    amax = max(np.nanmax(ss[:, 0]) if fs.any() else 0, np.nanmax(sg[:, 0]) if fg.any() else 0)
    if fp.any() and np.nanmax(sp[:, 0]) > 4.0 * max(amax, 1.0):
        return False, "shape_mask_leak"
    return True, None


# ---- liquids (liquid_tracks/<name>.npz, px at 320x180) ----
def liquid_q(z, v, tc):
    P = z.get(f"{v}|liquid_P"); S = z.get(f"{v}|liquid_S")
    if P is None:
        return None
    P, S = np.nan_to_num(P[:tc]), np.nan_to_num(S[:tc])
    win = lambda a, c: float(np.mean(a[max(0, c - 2):min(len(a), c + 3)]))
    q = {f"amount_q{i}": win(P, int(round(f * (tc - 1)))) for i, f in ((1, 0.25), (2, 0.5), (3, 0.75))}
    q["amount_end"] = float(np.mean(P[-5:])); q["stream_frames"] = float((S >= 6).sum())
    for k in ("y5", "y95"):
        a = z[f"{v}|liquid_{k}"][:tc][-5:]
        q["top_end" if k == "y5" else "bottom_end"] = float(np.nanmean(a)) if np.isfinite(a).any() else np.nan
    w = (z[f"{v}|liquid_x95"] - z[f"{v}|liquid_x5"])[:tc][-5:]
    q["width_end"] = float(np.nanmean(w)) if np.isfinite(w).any() else np.nan
    return q


def liquid_thr(k, a, b):
    if k.startswith("amount"):
        return max(30.0, 0.10 * max(abs(a), abs(b)))
    return 6.0 if k == "stream_frames" else 4.0


def liquid_frozen(qs, qg, qp):
    """liquid that does not flow: source and GT both end with liquid, the prediction with < 1/4 of the smaller"""
    lo = min(qs["amount_end"], qg["amount_end"])
    return lo >= 150 and qp["amount_end"] < 0.25 * lo
