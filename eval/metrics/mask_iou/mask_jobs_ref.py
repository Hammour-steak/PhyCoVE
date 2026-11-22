# -*- coding: utf-8 -*-
"""Mask IoU references (the counterpart of CF's re-encoded checks): every object of mask_meta.json is also segmented
in the SOURCE video along its verified source track and in a re-encoded copy of the ground-truth video along its
ground-truth track, so the source video ("no edit") and the re-encoded ground truth ("measurement repeatability")
get a Mask IoU against the ground truth.   -> WORK/sam2_jobs_mask_ref.json (run cf/tracking/track_sam2.py with KEYS=casm
OUTDIR=sam2_mask_ref) + WORK/mask_meta_ref.json
usage: mask_jobs_ref.py WORK   (environment: PHYCOVE_ROOT)"""
import json, os, sys
from pathlib import Path
import numpy as np
T = Path(sys.argv[1])
W0 = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
META = json.load(open(T / "mask_meta.json"))
jobs, meta = [], {}
cases = sorted({k.split("|")[0] for k in META})
for name in cases:
    split, scene, case = name.split("__")
    base = W0 / "real" if split == "real" else W0
    dumps = dict(np.load(T / ("real_tracks_used" if split == "real" else "tracks_used") / f"{name}.npz"))
    j = {"name": name, "suffix": "", "videos": {"source": str(base / "scenes" / scene / "cases" / "source" / "video.mp4"),
                                                "ref_gt_degraded": str(base / "scenes" / scene / "cases" / case / "video.mp4")}, "objects": []}
    for k, v in META.items():
        n, m, ob = k.split("|")
        if n != name or m != "gt":
            continue
        # source track of the object: the dump with the earliest start
        best = None
        for kk in dumps:
            if kk.endswith(f"|{ob}|s"):
                t0 = int(dumps[kk[:-2] + "|t"])
                if best is None or t0 < best[1]:
                    best = (np.asarray(dumps[kk], float) / 2.0, t0)
        if best is None:
            continue
        for vid, tr, t0 in (("source", best[0], best[1]), ("ref_gt_degraded", np.asarray(v["g"], float), v["t0"])):
            L = len(tr); prs = []
            for i in sorted({int(round(x)) for x in np.linspace(0, L - 1, 4)}):
                if not np.isfinite(tr[i]).all():
                    continue
                x, y = tr[i]; h = float(np.clip(0.65 * v["size"], 8, 160))
                if 0 <= x < 640 and 0 <= y < 360:
                    prs.append({"t": t0 + i, "pos": [[round(float(x), 1), round(float(y), 1)]], "neg": [],
                                "box": [round(max(0.0, x - h), 1), round(max(0.0, y - h), 1), round(min(640.0, x + h), 1), round(min(360.0, y + h), 1)]})
            if prs:
                j["objects"].append({"obj": ob, "video": vid, "prompts": prs})
                meta[f"{name}|{vid}|{ob}"] = {"status": "track", "t0": t0, "p": tr.round(2).tolist(), "size": v["size"], "nraw": 96, "W": None}
    if j["objects"]:
        jobs.append(j)
json.dump(jobs, open(T / "sam2_jobs_mask_ref.json", "w"))
json.dump(meta, open(T / "mask_meta_ref.json", "w"))
print(len(jobs), "jobs", sum(len(j["objects"]) for j in jobs), "objects")
