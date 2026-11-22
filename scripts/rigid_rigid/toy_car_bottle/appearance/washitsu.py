"""A Japanese tatami room (washitsu) built around the simulator's floor plane.

The physics has a single collider besides the two bodies, the infinite plane
z = 0, and the toy car runs on it along +x near y = 0. This module builds an
ordinary eight-and-a-bit mat room around that plane: ten 0.9 m x 1.8 m tatami
whose top faces *are* z = 0, clay-plaster walls on four straight lines,
exposed hinoki posts, a run of paper shoji across the back wall and a glazed
garden door in the west wall. All light is daylight: a sun lamp and a
physical sky outside, sampled through an area-light portal across the garden
door, and the same sky glowing through the shoji paper. Nothing inside the
room emits light.

The whole room is built in the simulator's coordinates (the action frame);
``build_room`` finally moves it to the action origin with everything else.

Nothing here is simulated: ``check_clearance`` refuses a take in which a
moving body would come within 2 cm of a prop or a wall, and
``check_line_of_sight`` refuses one in which a prop would hide a moving body
from the camera.
"""
from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

MAT_UNIT_M = 0.9          # a mat is one unit wide and two units long
MAT_THICK_M = 0.055
WALL_THICK_M = 0.12
POST_M = 0.105            # 3.5 sun hinoki posts
OPENING_TOP_M = 1.80      # kamoi (head rail) height of shoji and doors


# ------------------------------------------------------------------ geometry


def _finish(bm: bmesh.types.BMesh, name: str, material) -> bpy.types.Object:
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _rectangle(x0: float, x1: float, y0: float, y1: float) -> list[Vector]:
    return [Vector((x0, y0)), Vector((x1, y0)), Vector((x1, y1)), Vector((x0, y1))]


def _slab(name: str, outline: list[Vector], z0: float, z1: float, material) -> bpy.types.Object:
    """A closed prism over a convex outline."""
    bm = bmesh.new()
    low = [bm.verts.new((p.x, p.y, z0)) for p in outline]
    high = [bm.verts.new((p.x, p.y, z1)) for p in outline]
    bm.faces.new(low)
    bm.faces.new(high)
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        bm.faces.new((low[i], low[j], high[j], high[i]))
    return _finish(bm, name, material)


def _ring(name: str, outer: list[Vector], inner: list[Vector], z0: float, z1: float, material) -> bpy.types.Object:
    """A closed band between two outlines with matching corners."""
    bm = bmesh.new()
    o0, o1, i0, i1 = [[bm.verts.new((p.x, p.y, z)) for p in outline]
                      for outline in (outer, inner) for z in (z0, z1)]
    for i in range(len(outer)):
        j = (i + 1) % len(outer)
        bm.faces.new((o0[i], o0[j], o1[j], o1[i]))
        bm.faces.new((i0[i], i1[i], i1[j], i0[j]))
        bm.faces.new((o0[i], i0[i], i0[j], o0[j]))
        bm.faces.new((o1[i], o1[j], i1[j], i1[i]))
    return _finish(bm, name, material)


def _box(name: str, lo, hi, material, bevel: float = 0.0) -> bpy.types.Object:
    """An axis-aligned box between two corners, optionally with softened edges.

    ``material`` may be a {'x', 'y', 'z'} set of wood materials: the box then
    takes the one whose grain runs along its longest side.
    """
    lo, hi = Vector(lo), Vector(hi)
    if isinstance(material, dict):
        size = hi - lo
        material = material['xyz'[max(range(3), key=lambda i: size[i])]]
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=hi - lo, verts=bm.verts)
    bmesh.ops.translate(bm, vec=(lo + hi) / 2.0, verts=bm.verts)
    obj = _finish(bm, name, material)
    if bevel:
        mod = obj.modifiers.new('Soft edges', 'BEVEL')
        mod.width, mod.segments = bevel, 2
    return obj


