"""A child's playroom built around the simulator's floor plane, lit by the sun.

The physics has a single collider, the infinite plane z = 0, and the two cars
roll on it along +x. This module builds an ordinary room around that plane: a
scanned oak floor whose top face *is* z = 0, plaster walls on four straight
lines, skirting, a ceiling, two windows and Poly Haven CC0 furniture standing
against the walls. All light comes in through the windows: a sun lamp and a
physical sky outside, sampled through area-light portals. The west window is
outside the camera's view; what the camera sees of it is the patch of sunlight
it throws across the boards, crossed by the shadows of its glazing bars.

Nothing here is simulated, so ``check_clearance`` refuses a take in which a car
would come within 2 cm of a piece of furniture or a wall.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

# The skirting face is the room line; the plaster stands this far behind it.
SKIRT_THICK_M = 0.016
SKIRT_HEIGHT_M = 0.11
WALL_THICK_M = 0.20


# ------------------------------------------------------------------ geometry


def _finish(bm: bmesh.types.BMesh, name: str, material) -> bpy.types.Object:
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = False
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


def _box(name: str, centre, size, material, yaw: float = 0.0, bevel: float = 0.0) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(centre)) @ Matrix.Rotation(yaw, 4, 'Z'),
                        verts=bm.verts)
    obj = _finish(bm, name, material)
    if bevel:
        mod = obj.modifiers.new('Soft edges', 'BEVEL')
        mod.width, mod.segments = bevel, 2
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return obj


def _cut(target: bpy.types.Object, cutter: bpy.types.Object) -> None:
    mod = target.modifiers.new(f'cut {cutter.name}', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


# ----------------------------------------------------------------- materials


def _material(name: str, colour, roughness: float, bump: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*colour, 1.0)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*colour, 1.0)
    bsdf.inputs['Roughness'].default_value = roughness
    if bump:
        coord = nodes.new('ShaderNodeTexCoord')
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 170.0
        noise.inputs['Detail'].default_value = 2.0
        links.new(coord.outputs['Object'], noise.inputs['Vector'])
        node = nodes.new('ShaderNodeBump')
        node.inputs['Strength'].default_value = 0.22
        node.inputs['Distance'].default_value = bump
        links.new(noise.outputs['Fac'], node.inputs['Height'])
        links.new(node.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def _plaster(name: str, colour, roughness: float = 0.9) -> bpy.types.Material:
    """Rolled emulsion: one colour, drifting a few percent in tone and sheen
    over a metre, the way a painted wall does; a perfectly even albedo is what
    makes a CG wall read as a card."""
    mat = _material(name, colour, roughness, 0.0012)
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
    sheen.inputs['To Min'].default_value = roughness - 0.05
    sheen.inputs['To Max'].default_value = min(1.0, roughness + 0.05)
    links.new(drift.outputs['Fac'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    return mat


def _scanned_floor(diffuse: Path, tile_m: float, boards_along_x: bool, roughness_min: float) -> bpy.types.Material:
    """A Poly Haven texture set (colour, roughness, OpenGL normal) at its real size."""
    mat = _material('Scanned oak boards', (0.30, 0.20, 0.12), 0.5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1.0 / tile_m, 1.0 / tile_m, 1.0)
    if boards_along_x:
        # The scan's boards run along its v axis; a quarter turn lays them along x.
        mapping.inputs['Rotation'].default_value = (0.0, 0.0, math.pi / 2)
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])

    def scan(kind: str, colour_data: bool):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(diffuse).replace('_diff_', f'_{kind}_'), check_existing=True)
        if not colour_data:
            node.image.colorspace_settings.name = 'Non-Color'
        node.extension = 'REPEAT'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    links.new(scan('diff', True).outputs['Color'], bsdf.inputs['Base Color'])
    rough = scan('rough', False).outputs['Color']
    # A lacquered scan photographs close to a mirror; a floor children play on
    # is scuffed to a satin sheen.
    floor = nodes.new('ShaderNodeMath')
    floor.operation = 'MAXIMUM'
    floor.inputs[1].default_value = roughness_min
    links.new(rough, floor.inputs[0])
    links.new(floor.outputs['Value'], bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(scan('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def _thin_glass() -> bpy.types.Material:
    """Thin float glass: a 4 % Fresnel reflection over a see-through layer.

    Cycles' Fresnel node inverts the IOR on back faces, so a ray leaving the
    pane at a grazing angle would be totally reflected and the pane would go
    black; feeding 1/1.52 on back faces cancels that inversion.
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


