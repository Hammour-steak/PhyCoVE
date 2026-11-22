# -*- coding: utf-8 -*-
"""SAM2 jobs for every sim case with seeds: videos source, GT and every prediction; objects with role 'both'
(present in source and GT). Prompt per object and video at its seed frame t0: positive = the object's 9 seed points,
negative = centre points of the other seeded objects of the case. Hand prompts (WORK/manual_prompts.json:
{"<name>|<video>|<obj>": [{"t", "pos", "neg"}]}) replace the automatic prompt for that object in that video.
-> WORK/sam2_jobs.json   usage: build_sam2_jobs.py WORK   (environment: PHYCOVE_ROOT, PRED_ROOT)"""
import json, os, sys
from pathlib import Path

T = Path(sys.argv[1])
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
PRED = Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en"))
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]
man = json.load(open(T / "manual_prompts.json")) if (T / "manual_prompts.json").exists() else {}
jobs = []
for f in sorted((T / "seed_tracks").glob("*.npz")):
    name = f.stem; _, scene, case = name.split("__")
    objs = json.load(open(T / "seeds" / f"{name}.json"))["objects"]
    videos = {"source": str(REL / f"scenes/{scene}/cases/source/video.mp4"), "gt": str(REL / f"scenes/{scene}/cases/{case}/video.mp4")}
    for m in MODELS:
        p = PRED / m / "videos" / scene / f"{case}.mp4"
        if p.exists():
            videos[m] = str(p)
    jo = []
    for o in objs:
        if o["role"] != "both":
            continue
        neg = [[q[1], q[2]] for oo in objs if oo is not o and oo["role"] != "added" and abs(oo["t0"] - o["t0"]) < 2 for q in oo["queries"][:1]]
        cx, cy = o["queries"][0][1], o["queries"][0][2]
        neg = [n for n in neg if ((n[0] - cx) ** 2 + (n[1] - cy) ** 2) ** 0.5 > 0.6 * o["r_px"] / 2]
        for v in videos:
            pr = man.get(f"{name}|{v}|{o['name']}") or [{"t": o["t0"], "pos": [[q[1], q[2]] for q in o["queries"]], "neg": neg, "box": None}]
            jo.append({"obj": o["name"], "video": v, "prompts": pr})
    if jo:
        jobs.append({"name": name, "videos": videos, "objects": jo})
json.dump(jobs, open(T / "sam2_jobs.json", "w"))
print("cases", len(jobs), "object-video tracks", sum(len(j["objects"]) for j in jobs))
