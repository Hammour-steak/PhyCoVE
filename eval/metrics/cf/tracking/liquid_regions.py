# -*- coding: utf-8 -*-
"""Liquid regions by change detection (no 3D truth for liquids). Per video on the 24 fps timeline (Seedance stretched,
camera-aligned predictions warped onto the source frame), at 320x180:
  D_t = Lab distance between frame t and the same video's start picture (per-pixel median of frames 1-4, later for a
  prediction that takes a few frames to settle; 3x3 blurred), after a small ECC stabilisation and a tone fit on the
  background; noise_t = median D_t over the frame; changed_t = D_t > max(TAU, noise_t + TAU)
ROI of a case = pixels that change in the clean source or target clip in >= 3 frames (stricter TAU2), dilated 20 px,
minus per-scene boxes where liquid sits at the start (liquid_scenes.json "exclude"); the SAM 2 boxes of solid objects
that move are cut out of every frame. Liquid mask M_t = changed_t & ROI, opened 2x2. pool_t = horizontal opening of
M_t (3x11; the settled liquid: puddle, glass content); stream_t = M_t - pool_t (thin falling stream).
Per video: A (total), P (pool), S (stream) areas and pool extents x5, x95, y5, y95 (px at 320x180, NaN when empty).
-> WORK/liquid_tracks/<name>.npz  "<video>|liquid_<q>" (96,), "<video>|liquid_ref0", "<model>|cam", plus "roi" mask.
usage: liquid_regions.py WORK LIST   (LIST = JSON list of case names, relative to WORK; environment: PHYCOVE_ROOT,
PRED_ROOT, SHAPEDIR)"""
import json, os, sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from region_lib import transform_stats

T = Path(sys.argv[1]); names = json.load(open(T / sys.argv[2]))
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
PRED = Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en"))
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]
TAU, TAU2 = 7.0, 10.0
W_, H_ = 320, 180


def npz(p):
    return dict(np.load(p)) if p.exists() else {}


def load(path, W=None, stretch=False):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(cv2.resize(f, (640, 360), interpolation=cv2.INTER_AREA))
    if not fr:
        return []
    if stretch and len(fr) < 96:
        fr = [fr[int(round(j * (len(fr) - 1) / 95.0))] for j in range(96)]
    else:
        fr = [fr[int(round(k * fps / 24.0))] for k in range(96) if int(round(k * fps / 24.0)) < len(fr)]
    if W is not None:
        fr = [cv2.warpAffine(f, W, (640, 360), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE) for f in fr]
    return fr


def degrade(f, q=50):
    g = cv2.resize(cv2.resize(f, (336, 192), interpolation=cv2.INTER_AREA), (640, 360), interpolation=cv2.INTER_LINEAR)
    ok, b = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, q]); return cv2.imdecode(b, cv2.IMREAD_COLOR)


