"""Daylit children's playroom: measured furniture, photographed finishes, toy chest, star ball and football.

room(), toys() and lighting() build the scene in layers: the full-scale playroom, photographic
material maps, measured furniture and props, lived-in detail, moulded storage, the play corner, measured
finishes and window sunlight, the cleared window and display car, the toy chest and stitched football, the
white paneled chest, real-scale textiles, and finally the photographic fixes below. Helpers suffixed with a
layer name (room_textiles, toys_paneled_chest, ...) are the lower layers that the final functions build on.

Final photographic pass:

* B01 keeps the supplied refined 18 cm mesh and its star motif, but the pale, UV-torn atlas print becomes an
  evenly laid cream pad print on a pigmented vinyl body with a satin coat and moulding texture, so the ball
  reads as a real toy and its solved spin is visible.
* B02 keeps the stitched panels; the white panels receive the asset's own scuff map at low strength (light
  indoor use) instead of a uniform white.
* Printed props: book covers that carried stock titles and watermarks become plain cloth-bound boards; the
  floor picture book (printed title) is removed; the scale car's number plate and badge become blank
  metal/paint.
* The floor is a scanned oak plank floor (appearance only; contact parameters unchanged).
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector, Matrix, Quaternion
from pcve_assets import asset


def linear(color):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in color)


def material(name, color, roughness=0.4, micro=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*linear(color), 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["IOR"].default_value = 1.46
    if micro:
        coord = nodes.new("ShaderNodeTexCoord")
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 1000
        noise.inputs["Detail"].default_value = 2
        links.new(coord.outputs["Object"], noise.inputs["Vector"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        bump.inputs["Distance"].default_value = micro
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return mat


def cube(name, dimensions, location, mat, bevel=0.0, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = 4
        modifier = obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
        modifier.keep_sharp = True
    if parent:
        obj.parent = parent
    return obj


def cylinder(name, radius, depth, location, mat, parent=None, rotation=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    modifier = obj.modifiers.new("Moulded edge", "BEVEL")
    modifier.width = min(0.0015, depth * 0.12)
    modifier.segments = 3
    obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    for poly in obj.data.polygons:
        poly.use_smooth = len(poly.vertices) == 4
    if rotation:
        obj.rotation_euler = rotation
    if parent:
        obj.parent = parent
    return obj


def root(name):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.rotation_mode = "QUATERNION"
    return obj


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def difference(obj, cutter):
    bpy.context.view_layer.objects.active = cutter
    for modifier in list(cutter.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new("Manufacturing cavity", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def path_curve(name, points, radius, mat, parent=None, closed=False):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 2
    data.bevel_depth = radius
    data.bevel_resolution = 3
    spline = data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, xyz in zip(spline.points, points):
        point.co = (*xyz, 1)
    spline.use_cyclic_u = closed
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def rounded_loop(width, height, radius, origin=(0, 0, 0), plane="XY"):
    points = []
    for cx, cy, start in ((width / 2 - radius, height / 2 - radius, 0),
                          (-width / 2 + radius, height / 2 - radius, 90),
                          (-width / 2 + radius, -height / 2 + radius, 180),
                          (width / 2 - radius, -height / 2 + radius, 270)):
        for i in range(9):
            angle = math.radians(start + i * 90 / 8)
            u, v = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
            if plane == "XY":
                p = (u, v, 0)
            elif plane == "XZ":
                p = (u, 0, v)
            else:
                p = (0, u, v)
            points.append(tuple(a + b for a, b in zip(p, origin)))
    return points


def text(name, body, location, size, mat, parent=None, front=False):
    data = bpy.data.curves.new(name, "FONT")
    data.body, data.size, data.align_x, data.align_y = body, size, "CENTER", "CENTER"
    data.space_character = 1.15
    data.extrude = 0.00001
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    if front:
        obj.rotation_euler.x = math.pi / 2
    data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def image_map(mat, file, vector, color=False):
    if not Path(file).is_file():
        raise FileNotFoundError(file)
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(str(file), check_existing=True)
    node.image.colorspace_settings.name = "sRGB" if color else "Non-Color"
    node.projection, node.projection_blend = "BOX", 0.15
    mat.node_tree.links.new(vector, node.inputs["Vector"])
    return node


def photographed_material(name, directory, tile_m, tint=None):
    mat = material(name, tint or (0.8, 0.7, 0.5), 0.5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs[3].default_value = 1 / tile_m
    links.new(coord.outputs["Object"], scale.inputs[0])
    directory = Path(directory)
    identifier = directory.name
    color = image_map(mat, directory / f"{identifier}_diff_1k.jpg", scale.outputs[0], True)
    rough = image_map(mat, directory / f"{identifier}_rough_1k.jpg", scale.outputs[0])
    height = image_map(mat, directory / f"{identifier}_disp_1k.jpg", scale.outputs[0])
    if tint:
        gray = nodes.new("ShaderNodeRGBToBW")
        links.new(color.outputs["Color"], gray.inputs[0])
        ramp = nodes.new("ShaderNodeValToRGB")
        for element, factor in zip(ramp.color_ramp.elements, (0.60, 1.25)):
            element.color = (*(min(1, v * factor) for v in linear(tint)), 1)
        links.new(gray.outputs[0], ramp.inputs[0])
        links.new(ramp.outputs[0], shader.inputs["Base Color"])
        shader.inputs["Sheen Weight"].default_value = 0.16
        low, high = 0.72, 0.94
    else:
        links.new(color.outputs[0], shader.inputs["Base Color"])
        low, high = 0.32, 0.56
    remap = nodes.new("ShaderNodeMapRange")
    remap.inputs["To Min"].default_value = low
    remap.inputs["To Max"].default_value = high
    links.new(rough.outputs[0], remap.inputs[0])
    links.new(remap.outputs[0], shader.inputs["Roughness"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.00024 if tint else 0.00016
    bump.inputs["Strength"].default_value = 0.38 if tint else 0.20
    links.new(height.outputs[0], bump.inputs["Height"])
    links.new(bump.outputs[0], shader.inputs["Normal"])
    return mat


def floor_material():
    mat = material("Grey linoleum | fine marbling and varied satin finish", (0.72, 0.73, 0.73), 0.46)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 32
    noise.inputs["Detail"].default_value = 3.5
    noise.inputs["Roughness"].default_value = 0.73
    links.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*linear((0.66, 0.68, 0.68)), 1)
    ramp.color_ramp.elements[1].color = (*linear((0.76, 0.77, 0.76)), 1)
    links.new(noise.outputs["Fac"], ramp.inputs[0])
    links.new(ramp.outputs[0], shader.inputs["Base Color"])
    sheen = nodes.new("ShaderNodeMapRange")
    sheen.inputs["To Min"].default_value = 0.38
    sheen.inputs["To Max"].default_value = 0.54
    links.new(noise.outputs["Fac"], sheen.inputs[0])
    links.new(sheen.outputs[0], shader.inputs["Roughness"])
    micro = nodes.new("ShaderNodeTexNoise")
    micro.inputs["Scale"].default_value = 1400
    micro.inputs["Detail"].default_value = 2
    links.new(coord.outputs["Object"], micro.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.000018
    bump.inputs["Strength"].default_value = 0.12
    links.new(micro.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs[0], shader.inputs["Normal"])
    return mat


def bounds_furnished(objects):
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(v) for obj in objects if obj.type == "MESH" for v in obj.bound_box]
    return [Vector([fn(p[i] for p in corners) for i in range(3)]) for fn in (min, max)]


def append_meshes(path, names=None, prefix="Room asset"):
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.objects = [n for n in source.objects if names is None or n in names]
    objects = [o for o in target.objects if o and o.type == "MESH"]
    for obj in objects:
        bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.update()
    transforms = [(o, o.matrix_world.copy()) for o in objects]
    for obj, matrix in transforms:
        obj.parent = None
        obj.matrix_world = matrix
        obj.animation_data_clear()
        obj.hide_render = False
        obj.name = prefix + " | " + obj.name
    return objects


def place_group(objects, position, angle=0.0, height=None, scale=1.0):
    lo, hi = bounds_furnished(objects)
    if height is not None:
        scale = height / (hi.z - lo.z)
    center = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    transform = Matrix.Translation(Vector(position)) @ Matrix.Rotation(angle, 4, "Z") @ Matrix.Scale(scale, 4) @ Matrix.Translation(-center)
    for obj in objects:
        obj.matrix_world = transform @ obj.matrix_world
    lo, hi = bounds_furnished(objects)
    return {"dimensions_m": list(hi - lo), "world_bounds_m": [list(lo), list(hi)], "uniform_scale": scale}


def flat_stroke(name, points, width, mat):
    """Thin ink ribbon, with no cylindrical relief above drawing paper."""
    vertices, faces = [], []
    for a, b in zip(points, points[1:]):
        a, b = Vector(a), Vector(b)
        tangent = b - a
        side = Vector((-tangent.z, 0, tangent.x)).normalized() * width / 2
        start = len(vertices)
        vertices.extend((a - side, a + side, b + side, b - side))
        faces.append(tuple(range(start, start + 4)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def rug(center, radii, mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=192, radius=1, depth=0.008, location=(*center, 0.0045))
    obj = bpy.context.object
    obj.name = "Play area | oval woven rug outside collision path"
    obj.scale = (*radii, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("Soft bound rug edge", "BEVEL")
    bevel.width, bevel.segments = 0.003, 3
    edge = material("Rug | blue-grey woven binding", (0.48, 0.57, 0.60), 0.88)
    points = [(center[0] + radii[0] * math.cos(i * 2 * math.pi / 192),
               center[1] + radii[1] * math.sin(i * 2 * math.pi / 192), 0.008) for i in range(192)]
    path_curve("Play area | sewn rug binding", points, 0.004, edge, closed=True)
    # Woven bands read as a domestic play mat; the interaction stays on linoleum.
    for r in (0.50, 0.72, 0.91):
        vertices, faces = [], []
        for i in range(193):
            a = i * 2 * math.pi / 192
            for delta in (-.005, .005):
                vertices.append((center[0] + radii[0] * (r + delta) * math.cos(a),
                                 center[1] + radii[1] * (r + delta) * math.sin(a), .0086))
            if i:
                faces.append((2*i-2, 2*i-1, 2*i+1, 2*i))
        mesh = bpy.data.meshes.new("Flat woven rug band")
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(edge)
        band = bpy.data.objects.new("Play area | flat woven rug stripe", mesh)
        bpy.context.collection.objects.link(band)


def room_furnished(cfg):
    directory = asset(cfg["appearance"]["material_asset_directory"])
    wood = photographed_material("PBR | photographed birch plywood", directory / "plywood", 0.5)
    linen = photographed_material("PBR | woven neutral canvas", directory / "rough_linen", 0.3, (0.74, 0.70, 0.60))
    sage = photographed_material("PBR | woven sage canvas", directory / "rough_linen", 0.3, (0.51, 0.60, 0.53))
    rugmat = photographed_material("PBR | woven play rug", directory / "rough_linen", 0.4, (0.76, 0.75, 0.65))
    paint = material("Room | warm ivory mineral paint", (0.88, 0.88, 0.84), 0.87, 0.00005)
    lower = material("Room | pale sage washable wall paint", (0.68, 0.76, 0.70), 0.67, 0.000025)
    trim = material("Room | satin white woodwork", (0.89, 0.89, 0.85), 0.39)
    cube("F01 | continuous level floor", (8, 8, 0.12), (0, 0, -0.06), floor_material())
    cube("Room | rear wall", (6.5, 0.15, 2.8), (0, 2.75, 1.4), paint)
    cube("Room | rear lower painted wall", (6.5, 0.008, 0.84), (0, 2.67, 0.42), lower)
    cube("Room | rear skirting", (6.5, 0.024, 0.10), (0, 2.65, 0.05), trim, 0.003)
    cube("Room | rear picture rail", (6.5, 0.018, 0.023), (0, 2.66, 0.85), trim, 0.002)
    cube("Room | left wall", (0.15, 8, 2.8), (-3.2, -1.2, 1.4), paint)
    cube("Room | right wall", (0.15, 8, 2.8), (3.25, -1.2, 1.4), paint)
    cube("Room | ceiling", (6.5, 8, 0.10), (0, -1.2, 2.85), paint)
    cube("Room | wall behind camera", (6.5, 0.15, 2.8), (0, -6.0, 1.4), paint)
    cube("Room | left skirting", (0.024, 8, 0.10), (-3.11, -1.2, 0.05), trim, 0.002)

    # A real, child-scale furniture set anchors the playroom context.
    tables = append_meshes(asset("blenderkit/kids_table_chairs/kids_table_chairs.blend"),
        ["Cylinder.007", "Cylinder.001", "Cylinder.005", "Cylinder.008"], "Play area | downloaded children's furniture")
    furniture = place_group(tables, (-1.65, 1.32, 0.009), angle=-0.12)
    rug((-1.65, 1.30), (1.05, 0.90), rugmat)
    drawing = append_meshes(asset("blenderkit/playroom/playroom.blend"),
                            ["felt_pen_1_low.002"], "Play area | downloaded drawing and markers")
    drawing_size = place_group(drawing, (-1.76, 1.34, .5315), angle=.23)

    # Open shelving at the original child-height; all contents are actual geometry.
    sx, sy = 0.65, 2.25
    cube("Shelf | recessed plinth", (1.95, 0.39, 0.055), (sx, sy, 0.0275), wood, 0.004)
    for z in (0.075, 0.36, 0.66):
        cube("Shelf | birch horizontal panel", (2.0, 0.40, 0.023), (sx, sy, z), wood, 0.002)
    for dx in (-0.989, -0.33, 0.33, 0.989):
        cube("Shelf | birch vertical divider", (0.022, 0.40, 0.60), (sx + dx, sy, 0.36), wood, 0.002)
    cube("Shelf | plywood back", (2, 0.012, 0.61), (sx, sy + 0.194, 0.36), wood, 0.001)
    for dx, mat in ((-0.66, linen), (0, sage), (0.66, linen)):
        center = (sx + dx, sy - 0.015, 0.202)
        box = cube("Shelf | open sewn fabric toy basket", (0.55, 0.31, 0.23), center, mat, 0.007)
        cutter = cube("Temporary fabric basket cavity", (0.53, 0.29, 0.25), (center[0], center[1], center[2] + 0.023), mat, 0.006)
        difference(box, cutter)
        cutter = cube("Temporary fabric handle", (0.085, 0.035, 0.026), (center[0], center[1] - 0.156, 0.25), mat, 0.009)
        difference(box, cutter)
        path_curve("Shelf | canvas rim binding", rounded_loop(0.54, 0.30, 0.009, (center[0], center[1], 0.316)), 0.0035, mat, closed=True)
    for i, (color, h) in enumerate((((0.71, 0.40, 0.29), .23), ((0.78, .68, .44), .21), ((.35, .53, .58), .24), ((.64, .71, .57), .22), ((.79, .76, .64), .205))):
        cover = material("Books | cloth board cover", color, .77)
        page = material("Books | warm page edges", (.84, .82, .74), .85)
        x = sx - .91 + i * .037
        cube("Shelf | bound children's book pages", (.027, .17, h - .007), (x, sy, .372 + h / 2), page, .001)
        for xx in (-.016, .016):
            cube("Shelf | book cloth cover", (.003, .18, h), (x + xx, sy, .372 + h / 2), cover, .0006)
        cube("Shelf | book spine", (.033, .005, h), (x, sy - .09, .372 + h / 2), cover, .001)
    penguin = append_meshes(asset("blenderkit/stuffed_penguin/stuffed_penguin.blend"), prefix="Shelf | downloaded plush penguin")
    plush_size = place_group(penguin, (sx + .03, sy - .01, .372), angle=0.12)
    car = append_meshes(asset("blenderkit/rally_toy_car/rally_toy_car.blend"), prefix="Play area | downloaded toy car")
    car_size = place_group(car, (-1.14, 1.82, .009), angle=-1.0)
    bunny = append_meshes(asset("blenderkit/cosmic_kids_bedroom/cosmic_kids_bedroom.blend"),
                          ["nv3d_bunny_chair"], "Reading corner | downloaded rabbit stool")
    bunny_size = place_group(bunny, (1.95, 1.84, .0), angle=0.0)
    # A folded blanket, spare blocks and an open picture book suggest recent use.
    for i in range(3):
        cube("Shelf | folded woven blanket", (.43, .28, .020), (sx + .65, sy, .386 + i * .021), sage, .008)
    cylinder("Shelf | wooden stacking base", .09, .02, (sx + .02, sy, .684), wood)
    for i, (r, color) in enumerate(zip((.075, .063, .049, .035), ((.71,.35,.23),(.82,.64,.30),(.41,.60,.55),(.34,.48,.60)))):
        cylinder("Shelf | painted wooden stacking ring", r, .023, (sx + .02, sy, .704 + i * .024), material("Stacker | painted wood", color, .48))

    # Rear window and imported pleated curtains stay in the same 3D light field.
    glass = material("Window | pale exterior daylight", (.80, .88, .94), .28)
    shader = glass.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Emission Color"].default_value = (*linear((.80, .88, .94)), 1)
    shader.inputs["Emission Strength"].default_value = .65
    cube("Window | daylight beyond glass", (1.45, .012, 1.30), (-1.72, 2.658, 1.72), glass)
    for x in (-2.465, -1.72, -.975):
        cube("Window | white timber vertical frame", (.036, .08, 1.36), (x, 2.60, 1.72), trim, .002)
    for z in (1.05, 1.72, 2.39):
        cube("Window | white timber horizontal frame", (1.52, .08, .036), (-1.72, 2.60, z), trim, .002)
    cube("Window | deep painted sill", (1.63, .23, .033), (-1.72, 2.55, 1.025), trim, .003)
    curtain_source = asset("blenderkit/cosmic_kids_bedroom/cosmic_kids_bedroom.blend")
    for x in (-2.57, -.87):
        curtain = append_meshes(curtain_source, ["01.004"], "Window | downloaded pleated curtain")
        place_group(curtain, (x, 2.47, .45), angle=math.pi / 2, height=1.98)
        # Narrow the gathered panel in its world horizontal direction.
        lo, hi = bounds_furnished(curtain)
        cx = (lo.x + hi.x) / 2
        for obj in curtain:
            obj.matrix_world = Matrix.Translation((cx, 0, 0)) @ Matrix.Diagonal((.52, 1, 1, 1)) @ Matrix.Translation((-cx, 0, 0)) @ obj.matrix_world
            for slot in obj.material_slots:
                slot.material = linen
    cylinder("Window | curtain pole", .012, 2.18, (-1.72, 2.48, 2.46), wood, rotation=(0, math.pi / 2, 0))

    # Children's artwork at a plausible height supplies the room's lived-in cues.
    paper = material("Artwork | matte drawing paper", (.91, .89, .79), .93)
    frame = material("Artwork | light natural frame", (.65, .51, .34), .52)
    for x, z, motif in ((.05, 1.29, 0), (.68, 1.32, 1), (1.31, 1.27, 2)):
        cube("Artwork | timber picture frame", (.45, .022, .38), (x, 2.64, z), frame, .004)
        cube("Artwork | cream paper", (.412, .001, .342), (x, 2.627, z), paper)
        colors = ((.77,.37,.25),(.80,.64,.31),(.40,.59,.57))
        for j, col in enumerate(colors):
            ink = material("Artwork | soft printed pigment", col, .92)
            if motif == 0:
                points = [(x - .14 + i * .28/32, 2.62635, z - .09 + j * .037 + .085 * math.sin(math.pi * i/32)) for i in range(33)]
            elif motif == 1:
                # Uneven mountain outlines drawn with felt-tip markers.
                points = [(x - .16, 2.62635, z - .10 + j * .025),
                          (x - .045 + j * .018, 2.62635, z + .10 - j * .012),
                          (x + .14, 2.62635, z - .09 + j * .025)]
            else:
                points = [(x + (.11 - j * .025) * math.cos(i * 2 * math.pi/45), 2.62635,
                           z + (.115 - j * .026) * math.sin(i * 2 * math.pi/45)) for i in range(46)]
            flat_stroke("Artwork | felt-tip drawing on paper", points, .008, ink)
    return {"ball_diameter_m": 2 * cfg["physics"]["ball"]["radius_m"],
        "storage_box_collision_dimensions_m": cfg["physics"]["box"]["dimensions_m"],
        "block_body_dimensions_m": cfg["physics"]["block"]["dimensions_m"],
        "children_table_group": furniture, "drawing_with_markers": drawing_size,
        "penguin": plush_size, "toy_car": car_size, "rabbit_stool": bunny_size,
        "shelf_dimensions_m": [2.0, .4, .672], "room_dimensions_m": [6.5, 7.95, 2.8],
        "asset_policy": "Downloaded BlenderKit furniture, plush, toy car and bedroom components; CC0 Poly Haven container geometry and PBR maps; all sources and modifications recorded in asset_manifest.json.",
        "collision_proxy_notes": "Frozen original rigid solve. Downloaded bin is resized to the original 72x44x40 cm envelope and the broad near contact panel is made planar at y=-0.22 m in body space. No hidden visual collider or altered trajectory. Original 4K PBR normal and roughness maps retained, diffuse recolored blue. Background rug and props remain outside the swept path."}


def photographic_surface(name, identifier, tile_m, tint=None, floor=False):
    folder = asset("scenes/ball_box_rebound/room_surfaces/" + identifier)
    mat = material(name, tint or (.83, .82, .78), .6)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    coordinate = nodes.new("ShaderNodeTexCoord")
    vector = coordinate.outputs["UV"]
    if not floor:
        coordinate = nodes.new("ShaderNodeNewGeometry")
        scale = nodes.new("ShaderNodeVectorMath")
        scale.operation = "SCALE"
        scale.inputs[3].default_value = 1 / tile_m
        links.new(coordinate.outputs["Position"], scale.inputs[0])
        vector = scale.outputs[0]
    maps = {}
    for label in ("diff", "rough", "nor_gl"):
        node = nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(folder / f"{identifier}_{label}_2k.jpg"), check_existing=True)
        node.image.colorspace_settings.name = "sRGB" if label == "diff" else "Non-Color"
        if not floor:
            node.projection, node.projection_blend = "BOX", .2
        links.new(vector, node.inputs["Vector"])
        maps[label] = node
    gray = nodes.new("ShaderNodeRGBToBW")
    links.new(maps["diff"].outputs["Color"], gray.inputs[0])
    ramp = nodes.new("ShaderNodeValToRGB")
    low, high = ((.62, .64, .65), (.78, .79, .79)) if floor else ((.79, .78, .74), (.88, .87, .83))
    ramp.color_ramp.elements[0].position = .02
    ramp.color_ramp.elements[1].position = .55 if floor else .9
    ramp.color_ramp.elements[0].color = (*linear(low), 1)
    ramp.color_ramp.elements[1].color = (*linear(high), 1)
    links.new(gray.outputs[0], ramp.inputs[0])
    links.new(ramp.outputs[0], shader.inputs["Base Color"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = .24 if floor else .74
    rough.inputs["To Max"].default_value = .49 if floor else .91
    links.new(maps["rough"].outputs[0], rough.inputs[0])
    links.new(rough.outputs[0], shader.inputs["Roughness"])
    if floor:
        normal = nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = .12
        links.new(maps["nor_gl"].outputs[0], normal.inputs["Color"])
        links.new(normal.outputs[0], shader.inputs["Normal"])
    else:
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Distance"].default_value = .000025
        bump.inputs["Strength"].default_value = .15
        links.new(maps["rough"].outputs[0], bump.inputs["Height"])
        links.new(bump.outputs[0], shader.inputs["Normal"])
    return mat


def remove_prefixes(prefixes):
    for obj in list(bpy.context.scene.objects):
        if obj.name.startswith(prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)


def glazing(name, dimensions, location):
    mat = material(name, (.97, .99, 1), .025)
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Transmission Weight"].default_value = 1
    shader.inputs["IOR"].default_value = 1.45
    pane = cube(name, dimensions, location, mat)
    # Thin clear glazing transmits the direct sky sample without requiring
    # refractive-caustic sampling; camera and reflection rays still see glass.
    pane.visible_shadow = False
    return pane


def room_lived_in(cfg):
    ledger = room_furnished(cfg)
    remove_prefixes(("Play area | downloaded children's furniture", "Play area | downloaded drawing and markers",
                     "Play area | flat woven rug stripe", "Play area | sewn rug binding",
                     "Reading corner |", "Artwork |", "Shelf | book", "Shelf | bound children's book",
                     "Window | daylight beyond glass", "Room | rear lower painted wall", "Room | rear picture rail",
                     "Room | rear wall", "Room | left wall", "Room | right wall", "Room | ceiling", "Room | wall behind camera"))
    # Full-length gathered curtains terminate just above the finished floor.
    for obj in bpy.context.scene.objects:
        if obj.name.startswith("Window | downloaded pleated curtain"):
            lo, hi = bounds_furnished([obj])
            z_scale = (2.43 - .025) / (hi.z - lo.z)
            obj.matrix_world = Matrix.Translation((0, 0, .025)) @ Matrix.Diagonal((1, 1, z_scale, 1)) @ Matrix.Translation((0, 0, -lo.z)) @ obj.matrix_world
    paint = photographic_surface("Room | photographic matte mineral paint", "white_plaster_02", 1.0)
    trim = bpy.data.materials.get("Room | satin white woodwork")
    # Complete enclosure, with openings rather than luminous planes pasted on walls.
    cube("Room | rear wall below window", (6.5, .15, 1.05), (0, 2.75, .525), paint)
    cube("Room | rear wall above window", (6.5, .15, .41), (0, 2.75, 2.595), paint)
    cube("Room | rear wall left pier", (.785, .15, 1.34), (-2.8575, 2.75, 1.72), paint)
    cube("Room | rear wall right pier", (4.225, .15, 1.34), (1.1375, 2.75, 1.72), paint)
    cube("Room | side wall below daylight aperture", (.15, 8.75, .75), (-3.2, -1.625, .375), paint)
    cube("Room | side wall above daylight aperture", (.15, 8.75, .35), (-3.2, -1.625, 2.625), paint)
    cube("Room | side wall front pier", (.15, 4.8, 1.7), (-3.2, -3.6, 1.60), paint)
    cube("Room | side wall rear pier", (.15, 1.75, 1.7), (-3.2, 1.875, 1.60), paint)
    cube("Room | right wall", (.15, 8.75, 2.8), (3.25, -1.625, 1.4), paint)
    cube("Room | ceiling", (6.5, 8.9, .15), (0, -1.625, 2.875), paint)
    cube("Room | wall behind camera", (6.5, .15, 2.8), (0, -6.0, 1.4), paint)
    for y in (-1.2, -.10, 1.0):
        cube("Side window | timber mullion", (.10, .032, 1.74), (-3.105, y, 1.60), trim, .002)
    for z in (.73, 1.60, 2.47):
        cube("Side window | timber rail", (.10, 2.26, .036), (-3.105, -.10, z), trim, .002)
    cube("Side window | sill", (.22, 2.32, .035), (-3.08, -.10, .72), trim, .003)
    glazing("Side window | thin clear glazing", (.003, 2.18, 1.68), (-3.20, -.10, 1.60))
    glazing("Rear window | thin clear glazing", (1.44, .003, 1.29), (-1.72, 2.75, 1.72))

    # UVs are in real metres: the linoleum photographic capture is two metres wide.
    floor = bpy.data.objects.get("F01 | continuous level floor")
    floor.dimensions = (6.6, 9.2, .12)
    floor.location = (0, -1.6, -.06)
    bpy.context.view_layer.update()
    floor.data.materials.clear()
    floor.data.materials.append(photographic_surface("Floor | photographed light-grey satin linoleum", "linoleum_brown", 2.0, floor=True))
    uv = floor.data.uv_layers.active or floor.data.uv_layers.new(name="Physical 2 m texture capture")
    for poly in floor.data.polygons:
        for loop_index in poly.loop_indices:
            vertex = floor.data.vertices[floor.data.loops[loop_index].vertex_index]
            point = floor.matrix_world @ vertex.co
            uv.data[loop_index].uv = (point.x / 2, point.y / 2)

    # Replace the decorative pastel furniture with a photographed wood-and-canvas set.
    table = append_meshes(asset("blenderkit/noos_kids_table/noos_kids_table.blend"), prefix="Play area | Noos wood table and chairs")
    furniture = place_group(table, (-1.48, 1.28, .009), angle=-.45)
    # A chair is naturally pulled back a few centimetres, without changing object scale.
    for obj in table:
        if obj.name.endswith(("Cube.007", "Cube.008", "Cube.005")):
            obj.location.x -= .04
            obj.location.y -= .035
    cozy = asset("blenderkit/cozy_living_room/cozy_living_room.blend")
    books = append_meshes(cozy, ["Book-1", "Book-2", "Book-3"], "Shelf | photographed book stack")
    book_size = place_group(books, (-.01, 2.21, .372), angle=.11)
    books2 = append_meshes(cozy, ["Cover book-03"], "Shelf | open illustrated book")
    place_group(books2, (.94, 2.24, .678), angle=-.10)
    pillow = append_meshes(cozy, ["pillow L.001"], "Reading corner | fabric floor cushion")
    for obj in pillow:
        obj.matrix_world = Matrix.Rotation(math.pi / 2, 4, "X") @ obj.matrix_world
    pillow_size = place_group(pillow, (1.75, 1.92, .0), angle=-.28, scale=.78)
    for obj in pillow:
        for slot in obj.material_slots:
            slot.material = bpy.data.materials.get("PBR | woven neutral canvas")
    # The mat has a woven, slightly irregular bound edge instead of a CAD ellipse.
    mat_obj = bpy.data.objects.get("Play area | oval woven rug outside collision path")
    mat_obj.data.materials[0].node_tree.nodes.get("Principled BSDF").inputs["Sheen Weight"].default_value = .22
    import random
    random.seed(cfg["appearance"]["seed"])
    thread = bpy.data.materials.get("PBR | woven neutral canvas")
    curve = bpy.data.curves.new("Rug | individual soft fringe fibres", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth, curve.bevel_resolution = .00038, 1
    for i in range(780):
        angle = 2 * math.pi * i / 780
        c, s = math.cos(angle), math.sin(angle)
        length = .010 + random.random() * .012
        spline = curve.splines.new("POLY")
        spline.points.add(2)
        for point, amount, z in zip(spline.points, (0, length * .55, length), (.0065, .0045, .0025)):
            point.co = (-1.65 + 1.05 * c + amount * c, 1.30 + .90 * s + amount * s, z, 1)
    curve.materials.append(thread)
    fringe = bpy.data.objects.new("Play area | natural woven fringe", curve)
    bpy.context.collection.objects.link(fringe)
    # Actual three-dimensional foliage outside the window supplies depth and reflections.
    leaves = append_meshes(cozy, ["Leaves"], "Exterior | garden leaves")
    place_group(leaves, (-1.65, 4.3, .45), height=1.65)
    planter = append_meshes(cozy, ["Vase"], "Exterior | garden planter")
    place_group(planter, (-1.65, 4.3, .0), height=.52)
    paving = material("Exterior | pale courtyard paving", (.52, .55, .52), .9)
    cube("Exterior | courtyard ground", (12, 8, .10), (-1, 7.0, -.05), paving)
    ledger.pop("drawing_with_markers", None)
    ledger.pop("rabbit_stool", None)
    # Imported paper shaders mix a large-radius SSS component into the sheet.
    # Keep their photographed print but use a matte opaque paper response.
    for mat in bpy.data.materials:
        if not mat.name.startswith("paper") or not mat.use_nodes:
            continue
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        shader = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
        output = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
        if shader and output:
            for link in list(output.inputs["Surface"].links):
                links.remove(link)
            links.new(shader.outputs[0], output.inputs["Surface"])
            for label, value in (("Emission Strength", 0), ("Subsurface Weight", 0),
                                 ("Transmission Weight", 0), ("Roughness", .86)):
                for link in list(shader.inputs[label].links):
                    links.remove(link)
                shader.inputs[label].default_value = value
    ledger.update(children_table_group=furniture, book_stack=book_size, floor_cushion=pillow_size,
        room_dimensions_m=[6.5, 8.75, 2.8], material_tile_width_m={"linoleum_brown":2.0, "white_plaster_02":1.0},
        natural_light_policy="HDR sky sampled through two real glazed architectural apertures. Two zero-energy portals guide environment sampling; no interior emitting lights or luminous window backplates.",
        surface_policy="Photographed linoleum and mineral paint, wood/canvas children's furniture, printed book covers and wrinkled fabric. Floor geometry remains exactly level; no displacement.")
    return ledger


def lighting_lived_in(cfg):
    world = bpy.data.worlds.new("Photographic natural partly-cloudy sky")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new("ShaderNodeTexEnvironment")
    sky.image = bpy.data.images.load(str(asset("scenes/ball_box_rebound/room_surfaces/kloofendal_overcast_puresky/kloofendal_overcast_puresky_2k.hdr")), check_existing=True)
    sky.texture_mapping.rotation[2] = math.radians(cfg["appearance"]["daylight"]["rotation_degrees"])
    background = nodes.get("Background")
    background.inputs["Strength"].default_value = cfg["appearance"]["daylight"]["strength"]
    links.new(sky.outputs["Color"], background.inputs["Color"])
    bpy.context.scene.world = world
    # Portals guide sampling to the real openings; they emit no light.
    for name, position, target, width, height in (
        ("Side aperture | environment sampling portal", (-3.115, -.10, 1.60), (-2.115, -.10, 1.60), 2.18, 1.68),
        ("Rear aperture | environment sampling portal", (-1.72, 2.665, 1.72), (-1.72, 1.665, 1.72), 1.44, 1.29)):
        data = bpy.data.lights.new(name, "AREA")
        data.cycles.is_portal = True
        data.energy, data.shape, data.size, data.size_y = 0, "RECTANGLE", width, height
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        obj.location = position
        look_at(obj, target)


def lighting_storage(cfg):
    lighting_lived_in(cfg)
    world = bpy.context.scene.world
    world.name = "Measured partly-cloudy daylight through real windows"
    sky = next(n for n in world.node_tree.nodes if n.type == "TEX_ENVIRONMENT")
    sky.image = bpy.data.images.load(str(asset("scenes/ball_box_rebound/window_sky/kloofendal_48d_partly_cloudy_puresky/kloofendal_48d_partly_cloudy_puresky_2k.hdr")), check_existing=True)


def floor_finish():
    """Preserve photographed wear; weld lines are shading, never collision geometry."""
    mat = bpy.data.materials['Floor | photographed light-grey satin linoleum']
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get('Principled BSDF')
    gray = next(n for n in nodes if n.type == 'RGBTOBW')
    for link in list(shader.inputs['Base Color'].links):
        links.remove(link)
    tint = nodes.new('ShaderNodeValToRGB')
    tint.color_ramp.elements[0].position = .055
    tint.color_ramp.elements[1].position = .31
    tint.color_ramp.elements[0].color = (*linear((.52, .535, .53)), 1)
    tint.color_ramp.elements[1].color = (*linear((.77, .775, .76)), 1)
    links.new(gray.outputs[0], tint.inputs[0])
    links.new(tint.outputs[0], shader.inputs['Base Color'])
    for n in nodes:
        if n.type == 'MAP_RANGE':
            n.inputs['To Min'].default_value = .28
            n.inputs['To Max'].default_value = .59
        elif n.type == 'NORMAL_MAP':
            n.inputs['Strength'].default_value = .23
    # Real linoleum is laid in sheets. A single flush welded joint supplies
    # scale without disturbing the entirely level solved floor.
    geom = nodes.new('ShaderNodeNewGeometry')
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(geom.outputs['Position'], xyz.inputs[0])
    subtract = nodes.new('ShaderNodeMath'); subtract.operation = 'SUBTRACT'
    subtract.inputs[1].default_value = -.53
    links.new(xyz.outputs['X'], subtract.inputs[0])
    absolute = nodes.new('ShaderNodeMath'); absolute.operation = 'ABSOLUTE'
    links.new(subtract.outputs[0], absolute.inputs[0])
    seam = nodes.new('ShaderNodeMath'); seam.operation = 'LESS_THAN'
    seam.inputs[1].default_value = .0006
    links.new(absolute.outputs[0], seam.inputs[0])
    mix = nodes.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'
    mix.inputs[2].default_value = (.66, .66, .66, 1)
    links.new(seam.outputs[0], mix.inputs[0])
    links.new(tint.outputs[0], mix.inputs[1])
    links.new(mix.outputs[0], shader.inputs['Base Color'])


def imported(name, label, position, angle=0, scale=1, names=None):
    objects = append_meshes(asset(f'blenderkit/{name}/{name}.blend'), names, label)
    for obj in objects:
        for modifier in obj.modifiers:
            if modifier.type == 'SUBSURF':
                modifier.render_levels = min(2, modifier.render_levels)
    ledger = place_group(objects, position, angle=angle, scale=scale)
    return objects, ledger


def pinned_drawing():
    """Reuse the licensed drawing atlas on a curved sheet, with geometric tape."""
    image = next(im for im in bpy.data.images if im.name.startswith('feltpens_material_BaseColor'))
    paper = material('Wall | child drawing on real paper', (.91, .90, .86), .85)
    nodes, links = paper.node_tree.nodes, paper.node_tree.links
    tex = nodes.new('ShaderNodeTexImage'); tex.image = image
    links.new(tex.outputs['Color'], nodes.get('Principled BSDF').inputs['Base Color'])
    vertices, faces, coords = [], [], []
    nx, nz = 12, 9
    width, height = .42, .297
    for j in range(nz + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / nz
            curl = .0015 + .003 * (1 - v) ** 3 + .001 * math.sin(u * math.pi * 2) * (1 - v)
            vertices.append(((u - .5) * width, -curl, (v - .5) * height))
            coords.append((.532 - v * .528, .005 + u * .746))
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    mesh = bpy.data.meshes.new('Child drawing | curved sheet')
    mesh.from_pydata(vertices, [], faces); mesh.materials.append(paper)
    uv = mesh.uv_layers.new(name='Original licensed atlas drawing region')
    for loop in mesh.loops: uv.data[loop.index].uv = coords[loop.vertex_index]
    obj = bpy.data.objects.new('Wall | child drawing pinned above activity storage', mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = (.16, 2.667, .985); obj.rotation_euler.y = -.045
    thick = obj.modifiers.new('Paper thickness', 'SOLIDIFY'); thick.thickness = .00018
    tape = material('Wall | slightly translucent paper tape', (.77, .73, .59), .8)
    for x in (-.012, .332):
        obj = cube('Wall | short washi tape holding drawing', (.040, .0003, .021), (x, 2.662, 1.125), tape, .0002)
        obj.rotation_euler.y = -.10 if x < 0 else .14


def room_play_corner(cfg):
    ledger = room_lived_in(cfg)
    remove_prefixes(('Shelf |', 'Reading corner |', 'Play area | oval woven rug',
                        'Play area | natural woven fringe', 'Play area | downloaded toy car'))
    floor_finish()
    paint = bpy.data.materials['Room | photographic matte mineral paint']
    for node in paint.node_tree.nodes:
        if node.type == 'VALTORGB':
            node.color_ramp.elements[0].color = (*linear((.91, .91, .88)), 1)
            node.color_ramp.elements[1].color = (*linear((.97, .97, .94)), 1)
    pinned_drawing()
    # A textured, bound domestic rug replaces the perfect, textureless oval.
    rug, ledger['woven_rug'] = imported('woven_rug', 'Activity area | woven bound rug',
                                      (-1.58, 1.16, .001), angle=math.pi / 2 - .035)
    for obj in rug:
        # Give the existing 289-vertex cloth surface a millimetric settled edge.
        for vertex in obj.data.vertices:
            p = vertex.co
            p.z += .0012 * math.sin(p.x * 19 + .7) * math.sin(p.y * 13)
        lo, hi = bounds_furnished([obj]); obj.location.z += .0007 - lo.z
    furniture = [o for o in bpy.context.scene.objects if o.name.startswith('Play area | Noos')]
    for obj in furniture:
        obj.location.y += .10
        obj.location.z += .004
    ledger['children_table_group'] = {'world_bounds_m': [list(v) for v in bounds_furnished(furniture)]}
    cabinet, ledger['low_storage_cabinet'] = imported('small_storage_cabinet', 'Storage | real low cabinet',
                                                     (.11, 2.28, 0), angle=-.025)
    shelf, ledger['childrens_bookshelf'] = imported('childrens_bookshelf', 'Reading | arched child bookcase',
                                                  (1.02, 2.39, 0), angle=.018)
    # Pale painted MDF, with its original fine-grain shader and edge radii.
    for obj in shelf:
        for slot in obj.material_slots:
            mat = slot.material
            shader = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if shader:
                for link in list(shader.inputs['Base Color'].links): mat.node_tree.links.remove(link)
                shader.inputs['Base Color'].default_value = (*linear((.76, .78, .70)), 1)
                shader.inputs['Roughness'].default_value = .48
    basket, ledger['woven_toy_basket'] = imported('wicker_basket', 'Reading | scanned woven basket',
                                                (-2.05, .13, 0), angle=-.21, scale=1.60)
    # A fabric toy rests in the open basket; lid remains leaned beside it.
    penguin, ledger['penguin'] = imported('stuffed_penguin', 'Reading | plush in basket',
                                        (-2.16, .13, .29), angle=-.12, scale=.95)
    pillow, ledger['floor_cushion'] = imported('cozy_living_room', 'Reading | casually placed cushion',
                                              (1.55, 1.10, 0), angle=-.19, scale=.78, names=['pillow L.001'])
    for obj in pillow:
        obj.matrix_world = Matrix.Rotation(math.pi / 2, 4, 'X') @ obj.matrix_world
    place_group(pillow, (1.63, 1.24, .002), angle=-.16)
    for obj in pillow:
        for slot in obj.material_slots:
            slot.material = bpy.data.materials['PBR | woven neutral canvas']
    ledger['floor_cushion'] = {'world_bounds_m': [list(v) for v in bounds_furnished(pillow)]}
    train, ledger['wood_train_set'] = imported('wood_train_set', 'Activity area | wooden toy train',
                                              (-1.04, .64, .016), angle=.40, scale=.48)
    # Printed books have real cover and paper textures, with a few relaxed lean angles.
    cozy = asset('blenderkit/cozy_living_room/cozy_living_room.blend')
    for row, z in enumerate((.405, .803)):
        names = ('Book-1', 'Book-2', 'Book-3', 'Book-4') if row == 0 else ('Book-5', 'Book-3', 'Book-1')
        for i, name in enumerate(names):
            book = append_meshes(cozy, [name], f'Reading | printed book {row}-{i}')
            for obj in book:
                obj.matrix_world = Matrix.Rotation(math.pi / 2 + ((-.13, -.06, .015, .05)[i]), 4, 'Y') @ obj.matrix_world
            place_group(book, (.90 + i * .043, 2.35, z), angle=.018 + i * .013, scale=.88)
    stack = append_meshes(cozy, ['Book-1', 'Book-2', 'Book-3'], 'Storage | picture books on cabinet')
    place_group(stack, (.25, 2.20, .677), angle=-.22)
    opened = append_meshes(cozy, ['Cover book-03'], 'Reading | open picture book on floor')
    place_group(opened, (1.23, .97, .002), angle=.19)
    # A small timber toy and one familiar object supply natural household scale.
    horse, ledger['wooden_rocking_horse'] = imported('rocking_horse', 'Activity area | wooden rocking horse',
                                                   (-2.30, 2.23, 0), angle=math.pi / 2, scale=.90)
    car, ledger['toy_car'] = imported('rally_toy_car', 'Storage | toy car on cabinet',
                                     (-.13, 2.18, .677), angle=-.35)
    # Preserve the actual photographed curtain weave and softened daylight colour.
    curtain_mat = bpy.data.materials['PBR | woven neutral canvas']
    shader = curtain_mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Sheen Weight'].default_value = .24
    for key in ('shelf_dimensions_m', 'book_stack'):
        ledger.pop(key, None)
    ledger.update(room_dimensions_m=[6.5, 8.75, 2.8],
                  surface_policy='Photographic linoleum with preserved tonal wear and a flush weld; a textured bound rug, scanned wicker basket, printed books and measured manufactured furniture. All geometry shares one light field.',
                  appearance_revision='Asymmetrical domestic activity corner, no artificial oval mat or repeated empty cubbies. Original physical foreground remains unobstructed.')
    return ledger


def lighting_play_corner(cfg):
    lighting_storage(cfg)


def worn_finish(name, color, roughness, parent, lacquer=False):
    """Object-anchored, submillimetric wear affects reflection, not rigid shape."""
    mat = material(name, color, sum(roughness) / 2)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get('Principled BSDF')
    shader.inputs['IOR'].default_value = 1.50 if lacquer else 1.54
    shader.inputs['Coat Weight'].default_value = .18 if lacquer else .035
    shader.inputs['Coat Roughness'].default_value = .19 if lacquer else .23
    coordinate = nodes.new('ShaderNodeTexCoord')
    coordinate.object = parent
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 170
    noise.inputs['Detail'].default_value = 3
    links.new(coordinate.outputs['Object'], noise.inputs['Vector'])
    remap = nodes.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = roughness
    links.new(noise.outputs['Fac'], remap.inputs[0])
    # Fine scuffs interrupt a small part of the specular reflection. They are
    # deliberately not painted white or displaced outside the collision hull.
    cells = nodes.new('ShaderNodeTexVoronoi')
    cells.feature = 'DISTANCE_TO_EDGE'
    cells.inputs['Scale'].default_value = 48
    links.new(coordinate.outputs['Object'], cells.inputs['Vector'])
    narrow = nodes.new('ShaderNodeMath'); narrow.operation = 'LESS_THAN'
    narrow.inputs[1].default_value = .012
    links.new(cells.outputs['Distance'], narrow.inputs[0])
    mask = nodes.new('ShaderNodeTexNoise')
    mask.inputs['Scale'].default_value = 35
    mask.inputs['Detail'].default_value = 2
    links.new(coordinate.outputs['Object'], mask.inputs['Vector'])
    select = nodes.new('ShaderNodeMapRange')
    select.inputs['From Min'].default_value = .63
    select.inputs['From Max'].default_value = .76
    links.new(mask.outputs['Fac'], select.inputs[0])
    scratches = nodes.new('ShaderNodeMath'); scratches.operation = 'MULTIPLY'
    links.new(narrow.outputs[0], scratches.inputs[0])
    links.new(select.outputs[0], scratches.inputs[1])
    worn = nodes.new('ShaderNodeMath'); worn.operation = 'MULTIPLY_ADD'
    worn.inputs[1].default_value = .16
    links.new(scratches.outputs[0], worn.inputs[0])
    links.new(remap.outputs[0], worn.inputs[2])
    links.new(worn.outputs[0], shader.inputs['Roughness'])
    tint = nodes.new('ShaderNodeMixRGB'); tint.blend_type = 'MIX'
    tint.inputs[1].default_value = (*linear(color), 1)
    tint.inputs[2].default_value = (*linear(tuple(min(1, c * 1.055) for c in color)), 1)
    links.new(noise.outputs['Fac'], tint.inputs[0])
    links.new(tint.outputs[0], shader.inputs['Base Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = .000007
    bump.inputs['Strength'].default_value = .10
    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs[0], shader.inputs['Normal'])
    return mat


def room_finishes(cfg):
    ledger = room_play_corner(cfg)
    finish = cfg['appearance']['finish']
    floor = bpy.data.materials['Floor | photographed light-grey satin linoleum']
    for node in floor.node_tree.nodes:
        if node.type == 'MAP_RANGE':
            node.inputs['To Min'].default_value, node.inputs['To Max'].default_value = finish['floor_roughness']
        elif node.type == 'NORMAL_MAP':
            node.inputs['Strength'].default_value = finish['floor_normal_strength']
    # Break the perfectly repeated vertical fall while keeping the accepted
    # curtain position, upper suspension and 25 mm floor clearance unchanged.
    for obj in bpy.context.scene.objects:
        if not obj.name.startswith('Window | downloaded pleated curtain'):
            continue
        matrix, inverse = obj.matrix_world.copy(), obj.matrix_world.inverted()
        obj.data = obj.data.copy()
        for vertex in obj.data.vertices:
            p = matrix @ vertex.co
            envelope = max(0, min(1, (2.30 - p.z) / 1.7))
            p.y += envelope * (.009 * math.sin(p.z * 5.2 + p.x * 13) + .005 * math.sin(p.z * 13.1 + p.x * 4))
            p.x += envelope * .004 * math.sin(p.z * 7.1 + p.x * 11)
            vertex.co = inverse @ p
        obj.data.update()
    ledger.update(
        appearance_revision='Accepted furniture layout; restrained real-scale finish variation, satin floor reflections and settled curtain folds.',
        natural_light_policy='Existing HDR environment and real window apertures, with broad filtered sunlight through the same openings. No interior fill lamps or screen-space shadows.',
        finish_revision='Lower floor normal amplitude; photographic bin wear primarily retained in roughness; object-anchored lacquer and ABS micro-scuffs. No collision geometry or physics changes.',
    )
    return ledger


def lighting_finishes(cfg):
    lighting_play_corner(cfg)
    settings = cfg['appearance']['daylight']
    data = bpy.data.lights.new('Exterior | broad filtered afternoon sun', 'SUN')
    data.energy = settings['filtered_sun_energy']
    data.angle = math.radians(settings['filtered_sun_angle_degrees'])
    data.color = (1.0, .92, .80)
    sun = bpy.data.objects.new(data.name, data)
    bpy.context.collection.objects.link(sun)
    sun.location = (-5.2, -1.8, 4.0)
    look_at(sun, (0, .3, 0))


def room_cleared(cfg):
    ledger = room_finishes(cfg)
    remove_prefixes(('Reading | scanned woven basket', 'Reading | plush in basket',
                        'Storage | toy car on cabinet'))
    for key in ('woven_toy_basket', 'penguin', 'toy_car'):
        ledger.pop(key, None)
    settings = cfg['appearance']['scene_edits']
    # Clear the repositioned curtain while leaving a gap beside the table.
    horse = [o for o in bpy.context.scene.objects
             if o.name.startswith('Activity area | wooden rocking horse')]
    offset = settings['rocking_horse_offset_m']
    for obj in horse:
        obj.matrix_world = Matrix.Translation(Vector(offset)) @ obj.matrix_world
    horse_lo, horse_hi = bounds_furnished(horse)
    ledger['wooden_rocking_horse'].update(
        world_bounds_m=[list(horse_lo), list(horse_hi)], clearance_offset_m=offset)
    curtains = [o for o in bpy.context.scene.objects
                if o.name.startswith('Window | downloaded pleated curtain')]
    sill = bpy.data.objects['Window | deep painted sill']
    sill_lo, sill_hi = bounds_furnished([sill])
    lo, hi = bounds_furnished(curtains)
    rear = sill_lo.y - settings['curtain_sill_clearance_m']
    depth = settings['curtain_depth_m']
    # The imported drape had 30 cm deep folds penetrating both trim and sill.
    # Keep its height, width and weave, with a plausible 11 cm fold envelope.
    # Its whole rear envelope lies in front of the foremost sill surface.
    for obj in curtains:
        matrix, inverse = obj.matrix_world.copy(), obj.matrix_world.inverted()
        obj.data = obj.data.copy()
        for vertex in obj.data.vertices:
            p = matrix @ vertex.co
            p.y = rear - (hi.y - p.y) * depth / (hi.y - lo.y)
            vertex.co = inverse @ p
        obj.data.update()
    pole = bpy.data.objects['Window | curtain pole']
    pole.location.y = rear - depth / 2
    trim = bpy.data.materials['Room | satin white woodwork']
    wall_y = 2.675
    for x in (-2.62, -.82):
        cube('Window | supported curtain rod wall plate', (.046, .010, .072),
             (x, wall_y - .005, 2.46), trim, .003)
        cube('Window | curtain rod projection bracket', (.018, wall_y - pole.location.y, .018),
             (x, (wall_y + pole.location.y) / 2, 2.46), trim, .003)
    key = settings['cabinet_car_asset']
    car = append_meshes(asset(f'blenderkit/{key}/{key}.blend'),
                           prefix='Storage | newly sourced vintage Fiat 500 model')
    for obj in car:
        obj.animation_data_clear()
        for constraint in list(obj.constraints):
            obj.constraints.remove(constraint)
    car_lo, car_hi = bounds_furnished(car)
    scale = settings['cabinet_car_length_m'] / max(car_hi - car_lo)
    cabinet = [o for o in bpy.context.scene.objects if o.name.startswith('Storage | real low cabinet')]
    cabinet_lo, cabinet_hi = bounds_furnished(cabinet)
    car_size = place_group(car, (-.10, 2.20, cabinet_hi.z + .0001), angle=-.42, scale=scale)
    ledger['toy_car'] = {**car_size, 'asset_key': f'blenderkit/{key}',
                         'role': 'A 20 cm static scale model, newly sourced for this revision.',
                         'support_height_m': cabinet_hi.z}
    ledger['curtain_window_clearance'] = {
        'frontmost_sill_y_m': sill_lo.y, 'curtain_rear_envelope_y_m': rear,
        'minimum_clearance_m': settings['curtain_sill_clearance_m'],
        'curtain_fold_depth_m': depth, 'rod_y_m': pole.location.y,
        'scope': 'Entire drape envelope separated from all rear window trim and sill; rod supported from the wall.'}
    ledger['removed_props'] = ['Wicker toy basket', 'Separate basket lid', 'Plush penguin', 'Previous rally car']
    ledger['surface_policy'] = 'Photographic linoleum with preserved tonal wear and a flush weld; a textured bound rug, printed books, measured manufactured furniture and a new scale car. All retained geometry shares one light field.'
    ledger['appearance_revision'] = 'Requested prop removal, geometric curtain/window repair and a new cabinet display car; materials, light, camera and solved toys retained.'
    return ledger


def append_evaluated(path, prefix):
    """Resolve the complete source hierarchy before baking static world-space meshes.

    Mirror/array targets must remain linked while evaluating. Moving only source
    meshes, or purging unlinked helpers, changes their evaluated geometry.
    """
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.objects = list(source.objects)
    imported = [obj for obj in target.objects if obj]
    for obj in imported:
        bpy.context.collection.objects.link(obj)
        for modifier in obj.modifiers:
            modifier.show_viewport = modifier.show_render
            if modifier.type == 'SUBSURF':
                modifier.levels = modifier.render_levels
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    result = []
    for source in imported:
        if source.type != 'MESH' or source.hide_render:
            continue
        evaluated = source.evaluated_get(graph)
        mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=graph)
        if not mesh.vertices:
            bpy.data.meshes.remove(mesh)
            continue
        mesh.transform(evaluated.matrix_world)
        obj = bpy.data.objects.new(prefix + ' | ' + source.name, mesh)
        bpy.context.collection.objects.link(obj)
        result.append(obj)
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return result


def room_toy_chest(cfg):
    # The inherited room's scale ledger expected the former block envelope.
    room_cfg = copy.deepcopy(cfg)
    radius = cfg['physics']['football']['radius_m']
    room_cfg['physics']['block'] = {'dimensions_m': [2 * radius] * 3}
    ledger = room_cleared(room_cfg)
    ledger.pop('block_body_dimensions_m', None)
    remove_prefixes(('Storage | newly sourced vintage Fiat 500 model',))
    car = append_evaluated(asset('blenderkit/vintage_fiat_500/vintage_fiat_500.blend'),
                           'Storage | complete four-wheel Fiat 500 model')
    lo, hi = bounds_furnished(car)
    source_bounds = [list(lo), list(hi)]
    tire = next(obj for obj in car if obj.name.endswith('Rims.001'))
    cx, cy = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2
    quadrants = {}
    for sx in (-1, 1):
        for sy in (-1, 1):
            vertices = [v.co for v in tire.data.vertices
                        if (v.co.x - cx) * sx > .1 and (v.co.y - cy) * sy > .2]
            assert vertices, 'Missing source tire quadrant'
            quadrants[f'{sx},{sy}'] = len(vertices)
    # The source's front axle is slightly higher. Level the complete miniature
    # as a rigid group so all four tire bottoms meet the cabinet support plane.
    axle = []
    for sy in (-1, 1):
        points = [v.co for v in tire.data.vertices if (v.co.y - cy) * sy > .2]
        axle.append((sum(p.y for p in points) / len(points), min(p.z for p in points)))
    pitch = math.atan2(axle[0][1] - axle[1][1], axle[1][0] - axle[0][0])
    for obj in car:
        obj.data.transform(Matrix.Rotation(pitch, 4, 'X'))
    lo, hi = bounds_furnished(car)
    cabinet = [o for o in bpy.context.scene.objects if o.name.startswith('Storage | real low cabinet')]
    cabinet_top = bounds_furnished(cabinet)[1].z
    size = place_group(car, (-.10, 2.20, cabinet_top + .0001), angle=-.65,
                          scale=cfg['appearance']['scene_edits']['cabinet_car_length_m'] / max(hi - lo))
    ledger['toy_car'] = {**size, 'source_bounds_m': source_bounds,
                         'source_axle_leveling_degrees': math.degrees(pitch),
                         'evaluated_tire_vertices_in_each_quadrant': quadrants,
                         'support_height_m': cabinet_top,
                         'import_policy': 'All source mirror references evaluated before placement; four tire quadrants verified; static meshes have no remaining modifiers.'}
    ledger['football_diameter_m'] = 2 * radius
    ledger['toy_chest'] = {'dimensions_m': cfg['physics']['box']['dimensions_m'],
                            'body_wall_thickness_m': .018, 'lid_thickness_m': .018,
                            'finish': 'Satin blue painted timber, natural birch lid, recessed side grips and restrained printed stars.'}
    ledger['appearance_revision'] = 'Correct car mirrors, replace yellow block with a stitched football and replace industrial tote with a painted children toy chest. Window and adjacent furniture clearances retained.'
    return ledger


def leather(name, color, parent):
    mat = material(name, color, .52)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get('Principled BSDF')
    shader.inputs['IOR'].default_value = 1.48
    coord = nodes.new('ShaderNodeTexCoord'); coord.object = parent
    pores = nodes.new('ShaderNodeTexVoronoi')
    pores.feature = 'DISTANCE_TO_EDGE'; pores.inputs['Scale'].default_value = 1650
    links.new(coord.outputs['Object'], pores.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump'); bump.inputs['Distance'].default_value = .000055
    bump.inputs['Strength'].default_value = .24
    links.new(pores.outputs['Distance'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], shader.inputs['Normal'])
    noise = nodes.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 90
    noise.inputs['Detail'].default_value = 3
    links.new(coord.outputs['Object'], noise.inputs['Vector'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = .43; rough.inputs['To Max'].default_value = .61
    links.new(noise.outputs['Fac'], rough.inputs[0]); links.new(rough.outputs[0], shader.inputs['Roughness'])
    tint = nodes.new('ShaderNodeMixRGB')
    tint.inputs[1].default_value = (*linear(color), 1)
    tint.inputs[2].default_value = (*linear(tuple(c * .96 for c in color)), 1)
    links.new(noise.outputs['Fac'], tint.inputs[0]); links.new(tint.outputs[0], shader.inputs['Base Color'])
    return mat


def star(name, x, z, radius, mat, parent, phase=0):
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5 + phase
        r = radius if i % 2 == 0 else radius * .43
        points.append((x + r * math.cos(angle), -.22006, z + r * math.sin(angle)))
    mesh = bpy.data.meshes.new(name); mesh.from_pydata(points, [], [list(range(10))])
    obj = bpy.data.objects.new(name, mesh); bpy.context.collection.objects.link(obj)
    mesh.materials.append(mat); obj.parent = parent


def toy_chest(cfg):
    parent = root('C01 | solved blue children toy chest')
    x, y, z = cfg['physics']['box']['dimensions_m']
    paint = worn_finish('C01 | satin blue painted wood', (.075, .33, .59), (.28, .37), parent)
    inside = material('C01 | blue inner edges', (.05, .22, .38), .48)
    shell = cube('C01 | planar painted toy chest body', (x, y, z - .020), (0, 0, -.010), paint, .005, parent)
    inner = cube('Temporary toy chest interior', (x - .036, y - .036, z), (0, 0, .018), inside, .003)
    difference(shell, inner)
    for side in (-1, 1):
        opening = cube('Temporary side handhold', (.070, .130, .028), (side * x / 2, 0, .105), inside, .012)
        difference(shell, opening)
    # The whole near panel at ball height remains at the solved y = -0.22 m plane.
    cube('C01 | narrow lid shadow gap', (x - .009, y - .009, .002), (0, 0, .181), inside, .002, parent)
    wood = photographed_material('C01 | natural birch lid',
        asset(cfg['appearance']['material_asset_directory']) / 'plywood', .65)
    for node in wood.node_tree.nodes:
        if node.type == 'BUMP':
            node.inputs['Distance'].default_value = .000045; node.inputs['Strength'].default_value = .12
        elif node.type == 'MAP_RANGE':
            node.inputs['To Min'].default_value = .30; node.inputs['To Max'].default_value = .42
    cube('C01 | smooth rounded birch lid', (x + .004, y + .004, .018), (0, 0, .191), wood, .004, parent)
    ink = material('C01 | warm ivory printed toy motif', (.86, .82, .69), .42)
    text('C01 | small printed TOYS', 'TOYS', (0, -y / 2 - .00007, .034), .040, ink, parent, True)
    for i, (sx, sz, radius, phase) in enumerate(((-.16, .045, .026, -.2), (.16, .062, .022, .18), (.205, .018, .013, -.12))):
        star(f'C01 | printed star {i + 1}', sx, sz, radius, ink, parent, phase)
    return parent


def toys_toy_chest(cfg):
    ballroot = root('B01 | solved rigid red ball')
    red = worn_finish('B01 | red lacquer and restrained use marks', (.70, .027, .018),
                         cfg['appearance']['finish']['ball_roughness'], ballroot, True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=80, radius=cfg['physics']['ball']['radius_m'])
    ball = bpy.context.object; ball.name = 'B01 | hard lacquered ball'; ball.parent = ballroot
    ball.data.materials.append(red)
    for face in ball.data.polygons: face.use_smooth = True
    box = toy_chest(cfg)
    footballroot = root('B02 | solved rigid football')
    football = append_evaluated(asset('blenderkit/stitched_soccer_ball/stitched_soccer_ball.blend'),
                                 'B02 | stitched football')
    lo, hi = bounds_furnished(football); center = (lo + hi) / 2
    radius = cfg['physics']['football']['radius_m']
    scale = radius * 2 / max(hi - lo)
    white = leather('B02 | off-white pebbled football panels', (.82, .81, .78), footballroot)
    black = leather('B02 | charcoal pebbled football panels', (.035, .041, .046), footballroot)
    thread = material('B02 | recessed neutral seam thread', (.34, .33, .30), .72)
    for obj in football:
        for vertex in obj.data.vertices:
            p = (vertex.co - center) * scale
            # Keep the imported panel relief inside a submillimetric spherical envelope.
            # The sphere collision proxy then represents the visible rigid surface.
            p.length = min(radius, max(radius - .00065, p.length))
            vertex.co = p
        for slot in obj.material_slots:
            name = slot.material.name.lower() if slot.material else ''
            slot.material = thread if 'stitch' in name else black if 'black' in name else white
        obj.parent = footballroot
    return {'ball': ballroot, 'box': box, 'football': footballroot}


def lighting_toy_chest(cfg):
    lighting_finishes(cfg)


def reference_parts():
    """Keep only the supplied chest, separate lid and first patterned ball."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(asset('sketchfab/hayley_toy_box/toy_box.glb')))
    imported = set(bpy.data.objects) - before
    wanted = {'Box_Base_Mat_Box_0': 'body', 'Box_Lid_Mat_Box_0': 'lid',
              'Ball1_Mat_Toys_0': 'ball'}
    result = {}
    bpy.context.view_layer.update()
    for obj in imported:
        if obj.name not in wanted:
            continue
        key = wanted[obj.name]
        obj.data.transform(obj.matrix_world)
        obj.parent = None
        obj.matrix_world = Matrix.Identity(4)
        result[key] = obj
    for obj in imported - set(result.values()):
        bpy.data.objects.remove(obj, do_unlink=True)
    if set(result) != {'body', 'lid', 'ball'}:
        raise ValueError('The supplied GLB does not contain the expected meshes')
    return result


