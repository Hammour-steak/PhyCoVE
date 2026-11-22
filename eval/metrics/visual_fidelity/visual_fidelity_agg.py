# -*- coding: utf-8 -*-
"""Aggregate visual_fidelity.py: per-video PSNR / SSIM / LPIPS rows, the source-video ("no edit") reference per case,
and FVD per model (I3D features of the model's videos vs the ground-truth videos of the same cases, compared on the
same frames), plus FVD of the source videos vs the ground truth over all cases.   -> WORK/quality_summary<OUTSUF>.json
usage: visual_fidelity_agg.py WORK [OUTSUF]"""
import json, sys
from pathlib import Path
import numpy as np
T = Path(sys.argv[1]); OUTSUF = sys.argv[2] if len(sys.argv) > 2 else ""


def sqrtm(m):
    v, U = np.linalg.eigh(m)
    return (U * np.sqrt(np.clip(v, 0, None))) @ U.T


def fd(a, b):
    ma, mb = a.mean(0), b.mean(0); ca, cb = np.cov(a, rowvar=False), np.cov(b, rowvar=False)
    sa = sqrtm(ca)
    return float((ma - mb) @ (ma - mb) + np.trace(ca) + np.trace(cb) - 2 * np.trace(sqrtm(sa @ cb @ sa)))


rows, src_rows, F = [], [], {}
for p in sorted((T / f"quality_out{OUTSUF}").glob("*.json")):
    name = p.stem; split, scene, case = name.split("__")
    R = json.load(open(p)); z = np.load(T / f"quality_feat{OUTSUF}" / f"{name}.npz")
    for m, v in R.items():
        rec = {"split": split, "scene": scene, "case": case, "psnr": v["psnr"], "ssim": v["ssim"], "lpips": v["lpips"], "frames": v["frames"]}
        if m == "source":
            src_rows.append(rec)
        else:
            rec["model"] = m; rows.append(rec)
        F.setdefault(m, {"pred": [], "gt": []})
        F[m]["pred"].append(z[m]); F[m]["gt"].append(z[f"gt_{v['frames']}"])
fvd = {m: {"fvd": fd(np.stack(f["pred"]), np.stack(f["gt"])), "videos": len(f["pred"])} for m, f in F.items()}
json.dump({"videos": rows, "source": src_rows, "fvd": fvd}, open(T / f"quality_summary{OUTSUF}.json", "w"), indent=1)
print(len(rows), "videos,", len(src_rows), "cases")
for m in sorted({r["model"] for r in rows}) + ["source"]:
    rs = src_rows if m == "source" else [r for r in rows if r["model"] == m]
    ps = np.array([r["psnr"] for r in rs]); ps = ps[np.isfinite(ps)]
    print(f"{m:18s} n={len(rs):4d} PSNR {ps.mean():6.2f} SSIM {np.mean([r['ssim'] for r in rs]):.3f} LPIPS {np.mean([r['lpips'] for r in rs]):.3f} FVD {fvd[m]['fvd']:8.1f}")
