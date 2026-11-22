"""Render a simulated apple run in the kitchen with Cycles.

The kitchen, basin, apple, board, peppers and hero camera come from scene_apple_drop_kitchen_basin.py, lit by the
kitchen's own lights only (the Mantaflow scene's two added area lights washed it out). The water is
splash_apple_drop_kitchen_basin.py's per-frame anisotropic surface with its spray, mist and foam points, shaded
as clear water with volume absorption (the elastic-duck look); the apple asset follows the simulated
sphere's centre. Frames are exposed with a 180-degree shutter, as a camera would: the water surface
and droplets blur along their simulated velocities, so flying drops read as short streaks. Spilled
water is read from the splash stage's maps (wet_####.npz) in the materials it lies on. On the counter
and board the puddles' height gives the stone and wood a clear water coat whose normal follows the
water's surface, so puddle edges catch the light; the stone hardly darkens, wet wood more. Water
running down the basin's outer wall coats it and ripples the coat's normal, and where it ran stays
wet. A transparent sheet lying on them instead traps light between its underside and the surface
below and glows in that surface's colour. Droplets that came down on the counter or the board, or hit
the things standing there (the soda maker, the peppers, the tap), stay on them as beads of water.

blender -b --python render_apple_drop_kitchen_basin.py -- --run <run dir> --out <png dir> [--frames 1-96]
"""
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
import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scene_apple_drop_kitchen_basin as apple_scene  # noqa: E402

IOR = 1.333
WATER_ABSORPTION = ((.40, .84, .90), 1.)  # Volume Absorption colour and density, as the duck look
WET_SURFACES = {'Marble 5': .92, 'Material.007': .70}  # counter, cutting board: colour factor when wet
WATER_FULL = .02       # mm; water on the counter or board this deep coats it fully
WALL_SURFACE = ('PCVE Warm Gray Basin Plastic', .96)  # the basin: wet glazed ceramic hardly darkens
WALL_FACE_BAND = .003  # shading points this close inside the outer radius are its face (the wall is 7.5 mm)
WALL_FILM_FULL = .2    # mm; water running down the wall this deep coats it fully
WET_COAT_ROUGHNESS = .03
DRAIN_RADIUS = .06     # m; the drain hole is 27 mm in radius and its funnel 38 mm; the floor's smooth shading
                       # bends towards the funnel a little further out, so the cap covers that too and its
DRAIN_TOP = 2.1553     # m; edge runs under the gently rising floor (2.1553 at 5 cm)
BEAD_REACH = .015      # m; a stuck drop sits on the nearest surface this close (its 4 mm column, a path step)
SAMPLES = (1024, .003)  # most samples per pixel, and the adaptive noise threshold that stops them earlier. At
                        # 128 the denoiser re-drew the apple's skin and highlights differently every frame
                        # wherever it moved by a fraction of a pixel: a still apple (the honey-like edit)
                        # flickered (probe_flicker.py)
EXPOSURE = .7          # the camera's exposure under the kitchen's own lights: the file's 0.3 crushed the black
                       # sink and the cabinets (probe_lighting.py); a flatter AgX look lifted them but greyed it


def parse():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--frames', default='1-96')
    parser.add_argument('--frame-list', help='Comma-separated frames instead of the --frames range.')
    parser.add_argument('--samples', type=int, default=SAMPLES[0], help='Most samples per pixel (adaptive).')
    parser.add_argument('--exposure', type=float, default=EXPOSURE, help='View exposure.')
    parser.add_argument('--resolution', nargs=2, type=int, default=(1280, 720))
    parser.add_argument('--shutter', type=float, default=.5, help='Motion blur shutter in frames (0: off).')
    parser.add_argument('--gpu-backend', choices=('OPTIX', 'CUDA'), default='OPTIX',
                        help='Cycles GPU backend tried first (OptiX crashes Blender under NVIDIA driver 550).')
    parser.add_argument('--cpu-threads', type=int, default=0,
                        help='Render on the CPU with this many threads instead of a GPU (when no GPU is free).')
    parser.add_argument('--part', default='', help='Suffix of this process\'s render report.')
    parser.add_argument('--dry-run', action='store_true', help='Build the scene and load the first frame only.')
    return parser.parse_args(argv)


