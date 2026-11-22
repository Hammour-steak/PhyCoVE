# -*- coding: utf-8 -*-
"""Mask IoU, step 2: per-frame IoU between the generated video's object mask and the ground-truth object mask, on the
objects whose motion CF scores, using the masks of cf/tracking/track_sam2.py (sam2_mask<TAG>/) and mask_meta<TAG>.json
(mask_jobs.py). A frame counts for an object when the ground-truth mask is on the object (limited to a window of 1.2
object sizes around the verified ground-truth track point, centred on it, area within 0.5-2.0x the object's mask area
in the source video), the object exists in the ground truth at that frame (3D truth for simulated cases, the
annotation for real ones), and no other object's mask covers the same region (IoU > 0.5); the prediction's mask must
pass the same test on the verified prediction track, else the frame is a segmentation miss and is not scored.
Prediction masks are brought into the frame CF uses (camera map W inverted, Seedance clock), as in the CF run. An
object the prediction does not show (absent verdict) scores 0. Object IoU = mean over its frames (>= 3), video IoU =
mean over its objects. REFS=1 scores the source video and the re-encoded ground truth instead (mask_jobs_ref.py).
-> WORK/mask_iou_videos<TAG>.json (REFS=1: WORK/mask_iou_refs<TAG>.json)
usage: mask_iou.py WORK SIM_DETAIL REAL_RESULTS   (SIM_DETAIL = cf_sim_detail<SUFFIX>.json, REAL_RESULTS =
cf_real<SUFFIX>.json, both in WORK; environment: PHYCOVE_ROOT, NPROC, MASK_TAG for an additional model's masks)"""
import json, os, sys
from multiprocessing import Pool
from pathlib import Path
import cv2
import numpy as np
T = Path(sys.argv[1])
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
import traj_lib as tl
W0 = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
TAG = os.environ.get("MASK_TAG", "")
META = json.load(open(T / f"mask_meta{TAG}.json"))
# only objects whose motion CF actually scores (>= 1 position key in the final runs): a tracked object with no scored
# key, e.g. one the edit removes, would compare two background regions
SCORED = set()
for n, es in json.load(open(T / sys.argv[2])).items():
    for e in es:
        if any(not k.startswith("shape:") for k in (e.get("keys") or {})):
            SCORED.add((n, e["model"], e["obj"]))
for r in json.load(open(T / sys.argv[3])):
    for d in r["detail"]:
        if d.get("keys"):
            SCORED.add((r["name"], d.get("model"), d["obj"]))
META = {k: v for k, v in META.items() if k.split("|")[1] == "gt" or tuple(k.split("|")) in SCORED}
by_case = {}
for k, v in META.items():
    name, m, ob = k.split("|"); by_case.setdefault(name, {})[(m, ob)] = v


def unpack(z, key):
    return np.unpackbits(z[key], axis=-1)[..., :640].astype(bool) if key in z.files else None


def gate(mk, track, t0, size, aref=None, scale=1.0):
    """frames (absolute index) where the mask sits on the verified track. The mask is first limited to a window of
    1.2 object sizes around the track point (drops leaks onto the floor or onto far objects); it must then be centred
    on the track and its area within 0.5-2.0x the object's area in the source video (merges with a neighbour fail)"""
    ok = {}
    areas = []
    tol = max(0.75 * size, 12.0); hw = max(1.2 * size, 20.0)
    for i in range(len(track)):
        t = t0 + i
        if t >= len(mk) or not np.isfinite(track[i]).all():
            continue
        x, y = track[i]
        x0, x1, y0, y1 = int(max(0, x - hw)), int(min(640, x + hw + 1)), int(max(0, y - hw)), int(min(360, y + hw + 1))
        if x1 <= x0 or y1 <= y0:
            continue
        m = np.zeros_like(mk[t]); m[y0:y1, x0:x1] = mk[t][y0:y1, x0:x1]
        a = int(m.sum())
        if a < 4:
            continue
        ys, xs = np.nonzero(m)
        if np.hypot(xs.mean() - x, ys.mean() - y) <= tol:
            ok[t] = m; areas.append(a)
    if areas:
        ref = aref * scale * scale if aref else float(np.median(areas))
        ok = {t: m for t, m in ok.items() if 0.5 * ref <= m.sum() <= 2.0 * ref}
    return ok