def to_lab(frames):
    return [cv2.GaussianBlur(cv2.cvtColor(cv2.resize(f, (W_, H_), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2LAB).astype(np.float32), (3, 3), 0) for f in frames]


def settle_err(lab, bg):
    """e_t, t = 1..8: median Lab distance on the background between frame t (tone-fitted) and frame 12"""
    e = []
    for t in range(1, 9):
        L = lab[t].copy()
        for c in range(3):
            x, y = L[..., c][bg], lab[12][..., c][bg]
            a, b = np.polyfit(x, y, 1) if np.std(x) > 1e-3 else (1.0, float(np.median(y - x)))
            L[..., c] = a * L[..., c] + b
        e.append(float(np.median(np.linalg.norm(L - lab[12], axis=-1)[bg])))
    return e


def change(frames, tau, bg=None, base=None):
    lab = to_lab(frames)
    out = []
    # reference picture of the start = per-pixel median of frames 1-4, the same for every video: several models copy
    # the source's sharp first frame and only then switch to their own (softer, re-lit) rendering, which would turn every
    # dark surface into "liquid" against frame 0; a single odd frame does not move a median
    s0 = 1
    if base is not None and bg is not None and bg.sum() > 500 and len(lab) >= 13:
        # a few predictions (OmniWeaving) take up to ~7 frames to settle from an over-bright first frame: the reference
        # starts at the first frame whose background is as close to frame 12 as the SOURCE's is at that frame (+1.0);
        # base = the source's e_t, so real scene dynamics (water spreading fast, moving shadows) do not count as an
        # unsettled start. The clean renders (source, GT, references) always start at frame 1.
        e = settle_err(lab, bg)
        for t in range(1, 9):
            s0 = t
            if e[t - 1] <= max(1.5, base[t - 1] + 1.0):
                break
    ref = np.median(np.stack(lab[s0:s0 + 4]), axis=0) if len(lab) >= s0 + 4 else lab[0]
    change.s0 = s0
    m0 = np.median(ref.reshape(-1, 3), axis=0)
    rg = ref[..., 0].astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-4)
    for i, L in enumerate(lab):
        # stabilise: generated videos drift (slow zoom / pan after the first frames); every frame is aligned to the
        # reference with an affine ECC fit (insensitive to exposure), accepted only for small, clearly better fits
        # (|shift| <= 15 px at 320, scale within 3 %), so a large patch of new liquid cannot drag the alignment
        try:
            g = L[..., 0].astype(np.float32)
            c0 = float(np.corrcoef(rg.ravel(), g.ravel())[0, 1])
            c1, W = cv2.findTransformECC(rg, g, np.eye(2, 3, dtype=np.float32), cv2.MOTION_AFFINE, crit, None, 5)
            sc_ = np.sqrt(abs(np.linalg.det(W[:, :2])))
            if c1 > c0 + 0.02 and np.abs(W[:, 2]).max() <= 15 and abs(sc_ - 1) <= 0.03:
                L = cv2.warpAffine(L, W, (W_, H_), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
        except cv2.error:
            pass
        if bg is not None and bg.sum() > 500:
            # tone of each frame matched to the reference by a per-channel gain + offset fitted on the BACKGROUND (outside
            # the liquid's reach, where nothing should change): a model that drifts in contrast / colour after its first
            # frames must not turn every dark surface into liquid
            L = L.copy()
            for c in range(3):
                x, y = L[..., c][bg], ref[..., c][bg]
                a, b = np.polyfit(x, y, 1) if np.std(x) > 1e-3 else (1.0, float(np.median(y - x)))
                L[..., c] = a * L[..., c] + b
        else:
            # global exposure / white balance of each frame matched to the reference (median over the frame)
            L = L - np.median(L.reshape(-1, 3), axis=0) + m0
        d = np.linalg.norm(L - ref, axis=-1); noise = float(np.median(d))
        out.append(d > max(tau, noise + tau))
    return out


K2 = np.ones((2, 2), np.uint8)
K7 = np.ones((3, 11), np.uint8)    # horizontal opening: a falling stream (< 11 px wide at 320) goes, pooled liquid stays


def measure(ch, roi):
    q = {k: np.full(96, np.nan, np.float32) for k in ("A", "P", "S", "x5", "x95", "y5", "y95")}
    masks = []
    for t, c in enumerate(ch[:96]):
        m = cv2.morphologyEx((c & roi).astype(np.uint8), cv2.MORPH_OPEN, K2)
        p = cv2.morphologyEx(m, cv2.MORPH_OPEN, K7)
        q["A"][t], q["P"][t], q["S"][t] = m.sum(), p.sum(), (m & (1 - p)).sum()
        if p.sum() >= 4:
            ys, xs = np.nonzero(p)
            q["x5"][t], q["x95"][t] = np.percentile(xs, 5), np.percentile(xs, 95)
            q["y5"][t], q["y95"][t] = np.percentile(ys, 5), np.percentile(ys, 95)
        masks.append((m, p))
    return q, masks


SCN = json.load(open(T / "liquid_scenes.json")) if (T / "liquid_scenes.json").exists() else {}


def grad(f):
    g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(f, (W_, H_), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32), (5, 5), 0)
    m = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)); return g, m


def gcorr(a, b):
    a = (a - a.mean()) / (a.std() + 1e-6); b = (b - b.mean()) / (b.std() + 1e-6); return float(np.mean(a * b))


