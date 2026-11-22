"""A plain metre-scale bedroom on the simulator's own wall planes.

This module builds an ordinary room: four straight walls whose skirting
faces are the planes in ``scenario['room']`` -- the same planes the simulator
collides with -- a scanned laminate floor, plaster walls and ceiling,
windows with daylight coming in through them, and Poly Haven CC0 furniture
standing against the walls.

Nothing here touches the bottles or the ball: ``check_clearance`` refuses a take
in which any of them would pass within 2 cm of a piece of furniture, since the
simulator knows nothing about the furniture.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

# The skirting face is the physics plane; the plaster stands this far behind it.
SKIRT_THICK_M = 0.018
SKIRT_HEIGHT_M = 0.12
WALL_THICK_M = 0.20
# Poly Haven symmetrical_garden_02: its sun stands at u = 0.6002, azimuth
# (0.5 - u) * 360 in the photograph's own frame.
WINDOW_VIEW_SUN_AZIMUTH_DEG = -36.1


# ------------------------------------------------------------------ geometry


def _wall_lines(room: dict[str, Any]):
    """The four wall lines as (name, inward normal, c) with n . p = c on the line."""
    (x_lo, x_hi), (y_lo, y_hi) = room['x'], room['y']
    return [
        ('west', Vector((1.0, 0.0)), float(x_lo)),
        ('north', Vector((0.0, -1.0)), -float(y_hi)),
        ('east', Vector((-1.0, 0.0)), -float(x_hi)),
        ('south', Vector((0.0, 1.0)), float(y_lo)),
    ]


def _polygon(lines, outward: dict[str, float]) -> list[Vector]:
    """Corners of the room outline with each wall line pushed outward."""
    shifted = [(n, c - float(outward.get(name, 0.0))) for name, n, c in lines]
    corners = []
    for index, (n1, c1) in enumerate(shifted):
        n2, c2 = shifted[(index + 1) % len(shifted)]
        det = n1.x * n2.y - n1.y * n2.x
        corners.append(Vector(((c1 * n2.y - c2 * n1.y) / det, (n1.x * c2 - n2.x * c1) / det)))
    return corners


def _link(name: str, mesh: bpy.types.Mesh, material: bpy.types.Material | None) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _finish(bm: bmesh.types.BMesh, name: str, material) -> bpy.types.Object:
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = False
    return _link(name, mesh, material)


def _slab(name: str, outline: list[Vector], z0: float, z1: float, material) -> bpy.types.Object:
    """A closed prism over a (possibly concave) outline."""
    bm = bmesh.new()
    low = [bm.verts.new((p.x, p.y, z0)) for p in outline]
    high = [bm.verts.new((p.x, p.y, z1)) for p in outline]
    bm.faces.new(low)
    bm.faces.new(high)
    count = len(outline)
    for i in range(count):
        j = (i + 1) % count
        bm.faces.new((low[i], low[j], high[j], high[i]))
    return _finish(bm, name, material)


def _ring(name: str, outer: list[Vector], inner: list[Vector], z0: float, z1: float, material) -> bpy.types.Object:
    """A closed band between two outlines with matching corners."""
    bm = bmesh.new()
    rings = [[bm.verts.new((p.x, p.y, z)) for p in outline]
             for outline in (outer, inner) for z in (z0, z1)]
    o0, o1, i0, i1 = rings
    count = len(outer)
    for i in range(count):
        j = (i + 1) % count
        bm.faces.new((o0[i], o0[j], o1[j], o1[i]))
        bm.faces.new((i0[i], i1[i], i1[j], i0[j]))
        bm.faces.new((o0[i], i0[i], i0[j], o0[j]))
        bm.faces.new((o1[i], o1[j], i1[j], i1[i]))
    return _finish(bm, name, material)


def _box(name: str, centre: Vector, size, material, yaw: float = 0.0, bevel: float = 0.0) -> bpy.types.Object:
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


def _cut(target: bpy.types.Object, cutters: list[bpy.types.Object]) -> None:
    for cutter in cutters:
        mod = target.modifiers.new(f'cut {cutter.name}', 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.solver = 'EXACT'
        mod.object = cutter
        bpy.context.view_layer.objects.active = target
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for cutter in cutters:
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


def _plaster(name: str, colour, roughness: float = 0.88) -> bpy.types.Material:
    """Rolled emulsion: one colour, but drifting a few percent in tone and sheen."""
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
    sheen.inputs['To Min'].default_value = roughness - 0.06
    sheen.inputs['To Max'].default_value = min(1.0, roughness + 0.06)
    links.new(drift.outputs['Fac'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    return mat


def _scanned_material(name: str, diffuse: Path, tile_m, base=(0.30, 0.20, 0.12),
                      roughness_min: float = 0.0) -> bpy.types.Material:
    """A Poly Haven texture set (colour, roughness, OpenGL normal) at its real size in metres."""
    mat = _material(name, base, 0.5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    tile_x, tile_y = (tile_m, tile_m) if isinstance(tile_m, (int, float)) else tile_m
    mapping.inputs['Scale'].default_value = (1.0 / float(tile_x), 1.0 / float(tile_y), 1.0)
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
    if roughness_min > 0.0:
        # Some scans are lacquered to a mirror; a lived-in floor never is.
        floor = nodes.new('ShaderNodeMath')
        floor.operation = 'MAXIMUM'
        floor.inputs[1].default_value = roughness_min
        links.new(rough, floor.inputs[0])
        rough = floor.outputs['Value']
    links.new(rough, bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(scan('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def _thin_glass() -> bpy.types.Material:
    """Thin float glass: a 4 % Fresnel reflection over a see-through layer.

    Shaded as transparent so rays through it stay camera rays: the world then
    shows the garden photograph to the camera alone, while the room is lit by
    the physical sky.

    Both faces of the pane reflect as air-to-glass. Cycles' Fresnel node treats
    a back face as glass-to-air (it inverts the IOR there), so a ray leaving the
    pane at more than 41 deg is totally reflected and the window turns black --
    exactly what a camera looking at a window 49 deg off its axis got. Feeding
    the inverse IOR on back faces cancels that inversion.
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