def src_area(name, ob):
    split = name.split("__")[0]
    for f in ([T / "sam2_shape" / f"{name}.npz", T / "sam2_shape" / f"{name}__ref.npz"] if split == "sim" else [T / "sam2_real" / f"{name}.npz"]):
        if f.exists():
            z = np.load(f)
            if f"source|{ob}_s" in z.files:
                s = z[f"source|{ob}_s"]; ok = np.isfinite(s).all(1)
                if ok.sum() >= 3:
                    return float(np.median(s[ok, 0]))
    return None


POP = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(1)
_PRES = {}


def gt_present(name, ob):
    """frames on which the object exists in the ground-truth video (3D truth for simulated cases, the annotation for
    real ones); an object the edit removes has no ground-truth region to compare with"""
    if (name, ob) not in _PRES:
        split, scene, case = name.split("__")
        if split == "sim":
            g = tl.load_gt(W0 / "scenes" / scene / "cases" / case / "ground_truth_transforms.json")
            base = tl.load_gt(W0 / "scenes" / scene / "cases" / "source" / "ground_truth_transforms.json")
            od = tl.normalise(g)
            if ob not in od:
                _PRES[(name, ob)] = set()
            else:
                _, pres, _ = tl.projected_track(g, ob, od, camera_from=base)
                _PRES[(name, ob)] = {t for t, x in enumerate(pres) if x}
        else:
            g = json.load(open(W0 / "real/scenes" / scene / "cases" / case / "ground_truth_transforms.json"))
            o = g.get("objects", {}).get(ob)
            _PRES[(name, ob)] = set(range(96)) if (o is None or o.get("present", True)) else set()
    return _PRES[(name, ob)]


def ambiguous(z, vid, ob, cache):
    """frames (raw index) where this object's mask and another object's mask in the same video cover the same region
    (IoU > 0.5): the two SAM2 objects are bound to one thing there, so the frame is not scored for either"""
    if vid not in cache:
        cache[vid] = {k: z[k] for k in z.files if k.endswith("_m") and k.split("|")[0] == vid}
    me = cache[vid].get(f"{vid}|{ob}_m"); bad = set()
    if me is None:
        return bad
    for k, ot in cache[vid].items():
        if k == f"{vid}|{ob}_m":
            continue
        n = min(len(me), len(ot))
        inter = POP[me[:n] & ot[:n]].sum(axis=(1, 2)); uni = POP[me[:n] | ot[:n]].sum(axis=(1, 2))
        bad |= set(np.where((uni > 0) & (inter > 0.5 * uni))[0].tolist())
    return bad


def do_case(name):
    zp = T / f"sam2_mask{TAG}" / f"{name}.npz"
    if not zp.exists():
        return name, None
    z = np.load(zp); entries = by_case[name]; out = {}; cache = {}
    gt = {}
    for (m, ob), v in entries.items():
        if m == "gt":
            mk = unpack(z, f"gt|{ob}_m")
            g_ = gate(mk, np.asarray(v["g"], float), v["t0"], v["size"], src_area(name, ob)) if mk is not None else {}
            amb = ambiguous(z, "gt", ob, cache); pr = gt_present(name, ob)
            gt[ob] = {t: x for t, x in g_.items() if t not in amb and t in pr}
    for (m, ob), v in entries.items():
        if m == "gt" or v["status"] == "skip":
            continue
        G = gt.get(ob, {})
        if len(G) < 3:
            continue
        if v["status"] == "absent":
            out.setdefault(m, {})[ob] = {"iou": 0.0, "frames": len(G), "status": "absent"}
            continue
        mk = unpack(z, f"{m}|{ob}_m")
        if mk is None:
            continue
        p = np.asarray(v["p"], float); t0 = v["t0"]; nraw = v["nraw"]; W = np.asarray(v["W"], float) if v.get("W") else None
        Wi = cv2.invertAffineTransform(W) if W is not None else None
        # prediction masks on the CF clock and in the CF frame
        pm = np.zeros((96, 360, 640), bool)
        for i in range(len(p)):
            t = t0 + i
            j = int(round(t * (nraw - 1) / 95.0)) if m == "seedance25" else t
            if j >= min(nraw, len(mk)):
                continue
            a = mk[j]
            if Wi is not None and a.any():
                a = cv2.warpAffine(a.astype(np.uint8), Wi, (640, 360), flags=cv2.INTER_NEAREST) > 0
            pm[t] = a
        P = gate(pm, p, t0, v["size"], src_area(name, ob))
        amb = ambiguous(z, m, ob, cache)
        P = {t: x for t, x in P.items() if (int(round(t * (nraw - 1) / 95.0)) if m == "seedance25" else t) not in amb}
        vals = []
        for t, g in G.items():
            if t in P:
                a = P[t]; vals.append(float(np.count_nonzero(a & g)) / float(np.count_nonzero(a | g)))
        if len(vals) >= 3:
            out.setdefault(m, {})[ob] = {"iou": float(np.mean(vals)), "frames": len(vals), "status": "track"}
    return name, out


