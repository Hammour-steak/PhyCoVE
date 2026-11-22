"""Build the office, replay verified rigid-body poses and render the four-second clip."""
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
from validate_office_desk_kettle_tip import validate_cache
from scene_geometry import KEYS
from look_office_desk_kettle_tip import build_environment, make_dynamic_objects, MODELS, TEXTURES
import open_office
from pcve_render_quality import configure_renderer, configure_color

# Interior daylight under AgX: the desk sits about two stops under the window
# band, as a phone camera exposes a desk in front of a bright facade.
LOOK = 'AgX - Medium High Contrast'
EXPOSURE = 1.5


def render(args):
    import bpy
    from mathutils import Vector
    if args.samples < 1 or min(args.resolution) < 1: raise ValueError('Invalid render settings')
    out = args.out_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    physics = args.physics_json.resolve() if args.physics_json else out / 'physics_transforms.json'
    scenario_keys = ('scenario_json', 'scenario_overrides_json', *PHYSICS_LIMITS, 'fps', 'duration_sec', 'slow_motion')
    if args.physics_json:
        if args.remove_pen or any(getattr(args, k) is not None for k in scenario_keys): raise ValueError('Resimulate before changing cached initial conditions/timing')
    else:
        command = [str(args.physics_python or python_for('physics')), str(Path(__file__).with_name('simulate_office_desk_kettle_tip.py')), '--out', str(physics)]
        for key in scenario_keys:
            value = getattr(args, key)
            if value is not None: command += ['--' + key.replace('_', '-'), str(value)]
        if args.remove_pen: command += ['--remove-pen']
        subprocess.run(command, check=True)
    data = json.loads(physics.read_text(encoding='utf-8')); validate_cache(data)
    if physics != out / 'physics_transforms.json': shutil.copy2(physics, out / 'physics_transforms.json')
    (out / 'simulation_metrics.json').write_text(json.dumps(data['quality'], indent=2), encoding='utf-8')
    s = deepcopy(data['scenario'])
    bpy.ops.wm.read_factory_settings(use_empty=True); scene = bpy.context.scene
    device = configure_renderer(bpy, scene, args); configure_color(scene)
    # OIDN on every device: the OptiX denoiser smears the mesh cup's wires.
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    scene.view_settings.look = LOOK; scene.view_settings.exposure = EXPOSURE
    scene.render.resolution_x, scene.render.resolution_y = args.resolution; scene.render.resolution_percentage = 100
    scene.render.fps = data['playback_fps']; scene.frame_start = 1; scene.frame_end = data['frame_end']
    # Quarter-frame shutter: the pen leaves the cup at up to 1.6 m/s (6.8 cm a
    # frame); a longer shutter smears it into a see-through streak. Persistent
    # data must stay off with motion blur in Blender 4.3: with both on, a body
    # that has come to rest vanishes from later frames of the same session.
    scene.render.use_motion_blur = True; scene.render.motion_blur_shutter = .25
    scene.render.use_persistent_data = False
    room = build_environment(bpy, scene); objects = make_dynamic_objects(bpy)
    for key, o in objects.items():
        o.hide_render = o.hide_viewport = not data['objects'][key]['present']
        # Extras parented to a replayed body (handle, pen clip, cup rims) follow it.
        for child in list(o.children):
            child.hide_render = child.hide_viewport = not data['objects'][key]['present']
    for f in data['frames']:
        for key in KEYS:
            if not f[key]['present']: continue
            o = objects[key]; state = f[key]; o.location = state['location']; q = state['quaternion_xyzw']
            o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = (q[3], q[0], q[1], q[2])
            o.keyframe_insert('location', frame=f['frame_index']); o.keyframe_insert('rotation_quaternion', frame=f['frame_index'])
    for o in objects.values():
        if o.animation_data is None: continue
        for curve in o.animation_data.action.fcurves:
            for k in curve.keyframe_points: k.interpolation = 'LINEAR'
    # A body deleted partway through is still built -- the cache's object table
    # says present, because it exists at frame 1 -- so the replay keyframes it
    # up to the removal frame and then switches it off. CONSTANT interpolation:
    # the cup vanishes between two frames, it does not fade.
    for key in KEYS:
        if not data['objects'][key]['present']: continue
        absent_at = next((f['frame_index'] for f in data['frames'] if not f[key]['present']), None)
        if absent_at is None: continue
        for o in [objects[key], *objects[key].children_recursive]:
            for prop in ('hide_render', 'hide_viewport'):
                setattr(o, prop, False); o.keyframe_insert(prop, frame=max(1, absent_at - 1))
                setattr(o, prop, True); o.keyframe_insert(prop, frame=absent_at)
            for curve in o.animation_data.action.fcurves:
                if curve.data_path in ('hide_render', 'hide_viewport'):
                    for point in curve.keyframe_points: point.interpolation = 'CONSTANT'
    cam = s['camera']; bpy.ops.object.camera_add(location=cam['location']); camera = bpy.context.object
    camera.name = 'Desk kettle camera'; camera.data.lens = cam['lens_mm']
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
    # Props without a collider keep 2 cm from every moving body in every frame
    # (and between frames, for the motion blur); props with one stay inside it;
    # no prop hides a body from the camera.
    present = [k for k in KEYS if data['objects'][k]['present']]
    clearance = open_office.check_clearance(room, data['frames'], present)
    open_office.check_occlusion(bpy, scene, camera, room, data['frames'], {k: objects[k] for k in present})
    metadata = deepcopy(s)
    metadata['render'].update(resolution=args.resolution, samples=args.samples, engine=args.engine, device=device, mode=args.mode)
    metadata['assets'] = {n: str((MODELS / n).resolve()) for n in
                          ('office_desk.glb', 'water_bottle__plastic_bottle.glb', 'pen_holder.glb', 'the_pen.glb')}
    metadata['assets'].update({f'polyhaven/office_desk_kettle_tip/{p.name}': str(p.resolve())
                               for p in sorted(TEXTURES.glob('*')) if p.is_file()})
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
                                                          max_matrix_error=max_error,
                                                          prop_clearance_m=clearance))]:
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
        (out / 'keyframes.json').write_text(json.dumps([dict(frame=i, time_sec=(i - 1) / data['sample_fps'], file=f'frame_{i:04d}.png') for i in indices], indent=2), encoding='utf-8')
    if args.mode == 'animation':
        scene.render.image_settings.file_format = 'FFMPEG'; scene.render.ffmpeg.format = 'MPEG4'; scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'HIGH'; scene.render.filepath = str(out / 'office_desk_kettle_tip.mp4')
        scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'office_desk_kettle_tip.blend'))
    if args.mode == 'animation':
        bpy.ops.render.render(animation=True); shutil.copy2(out / 'office_desk_kettle_tip.mp4', out / 'video.mp4')


def main():
    p = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    p.add_argument('--out-dir', type=Path, required=True); p.add_argument('--physics-json', type=Path)
    p.add_argument('--physics-python', type=Path); p.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto'); p.add_argument('--samples', type=int, default=48)
    p.add_argument('--resolution', nargs=2, type=int, default=[960, 540])
    p.add_argument('--mode', choices=('build', 'preview', 'keyframes', 'animation'), default='keyframes')
    p.add_argument('--preview-frame', type=int)
    p.add_argument('--keyframes', nargs='+', type=int, help='Frame indices for --mode keyframes')
    render(parse_render_args(p))


if __name__ == '__main__': run_renderer(main, 'office_desk_kettle_tip')