def configure_gpu(preferred):
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for backend in sorted(('OPTIX', 'CUDA'), key=lambda name: name != preferred):
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
    for name, value in (('Base Color', (1., 1., 1., 1.)), ('Transmission Weight', 1.), ('Roughness', .02), ('IOR', IOR)):
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
    for socket, value in (('Base Color', (*base, 1.)), ('Transmission Weight', transmission), ('Roughness', roughness), ('IOR', IOR)):
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


def add_drain_cap():
    """A flush ceramic drain cap over the basin's drain: the model leaves the hole open onto the
    counter, which shows through the moving water as a black blot. The apple floats right above the drain,
    and the water lifts the view of the floor under it, so any cap that stands out reads as its shadow."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=DRAIN_RADIUS, depth=.004, location=(
        apple_scene.BASIN_CENTER.x, apple_scene.BASIN_CENTER.y, DRAIN_TOP - .002))
    cap = bpy.context.object
    cap.name = 'PCVE_DrainCap'
    cap.data.materials.append(bpy.data.objects['PCVE_BlenderKit_Basin'].data.materials[0])


def build_scene(args, apple_start):
    apple, offset, camera = apple_scene.build_environment(apple_start, added_lights=False)
    add_drain_cap()
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    if args.cpu_threads:
        scene.cycles.device = 'CPU'
        scene.render.threads_mode, scene.render.threads = 'FIXED', args.cpu_threads
        gpu = {'backend': 'CPU', 'threads': args.cpu_threads}
    else:
        gpu = None if args.dry_run else configure_gpu(args.gpu_backend)
    scene.cycles.samples = args.samples
    scene.cycles.use_adaptive_sampling, scene.cycles.adaptive_threshold = True, SAMPLES[1]
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = scene.cycles.transmission_bounces = scene.cycles.transparent_max_bounces = 12
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    # A 180-degree shutter: water, droplets and foam blur along their simulated velocity, the apple
    # along its keyed path.
    scene.render.use_motion_blur = args.shutter > 0
    scene.render.motion_blur_shutter = max(args.shutter, .01)
    scene.render.film_transparent = False
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = args.exposure
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    water = bpy.data.objects.new('GenesisWater', bpy.data.meshes.new('GenesisWater'))
    scene.collection.objects.link(water)
    particles = {'spray': points_object('Spray', particle_material('SprayDrops', (1., 1., 1.), 1., .02)),
                 'mist': points_object('Mist', particle_material('SprayMist', (1., 1., 1.), .3, .4, opacity=.7)),
                 'foam': points_object('Foam', particle_material('SurfaceFoam', (.85, .88, .9), .2, .5, opacity=.6)),
                 'beads': points_object('Beads', particle_material('PropBeads', (1., 1., 1.), 1., .02))}
    setup = {'gpu': gpu, 'exposure': scene.view_settings.exposure, 'view_transform': scene.view_settings.view_transform,
             'lights': sorted(o.name for o in scene.objects if o.type == 'LIGHT' and not o.hide_render)}
    return apple, offset, water, water_material(), particles, setup


def wet_layer(path):
    """The splash stage's map images and the wet layers that read them: the counter and board look up
    the water height at each shading point's world position, the basin's outer wall its maps around it
    by angle and height. Water weights a clear coat and darkens the base colour, and its depth shapes
    the coat's normal; outside the maps nothing changes."""
    with np.load(path) as data:
        shape, lower, cell = data['water_mm'].shape, data['lower'], float(data['cell'])
        wall_shape, bottom = data['wall'].shape, float(data['wall_bottom'])
        radius, centre = float(data['wall_radius']), data['wall_centre']
    images = {'water_mm': wet_image('CounterWater', shape), 'wall': wet_image('WallWetness', wall_shape),
              'wall_film_mm': wet_image('WallFilm', wall_shape)}
    for name, darken in WET_SURFACES.items():
        nodes, links = bpy.data.materials[name].node_tree.nodes, bpy.data.materials[name].node_tree.links
        position = shifted_position(nodes, links, (float(lower[0]), float(lower[1]), 0.))
        scale = nodes.new('ShaderNodeVectorMath')
        scale.operation = 'MULTIPLY'
        scale.inputs[1].default_value = (1 / (shape[0] * cell), 1 / (shape[1] * cell), 1.)
        links.new(position, scale.inputs[0])
        depth = lookup(nodes, links, images['water_mm'], scale.outputs['Vector'], 'CLIP')
        present = math_node(nodes, 'DIVIDE')
        present.use_clamp = True
        links.new(depth, present.inputs[0])
        present.inputs[1].default_value = WATER_FULL
        coat(bpy.data.materials[name], present.outputs[0], darken)
        water_surface(nodes, links, depth)
    material = bpy.data.materials[WALL_SURFACE[0]]
    nodes, links = material.node_tree.nodes, material.node_tree.links
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(shifted_position(nodes, links, (float(centre[0]), float(centre[1]), bottom)), xyz.inputs[0])
    angle, u, v = (math_node(nodes, operation) for operation in ('ARCTAN2', 'MULTIPLY_ADD', 'MULTIPLY'))
    links.new(xyz.outputs['Y'], angle.inputs[0])
    links.new(xyz.outputs['X'], angle.inputs[1])
    links.new(angle.outputs[0], u.inputs[0])
    u.inputs[1].default_value, u.inputs[2].default_value = 1 / (2 * math.pi), .5
    links.new(xyz.outputs['Z'], v.inputs[0])
    v.inputs[1].default_value = 1 / (wall_shape[1] * cell)
    uv = nodes.new('ShaderNodeCombineXYZ')
    links.new(u.outputs[0], uv.inputs['X'])
    links.new(v.outputs[0], uv.inputs['Y'])
    # Only the outer face: the inner wall at the same angle and height is not where the spill ran.
    flat = nodes.new('ShaderNodeCombineXYZ')
    links.new(xyz.outputs['X'], flat.inputs['X'])
    links.new(xyz.outputs['Y'], flat.inputs['Y'])
    distance = nodes.new('ShaderNodeVectorMath')
    distance.operation = 'LENGTH'
    links.new(flat.outputs['Vector'], distance.inputs[0])
    outside = math_node(nodes, 'GREATER_THAN')
    links.new(distance.outputs['Value'], outside.inputs[0])
    outside.inputs[1].default_value = radius - WALL_FACE_BAND
    # The water running down now coats the wall fully from WALL_FILM_FULL deep, and its depth ripples the
    # coat's normal, so the moving sheet shows in the reflections; where it ran stays wet.
    film = lookup(nodes, links, images['wall_film_mm'], uv.outputs['Vector'], 'EXTEND')
    running, either, wetness = math_node(nodes, 'DIVIDE'), math_node(nodes, 'MAXIMUM'), math_node(nodes, 'MULTIPLY')
    running.use_clamp = True
    links.new(film, running.inputs[0])
    running.inputs[1].default_value = WALL_FILM_FULL
    links.new(lookup(nodes, links, images['wall'], uv.outputs['Vector'], 'EXTEND'), either.inputs[0])
    links.new(running.outputs[0], either.inputs[1])
    links.new(either.outputs[0], wetness.inputs[0])
    links.new(outside.outputs[0], wetness.inputs[1])
    coat(material, wetness.outputs[0], WALL_SURFACE[1])
    water_surface(nodes, links, film)
    return images


