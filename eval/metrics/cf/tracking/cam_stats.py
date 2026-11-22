# -*- coding: utf-8 -*-
"""How much do predictions move the camera? For every simulated case with seeds and every model:
 (a) frame-0 misalignment: similarity (ECC, MOTION_AFFINE restricted later) between prediction frame 0 and source frame 0,
     reported as the mean displacement of a 9x16 point grid (px at 1280 width);
 (b) drift: background grid points (static in source and GT, > 60 px from every object seed) tracked in the prediction
     (full_tracks grid of grid_tracks.py, seeded at the prediction's own frame 0): max over t of the median displacement
     from frame 0.
-> WORK/cam_stats.json   usage: cam_stats.py WORK   (environment: PHYCOVE_ROOT, PRED_ROOT)"""
import json, os, sys
from pathlib import Path
import cv2
import numpy as np

T = Path(sys.argv[1])
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
PRED = Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en"))
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]
GX, GY = np.meshgrid(np.linspace(80, 1200, 16), np.linspace(60, 660, 9))
G = np.stack([GX.ravel(), GY.ravel()], 1)


def frame0(path):
    cap = cv2.VideoCapture(str(path)); ok, f = cap.read(); cap.release()
    return cv2.cvtColor(cv2.resize(f, (640, 360), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY) if ok else None


def ecc(a, b):
    w = np.eye(2, 3, dtype=np.float32)
    try:
        _, w = cv2.findTransformECC(cv2.GaussianBlur(b, (0, 0), 2).astype(np.float32), cv2.GaussianBlur(a, (0, 0), 2).astype(np.float32), w,
                                    cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5), None, 5)
    except cv2.error:
        return None
    A = np.vstack([w, [0, 0, 1]]); S = np.diag([0.5, 0.5, 1]); A = np.linalg.inv(S) @ A @ S     # in 1280 units
    p = np.c_[G, np.ones(len(G))] @ A.T
    return float(np.mean(np.linalg.norm(p[:, :2] - G, axis=1)))


rows = []
for f in sorted((T / "seed_tracks").glob("*.npz")):
    name = f.stem; _, scene, case = name.split("__")
    ft = T / "full_tracks" / f"{name}.npz"
    if not ft.exists():
        continue
    z = {k: v.astype(np.float32) for k, v in np.load(ft).items()}
    objs = json.load(open(T / "seeds" / f"{name}.json"))["objects"]
    sz = np.load(f); oc = np.concatenate([sz["source_xy"].reshape(-1, 2), sz["gt_xy"].reshape(-1, 2)])
    src, gt = z["source"], z["gt"]; n = min(len(src), len(gt))
    still = (np.linalg.norm(src[:n] - src[:1], axis=-1).max(0) < 4) & (np.linalg.norm(gt[:n] - gt[:1], axis=-1).max(0) < 4)
    far = np.array([np.min(np.linalg.norm(oc[::7] - q, axis=1)) > 60 for q in src[0]])
    bg = still & far
    s0 = frame0(REL / f"scenes/{scene}/cases/source/video.mp4")
    for m in MODELS:
        if m not in z or bg.sum() < 20:
            continue
        p = z[m]; drift = float(np.max(np.median(np.linalg.norm(p - p[:1], axis=-1)[:, bg], axis=1)))
        p0 = frame0(PRED / m / "videos" / scene / f"{case}.mp4")
        mis = ecc(p0, s0) if p0 is not None and s0 is not None else None
        rows.append({"name": name, "model": m, "drift": drift, "mis0": mis, "nbg": int(bg.sum())})
json.dump(rows, open(T / "cam_stats.json", "w"))
for m in MODELS:
    r = [x for x in rows if x["model"] == m]
    if not r:
        continue
    d = np.array([x["drift"] for x in r]); mi = np.array([x["mis0"] for x in r if x["mis0"] is not None])
    print(f"{m:18s} n={len(r):3d} drift med {np.median(d):5.1f} p90 {np.percentile(d, 90):6.1f} >10px {np.mean(d > 10):4.0%} >30px {np.mean(d > 30):4.0%} | "
          f"frame0 mis med {np.median(mi):5.1f} p90 {np.percentile(mi, 90):6.1f} >10px {np.mean(mi > 10):4.0%} >30px {np.mean(mi > 30):4.0%}")
