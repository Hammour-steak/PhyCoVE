"""Build the breakfast room, replay the verified rigid-body poses and render the four-second clip."""
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
from validate_kitchen_orange_collision import validate_cache
from scene_geometry import KEYS
from look_kitchen_orange_collision import build_environment, make_oranges, used_assets
from sunlit_dining_room import set_dressing_trees, check_clearance, check_occlusion
from pcve_render_quality import configure_renderer, configure_color
from pcve_assets import asset as _pcve_asset

# AgX for a sunlit room: the sun patch on the linen sits about three stops over
# the skylit near end of the table, which AgX rolls off where Standard clips.
EXPOSURE = 0.75
# Quarter-turn shutter: a rolling orange smears a little, as on a film camera,
# while a 7 m/s throw stays a solid orange rather than a translucent streak.
SHUTTER = .25


def render(args):
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view
    if args.samples < 1 or min(args.resolution) < 1:
        raise ValueError('Invalid render settings')
    out = args.out_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    physics = args.physics_json.resolve() if args.physics_json else out / 'physics_transforms.json'
    scenario_keys = ('scenario_json', 'scenario_overrides_json', *PHYSICS_LIMITS, 'fps', 'duration_sec', 'slow_motion')
    if args.physics_json:
        if any(getattr(args, k) is not None for k in scenario_keys):
            raise ValueError('Resimulate before changing cached initial conditions/timing')
    else:
        command = [str(args.physics_python or python_for('physics')),
                   str(Path(__file__).with_name('simulate_kitchen_orange_collision.py')), '--out', str(physics)]
        for key in scenario_keys:
            value = getattr(args, key)
            if value is not None:
                command += ['--' + key.replace('_', '-'), str(value)]
        subprocess.run(command, check=True)
    data = json.loads(physics.read_text(encoding='utf-8'))
    validate_cache(data)
    if physics != out / 'physics_transforms.json':
        shutil.copy2(physics, out / 'physics_transforms.json')
    (out / 'simulation_metrics.json').write_text(json.dumps(data['quality'], indent=2), encoding='utf-8')

    s = deepcopy(data['scenario'])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    device = configure_renderer(bpy, scene, args)
    configure_color(scene)
    scene.view_settings.exposure = EXPOSURE
    if scene.render.engine == 'CYCLES':
        # OpenImageDenoise with albedo and normal guides on every device.
        scene.cycles.denoiser = 'OPENIMAGEDENOISE'
        scene.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
        scene.cycles.denoising_prefilter = 'ACCURATE'
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = SHUTTER
    # Blender 4.3 drops objects that have come to rest from later frames of the
    # same session when persistent data is on together with motion blur, so it
    # is off here (configure_renderer turns it on).
    scene.render.use_persistent_data = False
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = data['playback_fps']
    scene.frame_start = 1
    scene.frame_end = data['frame_end']
    # The cloth is generated on the simulator's table box (sunlit_dining_room
    # refuses to build if its top is not the box's top face), so the fruit
    # rests on what it is drawn resting on.
    room = build_environment(bpy, scene)
    objects = make_oranges(bpy, s['physics']['rear_oranges'])
    for key, o in objects.items():
        o.hide_render = o.hide_viewport = not data['objects'].get(key, {}).get('present', False)
    for f in data['frames']:
        for key in KEYS:
            if not f[key]['present']:
                continue
            o = objects.get(key)
            if o is None:
                raise RuntimeError(f'No object for {key}; the scenario and the renderer disagree')
            state = f[key]
            o.location = state['location']
            q = state['quaternion_xyzw']
            o.rotation_mode = 'QUATERNION'
            o.rotation_quaternion = (q[3], q[0], q[1], q[2])
            o.keyframe_insert('location', frame=f['frame_index'])
            o.keyframe_insert('rotation_quaternion', frame=f['frame_index'])
    for o in objects.values():
        if o.animation_data is None:
            continue
        for curve in o.animation_data.action.fcurves:
            for k in curve.keyframe_points:
                k.interpolation = 'LINEAR'

    cam = s['camera']
    bpy.ops.object.camera_add(location=cam['location'])
    camera = bpy.context.object
    camera.name = 'Orange collision camera'
    camera.data.lens = cam['lens_mm']
    camera.rotation_euler = (Vector(cam['target']) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = (Vector(cam['target']) - camera.location).length
    camera.data.dof.aperture_fstop = 4.0
    scene.camera = camera
    bpy.context.view_layer.update()
    cm = [list(row) for row in camera.matrix_world]

    max_error = 0.
    min_screen_margin = 1.
    for f in data['frames']:
        scene.frame_set(f['frame_index'])
        bpy.context.view_layer.update()
        for key in KEYS:
            if not f[key]['present']:
                continue
            o = objects[key]
            max_error = max(max_error, max(abs(o.matrix_world[a][b] - f[key]['matrix_world'][a][b])
                                           for a in range(4) for b in range(4)))
            for corner in o.bound_box:
                uv = world_to_camera_view(scene, camera, o.matrix_world @ Vector(corner))
                if uv.z <= 0:
                    raise RuntimeError('Fruit behind camera')
                min_screen_margin = min(min_screen_margin, uv.x, 1 - uv.x, uv.y, 1 - uv.y)
    if max_error > 2e-6:
        raise RuntimeError(f'Blender replay differs from physics by {max_error}')
    # The set is not in the simulation: no piece of it may come within 2 cm of
    # a moving orange in any frame, and no piece of furniture may hide one.
    present = [k for k in KEYS if data['objects'][k]['present']]
    clearance = check_clearance(set_dressing_trees(bpy), data['frames'], present)
    occlusion = check_occlusion(bpy, scene, camera, data['frames'], present, objects)
    print(f'[render] clearance ok, closest: {clearance}', flush=True)
    print(f'[render] occlusion ok: {occlusion}', flush=True)
    # An edit that sends a heavier orange off the far end of the table also sends
    # it out of frame, which is the physical outcome rather than a render fault;
    # it is recorded in render_validation.json instead of aborting the render.
    framing_warning = ('fruit leaves the camera frame' if min_screen_margin < .02 else None)

    metadata = deepcopy(s)
    metadata['render'].update(resolution=args.resolution, samples=args.samples, engine=args.engine, device=device)
    metadata['render'].update(motion_blur_shutter=SHUTTER, view_transform=scene.view_settings.view_transform,
                              look=scene.view_settings.look, exposure=EXPOSURE)
    metadata['assets'] = used_assets()
    missing = [n for n in metadata['assets'] if not _pcve_asset(n).is_file()]
    if missing:
        raise FileNotFoundError(f'Missing assets: {missing}')
    gt = dict(schema_version=1, scene=data['scene'], fps=scene.render.fps, frame_start=1, frame_end=data['frame_end'],
              scenario=metadata, physics={k: v for k, v in data.items() if k != 'frames'},
              objects={k: dict(v, object_name=objects[k].name if k in objects else None) for k, v in data['objects'].items()},
              camera=dict(object_name=camera.name, matrix_world=cm, lens_mm=camera.data.lens,
                          sensor_width_mm=camera.data.sensor_width, resolution=args.resolution),
              sample_fps=data['sample_fps'], slow_motion=data['slow_motion'],
              physical_duration_sec=data['physical_duration_sec'],
              playback_duration_sec=data['playback_duration_sec'],
              frames=[dict(f, camera_matrix_world=cm) for f in data['frames']])
    for name, payload in [('ground_truth_transforms.json', gt), ('scenario_metadata.json', metadata),
                          ('render_validation.json', dict(
                              valid=True, checked_frames=len(data['frames']),
                              objects_checked=sum(v['present'] for v in data['objects'].values()),
                              max_matrix_error=max_error, min_screen_margin=min_screen_margin,
                              framing_warning=framing_warning,
                              set_clearance_closest_m=clearance, occlusion=occlusion, room=room))]:
        (out / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')

    preview = args.preview_frame or min(scene.frame_end,
                                        round(((data['quality']['first_impact_sec'] or 0) + .22) * data['sample_fps']) + 1)
    if not 1 <= preview <= scene.frame_end:
        raise ValueError('Preview frame outside trajectory')
    scene.frame_set(preview)
    bpy.ops.file.pack_all()
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(out / 'preview.png')
    if args.mode not in ('build', 'keyframes'):
        bpy.ops.render.render(write_still=True)
    if args.mode == 'keyframes':
        impact = math.ceil((data['quality']['first_impact_sec'] or 0) * data['sample_fps']) + 1
        indices = args.keyframes or [1, max(1, impact - 1), impact, impact + 5,
                                     round(2 * data['sample_fps']) + 1, scene.frame_end]
        if args.keyframes and any(not 1 <= i <= scene.frame_end for i in indices):
            raise ValueError('Keyframe outside trajectory')
        indices = sorted({min(scene.frame_end, i) for i in indices})
        for index in indices:
            scene.frame_set(index)
            scene.render.filepath = str(out / f'frame_{index:04d}.png')
            bpy.ops.render.render(write_still=True)
        shutil.copy2(out / f'frame_{min(indices, key=lambda i: abs(i - preview)):04d}.png', out / 'preview.png')
        (out / 'keyframes.json').write_text(json.dumps(
            [dict(frame=i, time_sec=(i - 1) / data['sample_fps'], file=f'frame_{i:04d}.png') for i in indices],
            indent=2), encoding='utf-8')
    if args.mode == 'animation':
        scene.render.image_settings.file_format = 'FFMPEG'
        scene.render.ffmpeg.format = 'MPEG4'
        scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'HIGH'
        scene.render.filepath = str(out / 'kitchen_orange_collision.mp4')
        scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'kitchen_orange_collision.blend'))
    if args.mode == 'animation':
        bpy.ops.render.render(animation=True)
        shutil.copy2(out / 'kitchen_orange_collision.mp4', out / 'video.mp4')


def main():
    p = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--physics-json', type=Path)
    p.add_argument('--physics-python', type=Path)
    p.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    p.add_argument('--samples', type=int, default=48)
    p.add_argument('--resolution', nargs=2, type=int, default=[960, 540])
    p.add_argument('--mode', choices=('build', 'preview', 'keyframes', 'animation'), default='keyframes')
    p.add_argument('--preview-frame', type=int)
    p.add_argument('--keyframes', nargs='+', type=int, help='Frame indices for --mode keyframes')
    render(parse_render_args(p))


if __name__ == '__main__':
    run_renderer(main, 'kitchen_orange_collision')