def _cut(target: bpy.types.Object, lo, hi) -> None:
    cutter = _box(f'{target.name} cutter', lo, hi, None)
    mod = target.modifiers.new(f'cut {cutter.name}', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


# ----------------------------------------------------------------- materials


def _image(nodes, path: Path, colour: bool):
    node = nodes.new('ShaderNodeTexImage')
    node.image = bpy.data.images.load(str(path), check_existing=True)
    if not colour:
        node.image.colorspace_settings.name = 'Non-Color'
    node.extension = 'REPEAT'
    return node


def _scanned(name: str, asset_dir: Path, stem: str, *, tile_m: float, projection: str = 'box',
             grain_axis: str = 'x', tint=None, value: float = 1.0, saturation: float = 1.0,
             roughness_min: float = 0.0, normal_strength: float = 1.0,
             per_object_jitter: float = 0.0) -> bpy.types.Material:
    """A Poly Haven texture set (colour, roughness, OpenGL normal) at its real size.

    ``projection`` 'uv' uses the mesh UVs (whose unit is one texture tile);
    'box' projects the scan onto every face in the object's own metres (for
    isotropic surfaces: plaster, cloth); 'grain' lays the scan's horizontal
    axis along ``grain_axis`` on every face, so a post, a rail or a table leg
    built as a plain box shows long grain down its length.
    ``per_object_jitter`` shifts value and saturation a little per object, so
    pieces cut from one scan do not read as copies.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    if projection == 'uv':
        vector = coord.outputs['UV']
    elif projection == 'grain':
        split = nodes.new('ShaderNodeSeparateXYZ')
        links.new(coord.outputs['Object'], split.inputs['Vector'])
        others = [a for a in 'xyz' if a != grain_axis]
        across = nodes.new('ShaderNodeMath')
        across.operation = 'ADD'
        links.new(split.outputs[others[0].upper()], across.inputs[0])
        links.new(split.outputs[others[1].upper()], across.inputs[1])
        join = nodes.new('ShaderNodeCombineXYZ')
        links.new(split.outputs[grain_axis.upper()], join.inputs['X'])
        links.new(across.outputs['Value'], join.inputs['Y'])
        scale = nodes.new('ShaderNodeVectorMath')
        scale.operation = 'SCALE'
        scale.inputs['Scale'].default_value = 1.0 / tile_m
        links.new(join.outputs['Vector'], scale.inputs[0])
        vector = scale.outputs['Vector']
    else:
        scale = nodes.new('ShaderNodeVectorMath')
        scale.operation = 'SCALE'
        scale.inputs['Scale'].default_value = 1.0 / tile_m
        links.new(coord.outputs['Object'], scale.inputs[0])
        vector = scale.outputs['Vector']

    def scan(kind: str, colour: bool):
        node = _image(nodes, asset_dir / f'{stem}_{kind}_2k.jpg', colour)
        if projection == 'box':
            node.projection = 'BOX'
            node.projection_blend = 0.2
        links.new(vector, node.inputs['Vector'])
        return node

    colour = scan('diff', True).outputs['Color']
    if tint is not None:
        mix = nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        mix.inputs[7].default_value = (*tint, 1.0)
        links.new(colour, mix.inputs[6])
        colour = mix.outputs[2]
    if value != 1.0 or saturation != 1.0 or per_object_jitter:
        hsv = nodes.new('ShaderNodeHueSaturation')
        hsv.inputs['Saturation'].default_value = saturation
        hsv.inputs['Value'].default_value = value
        if per_object_jitter:
            info = nodes.new('ShaderNodeObjectInfo')
            for socket, centre, spread in (('Value', value, per_object_jitter),
                                           ('Saturation', saturation, 1.5 * per_object_jitter)):
                remap = nodes.new('ShaderNodeMapRange')
                remap.inputs['To Min'].default_value = centre - spread
                remap.inputs['To Max'].default_value = centre + spread
                links.new(info.outputs['Random'], remap.inputs['Value'])
                links.new(remap.outputs['Result'], hsv.inputs[socket])
        links.new(colour, hsv.inputs['Color'])
        colour = hsv.outputs['Color']
    links.new(colour, bsdf.inputs['Base Color'])
    rough = scan('rough', False).outputs['Color']
    if roughness_min:
        clamp = nodes.new('ShaderNodeMath')
        clamp.operation = 'MAXIMUM'
        clamp.inputs[1].default_value = roughness_min
        links.new(rough, clamp.inputs[0])
        rough = clamp.outputs['Value']
    links.new(rough, bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = normal_strength
    links.new(scan('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def _plain(name: str, colour, roughness: float) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*colour, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*colour, 1.0)
    bsdf.inputs['Roughness'].default_value = roughness
    return mat


def _washi(name: str = 'Shoji washi') -> bpy.types.Material:
    """Mulberry paper: thin enough that the sky behind it shows as a soft glow.

    A little over a quarter of the light is scattered through the sheet (translucent),
    the rest reflected back (diffuse); a little fibre noise keeps the sheet
    from reading as a flat card.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    coord = nodes.new('ShaderNodeTexCoord')
    fibre = nodes.new('ShaderNodeTexNoise')
    fibre.inputs['Scale'].default_value = 90.0
    fibre.inputs['Detail'].default_value = 6.0
    links.new(coord.outputs['Object'], fibre.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].color = (0.74, 0.71, 0.64, 1.0)
    tone.color_ramp.elements[1].color = (0.86, 0.83, 0.76, 1.0)
    links.new(fibre.outputs['Fac'], tone.inputs['Fac'])
    through = nodes.new('ShaderNodeBsdfTranslucent')
    back = nodes.new('ShaderNodeBsdfDiffuse')
    links.new(tone.outputs['Color'], through.inputs['Color'])
    links.new(tone.outputs['Color'], back.inputs['Color'])
    mix = nodes.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = 0.28
    links.new(back.outputs['BSDF'], mix.inputs[1])
    links.new(through.outputs['BSDF'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


def thin_film_shader(mat: bpy.types.Material, ior: float, tint, roughness: float,
                     shadow_transmission: float = 1.0) -> bpy.types.Material:
    """Rebuild ``mat`` as a thin transparent wall: Fresnel reflection over a
    see-through layer, with no refraction (window glass, a PET bottle wall).

    Cycles' Fresnel node inverts the IOR on back faces, so a ray leaving the
    wall at a grazing angle would be totally reflected and the wall would go
    black; feeding 1/IOR on back faces cancels that inversion.

    ``shadow_transmission`` below 1 darkens what shadow rays see through the
    wall. A curved bottle bends the sunlight passing through it (caustics
    the renderer does not trace), so its shadow is a grey silhouette with a
    bright core rather than nearly nothing; without this the opaque cap's
    shadow lies on the floor detached, like a stain.
    """
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    output = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
    clear = nodes.new('ShaderNodeBsdfTransparent')
    clear.inputs['Color'].default_value = (*tint, 1.0)
    if shadow_transmission < 1.0:
        path = nodes.new('ShaderNodeLightPath')
        dim = nodes.new('ShaderNodeMix')
        dim.data_type = 'RGBA'
        links.new(path.outputs['Is Shadow Ray'], dim.inputs['Factor'])
        dim.inputs[6].default_value = (*tint, 1.0)
        dim.inputs[7].default_value = (*(c * shadow_transmission for c in tint), 1.0)
        links.new(dim.outputs[2], clear.inputs['Color'])
    reflection = nodes.new('ShaderNodeBsdfGlossy')
    reflection.inputs['Roughness'].default_value = roughness
    fresnel = nodes.new('ShaderNodeFresnel')
    geometry = nodes.new('ShaderNodeNewGeometry')
    flip = nodes.new('ShaderNodeMath')
    flip.operation = 'MULTIPLY_ADD'
    flip.inputs[1].default_value = 1.0 / ior - ior
    flip.inputs[2].default_value = ior
    links.new(geometry.outputs['Backfacing'], flip.inputs[0])
    links.new(flip.outputs['Value'], fresnel.inputs['IOR'])
    wall = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], wall.inputs['Fac'])
    links.new(clear.outputs['BSDF'], wall.inputs[1])
    links.new(reflection.outputs['BSDF'], wall.inputs[2])
    links.new(wall.outputs['Shader'], output.inputs['Surface'])
    return mat


# ------------------------------------------------------------------- tatami


def check_mat_layout(room: dict[str, Any], mats: list[tuple[int, int, int, int]]) -> None:
    """The mats must cover the floor exactly, and no four may meet at a point
    (the rule every tatami room is laid by)."""
    cols = round((room['x'][1] - room['x'][0]) / MAT_UNIT_M)
    rows = round((room['y'][1] - room['y'][0]) / MAT_UNIT_M)
    if abs(cols * MAT_UNIT_M - (room['x'][1] - room['x'][0])) > 1e-6 or \
            abs(rows * MAT_UNIT_M - (room['y'][1] - room['y'][0])) > 1e-6:
        raise ValueError('The room lines must be a whole number of mat units apart')
    owner: dict[tuple[int, int], int] = {}
    for index, (c0, r0, c1, r1) in enumerate(mats):
        if sorted((c1 - c0, r1 - r0)) != [1, 2]:
            raise ValueError(f'mat {index} is not one by two units')
        for c in range(c0, c1):
            for r in range(r0, r1):
                if (c, r) in owner:
                    raise ValueError(f'mats {owner[c, r]} and {index} overlap')
                owner[c, r] = index
    if len(owner) != cols * rows:
        raise ValueError('the mats leave part of the floor bare')
    for c in range(1, cols):
        for r in range(1, rows):
            if len({owner[c - 1, r - 1], owner[c, r - 1], owner[c - 1, r], owner[c, r]}) == 4:
                raise ValueError(f'four mats meet at grid point ({c}, {r})')


def _tatami_material(asset_dir: Path) -> bpy.types.Material:
    """Poly Haven's tatami scan: 1.8 m square, two mats side by side with
    their green heri. Each mat maps one half of it through its UVs, and the
    rush is aged a little differently on every mat."""
    return _scanned('Tatami (igusa rush)', asset_dir, 'tatami_mat', tile_m=1.8, projection='uv',
                    roughness_min=0.42, normal_strength=0.8, per_object_jitter=0.045)


def _wood_set(name: str, asset_dir: Path, stem: str, tile_m: float, **options) -> dict[str, bpy.types.Material]:
    """One scan as three materials whose grain runs along x, y and z."""
    return {axis: _scanned(f'{name} ({axis} grain)', asset_dir, stem, tile_m=tile_m, projection='grain',
                           grain_axis=axis, **options) for axis in 'xyz'}


def _tatami(name: str, x0: float, y0: float, x1: float, y1: float, material, rng: random.Random) -> bpy.types.Object:
    """One mat; its top face is z = 0. UV u runs along the mat (one texture
    width = 1.8 m), v across it over one half of the texture."""
    along_x = (x1 - x0) > (y1 - y0)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((x1 - x0, y1 - y0, MAT_THICK_M)), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(((x0 + x1) / 2, (y0 + y1) / 2, -MAT_THICK_M / 2)), verts=bm.verts)
    uv = bm.loops.layers.uv.new('UVMap')
    u0 = rng.random()
    half = rng.choice((0.0, 0.5))
    flip = rng.random() < 0.5
    for face in bm.faces:
        for loop in face.loops:
            co = loop.vert.co
            a, b = (co.x - x0, co.y - y0) if along_x else (co.y - y0, x1 - co.x)
            if flip:
                a, b = 2 * MAT_UNIT_M - a, MAT_UNIT_M - b
            loop[uv].uv = (u0 + a / (2 * MAT_UNIT_M), half + 0.5 * b / MAT_UNIT_M)
    obj = _finish(bm, name, material)
    # A mat's edges are rounded by its binding, so neighbours meet in a fine groove.
    mod = obj.modifiers.new('Bound edges', 'BEVEL')
    mod.width, mod.segments = 0.0035, 3
    return obj


