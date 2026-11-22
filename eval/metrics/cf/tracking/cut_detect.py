# -*- coding: utf-8 -*-
"""Scene cuts inside predictions (a model jumps to another shot mid-clip). On the 24 fps timeline (Seedance stretched
to 96 frames), frames at 160x90 grey: d_t = mean |f_t - f_{t-1}|. A cut at t: d_t > max(20, 6 x median d) and the
frame after does not match the frame before (gradient correlation < 0.5) and the image does not return within 3 frames.
-> WORK/cuts.json {name: {model: t_cut}}   usage: cut_detect.py WORK   (environment: PRED_ROOT)"""
import json, os, sys
from multiprocessing import Pool
from pathlib import Path
import cv2
import numpy as np

T = Path(sys.argv[1])
PRED = Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en"))
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]


def frames(path, stretch):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(cv2.cvtColor(cv2.resize(f, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32))
    if not fr:
        return []
    if stretch and len(fr) < 96:
        return [fr[int(round(j * (len(fr) - 1) / 95.0))] for j in range(96)]
    return [fr[int(round(k * fps / 24.0))] for k in range(96) if int(round(k * fps / 24.0)) < len(fr)]


def gcorr(a, b):
    ga = np.hypot(cv2.Sobel(a, cv2.CV_32F, 1, 0), cv2.Sobel(a, cv2.CV_32F, 0, 1)).ravel()
    gb = np.hypot(cv2.Sobel(b, cv2.CV_32F, 1, 0), cv2.Sobel(b, cv2.CV_32F, 0, 1)).ravel()
    ga = (ga - ga.mean()) / (ga.std() + 1e-6); gb = (gb - gb.mean()) / (gb.std() + 1e-6); return float(np.mean(ga * gb))


def do(name):
    _, scene, case = name.split("__"); out = {}
    for m in MODELS:
        p = PRED / m / "videos" / scene / f"{case}.mp4"
        if not p.exists():
            continue
        F = frames(p, m == "seedance25")
        if len(F) < 8:
            continue
        d = np.array([np.mean(np.abs(F[t] - F[t - 1])) for t in range(1, len(F))])
        thr = max(20.0, 6 * np.median(d))
        for t in range(2, len(F)):
            if d[t - 1] > thr and gcorr(F[t - 1], F[t]) < 0.5:
                back = any(gcorr(F[t - 1], F[k]) > 0.7 for k in range(t + 1, min(t + 4, len(F))))
                if not back:
                    out[m] = t; break
    return name, out


if __name__ == "__main__":
    names = [f.stem for f in sorted((T / "seed_tracks").glob("*.npz"))]
    with Pool(32) as pool:
        res = {n: o for n, o in pool.map(do, names, chunksize=2) if o}
    json.dump(res, open(T / "cuts.json", "w"), indent=0)
    from collections import Counter
    print("predictions with a cut:", dict(Counter(m for o in res.values() for m in o)))
    for n, o in list(res.items())[:12]:
        print(" ", n[5:], o)
