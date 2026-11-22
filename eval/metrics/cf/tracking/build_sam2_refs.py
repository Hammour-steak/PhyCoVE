# -*- coding: utf-8 -*-
"""SAM 2 jobs on the two re-encoded reference copies (track_sam2.py re-encodes videos whose key starts with "ref_"),
same prompts as the main run -> WORK/sam2_jobs_ref.json (suffix __ref).   usage: build_sam2_refs.py WORK"""
import json, sys
from pathlib import Path
T = Path(sys.argv[1])
jobs = []
for j in json.load(open(T / "sam2_jobs.json")):
    objs = []
    for o in j["objects"]:
        if o["video"] in ("source", "gt"):
            objs.append({**o, "video": "ref_gt_degraded" if o["video"] == "gt" else "ref_source_degraded"})
    vids = {"ref_gt_degraded": j["videos"]["gt"], "ref_source_degraded": j["videos"]["source"]}
    jobs.append({"name": j["name"], "suffix": "__ref", "videos": vids, "objects": objs})
json.dump(jobs, open(T / "sam2_jobs_ref.json", "w")); print(len(jobs), sum(len(j["objects"]) for j in jobs))