def place_model(path: Path, name: str, *, yaw_deg: float = 0.0, **anchor: float) -> dict[str, Any]:
    """Import a glTF model, turn it about z and set its bounding box on an anchor.

    Anchor keys: ``x`` / ``y`` (box centre), ``x_min`` / ``x_max`` /
    ``y_min`` / ``y_max`` (box faces) and ``z`` (bottom of the box).
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
    root.rotation_euler.z = math.radians(yaw_deg)
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == 'MESH']
    # A framed print's glazing imports as a solid refractive slab, which turns
    # the print behind it black; shade it as the same thin pane as the window.
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
    root.location = shift
    bpy.context.view_layer.update()
    lo, hi = lo + shift, hi + shift
    return {'model': path.name, 'yaw_deg': yaw_deg,
            'bbox_min': [round(v, 4) for v in lo], 'bbox_max': [round(v, 4) for v in hi]}


# ------------------------------------------------------------------ daylight


def _aim(obj: bpy.types.Object, point: Vector) -> None:
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def daylight(spec: dict[str, Any], sun_target: Vector, window_view: Path) -> dict[str, Any]:
    """A sun lamp and a physical sky outside; no lamp inside the room."""
    el = math.radians(float(spec['sun_elevation_deg']))
    heading = math.radians(float(spec['sun_heading_deg']))
    travel = Vector((math.cos(el) * math.cos(heading), math.cos(el) * math.sin(heading), -math.sin(el)))
    sun_data = bpy.data.lights.new('Morning sun', 'SUN')
    sun_data.energy = float(spec['sun_energy'])
    sun_data.angle = math.radians(0.53)
    sun_data.color = (1.0, 0.955, 0.90)
    sun = bpy.data.objects.new('Morning sun', sun_data)
    bpy.context.collection.objects.link(sun)
    sun.location = Vector(sun_target) - 6.0 * travel
    _aim(sun, sun.location + travel)

    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Morning sky')
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
    lighting.inputs['Strength'].default_value = float(spec['sky_strength'])

    coord = nodes.new('ShaderNodeTexCoord')
    turn = nodes.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    towards_sun = -travel
    turn.inputs['Rotation'].default_value = (
        0.0, 0.0, math.radians(WINDOW_VIEW_SUN_AZIMUTH_DEG) - math.atan2(towards_sun.y, towards_sun.x))
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(window_view), check_existing=True)
    links.new(coord.outputs['Generated'], turn.inputs['Vector'])
    links.new(turn.outputs['Vector'], photo.inputs['Vector'])
    view = nodes.new('ShaderNodeBackground')
    view.inputs['Strength'].default_value = float(spec['window_view_strength'])
    links.new(photo.outputs['Color'], view.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(lighting.outputs['Background'], mix.inputs[1])
    links.new(view.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['World Output'].inputs['Surface'])
    return {'sun_elevation_deg': float(spec['sun_elevation_deg']),
            'sun_heading_deg': float(spec['sun_heading_deg']),
            'sun_energy': float(spec['sun_energy']), 'window_view': window_view.name}


def _portal(name: str, centre: Vector, size, inward: Vector) -> None:
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = size
    data.cycles.is_portal = True
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = centre
    _aim(obj, Vector(centre) + Vector(inward))




# ---------------------------------------------------------------------- room


def _asset(asset_dirs: tuple[Path, ...], relative: str) -> Path:
    """The first of the scene's asset folders that holds the file."""
    for folder in asset_dirs:
        path = Path(folder) / relative
        if path.is_file():
            return path
    raise FileNotFoundError(f'{relative} is in none of {[str(d) for d in asset_dirs]}; '
                            'run scripts/download_assets.py for this scene')


