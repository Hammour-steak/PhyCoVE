# -*- coding: utf-8 -*-
"""SAM 2 (hiera large, video predictor) object masks for a job file: [{"name", "suffix", "videos": {key: path},
"objects": [{"obj", "video", "prompts": [{"t", "pos": [[x,y]...], "neg": [[x,y]...], "box": [x0,y0,x1,y1] | null}]}]}]
(640x360 coords, 24 fps timeline). All objects of one video are tracked together (one obj id each), forward and
backward from their prompt frames; videos whose key starts with "ref_" are re-encoded first (672x384, JPEG 75).
Output WORK/<OUTDIR>/<name><suffix>.npz with, per "<video>|<obj>", the arrays selected by KEYS (default "cas"):
  c  "_c" (96,2) mask centroid in 1280-px units (NaN if empty)
  a  "_a" (96,) mask area in px at 640x360
  s  "_s" (96,7) area, cx, cy, x5, x95, y5, y95 at 640x360 (NaN if empty)
  m  "_m" (T,360,80) packed per-frame masks (np.unpackbits(..., axis=-1))
usage: track_sam2.py WORK SHARD NSHARDS [JOBS.json]   (environment: SAM2_CKPT, SAM2_CFG, OUTDIR, KEYS; REVERSE=1 runs
the shard from its end, so two workers per GPU meet in the middle)"""
import json, os, shutil, sys, tempfile
from pathlib import Path
import cv2
import numpy as np
import torch

T = Path(sys.argv[1]); shard, nsh = int(sys.argv[2]), int(sys.argv[3])
from sam2.build_sam import build_sam2_video_predictor
pred = build_sam2_video_predictor(os.environ.get("SAM2_CFG", "sam2_hiera_l.yaml"), os.environ["SAM2_CKPT"], device="cuda")
KEYS = os.environ.get("KEYS", "cas")


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
        out.append(cv2.resize(fr[i], (640, 360), interpolation=cv2.INTER_AREA))
    return out


def degrade(f):
    g = cv2.resize(cv2.resize(f, (672, 384), interpolation=cv2.INTER_AREA), (640, 360), interpolation=cv2.INTER_LINEAR)
    ok, b = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, 75]); return cv2.imdecode(b, cv2.IMREAD_COLOR)


@torch.inference_mode()
def run(frames, objs):
    tmp = Path(tempfile.mkdtemp(prefix="s2_"))
    for i, f in enumerate(frames):
        cv2.imwrite(str(tmp / f"{i:05d}.jpg"), f, [cv2.IMWRITE_JPEG_QUALITY, 95])
    res = {}
    with torch.autocast("cuda", dtype=torch.bfloat16):
        st = pred.init_state(video_path=str(tmp))
        for j, o in enumerate(objs):
            for pr in o["prompts"]:
                pts = np.array(pr["pos"] + pr.get("neg", []), np.float32)
                lab = np.array([1] * len(pr["pos"]) + [0] * len(pr.get("neg", [])), np.int32)
                box = np.array(pr["box"], np.float32) if pr.get("box") else None
                if len(pts) == 0:              # box-only prompt
                    pts, lab = None, None
                pred.add_new_points_or_box(st, frame_idx=min(int(pr["t"]), len(frames) - 1), obj_id=j + 1, points=pts, labels=lab, box=box)
        masks = {}
        for rev in (False, True):
            for fi, ids, lg in pred.propagate_in_video(st, reverse=rev):
                for k, oid in enumerate(ids):
                    masks[(fi, oid)] = (lg[k] > 0).cpu().numpy().squeeze()
        pred.reset_state(st)
    shutil.rmtree(tmp, ignore_errors=True)
    for j, o in enumerate(objs):
        c = np.full((96, 2), np.nan, np.float32); a = np.zeros(96, np.float32); s = np.full((96, 7), np.nan, np.float32)
        for fi in range(len(frames)):
            m = masks.get((fi, j + 1))
            if m is not None and m.sum() > 0:
                ys, xs = np.nonzero(m); c[fi] = (xs.mean() * 2, ys.mean() * 2); a[fi] = m.sum()
                if m.sum() >= 4:   # shape (640x360 px of the frame the mask is on): area, cx, cy, x5, x95, y5, y95
                    s[fi] = [m.sum(), xs.mean(), ys.mean(), np.percentile(xs, 5), np.percentile(xs, 95), np.percentile(ys, 5), np.percentile(ys, 95)]
        for q, arr in (("c", c), ("a", a), ("s", s)):
            if q in KEYS:
                res[f"{o['video']}|{o['obj']}_{q}"] = arr
        if "m" in KEYS:
            mk = np.zeros((len(frames), 360, 640), bool)
            for fi in range(len(frames)):
                m = masks.get((fi, j + 1))
                if m is not None and m.shape == (360, 640):
                    mk[fi] = m
            res[f"{o['video']}|{o['obj']}_m"] = np.packbits(mk, axis=-1)      # (T, 360, 80) uint8, unpack with axis=-1
    return res


jobs = json.load(open(T / (sys.argv[4] if len(sys.argv) > 4 else "sam2_jobs.json")))[shard::nsh]
if os.environ.get("REVERSE"):          # a second worker per GPU runs its shard from the end; they meet in the middle
    jobs = jobs[::-1]
OUTD = T / os.environ.get("OUTDIR", "sam2_shape"); OUTD.mkdir(exist_ok=True)
for job in jobs:
    out = OUTD / f"{job['name']}{job.get('suffix', '')}.npz"
    if out.exists():
        continue
    arrs = {}
    by_video = {}
    for o in job["objects"]:
        by_video.setdefault(o["video"], []).append(o)
    cache = {}
    for v, objs in by_video.items():
        path = job["videos"][v]
        if path not in cache:
            cache[path] = load(path)
        frames = cache[path]
        if v.startswith("ref_"):
            frames = [degrade(f) for f in frames]
        if len(frames) < 4:
            continue
        arrs.update(run(frames, objs))
    np.savez_compressed(out, **arrs)
    print(json.dumps({"name": job["name"], "objects": len(job["objects"])}), flush=True)
