"""Remote-only Cycles contact review using the exact collision-ball surface."""
from pathlib import Path
import argparse
import json
import math
import os
import socket
import subprocess
import sys
import time

if sys.platform != "linux":
    raise RuntimeError("workspace rule: Blender may run only on the configured remote Linux server")

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
# Published look: appearance/realism.py sets this to its overlay, run once room, lights and camera exist.
OVERLAY = None
sys.path.insert(0, str(HERE))

# Blender's --python execution keeps the project root as cwd and does not
# reliably add the script directory to sys.path.
from render_mat_preview import aim, cube, floor_material, mat_material, principled


def medicine_ball_material():
    material = principled("Unbranded solid moulded-rubber medicine ball", (0.014, 0.016, 0.017), 0.78)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    coordinate = nodes.new("ShaderNodeTexCoord")
    color_noise = nodes.new("ShaderNodeTexNoise")
    color_noise.inputs["Scale"].default_value = 11.0
    color_noise.inputs["Detail"].default_value = 3.5
    color_noise.inputs["Roughness"].default_value = 0.72
    links.new(coordinate.outputs["UV"], color_noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.28
    ramp.color_ramp.elements[0].color = (0.009, 0.010, 0.011, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.022, 0.025, 0.026, 1.0)
    links.new(color_noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    micro_noise = nodes.new("ShaderNodeTexNoise")
    micro_noise.inputs["Scale"].default_value = 115.0
    micro_noise.inputs["Detail"].default_value = 3.0
    micro_noise.inputs["Roughness"].default_value = 0.78
    links.new(coordinate.outputs["UV"], micro_noise.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.00016
    bump.inputs["Strength"].default_value = 0.46
    links.new(micro_noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def wood_block_material():
    """Procedural sealed beech, scaled to a small household exercise block."""
    material = principled("Sealed beech sliding block", (0.34, 0.16, 0.055), 0.46)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    coordinate = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2.0, 9.0, 13.0)
    links.new(coordinate.outputs["Generated"], mapping.inputs["Vector"])
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 7.0
    wave.inputs["Distortion"].default_value = 6.0
    wave.inputs["Detail"].default_value = 4.0
    wave.inputs["Detail Scale"].default_value = 2.2
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.12, 0.035, 0.008, 1.0)
    ramp.color_ramp.elements[1].color = (0.48, 0.22, 0.055, 1.0)
    links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.00022
    bump.inputs["Strength"].default_value = 0.24
    links.new(wave.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def plaster_material():
    material = principled("Sage limewash plaster", (0.31, 0.42, 0.34), 0.91)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 72.0
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.72
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.20
    ramp.color_ramp.elements[0].color = (0.265, 0.355, 0.285, 1.0)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (0.345, 0.445, 0.365, 1.0)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.00035
    bump.inputs["Strength"].default_value = 0.18
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def walnut_material(name, dark=False):
    """Fine horizontal walnut grain for furniture-scale surfaces."""
    material = principled(name, (0.085, 0.027, 0.008) if dark else (0.15, 0.052, 0.014), 0.46)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    coordinate = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.5, 7.0, 22.0)
    links.new(coordinate.outputs["Generated"], mapping.inputs["Vector"])
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 4.5
    wave.inputs["Distortion"].default_value = 5.0
    wave.inputs["Detail"].default_value = 3.0
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.012, 0.0025, 0.0006, 1.0)
    ramp.color_ramp.elements[1].color = (0.085, 0.018, 0.0035, 1.0)
    links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.00012
    bump.inputs["Strength"].default_value = 0.16
    links.new(wave.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def add_home_context():
    """A grounded sage-wall exercise nook with no legged background furniture."""
    walnut = walnut_material("Smoked walnut cabinetry", dark=True)
    walnut_face = walnut_material("Book-matched walnut sliding fronts")
    linen = principled("Sheer natural linen", (0.73, 0.70, 0.62), 0.88)
    glass = principled("Cool daylight window", (0.26, 0.43, 0.50), 0.22)
    cream = principled("Warm ivory trim", (0.79, 0.75, 0.66), 0.45)
    rattan = principled("Natural woven rattan", (0.42, 0.23, 0.075), 0.73)
    brass = principled("Aged brass", (0.34, 0.19, 0.055), 0.31)

    # A recessed window and asymmetric curtains make this room clearly distinct
    # from the previous plain-wall apartment scene.
    cube("Window daylight", (-1.18, 1.492, 1.22), (0.56, 0.012, 0.62), glass, 0.004)
    for x, z, sx, sz in (
        (-1.18, 0.59, 0.62, 0.035), (-1.18, 1.85, 0.62, 0.035),
        (-1.78, 1.22, 0.035, 0.66), (-0.58, 1.22, 0.035, 0.66),
        (-1.18, 1.22, 0.018, 0.62),
    ):
        cube("Ivory window frame", (x, 1.472, z), (sx, 0.022, sz), cream, 0.003)
    # Multiple rounded folds make the curtains read as fabric rather than
    # suspended rectangular posts.  Their hems finish 25 mm above the floor.
    for side, centers in (("Left", (-1.94, -1.86, -1.78)), ("Right", (-0.56, -0.49, -0.42))):
        for index, x in enumerate(centers, 1):
            cube(f"{side} linen curtain fold {index}", (x, 1.43, 1.0375), (0.055, 0.028, 1.0125), linen, 0.025)

    # The cabinet is carried by a continuous plinth whose lower face is exactly
    # z=0.  There are no legs that can visually float above the floor.
    cube("Grounded cabinet plinth", (1.18, 1.27, 0.035), (0.64, 0.24, 0.035), walnut, 0.006)
    cube("Low walnut cabinet body", (1.18, 1.27, 0.265), (0.68, 0.25, 0.195), walnut, 0.012)
    cube("Cabinet left sliding front", (0.85, 1.005, 0.265), (0.315, 0.012, 0.17), walnut_face, 0.006)
    cube("Cabinet right sliding front", (1.51, 1.005, 0.265), (0.315, 0.012, 0.17), walnut_face, 0.006)
    for x in (0.88, 1.48):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.015, location=(x, 0.986, 0.265))
        bpy.context.object.name = "Aged brass cabinet pull"
        bpy.context.object.data.materials.append(brass)
    cube("Folded linen throw", (1.18, 1.20, 0.49), (0.24, 0.13, 0.025), linen, 0.015)

    # A simple floor basket is also explicitly grounded at z=0.
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.19, depth=0.30, location=(-2.05, 1.18, 0.15))
    basket = bpy.context.object
    basket.name = "Grounded woven exercise-prop basket"
    basket.data.materials.append(rattan)
    bevel = basket.modifiers.new("Rounded woven rim", "BEVEL")
    bevel.width = 0.012
    bevel.segments = 4


