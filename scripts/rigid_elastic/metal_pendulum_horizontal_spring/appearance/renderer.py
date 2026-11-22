"""Cycles rendering of integrated horizontal spring compression; never changes the simulation."""

import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import bpy
import numpy as np
from mathutils import Vector

from scene_paths import ASSET_DIR, render_signature


def material(name, color, metal=0.0, rough=0.4):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    return m


def wood(name, dark, light):
    m = material(name, light, 0, 0.43)
    m["grain_material"] = True
    n = m.node_tree.nodes
    links = m.node_tree.links
    p = n.get("Principled BSDF")
    coord = n.new("ShaderNodeTexCoord")
    scale = n.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs[3].default_value = 1 / 1.5
    links.new(coord.outputs["UV"], scale.inputs[0])
    textures = {}
    for kind in ["diff", "rough", "nor_gl"]:
        path = ASSET_DIR / f"wood_table_001_{kind}_2k.jpg"
        img = bpy.data.images.load(str(path), check_existing=True)
        img.colorspace_settings.name = "sRGB" if kind == "diff" else "Non-Color"
        tex = n.new("ShaderNodeTexImage")
        tex.image = img
        tex.projection = "FLAT"
        links.new(scale.outputs[0], tex.inputs["Vector"])
        textures[kind] = tex
    mix = n.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    mix.inputs[2].default_value = (*light, 1)
    links.new(textures["diff"].outputs["Color"], mix.inputs[1])
    links.new(mix.outputs[0], p.inputs["Base Color"])
    rough = n.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 0.0
    rough.inputs["From Max"].default_value = 1.0
    rough.inputs["To Min"].default_value = 0.3
    rough.inputs["To Max"].default_value = 0.55
    links.new(textures["rough"].outputs["Color"], rough.inputs[0])
    links.new(rough.outputs[0], p.inputs["Roughness"])
    normal = n.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.35
    links.new(textures["nor_gl"].outputs[0], normal.inputs["Color"])
    links.new(normal.outputs[0], p.inputs["Normal"])
    return m


def assign(o, m):
    o.data.materials.append(m)
    return o


def cube(name, loc, dims, m, bevel=0.002):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(o, m)
    if m.get("grain_material"):
        mesh = o.data
        uv = mesh.uv_layers.active or mesh.uv_layers.new()
        major = max(range(3), key=lambda k: dims[k])
        for poly in mesh.polygons:
            normal = max(range(3), key=lambda k: abs(poly.normal[k]))
            other = (
                next(k for k in range(3) if k != major and k != normal)
                if normal != major
                else (major + 1) % 3
            )
            along = major if major != normal else (major + 2) % 3
            for li in poly.loop_indices:
                co = mesh.vertices[mesh.loops[li].vertex_index].co
                uv.data[li].uv = (co[other], co[along])
    if bevel:
        b = o.modifiers.new("Rounded manufactured edges", "BEVEL")
        b.width = bevel
        b.segments = 3
        o.modifiers.new("Weighted surface normals", "WEIGHTED_NORMAL")
    return o


def cylinder(name, a, b, r, m, vertices=48):
    a, b = Vector(a), Vector(b)
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=r, depth=d.length, location=(a + b) / 2
    )
    o = bpy.context.object
    o.name = name
    o.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    assign(o, m)
    for f in o.data.polygons:
        f.use_smooth = True
    be = o.modifiers.new("Machined edge radius", "BEVEL")
    be.width = min(r * 0.12, 0.0006)
    be.segments = 3
    o.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return o


def ring(name, a, b, inner, outer, m):
    # Hollow X-axis annulus, with a real clearance for the central moving shaft.
    verts = []
    faces = []
    N = 64
    for x in [a[0], b[0]]:
        for rad in [inner, outer]:
            for j in range(N):
                ang = 2 * math.pi * j / N
                verts.append(
                    (x, a[1] + rad * math.cos(ang), a[2] + rad * math.sin(ang))
                )
    for j in range(N):
        k = (j + 1) % N
        faces.extend(
            [
                (j, k, N + k, N + j),
                (2 * N + j, 3 * N + j, 3 * N + k, 2 * N + k),
                (N + j, N + k, 3 * N + k, 3 * N + j),
                (j, 2 * N + j, 2 * N + k, k),
            ]
        )
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    assign(obj, m)
    for poly in mesh.polygons:
        poly.use_smooth = poly.index % 4 >= 2
    return obj


