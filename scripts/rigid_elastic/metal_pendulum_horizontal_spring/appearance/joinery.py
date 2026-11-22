"""Manufactured, lightly handled tabletop apparatus; appearance only, in metres.

All noise is evaluated in object coordinates with fixed seeds. No pose, contact
surface, elastic mesh, light or material is animated by this module.
"""

import json
import math
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import bpy
from mathutils import Matrix, Vector

from appearance.room import _assign, _cut, _principled
from appearance.surfaces import _finish_metal, _scanned_wood
from scene_paths import ASSET_DIR, CATALOG_DIR


def _rounded_plinth(obj, dims, radius, edge):
    """Router-cut XY corners, followed by a much smaller edge round-over."""
    hx, hy, hz = (x / 2 for x in dims)
    outline = []
    for cx, cy, start in [
        (hx - radius, hy - radius, 0),
        (-hx + radius, hy - radius, 90),
        (-hx + radius, -hy + radius, 180),
        (hx - radius, -hy + radius, 270),
    ]:
        for j in range(13):
            a = math.radians(start + 90 * j / 12)
            outline.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    count = len(outline)
    vertices = [(x, y, z) for z in [-hz, hz] for x, y in outline]
    faces = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
    faces += [
        (j, (j + 1) % count, (j + 1) % count + count, j + count) for j in range(count)
    ]
    mesh = bpy.data.meshes.new("Router-cut solid walnut plinth")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj.data = mesh
    obj.modifiers.clear()
    uv = mesh.uv_layers.new(name="Metre-scale timber grain")
    for face in mesh.polygons:
        axis = max(range(3), key=lambda k: abs(face.normal[k]))
        for li in face.loop_indices:
            co = mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv = (co.y, co.x) if axis == 2 else (co.z, co.x)
        face.use_smooth = face.index > 1
    bevel = obj.modifiers.new("Sanded 1.8 mm edge round-over", "BEVEL")
    bevel.width = edge
    bevel.segments = 6
    bevel.affect = "EDGES"
    bevel.angle_limit = math.radians(35)
    weighted = obj.modifiers.new("Planar face normals", "WEIGHTED_NORMAL")
    weighted.keep_sharp = True


def _endgrain(name, long_axis):
    """Cross-cut growth rings and open pores, at a 1.4 mm growth-ring pitch."""
    m, p = _principled(name, (0.15, 0.10, 0.055), 0, 0.61)
    n, links = m.node_tree.nodes, m.node_tree.links
    co = n.new("ShaderNodeTexCoord")
    sep = n.new("ShaderNodeSeparateXYZ")
    links.new(co.outputs["Object"], sep.inputs[0])
    xy = n.new("ShaderNodeCombineXYZ")
    axes = ["Y", "Z"] if long_axis == "X" else ["X", "Y"]
    links.new(sep.outputs[axes[0]], xy.inputs["X"])
    links.new(sep.outputs[axes[1]], xy.inputs["Y"])
    distance = n.new("ShaderNodeVectorMath")
    distance.operation = "DISTANCE"
    distance.inputs[1].default_value = (0.065, 0.037, 0)
    links.new(xy.outputs[0], distance.inputs[0])
    phase = n.new("ShaderNodeMath")
    phase.operation = "MULTIPLY"
    phase.inputs[1].default_value = 2 * math.pi / 0.0014
    links.new(distance.outputs["Value"], phase.inputs[0])
    ring = n.new("ShaderNodeMath")
    ring.operation = "SINE"
    links.new(phase.outputs[0], ring.inputs[0])
    tone = n.new("ShaderNodeMapRange")
    tone.inputs["From Min"].default_value = -1
    tone.inputs["From Max"].default_value = 1
    tone.inputs["To Min"].default_value = 0.32
    tone.inputs["To Max"].default_value = 0.70
    links.new(ring.outputs[0], tone.inputs[0])
    color = n.new("ShaderNodeMixRGB")
    color.inputs[1].default_value = (0.075, 0.047, 0.026, 1)
    color.inputs[2].default_value = (0.21, 0.14, 0.078, 1)
    links.new(tone.outputs[0], color.inputs[0])
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 7300
    noise.inputs["Detail"].default_value = 2
    links.new(co.outputs["Object"], noise.inputs[0])
    pore = n.new("ShaderNodeMath")
    pore.operation = "LESS_THAN"
    pore.inputs[1].default_value = 0.32
    links.new(noise.outputs["Fac"], pore.inputs[0])
    pores = n.new("ShaderNodeMixRGB")
    pores.inputs[2].default_value = (0.039, 0.024, 0.013, 1)
    links.new(pore.outputs[0], pores.inputs[0])
    links.new(color.outputs[0], pores.inputs[1])
    links.new(pores.outputs[0], p.inputs["Base Color"])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.11
    bump.inputs["Distance"].default_value = 0.000016
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs[0], p.inputs["Normal"])
    p.inputs["Coat Weight"].default_value = 0.025
    return m