def align(src0, pred0):
    """camera check for predictions with no stored alignment: gradient correlation of frame 0 against the source;
    if low, an ECC affine fit at 320x180; returns (W at 640 scale or None, before, after)"""
    gs, ms = grad(src0); gp, mp = grad(pred0); before = gcorr(ms, mp)
    if before >= 0.6:
        return None, before, before
    cands = []
    W = np.eye(2, 3, dtype=np.float32)
    try:
        _, W = cv2.findTransformECC(gs, gp, W, cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5), None, 5)
        cands.append(W.astype(np.float32))
    except cv2.error:
        pass
    # zooms / bigger shifts defeat ECC: SIFT + RANSAC similarity on the 640 frames (pred = M src)
    sift = cv2.SIFT_create(3000)
    a = cv2.cvtColor(src0, cv2.COLOR_BGR2GRAY); b = cv2.cvtColor(pred0, cv2.COLOR_BGR2GRAY)
    ka, da = sift.detectAndCompute(a, None); kb, db = sift.detectAndCompute(b, None)
    if da is not None and db is not None and len(ka) > 20 and len(kb) > 20:
        mt = [m for m, n in cv2.BFMatcher().knnMatch(da, db, k=2) if m.distance < 0.75 * n.distance]
        if len(mt) >= 12:
            M, inl = cv2.estimateAffinePartial2D(np.float32([ka[m.queryIdx].pt for m in mt]), np.float32([kb[m.trainIdx].pt for m in mt]),
                                                 method=cv2.RANSAC, ransacReprojThreshold=4.0)
            if M is not None and inl is not None and inl.sum() >= 12:
                M2 = M.astype(np.float32).copy(); M2[:, 2] /= 2.0; cands.append(M2)
    best, after = None, before
    for Wc in cands:
        c = gcorr(ms, cv2.warpAffine(mp, Wc, (W_, H_), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP))
        if c > after:
            best, after = Wc, c
    if best is None or after < max(before + 0.1, 0.5):
        return None, before, after
    W2 = best.copy(); W2[:, 2] *= 2.0
    return W2, before, after


