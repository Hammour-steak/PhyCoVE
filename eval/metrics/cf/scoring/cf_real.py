# -*- coding: utf-8 -*-
"""Counterfactual Fidelity (CF) on the real-video cases (separate source and target takes, no 3D truth) with the rules
of the simulated cases (cf_sim.py): per object the same key quantities (end, path, x-range, lowest, highest, stop;
smoothed), the same thresholds (BASE, 10 % of the source path, 3x the measurement noise), the same
score (share of the GT change achieved, clip [-1, 1], soft overshoot) and the same per-key reference gate (the degraded
GT copy must score >= 0.5, the degraded source copy |.| < 0.5); DELETE targets get the "gone" key and ADD targets the
"appeared" key (prediction between the source and GT looks at the object's place, mapped so degraded source = 0 and
degraded GT = 1, gap >= 0.5), and an edit target that is not removed / added caps the case's other keys at 0; the two
water-stream edits get a flow key (share of the stream region that changes frame to frame). Case = mean of its keys;
valid if >= 1 key passes the gate.
Objects and references are annotated by hand (real_prompts.json -> SAM 2 on source / target / degraded copies, every
track checked against the video), predictions are tracked by SAM 2 from the source track's first box and checked by
hand (real_manual.json: absent / exclude verdicts, presence and flow verdicts). Positions are compared in absolute image
coordinates from the source start (falling or thrown objects enter the frame, so their first seen position is not a
common start); camera offsets between takes are not corrected. Seedance's 89-frame clips are stretched to 96, Kiwi's
81 frames compared over its own length.
usage: cf_real.py WORK SUFFIX  -> WORK/cf_real<SUFFIX>.json, scored tracks in WORK/real_tracks_used/
environment: PHYCOVE_ROOT, PRED_ROOT_REAL (see README); NPROC"""
import json, os, sys
from multiprocessing import Pool
from pathlib import Path
import cv2
import numpy as np
T = Path(sys.argv[1]); SUF = sys.argv[2]
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE")) / "real"
PRED = Path(os.environ.get("PRED_ROOT_REAL", "predictions/PhyCoVE/real/quantitative_en"))
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]
SHORT = {"joyai_video_edit": "JoyAI", "kiwi_edit": "Kiwi", "omniweaving": "OmniW", "kling4_0_video": "Kling", "seedance25": "Seedance",
         "wan3_0_video": "Wan3", "minimax_h3": "MiniMax", "void": "VOID"}
REFS = ["ref_gt_degraded", "ref_source_degraded"]
BASE = {"end": 10, "xrange": 10, "lowest": 8, "highest": 8, "stop": 4}
KER = np.ones(5) / 5
P = json.load(open(T / "real_prompts.json"))
VAL = json.load(open(T / "real_valid.json"))
MAN = json.load(open(T / "real_manual.json")) if (T / "real_manual.json").exists() else {}
REG = json.load(open(T / "real_regions.json")) if (T / "real_regions.json").exists() else {}
# tracks are compared in ABSOLUTE image position from the source start. Camera offsets between the target take, the
# predictions and the source (a few px) and background differences are not corrected: they are noise every model has;
# a re-framed prediction then reads as objects that moved, as for the simulated cases.


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


def quantities(c, o=None):
    c = c - (c[0] if o is None else o)
    v = np.linalg.norm(np.diff(c, axis=0), axis=-1); stop = len(c) - 1
    for t in range(len(v) - 1, -1, -1):
        if v[t] >= 1.5:
            break
        stop = t
    return {"end": c[-1], "path": float(v.sum()), "xrange": float(np.ptp(c[:, 0])), "lowest": float(c[:, 1].max()),
            "highest": float(c[:, 1].min()), "stop": float(stop)}


def proj(qp, qs, qg, k):
    dG = np.asarray(qg[k] - qs[k], float); dP = np.asarray(qp[k] - qs[k], float); mag = float(np.linalg.norm(dG))
    p = float(np.dot(dP.ravel(), dG.ravel()) / mag ** 2)
    if p > 1:
        p = max(0.0, 2.0 - p)
    return float(np.clip(p, -1, 1)), mag


def frames(path, stretch=False):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(f)
    F = [cv2.resize(fr[int(round(k * fps / 24.0))], (640, 360), interpolation=cv2.INTER_AREA) for k in range(96) if int(round(k * fps / 24.0)) < len(fr)]
    if stretch and len(F) < 96:
        F = [F[int(round(t * (len(F) - 1) / 95.0))] for t in range(96)]
    return F


