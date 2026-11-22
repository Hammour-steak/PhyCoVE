#!/usr/bin/env python3
"""Build and render the PCVE wind-driven flag scene in Blender 4.3."""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector


def parse_args():
    argv = []
    if "--" in __import__("sys").argv:
        argv = __import__("sys").argv[__import__("sys").argv.index("--") + 1 :]
    p = argparse.ArgumentParser()
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--scene", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--assets-root", type=Path, required=True)
    p.add_argument("--environment", type=Path, required=True)
    p.add_argument("--flag-asset", type=Path, required=True)
    p.add_argument("--flag-texture-dir", type=Path, required=True)
    p.add_argument("--frames", default="1-96")
    p.add_argument("--preview", action="store_true")
    return p.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.materials, bpy.data.curves, bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def principled_material(name, color, rough=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def add_box(name, location, scale, material, bevel=0.02):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("Small realistic edge radius", "BEVEL")
        mod.width = bevel
        mod.segments = 3
    obj.data.materials.append(material)
    return obj


def add_cylinder(name, radius, depth, location, material, vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def add_uv_sphere(name, radius, location, material, seg=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def add_curve(name, points, bevel, material, cyclic=False):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = bevel
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for p, xyz in zip(spline.points, points):
        p.co = (*xyz, 1.0)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def un_flag_material(texture_dir: Path):
    """Use the cloth portion of the BlenderKit asset's original PBR atlas."""
    mat = bpy.data.materials.new("BlenderKit UN flag PBR cloth")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    # The source atlas stores the UN-blue cloth in its lower two-thirds.
    mapping.inputs["Scale"].default_value = (1.0, 0.655, 1.0)
    links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])

    files = {
        "base": "Standing_flag_mat_BaseColor.jpg.022.png",
        "metal": "Standing_flag_mat_Metallic.jpg.022.png",
        "normal": "Standing_flag_mat_Normal.jpg.022.png",
        "rough": "Standing_flag_mat_Roughness.jpg.022.png",
    }

    def image_node(key, label, non_color=False):
        node = nodes.new("ShaderNodeTexImage")
        node.label = label
        node.image = bpy.data.images.load(str((texture_dir / files[key]).resolve()), check_existing=True)
        if non_color:
            node.image.colorspace_settings.name = "Non-Color"
        node.extension = "EXTEND"
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node

    base = image_node("base", "Original BlenderKit base color")
    metal = image_node("metal", "Original BlenderKit metallic", True)
    normal_tex = image_node("normal", "Original BlenderKit normal", True)
    rough = image_node("rough", "Original BlenderKit roughness", True)
    links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(metal.outputs["Color"], bsdf.inputs["Metallic"])
    links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.42
    links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    if "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = 0.16
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (0.11, 0.43, 0.69, 1.0)
    return mat


def build_flag(cache, texture_dir: Path):
    vertices = cache["vertices"]
    faces = cache["faces"]
    uvs = cache["uvs"]
    mesh = bpy.data.meshes.new("GenesisFlagSurface")
    mesh.from_pydata(vertices[0].tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new("Flag_Genesis_FEM", mesh)
    bpy.context.collection.objects.link(obj)
    obj.shape_key_add(name="Basis")
    for frame in range(vertices.shape[0]):
        key = obj.shape_key_add(name=f"F{frame+1:04d}")
        for i, co in enumerate(vertices[frame]):
            key.data[i].co = co
        key.value = 0.0
    # Integer frames reproduce the Genesis cache exactly. Linear interpolation
    # between them gives the renderer continuous sub-frame motion and usable
    # motion blur instead of a subtly stepped 24 fps shape-key sequence.
    for i, key in enumerate(obj.data.shape_keys.key_blocks[1:], start=1):
        key.value = 0.0
        key.keyframe_insert("value", frame=max(0, i - 1))
        key.value = 1.0
        key.keyframe_insert("value", frame=i)
        key.value = 1.0 if i == vertices.shape[0] else 0.0
        key.keyframe_insert("value", frame=i + 1)
    if obj.data.shape_keys.animation_data and obj.data.shape_keys.animation_data.action:
        for curve in obj.data.shape_keys.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    # UVs are per-loop; source vertices have one consistent UV each.
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            uv_layer.data[li].uv = uvs[mesh.loops[li].vertex_index]
    obj.data.materials.append(un_flag_material(texture_dir))
    for poly in mesh.polygons:
        poly.material_index = 0
        poly.use_smooth = True
    solid = obj.modifiers.new("Double-sided cloth thickness", "SOLIDIFY")
    solid.thickness = 0.001
    solid.offset = 0.0
    solid.use_rim = True
    subd = obj.modifiers.new("Render subdivision", "SUBSURF")
    subd.levels = 1
    subd.render_levels = 1
    return obj


def setup_world(environment: Path):
    world = bpy.data.worlds.new("Real rooftop overcast HDRI")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputWorld")
    bg = nodes.new("ShaderNodeBackground")
    env = nodes.new("ShaderNodeTexEnvironment")
    mapping = nodes.new("ShaderNodeMapping")
    tex = nodes.new("ShaderNodeTexCoord")
    # A tone-mapped equirectangular copy avoids an OpenImageIO/GPU HDR texture
    # issue on this host while retaining the real rooftop/city photography.
    env.image = bpy.data.images.load(str(environment.resolve()), check_existing=True)
    mapping.inputs["Rotation"].default_value[2] = math.radians(202.0)
    bg.inputs["Strength"].default_value = 0.88
    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], out.inputs["Surface"])


