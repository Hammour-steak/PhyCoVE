"""Blender/Cycles replay of one native libuipc cache in the dining-room look (appearance/room.py).

Every moving body is the cache: the wooden block(s) are keyed from their ABD
transforms at every native state, the sponge is the native FEM surface driven by
one shape key per state. The video takes every `fps/display_fps`-th state
(t_i = i/24 s, i = 0..95). Run through render_wood_block_rubber_stop.py.
"""
from pathlib import Path
import argparse, hashlib, json, os, socket, subprocess, sys, time

import bpy
import numpy as np
from mathutils import Matrix

sys.dont_write_bytecode = True  # no __pycache__ under scripts/
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE), str(HERE.parent), str(ROOT / 'scripts')]
from pcve_assets import asset
from edit_vocab import case_dsl
import room

BLOCK_WOOD = asset('polyhaven/dark_wood/textures')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def material(name, color, rough=.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bs = principled(mat)
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = rough
    return mat


def edge_wear(mat, bs, color_socket, rough_socket, normal_socket):
    """Handled-block wear: lighter, rougher, dented arrises (Bevel-normal edge mask
    broken up by noise) and a few shallow dings on the faces. Returns new sockets."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    geo = nodes.new('ShaderNodeNewGeometry')
    soft = nodes.new('ShaderNodeBevel')
    soft.samples = 8
    soft.inputs['Radius'].default_value = .004
    dot = nodes.new('ShaderNodeVectorMath')
    dot.operation = 'DOT_PRODUCT'
    links.new(soft.outputs['Normal'], dot.inputs[0])
    links.new(geo.outputs['Normal'], dot.inputs[1])
    edge = nodes.new('ShaderNodeMapRange')
    edge.inputs['From Min'].default_value = .995
    edge.inputs['From Max'].default_value = .86
    links.new(dot.outputs['Value'], edge.inputs['Value'])
    coord = nodes.new('ShaderNodeTexCoord')
    chips = nodes.new('ShaderNodeTexNoise')
    chips.inputs['Scale'].default_value = 140.0
    chips.inputs['Detail'].default_value = 4.0
    links.new(coord.outputs['Object'], chips.inputs['Vector'])
    gate = nodes.new('ShaderNodeMapRange')
    gate.inputs['From Min'].default_value = .48
    gate.inputs['From Max'].default_value = .62
    links.new(chips.outputs['Fac'], gate.inputs['Value'])
    worn = nodes.new('ShaderNodeMath')
    worn.operation = 'MULTIPLY'
    worn.use_clamp = True
    links.new(edge.outputs['Result'], worn.inputs[0])
    links.new(gate.outputs['Result'], worn.inputs[1])
    dings = nodes.new('ShaderNodeTexVoronoi')
    dings.inputs['Scale'].default_value = 55.0
    dings.inputs['Randomness'].default_value = 1.0
    links.new(coord.outputs['Object'], dings.inputs['Vector'])
    dent = nodes.new('ShaderNodeMapRange')
    dent.inputs['From Min'].default_value = .035
    dent.inputs['From Max'].default_value = .0
    links.new(dings.outputs['Distance'], dent.inputs['Value'])
    damage = nodes.new('ShaderNodeMath')
    damage.operation = 'MAXIMUM'
    links.new(worn.outputs[0], damage.inputs[0])
    links.new(dent.outputs['Result'], damage.inputs[1])
    raw = nodes.new('ShaderNodeHueSaturation')  # exposed, unoiled fibres: paler and drier
    raw.inputs['Saturation'].default_value = .75
    raw.inputs['Value'].default_value = 1.6
    links.new(color_socket, raw.inputs['Color'])
    mix = nodes.new('ShaderNodeMixRGB')
    links.new(worn.outputs[0], mix.inputs[0])
    links.new(color_socket, mix.inputs[1])
    links.new(raw.outputs['Color'], mix.inputs[2])
    links.new(mix.outputs['Color'], bs.inputs['Base Color'])
    dry = nodes.new('ShaderNodeMath')
    dry.operation = 'MULTIPLY_ADD'
    links.new(worn.outputs[0], dry.inputs[0])
    dry.inputs[1].default_value = .25
    links.new(rough_socket, dry.inputs[2])
    links.new(dry.outputs[0], bs.inputs['Roughness'])
    bump = nodes.new('ShaderNodeBump')
    bump.invert = True
    bump.inputs['Strength'].default_value = .6
    bump.inputs['Distance'].default_value = .0006
    links.new(damage.outputs[0], bump.inputs['Height'])
    links.new(normal_socket, bump.inputs['Normal'])
    links.new(bump.outputs['Normal'], bs.inputs['Normal'])


def hardwood_long_grain():
    """Solid walnut-brown hardwood (Poly Haven dark_wood 2K, 2 m tile, toned down), oiled satin;
    straight grain along the block; worn arrises and dings."""
    mat = bpy.data.materials.new('Oiled solid hardwood - long grain')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    uv = nodes.new('ShaderNodeTexCoord').outputs['UV']
    maps = {}
    for kind in ('diff', 'rough', 'nor_gl'):
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(BLOCK_WOOD / f'dark_wood_{kind}_2k.jpg'), check_existing=True)
        if kind != 'diff':
            tex.image.colorspace_settings.name = 'Non-Color'
        links.new(uv, tex.inputs['Vector'])
        maps[kind] = tex
    tone = nodes.new('ShaderNodeHueSaturation')
    tone.inputs['Hue'].default_value = .53
    tone.inputs['Saturation'].default_value = .8
    tone.inputs['Value'].default_value = 1.15
    links.new(maps['diff'].outputs['Color'], tone.inputs['Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = .42
    rough.inputs['To Max'].default_value = .62
    links.new(maps['rough'].outputs['Color'], rough.inputs['Value'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = .6
    links.new(maps['nor_gl'].outputs['Color'], normal.inputs['Color'])
    edge_wear(mat, bs, tone.outputs['Color'], rough.outputs['Result'], normal.outputs['Normal'])
    return mat


def hardwood_end_grain():
    """Saw-cut ends: growth rings around a pith outside the block, open pores, matte."""
    mat = bpy.data.materials.new('Oiled solid hardwood - end grain')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    coord = nodes.new('ShaderNodeTexCoord')
    shift = nodes.new('ShaderNodeMapping')
    shift.inputs['Location'].default_value = (0.0, -.19, .29)
    links.new(coord.outputs['Object'], shift.inputs['Vector'])
    rings = nodes.new('ShaderNodeTexWave')
    rings.wave_type = 'RINGS'
    rings.rings_direction = 'X'
    rings.wave_profile = 'SAW'
    rings.inputs['Scale'].default_value = 38.0
    rings.inputs['Distortion'].default_value = 1.6
    rings.inputs['Detail'].default_value = 4.0
    links.new(shift.outputs['Vector'], rings.inputs['Vector'])
    pores = nodes.new('ShaderNodeTexNoise')
    pores.inputs['Scale'].default_value = 900.0
    links.new(coord.outputs['Object'], pores.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .25
    ramp.color_ramp.elements[0].color = (.062, .034, .017, 1)
    ramp.color_ramp.elements[1].position = .85
    ramp.color_ramp.elements[1].color = (.125, .072, .038, 1)
    links.new(rings.outputs['Fac'], ramp.inputs['Fac'])
    speck = nodes.new('ShaderNodeMixRGB')
    speck.blend_type = 'MULTIPLY'
    speck.inputs[0].default_value = .35
    links.new(ramp.outputs['Color'], speck.inputs[1])
    links.new(pores.outputs['Color'], speck.inputs[2])
    height = nodes.new('ShaderNodeMath')
    height.operation = 'ADD'
    links.new(rings.outputs['Fac'], height.inputs[0])
    links.new(pores.outputs['Fac'], height.inputs[1])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .25
    bump.inputs['Distance'].default_value = .0003
    links.new(height.outputs[0], bump.inputs['Height'])
    value = nodes.new('ShaderNodeValue')
    value.outputs[0].default_value = .72
    edge_wear(mat, bs, speck.outputs['Color'], value.outputs[0], bump.outputs['Normal'])
    return mat


def foam_material():
    """Yellow open-cell polyurethane: pore cells, slight tonal drift, faint subsurface."""
    mat = material('Yellow open-cell polyurethane foam', (.92, .62, .08), .93)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    bs.inputs['Subsurface Weight'].default_value = .03
    bs.inputs['Subsurface Radius'].default_value = (.004, .003, .001)
    coord = nodes.new('ShaderNodeTexCoord')
    pores = nodes.new('ShaderNodeTexVoronoi')
    pores.feature = 'DISTANCE_TO_EDGE'
    pores.inputs['Scale'].default_value = 260.0
    links.new(coord.outputs['Object'], pores.inputs['Vector'])
    big = nodes.new('ShaderNodeTexVoronoi')
    big.feature = 'DISTANCE_TO_EDGE'
    big.inputs['Scale'].default_value = 95.0
    links.new(coord.outputs['Object'], big.inputs['Vector'])
    cells = nodes.new('ShaderNodeMath')
    cells.operation = 'MINIMUM'
    links.new(pores.outputs['Distance'], cells.inputs[0])
    links.new(big.outputs['Distance'], cells.inputs[1])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .0
    ramp.color_ramp.elements[0].color = (.30, .16, .01, 1)
    ramp.color_ramp.elements[1].position = .05
    ramp.color_ramp.elements[1].color = (.92, .60, .07, 1)
    links.new(cells.outputs[0], ramp.inputs['Fac'])
    drift = nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value = 12.0
    links.new(coord.outputs['Object'], drift.inputs['Vector'])
    tone = nodes.new('ShaderNodeMixRGB')
    tone.blend_type = 'MULTIPLY'
    tone.inputs[0].default_value = .18
    links.new(ramp.outputs['Color'], tone.inputs[1])
    links.new(drift.outputs['Color'], tone.inputs[2])
    links.new(tone.outputs['Color'], bs.inputs['Base Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .55
    bump.inputs['Distance'].default_value = .0008
    links.new(cells.outputs[0], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bs.inputs['Normal'])
    return mat


def scouring_material():
    """Green non-woven scouring layer: tangled fibres, dark gaps."""
    mat = material('Green non-woven scouring pad', (.02, .09, .02), .97)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    coord = nodes.new('ShaderNodeTexCoord')
    fibres = nodes.new('ShaderNodeTexNoise')
    fibres.noise_dimensions = '4D'
    fibres.inputs['Scale'].default_value = 140.0
    fibres.inputs['Detail'].default_value = 8.0
    fibres.inputs['Roughness'].default_value = .85
    fibres.inputs['Distortion'].default_value = 1.4
    links.new(coord.outputs['Object'], fibres.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .38
    ramp.color_ramp.elements[0].color = (.004, .018, .003, 1)
    ramp.color_ramp.elements[1].position = .62
    ramp.color_ramp.elements[1].color = (.035, .15, .028, 1)
    links.new(fibres.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], bs.inputs['Base Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .9
    bump.inputs['Distance'].default_value = .0012
    links.new(fibres.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bs.inputs['Normal'])
    return mat


def wooden_block(name, dims, long_grain, end_grain, edge):
    """Exact collision box (render-only edge radius); UVs put the grain along x, end grain on the x faces."""
    mesh = bpy.data.meshes.new(name)
    hx, hy, hz = (d / 2 for d in dims)
    verts = [(sx * hx, sy * hy, sz * hz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.materials.append(long_grain)
    mesh.materials.append(end_grain)
    uv = mesh.uv_layers.new(name='Grain UV')
    tile = 2.0  # dark_wood is a 2 m x 2 m scan
    for poly in mesh.polygons:
        n = poly.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        poly.material_index = 1 if axis == 0 else 0
        for li in poly.loop_indices:
            v = mesh.vertices[mesh.loops[li].vertex_index].co
            u, w = (v.y, v.z) if axis == 0 else ((v.x, v.z) if axis == 1 else (v.x, v.y))  # grain (texture u) along x
            uv.data[li].uv = (u / tile + .37, w / tile + .21)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bevel = obj.modifiers.new('Machined edge radius - render only', 'BEVEL')
    bevel.width = edge
    bevel.segments = 3
    bevel.harden_normals = True
    obj.rotation_mode = 'QUATERNION'
    obj['collision_proxy'] = 'exact unbevelled box in the native ABD solve'
    return obj


def key_rigid(obj, transforms):
    for frame, T in enumerate(transforms, 1):
        M = Matrix(T.tolist())
        obj.location = M.to_translation()
        obj.rotation_quaternion = M.to_quaternion()
        obj.keyframe_insert('location', frame=frame)
        obj.keyframe_insert('rotation_quaternion', frame=frame)
    for fc in obj.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'


def sponge_object(z, mats):
    """The native FEM exterior; one absolute shape key per cached state."""
    pos, rest, faces = z['elastic_positions'], z['elastic_rest_positions'], z['elastic_surface_faces']
    if len(rest) == 0:
        return None
    mesh = bpy.data.meshes.new('Native tetrahedral exterior')
    mesh.from_pydata(pos[0].tolist(), [], faces.tolist())
    for mat in mats:
        mesh.materials.append(mat)
    top_cut = float(rest[:, 2].min() + .93 * (rest[:, 2].max() - rest[:, 2].min()))
    for poly, face in zip(mesh.polygons, faces):
        poly.use_smooth = False
        poly.material_index = 1 if float(rest[face, 2].mean()) >= top_cut else 0
    obj = bpy.data.objects.new('Open-cell sponge - native FEM exterior', mesh)
    bpy.context.collection.objects.link(obj)
    obj.shape_key_add(name='Basis')
    obj.data.shape_keys.use_relative = False
    for i, p in enumerate(pos):
        key = obj.shape_key_add(name=f'Native_{i:04d}')
        key.data.foreach_set('co', np.asarray(p, np.float32).ravel())
    keys = obj.data.shape_keys
    keys.eval_time = 10
    keys.keyframe_insert('eval_time', frame=1)
    keys.eval_time = len(pos) * 10
    keys.keyframe_insert('eval_time', frame=len(pos))
    for fc in keys.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    bevel = obj.modifiers.new('Soft 3 mm sponge edge radius - render surface', 'BEVEL')
    bevel.width = .003
    bevel.segments = 4
    sub = obj.modifiers.new('Pore-scale refinement', 'SUBSURF')
    sub.subdivision_type = 'SIMPLE'
    sub.levels = sub.render_levels = 1
    tex = bpy.data.textures.new('Torn foam microprofile', type='CLOUDS')
    tex.noise_scale = .006
    tex.noise_depth = 2
    disp = obj.modifiers.new('Sub-millimetre foam surface', 'DISPLACE')
    disp.texture = tex
    disp.texture_coords = 'GLOBAL'
    disp.strength = .0007
    disp.mid_level = .5
    obj['motion_source'] = 'libuipc StableNeoHookean FEM cache'
    obj['fixed_vertex_count'] = 0
    return obj


def setup_render(scene, args, spec, frame_step, delivered):
    scene.render.engine = 'CYCLES'
    cy = scene.cycles
    cy.device = 'GPU' if args.device == 'gpu' else 'CPU'
    cy.samples = args.samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = .01
    cy.use_denoising = True
    cy.denoiser = 'OPENIMAGEDENOISE'
    cy.max_bounces = 10
    cy.diffuse_bounces = 6
    cy.glossy_bounces = 6
    cy.sample_clamp_indirect = 10.0
    cy.seed = 0
    scene.render.resolution_x = args.width
    scene.render.resolution_y = round(args.width * 9 / 16)
    scene.render.resolution_percentage = 100
    scene.render.fps = spec['display_fps']
    scene.frame_start, scene.frame_step = 1, frame_step
    scene.frame_end = 1 + frame_step * (delivered - 1)
    # Motion blur of a 1/96 s exposure. The timeline runs at the 240 Hz native
    # rate, so the shutter is given in native frames. Persistent data stays off:
    # with motion blur it drops objects that came to rest (Blender 4.3).
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = spec['fps'] / 96.0
    scene.render.use_persistent_data = False
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Base Contrast'
    scene.view_settings.exposure = args.exposure
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.compression = 15
    if args.device == 'cpu':
        return 'CPU'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for kind in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            devices = [d for d in prefs.devices if d.type == kind]
        except Exception:
            devices = []
        if devices:
            for d in prefs.devices:
                d.use = d in devices[:1]
            return kind
    raise RuntimeError('No CUDA-visible Cycles GPU')


def encode(frames, video, fps):
    """H.264 yuv420p, CRF 16, constant 24 FPS, from the PNG frames (also run by tools/publish_suite.py encode)."""
    encoder = os.environ.get('PCVE_FFMPEG', 'ffmpeg')
    subprocess.run([encoder, '-y', '-framerate', str(fps), '-pattern_type', 'glob', '-i', str(Path(frames) / 'frame_*.png'),
                    '-c:v', 'libx264', '-crf', '16', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                    str(video)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--case', required=True)
    ap.add_argument('--samples', type=int, default=256)
    ap.add_argument('--width', type=int, default=1280)
    ap.add_argument('--exposure', type=float, default=1.0)
    ap.add_argument('--device', choices=('gpu', 'cpu'), default='gpu',
                    help='gpu: OptiX/CUDA on the one GPU in CUDA_VISIBLE_DEVICES; cpu: all threads given to Blender (-t)')
    ap.add_argument('--no-encode', action='store_true', help='write the 96 PNG frames only (encode later on a host with ffmpeg)')
    ap.add_argument('--cache-record', help='cache path to record in render_report.json (default: --cache as given)')
    ap.add_argument('--preview-frame', type=int, action='append',
                    help='render only these video frames (1..96) as PNG stills; repeatable')
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    a = ap.parse_args(argv)
    if sys.platform != 'linux' or (a.device == 'gpu' and not os.environ.get('CUDA_VISIBLE_DEVICES')):
        raise RuntimeError('Linux host; GPU renders need one GPU bound through CUDA_VISIBLE_DEVICES')
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    z = np.load(a.cache, allow_pickle=False)
    spec = json.loads((HERE.parent / 'scene_spec.json').read_text())
    p = dict(spec['baseline'])
    # A case outside scene_spec.json (a staged DELETE) takes its resolved physics from the solve's configuration.
    p.update(spec['cases'][a.case] if a.case in spec['cases']
             else json.loads(Path(a.cache).with_name('simulation_config.json').read_text())['physics'])
    frame_step = round(spec['fps'] * spec['playback_time_scale'] / spec['display_fps'])
    delivered = round(spec['duration_s'] / spec['playback_time_scale'] * spec['display_fps'])
    if 1 + frame_step * (delivered - 1) > len(z['times']):
        raise RuntimeError('The native cache does not contain the delivered sample times')
    if (out / 'video.mp4').exists() and not a.preview_frame:
        raise FileExistsError(out / 'video.mp4')

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    device = setup_render(scene, a, spec, frame_step, delivered)
    look = room.build(scene, p)
    long_grain, end_grain = hardwood_long_grain(), hardwood_end_grain()
    sponge_object(z, [foam_material(), scouring_material()])
    if p.get('block_present', True):  # DELETE wood_block: no block in the scene
        block = wooden_block('Wooden block', p['block_dimensions_m'], long_grain, end_grain, .003)
        key_rigid(block, z['block_transforms'])
    if p['added_block_present'] and len(z['added_block_transforms']):
        added = wooden_block('Small wooden block', p['added_block_dimensions_m'], long_grain, end_grain, .003)
        key_rigid(added, z['added_block_transforms'])
    import pcve_realism_kit as kit
    kit.lens_finish(scene, vignette=.10, dispersion=.002)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'scene.blend'), compress=True)
    bpy.ops.file.make_paths_relative()  # textures resolve wherever the repository tree is checked out
    bpy.ops.wm.save_mainfile(compress=True)

    start = time.monotonic()
    if a.preview_frame:
        rendered = []
        for i in a.preview_frame:
            scene.frame_set(1 + frame_step * (i - 1))
            scene.render.filepath = str(out / f'still_{i:02d}.png')
            bpy.ops.render.render(write_still=True)
            rendered.append(i)
    else:
        frames = out / 'frames'
        frames.mkdir(exist_ok=True)
        scene.render.filepath = str(frames / 'frame_')
        bpy.ops.render.render(animation=True)
        if not a.no_encode:
            encode(frames, out / 'video.mp4', spec['display_fps'])
        rendered = list(range(1, delivered + 1))
    native = [1 + frame_step * (i - 1) for i in rendered]
    report = {
        'status': 'preview_complete' if a.preview_frame else ('frames_complete' if a.no_encode else 'complete'), 'case_id': a.case,
        'edit_dsl': case_dsl(a.case), 'scene_id': spec['scene_id'], 'revision': spec['revision'],
        'appearance': 'appearance/render.py + appearance/room.py (dining-room corner, daylight)',
        'video_frames': rendered, 'rendered_native_frames': native,
        'delivered_sample_times_s': [float(z['times'][f - 1]) for f in native],
        'resolution': [scene.render.resolution_x, scene.render.resolution_y], 'cycles_samples': a.samples,
        'denoiser': 'OpenImageDenoise', 'motion_blur_shutter_s': 1 / 96, 'exposure': a.exposure,
        'physical_sample_fps': spec['fps'], 'encoded_display_fps': spec['display_fps'],
        'playback_time_scale': spec['playback_time_scale'], 'media_contract': spec.get('media_contract'),
        'cache': a.cache_record or str(a.cache), 'cache_sha256': sha(a.cache), 'device': device,
        'execution_host': socket.gethostname().split('.')[0], 'gpu_uuid': os.environ.get('CUDA_VISIBLE_DEVICES'),
        'blender': bpy.app.version_string, 'wall_seconds': time.monotonic() - start, 'look': look,
    }
    (out / 'render_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('RENDER_COMPLETE', a.case, report['status'], flush=True)


if __name__ == '__main__':
    main()
