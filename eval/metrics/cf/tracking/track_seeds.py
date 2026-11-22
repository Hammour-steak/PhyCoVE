# -*- coding: utf-8 -*-
"""Track the object seeds (seeds/<name>.json) with CoTracker3 in the source video, the target video and every
generated video (24 fps by timestamp, <= 96 frames, 640x360). Writes WORK/seed_tracks/<name>.npz with <video>_xy
(1280-px units, float32) and <video>_vis (bool). The re-encoded reference copies are tracked by track_refs_mild.py.
usage: track_seeds.py WORK SHARD NSHARDS   (environment: PHYCOVE_ROOT, PRED_ROOT, COTRACKER_REPO, COTRACKER_CKPT)"""
import json, os, sys, time
from pathlib import Path
import cv2
import numpy as np
import torch

T = Path(sys.argv[1]); shard, nsh = int(sys.argv[2]), int(sys.argv[3])
sys.path.insert(0, os.environ.get("COTRACKER_REPO", "co-tracker"))
from cotracker.predictor import CoTrackerPredictor
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
PRED = Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en"))
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]
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


@torch.no_grad()
def track(v, q):
    q = q.copy(); q[:, 0] = np.minimum(q[:, 0], len(v) - 1)
    x = torch.from_numpy(v).permute(0, 3, 1, 2)[None].float().cuda()
    tr, vis = tracker(x, queries=torch.tensor(q[None], dtype=torch.float32).cuda(), backward_tracking=True)
    return tr[0].cpu().numpy() * 2.0, vis[0].cpu().numpy() > 0.5


seeds = sorted((T / "seeds").glob("*.json"))[shard::nsh]
(T / "seed_tracks").mkdir(exist_ok=True)
for f in seeds:
    name = f.stem; out = T / "seed_tracks" / f"{name}.npz"
    objs = json.load(open(f))["objects"]
    if out.exists() or not objs:
        continue
    t0 = time.time(); _, scene, case = name.split("__")
    q = np.array([qq for o in objs for qq in o["queries"]], dtype=np.float32)
    src = load(REL / f"scenes/{scene}/cases/source/video.mp4"); gt = load(REL / f"scenes/{scene}/cases/{case}/video.mp4")
    n0 = min(len(src), len(gt)); src, gt = src[:n0], gt[:n0]
    vids = {"source": src, "gt": gt}
    for m in MODELS:
        p = PRED / m / "videos" / scene / f"{case}.mp4"
        if p.exists():
            vids[m] = load(p)
    arrs = {}
    for nm, v in vids.items():
        xy, vis = track(v, q); arrs[f"{nm}_xy"] = xy.astype(np.float32); arrs[f"{nm}_vis"] = vis
    np.savez_compressed(out, **arrs)
    print(json.dumps({"name": name, "points": len(q), "sec": round(time.time() - t0, 1)}), flush=True)