# ------------------------------------------------------------------ daylight


def _aim(obj: bpy.types.Object, point) -> None:
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def daylight(spec: dict[str, Any], sun_target) -> dict[str, Any]:
    """A sun lamp and a physical sky outside; no lamp inside the room.

    ``sun_heading_deg`` is the direction the light travels across the floor,
    in degrees from +x towards +y.
    """
    el = math.radians(float(spec['sun_elevation_deg']))
    heading = math.radians(float(spec['sun_heading_deg']))
    travel = Vector((math.cos(el) * math.cos(heading), math.cos(el) * math.sin(heading), -math.sin(el)))
    sun_data = bpy.data.lights.new('Afternoon sun', 'SUN')
    sun_data.energy = float(spec['sun_energy'])
    sun_data.angle = math.radians(0.53)
    sun_data.color = tuple(spec.get('sun_color', (1.0, 0.93, 0.84)))
    sun = bpy.data.objects.new('Afternoon sun', sun_data)
    bpy.context.collection.objects.link(sun)
    sun.location = Vector(sun_target) - 6.0 * travel
    _aim(sun, sun.location + travel)

    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Afternoon sky')
    scene.world.use_nodes = True
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    # The lamp is the sun; the sky model's own disc would be a second one.
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts the sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(-travel.x, -travel.y)
    sky.air_density, sky.dust_density = 1.0, 2.0
    background = nodes['Background']
    links.new(sky.outputs['Color'], background.inputs['Color'])
    background.inputs['Strength'].default_value = float(spec['sky_strength'])
    return {'sun_elevation_deg': float(spec['sun_elevation_deg']),
            'sun_heading_deg': float(spec['sun_heading_deg']),
            'sun_energy': float(spec['sun_energy']), 'sky_strength': float(spec['sky_strength'])}


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


# ---------------------------------------------------------------------- room


def _wall_frames(room: dict[str, Any]) -> dict[str, tuple[float, Vector, Vector]]:
    """Plaster coordinate, along-wall direction and inward normal of each wall.

    A window's span is measured along its wall in world coordinates: y on the
    east and west walls, x on the north and south ones.
    """
    (x_lo, x_hi), (y_lo, y_hi) = room['x'], room['y']
    along_y, along_x = Vector((0.0, 1.0, 0.0)), Vector((1.0, 0.0, 0.0))
    return {
        'east': (float(x_hi) + SKIRT_THICK_M, along_y, Vector((-1.0, 0.0, 0.0))),
        'west': (float(x_lo) - SKIRT_THICK_M, along_y, Vector((1.0, 0.0, 0.0))),
        'north': (float(y_hi) + SKIRT_THICK_M, along_x, Vector((0.0, -1.0, 0.0))),
        'south': (float(y_lo) - SKIRT_THICK_M, along_x, Vector((0.0, 1.0, 0.0))),
    }


def _window(index: int, spec: dict[str, Any], frames, walls, sash_paint, trim) -> dict[str, Any]:
    """A hole through the full wall, a painted casement frame with a mullion
    and a transom in the middle of the reveal, glass in the sash plane, an
    interior window board and a sky portal."""
    face, along, inward = frames[spec['wall']]
    outward = -inward
    s0, s1 = (float(v) for v in spec['span'])
    z0, z1 = (float(v) for v in spec['z'])
    width, height = s1 - s0, z1 - z0
    sc, zc = (s0 + s1) / 2.0, (z0 + z1) / 2.0
    base = Vector((face, sc, zc)) if along.y else Vector((sc, face, zc))
    yaw = math.atan2(along.y, along.x)

    def at(depth: float, offset: float = 0.0, z: float = zc) -> Vector:
        return base + outward * depth + along * offset + Vector((0.0, 0.0, z - zc))

    name = f'Window {index + 1} ({spec["wall"]})'
    _cut(walls, _box(f'{name} hole', at(WALL_THICK_M / 2), (width, WALL_THICK_M + 0.2, height), None, yaw))
    bar, thick, middle = 0.058, 0.048, 0.095
    _box(f'{name} head', at(middle, 0.0, z1 - bar / 2), (width, thick, bar), sash_paint, yaw, 0.001)
    _box(f'{name} bottom rail', at(middle, 0.0, z0 + bar / 2), (width, thick, bar), sash_paint, yaw, 0.001)
    for sign in (-1, 1):
        _box(f'{name} jamb {sign:+d}', at(middle, sign * (width - bar) / 2), (bar, thick, height - 2 * bar),
             sash_paint, yaw, 0.001)
    # A transom at two thirds of the height and one central mullion below it:
    # the bars are what draw the window's shape into its patch of sunlight.
    transom_z = z0 + (height - 2 * bar) * 0.66 + bar
    _box(f'{name} transom', at(middle, 0.0, transom_z), (width - 2 * bar, thick - 0.006, 0.050), sash_paint, yaw, 0.001)
    _box(f'{name} mullion', at(middle, 0.0, (z0 + bar + transom_z - 0.025) / 2),
         (0.050, thick - 0.006, transom_z - 0.025 - z0 - bar), sash_paint, yaw, 0.001)
    pane = _box(f'{name} glass', at(middle), (width - 0.02, 0.006, height - 0.02), _thin_glass(), yaw)
    pane.visible_shadow = False
    _box(f'{name} board', at(0.012, 0.0, z0 - 0.013), (width + 0.10, 0.17, 0.026), trim, yaw, 0.001)
    _portal(f'{name} sky portal', at(WALL_THICK_M + 0.01), (width, height), inward)
    return {'wall': spec['wall'], 'span': [s0, s1], 'z': [z0, z1],
            'centre': [round(v, 4) for v in at(0.0)]}


