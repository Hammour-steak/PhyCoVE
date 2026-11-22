# -*- coding: utf-8 -*-
"""Extra SAM2 jobs. mode "cam": predictions with a camera-aligned first frame (cam_tracks *_W) - same prompts as the
main run but mapped into the prediction's own coordinates (suffix __cam). mode "man": hand-placed clicks from
WORK/manual_prompts.json {"<name>|<model>|<obj>": [{"t", "pos": [[x,y]..], "neg": [[x,y]..]}]} given in source-camera
coordinates for camera-aligned predictions (mapped here) (suffix __man).
usage: build_sam2_extra.py WORK cam|man   -> WORK/sam2_jobs_<mode>.json   (environment: PHYCOVE_ROOT, PRED_ROOT)"""
import json, os, sys
from pathlib import Path
import numpy as np

T = Path(sys.argv[1]); mode = sys.argv[2]
PRED = Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en"))


def cam_of(name):
    p = T / "cam_tracks" / f"{name}.npz"
    return dict(np.load(p)) if p.exists() else {}


def mapped(pts, W):
    return pts if W is None or not pts else (np.c_[np.array(pts, float), np.ones(len(pts))] @ W.T).clip([0, 0], [639, 359]).tolist()


jobs = {}
if mode == "cam":
    main = {j["name"]: j for j in json.load(open(T / "sam2_jobs.json"))}
    for name, j in main.items():
        cam = cam_of(name)
        for o in j["objects"]:
            W = cam.get(f"{o['video']}_W")
            if W is None:
                continue
            jj = jobs.setdefault(name, {"name": name, "suffix": "__cam", "videos": j["videos"], "objects": []})
            jj["objects"].append({"obj": o["obj"], "video": o["video"],
                                  "prompts": [{"t": pr["t"], "pos": mapped(pr["pos"], W), "neg": mapped(pr.get("neg", []), W), "box": None} for pr in o["prompts"]]})
else:
    man = json.load(open(T / "manual_prompts.json"))
    for key, prs in man.items():
        name, m, ob = key.split("|"); _, scene, case = name.split("__")
        W = cam_of(name).get(f"{m}_W")
        jj = jobs.setdefault(name, {"name": name, "suffix": "__man", "objects": [],
                                    "videos": {m: str(PRED / m / "videos" / scene / f"{case}.mp4")}})
        jj["videos"][m] = str(PRED / m / "videos" / scene / f"{case}.mp4")
        jj["objects"].append({"obj": ob, "video": m, "prompts": [{"t": pr["t"], "pos": mapped(pr["pos"], W), "neg": mapped(pr.get("neg", []), W), "box": None} for pr in prs]})
json.dump(list(jobs.values()), open(T / f"sam2_jobs_{mode}.json", "w"))
print(mode, "cases", len(jobs), "object-video tracks", sum(len(j["objects"]) for j in jobs.values()))
