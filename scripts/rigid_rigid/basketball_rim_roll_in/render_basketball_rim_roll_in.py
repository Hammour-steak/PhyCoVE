"""Blender replay of the PyBullet transforms; keyframes are the default output."""
from __future__ import annotations

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
# sys.argv[0] must point at this scene script BEFORE importing the scene
# modules: they locate the scene folder from it, and under `blender -b` that is
# the blender binary.
_clean_sys.argv[0] = str(_CleanPath(__file__).resolve())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from scene_config import MODELS, SCENE_NAME, load_scenario, write_json, runtime
from look_basketball_rim_roll_in import aim, build_room, import_ball
import gym_hall

# Rendered parts of the backboard unit that DELETE backboard removes, and the
# collider list the solver uses in that case (see simulate_basketball_rim_roll_in.py).
BOARD_PARTS = ('Glass backboard', 'Board frame ', 'Back frame ', 'Rim ring', 'Rim mount housing',
               'Rim flange plate')
BOARD_ABSENT_COLLIDERS = Path(__file__).resolve().parent / 'physics' / 'board_absent_colliders.json'


def keyframes(data):
    """Frames a human would pick: the bank, the swirl, the drop."""
    metrics = data['metrics']
    values = {1, data['frame_end']}
    bank = metrics.get('board_impact')
    if bank:
        values.update((max(1, bank['frame_index'] - 3), bank['frame_index'],
                       min(data['frame_end'], bank['frame_index'] + 3)))
    entered = metrics.get('rim_orbit_entered_frame')
    through = metrics.get('through_rim')
    if entered:
        values.add(min(data['frame_end'], entered + 2))
    if through:
        span = through['frame_index'] - (entered or through['frame_index'])
        values.add(max(1, through['frame_index'] - 2))
        values.add(through['frame_index'])
        if entered:
            values.add(max(1, entered + span // 2))
    return sorted(values)


def add_camera(scenario, scene):
    cam_data = bpy.data.cameras.new('Court camera')
    cam = bpy.data.objects.new('Court camera', cam_data)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    spec = scenario['camera']
    cam.location = spec['location']
    aim(cam, spec['target'])
    cam_data.lens = spec['lens_mm']
    cam_data.sensor_width = 36.0
    cam_data.clip_start = .05
    cam_data.clip_end = 120.0
    cam_data.dof.use_dof = False
    return cam


def pick_device(scene, want, backend):
    """Point Cycles at the GPU and report what it actually got.

    Returns the chosen device description, or None for a CPU render. There is no
    silent fallback: a GPU request that quietly becomes a CPU render turns a
    forty-second frame into a fifteen-minute one, and the number that comes out
    of the timing log is then a lie about the machine. If the card cannot be
    used, the caller is told so and can decide.
    """
    if want == 'cpu':
        scene.cycles.device = 'CPU'
        return None
    prefs = bpy.context.preferences.addons['cycles'].preferences
    name = backend.upper()
    try:
        prefs.compute_device_type = name
    except TypeError:
        raise RuntimeError(f'this Blender build has no {backend} support compiled in')
    prefs.get_devices()
    cards = [d for d in prefs.devices if d.type == name]
    if not cards:
        if want == 'gpu':
            raise RuntimeError(f'no {backend} device: Cycles lists '
                               f'{[d.name for d in prefs.devices]}')
        scene.cycles.device = 'CPU'
        return None
    for device in prefs.devices:
        device.use = device.type == name
    scene.cycles.device = 'GPU'
    return f'{cards[0].name} [{backend}]'


def load_physics(path, scenario):
    """An already simulated trajectory, checked against the scenario it claims.

    For render machines without pybullet. The solver writes timed edits back
    into the physics block it saves, so those are applied to the scenario's
    physics before the two are compared; anything else that differs means the
    file belongs to another take, and rendering it would put a stale trajectory
    under an edit's name.
    """
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    expected = copy.deepcopy(scenario['physics'])
    for event in expected.get('timed_edits', []):
        expected.update(event['params'])
    if json.loads(json.dumps(data.get('physics'))) != json.loads(json.dumps(expected)):
        raise ValueError(f'{path} was simulated from different physics than this scenario')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--scenario-overrides-json', type=Path)
    parser.add_argument('--mode', choices=('build', 'preview', 'keyframes', 'animation', 'sequence'),
                        default='keyframes',
                        help='sequence = numbered PNG frames in <out-dir>/frames for an external encoder')
    parser.add_argument('--keyframes')
    parser.add_argument('--frame-range', nargs=2, type=int, metavar=('FIRST', 'LAST'),
                        help='Frames rendered by --mode sequence (default: the whole take)')
    parser.add_argument('--physics-json', type=Path,
                        help='Render this physics_transforms.json of the same scenario instead of '
                             'simulating again (for machines without pybullet)')
    parser.add_argument('--resolution', nargs=2, type=int, default=(1280, 720))
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--threads', type=int, default=8,
                        help='Limit CPU load on the local computer')
    parser.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    parser.add_argument('--device', choices=('auto', 'cpu', 'gpu'), default='auto',
                        help='auto = the GPU when Cycles can see one, else CPU')
    parser.add_argument('--gpu-backend', choices=('optix', 'cuda'), default='optix',
                        help='OptiX is the ray-tracing backend on RTX cards; CUDA is the fallback')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None)
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scenario = load_scenario(args.scenario_overrides_json)
    write_json(out / 'scenario_input.json', scenario)
    if args.physics_json:
        # A trajectory simulated elsewhere, accepted only for this exact scenario.
        load_physics(args.physics_json, scenario)
        if args.physics_json.resolve() != (out / 'physics_transforms.json').resolve():
            shutil.copyfile(args.physics_json, out / 'physics_transforms.json')
    else:
        # Always simulate the resolved input: a stale trajectory must not survive an edit.
        command = [runtime('sim'),
                   str(Path(__file__).resolve().with_name('simulate_basketball_rim_roll_in.py')),
                   '--out', str(out / 'physics_transforms.json')]
        if args.scenario_overrides_json:
            command += ['--scenario-overrides-json', str(args.scenario_overrides_json.resolve())]
        subprocess.run(command, check=True)
    data = json.loads((out / 'physics_transforms.json').read_text(encoding='utf-8'))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES' if args.engine == 'cycles' else 'BLENDER_EEVEE_NEXT'
    if args.engine == 'cycles':
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        scene.cycles.denoiser = 'OPENIMAGEDENOISE'
        device = pick_device(scene, args.device, args.gpu_backend)
        # The glass board needs two transmission events and the hall is lit
        # through windows and by bounce, so the paths are longer than a studio's.
        scene.cycles.max_bounces = 10
        scene.cycles.diffuse_bounces = 4
        scene.cycles.glossy_bounces = 4
        scene.cycles.transmission_bounces = 8
        scene.cycles.transparent_max_bounces = 12
        scene.cycles.caustics_reflective = False
        scene.cycles.caustics_refractive = False
        scene.cycles.blur_glossy = 0.5
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = .01
    else:
        device = 'EEVEE (GPU via OpenGL)'
        scene.eevee.taa_render_samples = args.samples
    print(f'render device: {device or "CPU"}')
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = max(1, args.threads)
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = data['fps']
    scene.frame_start, scene.frame_end = 1, data['frame_end']
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = scenario['layout']['look']
    scene.view_settings.exposure = scenario['layout']['exposure']
    # A quarter-frame shutter: enough to smear the fast flight the way a camera
    # does, short enough that the ball does not turn into a translucent ghost.
    # Persistent data must stay off with motion blur on: in Blender 4.3 the pair
    # makes a body that has come to rest vanish from later frames rendered in
    # the same session.
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.25
    scene.render.use_persistent_data = False

    room = build_room(scenario)
    if not scenario['physics'].get('board_presence', [1])[0]:
        # DELETE backboard: the glass board with its aluminium channel and steel
        # back frame, the ring, its mount housing and flange plate go; the parts
        # the solver made solid for this case stop counting as scenery.
        gone = [o for o in bpy.data.objects if o.name.startswith(BOARD_PARTS)]
        solid = {c['name'] for c in json.loads(BOARD_ABSENT_COLLIDERS.read_text(encoding='utf-8'))['colliders']}
        room['props'] = [o for o in room['props'] if o not in gone and o.name not in solid]
        room['colliders'] = [o for o in room['colliders'] if o not in gone]
        for o in gone:
            bpy.data.objects.remove(o, do_unlink=True)
    ball = import_ball(MODELS / scenario['assets']['ball'], scenario['physics']['ball_radius'])
    ball.rotation_mode = 'QUATERNION'
    for row in data['frames']:
        ball.location = row['ball_location']
        x, y, z, w = row['ball_quaternion_xyzw']
        ball.rotation_quaternion = (w, x, y, z)
        ball.keyframe_insert('location', frame=row['frame_index'])
        ball.keyframe_insert('rotation_quaternion', frame=row['frame_index'])
    for curve in ball.animation_data.action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation = 'LINEAR'

    cam = add_camera(scenario, scene)
    # Validate every rendered frame against the same physical sphere.
    radius = scenario['physics']['ball_radius']
    # The hall and the non-contact parts of the goal are not in the solver:
    # refuse a take in which the ball would pass within 2 cm of any of them.
    clearance = gym_hall.check_clearance(room['props'], [row['ball_location'] for row in data['frames']],
                                         radius)
    prop_names = {o.name for o in room['props']}
    hidden_by_props = []
    validation, ground = [], []
    for row in data['frames']:
        frame = row['frame_index']
        scene.frame_set(frame)
        pos = ball.matrix_world.translation
        error = (pos - Vector(row['ball_location'])).length
        points = [world_to_camera_view(scene, cam, pos + Vector(offset)) for offset in
                  ((radius, 0, 0), (-radius, 0, 0), (0, radius, 0), (0, -radius, 0),
                   (0, 0, radius), (0, 0, -radius))]
        inside = all(p.z > 0 and 0 <= p.x <= 1 and 0 <= p.y <= 1 for p in points)
        deps = bpy.context.evaluated_depsgraph_get()
        direction = pos - cam.location
        hit, point, normal, index, obj, matrix = scene.ray_cast(
            deps, cam.location, direction.normalized(), distance=direction.length + radius)
        visible = bool(hit and obj and obj.original == ball)
        # A prop may never stand between the camera and a ball that is in shot;
        # only the surfaces the ball really meets (rim, board, base) may.
        if inside:
            for offset in ((0, 0, 0), (radius * .7, 0, 0), (-radius * .7, 0, 0),
                           (0, 0, radius * .7), (0, 0, -radius * .7)):
                target = pos + Vector(offset)
                ray = target - cam.location
                hit, point, normal, index, obj, matrix = scene.ray_cast(
                    deps, cam.location, ray.normalized(), distance=ray.length)
                if hit and obj and obj.original.name in prop_names:
                    hidden_by_props.append((frame, obj.original.name))
                    break
        validation.append({'frame_index': frame, 'position_error_m': error,
                           'sphere_in_frame': inside, 'center_visible': visible})
        ground.append({'frame_index': frame, 'time_sec': row['time_sec'], 'basketball': {
            'location': list(pos), 'quaternion_xyzw': row['ball_quaternion_xyzw'],
            'radius_m': radius}})
    if hidden_by_props:
        raise ValueError(f'props hide the ball from the camera: {hidden_by_props[:8]}')
    write_json(out / 'ground_truth_transforms.json', {'fps': data['fps'], 'frames': ground})
    write_json(out / 'render_validation.json', {
        'all_frames_in_view': all(v['sphere_in_frame'] for v in validation),
        'all_centers_visible': all(v['center_visible'] for v in validation),
        'max_position_error_m': max(v['position_error_m'] for v in validation),
        'closest_props_m': clearance,
        'frames': validation})
    write_json(out / 'scenario_metadata.json', {
        'scene': scenario['scene'], 'duration_sec': data['duration_sec'],
        'frame_count': data['frame_end'], 'fps': data['fps'],
        'assets': {'ball': f"assets/models/{scenario['assets']['ball']}",
                   'hall': f'assets/polyhaven/{SCENE_NAME}'},
        'physics': ('One rigid sphere against a static floor, backboard, bracket, wedged '
                    'counterweight box and 96-sphere rim; the ball is the only body that '
                    'moves'),
        'camera_location': list(cam.location), 'camera_target': scenario['camera']['target'],
        'camera_lens_mm': cam.data.lens, 'mode': args.mode,
        # Which engine actually traced the pixels, not which one was asked for.
        'render_device': device or 'CPU',
        'samples': args.samples,
        'metrics': {key: data['metrics'][key] for key in
                    ('surface_sequence', 'rim_orbit_revolutions', 'passed_through_rim',
                     'rim_contact_count', 'path_length_m')}})
    selected = ([int(s) for s in args.keyframes.split(',')] if args.keyframes
                else keyframes(data))
    if any(f < 1 or f > scene.frame_end for f in selected):
        raise ValueError('Keyframes outside simulation range')
    write_json(out / 'keyframes.json', {'frames': selected,
                                        'board_impact': data['metrics'].get('board_impact'),
                                        'through_rim': data['metrics'].get('through_rim')})
    scene.frame_set(1)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'basketball_rim_roll_in.blend'))
    if args.mode == 'animation':
        # Blender's bundled encoder, so no external ffmpeg is needed. The
        # quality factor is pinned rather than left at the default: this clip is
        # mostly flat paint and a slow gradient across the floor, which is
        # exactly what a low H.264 setting turns into banding.
        scene.render.image_settings.file_format = 'FFMPEG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.ffmpeg.format = 'MPEG4'
        scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'PERC_LOSSLESS'
        scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
        scene.render.ffmpeg.audio_codec = 'NONE'
        scene.render.filepath = str(out / 'video.mp4')
        bpy.ops.render.render(animation=True)
    elif args.mode == 'sequence':
        # Numbered PNGs (frames/frame_0001.png ...) for an external encoder; a
        # sub-range lets one take be split across machines with identical settings.
        first, last = args.frame_range or (1, data['frame_end'])
        if not 1 <= first <= last <= data['frame_end']:
            raise ValueError('--frame-range outside the simulation')
        scene.frame_start, scene.frame_end = first, last
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '8'
        scene.render.filepath = str(out / 'frames' / 'frame_')
        bpy.ops.render.render(animation=True)
    elif args.mode != 'build':
        for frame in ([selected[0]] if args.mode == 'preview' else selected):
            scene.frame_set(frame)
            scene.render.filepath = str(out / f'frame_{frame:04d}.png')
            bpy.ops.render.render(write_still=True)
    print(f'Completed {out}')


if __name__ == '__main__':
    main()