def weld(obj):
    # glTF duplicates vertices at UV/material boundaries. Merge positions while
    # retaining per-corner UVs, so bevels and spherical refinement stay connected.
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=0.000001)
    mesh.to_mesh(obj.data)
    mesh.free()


def bounds_paneled_chest(obj):
    points = [v.co for v in obj.data.vertices]
    return (Vector([min(p[k] for p in points) for k in range(3)]),
            Vector([max(p[k] for p in points) for k in range(3)]))


def reference_material(source, name):
    """Use the supplied colors, star print, normal map and roughness unchanged."""
    mat = source.copy()
    mat.name = name
    shader = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    # The atlas also serves the source scene's transparent/emissive props.
    # The extracted wooden box and hard toy ball are opaque, non-emissive solids.
    for name in ('Alpha', 'Emission Color'):
        for link in list(shader.inputs[name].links):
            mat.node_tree.links.remove(link)
    shader.inputs['Alpha'].default_value = 1
    shader.inputs['Emission Color'].default_value = (0, 0, 0, 1)
    shader.inputs['Emission Strength'].default_value = 0
    return mat


def chest(cfg, body, lid):
    parent = root('C01 | solved reference paneled toy chest')
    width, depth, height = cfg['physics']['box']['dimensions_m']
    paint = reference_material(body.data.materials[0], 'C01 | original white painted timber')
    # Remove the source prop's 3.73-degree display yaw before measuring its
    # dimensions. Its lower front rail is the planar impact face at ball height.
    body.data.transform(Matrix.Rotation(-math.atan2(.06504122167825699, .997882604598999), 4, 'Z'))
    lo, hi = bounds_paneled_chest(body)
    center = (lo + hi) / 2
    size = hi - lo
    for vertex in body.data.vertices:
        p = vertex.co
        p.x = (p.x - center.x) * width / size.x
        p.y = (p.y - center.y) * depth / size.y
        p.z = (p.z - lo.z) * (height - .020) / size.z - height / 2
        # The larger ball must meet a broad flat rail, rather than the upper
        # edge of the source's low kick rail. Raise that rail modestly while
        # retaining the foot opening, body height and original white UV finish.
        h = p.z + height / 2
        foot, old_join, new_join, upper = cfg['appearance']['scene_edits']['chest_lower_rail_transition_m']
        if foot < h <= old_join:
            h = foot + (h - foot) * (new_join - foot) / (old_join - foot)
        elif old_join < h < upper:
            h = new_join + (h - old_join) * (upper - new_join) / (upper - old_join)
        p.z = h - height / 2
    body.name = 'C01 | supplied frame and inset board case'
    body.parent = parent
    body.data.materials.clear()
    body.data.materials.append(paint)
    weld(body)

    # The GLB stores the detached lid leaning against the front. Recover its
    # orthogonal board axes, retain its UVs and lay the decorated face upwards.
    points = np.array([tuple(v.co) for v in lid.data.vertices])
    _, axes = np.linalg.eigh(np.cov((points - points.mean(axis=0)).T))
    xaxis = Vector(axes[:, 2])
    if xaxis.x < 0:
        xaxis.negate()
    zaxis = Vector(axes[:, 0])
    if zaxis.z < 0:
        zaxis.negate()
    yaxis = zaxis.cross(xaxis).normalized()
    rotation = Matrix((xaxis, yaxis, zaxis)).to_4x4()
    lid.data.transform(rotation)
    lo, hi = bounds_paneled_chest(lid)
    center, size = (lo + hi) / 2, hi - lo
    for vertex in lid.data.vertices:
        p = vertex.co
        p.x = (p.x - center.x) * (width + .004) / size.x
        p.y = (p.y - center.y) * (depth + .004) / size.y
        p.z = (p.z - lo.z) * .018 / size.z + height / 2 - .018
    lid.name = 'C01 | supplied closed paneled lid'
    lid.parent = parent
    lid.data.materials.clear()
    lid.data.materials.append(paint)
    weld(lid)
    for obj in (body, lid):
        bevel = obj.modifiers.new('Submillimetric painted edge easing', 'BEVEL')
        bevel.width = .00065
        bevel.segments = 3
        bevel.limit_method = 'ANGLE'
        bevel.angle_limit = math.radians(35)
        bevel.harden_normals = True
        weighted = obj.modifiers.new('Stable flat board normals', 'WEIGHTED_NORMAL')
        weighted.keep_sharp = True
    # Small hardware belongs to the box and remains clear of both ball paths.
    steel = material('C01 | recessed hinge barrel steel', (.38, .40, .41), .38)
    steel.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value = .72
    for x in (-.22, .22):
        hinge = cylinder('C01 | rear hinge barrel', .0022, .037,
                         (x, depth / 2 - .001, height / 2 - .019), steel, parent)
        hinge.rotation_euler.y = math.pi / 2
    return parent


