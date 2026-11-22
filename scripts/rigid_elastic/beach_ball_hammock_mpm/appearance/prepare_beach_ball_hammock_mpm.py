"""Build and validate the beach-ball / elastic-hammock PCVE source scene."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np


HAMMOCK_NAME = "Hammock_ElasticBody_ORIGINAL"
BALL_NAME = "BeachBall_RigidBody"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-blend", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_surface(obj, destination: Path) -> tuple[int, int]:
    mesh = obj.data
    world = obj.matrix_world
    vertices = np.array([world @ vertex.co for vertex in mesh.vertices], dtype=np.float64)
    triangles = []
    for polygon in mesh.polygons:
        indices = list(polygon.vertices)
        for index in range(1, len(indices) - 1):
            triangles.append((indices[0], indices[index], indices[index + 1]))
    triangles = np.asarray(triangles, dtype=np.int32)

    uv = np.zeros((len(mesh.vertices), 2), dtype=np.float64)
    uv_count = np.zeros(len(mesh.vertices), dtype=np.int32)
    if mesh.uv_layers.active:
        uv_data = mesh.uv_layers.active.data
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                vertex_index = mesh.loops[loop_index].vertex_index
                uv[vertex_index] += uv_data[loop_index].uv
                uv_count[vertex_index] += 1
        uv /= np.maximum(uv_count[:, None], 1)

    np.savez_compressed(destination, vertices=vertices, triangles=triangles, uv=uv)
    return len(vertices), len(triangles)


def main():
    args = parse_args()
    source = args.source_blend.expanduser().resolve()
    work = args.work_dir.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    work.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.context.scene
    missing = [name for name in (HAMMOCK_NAME, BALL_NAME) if name not in bpy.data.objects]
    if missing:
        raise RuntimeError(f"Missing required objects: {missing}")

    scene.frame_start = 1
    scene.frame_end = 96
    scene.render.fps = 24
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene["pcve_scene_id"] = "rigid_elastic_beach_ball_hammock_mpm"
    scene["pcve_category"] = "rigid_elastic"
    scene["pcve_solver"] = "Taichi MLS-MPM fixed-corotated elasticity"
    scene["pcve_blender_cloth_used"] = False
    scene["pcve_strict_two_way_contact"] = True

    surface_path = work / "mpm_hammock_surface.npz"
    vertex_count, triangle_count = export_surface(bpy.data.objects[HAMMOCK_NAME], surface_path)
    scene_path = work / "scene.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))

    spec = {
        "scene_id": "rigid_elastic_beach_ball_hammock_mpm",
        "category": "rigid_elastic",
        "units": "m, kg, s",
        "assets": {
            "source_blend": {
                "path": str(source),
                "sha256": sha256(source),
                "source": "Sketchfab: Let's go to the beach! - Beach themed diorama",
                "model_uid": "b8784396e5f6424e88b036949164a473",
                "redistributed_with_code": False,
            }
        },
        "physics": {
            "elastic_body": HAMMOCK_NAME,
            "rigid_body": BALL_NAME,
            "gravity_m_s2": [0.0, 0.0, -9.81],
            "young_modulus_pa": 15000.0,
            "poisson_ratio": 0.30,
            "hammock_density_kg_m3": 6.0,
            "numerical_thickness_m": 0.15,
            "ball_radius_m": 0.16,
            "ball_mass_kg": 0.25,
            "ball_initial_velocity_m_s": [0.0, 0.0, -1.0],
            "ball_start_xy_m": [0.80, -8.92],
            "ball_lateral_translation_locked": False,
        },
        "simulation_quality": {
            "solver": "Taichi MLS-MPM fixed-corotated elasticity",
            "grid_resolution": 64,
            "substeps_per_frame": 100,
            "pre_roll_seconds": 4.0,
            "surface_vertex_count": vertex_count,
            "surface_triangle_count": triangle_count,
            "frames": 96,
            "fps": 24,
        },
        "appearance": {
            "source_scene_camera_and_lighting_preserved": True,
            "photo_background_used": False,
        },
        "render": {"resolution": [1280, 720], "frames": 96, "fps": 24},
        "coupling": {
            "method": "MPM grid-node non-penetration with full 3D rigid-sphere impulse feedback",
            "strict_two_way_contact": True,
        },
        "status": "built_unsimulated",
    }
    (work / "scene_spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"PCVE_SCENE={scene_path}", flush=True)
    print(f"PCVE_MPM_SURFACE={surface_path}", flush=True)


if __name__ == "__main__":
    main()

