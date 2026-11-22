"""A farmhouse boot room built on the solver's own planes.

This module builds the back hall of an old country house -- the boot room by
the back door -- lit by a clear autumn afternoon
through one window, and every surface the clock or the crate touches in the six
cases is placed from the boxes the solver collides
(``assets/scenes/wall_clock_drop/room_colliders.json``):

* the flagstone floor is the top of ``floor_sunken`` (z = 0), the strip along
  the south wall the crate stands on and both bodies fall onto;
* the pine-boarded floor of the hall is the top of ``floor_platform``
  (z = 0.05) and its pine nosing is the box's y = -1.12 face, the step the
  clock comes to rest against in the baseline;
* the deep painted skirting along the south wall is ``plinth_south``: its face
  is y = -2.500 and its top z = 0.1286 (the clock lands on it with gravity
  tripled, the crate is pushed back against it with the heavy clock);
* the plaster the clock hangs on is the y = -2.579 face of ``wall_south``.

The solver's other boxes (the north/west/east walls, a stack of boxes, a desk,
a chair and a pile of books) are never touched in any case;
the walls are drawn on their faces anyway and the rest has no counterpart.
Everything else here is decoration the solver does not know about:
``check_clearance`` refuses a take in which a moving body comes within 2 cm of a
decorative piece, and ``check_occlusion`` one in which a decorative piece hides
a moving body from the camera.
"""
from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

from room_colliders import load_colliders
from scene_geometry import CEILING_Z, CLOCK_RADIUS, CLOCK_THICKNESS, CRATE_HALF_EXTENTS


def _planes() -> dict[str, float]:
    """Faces of the solver's static boxes that the room is built on."""
    boxes = {b['name']: b for b in load_colliders()['boxes']}

    def lo(name, i):
        return boxes[name]['center'][i] - boxes[name]['half_extents'][i]

    def hi(name, i):
        return boxes[name]['center'][i] + boxes[name]['half_extents'][i]
    return dict(x0=hi('wall_west', 0), x1=lo('wall_east', 0), y0=hi('wall_south', 1), y1=lo('wall_north', 1),
                floor_z=hi('floor_sunken', 2), step_y=lo('floor_platform', 1), deck_z=hi('floor_platform', 2),
                plinth_y=hi('plinth_south', 1), plinth_z=hi('plinth_south', 2))


P = _planes()
ROOM_X = (P['x0'], P['x1'])
ROOM_Y = (P['y0'], P['y1'])
# Stone walls of an old house: deep reveals at the window and the door.
WALL_THICK_M = 0.38
# The lower wall is painted tongue-and-groove boarding finished flush with the
# plaster above it (its face is the wall plane the solver collides), under a
# moulded dado rail. The rail stands at 0.85 m: with gravity tripled the clock
# drops almost straight down the wall and passes 1 cm off it at 1.1 m, but it
# is 5 cm out by the time it reaches this height, so the 24 mm rail keeps the
# 2 cm clearance in every case. The skirting below is the plinth box.
CAP = dict(z=(0.850, 0.878), proud=0.024)
WINDOW_SILL_Z = 1.13

# The window in the south wall (east of the clock) that takes the sun, and the
# fill windows behind the camera: (wall, span along the wall, sill and head).
WINDOWS = [dict(wall='south', span=(1.20, 2.40), z=(WINDOW_SILL_Z, 2.26)),
           dict(wall='north', span=(-3.30, -2.20), z=(WINDOW_SILL_Z, 2.26)),
           dict(wall='north', span=(0.40, 1.50), z=(WINDOW_SILL_Z, 2.26)),
           dict(wall='west', span=(-0.55, 0.75), z=(WINDOW_SILL_Z, 2.26))]
# The back door in the east wall at the end of the flagstone strip.
DOOR = dict(span=(-2.32, -1.42), head=2.04)

# Clear autumn afternoon. HEADING is the direction the light travels across
# the floor, degrees from +y towards -x: through the south window it lays a
# patch over the step and the hall boards, east of where the clock lands, and
# never reaches the strip the bodies move in. The elevation is the sun's own in
# the window photograph.
SUN_ELEVATION_DEG = 41.8
SUN_HEADING_DEG = 35.0
SUN_ENERGY = 4.2
SKY_STRENGTH = 1.0
# Poly Haven alps_field (an alpine hay meadow under mountains): its sun stands
# at azimuth (0.5 - u) * 360 = -35.9 deg and elevation 41.8 deg in the
# photograph's own frame. It is shown to camera rays through the glass only and
# turned so that its sun stands where the lamp is; from the camera the window
# then looks across the meadow at the forest and the mountains beyond it, all
# hundreds of metres away, so nothing in the view reads as magnified.
WINDOW_VIEW = 'alps_field_2k.hdr'
WINDOW_VIEW_SUN_AZIMUTH_DEG = -35.9
WINDOW_VIEW_STRENGTH = 1.0
# AgX view: the room is lit by one sunny window and three in shadow.
LOOK = 'AgX - Base Contrast'
EXPOSURE = 2.2

