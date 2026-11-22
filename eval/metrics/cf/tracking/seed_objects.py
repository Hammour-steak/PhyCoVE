# -*- coding: utf-8 -*-
"""Object-seeded query points for the simulated cases, from the ground-truth 3D data (common/traj_lib.py).
For every object that moves (or differs between source and GT): the first frame its projected centre is inside the
frame (in the source clip; GT clip for objects that exist only in the GT, i.e. ADD), and 9 query points there:
the projected centre and 8 points on a ring at 0.4 x the projected radius (radius clamped to 4..50 px, 1280 scale).
Static fixtures and objects that never move in either clip are skipped.
Writes WORK/seeds/<name>.json: {"objects": [{"name", "kind", "role", "t0", "r_px", "queries": [[t,x640,y640],...]}]}
usage: seed_objects.py WORK [name-substring ...]   (environment: PHYCOVE_ROOT)"""
import json, os, sys
from pathlib import Path
import numpy as np

T = Path(sys.argv[1]); only = sys.argv[2:]
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
import traj_lib as tl
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
(T / "seeds").mkdir(exist_ok=True)


def first_visible(uv, pres, res):
    _, centre_in = tl.in_frame(uv, res)
    ok = np.where(pres & centre_in)[0]
    return int(ok[0]) if len(ok) else None


cases = []
for l in open(REL / "metadata.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r.get("source_case_id"):
        cases.append(r)
stats = []
for r in cases:
    scene, case = r["id"].split("/"); name = f"sim__{scene}__{case}"
    if only and not any(o in name for o in only):
        continue
    base = tl.load_gt(REL / f"scenes/{scene}/cases/source/ground_truth_transforms.json")
    edit = tl.load_gt(REL / f"scenes/{scene}/cases/{case}/ground_truth_transforms.json")
    ob, oe = tl.normalise(base), tl.normalise(edit)
    res = base["camera"]["resolution"]; sx, sy = 1280.0 / res[0], 720.0 / res[1]
    objs = []
    for o in sorted(set(ob) | set(oe)):
        rec = ob.get(o) or oe.get(o)
        if rec.get("static"):
            continue
        mw_b = np.array(ob[o]["mw"]) if o in ob else None; mw_e = np.array(oe[o]["mw"]) if o in oe else None
        def moves(mw):
            p = mw[:, :3, 3]; p = p[np.isfinite(p).all(1)]
            return len(p) > 1 and float(np.linalg.norm(p - p[0], axis=1).max()) > 0.01
        differs = mw_b is None or mw_e is None or (np.nanmax(np.abs(mw_b[:, :3, 3] - mw_e[:min(len(mw_b), len(mw_e)), :3, 3][:len(mw_b)])) > 0.01 if len(mw_b) and len(mw_e) else True)
        if not ((mw_b is not None and moves(mw_b)) or (mw_e is not None and moves(mw_e)) or differs):
            continue
        tb = te = None
        if o in ob:
            ub = tl.projected_track(base, o, ob); tb = first_visible(ub[0], ub[1], res)
        if o in oe:
            ue = tl.projected_track(edit, o, oe, camera_from=base); te = first_visible(ue[0], ue[1], res)
        if tb is not None:
            (uv, pres, rad), t0 = ub, tb; role = "both" if te is not None else "removed"
        elif te is not None:
            (uv, pres, rad), t0 = ue, te; role = "added"
        else:
            continue
        cx, cy = uv[t0, 0] * sx, uv[t0, 1] * sy
        rp = float(np.clip((rad[t0] if np.isfinite(rad[t0]) else 12.0) * sx, 4, 50))
        pts = [(cx, cy)] + [(cx + 0.4 * rp * np.cos(a), cy + 0.4 * rp * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
        q = [[t0, float(np.clip(x / 2, 0, 639)), float(np.clip(y / 2, 0, 359))] for x, y in pts]
        objs.append({"name": o, "kind": rec.get("kind"), "role": role, "t0": t0, "r_px": rp, "queries": q})
    (T / "seeds" / f"{name}.json").write_text(json.dumps({"objects": objs}, indent=1))
    stats.append((name, len(objs), sum(ob_["t0"] > 0 for ob_ in objs)))
print("cases", len(stats), "objects", sum(s[1] for s in stats), "cases without objects", sum(s[1] == 0 for s in stats), "objects seeded after frame 0", sum(s[2] for s in stats))
for s in stats[:10]:
    print("  ", s)
