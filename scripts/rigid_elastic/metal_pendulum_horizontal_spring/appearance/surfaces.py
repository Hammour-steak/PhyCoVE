"""SI visual manufacturing details and a coherent window-side home work table.

This module reads the integrated poses; it contains no simulation or time driver.
"""

import json
import math
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import bpy
from mathutils import Matrix, Vector

from appearance.room import _assign, _bounds, _cut, _principled, _rect_light
from scene_paths import ASSET_DIR, CATALOG_DIR


def _scanned_wood(ident, name, span, tint, offset, rough, swap=True, saturation=1.0):
    manifest = json.loads((CATALOG_DIR / "surface_scans.json").read_text())
    asset = next(x for x in manifest["assets"] if x["id"] == ident)
    m, p = _principled(name, (0.2, 0.1, 0.05))
    m["grain_material"] = True
    n = m.node_tree.nodes
    links = m.node_tree.links
    uv = n.new("ShaderNodeTexCoord")
    separate = n.new("ShaderNodeSeparateXYZ")
    combine = n.new("ShaderNodeCombineXYZ")
    links.new(uv.outputs["UV"], separate.inputs[0])
    links.new(separate.outputs["Y" if swap else "X"], combine.inputs["X"])
    links.new(separate.outputs["X" if swap else "Y"], combine.inputs["Y"])
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1 / span, 1 / span, 1)
    mapping.inputs["Location"].default_value = (*offset, 0)
    links.new(combine.outputs[0], mapping.inputs["Vector"])
    textures = {}
    for entry in asset["files"]:
        role = entry["role"]
        im = bpy.data.images.load(
            str(ASSET_DIR / "wood_surfaces" / entry["relative_path"]), check_existing=True
        )
        im.colorspace_settings.name = "sRGB" if role == "Diffuse" else "Non-Color"
        tex = n.new("ShaderNodeTexImage")
        tex.image = im
        links.new(mapping.outputs[0], tex.inputs[0])
        textures[role] = tex
    sat = n.new("ShaderNodeHueSaturation")
    sat.inputs["Saturation"].default_value = saturation
    links.new(textures["Diffuse"].outputs["Color"], sat.inputs["Color"])
    mix = n.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    mix.inputs[2].default_value = (*tint, 1)
    links.new(sat.outputs[0], mix.inputs[1])
    links.new(mix.outputs[0], p.inputs["Base Color"])
    r = n.new("ShaderNodeMapRange")
    r.inputs["To Min"].default_value = rough[0]
    r.inputs["To Max"].default_value = rough[1]
    links.new(textures["Rough"].outputs["Color"], r.inputs["Value"])
    links.new(r.outputs[0], p.inputs["Roughness"])
    normal = n.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.22
    links.new(textures["nor_gl"].outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], p.inputs["Normal"])
    p.inputs["Coat Weight"].default_value = 0.10
    p.inputs["Coat Roughness"].default_value = 0.28
    return m


