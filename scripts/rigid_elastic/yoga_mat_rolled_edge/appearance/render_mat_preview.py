"""Remote-only Blender/Cycles review render for the accepted mat preparation."""
from pathlib import Path
import argparse
import json
import socket
import sys
import time

if sys.platform != "linux":
    raise RuntimeError("workspace rule: Blender may run only on the configured remote Linux server")

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0,str(ROOT/"scripts"))
from pcve_assets import asset


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


def principled(name, color, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def mat_material():
    mat = principled("Dense closed-cell PVC — muted sage", (0.035, 0.20, 0.16), 0.78)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 820.0
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.72
    links.new(coord.outputs["Object"], noise.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.00007
    bump.inputs["Strength"].default_value = 0.24
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def floor_material():
    paths = [
        asset("scenes/yoga_mat_rolled_edge/rectangular_parquet_diff_2k.jpg"),
        asset("scenes/yoga_mat_rolled_edge/rectangular_parquet_rough_2k.jpg"),
        asset("scenes/yoga_mat_rolled_edge/rectangular_parquet_nor_gl_2k.jpg"),
    ]
    if not all(path.exists() for path in paths):
        raise FileNotFoundError("audited Poly Haven rectangular_parquet 2K maps are required")
    mat = principled("Poly Haven rectangular parquet 2K (CC0)", (0.25, 0.10, 0.035), 0.38)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2.7, 2.7, 2.7)
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    textures = []
    for path in paths:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(path), check_existing=True)
        tex.image.pack()
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        textures.append(tex)
    textures[1].image.colorspace_settings.name = "Non-Color"
    textures[2].image.colorspace_settings.name = "Non-Color"
    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.48
    links.new(textures[0].outputs["Color"], bsdf.inputs["Base Color"])
    links.new(textures[1].outputs["Color"], bsdf.inputs["Roughness"])
    links.new(textures[2].outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def cube(name, location, scale, material, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        modifier = obj.modifiers.new("Real edge radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--width", type=int, default=1600)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)

    started = time.monotonic()
    cache = np.load(args.cache, allow_pickle=False)
    config = json.loads((args.cache.parent / "preparation_config.json").read_text(encoding="utf-8"))
    positions = cache["positions"][-1]
    faces = cache["faces"]
    thickness = float(config["mat"]["thickness_m"])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.012
    scene.cycles.max_bounces = 10
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type in {"OPTIX", "CUDA"}
    except Exception as exc:
        print("GPU_DEVICE_WARNING", repr(exc), flush=True)
    scene.render.resolution_x = args.width
    scene.render.resolution_y = round(args.width * 9 / 16)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.7

    world = bpy.data.worlds.new("Soft apartment daylight")
    world.use_nodes = True
    scene.world = world
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.055, 0.065, 0.075, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.18

    floor = floor_material()
    wall = principled("Warm plaster", (0.58, 0.53, 0.45), 0.86)
    trim = principled("Warm white paint", (0.78, 0.76, 0.70), 0.38)
    cube("Hardwood floor", (0.45, 0.0, -0.035), (2.45, 1.8, 0.035), floor, 0.001)
    cube("Rear wall", (0.45, 1.55, 1.05), (2.45, 0.05, 1.05), wall, 0.008)
    cube("Skirting", (0.45, 1.49, 0.065), (2.45, 0.022, 0.065), trim, 0.004)

    mesh = bpy.data.meshes.new("Accepted native shell state")
    mesh.from_pydata(positions.tolist(), [], faces.tolist())
    mesh.materials.append(mat_material())
    mat_obj = bpy.data.objects.new("Yoga mat — accepted physical relaxation", mesh)
    bpy.context.collection.objects.link(mat_obj)
    solidify = mat_obj.modifiers.new("Physical 6 mm thickness", "SOLIDIFY")
    solidify.thickness = thickness
    solidify.offset = 0.0
    solidify.use_rim = True
    bevel = mat_obj.modifiers.new("Soft manufactured edge", "BEVEL")
    bevel.width = 0.0012
    bevel.segments = 3
    subdivision = mat_obj.modifiers.new("Render-only surface smoothing", "SUBSURF")
    subdivision.subdivision_type = "CATMULL_CLARK"
    subdivision.levels = 2
    subdivision.render_levels = 2

    for name, location, energy, size, color in (
        ("Window key", (-1.0, -1.0, 2.2), 430, 1.55, (1.0, 0.86, 0.70)),
        ("Room fill", (1.45, -0.55, 1.3), 165, 1.1, (0.62, 0.78, 1.0)),
        ("Ceiling bounce", (0.2, 0.6, 2.4), 260, 1.35, (0.90, 0.94, 1.0)),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = color
        light = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(light)
        light.location = location
        aim(light, (-0.25, 0.0, 0.04))

    camera_data = bpy.data.cameras.new("Review camera")
    camera = bpy.data.objects.new("Review camera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    camera_data.sensor_width = 36
    camera_data.dof.use_dof = True
    camera_data.dof.focus_object = mat_obj
    camera_data.dof.aperture_fstop = 8.0

    args.out.mkdir(parents=True, exist_ok=False)
    views = {
        "full_profile": {"location": (0.45, -3.05, 0.34), "target": (0.45, 0.0, 0.035), "lens": 55},
        "curl_detail": {"location": (-0.33, -1.18, 0.16), "target": (-0.32, 0.0, 0.025), "lens": 72},
    }
    for name, view in views.items():
        camera.location = view["location"]
        camera_data.lens = view["lens"]
        aim(camera, view["target"])
        scene.render.filepath = str(args.out / f"{name}.png")
        bpy.ops.render.render(write_still=True)

    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out / "mat_preparation_review.blend"), compress=True)
    report = {
        "status": "complete",
        "execution_origin": "remote_server",
        "execution_host": socket.gethostname(),
        "local_blender_used": False,
        "engine": "Blender 4.3.2 Cycles/OptiX",
        "samples": args.samples,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "cache": str(args.cache),
        "views": list(views),
        "assets": ["Poly Haven rectangular_parquet 2K PBR (CC0)"],
        "wall_seconds": time.monotonic() - started,
    }
    (args.out / "render_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PREVIEW_COMPLETE", json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
