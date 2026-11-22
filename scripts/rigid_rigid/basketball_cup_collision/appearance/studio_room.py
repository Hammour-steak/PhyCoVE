"""A small studio flat around the desk, built on the simulator's own planes.

This module builds an ordinary single-occupancy studio, lit by afternoon sun
through two windows, and every surface the ball or the cup touches in the five
cases is placed from the numbers the simulator itself uses
(physics/scene_geometry.py):

* the desk top is the simulator's desk box -- 0.80 m x 1.44 m, top at 0.80 m;
* the east wall's plaster is the x = 2.50 face of the solid wall behind the
  desk, where the cup and the ball strike;
* the flat carton beside the desk is the ``carton`` box (0.64 x 0.62 x 0.18 m);
* the low coffee table in the bottom-left corner of the frame stands on the
  ``coffee_table`` box, whose x = -1.03 face the ball rolls into in the
  heavy-bottle case;
* the floor is z = 0, and the west, south and north walls are the inner faces
  of the simulator's safety walls.

The simulator's bed, pillow, vent, sofa and chair boxes are never touched in any
case and have no visible counterpart. Everything else here is decoration the
simulator does not know about: ``check_clearance`` refuses a take in which a
moving body comes within 2 cm of a decorative piece, and ``check_occlusion``
one in which a decorative piece hides a moving body from the camera.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

from scene_geometry import TABLE_CENTER, TABLE_HALF, TABLE_TOP_Z, prop_box

# --------------------------------------------------------------------- plan
# Plaster planes of the room (world metres). East: the face of the solid wall
# behind the desk. West/south/north: inner faces of the safety walls.
ROOM_X = (-2.90, 2.50)
ROOM_Y = (-3.385, 2.56)
CEILING_Z = 2.65
WALL_THICK_M = 0.20
SKIRT_HEIGHT_M = 0.08
SKIRT_PROUD_M = 0.012
# The solid wall the simulator puts behind the desk only spans this much of
# the east wall; outside it the plaster has no collider behind it.
_BACK_LO, _BACK_HI = prop_box('back_wall')

# Two windows: the main one in the east wall beyond the desk, which takes the
# afternoon sun, and one in the north wall above the sofa. Each is (wall, span
# along the wall in world metres, sill and head heights).
WINDOWS = [dict(wall='east', span=(0.80, 1.90), z=(0.90, 2.30)),
           dict(wall='north', span=(0.35, 1.55), z=(0.90, 2.30))]
# Sill-length sheer curtains drawn to both sides of each window.
CURTAIN_TOP_Z = 2.42
CURTAIN_BOTTOM_Z = 0.80

# Afternoon sun. HEADING is the direction the light travels across the floor,
# degrees from +x towards +y: it comes in through both windows, laying long
# patches across the floor in front of the desk and on the rug, and only
# grazes the far end of the desk. The elevation is the sun's own in the
# window photograph.
SUN_ELEVATION_DEG = 29.5
SUN_HEADING_DEG = 218.0
SUN_ENERGY = 4.6
SKY_STRENGTH = 1.0
# Poly Haven urban_street_04 (a sunny residential street of white stucco
# terraces): its sun stands at u = 0.6003, v = 0.3361 of the equirectangular
# photograph, i.e. azimuth (0.5 - u) * 360 = -36.1 deg and elevation 29.5 deg in
# the photograph's own frame. It is shown to camera rays through the glass only
# and turned so that its sun stands where the lamp is. With the sun at this
# heading both windows look along the street towards its far end, past
# terraces 20-40 m away, rather than at the balustrade and cars a few metres
# from the photographer, which would look magnified in a pane 5 m from the
# camera.
WINDOW_VIEW = 'urban_street_04_2k.hdr'
WINDOW_VIEW_SUN_AZIMUTH_DEG = -36.1
WINDOW_VIEW_STRENGTH = 1.6

# Laminate_floor is authored as a 2 m patch, oak_veneer_03 as a 1 m patch,
# wool_boucle as a 0.31 x 0.39 m swatch, crepe_georgette as a 0.26 m swatch.
FLOOR_TEX = ('laminate_floor_diff_2k.jpg', 2.0)
DESK_TEX = ('oak_veneer_03_diff_2k.jpg', 1.0)
RUG_TEX = ('wool_boucle_diff_2k.jpg', 0.35)
CURTAIN_TEX = ('crepe_georgette_diff_2k.jpg', 0.26)

# Poly Haven CC0 furniture: model, anchor (bounding-box faces / centre, metres),
# yaw. Models face -y as authored. ``scale`` corrects files authored in the
# wrong unit (steel_frame_shelves_01 is stored ten times too large; its
# published size is 1.10 x 0.50 x 2.14 m).
FURNITURE = [
    # Chesterfield sofa under the north window, its back against the wall.
    dict(model='sofa_02', name='Sofa', yaw_deg=0.0, x=0.95, y_max=ROOM_Y[1] - 0.025),
    # Steel and oak shelving in the north-west corner of the view.
    dict(model='steel_frame_shelves_01', name='Shelving', yaw_deg=0.0, scale=0.1,
         x_max=-0.02, y_max=ROOM_Y[1] - 0.02),
    # Architect lamp at the far end of the desk, its head towards the wall. The
    # model's origin is its mounting collar; the peg below it goes into the
    # desk top, so the origin is set on the top face.
    dict(model='desk_lamp_arm_01', name='Desk lamp', yaw_deg=-90.0, at=(2.17, 0.10, TABLE_TOP_Z)),
]
# A few things on the shelving: (model, name, x, y, shelf height, yaw). The
# shelf boards of steel_frame_shelves_01 stand 0.134, 0.640, 1.146 and
# 1.652 m above the floor.
SHELF_ITEMS = [
    ('metal_jug', 'Enamel milk can', -0.80, 2.30, 0.134, 20.0),
    ('carved_wooden_elephant', 'Carved elephant', -0.35, 2.28, 0.640, -30.0),
    ('standing_picture_frame_02', 'Framed photograph', -0.55, 2.36, 1.146, 100.0),
]
# An abstract print in a black frame on the east wall, right of the desk:
# (y span, z span) of the frame's outer edge.
PRINT = dict(y=(-2.42, -1.80), z=(1.12, 1.94))
# A white steel panel radiator under the print, on brackets off the east wall
# and piped from the floor: (y span, z span) of its panels.
RADIATOR = dict(y=(-2.90, -2.12), z=(0.15, 0.73))
# Low coffee table standing on the simulator's coffee-table box: its east face
# is the box's x = -1.03 face the ball rolls into.
COFFEE_TABLE = dict(model='modern_coffee_table_02', name='Coffee table', yaw_deg=0.0)
# Wool rug in front of the sofa, well away from every floor path of the ball.
RUG = dict(x=(-0.40, 1.60), y=(0.25, 1.62), height_m=0.008)


# ------------------------------------------------------------------ geometry


def _link(name: str, mesh, material) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _finish(bm, name: str, material) -> bpy.types.Object:
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = False
    return _link(name, mesh, material)


def _box(name: str, lo, hi, material, bevel: float = 0.0, yaw: float = 0.0) -> bpy.types.Object:
    """Axis box from its two corners (optionally turned about its own centre)."""
    lo, hi = Vector(lo), Vector(hi)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=hi - lo, verts=bm.verts)
    bmesh.ops.transform(bm, matrix=Matrix.Translation((lo + hi) / 2) @ Matrix.Rotation(yaw, 4, 'Z'),
                        verts=bm.verts)
    obj = _finish(bm, name, material)
    if bevel:
        mod = obj.modifiers.new('Soft edges', 'BEVEL')
        mod.width, mod.segments = bevel, 3
        mod.limit_method = 'ANGLE'
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return obj


def _ring(name: str, outer, inner, z0: float, z1: float, material) -> bpy.types.Object:
    """A closed band between two rectangles given as (x0, x1, y0, y1)."""
    def corners(r):
        x0, x1, y0, y1 = r
        return [Vector((x0, y0)), Vector((x1, y0)), Vector((x1, y1)), Vector((x0, y1))]
    bm = bmesh.new()
    rings = [[bm.verts.new((p.x, p.y, z)) for p in corners(r)] for r in (outer, inner) for z in (z0, z1)]
    o0, o1, i0, i1 = rings
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((o0[i], o0[j], o1[j], o1[i]))
        bm.faces.new((i0[i], i1[i], i1[j], i0[j]))
        bm.faces.new((o0[i], i0[i], i0[j], o0[j]))
        bm.faces.new((o1[i], o1[j], i1[j], i1[i]))
    return _finish(bm, name, material)


def _cylinder(name: str, start, end, radius: float, material, segments: int = 24) -> bpy.types.Object:
    start, end = Vector(start), Vector(end)
    axis = end - start
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius,
                          depth=axis.length)
    rot = axis.normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((start + end) / 2) @ rot, verts=bm.verts)
    obj = _finish(bm, name, material)
    for poly in obj.data.polygons:
        poly.use_smooth = abs(poly.normal.dot(axis.normalized())) < 0.5
    return obj


def _cut(target: bpy.types.Object, cutter: bpy.types.Object) -> None:
    mod = target.modifiers.new(f'cut {cutter.name}', 'BOOLEAN')
    mod.operation, mod.solver, mod.object = 'DIFFERENCE', 'EXACT', cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


# ----------------------------------------------------------------- materials


def _material(name: str, colour, roughness: float, metallic: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*colour, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*colour, 1.0)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return mat


def _bump(mat, scale: float, distance: float, strength: float = 0.2, coords: str = 'Object'):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = scale
    noise.inputs['Detail'].default_value = 2.0
    links.new(coord.outputs[coords], noise.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = strength
    bump.inputs['Distance'].default_value = distance
    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], nodes.get('Principled BSDF').inputs['Normal'])
    return mat


def _emulsion(name: str, colour, roughness: float = 0.86) -> bpy.types.Material:
    """Rolled matt emulsion: one colour, drifting a few percent in tone and sheen."""
    mat = _bump(_material(name, colour, roughness), 170.0, 0.0012, 0.22)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    position = nodes.new('ShaderNodeNewGeometry')
    drift = nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value = 0.8
    drift.inputs['Detail'].default_value = 3.0
    links.new(position.outputs['Position'], drift.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].position = 0.3
    tone.color_ramp.elements[0].color = (*(c * 0.955 for c in colour), 1.0)
    tone.color_ramp.elements[1].position = 0.7
    tone.color_ramp.elements[1].color = (*(min(1.0, c * 1.03) for c in colour), 1.0)
    links.new(drift.outputs['Fac'], tone.inputs['Fac'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    sheen = nodes.new('ShaderNodeMapRange')
    sheen.inputs['To Min'].default_value = roughness - 0.06
    sheen.inputs['To Max'].default_value = min(1.0, roughness + 0.06)
    links.new(drift.outputs['Fac'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    return mat


def _scanned(name: str, diffuse: Path, tile_m: float, *, rotate_deg: float = 0.0,
             roughness_min: float = 0.0, roughness_scale: float = 1.0, tint=None,
             coords: str = 'Object') -> bpy.types.Material:
    """A Poly Haven texture set (colour, roughness, OpenGL normal) at its real size."""
    mat = _material(name, (0.4, 0.3, 0.2), 0.5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1.0 / tile_m, 1.0 / tile_m, 1.0 / tile_m)
    mapping.inputs['Rotation'].default_value = (0.0, 0.0, math.radians(rotate_deg))
    links.new(coord.outputs[coords], mapping.inputs['Vector'])

    def scan(kind: str, colour_data: bool):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(diffuse).replace('_diff_', f'_{kind}_'), check_existing=True)
        if not colour_data:
            node.image.colorspace_settings.name = 'Non-Color'
        node.extension = 'REPEAT'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    colour = scan('diff', True).outputs['Color']
    if tint is not None:
        mix = nodes.new('ShaderNodeMix')
        mix.data_type, mix.blend_type = 'RGBA', 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        # ShaderNodeMix keeps float, vector and colour sockets side by side;
        # the colour A/B inputs are 6/7 and the colour result is output 2.
        links.new(colour, mix.inputs[6])
        mix.inputs[7].default_value = (*tint, 1.0)
        colour = mix.outputs[2]
    links.new(colour, bsdf.inputs['Base Color'])
    rough = scan('rough', False).outputs['Color']
    if roughness_scale != 1.0 or roughness_min > 0.0:
        remap = nodes.new('ShaderNodeMapRange')
        remap.clamp = True
        remap.inputs['To Min'].default_value = roughness_min
        remap.inputs['To Max'].default_value = roughness_scale
        links.new(rough, remap.inputs['Value'])
        rough = remap.outputs['Result']
    links.new(rough, bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(scan('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def _kraft() -> bpy.types.Material:
    """Corrugated kraft board: mottled brown paper, flutes telegraphing through.

    Poly Haven has no cardboard scan, so the paper is procedural: a low-
    frequency mottle in tone, paper fibre in the roughness and relief, and the
    8 mm flutes of the board underneath as a faint ripple along one axis.
    """
    mat = _material('Kraft carton board', (0.42, 0.25, 0.12), 0.82)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Specular IOR Level'].default_value = 0.35
    coord = nodes.new('ShaderNodeTexCoord')
    mottle = nodes.new('ShaderNodeTexNoise')
    mottle.inputs['Scale'].default_value = 9.0
    mottle.inputs['Detail'].default_value = 4.0
    links.new(coord.outputs['Object'], mottle.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].color = (0.36, 0.21, 0.10, 1.0)
    tone.color_ramp.elements[1].color = (0.47, 0.29, 0.15, 1.0)
    links.new(mottle.outputs['Fac'], tone.inputs['Fac'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    fibre = nodes.new('ShaderNodeTexNoise')
    fibre.inputs['Scale'].default_value = 900.0
    fibre.inputs['Detail'].default_value = 6.0
    links.new(coord.outputs['Object'], fibre.inputs['Vector'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = 0.74
    rough.inputs['To Max'].default_value = 0.92
    links.new(fibre.outputs['Fac'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    flutes = nodes.new('ShaderNodeTexWave')
    flutes.wave_type, flutes.bands_direction = 'BANDS', 'Y'
    # Blender's wave bands repeat every 2*pi/20 texture units: 8 mm flutes.
    flutes.inputs['Scale'].default_value = (2 * math.pi / 20.0) / 0.008
    links.new(coord.outputs['Object'], flutes.inputs['Vector'])
    relief = nodes.new('ShaderNodeMath')
    relief.operation = 'MULTIPLY_ADD'
    relief.inputs[1].default_value = 0.15
    links.new(flutes.outputs['Fac'], relief.inputs[0])
    links.new(fibre.outputs['Fac'], relief.inputs[2])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.12
    bump.inputs['Distance'].default_value = 0.0006
    links.new(relief.outputs['Value'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def _thin_glass() -> bpy.types.Material:
    """Thin float glass: a 4 % Fresnel reflection over a see-through layer.

    Shaded as transparent so rays through it stay camera rays: the world shows
    the street photograph to the camera alone while the room is lit by the
    physical sky. Cycles' Fresnel node treats a back face as glass-to-air (it
    inverts the IOR), which totally reflects rays leaving the pane at more than
    41 deg and turns an obliquely seen window black; feeding the inverse IOR on
    back faces cancels that inversion.
    """
    existing = bpy.data.materials.get('Clear float glass')
    if existing is not None:
        return existing
    mat = bpy.data.materials.new('Clear float glass')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    clear = nodes.new('ShaderNodeBsdfTransparent')
    reflection = nodes.new('ShaderNodeBsdfGlossy')
    reflection.inputs['Roughness'].default_value = 0.0
    fresnel = nodes.new('ShaderNodeFresnel')
    geometry = nodes.new('ShaderNodeNewGeometry')
    ior = nodes.new('ShaderNodeMath')
    ior.operation = 'MULTIPLY_ADD'
    ior.inputs[1].default_value = 1.0 / 1.52 - 1.52
    ior.inputs[2].default_value = 1.52
    links.new(geometry.outputs['Backfacing'], ior.inputs[0])
    links.new(ior.outputs['Value'], fresnel.inputs['IOR'])
    pane = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], pane.inputs['Fac'])
    links.new(clear.outputs['BSDF'], pane.inputs[1])
    links.new(reflection.outputs['BSDF'], pane.inputs[2])
    links.new(pane.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


def _sheer(diffuse: Path, tile_m: float) -> bpy.types.Material:
    """Sheer polyester voile: mostly see-through, the weave lit from behind."""
    mat = _scanned('Sheer voile', diffuse, tile_m, roughness_min=0.6, coords='UV')
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    # The georgette scan is faintly green; keep its weave, not its dye.
    scan = bsdf.inputs['Base Color'].links[0].from_socket
    grey = nodes.new('ShaderNodeRGBToBW')
    links.new(scan, grey.inputs['Color'])
    white = nodes.new('ShaderNodeMix')
    white.data_type, white.blend_type = 'RGBA', 'MULTIPLY'
    white.inputs['Factor'].default_value = 1.0
    links.new(grey.outputs['Val'], white.inputs[6])
    white.inputs[7].default_value = (1.0, 0.98, 0.95, 1.0)
    links.new(white.outputs[2], bsdf.inputs['Base Color'])
    bsdf.inputs['Transmission Weight'].default_value = 0.0
    bsdf.inputs['Subsurface Weight'].default_value = 0.0
    output = nodes['Material Output']
    translucent = nodes.new('ShaderNodeBsdfTranslucent')
    translucent.inputs['Color'].default_value = (0.92, 0.90, 0.86, 1.0)
    cloth = nodes.new('ShaderNodeMixShader')
    cloth.inputs['Fac'].default_value = 0.45
    links.new(bsdf.outputs['BSDF'], cloth.inputs[1])
    links.new(translucent.outputs['BSDF'], cloth.inputs[2])
    hole = nodes.new('ShaderNodeBsdfTransparent')
    weave = nodes.new('ShaderNodeMixShader')
    weave.inputs['Fac'].default_value = 0.42
    links.new(cloth.outputs['Shader'], weave.inputs[1])
    links.new(hole.outputs['BSDF'], weave.inputs[2])
    links.new(weave.outputs['Shader'], output.inputs['Surface'])
    return mat


# ----------------------------------------------------------------- furniture


def place_model(path: Path, name: str, *, yaw_deg: float = 0.0, scale: float = 1.0,
                **anchor) -> dict[str, Any]:
    """Import a glTF model, scale it uniformly, turn it about z and set its
    bounding box on an anchor: ``x``/``y`` (centre), ``x_min``/``x_max``/
    ``y_min``/``y_max`` (faces) and ``z`` (bottom) -- or put the model's own
    origin at ``at``."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in before]
    for obj in imported:
        obj.animation_data_clear()
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world
    root.scale = (scale, scale, scale)
    root.rotation_euler.z = math.radians(yaw_deg)
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == 'MESH']
    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material is not None and 'glass' in slot.material.name.lower():
                slot.material = _thin_glass()
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    shift = Vector((0.0, 0.0, 0.0))
    for axis, index in (('x', 0), ('y', 1)):
        if axis in anchor:
            shift[index] = anchor[axis] - (lo[index] + hi[index]) / 2.0
        elif f'{axis}_min' in anchor:
            shift[index] = anchor[f'{axis}_min'] - lo[index]
        elif f'{axis}_max' in anchor:
            shift[index] = anchor[f'{axis}_max'] - hi[index]
    if 'z' in anchor:
        shift.z = anchor['z'] - lo.z
    if 'at' in anchor:
        shift = Vector(anchor['at'])
    root.location = shift
    bpy.context.view_layer.update()
    lo, hi = lo + shift, hi + shift
    return {'name': name, 'model': path.name, 'yaw_deg': yaw_deg, 'objects': [o.name for o in meshes],
            'bbox_min': [round(v, 4) for v in lo], 'bbox_max': [round(v, 4) for v in hi]}


