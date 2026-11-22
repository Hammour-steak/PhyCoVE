"""Build the bistro corner, replay verified rigid-body poses and render the four-second clip."""
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
from validate_kitchen_tin_collision import validate_cache
from scene_geometry import KEYS, TABLE_TOP_Z, TABLE_HALF_X, TABLE_HALF_Y
from look_kitchen_tin_collision import (build_environment, make_tins, CLOTH_OBJECTS,
                                        used_files)
from bistro_room import clearance_pieces
from pcve_render_quality import configure_renderer, configure_color
from pcve_project_paths import project_relative

SCENE = 'kitchen_tin_collision'
# AgX exposure for a room lit by tungsten chandeliers and a candle.
EXPOSURE = .75
# A 90-degree shutter (0.25 of a frame): the 1.55 m/s tin smears about 1.6 cm,
# as it would on a real 1/96 s exposure, without turning into a ghost.
SHUTTER = .25
# Set dressing must keep this far from every tin in every frame.
CLEARANCE_M = .02


def check_clearance(scene, objects, data):
    """Smallest gap between each tin's bounding sphere and each static piece's
    world box over the whole clip; raises if any is under CLEARANCE_M.  The
    table and the cloth the tins stand on are the support, not set dressing."""
    import bpy
    from mathutils import Vector
    pieces = clearance_pieces(bpy)
    radius = {}
    for key, o in objects.items():
        corners = [Vector(c) for c in o.bound_box]
        centre = sum(corners, Vector()) / 8
        radius[key] = max((c - centre).length for c in corners)
    gaps = {p['name']: 1e9 for p in pieces}
    for f in data['frames']:
        for key in KEYS:
            if not f[key]['present']:
                continue
            c = f[key]['location']
            for p in pieces:
                lo, hi = p['lo'], p['hi']
                d = math.sqrt(sum(max(lo[i] - c[i], 0., c[i] - hi[i]) ** 2 for i in range(3))) - radius[key]
                gaps[p['name']] = min(gaps[p['name']], d)
    worst = min(gaps.items(), key=lambda kv: kv[1])
    if worst[1] < CLEARANCE_M:
        raise RuntimeError(f'A tin passes within {worst[1]:.3f} m of {worst[0]}; move the piece')
    return dict(margin_m=CLEARANCE_M, closest_piece=worst[0], closest_gap_m=round(worst[1], 4))


def check_occlusion(scene, camera, objects, data):
    """Ray-check every frame: nothing but a tin may stand between the camera and
    the centre or the (slightly inset) corners of each tin."""
    import bpy
    from mathutils import Vector
    tins = {o.name for o in objects.values()}
    origin = camera.matrix_world.translation.copy()
    blocked = []
    rays = 0
    for f in data['frames']:
        scene.frame_set(f['frame_index'])
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for key, o in objects.items():
            if not f[key]['present']:
                continue
            corners = [o.matrix_world @ Vector(c) for c in o.bound_box]
            centre = sum(corners, Vector()) / 8
            for point in [centre] + [centre + (c - centre) * .85 for c in corners]:
                ray = point - origin
                hit, _, _, _, obj, _ = scene.ray_cast(depsgraph, origin, ray.normalized(),
                                                      distance=ray.length - 1e-4)
                rays += 1
                if hit and obj.name not in tins:
                    blocked.append((f['frame_index'], key, obj.name))
    if blocked:
        raise RuntimeError(f'{len(blocked)} sight lines to a tin are blocked, e.g. {blocked[:3]}')
    return dict(rays=rays, blocked=0)