def screw(name, x, y, z, steel, slot, axis="Z"):
    if axis == "Z":
        cylinder(name, (x, y, z - 0.0005), (x, y, z + 0.0011), 0.0031, steel, 32)
        _o = cube(
            name + " cross slot",
            (x, y, z + 0.00115),
            (0.0042, 0.00065, 0.00025),
            slot,
            0.00015,
        )
    else:
        cylinder(name, (x, y + 0.0005, z), (x, y - 0.0011, z), 0.0031, steel, 32)
        cube(
            name + " slot", (x, y - 0.0012, z), (0.004, 0.00025, 0.00065), slot, 0.0001
        )


def text(name, body, loc, size, m, rot=(0, 0, 0)):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = 0.00002
    cu.align_x = "CENTER"
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    assign(o, m)
    return o


def area(name, loc, target, power, size, color):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.shape = "DISK"
    data.size = size
    data.color = color
    o = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - o.location).to_track_quat("-Z", "Y").to_euler()
    return o


def setup(c, cache):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    p = c["physics"]["pendulum"]
    s = c["physics"]["spring"]
    ap = c["appearance"]
    r = c["render"]
    walnut = wood(
        "Oiled walnut | fine lengthwise grain",
        (0.055, 0.020, 0.008),
        (0.62, 0.38, 0.22),
    )
    oak = wood("Domestic oak tabletop", (0.22, 0.12, 0.055), (0.92, 0.82, 0.64))
    steel = material("Polished steel | GGX", (0.54, 0.58, 0.63), 1, 0.16)
    satin = material("Satin machined stainless", (0.34, 0.38, 0.42), 0.92, 0.3)
    brass = material("Brass bushings", (0.45, 0.27, 0.07), 0.85, 0.28)
    dark = material("Recesses and screw slots", (0.018, 0.023, 0.026), 0.1, 0.38)
    ivory = material("Warm ivory", (0.73, 0.69, 0.57), 0, 0.68)
    # Table and background all share the fixed camera and illumination.
    cube("Oak dining / science table", (0, 0.03, -0.014), (1.4, 0.8, 0.028), oak, 0.006)
    cube(
        "Continuous rear wall",
        (0, 0.48, 0.72),
        (6.0, 0.08, 3.6),
        material("Warm painted plaster", (0.65, 0.68, 0.64), 0, 0.85),
        0.004,
    )
    # Walnut plinth on four rubber feet, table surface z=0.
    cube("Walnut toy base", ap["base_center_m"], ap["base_dimensions_m"], walnut, 0.005)
    for x in [-0.195, 0.125]:
        for y in [-0.065, 0.065]:
            cylinder("Isolating foot", (x, y, 0), (x, y, 0.004), 0.009, dark)
    # Rear support, machined foot plate, and crossbeam.
    cube(
        "Rear walnut upright",
        (-0.17, 0.043, 0.169),
        (0.025, 0.031, 0.292),
        walnut,
        0.003,
    )
    cube(
        "Upright base angle bracket",
        (-0.17, 0.043, 0.026),
        (0.052, 0.065, 0.008),
        satin,
        0.0015,
    )
    cube(
        "Bracket upright heel",
        (-0.17, 0.063, 0.045),
        (0.046, 0.006, 0.035),
        satin,
        0.001,
    )
    for x in [-0.188, -0.152]:
        for y in [0.019, 0.063]:
            screw("Stand mounting screw", x, y, 0.0305, satin, dark)
    cube(
        "Cantilever walnut crossbeam",
        (-0.077, 0.043, 0.321),
        (0.211, 0.031, 0.026),
        walnut,
        0.003,
    )
    cube("Axle bearing plate", (0, 0.023, 0.32), (0.035, 0.007, 0.033), satin, 0.002)
    for x in [-0.012, 0.012]:
        screw("Bearing plate screw", x, 0.0188, 0.32, satin, dark, "Y")
    cylinder(
        "True hinge shaft | axis Y", (0, -0.015, 0.32), (0, 0.062, 0.32), 0.0042, steel
    )
    cylinder("Front brass journal", (0, -0.007, 0.32), (0, 0.017, 0.32), 0.0075, brass)
    cylinder("Axle end cap", (0, -0.019, 0.32), (0, -0.013, 0.32), 0.006, steel)
    # Rigid rod + sphere assembly: cache gives theta only; rotation is at the axle.
    pivot = bpy.data.objects.new("Integrated physical hinge pose", None)
    bpy.context.collection.objects.link(pivot)
    pivot.location = p["pivot_m"]
    rod = cylinder(
        "Slender steel pendulum rod",
        (0, 0, 0),
        (0, 0, -p["rod_length_m"]),
        p["rod_radius_m"],
        satin,
    )
    rod.parent = pivot
    eye = cylinder("Rod hinge eye", (0, -0.005, 0), (0, 0.005, 0), 0.0065, satin)
    eye.parent = pivot
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=64,
        ring_count=40,
        radius=p["ball_radius_m"],
        location=(0, 0, -p["length_m"]),
    )
    ball = bpy.context.object
    ball.name = "Solid steel bob | measured diameter 36 mm"
    assign(ball, steel)
    ball.parent = pivot
    for f in ball.data.polygons:
        f.use_smooth = True
    # Horizontal axial compression module. The backing is bolted to the wood.
    z = s["axis_z_m"]
    anchor = s["fixed_seat_x_m"]
    headx = s["head_rest_center_x_m"]
    hr = s["head_radius_m"]
    ht = s["head_thickness_m"]
    cube(
        "Spring module mounting foot",
        (0.132, 0, 0.0245),
        (0.058, 0.065, 0.005),
        satin,
        0.0015,
    )
    cube(
        "Spring fixed backing", (0.130, 0, 0.065), (0.004, 0.050, 0.080), satin, 0.0012
    )
    for x in [0.112, 0.151]:
        for y in [-0.024, 0.024]:
            screw("Horizontal module mounting screw", x, y, 0.0275, satin, dark)
    # Two gussets make the load path from axial seat into the foot visible.
    for y in [-0.022, 0.022]:
        cube(
            "Backing reinforcing heel",
            (0.139, y, 0.042),
            (0.016, 0.005, 0.030),
            satin,
            0.001,
        )
    ring(
        "Fixed spring end seat",
        (anchor, 0, z),
        (anchor + 0.002, 0, z),
        0.0015,
        0.014,
        satin,
    )
    ring(
        "Brass linear guide bushing",
        (anchor + 0.002, 0, z),
        (anchor + s["bushing_length_m"], 0, z),
        0.00145,
        0.0045,
        brass,
    )
    # The native guide stop prevents extension beyond the unloaded spring length.
    # The long central guide is part of the moving assembly, not a fixed obstacle.
    post = None
    if s["present"]:
        wire = material(
            "Spring steel | satin drawn wire", (0.23, 0.27, 0.31), 0.96, 0.24
        )
        me = bpy.data.meshes.new("Integrated axial mode helix")
        me.from_pydata(
            cache["spring_vertices"][0].tolist(), [], cache["surface_faces"].tolist()
        )
        me.update()
        post = bpy.data.objects.new("Deforming horizontal compression spring", me)
        bpy.context.collection.objects.link(post)
        assign(post, wire)
        for f in me.polygons:
            f.use_smooth = True
        carriage = bpy.data.objects.new("Native guided compression pose", None)
        bpy.context.collection.objects.link(carriage)
        # Geometry uses absolute rest positions; parent translation is the solved q.
        disk = cylinder(
            "Moving aluminium pressure disk",
            (headx - ht / 2, 0, z),
            (headx + ht / 2, 0, z),
            hr,
            material("Brushed aluminium pressure face", (0.56, 0.59, 0.61), 0.91, 0.29),
            96,
        )
        disk.parent = carriage
        guide = cylinder(
            "Moving central guide rod",
            (headx + ht / 2, 0, z),
            (headx + ht / 2 + s["guide_rod_length_m"], 0, z),
            s["guide_rod_radius_m"],
            steel,
        )
        guide.parent = carriage
        ring(
            "Guide rod retaining collar",
            (anchor + s["bushing_length_m"], 0, z),
            (anchor + s["bushing_length_m"] + s["retaining_collar_thickness_m"], 0, z),
            s["guide_rod_radius_m"],
            s["retaining_collar_radius_m"],
            satin,
        ).parent = carriage
        # Small engraved badge and subdued ruler marks establish a domestic science toy.
    cube(
        "Inlaid toy badge",
        (-0.125, -0.054, 0.0223),
        (0.087, 0.029, 0.0006),
        brass,
        0.001,
    )
    text("Badge wordmark", "PENDULUM LAB", (-0.125, -0.052, 0.0227), 0.0052, dark)
    text("Badge subtitle", "AXIAL SPRING", (-0.125, -0.061, 0.0227), 0.0026, dark)
    for i in range(15):
        cube(
            "Engraved scale tick",
            (-0.14 + i * 0.02, -0.075, 0.0222),
            (0.0006, 0.006 if i % 5 == 0 else 0.003, 0.00015),
            ivory,
            0.0001,
        )
    # Background props at life scale, outside the motion silhouette.
    paper = material("Notebook cream paper", (0.76, 0.73, 0.62), 0, 0.85)
    cover = material("Notebook faded navy cloth", (0.035, 0.075, 0.105), 0, 0.75)
    book = cube(
        "A5 science notebook", (0.30, 0.18, 0.008), (0.148, 0.21, 0.014), cover, 0.002
    )
    book.rotation_euler.z = -0.18
    pages = cube(
        "Notebook pages", (0.30, 0.18, 0.012), (0.142, 0.202, 0.008), paper, 0.0007
    )
    pages.rotation_euler.z = -0.18
    pencilmat = material("Natural pencil cedar", (0.54, 0.27, 0.065), 0, 0.42)
    cylinder(
        "Pencil on notebook",
        (0.24, 0.13, 0.022),
        (0.37, 0.19, 0.022),
        0.0034,
        pencilmat,
        6,
    )
    cylinder(
        "Graphite pencil tip",
        (0.37, 0.19, 0.022),
        (0.379, 0.194, 0.022),
        0.0012,
        dark,
        12,
    )
    # Out-of-focus shelving is modeled, not a pasted photograph.
    _shelfmat = material("Painted shelving", (0.58, 0.59, 0.53), 0, 0.65)
    cube("Rear room shelf", (-0.10, 0.40, 0.11), (1.15, 0.14, 0.023), walnut, 0.003)
    for j, (xx, h, co) in enumerate(
        [
            (-0.49, 0.20, (0.17, 0.24, 0.28)),
            (-0.45, 0.23, (0.34, 0.17, 0.09)),
            (-0.40, 0.18, (0.36, 0.38, 0.25)),
            (-0.35, 0.22, (0.55, 0.48, 0.31)),
        ]
    ):
        cube(
            "Background book " + str(j),
            (xx, 0.40, 0.125 + h / 2),
            (0.035, 0.11, h),
            material("Book cloth " + str(j), co, 0, 0.72),
            0.0015,
        )
    potmat = material("Matte terracotta", (0.36, 0.14, 0.065), 0, 0.85)
    cylinder("Background pot", (0.30, 0.39, 0.125), (0.30, 0.39, 0.225), 0.055, potmat)
    leaf = material("Houseplant leaves", (0.05, 0.13, 0.045), 0, 0.6)
    for j in range(9):
        a = j * 2.4
        end = (
            0.30 + 0.065 * math.cos(a),
            0.39 + 0.05 * math.sin(a),
            0.30 + 0.035 * math.sin(j),
        )
        cylinder("Plant stem", (0.30, 0.39, 0.215), end, 0.0014, leaf, 12)
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=12, ring_count=8, radius=1, location=end
        )
        o = bpy.context.object
        o.name = "Plant leaf"
        o.scale = (0.03, 0.012, 0.006)
        o.rotation_euler = (0.4, a, a)
        assign(o, leaf)
        for f in o.data.polygons:
            f.use_smooth = True
    world = bpy.data.worlds.new("Soft room ambience")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.58, 0.66, 0.78, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.28
    sc.world = world
    area(
        "Large left window",
        (-0.55, -0.35, 0.9),
        (0, 0, 0.13),
        45,
        0.65,
        (1.0, 0.88, 0.72),
    )
    area(
        "Cool broad room fill",
        (0.55, 0.05, 0.7),
        (0, 0, 0.18),
        22,
        0.55,
        (0.78, 0.87, 1.0),
    )
    area(
        "Soft strip for steel reflections",
        (-0.1, 0.40, 0.65),
        (0, 0, 0.2),
        25,
        0.35,
        (1.0, 0.97, 0.88),
    )
    bpy.ops.object.camera_add(location=ap["camera_m"])
    cam = bpy.context.object
    cam.name = "Fixed side front camera"
    cam.rotation_euler = (
        (Vector(ap["target_m"]) - cam.location).to_track_quat("-Z", "Y").to_euler()
    )
    cam.data.lens = ap["lens_mm"]
    cam.data.clip_start = 0.01
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = (Vector(ap["target_m"]) - cam.location).length
    cam.data.dof.aperture_fstop = 12.0
    sc.camera = cam
    from appearance.room import upgrade_scene

    upgrade_scene(
        sc,
        c,
        {
            "cube": cube,
            "cylinder": cylinder,
            "ring": ring,
            "text": text,
            "material": material,
        },
    )
    from appearance.surfaces import refine_scene

    refine_scene(
        sc,
        c,
        {
            "cube": cube,
            "cylinder": cylinder,
            "ring": ring,
            "text": text,
            "material": material,
        },
    )
    from appearance.joinery import finish_scene

    finish_scene(
        sc,
        c,
        {
            "cube": cube,
            "cylinder": cylinder,
            "ring": ring,
            "text": text,
            "material": material,
        },
    )
    if ap.get("finish"):
        from appearance.photo_finish import finish_scene

        finish_scene(sc, c, {"cube": cube, "cylinder": cylinder})
    if not p.get("present", True):
        # physics.pendulum.present false (DELETE ball): the swinging pendulum body, i.e. everything carried
        # by the hinge pose (bob, rod, rod eye, eye bush, bob neck), does not exist; the fixed axle stays.
        for obj in list(pivot.children_recursive):
            bpy.data.objects.remove(obj, do_unlink=True)
    sc.render.engine = "CYCLES"
    sc.cycles.samples = r["samples"]
    sc.cycles.adaptive_threshold = r["adaptive_threshold"]
    sc.cycles.use_denoising = True
    if "denoiser" in r:
        sc.cycles.denoiser = r["denoiser"]
    if "filter_glossy" in r:
        sc.cycles.blur_glossy = r["filter_glossy"]
    if "caustics" in r:
        sc.cycles.caustics_reflective = r["caustics"]
        sc.cycles.caustics_refractive = r["caustics"]
    sc.cycles.device = os.environ.get("PCVE_RENDER_DEVICE", "GPU")
    sc.cycles.max_bounces = r["max_bounces"]
    sc.cycles.seed = r["seed"]
    sc.render.resolution_x, sc.render.resolution_y = r["resolution"]
    sc.render.resolution_percentage = 100
    sc.render.fps = r["fps"]
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.use_motion_blur = r["motion_blur"]
    # Blender 4.3 drops objects that come to rest from later frames of one session
    # when persistent data is combined with motion blur.
    sc.render.use_persistent_data = not r["motion_blur"]
    if r["motion_blur"]:
        sc.render.motion_blur_shutter = r["motion_blur_shutter"]
        sc.render.motion_blur_position = "CENTER"
    sc.view_settings.view_transform = r["view_transform"]
    sc.view_settings.look = r["look"]
    sc.view_settings.exposure = r["exposure"]
    sc.frame_start = 1
    sc.frame_end = r["frames"]
    sc.render.film_transparent = False
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "OPTIX"
    except TypeError:
        prefs.compute_device_type = "METAL"
    prefs.get_devices()
    devices = []
    for dev in prefs.devices:
        dev.use = (
            (dev.type == "CPU")
            if sc.cycles.device == "CPU"
            else dev.type in ["OPTIX", "METAL"]
        )
        devices.append({"name": dev.name, "type": dev.type, "use": dev.use})
    return sc, pivot, post, devices


