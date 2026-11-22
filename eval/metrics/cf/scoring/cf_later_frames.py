# -*- coding: utf-8 -*-
"""Time-graded CF for edits that take effect at a later frame t (the execution frame).
Before t the target video equals the source video, so any change there moves a video away from the target. For every
scored object we sum how far the video departs from the source video over the frames before t, divide by how far the
target video departs from the source video over the frames from t on (the same sum), and subtract this share from each
of the object's scores (clipped to [-1, 1]):
  solid object             per-frame distance between the displacements from the object's own start (the verified CF
                           tracks of WORK/tracks_pre/), minus the tracker tolerance max(16 px, 0.6 r) as a dead zone;
                           the denominator is at least the tolerance per frame;
  object deleted mid-clip  per-frame presence (1 when the video no longer shows it): the frames before td in which it
                           is gone (hand count, later_frames_manual.json "absent_frames") over the 96 - td frames of the
                           target's change;
  liquid                   per-frame liquid area A vs the source, dead zone max(30, 10% of the source maximum), applied
                           only to videos whose liquid visibly departs before t (later_frames_manual.json "liquid_gate").
Objects already scored -1 (vanished, missing, frozen) stay at -1. Objects on which the re-encoded target copy itself
departs before t are not judged. Only the later-frame cases change; the video CF is again the mean over its quantities.
Inputs: WORK/cf_sim<SUFFIX_IN>.json and cf_sim_detail<SUFFIX_IN>.json (cf_sim.py with DUMPTRACK=1), the detail and
tracks of a cf_sim.py run on the later-frame cases with the reference copies included (DUMPREF=1 DUMPTRACK=1
DUMPTRACK_REFS=1 DUMPTRACK_DIR=tracks_pre, suffix REF_SUFFIX), later_frames.json {case: execution frame (1-based)},
later_frames_manual.json, timed_targets.json, liquid_tracks/, seeds/.
usage: cf_later_frames.py WORK SUFFIX_IN SUFFIX_OUT [REF_SUFFIX]
  -> WORK/cf_sim<SUFFIX_OUT>.json, cf_sim_detail<SUFFIX_OUT>.json, later_frames_log<SUFFIX_OUT>.json"""
import json, sys
from pathlib import Path
import numpy as np
T = Path(sys.argv[1]); SIN, SOUT = sys.argv[2], sys.argv[3]; SREF = sys.argv[4] if len(sys.argv) > 4 else "_later"
FR = json.load(open(T / "later_frames.json"))
MAN = json.load(open(T / "later_frames_manual.json")) if (T / "later_frames_manual.json").exists() else {}
TIMED = json.load(open(T / "timed_targets.json")) if (T / "timed_targets.json").exists() else {}
rows = json.load(open(T / f"cf_sim{SIN}.json")); det = json.load(open(T / f"cf_sim_detail{SIN}.json"))
det_ref = json.load(open(T / f"cf_sim_detail{SREF}.json"))       # run with the reference copies' entries (DUMPREF=1)
REFS = ("ref_gt_degraded", "ref_source_degraded")
KER = np.ones(5) / 5


def smooth1(c):
    pad = np.concatenate([c[:1].repeat(2, 0), c, c[-1:].repeat(2, 0)])
    return np.stack([np.convolve(pad[:, d], KER, "valid") for d in range(2)], -1)


def disp(a):
    a = smooth1(np.asarray(a, float)); return a - a[0]


def motion_pen(z, m, ob, t_ex, tol):
    if f"{m}|{ob}|p" not in z:
        return None
    t0 = int(z[f"{m}|{ob}|t"]); p, s = z[f"{m}|{ob}|p"], z[f"{m}|{ob}|s"]
    n_pre = min(len(p), len(s), t_ex - t0)
    if n_pre <= 0:
        return 0.0
    e = np.linalg.norm(disp(p[:len(s)]) - disp(s[:len(p)]), axis=-1)[:n_pre]
    num = float(np.maximum(0.0, e - tol).sum())
    rk = "ref_gt_degraded" if f"ref_gt_degraded|{ob}|s" in z else m        # full-length window for the target's change
    tr, sr, gr = int(z[f"{rk}|{ob}|t"]), z[f"{rk}|{ob}|s"], z[f"{rk}|{ob}|g"]
    dg = np.linalg.norm(disp(gr) - disp(sr), axis=-1)[max(0, t_ex - tr):]
    den = max(float(dg.sum()), tol * max(1, len(dg)))
    return num / den


