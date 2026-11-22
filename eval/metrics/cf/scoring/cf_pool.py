# -*- coding: utf-8 -*-
"""Pools the simulated and real-video cases into the per-video and per-model results: Counterfactual Fidelity (CF) of
every generated video, Mask IoU of the same videos, model performance overall and by edit type (Remove / Add / Modify),
the reliability check of the two re-encoded reference copies, a paired bootstrap on the cases every editing model has
a score for, and the list of unscored cases. Pure Python (no numpy).
Inputs: cf_sim<SUFFIX>.json (cf_sim.py, then cf_later_frames.py), cf_real<SUFFIX>.json (cf_real.py), Mask IoU per
video and references (mask_iou.py), and the edit-type assignment of the benchmark cases, a JSON list of
{"split", "scene", "case", "edit_type"} with edit_type in Remove / Add / Modify.
usage: python cf_pool.py CF_SIM.json CF_REAL.json EDIT_TYPES.json MASK_IOU_VIDEOS.json MASK_IOU_REFS.json OUT_DIR
  -> OUT_DIR/all_results.json, model_performance.json, unscored_cases.json"""
import json, random, sys
from pathlib import Path
SIMF, REALF, ETYPEF, MASKF, MREFF, OUT = (Path(a) for a in sys.argv[1:7]); OUT.mkdir(parents=True, exist_ok=True)
MODELS = ["seedance25", "minimax_h3", "wan3_0_video", "kling4_0_video", "joyai_video_edit", "kiwi_edit", "omniweaving", "void"]
EDITORS = MODELS[:7]
REFS = {"ref_gt_degraded": "reencoded_ground_truth", "ref_source_degraded": "reencoded_source"}
TYPES = ["Remove", "Add", "Modify"]
etype = {f"{c['split']}__{c['scene']}__{c['case']}": c["edit_type"] for c in json.load(open(ETYPEF))}
assert len(etype) == 533

cases = []                       # one record per benchmark case
for split, path in (("sim", SIMF), ("real", REALF)):
    for r in json.load(open(path)):
        cases.append({"split": split, "name": r["name"], "valid": bool(r.get("valid")), "s": r["s"]})
assert len(cases) == 533 and all(c["name"] in etype for c in cases)

videos, unscored, refs = [], [], {v: [] for v in REFS}
for c in cases:
    _, scene, case = c["name"].split("__")
    if not c["valid"]:
        unscored.append({"split": c["split"], "scene": scene, "case": case, "edit_type": etype[c["name"]],
                         "reason": "no physical quantity changed by the edit is measurable at the video resolution"})
        continue
    for v in REFS:
        refs[v].append(c["s"][v]["kq"])
    for m in MODELS:
        x = c["s"].get(m)
        if x is None or x.get("kq") is None:
            continue
        videos.append({"split": c["split"], "scene": scene, "case": case, "model": m, "edit_type": etype[c["name"]],
                       "CF": round(float(x["kq"]), 6), "scored_quantities": int(x.get("nkey", 0))})
mean = lambda a: sum(a) / len(a) if a else None
# Mask IoU (mask_iou.py on the same verified tracks), attached to the same video records
MIOU = {(r["split"], r["scene"], r["case"], r["model"]): r["mask_iou"] for r in json.load(open(MASKF))} if MASKF.exists() else {}
MREF = json.load(open(MREFF)) if MREFF.exists() else {}
mref = {vid: (sum(x[vid] for x in MREF.values() if vid in x) / max(1, sum(vid in x for x in MREF.values()))) for vid in ("source", "ref_gt_degraded")}
for v in videos:
    v["mask_IoU"] = round(MIOU[(v["split"], v["scene"], v["case"], v["model"])], 6) if (v["split"], v["scene"], v["case"], v["model"]) in MIOU else None


def perf(vs):
    return {"videos": len(vs), "splits": {s: sum(v["split"] == s for v in vs) for s in ("sim", "real")},
            "CF": {"mean": mean([v["CF"] for v in vs]), "share_at_least_0.5": mean([v["CF"] >= 0.5 for v in vs]),
                   "share_negative": mean([v["CF"] < 0 for v in vs])},
            "mask_IoU": {"videos": sum(v["mask_IoU"] is not None for v in vs), "mean": mean([v["mask_IoU"] for v in vs if v["mask_IoU"] is not None])}}


overall = {m: perf([v for v in videos if v["model"] == m]) for m in MODELS}
by_type = {t: {m: perf([v for v in videos if v["model"] == m and v["edit_type"] == t]) for m in MODELS
               if any(v["model"] == m and v["edit_type"] == t for v in videos)} for t in TYPES}
scored_cases = sum(c["valid"] for c in cases)
cases_by_type = {t: {"benchmark": sum(etype[c["name"]] == t for c in cases), "scored": sum(c["valid"] and etype[c["name"]] == t for c in cases)} for t in TYPES}

# paired bootstrap on the cases every editing model has a score for
rnd = random.Random(0)
common = [c for c in cases if c["valid"] and all(c["s"].get(m, {}).get("kq") is not None for m in EDITORS)]
X = [[c["s"][m]["kq"] for m in EDITORS] for c in common]; B = []
for _ in range(4000):
    idx = [rnd.randrange(len(X)) for _ in X]
    B.append([sum(X[i][j] for i in idx) / len(idx) for j in range(len(EDITORS))])
ci = {}
for j, m in enumerate(EDITORS):
    col = sorted(b[j] for b in B)
    ci[m] = {"mean": mean([x[j] for x in X]), "ci95": [col[int(0.025 * len(col))], col[int(0.975 * len(col)) - 1]]}

json.dump(videos, open(OUT / "all_results.json", "w"), indent=1)
json.dump(unscored, open(OUT / "unscored_cases.json", "w"), indent=1)
json.dump({"metric": "Counterfactual Fidelity (CF)", "range": [-1, 1],
           "aggregation": "CF of a video is the mean over its scored quantities; each generated video has equal weight.",
           "benchmark_cases": len(cases), "scored_cases": scored_cases, "cases_by_edit_type": cases_by_type,
           "reliability_check": {REFS[v]: mean(refs[v]) for v in REFS},
           "mask_IoU_references": {"source_video": mref["source"], "reencoded_ground_truth": mref["ref_gt_degraded"], "cases": len(MREF)},
           "all_available": overall, "by_edit_type": by_type,
           "common_cases": {"cases": len(common), "models": EDITORS, "paired_bootstrap": ci}},
          open(OUT / "model_performance.json", "w"), indent=1)
for m in MODELS:
    print(f"{m:18s} videos {overall[m]['videos']:4d}  CF {overall[m]['CF']['mean']}  Mask IoU {overall[m]['mask_IoU']['mean']}")