def keyframe_shutter(c, run, data, pivot, post):
    """Key the solved states for the shutter interval of every rendered frame.

    The frame centre is the cached state itself. Shutter open and close use the
    native 6144 Hz trace samples (no re-solve, no smoothing). The coil uses the
    cached per-frame meshes as absolute shape keys; within the short shutter it
    is blended toward the neighbouring frame by the traced compression.
    """
    trace = np.load(run / "trace.npz")
    columns = [str(x) for x in trace["columns"]]
    values = trace["values"]
    theta = values[:, columns.index("theta_rad")]
    comp = values[:, columns.index("compression_m")]
    per = c["simulation_quality"]["trace_samples_per_frame"]
    half = c["render"]["motion_blur_shutter"] / 2
    offset = round(half * per)
    if abs(offset / per - half) > 1e-12:
        raise RuntimeError("Shutter edges must fall on native trace samples")
    frames = c["render"]["frames"]
    last = len(values) - 1
    carriage = bpy.data.objects.get("Native guided compression pose")
    audit = {"shutter_frames": 2 * half, "trace_offset_samples": offset, "keys": 0}
    if post is not None:
        post.shape_key_add(name="Solved reference at t=0")
        post.data.shape_keys.use_relative = False
        blocks = []
        for k, coords in enumerate(data["spring_vertices"]):
            key = post.shape_key_add(name=f"Solved t={k / c['render']['fps']:.6f}s")
            key.data.foreach_set("co", coords.ravel())
            key.interpolation = "KEY_LINEAR"
            blocks.append(key)
    for k in range(1, frames + 1):
        i = (k - 1) * per
        if theta[i] != data["theta"][k - 1] or comp[i] != data["compression"][k - 1]:
            raise RuntimeError("Trace sample differs from the cached frame state")
        for f, j in [(k - half, max(i - offset, 0)), (k, i), (k + half, min(i + offset, last))]:
            pivot.rotation_euler = (0, -float(theta[j]), 0)
            pivot.keyframe_insert(data_path="rotation_euler", index=1, frame=f)
            if carriage is not None:
                carriage.location.x = float(comp[j])
                carriage.keyframe_insert(data_path="location", index=0, frame=f)
            if post is not None:
                here = k - 1
                there = here + (1 if f > k else -1)
                weight = 0.0
                if f != k and 0 <= there < len(blocks):
                    span = data["compression"][there] - data["compression"][here]
                    if abs(span) > 1e-12:
                        weight = min(max((comp[j] - comp[i]) / span, 0.0), 1.0)
                position = blocks[here].frame
                if weight:
                    position += weight * (blocks[there].frame - position)
                post.data.shape_keys.eval_time = position
                post.data.shape_keys.keyframe_insert(data_path="eval_time", frame=f)
            audit["keys"] += 1
    holders = [pivot.animation_data.action]
    if carriage is not None:
        holders.append(carriage.animation_data.action)
    if post is not None:
        holders.append(post.data.shape_keys.animation_data.action)
    for action in holders:
        for fc in action.fcurves:
            for key in fc.keyframe_points:
                key.interpolation = "LINEAR"
    return audit


