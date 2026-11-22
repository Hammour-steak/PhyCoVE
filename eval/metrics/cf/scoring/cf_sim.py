# -*- coding: utf-8 -*-
"""Counterfactual Fidelity (CF) of every generated video on the simulated cases.

Every object of a case is followed as a region through the source video, the target video (ground truth), two
re-encoded reference copies (ref_gt_degraded, ref_source_degraded) and each generated video. Quantities:
 * position: end displacement, path length, horizontal range, lowest and highest point, stop frame, all from the
   displacement relative to the object's own start, on the validated position track;
 * shape: height, width and area at the end and smallest height of the SAM 2 mask (region_lib.py); deformables with
   no valid position track also get their extents (top, bottom, lowest reach, x centre);
 * liquids: amount over time, stream frames and pool extents of the change region (liquid_regions.py); liquid that
   does not flow scores -1; cases where only liquid moves are scored from the liquid alone;
 * presence: objects removed at a later frame ("gone") and objects added by an ADD edit ("appeared").
A quantity counts only if the target changes it clearly and the re-encoded target copy reproduces the change (>= 0.5)
while the re-encoded source copy does not (|.| < 0.5). Score = <dP, dG> / |dG|^2, values above 1 scored 2 - x, clipped
to [-1, 1]. Objects that are absent, missing or frozen score -1 on every quantity; an added or removed object whose
start frame looks more like the source than like the target has its scores capped at 0. CF of a video = mean over its
quantities; a case is valid if at least one quantity passes the reference check.

Position track per (video, object): hand verdict (manual_tracks.json) if any, else the trackers validated for the
object against the 3D ground truth (validation.json: CoTracker seed tracks "ct", SAM 2 mask centroid "s2", or SAM 2
prompted from the true 3D position "m2"), each checked for spread, persistence and stuck tracks; a re-seeded track
where the object only appears later; camera-aligned tracks where the first frame is shifted (cam_tracks*/).

usage: cf_sim.py WORK SUFFIX  -> WORK/cf_sim<SUFFIX>.json (per case), cf_sim_detail<SUFFIX>.json (per video and
object), cf_sim_todo<SUFFIX>.json (objects left for the hand check)
environment: PHYCOVE_ROOT, PRED_ROOT (see README); NPROC; EXTRA_MODELS / ONLY (an additional model, a case subset);
DUMPREF=1 also writes the reference copies' entries to the detail file; DUMPTRACK=1 writes the scored trajectories to
WORK/<DUMPTRACK_DIR>/<case>.npz (default tracks_used), DUMPTRACK_REFS=1 includes the reference copies."""
import glob, json, os, re, sys
from multiprocessing import Pool
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from region_lib import score as rscore, transform_stats, shape_q, shape_thr, shape_ok, liquid_q, liquid_thr, liquid_frozen

T = Path(sys.argv[1]); SUF = sys.argv[2] if len(sys.argv) > 2 else ""
SHAPED = T / os.environ.get("SHAPEDIR", "sam2_shape")
LIQ = json.load(open(T / "liquid_scenes.json")) if (T / "liquid_scenes.json").exists() else {}   # pour vs body of water
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
PRED = Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en"))
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"] + [m for m in os.environ.get("EXTRA_MODELS", "").split(",") if m]
SHORT = ["JoyAI", "Kiwi", "OmniW", "Kling", "Seedance", "Wan3", "MiniMax", "VOID"]
REFS = ("ref_gt_degraded", "ref_source_degraded")
BASE = {"end": 10, "xrange": 10, "lowest": 8, "highest": 8, "stop": 4}
KER = np.ones(5) / 5
FLUID = re.compile(r"^(water|orange_juice|juice|tea|coffee|milk|wine|honey|oil|liquid)(_\d+)?$")
MANUAL = json.load(open(T / "manual_tracks.json")) if (T / "manual_tracks.json").exists() else {}
# camera-changed predictions re-located by hand: SAM 2 on the raw prediction, mapped to the source frame by a
# similarity fitted at the start only; later camera motion counts as object motion
RELOC_W = {tuple(k.split("|")): np.array(v["W"], np.float64) for k, v in json.load(open(T / "reloc_W.json")).items()} \
    if (T / "reloc_W.json").exists() else {}
TIMED = json.load(open(T / "timed_targets.json")) if (T / "timed_targets.json").exists() else {}   # timed_prep.py
VAL_M2 = json.load(open(T / "validation_m2.json")) if (T / "validation_m2.json").exists() else {}  # refman.py
PRES_MANUAL = json.load(open(T / "presence_manual.json")) if (T / "presence_manual.json").exists() else {}   # hand presence verdicts
VAL_REF2 = json.load(open(T / "validation_ref2.json")) if (T / "validation_ref2.json").exists() else {}  # refman2.py
ADDED = json.load(open(T / "added_targets.json")) if (T / "added_targets.json").exists() else {}  # added_prep.py
CONNECTORS = {"elastic_key_strap": {"strap"}, "opposing_pendulum_collision": {"B_left_rope", "B_right_rope"},
              "rubber_band_wood_slider": {"band"}, "slingshot_domino": {"bands"}, "tennis_net_hit": {"center_strap"}}
VAL = json.load(open(T / "validation.json"))
MIS0 = {(r["name"], r["model"]): r["mis0"] or 0 for r in json.load(open(T / "cam_stats.json"))}
STRETCH = ["seedance25"]   # models that return the whole 4 s clip in fewer frames
CUTS = json.load(open(T / "cuts.json")) if (T / "cuts.json").exists() else {}
DUMPREF = os.environ.get("DUMPREF", "0") == "1"    # 1: also write the references' per-object keys to the detail file
DUMPTRACK = os.environ.get("DUMPTRACK", "0") == "1"  # 1: write the scored trajectories to T/<DUMPTRACK_DIR>/<name>.npz
DUMPTRACK_REFS = os.environ.get("DUMPTRACK_REFS", "0") == "1"   # 1: including the two reference copies
DUMPTRACK_DIR = os.environ.get("DUMPTRACK_DIR", "tracks_used")
OVERSHOOT = "soft"    # going beyond the target change is scored 2 - ratio (2x -> 0)
BEFORE = {(x["name"], x["model"]): x.get("before") for f in glob.glob(str(T / "cam_retrack_[0-9].json")) for x in json.load(open(f))}
# predictions seen by eye to move the camera (pan / zoom / new viewpoint) that the automatic test missed: "CAM <name> <model>"
CAM_MANUAL = {tuple(l.split()[1:3]) for l in open(T / "camera_manual.txt")
              if l.startswith("CAM ")} if (T / "camera_manual.txt").exists() else set()
# predictions seen by eye to have lost the scene (fog / heavy blur, none of the objects recognisable): "UNRECOGNIZABLE <name>
# <model>" -> every measured object counts as absent (-1); otherwise an invisible object reads as "did not move"
UNRECOGNIZABLE = {tuple(l.split()[1:3]) for l in open(T / "camera_manual.txt")
           if l.startswith("UNRECOGNIZABLE ")} if (T / "camera_manual.txt").exists() else set()


def npz(p):
    return dict(np.load(p)) if p.exists() else {}


def load_video(path):
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
    return out


def degrade(f):
    g = cv2.resize(cv2.resize(f, (672, 384), interpolation=cv2.INTER_AREA), (640, 360), interpolation=cv2.INTER_LINEAR)
    ok, b = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, 75]); return cv2.imdecode(b, cv2.IMREAD_COLOR)


