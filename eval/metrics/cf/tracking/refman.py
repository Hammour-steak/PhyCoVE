# -*- coding: utf-8 -*-
"""Objects no tracker followed on the clean renders (validation failed: "reference_track_bad"), in cases that are
otherwise not measurable (listed in C). SAM 2 on source / target / both degraded copies, prompted from the TRUE 3D
position: a box of the projected radius at the first visible frame plus a point every 12 frames; objects listed in
BOXALL get a box + point every 6 frames (used where SAM 2 drifted, together with ONLYS = the scenes to redo).
  mode jobs:     -> WORK/sam2_jobs_refman.json   (run cf/tracking/track_sam2.py with KEYS=cas OUTDIR=sam2_refman)
  mode validate: p75 displacement error vs the projected 3D origin (1280 px), tol = max(16, 0.6 r_px)
                 -> WORK/validation_m2.json {name: {obj: {m2_src, m2_gt, m2_rgt, m2_rsrc, tol}}} (merged into an
                 existing file)
usage: refman.py WORK jobs|validate   (environment: PHYCOVE_ROOT; BOXALL, ONLYS as above)"""
import json, os, sys
from pathlib import Path
import numpy as np
T = Path(sys.argv[1]); MODE = sys.argv[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
import traj_lib as tl
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
C = {"bathroom_stool_rebound": (["edit_fast_spin", "edit_frictionless_floor_timed", "edit_remove_bathtub"], ["stool"]),
     "bathroom_tennis_throw": (["edit_aim_north", "edit_aim_south"], ["tennis_ball"]),
     "coffee_ice_drop": (["edit_delete_coffee", "edit_low_density_coffee"], ["ice"]),
     "metro_security_bag_curtain": (["edit_belt_speed_x2", "edit_delete_curtain", "edit_friction_x0p02", "edit_young_modulus_x100"], ["bag"]),
     "office_desk_kettle_tip": (["edit_heavy_kettle"], ["kettle", "pen"]),
     "pot_lid_drop": (["edit_zero_gravity_timed"], ["lid"]),
     "silicone_bag_can": (["edit_bag_young_x5"], ["metal_can"]),
     "toy_boat_pool_glide": (["edit_heavy_boat", "edit_light_water"], ["toy_tug"])}


def truth(scene, case, ob):
    base = tl.load_gt(REL / f"scenes/{scene}/cases/source/ground_truth_transforms.json")
    edit = tl.load_gt(REL / f"scenes/{scene}/cases/{case}/ground_truth_transforms.json")
    res = base["camera"]["resolution"]; sx, sy = 640.0 / res[0], 360.0 / res[1]
    out = {}
    for key, gtd, cf in (("source", base, None), ("gt", edit, base)):
        od = tl.normalise(gtd)
        if ob not in od:
            continue
        uv, pres, rad = tl.projected_track(gtd, ob, od, camera_from=cf)
        uv = np.asarray(uv, float) * [sx, sy]; uv[~np.asarray(pres, bool)] = np.nan
        out[key] = (uv, np.asarray(rad, float) * sx)
    return out


BOXALL = set(os.environ.get("BOXALL", "").split(",")) - {""}
ONLYS = set(os.environ.get("ONLYS", "").split(",")) - {""}
if ONLYS:
    C = {k: v for k, v in C.items() if k in ONLYS}
if MODE == "jobs":
    jobs = []
    for scene, (cases, obs) in C.items():
        for case in cases:
            name = f"sim__{scene}__{case}"
            vids = {"source": str(REL / f"scenes/{scene}/cases/source/video.mp4"), "gt": str(REL / f"scenes/{scene}/cases/{case}/video.mp4")}
            vids["ref_source_degraded"] = vids["source"]; vids["ref_gt_degraded"] = vids["gt"]
            objs = []
            for ob in obs:
                tr = truth(scene, case, ob)
                for v in vids:
                    key = "gt" if v in ("gt", "ref_gt_degraded") else "source"
                    if key not in tr:
                        continue
                    uv, rad = tr[key]; fin = np.where(np.isfinite(uv).all(1))[0]
                    if len(fin) == 0:
                        continue
                    t1 = int(fin[0]); r = float(max(np.nanmedian(rad[fin]), 6.0))
                    pr = [{"t": t1, "pos": [[round(float(uv[t1][0]), 1), round(float(uv[t1][1]), 1)]], "neg": [],
                           "box": [round(float(uv[t1][0] - r), 1), round(float(uv[t1][1] - r), 1), round(float(uv[t1][0] + r), 1), round(float(uv[t1][1] + r), 1)]}]
                    step = 6 if ob in BOXALL else 12      # BOXALL objects: box + point every 6 frames
                    bx = lambda t: [round(float(uv[t][0] - r), 1), round(float(uv[t][1] - r), 1), round(float(uv[t][0] + r), 1), round(float(uv[t][1] + r), 1)] if ob in BOXALL else None
                    pr += [{"t": int(t), "pos": [[round(float(uv[t][0]), 1), round(float(uv[t][1]), 1)]], "neg": [], "box": bx(t)}
                           for t in range(t1 + step, 96, step) if np.isfinite(uv[t]).all() and 0 <= uv[t][0] < 640 and 0 <= uv[t][1] < 360]
                    objs.append({"obj": ob, "video": v, "prompts": pr})
            jobs.append({"name": name, "suffix": "__refman", "videos": vids, "objects": objs})
    json.dump(jobs, open(T / "sam2_jobs_refman.json", "w"), indent=0)
    print(len(jobs), "jobs", sum(len(j["objects"]) for j in jobs), "object-videos")
else:
    seeds_r = {}
    out = {}
    for scene, (cases, obs) in C.items():
        for case in cases:
            name = f"sim__{scene}__{case}"
            z = dict(np.load(T / "sam2_refman" / f"{name}__refman.npz"))
            rp = {o["name"]: o["r_px"] for o in json.load(open(T / "seeds" / f"{name}.json"))["objects"]}
            for ob in obs:
                tr = truth(scene, case, ob); res = {"tol": max(16.0, 0.6 * rp.get(ob, 30))}
                for v, short, key in (("source", "m2_src", "source"), ("gt", "m2_gt", "gt"), ("ref_gt_degraded", "m2_rgt", "gt"), ("ref_source_degraded", "m2_rsrc", "source")):
                    c = z.get(f"{v}|{ob}_c")
                    if c is None or key not in tr:
                        res[short] = None; continue
                    g = tr[key][0] * 2.0                        # 1280 px like the _c centroids
                    ok = np.isfinite(c).all(1) & np.isfinite(g).all(1)
                    if ok.sum() < 8:
                        res[short] = None; continue
                    i0 = np.where(ok)[0][0]
                    e = np.linalg.norm((c[ok] - c[i0]) - (g[ok] - g[i0]), axis=1)
                    res[short] = round(float(np.percentile(e, 75)), 1)
                out.setdefault(name, {})[ob] = res
                print(name[5:60], ob, res)
    old = json.load(open(T / "validation_m2.json")) if (T / "validation_m2.json").exists() else {}
    old.update(out)
    json.dump(old, open(T / "validation_m2.json", "w"), indent=1)