def degrade(f):
    g = cv2.resize(cv2.resize(f, (672, 384), interpolation=cv2.INTER_AREA), (640, 360), interpolation=cv2.INTER_LINEAR)
    ok, b = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, 75]); return cv2.imdecode(b, cv2.IMREAD_COLOR)


def stretch_track(a, n):
    """a prediction track on its own n-frame clock -> 96 frames (Seedance returns the 4 s clip in 89 frames)"""
    out = np.full((96,) + a.shape[1:], np.nan, np.float64); src = np.arange(n)
    for t in range(96):
        x = t * (n - 1) / 95.0; i = int(np.floor(x)); w = x - i
        if i + 1 < n and np.isfinite(a[i]).all() and np.isfinite(a[i + 1]).all():
            out[t] = (1 - w) * a[i] + w * a[i + 1]
        elif np.isfinite(a[min(int(round(x)), n - 1)]).all():
            out[t] = a[min(int(round(x)), n - 1)]
    return out


def lab(f):
    return cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2LAB).astype(np.float32), (5, 5), 0)


def look(Pf, Sf, Gf, box):
    """where the prediction's crop sits between the source and GT crops (0 = source look, 1 = GT look)"""
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(640, x1), min(360, y1)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    p, s, g = (lab(F)[y0:y1, x0:x1] for F in (Pf, Sf, Gf))
    dsg = float(np.mean(np.linalg.norm(s - g, axis=-1)))
    if dsg < 6:
        return None
    dps = float(np.mean(np.linalg.norm(p - s, axis=-1))); dpg = float(np.mean(np.linalg.norm(p - g, axis=-1)))
    return (dps ** 2 - dpg ** 2 + dsg ** 2) / (2 * dsg ** 2)