def gz(img, box):
    x0, y0, x1, y1 = box
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    g = cv2.GaussianBlur(cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 1.5)
    m = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)).ravel()
    return None if m.std() < 1e-3 else (m - m.mean()) / m.std()


def ncc(a, b, box, box_b=None):
    if a is None or b is None:
        return None
    za, zb = gz(a, box), gz(b, box_b or box)
    return None if za is None or zb is None or za.shape != zb.shape else float(np.mean(za * zb))


def smooth1(c):
    pad = np.concatenate([c[:1].repeat(2, 0), c, c[-1:].repeat(2, 0)])
    return np.stack([np.convolve(pad[:, d], KER, "valid") for d in range(2)], -1)


def fill(c):
    c = np.array(c, float); ok = np.isfinite(c).all(1)
    if ok.sum() < 2:
        return None
    t = np.arange(len(c))
    for d in range(2):
        c[:, d] = np.interp(t, t[ok], c[ok, d])
    return c


def quantities(c):
    c = c - c[0]                                         # displacement from the object's own start
    v = np.linalg.norm(np.diff(c, axis=0), axis=-1); stop = len(c) - 1
    for t in range(len(v) - 1, -1, -1):
        if v[t] >= 1.5:
            break
        stop = t
    return {"end": c[-1], "path": float(v.sum()), "xrange": float(np.ptp(c[:, 0])), "lowest": float(c[:, 1].max()),
            "highest": float(c[:, 1].min()), "stop": float(stop)}


def boxat(c, rr):
    cx, cy = c / 2.0
    return (int(max(0, cx - rr)), int(max(0, cy - rr)), int(min(640, cx + rr + 1)), int(min(360, cy + rr + 1)))


def ref_validity(out, refk):
    """case validity, consistent with how predictions are scored: a key counts only if the degraded GT copy reproduces
    it (>= 0.5) and the degraded source does not (|.| < 0.5); the case is valid if at least one key passes. The two
    reference scores are then reported over the passing keys (so they are ~1 / ~0 by construction); the share of
    passing keys is kept in out["ref_keys"] = [passing, all]."""
    G, S = refk.get("ref_gt_degraded", {}), refk.get("ref_source_degraded", {})
    P = [k for k in G if G[k] >= 0.5 and (k not in S or abs(S[k]) < 0.5)]
    out["ref_keys"] = [len(P), len(G)]
    if P:
        out["s"]["ref_gt_degraded"] = {"kq": float(np.mean([G[k] for k in P])), "nkey": len(P), "nkey_all": len(G)}
        ps = [S[k] for k in P if k in S]
        out["s"]["ref_source_degraded"] = {"kq": float(np.mean(ps)) if ps else 0.0, "nkey": len(ps), "nkey_all": len(S)}
        out["valid"] = True
    else:
        out["valid"] = False


def liquid_keys(name, zl, m, tc, detail, rk=None):
    """liquid region keys of one video (prediction or reference) -> list of scores (details appended)"""
    if f"{m}|liquid_P" not in zl:
        return []
    cq = zl.get(f"{m}|cam")       # own camera check of the liquid run (frame-0 gradient correlation, ECC / SIFT)
    if m not in REFS and (name, m) not in UNRECOGNIZABLE and cq is not None and not cq[2] and cq[0] < 0.55:
        detail.append({"model": m, "obj": "liquid", "src": "camera_changed"}); return []
    tcl = min(tc, int(np.isfinite(zl[f"{m}|liquid_P"]).sum()))
    if tcl < 8:
        return []
    Q = {v: liquid_q(zl, v, tcl) for v in ("source", "gt") + REFS}
    qp = Q[m] if m in REFS else liquid_q(zl, m, tcl)
    frozen = m not in REFS and ((name, m) in UNRECOGNIZABLE or liquid_frozen(Q["source"], Q["gt"], qp))
    d = {"model": m, "obj": "liquid", "role": "region", "kind": "liquid", "src": "liquid_region", "keys": {}}
    out = []
    for k in Q["source"]:
        a, b = Q["source"][k], Q["gt"][k]
        if not (np.isfinite(a) and np.isfinite(b)) or abs(b - a) <= liquid_thr(k, a, b):
            continue
        if m not in REFS:
            rg = rscore(Q[REFS[0]][k], a, b) if np.isfinite(Q[REFS[0]][k]) else None
            rs = rscore(Q[REFS[1]][k], a, b) if np.isfinite(Q[REFS[1]][k]) else None
            if rg is None or rg < 0.5 or (rs is not None and abs(rs) >= 0.5):
                continue
        v = qp[k]
        s = -1.0 if frozen else (rscore(v, a, b, OVERSHOOT) if np.isfinite(v) else -1.0)
        d["keys"][f"liquid:{k}"] = [round(abs(b - a), 1), round(s, 3), round(liquid_thr(k, a, b), 1)]
        out.append(s)
        if rk is not None and m in REFS:
            rk[("liquid", f"liquid:{k}")] = s
    d["penalty"] = "liquid_frozen" if frozen else None
    if m not in REFS or DUMPREF:
        detail.append(d)
    return out


def do_liquid_case(args):
    """cases where only liquid moves (no GT-tracked object): scored from the liquid region alone"""
    name, r = args
    zl = npz(T / "liquid_tracks" / f"{name}.npz")
    out = {"name": name, "set": "sim", "kind": (r.get("edit_dsl") or "").split()[0] if r.get("edit_dsl") else "",
           "category": r.get("interaction_category"), "s": {}, "merged": [], "liquid_only": True}
    detail = []; refk = {r_: {} for r_ in REFS}
    for m in list(REFS) + MODELS:
        if f"{m}|liquid_P" not in zl:
            continue
        if m not in REFS and (name, m) in CAM_MANUAL and (name, m) not in UNRECOGNIZABLE:
            detail.append({"model": m, "obj": "liquid", "src": "camera_changed"}); continue
        tc = 96 if m in REFS else int(np.isfinite(zl[f"{m}|liquid_P"]).sum())
        if m in CUTS.get(name, {}):
            tc = min(tc, int(CUTS[name][m]))
        sc = liquid_keys(name, zl, m, tc, detail, refk.get(m))
        if sc:
            out["s"][m] = {"kq": float(np.mean(sc)), "nkey": len(sc)}
    ref_validity(out, refk)
    return out, detail, []


