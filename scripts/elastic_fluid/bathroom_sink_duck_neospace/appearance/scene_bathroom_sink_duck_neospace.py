"""Build the bathroom sink scene with the rubber duck resting in the basin.

The scene holds the room, the camera and the undeformed visible duck; the Genesis steps take the duck geometry
from it (duck_*), simulate the water and the duck, and swap both back in at render time
(render_*, which also applies the look).
    blender -b --python scene_bathroom_sink_duck_neospace.py -- --work-dir WORK
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import asset


DEFAULT_BATHROOM = asset("sketchfab/bathroom_rev1_neospace/bathroom_rev1.glb")
DEFAULT_DUCK = asset("elastic_fluid/elastic_fluid_duck/scene.blend")
DUCK_LONG_AXIS_M = 0.12
BASIN_CONTACT_Z_M = 0.806
DUCK_CROWN_XY = (0.600, 1.683)       # as far towards the back wall as the basin allows; the stream lands on the head


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bathroom-asset", type=Path, default=DEFAULT_BATHROOM)
    parser.add_argument("--duck-asset", type=Path, default=DEFAULT_DUCK)
    parser.add_argument("--work-dir", type=Path, required=True)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def configure_camera(scene):
    camera_data = bpy.data.cameras.new("BathroomSinkCameraData")
    camera_data.lens = 52
    camera_data.sensor_width = 36
    camera = bpy.data.objects.new("BathroomSinkCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (1.34, 1.02, 1.14)
    aim(camera, (0.61, 1.68, 0.86))
    scene.camera = camera


def append_duck(path):
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        if "duck_visual" not in src.objects:
            raise RuntimeError(f"duck_visual missing from {path}")
        dst.objects = ["duck_visual"]
    duck = dst.objects[0]
    bpy.context.scene.collection.objects.link(duck)
    duck.name = "ElasticRubberDuck"
    duck.animation_data_clear()
    duck.parent = None
    for modifier in list(duck.modifiers):
        duck.modifiers.remove(modifier)

    scale = DUCK_LONG_AXIS_M / max(duck.dimensions.x, duck.dimensions.y)
    duck.scale = (scale, scale, scale)
    bpy.context.view_layer.objects.active = duck
    duck.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    duck.select_set(False)

    lo_z = min(vertex.co.z for vertex in duck.data.vertices)
    # Start from a useful facing direction, then solve the final XY translation from the imported crown geometry.
    duck.location = (0.607, 1.713, BASIN_CONTACT_Z_M - lo_z)
    duck.rotation_euler[2] = math.radians(132)
    bpy.context.view_layer.update()
    world = [duck.matrix_world @ vertex.co for vertex in duck.data.vertices]
    z_max = max(point.z for point in world)
    top = [point for point in world if point.z >= z_max - 0.018]
    crown = sum(top, Vector((0.0, 0.0, 0.0))) / len(top)
    duck.location.x += DUCK_CROWN_XY[0] - crown.x
    duck.location.y += DUCK_CROWN_XY[1] - crown.y
    bpy.context.view_layer.update()
    duck["pcve_world_long_axis_m"] = DUCK_LONG_AXIS_M
    duck["pcve_basin_contact_z_m"] = BASIN_CONTACT_Z_M
    return duck


def write_spec(work, bathroom, duck_path, duck):
    spec = {
        "scene_id": "elastic_fluid_bathroom_sink_duck_neospace",
        "category": "elastic_fluid",
        "units": "m, kg, s",
        "event": "running bathroom faucet strikes and deforms a rubber duck resting inside the sink basin",
        "revision": "genesis",
        "assets": {
            "environment": {"path": str(bathroom), "sha256": sha256(bathroom), "title": "Bathroom rev1", "author": "Neospace",
                            "source": "https://sketchfab.com/3d-models/bathroom-rev1-1ead93001d9d44d9a025e3dbbf04c52a",
                            "license": "CC-BY-4.0"},
            "duck": {"path": str(duck_path), "sha256": sha256(duck_path), "source": "Sketchfab rubber duck f1de4fc",
                     "author": "Ikki_3d", "license": "CC-BY-4.0"},
        },
        "dimensions": {
            "imported_room_bbox_m": [3.255333, 4.853523, 3.169577],
            "sink_countertop_bbox_m": [0.500091, 1.001841, 0.140296],
            "duck_long_axis_m": DUCK_LONG_AXIS_M,
            "duck_basin_contact_z_m": BASIN_CONTACT_Z_M,
            "duck_origin_m": [round(duck.location.x, 7), round(duck.location.y, 7)],
        },
        "simulation": "simulate_bathroom_sink_duck_neospace.py (Genesis MPM duck + DFSPH water, two-way coupled)",
        "appearance": {"camera": "BathroomSinkCamera", "all_foreground_geometry_3d": True, "photo_background_used": False,
                       "original_environment_materials_preserved": True},
        "render": {"resolution": [1280, 720], "engine": "CYCLES", "duration_seconds": 4,
                   "look": "look_bathroom_sink_duck_neospace.apply_look (applied at render time)"},
        "status": "built",
    }
    (work / "scene_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    bathroom = args.bathroom_asset.expanduser().resolve()
    duck_path = args.duck_asset.expanduser().resolve()
    work = args.work_dir.expanduser().resolve()
    for path in (bathroom, duck_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    work.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(bathroom))
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 96
    scene.render.fps = 24
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    configure_camera(scene)
    duck = append_duck(duck_path)

    scene["pcve_scene_id"] = "elastic_fluid_bathroom_sink_duck_neospace"
    scene["pcve_photo_background_used"] = False
    scene["pcve_real_asset_environment"] = True
    scene["pcve_coupling"] = "Genesis two-way: MPM duck and DFSPH water (simulate_*)"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    write_spec(work, bathroom, duck_path, duck)

    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(work / "scene.blend"))
    print(f"PCVE_SCENE={work / 'scene.blend'}", flush=True)


if __name__ == "__main__":
    main()