# Scanned texture sets at their published size: (diffuse file, metres per tile).
SLATE_TEX = ('patterned_slate_tiles_diff_2k.jpg', 2.2)
# The hall floor is laid from separate wide pine boards (see _deck), each a
# random patch of a flat-sawn softwood scan (Poly Haven olive_veneer, the same
# timber as the crate, aged to amber), its 1 m tile stretched to 1.6 m along
# the grain.
PINE_FLOOR_TEX = ('olive_veneer_diff_2k.jpg', 1.0)
DECK = dict(width=(0.18, 0.26), length=(1.4, 3.2), gap=0.003, thick=0.022, seed=5)
OAK_TEX = ('walnut_veneer_02_diff_2k.jpg', 1.0)
BOARDING_TEX = ('white_planks_clean_diff_2k.jpg', 1.8)
PLASTER_TEX = ('plastered_wall_diff_2k.jpg', 2.0)
# Average linear colour of plastered_wall_diff_2k.jpg (its sand-grain blotches
# read like pebble-dash at this distance, so the plaster is pulled half way
# towards this flat colour).
PLASTER_MEAN = (0.436, 0.392, 0.335)
# Paint over the boarding, skirting, dado rail and peg rail: a muted farmhouse
# green (linear RGB), and the off-white of the window joinery.
PAINT_GREEN = (0.160, 0.200, 0.145)
PAINT_DOOR = (0.100, 0.130, 0.095)
PAINT_WINDOW = (0.70, 0.69, 0.64)

# Poly Haven CC0 pieces: model, anchor (bounding-box faces / centre, metres;
# ``z`` is the bottom, by default the floor under the piece), yaw, and an
# optional tilt about the model's own x axis. Models face -y as authored.
BENCH_SEAT_Z = 0.651     # painted_wooden_bench: top of the seat
BENCH_SHELF_Z = 0.207    # and of the boot shelf under it
FURNITURE = [
    # A painted boot bench against the south wall at the near end, under the
    # pegs, a pair of clean wellingtons on its shelf and a canvas hat on its seat.
    dict(model='painted_wooden_bench', name='Boot bench', yaw_deg=180.0, x=-1.99, y_min=P['plinth_y'] + 0.004),
    dict(model='rubber_boots', name='Wellingtons on the shelf', yaw_deg=0.0, keep=('rubber_boots_l', 'rubber_boots_r'),
         x=-2.06, y=-2.25, z=BENCH_SHELF_Z),
    dict(model='fishermans_hat', name='Canvas hat', yaw_deg=25.0, x=-1.70, y=-2.23, z=BENCH_SEAT_Z),
    # Muddy wellingtons on the flags by the back door.
    dict(model='rubber_boots', name='Muddy wellingtons', yaw_deg=90.0, keep=('rubber_boots_dirt_r', 'rubber_boots_dirty_l'),
         x=3.12, y=-2.02),
    # A coopered bucket in the corner by the door and a yard broom leaning on
    # the wall between the window and the door. The broom is tipped 13 deg
    # about its head: its bristles stand on the flags (lowest corner 0.131 m
    # below the model's origin) and the top of its 1.331 m handle rests on the
    # plaster, which puts the origin at y = -2.579 + 0.014 + 1.331 sin 13 deg;
    # the handle passes the dado rail 12 cm clear.
    dict(model='wooden_bucket_01', name='Wooden bucket', yaw_deg=30.0, x=3.62, y_min=P['plinth_y'] + 0.01),
    dict(model='wooden_broom', name='Yard broom', yaw_deg=0.0, tilt_deg=13.0, at=(2.85, -2.2656, 0.131)),
    # A painted stool under the window.
    dict(model='painted_wooden_stool', name='Stool', yaw_deg=8.0, x=1.86, y_min=P['plinth_y'] + 0.03),
]
# The peg rail above the bench: (x span, z span of the rail) and the pegs' x.
PEG_RAIL = dict(x=(-2.64, -1.34), z=(1.565, 1.655), pegs=(-2.45, -2.13, -1.82, -1.52))
# A hurricane lantern hangs from one peg by its bail (the bail's top is the
# model's highest point, 0.294 m above its base).
LANTERN = dict(model='Lantern_01', name='Hurricane lantern', peg=-1.82, height=0.294)


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


def world_uv(obj: bpy.types.Object, offset=(0.0, 0.0)) -> bpy.types.Object:
    """UVs in metres from world coordinates, projected per face along its
    dominant normal axis: top faces get (x, y), faces across y get (x, z),
    faces across x get (y, z), shifted by ``offset``. The scanned materials
    scale them to their tile."""
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    layer = bm.loops.layers.uv.verify()
    mw = obj.matrix_world
    rot = mw.to_3x3()
    for face in bm.faces:
        n = rot @ face.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        for loop in face.loops:
            p = mw @ loop.vert.co
            u, v = (p.x, p.y) if axis == 2 else ((p.x, p.z) if axis == 1 else (p.y, p.z))
            loop[layer].uv = (u + offset[0], v + offset[1])
    bm.to_mesh(mesh)
    bm.free()
    return obj


def _box(name: str, lo, hi, material, bevel: float = 0.0, rotation: Matrix | None = None,
         uv: bool = True, uv_offset=(0.0, 0.0)) -> bpy.types.Object:
    """Axis box from its two corners, optionally turned about its own centre."""
    lo, hi = Vector(lo), Vector(hi)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=hi - lo, verts=bm.verts)
    turn = rotation.to_4x4() if rotation is not None else Matrix.Identity(4)
    bmesh.ops.transform(bm, matrix=Matrix.Translation((lo + hi) / 2) @ turn, verts=bm.verts)
    obj = _finish(bm, name, material)
    if uv:
        world_uv(obj, uv_offset)
    if bevel:
        mod = obj.modifiers.new('Soft edges', 'BEVEL')
        mod.width, mod.segments = bevel, 2
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
    return world_uv(_finish(bm, name, material))


