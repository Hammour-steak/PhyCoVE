"""Procedural inflatable float: two PVC sheets welded along a rounded edge, ribbed by weld lines, with a wavy seam flange
and fine puckers along the seam. The body is |z - z0(x, y)| < t(x, y) on a grid, so the same function gives the render
mesh, the Archimedes table and the inside test for the boundary particles. Body frame: long axis X, centred, Z up.
Writes float_mesh.npz (vertices, triangles, normals), float_field.npz (x, y, t, z0), float_collision.obj (convex hull),
float_manifest.json into assets/scenes/toy_car_float_bathtub/procedural_float/ (or --out). Needs numpy, scipy, scikit-image,
trimesh.
usage: <python> tools/make_float.py [--out DIR]"""
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import scene_asset
import argparse
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes


def plan_sd(x, y, hl, hw, r):
    """signed distance to a rounded rectangle (negative inside)"""
    qx, qy = np.abs(x) - (hl - r), np.abs(y) - (hw - r)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def outline(hl, hw, r, n=8000):
    """points along the plan outline and their arc length"""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    # superellipse-free construction: push each direction out to the rounded rectangle by bisection
    lo, hi = np.zeros(n), np.full(n, hl + hw)
    for _ in range(50):
        m = 0.5 * (lo + hi)
        inside = plan_sd(m * c, m * s, hl, hw, r) < 0
        lo, hi = np.where(inside, m, lo), np.where(inside, hi, m)
    p = np.stack([lo * c, lo * s], 1)
    return p, np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=scene_asset(Path(__file__).resolve().parents[1], "assets/procedural_float"))
    ap.add_argument("--length", type=float, default=0.46)
    ap.add_argument("--width", type=float, default=0.28)
    ap.add_argument("--tubes", type=int, default=6)
    ap.add_argument("--half-thick", type=float, default=0.026)
    ap.add_argument("--corner", type=float, default=0.05, help="plan corner radius (m)")
    ap.add_argument("--seam", type=float, default=0.006, help="width of the welded flange (m)")
    ap.add_argument("--groove", type=float, default=0.62, help="rib groove depth as a share of the thickness")
    ap.add_argument("--mass", type=float, default=0.15, help="PVC skin of this size, kg")
    ap.add_argument("--cell", type=float, default=0.001)
    ap.add_argument("--seed", type=int, default=20261102)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    hl, hw, R = a.length / 2, a.width / 2, a.half_thick

    xs = np.arange(-hl - 3 * a.cell, hl + 3 * a.cell + 1e-9, a.cell)
    ys = np.arange(-hw - 3 * a.cell, hw + 3 * a.cell + 1e-9, a.cell)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    dp = plan_sd(X, Y, hl, hw, a.corner)

    # the inflated pouch rises as a quarter circle from the seam
    u = np.clip((-dp - a.seam) / R, 0, 1)
    env = R * np.sqrt(np.clip(1 - (1 - u) ** 2, 0, 1))

    # weld lines between the tubes: they stop short of the ends, where the tubes join into one chamber
    s = a.width / a.tubes
    yc = (Y / s + a.tubes / 2) % 1.0 - 0.5 if a.tubes % 2 == 0 else (Y / s) % 1.0 - 0.5
    rib = np.sqrt(np.clip(1 - (2 * np.abs(yc)) ** 2 * (1 - (1 - a.groove) ** 2), 0, 1))
    end = hl - 0.042
    window = np.clip((end - np.abs(X)) / 0.022, 0, 1)
    window = window * window * (3 - 2 * window)
    keep = np.abs(Y) < hw - 0.5 * s                  # no groove outside the outermost tube
    t = env * (1 - window * keep * (1 - rib))

    # puckers: the flat sheet is gathered along the curved seam; they fade within ~15 mm of it
    pts, arc = outline(hl, hw, a.corner)
    idx = cKDTree(pts).query(np.stack([X.ravel(), Y.ravel()], 1), workers=-1)[1].reshape(X.shape)
    arc_xy = arc[idx]
    phases = rng.uniform(0, 2 * np.pi, 5)
    waves = sum(w * np.sin(2 * np.pi * arc_xy / lam + ph) for w, lam, ph in
                zip((1.0, 0.7, 0.45, 0.8, 0.5), (0.021, 0.013, 0.0085, 0.033, 0.0175), phases))
    corner_gain = 1.0 + 1.2 * np.clip((a.corner - np.minimum(hl - np.abs(X), hw - np.abs(Y))) / a.corner, 0, 1)
    pucker = 0.00055 * waves * corner_gain * np.exp(np.minimum(dp + a.seam, 0) / 0.013)
    # slow unevenness of the inflated skin
    lump = gaussian_filter(rng.standard_normal(X.shape), 18 / (a.cell * 1000)) * 18 / (a.cell * 1000) * 0.00045
    t = np.where(u > 0, t + (pucker + lump) * np.minimum(u * 4, 1), t)
    # the seam flange: a thin strip whose mid-plane waves with the same gathers
    z0 = 0.0011 * waves / 2.0 * corner_gain * np.exp(np.minimum(dp + a.seam, 0) / 0.009)
    flange = np.where(dp < 0, 0.0009, -1.0)
    t = gaussian_filter(np.maximum(t, flange), 0.6)
    t[dp > 0.5 * a.cell] = -1.0

    # ---- closed mesh by marching cubes on |z - z0| - t
    dz = 0.4e-3
    zs = np.arange(-R - 0.004, R + 0.004 + 1e-9, dz)
    F = np.abs(zs[None, None, :] - z0[:, :, None]) - t[:, :, None]
    v, f, _, _ = marching_cubes(F.astype(np.float32), 0.0, spacing=(a.cell, a.cell, dz))
    v += [xs[0], ys[0], zs[0]]
    mesh = trimesh.Trimesh(v, f[:, ::-1] if False else f, process=True)
    keep_big = max(mesh.split(only_watertight=False), key=lambda m: len(m.faces))
    mesh = keep_big
    if mesh.volume < 0:
        mesh.invert()
    print("float mesh", len(mesh.vertices), "verts", len(mesh.faces), "faces, watertight", mesh.is_watertight,
          f"volume {mesh.volume * 1e3:.3f} L bbox {mesh.bounds.tolist()}")
    np.savez(a.out / "float_mesh.npz", vertices=mesh.vertices.astype(np.float32), triangles=mesh.faces.astype(np.int32),
             normals=mesh.vertex_normals.astype(np.float32))
    np.savez_compressed(a.out / "float_field.npz", x=xs, y=ys, t=t.astype(np.float32), z0=z0.astype(np.float32))
    hull = mesh.convex_hull
    hull.export(a.out / "float_collision.obj")

    # ---- Archimedes table: displaced volume against the depth of the lowest point
    cell = a.cell ** 2
    bottom = float((z0 - t)[t > 0].min())
    draft = np.arange(0.0, 0.0651, 0.0002)
    disp = np.array([np.clip(bottom + d - (z0 - t), 0, 2 * t)[t > 0].sum() * cell for d in draft])
    (a.out / "float_manifest.json").write_text(json.dumps({
        "name": "procedural inflatable float", "provider": "project-authored (make_float.py)", "license": "project-authored",
        "length_m": a.length, "width_m": a.width, "tubes": a.tubes, "half_thick_m": a.half_thick, "corner_radius_m": a.corner,
        "seam_m": a.seam, "groove": a.groove, "mass_kg": a.mass, "volume_m3": float(mesh.volume), "plan_area_m2": float((dp < 0).sum() * cell),
        "z_range_m": mesh.bounds[:, 2].tolist(), "hull_volume_m3": float(hull.volume),
        "archimedes": {"draft_m": draft.tolist(), "displaced_m3": disp.tolist()}}, indent=1))
    for m in (a.mass, a.mass + 2.0):
        print(f"{m:.2f} kg: Archimedes draft {np.interp(m / 998, disp, draft) * 1e3:.1f} mm below the water line of the lowest point")


if __name__ == "__main__":
    main()