def do_case(args):
    name, r = args
    if not (T / "seed_tracks" / f"{name}.npz").exists():
        return do_liquid_case(args)
    _, scene, case = name.split("__")
    objs = json.load(open(T / "seeds" / f"{name}.json"))["objects"]
    z = npz(T / "seed_tracks" / f"{name}.npz"); zm = npz(T / "seed_tracks_mild" / f"{name}.npz")
    z["ref_gt_degraded_xy"], z["ref_source_degraded_xy"] = zm["ref_gt_mild_xy"], zm["ref_source_mild_xy"]
    s2 = npz(T / "sam2_tracks" / f"{name}.npz"); s2.update(npz(T / "sam2_tracks" / f"{name}__ref.npz"))
    rs = npz(T / "reseed_tracks" / f"{name}.npz")
    for k, v in npz(T / "reseed2_tracks" / f"{name}.npz").items():
        if k.endswith("_t") and int(v) >= 0:
            rs[k] = v; rs[k[:-2] + "_xy"] = np.load(T / "reseed2_tracks" / f"{name}.npz")[k[:-2] + "_xy"]
    cam = npz(T / "cam_tracks" / f"{name}.npz")
    for k, v in npz(T / "cam_tracks2" / f"{name}.npz").items():
        cam.setdefault(k, v)
    s2c = npz(T / "sam2_tracks" / f"{name}__cam.npz")
    man = {k: v for k, v in npz(T / "sam2_tracks" / f"{name}__man.npz").items() if not k.endswith("_s")}   # shapes: shm
    # region shape stats (same SAM 2 prompts, run with shape output): main + references, camera runs, hand-prompted runs
    sh = {k: v for k, v in npz(SHAPED / f"{name}.npz").items() if k.endswith("_s")}
    sh.update({k: v for k, v in npz(SHAPED / f"{name}__ref.npz").items() if k.endswith("_s")})
    shc = {k: v for k, v in npz(SHAPED / f"{name}__cam.npz").items() if k.endswith("_s")}
    shm = {k: v for k, v in npz(SHAPED / f"{name}__man.npz").items() if k.endswith("_s")}
    for m in MODELS:
        if f"{m}_xy" in cam:
            z[f"{m}_xy"] = cam[f"{m}_xy"]
            for k in [k for k in s2 if k.startswith(f"{m}|")]:
                del s2[k]
            Ai = np.linalg.inv(np.vstack([cam[f"{m}_W"], [0, 0, 1]]))
            for k, v in s2c.items():
                if k.startswith(f"{m}|"):
                    s2[k] = (np.c_[v / 2.0, np.ones(len(v))] @ Ai[:2].T * 2.0).astype(np.float32) if k.endswith("_c") else v
            for k, v in list(man.items()):
                if k.startswith(f"{m}|") and k.endswith("_c"):
                    man[k] = (np.c_[v / 2.0, np.ones(len(v))] @ Ai[:2].T * 2.0).astype(np.float32)
            # shapes measured on the raw prediction -> source frame (camera runs replace the unaligned main runs)
            for k in [k for k in sh if k.startswith(f"{m}|")]:
                del sh[k]
            for k, v in shc.items():
                if k.startswith(f"{m}|"):
                    sh[k] = transform_stats(v, Ai[:2])
            for k, v in list(shm.items()):
                if k.startswith(f"{m}|"):
                    shm[k] = transform_stats(v, Ai[:2])
        elif (name, m) in RELOC_W:
            Ai = np.linalg.inv(np.vstack([RELOC_W[(name, m)], [0, 0, 1]]))
            for k, v in list(man.items()):
                if k.startswith(f"{m}|") and k.endswith("_c"):
                    man[k] = (np.c_[v / 2.0, np.ones(len(v))] @ Ai[:2].T * 2.0).astype(np.float32)
            for k, v in list(shm.items()):
                if k.startswith(f"{m}|"):
                    shm[k] = transform_stats(v, Ai[:2])
    # clock: a model that returns the whole clip in fewer frames (Seedance: 89 frames at 24 fps for the 4 s source,
    # measured time scale 1.08 = 96/89) is stretched back to the source duration; tracks are per video frame, so
    # stretching = resampling them on the 96-frame timeline. Frame k of the timeline is video frame k*(L-1)/95.
    stretch = {}
    for m in STRETCH:
        L = len(z[f"{m}_xy"]) if f"{m}_xy" in z else 0
        if 0 < L < 96:
            stretch[m] = L
            pos = np.arange(96) * (L - 1) / 95.0
            def rs_(a, L=L, pos=pos):
                a = np.asarray(a, float)[:L]; flat = a.reshape(L, -1)
                okr = np.isfinite(flat).all(1)
                if okr.sum() < 2:
                    return np.full((96,) + a.shape[1:], np.nan)
                o_ = np.stack([np.interp(pos, np.where(okr)[0], flat[okr, j]) for j in range(flat.shape[1])], -1)
                return o_.reshape((96,) + a.shape[1:]).astype(np.float32)
            z[f"{m}_xy"] = rs_(z[f"{m}_xy"])
            for dct in (s2, man):
                for k in [k for k in dct if k.startswith(f"{m}|")]:
                    dct[k] = rs_(dct[k]) if k.endswith("_c") else np.interp(pos, np.arange(L), np.asarray(dct[k], float)[:L]).astype(np.float32)
            ni = np.round(pos).astype(int)            # shapes: nearest frame, so empty masks stay empty
            for dct in (sh, shm):
                for k in [k for k in dct if k.startswith(f"{m}|")]:
                    dct[k] = np.asarray(dct[k], np.float32)[:L][ni]
            for k in [k for k in rs if k.startswith(f"{m}|") and k.endswith("_t")]:
                if int(rs[k]) >= 0:
                    rs[k] = np.int32(round(int(rs[k]) * 95.0 / (L - 1))); rs[k[:-2] + "_xy"] = rs_(rs[k[:-2] + "_xy"])
    val = VAL.get(name, {})
    xy = lambda k: z.get(f"{k}_xy")
    src, gt = xy("source"), xy("gt"); n = min(len(src), len(gt))
    dsl = r.get("edit_dsl") or ""; kind = dsl.split()
    targets = {seg.split()[1] for seg in dsl.split(";") if len(seg.split()) > 1 and seg.split()[0] == "DELETE"}
    is_target = lambda nm: any(nm == tg or nm.startswith(tg + "_") for tg in targets)
    vp = {"source": REL / f"scenes/{scene}/cases/source/video.mp4", "gt": REL / f"scenes/{scene}/cases/{case}/video.mp4"}
    for m in MODELS:
        vp[m] = PRED / m / "videos" / scene / f"{case}.mp4"
    vids = {}
    def fr(k, t):
        if k not in vids:
            if k in REFS:
                bk = "gt" if k == "ref_gt_degraded" else "source"; fr(bk, 0)
                vids[k] = [degrade(f) for f in vids[bk]]
            else:
                vids[k] = load_video(vp[k]) if vp[k].exists() else []
                if f"{k}_W" in cam:
                    vids[k] = [cv2.warpAffine(f, cam[f"{k}_W"], (640, 360), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP) for f in vids[k]]
                if k in stretch and vids[k]:
                    L = len(vids[k]); vids[k] = [vids[k][int(round(j * (L - 1) / 95.0))] for j in range(96)]
        v = vids[k]
        return v[min(t, len(v) - 1)] if v else None

    def gone_score(m, G, tc, added=False):
        """object deleted mid-clip (timed_targets.json): after the deletion frame, at the object's position in the
        SOURCE (where it still is), does video m look like the source (object still there, 0) or like the GT (object
        gone, 1)?  s_t = (D_ps^2 - D_pg^2 + D_sg^2) / (2 D_sg^2) on blurred Lab crops (half-size max(r/2, 8) px),
        frames with D_sg >= 8 only; median over frames td+3 .. end, clipped to [-1, 1].
        added=True (added_targets.json): the mirror case of an ADD edit: at the object's position in the GT, does m
        look like the GT (object there, 1) or like the source (no object, 0); the object's look (GT crop) is searched
        within +-2h, the empty look (source crop) compared in place"""
        if added:
            return appear_score(m, G, tc)
        h = int(max(G["r"] / 2.0, 8)); vals = []
        lab = lambda f: cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_RGB2LAB).astype(np.float32), (5, 5), 0)   # frames are RGB
        for t in range(G["td"] + 3, tc, 3):
            p = G["pos"][t] if t < len(G["pos"]) else None
            if p is None:
                continue
            x, y = int(round(p[0])), int(round(p[1]))
            if not (h <= x < 640 - h and h <= y < 360 - h):
                continue
            fs, fg, fp = fr("source", t), fr("gt", t), fr(m, t)
            if fs is None or fg is None or fp is None:
                continue
            cs_, cg_, cp_ = (lab(f_[y - h:y + h, x - h:x + h]) for f_ in (fs, fg, fp))
            dist = lambda a, b: float(np.sqrt(np.mean(np.sum((a - b) ** 2, axis=-1))))     # RMS Lab distance
            dsg = dist(cs_, cg_)
            if dsg < 8.0:
                continue
            # "still there" is looked for within +-2h (the object may have been pushed elsewhere than in the source)
            wx0, wy0, wx1, wy1 = max(0, x - 3 * h), max(0, y - 3 * h), min(640, x + 3 * h), min(360, y + 3 * h)
            win = lab(fp[wy0:wy1, wx0:wx1])
            dps = float(np.sqrt(cv2.matchTemplate(win, cs_, cv2.TM_SQDIFF).min() / (4 * h * h)))
            dpg = dist(cp_, cg_)
            # the prediction looks like neither (scene re-drawn there): the deletion is not shown -> 0
            vals.append(0.0 if min(dps, dpg) > dsg else (dps ** 2 - dpg ** 2 + dsg ** 2) / (2 * dsg ** 2))
        return float(np.clip(np.median(vals), -1, 1)) if len(vals) >= 3 else None

    def appear_score(m, G, tc):
        h = int(max(G["r"] / 2.0, 8)); vals = []
        lab = lambda f: cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_RGB2LAB).astype(np.float32), (5, 5), 0)
        dist = lambda a, b: float(np.sqrt(np.mean(np.sum((a - b) ** 2, axis=-1))))
        for t in range(G["ta"] + 3, tc, 3):
            p = G["pos"][t] if t < len(G["pos"]) else None
            if p is None:
                continue
            x, y = int(round(p[0])), int(round(p[1]))
            if not (h <= x < 640 - h and h <= y < 360 - h):
                continue
            fs, fg, fp = fr("source", t), fr("gt", t), fr(m, t)
            if fs is None or fg is None or fp is None:
                continue
            cs_, cg_, cp_ = (lab(f_[y - h:y + h, x - h:x + h]) for f_ in (fs, fg, fp))
            dsg = dist(cs_, cg_)
            if dsg < 8.0:
                continue
            wx0, wy0, wx1, wy1 = max(0, x - 3 * h), max(0, y - 3 * h), min(640, x + 3 * h), min(360, y + 3 * h)
            dpg = float(np.sqrt(cv2.matchTemplate(lab(fp[wy0:wy1, wx0:wx1]), cg_, cv2.TM_SQDIFF).min() / (4 * h * h)))
            dps = dist(cp_, cs_)
            # an added object that looks like neither (another look or size) is settled by a hand verdict
            # (presence_manual.json)
            vals.append((dps ** 2 - dpg ** 2 + dsg ** 2) / (2 * dsg ** 2))
        return float(np.clip(np.median(vals), -1, 1)) if len(vals) >= 3 else None

    def presence_key(m, nm, G, tc, kname, added, d):
        """gone / appeared key of one object in video m, expressed relative to the degraded GT copy; None if not
        measurable or the references do not reproduce it"""
        mvp = MANUAL.get(f"{name}|{m}|{nm}", {}).get("verdict")
        if mvp == "exclude" or (m not in REFS and (name, m) in RELOC_W):
            return None
        if m not in REFS and (name, m) in UNRECOGNIZABLE:
            gs = -1.0
        elif added and mvp == "absent":
            gs = 0.0
        else:
            gs = gone_score(m, G, tc, added)
        if gs is None:
            return None
        # raw scores are mapped so that the degraded source copy is 0 and the degraded GT copy is 1 (the window search
        # lets background patches partly match the object, so raw values are offset); the key counts only if the two
        # copies are >= 0.5 apart and the GT copy reaches >= 0.5
        rg_raw, rs_raw = refkey.get((kname + "_raw", nm)), refkey.get((kname + "_rawsrc", nm))
        if m == "ref_gt_degraded":
            refkey[(kname + "_raw", nm)] = gs; gs = 1.0 if gs >= 0.5 else gs
        elif m == "ref_source_degraded":
            if rg_raw is None:
                return None
            refkey[(kname + "_rawsrc", nm)] = gs
            gs = 0.0 if (rg_raw >= 0.5 and rg_raw - gs >= 0.5) else 1.0
        else:
            if rg_raw is None or rs_raw is None or rg_raw < 0.5 or rg_raw - rs_raw < 0.5:
                return None
            if gs != -1.0 and not (added and mvp == "absent"):
                # 0 = edit not shown, 1 = as in the GT (a negative value would mean "more present than the source")
                gs = float(np.clip((gs - rs_raw) / (rg_raw - rs_raw), 0, 1))
            pm = PRES_MANUAL.get(f"{name}|{m}|{nm}")
            if pm is not None:              # hand presence verdict
                gs = float(pm["value"]); d["src_presence"] = "manual"
        if m in REFS:
            refkey[(m, nm, kname)] = gs
        d.setdefault("keys", {})[kname] = [0.0, round(gs, 3), 0.0]
        if m in REFS:
            refk[m][(nm, kname)] = gs
        return gs

    refk = {r_: {} for r_ in REFS}      # every reference key score: case validity = >= 1 key passing the per-key check
    dumptr = {}                         # DUMPTRACK=1: trajectory actually scored per (model, object) -> DUMPTRACK_DIR

    # ---- per object: which trackers are valid, reference tracker, reference trajectories (full length n)
    vm2 = VAL_M2.get(name, {})
    m2ok = lambda nm: nm in vm2 and all(vm2[nm].get(k) is not None and vm2[nm][k] <= vm2[nm]["tol"] for k in ("m2_src", "m2_gt", "m2_rgt", "m2_rsrc"))
    refm_all = npz(T / "sam2_refman" / f"{name}__refman.npz")
    refm = {k: v for k, v in refm_all.items() if k.endswith("_c") and m2ok(k.split("|")[1][:-2])}
    for k, v in refm_all.items():                  # their shapes on source / GT / references, from the same runs
        if k.endswith("_s") and m2ok(k.split("|")[1][:-2]):
            sh[k] = v
    vr2 = VAL_REF2.get(name, {})
    refm2_all = npz(T / "sam2_refman2" / f"{name}__refman.npz") if vr2 else {}
    refm2 = {k: v for k, v in refm2_all.items() if k.endswith("_c") and vr2.get(k.split("|")[1][:-2], {}).get("ok")}
    for k, v in refm2_all.items():
        if k.endswith("_s") and vr2.get(k.split("|")[1][:-2], {}).get("ok"):
            sh[k] = v
    info, s_ = {}, 0
    for o in objs:
        idx = list(range(s_, s_ + len(o["queries"]))); s_ += len(o["queries"])
        nm = o["name"]; v = val.get(nm, {}); tol = max(16.0, 0.6 * o["r_px"])
        okv = lambda k: v.get(k) is not None and v[k] <= tol
        I = {"idx": idx, "fluid": bool(FLUID.match(nm))}
        if o["role"] != "both":
            I["cands"], I["kind"] = ["ct"], "role_" + o["role"]
        elif v.get("moves", 0) < 10:
            I["cands"], I["kind"] = ["ct", "s2"], "origin_static"
        else:
            I["cands"] = [t for t, ok in (("ct", okv("ct_src") and okv("ct_gt")), ("s2", okv("s2_src") and okv("s2_gt"))) if ok]
            I["kind"] = "validated"
            if not I["cands"] and okv("cs_src") and okv("cs_gt"):
                # both trackers agree with each other on the clean renders but not with the 3D origin (origin off the
                # visible centre, partly submerged object ...): the visible object is tracked, so both count
                I["cands"], I["kind"] = ["ct", "s2"], "trackers_agree"
        if not I["cands"] and o["role"] == "both" and m2ok(nm):
            # no tracker held on the clean renders, but SAM2 prompted from the true 3D position (refman.py) does:
            # reference trajectories from it; predictions are measured by their SAM2 run (+ hand verdicts)
            I["cands"], I["kind"] = ["m2"], "manual_ref"
        I["R"] = I["cands"][0] if I["cands"] else None
        def trk(tr, key):
            if tr == "m2":
                c = refm.get(f"{key}|{nm}_c"); return None if c is None else fill(c)
            if tr == "ct":
                x = xy(key); return None if x is None else np.median(x[:, idx], axis=1)
            c = s2.get(f"{key}|{nm}_c"); return None if c is None else fill(c)
        if I["R"]:
            I["ref"] = {key: trk(I["R"], key) for key in ("source", "gt", "ref_gt_degraded", "ref_source_degraded")}
        f2 = VAL_REF2.get(name, {}).get(nm)
        if f2 is not None:
            # the reference tracker lost the object (ref_check.py): redone from the true 3D position (refman2.py);
            # validated -> those references (a video without the object keeps the one from its tracker), else not
            # measurable
            if f2["ok"]:
                old = I.get("ref") or {}
                I["ref"] = {key: (fill(refm2[f"{key}|{nm}_c"]) if f"{key}|{nm}_c" in refm2 else old.get(key))
                            for key in ("source", "gt", "ref_gt_degraded", "ref_source_degraded")}
                # only the source / GT references change; predictions keep their trackers (a deleted object keeps
                # its CoTracker track; s2 when no tracker was listed)
                I["R"], I["cands"], I["kind"] = "m2", (I["cands"] or ["m2"]), "ref_redone"
            else:
                I["R"], I["cands"], I["kind"] = None, [], "ref_lost"
        info[nm] = I
    # rigid assemblies count once (offsets between reference trajectories nearly fixed in source and GT)
    drop, order = set(), sorted([o["name"] for o in objs if o["role"] == "both" and info[o["name"]]["R"]], key=lambda k: -next(o["r_px"] for o in objs if o["name"] == k))
    rpx = {o["name"]: o["r_px"] for o in objs}; t0s = {o["name"]: o["t0"] for o in objs}
    for i_, a in enumerate(order):
        if a in drop:
            continue
        for b in order[i_ + 1:]:
            if b in drop:
                continue
            t_ = max(t0s[a], t0s[b]); same = True
            for key in ("source", "gt"):
                A, B = info[a]["ref"][key], info[b]["ref"][key]
                if A is None or B is None:
                    same = False; break
                off = A[t_:n] - B[t_:n]
                if len(off) < 4 or np.linalg.norm(off.std(0)) > 0.5 * rpx[a] or np.linalg.norm(off.mean(0)) > 1.2 * rpx[a]:
                    same = False
            if same:
                drop.add(b)
    out = {"name": name, "set": "sim", "kind": kind[0] if kind else "", "category": r.get("interaction_category"), "s": {}, "merged": sorted(drop)}
    detail, todo, refkey = [], [], {}
    KIND = {}
    for gp in (REL / f"scenes/{scene}/cases/source/ground_truth_transforms.json", REL / f"scenes/{scene}/cases/{case}/ground_truth_transforms.json"):
        if gp.exists():
            KIND.update({k: v.get("kind") for k, v in json.load(open(gp))["objects"].items()})
    zl = npz(T / "liquid_tracks" / f"{name}.npz")

    def shape_keys(m, o, t0, tc, has_pos, penalty, cap, mv, d, track=None, t_start=None):
        """region shape keys of one object in one video; position-free unless the object has no position track.
        track: the position trajectory used for this object (1280 px, from t_start) when it is not the SAM2 mask's own
        centroid -> the mask must move like it (displacement error <= max(16, 0.6 r), as the 3D validation)"""
        nm = o["name"]; ss, sg = sh.get(f"source|{nm}_s"), sh.get(f"gt|{nm}_s")
        if ss is None or sg is None or KIND.get(nm) == "fluid":
            return []
        if nm in CONNECTORS.get(scene, ()):
            # thin connectors (1-3 px ropes, straps, rubber bands): SAM2 segments the rail / loses them after release in
            # source, GT and predictions alike, and their shape is set by the objects they hold, which are measured
            d["shape_why"] = "thin_connector"
            return []
        qs, qg = shape_q(ss, t0, tc, not has_pos), shape_q(sg, t0, tc, not has_pos)
        if qs is None or qg is None:
            return []
        refq = {}
        for rf in REFS:
            sr = sh.get(f"{rf}|{nm}_s")
            refq[rf] = shape_q(sr, t0, tc, not has_pos) if sr is not None and shape_ok(sr, ss, sg, t0, tc)[0] else None
        if m in REFS:
            qp = refq[m]
            if qp is None:
                return []
        elif penalty:
            qp = None
        elif mv == "as_source":
            qp = qs
        elif mv == "as_gt":
            qp = qg
        else:
            sp = (shm if mv == "sam2" else sh).get(f"{m}|{nm}_s")
            ok, why = shape_ok(sp, ss, sg, t0, tc)
            if ok and track is not None:
                ts_ = t0 if t_start is None else t_start
                mc = np.asarray(sp, float)[ts_:ts_ + len(track), 1:3] * 2.0; tr = np.asarray(track, float)[:len(mc)]
                okf = np.isfinite(mc).all(1) & np.isfinite(tr).all(1)
                if okf.sum() >= 4:
                    i0 = np.where(okf)[0][0]
                    err = np.linalg.norm((mc[okf] - mc[i0]) - (tr[okf] - tr[i0]), axis=-1)
                    if np.percentile(err, 75) > max(16.0, 0.6 * o["r_px"]):
                        ok, why = False, "shape_vs_track"
            if not ok:
                # the object keeps its position keys; only a region measured by its shape alone is lost -> hand list
                d["shape_why"] = why
                if not has_pos:
                    todo.append({"name": name, "model": m, "obj": nm, "why": why, "part": "shape"})
                return []
            qp = shape_q(sp, t0, tc, not has_pos)
        out_s = []
        for k in qs:
            a, b = qs[k], qg[k]
            if not (np.isfinite(a) and np.isfinite(b)) or abs(b - a) <= shape_thr(k, a, b):
                continue
            if m not in REFS:
                qa, qb = refq[REFS[0]], refq[REFS[1]]
                rg = rscore(qa[k], a, b) if qa is not None and np.isfinite(qa[k]) else None
                rs = rscore(qb[k], a, b) if qb is not None and np.isfinite(qb[k]) else None
                if rg is None or rg < 0.5 or (rs is not None and abs(rs) >= 0.5):
                    continue
            if penalty:
                s = -1.0
            else:
                v = qp.get(k, np.nan); s = rscore(v, a, b, OVERSHOOT) if np.isfinite(v) else -1.0
            s = min(s, 0.0) if cap else s
            d.setdefault("keys", {})[f"shape:{k}"] = [round(abs(b - a), 1), round(s, 3), round(shape_thr(k, a, b), 1)]
            out_s.append(s)
            if m in REFS:
                refk[m][(nm, f"shape:{k}")] = s
        return out_s

    for m in list(REFS) + MODELS:
        p = xy(m)
        if p is None:
            continue
        if m not in REFS and (name, m) not in UNRECOGNIZABLE and (name, m) not in RELOC_W and ((MIS0.get((name, m), 0) > 30 and f"{m}_W" not in cam and BEFORE.get((name, m)) is not None and BEFORE[(name, m)] < 0.3)
                              or (name, m) in CAM_MANUAL):
            detail += [{"model": m, "obj": o["name"], "src": "camera_changed"} for o in objs if o["name"] not in drop]
            continue
        tc = min(len(p), n); sc, nkey = [], 0
        if m in CUTS.get(name, {}):
            tc = min(tc, int(CUTS[name][m]))      # the model cut to another shot: only the part before the cut is measured
        for o in objs:
            nm = o["name"]; I = info[nm]; idx = I["idx"]
            t0 = min(o["t0"], tc - 2)
            if tc - t0 < 4 or nm in drop:
                continue
            d = {"model": m, "obj": nm, "role": o["role"], "kind": I["kind"]}
            # removed mid-clip (gone from the GT later; a name sharing the target's prefix that stays is not one): its GT
            # track after removal is meaningless -> scored by whether it is gone after the deletion frame
            # (also a removed object hidden at the start, e.g. a bag inside a scanner)
            timed_target = o["role"] in ("both", "removed") and nm in TIMED.get(name, {})
            mv0 = MANUAL.get(f"{name}|{m}|{nm}", {}).get("verdict")
            if not I["fluid"] and not I["R"] and not timed_target and KIND.get(nm) == "deformable" and mv0 != "exclude":
                # deformable with no valid position track (cloth, straps, ropes): the region's shape incl. its extents
                pen0 = "absent" if mv0 == "absent" or (name, m) in UNRECOGNIZABLE else None
                ss_ = shape_keys(m, o, t0, tc, False, pen0, False, mv0, d)
                d["src"] = "shape_only" if ss_ else "not_measurable"; d["why"] = None if ss_ else d.get("shape_why", "no_shape_key")
                sc += ss_; nkey += len(ss_)
                if m not in REFS or DUMPREF:
                    detail.append(d)
                continue
            if timed_target and not any(nm.startswith(t_ + "_") for t_ in TIMED[name]):
                # the window search makes even the GT copy score below 1 (background patches partly match the
                # object): scores are expressed relative to the degraded GT copy (raw >= 0.5 required)
                gs = presence_key(m, nm, TIMED[name][nm], tc, "gone", False, d)
                if gs is not None:
                    d["src"] = "gone_check"
                    sc.append(gs); nkey += 1
                    if m not in REFS or DUMPREF:
                        detail.append(d)
                    continue
            if I["fluid"] or not I["R"] or timed_target:
                if m not in REFS:
                    d["src"] = "not_measurable"; d["why"] = "fluid" if I["fluid"] else ("timed_delete_target" if timed_target else "reference_track_bad"); detail.append(d)
                continue
            R = I["R"]; cs0, cg0 = I["ref"]["source"], I["ref"]["gt"]
            if cs0 is None or cg0 is None or len(cs0) < tc or len(cg0) < tc:
                continue
            cs = cs0[t0:tc]; cg = cg0[t0:tc]
            if cs is None or cg is None or not np.isfinite(cs).all() or not np.isfinite(cg).all():
                continue
            gref = I["ref"]["ref_gt_degraded"]
            noise = float(np.median(np.linalg.norm(smooth1(gref[t0:tc]) - smooth1(cg), axis=-1))) if gref is not None and len(gref) >= tc else 0.0
            rr = max(o["r_px"] / 2.0, 8.0)
            box = boxat(np.median(src[t0, idx] if o["role"] != "added" else gt[t0, idx], axis=0), rr)
            ok_box = box[2] - box[0] >= 6 and box[3] - box[1] >= 6
            penalty, cap, cp = None, False, None
            key = f"{name}|{m}|{nm}"
            if m in REFS:
                cp = I["ref"][m]
                if cp is None or len(cp) < tc:
                    continue
                cp = cp[t0:tc]; d["src"] = R
            elif (name, m) in UNRECOGNIZABLE:
                penalty = "absent"; cp = cs; d["src"] = "unrecognisable_video"
            elif key in MANUAL:
                mv = MANUAL[key]["verdict"]; d["src"] = "manual_" + mv
                if mv == "absent":
                    penalty = "absent"; cp = cs
                elif mv in ("as_source", "as_gt"):
                    # seen by eye: the object clearly does what it does in the source (or in the GT) but no tracker holds
                    cp = (cs if mv == "as_source" else cg).copy()
                elif mv == "exclude":
                    cp = "skip"; d["why"] = "manual_exclude"
                elif mv == "ct":
                    cp = np.median(p[t0:tc, idx], axis=1)
                elif mv in ("sam2", "s2"):
                    srcd = man if mv == "sam2" else s2
                    raw = srcd[f"{m}|{nm}_c"][t0:tc] if f"{m}|{nm}_c" in srcd else None
                    okr = np.isfinite(raw).all(1) if raw is not None else np.zeros(1, bool)
                    k0 = int(np.argmax(okr)) if okr.any() else -1
                    if 2 < k0 < len(raw) - 4:
                        # the object only shows up later in the prediction (seen by eye): measured from then on, against
                        # the GT and the source from the same frame, as for re-seeded objects
                        cs, cg = cs[k0:], cg[k0:]; raw = raw[k0:]; d["t_found"] = t0 + k0
                    P_ = fill(raw) if raw is not None and k0 >= 0 else None
                    cp = P_ if P_ is not None else "skip"
            if cp is None and ok_box:
                if o["role"] == "both":
                    disp_s = np.linalg.norm(cs - cs[0], axis=-1); disp_g = np.linalg.norm(cg - cg[0], axis=-1)
                    bg = None
                    if disp_s.max() / 2 > 2.5 * rr:
                        bg = fr("source", int(np.argmax(disp_s)) + t0)
                    elif disp_g.max() / 2 > 2.5 * rr:
                        bg = fr("gt", int(np.argmax(disp_g)) + t0)
                    n_obj = ncc(fr(m, t0), fr("gt", t0), box); n_bg = ncc(fr(m, t0), bg, box) if bg is not None else None
                    nref = ncc(fr("ref_gt_degraded", t0), fr("gt", t0), box)
                    d["n_obj"] = n_obj
                    if n_bg is not None and n_obj is not None and n_bg >= 0.5 and n_bg > n_obj + 0.15 and nref is not None and nref >= 0.5:
                        d["absent_t0"] = True
                        tf = int(rs[f"{m}|{nm}_t"]) if f"{m}|{nm}_t" in rs else -1
                        if t0 < tf < tc - 4:
                            R_ = rs[f"{m}|{nm}_xy"][tf:tc]
                            spr = float(np.median(np.linalg.norm(R_ - np.median(R_, axis=1, keepdims=True), axis=-1)))
                            G_ = gt[tf:tc][:, idx]; spg = float(np.median(np.linalg.norm(G_ - np.median(G_, axis=1, keepdims=True), axis=-1)))
                            if spr <= max(2 * spg, spg + 0.5 * o["r_px"]):
                                cp = np.median(R_, axis=1); cs, cg = cs[tf - t0:], cg[tf - t0:]; d["src"] = "reseed"; d["t_found"] = tf
                                if quantities(cs)["path"] > 50 and quantities(cp)["path"] < 0.1 * quantities(cs)["path"]:
                                    cp = "skip"; d["why"] = "reseed_stuck"     # found again, but the track then does not move
                            else:
                                cp = "skip"; d["why"] = "reseed_spread"
                        else:
                            cp = np.median(p[t0:tc, idx], axis=1); d["src"] = "ct"   # where the object should be: measured as it is
                            if not is_target(nm):
                                penalty = "missing"
                else:
                    nsg = ncc(fr("source", t0), fr("gt", t0), box)
                    if nsg is not None and 1 - nsg > 0.2:
                        dsg = 1 - nsg; dps = 1 - (ncc(fr(m, t0), fr("source", t0), box) or 0); dpg = 1 - (ncc(fr(m, t0), fr("gt", t0), box) or 0)
                        cap = (dps ** 2 - dpg ** 2 + dsg ** 2) / (2 * dsg ** 2) < 0.5
            if cp is None:
                # try every valid tracker on the prediction
                passed, whys = {}, []
                qs_, qg_ = quantities(cs), quantities(cg)
                moving = min(qs_["path"], qg_["path"]) > 50
                for trk in I["cands"]:
                    if trk == "ct":
                        x = p[t0:tc, idx]; g_ = gt[t0:tc, idx]
                        sp = float(np.median(np.linalg.norm(x - np.median(x, axis=1, keepdims=True), axis=-1)))
                        sg = float(np.median(np.linalg.norm(g_ - np.median(g_, axis=1, keepdims=True), axis=-1)))
                        if sp > max(2 * sg, sg + 0.5 * o["r_px"]):
                            whys.append("ct_spread"); continue
                        c = np.median(x, axis=1)
                    else:
                        cc = s2.get(f"{m}|{nm}_c"); aa = s2.get(f"{m}|{nm}_a"); ag = s2.get(f"gt|{nm}_a")
                        if cc is None:
                            whys.append("s2_missing"); continue
                        c = fill(cc[t0:tc])
                        if c is None:
                            whys.append("s2_empty"); continue
                        aP = aa[t0:tc]; vis = ag[t0:tc] > 0 if ag is not None else np.ones(tc - t0, bool)
                        a0 = aP[0] if aP[0] > 0 else (np.median(aP[aP > 0]) if (aP > 0).any() else 0)
                        okc = np.isfinite(cc[t0:tc]).all(1)
                        last = cc[t0:tc][okc][-1] / 2.0 if okc.any() else None
                        left_frame = last is not None and (min(last[0], 640 - last[0], last[1], 360 - last[1]) < 1.5 * rr) and okc[:max(1, okc.sum())].all()   # mask ends at the image border: the object drove off-screen
                        persist = vis.any() and ((aP[vis] > 0).mean() >= 0.85 or left_frame)
                        if not persist or a0 <= 0 or not (1 / 6 <= np.median(aP[aP > 0]) / a0 <= 6):
                            whys.append("s2_mask"); continue
                    qp_ = quantities(c)
                    # a (nearly) motionless track while the source object moves: either the object really stays put
                    # (pixels at its start position unchanged, and the object was there) or the tracker is stuck
                    if qs_["path"] > 50 and qp_["path"] < 0.1 * qs_["path"] and o["role"] == "both" and ok_box:
                        tl_ = int(np.argmax(np.linalg.norm(cs - cs[0], axis=-1))) + t0
                        same = ncc(fr(m, t0), fr(m, min(tl_, tc - 1)), box)
                        if same is not None and same >= 0.7 and (d.get("n_obj") or 0) >= 0.5:
                            passed[trk] = (c, "frozen" if moving else None)
                        else:
                            whys.append(f"{trk}_stuck")
                        continue
                    passed[trk] = (c, None)
                if len(passed) == 2:
                    (c1, p1), (c2, p2) = passed["ct"], passed["s2"]
                    gap = float(np.percentile(np.linalg.norm((c1 - c1[0]) - (c2 - c2[0]), axis=-1), 75)); d["gap"] = round(gap, 1)
                    pth = {k: quantities(v[0])["path"] for k, v in passed.items()}
                    still = [k for k in pth if pth[k] < 0.25 * max(pth.values())]
                    if gap > max(24.0, o["r_px"]) and len(still) == 1 and ok_box:
                        # one track barely moves, the other does: did the object leave its start position? (pixels)
                        moving_k = next(k for k in pth if k not in still)
                        tl_ = int(np.argmax(np.linalg.norm(passed[moving_k][0] - passed[moving_k][0][0], axis=-1))) + t0
                        same = ncc(fr(m, t0), fr(m, min(tl_, tc - 1)), box)
                        if same is not None:
                            keep = still[0] if same >= 0.7 else moving_k
                            passed = {keep: passed[keep]}; d["why"] = "disagree_resolved_by_pixels"; gap = 0.0
                    if gap > max(24.0, o["r_px"]):
                        # tie-break: which track keeps sitting on something that looks like the object at its start
                        cons = {}
                        for trk, (c, _) in passed.items():
                            vals = []
                            b0 = boxat(c[0], rr)
                            for tt in range(0, len(c), 8):
                                vv = ncc(fr(m, t0), fr(m, t0 + tt), b0, boxat(c[tt], rr))
                                if vv is not None:
                                    vals.append(vv)
                            cons[trk] = float(np.median(vals)) if vals else -1
                        d["cons"] = {k: round(v, 2) for k, v in cons.items()}
                        if abs(cons["ct"] - cons["s2"]) >= 0.1:
                            keep = max(cons, key=cons.get); passed = {keep: passed[keep]}; d["why"] = "disagree_resolved"
                        else:
                            passed = {}; whys.append("trackers_disagree")
                if not passed and ok_box and o["role"] == "both" and (d.get("n_obj") or 0) >= 0.5:
                    # no tracker held, but the object sits at its start position and the pixels there never change:
                    # a genuinely static object (thin/transparent ones defeat both trackers) -> constant trajectory
                    sims = [ncc(fr(m, t0), fr(m, t0 + tt), box) for tt in range(4, tc - t0, 8)]
                    if sims and all(s_ is not None and s_ >= 0.7 for s_ in sims):
                        c = np.repeat(cs[:1] * 0 + np.median(src[t0, idx], axis=0)[None], len(cs), 0)
                        frozen_ = moving and o["role"] == "both"
                        passed["static"] = (c, "frozen" if frozen_ else None); whys.append("static_confirmed")
                if passed:
                    trk = R if R in passed else next(iter(passed))
                    cp, penalty = passed[trk]; d["src"] = "s2" if trk == "m2" else trk
                else:
                    d["why"] = ",".join(whys) or d.get("why")
            if cp is None or isinstance(cp, str):
                d["src"] = "excluded"; detail.append(d)
                todo.append({"name": name, "model": m, "obj": nm, "why": d.get("why")})
                continue
            cs_s, cg_s, cp_s = smooth1(cs), smooth1(cg), smooth1(cp[:len(cs)])
            if DUMPTRACK and (DUMPTRACK_REFS or m not in REFS):
                ts0 = d.get("t_found", t0)
                dumptr[f"{m}|{nm}|p"] = np.asarray(cp[:len(cs)], np.float32); dumptr[f"{m}|{nm}|s"] = np.asarray(cs, np.float32)
                dumptr[f"{m}|{nm}|g"] = np.asarray(cg, np.float32); dumptr[f"{m}|{nm}|t"] = np.int32(ts0)
            qs, qg, qp = quantities(cs_s), quantities(cg_s), quantities(cp_s)
            d["keys"] = {}
            for k in qs:
                dG = np.asarray(qg[k] - qs[k], float); dP = np.asarray(qp[k] - qs[k], float); mag = float(np.linalg.norm(dG))
                thr = BASE[k] if k == "stop" else max(max(BASE["end"], 0.10 * qs["path"]) if k == "path" else BASE[k], 3 * noise)
                if mag <= thr:
                    continue
                if m not in REFS and "t_found" not in d:
                    # the measurement itself must reproduce this change: the degraded copy of the GT video has to show
                    # it (>= 0.5) and the degraded copy of the source must not (|.| < 0.5); else the key is noise
                    rgk, rsk = refkey.get(("ref_gt_degraded", nm, k)), refkey.get(("ref_source_degraded", nm, k))
                    if (rgk is not None and rgk < 0.5) or (rsk is not None and abs(rsk) >= 0.5):
                        d.setdefault("keys_dropped", []).append(k); continue
                nkey += 1
                proj = float(np.dot(dP.ravel(), dG.ravel()) / mag ** 2)
                if OVERSHOOT == "soft" and proj > 1:
                    proj = max(0.0, 2.0 - proj)          # going beyond the GT change is not the right physics either
                s = -1.0 if penalty else float(np.clip(proj, -1, 1))
                s = min(s, 0.0) if cap else s
                if m in REFS:
                    refkey[(m, nm, k)] = s; refk[m][(nm, k)] = s
                sc.append(s); d["keys"][k] = [round(mag, 1), round(s, 3), round(thr, 1)]
            # the same region's shape (position-free): same penalties, cap and hand verdict as its position
            own_mask = d.get("src") in ("s2", "manual_sam2", "manual_s2") or m in REFS
            ss_ = shape_keys(m, o, t0, tc, True, penalty, cap, mv0, d, track=None if own_mask else cp[:len(cs)],
                             t_start=d.get("t_found"))
            sc += ss_; nkey += len(ss_)
            d["penalty"], d["cap"], d["R"] = penalty, cap, R
            if m not in REFS or DUMPREF:
                detail.append(d)
        if zl and LIQ.get(scene, {}).get("mode") != "body":
            # the liquid region of the case (pour / spill scenes; a body of still water only ripples, its physics shows
            # in the solids in it). A prediction whose frame 0 is far off and that no alignment fixed: the fixed liquid
            # region would not line up -> no liquid keys for it
            cq = zl.get(f"{m}|cam")
            if m not in REFS and (name, m) not in UNRECOGNIZABLE and MIS0.get((name, m), 0) > 30 and f"{m}_W" not in cam and not (cq is not None and cq[2]):
                detail.append({"model": m, "obj": "liquid", "src": "camera_suspect"})
            else:
                lk = liquid_keys(name, zl, m, tc, detail, refk.get(m))
                sc += lk; nkey += len(lk)
        for nm, G in ADDED.get(name, {}).items():
            # ADD edits: is the added object there, at its GT place (added_targets.json)
            d = {"model": m, "obj": nm, "role": "added", "kind": "presence"}
            gs = presence_key(m, nm, G, tc, "appeared", True, d)
            if gs is not None:
                d["src"] = "appear_check"; sc.append(gs); nkey += 1
                if m not in REFS or DUMPREF:
                    detail.append(d)
        if nkey:
            out["s"][m] = {"kq": float(np.mean(sc)), "nkey": nkey}
    ref_validity(out, refk)
    if DUMPTRACK and dumptr:
        (T / DUMPTRACK_DIR).mkdir(exist_ok=True)
        np.savez_compressed(T / DUMPTRACK_DIR / f"{name}.npz", **dumptr)
    return out, detail, todo


