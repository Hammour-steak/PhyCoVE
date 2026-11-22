# -*- coding: utf-8 -*-
"""Real-video cases: moving-region proposals for the hand annotation. Background = per-pixel median of the 96 frames;
a pixel is foreground when its Lab distance to the background > THR (default 28); opening/closing; connected
components with area >= 60 px (640x360) -> per frame a list of boxes (largest 8). A hand prompt ["b", t, i] in
real_prompts.json refers to box i of frame t and becomes a SAM 2 box prompt (real_jobs.py).
-> WORK/real_blobs/<vid>.json {t: [[x0, y0, x1, y1, area], ...]}
usage: real_blobs.py WORK [vid ...]   (environment: PHYCOVE_ROOT, PRED_ROOT_REAL, THR)"""
import json, os, sys
from multiprocessing import Pool
from pathlib import Path
import cv2
import numpy as np
T = Path(sys.argv[1])
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE")) / "real"
OUT = T / "real_blobs"; OUT.mkdir(exist_ok=True)
THR = float(os.environ.get("THR", "28"))


def frames(path):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(f)
    return [cv2.resize(fr[int(round(k * fps / 24.0))], (640, 360), interpolation=cv2.INTER_AREA)
            for k in range(96) if int(round(k * fps / 24.0)) < len(fr)]


PREDROOT = Path(os.environ.get("PRED_ROOT_REAL", "predictions/PhyCoVE/real/quantitative_en"))


def videos():
    out = {}
    for l in open(REL / "metadata.jsonl"):
        d = json.loads(l); sc = d["scene"]
        out[f"{sc}__source"] = REL / "scenes" / sc / "cases" / "source" / "video.mp4"
        out[f"{sc}__{d['case_id']}"] = REL / "scenes" / sc / "cases" / d["case_id"] / "video.mp4"
    for m in ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]:
        for l in open(REL / "metadata.jsonl"):
            d = json.loads(l); p = PREDROOT / m / "videos" / d["scene"] / f"{d['case_id']}.mp4"
            if p.exists():
                out[f"{d['scene']}__{d['case_id']}@{m}"] = p
    return out


def do(vid):
    F = frames(videos()[vid]); L = np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2LAB).astype(np.float32) for f in F])
    bg = np.median(L, 0); B = {}
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    for t in range(len(F)):
        d = np.linalg.norm(L[t] - bg, axis=-1) > THR
        m = cv2.morphologyEx(cv2.morphologyEx(d.astype(np.uint8), cv2.MORPH_OPEN, k3), cv2.MORPH_CLOSE, k3, iterations=2)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m)
        bx = [[int(s[0]), int(s[1]), int(s[0] + s[2]), int(s[1] + s[3]), int(s[4])] for s in st[1:] if s[4] >= 60]
        B[t] = sorted(bx, key=lambda b: -b[4])[:8]
    json.dump(B, open(OUT / f"{vid}.json", "w"))
    return vid


if __name__ == "__main__":
    vids = sys.argv[2:] or sorted(videos())
    with Pool(16) as p:
        print(len(p.map(do, vids)), "videos")
