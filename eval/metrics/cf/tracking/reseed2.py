# -*- coding: utf-8 -*-
"""Second search for objects absent at t0 and not found near their expected position (reseed.py "found": null; DELETE
targets and their parts skipped): the object may enter from outside the frame or start elsewhere. Full-frame,
multi-scale (0.7, 1, 1.4, 2) gradient-magnitude template match of the GT crop at t0 for t = t0+1 .. t0+24; accepted
at the first frame whose best match >= 0.7 is repeated at the next frame (>= 0.65, within 3 r) and does not look like
the empty background there. Then CoTracker from it, as reseed.py. Jobs = the "found": null lines of the reseed.py logs.
-> WORK/reseed2_tracks/<name>.npz
usage: reseed2.py WORK SHARD NSHARDS RESEED_LOG [RESEED_LOG ...]
environment: PHYCOVE_ROOT, PRED_ROOT, COTRACKER_REPO, COTRACKER_CKPT"""
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


def gm(img):
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 1.5)
    return np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))


def crop(a, c, r):
    x, y = int(round(c[0])), int(round(c[1]))
    if x - r < 0 or y - r < 0 or x + r + 1 > a.shape[1] or y + r + 1 > a.shape[0]:
        return None
    return a[y - r:y + r + 1, x - r:x + r + 1]


def best_match(img_gm, tpl):
    best = (-1, None, 1.0)
    for s in (0.7, 1.0, 1.4, 2.0):
        t = cv2.resize(tpl, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
        if t.shape[0] < 7 or t.shape[0] >= img_gm.shape[0] or t.std() < 1e-3:
            continue
        res = cv2.matchTemplate(img_gm, t, cv2.TM_CCOEFF_NORMED); _, mx, _, loc = cv2.minMaxLoc(res)
        if mx > best[0]:
            best = (float(mx), (loc[0] + t.shape[1] // 2, loc[1] + t.shape[0] // 2), s)
    return best


@torch.no_grad()
def track(v, q):
    x = torch.from_numpy(v).permute(0, 3, 1, 2)[None].float().cuda()
    tr, _ = tracker(x, queries=torch.tensor(q[None], dtype=torch.float32).cuda(), backward_tracking=True)
    return tr[0].cpu().numpy() * 2.0


meta = {}
for l in open(REL / "metadata.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r.get("source_case_id"):
        meta["sim__" + r["id"].replace("/", "__")] = r
L = [json.loads(l) for f in sorted(sys.argv[4:]) for l in open(f) if l.startswith("{")]
jobs = {}
for x in L:
    if x["found"] is not None:
        continue
    tg = {seg.split()[1] for seg in (meta[x["name"]].get("edit_dsl") or "").split(";") if len(seg.split()) > 1 and seg.split()[0] == "DELETE"}
    if any(x["obj"] == t or x["obj"].startswith(t + "_") for t in tg):
        continue
    jobs.setdefault(x["name"], []).append(x)
names = sorted(jobs)[shard::nsh]
(T / "reseed2_tracks").mkdir(exist_ok=True)
for name in names:
    out = T / "reseed2_tracks" / f"{name}.npz"
    if out.exists():
        continue
    _, scene, case = name.split("__")
    objs_l = json.load(open(T / "seeds" / f"{name}.json"))["objects"]; objs = {o["name"]: o for o in objs_l}
    starts, s = {}, 0
    for o in objs_l:
        starts[o["name"]] = list(range(s, s + len(o["queries"]))); s += len(o["queries"])
    z = np.load(T / "seed_tracks" / f"{name}.npz")
    S = load(REL / f"scenes/{scene}/cases/source/video.mp4"); G = load(REL / f"scenes/{scene}/cases/{case}/video.mp4")
    arrs = {}
    for x in jobs[name]:
        m, o = x["model"], objs[x["obj"]]; idx = starts[x["obj"]]; t0 = o["t0"]
        P = load(PRED / m / "videos" / scene / f"{case}.mp4")
        n = min(len(P), len(S), len(G)); rr = int(max(o["r_px"] / 2.0, 8.0))
        cs = np.median(z["source_xy"][:n, idx], axis=1) / 2
        tpl = crop(gm(G[t0]), np.median(z["gt_xy"][t0, idx], axis=0) / 2, rr)
        found = None
        if tpl is not None:
            prev = None
            for t in range(t0 + 1, min(t0 + 25, n)):
                sc, pos, scl = best_match(gm(P[t]), tpl)
                if prev is not None and sc >= 0.65 and prev[0] >= 0.7 and np.hypot(pos[0] - prev[1][0], pos[1] - prev[1][1]) < 3 * rr * scl:
                    far = int(np.argmax(np.linalg.norm(cs - np.array(prev[1]), axis=-1)))
                    r2 = int(rr * prev[2]); bgc = crop(gm(S[far]), prev[1], r2); pc = crop(gm(P[t - 1]), prev[1], r2)
                    nb = float(cv2.matchTemplate(pc, bgc, cv2.TM_CCOEFF_NORMED)[0, 0]) if bgc is not None and pc is not None and bgc.std() > 1e-3 and pc.std() > 1e-3 else -1
                    if nb < 0.5:
                        found = (t - 1, prev[1], prev[0], prev[2]); break
                prev = (sc, pos, scl) if pos is not None else None
        key = f"{m}|{x['obj']}"
        if found is None:
            arrs[f"{key}_t"] = np.int32(-1); print(json.dumps({"name": name, "model": m, "obj": x["obj"], "found": None}), flush=True); continue
        t, (fx, fy), sc, scl = found
        off = (np.array([[q[1], q[2]] for q in o["queries"]]) - np.array(o["queries"][0][1:])) * scl
        q = np.array([[t, fx + dx, fy + dy] for dx, dy in off], np.float32); q[:, 1] = q[:, 1].clip(0, 639); q[:, 2] = q[:, 2].clip(0, 359)
        arrs[f"{key}_t"] = np.int32(t); arrs[f"{key}_xy"] = track(P, q).astype(np.float32)
        print(json.dumps({"name": name, "model": m, "obj": x["obj"], "found": [t, int(fx), int(fy), round(sc, 2), scl]}), flush=True)
    np.savez_compressed(out, **arrs)