# ------------------------------------------------------------------ daylight


def _aim(obj: bpy.types.Object, point) -> None:
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def daylight(spec: dict[str, Any], sun_target) -> dict[str, Any]:
    """A sun lamp and a physical sky outside; no lamp inside the room.

    ``sun_heading_deg`` is the direction the sunlight travels across the
    floor, in degrees from +x towards +y.
    """
    el = math.radians(float(spec['sun_elevation_deg']))
    heading = math.radians(float(spec['sun_heading_deg']))
    travel = Vector((math.cos(el) * math.cos(heading), math.cos(el) * math.sin(heading), -math.sin(el)))
    sun_data = bpy.data.lights.new('Sun', 'SUN')
    sun_data.energy = float(spec['sun_energy'])
    sun_data.angle = math.radians(0.53)
    sun_data.color = tuple(spec.get('sun_color', (1.0, 0.93, 0.84)))
    sun = bpy.data.objects.new('Sun', sun_data)
    bpy.context.collection.objects.link(sun)
    sun.location = Vector(sun_target) - 6.0 * travel
    _aim(sun, sun.location + travel)

    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Sky')
    scene.world.use_nodes = True
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    # The lamp is the sun; the sky model's own disc would be a second one.
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts the sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(-travel.x, -travel.y)
    sky.air_density, sky.dust_density = 1.0, float(spec.get('dust_density', 2.0))
    background = nodes['Background']
    links.new(sky.outputs['Color'], background.inputs['Color'])
    background.inputs['Strength'].default_value = float(spec['sky_strength'])
    return {key: float(spec[key]) for key in ('sun_elevation_deg', 'sun_heading_deg', 'sun_energy', 'sky_strength')}