def add_foam_roller():
    """High-detail closed-cell EPP foam roller used by the add-object edit."""
    material = principled("Charcoal EPP foam", (0.012, 0.016, 0.020), 0.88)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 180.0
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.82
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.0007
    bump.inputs["Strength"].default_value = 0.55
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=0.075, depth=0.33, location=(-0.05, 0.52, 0.076), rotation=(0.0, 1.57079632679, 0.0))
    roller = bpy.context.object
    roller.name = "Added high-density foam roller"
    roller.data.materials.append(material)
    bevel = roller.modifiers.new("Soft moulded edge", "BEVEL")
    bevel.width = 0.008
    bevel.segments = 5
    return roller


def animated_mat(cache, thickness):
    positions = cache["mat_positions"]
    faces = cache["mat_faces"]
    mesh = bpy.data.meshes.new("Native IPC yoga-mat shell")
    mesh.from_pydata(positions[0].tolist(), [], faces.tolist())
    mesh.materials.append(mat_material())
    obj = bpy.data.objects.new("Yoga mat — native shell replay", mesh)
    bpy.context.collection.objects.link(obj)
    solidify = obj.modifiers.new("Physical 6 mm thickness", "SOLIDIFY")
    solidify.thickness = thickness
    solidify.offset = 0.0
    solidify.use_rim = True
    bevel = obj.modifiers.new("Manufactured edge radius", "BEVEL")
    bevel.width = 0.0012
    bevel.segments = 3
    obj.shape_key_add(name="Basis")
    obj.data.shape_keys.use_relative = False
    for index, state in enumerate(positions):
        key = obj.shape_key_add(name=f"Native_{index:04d}")
        for vertex, coordinate in zip(key.data, state):
            vertex.co = coordinate
    obj.data.shape_keys.eval_time = 10
    obj.data.shape_keys.keyframe_insert("eval_time", frame=1)
    obj.data.shape_keys.eval_time = len(positions) * 10
    obj.data.shape_keys.keyframe_insert("eval_time", frame=len(positions))
    for curve in obj.data.shape_keys.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    return obj