def _piece(name: str, objects) -> dict[str, Any]:
    """Name, world bounding box and object names of procedural geometry."""
    bpy.context.view_layer.update()
    points = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    return {'name': name, 'objects': [o.name for o in objects],
            'bbox_min': [round(min(p[i] for p in points), 4) for i in range(3)],
            'bbox_max': [round(max(p[i] for p in points), 4) for i in range(3)]}


# ---------------------------------------------------------------------- room


def _desk(top_material, frame_material) -> list[bpy.types.Object]:
    """The desk on the simulator's desk box: an oak-veneered board on a black
    steel frame. The board's top face and its four edges are the box's top
    face (0.80 x 1.44 m at 0.80 m); the frame stands inside the box."""
    (cx, cy), (hx, hy), top = TABLE_CENTER, TABLE_HALF, TABLE_TOP_Z
    board_t, leg, inset, apron = 0.025, 0.04, 0.035, 0.07
    x0, x1, y0, y1 = cx - hx, cx + hx, cy - hy, cy + hy
    parts = [_box('Desk top', (x0, y0, top - board_t), (x1, y1, top), top_material, bevel=0.0015)]
    under = top - board_t
    for sx in (x0 + inset, x1 - inset - leg):
        for sy in (y0 + inset, y1 - inset - leg):
            parts.append(_box('Desk leg', (sx, sy, 0.0), (sx + leg, sy + leg, under), frame_material, 0.002))
            parts.append(_box('Desk foot', (sx - 0.002, sy - 0.002, 0.0), (sx + leg + 0.002, sy + leg + 0.002, 0.006),
                              _material('Felt glide', (0.05, 0.05, 0.05), 0.9)))
    for sx in (x0 + inset, x1 - inset - 0.02):
        parts.append(_box('Desk apron long', (sx, y0 + inset, under - apron), (sx + 0.02, y1 - inset, under),
                          frame_material, 0.0015))
    for sy in (y0 + inset, y1 - inset - 0.02):
        parts.append(_box('Desk apron short', (x0 + inset, sy, under - apron), (x1 - inset, sy + 0.02, under),
                          frame_material, 0.0015))
    return parts