def _wood_finish(obj, ap, index):
    is_base = index == 0
    rough = ap["base_roughness_range"] if is_base else ap["stand_roughness_range"]
    manifest = json.loads((CATALOG_DIR / "wood_finish.json").read_text())
    asset = manifest["assets"][0]
    mat, p = _principled("Satin oil / " + obj.name, (0.12, 0.08, 0.04))
    mat["grain_material"] = True
    n, links = mat.node_tree.nodes, mat.node_tree.links
    uv = n.new("ShaderNodeTexCoord")
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1 / ap["fine_wood_scan_span_m"],) * 3
    mapping.inputs["Location"].default_value = (
        0.13 + 0.19 * index,
        0.23 + 0.17 * index,
        0,
    )
    links.new(uv.outputs["UV"], mapping.inputs[0])
    textures = {}
    for entry in asset["files"]:
        image = bpy.data.images.load(
            str(ASSET_DIR / "joinery_wood" / entry["relative_path"]), check_existing=True
        )
        image.colorspace_settings.name = (
            "sRGB" if entry["role"] == "Diffuse" else "Non-Color"
        )
        node = n.new("ShaderNodeTexImage")
        node.image = image
        links.new(mapping.outputs[0], node.inputs[0])
        textures[entry["role"]] = node
    color = n.new("ShaderNodeMixRGB")
    color.blend_type = "MULTIPLY"
    color.inputs[0].default_value = 1
    color.inputs[2].default_value = (*ap["fine_wood_tint_linear"], 1)
    links.new(textures["Diffuse"].outputs["Color"], color.inputs[1])
    links.new(color.outputs[0], p.inputs["Base Color"])
    remap = n.new("ShaderNodeMapRange")
    remap.inputs["To Min"].default_value, remap.inputs["To Max"].default_value = rough
    links.new(textures["Rough"].outputs["Color"], remap.inputs[0])
    links.new(remap.outputs[0], p.inputs["Roughness"])
    normal = n.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.12
    links.new(textures["nor_gl"].outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs[0], p.inputs["Normal"])
    p = mat.node_tree.nodes.get("Principled BSDF")
    p.inputs["Coat Weight"].default_value = 0.025
    p.inputs["Coat Roughness"].default_value = 0.40
    p.inputs["IOR"].default_value = 1.46
    for node in mat.node_tree.nodes:
        if node.type == "NORMAL_MAP":
            node.inputs["Strength"].default_value = 0.12
    _assign(obj, mat)
    axis = "Z" if index == 1 else "X"
    end = _endgrain("Cross-cut walnut / " + obj.name, axis)
    obj.data.materials.append(end)
    for face in obj.data.polygons:
        face.material_index = int(abs(getattr(face.normal, axis.lower())) > 0.96)
    if not is_base:
        for mod in obj.modifiers:
            if mod.type == "BEVEL":
                mod.width = 0.00115
                mod.segments = 6
    return {
        "object": obj.name,
        "long_grain_axis": axis,
        "endgrain_faces": sum(f.material_index == 1 for f in obj.data.polygons),
        "roughness_range": rough,
        "coat_weight": 0.025,
    }


def _pan_head(obj, cube, material, index):
    """Replace cylindrical caps by pan heads with actual recessed cross drives."""
    z0 = min(v.co.z for v in obj.data.vertices)
    z1 = max(v.co.z for v in obj.data.vertices)
    r = max(math.hypot(v.co.x, v.co.y) for v in obj.data.vertices)
    h = z1 - z0
    profile = [
        (r * 0.92, z0),
        (r, z0 + 0.12 * h),
        (r, z0 + 0.40 * h),
        (r * 0.91, z0 + 0.74 * h),
        (r * 0.64, z0 + 0.96 * h),
        (0.00002, z1),
    ]
    N = 48
    vertices = [
        (rr * math.cos(2 * math.pi * j / N), rr * math.sin(2 * math.pi * j / N), z)
        for rr, z in profile
        for j in range(N)
    ]
    faces = [tuple(reversed(range(N)))]
    for k in range(len(profile) - 1):
        faces += [
            (k * N + j, k * N + (j + 1) % N, (k + 1) * N + (j + 1) % N, (k + 1) * N + j)
            for j in range(N)
        ]
    faces.append(tuple(range((len(profile) - 1) * N, len(profile) * N)))
    mesh = bpy.data.meshes.new("Pan head with recessed cross drive")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for face in mesh.polygons:
        face.use_smooth = face.index not in (0, len(mesh.polygons) - 1)
    obj.data = mesh
    obj.modifiers.clear()
    _assign(obj, material)
    transform = obj.matrix_world @ Matrix.Rotation(
        math.radians((index * 37) % 89 - 44), 4, "Z"
    )
    for angle in [0, math.pi / 2]:
        cut = cube(
            "Temporary actual cross drive",
            (0, 0, 0),
            (r * 1.22, r * 0.20, h * 0.70),
            material,
            0,
        )
        cut.matrix_world = (
            transform
            @ Matrix.Translation((0, 0, z1 - h * 0.12))
            @ Matrix.Rotation(angle, 4, "Z")
        )
        _cut(obj, cut)
    bevel = obj.modifiers.new("Deburred screw recess", "BEVEL")
    bevel.width = 0.000025
    bevel.segments = 2
    obj.modifiers.new("Pan head normals", "WEIGHTED_NORMAL")


