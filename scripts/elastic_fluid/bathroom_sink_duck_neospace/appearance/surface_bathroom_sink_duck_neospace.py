"""Surfaces for rendering the Genesis run: water meshes with per-vertex velocity, and the skinned visible duck.

Water: pysplashsurf at 0.75 x the SPH particle spacing (the radius that keeps the stream continuous without
blobby splashes), smoothing length 2, iso 0.6; each vertex gets the inverse-distance velocity of its nearest
particles so Cycles can motion-blur a mesh whose topology changes every frame.
Duck: every visible-duck vertex follows its eight nearest MPM particles (inverse-distance weights on the
configuration the particles were sampled in, which matches the visible mesh), so the sag while the duck settles
under its own weight is shown too.
    python surface_bathroom_sink_duck_neospace.py --sim genesis_sim.npz --duck-rest duck_rest.npz --out-dir surfaces
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim", type=Path, required=True)
    parser.add_argument("--duck-rest", type=Path, required=True, help="duck_rest.npz holding the visible duck's rest vertices")
    parser.add_argument("--spacing", type=float, default=0.0015, help="SPH particle size of the run (m)")
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def main():
    import pysplashsurf
    from scipy.spatial import cKDTree

    args = parse_args()
    out = args.out_dir.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    sim = np.load(args.sim)
    has_duck = "trajectory" in sim.files                       # absent when the duck is deleted
    if has_duck:
        sampled, trajectory = sim["initial"], sim["trajectory"]
        visual = np.load(args.duck_rest)["rest_vertices"]
        distance, owners = cKDTree(sampled).query(visual, k=8)
        weights = 1.0 / (distance ** 2 + (0.5 * args.spacing) ** 2)
        weights /= weights.sum(1, keepdims=True)
    frames = sorted(int(k.split("_")[1]) for k in sim.files if k.startswith("water_") and k[6:].isdigit())
    radius = 0.75 * args.spacing
    log = {"particle_radius_m": radius, "smoothing_length_radius_factor": 2.0, "iso_surface_threshold": 0.6, "frames": {}}
    duck_frames = np.zeros((len(frames), len(visual), 3), dtype=np.float32) if has_duck else None
    for index, frame in enumerate(frames):
        tick = time.monotonic()
        positions = sim[f"water_{frame:03d}"].astype(np.float64)
        velocities = sim[f"wvel_{frame:03d}"].astype(np.float64)
        if len(positions):
            mesh, _ = pysplashsurf.reconstruction_pipeline(
                positions, particle_radius=radius, smoothing_length=2.0, cube_size=0.8, iso_surface_threshold=0.6,
                mesh_smoothing_weights=True, mesh_smoothing_iters=25, normals_smoothing_iters=10, mesh_cleanup=True,
                compute_normals=False, multi_threading=True)
            vertices = np.asarray(mesh.mesh.vertices, dtype=np.float64)
            triangles = np.asarray(mesh.mesh.triangles, dtype=np.int32)
            near_d, near_i = cKDTree(positions).query(vertices, k=4)
            w = 1.0 / (near_d ** 2 + (0.5 * args.spacing) ** 2)
            vertex_velocity = (velocities[near_i] * w[..., None]).sum(1) / w.sum(1, keepdims=True)
        else:                                                    # the water is deleted
            vertices, triangles, vertex_velocity = np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32), np.zeros((0, 3))
        np.savez_compressed(out / f"water_{frame:04d}.npz", vertices=vertices.astype(np.float32),
                            triangles=triangles, velocity=vertex_velocity.astype(np.float32))
        if has_duck:
            duck_frames[index] = visual + (weights[..., None] * (trajectory[frame - 1] - sampled)[owners]).sum(1)
        log["frames"][frame] = {"particles": int(len(positions)), "vertices": int(len(vertices)),
                                "triangles": int(len(triangles)), "seconds": time.monotonic() - tick}
        print(f"SURFACE frame {frame}: {len(positions)} particles -> {len(vertices)} vertices", flush=True)
    if has_duck:
        np.savez_compressed(out / "duck_visual.npz", frames=np.array(frames), vertices=duck_frames)
    (out / "surface_report.json").write_text(json.dumps(log, indent=2) + "\n")


if __name__ == "__main__":
    main()