def water_surface(nodes, links, depth_mm):
    """The coat's normal follows the surface of water depth_mm deep on the material."""
    relief, bump = math_node(nodes, 'MULTIPLY'), nodes.new('ShaderNodeBump')
    links.new(depth_mm, relief.inputs[0])
    relief.inputs[1].default_value = 1e-3  # mm to m
    links.new(relief.outputs[0], bump.inputs['Height'])
    bump.inputs['Distance'].default_value = 1.
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    links.new(bump.outputs['Normal'], bsdf.inputs['Coat Normal'])


def wet_image(name, shape):
    image = bpy.data.images.new(name, shape[0], shape[1], alpha=False, float_buffer=True)
    image.colorspace_settings.name = 'Non-Color'
    return image


def shifted_position(nodes, links, origin):
    geometry, shift = nodes.new('ShaderNodeNewGeometry'), nodes.new('ShaderNodeVectorMath')
    shift.operation = 'SUBTRACT'
    shift.inputs[1].default_value = origin
    links.new(geometry.outputs['Position'], shift.inputs[0])
    return shift.outputs['Vector']


def math_node(nodes, operation):
    node = nodes.new('ShaderNodeMath')
    node.operation = operation
    return node


def lookup(nodes, links, image, vector, extension):
    texture = nodes.new('ShaderNodeTexImage')
    texture.image, texture.interpolation, texture.extension = image, 'Cubic', extension
    links.new(vector, texture.inputs['Vector'])
    return texture.outputs['Color']


