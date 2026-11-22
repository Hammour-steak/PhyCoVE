"""Pack a normal Blender animation with sampled liquid and image sequences.

Primary water is exact source geometry. Native secondary point primitives are
represented by small smooth UV sphere meshes; the delivered video always uses
the original source's point renderer. No Python auto-run is needed for playback.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render_apple_drop_kitchen_basin as renderer


def signature():
    s = bpy.context.scene
    return {'camera_matrix': [list(x) for x in s.camera.matrix_world],
        'camera_lens': s.camera.data.lens, 'resolution': [s.render.resolution_x, s.render.resolution_y],
        'samples': s.cycles.samples, 'threshold': s.cycles.adaptive_threshold,
        'exposure': s.view_settings.exposure, 'look': s.view_settings.look,
        'shutter': s.render.motion_blur_shutter, 'fps': s.render.fps,
        'lights': {o.name: {'matrix': [list(x) for x in o.matrix_world],
            'energy': o.data.energy, 'color': list(o.data.color)} for o in s.objects if o.type == 'LIGHT'},
        'basin_matrix': [list(x) for x in bpy.data.objects['PCVE_BlenderKit_Basin'].matrix_world]}


def sphere_template():
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=1.)
    obj = bpy.context.object
    mesh = obj.data
    v = np.array([x.co[:] for x in mesh.vertices], np.float32)
    # Keep triangle tessellation constant for simple vectorized replication.
    mesh.calc_loop_triangles()
    t = np.array([x.vertices[:] for x in mesh.loop_triangles], np.int32)
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)
    return v, t


def native_points(obj, material, template):
    mesh = obj.data
    n = len(mesh.vertices)
    pos = np.empty(n * 3, np.float32)
    mesh.vertices.foreach_get('co', pos)
    radius = np.empty(n, np.float32)
    fade = np.empty(n, np.float32)
    mesh.attributes['radius'].data.foreach_get('value', radius)
    mesh.attributes['fade'].data.foreach_get('value', fade)
    base, tri = template
    vertices = (pos.reshape(-1, 1, 3) + radius[:, None, None] * base[None]).reshape(-1, 3)
    faces = (tri[None] + np.arange(n, dtype=np.int32)[:, None, None] * len(base)).reshape(-1, 3)
    result = bpy.data.meshes.new(obj.name + '_Spheres')
    result.vertices.add(len(vertices))
    result.vertices.foreach_set('co', vertices.ravel())
    result.loops.add(faces.size)
    result.loops.foreach_set('vertex_index', faces.ravel())
    result.polygons.add(len(faces))
    result.polygons.foreach_set('loop_start', np.arange(0, faces.size, 3, dtype=np.int32))
    result.polygons.foreach_set('loop_total', np.full(len(faces), 3, np.int32))
    result.polygons.foreach_set('use_smooth', np.ones(len(faces), np.bool_))
    result.update(calc_edges=True)
    color = result.color_attributes.new(name='fade', type='FLOAT_COLOR', domain='CORNER')
    rgba = np.ones((faces.size, 4), np.float32)
    rgba[:, :3] = np.repeat(fade, len(tri) * 3)[:, None]
    color.data.foreach_set('color', rgba.ravel())
    result.materials.append(material)
    obj.data = result
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    run = a.run.resolve()
    dest = run / 'native'
    dest.mkdir(exist_ok=True)
    cache_dir = dest / 'cache'
    cache_dir.mkdir(exist_ok=True)
    report = json.loads((run / 'simulation_report.json').read_text())
    event_frame = report['event']['frame']
    opts = SimpleNamespace(cpu_threads=8, dry_run=True, gpu_backend='CUDA', samples=1024,
        resolution=[1280, 720], shutter=.5, exposure=.7)
    apple, offset, water, material, points, setup = renderer.build_scene(opts, report['info']['apple']['start_m'])
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end, scene.render.fps = 1, 96, 24
    frozen = signature()
    for row in report['frames']:
        apple.location = np.asarray(row['ball_center']) + np.array(offset)
        apple.keyframe_insert('location', frame=row['frame'])
    images = renderer.wet_layer(run / 'aniso/wet_0001.npz')
    names = [water.name] + [o.name for o in points.values()]
    if event_frame > 1:
        holders = renderer.bead_holders()
        template = sphere_template()
        materials = {kind: obj.modifiers['Points'].node_group.nodes.get('Set Material').inputs['Material'].default_value
                     for kind, obj in points.items()}
        for obj in points.values():
            obj.modifiers.remove(obj.modifiers['Points'])
        objects = {'water': water, **points}
        materials['water'] = material
        for obj in objects.values():
            marker = obj.modifiers.new('Export time sampling marker', 'DISPLACE')
            marker.strength = 0
            marker.show_viewport = marker.show_render = False
        # Image sequences supply native animated wet coats without handlers.
        for f in range(1, 97):
            renderer.load_wet(run / 'aniso' / f'wet_{f:04d}.npz', images)
            for key, image in images.items():
                path = cache_dir / f'{key}_{f:04d}.exr'
                image.file_format = 'OPEN_EXR'
                image.filepath_raw = str(path)
                if not path.exists():
                    image.save()
        def load(f):
            renderer.load_water(run / 'aniso' / f'water_{f:04d}.npz', water, material)
            # Alembic identifies geometry by data name. Per-frame NPZ names
            # would create 48 separate static children instead of one stream.
            water.data.name = 'LiquidSampledMesh'
            for kind, obj in points.items():
                path = run / 'aniso' / f'{kind}_{f:04d}.npz'
                if kind == 'beads':
                    renderer.load_beads(path, obj, holders)
                else:
                    renderer.load_points(path, obj)
                native_points(obj, materials[kind], template)
        def frame_handler(s, *_):
            f = int(s.frame_current)
            if 1 <= f < event_frame:
                load(f)
        scene.frame_set(1)
        load(1)
        bpy.app.handlers.frame_change_pre.append(frame_handler)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects.values():
            obj.select_set(True)
        bpy.context.view_layer.objects.active = water
        abc = cache_dir / 'liquid_prefix.abc'
        start = time.monotonic()
        try:
            bpy.ops.wm.alembic_export(filepath=str(abc), start=1, end=event_frame - 1,
                selected=True, visible_objects_only=False, flatten=True,
                uvs=False, normals=True, vcolors=True, face_sets=False,
                export_hair=False, export_particles=False, as_background_job=False,
                use_instancing=False, xsamples=1, gsamples=1, evaluation_mode='RENDER')
        finally:
            bpy.app.handlers.frame_change_pre.remove(frame_handler)
        seconds = time.monotonic() - start
        for obj in list(objects.values()):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        old = set(bpy.data.objects)
        bpy.ops.wm.alembic_import(filepath=str(abc), relative_path=True, set_frame_range=False,
            always_add_cache_reader=True, as_background_job=False)
        imported = set(bpy.data.objects) - old
        for kind, name in zip(['water'] + list(points), names):
            obj = next(o for o in imported if o.type == 'MESH' and o.name.startswith(name))
            obj.data.materials.clear()
            obj.data.materials.append(materials[kind])
            obj['PCVE_kind'] = kind
            for f, hidden in [(1, False), (event_frame - 1, False), (event_frame, True), (96, True)]:
                obj.hide_render = obj.hide_viewport = hidden
                obj.keyframe_insert('hide_render', frame=f)
                obj.keyframe_insert('hide_viewport', frame=f)
            for curve in obj.animation_data.action.fcurves:
                for key in curve.keyframe_points:
                    key.interpolation = 'CONSTANT'
        for key, image in images.items():
            first = cache_dir / f'{key}_0001.exr'
            sequence = bpy.data.images.load(str(first), check_existing=False)
            sequence.source = 'SEQUENCE'
            sequence.colorspace_settings.name = 'Non-Color'
            for mat in bpy.data.materials:
                for node in (mat.node_tree.nodes if mat.use_nodes else []):
                    if node.type == 'TEX_IMAGE' and node.image == image:
                        node.image = sequence
                        node.image_user.frame_start = 1
                        node.image_user.frame_duration = 96
                        node.image_user.use_auto_refresh = True
        scene['PCVE_liquid_cache_seconds'] = seconds
    else:
        for obj in [water, *points.values()]:
            bpy.data.objects.remove(obj, do_unlink=True)
    scene.frame_set(1)
    scene['PCVE_case'] = report['case']
    scene['PCVE_water_removal_time_s'] = report['event']['time_s']
    scene['PCVE_physics'] = json.dumps(report['physics'])
    scene['PCVE_native_notes'] = 'Exact primary water; secondary point spheres tessellated for native Alembic. Original point renderer used in MP4.'
    scene['PCVE_apple_motion_model'] = 'Source smooth spherical rigid apple, translation only.'
    scene.render.filepath = '//render/0001.png'
    assert signature() == frozen
    # Pack all ordinary textures; animated image sequences remain relative files.
    for image in bpy.data.images:
        if image.source == 'FILE' and image.filepath and not image.packed_file:
            image.pack()
    blend = dest / 'scene_animation.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
    for c in bpy.data.cache_files:
        c.filepath = bpy.path.relpath(str(abc))
    for image in bpy.data.images:
        if image.source == 'SEQUENCE':
            image.filepath = bpy.path.relpath(image.filepath)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
    (dest / 'native_manifest.json').write_text(json.dumps({'case': report['case'],
        'blender': bpy.app.version_string, 'frame_count': 96, 'water_removal_frame': event_frame,
        'static_scene': frozen, 'native': str(blend), 'python_auto_run_required': False,
        'primary_water_exact': True, 'native_secondary_representation': 'Smooth UV spheres; original MP4 uses exact source point primitives.',
        'cache_files': [c.filepath for c in bpy.data.cache_files]}, indent=2))
    print('NATIVE_PACKED', report['case'], flush=True)


if __name__ == '__main__':
    main()
