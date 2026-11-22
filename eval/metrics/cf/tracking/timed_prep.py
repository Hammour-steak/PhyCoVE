# -*- coding: utf-8 -*-
"""Objects deleted mid-clip (DELETE target, present at the start of the GT, gone later): deletion frame td from the
GT presence, and the object's true position in the SOURCE (where it still is) per frame, 640 px. Objects that only
share the name prefix of a target but stay in the GT (pen_holder for target pen) are not deletion targets.
-> WORK/timed_targets.json {name: {obj: {"td", "r", "pos": [[x, y] | null] * 96}}}
usage: timed_prep.py WORK   (environment: PHYCOVE_ROOT)"""
import json, os, sys
from pathlib import Path
import numpy as np
T = Path(sys.argv[1])
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
import traj_lib as tl
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
out, stay = {}, []
for l in open(REL / "metadata.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if not r.get("source_case_id"):
        continue
    name = "sim__" + r["id"].replace("/", "__"); dsl = r.get("edit_dsl") or ""
    tg = {s.split()[1] for s in dsl.split(";") if len(s.split()) > 1 and s.split()[0] == "DELETE"}
    if not tg or not (T / "seeds" / f"{name}.json").exists():
        continue
    _, scene, case = name.split("__")
    seeds = json.load(open(T / "seeds" / f"{name}.json"))["objects"]
    base = tl.load_gt(REL / f"scenes/{scene}/cases/source/ground_truth_transforms.json")
    edit = tl.load_gt(REL / f"scenes/{scene}/cases/{case}/ground_truth_transforms.json")
    obn, oen = tl.normalise(base), tl.normalise(edit)
    res = base["camera"]["resolution"]; sx, sy = 640.0 / res[0], 360.0 / res[1]
    for o in seeds:
        nm = o["name"]
        if o["role"] != "both" or not any(nm == t or nm.startswith(t + "_") for t in tg):
            continue
        if nm not in oen or nm not in obn:
            continue
        _, pres_g, _ = tl.projected_track(edit, nm, oen, camera_from=base)
        pres_g = np.asarray(pres_g, bool)
        if pres_g[-8:].any():
            stay.append((name, nm)); continue
        td = int(np.where(~pres_g)[0][0])
        uv, pres_s, _ = tl.projected_track(base, nm, obn)
        uv = np.asarray(uv, float) * [sx, sy]
        pos = [[round(float(uv[t][0]), 1), round(float(uv[t][1]), 1)] if t < len(uv) and pres_s[t] and np.isfinite(uv[t]).all() else None for t in range(96)]
        out.setdefault(name, {})[nm] = {"td": td, "r": float(o["r_px"]), "pos": pos}
json.dump(out, open(T / "timed_targets.json", "w"))
for n, d in out.items():
    print(n[5:60], {k: v["td"] for k, v in d.items()})
print("prefix-only (stay in GT):", stay)