def _carton(kraft) -> list[bpy.types.Object]:
    """A flat shipping carton on the simulator's carton box (0.64 x 0.62 x 0.18 m),
    flaps meeting along its length and taped over."""
    lo, hi = prop_box('carton')
    body = _box('Carton', lo, hi, kraft, bevel=0.004)
    cx = (lo[0] + hi[0]) / 2
    tape = _material('Brown packing tape', (0.17, 0.095, 0.035), 0.16)
    tape.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value = 0.3
    _bump(tape, 45.0, 0.0005, 0.25)
    w, t = 0.048, 0.0003
    parts = [body,
             _box('Carton seam', (cx - 0.0008, lo[1] + 0.004, hi[2] - 0.0006), (cx + 0.0008, hi[1] - 0.004, hi[2] + 0.00005),
                  _material('Carton seam shadow', (0.06, 0.035, 0.02), 0.9)),
             _box('Carton tape', (cx - w / 2, lo[1] - t, hi[2]), (cx + w / 2, hi[1] + t, hi[2] + t), tape)]
    for end, sign in ((lo[1], -1), (hi[1], 1)):
        face = end + sign * t
        parts.append(_box('Carton tape end', (cx - w / 2, min(end, face), hi[2] - 0.07), (cx + w / 2, max(end, face), hi[2]), tape))
    return parts


