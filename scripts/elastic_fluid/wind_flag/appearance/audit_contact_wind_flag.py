"""Blender audit: actual stand vs evaluated subdivided/thickened cloth.

Check every integer frame and three quarter-frame interior samples.
No pole, cloth, material or animation data is modified or saved by this audit.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def triangle_minimum_radii(xyz, triangles):
    """Exact min XY distance to the origin for each projected triangle."""
    p = xyz[triangles, :2].astype(np.float64)
    a, b = p, np.roll(p, -1, axis=1)
    delta = b - a
    denom = np.sum(delta * delta, axis=2)
    t = np.clip(-np.sum(a * delta, axis=2) / np.maximum(denom, 1e-24), 0, 1)
    distance2 = np.sum((a + t[:, :, None] * delta) ** 2, axis=2).min(axis=1)
    crosses = a[:, :, 0] * b[:, :, 1] - a[:, :, 1] * b[:, :, 0]
    area2 = np.abs(crosses.sum(axis=1))
    inside = ((crosses >= -1e-15).all(axis=1) | (crosses <= 1e-15).all(axis=1)) & (area2 > 1e-14)
    distance2[inside] = 0
    return np.sqrt(distance2)


def pole_slabs(pole_xyz, pole_triangles):
    """Conservative actual-mesh radial bounds, including the upper finial."""
    z=pole_xyz[pole_triangles,2]
    lower,upper=z.min(axis=1),z.max(axis=1)
    radii=np.linalg.norm(pole_xyz[pole_triangles,:2],axis=2).max(axis=1)
    edges=np.unique(np.r_[np.linspace(pole_xyz[:,2].min(),pole_xyz[:,2].max(),129),3.63,3.64,3.65])
    slabs=[]
    for lo,hi in zip(edges[:-1],edges[1:]):
        active=(lower<=hi)&(upper>=lo)
        if active.any():
            slabs.append((float(lo),float(hi),float(radii[active].max())))
    return slabs,lower,upper,radii


def conservative_pole_gap(xyz, triangles, slabs):
    radii=triangle_minimum_radii(xyz,triangles)
    z=xyz[triangles,2]
    lower,upper=z.min(axis=1),z.max(axis=1)
    gap=float("inf")
    for lo,hi,pole_radius in slabs:
        active=(lower<=hi)&(upper>=lo)
        if active.any():
            gap=min(gap,float(radii[active].min())-pole_radius)
    return gap


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="Optional diagnostic output outside the inspected baseline")
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--vertex-tolerance-m", type=float, default=0.0001)
    parser.add_argument("--subdivisions", type=int, default=4)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    started = time.monotonic()
    results = {}
    for case in args.cases or ["source", "flow_x0p25"]:
        bpy.ops.wm.open_mainfile(filepath=str((args.root / case / "scene.blend").resolve()))
        scene = bpy.context.scene
        pole = bpy.data.objects["BlenderKit_UN_ceremonial_flag_stand"]
        flag = bpy.data.objects["Flag_Genesis_FEM"]
        pole_xyz = np.array([pole.matrix_world @ v.co for v in pole.data.vertices], np.float64)
        pole_faces = [tuple(p.vertices) for p in pole.data.polygons]
        pole_bvh = BVHTree.FromPolygons(pole_xyz.tolist(), pole_faces, all_triangles=False)
        pole.data.calc_loop_triangles()
        pole_triangles=np.array([t.vertices[:] for t in pole.data.loop_triangles],np.int32)
        slabs,pole_lower,pole_upper,pole_face_radii=pole_slabs(pole_xyz,pole_triangles)
        shaft = pole_xyz[(pole_xyz[:, 2] > 0.5) & (pole_xyz[:, 2] < 3.64)]
        shaft_radius = float(np.linalg.norm(shaft[:, :2], axis=1).max())
        samples = []
        minimum_radial_gap = float("inf")
        max_inside_depth, max_inside_count, max_pairs = 0.0, 0, 0
        sample_count = (scene.frame_end-scene.frame_start)*args.subdivisions+1
        for sample in range(sample_count):
            frame = scene.frame_start + sample / args.subdivisions
            scene.frame_set(int(frame), subframe=frame % 1)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = flag.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            xyz = np.array([evaluated.matrix_world @ v.co for v in mesh.vertices], np.float64)
            triangles = np.array([p.vertices[:] for p in mesh.loop_triangles], np.int32)
            flag_bvh = BVHTree.FromPolygons(xyz.tolist(), triangles.tolist(), all_triangles=True)
            pairs = pole_bvh.overlap(flag_bvh)
            radial = np.linalg.norm(xyz[:, :2], axis=1)
            nearby_pole_faces=(pole_lower<=xyz[:,2].max())&(pole_upper>=xyz[:,2].min())
            relevant_radius=float(pole_face_radii[nearby_pole_faces].max()) if nearby_pole_faces.any() else 0.
            candidates = np.flatnonzero((radial < relevant_radius + 0.002) &
                (xyz[:,2]>=pole_xyz[:,2].min()) & (xyz[:,2]<=pole_xyz[:,2].max()))
            inside_depths = []
            for index in candidates:
                point = Vector(xyz[index])
                nearest, normal, face_index, distance = pole_bvh.find_nearest(point)
                if nearest is not None and (point - nearest).dot(normal) < -args.vertex_tolerance_m:
                    inside_depths.append(float(distance))
            # The raised flag may extend above the plain shaft. Bound every
            # cloth triangle against actual pole-face radii in overlapping Z
            # slabs, rather than ignoring or rejecting the finial interval.
            gap = conservative_pole_gap(xyz,triangles,slabs)
            minimum_radial_gap = min(minimum_radial_gap, gap)
            max_inside_depth = max(max_inside_depth, max(inside_depths, default=0.0))
            max_inside_count = max(max_inside_count, len(inside_depths))
            max_pairs = max(max_pairs, len(pairs))
            samples.append({"frame": frame, "inside_evaluated_vertices": len(inside_depths),
                            "intersecting_triangle_pairs": len(pairs),
                            "minimum_evaluated_triangle_radial_gap_m": gap})
            evaluated.to_mesh_clear()
        accepted = max_inside_count == 0 and max_pairs == 0 and minimum_radial_gap > 0
        results[case] = {
            "status": "accepted" if accepted else "failed",
            "integer_frames": scene.frame_end-scene.frame_start+1,
            "interior_subframe_samples": sample_count-(scene.frame_end-scene.frame_start+1),
            "subdivisions_per_frame_interval": args.subdivisions,
            "measured_shaft_envelope_radius_m": shaft_radius,
            "pole_clearance_method":"Conservative actual triangle radial bounds in overlapping vertical slabs, including the finial",
            "minimum_evaluated_triangle_radial_gap_m": minimum_radial_gap,
            "maximum_inside_evaluated_vertices": max_inside_count,
            "maximum_vertex_interior_depth_m": max_inside_depth,
            "maximum_intersecting_triangle_pairs": max_pairs,
            "vertex_inside_tolerance_m": args.vertex_tolerance_m,
            "samples": samples,
        }
        print(json.dumps({"case": case, **{k: v for k, v in results[case].items() if k != "samples"}}, indent=2), flush=True)
    report = {
        "status": "accepted" if all(r["status"] == "accepted" for r in results.values()) else "failed",
        "scope": "Actual stand mesh vs evaluated cloth including shape keys, 1 mm solidify and level-1 subdivision. All vertices and all triangle interiors are included; no hoist exclusion. Integer and quarter-frame samples by default; not a proof for every continuous subframe.",
        "cases": results, "audit_wall_seconds": time.monotonic() - started,
    }
    (args.out or args.root / "pole_contact_audit.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    if report["status"] != "accepted":
        raise RuntimeError("Evaluated cloth / pole contact audit failed")


if __name__ == "__main__":
    main()
