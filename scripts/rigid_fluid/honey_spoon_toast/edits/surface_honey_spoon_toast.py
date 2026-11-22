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
    p.add_argument("--calibrate-isolated-volume", action="store_true",
                   help="Match well-separated 1-3 particle mesh islands to their SPH mass volume")
    p.add_argument("--toast-contact", type=Path,
                   help="The measured toast surface shared with the simulator")
    p.add_argument("--boundary-mirror", action="store_true",
                   help="Restore reconstruction density at the solid using mirrored boundary samples")
    return p.parse_args()


def calibrate_small_islands(vertices, triangles, points, dx, contact=None):
    """Keep every resolved surface and every droplet; correct inflated tiny islands.

    Genesis assigns 0.8*dx^3 to each particle. Low density kernel isosurfaces
    otherwise inflate isolated particles. Only well-separated 1-3 particle
    components qualify; thin jet fragments with nearby particles are retained.
    """
    import trimesh
    from scipy.spatial import cKDTree
    mesh = trimesh.Trimesh(vertices, triangles, process=False)
    groups = trimesh.graph.connected_components(mesh.edges_unique, nodes=np.arange(len(vertices)), engine='scipy')
    labels = np.empty(len(vertices), dtype=int)
    for label, indices in enumerate(groups):
        labels[indices] = label
    face_labels = labels[triangles[:, 0]]
    nearest = cKDTree(vertices).query(points)[1]
    particle_labels = labels[nearest]
    point_tree = cKDTree(points)
    out = vertices.astype(float).copy()
    changes = []
    for label, indices in enumerate(groups):
        pi = np.flatnonzero(particle_labels == label)
        if not 1 <= len(pi) <= 3:
            continue
        if np.ptp(vertices[indices], axis=0).max() > 8*dx:
            continue
        distances, neighbors = point_tree.query(points[pi], k=min(8,len(points)))
        outside = particle_labels[neighbors] != label
        if np.any((distances < 2*dx) & outside):
            continue
        faces = triangles[face_labels == label]
        center = points[pi].mean(0)
        q = out-center
        volume = abs(np.einsum('ij,ij->i',q[faces[:,0]],np.cross(q[faces[:,1]],q[faces[:,2]])).sum()/6)
        target = len(pi)*.8*dx**3
        if volume <= 1.1*target:
            continue
        factor = (target/volume)**(1/3)
        anchor=center
        if contact is not None:
            height,normal,valid=contact.sample(center[None,:2])
            if valid[0] and abs((center[2]-height[0])*normal[0,2])<1.1*dx:
                anchor=np.array([center[0],center[1],height[0]-.00003])
        out[indices] = anchor+(out[indices]-anchor)*factor
        changes.append({'particles': int(len(pi)), 'mesh_before_ml': volume*1e6,
                        'target_ml': target*1e6, 'linear_scale': factor})
    return out.astype(np.float32), changes


def atomic_json(path, value):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def main():
    args = args_parser()
    import pysplashsurf
    contact=None
    if args.toast_contact:
        from receiver_surface import BreadSurface
        contact=BreadSurface(args.toast_contact)
    if args.boundary_mirror:
        assert contact is not None

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
    if args.calibrate_isolated_volume:
        settings['isolated_volume_calibration'] = True
    if args.boundary_mirror:
        settings.update(boundary_mirror=True,toast_contact=str(args.toast_contact.resolve()),
                        boundary_sample_range_factor=.9,solid_surface_overlap_m=.00003)
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
        reconstruction_points=points
        mirror_count=0
        if args.boundary_mirror:
            h,n,valid=contact.sample(points[:,:2])
            distance=(points[:,2]-h)*n[:,2]
            near=valid&(distance>=0)&(distance<.9*dx)
            mirrored=points[near]-2*distance[near,None]*n[near]
            reconstruction_points=np.ascontiguousarray(np.concatenate((points,mirrored)),dtype=np.float64)
            mirror_count=int(near.sum())
        mesh_data, _ = pysplashsurf.reconstruction_pipeline(
            reconstruction_points, particle_radius=dx / 2, smoothing_length=2.0,
            cube_size=args.cube_size_factor, iso_surface_threshold=args.iso_threshold,
            mesh_smoothing_weights=True, mesh_smoothing_iters=args.smoothing_iters,
            normals_smoothing_iters=8, mesh_cleanup=True, compute_normals=True,
            multi_threading=True,
        )
        vertices = np.asarray(mesh_data.mesh.vertices, dtype=np.float32)
        triangles = np.asarray(mesh_data.mesh.triangles, dtype=np.int32)
        if not len(vertices) or not len(triangles) or not np.isfinite(vertices).all():
            raise RuntimeError(f"invalid reconstructed mesh at frame {frame}")
        if args.boundary_mirror:
            h,_,valid=contact.sample(vertices[:,:2])
            below=valid&(vertices[:,2]<h-.00003)
            vertices[below,2]=h[below]-.00003
        corrections = []
        if args.calibrate_isolated_volume:
            vertices, corrections = calibrate_small_islands(vertices, triangles, points, dx,contact if args.boundary_mirror else None)
        if args.boundary_mirror:
            h,_,valid=contact.sample(vertices[:,:2])
            below=valid&(vertices[:,2]<h-.00003)
            vertices[below,2]=h[below]-.00003
        np.savez_compressed(target, vertices=vertices, triangles=triangles)
        row = {"vertices": int(len(vertices)), "triangles": int(len(triangles)),
               "bounds_m": [vertices.min(0).tolist(), vertices.max(0).tolist()],
               "seconds": time.monotonic() - tick,
               "boundary_mirror_samples":mirror_count,
               "isolated_volume_corrections": corrections}
        log["frames"][str(frame)] = row
        atomic_json(log_path, log)
        print("MESH", frame, json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