def _wall_box(name: str, wall: str, s0, s1, d0, d1, z0, z1, material, bevel: float = 0.0):
    """A box given along a wall (s), into it from its plaster face (d, positive
    outwards) and in height (z)."""
    if wall == 'north':
        face = ROOM_Y[1]
        return _box(name, (s0, face + d0, z0), (s1, face + d1, z1), material, bevel)
    if wall == 'east':
        face = ROOM_X[1]
        return _box(name, (face + d0, s0, z0), (face + d1, s1, z1), material, bevel)
    raise ValueError(wall)


def _window(spec, walls, frame_paint, sill_material) -> list[bpy.types.Object]:
    """A hole through the wall, a two-light anthracite frame set in the middle
    of the reveal, thin glass, a stone window board and a sky portal."""
    wall, (a0, a1), (z0, z1) = spec['wall'], spec['span'], spec['z']
    tag = f'Window ({wall})'
    _cut(walls, _wall_box(f'{tag} hole', wall, a0, a1, -0.05, WALL_THICK_M + 0.05, z0, z1, None))
    d0, d1 = 0.075, 0.145
    bar, mull, s = 0.065, 0.04, 0.045
    am = (a0 + a1) / 2
    parts = [
        _wall_box(f'{tag} frame head', wall, a0, a1, d0, d1, z1 - bar, z1, frame_paint, 0.002),
        _wall_box(f'{tag} frame sill', wall, a0, a1, d0, d1, z0, z0 + bar, frame_paint, 0.002),
        _wall_box(f'{tag} frame jamb', wall, a0, a0 + bar, d0, d1, z0 + bar, z1 - bar, frame_paint, 0.002),
        _wall_box(f'{tag} frame jamb', wall, a1 - bar, a1, d0, d1, z0 + bar, z1 - bar, frame_paint, 0.002),
        _wall_box(f'{tag} mullion', wall, am - mull, am + mull, d0 - 0.008, d1, z0 + bar, z1 - bar, frame_paint, 0.002),
    ]
    # Each opening light has its own sash profile inside the frame.
    for b0, b1 in ((a0 + bar, am - mull), (am + mull, a1 - bar)):
        parts += [
            _wall_box(f'{tag} sash rail', wall, b0, b1, d0 - 0.012, d0 + 0.05, z1 - bar - s, z1 - bar, frame_paint, 0.0015),
            _wall_box(f'{tag} sash rail', wall, b0, b1, d0 - 0.012, d0 + 0.05, z0 + bar, z0 + bar + s, frame_paint, 0.0015),
            _wall_box(f'{tag} sash stile', wall, b0, b0 + s, d0 - 0.012, d0 + 0.05, z0 + bar + s, z1 - bar - s, frame_paint, 0.0015),
            _wall_box(f'{tag} sash stile', wall, b1 - s, b1, d0 - 0.012, d0 + 0.05, z0 + bar + s, z1 - bar - s, frame_paint, 0.0015),
        ]
        pane = _wall_box(f'{tag} glass', wall, b0 + s - 0.01, b1 - s + 0.01, d0 + 0.016, d0 + 0.022,
                         z0 + bar + s - 0.01, z1 - bar - s + 0.01, _thin_glass())
        pane.visible_shadow = False
        parts.append(pane)
    # Interior window board, a little proud of the plaster.
    parts.append(_wall_box(f'{tag} board', wall, a0 - 0.05, a1 + 0.05, -0.035, d0, z0 - 0.025, z0, sill_material, 0.002))
    # The reveal is the plastered wall itself; the sky portal sits outside it.
    data = bpy.data.lights.new(f'{tag} sky portal', 'AREA')
    data.shape, data.size, data.size_y = 'RECTANGLE', a1 - a0, z1 - z0
    data.cycles.is_portal = True
    portal = bpy.data.objects.new(f'{tag} sky portal', data)
    bpy.context.collection.objects.link(portal)
    out = WALL_THICK_M + 0.01
    if wall == 'north':
        portal.location, inward = (am, ROOM_Y[1] + out, (z0 + z1) / 2), Vector((0.0, -1.0, 0.0))
    else:
        portal.location, inward = (ROOM_X[1] + out, am, (z0 + z1) / 2), Vector((-1.0, 0.0, 0.0))
    portal.rotation_euler = inward.to_track_quat('-Z', 'Y').to_euler()
    return parts