def patterned_ball(cfg, obj):
    parent = root('B01 | solved original star toy ball')
    radius = cfg['physics']['ball']['radius_m']
    # Least-squares sphere center avoids bias from the rotated low-poly source
    # bounding box. Refinement changes the silhouette, not its UV motif.
    points = np.array([tuple(v.co) for v in obj.data.vertices])
    fit = np.linalg.lstsq(np.column_stack((2 * points, np.ones(len(points)))),
                          (points * points).sum(axis=1), rcond=None)[0]
    center = Vector(fit[:3])
    for vertex in obj.data.vertices:
        vertex.co = (vertex.co - center).normalized() * radius
    weld(obj)
    modifier = obj.modifiers.new('Refine source star-ball UV mesh', 'SUBSURF')
    modifier.subdivision_type = 'SIMPLE'
    modifier.levels = modifier.render_levels = 3
    modifier.uv_smooth = 'NONE'
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    for vertex in obj.data.vertices:
        vertex.co.length = radius
    obj.data.transform(Matrix.Rotation(math.pi, 4, 'Z'))
    if obj.data.has_custom_normals:
        obj.data.normals_split_custom_set([(0, 0, 0)] * len(obj.data.loops))
    for face in obj.data.polygons:
        face.use_smooth = True
    obj.data.materials[0] = reference_material(obj.data.materials[0],
        'B01 | original reference star-ball material')
    obj.name = 'B01 | supplied star pattern on refined rigid sphere'
    obj.parent = parent
    return parent


