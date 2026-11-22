"""All-particle kernel reconstruction; shading normals cannot move the liquid.

No geometry smoothing, temporal averaging, particle removal, target volume,
wall Boolean, wetting-film replacement, or level animation is performed.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pysplashsurf
from scipy.spatial import cKDTree

from audit_raw_liquid_cache import volume_below

p = argparse.ArgumentParser()
p.add_argument("case", type=Path)
p.add_argument("--frames", type=int, nargs="+")
a = p.parse_args()
case = a.case.resolve()
out = case / "surfaces"
out.mkdir(exist_ok=True)
experiment = json.loads((case / "experiment.json").read_text())
spacing = experiment["after"]["particle_size_m"]
floor = experiment["before"]["physics"]["cup_floor_m"] - 2 * spacing
rim = experiment["before"]["physics"]["cup_rim_m"]
rows = {}
for frame in a.frames or range(1, 97):
    path = case / "particles" / f"frame_{frame:04d}.npz"
    target = out / path.name
    before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    tick = time.monotonic()
    with np.load(path) as z:
        positions, velocities = z["pos"].astype(float), z["vel"].astype(float)
    if target.exists():
        with np.load(target) as z:
            v, t, n = z["vertices"].astype(float), z["triangles"], z["normals"]
    else:
        if len(positions):
            result, _ = pysplashsurf.reconstruction_pipeline(
                positions, particle_radius=.5 * spacing, rest_density=1000.,
                smoothing_length=2., cube_size=1., iso_surface_threshold=.5,
                mesh_cleanup=True, mesh_smoothing_iters=0,
                compute_normals=True, normals_smoothing_iters=10,
                multi_threading=True)
            v = np.asarray(result.mesh.vertices, dtype=float)
            t = np.asarray(result.mesh.triangles, dtype=np.int32)
            n = np.asarray(result.point_attributes["normals"], dtype=float)
            # Isolated triangle normals may be zero in the kernel field.
            # Repair only normals, never geometry or particle positions.
            lengths = np.linalg.norm(n, axis=1)
            bad = (~np.isfinite(n).all(axis=1)) | (lengths < 1e-12)
            if bad.any():
                face_n = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
                fallback = np.zeros_like(v)
                for corner in range(3):
                    np.add.at(fallback, t[:, corner], face_n)
                n[bad] = fallback[bad]
                lengths = np.linalg.norm(n, axis=1)
                zero = lengths < 1e-12
                n[zero], lengths[zero] = (0., 0., 1.), 1.
            n /= lengths[:, None]
            distances, ids = cKDTree(positions).query(v, k=min(4, len(positions)))
            weights = 1. / (distances ** 2 + (.5 * spacing) ** 2)
            velocity = (velocities[ids] * weights[..., None]).sum(1) / weights.sum(1, keepdims=True)
        else:
            v = n = velocity = np.zeros((0, 3))
            t = np.zeros((0, 3), dtype=np.int32)
        assert np.isfinite(v).all() and np.isfinite(n).all()
        assert not len(n) or np.max(np.abs(np.linalg.norm(n, axis=1) - 1)) < .002
        np.savez_compressed(target, vertices=v.astype(np.float32), triangles=t,
                            normals=n.astype(np.float32), velocity=velocity.astype(np.float32))
    assert np.isfinite(v).all() and np.isfinite(n).all()
    assert not len(n) or np.max(np.abs(np.linalg.norm(n, axis=1) - 1)) < .002
    assert before_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    row = {"cup_mesh_volume_ml": volume_below(v, t, rim) - volume_below(v, t, floor),
           "total_mesh_volume_ml": volume_below(v, t, 1.),
           "below_bottom_mesh_volume_ml": volume_below(v, t, floor),
           "vertex_count": len(v), "triangle_count": len(t),
           "input_particles": len(positions), "input_sha256": before_hash,
           "source_particles_unchanged": True, "unit_finite_normals": True,
           "seconds": time.monotonic() - tick}
    rows[str(frame)] = row
    print("SURFACE=" + json.dumps({"frame": frame, **row}), flush=True)
report = {"case": str(case), "frames": rows, "reconstruction": {
    "audit_vertical_window_m": [floor, rim],
    "particle_radius_m": .5 * spacing, "compact_support_radius_m": 2 * spacing,
    "matches_native_sph_kernel_support": True, "marching_cubes_cell_m": .5 * spacing,
    "iso_surface_threshold": .5, "geometry_smoothing_iterations": 0,
    "normal_smoothing_iterations": 10, "all_particles_retained": True,
    "note": "Only shading normals are smoothed. Geometry comes from all simulated particles, without temporal or geometry filtering, level fitting, Boolean or volume rescaling."}}
(case / ("surface_audit_selected.json" if a.frames else "surface_audit.json")).write_text(json.dumps(report, indent=2) + "\n")