def coat(material, wetness, darken):
    """A clear water coat weighted by wetness, and the base colour darkened towards darken."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    links.new(wetness, bsdf.inputs['Coat Weight'])
    bsdf.inputs['Coat Roughness'].default_value = WET_COAT_ROUGHNESS
    bsdf.inputs['Coat IOR'].default_value = IOR
    mix = nodes.new('ShaderNodeMix')
    mix.data_type, mix.blend_type = 'RGBA', 'MULTIPLY'
    links.new(wetness, socket(mix.inputs, 'Factor', 'VALUE'))
    base = bsdf.inputs['Base Color']
    if base.is_linked:
        links.new(base.links[0].from_socket, socket(mix.inputs, 'A', 'RGBA'))
    else:
        socket(mix.inputs, 'A', 'RGBA').default_value = base.default_value
    socket(mix.inputs, 'B', 'RGBA').default_value = (darken, darken, darken, 1.)
    links.new(socket(mix.outputs, 'Result', 'RGBA'), base)


def socket(sockets, name, kind):
    """Mix nodes carry one socket per data type under the same name."""
    return next(s for s in sockets if s.name == name and s.type == kind)


def load_water(path, water, material):
    with np.load(path) as data:
        vertices, triangles, normals, velocity = data['vertices'], data['triangles'], data['normals'], data['velocity']
    mesh = bpy.data.meshes.new(path.stem)
    mesh.vertices.add(len(vertices))
    mesh.vertices.foreach_set('co', np.ascontiguousarray(vertices, dtype=np.float32).ravel())
    mesh.attributes.new('velocity', 'FLOAT_VECTOR', 'POINT').data.foreach_set(
        'vector', np.ascontiguousarray(velocity, dtype=np.float32).ravel())
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


def load_wet(path, images):
    """Frame's wetness maps onto the images (map index i runs along image columns, j along rows)."""
    means = {}
    with np.load(path) as data:
        for key, image in images.items():
            wet = data[key].astype(np.float32).T
            rgba = np.stack([wet, wet, wet, np.ones_like(wet)], axis=-1)
            image.pixels.foreach_set(np.ascontiguousarray(rgba).ravel())
            image.update()
            means[key] = round(float(wet.mean()), 5)
    return means


def load_points(path, obj):
    with np.load(path) as data:
        position, radius, velocity = data['position'], data['radius'], data['velocity']
        fade = data['fade'] if 'fade' in data else np.ones(len(radius), np.float32)
    return set_points(obj, path.stem, position, radius, velocity, fade)


def bead_holders(skip=('PCVE_BlenderKit_Basin', 'PCVE_BlenderKit_RedApple', 'PCVE_DrainCap', 'GenesisWater')):
    """The things beads can sit on (anything rendered but the basin, the apple and the water), with their
    world bounds and, once first needed, a search tree of their surface."""
    holders = []
    for thing in bpy.context.scene.objects:
        if thing.type == 'MESH' and not thing.hide_render and thing.name not in skip and 'Points' not in thing.modifiers:
            lo, hi = apple_scene.bounds(thing)
            holders.append([thing, np.array(lo), np.array(hi), None])
    return holders