def _ply_edge():
    m, p = _principled(
        "Thirteen birch plies / thin glue seams", (0.27, 0.18, 0.09), 0, 0.46
    )
    n = m.node_tree.nodes
    links = m.node_tree.links
    co = n.new("ShaderNodeTexCoord")
    sep = n.new("ShaderNodeSeparateXYZ")
    links.new(co.outputs["Object"], sep.inputs[0])
    mul = n.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 13 / 0.018
    links.new(sep.outputs["Z"], mul.inputs[0])
    fract = n.new("ShaderNodeMath")
    fract.operation = "FRACT"
    links.new(mul.outputs[0], fract.inputs[0])
    glue = n.new("ShaderNodeMath")
    glue.operation = "LESS_THAN"
    glue.inputs[1].default_value = 0.06
    links.new(fract.outputs[0], glue.inputs[0])
    layer = n.new("ShaderNodeMath")
    layer.operation = "FLOOR"
    links.new(mul.outputs[0], layer.inputs[0])
    variation = n.new("ShaderNodeTexNoise")
    variation.noise_dimensions = "1D"
    variation.inputs["Scale"].default_value = 0.87
    links.new(layer.outputs[0], variation.inputs["W"])
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.22, 0.13, 0.060, 1)
    ramp.color_ramp.elements[1].color = (0.32, 0.22, 0.12, 1)
    links.new(variation.outputs["Fac"], ramp.inputs[0])
    mix = n.new("ShaderNodeMixRGB")
    mix.inputs[2].default_value = (0.10, 0.05, 0.018, 1)
    links.new(ramp.outputs[0], mix.inputs[1])
    links.new(glue.outputs[0], mix.inputs[0])
    links.new(mix.outputs[0], p.inputs["Base Color"])
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2200.0
    links.new(co.outputs["Object"], noise.inputs[0])
    b = n.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = 0.14
    b.inputs["Distance"].default_value = 0.000012
    links.new(noise.outputs["Fac"], b.inputs["Height"])
    links.new(b.outputs[0], p.inputs["Normal"])
    return m