def _cylinder(name: str, start, end, radius: float, material, segments: int = 24,
              radius_end: float | None = None) -> bpy.types.Object:
    start, end = Vector(start), Vector(end)
    axis = end - start
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius,
                          radius2=radius if radius_end is None else radius_end, depth=axis.length)
    rot = axis.normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((start + end) / 2) @ rot, verts=bm.verts)
    obj = world_uv(_finish(bm, name, material))
    for poly in obj.data.polygons:
        poly.use_smooth = abs(poly.normal.dot(axis.normalized())) < 0.5
    return obj


def _cut(target: bpy.types.Object, cutter: bpy.types.Object) -> None:
    mod = target.modifiers.new(f'cut {cutter.name}', 'BOOLEAN')
    mod.operation, mod.solver, mod.object = 'DIFFERENCE', 'EXACT', cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    world_uv(target)


def _wall_box(name: str, wall: str, s0, s1, d0, d1, z0, z1, material, bevel: float = 0.0):
    """A box given along a wall (s, world x or y), out of it from its plaster
    face (d, positive into the room) and in height (z)."""
    if wall == 'south':
        f = ROOM_Y[0]
        return _box(name, (s0, f + d0, z0), (s1, f + d1, z1), material, bevel)
    if wall == 'north':
        f = ROOM_Y[1]
        return _box(name, (s0, f - d1, z0), (s1, f - d0, z1), material, bevel)
    if wall == 'east':
        f = ROOM_X[1]
        return _box(name, (f - d1, s0, z0), (f - d0, s1, z1), material, bevel)
    if wall == 'west':
        f = ROOM_X[0]
        return _box(name, (f + d0, s0, z0), (f + d1, s1, z1), material, bevel)
    raise ValueError(wall)