for name in names:
    _, scene, case = name.split("__")
    cam = npz(T / "cam_tracks" / f"{name}.npz"); cam.update(npz(T / "cam_tracks2" / f"{name}.npz"))
    vids = {"source": load(REL / f"scenes/{scene}/cases/source/video.mp4"), "gt": load(REL / f"scenes/{scene}/cases/{case}/video.mp4")}
    n = min(len(vids["source"]), len(vids["gt"])); vids["source"], vids["gt"] = vids["source"][:n], vids["gt"][:n]
    vids["ref_gt_degraded"] = [degrade(f) for f in vids["gt"]]; vids["ref_source_degraded"] = [degrade(f) for f in vids["source"]]
    camq = {}
    for m in MODELS:
        p = PRED / m / "videos" / scene / f"{case}.mp4"
        if p.exists():
            Wm = cam.get(f"{m}_W")
            if Wm is None:
                raw = load(p, None, m == "seedance25")
                if raw:
                    Wm, b, a = align(vids["source"][0], raw[0]); camq[m] = [b, a, Wm is not None]
            vids[m] = load(p, Wm, m == "seedance25")
    cs, cg = change(vids["source"], TAU2), change(vids["gt"], TAU2)
    cnt = np.sum(cs, 0) + np.sum(cg, 0)
    roi = cv2.dilate((cnt >= 3).astype(np.uint8), np.ones((41, 41), np.uint8)).astype(bool)
    for x0, y0, x1, y1 in SCN.get(scene, {}).get("exclude", []):    # where liquid sits at the start (spoon, tank, bottle)
        roi[y0 // 2:y1 // 2, x0 // 2:x1 // 2] = False
    arrs, keep = {"roi": roi}, {}
    bgmask = ~cv2.dilate(roi.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)   # where nothing should change
    for m, v in camq.items():
        arrs[f"{m}|cam"] = np.array(v, np.float32)
    # solids moving in the liquid (ball, duck, ice, toy car, falling cup, inflating balloon) are not liquid: their
    # SAM 2 box (the runs in sam2_shape/) is cut out of every frame, per video. Only objects that move
    # or change size in the source or the GT; static containers (glass, sink, pool) keep the liquid inside them.
    SH = T / os.environ.get("SHAPEDIR", "sam2_shape")
    sh = {k: v for f in ("", "__ref") for k, v in npz(SH / f"{name}{f}.npz").items() if k.endswith("_s")}
    shc = {k: v for k, v in npz(SH / f"{name}__cam.npz").items() if k.endswith("_s")}
    seeds = json.load(open(T / "seeds" / f"{name}.json"))["objects"] if (T / "seeds" / f"{name}.json").exists() else []
    g = json.load(open(REL / f"scenes/{scene}/cases/source/ground_truth_transforms.json"))["objects"]
    dyn = []
    for o in seeds:
        if g.get(o["name"], {}).get("kind") == "fluid":
            continue
        for v in ("source", "gt"):
            s = sh.get(f"{v}|{o['name']}_s")
            if s is None or not np.isfinite(s).all(1).any():
                continue
            s = s[np.isfinite(s).all(1)]
            if np.max(np.linalg.norm(s[:, 1:3] - s[0, 1:3], axis=1)) > max(6.0, 0.15 * o["r_px"]) or np.max(np.abs(s[:, 0] / max(s[0, 0], 1) - 1)) > 0.3:
                dyn.append(o["name"]); break

    def solid_boxes(k, n_):
        """per frame list of boxes (320x180) of the moving solids in video k"""
        out = [[] for _ in range(n_)]
        for ob in dyn:
            s = None
            if f"{k}|{ob}_s" in shc and cam.get(f"{k}_W") is not None:
                s = transform_stats(shc[f"{k}|{ob}_s"], np.linalg.inv(np.vstack([cam[f"{k}_W"], [0, 0, 1]]))[:2])
            elif k in camq and camq[k][2]:
                s = None                           # aligned here (no stored alignment): its SAM2 boxes are unaligned
            else:
                s = sh.get(f"{k}|{ob}_s")
            if s is None:
                continue
            s = np.asarray(s, np.float32)
            if k == "seedance25" and np.isfinite(s).all(1).sum() < 96:
                L = int(np.isfinite(s).all(1).sum()) or 1
                s = s[np.round(np.arange(96) * (L - 1) / 95.0).astype(int)]
            box = lambda r: (int((r[3] - 0.25 * (r[4] - r[3]) - 6) / 2), int((r[5] - 0.25 * (r[6] - r[5]) - 6) / 2),
                             int((r[4] + 0.25 * (r[4] - r[3]) + 6) / 2) + 1, int((r[6] + 0.25 * (r[6] - r[5]) + 6) / 2) + 1)
            fin = np.isfinite(s).all(1)
            first = box(s[np.where(fin)[0][0]]) if fin.any() else None
            for t in range(n_):
                if first is not None:
                    out[t].append(first)          # where the solid was at the start: its leaving is not liquid either
                if t < len(s) and fin[t]:
                    out[t].append(box(s[t]))
        return out
    e_src = settle_err(to_lab(vids["source"][:13]), bgmask) if len(vids["source"]) >= 13 and bgmask.sum() > 500 else None
    for k, v in vids.items():
        if len(v) < 8:
            continue
        ch = change(v, TAU, bg=bgmask, base=e_src if k in MODELS else None); arrs[f"{k}|liquid_ref0"] = np.array(change.s0, np.float32)
        if dyn:
            bx = solid_boxes("source" if k == "ref_source_degraded" and not any(f"ref_source_degraded|{o}_s" in sh for o in dyn)
                             else ("gt" if k == "ref_gt_degraded" and not any(f"ref_gt_degraded|{o}_s" in sh for o in dyn) else k), len(ch))
            for t, bl in enumerate(bx):
                for x0, y0, x1, y1 in bl:
                    ch[t][max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = False
        q, masks = measure(ch, roi)
        for qq, a in q.items():
            arrs[f"{k}|liquid_{qq}"] = a
        keep[k] = (v, masks)
    (T / "liquid_tracks").mkdir(exist_ok=True)
    np.savez_compressed(T / "liquid_tracks" / f"{name}.npz", **arrs)
    print(json.dumps({"name": name, "roi_px": int(roi.sum()), **{k: [int(np.nanmax(arrs[f'{k}|liquid_P'])), int(np.nanmax(arrs[f'{k}|liquid_S']))] for k in keep}}), flush=True)