def _portal(name: str, centre, size, inward) -> None:
    """An area-light portal across an opening, so Cycles samples the sky
    through it instead of waiting for a bounce to find it."""
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = size
    data.cycles.is_portal = True
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = centre
    _aim(obj, Vector(centre) + Vector(inward))


# ------------------------------------------------------------- shoji, doors


def _shoji_panel(name: str, x0: float, x1: float, y0: float, depth: float, height: float,
                 wood, board, paper, spec: dict[str, Any]) -> None:
    """A yoko-shige shoji on the back wall: hinoki frame and kick board, a
    lattice of thin kumiko, washi pasted on the garden side."""
    stile, top, bottom, kick = 0.030, 0.036, 0.055, float(spec.get('kick_board_m', 0.24))
    y1 = y0 + depth
    _box(f'{name} stile L', (x0, y0, 0.0), (x0 + stile, y1, height), wood, 0.0015)
    _box(f'{name} stile R', (x1 - stile, y0, 0.0), (x1, y1, height), wood, 0.0015)
    _box(f'{name} bottom rail', (x0 + stile, y0, 0.0), (x1 - stile, y1, bottom), wood, 0.0015)
    _box(f'{name} top rail', (x0 + stile, y0, height - top), (x1 - stile, y1, height), wood, 0.0015)
    _box(f'{name} kick board', (x0 + stile, y0 + 0.010, bottom), (x1 - stile, y0 + 0.019, bottom + kick), board)
    rail_z = bottom + kick
    _box(f'{name} middle rail', (x0 + stile, y0, rail_z), (x1 - stile, y1, rail_z + 0.026), wood, 0.001)
    bar, bar_depth = 0.008, 0.016
    inner0, inner1 = x0 + stile, x1 - stile
    lattice0, lattice1 = rail_z + 0.026, height - top
    for k in range(1, int(spec.get('vertical_bars', 3)) + 1):
        xc = inner0 + (inner1 - inner0) * k / (int(spec.get('vertical_bars', 3)) + 1)
        _box(f'{name} kumiko v{k}', (xc - bar / 2, y1 - bar_depth, lattice0), (xc + bar / 2, y1, lattice1), wood)
    rows = max(1, round((lattice1 - lattice0) / float(spec.get('bar_pitch_m', 0.135))))
    for k in range(1, rows):
        zc = lattice0 + (lattice1 - lattice0) * k / rows
        _box(f'{name} kumiko h{k}', (inner0, y1 - bar_depth, zc - bar / 2), (inner1, y1, zc + bar / 2), wood)
    sheet = _box(f'{name} washi', (inner0, y1, lattice0), (inner1, y1 + 0.0004, lattice1), paper)
    sheet.visible_shadow = True


