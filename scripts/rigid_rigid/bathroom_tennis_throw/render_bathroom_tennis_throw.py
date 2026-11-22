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
from scene_config import add_scenario_arguments
from validate_bathroom_tennis_throw import validate_cache
from scene_geometry import KEYS
from look_bathroom_tennis_throw import (build_environment, make_objects, check_clearance, check_occlusion,
                                        MODELS, POLYHAVEN)
from pcve_render_quality import configure_renderer, configure_color

# AgX Medium High Contrast (shared configure_color) exposed for a room lit by
# one sunny window: the sun patch sits near the top of the curve, the shaded
# tiles in the mid-tones.
EXPOSURE = .85


def render(args):
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view
    if args.fps is not None or args.duration_sec is not None:
        raise ValueError('Use scenario JSON for the sampling fps; clip duration is fixed at four seconds')
    if args.samples < 1 or min(args.resolution) < 1:
        raise ValueError('Invalid render settings')
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    physics = args.physics_json.resolve() if args.physics_json else out / 'physics_transforms.json'
    scenario_keys = ('scenario_json', 'scenario_overrides_json', 'initial_velocity', 'ball_mass', 'stool_mass', 'aim_shift', 'gravity_z')
    if args.physics_json:
        if any(getattr(args, k) is not None for k in scenario_keys):
            raise ValueError('Resimulate before changing cached initial conditions/timing')
    else:
        command = [str(args.physics_python or python_for('physics')),
                   str(Path(__file__).with_name('simulate_bathroom_tennis_throw.py')), '--out', str(physics)]
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
    if scene.render.engine == 'CYCLES':
        # OIDN everywhere (same denoiser on every GPU/CPU the suite is split
        # across, so the grain-to-detail trade-off matches between cases).
        scene.cycles.denoiser = 'OPENIMAGEDENOISE'
        # Camera rays cross up to five 10 mm panes (two faces each) on the way
        # into the shower; the default 8 transparent bounces would turn the
        # far end of the enclosure black.
        scene.cycles.transparent_max_bounces = 32
        scene.cycles.caustics_reflective = False
        scene.cycles.caustics_refractive = False
        scene.cycles.blur_glossy = .5
    configure_color(scene)
    scene.view_settings.exposure = EXPOSURE
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = data['playback_fps']
    if args.motion_blur:
        # A quarter-frame shutter (1/96 s): the 14 m/s ball smears over about
        # 1.5 of its diameters instead of strobing 5.8 diameters apart, without
        # thinning into a translucent streak.
        scene.render.use_motion_blur = True
        scene.render.motion_blur_shutter = .25
        # Blender 4.3: with motion blur ON, persistent data must be OFF --
        # otherwise a body that comes to rest disappears from later frames
        # rendered in the same session (its motion-blur cache goes stale).
        scene.render.use_persistent_data = False
    else:
        scene.render.use_persistent_data = True  # keep scene data between frames; avoids per-frame resync/BVH rebuild
    scene.frame_start = 1
    scene.frame_end = data['frame_end']
    room = build_environment(bpy, scene)
    objects = make_objects(bpy, room)
    for key, o in objects.items():
        o.hide_render = o.hide_viewport = not data['objects'][key]['present']
    for f in data['frames']:
        for key in KEYS:
            if not f[key]['present']:
                continue
            o = objects[key]
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
    camera.name = 'Bathroom throw camera'
    camera.data.lens = cam['lens_mm']
    camera.rotation_euler = (Vector(cam['target']) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = (Vector(cam['target']) - camera.location).length
    camera.data.dof.aperture_fstop = 10.
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
            max_error = max(max_error, max(abs(objects[key].matrix_world[a][b] - f[key]['matrix_world'][a][b])
                                           for a in range(4) for b in range(4)))
            for corner in objects[key].bound_box:
                uv = world_to_camera_view(scene, camera, objects[key].matrix_world @ Vector(corner))
                if uv.z <= 0:
                    raise RuntimeError('Object behind camera')
                min_screen_margin = min(min_screen_margin, uv.x, 1 - uv.x, uv.y, 1 - uv.y)
    if max_error > 2e-6:
        raise RuntimeError(f'Blender replay differs from physics by {max_error}')
    # Room-scale scene: the ball may legitimately roll toward the frame edge
    # late in the clip, so the framing margin is recorded, not enforced. Only
    # geometry behind the camera is a hard error.
    if min_screen_margin < 0:
        print(f'[warn] object touches the camera plane: {min_screen_margin}')
    # Set dressing is not in the simulation: it must keep 2 cm from the ball in
    # every frame and never stand between the camera and the ball.
    prop_clearance = check_clearance(bpy, room, data)
    check_occlusion(bpy, scene, camera, room, data)
    metadata = deepcopy(s)
    metadata['render'].update(resolution=args.resolution, samples=args.samples, engine=args.engine, device=device, mode=args.mode,
                              motion_blur_shutter=scene.render.motion_blur_shutter if args.motion_blur else None)
    # big_project.glb is not drawn; physics checks the collider export
    # against its hash, so it is the geometric source of the room.
    metadata['assets'] = {n: str((MODELS / n).resolve()) for n in ('big_project.glb', 'tennis_ball.glb')}
    metadata['assets']['polyhaven'] = str(POLYHAVEN.resolve())
    metadata['daylight'] = room['daylight']
    metadata['prop_clearance_m'] = prop_clearance
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
                                                          max_matrix_error=max_error, min_screen_margin=min_screen_margin))]:
        (out / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    preview = args.preview_frame or min(scene.frame_end, round(((data['quality']['first_impact_sec'] or 0) + .22) * data['sample_fps']) + 1)
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
        indices = args.keyframes or [1, max(1, impact - 1), impact, impact + 5, round(2 * data['sample_fps']) + 1, scene.frame_end]
        if args.keyframes and any(not 1 <= i <= scene.frame_end for i in indices):
            raise ValueError('Keyframe outside trajectory')
        indices = sorted({min(scene.frame_end, i) for i in indices})
        for index in indices:
            scene.frame_set(index)
            scene.render.filepath = str(out / f'frame_{index:04d}.png')
            bpy.ops.render.render(write_still=True)
        shutil.copy2(out / f'frame_{next((i for i in indices if i >= preview), indices[-1]):04d}.png', out / 'preview.png')
        (out / 'keyframes.json').write_text(json.dumps([dict(frame=i, time_sec=(i - 1) / data['sample_fps'],
                                                             file=f'frame_{i:04d}.png') for i in indices], indent=2), encoding='utf-8')
    if args.mode == 'animation':
        scene.render.image_settings.file_format = 'FFMPEG'
        scene.render.ffmpeg.format = 'MPEG4'
        scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'HIGH'
        scene.render.filepath = str(out / 'bathroom_tennis_throw.mp4')
        scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'bathroom_tennis_throw.blend'))
    if args.mode == 'animation':
        bpy.ops.render.render(animation=True)
        shutil.copy2(out / 'bathroom_tennis_throw.mp4', out / 'video.mp4')


def main():
    p = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--physics-json', type=Path)
    p.add_argument('--physics-python', type=Path)
    p.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    p.add_argument('--samples', type=int, default=48)
    p.add_argument('--resolution', nargs=2, type=int, default=[1280, 720])
    p.add_argument('--mode', choices=('build', 'preview', 'keyframes', 'animation'), default='keyframes')
    p.add_argument('--preview-frame', type=int)
    p.add_argument('--keyframes', nargs='+', type=int, help='Frame indices for --mode keyframes')
    p.add_argument('--motion-blur', dest='motion_blur', action='store_true', default=True,
                   help='Quarter-frame shutter motion blur (default). The ball covers 5.8 of its own '
                        'diameters per frame at 14 m/s, so without blur it strobes.')
    p.add_argument('--no-motion-blur', dest='motion_blur', action='store_false',
                   help='Crisp frames (no shutter), e.g. for annotation stills.')
    render(parse_render_args(p))


if __name__ == '__main__':
    run_renderer(main, 'bathroom_tennis_throw')
