"""Photographic appearance revision; contains no dynamics or cache modification."""

import json
import math
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import bpy
import numpy as np
from mathutils import Vector

from scene_paths import ASSET_DIR, CATALOG_DIR

ASSETS = ASSET_DIR / "room_dressing"


def _principled(name, color, metal=0.0, rough=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    return m, p


def _wood(ident, name, span, offset=(0, 0), rough=(0.43, 0.66)):
    manifest = json.loads((CATALOG_DIR / "room_props.json").read_text())
    asset = next(x for x in manifest["assets"] if x["id"] == ident)
    paths = {x["role"]: ASSETS / x["relative_path"] for x in asset["files"]}
    m, p = _principled(name, (0.3, 0.2, 0.12))
    m["grain_material"] = True
    n = m.node_tree.nodes
    links = m.node_tree.links
    uv = n.new("ShaderNodeTexCoord")
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1 / span[0], 1 / span[1], 1)
    mapping.inputs["Location"].default_value = (*offset, 0)
    links.new(uv.outputs["UV"], mapping.inputs["Vector"])
    textures = {}
    for role, path in paths.items():
        im = bpy.data.images.load(str(path), check_existing=True)
        im.colorspace_settings.name = "sRGB" if role == "Diffuse" else "Non-Color"
        tex = n.new("ShaderNodeTexImage")
        tex.image = im
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        textures[role] = tex
    # Both photographed veneer textures have grain along image U; mesh UV V is its long axis.
    separate = n.new("ShaderNodeSeparateXYZ")
    combine = n.new("ShaderNodeCombineXYZ")
    links.new(uv.outputs["UV"], separate.inputs[0])
    links.new(separate.outputs["Y"], combine.inputs["X"])
    links.new(separate.outputs["X"], combine.inputs["Y"])
    links.new(combine.outputs[0], mapping.inputs["Vector"])
    mapping.inputs["Scale"].default_value = (1 / span[1], 1 / span[0], 1)
    if ident == "american_walnut_veneer":
        tint = n.new("ShaderNodeMixRGB")
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 1.0
        tint.inputs[2].default_value = (0.28, 0.12, 0.05, 1)
        links.new(textures["Diffuse"].outputs["Color"], tint.inputs[1])
        links.new(tint.outputs[0], p.inputs["Base Color"])
        p.inputs["Coat Weight"].default_value = 0.08
        p.inputs["Coat Roughness"].default_value = 0.35
    else:
        links.new(textures["Diffuse"].outputs["Color"], p.inputs["Base Color"])
    r = n.new("ShaderNodeMapRange")
    r.inputs["To Min"].default_value = rough[0]
    r.inputs["To Max"].default_value = rough[1]
    links.new(textures["Rough"].outputs["Color"], r.inputs["Value"])
    links.new(r.outputs["Result"], p.inputs["Roughness"])
    normal = n.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.12
    links.new(textures["nor_gl"].outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], p.inputs["Normal"])
    return m


