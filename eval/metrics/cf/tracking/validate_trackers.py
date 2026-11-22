# -*- coding: utf-8 -*-
"""Check both trackers against the 3D ground truth on the clean renders. For every seeded object: projected 3D origin
in the source and GT clips (traj_lib, GT clip seen through the source camera), and the displacement error (each path
minus its own position at the object's first frame, so the origin-vs-centroid offset cancels) of
 ct = median of the 9 CoTracker seed tracks, s2 = SAM2 mask centroid,
over frames where the projected centre is inside the image by one radius. err = 75th percentile, 1280-px units.
moves = max projected displacement (src or GT); an object whose origin does not move while its tracks do is deformable
(cloth, spring, net) and cannot be checked this way.
Also cs_src / cs_gt = point track vs SAM 2 (both trackers agreeing on the visible object).
-> WORK/validation.json {name: {obj: {"moves", "ct_src", "ct_gt", "s2_src", "s2_gt", "cs_src", "cs_gt", "r_px"}}}
usage: validate_trackers.py WORK   (environment: PHYCOVE_ROOT)"""
import json, os, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np

T = Path(sys.argv[1])
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
import traj_lib as tl
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))


def err(trk, proj, ok, t0):
    if trk is None:
        return None
    ok = ok & np.isfinite(trk).all(1) & np.isfinite(proj).all(1)
    ok[:t0] = False
    if ok.sum() < 4:
        return None
    a = np.where(ok)[0][0]
    d = np.linalg.norm((trk[ok] - trk[a]) - (proj[ok] - proj[a]), axis=-1)
    return float(np.percentile(d, 75))


def do(name):
    _, scene, case = name.split("__")
    objs = json.load(open(T / "seeds" / f"{name}.json"))["objects"]
    z = np.load(T / "seed_tracks" / f"{name}.npz"); s2p = T / "sam2_tracks" / f"{name}.npz"
    s2 = dict(np.load(s2p)) if s2p.exists() else {}
    base = tl.load_gt(REL / f"scenes/{scene}/cases/source/ground_truth_transforms.json")
    edit = tl.load_gt(REL / f"scenes/{scene}/cases/{case}/ground_truth_transforms.json")
    ob, oe = tl.normalise(base), tl.normalise(edit)
    res = base["camera"]["resolution"]; sx, sy = 1280.0 / res[0], 720.0 / res[1]
    out, s = {}, 0
    for o in objs:
        idx = list(range(s, s + len(o["queries"]))); s += len(o["queries"])
        rec = {"r_px": o["r_px"], "role": o["role"]}
        for clip, gtd, od, key, cam in (("src", base, ob, "source", None), ("gt", edit, oe, "gt", base)):
            if o["name"] not in od:
                continue
            uv, pres, rad = tl.projected_track(gtd, o["name"], od, camera_from=cam)
            uv = uv * [sx, sy]; n = min(len(uv), len(z[f"{key}_xy"]))
            full, _ = tl.in_frame(uv / [sx, sy], res, float(np.nanmedian(rad)) if np.isfinite(rad).any() else 0.0, 1.0)
            ok = pres[:n] & full[:n]
            ct = np.median(z[f"{key}_xy"][:n, idx], axis=1)
            sc = s2.get(f"{key}|{o['name']}_c"); sc = sc[:n] if sc is not None else None
            rec[f"ct_{clip}"] = err(ct, uv[:n], ok.copy(), o["t0"]); rec[f"s2_{clip}"] = err(sc, uv[:n], ok.copy(), o["t0"])
            rec[f"cs_{clip}"] = err(ct, sc, ok.copy(), o["t0"]) if sc is not None else None   # point track vs SAM2, displacement
            okm = ok.copy(); okm[:o["t0"]] = False
            rec[f"moves_{clip}"] = float(np.nanmax(np.linalg.norm(uv[:n][okm] - uv[:n][okm][0], axis=-1))) if okm.sum() >= 2 else 0.0
            rec[f"nvis_{clip}"] = int(ok.sum())
        rec["moves"] = max(rec.get("moves_src", 0.0), rec.get("moves_gt", 0.0))
        out[o["name"]] = rec
    return name, out


if __name__ == "__main__":
    names = [f.stem for f in sorted((T / "seed_tracks").glob("*.npz"))]
    with Pool(32) as pool:
        res = dict(pool.map(do, names, chunksize=2))
    json.dump(res, open(T / "validation.json", "w"))
    import collections
    c = collections.Counter()
    for nm, objs in res.items():
        for ob, r in objs.items():
            if r["role"] != "both":
                continue
            tol = max(16.0, 0.6 * r["r_px"])
            ok = lambda k: r.get(k) is not None and r[k] <= tol
            if r["moves"] < 10:
                c["origin_static"] += 1; continue
            c[("ct" if ok("ct_src") and ok("ct_gt") else "-") + "/" + ("s2" if ok("s2_src") and ok("s2_gt") else "-")] += 1
    print(dict(c))