def toys_paneled_chest(cfg):
    objects = toys_toy_chest(cfg)
    for key in ('box', 'ball'):
        old = objects[key]
        for obj in list(old.children_recursive):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.objects.remove(old, do_unlink=True)
    parts = reference_parts()
    objects['box'] = chest(cfg, parts['body'], parts['lid'])
    objects['ball'] = patterned_ball(cfg, parts['ball'])
    return objects


def room_paneled_chest(cfg):
    ledger = room_toy_chest(cfg)
    ledger['toy_chest'] = {
        'source': 'User-supplied Toy Box GLB by Hayley Jacka, CC BY 4.0',
        'source_model': '8ce01f03c4c54c1bb69f6ba47a590586',
        'dimensions_m': cfg['physics']['box']['dimensions_m'],
        'body_height_m': .380, 'lid_joint_m': .002, 'lid_thickness_m': .018,
        'finish': 'Source frame, inset vertical boards, low feet, UV wear and normal maps; original white painted finish and closed lid.',
        'collision_policy': 'Lower rail widened vertically for the 9 cm contact height; front impact and four support planes coincide with the rigid box proxy.'}
    ledger['star_ball_reference'] = {
        'source_mesh': 'Ball1_Mat_Toys_0', 'diameter_m': 2 * cfg['physics']['ball']['radius_m'],
        'finish': 'Original source ball mesh, pink-red color and pale pink star print, UVs and PBR maps retained; render subdivision smooths the spherical silhouette.'}
    ledger['appearance_revision'] = 'Retain the supplied white chest and original star-ball finish; solve new 18 cm toy-ball motion and retain the football, four-wheel car and curtain clearance.'
    return ledger