def _curtain_panel(name: str, wall: str, a0: float, a1: float, inset: float, material, seed: float):
    """A gathered sheer panel hanging ``inset`` in front of the plaster:
    pleats deeper at the heading than at the hem."""
    bm = bmesh.new()
    cols = max(8, int((a1 - a0) / 0.006))
    rows = 24
    uv_layer = bm.loops.layers.uv.new('UVMap')
    grid = []
    for r in range(rows + 1):
        t = r / rows
        z = CURTAIN_BOTTOM_Z + t * (CURTAIN_TOP_Z - CURTAIN_BOTTOM_Z)
        depth = 0.020 + 0.012 * t
        row = []
        for c in range(cols + 1):
            a = a0 + c / cols * (a1 - a0)
            phase = 2 * math.pi * (a - a0) / 0.085 + 0.6 * math.sin(7.0 * a + seed) + 0.25 * t * math.sin(3.1 * a + seed)
            d = -inset + depth * math.sin(phase)
            row.append(bm.verts.new((a, ROOM_Y[1] + d, z) if wall == 'north' else (ROOM_X[1] + d, a, z)))
        grid.append(row)
    for r in range(rows):
        for c in range(cols):
            f = bm.faces.new((grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c]))
            for loop, (rr, cc) in zip(f.loops, ((r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c))):
                # Fabric length along the pleats (~1.6x the gathered width).
                loop[uv_layer].uv = (1.6 * cc / cols * (a1 - a0), rr / rows * (CURTAIN_TOP_Z - CURTAIN_BOTTOM_Z))
    obj = _finish(bm, name, material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def _curtains(spec, material, metal) -> list[bpy.types.Object]:
    wall, (a0, a1) = spec['wall'], spec['span']
    tag = f'Curtain ({wall})'
    inset = 0.085
    rod_z = CURTAIN_TOP_Z + 0.035

    def at(a, d, z=rod_z):
        return (a, ROOM_Y[1] - d, z) if wall == 'north' else (ROOM_X[1] - d, a, z)
    reach = 0.30 if wall == 'north' else 0.26
    parts = [_cylinder(f'{tag} rod', at(a0 - reach - 0.06, inset), at(a1 + reach + 0.06, inset), 0.011, metal)]
    for a in (a0 - reach, a1 + reach):
        parts.append(_cylinder(f'{tag} rod bracket', at(a, 0.0), at(a, inset + 0.01), 0.006, metal, 12))
        parts.append(_cylinder(f'{tag} rod bracket plate', at(a, 0.0), at(a, 0.006), 0.022, metal))
    for a, sign in ((a0 - reach - 0.06, -1), (a1 + reach + 0.06, 1)):
        parts.append(_cylinder(f'{tag} rod finial', at(a - sign * 0.01, inset), at(a + sign * 0.02, inset), 0.016, metal))
    parts.append(_curtain_panel(f'{tag} sheer left', wall, a0 - reach + 0.02, a0 + 0.14, inset - 0.005, material, 0.7))
    parts.append(_curtain_panel(f'{tag} sheer right', wall, a1 - 0.14, a1 + reach - 0.02, inset - 0.005, material, 2.3))
    return parts


def _abstract_print(frame_paint) -> list[bpy.types.Object]:
    """A framed abstract print: three flat colour shapes on off-white paper,
    no lettering. Drawn in the shader from the paper's own coordinates."""
    (b0, b1), (z0, z1) = PRINT['y'], PRINT['z']
    face = ROOM_X[1]
    f, depth = 0.022, 0.024
    parts = [
        _box('Print frame top', (face - depth, b0, z1 - f), (face, b1, z1), frame_paint, 0.0015),
        _box('Print frame bottom', (face - depth, b0, z0), (face, b1, z0 + f), frame_paint, 0.0015),
        _box('Print frame side', (face - depth, b0, z0 + f), (face, b0 + f, z1 - f), frame_paint, 0.0015),
        _box('Print frame side', (face - depth, b1 - f, z0 + f), (face, b1, z1 - f), frame_paint, 0.0015),
    ]
    mat = _material('Abstract print paper', (0.80, 0.78, 0.72), 0.8)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    sep = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Object'], sep.inputs['Vector'])
    # Paper coordinates in metres: across (from the frame's -y edge) and up.
    across = nodes.new('ShaderNodeMath')
    across.operation = 'SUBTRACT'
    links.new(sep.outputs['Y'], across.inputs[0])
    across.inputs[1].default_value = b0
    up = nodes.new('ShaderNodeMath')
    up.operation = 'SUBTRACT'
    links.new(sep.outputs['Z'], up.inputs[0])
    up.inputs[1].default_value = z0
    point = nodes.new('ShaderNodeCombineXYZ')
    links.new(across.outputs[0], point.inputs['X'])
    links.new(up.outputs[0], point.inputs['Y'])

    def disc(cx, cy, r, half=None):
        d = nodes.new('ShaderNodeVectorMath')
        d.operation = 'DISTANCE'
        links.new(point.outputs['Vector'], d.inputs[0])
        d.inputs[1].default_value = (cx, cy, 0.0)
        m = nodes.new('ShaderNodeMath')
        m.operation = 'LESS_THAN'
        links.new(d.outputs['Value'], m.inputs[0])
        m.inputs[1].default_value = r
        if half is None:
            return m.outputs[0]
        above = nodes.new('ShaderNodeMath')
        above.operation = 'GREATER_THAN'
        links.new(up.outputs[0], above.inputs[0])
        above.inputs[1].default_value = cy
        both = nodes.new('ShaderNodeMath')
        both.operation = 'MULTIPLY'
        links.new(m.outputs[0], both.inputs[0])
        links.new(above.outputs[0], both.inputs[1])
        return both.outputs[0]

    def rect(xa, xb, ya, yb):
        out = None
        for value, lo_, hi_ in ((across.outputs[0], xa, xb), (up.outputs[0], ya, yb)):
            for op, edge in (('GREATER_THAN', lo_), ('LESS_THAN', hi_)):
                m = nodes.new('ShaderNodeMath')
                m.operation = op
                links.new(value, m.inputs[0])
                m.inputs[1].default_value = edge
                if out is None:
                    out = m.outputs[0]
                else:
                    both = nodes.new('ShaderNodeMath')
                    both.operation = 'MULTIPLY'
                    links.new(out, both.inputs[0])
                    links.new(m.outputs[0], both.inputs[1])
                    out = both.outputs[0]
        return out

    w, h = b1 - b0, z1 - z0
    colour = bsdf.inputs['Base Color'].default_value[:]
    result = None
    layers = [(rect(0.12 * w, 0.88 * w, 0.14 * h, 0.34 * h), (0.16, 0.20, 0.14)),
              (disc(0.42 * w, 0.58 * h, 0.21 * w), (0.50, 0.17, 0.08)),
              (disc(0.63 * w, 0.34 * h, 0.17 * w, half=True), (0.68, 0.43, 0.12))]
    for mask, rgb in layers:
        mix = nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        links.new(mask, mix.inputs['Factor'])
        if result is None:
            mix.inputs[6].default_value = colour
        else:
            links.new(result, mix.inputs[6])
        mix.inputs[7].default_value = (*rgb, 1.0)
        result = mix.outputs[2]
    links.new(result, bsdf.inputs['Base Color'])
    _bump(mat, 600.0, 0.0002, 0.08)
    parts.append(_box('Print paper', (face - 0.012, b0 + f, z0 + f), (face - 0.010, b1 - f, z1 - f), mat))
    return parts


def _radiator(paint, valve_metal) -> list[bpy.types.Object]:
    """A double panel radiator: two fluted steel panels, a slotted top grille,
    side covers, a thermostatic valve and the two pipes down into the floor."""
    (y0, y1), (z0, z1) = RADIATOR['y'], RADIATOR['z']
    face = ROOM_X[1]
    front = _material('Radiator gloss white', (0.80, 0.80, 0.78), 0.28)
    nodes, links = front.node_tree.nodes, front.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    flutes = nodes.new('ShaderNodeTexWave')
    flutes.wave_type, flutes.bands_direction = 'BANDS', 'Y'
    # 50 mm flutes (Blender's bands repeat every 2*pi/20 texture units).
    flutes.inputs['Scale'].default_value = (2 * math.pi / 20.0) / 0.05
    links.new(coord.outputs['Object'], flutes.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.35
    bump.inputs['Distance'].default_value = 0.004
    links.new(flutes.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], nodes.get('Principled BSDF').inputs['Normal'])
    grille = _material('Radiator grille shadow', (0.05, 0.05, 0.05), 0.6)
    parts = [
        _box('Radiator front panel', (face - 0.105, y0, z0), (face - 0.083, y1, z1), front, 0.004),
        _box('Radiator rear panel', (face - 0.072, y0, z0), (face - 0.050, y1, z1), paint, 0.004),
        _box('Radiator grille', (face - 0.103, y0 + 0.01, z1 - 0.002), (face - 0.052, y1 - 0.01, z1 + 0.004), grille),
        _box('Radiator top cover', (face - 0.106, y0, z1 + 0.004), (face - 0.049, y1, z1 + 0.008), paint, 0.002),
        _box('Radiator side cover', (face - 0.106, y0 - 0.004, z0 + 0.02), (face - 0.049, y0, z1 + 0.008), paint, 0.001),
        _box('Radiator side cover', (face - 0.106, y1, z0 + 0.02), (face - 0.049, y1 + 0.004, z1 + 0.008), paint, 0.001),
    ]
    for z in (z0 + 0.08, z1 - 0.08):
        for y in (y0 + 0.12, y1 - 0.12):
            parts.append(_box('Radiator bracket', (face - 0.050, y - 0.015, z - 0.01), (face, y + 0.015, z + 0.01), paint))
    for y in (y0 + 0.035, y1 - 0.035):
        parts.append(_cylinder('Radiator pipe', (face - 0.06, y, 0.0), (face - 0.06, y, z0 + 0.01), 0.0075, valve_metal, 16))
        parts.append(_cylinder('Radiator pipe collar', (face - 0.06, y, 0.0), (face - 0.06, y, 0.006), 0.018, paint))
    parts.append(_cylinder('Radiator valve', (face - 0.06, y1 - 0.035, z0 - 0.07), (face - 0.06, y1 - 0.035, z0 - 0.02), 0.014, valve_metal))
    parts.append(_cylinder('Radiator valve head', (face - 0.06, y1 - 0.035, z0 - 0.065), (face - 0.13, y1 - 0.035, z0 - 0.065),
                           0.024, paint))
    return parts


def daylight(window_view: Path, sun_target) -> dict[str, Any]:
    """A sun lamp and a physical sky outside; no lamp inside the room."""
    el = math.radians(SUN_ELEVATION_DEG)
    heading = math.radians(SUN_HEADING_DEG)
    travel = Vector((math.cos(el) * math.cos(heading), math.cos(el) * math.sin(heading), -math.sin(el)))
    sun_data = bpy.data.lights.new('Afternoon sun', 'SUN')
    sun_data.energy = SUN_ENERGY
    sun_data.angle = math.radians(0.53)
    sun_data.color = (1.0, 0.93, 0.84)
    sun = bpy.data.objects.new('Afternoon sun', sun_data)
    bpy.context.collection.objects.link(sun)
    sun.location = Vector(sun_target) - 6.0 * travel
    sun.rotation_euler = travel.to_track_quat('-Z', 'Y').to_euler()

    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Afternoon sky')
    scene.world.use_nodes = True
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts the sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(-travel.x, -travel.y)
    sky.air_density, sky.dust_density = 1.0, 2.0
    lighting = nodes['Background']
    links.new(sky.outputs['Color'], lighting.inputs['Color'])
    lighting.inputs['Strength'].default_value = SKY_STRENGTH

    coord = nodes.new('ShaderNodeTexCoord')
    turn = nodes.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    towards_sun = -travel
    # Rotating the lookup vector by theta moves the photograph by -theta, so
    # the lamp's direction is sent to the photograph's own sun azimuth.
    turn.inputs['Rotation'].default_value = (
        0.0, 0.0, math.radians(WINDOW_VIEW_SUN_AZIMUTH_DEG) - math.atan2(towards_sun.y, towards_sun.x))
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(window_view), check_existing=True)
    links.new(coord.outputs['Generated'], turn.inputs['Vector'])
    links.new(turn.outputs['Vector'], photo.inputs['Vector'])
    view = nodes.new('ShaderNodeBackground')
    view.inputs['Strength'].default_value = WINDOW_VIEW_STRENGTH
    links.new(photo.outputs['Color'], view.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(lighting.outputs['Background'], mix.inputs[1])
    links.new(view.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['World Output'].inputs['Surface'])
    return {'sun_elevation_deg': SUN_ELEVATION_DEG, 'sun_heading_deg': SUN_HEADING_DEG,
            'sun_energy': SUN_ENERGY, 'window_view': window_view.name}


def _asset(asset_dir: Path, relative: str) -> Path:
    path = Path(asset_dir) / relative
    if not path.is_file():
        raise FileNotFoundError(f'{path} is missing; run scripts/download_assets.py --scene basketball_cup_collision')
    return path


def build_room(asset_dir: Path) -> dict[str, Any]:
    """Walls, floor, ceiling, window, daylight, desk, carton, coffee table and
    furniture. Returns what was built: ``decor`` lists the pieces the simulator
    does not know about, each with its world bounding box."""
    x0, x1 = ROOM_X
    y0, y1 = ROOM_Y
    t = WALL_THICK_M
    wall_paint = _emulsion('Warm white emulsion', (0.70, 0.67, 0.62))
    ceiling_paint = _emulsion('Ceiling white', (0.76, 0.75, 0.72), 0.92)
    skirting_paint = _bump(_material('Satin white skirting', (0.72, 0.71, 0.68), 0.38), 120.0, 0.0003, 0.1)
    frame_paint = _material('Anthracite powder coat', (0.035, 0.038, 0.042), 0.42)
    steel = _material('Black powder-coated steel', (0.02, 0.02, 0.021), 0.38)
    sill = _bump(_material('White quartz window board', (0.72, 0.71, 0.68), 0.22), 400.0, 0.0002, 0.08)

    floor = _box('Floor', (x0 - t / 2, y0 - t / 2, -0.08), (x1 + t / 2, y1 + t / 2, 0.0),
                 _scanned('Oak laminate', _asset(asset_dir, FLOOR_TEX[0]), FLOOR_TEX[1], rotate_deg=90.0,
                          roughness_min=0.25))
    ceiling = _box('Ceiling', (x0 - t / 2, y0 - t / 2, CEILING_Z), (x1 + t / 2, y1 + t / 2, CEILING_Z + 0.12), ceiling_paint)
    walls = _ring('Walls', (x0 - t, x1 + t, y0 - t, y1 + t), (x0, x1, y0, y1), -0.10, CEILING_Z + 0.10, wall_paint)
    window_parts = [_window(spec, walls, frame_paint, sill) for spec in WINDOWS]
    skirting = _ring('Skirting', (x0, x1, y0, y1),
                     (x0 + SKIRT_PROUD_M, x1 - SKIRT_PROUD_M, y0 + SKIRT_PROUD_M, y1 - SKIRT_PROUD_M),
                     0.0, SKIRT_HEIGHT_M, skirting_paint)
    mod = skirting.modifiers.new('Soft edges', 'BEVEL')
    mod.width, mod.segments = 0.002, 2
    skirting.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    # The ground outside stops sky light from below; the camera sees through it.
    ground = _box('Ground outside', (-100, -100, -0.75), (100, 100, -0.45), _material('Ground outside', (0.18, 0.17, 0.15), 0.9))
    ground.visible_camera = False

    desk = _desk(_scanned('Oak veneer desk top', _asset(asset_dir, DESK_TEX[0]), DESK_TEX[1], rotate_deg=90.0,
                          roughness_min=0.32), steel)
    carton = _carton(_kraft())
    rug = _box('Wool rug', (RUG['x'][0], RUG['y'][0], 0.0), (RUG['x'][1], RUG['y'][1], RUG['height_m']),
               _scanned('Wool boucle rug', _asset(asset_dir, RUG_TEX[0]), RUG_TEX[1], roughness_min=0.7), bevel=0.004)
    voile = _sheer(_asset(asset_dir, CURTAIN_TEX[0]), CURTAIN_TEX[1])
    curtains = [_curtains(spec, voile, steel) for spec in WINDOWS]
    art = _abstract_print(steel)
    radiator = _radiator(skirting_paint, _material('Chrome valve', (0.75, 0.75, 0.75), 0.18, metallic=1.0))
    # A plain double socket on the east wall just past the end of the desk.
    plate = _bump(_material('White socket plastic', (0.74, 0.73, 0.70), 0.3), 300.0, 0.0002, 0.05)
    fittings = [_box('Wall socket', (x1 - 0.009, 0.30, 0.86), (x1, 0.446, 0.946), plate, 0.002)]

    main = WINDOWS[0]
    light = daylight(_asset(asset_dir, WINDOW_VIEW), (x1, sum(main['span']) / 2, sum(main['z']) / 2))

    # Furniture on the floor, and the lamp on the desk top.
    pieces = []
    for spec in FURNITURE:
        spec = dict(spec)
        model, name = spec.pop('model'), spec.pop('name')
        if 'at' not in spec:
            spec['z'] = 0.0
        pieces.append(place_model(_asset(asset_dir, f'{model}/{model}_1k.gltf'), name, **spec))
    for model, name, x, y, z, yaw in SHELF_ITEMS:
        pieces.append(place_model(_asset(asset_dir, f'{model}/{model}_1k.gltf'), name, yaw_deg=yaw, x=x, y=y, z=z))
    lo, hi = prop_box('coffee_table')
    coffee = place_model(_asset(asset_dir, f"{COFFEE_TABLE['model']}/{COFFEE_TABLE['model']}_1k.gltf"),
                         COFFEE_TABLE['name'], yaw_deg=COFFEE_TABLE['yaw_deg'],
                         x_max=hi[0], y=(lo[1] + hi[1]) / 2, z=0.0)

    decor = list(pieces)
    decor.append(_piece('Wool rug', [rug]))
    for spec, parts in zip(WINDOWS, curtains):
        decor.append(_piece(f'Curtains and rod ({spec["wall"]})', parts))
    for spec, parts in zip(WINDOWS, window_parts):
        decor.append(_piece(f'Window board ({spec["wall"]})', [p for p in parts if ' board' in p.name]))
    decor.append(_piece('Framed print', art))
    decor.append(_piece('Radiator', radiator))
    decor += [_piece(o.name, [o]) for o in fittings]
    # The skirting is one ring; check it as its four straight runs.
    k, h = SKIRT_PROUD_M, SKIRT_HEIGHT_M
    for name, lo_, hi_ in (('Skirting west', (x0, y0, 0), (x0 + k, y1, h)), ('Skirting east', (x1 - k, y0, 0), (x1, y1, h)),
                           ('Skirting south', (x0, y0, 0), (x1, y0 + k, h)), ('Skirting north', (x0, y1 - k, 0), (x1, y1, h))):
        decor.append({'name': name, 'objects': [skirting.name], 'bbox_min': list(lo_), 'bbox_max': list(hi_)})
    # Surfaces with no collider behind them: the ceiling, the stretches of the
    # east wall beyond the simulator's back-wall box, and the part of the coffee
    # table that rises above its box.
    decor.append({'name': 'Ceiling', 'objects': [ceiling.name],
                  'bbox_min': [x0, y0, CEILING_Z], 'bbox_max': [x1, y1, CEILING_Z + 0.12]})
    decor.append({'name': 'East wall south of the solid wall', 'objects': [walls.name],
                  'bbox_min': [x1, y0, 0.0], 'bbox_max': [x1 + t, _BACK_LO[1], CEILING_Z]})
    decor.append({'name': 'East wall above the solid wall', 'objects': [walls.name],
                  'bbox_min': [x1, _BACK_LO[1], _BACK_HI[2]], 'bbox_max': [x1 + t, y1, CEILING_Z]})
    decor.append({'name': 'Coffee table above its box', 'objects': coffee['objects'],
                  'bbox_min': [coffee['bbox_min'][0], coffee['bbox_min'][1], hi[2]], 'bbox_max': coffee['bbox_max']})
    # What stands on the colliders the moving bodies touch.
    contact = {'desk': [o.name for o in desk], 'carton': [o.name for o in carton],
               'coffee_table': coffee['objects'], 'walls': [walls.name], 'floor': [floor.name]}
    print(f'[room] studio built: {len(pieces)} furniture pieces, {len(WINDOWS)} windows')
    return {'source': 'studio_room', 'room_x': list(ROOM_X), 'room_y': list(ROOM_Y), 'ceiling_z': CEILING_Z,
            'daylight': light, 'furniture': pieces + [coffee], 'decor': decor, 'contact_surfaces': contact}


# -------------------------------------------------------------------- checks


def _box_distance(points, lo, hi):
    """Distance from each point (N x 3 numpy array) to an axis box."""
    import numpy as np
    d = np.maximum(np.maximum(np.asarray(lo) - points, 0.0), points - np.asarray(hi))
    return np.sqrt((d * d).sum(axis=1))


def check_clearance(decor, frames, keys, hull_vertices, ball_radius, margin=0.02, substeps=4):
    """Smallest gap between a moving body and each decorative piece's box.

    The ball is its sphere; a cup is its collision hull's vertices. Poses are
    sampled at every frame and, linearly as Blender interpolates them, at
    ``substeps`` points in between, which covers what motion blur shows.
    """
    import numpy as np
    from mathutils import Quaternion
    hull = np.asarray(hull_vertices, dtype=float)
    samples = {k: [] for k in keys}
    for a, b in zip(frames, frames[1:] + frames[-1:]):
        for k in keys:
            if not a[k]['present']:
                continue
            pa, pb = Vector(a[k]['location']), Vector(b[k]['location'])
            qa = Quaternion((a[k]['quaternion_xyzw'][3], *a[k]['quaternion_xyzw'][:3]))
            qb = Quaternion((b[k]['quaternion_xyzw'][3], *b[k]['quaternion_xyzw'][:3]))
            for s in range(substeps if b is not a else 1):
                f = s / substeps
                samples[k].append((pa.lerp(pb, f), qa.slerp(qb, f)))
    gaps = {}
    for piece in decor:
        lo, hi = piece['bbox_min'], piece['bbox_max']
        gap = float('inf')
        for k, poses in samples.items():
            if not poses:
                continue
            if k == 'basketball':
                centres = np.array([list(p) for p, _q in poses])
                gap = min(gap, float(_box_distance(centres, lo, hi).min()) - ball_radius)
            else:
                for p, q in poses:
                    rot = np.array(q.to_matrix())
                    world = hull @ rot.T + np.array(list(p))
                    gap = min(gap, float(_box_distance(world, lo, hi).min()))
        gaps[piece['name']] = round(gap, 4)
    print('[room] clearance to decor: ' + ', '.join(f'{k} {v:.3f} m' for k, v in sorted(gaps.items(), key=lambda kv: kv[1])))
    close = [name for name, gap in gaps.items() if gap < margin]
    if close:
        raise ValueError(f'a moving body passes within {margin} m of {close}; move the piece')
    return gaps


def check_occlusion(scene, camera, decor, frames, objects, ball_radius):
    """Cast rays from the camera at each moving body in every frame.

    A ray that meets a decorative piece before the body means that piece hides
    it. Rays at the body's centre must never be blocked by decoration; rays at
    the rim are counted and reported.
    """
    decor_objects = {name for piece in decor for name in piece['objects']}
    for piece in decor:
        for name in list(piece['objects']):
            obj = bpy.data.objects.get(name)
            if obj is not None:
                decor_objects.update(child.name for child in obj.children_recursive)
    moving = {o.name for o in objects.values()}
    origin = camera.matrix_world.translation.copy()
    worst = {'centre': 0, 'rim': 0}
    blocked_by = {}
    for f in frames:
        scene.frame_set(f['frame_index'])
        depsgraph = bpy.context.evaluated_depsgraph_get()
        right = camera.matrix_world.to_3x3() @ Vector((1.0, 0.0, 0.0))
        up = camera.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0))
        for key, obj in objects.items():
            if not f[key]['present']:
                continue
            centre = Vector(f[key]['location'])
            reach = ball_radius * 0.8 if key == 'basketball' else 0.035
            targets = [('centre', centre)] + [('rim', centre + d * reach) for d in (right, -right, up, -up)]
            for kind, target in targets:
                direction = target - origin
                hit, loc, _n, _i, hit_obj, _m = scene.ray_cast(depsgraph, origin, direction.normalized(),
                                                              distance=direction.length + 0.2)
                # A rim ray that slips past a thin cup ends on whatever stands
                # behind it; only a hit in front of the target is an occluder.
                if not hit or hit_obj is None or (loc - origin).length > direction.length - 0.005:
                    continue
                name = hit_obj.original.name if hasattr(hit_obj, 'original') else hit_obj.name
                if name in moving:
                    continue
                if name in decor_objects:
                    worst[kind] += 1
                    blocked_by[name] = blocked_by.get(name, 0) + 1
                    if kind == 'centre':
                        raise ValueError(f'{name} hides the centre of {key} in frame {f["frame_index"]}')
    print(f'[room] occlusion by decor: centre rays {worst["centre"]}, rim rays {worst["rim"]} {blocked_by}')
    return {'centre_rays_blocked': worst['centre'], 'rim_rays_blocked': worst['rim'], 'blocked_by': blocked_by}