def _glazed_door(name: str, wall_x: float, y0: float, y1: float, height: float, wood, glass) -> None:
    """Two hinoki-framed glass sliding panels in the west wall (outside the frame)."""
    width = (y1 - y0 + 0.04) / 2
    for k, (s0, x0) in enumerate(((y0, wall_x - 0.035), (y1 - width, wall_x - 0.075))):
        s1 = s0 + width
        x1 = x0 + 0.03
        _box(f'{name} {k} stile a', (x0, s0, 0.0), (x1, s0 + 0.045, height), wood)
        _box(f'{name} {k} stile b', (x0, s1 - 0.045, 0.0), (x1, s1, height), wood)
        _box(f'{name} {k} bottom', (x0, s0, 0.0), (x1, s1, 0.07), wood)
        _box(f'{name} {k} top', (x0, s0, height - 0.05), (x1, s1, height), wood)
        pane = _box(f'{name} {k} glass', (x0 + 0.012, s0 + 0.045, 0.07), (x0 + 0.017, s1 - 0.045, height - 0.05), glass)
        pane.visible_shadow = False


# ---------------------------------------------------------------- furniture


def _low_table(name: str, centre, size, height: float, material) -> dict[str, Any]:
    """A zataku: a thick lacquered top on four square legs with aprons."""
    cx, cy = centre
    sx, sy = size
    top_t, leg, apron = 0.035, 0.055, 0.05
    lo = (cx - sx / 2, cy - sy / 2)
    _box(f'{name} top', (lo[0], lo[1], height - top_t), (lo[0] + sx, lo[1] + sy, height), material, 0.004)
    inset = 0.06
    for dx in (inset, sx - inset - leg):
        for dy in (inset, sy - inset - leg):
            _box(f'{name} leg', (lo[0] + dx, lo[1] + dy, 0.0), (lo[0] + dx + leg, lo[1] + dy + leg, height - top_t),
                 material, 0.002)
    z1 = height - top_t
    for y in (lo[1] + inset + leg / 2 - 0.01, lo[1] + sy - inset - leg / 2 - 0.01):
        _box(f'{name} apron x', (lo[0] + inset + leg, y, z1 - apron), (lo[0] + sx - inset - leg, y + 0.02, z1), material)
    for x in (lo[0] + inset + leg / 2 - 0.01, lo[0] + sx - inset - leg / 2 - 0.01):
        _box(f'{name} apron y', (x, lo[1] + inset + leg, z1 - apron), (x + 0.02, lo[1] + sy - inset - leg, z1), material)
    return {'name': name, 'model': 'built low table', 'bbox_min': [lo[0], lo[1], 0.0],
            'bbox_max': [lo[0] + sx, lo[1] + sy, height]}


def _zabuton(name: str, centre, size, yaw_deg: float, material) -> dict[str, Any]:
    """A floor cushion: a square of cotton stuffed to about 7 cm, the seam
    running round its edge half-way up and its underside flattened on the mat."""
    a, b = size[0] / 2, size[1] / 2
    seam, n = 0.030, 32
    bm = bmesh.new()

    def bulge(u: float, v: float) -> float:
        return ((1 - abs(u) ** 8) * (1 - abs(v) ** 8)) ** 0.3

    grid_top, grid_bottom = {}, {}
    for i in range(n + 1):
        for j in range(n + 1):
            u, v = -1 + 2 * i / n, -1 + 2 * j / n
            g = bulge(u, v)
            # The seam pulls the cover in a little at the very edge; the
            # stuffing sags a little towards the middle of the top.
            pull = 1 - 0.03 * (1 - g)
            x, y = a * u * pull, b * v * pull
            # The seam line itself puckers a little; top and bottom covers
            # meet on it (g = 0 on the edge), so the cushion stays closed.
            edge = seam + 0.0025 * (1 - g) * math.sin(37.0 * (u + 0.6 * v))
            sag = 0.004 * (1 - (u * u + v * v) / 2) * g
            # The tufting thread in the middle pulls a small dimple into the top.
            dimple = 0.011 * math.exp(-(x * x + y * y) / 0.045 ** 2)
            # Hand-stuffed cotton is never quite even.
            lump = 0.003 * math.sin(3.1 * u + 0.7) * math.sin(2.3 * v + 1.9) * g
            grid_top[i, j] = bm.verts.new((x, y, edge + 0.034 * g - sag - dimple + lump))
            grid_bottom[i, j] = bm.verts.new((x, y, max(0.0, edge - 0.15 * g)))
    for i in range(n):
        for j in range(n):
            bm.faces.new((grid_top[i, j], grid_top[i + 1, j], grid_top[i + 1, j + 1], grid_top[i, j + 1]))
            bm.faces.new((grid_bottom[i, j], grid_bottom[i, j + 1], grid_bottom[i + 1, j + 1], grid_bottom[i + 1, j]))
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
    bmesh.ops.transform(bm, matrix=Matrix.Translation((centre[0], centre[1], 0.0)) @
                        Matrix.Rotation(math.radians(yaw_deg), 4, 'Z'), verts=bm.verts)
    obj = _finish(bm, name, material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    # The tuft: a short cross of thick thread in the dimple.
    top = max(v.co.z for v in obj.data.vertices if (v.co.xy - Vector(centre)).length < 0.01)
    yaw = math.radians(yaw_deg)
    for k, angle in enumerate((yaw + math.pi / 4, yaw - math.pi / 4)):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=Vector((0.026, 0.0045, 0.004)), verts=bm.verts)
        bmesh.ops.transform(bm, matrix=Matrix.Translation((centre[0], centre[1], top + 0.0015)) @
                            Matrix.Rotation(angle, 4, 'Z'), verts=bm.verts)
        thread = _finish(bm, f'{name} tuft {k + 1}', material)
        thread.parent = obj
        mod = thread.modifiers.new('Round', 'SUBSURF')
        mod.levels = mod.render_levels = 2
    points = [obj.matrix_world @ v.co for v in obj.data.vertices]
    lo = [min(p[k] for p in points) for k in range(3)]
    hi = [max(p[k] for p in points) for k in range(3)]
    return {'name': name, 'model': 'built zabuton', 'bbox_min': [round(v, 4) for v in lo],
            'bbox_max': [round(v, 4) for v in hi]}