def liquid_pen(zl, m, t_ex):
    if f"{m}|liquid_A" not in zl:
        return None
    A = lambda v: np.nan_to_num(np.asarray(zl[f"{v}|liquid_A"], float))
    f0 = max(1, int(zl.get(f"{m}|liquid_ref0", 1)), int(zl.get("source|liquid_ref0", 1)))
    ap, a_s, ag = A(m), A("source"), A("gt")
    thr = max(30.0, 0.10 * float(a_s.max()))
    num = float(np.maximum(0.0, np.abs(ap[f0:t_ex] - a_s[f0:t_ex]) - thr).sum())
    den = max(float(np.abs(ag[t_ex:] - a_s[t_ex:]).sum()), thr * max(1, 96 - t_ex))
    return num / den


def adjust(d, pen):
    if not pen or not d.get("keys") or d.get("penalty") in ("missing", "absent", "frozen", "liquid_frozen"):
        return
    d["pre_pen"] = round(pen, 4)
    for k, v in d["keys"].items():
        v[1] = round(float(np.clip(v[1] - pen, -1, 1)), 4)


log = []
pen_videos = set()
for name, frame in FR.items():
    t_ex = int(frame) - 1
    z = dict(np.load(T / "tracks_pre" / f"{name}.npz")) if (T / "tracks_pre" / f"{name}.npz").exists() else {}
    zl = dict(np.load(T / "liquid_tracks" / f"{name}.npz")) if (T / "liquid_tracks" / f"{name}.npz").exists() else {}
    rpx = {o["name"]: o["r_px"] for o in json.load(open(T / "seeds" / f"{name}.json"))["objects"]} if (T / "seeds" / f"{name}.json").exists() else {}
    gate = MAN.get("liquid_gate", {}).get(name, {}); absent = MAN.get("absent_frames", {}).get(name, {})
    unjudged = set()
    for d in det_ref.get(name, []):
        if d["model"] == "ref_gt_degraded" and d.get("src") not in ("gone_check", "liquid_region") and d["obj"] != "liquid":
            rp = motion_pen(z, "ref_gt_degraded", d["obj"], t_ex, max(16.0, 0.6 * rpx.get(d["obj"], 20.0)))
            if rp and rp > 0.005:
                unjudged.add(d["obj"]); log.append(("UNJUDGED", name, "ref_gt_degraded", d["obj"], round(rp, 3)))
    for src_det, is_ref in ((det, False), (det_ref, True)):
        for d in src_det.get(name, []):
            m, ob = d["model"], d["obj"]
            if (m in REFS) != is_ref:
                continue
            if d.get("src") == "gone_check":
                td = TIMED[name][ob]["td"]; pen = absent.get(m, 0) / float(96 - td) if not is_ref else 0.0
            elif d.get("src") == "liquid_region" or ob == "liquid":
                pen = liquid_pen(zl, m, t_ex) if (m in gate) else 0.0
            elif ob in unjudged:
                pen = 0.0
            else:
                pen = motion_pen(z, m, ob, t_ex, max(16.0, 0.6 * rpx.get(ob, 20.0)))
            if is_ref:
                if pen:
                    log.append(("REF", name, m, ob, round(pen, 3)))
                continue
            adjust(d, pen)
            if d.get("pre_pen"):
                log.append(("pen", name, m, ob, round(pen, 3))); pen_videos.add((name, m))
# video CF = mean over its scored quantities
changed = 0
for r in rows:
    if r["name"] not in FR:
        continue
    for m, v in r["s"].items():
        if m in REFS or (r["name"], m) not in pen_videos:
            continue
        ks = [x[1] for d in det.get(r["name"], []) if d["model"] == m for x in d.get("keys", {}).values()]
        if ks:
            new = float(np.mean(ks))
            if abs(new - v["kq"]) > 1e-9:
                changed += 1; v["kq_unadjusted"] = v["kq"]; v["kq"] = new
json.dump(rows, open(T / f"cf_sim{SOUT}.json", "w")); json.dump(det, open(T / f"cf_sim_detail{SOUT}.json", "w"))
json.dump(log, open(T / f"later_frames_log{SOUT}.json", "w"), indent=0)
refpen = [l for l in log if l[0] in ("REF", "UNJUDGED")]
print("videos changed", changed, "| object penalties", sum(1 for l in log if l[0] == "pen"), "| reference copies with a penalty", len(refpen))
for l in sorted(refpen, key=lambda l: -l[4])[:10]:
    print("  ", l)
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"]
old = {r["name"]: r for r in json.load(open(T / f"cf_sim{SIN}.json"))}
for m in MODELS:
    a = [old[r["name"]]["s"][m]["kq"] for r in rows if r.get("valid") and m in r["s"]]
    b = [r["s"][m]["kq"] for r in rows if r.get("valid") and m in r["s"]]
    print("%-18s sim valid %3d  CF %.3f -> %.3f" % (m, len(b), np.mean(a), np.mean(b)))