def _socket(name: str, centre, wall: str, trim, dark) -> None:
    """A double power socket on the plaster, as every child's room has."""
    yaw = 0.0 if wall in ('north', 'south') else math.pi / 2
    inward = {'north': Vector((0, -1, 0)), 'south': Vector((0, 1, 0)),
              'east': Vector((-1, 0, 0)), 'west': Vector((1, 0, 0))}[wall]
    centre = Vector(centre)
    _box(f'{name} plate', centre + inward * 0.005, (0.146, 0.010, 0.086), trim, yaw, 0.002)
    along = Vector((1, 0, 0)) if wall in ('north', 'south') else Vector((0, 1, 0))
    for k, offset in enumerate((-0.036, 0.036)):
        for side in (-0.0095, 0.0095):
            _box(f'{name} pin {k}{side:+.3f}', centre + inward * 0.0102 + along * (offset + side) + Vector((0, 0, 0.003)),
                 (0.0035, 0.0012, 0.0075), dark, yaw)


def build_room(room: dict[str, Any], look: dict[str, Any], asset_dir: Path) -> dict[str, Any]:
    """Floor, walls, skirting, ceiling, windows, sockets, daylight and furniture.

    ``room`` gives the four room lines (the skirting faces) and the ceiling
    height; ``look`` holds colours, windows, daylight and the furniture list.
    The floor's top face is z = 0, the simulator's ground plane.
    """
    (x_lo, x_hi), (y_lo, y_hi) = room['x'], room['y']
    ceiling_z = float(room['ceiling_m'])
    grow = lambda d: _rectangle(x_lo - d, x_hi + d, y_lo - d, y_hi + d)

    wall_paint = _plaster('Duck-egg emulsion', tuple(look['wall_color']))
    ceiling_paint = _plaster('Ceiling white', (0.76, 0.75, 0.72), 0.93)
    trim = _material('Satin white joinery', (0.72, 0.71, 0.68), 0.38, 0.0003)
    sash_paint = _material('Eggshell window paint', (0.74, 0.73, 0.70), 0.5)
    dark = _material('Socket contacts', (0.02, 0.02, 0.02), 0.5)

    floor_spec = look['floor']
    _slab('Floor', grow(SKIRT_THICK_M + WALL_THICK_M / 2), -0.04, 0.0,
          _scanned_floor(asset_dir / floor_spec['diffuse'], float(floor_spec['tile_m']),
                         bool(floor_spec.get('boards_along_x', True)), float(floor_spec.get('roughness_min', 0.0))))
    _slab('Ceiling', grow(SKIRT_THICK_M + WALL_THICK_M / 2), ceiling_z, ceiling_z + 0.10, ceiling_paint)
    walls = _ring('Walls', grow(SKIRT_THICK_M + WALL_THICK_M), grow(SKIRT_THICK_M), -0.04, ceiling_z + 0.10, wall_paint)
    skirting = _ring('Skirting', grow(SKIRT_THICK_M + 0.004), grow(0.0), -0.002, SKIRT_HEIGHT_M, trim)
    mod = skirting.modifiers.new('Soft edges', 'BEVEL')
    mod.width, mod.segments = 0.0015, 2
    skirting.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')

    frames = _wall_frames(room)
    windows = [_window(i, w, frames, walls, sash_paint, trim) for i, w in enumerate(look['windows'])]
    for i, socket in enumerate(look.get('sockets') or []):
        face, along, inward = frames[socket['wall']]
        s, z = (float(v) for v in socket['at'])
        centre = Vector((face, s, z)) if along.y else Vector((s, face, z))
        _socket(f'Socket {i + 1}', centre, socket['wall'], trim, dark)

    # Ground outside: stops sky light from below the window sills.
    ground = _box('Ground outside', (0.0, 0.0, -0.45), (200.0, 200.0, 0.3),
                  _material('Ground outside', (0.16, 0.15, 0.12), 0.9))
    ground.visible_camera = False

    sun_window = next(w for w in windows if w['wall'] == look['daylight']['sun_window'])
    light_info = daylight(look['daylight'], Vector(sun_window['centre']))
    furniture = furnish(look.get('furniture') or [], asset_dir)
    print(f'[room] built: {len(windows)} windows, {len(furniture)} furniture pieces, ceiling at {ceiling_z:.2f} m',
          flush=True)
    return {'source': 'built', 'room_lines': {'x': [x_lo, x_hi], 'y': [y_lo, y_hi]}, 'floor': floor_spec['diffuse'],
            'ceiling_z': ceiling_z, 'windows': windows, 'daylight': light_info, 'furniture': furniture}