def place_model(path: Path, name: str, *, yaw_deg: float = 0.0, **anchor: float) -> dict[str, Any]:
    """Import a Poly Haven glTF model, turn it about z and set its bounding
    box on an anchor: ``x`` / ``y`` (centre) or ``x_min`` / ``x_max`` /
    ``y_min`` / ``y_max`` (faces); its bottom stands on the mats (z = 0)."""
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
    root.rotation_euler = (0.0, 0.0, math.radians(yaw_deg))
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == 'MESH']
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    shift = Vector((0.0, 0.0, -lo.z))
    for axis, index in (('x', 0), ('y', 1)):
        if axis in anchor:
            shift[index] = anchor[axis] - (lo[index] + hi[index]) / 2.0
        elif f'{axis}_min' in anchor:
            shift[index] = anchor[f'{axis}_min'] - lo[index]
        elif f'{axis}_max' in anchor:
            shift[index] = anchor[f'{axis}_max'] - hi[index]
    root.location = shift
    bpy.context.view_layer.update()
    lo, hi = lo + shift, hi + shift
    return {'name': name, 'model': path.parent.name, 'asset': f'{path.parent.name}/{path.name}', 'yaw_deg': yaw_deg,
            'bbox_min': [round(v, 4) for v in lo], 'bbox_max': [round(v, 4) for v in hi]}


def furnish(items: list[dict[str, Any]], asset_dir: Path, materials: dict[str, Any]) -> list[dict[str, Any]]:
    """Build or import each piece; no two may overlap."""
    placed: dict[str, dict[str, Any]] = {}
    for item in items:
        item = dict(item)
        kind = item.pop('kind', 'model')
        name = item.pop('name')
        if kind == 'low_table':
            info = _low_table(name, item['centre'], item['size'], float(item['height_m']), materials['table'])
        elif kind == 'zabuton':
            info = _zabuton(name, item['centre'], item['size'], float(item.get('yaw_deg', 0.0)), materials['cushion'])
        else:
            model = item.pop('model')
            yaw = float(item.pop('yaw_deg', 0.0))
            info = place_model(asset_dir / model / f'{model}_1k.gltf', name, yaw_deg=yaw,
                               **{k: float(v) for k, v in item.items()})
        placed[name] = info
    names = list(placed)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pa, pb = placed[a], placed[b]
            if all(pa['bbox_min'][k] < pb['bbox_max'][k] and pb['bbox_min'][k] < pa['bbox_max'][k] for k in range(3)):
                raise ValueError(f'{a} and {b} overlap; move one of them')
    return list(placed.values())


# --------------------------------------------------------------------- room


