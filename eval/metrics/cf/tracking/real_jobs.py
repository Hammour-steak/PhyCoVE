# -*- coding: utf-8 -*-
"""Real-video cases: SAM 2 jobs from the hand annotations (real_prompts.json: per video and object, prompts ["p", t, x, y] =
point, ["b", t, i] = box of motion blob i of frame t from real_blobs/<vid>.json, ["x", t, x0, y0, x1, y1] = hand box).
mode ref : one job per edit case, videos source / gt / ref_source_degraded / ref_gt_degraded (the degraded copies get
           the same prompts as the clean ones)          -> WORK/sam2_jobs_realref.json   (OUTDIR=sam2_real)
mode pred: one job per edit case, the 8 models' raw predictions, each object prompted where the source track (or the
           hand prompts in real_pred_prompts.json) says  -> WORK/sam2_jobs_realpred.json  (OUTDIR=sam2_realpred)
Both are run with cf/tracking/track_sam2.py, KEYS=cas.
usage: real_jobs.py WORK ref|pred   (environment: PHYCOVE_ROOT, PRED_ROOT_REAL)"""
import json, os, sys
from pathlib import Path
import numpy as np
T = Path(sys.argv[1]); MODE = sys.argv[2]
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE")) / "real"
PRED = Path(os.environ.get("PRED_ROOT_REAL", "predictions/PhyCoVE/real/quantitative_en"))
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]
P = json.load(open(T / "real_prompts.json"))


def conv(vid, pr):
    if pr[0] == "p":
        return {"t": pr[1], "pos": [[pr[2], pr[3]]], "neg": [], "box": None}
    if pr[0] == "x":
        x0, y0, x1, y1 = pr[2:6]
        return {"t": pr[1], "pos": [[(x0 + x1) / 2, (y0 + y1) / 2]], "neg": [], "box": [x0, y0, x1, y1]}
    b = json.load(open(T / "real_blobs" / f"{vid}.json"))[str(pr[1])][pr[2]]
    return {"t": pr[1], "pos": [[(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]], "neg": [], "box": b[:4]}


cases = [json.loads(l) for l in open(REL / "metadata.jsonl")]
jobs = []
if MODE == "ref":
    for d in cases:
        sc, cs = d["scene"], d["case_id"]; vs, vg = f"{sc}__source", f"{sc}__{cs}"
        if vs not in P and vg not in P:
            continue
        j = {"name": f"real__{sc}__{cs}", "suffix": "", "videos": {
            "source": str(REL / "scenes" / sc / "cases" / "source" / "video.mp4"), "gt": str(REL / "scenes" / sc / "cases" / cs / "video.mp4"),
            "ref_source_degraded": str(REL / "scenes" / sc / "cases" / "source" / "video.mp4"), "ref_gt_degraded": str(REL / "scenes" / sc / "cases" / cs / "video.mp4")},
            "objects": []}
        for vid, keys in ((vs, ("source", "ref_source_degraded")), (vg, ("gt", "ref_gt_degraded"))):
            for ob, prs in P.get(vid, {}).items():
                for k in keys:
                    j["objects"].append({"obj": ob, "video": k, "prompts": [conv(vid, p) for p in prs]})
        jobs.append(j)
    json.dump(jobs, open(T / "sam2_jobs_realref.json", "w"), indent=1)
else:
    HP = json.load(open(T / "real_pred_prompts.json")) if (T / "real_pred_prompts.json").exists() else {}
    VAL = json.load(open(T / "real_valid.json"))
    for d in cases:
        sc, cs = d["scene"], d["case_id"]; name = f"real__{sc}__{cs}"
        zp = T / "sam2_real" / f"{name}.npz"
        if not zp.exists():
            continue
        z = np.load(zp); j = {"name": name, "suffix": "", "videos": {}, "objects": []}
        for m in MODELS:
            vp = PRED / m / "videos" / sc / f"{cs}.mp4"
            if not vp.exists():
                continue
            j["videos"][m] = str(vp)
            for ob in P.get(f"{sc}__source", {}):
                key = f"{name}|{m}|{ob}"
                if key in HP:                      # hand prompts on the prediction (frame-by-frame)
                    prs = [conv(None, p) for p in HP[key]["prompts"]] if HP[key].get("prompts") else []
                else:
                    s = z[f"source|{ob}_s"] if f"source|{ob}_s" in z else None
                    if s is None:
                        continue
                    ok = np.where(np.isfinite(s).all(1))[0]
                    rng = VAL.get(f"{sc}__source|{ob}")
                    if rng:
                        ok = ok[(ok >= rng[0]) & (ok <= rng[1])]
                    if not len(ok):
                        continue
                    # the first frame where the source mask is there and object-sized: all predictions start from the
                    # source frame 0 and follow it until the edit acts, so the object is there
                    t = int(ok[0]); x5, x95, y5, y95 = s[t][3:7]
                    prs = [{"t": t, "pos": [[float(s[t][1]), float(s[t][2])]], "neg": [], "box": [float(x5) - 3, float(y5) - 3, float(x95) + 3, float(y95) + 3]}]
                if prs:
                    j["objects"].append({"obj": ob, "video": m, "prompts": prs})
        jobs.append(j)
    json.dump(jobs, open(T / "sam2_jobs_realpred.json", "w"), indent=1)
print(len(jobs), "jobs", sum(len(j["objects"]) for j in jobs), "objects")
