# -*- coding: utf-8 -*-
"""Second camera alignment pass for the pairs (cam_stats.json mis0 > 5 px) that cam_retrack.py did not align: SIFT
matches on the background (objects masked) + RANSAC similarity as the starting guess, then ECC refinement; same
acceptance test (the background gradient correlation must rise) and the same re-tracking of the seeds as
cam_retrack.py. Writes WORK/cam_tracks2/<name>.npz ("<model>_xy", "<model>_W") and WORK/cam_retrack2_<SHARD>.json.
usage: cam_retrack2.py WORK SHARD NSHARDS   (environment: PHYCOVE_ROOT, PRED_ROOT, COTRACKER_REPO, COTRACKER_CKPT)"""
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


stats = json.load(open(T / "cam_stats.json")); prev = {(x["name"], x["model"]): x for f in sorted(T.glob("cam_retrack_[0-9].json")) for x in json.load(open(f))}
pairs = sorted({(r["name"], r["model"]) for r in stats if r["mis0"] is not None and r["mis0"] > 5 and not prev.get((r["name"], r["model"]), {}).get("ok")})
names = sorted({n for n, _ in pairs})[shard::nsh]
(T / "cam_tracks2").mkdir(exist_ok=True); log = []; sift = cv2.SIFT_create(4000); bf = cv2.BFMatcher()
for name in names:
    out = T / "cam_tracks2" / f"{name}.npz"
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
        # SIFT matches on the background (objects masked) + RANSAC similarity as the starting guess, then ECC refinement
        g8s = cv2.cvtColor(S0, cv2.COLOR_RGB2GRAY); g8p = cv2.cvtColor(P[0], cv2.COLOR_RGB2GRAY)
        ks, ds = sift.detectAndCompute(g8s, mask); kp, dp = sift.detectAndCompute(g8p, None)
        if ds is None or dp is None or len(ks) < 20 or len(kp) < 20:
            log.append({"name": name, "model": m, "ok": False, "why": "few_features"}); continue
        good = [a for a, b in bf.knnMatch(ds, dp, k=2) if a.distance < 0.75 * b.distance]
        if len(good) < 20:
            log.append({"name": name, "model": m, "ok": False, "why": "few_matches", "n": len(good)}); continue
        A, inl = cv2.estimateAffinePartial2D(np.float32([ks[g.queryIdx].pt for g in good]), np.float32([kp[g.trainIdx].pt for g in good]),
                                             method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if A is None or inl.sum() < 20:
            log.append({"name": name, "model": m, "ok": False, "why": "ransac", "n": int(0 if inl is None else inl.sum())}); continue
        W = A.astype(np.float32)
        try:
            _, W = cv2.findTransformECC(gs, gp, W, cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), mask, 5)
        except cv2.error:
            W = A.astype(np.float32)
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
json.dump(log, open(T / f"cam_retrack2_{shard}.json", "w"))