def lighting_paneled_chest(cfg):
    lighting_toy_chest(cfg)


def replace_input(mat, shader, name, socket=None, value=None):
    for link in list(shader.inputs[name].links):
        mat.node_tree.links.remove(link)
    if socket is not None:
        mat.node_tree.links.new(socket, shader.inputs[name])
    if value is not None:
        shader.inputs[name].default_value = value


def world_texture(mat, directory, identifier, suffix, tile_m, color=False):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new('ShaderNodeNewGeometry')
    scale = nodes.new('ShaderNodeVectorMath')
    scale.operation = 'SCALE'
    scale.inputs[3].default_value = 1 / tile_m
    links.new(coord.outputs['Position'], scale.inputs[0])
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(asset(
        f'scenes/ball_box_rebound/{directory}/{identifier}/{identifier}_{suffix}')),
        check_existing=True)
    tex.image.colorspace_settings.name = 'sRGB' if color else 'Non-Color'
    tex.projection, tex.projection_blend = 'BOX', .22
    links.new(scale.outputs[0], tex.inputs['Vector'])
    return tex


def satin_paint(name, color, roughness, grain_m=.000018):
    """Dielectric paint with restrained photographed roller/wood variation."""
    mat = material(name, color, sum(roughness) / 2)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get('Principled BSDF')
    shader.inputs['Metallic'].default_value = 0
    shader.inputs['IOR'].default_value = 1.48
    tex = world_texture(mat, 'room_surfaces', 'white_plaster_02', 'rough_2k.jpg', .65)
    tint = nodes.new('ShaderNodeMixRGB')
    tint.inputs[1].default_value = (*linear(tuple(c * .982 for c in color)), 1)
    tint.inputs[2].default_value = (*linear(tuple(min(1, c * 1.012) for c in color)), 1)
    links.new(tex.outputs[0], tint.inputs[0])
    links.new(tint.outputs[0], shader.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = roughness
    links.new(tex.outputs[0], rough.inputs[0])
    links.new(rough.outputs[0], shader.inputs['Roughness'])
    coord = nodes.new('ShaderNodeNewGeometry')
    pores = nodes.new('ShaderNodeTexNoise')
    pores.inputs['Scale'].default_value = 1800
    pores.inputs['Detail'].default_value = 2
    links.new(coord.outputs['Position'], pores.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = grain_m
    bump.inputs['Strength'].default_value = .18
    links.new(pores.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], shader.inputs['Normal'])
    return mat


def linen():
    """Thin undyed linen: mapped in metres, with diffuse light transmission."""
    mat = material('Window | real-scale washed linen', (.84, .81, .74), .72)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get('Principled BSDF')
    tex = world_texture(mat, 'material_textures', 'rough_linen', 'diff_1k.jpg', .30, True)
    gray = nodes.new('ShaderNodeRGBToBW')
    links.new(tex.outputs['Color'], gray.inputs[0])
    tint = nodes.new('ShaderNodeValToRGB')
    tint.color_ramp.elements[0].position = .035
    tint.color_ramp.elements[1].position = .54
    tint.color_ramp.elements[0].color = (*linear((.74, .715, .65)), 1)
    tint.color_ramp.elements[1].color = (*linear((.89, .87, .81)), 1)
    links.new(gray.outputs[0], tint.inputs[0])
    links.new(tint.outputs[0], shader.inputs['Base Color'])
    height = world_texture(mat, 'material_textures', 'rough_linen', 'disp_1k.jpg', .30)
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = .00013
    bump.inputs['Strength'].default_value = .26
    links.new(height.outputs[0], bump.inputs['Height'])
    links.new(bump.outputs[0], shader.inputs['Normal'])
    shader.inputs['Sheen Weight'].default_value = .28
    shader.inputs['Sheen Roughness'].default_value = .75
    shader.inputs['IOR'].default_value = 1.46
    translucent = nodes.new('ShaderNodeBsdfTranslucent')
    links.new(tint.outputs[0], translucent.inputs['Color'])
    links.new(bump.outputs[0], translucent.inputs['Normal'])
    mix = nodes.new('ShaderNodeMixShader')
    mix.inputs[0].default_value = .14
    links.new(shader.outputs[0], mix.inputs[1])
    links.new(translucent.outputs[0], mix.inputs[2])
    output = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
    links.new(mix.outputs[0], output.inputs['Surface'])
    return mat


def refine_curtains():
    cloth = linen()
    hem = cloth.copy()
    hem.name = 'Window | doubled linen hem'
    next(n for n in hem.node_tree.nodes if n.type == 'MIX_SHADER').inputs[0].default_value = .04
    curtains = [o for o in bpy.context.scene.objects
                if o.name.startswith('Window | downloaded pleated curtain')]
    for index, obj in enumerate(curtains):
        matrix, inverse = obj.matrix_world.copy(), obj.matrix_world.inverted()
        obj.data = obj.data.copy()
        for mod in list(obj.modifiers):
            if mod.type == 'WEIGHTED_NORMAL':
                obj.modifiers.remove(mod)
        obj.data.materials.clear()
        obj.data.materials.append(cloth)
        obj.data.materials.append(hem)
        for vertex in obj.data.vertices:
            p = matrix @ vertex.co
            fall = max(0, min(1, (2.43 - p.z) / 2.405))
            # Lateral settling and a slightly unequal hem. Depth stays frozen,
            # maintaining the accepted separation from the sill and horse.
            p.x += .010 * fall ** 1.5 * math.sin(4.1 * p.z + 9 * p.x + index)
            p.z += (.002 + .004 * (math.sin(p.x * 17 + index) + 1) / 2) * fall ** 8
            vertex.co = inverse @ p
        for poly in obj.data.polygons:
            poly.use_smooth = True
            if max((matrix @ obj.data.vertices[i].co).z for i in poly.vertices) < .065:
                poly.material_index = 1
        obj.data.update()


def refine_furniture():
    body = cabinet_wood()
    doors = satin_paint('Storage | muted slate cabinet enamel', (.52, .57, .59), (.34, .48))
    chair = satin_paint('Activity | warm white sealed chair surface', (.88, .865, .82), (.40, .53))
    shelf = satin_paint('Reading | sage painted timber', (.72, .75, .67), (.40, .54))
    replacement = {'cabinet_mat': body, 'Opener_mat': doors, 'mdf branco': chair,
                   'Orange grain plastic': shelf}
    objects = [o for o in bpy.context.scene.objects if o.name.startswith(
        ('Storage | real low cabinet', 'Reading | arched child bookcase', 'Play area | Noos'))]
    wood_mats = set()
    for obj in objects:
        for slot in obj.material_slots:
            mat = slot.material
            if not mat:
                continue
            if mat.name in replacement:
                slot.material = replacement[mat.name]
            elif mat.name.startswith(('Freijó wood', 'Plywood siding', 'Holder_mat', 'Legs_mat')):
                wood_mats.add(mat)
    for mat in wood_mats:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        for shader in [n for n in nodes if n.type == 'BSDF_PRINCIPLED']:
            source = shader.inputs['Base Color'].links[0].from_socket
            hue = nodes.new('ShaderNodeHueSaturation')
            hue.inputs['Saturation'].default_value = .65
            hue.inputs['Value'].default_value = 1.10
            links.new(source, hue.inputs['Color'])
            replace_input(mat, shader, 'Base Color', hue.outputs[0])
            if shader.inputs['Roughness'].is_linked:
                source = shader.inputs['Roughness'].links[0].from_socket
                remap = nodes.new('ShaderNodeMapRange')
                remap.inputs['To Min'].default_value = .31
                remap.inputs['To Max'].default_value = .49
                links.new(source, remap.inputs[0])
                replace_input(mat, shader, 'Roughness', remap.outputs[0])
            shader.inputs['Coat Weight'].default_value = .05
            shader.inputs['Coat Roughness'].default_value = .30
        for node in nodes:
            if node.type == 'BUMP':
                node.inputs['Distance'].default_value = .000035
                node.inputs['Strength'].default_value = .20
            elif node.type == 'NORMAL_MAP':
                node.inputs['Strength'].default_value = .16


def cabinet_wood():
    """Reuse the asset's photographed oak, mapped to a 0.80 m physical area."""
    mat = material('Storage | photographed oak cabinet carcass', (.68, .55, .39), .41)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get('Principled BSDF')
    shader.inputs['IOR'].default_value = 1.5
    shader.inputs['Coat Weight'].default_value = .055
    shader.inputs['Coat Roughness'].default_value = .32
    geometry = nodes.new('ShaderNodeNewGeometry')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1.25, 1.25, 1.25)
    mapping.inputs['Rotation'].default_value[2] = .025
    links.new(geometry.outputs['Position'], mapping.inputs['Vector'])
    maps = {}
    for channel, filename in [('color', 'Wood023_2K_Color.png'), ('rough', 'Wood023_2K_Roughness.png')]:
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images[filename]
        tex.projection, tex.projection_blend = 'BOX', .18
        links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
        maps[channel] = tex
    hue = nodes.new('ShaderNodeHueSaturation')
    hue.inputs['Saturation'].default_value = .66
    hue.inputs['Value'].default_value = 1.03
    links.new(maps['color'].outputs[0], hue.inputs['Color'])
    links.new(hue.outputs[0], shader.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = .32, .49
    links.new(maps['rough'].outputs[0], rough.inputs[0])
    links.new(rough.outputs[0], shader.inputs['Roughness'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value, bump.inputs['Strength'].default_value = .00005, .20
    links.new(maps['rough'].outputs[0], bump.inputs['Height'])
    links.new(bump.outputs[0], shader.inputs['Normal'])
    return mat


def reading_cushion():
    """Place the existing draped cushion on the floor behind the ball corridor."""
    objects = [o for o in bpy.context.scene.objects if o.name.startswith('Reading | casually placed cushion')]
    if not objects:
        raise ValueError('Expected the licensed living-room cushion in the inherited scene')
    # This comes from the source's sewn pillow geometry, including rounded
    # corners and irregular folds, rather than a rounded rectangular primitive.
    graph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        evaluated = obj.evaluated_get(graph)
        mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=graph)
        mesh.transform(evaluated.matrix_world)
        obj.data = mesh
        obj.matrix_world = Matrix.Identity(4)
        for modifier in list(obj.modifiers):
            obj.modifiers.remove(modifier)
        points.extend(tuple(vertex.co) for vertex in mesh.vertices)
    xyz = np.asarray(points)
    center = xyz.mean(axis=0)
    _, vectors = np.linalg.eigh(np.cov((xyz - center).T))
    # Lay the cushion on its broad face. The source asset is a propped sofa
    # pillow, so the basis comes from its principal axes, not a fixed quarter-turn.
    basis = vectors[:, [2, 1, 0]]
    if np.linalg.det(basis) < 0:
        basis[:, 1] *= -1
    for obj in objects:
        for vertex in obj.data.vertices:
            vertex.co = Vector((np.asarray(vertex.co) - center) @ basis)
        obj.data.update()
    lo, hi = bounds_furnished(objects)
    scale = .43 / max(hi.x - lo.x, hi.y - lo.y)
    size = place_group(objects, (.68, 1.60, .0007), angle=.17, scale=scale)
    cloth = linen().copy()
    cloth.name = 'Reading | washed oatmeal cushion cover'
    nodes = cloth.node_tree.nodes
    tint = next(n for n in nodes if n.type == 'VALTORGB')
    tint.color_ramp.elements[0].color = (*linear((.52, .49, .43)), 1)
    tint.color_ramp.elements[1].color = (*linear((.72, .68, .60)), 1)
    next(n for n in nodes if n.type == 'MIX_SHADER').inputs[0].default_value = 0
    nodes.get('Principled BSDF').inputs['Sheen Weight'].default_value = .18
    for obj in objects:
        for slot in obj.material_slots:
            slot.material = cloth
    # A sewn cover has a narrow cord along its equator, not a seamless balloon
    # silhouette. Trace the actual imported cushion perimeter in world space.
    bpy.context.view_layer.update()
    xyz = np.asarray([tuple(obj.matrix_world @ v.co) for obj in objects for v in obj.data.vertices])
    center = (xyz.min(axis=0) + xyz.max(axis=0)) / 2
    xy = xyz[:, :2] - center[:2]
    angles = np.arctan2(xy[:, 1], xy[:, 0])
    radii = np.linalg.norm(xy, axis=1)
    outline = []
    for angle in np.linspace(-math.pi, math.pi, 128, endpoint=False):
        distance = np.abs(np.arctan2(np.sin(angles - angle), np.cos(angles - angle)))
        candidates = np.flatnonzero(distance < math.pi / 100)
        if not len(candidates):
            candidates = np.argsort(distance)[:8]
        index = candidates[np.argmax(radii[candidates])]
        point = xyz[index].copy()
        point[:2] += .0003 * xy[index] / radii[index]
        outline.append(point)
    curve = bpy.data.curves.new('Reading | sewn cushion perimeter', 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth, curve.bevel_resolution = .0012, 2
    spline = curve.splines.new('BEZIER')
    spline.bezier_points.add(len(outline) - 1)
    for point, location in zip(spline.bezier_points, outline):
        point.co = location
        point.handle_left_type = point.handle_right_type = 'AUTO'
    spline.use_cyclic_u = True
    curve.materials.append(material('Reading | linen cushion seam cord', (.61, .58, .51), .76))
    piping = bpy.data.objects.new('Reading | sewn cushion perimeter', curve)
    bpy.context.collection.objects.link(piping)
    size['cover_seam_cord_radius_m'] = .0012
    return size


def room_textiles(cfg):
    ledger = room_paneled_chest(cfg)
    if not cfg['appearance']['environment_refinement']['enabled']:
        return ledger
    refine_curtains()
    refine_furniture()
    ledger['floor_cushion'] = reading_cushion()
    floor = bpy.data.materials['Floor | photographed light-grey satin linoleum']
    for node in floor.node_tree.nodes:
        if node.type == 'NORMAL_MAP':
            node.inputs['Strength'].default_value = .085
        elif node.type == 'MAP_RANGE':
            node.inputs['To Min'].default_value = .32
            node.inputs['To Max'].default_value = .49
    ledger.update(
        appearance_revision='Static environment study; head-on motion retained verbatim.',
        textile_revision='0.30 m photographic weave in world metres, diffuse transmission, doubled hem, smooth cloth normals and asymmetric settled lower folds; curtain depth unchanged.',
        furniture_finish_revision='Photographed oak cabinet carcass with slate enamel doors, nonmetallic sage shelf paint, warm-white chair lacquer and desaturated sealed wood; existing sewn cushion placed in the reading corner.',
        preview_scope='Only selected static keyframes are rendered; no full video render is authorized for this study.',
    )
    return ledger


def toys_textiles(cfg):
    return toys_paneled_chest(cfg)


def lighting_textiles(cfg):
    lighting_paneled_chest(cfg)
    settings = cfg['appearance']['daylight']
    sun = bpy.data.objects['Exterior | broad filtered afternoon sun']
    sun.location = settings['sun_position_m']
    look_at(sun, settings['sun_target_m'])
    sun.data.color = (1.0, .955, .885)


# Books whose cover images carry stock titles, publisher text or watermarks.
PRINTED_COVER_PREFIXES = ('pngtree-', 'yellow-business-leadership')


# Plain bookcloth colours (sRGB): muted dyes typical of children's hardbacks.
BOOKCLOTH_SRGB = ((.36, .45, .55), (.72, .58, .30), (.55, .60, .50), (.66, .40, .32),
                  (.80, .76, .66), (.30, .36, .45), (.62, .55, .62))


def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def _unlink(mat, socket):
    for link in list(socket.links):
        mat.node_tree.links.remove(link)


def _cloth_texture(mat, tile_m=.012):
    """Fine woven bookcloth from the existing CC0 linen scan (object space)."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    scale = nodes.new('ShaderNodeVectorMath')
    scale.operation = 'SCALE'
    scale.inputs[3].default_value = 1 / tile_m
    links.new(coord.outputs['Object'], scale.inputs[0])
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(asset(
        'scenes/ball_box_rebound/material_textures/rough_linen/rough_linen_disp_1k.jpg')), check_existing=True)
    tex.image.colorspace_settings.name = 'Non-Color'
    tex.projection, tex.projection_blend = 'BOX', .2
    links.new(scale.outputs[0], tex.inputs['Vector'])
    return tex


def plain_book_covers():
    """Replace printed stock covers with unprinted bookcloth; keep page blocks."""
    changed = []
    index = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes or mat.users == 0:
            continue
        images = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image
                  and n.image.name.startswith(PRINTED_COVER_PREFIXES)]
        if not images:
            continue
        shader = _principled(mat)
        for node in images:
            mat.node_tree.nodes.remove(node)
        color = BOOKCLOTH_SRGB[index % len(BOOKCLOTH_SRGB)]
        index += 1
        weave = _cloth_texture(mat)
        tint = mat.node_tree.nodes.new('ShaderNodeMixRGB')
        tint.inputs[1].default_value = (*linear(tuple(c * .93 for c in color)), 1)
        tint.inputs[2].default_value = (*linear(tuple(min(1, c * 1.04) for c in color)), 1)
        mat.node_tree.links.new(weave.outputs[0], tint.inputs[0])
        _unlink(mat, shader.inputs['Base Color'])
        mat.node_tree.links.new(tint.outputs[0], shader.inputs['Base Color'])
        bump = mat.node_tree.nodes.new('ShaderNodeBump')
        bump.inputs['Distance'].default_value = .00008
        bump.inputs['Strength'].default_value = .25
        mat.node_tree.links.new(weave.outputs[0], bump.inputs['Height'])
        _unlink(mat, shader.inputs['Normal'])
        mat.node_tree.links.new(bump.outputs[0], shader.inputs['Normal'])
        shader.inputs['Roughness'].default_value = .78
        shader.inputs['Sheen Weight'].default_value = .12
        changed.append({'material': mat.name, 'bookcloth_srgb': list(color)})
    return changed


def remove_floor_book():
    removed = [o.name for o in bpy.context.scene.objects
               if o.name.startswith('Reading | open picture book on floor')]
    for name in removed:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    return removed


def blank_car_markings():
    """Blank the scale car's number plate (printed studio name) and badge (logo)."""
    changed = []
    for mat in bpy.data.materials:
        if not mat.use_nodes or mat.users == 0:
            continue
        # Only images that actually drive the surface; an unlinked logo node
        # in the shared car metal has no visible effect and is left alone.
        logos = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image
                 and n.image.name.startswith(('Untitled-1-01', 'Fiat_Logo'))
                 and any(output.is_linked for output in n.outputs)]
        if not logos:
            continue
        shader = _principled(mat)
        plate = any(n.image.name.startswith('Untitled-1-01') for n in logos)
        for node in logos:
            mat.node_tree.nodes.remove(node)
        if plate:
            shader.inputs['Base Color'].default_value = (*linear((.83, .83, .80)), 1)
            shader.inputs['Metallic'].default_value = 0
            shader.inputs['Roughness'].default_value = .42
        else:
            shader.inputs['Base Color'].default_value = (*linear((.78, .78, .77)), 1)
            shader.inputs['Roughness'].default_value = .30
        changed.append(mat.name)
    return changed


def _star_sdf(x, y, radius, inner):
    """Signed distance to a regular five-pointed star (negative inside)."""
    k1x, k1y = .809016994375, -.587785252292
    x = np.abs(x)
    for kx, ky in ((k1x, k1y), (-k1x, k1y)):
        d = np.maximum(kx * x + ky * y, 0) * 2
        x, y = x - d * kx, y - d * ky
    x = np.abs(x)
    y = y - radius
    bax, bay = -inner * k1y, inner * k1x - 1
    h = np.clip((x * bax + y * bay) / (bax * bax + bay * bay), 0, radius)
    return np.hypot(x - bax * h, y - bay * h) * np.sign(y * bax - x * bay)


def _star_centres(count, seed):
    """Evenly spread print positions, rotated so no star sits on a UV pole."""
    i = np.arange(count) + .5
    z = 1 - 2 * i / count
    phi = i * math.pi * (3 - math.sqrt(5))
    base = np.column_stack((np.sqrt(1 - z * z) * np.cos(phi), np.sqrt(1 - z * z) * np.sin(phi), z))
    rng = np.random.default_rng(seed)
    best, best_gap = base, -1
    for _ in range(64):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        rot = np.asarray(Quaternion(q).to_matrix())
        points = base @ rot.T
        gap = np.min(np.arccos(np.clip(np.abs(points[:, 2]), 0, 1)))
        if gap > best_gap:
            best, best_gap = points, gap
    return best, rng


def star_print_image(settings):
    """Equirectangular print layer: cream five-pointed stars on a clear ground.

    The supplied atlas carries the star motif cut across low-poly UV island
    borders; printed at visible contrast it reads as torn blotches. The motif
    is therefore re-laid as a real pad print: evenly spaced stars of two sizes,
    computed per texel direction (no projection stretch), with a slightly
    worn edge. Values are a coverage mask; colours are applied in the shader.
    """
    width, height = settings['print_texture_px']
    centres, rng = _star_centres(settings['star_count'], settings['seed'])
    lon = (np.arange(width) + .5) / width * 2 * math.pi - math.pi
    lat = math.pi / 2 - (np.arange(height)[::-1] + .5) / height * math.pi
    lon, lat = np.meshgrid(lon, lat)
    d = np.stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)), axis=-1)
    coverage = np.zeros((height, width))
    edge = settings['print_edge_rad']
    for index, c in enumerate(centres):
        e1 = np.cross(c, (0, 0, 1) if abs(c[2]) < .9 else (1, 0, 0))
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(c, e1)
        angle = rng.uniform(0, 2 * math.pi)
        e1, e2 = e1 * math.cos(angle) + e2 * math.sin(angle), -e1 * math.sin(angle) + e2 * math.cos(angle)
        facing = d @ c
        visible = facing > .5
        radius = settings['star_radius_rad'][index % 2]
        x = np.where(visible, (d @ e1) / np.maximum(facing, 1e-6), 9)
        y = np.where(visible, (d @ e2) / np.maximum(facing, 1e-6), 9)
        sdf = _star_sdf(x, y, radius, settings['star_inner_ratio'])
        coverage = np.maximum(coverage, np.clip(.5 - sdf / edge, 0, 1))
    image = bpy.data.images.new('B01 | equirectangular star pad print', width, height, alpha=False, float_buffer=False)
    image.colorspace_settings.name = 'Non-Color'
    pixels = np.repeat(coverage.astype(np.float32)[..., None], 4, axis=2)
    pixels[..., 3] = 1
    image.pixels.foreach_set(pixels.ravel())
    image.update()
    image.pack()
    return image, centres


