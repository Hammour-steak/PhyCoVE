# -*- coding: utf-8 -*-
"""Reference trajectories that lose the object (ref_check.py: 90th-percentile displacement error vs the true 3D
projection > max(120, 2.5 tol) px at 1280) are redone: SAM2 on source / GT / both degraded copies, prompted from the
true 3D position with a box of the projected radius plus a point every 6 frames (a box every 6 frames too), so the
mask cannot drift. Validated over the whole window (90th percentile <= max(1.5 tol, 60) px, every video that has the
object): validated -> the reference tracker for the object becomes "m2" (cf_sim.py); not validated -> the object is
not measurable in that case.
  jobs:     -> WORK/sam2_jobs_refman2.json (run cf/tracking/track_sam2.py with KEYS=cas OUTDIR=sam2_refman2)
  validate: -> WORK/validation_ref2.json {name: {obj: {e_src, e_gt, e_rgt, e_rsrc, tol, ok}}}
usage: refman2.py WORK jobs|validate   (environment: PHYCOVE_ROOT)"""
import json, os, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
T = Path(sys.argv[1]); MODE = sys.argv[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
import traj_lib as tl
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
RC = json.load(open(T / "ref_check.json"))
SEL = defaultdict(list)
for r in RC:
    e = max(r["e_src90"] or 0, r["e_gt90"] or 0)
    if e > max(120.0, 2.5 * r["tol"]):
        SEL[r["name"]].append(r["obj"])


def truth(name, ob):
    _, scene, case = name.split("__")
    base = tl.load_gt(REL / f"scenes/{scene}/cases/source/ground_truth_transforms.json")
    edit = tl.load_gt(REL / f"scenes/{scene}/cases/{case}/ground_truth_transforms.json")
    res = base["camera"]["resolution"]; sx, sy = 640.0 / res[0], 360.0 / res[1]
    out = {}
    for key, gtd, cf in (("source", base, None), ("gt", edit, base)):
        od = tl.normalise(gtd)
        if ob not in od:
            continue
        uv, pres, rad = tl.projected_track(gtd, ob, od, camera_from=cf)
        uv = np.asarray(uv, float) * [sx, sy]
        ok = np.asarray(pres, bool) & np.isfinite(uv).all(1) & (uv[:, 0] >= 0) & (uv[:, 0] < 640) & (uv[:, 1] >= 0) & (uv[:, 1] < 360)
        uv[~ok] = np.nan
        out[key] = (uv, np.asarray(rad, float) * sx)
    return out


if MODE == "jobs":
    jobs = []
    for name, obs in SEL.items():
        _, scene, case = name.split("__")
        vids = {"source": str(REL / f"scenes/{scene}/cases/source/video.mp4"), "gt": str(REL / f"scenes/{scene}/cases/{case}/video.mp4")}
        vids["ref_source_degraded"] = vids["source"]; vids["ref_gt_degraded"] = vids["gt"]
        objs = []
        for ob in obs:
            tr = truth(name, ob)
            for v in vids:
                key = "gt" if v in ("gt", "ref_gt_degraded") else "source"
                if key not in tr:
                    continue
                uv, rad = tr[key]; fin = np.where(np.isfinite(uv).all(1))[0]
                if len(fin) == 0:
                    continue
                r = float(max(np.nanmedian(rad[fin]), 6.0))
                pr = [{"t": int(t), "pos": [[round(float(uv[t][0]), 1), round(float(uv[t][1]), 1)]], "neg": [],
                       "box": [round(float(uv[t][0] - r), 1), round(float(uv[t][1] - r), 1), round(float(uv[t][0] + r), 1), round(float(uv[t][1] + r), 1)]}
                      for t in range(int(fin[0]), 96, 6) if np.isfinite(uv[t]).all()]
                objs.append({"obj": ob, "video": v, "prompts": pr})
        jobs.append({"name": name, "suffix": "__refman", "videos": vids, "objects": objs})
    json.dump(jobs, open(T / "sam2_jobs_refman2.json", "w"), indent=0)
    print(len(jobs), "jobs", sum(len(v) for v in SEL.values()), "objects", sum(len(j["objects"]) for j in jobs), "object-videos")
else:
    out = {}
    for name, obs in SEL.items():
        p = T / "sam2_refman2" / f"{name}__refman.npz"
        z = dict(np.load(p)) if p.exists() else {}
        rp = {o["name"]: o["r_px"] for o in json.load(open(T / "seeds" / f"{name}.json"))["objects"]}
        for ob in obs:
            tr = truth(name, ob); tol = max(60.0, 1.5 * max(16.0, 0.6 * rp.get(ob, 40.0)))
            res = {"tol": round(tol, 1)}
            for v, short, key in (("source", "e_src", "source"), ("gt", "e_gt", "gt"), ("ref_gt_degraded", "e_rgt", "gt"), ("ref_source_degraded", "e_rsrc", "source")):
                c = z.get(f"{v}|{ob}_c")
                if key not in tr or np.isfinite(tr[key][0]).all(1).sum() < 8:     # not in that video (deleted object)
                    res[short] = "absent"; continue
                if c is None:
                    res[short] = None; continue
                g = tr[key][0] * 2.0
                ok = np.isfinite(c).all(1) & np.isfinite(g).all(1)
                if ok.sum() < 8:
                    res[short] = None; continue
                i0 = np.where(ok)[0][0]
                e = np.linalg.norm((c[ok] - c[i0]) - (g[ok] - g[i0]), axis=1)
                res[short] = round(float(np.percentile(e, 90)), 1)
            vals = [res[k] for k in ("e_src", "e_gt", "e_rgt", "e_rsrc") if res[k] != "absent"]
            res["ok"] = bool(vals) and all(v is not None and v <= tol for v in vals)
            out.setdefault(name, {})[ob] = res
            print(f"{name[5:60]:56s} {ob:16s} {res}")
    json.dump(out, open(T / "validation_ref2.json", "w"), indent=1)
    print(sum(r["ok"] for d in out.values() for r in d.values()), "of", sum(len(d) for d in out.values()), "validated")