def _finish_metal(name, color, rough, anisotropy):
    m, p = _principled(name, color, 1.0, rough)
    p.inputs["Anisotropic"].default_value = anisotropy
    n = m.node_tree.nodes
    links = m.node_tree.links
    co = n.new("ShaderNodeTexCoord")
    scale = n.new("ShaderNodeVectorMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = (140.0, 6500.0, 190.0)
    links.new(co.outputs["Object"], scale.inputs[0])
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.0
    noise.inputs["Detail"].default_value = 2.0
    links.new(scale.outputs[0], noise.inputs[0])
    b = n.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = 0.15
    b.inputs["Distance"].default_value = 0.0000008
    links.new(noise.outputs["Fac"], b.inputs["Height"])
    links.new(b.outputs[0], p.inputs["Normal"])
    variation = n.new("ShaderNodeTexNoise")
    variation.inputs["Scale"].default_value = 70.0
    links.new(co.outputs["Object"], variation.inputs[0])
    r = n.new("ShaderNodeMapRange")
    r.inputs["To Min"].default_value = rough * 0.84
    r.inputs["To Max"].default_value = rough * 1.14
    links.new(variation.outputs["Fac"], r.inputs[0])
    links.new(r.outputs[0], p.inputs["Roughness"])
    return m


def _annulus(name, a, b, inner, outer, mat, N=64):
    a, b = Vector(a), Vector(b)
    axis = (b - a).normalized()
    u = axis.cross(Vector((0, 0, 1)))
    if u.length < 0.01:
        u = axis.cross(Vector((0, 1, 0)))
    u.normalize()
    v = axis.cross(u)
    verts = []
    faces = []
    for center in [a, b]:
        for radius in [inner, outer]:
            for j in range(N):
                angle = 2 * math.pi * j / N
                verts.append(
                    center + radius * (u * math.cos(angle) + v * math.sin(angle))
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
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    _assign(o, mat)
    for poly in mesh.polygons:
        poly.use_smooth = poly.index % 4 >= 2
    be = o.modifiers.new("Small deburred radius", "BEVEL")
    be.width = 0.00008
    be.segments = 2
    o.modifiers.new("Machined normals", "WEIGHTED_NORMAL")
    return o


def _prop_place(
    ident, base, target, rotation=(0, 0, 0), dimension="height", stack_books=False
):
    root = bpy.data.objects["Measured prop | " + ident]
    root.location = (0, 0, 0)
    root.rotation_euler = (0, 0, 0)
    root.scale = (1, 1, 1)
    if stack_books:
        for obj in list(root.children_recursive):
            if obj.type == "MESH" and int(obj.name.split("book")[-1].split(".")[0]) > 3:
                bpy.data.objects.remove(obj, do_unlink=True)
    objects = [o for o in root.children_recursive if o.type == "MESH"]
    root.rotation_euler = rotation
    low, high = _bounds(objects)
    factor = target / (
        (high - low)[2] if dimension == "height" else max((high - low)[:2])
    )
    root.scale = (factor,) * 3
    supports = []
    if stack_books:
        low, high = _bounds(objects)
        surface = float(low[2])
        for i, obj in enumerate(sorted(objects, key=lambda o: _bounds([o])[0][2])):
            lo, hi = _bounds([obj])
            center = Vector((lo + hi) / 2)
            rot = (
                Matrix.Translation(center)
                @ Matrix.Rotation([-0.027, 0.013, -0.008][i], 4, "Z")
                @ Matrix.Translation(-center)
            )
            obj.matrix_world = rot @ obj.matrix_world
            lo, hi = _bounds([obj])
            move = Vector((0.003 * (i - 1), 0.002 * (i % 2), surface - lo[2]))
            obj.matrix_world = Matrix.Translation(move) @ obj.matrix_world
            lo, hi = _bounds([obj])
            supports.append(
                {
                    "book": obj.name,
                    "bottom_m": float(lo[2]),
                    "support_m": surface,
                    "error_m": float(abs(lo[2] - surface)),
                }
            )
            surface = float(hi[2])
    low, high = _bounds(objects)
    root.location += Vector(base) - Vector(
        ((low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2])
    )
    low, high = _bounds(objects)
    return {
        "asset": ident,
        "target_dimension": dimension,
        "target_m": target,
        "uniform_scale": float(factor),
        "world_bbox_min_m": low.tolist(),
        "world_bbox_max_m": high.tolist(),
        "world_dimensions_m": (high - low).tolist(),
        "contact_surface_z_m": base[2],
        "bottom_error_m": float(abs(low[2] - base[2])),
        "book_stack_support_checks": supports,
        "objects": [o.name for o in objects],
    }


def _curtain(cube):
    verts = []
    faces = []
    nx, nz = 96, 12
    for k in range(nz + 1):
        z = 0.17 + k * 1.10 / nz
        for j in range(nx + 1):
            x = -0.82 + j * 0.56 / nx
            y = (
                0.696
                + 0.012 * math.cos(j * math.pi * 12 / nx)
                + 0.002 * math.sin(k * 0.5 + j * 0.09)
            )
            verts.append((x, y, z))
    for k in range(nz):
        for j in range(nx):
            q = k * (nx + 1) + j
            faces.append((q, q + 1, q + nx + 2, q + nx + 1))
    mesh = bpy.data.meshes.new("Soft woven curtain folds")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new("Sheer linen window curtain", mesh)
    bpy.context.collection.objects.link(o)
    for p in mesh.polygons:
        p.use_smooth = True
    mat, p = _principled(
        "Linen curtain with light transmission", (0.72, 0.70, 0.62), 0, 0.9
    )
    n = mat.node_tree.nodes
    links = mat.node_tree.links
    out = n.get("Material Output")
    trans = n.new("ShaderNodeBsdfTranslucent")
    trans.inputs[0].default_value = (0.8, 0.79, 0.71, 1)
    mix = n.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.55
    links.new(p.outputs[0], mix.inputs[1])
    links.new(trans.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs[0])
    co = n.new("ShaderNodeTexCoord")
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6000.0
    links.new(co.outputs["Object"], noise.inputs[0])
    b = n.new("ShaderNodeBump")
    b.inputs["Distance"].default_value = 0.00002
    b.inputs["Strength"].default_value = 0.2
    links.new(noise.outputs["Fac"], b.inputs["Height"])
    links.new(b.outputs[0], p.inputs["Normal"])
    _assign(o, mat)


def refine_scene(sc, c, helpers):
    cube = helpers["cube"]
    cylinder = helpers["cylinder"]
    _text = helpers["text"]
    ap = c["appearance"]
    p = c["physics"]["pendulum"]
    audits = []
    # Scanned grain on each separate timber member; exposed substrate gives the base an actual build method.
    for i, name in enumerate(
        ["Walnut toy base", "Rear walnut upright", "Cantilever walnut crossbeam"]
    ):
        obj = bpy.data.objects[name]
        wood = _scanned_wood(
            "natural_walnut_veneer",
            "Oiled natural walnut / " + name,
            ap["walnut_scan_span_m"],
            ap["walnut_tint_linear"],
            (0.11 + 0.19 * i, 0.31 + 0.13 * i),
            ((0.40, 0.59) if i == 0 else (0.29, 0.49)),
        )
        _assign(obj, wood)
        if i == 0:
            obj.data.materials.append(_ply_edge())
            for face in obj.data.polygons:
                face.material_index = 1 if abs(face.normal.z) < 0.5 else 0
        wood.node_tree.nodes.get("Principled BSDF").inputs[
            "Coat Weight"
        ].default_value = 0.025
        wood.node_tree.nodes.get("Principled BSDF").inputs["IOR"].default_value = 1.45
        for mod in obj.modifiers:
            if mod.type == "BEVEL":
                mod.width = 0.0014 if i == 0 else 0.00075
    table = bpy.data.objects["Oak dining / science table"]
    _assign(
        table,
        _scanned_wood(
            "wood_table_worn",
            "Used family writing desk / scanned grain",
            ap["desk_scan_span_m"],
            ap["desk_tint_linear"],
            (0.15, 0.23),
            (0.32, 0.61),
            saturation=0.66,
        ),
    )
    # All metal has a restrained machining response, rather than identical chrome.
    satin = _finish_metal(
        "Directional brushed stainless", (0.48, 0.49, 0.50), 0.30, 0.45
    )
    brass = _finish_metal("Turned bearing bronze", (0.48, 0.29, 0.10), 0.27, 0.3)
    steel = _finish_metal("Clean bearing-steel sphere", (0.56, 0.58, 0.60), 0.125, 0.05)
    dark, _ = _principled("Dark laser engraving", (0.027, 0.020, 0.013), 0, 0.8)
    ptfe, _ = _principled(
        "Thrust washer fibre composite", (0.026, 0.03, 0.029), 0, 0.65
    )
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        if obj.name.startswith("Solid steel bob"):
            _assign(obj, steel)
        elif any(
            x in obj.name.lower()
            for x in [
                "screw",
                "backing",
                "mounting foot",
                "plate",
                "gusset",
                "heel",
                "bracket",
                "shaft",
                "guide rod",
                "retaining collar",
            ]
        ):
            _assign(obj, satin)
    # Open the mounting plate so the upright actually rests on the wood through its socket.
    upright = bpy.data.objects["Rear walnut upright"]
    upright.scale.z = (
        ap["upright_visual_top_m"] - ap["upright_visual_bottom_m"]
    ) / 0.292
    upright.location.z = (
        ap["upright_visual_top_m"] + ap["upright_visual_bottom_m"]
    ) / 2
    plate = bpy.data.objects["Upright base angle bracket"]
    _cut(
        plate,
        cube(
            "Temporary upright mounting socket",
            (-0.17, 0.043, 0.026),
            (0.0252, 0.0312, 0.012),
            satin,
            0,
        ),
    )
    heel = bpy.data.objects["Bracket upright heel"]
    heel.location = (-0.17, 0.0615, 0.0475)
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Stand mounting screw") and obj.location.y > 0.04:
            obj.location.y = 0.0705
    for name in ["Stand mounting screw", "Horizontal module mounting screw"]:
        for obj in list(bpy.data.objects):
            if obj.type == "MESH" and obj.name.startswith(name):
                top = 0.030 if name == "Stand mounting screw" else 0.027
                _annulus(
                    "Fastener bearing washer",
                    (obj.location.x, obj.location.y, top),
                    (obj.location.x, obj.location.y, top + 0.0004),
                    0.0017,
                    0.0036,
                    satin,
                )
                obj.location.z += 0.0004
    # A bored eye turns on the shaft. Thrust washers leave visible clearance either side.
    pivot = bpy.data.objects["Integrated physical hinge pose"]
    for name in ["Front brass journal", "Rod hinge eye", "Slender steel pendulum rod"]:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    bearing = bpy.data.objects["Axle bearing plate"]
    bearing.location.y = 0.024
    _annulus(
        "Front brass journal",
        (0, 0.008, 0.32),
        (0, 0.0205, 0.32),
        0.0043,
        0.0075,
        brass,
    )
    _annulus(
        "Front axle shoulder spacer",
        (0, -0.013, 0.32),
        (0, -0.0061, 0.32),
        0.00425,
        0.0050,
        satin,
    )
    _annulus(
        "Rear axle shoulder spacer",
        (0, 0.0061, 0.32),
        (0, 0.008, 0.32),
        0.00425,
        0.0050,
        satin,
    )
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Bearing plate screw"):
            obj.location.y += 0.0008
            _annulus(
                "Bearing screw washer",
                (obj.location.x, 0.0201, obj.location.z),
                (obj.location.x, 0.0205, obj.location.z),
                0.0014,
                0.0036,
                satin,
            )
    eye = _annulus(
        "Rod hinge eye", (0, -0.005, 0), (0, 0.005, 0), 0.0055, 0.0065, satin
    )
    eye.parent = pivot
    bush = _annulus(
        "Moving bronze eye bush", (0, -0.005, 0), (0, 0.005, 0), 0.00425, 0.0055, brass
    )
    bush.parent = pivot
    for y in [-0.0060, 0.0051]:
        _annulus(
            "Axle thrust washer",
            (0, y, 0.32),
            (0, y + 0.0009, 0.32),
            0.00425,
            0.0070,
            ptfe,
        )
    rod = cylinder(
        "Slender steel pendulum rod",
        (0, 0, -0.006),
        (0, 0, -p["rod_length_m"]),
        p["rod_radius_m"],
        satin,
    )
    rod.parent = pivot
    neck = _annulus(
        "Threaded bob neck",
        (0, 0, -p["length_m"] + 0.0175),
        (0, 0, -p["length_m"] + 0.0215),
        0.0015,
        0.0025,
        satin,
    )
    neck.parent = pivot
    _cut(
        bpy.data.objects["Axle bearing plate"],
        cylinder(
            "Temporary bearing plate bore",
            (0, 0.018, 0.32),
            (0, 0.028, 0.32),
            0.0043,
            satin,
            64,
        ),
    )
    _cut(
        bpy.data.objects["Cantilever walnut crossbeam"],
        cylinder(
            "Temporary crossbeam axle bore",
            (0, 0.026, 0.32),
            (0, 0.060, 0.32),
            0.0044,
            satin,
            64,
        ),
    )
    # Engraved markings sit on the surface. The small plaque is mechanically fastened.
    plaque = bpy.data.objects["Inlaid toy badge"]
    plaque.dimensions = (0.066, 0.021, 0.0005)
    plaque.location.z = 0.02225
    _assign(plaque, satin)
    bpy.data.objects["Badge wordmark"].data.size = 0.0045
    bpy.data.objects["Badge wordmark"].location.y = -0.052
    bpy.data.objects["Badge wordmark"].location.z = 0.02255
    bpy.data.objects["Badge subtitle"].data.body = "MECHANICAL TOY"
    bpy.data.objects["Badge subtitle"].data.size = 0.0022
    bpy.data.objects["Badge subtitle"].location.y = -0.059
    bpy.data.objects["Badge subtitle"].location.z = 0.02255
    for x in [-0.153, -0.097]:
        cap = cylinder(
            "Plaque retaining screw",
            (x, -0.0458, 0.0224),
            (x, -0.0458, 0.023),
            0.0009,
            satin,
            24,
        )
        cut = cube(
            "Temporary plaque slot",
            (x, -0.0458, 0.023),
            (0.0012, 0.00025, 0.0003),
            satin,
            0,
        )
        _cut(cap, cut)
    for obj in bpy.data.objects:
        if obj.name.startswith("Engraved scale tick"):
            obj.location.z = 0.022005
            obj.scale.z = 0.08
            _assign(obj, dark)
    # Replace the display shelf with a real window and a table carrying a few working objects.
    prefixes = [
        "Continuous home wall",
        "Matte oak wall shelf",
        "Shelf hidden steel support",
        "Shelf wall mounting angle",
        "Window vertical mullion",
        "Window horizontal mullion",
    ]
    for obj in list(bpy.data.objects):
        if obj.type == "LIGHT" or any(obj.name.startswith(s) for s in prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)
    plaster, paint = _principled(
        "Warm mineral painted room wall", (0.53, 0.51, 0.46), 0, 0.83
    )
    wall = cube(
        "Continuous home wall", (0, 0.80, 0.72), (6, 0.10, 3.6), plaster, 0.0005
    )
    _cut(
        wall,
        cube(
            "Temporary actual window opening",
            (-0.49 + ap["window_visual_shift_x_m"], 0.80, 0.66),
            (0.66, 0.16, 1.02),
            plaster,
            0,
        ),
    )
    joinery, _ = _principled(
        "Satin white-painted window frame", (0.64, 0.64, 0.58), 0, 0.39
    )
    for x in [-0.835, -0.145]:
        cube(
            "Window vertical frame",
            (x, 0.742, 0.66),
            (0.035, 0.072, 1.10),
            joinery,
            0.0012,
        )
    for z in [0.1325, 1.1875]:
        cube(
            "Window horizontal frame",
            (-0.49, 0.742, z),
            (0.72, 0.072, 0.035),
            joinery,
            0.0012,
        )
    cube("Window sill", (-0.49, 0.695, 0.124), (0.78, 0.17, 0.026), joinery, 0.002)
    glass, bsdf = _principled(
        "Clear two-millimetre window glass", (0.96, 0.98, 1), 0, 0.045
    )
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    bsdf.inputs["IOR"].default_value = 1.45
    cube("Window glazing", (-0.49, 0.782, 0.66), (0.65, 0.002, 1.02), glass, 0)
    outside, bsdf = _principled(
        "Bright overcast exterior through glass", (0.72, 0.83, 0.91), 0, 1.0
    )
    bsdf.inputs["Emission Color"].default_value = (0.82, 0.90, 1.0, 1)
    bsdf.inputs["Emission Strength"].default_value = 2.5
    cube(
        "Exterior daylight beyond the window",
        (-0.49, 0.87, 0.66),
        (0.65, 0.008, 1.02),
        outside,
        0,
    )
    _curtain(cube)
    window = _rect_light(
        "Large daylight window",
        ap["window_position_m"],
        ap["window_target_m"],
        ap["window_power_W"],
        0.58,
        0.96,
    )
    window.data.color = ap["window_color_linear"]
    cylinder(
        "Curtain support rod", (-0.88, 0.65, 1.285), (-0.19, 0.65, 1.285), 0.0065, brass
    )
    bounce = _rect_light(
        "Diffuse reflection from the opposite room wall",
        (0.30, -0.72, 0.72),
        (0, 0, 0.14),
        ap["room_bounce_power_W"],
        1.25,
        0.90,
    )
    bounce.data.color = (1.0, 0.98, 0.95)
    # Shift the whole window consistently so the wet-looking reflection leaves the central base.
    for obj in bpy.data.objects:
        if obj.name.startswith(
            ("Window ", "Exterior daylight", "Sheer linen", "Curtain support")
        ):
            obj.location.x += ap["window_visual_shift_x_m"]
    # The HDRI carries room reflections; the modeled window explains the dominant light direction.
    for node in sc.world.node_tree.nodes:
        if node.type == "BACKGROUND":
            node.inputs["Strength"].default_value = ap["world_strength"]
        if node.type == "MAPPING":
            node.inputs["Rotation"].default_value[2] = math.radians(
                ap["hdri_rotation_deg"]
            )
    audits.append(
        _prop_place(
            "potted_plant_02",
            ap["plant_base_m"],
            ap["background_plant_height_m"],
            rotation=(0, 0, 0.25),
        )
    )
    audits.append(
        _prop_place(
            "book_encyclopedia_set_01",
            ap["books_base_m"],
            0.24,
            rotation=(0, -math.pi / 2, 0.06),
            dimension="long_edge",
            stack_books=True,
        )
    )
    audits.append(
        _prop_place(
            "binder_notebook",
            ap["notebook_base_m"],
            0.28,
            rotation=(0, 0, -0.16),
            dimension="long_edge",
        )
    )
    # A six-sided pencil, sharpened cedar and graphite, rests directly on the table.
    yellow, _ = _principled("Used ochre pencil paint", (0.45, 0.24, 0.025), 0, 0.42)
    cedar, _ = _principled("Sharpened pencil cedar", (0.40, 0.23, 0.10), 0, 0.66)
    graphite, _ = _principled("Graphite point", (0.018, 0.022, 0.025), 0.15, 0.5)
    start = Vector((0.36, 0.215, 0.0031))
    direction = Vector((-1, 0.14, 0)).normalized()
    end = start + direction * 0.145
    cylinder("Hexagonal pencil body", start, end, 0.0031, yellow, 6)
    bpy.ops.mesh.primitive_cone_add(
        vertices=48,
        radius1=0.0031,
        radius2=0.0005,
        depth=0.010,
        location=end + direction * 0.005,
    )
    tip = bpy.context.object
    tip.name = "Sharpened cedar pencil tip"
    tip.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    _assign(tip, cedar)
    point = cylinder(
        "Graphite pencil point",
        end + direction * 0.0095,
        end + direction * 0.012,
        0.0005,
        graphite,
        24,
    )
    rubber, _ = _principled("Used pencil eraser", (0.37, 0.15, 0.12), 0, 0.85)
    ferrule = cylinder(
        "Pencil ferrule", start - direction * 0.009, start, 0.0032, satin, 48
    )
    eraser = cylinder(
        "Pencil eraser",
        start - direction * 0.017,
        start - direction * 0.009,
        0.0030,
        rubber,
        48,
    )
    pencil = [bpy.data.objects["Hexagonal pencil body"], tip, point, ferrule, eraser]
    lo, hi = _bounds(pencil)
    for o in pencil:
        o.location.z += 0.00002 - float(lo[2])
    sc.camera.data.dof.aperture_fstop = ap["aperture_fstop"]
    sc["asset_scale_audit_json"] = json.dumps(audits)
    sc["manufacturing_audit_json"] = json.dumps(
        {
            "upright_bottom_m": ap["upright_visual_bottom_m"],
            "base_top_m": 0.022,
            "upright_base_gap_m": abs(ap["upright_visual_bottom_m"] - 0.022),
            "mounting_plate_has_socket": True,
            "hinge_eye_bore_radius_m": 0.00425,
            "shaft_radius_m": 0.0042,
            "radial_running_clearance_m": 0.00005,
            "rear_bush_meets_bearing_plate": True,
            "plaque_surface_seated": True,
            "pencil_radius_m": 0.0031,
            "fixed_collision_model_modified": False,
            "visual_scope": "Cosmetic light hardware and substrate details; original native hinge and axial elastic models are reused unchanged.",
        }
    )
