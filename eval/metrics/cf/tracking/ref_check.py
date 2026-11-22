# -*- coding: utf-8 -*-
"""Reference trajectories vs the true 3D projection, over the whole scored window (the tracker validation used the
75th percentile, so a reference that loses the object for the last quarter can pass). For every (case, object) in
tracks_used/ (source / GT reference = the same for all models), displacement error from the window start at 1280 px,
over frames where the object is in view; flagged if the 90th percentile error > max(40, r_px).
Needs tracks_used/ from a cf_sim.py run with DUMPTRACK=1.
-> WORK/ref_check.json  [{name, obj, e_src90, e_gt90, tol}]   usage: ref_check.py WORK   (environment: PHYCOVE_ROOT)"""
import glob, json, os, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
T = Path(sys.argv[1])
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
import traj_lib as tl
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))


def do(f):
    name = Path(f).stem; _, scene, case = name.split("__")
    z = dict(np.load(f))
    seeds = {o["name"]: o for o in json.load(open(T / "seeds" / f"{name}.json"))["objects"]}
    base = tl.load_gt(REL / f"scenes/{scene}/cases/source/ground_truth_transforms.json")
    edit = tl.load_gt(REL / f"scenes/{scene}/cases/{case}/ground_truth_transforms.json")
    obn, oen = tl.normalise(base), tl.normalise(edit)
    res = base["camera"]["resolution"]; sx, sy = 1280.0 / res[0], 720.0 / res[1]
    objs = sorted({k.split("|")[1] for k in z if k.endswith("|s")})
    out = []
    for ob in objs:
        key = next(k for k in z if k.endswith(f"|{ob}|s"))
        m = key.split("|")[0]; s, g, t0 = z[f"{m}|{ob}|s"], z[f"{m}|{ob}|g"], int(z[f"{m}|{ob}|t"])
        r = seeds.get(ob, {}).get("r_px", 40.0); errs = {}
        for lab, ref, gtd, od, cf in (("src", s, base, obn, None), ("gt", g, edit, oen, base)):
            if ob not in od:
                errs[lab] = None; continue
            uv, pres, _ = tl.projected_track(gtd, ob, od, camera_from=cf)
            uv = np.asarray(uv, float)[t0:t0 + len(ref)] * [sx, sy]; pres = np.asarray(pres, bool)[t0:t0 + len(ref)]
            ok = pres & np.isfinite(uv).all(1) & (uv[:, 0] > 0) & (uv[:, 0] < 1280) & (uv[:, 1] > 0) & (uv[:, 1] < 720)
            if ok.sum() < 8 or not ok[0]:
                errs[lab] = None; continue
            e = np.linalg.norm((ref[ok] - ref[0]) - (uv[ok] - uv[0]), axis=1)
            errs[lab] = round(float(np.percentile(e, 90)), 1)
        out.append({"name": name, "obj": ob, "e_src90": errs["src"], "e_gt90": errs["gt"], "tol": round(max(40.0, r), 1)})
    return out


if __name__ == "__main__":
    with Pool(int(os.environ.get("NPROC", "40"))) as pool:
        rows = [r for rs in pool.imap_unordered(do, sorted(glob.glob(str(T / "tracks_used" / "*.npz")))) for r in rs]
    bad = [r for r in rows if any(r[k] is not None and r[k] > r["tol"] for k in ("e_src90", "e_gt90"))]
    json.dump(bad, open(T / "ref_check.json", "w"), indent=0)
    print(len(rows), "objects;", len(bad), "flagged")
    for r in sorted(bad, key=lambda r: -max(r["e_src90"] or 0, r["e_gt90"] or 0)):
        print(f"  {r['name'][5:62]:58s} {r['obj']:16s} src {r['e_src90']} gt {r['e_gt90']} tol {r['tol']}")
