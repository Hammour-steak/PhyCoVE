"""Import the bathroom, replay verified rigid-body poses and render the four-second clip."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        # This scene also renders from a Python that has the bpy module
        # (--render-python). Load bpy first for real runs so prepare_entry keeps
        # the render in this process instead of relaunching Blender; planning
        # calls (--help/--dry-run/--describe) stay import-free.
        if not {"-h", "--help", "--dry-run", "--describe"} & set(_sys.argv[1:]):
            try:
                import bpy  # noqa: F401
            except ImportError:
                pass
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
import subprocess
from pcve_scene_runtime import python_for, parse_render_args, run_renderer
from scene_config import add_scenario_arguments, PHYSICS_LIMITS
from validate_bathroom_stool_rebound import validate_cache
from scene_geometry import KEYS
from look_bathroom_stool_rebound import (build_environment, make_stools, set_visible, set_bathtub_visible,
                                         decor_for_checks, EXPOSURE)
from spa_dressing import check_props, DUSK_VIEW
from pcve_render_quality import configure_renderer, configure_color

# Motion-blur shutter as a fraction of the 1/24 s frame. 0.25 keeps a thrown
# stool crisp enough to read; longer turns the 18 m/s edit into a ghost.
SHUTTER = .25


def render(args):
    import bpy
    from mathutils import Vector
    if args.samples < 1 or min(args.resolution) < 1: raise ValueError('Invalid render settings')
    out = args.out_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    physics = args.physics_json.resolve() if args.physics_json else out / 'physics_transforms.json'
    scenario_keys = ('scenario_json', 'scenario_overrides_json', *PHYSICS_LIMITS, 'fps', 'duration_sec', 'slow_motion')
    if args.physics_json:
        if args.remove_bathtub or any(getattr(args, k) is not None for k in scenario_keys):
            raise ValueError('Resimulate before changing cached initial conditions/timing')
    else:
        command = [str(args.physics_python or python_for('physics')),
                   str(Path(__file__).with_name('simulate_bathroom_stool_rebound.py')), '--out', str(physics)]
        for key in scenario_keys:
            value = getattr(args, key)
            if value is not None: command += ['--' + key.replace('_', '-'), str(value)]
        if args.remove_bathtub: command += ['--remove-bathtub']
        subprocess.run(command, check=True)
    data = json.loads(physics.read_text(encoding='utf-8')); validate_cache(data)
    if physics != out / 'physics_transforms.json': shutil.copy2(physics, out / 'physics_transforms.json')
    (out / 'simulation_metrics.json').write_text(json.dumps(data['quality'], indent=2), encoding='utf-8')
    s = deepcopy(data['scenario'])
    bpy.ops.wm.read_factory_settings(use_empty=True); scene = bpy.context.scene
    device = configure_renderer(bpy, scene, args); configure_color(scene)
    scene.view_settings.exposure = EXPOSURE
    scene.render.resolution_x, scene.render.resolution_y = args.resolution; scene.render.resolution_percentage = 100
    scene.render.fps = data['playback_fps']; scene.frame_start = 1; scene.frame_end = data['frame_end']
    # Blender 4.3: with motion blur on, persistent data makes a body that has
    # come to rest vanish from later frames rendered in the same session, so
    # persistent data stays off whenever the shutter is open.
    scene.render.use_motion_blur = True; scene.render.motion_blur_shutter = SHUTTER
    scene.render.use_persistent_data = False
    env = build_environment(bpy, scene); objects = make_stools(bpy, env['imported'])
    for key, o in objects.items():
        set_visible(o, data['objects'][key]['present'])
    if not s['physics']['bathtub_active'][0]:
        set_bathtub_visible(bpy, False)
    for f in data['frames']:
        for key in KEYS:
            if not f[key]['present']: continue
            o = objects[key]; state = f[key]
            o.location = state['location']; q = state['quaternion_xyzw']
            o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = (q[3], q[0], q[1], q[2])
            o.keyframe_insert('location', frame=f['frame_index']); o.keyframe_insert('rotation_quaternion', frame=f['frame_index'])
    for o in objects.values():
        if o.animation_data is None: continue
        for curve in o.animation_data.action.fcurves:
            for k in curve.keyframe_points: k.interpolation = 'LINEAR'
    cam = s['camera']; bpy.ops.object.camera_add(location=cam['location']); camera = bpy.context.object
    camera.name = 'Bathroom stool camera'; camera.data.lens = cam['lens_mm']
    camera.rotation_euler = (Vector(cam['target']) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.dof.use_dof = True; camera.data.dof.focus_distance = (Vector(cam['target']) - camera.location).length
    camera.data.dof.aperture_fstop = 8.; scene.camera = camera
    bpy.context.view_layer.update(); cm = [list(row) for row in camera.matrix_world]
    max_error = 0.
    for f in data['frames']:
        scene.frame_set(f['frame_index']); bpy.context.view_layer.update()
        for key in KEYS:
            if not f[key]['present']: continue
            max_error = max(max_error, max(abs(objects[key].matrix_world[a][b] - f[key]['matrix_world'][a][b])
                                           for a in range(4) for b in range(4)))
    if max_error > 2e-6: raise RuntimeError(f'Blender replay differs from physics by {max_error}')
    # Props are not simulated: none may come within 2 cm of a stool in any
    # frame, and none may hide a stool from the camera.
    prop_report = check_props(bpy, scene, camera, {k: o for k, o in objects.items() if data['objects'][k]['present']},
                              data['frames'], decor_for_checks(bpy, env['placed']))
    metadata = deepcopy(s)
    metadata['render'].update(resolution=args.resolution, samples=args.samples, engine=args.engine, device=device, mode=args.mode,
                              motion_blur_shutter=SHUTTER)
    metadata['assets'] = {'bathroom': 'assets/models/big_project.glb (room shell, vanity, mirror, bathtub, fittings)',
                          'stool': "the GLB's own tall stool (Cube.045 assembly: seat slab + three splayed legs) re-dressed as oiled teak on blackened bronze; lower slab Cube.046 and coffee cup removed",
                          'polyhaven': 'assets/polyhaven/bathroom_stool_rebound (scanned stone/wood textures, props, window view ' + DUSK_VIEW + ')'}
    metadata['prop_clearance'] = prop_report
    gt = dict(schema_version=1, scene=data['scene'], fps=scene.render.fps, frame_start=1, frame_end=data['frame_end'],
              scenario=metadata, physics={k: v for k, v in data.items() if k != 'frames'},
              objects={k: dict(v, object_name=objects[k].name) for k, v in data['objects'].items()},
              camera=dict(object_name=camera.name, matrix_world=cm, lens_mm=camera.data.lens,
                          sensor_width_mm=camera.data.sensor_width, resolution=args.resolution),
              sample_fps=data['sample_fps'], slow_motion=data['slow_motion'],
              physical_duration_sec=data['physical_duration_sec'], playback_duration_sec=data['playback_duration_sec'],
              frames=[dict(f, camera_matrix_world=cm) for f in data['frames']])
    for name, payload in [('ground_truth_transforms.json', gt), ('scenario_metadata.json', metadata),
                          ('render_validation.json', dict(valid=True, checked_frames=len(data['frames']),
                                                          objects_checked=sum(v['present'] for v in data['objects'].values()),
                                                          max_matrix_error=max_error))]:
        (out / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    preview = args.preview_frame or min(scene.frame_end, round(((data['quality']['first_impact_sec'] or 0) + .22) * data['sample_fps']) + 1)
    if not 1 <= preview <= scene.frame_end: raise ValueError('Preview frame outside trajectory')
    scene.frame_set(preview); bpy.ops.file.pack_all()
    scene.render.image_settings.file_format = 'PNG'; scene.render.filepath = str(out / 'preview.png')
    if args.mode not in ('build', 'keyframes'): bpy.ops.render.render(write_still=True)
    if args.mode == 'keyframes':
        impact = math.ceil((data['quality']['first_impact_sec'] or 0) * data['sample_fps']) + 1
        indices = args.keyframes or [1, max(1, impact - 1), impact, impact + 5, round(2 * data['sample_fps']) + 1, round(3 * data['sample_fps']) + 1]
        if args.keyframes and any(not 1 <= i <= scene.frame_end for i in indices): raise ValueError('Keyframe outside trajectory')
        indices = sorted({min(scene.frame_end, i) for i in indices})
        for index in indices:
            scene.frame_set(index); scene.render.filepath = str(out / f'frame_{index:04d}.png'); bpy.ops.render.render(write_still=True)
        shutil.copy2(out / f'frame_{min(indices, key=lambda i: abs(i - preview)):04d}.png', out / 'preview.png')
        (out / 'keyframes.json').write_text(json.dumps([dict(frame=i, time_sec=(i - 1) / data['sample_fps'],
                                                             file=f'frame_{i:04d}.png') for i in indices], indent=2), encoding='utf-8')
    if args.mode == 'animation':
        scene.render.image_settings.file_format = 'FFMPEG'; scene.render.ffmpeg.format = 'MPEG4'; scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'HIGH'; scene.render.filepath = str(out / 'bathroom_stool_rebound.mp4')
        scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'bathroom_stool_rebound.blend'))
    if args.mode == 'animation':
        bpy.ops.render.render(animation=True); shutil.copy2(out / 'bathroom_stool_rebound.mp4', out / 'video.mp4')


def main():
    p = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    p.add_argument('--out-dir', type=Path, required=True); p.add_argument('--physics-json', type=Path)
    p.add_argument('--physics-python', type=Path); p.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto'); p.add_argument('--samples', type=int, default=48)
    p.add_argument('--resolution', nargs=2, type=int, default=[1280, 720])
    p.add_argument('--mode', choices=('build', 'preview', 'keyframes', 'animation'), default='keyframes')
    p.add_argument('--preview-frame', type=int)
    p.add_argument('--keyframes', nargs='+', type=int, help='Frame indices for --mode keyframes')
    render(parse_render_args(p))


if __name__ == '__main__':
    run_renderer(main, 'bathroom_stool_rebound')
