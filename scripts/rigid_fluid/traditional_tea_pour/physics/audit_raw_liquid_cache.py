"""Measure cached solver geometry, without Blender particle display transforms.

BOBJ coordinates are the normalized domain-local mesh coordinates produced by
Mantaflow. PB02 positions are in grid cells. Both mappings are checked against
the physical source on its first active frame before particle regions are used.
"""

import argparse
import gzip
import json
import struct
from pathlib import Path

import numpy as np


def domain_mapping(case):
    metadata = case / "experiment.json"
    if metadata.exists():
        bounds = json.loads(metadata.read_text()).get("after", {}).get("domain_bounds_m")
        if bounds:
            bounds = np.array(bounds)
            return float((bounds[1] - bounds[0]).max()), bounds.mean(axis=0)
    return 0.2, np.array([0., 0., 0.103])


def read_mesh(path, domain_length, domain_center):
    data = gzip.open(path, "rb").read()
    count = struct.unpack_from("<i", data, 0)[0]
    vertices = np.frombuffer(data, "<f4", count * 3, 4).reshape(-1, 3).astype(float)
    offset = 4 + count * 12
    normal_count = struct.unpack_from("<i", data, offset)[0]
    offset += 4 + normal_count * 12
    triangle_count = struct.unpack_from("<i", data, offset)[0]
    faces = np.frombuffer(data, "<i4", triangle_count * 3, offset + 4).reshape(-1, 3)
    return vertices * domain_length + domain_center, faces


def volume_below(vertices, faces, z):
    """Clip closed triangles at z, with tetrahedron origin on the cap plane."""
    tri = vertices[faces].copy()
    tri[:, :, 2] -= z
    inside = tri[:, :, 2] <= 0
    counts = inside.sum(axis=1)
    pieces = [tri[counts == 3]]
    for num_inside in (1, 2):
        selected = tri[counts == num_inside]
        if not len(selected):
            continue
        selected_inside = inside[counts == num_inside]
        for pivot in range(3):
            # Pivot is the sole inside vertex (one inside), or sole outside.
            keep = selected_inside[:, pivot] if num_inside == 1 else ~selected_inside[:, pivot]
            t = selected[keep][:, [pivot, (pivot + 1) % 3, (pivot + 2) % 3]]
            if not len(t):
                continue
            a, b, c = t[:, 0], t[:, 1], t[:, 2]
            ab = a + (b - a) * (-a[:, 2] / (b[:, 2] - a[:, 2]))[:, None]
            ac = a + (c - a) * (-a[:, 2] / (c[:, 2] - a[:, 2]))[:, None]
            if num_inside == 1:
                pieces.append(np.stack((a, ab, ac), axis=1))
            else:
                pieces.append(np.stack((ab, b, c), axis=1))
                pieces.append(np.stack((ab, c, ac), axis=1))
    value = sum(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() for t in pieces)
    return abs(float(value)) / 6 * 1e6


def read_particles(path, domain_length, domain_center):
    data = gzip.open(path, "rb").read()
    if data[:4] != b"PB02":
        raise ValueError("Expected Mantaflow PB02 particle cache")
    count, nx, ny, nz, element_type, stride = struct.unpack_from("<6i", data, 4)
    if stride != 16:
        raise ValueError(f"Unexpected particle stride: {stride}")
    array = np.frombuffer(data, np.dtype([("p", "<f4", 3), ("flag", "<i4")]), count, len(data) - count * stride)
    # Mantaflow deletion flag is bit 10, see particle.h. Keep NEW particles.
    array = array[(array["flag"] & 1024) == 0]
    dx = domain_length / max(nx, ny, nz)
    positions = (array["p"] - np.array([nx, ny, nz]) / 2) * dx + domain_center
    return positions, dx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cache", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--length", type=float)
    parser.add_argument("--center", type=float, nargs=3)
    args = parser.parse_args()
    length, center = domain_mapping(args.cache.parent)
    args.length = args.length if args.length is not None else length
    center = np.array(args.center) if args.center is not None else center
    frames = {}
    for path in sorted((args.cache / "mesh").glob("fluid_mesh_*.bobj.gz")):
        frame = int(path.name.split("_")[-1].split(".")[0])
        try:
            vertices, faces = read_mesh(path, args.length, center)
        except (EOFError, ValueError, struct.error):
            print(f"Skipping incomplete mesh {path.name}", flush=True)
            continue
        cup_volume = volume_below(vertices, faces, 0.068)
        total_volume = volume_below(vertices, faces, 1)
        base_volume = volume_below(vertices, faces, 0.018)
        entry = {
            "cup_mesh_volume_ml": cup_volume - base_volume,
            "below_bottom_mesh_volume_ml": base_volume,
            "total_mesh_volume_ml": total_volume,
            "bounds_m": [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()] if len(vertices) else None,
            "vertex_count": len(vertices),
            "triangle_count": len(faces),
        }
        pp_path = args.cache / "data" / f"pp_{frame:04d}.uni"
        if pp_path.exists():
            positions, dx = read_particles(pp_path, args.length, center)
            entry["particle_bounds_m"] = [positions.min(axis=0).tolist(), positions.max(axis=0).tolist()] if len(positions) else None
            entry["active_particle_count"] = len(positions)
            entry["particles_below_18mm"] = int((positions[:, 2] < 0.018).sum())
            # Occupied-cell volume provides a second, resampling-independent
            # diagnostic of the bulk. It is not treated as exact liquid volume.
            cup = positions[(positions[:, 2] >= 0.018) & (positions[:, 2] < 0.068)]
            voxels = np.unique(np.floor((cup - center) / dx).astype(int), axis=0)
            entry["cup_occupied_cell_volume_ml"] = len(voxels) * dx ** 3 * 1e6
        frames[str(frame)] = entry
    report = {"cache": str(args.cache), "domain_length_m": args.length, "domain_center_m": center.tolist(), "frames": frames}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    for frame in (13, 20, 24, 36, 48, 60, 72, 80, 84, 90, 96):
        if str(frame) in frames:
            print(frame, json.dumps(frames[str(frame)], sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
