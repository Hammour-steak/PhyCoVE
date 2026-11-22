# -*- coding: utf-8 -*-
"""Mask IoU, step 1: SAM2 mask jobs built from the VERIFIED tracks that CF scored, so every correction (hand prompts,
picked candidates, absent / excluded verdicts, camera re-location, Seedance clock) carries over unchanged.
For each scored (case, model, object) of the final CF runs (sim cf_sim_detail<SIM> + tracks_used/, real cf_real<REAL>
+ real_tracks_used/): status "track" -> SAM2 object on the RAW prediction prompted with point + square box at 4 frames
along the verified trajectory (mapped to raw coordinates by the camera map W and to the raw clock for Seedance);
"absent" (object not drawn / scene unrecognisable / missing) -> IoU 0 without SAM2; "skip" (excluded, or a copied
source / GT trajectory). Each object of the case is also segmented in the ground-truth video along its verified
ground-truth trajectory.   -> WORK/sam2_jobs_mask.json (run cf/tracking/track_sam2.py with KEYS=casm OUTDIR=sam2_mask)
+ WORK/mask_meta.json
usage: mask_jobs.py WORK SIM_SUFFIX REAL_SUFFIX   (environment: PHYCOVE_ROOT, PRED_ROOT, PRED_ROOT_REAL)"""
import json, os, sys
from collections import Counter
from pathlib import Path
import numpy as np
T = Path(sys.argv[1]); SIM, REAL = sys.argv[2], sys.argv[3]
W0 = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
PS = Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en"))
PR = Path(os.environ.get("PRED_ROOT_REAL", "predictions/PhyCoVE/real/quantitative_en"))
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]
RELOC = json.load(open(T / "reloc_W.json"))


def nframes(path):
    import cv2
    c = cv2.VideoCapture(str(path)); fps = c.get(cv2.CAP_PROP_FPS) or 24.0; n = int(c.get(cv2.CAP_PROP_FRAME_COUNT))
    return min(96, sum(1 for k in range(96) if int(round(k * fps / 24.0)) < n))


def cam_w(name, m):
    for d in ("cam_tracks2", "cam_tracks"):
        p = T / d / f"{name}.npz"
        if p.exists():
            z = np.load(p)
            if f"{m}_W" in z:
                return np.asarray(z[f"{m}_W"], float)[:2]
    if f"{name}|{m}" in RELOC:
        return np.asarray(RELOC[f"{name}|{m}"]["W"], float)[:2]
    return None


def size_of(zs, key, fallback):
    s = zs.get(key)
    if s is not None:
        ok = np.isfinite(s).all(1)
        if ok.any():
            return float(np.median(np.maximum(s[ok, 4] - s[ok, 3], s[ok, 6] - s[ok, 5])))
    return float(fallback)


def prompts(track, t0, size, W=None, nraw=96, stretch=False):
    """4 prompts along a verified track (640 coords of the source frame, frame t0 + i) -> raw video prompts"""
    L = len(track); out = []
    for i in sorted({int(round(x)) for x in np.linspace(0, L - 1, 4)}):
        q = track[i]
        if not np.isfinite(q).all():
            continue
        x, y = (W[:, :2] @ q + W[:, 2]) if W is not None else q
        t = t0 + i
        if stretch:
            t = int(round(t * (nraw - 1) / 95.0))
        if t >= nraw or not (0 <= x < 640 and 0 <= y < 360):
            continue
        h = float(np.clip(0.65 * size, 8, 160))
        out.append({"t": int(t), "pos": [[round(float(x), 1), round(float(y), 1)]], "neg": [],
                    "box": [round(max(0.0, x - h), 1), round(max(0.0, y - h), 1), round(min(640.0, x + h), 1), round(min(360.0, y + h), 1)]})
    return out


jobs, meta = [], {}