def build_room(room: dict[str, Any], look: dict[str, Any], asset_dir: Path, origin: Vector) -> dict[str, Any]:
    """Tatami, walls, posts, shoji, the garden door, daylight and furniture.

    ``room`` gives the four room lines (the wall faces) and the ceiling
    height in the simulator's frame; ``look`` holds materials, openings,
    daylight and the furniture list. Everything is built in that frame and
    then moved by ``origin``, the action origin of the scenario.
    """
    before = set(bpy.data.objects)
    (x_lo, x_hi), (y_lo, y_hi) = room['x'], room['y']
    ceiling_z = float(room['ceiling_m'])
    grow = lambda d: _rectangle(x_lo - d, x_hi + d, y_lo - d, y_hi + d)

    tatami = _tatami_material(asset_dir)
    wall_spec = look['walls']
    plaster = _scanned('Juraku clay plaster', asset_dir, wall_spec['texture'], tile_m=float(wall_spec['tile_m']),
                       tint=tuple(wall_spec['tint']), value=float(wall_spec.get('value', 1.0)),
                       saturation=float(wall_spec.get('saturation', 1.0)),
                       normal_strength=float(wall_spec.get('normal_strength', 0.5)), roughness_min=0.8)
    hinoki = _wood_set('Hinoki', asset_dir, 'hinoki_planks', 1.89, roughness_min=0.45, per_object_jitter=0.03)
    hinoki_board = hinoki['x']
    ceiling_wood = _plain('Cedar ceiling', (0.33, 0.22, 0.14), 0.7)
    paper = _washi()
    glass = thin_film_shader(bpy.data.materials.new('Float glass'), 1.52, (1.0, 1.0, 1.0), 0.0)
    table_spec = look['table_material']
    materials = {
        'table': _wood_set('Lacquered keyaki', asset_dir, table_spec['texture'], float(table_spec['tile_m'])),
        # Scanned denim is a washed mid-blue; zabuton covers are dyed deeper.
        'cushion': _scanned('Indigo cotton', asset_dir, look['cushion_texture'], tile_m=0.27,
                            value=0.36, saturation=1.25, roughness_min=0.8, per_object_jitter=0.03),
    }

    # ---- floor: the mats, laid by the plan in ``look`` (grid units of 0.9 m)
    plan = [tuple(m) for m in look['tatami']]
    check_mat_layout(room, plan)
    rng = random.Random(int(look.get('seed', 11)))
    for k, (c0, r0, c1, r1) in enumerate(plan):
        _tatami(f'Tatami {k + 1}', x_lo + c0 * MAT_UNIT_M, y_lo + r0 * MAT_UNIT_M,
                x_lo + c1 * MAT_UNIT_M, y_lo + r1 * MAT_UNIT_M, tatami, rng)
    _slab('Subfloor', grow(WALL_THICK_M), -0.10, -MAT_THICK_M, _plain('Subfloor boards', (0.2, 0.15, 0.1), 0.8))

    # ---- walls, ceiling, posts
    walls = _ring('Walls', grow(WALL_THICK_M), grow(0.0), -0.10, ceiling_z + 0.10, plaster)
    _slab('Ceiling', grow(WALL_THICK_M), ceiling_z, ceiling_z + 0.08, ceiling_wood)
    half = POST_M / 2
    posts = []
    for k, (px, py) in enumerate(((x_lo, y_lo), (x_hi, y_lo), (x_lo, y_hi), (x_hi, y_hi))):
        lo, hi = (px - half, py - half, 0.0), (px + half, py + half, ceiling_z)
        _box(f'Post {k + 1}', lo, hi, hinoki, 0.002)
        posts.append({'name': f'Post {k + 1}', 'bbox_min': list(lo), 'bbox_max': list(hi)})

    # ---- the shoji across the back (north) wall
    shoji = look['shoji']
    s0, s1 = x_lo + half, x_hi - half
    _cut(walls, (s0, y_hi - 0.01, 0.0), (s1, y_hi + WALL_THICK_M + 0.01, OPENING_TOP_M))
    _box('Shoji sill', (s0, y_hi, -0.045), (s1, y_hi + WALL_THICK_M, 0.0), hinoki, 0.0)
    _box('Shoji head rail', (s0, y_hi, OPENING_TOP_M), (s1, y_hi + WALL_THICK_M, OPENING_TOP_M + 0.045), hinoki, 0.0)
    count, overlap = int(shoji['panels']), 0.03
    width = (s1 - s0 + (count - 1) * overlap) / count
    for k in range(count):
        p0 = s0 + k * (width - overlap)
        track = y_hi + (0.022 if k % 2 == 0 else 0.062)
        _shoji_panel(f'Shoji {k + 1}', p0, p0 + width, track, 0.03, OPENING_TOP_M - 0.004, hinoki, hinoki_board,
                     paper, shoji)

    # Behind the shoji: a veranda under deep eaves. The roof keeps the high
    # sky off the paper, so the shoji glow softly, brightest low down, as
    # they do in a real house, instead of as one white sheet.
    out0 = y_hi + WALL_THICK_M
    _box('Veranda boards', (x_lo - 1.0, out0, -0.08), (x_hi + 1.0, out0 + 1.1, -0.04), hinoki)
    _box('Eaves', (x_lo - 1.5, y_hi, ceiling_z + 0.08), (x_hi + 1.5, out0 + 1.5, ceiling_z + 0.20),
         _plain('Eaves soffit', (0.16, 0.11, 0.07), 0.8))

    # ---- the garden door in the west wall, outside the frame
    door = look['garden_door']
    d0, d1 = (float(v) for v in door['span'])
    _cut(walls, (x_lo - WALL_THICK_M - 0.01, d0, 0.0), (x_lo + 0.01, d1, OPENING_TOP_M))
    _box('Door sill', (x_lo - WALL_THICK_M, d0, -0.045), (x_lo, d1, 0.0), hinoki)
    _box('Door head rail', (x_lo - WALL_THICK_M, d0, OPENING_TOP_M), (x_lo, d1, OPENING_TOP_M + 0.045), hinoki)
    _glazed_door('Garden door', x_lo, d0, d1, OPENING_TOP_M, hinoki, glass)
    _portal('Garden door sky portal', (x_lo - WALL_THICK_M - 0.02, (d0 + d1) / 2, OPENING_TOP_M / 2),
            (d1 - d0, OPENING_TOP_M), (1.0, 0.0, 0.0))

    # Ground outside: stops sky light from below the openings.
    ground = _box('Ground outside', (-100.0, -100.0, -0.60), (100.0, 100.0, -0.30),
                  _plain('Garden ground', (0.12, 0.13, 0.09), 0.9))
    ground.visible_camera = False

    light_info = daylight(look['daylight'], Vector((x_lo, (d0 + d1) / 2, OPENING_TOP_M / 2)))
    furniture = furnish(look.get('furniture') or [], asset_dir, materials)

    # Move the whole room from the simulator's frame to the action origin.
    for obj in set(bpy.data.objects) - before:
        if obj.parent is None:
            obj.location = obj.location + origin
    bpy.context.view_layer.update()
    print(f'[washitsu] built: {len(plan)} mats, {len(furniture)} furniture pieces, ceiling {ceiling_z:.2f} m',
          flush=True)
    return {'source': 'built', 'room_lines': {'x': [x_lo, x_hi], 'y': [y_lo, y_hi]}, 'ceiling_z': ceiling_z,
            'tatami': [list(m) for m in plan], 'daylight': light_info, 'furniture': furniture, 'posts': posts,
            'objects': sorted(o.name for o in set(bpy.data.objects) - before)}