def exact_animated_ball(cache):
    vertices = cache["ball_vertices"]
    faces = cache["ball_faces"]
    transforms = cache["ball_transforms"]
    world_states = np.array([vertices @ transform[:3, :3].T + transform[:3, 3] for transform in transforms])
    mesh = bpy.data.meshes.new("Exact ABD collision surface")
    mesh.from_pydata(world_states[0].tolist(), [], faces.tolist())
    uv_layer = mesh.uv_layers.new(name="Ball spherical UV")
    local_radius = float(np.max(np.linalg.norm(vertices, axis=1)))
    for loop in mesh.loops:
        vertex = vertices[loop.vertex_index]
        u = 0.5 + math.atan2(float(vertex[1]), float(vertex[0])) / (2.0 * math.pi)
        v = 0.5 - math.asin(max(-1.0, min(1.0, float(vertex[2]) / local_radius))) / math.pi
        uv_layer.data[loop.index].uv = (u, v)
    mesh.materials.append(medicine_ball_material())
    obj = bpy.data.objects.new("Medicine ball — exact collision surface", mesh)
    bpy.context.collection.objects.link(obj)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj.shape_key_add(name="Basis")
    obj.data.shape_keys.use_relative = False
    for index, state in enumerate(world_states):
        key = obj.shape_key_add(name=f"ExactNative_{index:04d}")
        for vertex, coordinate in zip(key.data, state):
            vertex.co = coordinate
    obj.data.shape_keys.eval_time = 10
    obj.data.shape_keys.keyframe_insert("eval_time", frame=1)
    obj.data.shape_keys.eval_time = len(world_states) * 10
    obj.data.shape_keys.keyframe_insert("eval_time", frame=len(world_states))
    for curve in obj.data.shape_keys.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    return obj


def exact_animated_wood_block(cache):
    if "has_wood_block" not in cache or not bool(cache["has_wood_block"][0]):
        return None
    vertices = cache["wood_block_vertices"]
    faces = cache["wood_block_faces"]
    transforms = cache["wood_block_transforms"]
    world_states = np.array([vertices @ transform[:3, :3].T + transform[:3, 3] for transform in transforms])
    mesh = bpy.data.meshes.new("Exact ABD wood-block collision surface")
    mesh.from_pydata(world_states[0].tolist(), [], faces.tolist())
    mesh.materials.append(wood_block_material())
    obj = bpy.data.objects.new("Added sliding wood block — exact collision surface", mesh)
    bpy.context.collection.objects.link(obj)
    obj.shape_key_add(name="Basis")
    obj.data.shape_keys.use_relative = False
    for index, state in enumerate(world_states):
        key = obj.shape_key_add(name=f"ExactNative_{index:04d}")
        for vertex, coordinate in zip(key.data, state):
            vertex.co = coordinate
    obj.data.shape_keys.eval_time = 10
    obj.data.shape_keys.keyframe_insert("eval_time", frame=1)
    obj.data.shape_keys.eval_time = len(world_states) * 10
    obj.data.shape_keys.keyframe_insert("eval_time", frame=len(world_states))
    for curve in obj.data.shape_keys.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    return obj