def main():
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frame-list", default="")
    p.add_argument("--samples", type=int)
    p.add_argument("--save-blend", action="store_true")
    p.add_argument("--skip-existing", action="store_true")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    a.out.mkdir(parents=True, exist_ok=True)
    signature = render_signature()
    assethash = signature["asset_manifest_sha256"]
    c = json.loads((a.run / "actual_config.json").read_text())
    data = np.load(a.run / "trajectory.npz")
    sc, pivot, post, devices = setup(c, data)
    if a.samples:
        sc.cycles.samples = a.samples
    shutter_audit = (
        keyframe_shutter(c, a.run, data, pivot, post)
        if c["render"]["motion_blur"]
        else None
    )
    wanted = (
        [int(x) for x in a.frame_list.split(",")]
        if a.frame_list
        else list(range(1, c["render"]["frames"] + 1))
    )
    times = {}
    oldpath = a.out / "render_report.json"
    old = json.loads(oldpath.read_text()) if oldpath.exists() else {}
    if (
        a.skip_existing
        and old
        and (
            old.get("config") != c
            or old.get("actual_samples") != sc.cycles.samples
            or old.get("asset_manifest_sha256") != assethash
        )
    ):
        raise RuntimeError(
            "Existing cache has a different renderer/config/quality; use an independent output directory"
        )
    provenance = old.get("frame_devices", {}) if a.skip_existing else {}

    def save_report(status):
        report = {
            "asset_manifest_sha256": assethash,
            "config": c,
            "actual_samples": sc.cycles.samples,
            "frames": wanted,
            "completed_frames": sorted(int(x) for x in times),
            "seconds_per_frame": times,
            "render_seconds": sum(times.values()),
            "devices": devices,
            "frame_devices": provenance,
            "blender": bpy.app.version_string,
            "trajectory_sha256": hashlib.sha256(
                (a.run / "trajectory.npz").read_bytes()
            ).hexdigest(),
            "geometry_limits": {
                "wire_visual_interpolation": "Guided axial mode: fixed root, active pitch from native compression; closed end turns keep wire-diameter pitch",
                "simulation_compression_not_modified": True,
            },
            "asset_scale_audit": json.loads(sc.get("asset_scale_audit_json", "[]")),
            "manufacturing_audit": json.loads(sc.get("manufacturing_audit_json", "{}")),
            "craft_finish_audit": json.loads(sc.get("craft_finish_audit_json", "{}")),
            "finish_audit": json.loads(sc.get("finish_audit_json", "{}")),
            "motion_blur_keys": shutter_audit,
            "execution": {
                "hostname": __import__("socket").gethostname(),
                "script_path": str(Path(__file__).resolve()),
                "python": sys.version,
                "pid": os.getpid(),
            },
            "status": status,
        }
        tmp = oldpath.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(report, indent=2) + "\n")
        tmp.replace(oldpath)

    for frame in wanted:
        if (
            a.skip_existing
            and (a.out / f"{frame:04d}.png").exists()
            and old
            and frame in old.get("completed_frames", [])
        ):
            times[str(frame)] = old.get("seconds_per_frame", {}).get(str(frame), 0.0)
            continue
        index = frame - 1
        sc.frame_set(frame)
        if shutter_audit is not None:
            # Keyed states drive the pose; check the frame centre is the cached state.
            if abs(pivot.rotation_euler.y + float(data["theta"][index])) > 1e-6:
                raise RuntimeError("Keyed hinge pose differs from the cache")
        else:
            pivot.rotation_euler = (0, -float(data["theta"][index]), 0)
        if post is not None and shutter_audit is None:
            post.data.vertices.foreach_set("co", data["spring_vertices"][index].ravel())
            post.data.update()
            bpy.data.objects["Native guided compression pose"].location.x = float(
                data["compression"][index]
            )
        sc.render.filepath = str(a.out / f"{frame:04d}.png")
        start = time.monotonic()
        bpy.ops.render.render(write_still=True)
        times[str(frame)] = time.monotonic() - start
        provenance[str(frame)] = {
            "device": sc.cycles.device,
            "devices": [x for x in devices if x["use"]],
        }
        if a.save_blend and frame == wanted[0]:
            bpy.ops.wm.save_as_mainfile(filepath=str(a.out / "scene.blend"))
        save_report("rendering")
    save_report("rendered")


if __name__ == "__main__":
    main()