# ------------------------------------------------------------------- checks


def check_clearance(room: dict[str, Any], furniture: list[dict[str, Any]], samples: list[tuple[Vector, float]],
                    margin: float = 0.02) -> dict[str, float]:
    """Smallest gap between any moving body's bounding sphere and each
    piece's box (furniture and the corner posts) or a wall's plaster face,
    in the simulator's frame.

    ``samples`` are (centre, radius) for every present body in every frame
    of the take.
    """
    gaps = {}
    for piece in furniture:
        lo, hi = Vector(piece['bbox_min']), Vector(piece['bbox_max'])
        gaps[piece['name']] = min(
            math.sqrt(sum(max(lo[i] - c[i], 0.0, c[i] - hi[i]) ** 2 for i in range(3))) - radius
            for c, radius in samples)
    (x_lo, x_hi), (y_lo, y_hi) = room['x'], room['y']
    gaps['walls'] = min(min(c.x - x_lo, x_hi - c.x, c.y - y_lo, y_hi - c.y) - radius for c, radius in samples)
    for name, gap in gaps.items():
        if gap < margin:
            raise ValueError(f'a moving body passes within {gap:.3f} m of {name}; move it')
    print('[washitsu] clearance: ' + ', '.join(f'{k} {v:.2f} m' for k, v in gaps.items()), flush=True)
    return {k: round(v, 4) for k, v in gaps.items()}


def check_line_of_sight(camera_location: Vector, static_objects: list[bpy.types.Object],
                        bodies: list[tuple[str, Vector, Any, Vector]]) -> dict[str, int]:
    """Cast a ray from the camera to the centre and to points near the
    corners of every moving body; none may be stopped by the room or a prop
    (the bodies themselves are not in ``static_objects``).

    ``bodies`` are (name, world centre, rotation quaternion, half extents).
    Returns the number of rays cast per body name.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    trees = []
    for obj in static_objects:
        if obj.type != 'MESH':
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        matrix = obj.matrix_world
        verts = [matrix @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
        if polys:
            trees.append((obj.name, BVHTree.FromPolygons(verts, polys)))
        evaluated.to_mesh_clear()
    counts: dict[str, int] = {}
    for name, centre, rotation, half in bodies:
        offsets = [Vector((0.0, 0.0, 0.0))] + [Vector((sx * half.x, sy * half.y, sz * half.z)) * 0.7
                                                for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        blocked = []
        for k, offset in enumerate(offsets):
            target = centre + rotation @ offset
            direction = target - camera_location
            distance = direction.length
            direction.normalize()
            for tree_name, tree in trees:
                hit = tree.ray_cast(camera_location, direction, distance - 1e-3)
                if hit[0] is not None:
                    blocked.append((k, tree_name))
                    break
        if blocked:
            raise ValueError(f'{name} is partly hidden from the camera by {sorted({n for _, n in blocked})}')
        counts[name] = counts.get(name, 0) + len(offsets)
    return counts