def do_case(d):
    sc, cs = d["scene"], d["case_id"]; name = f"real__{sc}__{cs}"
    kind = "DELETE" if d["edit_dsl"].startswith("DELETE") else "ADD" if d["edit_dsl"].startswith("ADD") else "SET"
    targets = [x.split()[1] for x in d["edit_dsl"].split(";") if x.strip().split()[0] in ("DELETE", "ADD")]
    zr = dict(np.load(T / "sam2_real" / f"{name}.npz")) if (T / "sam2_real" / f"{name}.npz").exists() else {}
    zp = dict(np.load(T / "sam2_realpred" / f"{name}.npz")) if (T / "sam2_realpred" / f"{name}.npz").exists() else {}
    srcP, gtP = P.get(f"{sc}__source", {}), P.get(f"{sc}__{cs}", {})
    out = {"name": name, "kind": kind, "s": {}, "keys": {}, "detail": []}
    # frames for the look / flow keys
    F = {"source": frames(REL / "scenes" / sc / "cases" / "source" / "video.mp4"), "gt": frames(REL / "scenes" / sc / "cases" / cs / "video.mp4")}
    F["ref_source_degraded"] = [degrade(f) for f in F["source"]]; F["ref_gt_degraded"] = [degrade(f) for f in F["gt"]]
    npred = {}
    for m in MODELS:
        vp = PRED / m / "videos" / sc / f"{cs}.mp4"
        if vp.exists():
            raw = frames(vp); npred[m] = len(raw)
            F[m] = frames(vp, stretch=(m == "seedance25"))

    def track(v, ob):
        z = zr if v in ("source", "gt") or v in REFS else zp
        c = None
        for nm in [ob] + sorted(k.split("|")[1][:-2] for k in z if k.startswith(f"{v}|{ob}~") and k.endswith("_c")):
            k = f"{v}|{nm}_c"
            if k in z:
                a = np.array(z[k], float)
                c = a if c is None else np.where(np.isfinite(c), c, a)
        if c is None:
            return None
        # same rule for every video: a frame where the mask jumped to / merged with another region is dropped (then
        # interpolated) when BOTH the centroid jumps (> half the object's size, min 8 px at 640, from the 5-frame
        # running median) AND the mask area changes > 2.5x vs the 7-frame running median (fast but intact motion,
        # e.g. a bouncing ball, keeps its area and is left alone)
        ss = z.get(f"{v}|{ob}_s")
        ok_ = np.where(np.isfinite(c).all(1) & np.isfinite(ss).all(1))[0] if ss is not None else np.zeros(0, int)
        if len(ok_) >= 5:
            size = float(np.median(np.maximum(ss[ok_, 4] - ss[ok_, 3], ss[ok_, 6] - ss[ok_, 5])))
            cc = c[ok_]; aa = ss[ok_, 0]
            med = np.stack([np.array([np.median(cc[max(0, i - 2):i + 3, d]) for i in range(len(cc))]) for d in range(2)], 1)
            am = np.array([np.median(aa[max(0, i - 3):i + 4]) for i in range(len(aa))])
            ar = aa / np.maximum(am, 1.0)
            bad = ok_[(np.linalg.norm(cc - med, axis=1) > 2.0 * max(0.5 * size, 8.0)) & ((ar > 2.5) | (ar < 0.4))]
            if len(bad):
                c = c.copy(); c[bad] = np.nan
        if v == "seedance25":
            c = stretch_track(c, npred.get(v, 89))
        rng = VAL.get(f"{sc}__source|{ob}") if v not in ("gt", "ref_gt_degraded") else VAL.get(f"{sc}__{cs}|{ob}")
        if rng:
            c = c.copy(); c[:rng[0]] = np.nan; c[rng[1] + 1:] = np.nan
        return c

    def box_of(v, ob, t):
        z = zr if v in ("source", "gt") or v in REFS else zp
        k = f"{v}|{ob}_s"
        if k not in z or t >= len(z[k]) or not np.isfinite(z[k][t]).all():
            return None
        _, _, _, x5, x95, y5, y95 = z[k][t]
        return (x5 - 4, y5 - 4, x95 + 4, y95 + 4)

    keys = {m: [] for m in MODELS + REFS}; dump = {}
    caps = {m: False for m in MODELS}
    # ---- presence keys: DELETE targets (gone) / ADD targets (appeared)
    for tg in targets:
        if tg in REG.get(f"{sc}__{cs}", {}):
            boxes = {t: REG[f"{sc}__{cs}"][tg] for t in range(8, 96, 2)}
        else:
            v0 = "gt" if kind == "ADD" else "source"
            boxes = {t: box_of(v0, tg, t) for t in range(8, 96, 2)}
            boxes = {t: b for t, b in boxes.items() if b is not None}
            rng = VAL.get(f"{sc}__source|{tg}")
            if rng:
                boxes = {t: b for t, b in boxes.items() if rng[0] <= t <= rng[1]}
        if boxes:
            # judge presence only where nothing else passes: frames where the take WITHOUT the target (GT for DELETE,
            # source for ADD) is unchanged at the target's place since frame 8 (another object landing or rolling
            # through there would otherwise mix "is the target there" with "where the other objects went")
            # first try frames quiet in BOTH takes (before anything happens at the target's place), then the take
            # without the target only (targets that are themselves moving, e.g. a ball rolling in)
            L8 = {v: lab(F[v][8]) for v in ("source", "gt")}

            def quiet_in(vs):
                out = {}
                for t, b in boxes.items():
                    x0, y0, x1, y1 = [int(v) for v in b]; x0, y0 = max(0, x0), max(0, y0)
                    if x1 - x0 < 6 or y1 - y0 < 6 or any(t >= len(F[v]) for v in vs):
                        continue
                    if all(float(np.mean(np.abs(lab(F[v][t])[y0:y1, x0:x1] - L8[v][y0:y1, x0:x1]))) < 6.0 for v in vs):
                        out[t] = b
                return out
            q2 = quiet_in(("source", "gt")); q1 = quiet_in(("source",) if kind == "ADD" else ("gt",))
            boxes = q2 if len(q2) >= 3 else q1 if len(q1) >= 3 else boxes
        if len(boxes) < 3:
            out["detail"].append({"obj": tg, "kind": "presence", "why": "no_box"}); continue
        raw = {}
        for m in MODELS + REFS:
            if m not in F:
                continue
            vals = [look(F[m][t], F["source"][t], F["gt"][t], b) for t, b in boxes.items() if t < len(F[m])]
            vals = [v for v in vals if v is not None]
            raw[m] = float(np.mean(vals)) if len(vals) >= 3 else None
        r0, r1 = raw.get("ref_source_degraded"), raw.get("ref_gt_degraded")
        if r0 is None or r1 is None or r1 - r0 < 0.5:
            out["detail"].append({"obj": tg, "kind": "presence", "why": "refs_not_apart", "r0": r0, "r1": r1}); continue
        for m in MODELS + REFS:
            if raw.get(m) is None:
                continue
            s = float(np.clip((raw[m] - r0) / (r1 - r0), 0, 1))
            mv = MAN.get(f"{name}|{m}|{tg}", {}).get("verdict") if m in MODELS else None
            if mv in ("present_as_source", "absent_as_gt"):
                s = 0.0 if mv == "present_as_source" else 1.0
            keys[m].append(("presence", tg, s))
            if m in MODELS and s < 0.5:
                caps[m] = True
            out["detail"].append({"obj": tg, "model": m, "kind": "gone" if kind == "DELETE" else "appeared", "raw": round(raw[m], 3), "s": round(s, 3)})
    # ---- flow keys (water-stream edits)
    for rk, box in REG.get(f"{sc}__{cs}", {}).items():
        if not rk.startswith("flow"):
            continue
        x0, y0, x1, y1 = box

        def flow(v):
            L = [lab(f)[y0:y1, x0:x1, 0] for f in F[v]]
            e = [float(np.mean(np.abs(L[t] - L[t - 1]) > 8)) for t in range(1, len(L))]
            e = np.array(e[11:]); return {"flow_mean": float(e.mean()), "flow_p90": float(np.percentile(e, 90))}
        qf = {v: flow(v) for v in ["source", "gt"] + REFS + [m for m in MODELS if m in F]}
        for k in ("flow_mean", "flow_p90"):
            dG = qf["gt"][k] - qf["source"][k]; noise = abs(qf["ref_gt_degraded"][k] - qf["gt"][k])
            if abs(dG) <= max(0.01, 3 * noise):
                continue
            sc_ = {v: (qf[v][k] - qf["source"][k]) / dG for v in qf}
            if sc_["ref_gt_degraded"] < 0.5 or abs(sc_["ref_source_degraded"]) >= 0.5:
                out["detail"].append({"obj": rk, "kind": "flow", "key": k, "why": "ref_gate"}); continue
            for v, p in sc_.items():
                if v in ("source", "gt"):
                    continue
                p = max(0.0, 2.0 - p) if p > 1 else p
                # frame-difference share is fooled by generation flicker and by smooth thick streams: the stream is
                # judged by eye where a verdict exists (absent_as_gt = changed as in the GT, present_as_source = not)
                fv = MAN.get(f"{name}|{v}|{rk}", {}).get("verdict") if v in MODELS else None
                if fv in ("absent_as_gt", "present_as_source"):
                    p = 1.0 if fv == "absent_as_gt" else 0.0
                keys[v].append(("flow", k, float(np.clip(p, -1, 1))))
    # ---- position keys of the objects present in both takes
    both = [ob for ob in srcP if "~" not in ob and ob in gtP and ob not in targets]
    for ob in both:
        cs0, cg0 = track("source", ob), track("gt", ob)
        if cs0 is None or cg0 is None:
            continue
        oks, okg = np.where(np.isfinite(cs0).all(1))[0], np.where(np.isfinite(cg0).all(1))[0]
        if len(oks) < 4 or len(okg) < 4:
            continue
        t0 = int(max(oks[0], okg[0]))
        # the object can leave the frame in one take (a thrown bottle flying off): compare only while it is seen in both
        t1 = int(min(oks[-1], okg[-1])) + 1
        ref = {v: track(v, ob) for v in REFS}
        for m in MODELS + REFS:
            if m in MODELS and m not in F:
                continue
            tc = 96 if m in REFS else (min(96, npred[m]) if m != "seedance25" else 96)
            tc = min(tc, t1)
            if tc - t0 < 8:
                continue
            d_ = {"obj": ob, "model": m, "t0": t0, "tc": tc}
            mv = MAN.get(f"{name}|{m}|{ob}", {}).get("verdict") if m in MODELS else None
            if mv == "exclude":
                d_["src"] = "manual_exclude"; out["detail"].append(d_); continue
            cs_, cg_ = fill(cs0[t0:tc]), fill(cg0[t0:tc])
            crs, crg = (fill(ref[v][t0:tc]) if ref[v] is not None else None for v in ("ref_source_degraded", "ref_gt_degraded"))
            if cs_ is None or cg_ is None:
                continue
            penalty = mv == "absent"
            raw = ref[m] if m in REFS else track(m, ob)
            if raw is None and not penalty:
                d_["src"] = "no_track"; out["detail"].append(d_); continue
            rw = raw[t0:tc] if raw is not None else np.full((tc - t0, 2), np.nan)
            okr = np.isfinite(rw).all(1)
            if not okr.any() and not penalty:
                d_["src"] = "no_mask"; out["detail"].append(d_); continue
            k0 = int(np.argmax(okr)) if okr.any() else 0
            a_s, a_g, a_rs, a_rg = cs_, cg_, crs, crg
            if 2 < k0 < len(rw) - 4:      # the object shows up later in the prediction: compare from that frame on
                a_s, a_g = cs_[k0:], cg_[k0:]; a_rs = crs[k0:] if crs is not None else None; a_rg = crg[k0:] if crg is not None else None
                rw = rw[k0:]; d_["t_found"] = t0 + k0
            cp = fill(rw) if okr.any() else a_s.copy()
            if cp is None and penalty:     # absent: a stray frame or two of a track must not drop the -1 keys
                cp = a_s.copy()
            if cp is None:
                continue
            S, G, Pp = smooth1(a_s), smooth1(a_g), smooth1(cp)
            ts_ = d_.get("t_found", t0)          # scored tracks (1280-px units), used by the Mask IoU jobs
            dump[f"{m}|{ob}|p"], dump[f"{m}|{ob}|s"], dump[f"{m}|{ob}|g"], dump[f"{m}|{ob}|t"] = cp, a_s, a_g, np.int32(ts_)
            noise =float(np.median(np.linalg.norm(smooth1(a_rg) - G, axis=-1))) if a_rg is not None else 0.0
            o = S[0]
            qs, qg, qp = quantities(S, o), quantities(G, o), quantities(Pp, o)
            qrs = quantities(smooth1(a_rs), o) if a_rs is not None else None; qrg = quantities(smooth1(a_rg), o) if a_rg is not None else None
            d_["keys"] = {}
            for k in qs:
                thr = BASE[k] if k == "stop" else max(max(BASE["end"], 0.10 * qs["path"]) if k == "path" else BASE[k], 3 * noise)
                s_, mag = proj(qp, qs, qg, k)
                if mag <= thr:
                    continue
                if qrg is not None and qrs is not None:
                    rg_, _ = proj(qrg, qs, qg, k); rs_, _ = proj(qrs, qs, qg, k)
                    if rg_ < 0.5 or abs(rs_) >= 0.5:
                        d_.setdefault("keys_dropped", []).append(k); continue
                s_ = -1.0 if penalty else s_
                if m in MODELS and caps[m]:
                    s_ = min(s_, 0.0)
                keys[m].append(("pos", f"{ob}:{k}", s_)); d_["keys"][k] = [round(mag, 1), round(s_, 3), round(thr, 1)]
            d_["src"] = "manual_absent" if penalty else "sam2"
            out["detail"].append(d_)
    for m, ks in keys.items():
        if ks:
            out["s"][m] = {"kq": float(np.mean([k[2] for k in ks])), "nkey": len(ks)}
            out["keys"][m] = [[a, b, round(c, 3)] for a, b, c in ks]
    out["valid"] = "ref_gt_degraded" in out["s"]
    (T / "real_tracks_used").mkdir(exist_ok=True)
    np.savez_compressed(T / "real_tracks_used" / f"{name}.npz", **dump)
    return out


if __name__ == "__main__":
    cases = [json.loads(l) for l in open(REL / "metadata.jsonl")]
    with Pool(int(os.environ.get("NPROC", "13"))) as pool:
        R = pool.map(do_case, cases)
    json.dump(R, open(T / f"cf_real{SUF}.json", "w"), indent=1)
    val = [r for r in R if r["valid"]]
    print(f"valid {len(val)} of {len(R)} edits")
    print(f"{'':8s}" + "".join(f"{x:>12s}" for x in ["refGT", "refSrc"] + [SHORT[m] for m in MODELS]))
    for kd in ("ALL", "DELETE", "ADD", "SET"):
        rs = [r for r in val if kd == "ALL" or r["kind"] == kd]
        line = f"{kd:8s}"
        for m in REFS + MODELS:
            v = [r["s"][m]["kq"] for r in rs if m in r["s"]]
            line += f"{np.mean(v):7.3f}({len(v):3d})".rjust(12) if v else f"{'nan':>12s}"
        print(line)
    print("objects without a track or mask:",sum(1 for r in R for d in r["detail"] if d.get("src") in ("no_track", "no_mask")))