def validate_tabletop(bpy):
    """Ray-check that the rendered cloth really is the plane the solver used.

    The solver puts a box at ``z = TABLE_TOP_Z``; the render lays a generated
    cloth over a scanned table.  If those two disagree the tins float
    or sink, and no amount of material work hides it, so it is measured here
    rather than assumed.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bpy.context.view_layer.update()
    cloth = bpy.data.objects[CLOTH_OBJECTS[0]]
    evaluated = cloth.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        verts = [cloth.matrix_world @ v.co for v in mesh.vertices]
        polys = [list(p.vertices) for p in mesh.polygons]
        tree = BVHTree.FromPolygons(verts, polys)
    finally:
        evaluated.to_mesh_clear()
    samples = []
    for x in (-.40, -.20, 0., .20, .40):
        for y in (-.22, 0., .22):
            hit = tree.ray_cast(Vector((x, y, .4)), Vector((0, 0, -1.)), .8)[0]
            if hit is None:
                raise RuntimeError(f'Tablecloth does not cover ({x}, {y}); the solver assumes it does')
            samples.append(hit.z)
    spread = max(samples) - min(samples)
    mean = sum(samples) / len(samples)
    if abs(mean - TABLE_TOP_Z) > 1e-4 or spread > 1e-3:
        raise RuntimeError(f'Cloth surface {mean:.5f} +-{spread:.5f} is not the physics table at {TABLE_TOP_Z}')
    return dict(valid=True, samples=len(samples), mean_z=round(mean, 6), spread_m=round(spread, 6),
                physics_table_half_extents=[TABLE_HALF_X, TABLE_HALF_Y])


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
        if args.remove_receiver or any(getattr(args, k) is not None for k in scenario_keys):
            raise ValueError('Resimulate before changing cached initial conditions/timing')
    else:
        command = [str(args.physics_python or python_for('physics')),
                   str(Path(__file__).with_name('simulate_kitchen_tin_collision.py')), '--out', str(physics)]
        for key in scenario_keys:
            value = getattr(args, key)
            if value is not None:
                command += ['--' + key.replace('_', '-'), str(value)]
        if args.remove_receiver:
            command += ['--remove-receiver']
        subprocess.run(command, check=True)
    data = json.loads(physics.read_text(encoding='utf-8')); validate_cache(data)
    if physics != out / 'physics_transforms.json':
        shutil.copy2(physics, out / 'physics_transforms.json')
    (out / 'simulation_metrics.json').write_text(json.dumps(data['quality'], indent=2), encoding='utf-8')

    s = deepcopy(data['scenario'])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    device = configure_renderer(bpy, scene, args); configure_color(scene)
    scene.view_settings.exposure = EXPOSURE
    if scene.render.engine == 'CYCLES':
        scene.cycles.denoiser = 'OPENIMAGEDENOISE'
        scene.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
        # Glints of the bulbs in the tins through diffuse bounces are the only
        # fireflies this room makes; clamping indirect light removes them.
        scene.cycles.sample_clamp_indirect = 10.
        scene.render.use_motion_blur = True
        scene.render.motion_blur_shutter = SHUTTER
        # Blender 4.3 with motion blur on and persistent data kept between
        # frames drops objects that have come to rest from later frames of the
        # same session, so persistent data must stay off whenever blur is on.
        scene.render.use_persistent_data = False
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = data['playback_fps']
    scene.frame_start = 1; scene.frame_end = data['frame_end']
    room = build_environment(bpy, scene)
    objects = make_tins(bpy)
    tabletop = validate_tabletop(bpy)
    for key, o in objects.items():
        o.hide_render = o.hide_viewport = not data['objects'][key]['present']
    for f in data['frames']:
        for key in KEYS:
            if not f[key]['present']:
                continue
            o = objects[key]; state = f[key]
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
    camera.name = 'Tabletop camera'
    camera.data.lens = cam['lens_mm']
    camera.rotation_euler = (Vector(cam['target']) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = (Vector(cam['target']) - camera.location).length
    camera.data.dof.aperture_fstop = 5.6
    scene.camera = camera
    bpy.context.view_layer.update()
    cm = [list(row) for row in camera.matrix_world]

    max_error = 0.; min_screen_margin = 1.; checked = 0
    for f in data['frames']:
        scene.frame_set(f['frame_index']); bpy.context.view_layer.update()
        for key in KEYS:
            if not f[key]['present']:
                continue
            max_error = max(max_error, max(abs(objects[key].matrix_world[a][b] - f[key]['matrix_world'][a][b])
                                           for a in range(4) for b in range(4)))
            # Framing only means something while the tin is still on the cloth.
            # An extreme edit is allowed to sweep a tin clean off the tabletop,
            # and once it has left the table no camera could hold it anyway --
            # this shot is framed for the cloth, not for the floor beyond it.
            # So the guard is scoped to tins that are both above the table plane
            # and inside its footprint; a tin that is airborne past the edge is
            # simply on its way out of the scene.
            loc = f[key]['location']
            if loc[2] < TABLE_TOP_Z - .01:
                continue
            if abs(loc[0]) > TABLE_HALF_X or abs(loc[1]) > TABLE_HALF_Y:
                continue
            checked += 1
            for corner in objects[key].bound_box:
                uv = world_to_camera_view(scene, camera, objects[key].matrix_world @ Vector(corner))
                if uv.z <= 0:
                    raise RuntimeError('Tin behind camera')
                min_screen_margin = min(min_screen_margin, uv.x, 1 - uv.x, uv.y, 1 - uv.y)
    if max_error > 2e-6:
        raise RuntimeError(f'Blender replay differs from physics by {max_error}')
    if min_screen_margin < .015:
        raise RuntimeError(f'Tin outside safe camera framing: {min_screen_margin}')
    clearance = check_clearance(scene, objects, data)
    occlusion = check_occlusion(scene, camera, objects, data)
    print(f'[render] clearance {clearance}; occlusion {occlusion}', flush=True)
    tabletop.update(room=dict(table=room['table'], chairs=len(room['chairs'])), clearance=clearance,
                    occlusion=occlusion)
    (out / 'tabletop_validation.json').write_text(json.dumps(tabletop, indent=2), encoding='utf-8')

    metadata = deepcopy(s)
    metadata['render'].update(resolution=args.resolution, samples=args.samples, engine=args.engine,
                              device=device, mode=args.mode, denoiser=getattr(scene.cycles, 'denoiser', None),
                              motion_blur_shutter=SHUTTER, exposure=EXPOSURE)
    metadata['assets'] = {str(project_relative(p.resolve())): str(p.resolve()) for p in used_files()}
    gt = dict(schema_version=1, scene=data['scene'], fps=scene.render.fps, frame_start=1,
              frame_end=data['frame_end'], scenario=metadata,
              physics={k: v for k, v in data.items() if k != 'frames'},
              objects={k: dict(v, object_name=objects[k].name) for k, v in data['objects'].items()},
              camera=dict(object_name=camera.name, matrix_world=cm, lens_mm=camera.data.lens,
                          sensor_width_mm=camera.data.sensor_width, resolution=args.resolution),
              sample_fps=data['sample_fps'], slow_motion=data['slow_motion'],
              physical_duration_sec=data['physical_duration_sec'],
              playback_duration_sec=data['playback_duration_sec'],
              frames=[dict(f, camera_matrix_world=cm) for f in data['frames']])
    for name, payload in [('ground_truth_transforms.json', gt), ('scenario_metadata.json', metadata),
                          ('render_validation.json', dict(valid=True, checked_frames=len(data['frames']),
                                                          objects_checked=checked,
                                                          max_matrix_error=max_error,
                                                          min_screen_margin=min_screen_margin))]:
        (out / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')

    impact = math.ceil((data['quality']['first_impact_sec'] or 0) * data['sample_fps']) + 1
    preview = args.preview_frame or min(scene.frame_end, impact + 2)
    if not 1 <= preview <= scene.frame_end:
        raise ValueError('Preview frame outside trajectory')
    scene.frame_set(preview); bpy.ops.file.pack_all()
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(out / 'preview.png')
    if args.mode not in ('build', 'keyframes'):
        bpy.ops.render.render(write_still=True)
    if args.mode == 'keyframes':
        indices = args.keyframes or [1, max(1, impact - 1), impact, impact + 6,
                                     round(2 * data['sample_fps']) + 1, scene.frame_end]
        if args.keyframes and any(not 1 <= i <= scene.frame_end for i in indices):
            raise ValueError('Keyframe outside trajectory')
        indices = sorted({min(scene.frame_end, i) for i in indices})
        for index in indices:
            scene.frame_set(index)
            scene.render.filepath = str(out / f'frame_{index:04d}.png')
            bpy.ops.render.render(write_still=True)
        shutil.copy2(out / f'frame_{min(indices, key=lambda i: abs(i - preview)):04d}.png', out / 'preview.png')
        (out / 'keyframes.json').write_text(
            json.dumps([dict(frame=i, time_sec=(i - 1) / data['sample_fps'], file=f'frame_{i:04d}.png')
                        for i in indices], indent=2), encoding='utf-8')
    if args.mode == 'animation':
        scene.render.image_settings.file_format = 'FFMPEG'
        scene.render.ffmpeg.format = 'MPEG4'; scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'HIGH'
        scene.render.filepath = str(out / f'{SCENE}.mp4')
        scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / f'{SCENE}.blend'))
    if args.mode == 'animation':
        bpy.ops.render.render(animation=True)
        shutil.copy2(out / f'{SCENE}.mp4', out / 'video.mp4')


def main():
    p = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    p.add_argument('--out-dir', type=Path, required=True); p.add_argument('--physics-json', type=Path)
    p.add_argument('--physics-python', type=Path)
    p.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    p.add_argument('--samples', type=int, default=48)
    p.add_argument('--resolution', nargs=2, type=int, default=[1280, 720])
    p.add_argument('--mode', choices=('build', 'preview', 'keyframes', 'animation'), default='keyframes')
    p.add_argument('--preview-frame', type=int)
    p.add_argument('--keyframes', nargs='+', type=int, help='Frame indices for --mode keyframes')
    render(parse_render_args(p))


if __name__ == '__main__':
    run_renderer(main, SCENE)
