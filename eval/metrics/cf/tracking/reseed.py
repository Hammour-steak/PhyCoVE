# -*- coding: utf-8 -*-
"""Re-find objects that are absent at t0 in a prediction (entries flagged absent_t0 in the detail file of a scoring
pass, DETAIL, relative to WORK; not the DELETE target).
Search frames t0+1 .. t0+16 around the object's GT and source positions at that frame (gradient-magnitude template
match against the GT crop and the source crop of that frame, window +-max(3r, 24 px)); the first frame with a match
>= 0.6 that does not look like the empty background there is taken, and 9 seeds (same pattern as the GT seeds) are
tracked with CoTracker from it. Writes WORK/reseed_tracks/<name>.npz ("<model>|<obj>_t" = -1 if not found, "_xy"
(n,9,2) 1280-px units); one JSON line per object on stdout (the log read by reseed2.py).
usage: reseed.py WORK DETAIL SHARD NSHARDS   (environment: PHYCOVE_ROOT, PRED_ROOT, COTRACKER_REPO, COTRACKER_CKPT)"""
import json, os, sys
from pathlib import Path
import cv2
import numpy as np
import torch

T = Path(sys.argv[1]); DETAIL = sys.argv[2]; shard, nsh = int(sys.argv[3]), int(sys.argv[4])
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


def match(img_gm, tpl, c, w):
    x0, y0 = int(max(0, c[0] - w)), int(max(0, c[1] - w)); x1, y1 = int(min(img_gm.shape[1], c[0] + w + 1)), int(min(img_gm.shape[0], c[1] + w + 1))
    reg = img_gm[y0:y1, x0:x1]
    if tpl is None or reg.shape[0] < tpl.shape[0] or reg.shape[1] < tpl.shape[1] or tpl.std() < 1e-3:
        return -1, None
    res = cv2.matchTemplate(reg, tpl, cv2.TM_CCOEFF_NORMED); _, mx, _, loc = cv2.minMaxLoc(res)
    r = tpl.shape[0] // 2
    return float(mx), (x0 + loc[0] + r, y0 + loc[1] + r)


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
detail = json.load(open(T / DETAIL))
jobs = {}
for name, ds in detail.items():
    dsl = (meta[name].get("edit_dsl") or "").split(); target = dsl[1] if len(dsl) > 1 and dsl[0] == "DELETE" else None
    for d in ds:
        if d.get("absent_t0") and d["obj"] != target:
            jobs.setdefault(name, []).append(d)
names = sorted(jobs)[shard::nsh]
(T / "reseed_tracks").mkdir(exist_ok=True)
for name in names:
    out = T / "reseed_tracks" / f"{name}.npz"
    if out.exists():
        continue
    _, scene, case = name.split("__")
    objs = {o["name"]: o for o in json.load(open(T / "seeds" / f"{name}.json"))["objects"]}
    starts = {}; s = 0
    for o in json.load(open(T / "seeds" / f"{name}.json"))["objects"]:
        starts[o["name"]] = list(range(s, s + len(o["queries"]))); s += len(o["queries"])
    z = np.load(T / "seed_tracks" / f"{name}.npz"); src_t, gt_t = z["source_xy"], z["gt_xy"]
    S = load(REL / f"scenes/{scene}/cases/source/video.mp4"); G = load(REL / f"scenes/{scene}/cases/{case}/video.mp4")
    arrs = {}
    for d in jobs[name]:
        m, o = d["model"], objs[d["obj"]]; idx = starts[d["obj"]]
        if (T / "cam_tracks" / f"{name}.npz").exists() and f"{m}_W" in np.load(T / "cam_tracks" / f"{name}.npz").files:
            continue
        P = load(PRED / m / "videos" / scene / f"{case}.mp4")
        n = min(len(P), len(S), len(G)); rr = int(max(o["r_px"] / 2.0, 8.0)); w = max(3 * rr, 24)
        cs = np.median(src_t[:n, idx], axis=1) / 2; cg = np.median(gt_t[:n, idx], axis=1) / 2
        found = None
        for t in range(o["t0"] + 1, min(o["t0"] + 17, n)):
            pg = gm(P[t]); best = (-1, None)
            for ref, cref in ((G[t], cg[t]), (S[t], cs[t])):
                tpl = crop(gm(ref), cref, rr)
                for c in (cg[t], cs[t]):
                    sc, pos = match(pg, tpl, c, w)
                    if sc > best[0]:
                        best = (sc, pos)
            if best[0] >= 0.6:
                # not the empty background: source frame where the source object is farthest from this spot
                far = int(np.argmax(np.linalg.norm(cs - np.array(best[1]), axis=-1)))
                bgc = crop(gm(S[far]), best[1], rr); pc = crop(pg, best[1], rr)
                nb = float(cv2.matchTemplate(pc, bgc, cv2.TM_CCOEFF_NORMED)[0, 0]) if bgc is not None and pc is not None and bgc.std() > 1e-3 and pc.std() > 1e-3 else -1
                if nb < 0.5:
                    found = (t, best[1], best[0], nb); break
        key = f"{m}|{d['obj']}"
        if found is None:
            arrs[f"{key}_t"] = np.int32(-1); print(json.dumps({"name": name, "model": m, "obj": d["obj"], "found": None}), flush=True); continue
        t, (x, y), sc, nb = found
        off = np.array([[q[1], q[2]] for q in o["queries"]]) - np.array(o["queries"][0][1:])
        q = np.array([[t, x + dx, y + dy] for dx, dy in off], np.float32)
        q[:, 1] = q[:, 1].clip(0, 639); q[:, 2] = q[:, 2].clip(0, 359)
        arrs[f"{key}_t"] = np.int32(t); arrs[f"{key}_xy"] = track(P, q).astype(np.float32)
        print(json.dumps({"name": name, "model": m, "obj": d["obj"], "found": [t, x, y, round(sc, 2), round(nb, 2)]}), flush=True)
    np.savez_compressed(out, **arrs)