def add_case(name, gt_path, pred_path, entries, dumps, shape, seeds_r, cam):
    """entries: list of (model, obj, status); dumps: tracks npz (1280 units); shape: SAM2 stats (source / gt)"""
    j = {"name": name, "suffix": "", "videos": {"gt": str(gt_path)}, "objects": []}
    gtrack = {}
    for m, ob, st in entries:
        key = f"{m}|{ob}"
        if f"{key}|g" not in dumps:
            continue
        g = np.asarray(dumps[f"{key}|g"], float) / 2.0; t0 = int(dumps[f"{key}|t"])
        if ob not in gtrack or t0 < gtrack[ob][1]:
            gtrack[ob] = (g, t0)
        rec = {"status": st, "t0": t0, "len": len(g)}
        if st == "track":
            vp = pred_path(m)
            if not vp.exists():
                continue
            nraw = nframes(vp); W = cam(m)
            sz = size_of(shape, f"source|{ob}_s", seeds_r.get(ob, 30)) * (float(np.sqrt(abs(np.linalg.det(W[:, :2])))) if W is not None else 1.0)
            p = np.asarray(dumps[f"{key}|p"], float) / 2.0
            prs = prompts(p, t0, sz, W, nraw, stretch=(m == "seedance25"))
            if not prs:
                rec["status"] = "skip"; rec["why"] = "no prompt inside the frame"
            else:
                j["videos"][m] = str(vp)
                j["objects"].append({"obj": ob, "video": m, "prompts": prs})
                rec.update({"W": W.tolist() if W is not None else None, "nraw": nraw, "size": sz, "p": p.round(2).tolist()})
        meta[f"{name}|{m}|{ob}"] = rec
    for ob, (g, t0) in gtrack.items():
        sz = size_of(shape, f"gt|{ob}_s", size_of(shape, f"source|{ob}_s", seeds_r.get(ob, 30)))
        prs = prompts(g, t0, sz)
        if prs:
            j["objects"].append({"obj": ob, "video": "gt", "prompts": prs})
        meta[f"{name}|gt|{ob}"] = {"t0": t0, "g": g.round(2).tolist(), "size": sz}
    if j["objects"]:
        jobs.append(j)


# ---- simulated cases (final CF run SIM)
D = json.load(open(T / f"cf_sim_detail{SIM}.json")); R = {r["name"]: r for r in json.load(open(T / f"cf_sim{SIM}.json"))}
for name, es in D.items():
    if not R[name]["valid"] or not (T / "tracks_used" / f"{name}.npz").exists():
        continue
    _, scene, case = name.split("__")
    dumps = dict(np.load(T / "tracks_used" / f"{name}.npz"))
    shape = {}
    for f in ("", "__ref", "__man"):
        p = T / "sam2_shape" / f"{name}{f}.npz"
        if p.exists():
            shape.update({k: v for k, v in np.load(p).items() if k.endswith("_s") and (k.startswith("source|") or k.startswith("gt|"))})
    seeds_r = {o["name"]: o.get("r_px", 30) for o in json.load(open(T / "seeds" / f"{name}.json"))["objects"]}
    ent = []
    for e in es:
        m = e["model"]
        if m not in MODELS or f"{m}|{e['obj']}|p" not in dumps:
            continue
        src, pen = e.get("src", ""), e.get("penalty")
        st = "absent" if pen in ("absent", "missing") or src == "unrecognisable_video" else "skip" if src in ("manual_as_source", "manual_as_gt") else "track"
        ent.append((m, e["obj"], st))
    add_case(name, W0 / "scenes" / scene / "cases" / case / "video.mp4", lambda m, s=scene, c=case: PS / m / "videos" / s / f"{c}.mp4",
             ent, dumps, shape, seeds_r, lambda m, n=name: cam_w(n, m))

# ---- real cases (final CF run REAL; no camera map, as scored)
for r in json.load(open(T / f"cf_real{REAL}.json")):
    name = r["name"]; _, scene, case = name.split("__")
    if not r["valid"] or not (T / "real_tracks_used" / f"{name}.npz").exists():
        continue
    dumps = dict(np.load(T / "real_tracks_used" / f"{name}.npz"))
    sp = T / "sam2_real" / f"{name}.npz"; shape = {k: v for k, v in np.load(sp).items() if k.endswith("_s")} if sp.exists() else {}
    ent = []
    for d in r["detail"]:
        m = d.get("model")
        if m not in MODELS or "keys" not in d or f"{m}|{d['obj']}|p" not in dumps:
            continue
        ent.append((m, d["obj"], "absent" if d.get("src") == "manual_absent" else "track"))
    add_case(name, W0 / "real" / "scenes" / scene / "cases" / case / "video.mp4", lambda m, s=scene, c=case: PR / m / "videos" / s / f"{c}.mp4",
             ent, dumps, shape, {}, lambda m: None)

json.dump(jobs, open(T / "sam2_jobs_mask.json", "w"))
json.dump(meta, open(T / "mask_meta.json", "w"))
print(len(jobs), "jobs,", sum(len(j["objects"]) for j in jobs), "SAM2 objects;", Counter(v.get("status", "gt") for v in meta.values()))