# ----------------------------------------------------------------- furniture


def place_model(path: Path, name: str, *, yaw_deg: float = 0.0, tilt_deg=(0.0, 0.0), **anchor: float) -> dict[str, Any]:
    """Import a glTF model, turn it and set its bounding box on an anchor.

    ``tilt_deg`` is a rotation about x then y applied before the yaw (a
    ukulele laid on its back). Anchor keys: ``x`` / ``y`` (box centre),
    ``x_min`` / ``x_max`` / ``y_min`` / ``y_max`` (box faces), ``z`` (bottom).
    """
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
    # XYZ order: the tilt about x and y is applied first, the yaw last.
    root.rotation_mode = 'XYZ'
    root.rotation_euler = (math.radians(tilt_deg[0]), math.radians(tilt_deg[1]), math.radians(yaw_deg))
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == 'MESH']
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
    shift.z = anchor.get('z', 0.0) - lo.z
    root.location = shift
    bpy.context.view_layer.update()
    lo, hi = lo + shift, hi + shift
    return {'model': path.name, 'yaw_deg': yaw_deg, 'tilt_deg': list(tilt_deg),
            'bbox_min': [round(v, 4) for v in lo], 'bbox_max': [round(v, 4) for v in hi]}


def furnish(items: list[dict[str, Any]], asset_dir: Path) -> list[dict[str, Any]]:
    """Place each Poly Haven model by its anchor; ``on`` stands it on an earlier piece."""
    placed: dict[str, dict[str, Any]] = {}
    for item in items:
        item = dict(item)
        model = item.pop('model')
        name = item.pop('name', model)
        yaw = float(item.pop('yaw_deg', 0.0))
        tilt = tuple(float(v) for v in item.pop('tilt_deg', (0.0, 0.0)))
        on = item.pop('on', None)
        item['z'] = placed[on]['bbox_max'][2] if on is not None else 0.0
        info = place_model(asset_dir / model / f'{model}_1k.gltf', name, yaw_deg=yaw, tilt_deg=tilt,
                           **{k: float(v) for k, v in item.items()})
        info['name'] = name
        info['asset'] = f'{model}/{model}_1k.gltf'
        placed[name] = info
    # Separate boxes cannot intersect; a piece standing on another only
    # touches it along a face, which is not an overlap.
    names = list(placed)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pa, pb = placed[a], placed[b]
            if all(pa['bbox_min'][k] < pb['bbox_max'][k] and pb['bbox_min'][k] < pa['bbox_max'][k] for k in range(3)):
                raise ValueError(f'{a} and {b} overlap; move one of them')
    return list(placed.values())


def check_clearance(room: dict[str, Any], furniture: list[dict[str, Any]], samples: list[tuple[Vector, float]],
                    margin: float = 0.02) -> dict[str, float]:
    """Smallest gap between any car's bounding sphere and each piece's box or wall.

    ``samples`` are (centre, radius) for every present car in every frame of
    the take; the walls are the four room lines (skirting faces).
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
            raise ValueError(f'a car passes within {gap:.3f} m of {name}; move it')
    print('[room] clearance: ' + ', '.join(f'{k} {v:.2f} m' for k, v in gaps.items()), flush=True)
    return {k: round(v, 4) for k, v in gaps.items()}