def _wall_frames(room: dict[str, Any]) -> dict[str, tuple[float, Vector, Vector]]:
    """Plaster coordinate, along-wall direction and inward normal of each wall.

    A window's span is measured along the wall in world coordinates: y on the
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


def _window(index: int, spec: dict[str, Any], frames, walls: bpy.types.Object, floor_z: float,
            sash_paint, trim) -> dict[str, Any]:
    """A hole through the full wall, a painted frame in the middle of the reveal,
    glass in the sash plane, an interior window board and a sky portal."""
    face, along, inward = frames[spec['wall']]
    outward = -inward
    s0, s1 = (float(v) for v in spec['span'])
    z0, z1 = (floor_z + float(v) for v in spec['z'])
    width, height = s1 - s0, z1 - z0
    sc, zc = (s0 + s1) / 2.0, (z0 + z1) / 2.0
    base = Vector((face, sc, zc)) if along.y else Vector((sc, face, zc))
    yaw = math.atan2(along.y, along.x)

    def at(depth: float, offset: float = 0.0, z: float = zc) -> Vector:
        return base + outward * depth + along * offset + Vector((0.0, 0.0, z - zc))

    name = f'Window {index + 1} ({spec["wall"]})'
    _cut(walls, [_box(f'{name} hole', at(WALL_THICK_M / 2), (width, WALL_THICK_M + 0.2, height), None, yaw)])
    bar, thick, middle = 0.055, 0.045, 0.0925
    _box(f'{name} head', at(middle, 0.0, z1 - bar / 2), (width, thick, bar), sash_paint, yaw, 0.001)
    _box(f'{name} bottom rail', at(middle, 0.0, z0 + bar / 2), (width, thick, bar), sash_paint, yaw, 0.001)
    for sign in (-1, 1):
        _box(f'{name} jamb {sign:+d}', at(middle, sign * (width - bar) / 2), (bar, thick, height - 2 * bar),
             sash_paint, yaw, 0.001)
    mullions = max(1, round(width / 0.9))
    for k in range(1, mullions + 1):
        offset = -width / 2 + k * width / (mullions + 1)
        _box(f'{name} mullion {k}', at(middle, offset), (0.050, thick - 0.008, height - 2 * bar),
             sash_paint, yaw, 0.001)
    pane = _box(f'{name} glass', at(middle), (width - 0.02, 0.006, height - 0.02), _thin_glass(), yaw)
    pane.visible_shadow = False
    _box(f'{name} board', at(0.015, 0.0, z0 - 0.012), (width + 0.10, 0.15, 0.026), trim, yaw, 0.001)
    _portal(f'{name} sky portal', at(WALL_THICK_M + 0.01), (width, height), inward)
    return {'wall': spec['wall'], 'span': [s0, s1], 'z': [round(z0, 4), round(z1, 4)],
            'centre': [round(v, 4) for v in at(0.0)]}


def build_room(room: dict[str, Any], look: dict[str, Any], asset_dirs: tuple[Path, ...],
               floor_z: float = 0.0) -> dict[str, Any]:
    """Walls, floor, ceiling, skirting, windows, daylight and furniture.

    ``room`` is the scenario's physical room (wall planes and ceiling height);
    ``look`` holds what the simulator does not see: colours, windows, the
    daylight and the furniture list.
    """
    ceiling_z = floor_z + float(room['ceiling_m'])
    lines = _wall_lines(room)
    plaster_outline = _polygon(lines, {name: SKIRT_THICK_M for name, _n, _c in lines})
    outer_outline = _polygon(lines, {name: SKIRT_THICK_M + WALL_THICK_M for name, _n, _c in lines})
    skirt_face = _polygon(lines, {})
    skirt_back = _polygon(lines, {name: SKIRT_THICK_M + 0.004 for name, _n, _c in lines})
    slab_outline = _polygon(lines, {name: SKIRT_THICK_M + WALL_THICK_M / 2 for name, _n, _c in lines})

    wall_paint = _plaster('Warm white emulsion', tuple(look.get('wall_color', (0.66, 0.63, 0.58))))
    ceiling_paint = _plaster('Ceiling white', (0.74, 0.73, 0.70), 0.92)
    trim = _material('Satin white joinery', tuple(look.get('trim_color', (0.70, 0.69, 0.66))), 0.42, 0.0003)
    sash_paint = _material('Eggshell window paint', (0.72, 0.71, 0.68), 0.55)

    _slab('Floor', slab_outline, floor_z - 0.08, floor_z,
          _scanned_material('Scanned floor', _asset(asset_dirs, look['floor']['diffuse']), look['floor']['tile_m'],
                            roughness_min=float(look['floor'].get('roughness_min', 0.0))))
    rug = look.get('rug')
    if rug:
        # A pile rug well away from where anything rolls: the floor the ball and
        # bottles touch stays the bare boards the simulator's friction describes.
        (rx0, rx1), (ry0, ry1) = rug['x'], rug['y']
        _box('Rug', Vector(((rx0 + rx1) / 2, (ry0 + ry1) / 2, floor_z + rug['height_m'] / 2)),
             (rx1 - rx0, ry1 - ry0, rug['height_m']),
             _scanned_material('Rug', _asset(asset_dirs, rug['diffuse']), rug['tile_m'], (0.4, 0.45, 0.4)), bevel=0.006)
    _slab('Ceiling', slab_outline, ceiling_z, ceiling_z + 0.10, ceiling_paint)
    walls = _ring('Walls', outer_outline, plaster_outline, floor_z - 0.10, ceiling_z + 0.10, wall_paint)
    skirting = _ring('Skirting', skirt_back, skirt_face, floor_z - 0.002, floor_z + SKIRT_HEIGHT_M, trim)
    mod = skirting.modifiers.new('Soft edges', 'BEVEL')
    mod.width, mod.segments = 0.0015, 2
    skirting.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')

    frames = _wall_frames(room)
    windows = [_window(i, w, frames, walls, floor_z, sash_paint, trim)
               for i, w in enumerate(look.get('windows') or [])]
    if not windows:
        raise ValueError('the room has no windows: it is lit only through them')

    # The ground outside stops sky light from below; the camera sees through it.
    ground = _box('Ground outside', Vector((0.0, 0.0, floor_z - 0.45)), (200.0, 200.0, 0.3),
                  _material('Ground outside', (0.18, 0.17, 0.15), 0.9))
    ground.visible_camera = False

    light_info = daylight(dict(look['daylight']), Vector(windows[0]['centre']),
                          _asset(asset_dirs, look.get('window_view', 'symmetrical_garden_02_2k.hdr')))
    furniture = furnish(look.get('furniture') or [], asset_dirs, floor_z)
    print(f'[room] built: {len(windows)} windows, {len(furniture)} furniture pieces, '
          f'ceiling at {ceiling_z:.2f} m')
    return {'source': 'built', 'plan_plaster': [[round(p.x, 4), round(p.y, 4)] for p in plaster_outline],
            'ceiling_z': round(ceiling_z, 4), 'windows': windows, 'daylight': light_info,
            'furniture': furniture}


def furnish(items: list[dict[str, Any]], asset_dirs: tuple[Path, ...], floor_z: float) -> list[dict[str, Any]]:
    """Place each Poly Haven model by its anchor.

    ``on`` stands a piece on the top of an earlier one, ``level_m`` on a shelf
    that high above the floor; otherwise it stands on the floor.
    """
    placed: dict[str, dict[str, Any]] = {}
    for item in items:
        item = dict(item)
        model = item.pop('model')
        name = item.pop('name', model)
        yaw = float(item.pop('yaw_deg', 0.0))
        on, level = item.pop('on', None), item.pop('level_m', None)
        if on is not None:
            item['z'] = placed[on]['bbox_max'][2]
        elif level is not None:
            item['z'] = floor_z + float(level)
        else:
            item['z'] = floor_z
        info = place_model(_asset(asset_dirs, f'{model}/{model}_1k.gltf'), name, yaw_deg=yaw,
                           **{k: float(v) for k, v in item.items()})
        info['name'] = name
        placed[name] = info
    return list(placed.values())


def check_clearance(furniture: list[dict[str, Any]], samples: list[tuple[Vector, float]],
                    margin: float = 0.02) -> dict[str, float]:
    """Smallest gap between any moving body's bounding sphere and each piece's box."""
    gaps = {}
    for piece in furniture:
        lo, hi = Vector(piece['bbox_min']), Vector(piece['bbox_max'])
        gap = min(
            math.sqrt(sum(max(lo[i] - c[i], 0.0, c[i] - hi[i]) ** 2 for i in range(3))) - radius
            for c, radius in samples)
        gaps[piece['name']] = round(gap, 3)
        if gap < margin:
            raise ValueError(f'a moving body passes within {gap:.3f} m of {piece["name"]}; move the piece')
    print('[room] clearance to furniture: ' + ', '.join(f'{k} {v:.2f} m' for k, v in gaps.items()))
    return gaps