def _metal(name, color, rough, anisotropy=0.0, turned=False):
    m, p = _principled(name, color, 1, rough)
    p.inputs["Anisotropic"].default_value = anisotropy
    n = m.node_tree.nodes
    links = m.node_tree.links
    coord = n.new("ShaderNodeTexCoord")
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3600.0
    noise.inputs["Detail"].default_value = 2.0
    links.new(coord.outputs["Object"], noise.inputs["Vector"])
    r = n.new("ShaderNodeMapRange")
    r.inputs["To Min"].default_value = rough * 0.88
    r.inputs["To Max"].default_value = rough * 1.12
    links.new(noise.outputs["Fac"], r.inputs["Value"])
    links.new(r.outputs["Result"], p.inputs["Roughness"])
    if turned:
        wave = n.new("ShaderNodeTexWave")
        wave.wave_type = "RINGS"
        wave.rings_direction = "Z"
        wave.inputs["Scale"].default_value = 1200.0
        wave.inputs["Distortion"].default_value = 0.015
        links.new(coord.outputs["Object"], wave.inputs["Vector"])
        bump = n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        bump.inputs["Distance"].default_value = 0.000002
        links.new(wave.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def _assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def _bounds(objects):
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        if obj.type == "MESH":
            ev = obj.evaluated_get(deps)
            points.extend(
                [tuple(ev.matrix_world @ Vector(corner)) for corner in ev.bound_box]
            )
    a = np.asarray(points)
    return a.min(axis=0), a.max(axis=0)


def _prop(ident, base, target, rotation=0.0, dimension="height", book_count=8):
    before = set(bpy.data.objects)
    path = ASSETS / ident / (ident + "_2k.blend")
    if ident == "binder_notebook":
        bpy.ops.import_scene.gltf(filepath=str(ASSETS / ident / (ident + "_2k.gltf")))
        objects = [o for o in bpy.data.objects if o not in before]
    else:
        with bpy.data.libraries.load(str(path), link=False) as (src, dst):
            if ident == "book_encyclopedia_set_01":
                dst.objects = [
                    name
                    for name in src.objects
                    if name.startswith(ident + "_book")
                    and int(name.rsplit("book", 1)[-1]) <= book_count
                ]
            else:
                dst.objects = [
                    name for name in src.objects if name.startswith(ident + "_")
                ]
        objects = [obj for obj in dst.objects if obj]
        for obj in objects:
            bpy.context.collection.objects.link(obj)
    root = bpy.data.objects.new("Measured prop | " + ident, None)
    bpy.context.collection.objects.link(root)
    for obj in objects:
        if obj.parent is None:
            obj.parent = root
    # Appending resolves linked texture paths; explicitly repair any remaining relative references.
    for image in bpy.data.images:
        if ident in image.filepath and image.source == "FILE":
            candidates = list((ASSETS / ident).rglob(Path(image.filepath).name))
            if candidates:
                image.filepath = str(candidates[0])
    low, high = _bounds(objects)
    native = (high - low).tolist()
    root.rotation_euler.z = rotation
    low, high = _bounds(objects)
    axis = 2 if dimension == "height" else int(np.argmax((high - low)[:2]))
    factor = target / (high[axis] - low[axis])
    root.scale = (factor,) * 3
    low, high = _bounds(objects)
    root.location += Vector(base) - Vector(
        ((low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2])
    )
    low, high = _bounds(objects)
    audit = {
        "asset": ident,
        "native_bbox_m": native,
        "uniform_scale": float(factor),
        "target_dimension": dimension,
        "target_m": target,
        "world_bbox_min_m": low.tolist(),
        "world_bbox_max_m": high.tolist(),
        "world_dimensions_m": (high - low).tolist(),
        "contact_surface_z_m": base[2],
        "bottom_error_m": float(abs(low[2] - base[2])),
        "objects": [o.name for o in objects],
    }
    return root, objects, audit


def _gusset(name, y, mat):
    vertices = [
        (x, yy, z)
        for yy in [y - 0.0015, y + 0.0015]
        for x, z in [(0.132, 0.027), (0.150, 0.027), (0.132, 0.058)]
    ]
    faces = [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    _assign(obj, mat)
    b = obj.modifiers.new("Deburred weld plate edges", "BEVEL")
    b.width = 0.00022
    b.segments = 2
    obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj


def _cut(obj, cutter):
    bpy.context.view_layer.objects.active = obj
    mod = obj.modifiers.new("Manufactured recess", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def _rect_light(name, loc, target, energy, size_x, size_y):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "RECTANGLE"
    data.size = size_x
    data.size_y = size_y
    data.color = (1.0, 0.965, 0.91)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (
        (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    )
    return obj


def upgrade_scene(sc, c, helpers):
    ap = c["appearance"]
    cube = helpers["cube"]
    cylinder = helpers["cylinder"]
    audits = []
    # Different species and finishes, with actual metre-scale UVs and small edge radii.
    walnut_names = [
        "Walnut toy base",
        "Rear walnut upright",
        "Cantilever walnut crossbeam",
    ]
    for i, name in enumerate(walnut_names):
        obj = bpy.data.objects[name]
        _assign(
            obj,
            _wood(
                "american_walnut_veneer",
                "Oiled walnut / " + name,
                ap["walnut_texture_span_m"],
                (0.07 + 0.17 * i, 0.21 + 0.13 * i),
            ),
        )
        for mod in obj.modifiers:
            if mod.type == "BEVEL":
                mod.width = 0.0012 if name == "Walnut toy base" else 0.00065
    # Butt-jointed upright meets the beam underside; remove the old overlapping coplanar faces.
    upright = bpy.data.objects["Rear walnut upright"]
    upright.scale.z = (ap["upright_visual_top_m"] - 0.023) / 0.292
    upright.location.z = (ap["upright_visual_top_m"] + 0.023) / 2
    oak = _wood(
        "oak_veneer_02",
        "Natural matte oak desk",
        ap["oak_texture_span_m"],
        (0.13, 0.34),
        (0.47, 0.69),
    )
    _assign(bpy.data.objects["Oak dining / science table"], oak)
    # Remove the blockout room props and generic studio lights.
    prefixes = [
        "Background book",
        "Background pot",
        "Plant stem",
        "Plant leaf",
        "A5 science notebook",
        "Notebook pages",
        "Pencil on notebook",
        "Graphite pencil tip",
        "Backing reinforcing heel",
        "Rear room shelf",
        "Continuous rear wall",
    ]
    for obj in list(bpy.data.objects):
        if obj.type == "LIGHT" or any(
            obj.name.startswith(prefix) for prefix in prefixes
        ):
            bpy.data.objects.remove(obj, do_unlink=True)
    steel = _metal(
        "Polished bearing steel with restrained microfinish",
        (0.56, 0.58, 0.60),
        0.145,
        0.1,
    )
    satin = _metal(
        "Brushed stainless / machining variation", (0.48, 0.49, 0.50), 0.32, 0.4
    )
    aluminium = _metal(
        "Turned aluminium pressure disk", (0.67, 0.68, 0.69), 0.29, 0.5, True
    )
    brass = _metal("Machined brass journals", (0.55, 0.35, 0.12), 0.31, 0.35)
    springmat = _metal("Drawn spring-steel wire", (0.34, 0.36, 0.38), 0.235, 0.25)
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        name = obj.name
        if name.startswith("Solid steel bob"):
            _assign(obj, steel)
        elif name == "Deforming horizontal compression spring":
            _assign(obj, springmat)
        elif name == "Moving aluminium pressure disk":
            _assign(obj, aluminium)
        elif any(word in name for word in ["brass", "Brass"]):
            _assign(obj, brass)
        elif any(
            word in name
            for word in [
                "shaft",
                "Axle end cap",
                "guide rod",
                "Slender steel",
                "Rod hinge",
                "retaining collar",
            ]
        ):
            _assign(obj, satin)
        elif any(
            word in name
            for word in [
                "bracket",
                "heel",
                "plate",
                "backing",
                "mounting foot",
                "end seat",
                "mounting screw",
                "Bearing plate screw",
            ]
        ):
            if "slot" not in name.lower():
                _assign(obj, satin)
        for mod in obj.modifiers:
            if (
                mod.type == "BEVEL"
                and name not in walnut_names
                and "table" not in name.lower()
            ):
                mod.width = min(mod.width, 0.00022)
    # Two actual recessed fasteners close the beam-to-upright assembly joint.
    for z in [0.316, 0.327]:
        cap = cylinder(
            "Beam assembly screw",
            (-0.17, 0.0277, z),
            (-0.17, 0.0270, z),
            0.0022,
            satin,
            32,
        )
        for angle in [0, math.pi / 2]:
            cut = cube(
                "Temporary beam screw slot",
                (-0.17, 0.0269, z),
                (0.0027, 0.00055, 0.00045),
                satin,
                0,
            )
            cut.rotation_euler.y = angle
            _cut(cap, cut)
    for y in [-0.022, 0.022]:
        _gusset("Welded triangular backing gusset", y, satin)
    # A real bore through the backing and actual recessed cross slots in the screw heads.
    backing = bpy.data.objects["Spring fixed backing"]
    cutter = cylinder(
        "Temporary guide bore", (0.124, 0, 0.09), (0.137, 0, 0.09), 0.00155, satin, 48
    )
    _cut(backing, cutter)
    for obj in list(bpy.data.objects):
        if (
            "cross slot" in obj.name
            or obj.name.endswith(" slot")
            or " slot." in obj.name
        ):
            bpy.data.objects.remove(obj, do_unlink=True)
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or "screw" not in obj.name.lower():
            continue
        # Caps are local Z-axis cylinders, including the bearing caps whose local Z points toward the camera.
        depth = max(v.co.z for v in obj.data.vertices)
        transform = obj.matrix_world.copy()
        for angle in [0, math.pi / 2]:
            cut = cube(
                "Temporary recessed screw slot",
                (0, 0, 0),
                (0.0038, 0.00060, 0.00055),
                satin,
                0,
            )
            cut.matrix_world = transform
            cut.location = transform @ Vector((0, 0, depth - 0.00014))
            cut.rotation_euler.rotate_axis("Z", angle)
            _cut(obj, cut)
    # Plaster wall and properly supported shelf, all in the same camera and illumination.
    plaster, p = _principled("Quiet painted plaster", (0.51, 0.53, 0.50), 0, 0.86)
    n = plaster.node_tree.nodes
    links = plaster.node_tree.links
    tex = n.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 720.0
    coord = n.new("ShaderNodeTexCoord")
    links.new(coord.outputs["Object"], tex.inputs["Vector"])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.000035
    links.new(tex.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], p.inputs["Normal"])
    cube("Continuous home wall", (0, 0.72, 0.72), (6, 0.08, 3.6), plaster, 0.002)
    _shelf = cube(
        "Matte oak wall shelf", (-0.10, 0.55, 0.129), (1.15, 0.24, 0.022), oak, 0.0015
    )
    for x in [-0.48, 0.28]:
        cube(
            "Shelf hidden steel support",
            (x, 0.645, 0.105),
            (0.018, 0.070, 0.008),
            satin,
            0.0004,
        )
        cube(
            "Shelf wall mounting angle",
            (x, 0.675, 0.080),
            (0.018, 0.006, 0.055),
            satin,
            0.0004,
        )
    _, _, audit = _prop(
        "potted_plant_02",
        (0.30, 0.535, 0.14),
        ap["background_plant_height_m"],
        rotation=0.35,
    )
    audits.append(audit)
    _, _, audit = _prop(
        "book_encyclopedia_set_01",
        (-0.40, 0.555, 0.14),
        ap["background_books_height_m"],
        rotation=0.035,
        book_count=8,
    )
    audits.append(audit)
    _, _, audit = _prop(
        "binder_notebook",
        (0.32, 0.22, 0.0002),
        0.28,
        rotation=-0.12,
        dimension="long_edge",
    )
    audits.append(audit)
    # Photographed room reflections and one broad window give consistent, directional indoor light.
    world = bpy.data.worlds.new("Measured indoor HDRI / daylight room")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(
        str(ASSETS / "small_empty_room_1/small_empty_room_1_2k.exr"),
        check_existing=True,
    )
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = math.radians(ap["hdri_rotation_deg"])
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    bg = nodes.get("Background")
    links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = ap["world_strength"]
    sc.world = world
    window = _rect_light(
        "Large daylight window",
        (-0.52, -0.36, 0.85),
        (0, 0, 0.15),
        ap["window_power_W"],
        0.75,
        1.05,
    )
    # White-painted mullions break up the emitter reflection at real window scale.
    frame, _ = _principled("White window joinery", (0.69, 0.71, 0.69), 0, 0.54)
    for x in [-0.375, 0, 0.375]:
        obj = cube(
            "Window vertical mullion", (0, 0, 0), (0.022, 1.10, 0.025), frame, 0.001
        )
        obj.parent = window
        obj.location = (x, 0, -0.012)
    for y in [-0.525, 0, 0.525]:
        obj = cube(
            "Window horizontal mullion", (0, 0, 0), (0.79, 0.022, 0.025), frame, 0.001
        )
        obj.parent = window
        obj.location = (0, y, -0.012)
    sc.camera.data.dof.aperture_fstop = ap["aperture_fstop"]
    sc["asset_scale_audit_json"] = json.dumps(audits)