def _spherical_uv(mesh):
    """Longitude/latitude UVs from the refined sphere, continuous across the seam."""
    layer = mesh.uv_layers.new(name='B01 star print equirectangular')
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    direction = co / np.linalg.norm(co, axis=1)[:, None]
    u = (np.arctan2(direction[:, 1], direction[:, 0]) + math.pi) / (2 * math.pi)
    v = .5 + np.arcsin(np.clip(direction[:, 2], -1, 1)) / math.pi
    loop_vertex = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get('vertex_index', loop_vertex)
    starts = np.empty(len(mesh.polygons), dtype=np.int64)
    totals = np.empty(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get('loop_start', starts)
    mesh.polygons.foreach_get('loop_total', totals)
    loop_u = u[loop_vertex]
    for start, total in zip(starts, totals):
        # Faces straddling the longitude seam continue past u = 1 (REPEAT
        # extension); no star lies near the poles, where the print is blank.
        face = loop_u[start:start + total]
        if face.max() - face.min() > .5:
            face[face < .5] += 1
    uv = np.column_stack((loop_u, v[loop_vertex]))
    layer.data.foreach_set('uv', uv.ravel())
    return layer


def star_ball_finish(cfg, ball_root):
    """Pigmented vinyl ball with the star motif pad-printed in cream."""
    settings = cfg['appearance']['star_ball_finish']
    mesh_obj = next(o for o in ball_root.children_recursive if o.type == 'MESH')
    layer = _spherical_uv(mesh_obj.data)
    print_image, centres = star_print_image(settings)
    mat = bpy.data.materials.new('B01 | pigmented vinyl with printed cream stars')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = layer.name
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = print_image
    tex.interpolation = 'Cubic'
    links.new(uv.outputs['UV'], tex.inputs['Vector'])
    coord = nodes.new('ShaderNodeTexCoord')
    # Light rub-off of the printed ink at a few millimetres (object space).
    wear = nodes.new('ShaderNodeTexNoise')
    wear.inputs['Scale'].default_value = 260
    wear.inputs['Detail'].default_value = 4
    links.new(coord.outputs['Object'], wear.inputs['Vector'])
    rub = nodes.new('ShaderNodeMapRange')
    rub.inputs['From Min'].default_value, rub.inputs['From Max'].default_value = .62, .78
    rub.inputs['To Min'].default_value, rub.inputs['To Max'].default_value = 1, 1 - settings['print_wear']
    links.new(wear.outputs['Fac'], rub.inputs['Value'])
    mask = nodes.new('ShaderNodeMath')
    mask.operation = 'MULTIPLY'
    mask.use_clamp = True
    links.new(tex.outputs['Color'], mask.inputs[0])
    links.new(rub.outputs['Result'], mask.inputs[1])
    mask_out = mask.outputs[0]
    # Subtle pigment/dust mottling (cm scale) and moulding orange peel (mm scale).
    mottle = nodes.new('ShaderNodeTexNoise')
    mottle.inputs['Scale'].default_value = 38
    mottle.inputs['Detail'].default_value = 3
    links.new(coord.outputs['Object'], mottle.inputs['Vector'])
    body = nodes.new('ShaderNodeMixRGB')
    body.inputs[1].default_value = (*linear(tuple(c * .965 for c in settings['body_srgb'])), 1)
    body.inputs[2].default_value = (*linear(tuple(min(1, c * 1.025) for c in settings['body_srgb'])), 1)
    links.new(mottle.outputs['Fac'], body.inputs[0])
    paint = nodes.new('ShaderNodeMixRGB')
    links.new(mask_out, paint.inputs[0])
    links.new(body.outputs[0], paint.inputs[1])
    paint.inputs[2].default_value = (*linear(settings['star_srgb']), 1)
    links.new(paint.outputs[0], bsdf.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = settings['roughness']
    links.new(mottle.outputs['Fac'], rough.inputs['Value'])
    ink = nodes.new('ShaderNodeMath')
    ink.operation = 'MULTIPLY_ADD'
    ink.inputs[1].default_value = settings['print_roughness_offset']
    links.new(mask_out, ink.inputs[0])
    links.new(rough.outputs['Result'], ink.inputs[2])
    links.new(ink.outputs[0], bsdf.inputs['Roughness'])
    peel = nodes.new('ShaderNodeTexNoise')
    peel.inputs['Scale'].default_value = 950
    peel.inputs['Detail'].default_value = 2
    links.new(coord.outputs['Object'], peel.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = .00002
    bump.inputs['Strength'].default_value = .12
    links.new(peel.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['IOR'].default_value = 1.53
    bsdf.inputs['Coat Weight'].default_value = settings['coat_weight']
    bsdf.inputs['Coat Roughness'].default_value = settings['coat_roughness']
    bsdf.inputs['Coat IOR'].default_value = 1.5
    mesh_obj.data.materials[0] = mat
    return {'material': mat.name, 'print_image': print_image.name,
            'star_centres_object_space': centres.round(6).tolist(), **settings}


def football_scuffs(cfg, football_root):
    """Low-strength use marks from the football asset's own scuff map (UV)."""
    strength = cfg['appearance']['football_scuff_strength']
    dirt = next((img for img in bpy.data.images if img.name.startswith('soccer_dirtmap')), None)
    if dirt is None or not dirt.size[0]:
        raise ValueError('Expected the stitched football asset scuff map')
    mat = bpy.data.materials['B02 | off-white pebbled football panels']
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = _principled(mat)
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = dirt
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'UVMap'
    links.new(uv.outputs['UV'], tex.inputs['Vector'])
    gray = nodes.new('ShaderNodeRGBToBW')
    links.new(tex.outputs['Color'], gray.inputs[0])
    # 1 on clean areas, down to (1 - strength) in the darkest scuffs.
    amount = nodes.new('ShaderNodeMapRange')
    amount.inputs['From Min'].default_value, amount.inputs['From Max'].default_value = .25, .85
    amount.inputs['To Min'].default_value, amount.inputs['To Max'].default_value = 1 - strength, 1
    links.new(gray.outputs[0], amount.inputs['Value'])
    source = bsdf.inputs['Base Color'].links[0].from_socket
    grime = nodes.new('ShaderNodeMixRGB')
    grime.blend_type = 'MULTIPLY'
    grime.inputs[0].default_value = 1
    links.new(source, grime.inputs[1])
    tint = nodes.new('ShaderNodeCombineColor')
    links.new(amount.outputs['Result'], tint.inputs[0])
    warm = nodes.new('ShaderNodeMath')
    warm.operation = 'MULTIPLY'
    warm.inputs[1].default_value = .985
    links.new(amount.outputs['Result'], warm.inputs[0])
    links.new(amount.outputs['Result'], tint.inputs[1])
    links.new(warm.outputs[0], tint.inputs[2])
    links.new(tint.outputs[0], grime.inputs[2])
    _unlink(mat, bsdf.inputs['Base Color'])
    links.new(grime.outputs[0], bsdf.inputs['Base Color'])
    return {'source_image': dirt.name, 'max_darkening': strength}


def oak_floor(cfg):
    """Give the floor plane a scanned satin oak plank finish over the linoleum layer.

    The registered Poly Haven wood_floor scan (CC0, 1.7 m capture) is mapped in
    world metres with planks running away from the camera. Only appearance
    changes: the solved floor plane, its height and contact parameters stay.
    """
    settings = cfg['appearance']['floor_finish']
    floor = bpy.data.objects['F01 | continuous level floor']
    mat = bpy.data.materials.new('Floor | photographed satin oak planks')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    geometry = nodes.new('ShaderNodeNewGeometry')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Location'].default_value = (*settings['offset_m'], 0)
    mapping.inputs['Rotation'].default_value[2] = math.radians(settings['rotation_degrees'])
    mapping.inputs['Scale'].default_value = (1 / settings['tile_m'],) * 3
    links.new(geometry.outputs['Position'], mapping.inputs['Vector'])
    maps = {}
    for channel, color in (('diff', True), ('rough', False), ('nor_gl', False)):
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(asset(
            f"{settings['asset']}/{settings['asset'].split('/')[-1]}_{channel}_{settings['resolution']}.jpg")),
            check_existing=True)
        tex.image.colorspace_settings.name = 'sRGB' if color else 'Non-Color'
        links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
        maps[channel] = tex
    tone = nodes.new('ShaderNodeHueSaturation')
    tone.inputs['Saturation'].default_value = settings['saturation']
    tone.inputs['Value'].default_value = settings['value']
    links.new(maps['diff'].outputs['Color'], tone.inputs['Color'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = settings['roughness']
    links.new(maps['rough'].outputs['Color'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = settings['normal_strength']
    links.new(maps['nor_gl'].outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['IOR'].default_value = 1.5
    bsdf.inputs['Coat Weight'].default_value = settings['coat_weight']
    bsdf.inputs['Coat Roughness'].default_value = settings['coat_roughness']
    floor.data.materials.clear()
    floor.data.materials.append(mat)
    return {'material': mat.name, **settings,
            'policy': 'Appearance only; floor plane, top height and contact parameters unchanged.'}


def room(cfg):
    ledger = room_textiles(cfg)
    ledger['floor_finish'] = oak_floor(cfg)
    ledger['text_free_props'] = {
        'plain_bookcloth_covers': plain_book_covers(),
        'removed_floor_book': remove_floor_book(),
        'blank_car_markings': blank_car_markings(),
        'policy': 'No legible text, titles, watermarks, plates or logos remain on visible props.'}
    ledger['appearance_revision'] = ('Photographic pass: room, light and camera of the playroom; star ball printed '
        'in cream on pigmented vinyl, football use marks, text-free books and car.')
    return ledger


def toys(cfg):
    objects = toys_textiles(cfg)
    star_ball_finish(cfg, objects['ball'])
    football_scuffs(cfg, objects['football'])
    return objects


def lighting(cfg):
    lighting_textiles(cfg)
