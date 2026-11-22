"""Reconstruct smooth honey meshes from Genesis DFSPH particles."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


def args_parser():
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--frames", nargs="*", type=int)
    p.add_argument("--dx", type=float,
                   help="Explicit particle spacing for completed-frame previews during a running simulation")
    p.add_argument("--smoothing-iters", type=int, default=14)
    p.add_argument("--cube-size-factor", type=float, default=0.70)
    p.add_argument("--iso-threshold", type=float, default=0.55)
    p.add_argument("--mesh-subdir", default="meshes")
    return p.parse_args()


def atomic_json(path, value):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def main():
    args = args_parser()
    import pysplashsurf

    report_path = args.run / "simulation_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text())
        dx = float(report["numerics"]["dx_m"])
        frame_count = int(report["numerics"]["frames"])
    elif args.dx and args.frames:
        dx, frame_count = args.dx, max(args.frames)
    else:
        raise RuntimeError("Running simulation previews require explicit --dx and --frames")
    frames = args.frames or list(range(1, frame_count + 1))
    if Path(args.mesh_subdir).name != args.mesh_subdir:
        raise ValueError("--mesh-subdir must be a single directory name")
    out = args.run / args.mesh_subdir
    out.mkdir(exist_ok=True)
    settings = {
        "source": "Genesis DFSPH honey particles", "particle_radius_m": dx / 2,
        "smoothing_length_radius_factor": 2.0, "cube_size_radius_factor": args.cube_size_factor,
        "iso_surface_threshold": args.iso_threshold, "mesh_smoothing_iters": args.smoothing_iters,
    }
    log_name = "meshing_report.json" if args.mesh_subdir=="meshes" else f"meshing_report_{args.mesh_subdir}.json"
    log_path = args.run / log_name
    log = json.loads(log_path.read_text()) if log_path.exists() else {"settings": settings, "frames": {}}
    if log["settings"] != settings:
        raise RuntimeError("existing meshing settings differ")
    for frame in frames:
        target = out / f"honey_{frame:04d}.npz"
        if target.exists():
            continue
        tick = time.monotonic()
        with np.load(args.run / "particles" / f"frame_{frame:04d}.npz") as state:
            points = np.ascontiguousarray(state["honey_pos"], dtype=np.float64)
        mesh_data, _ = pysplashsurf.reconstruction_pipeline(
            points, particle_radius=dx / 2, smoothing_length=2.0,
            cube_size=args.cube_size_factor, iso_surface_threshold=args.iso_threshold,
            mesh_smoothing_weights=True, mesh_smoothing_iters=args.smoothing_iters,
            normals_smoothing_iters=8, mesh_cleanup=True, compute_normals=True,
            multi_threading=True,
        )
        vertices = np.asarray(mesh_data.mesh.vertices, dtype=np.float32)
        triangles = np.asarray(mesh_data.mesh.triangles, dtype=np.int32)
        if not len(vertices) or not len(triangles) or not np.isfinite(vertices).all():
            raise RuntimeError(f"invalid reconstructed mesh at frame {frame}")
        np.savez_compressed(target, vertices=vertices, triangles=triangles)
        row = {"vertices": int(len(vertices)), "triangles": int(len(triangles)),
               "bounds_m": [vertices.min(0).tolist(), vertices.max(0).tolist()],
               "seconds": time.monotonic() - tick}
        log["frames"][str(frame)] = row
        atomic_json(log_path, log)
        print("MESH", frame, json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
