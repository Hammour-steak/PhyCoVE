# -*- coding: utf-8 -*-
"""Track the object seeds (seeds/<name>.json) with CoTracker3 in the two re-encoded reference copies of each case
(target and source video downscaled to 672x384 and back, JPEG quality 75, like a 384p model output). Same alignment
as track_seeds.py. Writes WORK/seed_tracks_mild/<name>.npz with ref_gt_mild_xy / ref_source_mild_xy (1280-px units)
and _vis.   usage: track_refs_mild.py WORK SHARD NSHARDS   (environment: PHYCOVE_ROOT, COTRACKER_REPO, COTRACKER_CKPT)"""
import json, os, sys, time
from pathlib import Path
import cv2
import numpy as np
import torch

T = Path(sys.argv[1]); shard, nsh = int(sys.argv[2]), int(sys.argv[3])
sys.path.insert(0, os.environ.get("COTRACKER_REPO", "co-tracker"))
from cotracker.predictor import CoTrackerPredictor
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
tracker = CoTrackerPredictor(checkpoint=os.environ["COTRACKER_CKPT"], offline=True, window_len=60).cuda().eval()


def load(path):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(f)
    out = []
    for k in range(96):
        i = int(round(k * fps / 24.0))
        if i >= len(fr):
            break
        out.append(cv2.cvtColor(cv2.resize(fr[i], (640, 360), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB))
    return np.stack(out)


def degrade(v):
    out = []
    for f in v:
        g = cv2.resize(cv2.resize(f, (672, 384), interpolation=cv2.INTER_AREA), (640, 360), interpolation=cv2.INTER_LINEAR)
        ok, b = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, 75])
        out.append(cv2.imdecode(b, cv2.IMREAD_COLOR))
    return np.stack(out)


@torch.no_grad()
def track(v, q):
    q = q.copy(); q[:, 0] = np.minimum(q[:, 0], len(v) - 1)
    x = torch.from_numpy(v).permute(0, 3, 1, 2)[None].float().cuda()
    tr, vis = tracker(x, queries=torch.tensor(q[None], dtype=torch.float32).cuda(), backward_tracking=True)
    return tr[0].cpu().numpy() * 2.0, vis[0].cpu().numpy() > 0.5


seeds = sorted((T / "seeds").glob("*.json"))[shard::nsh]
(T / "seed_tracks_mild").mkdir(exist_ok=True)
for f in seeds:
    name = f.stem; out = T / "seed_tracks_mild" / f"{name}.npz"
    objs = json.load(open(f))["objects"]
    if out.exists() or not objs:
        continue
    t0 = time.time(); _, scene, case = name.split("__")
    q = np.array([qq for o in objs for qq in o["queries"]], dtype=np.float32)
    src = load(REL / f"scenes/{scene}/cases/source/video.mp4"); gt = load(REL / f"scenes/{scene}/cases/{case}/video.mp4")
    n0 = min(len(src), len(gt)); src, gt = src[:n0], gt[:n0]
    vids = {"ref_gt_mild": degrade(gt), "ref_source_mild": degrade(src)}
    arrs = {}
    for nm, v in vids.items():
        xy, vis = track(v, q); arrs[f"{nm}_xy"] = xy.astype(np.float32); arrs[f"{nm}_vis"] = vis
    np.savez_compressed(out, **arrs)
    print(json.dumps({"name": name, "points": len(q), "sec": round(time.time() - t0, 1)}), flush=True)
