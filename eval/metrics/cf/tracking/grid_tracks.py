# -*- coding: utf-8 -*-
"""Grid point tracks for the camera statistics (cam_stats.py): CoTracker3 tracks of an 880-point grid (every 16 px at
640x360) seeded on frame 0, in the source video, the target video and every generated video of each simulated case.
Videos are read on the 24 fps clock by timestamp (<= 96 frames) and resized to 640x360.
-> WORK/full_tracks/<case>.npz {video: (T, 880, 2) float16, 1280-px units}
usage: grid_tracks.py WORK SHARD NSHARDS   (environment: PHYCOVE_ROOT, PRED_ROOT, COTRACKER_REPO, COTRACKER_CKPT)"""
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
H, W, SCALE, NT = 360, 640, 2.0, 96
tracker = CoTrackerPredictor(checkpoint=os.environ["COTRACKER_CKPT"], offline=True, window_len=60).cuda().eval()
ys, xs = np.meshgrid(np.arange(8, H, 16), np.arange(8, W, 16), indexing="ij")
Q = torch.tensor(np.stack([np.zeros(xs.size), xs.ravel(), ys.ravel()], 1)[None], dtype=torch.float32).cuda()


def load(path):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(f)
    out = []
    for k in range(NT):
        i = int(round(k * fps / 24.0))
        if i >= len(fr):
            break
        out.append(cv2.cvtColor(cv2.resize(fr[i], (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB))
    return np.stack(out), fps, len(fr)


@torch.no_grad()
def track(v):
    x = torch.from_numpy(v).permute(0, 3, 1, 2)[None].float().cuda()
    return tracker(x, queries=Q)[0][0].cpu().numpy() * SCALE


cases = []
for l in open(REL / "metadata.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r.get("source_case_id"):
        cases.append(r)
cases = cases[shard::nsh]
(T / "full_tracks").mkdir(exist_ok=True)
for r in cases:
    s, k = r["id"].split("/"); name = f"sim__{s}__{k}"
    out = T / "full_tracks" / f"{name}.npz"
    if out.exists():
        continue
    t0 = time.time()
    src, _, _ = load(REL / f"scenes/{s}/cases/source/video.mp4"); gt, _, _ = load(REL / f"scenes/{s}/cases/{k}/video.mp4")
    n0 = min(len(src), len(gt)); src, gt = src[:n0], gt[:n0]
    trs = {"source": track(src), "gt": track(gt)}
    for m in MODELS:
        p = PRED / m / "videos" / s / f"{k}.mp4"
        if p.exists():
            trs[m] = track(load(p)[0])
    np.savez_compressed(out, **{nm: t.astype(np.float16) for nm, t in trs.items()})
    print(json.dumps({"name": name, "sec": round(time.time() - t0, 1)}), flush=True)