def append_blenderkit_stand(asset_path: Path):
    """Append the source asset, retaining only its connected pole/base component."""
    with bpy.data.libraries.load(str(asset_path.resolve()), link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    loaded = [obj for obj in data_to.objects if obj is not None]
    mesh_obj = next(obj for obj in loaded if obj.type == "MESH")
    if mesh_obj.name not in bpy.context.scene.objects:
        bpy.context.collection.objects.link(mesh_obj)
    mesh_obj.parent = None

    bm = bmesh.new()
    bm.from_mesh(mesh_obj.data)
    remaining = set(bm.verts)
    components = []
    while remaining:
        seed = remaining.pop()
        component = {seed}
        stack = [seed]
        while stack:
            vert = stack.pop()
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                if other in remaining:
                    remaining.remove(other)
                    component.add(other)
                    stack.append(other)
        components.append(component)
    keep = min(components, key=len)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v not in keep], context="VERTS")
    bm.to_mesh(mesh_obj.data)
    bm.free()
    mesh_obj.data.update()
    mesh_obj.name = "BlenderKit_UN_ceremonial_flag_stand"
    mesh_obj.location = (0.0, 0.0, 0.0)
    # Extend only the shaft. Keep the foot and finial at their source scale so
    # the higher outdoor composition does not look like a vertically stretched asset.
    source_shaft_top = 2.30
    target_shaft_top = 3.65
    base_top = 0.15
    shaft_scale = (target_shaft_top - base_top) / (source_shaft_top - base_top)
    for vert in mesh_obj.data.vertices:
        z = vert.co.z
        if z <= base_top:
            continue
        if z < source_shaft_top:
            vert.co.z = base_top + (z - base_top) * shaft_scale
        else:
            vert.co.z = z + (target_shaft_top - source_shaft_top)
    mesh_obj.data.update()
    for poly in mesh_obj.data.polygons:
        poly.use_smooth = True
    for obj in loaded:
        if obj != mesh_obj and obj.name in bpy.context.scene.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    return mesh_obj


def build_environment(flag_asset: Path):
    concrete = principled_material("Weathered rooftop concrete", (0.20, 0.21, 0.21, 1), 0.82)
    steel = principled_material("Brushed marine steel", (0.23, 0.26, 0.28, 1), 0.25, 0.82)
    dark_steel = principled_material("Dark galvanized fittings", (0.035, 0.045, 0.052, 1), 0.30, 0.72)
    glass = principled_material("Rooftop safety glass", (0.10, 0.14, 0.15, 1), 0.16, 0.0)
    gbsdf = glass.node_tree.nodes.get("Principled BSDF")
    gbsdf.inputs["Transmission Weight"].default_value = 0.80
    gbsdf.inputs["IOR"].default_value = 1.46

    # Matching rooftop foreground integrates the photographic HDRI with the scene.
    add_box("Rooftop deck", (0.0, -0.5, -0.12), (9.0, 4.0, 0.12), concrete, 0.025)
    add_box("Dark parapet", (0.0, 2.55, 0.42), (9.0, 0.10, 0.42), dark_steel, 0.025)
    for x in np.arange(-7.2, 7.3, 1.8):
        add_cylinder(f"Glass rail post {x:.1f}", 0.025, 0.80, (float(x), 2.48, 1.20), steel, 24)
    glass_panel = add_box("Glass wind screen", (0.0, 2.50, 1.23), (7.8, 0.012, 0.37), glass, 0.006)
    glass_panel.visible_shadow = False
    append_blenderkit_stand(flag_asset)

    # Expansion joints and service boxes make the foreground read at full scale.
    joint = principled_material("Expansion joints", (0.055, 0.05, 0.042, 1), 0.9)
    for x in (-5.5, -2.0, 2.5, 6.0):
        add_box(f"Expansion joint {x:.1f}", (x, -0.6, 0.006), (0.012, 2.7, 0.006), joint, 0.0)
    add_box("Rooftop service box", (-2.7, 1.35, 0.38), (0.46, 0.30, 0.38), dark_steel, 0.035)