def load_beads(path, obj, holders):
    """Droplets resting on the counter or the board or stuck to the things standing there (beads_####.npz),
    drawn as water: a bead is a lens, which a coat on the surface cannot draw (on the board those showed
    as grey blobs). Each is a spherical cap of the drop's volume meeting the surface at its contact angle,
    so a sphere sunk into the surface. The splash stage knows the kitchen only as 4 mm columns, so each
    bead moves to the nearest surface within BEAD_REACH; one with none that near was under an overhang
    (the soda maker's head over its bottle), in the air, and is left out."""
    with np.load(path) as data:
        position, radius, angle = data['position'], data['radius'], data['angle']
    depsgraph = bpy.context.evaluated_depsgraph_get()
    # A cap meeting the surface at angle a, cut from a sphere of radius R, holds pi R^3 (1 - cos a)^2
    # (2 + cos a) / 3; the sphere's centre is R cos a inside the surface.
    cosine = np.cos(np.radians(angle))
    sphere = radius * np.cbrt(4 / ((1 - cosine) ** 2 * (2 + cosine)))
    seated, kept = [], []
    for k, point in enumerate(position.astype(np.float64)):
        best, reach, met = None, BEAD_REACH, Vector(point)
        for holder in holders:
            thing, lo, hi, tree = holder
            if np.any(point < lo - BEAD_REACH) or np.any(point > hi + BEAD_REACH):
                continue
            if tree is None:
                tree = holder[3] = BVHTree.FromObject(thing, depsgraph)
            world = thing.matrix_world
            near, normal, _, _ = tree.find_nearest(world.inverted() @ met)
            if near is None or (world @ near - met).length >= reach:
                continue
            near = world @ near
            normal = (world.to_3x3().inverted().transposed() @ normal).normalized()
            if normal.dot(met - near) < 0:  # outwards: towards where the drop came from
                normal = -normal
            best, reach = (near, normal), (near - met).length
        if best:
            seated.append(best[0] - best[1] * cosine[k] * sphere[k])
            kept.append(k)
    seated = np.array(seated, np.float32).reshape(-1, 3)
    return set_points(obj, path.stem, seated, sphere[kept].astype(np.float32), np.zeros_like(seated),
                      np.ones(len(seated), np.float32))


def set_points(obj, name, position, radius, velocity, fade):
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(position))
    mesh.vertices.foreach_set('co', np.ascontiguousarray(position, dtype=np.float32).ravel())
    mesh.attributes.new('velocity', 'FLOAT_VECTOR', 'POINT').data.foreach_set(
        'vector', np.ascontiguousarray(velocity, dtype=np.float32).ravel())
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
    apple, offset, water, material, particles, setup = build_scene(args, info['apple']['start_m'])
    setup['apple_present'] = simulation['physics'].get('apple_present', True)
    if not setup['apple_present']:      # DELETE apple
        for obj in (apple, *apple.children_recursive):
            obj.hide_render = obj.hide_viewport = True
    wetness = wet_layer(run / 'aniso' / f'wet_{frames[0]:04d}.npz')
    holders = bead_holders()
    report = {'run': str(run), **setup, 'samples': args.samples, 'shutter': args.shutter, 'frames': {}}
    # The apple's path is keyed on every simulated frame, so its motion blur follows it.
    keyed = sorted({k for frame in frames for k in (frame - 1, frame, frame + 1)
                    if (run / 'particles' / f'frame_{k:04d}.npz').exists()})
    for frame in keyed:
        with np.load(run / 'particles' / f'frame_{frame:04d}.npz') as data:
            apple.location = [float(c + o) for c, o in zip(data['ball_center'], offset)]
        apple.keyframe_insert('location', frame=frame)
    for frame in frames:
        tick = time.monotonic()
        bpy.context.scene.frame_set(frame)
        record = {'mesh': load_water(run / 'aniso' / f'water_{frame:04d}.npz', water, material),
                  'wet_mean': load_wet(run / 'aniso' / f'wet_{frame:04d}.npz', wetness)}
        for kind, obj in particles.items():
            path = run / 'aniso' / f'{kind}_{frame:04d}.npz'
            record[kind] = load_beads(path, obj, holders) if kind == 'beads' else load_points(path, obj)
        if args.dry_run:
            print('DRY_RUN_OK', frame, json.dumps(record), json.dumps(setup), flush=True)
            return
        bpy.context.scene.render.filepath = str(out / f'{frame:04d}.png')
        bpy.ops.render.render(write_still=True)
        record['seconds'] = time.monotonic() - tick
        report['frames'][str(frame)] = record
        (out / f'render_report{args.part}.json').write_text(json.dumps(report, indent=1))
        print('RENDERED', frame, json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