def minimum_world_z(vertices, transform):
    return float(np.min(vertices @ transform[:3, :3].T + transform[:3, 3], axis=0)[2])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--all-contact-frames", action="store_true")
    parser.add_argument("--single-frame-index", type=int, help="zero-based diagnostic frame for a quick material/lighting review")
    parser.add_argument("--scene-edit", choices=("none", "add_foam_roller", "delete_skirting", "delete_mat"), default="none")
    parser.add_argument("--device", choices=("OPTIX", "CPU"), default="OPTIX", help="CPU renders the same scene without a GPU")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    cache = np.load(args.cache, allow_pickle=False)
    config = json.loads((args.cache.parent / "simulation_config.json").read_text(encoding="utf-8"))
    report = json.loads((args.cache.parent / "simulation_report.json").read_text(encoding="utf-8"))
    vertices = cache["ball_vertices"]
    transforms = cache["ball_transforms"]
    exact_gaps = np.array([minimum_world_z(vertices, transform) for transform in transforms])
    recorded_gaps = np.array([row["ball_bottom_gap_m"] for row in report["rows"]])
    if float(np.max(np.abs(exact_gaps - recorded_gaps))) > 1e-9:
        raise RuntimeError("renderer collision-surface gap differs from simulation report")
    if exact_gaps[0] > 0.001:
        raise RuntimeError("first recorded ball is visibly above the floor")

    positions = cache["mat_positions"]
    mat_present = bool(config.get("mat_present", True))
    ball_x = transforms[:, 0, 3]
    radius = float(config["ball"]["radius_m"])
    airborne_apex = int(np.argmax(exact_gaps))
    if mat_present:
        grid_y = int(config["simulation"]["grid_y"])
        curl_count = int(config["mesh"]["curl_samples"]) * grid_y
        curl_peak = positions[:, :curl_count, 2].max(axis=1)
        tip_x = positions[:, :grid_y, 0].mean(axis=1)
        contact = int(np.argmin(np.abs(ball_x + radius - tip_x)))
        peak = int(np.argmin(curl_peak))
        indices = sorted(set((0, max(0, contact - 1), contact, peak, airborne_apex, len(transforms) - 1)))
    else:
        indices = sorted(set((0, airborne_apex, len(transforms) - 1)))
    if args.all_contact_frames:
        indices = list(range(len(transforms)))
    elif args.single_frame_index is not None:
        if not 0 <= args.single_frame_index < len(transforms):
            raise ValueError("single-frame-index is outside the cached frame range")
        indices = [args.single_frame_index]

    started = time.monotonic()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = len(transforms)
    scene.render.fps = int(round(1.0 / float(cache["times"][1] - cache["times"][0])))   # 24 for the benchmark
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.012
    if args.device == "CPU":
        # Same scene on the CPU (for re-renders when no GPU is free); no GPU is bound.
        scene.cycles.device = "CPU"
        pci_bus = None
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "CPU"
    else:
        selected_gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
        if not selected_gpu.startswith("GPU-"):
            raise RuntimeError("render requires an explicit stable GPU UUID")
        pci_bus = subprocess.check_output(["nvidia-smi", "--id="+selected_gpu, "--query-gpu=pci.bus_id", "--format=csv,noheader"], text=True).strip().split(".")[0][-10:].lower()
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "OPTIX"
            prefs.get_devices()
            for device in prefs.devices:
                device.use = device.type == "OPTIX" and pci_bus in device.id.lower()
            if not any(device.use for device in prefs.devices):
                raise RuntimeError("selected GPU PCI identity is absent from Cycles devices")
        except Exception as exc:
            raise RuntimeError("cannot bind Cycles to the selected idle GPU") from exc
    scene.render.resolution_x = args.width
    scene.render.resolution_y = round(args.width * 9 / 16)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.7
    world = bpy.data.worlds.new("Soft apartment daylight")
    world.use_nodes = True
    scene.world = world
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.055, 0.065, 0.075, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.18

    cube("Hardwood floor", (0.35, 0.0, -0.035), (2.5, 1.8, 0.035), floor_material(), 0.001)
    cube("Sage limewash rear wall", (0.35, 1.55, 1.05), (2.5, 0.05, 1.05), plaster_material(), 0.008)
    if args.scene_edit != "delete_skirting":
        cube("Skirting", (0.35, 1.49, 0.065), (2.5, 0.022, 0.065), principled("Warm white paint", (0.78, 0.76, 0.70), 0.38), 0.004)
    if args.scene_edit == "add_foam_roller":
        add_foam_roller()
    add_home_context()
    mat_obj = animated_mat(cache, float(config["mat"]["thickness_m"])) if mat_present else None
    ball_obj = exact_animated_ball(cache)
    if "ball_present" in cache.files and not bool(cache["ball_present"][0]):
        # DELETE ball: the ball is not rendered; its static record stays only as the camera's focus target.
        ball_obj.hide_render = True
    block_obj = exact_animated_wood_block(cache)

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

    camera_data = bpy.data.cameras.new("Low contact review camera")
    camera = bpy.data.objects.new("Low contact review camera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    camera_data.sensor_width = 36
    camera_data.dof.use_dof = True
    camera_data.dof.focus_object = ball_obj
    camera_data.dof.aperture_fstop = 9.0
    if OVERLAY is not None:
        OVERLAY(scene, args, ball_obj)
    args.out.mkdir(parents=True, exist_ok=False)
    views = {
        "profile": ((-0.35, -4.10, 0.35), (-0.35, 0.0, 0.045), 58),
        "contact": ((-0.35, -2.65, 0.27), (-0.35, 0.0, 0.045), 55),
    }
    if args.all_contact_frames:
        views = {"contact": views["contact"]}
    outputs = []
    for view_name, (location, target, lens) in views.items():
        camera.location = location
        camera_data.lens = lens
        aim(camera, target)
        for index in indices:
            scene.frame_set(index + 1)
            path = args.out / f"{view_name}_frame_{index + 1:04d}.png"
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            outputs.append(path.name)
    if OVERLAY is None:
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(args.out / "source_contact_review.blend"), compress=True)
    gpu_uuid = os.environ.get("CUDA_VISIBLE_DEVICES")
    result = {
        "status": "complete",
        "execution_origin": "remote_server" if OVERLAY is None else "local_workstation",
        "execution_host": socket.gethostname(),
        "worker_ip": None,
        "gpu_uuid": gpu_uuid,
        "gpu_pci_bus": pci_bus,
        "cycles_selected_devices": [{"name": device.name, "id": device.id, "type": device.type} for device in prefs.devices if device.use],
        "local_blender_used": OVERLAY is not None,
        "engine": "Blender 4.3.2 Cycles/" + ("CPU" if args.device == "CPU" else "OptiX"),
        "visual_ball_geometry": "exact ABD collision surface with unbranded moulded-rubber material; no badge or decal",
        "visual_wood_block_geometry": None if block_obj is None else "exact ABD collision surface with procedural sealed-beech grain",
        "visual_mat_geometry": None if mat_obj is None else "exact nonlinear-shell replay with physical thickness",
        "first_frame_exact_ball_floor_gap_m": float(exact_gaps[0]),
        "maximum_gap_report_replay_error_m": float(np.max(np.abs(exact_gaps - recorded_gaps))),
        "selected_zero_based_indices": indices,
        "selected_times_s": [float(cache["times"][index]) for index in indices],
        "outputs": outputs,
        "render_mode": "all_contact_frames" if args.all_contact_frames else "diagnostic_stills",
        "scene_edit": args.scene_edit,
        "fps": scene.render.fps,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "camera": {"matrix_world": [list(row) for row in camera.matrix_world], "lens_mm": camera_data.lens,
                   "sensor_width_mm": camera_data.sensor_width, "sensor_fit": camera_data.sensor_fit,
                   "shift_x": camera_data.shift_x, "shift_y": camera_data.shift_y},
        "assets": ["Poly Haven rectangular_parquet 2K PBR (CC0)", "procedural moulded-rubber medicine-ball grip", "sage limewash exercise nook with grounded plinth cabinetry"],
        "wall_seconds": time.monotonic() - started,
    }
    (args.out / "render_report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("REVIEW_COMPLETE", json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
