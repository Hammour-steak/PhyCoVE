# -*- coding: utf-8 -*-
"""Objects added by an ADD edit (in the GT, not in the source): first frame ta where the object is in the GT view,
its true GT position per frame (640 px) and size r (r_px convention of the seeds: 2 x projected radius at 640 px).
Parts of an added assembly (name prefix of another added object) are skipped.
-> WORK/added_targets.json {name: {obj: {"ta", "r", "pos": [[x, y] | null] * 96}}}
usage: added_prep.py WORK   (environment: PHYCOVE_ROOT)"""
import json, os, sys
from pathlib import Path
import numpy as np
T = Path(sys.argv[1])
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
import traj_lib as tl
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
out = {}
for l in open(REL / "metadata.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if not r.get("source_case_id"):
        continue
    name = "sim__" + r["id"].replace("/", "__"); dsl = r.get("edit_dsl") or ""
    if "ADD" not in [s.split()[0] for s in dsl.split(";") if s.split()]:
        continue
    _, scene, case = name.split("__")
    base = tl.load_gt(REL / f"scenes/{scene}/cases/source/ground_truth_transforms.json")
    edit = tl.load_gt(REL / f"scenes/{scene}/cases/{case}/ground_truth_transforms.json")
    obn, oen = tl.normalise(base), tl.normalise(edit)
    res = base["camera"]["resolution"]; sx, sy = 640.0 / res[0], 360.0 / res[1]
    names_dsl = {s.split()[1] for s in dsl.split(";") if len(s.split()) > 1 and s.split()[0] == "ADD"}
    seeds = json.load(open(T / "seeds" / f"{name}.json"))["objects"] if (T / "seeds" / f"{name}.json").exists() else []
    new = {o for o in oen if o not in obn} | {o for o in oen if o in names_dsl} | {o["name"] for o in seeds if o["role"] == "added" and o["name"] in oen}
    new = sorted(o for o in new if not any(o != p and o.startswith(p + "_") for p in new))
    if not new:
        print("NO ADDED OBJECT FOUND", name, names_dsl, sorted(oen)[:12])
    for ob in new:
        uv, pres, rad = tl.projected_track(edit, ob, oen, camera_from=base)
        uv = np.asarray(uv, float) * [sx, sy]; pres = np.asarray(pres, bool)
        inview = pres & np.isfinite(uv).all(1) & (uv[:, 0] >= 0) & (uv[:, 0] < 640) & (uv[:, 1] >= 0) & (uv[:, 1] < 360)
        if inview.sum() < 6:
            continue
        ta = int(np.where(inview)[0][0])
        rr = float(np.nanmedian(np.asarray(rad, float)[inview]) * sx * 2.0)
        pos = [[round(float(uv[t][0]), 1), round(float(uv[t][1]), 1)] if t < len(uv) and inview[t] else None for t in range(96)]
        out.setdefault(name, {})[ob] = {"ta": ta, "r": rr, "pos": pos}
json.dump(out, open(T / "added_targets.json", "w"))
for n, d in out.items():
    print(n[5:62], {k: (v["ta"], round(v["r"], 1)) for k, v in d.items()})
print(len(out), "ADD cases with added objects in view")
