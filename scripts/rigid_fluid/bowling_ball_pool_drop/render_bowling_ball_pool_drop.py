"""Render a simulated run in the mountain-pool scene with Cycles.

The environment, ball asset, world and lights come from scene_bowling_ball_pool_drop.py. The water
is splash_bowling_ball_pool_drop.py's per-frame anisotropic surface with its spray, mist and foam
points, shaded as clear water with volume absorption (the elastic-duck look). The authored basin
below the coping gives way to a tiled tank along the pool opening; the sun on the tank is
caustics_bowling_ball_pool_drop.py's traced sunlight, and a lamp matching the sun fitted to the baked
window patches lights the water, ball and spray. The baked deck and coping gain the specular
reflection the bake lacks (wet near the pool), the ladder rails turn chrome and continue under water
with treads, and the open glazing gets a pane of glass.

blender -b --python render_bowling_ball_pool_drop.py -- --run <run dir> --out <png dir> [--frames 1-96]
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import optics_bowling_ball_pool_drop as optics  # noqa: E402
import scene_bowling_ball_pool_drop as pool_scene  # noqa: E402

FLOOR = optics.FLOOR
BALL_RADIUS = .075
SHELL_OVERLAP = .05       # water mesh at the floor pushed this far into it
WATER_ABSORPTION = optics.WATER_ABSORPTION
SUN_STRENGTH = 15.
SUN_COLOR = (1., .80, .60)
SUN_ANGLE_DEGREES = .53
TILE = .025               # mosaic tile size (m)
TILE_COLOURS = ((.34, .60, .72), (.43, .69, .80))  # light aqua mosaic, each tile somewhere between
GROUT = (.55, .58, .56)
WET_REACH = .6            # the deck this close to the pool reads wet: glossier towards the edge
GLASS_PLANE = ((.633, .575, .520), 1.50)  # the slanted glazing (normal, offset), fitted to its frames
GLASS_SPAN = ((1.55, 8.65), (-1.20, 1.65))  # pane extent along the glazing and up its slope, from the camera
LADDER_ENDS = ((.056, 1.649, -.131), (-.130, 1.882, -.131))  # pool-side ends of the authored rails
LADDER_RAIL = .012        # rail radius (m)


def parse():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--frames', default='1-96')
    parser.add_argument('--frame-list', help='Comma-separated frames instead of the --frames range.')
    parser.add_argument('--samples', type=int, default=64)
    parser.add_argument('--exposure', type=float, default=-.75)
    parser.add_argument('--resolution', nargs=2, type=int, default=(1280, 720))
    parser.add_argument('--sun-strength', type=float, default=SUN_STRENGTH)
    parser.add_argument('--dry-run', action='store_true', help='Build the scene and load the first frame only.')
    return parser.parse_args(argv)


def configure_gpu():
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for backend in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            selected = [d for d in prefs.devices if d.type == backend]
            if not selected:
                continue
            for d in prefs.devices:
                d.use = d in selected
            bpy.context.scene.cycles.device = 'GPU'
            return {'backend': backend, 'devices': [d.name for d in selected]}
        except Exception as exc:
            print('GPU_RETRY', exc, flush=True)
    raise RuntimeError('No GPU: refusing a silent CPU fallback.')


def water_material():
    """Clear water; shadow rays pass the surface (still absorbed in the volume) so things under it are lit."""
    material = bpy.data.materials.new('GenesisWater')
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes['Principled BSDF']
    for name, value in (('Base Color', (1., 1., 1., 1.)), ('Transmission Weight', 1.), ('Roughness', .02), ('IOR', optics.IOR)):
        bsdf.inputs[name].default_value = value
    output = nodes['Material Output']
    absorption = nodes.new('ShaderNodeVolumeAbsorption')
    absorption.inputs['Color'].default_value = (*WATER_ABSORPTION[0], 1.)
    absorption.inputs['Density'].default_value = WATER_ABSORPTION[1]
    links.new(absorption.outputs['Volume'], output.inputs['Volume'])
    path, transparent, mix = (nodes.new(kind) for kind in ('ShaderNodeLightPath', 'ShaderNodeBsdfTransparent', 'ShaderNodeMixShader'))
    links.new(path.outputs['Is Shadow Ray'], mix.inputs['Fac'])
    links.new(bsdf.outputs['BSDF'], mix.inputs[1])
    links.new(transparent.outputs['BSDF'], mix.inputs[2])
    links.new(mix.outputs['Shader'], output.inputs['Surface'])
    return material


def particle_material(name, base, transmission, roughness, opacity=None):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes['Principled BSDF']
    for socket, value in (('Base Color', (*base, 1.)), ('Transmission Weight', transmission), ('Roughness', roughness), ('IOR', optics.IOR)):
        bsdf.inputs[socket].default_value = value
    if opacity is not None:
        fade = nodes.new('ShaderNodeAttribute')
        fade.attribute_name = 'fade'
        scale = nodes.new('ShaderNodeMath')
        scale.operation = 'MULTIPLY'
        scale.inputs[1].default_value = opacity
        links.new(fade.outputs['Fac'], scale.inputs[0])
        links.new(scale.outputs['Value'], bsdf.inputs['Alpha'])
    return material


def points_object(name, material):
    group = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    group.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = group.nodes, group.links
    source, target = nodes.new('NodeGroupInput'), nodes.new('NodeGroupOutput')
    points = nodes.new('GeometryNodeMeshToPoints')
    radius = nodes.new('GeometryNodeInputNamedAttribute')
    radius.data_type = 'FLOAT'
    radius.inputs['Name'].default_value = 'radius'
    assign = nodes.new('GeometryNodeSetMaterial')
    assign.inputs['Material'].default_value = material
    links.new(source.outputs[0], points.inputs['Mesh'])
    links.new(radius.outputs['Attribute'], points.inputs['Radius'])
    links.new(points.outputs['Points'], assign.inputs['Geometry'])
    links.new(assign.outputs['Geometry'], target.inputs[0])
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    obj.modifiers.new('Points', 'NODES').node_group = group
    return obj


def remove_pool_debris():
    """Delete the authored basin below the coping lip: its walls, stretched by the deepened floor, and the
    remains of the removed pool floats. The tank takes their place."""
    obj = bpy.data.objects['pool.001']
    world = obj.matrix_world
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    centres = np.array([tuple(world @ face.calc_center_median()) for face in bm.faces])
    doomed = [face for face, gone in zip(bm.faces, optics.debris(centres)) if gone]
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(doomed)


def split_environment(corners):
    """Give the authored deck and coping a glossy layer (wet near the pool) and the ladder rails chrome;
    everything else keeps the baked emission. Returns face counts per material."""
    obj = bpy.data.objects['pool.001']
    mesh = obj.data
    baked = mesh.materials[0]
    mesh.materials.append(deck_material(baked, corners))
    mesh.materials.append(chrome_material())
    world = np.array([tuple(obj.matrix_world @ v.co) for v in mesh.vertices])
    parent = np.arange(len(world))

    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for edge in mesh.edges:
        parent[root(edge.vertices[0])] = root(edge.vertices[1])
    roots = np.array([root(i) for i in range(len(world))])
    rails = {roots[np.argmin(np.linalg.norm(world - end, axis=1))] for end in LADDER_ENDS}
    counts = {'deck': 0, 'chrome': 0}
    for polygon in mesh.polygons:
        points = world[list(polygon.vertices)]
        centre = points.mean(axis=0)
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        normal /= max(np.linalg.norm(normal), 1e-12)
        outside = -optics.wall_distance(centre, optics.OPENING)
        if roots[polygon.vertices[0]] in rails:
            polygon.material_index = 2
            counts['chrome'] += 1
        elif outside > -.002 and -.16 < centre[2] < -.05 and (abs(normal[2]) > .9 or outside < .3):
            polygon.material_index = 1
            counts['deck'] += 1
    mesh.update()
    return counts


def deck_material(baked, corners):
    """The baked deck plus the specular reflection the bake lacks: glazed tile and stone, wet and glossy at
    the pool edge (roughness .05) drying out over WET_REACH (.32)."""
    material = baked.copy()
    material.name = 'BakedDeckGlossy'
    nodes, links = material.node_tree.nodes, material.node_tree.links
    output = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
    baked_shader = output.inputs['Surface'].links[0].from_socket
    position = nodes.new('ShaderNodeNewGeometry')
    outside = None
    for n, d in zip(*optics.planes(corners)):
        dot = nodes.new('ShaderNodeVectorMath')
        dot.operation = 'DOT_PRODUCT'
        dot.inputs[1].default_value = (n[0], n[1], 0.)
        links.new(position.outputs['Position'], dot.inputs[0])
        beyond = nodes.new('ShaderNodeMath')
        beyond.operation = 'SUBTRACT'
        beyond.inputs[1].default_value = d
        links.new(dot.outputs['Value'], beyond.inputs[0])
        if outside is None:
            outside = beyond.outputs['Value']
        else:
            most = nodes.new('ShaderNodeMath')
            most.operation = 'MAXIMUM'
            links.new(outside, most.inputs[0])
            links.new(beyond.outputs['Value'], most.inputs[1])
            outside = most.outputs['Value']
    roughness = nodes.new('ShaderNodeMapRange')
    roughness.interpolation_type = 'SMOOTHSTEP'
    roughness.inputs['From Min'].default_value, roughness.inputs['From Max'].default_value = 0., WET_REACH
    roughness.inputs['To Min'].default_value, roughness.inputs['To Max'].default_value = .05, .32
    links.new(outside, roughness.inputs['Value'])
    specular = nodes.new('ShaderNodeBsdfPrincipled')
    specular.inputs['Base Color'].default_value = (0., 0., 0., 1.)
    specular.inputs['IOR'].default_value = 1.5
    links.new(roughness.outputs['Result'], specular.inputs['Roughness'])
    add = nodes.new('ShaderNodeAddShader')
    links.new(baked_shader, add.inputs[0])
    links.new(specular.outputs['BSDF'], add.inputs[1])
    links.new(add.outputs['Shader'], output.inputs['Surface'])
    return material


def chrome_material():
    material = bpy.data.materials.new('LadderChrome')
    material.use_nodes = True
    bsdf = material.node_tree.nodes['Principled BSDF']
    for name, value in (('Base Color', (.86, .87, .89, 1.)), ('Metallic', 1.), ('Roughness', .12)):
        bsdf.inputs[name].default_value = value
    return material


def glass_material():
    """Thin glazing: Fresnel mix of a faintly tinted transparent pass-through and a slightly smudged mirror.
    The camera sees the slanted glazing almost edge-on, where full Fresnel turns it into a mirror that hides
    the view; the reflection is held at under a third, as coated architectural glass reads."""
    material = bpy.data.materials.new('WindowGlass')
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.remove(nodes['Principled BSDF'])
    fresnel = nodes.new('ShaderNodeFresnel')
    fresnel.inputs['IOR'].default_value = 1.52
    both_faces = nodes.new('ShaderNodeMath')
    both_faces.operation = 'MULTIPLY'
    both_faces.use_clamp = True
    both_faces.inputs[1].default_value = .45
    clear = nodes.new('ShaderNodeBsdfTransparent')
    clear.inputs['Color'].default_value = (.93, .96, .95, 1.)
    mirror = nodes.new('ShaderNodeBsdfGlossy')
    smudge = nodes.new('ShaderNodeTexNoise')
    smudge.inputs['Scale'].default_value = 4.
    smudge.inputs['Detail'].default_value = 6.
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['From Min'].default_value, rough.inputs['From Max'].default_value = .35, .75
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = .01, .09
    links.new(smudge.outputs['Fac'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], mirror.inputs['Roughness'])
    mix = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], both_faces.inputs[0])
    links.new(both_faces.outputs['Value'], mix.inputs['Fac'])
    links.new(clear.outputs['BSDF'], mix.inputs[1])
    links.new(mirror.outputs['BSDF'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return material


def add_glass(camera):
    """One pane in the slanted glazing, just inside the outer face of its frames, over every opening the
    camera sees the sky through (rays from the camera over the frame)."""
    normal, offset = GLASS_PLANE
    normal = np.asarray(normal) / np.linalg.norm(normal)
    along = np.cross([0., 0., 1.], normal)
    along /= np.linalg.norm(along)
    up = np.cross(normal, along)
    base = np.asarray(camera) + (offset - normal @ camera) * normal
    (a0, a1), (b0, b1) = GLASS_SPAN
    corners = [tuple(base + a * along + b * up) for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1))]
    mesh = bpy.data.meshes.new('WindowGlass')
    mesh.from_pydata(corners, [], [(0, 1, 2, 3)])
    mesh.materials.append(glass_material())
    obj = bpy.data.objects.new('WindowGlass', mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def add_ladder(corners):
    """The underwater part the authored ladder lacks: both rails continue from their ends at the coping down
    the wall, 6 cm off it, with three treads between them."""
    material = chrome_material()
    normal, offset = optics.planes(corners)
    wall = int(np.argmin(np.abs(offset - normal @ np.asarray(LADDER_ENDS[0][:2]))))  # the wall the ladder hangs on
    inward = np.array([*-normal[wall], 0.])
    objects = []
    rails = []
    for end in LADDER_ENDS:
        end = np.asarray(end)
        path = [end, end + .03 * inward + (0, 0, -.05), end + .06 * inward + (0, 0, -.15),
                end + .06 * inward + (0, 0, -.90), end + .03 * inward + (0, 0, -.99), end + (0, 0, -1.01)]
        curve = bpy.data.curves.new('LadderRail', 'CURVE')
        curve.dimensions = '3D'
        curve.bevel_depth = LADDER_RAIL
        curve.bevel_resolution = 4
        spline = curve.splines.new('NURBS')
        spline.points.add(len(path) - 1)
        for point, p in zip(spline.points, path):
            point.co = (*p, 1.)
        spline.order_u = 3
        spline.use_endpoint_u = True
        curve.materials.append(material)
        obj = bpy.data.objects.new('LadderRail', curve)
        bpy.context.scene.collection.objects.link(obj)
        objects.append(obj)
        rails.append(end + .06 * inward)
    along = (rails[1] - rails[0]) / np.linalg.norm(rails[1] - rails[0])
    span = np.linalg.norm(rails[1] - rails[0])
    for depth in (-.40, -.62, -.84):
        centre = (rails[0] + rails[1]) / 2 + (0, 0, depth - LADDER_ENDS[0][2])
        half = (along * span / 2, inward * .04, np.array([0, 0, .006]))
        signs = [(sa, sb, sc) for sc in (-1, 1) for sb in (-1, 1) for sa in (-1, 1)]
        verts = [tuple(centre + sa * half[0] + sb * half[1] + sc * half[2]) for sa, sb, sc in signs]
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        mesh = bpy.data.meshes.new('LadderTread')
        mesh.from_pydata(verts, [], faces)
        mesh.materials.append(material)
        obj = bpy.data.objects.new('LadderTread', mesh)
        bpy.context.scene.collection.objects.link(obj)
        objects.append(obj)
    return objects


def colour_socket(sockets, name, kind='RGBA'):
    """A Mix node socket by name and type (its float, vector and colour sockets share names)."""
    return next(s for s in sockets if s.name == name and s.type == kind)


def tank_material(name, sunlight, strength, waterline):
    """Glazed light-aqua mosaic (2.5 cm tiles, each a slightly different shade, greyish grout, slight edge
    relief) with a faint stain line at the water's edge. Its sunlit colour is emitted from the traced
    sunlight texture: tile colour x irradiance x sun strength x colour / pi."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.cycles.emission_sampling = 'NONE'
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = .22
    bsdf.inputs['Coat Weight'].default_value = .35
    bsdf.inputs['Coat Roughness'].default_value = .06
    metres = nodes.new('ShaderNodeUVMap')
    metres.uv_map = 'UVMap'
    # One random shade per tile: white noise of the tile index.
    cell = nodes.new('ShaderNodeVectorMath')
    cell.operation = 'SCALE'
    cell.inputs['Scale'].default_value = 1 / TILE
    index = nodes.new('ShaderNodeVectorMath')
    index.operation = 'FLOOR'
    shade = nodes.new('ShaderNodeTexWhiteNoise')
    shade.noise_dimensions = '3D'
    tile = nodes.new('ShaderNodeMix')
    tile.data_type = 'RGBA'
    colour_socket(tile.inputs, 'A').default_value = (*TILE_COLOURS[0], 1.)
    colour_socket(tile.inputs, 'B').default_value = (*TILE_COLOURS[1], 1.)
    links.new(metres.outputs['UV'], cell.inputs[0])
    links.new(cell.outputs['Vector'], index.inputs[0])
    links.new(index.outputs['Vector'], shade.inputs['Vector'])
    links.new(shade.outputs['Value'], colour_socket(tile.inputs, 'Factor', 'VALUE'))
    brick = nodes.new('ShaderNodeTexBrick')
    brick.offset, brick.squash = 0., 1.
    links.new(colour_socket(tile.outputs, 'Result'), brick.inputs['Color1'])
    links.new(colour_socket(tile.outputs, 'Result'), brick.inputs['Color2'])
    brick.inputs['Mortar'].default_value = (*GROUT, 1.)
    brick.inputs['Scale'].default_value = 1.
    brick.inputs['Mortar Size'].default_value = .0018
    brick.inputs['Mortar Smooth'].default_value = .3
    brick.inputs['Bias'].default_value = 0.
    brick.inputs['Brick Width'].default_value = TILE
    brick.inputs['Row Height'].default_value = TILE
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .25
    bump.inputs['Distance'].default_value = .0015
    invert = nodes.new('ShaderNodeMath')
    invert.operation = 'SUBTRACT'
    invert.inputs[0].default_value = 1.
    links.new(metres.outputs['UV'], brick.inputs['Vector'])
    # Stain line: a few centimetres at and just above the still water read slightly darker and greener.
    position = nodes.new('ShaderNodeNewGeometry')
    height = nodes.new('ShaderNodeSeparateXYZ')
    links.new(position.outputs['Position'], height.inputs['Vector'])
    band = None
    for low, high in ((waterline - .015, waterline), (waterline + .045, waterline + .02)):
        edge = nodes.new('ShaderNodeMapRange')
        edge.interpolation_type = 'SMOOTHSTEP'
        edge.inputs['From Min'].default_value, edge.inputs['From Max'].default_value = low, high
        links.new(height.outputs['Z'], edge.inputs['Value'])
        if band is None:
            band = edge
        else:
            both = nodes.new('ShaderNodeMath')
            both.operation = 'MULTIPLY'
            links.new(band.outputs['Result'], both.inputs[0])
            links.new(edge.outputs['Result'], both.inputs[1])
            band = both
    strength_band = nodes.new('ShaderNodeMath')
    strength_band.operation = 'MULTIPLY'
    strength_band.inputs[1].default_value = .55
    links.new(band.outputs[0], strength_band.inputs[0])
    stained = nodes.new('ShaderNodeMix')
    stained.data_type = 'RGBA'
    stained.blend_type = 'MULTIPLY'
    colour_socket(stained.inputs, 'B').default_value = (.72, .76, .62, 1.)
    links.new(strength_band.outputs['Value'], colour_socket(stained.inputs, 'Factor', 'VALUE'))
    links.new(brick.outputs['Color'], colour_socket(stained.inputs, 'A'))
    colour = colour_socket(stained.outputs, 'Result')
    links.new(colour, bsdf.inputs['Base Color'])
    links.new(brick.outputs['Fac'], invert.inputs[1])
    links.new(invert.outputs['Value'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    unit = nodes.new('ShaderNodeUVMap')
    unit.uv_map = 'SunUV'
    texture = nodes.new('ShaderNodeTexImage')
    texture.image = sunlight
    texture.interpolation = 'Linear'
    texture.extension = 'EXTEND'
    lit = nodes.new('ShaderNodeVectorMath')
    lit.operation = 'MULTIPLY'
    scale = nodes.new('ShaderNodeVectorMath')
    scale.operation = 'SCALE'
    scale.inputs['Scale'].default_value = strength / math.pi
    tint = nodes.new('ShaderNodeVectorMath')
    tint.operation = 'MULTIPLY'
    tint.inputs[1].default_value = SUN_COLOR
    emission = nodes.new('ShaderNodeEmission')
    add = nodes.new('ShaderNodeAddShader')
    links.new(unit.outputs['UV'], texture.inputs['Vector'])
    links.new(colour, lit.inputs[0])
    links.new(texture.outputs['Color'], lit.inputs[1])
    links.new(lit.outputs['Vector'], tint.inputs[0])
    links.new(tint.outputs['Vector'], scale.inputs[0])
    links.new(scale.outputs['Vector'], emission.inputs['Color'])
    links.new(bsdf.outputs['BSDF'], add.inputs[0])
    links.new(emission.outputs['Emission'], add.inputs[1])
    links.new(add.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return material


def add_tank(strength, corners, waterline):
    """Floor and four walls along the pool opening, up to the coping lip. UVMap is in metres along the walls
    (parallelogram floor tiles follow both pairs of walls, as the sheared scene does); SunUV spans each
    sunlight texture."""
    layout = optics.faces(corners)
    shear = np.linalg.inv(np.column_stack([(corners[1] - corners[0]) / np.linalg.norm(corners[1] - corners[0]),
                                           (corners[3] - corners[0]) / np.linalg.norm(corners[3] - corners[0])]))
    tank, images = [], {}
    for name, quad in zip(optics.FACES, optics.tank_quads(corners)):
        origin, u, v, (size_u, size_v), (rows, cols) = layout[name]
        image = bpy.data.images.new(f'Sun{name}', width=cols, height=rows, alpha=True, float_buffer=True)
        image.colorspace_settings.name = 'Non-Color'
        images[name] = image
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(quad, [], [tuple(range(len(quad)))])
        metres, unit = mesh.uv_layers.new(name='UVMap'), mesh.uv_layers.new(name='SunUV')
        for loop in mesh.loops:
            relative = np.asarray(quad[loop.vertex_index]) - origin
            if name == 'PoolFloor':
                metres.data[loop.index].uv = tuple(shear @ (np.asarray(quad[loop.vertex_index][:2]) - corners[0]))
            else:
                metres.data[loop.index].uv = (relative @ u, relative @ v)
            unit.data[loop.index].uv = (relative @ u / size_u, relative @ v / size_v)
        mesh.materials.append(tank_material(f'Tank{name}', image, strength, waterline))
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        tank.append(obj)
    return tank, images


def add_sun(strength, excluded):
    """The fitted sunset sun. It lights the water, ball and spray; the tank gets its traced sunlight instead.
    The authored environment is emission-only and already holds this sunlight."""
    data = bpy.data.lights.new('FittedSun', 'SUN')
    data.energy = strength
    data.color = SUN_COLOR
    data.angle = math.radians(SUN_ANGLE_DEGREES)
    sun = bpy.data.objects.new('FittedSun', data)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = Vector(optics.TO_SUN).to_track_quat('Z', 'Y').to_euler()
    receivers = bpy.data.collections.new('FittedSunExcluded')
    for obj in excluded:
        receivers.objects.link(obj)
    sun.light_linking.receiver_collection = receivers
    for item in receivers.collection_objects:
        item.light_linking.link_state = 'EXCLUDE'
    return sun


def build_scene(args, corners, waterline, ball_present=True):
    pool_scene.clear_scene()
    pool_scene.configure_world()
    pool_scene.add_lighting()
    pool_scene.add_mountain_pool_environment(FLOOR)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    gpu = None if args.dry_run else configure_gpu()
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = scene.cycles.transmission_bounces = scene.cycles.transparent_max_bounces = 12
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.render.use_motion_blur = False
    scene.render.film_transparent = False
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = args.exposure
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    ball = None
    if ball_present:
        ball = pool_scene.add_uv_sphere('ball', (0., 0., .7), BALL_RADIUS)
        pool_scene.add_bowling_ball_visual(ball, BALL_RADIUS, pool_scene.BOWLING_ASSET, 'soft-reflection', 'burgundy-red')
    bpy.ops.object.camera_add(location=(1.25, -2.00, .45))
    camera = bpy.context.object
    camera.data.lens = 26
    pool_scene.point_camera(camera, (0., 0., .25))
    camera.data.dof.use_dof = False
    scene.camera = camera
    water = bpy.data.objects.new('GenesisWater', bpy.data.meshes.new('GenesisWater'))
    scene.collection.objects.link(water)
    particles = {'spray': points_object('Spray', particle_material('SprayDrops', (1., 1., 1.), 1., .02)),
                 'mist': points_object('Mist', particle_material('SprayMist', (1., 1., 1.), .3, .4, opacity=.7)),
                 'foam': points_object('Foam', particle_material('SurfaceFoam', (.85, .88, .9), .2, .5, opacity=.6))}
    setup = {'gpu': gpu, 'debris_faces_removed': remove_pool_debris(), 'environment_faces': split_environment(corners)}
    add_glass(np.asarray(camera.location))
    add_ladder(corners)
    tank, images = add_tank(args.sun_strength, corners, waterline)
    add_sun(args.sun_strength, tank)
    return ball, water, water_material(), particles, images, setup


def load_water(path, water, material, corners):
    """Frame's water surface. It continues through the walls (mirror images), hidden behind the tank; what
    lies beyond the walls stays below the coping lip, and its contact with the floor moves into the floor."""
    with np.load(path) as data:
        vertices, triangles, normals = data['vertices'].copy(), data['triangles'], data['normals']
    normal, offset = optics.planes(corners)
    for n, d in zip(normal, offset):
        gap = d - vertices[:, :2] @ n
        near = (gap > 0) & (gap < .03)
        vertices[near, :2] += (gap[near] + .03)[:, None] * n
    outside = optics.wall_distance(vertices, corners) < 0
    vertices[outside, 2] = np.minimum(vertices[outside, 2], optics.RIM_Z - .01)
    vertices[vertices[:, 2] < FLOOR + .03, 2] -= SHELL_OVERLAP
    mesh = bpy.data.meshes.new(path.stem)
    mesh.vertices.add(len(vertices))
    mesh.vertices.foreach_set('co', np.ascontiguousarray(vertices, dtype=np.float32).ravel())
    mesh.loops.add(triangles.size)
    mesh.loops.foreach_set('vertex_index', np.ascontiguousarray(triangles, dtype=np.int32).ravel())
    mesh.polygons.add(len(triangles))
    mesh.polygons.foreach_set('loop_start', np.arange(0, triangles.size, 3, dtype=np.int32))
    mesh.polygons.foreach_set('loop_total', np.full(len(triangles), 3, dtype=np.int32))
    mesh.polygons.foreach_set('use_smooth', np.ones(len(triangles), dtype=np.bool_))
    mesh.update(calc_edges=True)
    mesh.normals_split_custom_set_from_vertices(normals.tolist())
    mesh.materials.append(material)
    old = water.data
    water.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return len(vertices), len(triangles)


def load_sunlight(path, images):
    """Frame's traced sunlight textures onto the tank's images."""
    with np.load(path) as data:
        for name, image in images.items():
            rgb = data[name]
            rgba = np.concatenate([rgb, np.ones(rgb.shape[:2] + (1,), np.float32)], axis=-1)
            image.pixels.foreach_set(np.ascontiguousarray(rgba, dtype=np.float32).ravel())
            image.update()
            mean = float(rgb.mean())
    return round(mean, 4)


def load_points(path, obj):
    with np.load(path) as data:
        position, radius = data['position'], data['radius']
        fade = data['fade'] if 'fade' in data else np.ones(len(radius), np.float32)
    mesh = bpy.data.meshes.new(path.stem)
    mesh.vertices.add(len(position))
    mesh.vertices.foreach_set('co', np.ascontiguousarray(position, dtype=np.float32).ravel())
    mesh.attributes.new('radius', 'FLOAT', 'POINT').data.foreach_set('value', np.ascontiguousarray(radius, dtype=np.float32))
    mesh.attributes.new('fade', 'FLOAT', 'POINT').data.foreach_set('value', np.ascontiguousarray(fade, dtype=np.float32))
    mesh.update()
    old = obj.data
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return len(position)


def main():
    args = parse()
    run, out = args.run.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.frame_list:
        frames = [int(v) for v in args.frame_list.split(',')]
    else:
        low, high = (int(v) for v in args.frames.split('-'))
        frames = list(range(low, high + 1))
    simulation = json.loads((run / 'simulation_report.json').read_text())
    info = simulation['info']
    corners = optics.container(info)
    ball_present = simulation['physics'].get('ball_present', True)
    ball, water, material, particles, images, setup = build_scene(args, corners, info['settled_surface_m'], ball_present)
    bpy.context.view_layer.update()
    fixed = {}
    for obj in sorted(bpy.context.scene.objects, key=lambda obj: obj.name):
        if obj.name in {'ball', 'BowlingBall_Visual', 'GenesisWater', 'Spray', 'Mist', 'Foam'}:
            continue
        item = {'type': obj.type, 'matrix_world': [list(row) for row in obj.matrix_world],
                'hide_render': obj.hide_render}
        if obj.type == 'MESH':
            co = np.empty(len(obj.data.vertices) * 3, np.float32)
            obj.data.vertices.foreach_get('co', co)
            indices = np.empty(len(obj.data.loops), np.int32)
            obj.data.loops.foreach_get('vertex_index', indices)
            item.update(vertices=len(obj.data.vertices), loops=len(indices),
                        geometry_sha256=hashlib.sha256(co.tobytes() + indices.tobytes()).hexdigest(),
                        materials=[m.name if m else None for m in obj.data.materials])
        if obj.type == 'LIGHT':
            item.update(light_type=obj.data.type, energy=obj.data.energy, color=list(obj.data.color))
        fixed[obj.name] = item
    scene = bpy.context.scene
    look = {'fixed_objects': fixed, 'lens_mm': scene.camera.data.lens,
            'resolution': [scene.render.resolution_x, scene.render.resolution_y], 'fps': scene.render.fps,
            'samples': scene.cycles.samples, 'denoising': scene.cycles.use_denoising,
            'exposure': scene.view_settings.exposure, 'view_transform': scene.view_settings.view_transform,
            'look': scene.view_settings.look, 'motion_blur': scene.render.use_motion_blur}
    setup['scene_snapshot'] = look
    setup['scene_snapshot_sha256'] = hashlib.sha256(json.dumps(look, sort_keys=True).encode()).hexdigest()
    setup['ball_present'] = ball_present
    report = {'run': str(run), **setup, 'pool_corners_m': corners.tolist(), 'samples': args.samples,
              'exposure': args.exposure, 'sun_strength': args.sun_strength, 'frames': {}}
    for frame in frames:
        tick = time.monotonic()
        with np.load(run / 'particles' / f'frame_{frame:04d}.npz') as data:
            if ball is not None:
                ball.location = [float(v) for v in data['ball_center']]
        record = {'mesh': load_water(run / 'aniso' / f'water_{frame:04d}.npz', water, material, corners)}
        for kind, obj in particles.items():
            record[kind] = load_points(run / 'aniso' / f'{kind}_{frame:04d}.npz', obj)
        record['sunlight_mean'] = load_sunlight(run / 'aniso' / f'caustics_{frame:04d}.npz', images)
        if args.dry_run:
            print('DRY_RUN_OK', frame, json.dumps(record), json.dumps(setup), flush=True)
            return
        bpy.context.scene.render.filepath = str(out / f'{frame:04d}.png')
        bpy.ops.render.render(write_still=True)
        record['seconds'] = time.monotonic() - tick
        report['frames'][str(frame)] = record
        (out / 'render_report.json').write_text(json.dumps(report, indent=1))
        print('RENDERED', frame, json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