def setup_camera_and_lights():
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (5.15, -9.35, 2.25)
    cam_data.lens = 55.0
    cam_data.sensor_width = 36.0
    cam_data.dof.use_dof = True
    cam_data.dof.focus_distance = 10.65
    cam_data.dof.aperture_fstop = 5.6
    look_at(cam, (0.64, 0.0, 1.90))

    sun_data = bpy.data.lights.new("Late afternoon sun", "SUN")
    sun_data.energy = 1.5
    sun_data.angle = math.radians(7.0)
    sun = bpy.data.objects.new("Late afternoon sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(42), math.radians(-12), math.radians(148))

    area_data = bpy.data.lights.new("Soft sea bounce", "AREA")
    area_data.energy = 220.0
    area_data.shape = "DISK"
    area_data.size = 5.0
    area_data.color = (0.56, 0.72, 1.0)
    area = bpy.data.objects.new("Soft sea bounce", area_data)
    bpy.context.collection.objects.link(area)
    area.location = (-2.5, 3.8, 5.2)
    look_at(area, (0.75, 0.0, 2.65))

    key_data = bpy.data.lights.new("Warm grazing cloth key", "AREA")
    key_data.energy = 360.0
    key_data.shape = "RECTANGLE"
    key_data.size = 3.0
    key_data.size_y = 1.2
    key_data.color = (1.0, 0.70, 0.47)
    key = bpy.data.objects.new("Warm grazing cloth key", key_data)
    bpy.context.collection.objects.link(key)
    key.location = (4.2, -4.1, 5.4)
    look_at(key, (0.75, 0.0, 2.75))


def configure_render(out_dir: Path, preview: bool, frame_start: int, frame_end: int):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 640 if preview else 1280
    scene.render.resolution_y = 360 if preview else 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.fps = 24
    scene.frame_start = frame_start
    scene.frame_end = frame_end
    scene.render.filepath = str(out_dir / "frames" / "frame_")
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.filepath = str(out_dir / "frames" / "frame_")
    scene.render.resolution_percentage = 100
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.image_settings.color_management = "FOLLOW_SCENE"
    scene.render.use_compositing = True
    scene.render.use_sequencer = False
    scene.render.filepath = str(out_dir / "frames" / "frame_")
    if hasattr(scene.render, "use_motion_blur"):
        scene.render.use_motion_blur = True
    # Blender appends the four-digit frame number automatically.


def main():
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "frames").mkdir(parents=True, exist_ok=True)
    start_s, end_s = args.frames.split("-", 1)
    frame_start, frame_end = int(start_s), int(end_s)
    started = time.monotonic()
    cache = np.load(args.cache)
    clear_scene()
    setup_world(args.environment)
    build_environment(args.flag_asset)
    flag = build_flag(cache, args.flag_texture_dir)
    setup_camera_and_lights()
    configure_render(args.out, args.preview, frame_start, frame_end)
    scene = bpy.context.scene
    scene.frame_set(frame_start)
    args.scene.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.scene))
    bpy.ops.render.render(animation=True)
    report = {
        "scene": str(args.scene),
        "cache": str(args.cache),
        "frames": [frame_start, frame_end],
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "fps": scene.render.fps,
        "engine": scene.render.engine,
        "render_samples": scene.eevee.taa_render_samples,
        "flag_vertices": len(flag.data.vertices),
        "flag_triangles": len(flag.data.polygons),
        "wall_seconds": time.monotonic() - started,
        "asset_manifest": "BlenderKit 'United Nations Ceremonial flag on stand' by Demycs, royalty-free, asset base 99a75a2f-acd7-4471-a297-2af7fa30e7fc; original pole/base and 1K PBR atlas. Tone-mapped Poly Haven hotel_rooftop_balcony 1K HDRI (CC0).",
    }
    (args.out / "render_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
