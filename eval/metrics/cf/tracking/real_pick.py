# -*- coding: utf-8 -*-
"""Real-video cases: write the prediction tracks picked by eye in the verification step into sam2_realpred/<name>.npz
under the object's name. Sources: SAM 2 runs at template-match candidates "tm" (sam2_realcand/), at motion-chain
candidates "mc" (sam2_realmc/), from hand prompts "hand" (sam2_realhand/), or "auto" = the automatic run of
real_jobs.py pred. Segments are stitched in their own frame index (Seedance: its 89-frame clock). The automatic arrays
are read from a copy made on the first pick (sam2_realpred_auto/), so re-running is idempotent.
real_pred_picks.json: {"i": [[src, k, t_from, t_to], ...]} with i = index into realcand_list.json ([name, model, obj])
usage: real_pick.py WORK"""
import json, shutil, sys
from pathlib import Path
import numpy as np
T = Path(sys.argv[1])
PK = json.load(open(T / "real_pred_picks.json"))
items = json.load(open(T / "realcand_list.json"))
bk = T / "sam2_realpred_auto"; bk.mkdir(parents=True, exist_ok=True)
by = {}
for i, segs in PK.items():
    name, m, ob = items[int(i)]; by.setdefault(name, []).append((m, ob, segs))
n = 0
for name, lst in by.items():
    p = T / "sam2_realpred" / f"{name}.npz"
    if not (bk / p.name).exists():
        shutil.copy(p, bk / p.name)
    auto = dict(np.load(bk / p.name)); z = dict(np.load(p))
    for m, ob, segs in lst:
        c = np.full((96, 2), np.nan, np.float32); a = np.zeros(96, np.float32); s = np.full((96, 7), np.nan, np.float32)
        for src, k, t1, t2 in segs:
            if src == "auto":
                S, pre = auto, f"{m}|{ob}"
            else:
                S, pre = (dict(np.load(T / "sam2_realhand" / f"{name}@{m}.npz")), f"{m}|{ob}") if src == "hand" else (dict(np.load(T / ("sam2_realcand" if src == "tm" else "sam2_realmc") / f"{name}@{m}.npz")), f"{m}|{ob}#c{k}")
            kc, ka, ks = S[f"{pre}_c"], S[f"{pre}_a"], S[f"{pre}_s"]
            for t in range(t1, min(t2, 95) + 1):
                if np.isfinite(ks[t]).all():
                    c[t], a[t], s[t] = kc[t], ka[t], ks[t]
        z[f"{m}|{ob}_c"], z[f"{m}|{ob}_a"], z[f"{m}|{ob}_s"] = c, a, s; n += 1
    np.savez_compressed(p, **z)
print(n, "tracks written")