def _wall_span(wall: str) -> tuple[float, float]:
    return ROOM_X if wall in ('south', 'north') else ROOM_Y


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
    bsdf = nodes.get('Principled BSDF')
    if bsdf.inputs['Normal'].is_linked:
        links.new(bsdf.inputs['Normal'].links[0].from_socket, bump.inputs['Normal'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def scanned(name: str, diffuse: Path, tile_m: float, *, rotate_deg: float = 0.0, roughness_min: float = 0.0,
            roughness_scale: float = 1.0, tint=None, desaturate: float = 0.0, normal_strength: float = 1.0,
            offset=(0.0, 0.0), flatten: float = 0.0, mean=None, stretch: float = 1.0,
            per_object: float = 0.0) -> bpy.types.Material:
    """A Poly Haven texture set (colour, roughness, OpenGL normal) at its real
    size on UVs given in metres. ``tint`` multiplies the colour (paint over a
    scanned surface keeps the scan's grain and wear, not its colour);
    ``flatten`` pulls the colour that far towards the scan's average colour
    ``mean`` (linear RGB, measured from the file) times the tint, for a scan
    whose blotches read too coarse at the size it is seen. ``stretch``
    lengthens the tile along u (the grain of a wood scan), and ``per_object``
    varies the brightness of each object by up to that fraction (boards cut
    from different trees)."""
    mat = _material(name, (0.4, 0.3, 0.2), 0.5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1.0 / (tile_m * stretch), 1.0 / tile_m, 1.0)
    mapping.inputs['Rotation'].default_value = (0.0, 0.0, math.radians(rotate_deg))
    mapping.inputs['Location'].default_value = (offset[0], offset[1], 0.0)
    links.new(coord.outputs['UV'], mapping.inputs['Vector'])

    def scan(kind: str, colour_data: bool):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(diffuse).replace('_diff_', f'_{kind}_'), check_existing=True)
        if not colour_data:
            node.image.colorspace_settings.name = 'Non-Color'
        node.extension = 'REPEAT'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    colour = scan('diff', True).outputs['Color']
    if desaturate:
        hsv = nodes.new('ShaderNodeHueSaturation')
        hsv.inputs['Saturation'].default_value = 1.0 - desaturate
        links.new(colour, hsv.inputs['Color'])
        colour = hsv.outputs['Color']
    if tint is not None:
        mix = nodes.new('ShaderNodeMix')
        mix.data_type, mix.blend_type = 'RGBA', 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        # ShaderNodeMix keeps float, vector and colour sockets side by side;
        # the colour A/B inputs are 6/7 and the colour result is output 2.
        links.new(colour, mix.inputs[6])
        mix.inputs[7].default_value = (*tint, 1.0)
        colour = mix.outputs[2]
    if per_object:
        info = nodes.new('ShaderNodeObjectInfo')
        spread = nodes.new('ShaderNodeMapRange')
        spread.inputs['To Min'].default_value = 1.0 - per_object
        spread.inputs['To Max'].default_value = 1.0 + per_object
        links.new(info.outputs['Random'], spread.inputs['Value'])
        vary = nodes.new('ShaderNodeHueSaturation')
        links.new(colour, vary.inputs['Color'])
        links.new(spread.outputs['Result'], vary.inputs['Value'])
        colour = vary.outputs['Color']
    if flatten:
        flat = nodes.new('ShaderNodeMix')
        flat.data_type = 'RGBA'
        flat.inputs['Factor'].default_value = flatten
        links.new(colour, flat.inputs[6])
        flat.inputs[7].default_value = (*(m * k for m, k in zip(mean, tint or (1.0, 1.0, 1.0))), 1.0)
        colour = flat.outputs[2]
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
    normal.inputs['Strength'].default_value = normal_strength
    links.new(scan('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def _paint(name: str, colour, roughness: float) -> bpy.types.Material:
    """Brushed eggshell paint on joinery: one colour with brush-mark relief."""
    mat = _material(name, colour, roughness)
    mat.node_tree.nodes.get('Principled BSDF').inputs['Specular IOR Level'].default_value = 0.45
    return _bump(mat, 90.0, 0.0004, 0.15)


def _thin_glass() -> bpy.types.Material:
    """Thin float glass: a 4 % Fresnel reflection over a see-through layer.

    Shaded as transparent so rays through it stay camera rays: the world shows
    the meadow photograph to the camera alone while the room is lit by the
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


# ----------------------------------------------------------------- furniture


def place_model(path: Path, name: str, *, yaw_deg: float = 0.0, tilt_deg: float = 0.0, scale: float = 1.0,
                keep=None, **anchor) -> dict[str, Any]:
    """Import a glTF model, scale it uniformly, tip it about x, turn it about z
    and set its bounding box on an anchor: ``x``/``y`` (centre),
    ``x_min``/``x_max``/``y_min``/``y_max`` (faces) and ``z`` (bottom, default
    the floor under it) -- or put the model's own origin at ``at``. ``keep``
    names the mesh objects to keep when a file carries several variants."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in before]
    if keep is not None:
        drop = [o for o in imported if o.type == 'MESH' and o.name not in keep]
        if len(drop) == len([o for o in imported if o.type == 'MESH']):
            raise RuntimeError(f'{path.name} has none of {keep}')
        for obj in drop:
            imported.remove(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
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
    # XYZ Euler: the tilt about the model's own x comes first, then the yaw.
    root.rotation_euler = (math.radians(tilt_deg), 0.0, math.radians(yaw_deg))
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
    else:
        cy = (lo.y + hi.y) / 2.0 + shift.y
        shift.z = (P['deck_z'] if cy > P['step_y'] else P['floor_z']) - lo.z
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


def _deck(material, span_x, span_y) -> list[bpy.types.Object]:
    """The boarded hall floor: wide pine boards in rows along x, butt joints
    staggered at random lengths, 3 mm gaps over a dark sub-floor. Every board's
    top face is the top of the solver's ``floor_platform`` box (z = 0.05)."""
    rng = random.Random(DECK['seed'])
    top, g, th = P['deck_z'], DECK['gap'], DECK['thick']
    boards = [_box('Sub-floor', (span_x[0], span_y[0], top - 0.12), (span_x[1], span_y[1], top - th),
                   _material('Sub-floor', (0.02, 0.016, 0.012), 0.9), uv=False)]
    y = span_y[0]
    while y < span_y[1] - 1e-6:
        w = min(rng.uniform(*DECK['width']), span_y[1] - y)
        x = span_x[0] - rng.uniform(0.0, DECK['length'][1])
        while x < span_x[1]:
            length = rng.uniform(*DECK['length'])
            a, b = max(x, span_x[0]), min(x + length, span_x[1])
            if b - a > 0.05:
                boards.append(_box('Pine board', (a + g / 2, y + g / 2, top - th), (b - g / 2, y + w - g / 2, top),
                                   material, 0.0015, uv_offset=(rng.uniform(0, 20), rng.uniform(0, 20))))
            x += length
        y += w
    return boards


def _window(spec, walls, frame_paint, board_material) -> list[bpy.types.Object]:
    """A hole through the wall, a two-light painted casement set in the middle
    of the deep reveal, thin glass, an oak window board and a sky portal."""
    wall, (a0, a1), (z0, z1) = spec['wall'], spec['span'], spec['z']
    t = WALL_THICK_M
    tag = f'Window ({wall} {a0:+.2f})'
    _cut(walls, _wall_box(f'{tag} hole', wall, a0, a1, -t - 0.05, 0.05, z0, z1, None, 0.0))
    # Frame depth inside the reveal, measured into the room from the plaster
    # face (negative: inside the wall).
    d0, d1 = -0.235, -0.165
    bar, mull, s = 0.06, 0.035, 0.05
    am = (a0 + a1) / 2
    parts = [
        _wall_box(f'{tag} frame head', wall, a0, a1, d0, d1, z1 - bar, z1, frame_paint, 0.002),
        _wall_box(f'{tag} frame sill', wall, a0, a1, d0 - 0.02, d1, z0, z0 + bar, frame_paint, 0.002),
        _wall_box(f'{tag} frame jamb', wall, a0, a0 + bar, d0, d1, z0 + bar, z1 - bar, frame_paint, 0.002),
        _wall_box(f'{tag} frame jamb', wall, a1 - bar, a1, d0, d1, z0 + bar, z1 - bar, frame_paint, 0.002),
        _wall_box(f'{tag} mullion', wall, am - mull, am + mull, d0, d1 + 0.008, z0 + bar, z1 - bar, frame_paint, 0.002),
    ]
    # Each light: a sash with one glazing bar across, so six panes in all.
    zb = z0 + bar + 0.55 * (z1 - z0 - 2 * bar)
    for b0, b1 in ((a0 + bar, am - mull), (am + mull, a1 - bar)):
        parts += [
            _wall_box(f'{tag} sash rail', wall, b0, b1, d1 - 0.045, d1 + 0.012, z1 - bar - s, z1 - bar, frame_paint, 0.0015),
            _wall_box(f'{tag} sash rail', wall, b0, b1, d1 - 0.045, d1 + 0.012, z0 + bar, z0 + bar + s * 1.3, frame_paint, 0.0015),
            _wall_box(f'{tag} sash stile', wall, b0, b0 + s, d1 - 0.045, d1 + 0.012, z0 + bar, z1 - bar, frame_paint, 0.0015),
            _wall_box(f'{tag} sash stile', wall, b1 - s, b1, d1 - 0.045, d1 + 0.012, z0 + bar, z1 - bar, frame_paint, 0.0015),
            _wall_box(f'{tag} glazing bar', wall, b0 + s, b1 - s, d1 - 0.035, d1 + 0.006, zb - 0.012, zb + 0.012, frame_paint, 0.001),
        ]
        pane = _wall_box(f'{tag} glass', wall, b0 + s - 0.01, b1 - s + 0.01, d1 - 0.024, d1 - 0.020,
                         z0 + bar + s - 0.01, z1 - bar - s + 0.01, _thin_glass())
        pane.visible_shadow = False
        parts.append(pane)
    # Interior window board across the reveal, a little proud of the plaster.
    parts.append(_wall_box(f'{tag} board', wall, a0 - 0.06, a1 + 0.06, d1, 0.045, z0 - 0.028, z0 + 0.004,
                           board_material, 0.003))
    # The sky portal sits just outside the reveal.
    data = bpy.data.lights.new(f'{tag} sky portal', 'AREA')
    data.shape, data.size, data.size_y = 'RECTANGLE', a1 - a0, z1 - z0
    data.cycles.is_portal = True
    portal = bpy.data.objects.new(f'{tag} sky portal', data)
    bpy.context.collection.objects.link(portal)
    out = t + 0.02
    zc = (z0 + z1) / 2
    if wall == 'south':
        portal.location, inward = (am, ROOM_Y[0] - out, zc), Vector((0.0, 1.0, 0.0))
    elif wall == 'north':
        portal.location, inward = (am, ROOM_Y[1] + out, zc), Vector((0.0, -1.0, 0.0))
    else:
        portal.location, inward = (ROOM_X[0] - out, am, zc), Vector((1.0, 0.0, 0.0))
    portal.rotation_euler = inward.to_track_quat('-Z', 'Y').to_euler()
    return parts


def _door(walls, boards, paint, iron, oak) -> list[bpy.types.Object]:
    """The back door: a ledged and braced boarded door hung in the east wall,
    its ledges and brace on the room side, an iron thumb latch, an oak
    threshold and a moulded architrave on the plaster."""
    (a0, a1), head = DOOR['span'], DOOR['head']
    t = WALL_THICK_M
    _cut(walls, _wall_box('Door hole', 'east', a0, a1, -t - 0.05, 0.05, 0.0, head, None))
    face = ROOM_X[1]
    # Leaf set 6 cm into the reveal, 45 mm thick boards, 25 mm ledges on top.
    lx0, lx1 = face + 0.060, face + 0.105
    parts = [_box('Door leaf', (lx0, a0 + 0.004, 0.012), (lx1, a1 - 0.004, head - 0.006), boards, 0.0015)]
    ledge_x = (lx0 - 0.025, lx0)
    for zc in (0.22, 1.02, head - 0.24):
        parts.append(_box('Door ledge', (ledge_x[0], a0 + 0.05, zc - 0.075), (ledge_x[1], a1 - 0.05, zc + 0.075),
                          paint, 0.003))
    # Two braces rising towards the hanging (south) side.
    for z_lo, z_hi in ((0.22 + 0.075, 1.02 - 0.075), (1.02 + 0.075, head - 0.24 - 0.075)):
        span_y = (a1 - 0.10) - (a0 + 0.10)
        rise = z_hi - z_lo
        length = math.hypot(span_y, rise)
        angle = math.atan2(rise, -span_y)
        rot = Matrix.Rotation(angle, 3, 'X')
        yc, zc = (a0 + a1) / 2, (z_lo + z_hi) / 2
        parts.append(_box('Door brace', (ledge_x[0], yc - length / 2, zc - 0.06), (ledge_x[1], yc + length / 2, zc + 0.06),
                          paint, 0.003, rotation=rot))
    # Thumb latch on the opening (north) side.
    parts += [_box('Door latch bar', (ledge_x[0] - 0.012, a1 - 0.30, 1.005), (ledge_x[0], a1 - 0.08, 1.020), iron, 0.001),
              _box('Door latch keep', (ledge_x[0] - 0.030, a1 - 0.075, 0.990), (ledge_x[0] - 0.006, a1 - 0.045, 1.035),
                   iron, 0.001),
              _cylinder('Door handle', (ledge_x[0], a1 - 0.20, 0.90), (ledge_x[0] - 0.055, a1 - 0.20, 0.90), 0.009, iron, 12),
              _box('Door threshold', (face - 0.02, a0, 0.0), (face + 0.20, a1, 0.022), oak, 0.004)]
    # Architrave on the wall face around the opening.
    w, d = 0.075, 0.022
    parts += [_box('Architrave', (face - d, a0 - w, 0.0), (face, a0, head + w), paint, 0.002),
              _box('Architrave', (face - d, a1, 0.0), (face, a1 + w, head + w), paint, 0.002),
              _box('Architrave', (face - d, a0 - w, head), (face, a1 + w, head + w), paint, 0.002)]
    return parts


def _boarding(board_mat, paint) -> list[bpy.types.Object]:
    """The lower walls: boarding, dado rail and the deep skirting.

    The boarded lower wall is solid, its face in the plane of the plaster above
    it (on the south wall: y = -2.579, the solver's wall face). On the south
    wall the skirting is exactly the solver's plinth box (face y = -2.500, top
    z = 0.1286); on the other walls it is the same profile as decoration. The
    back door interrupts the east wall."""
    y0, y1 = ROOM_Y
    t = WALL_THICK_M
    sk_d = P['plinth_y'] - y0
    sk_z = P['plinth_z']
    cz, cd = CAP['z'], CAP['proud']
    (d0, d1) = DOOR['span']
    parts = []

    def runs(wall, margin):
        if wall != 'east':
            s0, s1 = _wall_span(wall)
            return [(s0 - t, s1 + t)] if margin == 0.0 else [(s0, s1)]
        return [(y0 - t, d0 - margin), (d1 + margin, y1 + t)] if margin == 0.0 else [(y0, d0 - margin), (d1 + margin, y1)]
    for wall in ('south', 'north', 'east', 'west'):
        for s0, s1 in runs(wall, 0.0):
            parts.append(_wall_box(f'Boarded wall ({wall})', wall, s0, s1, -t, 0.0, P['floor_z'] - 0.10, cz[0],
                                   board_mat, 0.0))
        for s0, s1 in runs(wall, 0.075):
            parts.append(_wall_box(f'Skirting ({wall})', wall, s0, s1, 0.0, sk_d, P['floor_z'], sk_z, paint, 0.0))
            parts.append(_wall_box(f'Dado rail ({wall})', wall, s0, s1, 0.0, cd, cz[0], cz[1], paint, 0.004))
    # The south skirting and boarding must stand exactly on the solver's faces.
    for prefix, axis, value in (('Skirting (south', 'y', P['plinth_y']), ('Skirting (south', 'z', sk_z),
                                ('Boarded wall (south', 'y', y0)):
        part = next(p for p in parts if p.name.startswith(prefix))
        top = max(getattr(part.matrix_world @ Vector(c), axis) for c in part.bound_box)
        if abs(top - value) > 1e-6:
            raise RuntimeError(f'{prefix}) is off the solver face {axis} = {value}')
    return parts


def _peg_rail(paint, pine) -> list[bpy.types.Object]:
    """A Shaker peg rail on the plaster above the settle."""
    (r0, r1), (z0, z1) = PEG_RAIL['x'], PEG_RAIL['z']
    y = ROOM_Y[0]
    parts = [_box('Peg rail', (r0, y, z0), (r1, y + 0.022, z1), paint, 0.004)]
    zc = (z0 + z1) / 2
    for px in PEG_RAIL['pegs']:
        parts.append(_cylinder('Peg', (px, y + 0.022, zc), (px, y + 0.098, zc + 0.006), 0.011, pine, 16, 0.009))
        parts.append(_cylinder('Peg head', (px, y + 0.090, zc + 0.006), (px, y + 0.104, zc + 0.007), 0.017, pine, 20))
    return parts


def daylight(window_view: Path, sun_target) -> dict[str, Any]:
    """A sun lamp and a physical sky outside; no lamp inside the room."""
    el = math.radians(SUN_ELEVATION_DEG)
    heading = math.radians(SUN_HEADING_DEG)
    travel = Vector((-math.sin(heading) * math.cos(el), math.cos(heading) * math.cos(el), -math.sin(el)))
    sun_data = bpy.data.lights.new('Afternoon sun', 'SUN')
    sun_data.energy = SUN_ENERGY
    sun_data.angle = math.radians(0.53)
    sun_data.color = (1.0, 0.95, 0.88)
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
    sky.air_density, sky.dust_density = 1.0, 1.5
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
        raise FileNotFoundError(f'{path} is missing; run scripts/download_assets.py --scene wall_clock_drop')
    return path


def build_room(asset_dir: Path) -> dict[str, Any]:
    """Floors, walls, boarding, window, door, daylight and furniture. Returns
    what was built: ``decor`` lists the pieces the solver does not know about,
    each with its world bounding box."""
    x0, x1 = ROOM_X
    y0, y1 = ROOM_Y
    t = WALL_THICK_M
    plaster = scanned('Limewashed plaster', _asset(asset_dir, PLASTER_TEX[0]), PLASTER_TEX[1],
                      tint=(1.62, 1.60, 1.56), roughness_min=0.7, normal_strength=0.45,
                      flatten=0.55, mean=PLASTER_MEAN)
    boarding = scanned('Painted boarding', _asset(asset_dir, BOARDING_TEX[0]), BOARDING_TEX[1],
                       tint=tuple(c / 0.40 for c in PAINT_GREEN), desaturate=1.0, roughness_min=0.42,
                       roughness_scale=0.75)
    door_boards = scanned('Painted door boards', _asset(asset_dir, BOARDING_TEX[0]), BOARDING_TEX[1],
                          tint=tuple(c / 0.40 for c in PAINT_DOOR), desaturate=1.0, roughness_min=0.42,
                          roughness_scale=0.75, offset=(0.37, 0.0))
    green = _paint('Farmhouse green eggshell', PAINT_GREEN, 0.48)
    door_paint = _paint('Back door green eggshell', PAINT_DOOR, 0.48)
    window_paint = _paint('Off-white window paint', PAINT_WINDOW, 0.40)
    iron = _bump(_material('Black iron', (0.025, 0.024, 0.023), 0.55, metallic=0.6), 400.0, 0.0003, 0.2)
    pine_deck = scanned('Pine floorboards', _asset(asset_dir, PINE_FLOOR_TEX[0]), PINE_FLOOR_TEX[1],
                        roughness_min=0.45, tint=(0.42, 0.29, 0.17), desaturate=0.1, stretch=1.6, per_object=0.22)
    slate = scanned('Slate flags', _asset(asset_dir, SLATE_TEX[0]), SLATE_TEX[1], roughness_min=0.45,
                    tint=(2.0, 2.0, 2.0))
    # Oiled oak for the window boards, the door threshold and the pegs (the
    # walnut scan of the clock case, lightened).
    oak = scanned('Oiled oak', _asset(asset_dir, OAK_TEX[0]), OAK_TEX[1], roughness_min=0.35,
                  tint=(1.30, 1.22, 1.10), offset=(0.53, 0.11))
    nosing_wood = scanned('Pine nosing', _asset(asset_dir, PINE_FLOOR_TEX[0]), PINE_FLOOR_TEX[1],
                  roughness_min=0.45, tint=(0.36, 0.25, 0.15), desaturate=0.1, stretch=1.6, offset=(0.21, 0.37))

    # Floors: the flagstone strip along the south wall and the boarded hall,
    # its pine nosing being the solver's step face.
    flags = _box('Flagstone floor', (x0 - t, y0 - t, P['floor_z'] - 0.10), (x1 + t, P['step_y'], P['floor_z']), slate)
    deck = _deck(pine_deck, (x0 - t, x1 + t), (P['step_y'] + 0.045, y1 + t))
    nosing = _box('Pine nosing', (x0, P['step_y'], P['floor_z']), (x1, P['step_y'] + 0.045, P['deck_z']), nosing_wood, 0.0)
    ceiling = _box('Ceiling', (x0 - t, y0 - t, CEILING_Z), (x1 + t, y1 + t, CEILING_Z + 0.15),
                   _material('Ceiling limewash', (0.74, 0.72, 0.68), 0.92))
    # Plastered upper walls; the boarded lower walls are built by _boarding.
    walls = _ring('Walls', (x0 - t, x1 + t, y0 - t, y1 + t), (x0, x1, y0, y1), CAP['z'][0], CEILING_Z + 0.10, plaster)
    window_parts = [_window(spec, walls, window_paint, oak) for spec in WINDOWS]
    door = _door(walls, door_boards, door_paint, iron, oak)
    board_parts = _boarding(boarding, green)
    pegs = _peg_rail(green, oak)
    # The ground outside stops sky light from below; the camera sees through it.
    ground = _box('Ground outside', (-100, -100, -1.2), (100, 100, -0.9), _material('Ground outside', (0.16, 0.17, 0.12), 0.9))
    ground.visible_camera = False

    sun_window = WINDOWS[0]
    light = daylight(_asset(asset_dir, WINDOW_VIEW), (sum(sun_window['span']) / 2, y0, sum(sun_window['z']) / 2))

    pieces = []
    for spec in FURNITURE:
        spec = dict(spec)
        model, name = spec.pop('model'), spec.pop('name')
        pieces.append(place_model(_asset(asset_dir, f'{model}/{model}_1k.gltf'), name, **spec))
    # The lantern's bail rests on the top of its peg, 7 cm out from the wall.
    peg_top = sum(PEG_RAIL['z']) / 2 + 0.013
    pieces.append(place_model(_asset(asset_dir, f"{LANTERN['model']}/{LANTERN['model']}_1k.gltf"), LANTERN['name'],
                              x=LANTERN['peg'], y=y0 + 0.07, z=peg_top - LANTERN['height']))

    decor = list(pieces)
    for spec, parts in zip(WINDOWS, window_parts):
        decor.append(_piece(f'Window board ({spec["wall"]} {spec["span"][0]:+.2f})',
                            [p for p in parts if p.name.endswith(' board')]))
    decor.append(_piece('Back door and architrave', door))
    decor.append(_piece('Peg rail', pegs))
    for part in board_parts:
        # The boarded walls are the wall planes and the south skirting is the
        # plinth collider itself; neither is decoration.
        if part.name.startswith(('Skirting (south', 'Boarded wall')):
            continue
        decor.append(_piece(part.name, [part]))
    decor.append({'name': 'Ceiling', 'objects': [ceiling.name],
                  'bbox_min': [x0, y0, CEILING_Z], 'bbox_max': [x1, y1, CEILING_Z + 0.15]})
    contact = {'flagstone floor (floor_sunken)': [flags.name],
               'pine boards and nosing (floor_platform)': [o.name for o in deck] + [nosing.name],
               'south skirting (plinth_south)': [p.name for p in board_parts if p.name.startswith('Skirting (south')],
               'south wall: plaster and boarding (wall_south)': [walls.name] + [
                   p.name for p in board_parts if p.name.startswith('Boarded wall (south')]}
    print(f'[room] boot room built: {len(pieces)} furniture pieces, {len(WINDOWS)} windows')
    return {'source': 'boot_room', 'room_x': list(ROOM_X), 'room_y': list(ROOM_Y), 'ceiling_z': CEILING_Z,
            'daylight': light, 'furniture': pieces, 'decor': decor, 'contact_surfaces': contact}


# -------------------------------------------------------------------- checks


def _box_distance(points, lo, hi):
    """Distance from each point (N x 3 numpy array) to an axis box."""
    import numpy as np
    d = np.maximum(np.maximum(np.asarray(lo) - points, 0.0), points - np.asarray(hi))
    return np.sqrt((d * d).sum(axis=1))


def body_samples():
    """Points on the surfaces the solver collides, in each body's own frame:
    the clock's case disc (radius, thickness) and the crate's box."""
    import numpy as np
    r, h = CLOCK_RADIUS, CLOCK_THICKNESS / 2
    ring = np.linspace(0.0, 2 * math.pi, 72, endpoint=False)
    clock = [(0.0, 0.0, s * h) for s in (-1, 1)]
    for radius in (0.06, 0.12, 0.18, r):
        for s in (-1, 1):
            clock += [(radius * math.cos(a), radius * math.sin(a), s * h) for a in ring]
    clock += [(r * math.cos(a), r * math.sin(a), 0.0) for a in ring]
    hx, hy, hz = CRATE_HALF_EXTENTS
    crate = []
    step = 0.025
    for axis, half in ((0, hx), (1, hy), (2, hz)):
        others = [i for i in range(3) if i != axis]
        spans = [np.linspace(-CRATE_HALF_EXTENTS[i], CRATE_HALF_EXTENTS[i],
                             max(2, int(round(2 * CRATE_HALF_EXTENTS[i] / step)) + 1)) for i in others]
        for a in spans[0]:
            for b in spans[1]:
                for s in (-1, 1):
                    p = [0.0, 0.0, 0.0]
                    p[axis], p[others[0]], p[others[1]] = s * half, a, b
                    crate.append(tuple(p))
    return {'clock': np.array(clock), 'crate': np.array(crate)}


def check_clearance(decor, frames, margin=0.02, substeps=4):
    """Smallest gap between a moving body and each decorative piece's box.

    Each body is a cloud of points on its collision shape; poses are sampled at
    every frame and, linearly as Blender interpolates them, at ``substeps``
    points in between, which covers what motion blur shows."""
    import numpy as np
    from mathutils import Quaternion
    shapes = body_samples()
    clouds = {k: [] for k in shapes}
    for a, b in zip(frames, frames[1:] + frames[-1:]):
        for k in shapes:
            if not a[k]['present']:
                continue
            pa, pb = Vector(a[k]['location']), Vector(b[k]['location'])
            qa = Quaternion((a[k]['quaternion_xyzw'][3], *a[k]['quaternion_xyzw'][:3]))
            qb = Quaternion((b[k]['quaternion_xyzw'][3], *b[k]['quaternion_xyzw'][:3]))
            for s in range(substeps if b is not a else 1):
                f = s / substeps
                p, q = pa.lerp(pb, f), qa.slerp(qb, f)
                clouds[k].append(shapes[k] @ np.array(q.to_matrix()).T + np.array(list(p)))
    clouds = {k: np.concatenate(v) for k, v in clouds.items() if v}
    gaps = {}
    for piece in decor:
        gaps[piece['name']] = round(min(float(_box_distance(c, piece['bbox_min'], piece['bbox_max']).min())
                                        for c in clouds.values()), 4)
    print('[room] clearance to decor: ' + ', '.join(f'{k} {v:.3f} m' for k, v in sorted(gaps.items(), key=lambda kv: kv[1])[:8]))
    close = [name for name, gap in gaps.items() if gap < margin]
    if close:
        raise ValueError(f'a moving body passes within {margin} m of {close}; move the piece')
    return gaps


def check_occlusion(scene, camera, decor, frames, objects):
    """Cast rays from the camera at each moving body in every frame.

    A ray that meets a decorative piece before the body means that piece hides
    it. Rays at the body's centre must never be blocked by decoration; rays at
    points on its rim are counted and reported."""
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
            reach = 0.15
            targets = [('centre', centre)] + [('rim', centre + d * reach) for d in (right, -right, up, -up)]
            for kind, target in targets:
                direction = target - origin
                hit, loc, _n, _i, hit_obj, _m = scene.ray_cast(depsgraph, origin, direction.normalized(),
                                                              distance=direction.length + 0.2)
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