if __name__ == "__main__":
    meta = {}
    for l in open(REL / "metadata.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r.get("source_case_id"):
            meta["sim__" + r["id"].replace("/", "__")] = r
    names = [f.stem for f in sorted((T / "seed_tracks").glob("*.npz")) if (T / "seed_tracks_mild" / f.name).exists()]
    if os.environ.get("ONLY"):
        names = [n for n in names if n in os.environ["ONLY"].split(",")]
    seen = set(names)       # + cases where only liquid moves (no GT-tracked object), scored from the liquid region
    names += [f.stem for f in sorted((T / "liquid_tracks").glob("*.npz")) if f.stem not in seen and f.stem in meta]
    if os.environ.get("ONLY"):
        names = [nm for nm in names if any(o in nm for o in os.environ["ONLY"].split(","))]
    with Pool(int(os.environ.get("NPROC", "32"))) as pool:
        res = pool.map(do_case, [(nm, meta[nm]) for nm in names], chunksize=1)
    rows = [r for r, _, _ in res]; detail = {r["name"]: d for r, d, _ in res}; todo = [t for _, _, ts in res for t in ts]
    json.dump(rows, open(T / f"cf_sim{SUF}.json", "w")); json.dump(detail, open(T / f"cf_sim_detail{SUF}.json", "w"))
    json.dump(todo, open(T / f"cf_sim_todo{SUF}.json", "w"), indent=0)
    valid = [r for r in rows if r["valid"]]
    print(f"sim cases tracked {len(rows)}, with key quantities {sum('ref_gt_degraded' in r['s'] for r in rows)}, valid {len(valid)}")
    print(f"{'':16s}{'refGT':>7s}{'refSrc':>7s}" + "".join(f"{s:>12s}" for s in SHORT))
    for lab, kd in [("ALL", None), ("SET", "SET"), ("DELETE", "DELETE"), ("ADD", "ADD")] + [(c, c) for c in ("rigid_rigid", "rigid_elastic", "rigid_fluid", "elastic_fluid", "elastic_elastic")]:
        sel = [r for r in valid if kd is None or r["kind"] == kd or r["category"] == kd]
        if not sel:
            continue
        mean = lambda m: np.mean([r["s"][m]["kq"] for r in sel if m in r["s"]]) if any(m in r["s"] for r in sel) else np.nan
        print(f"{lab:16s}{mean('ref_gt_degraded'):7.2f}{mean('ref_source_degraded'):7.2f}" + "".join(f"{mean(m):7.3f}({sum(m in r['s'] for r in sel):3d})" for m in MODELS))
    print("objects left for the hand check:", len(todo))