def _weld(name, points, material, radius=0.00065):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for p, co in zip(spline.points, points):
        p.co = (*co, 1)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def finish_scene(sc, c, helpers):
    ap = c["appearance"]
    base = bpy.data.objects["Walnut toy base"]
    _rounded_plinth(
        base,
        ap["base_dimensions_m"],
        ap["base_corner_radius_m"],
        ap["base_edge_radius_m"],
    )
    timber = [
        _wood_finish(bpy.data.objects[name], ap, i)
        for i, name in enumerate(
            ["Walnut toy base", "Rear walnut upright", "Cantilever walnut crossbeam"]
        )
    ]
    # The photographed desk roughness is kept spatially varying, without a broad wet sheen.
    table = bpy.data.objects["Oak dining / science table"]
    desk = _scanned_wood(
        "wood_table_worn",
        "Diffuse used writing desk",
        ap["desk_scan_span_m"],
        ap["desk_tint_linear"],
        (0.15, 0.23),
        ap["desk_roughness_range"],
        saturation=0.66,
    )
    desk.node_tree.nodes.get("Principled BSDF").inputs["Coat Weight"].default_value = 0
    _assign(table, desk)

    satin = _finish_metal(
        "Fine satin stainless / handled hardware", (0.49, 0.50, 0.51), 0.36, 0.28
    )
    weld = _finish_metal(
        "TIG fillet with unpolished surface", (0.29, 0.30, 0.31), 0.49, 0.10
    )
    bob = _finish_metal(
        "Polished solid steel / slight handling haze",
        (0.56, 0.58, 0.60),
        ap["ball_surface_roughness"],
        0.035,
    )
    _assign(bpy.data.objects["Solid steel bob | measured diameter 36 mm"], bob)
    screw_objects = sorted(
        [
            o
            for o in bpy.data.objects
            if o.type == "MESH"
            and "screw" in o.name.lower()
            and "washer" not in o.name.lower()
        ],
        key=lambda o: o.name,
    )
    for i, obj in enumerate(screw_objects):
        _pan_head(obj, helpers["cube"], satin, i)
    for obj in bpy.data.objects:
        if obj.type == "MESH" and any(
            s in obj.name.lower()
            for s in [
                "mounting foot",
                "backing",
                "bearing plate",
                "bracket",
                "heel",
                "gusset",
            ]
        ):
            _assign(obj, satin)
    # Fillets follow the actual backing/gusset and foot junctions, away from the moving guide.
    for sign in [-1, 1]:
        yy = sign * 0.0236
        _weld(
            "Backing gusset TIG fillet",
            [
                (0.133 + 0.00035 * math.sin(j * 2.8), yy, 0.028 + j * 0.0014)
                for j in range(20)
            ],
            weld,
        )
        _weld(
            "Gusset foot TIG fillet",
            [
                (0.134 + j * 0.0008, yy, 0.0273 + 0.00004 * math.sin(j * 2.5))
                for j in range(19)
            ],
            weld,
        )
    # A warm satin plaque can be read as engraved metal rather than a white graphic.
    badge, p = _principled("Brushed aged brass nameplate", (0.36, 0.24, 0.105), 1, 0.48)
    _assign(bpy.data.objects["Inlaid toy badge"], badge)
    # Keep all props, subject position and the full motion silhouette in the accepted camera.
    if ap["lighting_revision"]:
        window = bpy.data.objects["Large daylight window"]
        window.data.shape = "RECTANGLE"
        window.data.size = ap["window_emitter_size_m"][0]
        window.data.size_y = ap["window_emitter_size_m"][1]
        window.data.energy = ap["window_power_W"]
        bounce = bpy.data.objects["Diffuse reflection from the opposite room wall"]
        bounce.data.energy = ap["room_bounce_power_W"]
        bounce.location = ap["room_bounce_position_m"]
        bounce.rotation_euler = (
            (Vector(ap["room_bounce_target_m"]) - bounce.location)
            .to_track_quat("-Z", "Y")
            .to_euler()
        )
        bounce.data.size, bounce.data.size_y = ap["room_bounce_size_m"]
        # Only the optical focus changes; geometry and the rigid/elastic pose stay exact.
        focus = Vector(ap["focus_m"])
        sc.camera.data.dof.focus_distance = (focus - sc.camera.location).length
    sc["craft_finish_audit_json"] = json.dumps(
        {
            "wood": timber,
            "base_construction": "18 mm solid dark hardwood with cross-cut end grain",
            "xy_corner_radius_m": ap["base_corner_radius_m"],
            "edge_roundover_m": ap["base_edge_radius_m"],
            "fastener_count": len(screw_objects),
            "fastener_drive": "actual recessed cross drive, fixed varied orientation",
            "fillet_count": 4,
            "wear_coordinates": "object space, fixed, no animation",
            "main_contact_geometry_changed": False,
            "native_hinge_and_slider_unchanged": True,
        }
    )