METAR = json.load(open(T / f"mask_meta_ref{TAG}.json")) if (T / f"mask_meta_ref{TAG}.json").exists() else {}


def do_ref(name):
    """the source video and the re-encoded ground truth against the ground truth, on the objects CF scores in the case"""
    zp, zr = T / f"sam2_mask{TAG}" / f"{name}.npz", T / f"sam2_mask_ref{TAG}" / f"{name}.npz"
    if not zp.exists() or not zr.exists():
        return name, None
    z, zz = np.load(zp), np.load(zr); out = {}; cache, cache2 = {}, {}
    objs = {o for (n, m, o) in SCORED if n == name and m in MODELS_ALL}
    for ob in objs:
        gv = META.get(f"{name}|gt|{ob}")
        mk = unpack(z, f"gt|{ob}_m") if gv else None
        if mk is None:
            continue
        G = gate(mk, np.asarray(gv["g"], float), gv["t0"], gv["size"], src_area(name, ob))
        amb = ambiguous(z, "gt", ob, cache); pr = gt_present(name, ob)
        G = {t: x for t, x in G.items() if t not in amb and t in pr}
        if len(G) < 3:
            continue
        for vid in ("source", "ref_gt_degraded"):
            v = METAR.get(f"{name}|{vid}|{ob}"); pm = unpack(zz, f"{vid}|{ob}_m") if v else None
            if pm is None:
                continue
            P = gate(pm, np.asarray(v["p"], float), v["t0"], v["size"], src_area(name, ob))
            amb2 = ambiguous(zz, vid, ob, cache2)
            P = {t: x for t, x in P.items() if t not in amb2}
            vals = [float(np.count_nonzero(P[t] & g)) / float(np.count_nonzero(P[t] | g)) for t, g in G.items() if t in P]
            if len(vals) >= 3:
                out.setdefault(vid, []).append(float(np.mean(vals)))
    return name, {k: float(np.mean(v)) for k, v in out.items()}


MODELS_ALL = {"joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"}


if __name__ == "__main__":
    if METAR and os.environ.get("REFS") == "1":
        with Pool(int(os.environ.get("NPROC", "32"))) as pool:
            RR = dict(pool.map(do_ref, sorted(by_case)))
        RR = {k: v for k, v in RR.items() if v}
        json.dump(RR, open(T / f"mask_iou_refs{TAG}.json", "w"), indent=1)
        for vid in ("source", "ref_gt_degraded"):
            v = [x[vid] for x in RR.values() if vid in x]
            print(f"reference {vid}: {np.mean(v):.3f} over {len(v)} cases")
        sys.exit(0)
    with Pool(int(os.environ.get("NPROC", "32"))) as pool:
        R = dict(pool.map(do_case, sorted(by_case)))
    res = []
    for name, out in R.items():
        if not out:
            continue
        split, scene, case = name.split("__")
        for m, objs in out.items():
            res.append({"split": split, "scene": scene, "case": case, "model": m, "mask_iou": float(np.mean([o["iou"] for o in objs.values()])),
                        "objects": {k: round(o["iou"], 4) for k, o in objs.items()}, "frames": int(sum(o["frames"] for o in objs.values()))})
    json.dump(res, open(T / f"mask_iou_videos{TAG}.json", "w"), indent=1)
    miss = [n for n, o in R.items() if o is None]
    print(len(res), "videos with a Mask IoU;", len(miss), "cases without mask file")
    for m in sorted({r["model"] for r in res}):
        v = [r["mask_iou"] for r in res if r["model"] == m]
        print(f"  {m:18s} {np.mean(v):.3f} ({len(v)})")
