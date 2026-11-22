#!/usr/bin/env python3
"""Render surfaces for the pressure-membrane water balloon.

Balloon: the latex membrane mesh from the solver cache, unchanged.
Water: for each frame, the region inside the latex and below that frame's
water level, inset 0.4 mm from the latex so the two surfaces never coincide,
extracted with marching cubes and lightly smoothed.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--run", "--simulation-dir", type=Path, required=True, help="directory with membrane.npz")
    p.add_argument("--out", "--out-dir", type=Path, required=True)
    p.add_argument("--frames", default="all")
    p.add_argument("--voxel", type=float, default=0.0006)
    p.add_argument("--inset", type=float, default=0.0010)
    p.add_argument("--without-balloon", action="store_true",
                   help="DELETE balloon: water surfaces of the open jar from <run>/jar_water.npz (simulate --without-balloon)")
    args=p.parse_args(argv)
    if args.out.exists() and any(args.out.iterdir()):
        p.error("Refusing to overwrite existing surface output: "+str(args.out))
    return args


def jar_surfaces(args, gap=0.0003, lift=0.0001, segments=128) -> None:
    """DELETE balloon: the water in the open jar, a solid of revolution of the jar's inner wall up to each frame's level.

    The surface keeps `gap` from the glass and starts `lift` above the jar floor so the water and glass surfaces
    never coincide; the top is the flat hydrostatic free surface.
    """
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "water").mkdir(exist_ok=True)
    sim = np.load(args.run / "jar_water.npz")
    levels, poured = sim["water_level"], sim["poured_m3"]
    profile, bottom = sim["jar_inner_profile_zr"], float(sim["jar_floor_z"]) + lift
    np.save(args.out / "water_level.npy", levels.astype(np.float32))
    ang = 2.0 * np.pi * np.arange(segments) / segments
    rows = []
    for index, level in enumerate(levels):
        frame, tick = index + 1, time.monotonic()
        wv, wf, volume = np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32), 0.0
        if level - bottom > 2e-4:
            zs = np.unique(np.concatenate([[bottom, level], np.arange(bottom, level, 0.001),
                                           profile[(profile[:, 0] > bottom) & (profile[:, 0] < level), 0]]))
            zs = zs[np.r_[True, np.diff(zs) > 1e-6]]
            radius = np.interp(zs, profile[:, 0], profile[:, 1]) - gap
            ring = np.stack([np.outer(radius, np.cos(ang)), np.outer(radius, np.sin(ang)),
                             np.repeat(zs[:, None], segments, 1)], -1).reshape(-1, 3)
            n = len(zs) * segments
            verts = np.vstack([ring, [[0.0, 0.0, zs[0]], [0.0, 0.0, zs[-1]]]])
            k = np.arange(segments)
            q = (k + 1) % segments
            faces = []
            for j in range(len(zs) - 1):
                a, b, c, d = j * segments + k, j * segments + q, (j + 1) * segments + q, (j + 1) * segments + k
                faces += [np.stack([a, b, c], 1), np.stack([a, c, d], 1)]
            faces += [np.stack([np.full(segments, n), q, k], 1),
                      np.stack([np.full(segments, n + 1), (len(zs) - 1) * segments + k, (len(zs) - 1) * segments + q], 1)]
            faces = np.vstack(faces)
            tri = verts[faces]
            volume = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
            if volume > 0.5e-6:                      # as main(): ignore sub-0.5 mL slivers
                wv, wf = verts.astype(np.float32), faces.astype(np.int32)
            else:
                volume = 0.0
        np.savez_compressed(args.out / "water" / f"water_{frame:04d}.npz", vertices=wv, faces=wf)
        rows.append({"frame": frame, "level_z": float(level), "water_vertices": int(len(wv)),
                     "max_signed_distance_to_latex_mm": 0.0, "water_vertices_outside_latex": 0,
                     "water_volume_ml": volume * 1e6, "poured_ml": float(poured[index] * 1e6),
                     "seconds": time.monotonic() - tick})
        print("WATER", json.dumps(rows[-1]), flush=True)
    (args.out / "surface_report.json").write_text(json.dumps({
        "water": rows, "frames_with_water_outside_latex": [],
        "container": "open glass jar (DELETE balloon): no latex membrane; latex fields are not applicable and zero",
        "gap_to_glass_m": gap, "lift_above_floor_m": lift}, indent=1))
    print("SURFACE_DONE", flush=True)


def main() -> None:
    args = parse_args()
    if args.without_balloon:
        jar_surfaces(args)
        return
    import igl
    import trimesh
    from skimage import measure

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "water").mkdir(exist_ok=True)
    sim = np.load(args.run / "membrane.npz")
    traj = sim["trajectory"]
    faces = sim["faces"].astype(np.int64)
    levels = sim["water_level"]
    np.savez_compressed(args.out / "balloon_visual.npz", outer_vertices=traj.astype(np.float32),
                        outer_faces=faces.astype(np.int32))
    np.save(args.out / "water_level.npy", levels.astype(np.float32))
    wanted = None if args.frames == "all" else {int(v) for v in args.frames.split(",")}
    rows = []
    for index, verts in enumerate(traj):
        frame = index + 1
        if wanted is not None and frame not in wanted:
            continue
        tick = time.monotonic()
        level = float(levels[index])
        v = verts.astype(np.float64)
        lo = v.min(axis=0) - 2 * args.voxel
        hi = v.max(axis=0) + 2 * args.voxel
        hi[2] = min(hi[2], level + 2 * args.voxel)
        wv = np.zeros((0, 3), np.float32)
        wf = np.zeros((0, 3), np.int32)
        if level > lo[2] + 3 * args.voxel:
            axes = [np.arange(lo[k], hi[k] + args.voxel, args.voxel) for k in range(3)]
            grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
            sd, *_ = igl.signed_distance(grid, v, faces,
                                         sign_type=igl.SIGNED_DISTANCE_TYPE_FAST_WINDING_NUMBER)
            # water field: positive inside (inset from latex) and below the free surface
            field = np.minimum(-sd - args.inset, level - grid[:, 2]).reshape([len(a) for a in axes])
            if field.max() > 0:
                mv, mf, _, _ = measure.marching_cubes(field, 0.0, spacing=(args.voxel,) * 3)
                mv += lo
                mesh = trimesh.Trimesh(mv, mf[:, ::-1], process=True)
                # one body of water: drop any stray islands from sign noise
                parts = mesh.split(only_watertight=False)
                if len(parts) > 1:
                    mesh = max(parts, key=lambda m: abs(m.volume))
                trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53, iterations=12)
                if mesh.volume < 0:
                    mesh.invert()
                if abs(mesh.volume) > 0.5e-6:      # ignore sub-0.5 mL slivers before the pump starts
                    wv = np.asarray(mesh.vertices, np.float32)
                    wf = np.asarray(mesh.faces, np.int32)
        np.savez_compressed(args.out / "water" / f"water_{frame:04d}.npz", vertices=wv, faces=wf)
        outside_mm, outside_n = 0.0, 0
        if len(wv):
            check, *_ = igl.signed_distance(wv.astype(np.float64), v, faces,
                                            sign_type=igl.SIGNED_DISTANCE_TYPE_FAST_WINDING_NUMBER)
            outside_mm, outside_n = float(check.max() * 1e3), int((check > 0).sum())
        rows.append({"frame": frame, "level_z": level, "water_vertices": int(len(wv)),
                     "max_signed_distance_to_latex_mm": outside_mm, "water_vertices_outside_latex": outside_n,
                     "water_volume_ml": float(abs(trimesh.Trimesh(wv, wf, process=False).volume) * 1e6) if len(wf) else 0.0,
                     "seconds": time.monotonic() - tick})
        print("WATER", json.dumps(rows[-1]), flush=True)
    (args.out / "surface_report.json").write_text(json.dumps({
        "water": rows,
        "frames_with_water_outside_latex": [r["frame"] for r in rows if r["water_vertices_outside_latex"]],
    }, indent=1))
    print("SURFACE_DONE", flush=True)


if __name__ == "__main__":
    main()
