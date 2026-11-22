# -*- coding: utf-8 -*-
"""Camera alignment for predictions whose first frame is shifted/zoomed against the source (cam_stats.json mis0 > 5 px).
Affine W (source -> prediction, 640x360 coords) from ECC between source frame 0 (template, object regions masked out)
and prediction frame 0; kept only if it raises the background gradient correlation. The GT seeds are mapped with W,
tracked in the prediction with CoTracker, and mapped back with W^-1, so trajectories are in source-camera coordinates.
Writes WORK/cam_tracks/<name>.npz: "<model>_xy" (n,Nq,2) 1280-px source coords, "<model>_W" (2,3), plus the log
WORK/cam_retrack_<SHARD>.json (background correlation before / after per pair).
usage: cam_retrack.py WORK SHARD NSHARDS   (environment: PHYCOVE_ROOT, PRED_ROOT, COTRACKER_REPO, COTRACKER_CKPT)"""
import json, os, sys
from pathlib import Path
import cv2
import numpy as np
import torch

T = Path(sys.argv[1]); shard, nsh = int(sys.argv[2]), int(sys.argv[3])
sys.path.insert(0, os.environ.get("COTRACKER_REPO", "co-tracker"))
from cotracker.predictor import CoTrackerPredictor
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
PRED = Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en"))
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


def gmag(img):
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 2)
    return g, np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))


def corr(a, b, mask):
    a, b = a[mask], b[mask]; a = (a - a.mean()) / (a.std() + 1e-6); b = (b - b.mean()) / (b.std() + 1e-6); return float(np.mean(a * b))


@torch.no_grad()
def track(v, q):
    x = torch.from_numpy(v).permute(0, 3, 1, 2)[None].float().cuda()
    tr, _ = tracker(x, queries=torch.tensor(q[None], dtype=torch.float32).cuda(), backward_tracking=True)
    return tr[0].cpu().numpy() * 2.0


stats = json.load(open(T / "cam_stats.json"))
pairs = sorted({(r["name"], r["model"]) for r in stats if r["mis0"] is not None and r["mis0"] > 5})
names = sorted({n for n, _ in pairs})[shard::nsh]
(T / "cam_tracks").mkdir(exist_ok=True); log = []
for name in names:
    out = T / "cam_tracks" / f"{name}.npz"
    if out.exists():
        continue
    _, scene, case = name.split("__")
    objs = json.load(open(T / "seeds" / f"{name}.json"))["objects"]
    q = np.array([qq for o in objs for qq in o["queries"]], np.float32)
    S0 = load(REL / f"scenes/{scene}/cases/source/video.mp4")[0]; gs, ms = gmag(S0)
    mask = np.ones((360, 640), np.uint8)
    for o in objs:
        c = o["queries"][0]; cv2.circle(mask, (int(c[1]), int(c[2])), int(1.5 * max(o["r_px"] / 2, 8)), 0, -1)
    arrs = {}
    for nm, m in [p for p in pairs if p[0] == name]:
        P = load(PRED / m / "videos" / scene / f"{case}.mp4"); gp, mp = gmag(P[0])
        W = np.eye(2, 3, dtype=np.float32)
        try:
            _, W = cv2.findTransformECC(gs, gp, W, cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6), mask, 5)
        except cv2.error:
            log.append({"name": name, "model": m, "ok": False, "why": "ecc"}); continue
        warped = cv2.warpAffine(mp, W, (640, 360), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
        valid = (cv2.warpAffine(np.ones((360, 640), np.uint8), W, (640, 360), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP) > 0) & (mask > 0)
        before, after = corr(ms, mp, mask > 0), corr(ms, warped, valid)
        shift = float(np.mean(np.linalg.norm((np.c_[q[:, 1:], np.ones(len(q))] @ W.T) - q[:, 1:], axis=1))) * 2
        ok = after > before + 0.05 and after > 0.3 and valid.mean() > 0.5
        log.append({"name": name, "model": m, "ok": bool(ok), "before": round(before, 3), "after": round(after, 3), "shift_px": round(shift, 1)})
        if not ok:
            continue
        qp = q.copy(); qp[:, 1:] = np.c_[q[:, 1:], np.ones(len(q))] @ W.T
        qp[:, 1] = qp[:, 1].clip(0, 639); qp[:, 2] = qp[:, 2].clip(0, 359)
        tr = track(P, qp) / 2.0                                                  # prediction coords (640)
        A = np.vstack([W, [0, 0, 1]]); Ai = np.linalg.inv(A)
        back = np.einsum("ij,tnj->tni", Ai[:2], np.concatenate([tr, np.ones(tr.shape[:2] + (1,))], -1)) * 2.0
        arrs[f"{m}_xy"] = back.astype(np.float32); arrs[f"{m}_W"] = W
    np.savez_compressed(out, **arrs)
    print(json.dumps([l for l in log if l["name"] == name]), flush=True)
json.dump(log, open(T / f"cam_retrack_{shard}.json", "w"))
