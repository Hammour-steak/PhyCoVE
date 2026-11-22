"""Four seconds, one fixed camera: a bowl falls off a cupboard onto the tableware below."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json
import math
from scene_geometry import (FALLING_BOWL_MASS, FALLING_BOWL_RADIUS, FALLING_BOWL_SPIN,
                            FALLING_BOWL_PUSH, FALLING_BOWL_PUSH_X, FALLING_BOWL_HANG,
                            FALLING_BOWL_TILT_DEG, TABLEWARE_MASS,
                            TABLEWARE_CENTER_XY, TABLEWARE_BASE_Z, FALLING_BOWL_FRICTION,
                            TABLEWARE_FRICTION, FALLING_BOWL_RESTITUTION, TABLEWARE_RESTITUTION,
                            COUNTER_RESTITUTION, CUPBOARD_RESTITUTION, GRAVITY_Z)

SCENE_NAME = 'kitchen_bowl_fall'

# Every editable number the scene has. The two anchor arrays exist so the edit
# vocabulary and the ADD-style helpers can talk about "where the bowl hangs"
# and "where the tableware stands" without scene coordinates leaking into the DSL.
BASELINE_PHYSICS = dict(
    falling_bowl_mass=FALLING_BOWL_MASS, falling_bowl_spin=FALLING_BOWL_SPIN,
    falling_bowl_push=FALLING_BOWL_PUSH, falling_bowl_push_x=FALLING_BOWL_PUSH_X,
    falling_bowl_tilt_deg=FALLING_BOWL_TILT_DEG,
    falling_bowl_friction=FALLING_BOWL_FRICTION,
    tableware_mass=TABLEWARE_MASS, tableware_friction=TABLEWARE_FRICTION,
    falling_bowl_restitution=FALLING_BOWL_RESTITUTION,
    tableware_restitution=TABLEWARE_RESTITUTION,
    counter_restitution=COUNTER_RESTITUTION, cupboard_restitution=CUPBOARD_RESTITUTION,
    gravity_z=GRAVITY_Z, tableware_active=[1],
    falling_bowl_hang=[FALLING_BOWL_HANG[0], FALLING_BOWL_HANG[1], FALLING_BOWL_HANG[2]],
    tableware_center=[TABLEWARE_CENTER_XY[0], TABLEWARE_CENTER_XY[1], TABLEWARE_BASE_Z],
    falling_bowl_radius=FALLING_BOWL_RADIUS, timed_edits=[])

PHYSICS_LIMITS = {
    'falling_bowl_mass': (.05, 20.), 'falling_bowl_spin': (-8., 8.),
    'falling_bowl_push': (0., 2.), 'falling_bowl_push_x': (-2., 2.),
    'falling_bowl_tilt_deg': (0., 70.),
    'falling_bowl_friction': (0., 1.5),
    'tableware_mass': (.05, 20.), 'tableware_friction': (0., 1.5),
    'falling_bowl_restitution': (0., .95), 'tableware_restitution': (0., .95),
    'counter_restitution': (0., .95), 'cupboard_restitution': (0., .95),
    'gravity_z': (-60., 0.),
    'falling_bowl_radius': (.05, .5),
}
VECTOR_KEYS = ('falling_bowl_hang', 'tableware_center')
TOGGLE_KEYS = ('tableware_active',)
# Optional presence switch for the falling bowl, written only by a DELETE of it; absent means present,
# so the baseline scenario (and every published case) carries no such key.
OPTIONAL_TOGGLE_KEYS = ('falling_bowl_active',)
TOTAL_FRAMES = 96


def defaults():
    return dict(schema_version=1, scene=SCENE_NAME, seed=0, physics=deepcopy(BASELINE_PHYSICS),
                render=dict(fps=24, duration_sec=4., slow_motion=1, resolution=[1280, 720], samples=384),
                camera=dict(location=[-2.15, 0.45, 2.05], target=[-0.15, 3.00, 1.70], lens_mm=28.0))


def merge(base, overrides):
    result = deepcopy(base)
    if not isinstance(overrides, dict):
        raise ValueError('Scenario overrides must be an object')
    for key, value in overrides.items():
        if key not in result:
            raise ValueError(f'Unknown scenario field: {key}')
        result[key] = merge(result[key], value) if isinstance(value, dict) else deepcopy(value)
    return result


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(s):
    if set(s) - {'schema_version', 'scene', 'physics', 'render', 'camera', 'seed'}:
        raise ValueError('Unknown scenario field')
    if s['scene'] != SCENE_NAME or s['schema_version'] != 1:
        raise ValueError('Wrong scene/schema')
    ph = s['physics']
    if set(ph) - set(OPTIONAL_TOGGLE_KEYS) != set(BASELINE_PHYSICS):
        raise ValueError('Unknown editable physics parameter')
    for key in TOGGLE_KEYS + tuple(k for k in OPTIONAL_TOGGLE_KEYS if k in ph):
        active = ph[key]
        if not isinstance(active, list) or len(active) != 1 or type(active[0]) is not int or active[0] not in (0, 1):
            raise ValueError(f'{key} must be [0] or [1]')
    for key in VECTOR_KEYS:
        vec = ph[key]
        if not isinstance(vec, list) or len(vec) != 3 or not all(finite(v) for v in vec):
            raise ValueError(f'{key} must be a 3-vector')
    for key, (low, high) in PHYSICS_LIMITS.items():
        if not finite(ph[key]) or not low <= ph[key] <= high:
            raise ValueError(f'{key} must be finite and within {low}..{high}')
    schedule = ph['timed_edits']
    if not isinstance(schedule, list):
        raise ValueError('timed_edits must be a list')
    seen = set()
    for event in schedule:
        if not isinstance(event, dict) or set(event) != {'frame', 'params'}:
            raise ValueError('timed_edits entry must be {frame, params}')
        frame, params = event['frame'], event['params']
        if type(frame) is not int or not 2 <= frame <= TOTAL_FRAMES or frame in seen:
            raise ValueError('timed_edits frame must be a distinct frame inside the clip')
        seen.add(frame)
        if not isinstance(params, dict) or set(params) != {'gravity_z'}:
            raise ValueError('this scene can only change gravity mid-run')
        value = params['gravity_z']
        # Zero is the point of the mid-run edit: gravity switches off after the
        # first collision and everything keeps the momentum it had.
        if not finite(value) or not -60. <= value <= 0.:
            raise ValueError('timed gravity_z must be finite and point down or vanish')
    r = s['render']
    if type(r['fps']) is not int or r['fps'] <= 0:
        raise ValueError('Invalid fps')
    if type(r['slow_motion']) is not int or r['slow_motion'] not in (1, 2, 4, 8) or 1440 % (r['fps'] * r['slow_motion']):
        raise ValueError('fps * slow_motion must divide the 1440 Hz simulation clock')
    if not finite(r['duration_sec']) or not 0 < r['duration_sec'] <= 30 or round(r['fps'] * r['slow_motion'] * r['duration_sec']) < 2:
        raise ValueError('Invalid duration')
    if set(r) != {'fps', 'duration_sec', 'slow_motion', 'resolution', 'samples'}:
        raise ValueError('Unknown render field')
    if len(r['resolution']) != 2 or any(type(v) is not int or v <= 0 for v in r['resolution']):
        raise ValueError('Invalid resolution')
    if type(r['samples']) is not int or r['samples'] < 1:
        raise ValueError('Invalid sample count')
    if set(s['camera']) != {'location', 'target', 'lens_mm'}:
        raise ValueError('Unknown camera field')
    for key in ('location', 'target'):
        if len(s['camera'][key]) != 3 or not all(finite(v) for v in s['camera'][key]):
            raise ValueError('Invalid camera vector')
    if not finite(s['camera']['lens_mm']) or s['camera']['lens_mm'] <= 0:
        raise ValueError('Invalid lens')


def add_scenario_arguments(parser):
    from pathlib import Path
    parser.add_argument('--scenario-json', type=Path)
    parser.add_argument('--scenario-overrides-json', type=Path)
    for key in PHYSICS_LIMITS:
        parser.add_argument('--' + key.replace('_', '-'), type=float)
    parser.add_argument('--remove-tableware', dest='remove_tableware', action='store_true',
                        help='Remove the tableware bowl standing on the hob from frame 1')
    parser.add_argument('--fps', type=int)
    parser.add_argument('--duration-sec', type=float)
    parser.add_argument('--slow-motion', type=int, choices=(1, 2, 4, 8))
    return parser


def load_scenario(args):
    s = merge(defaults(), json.loads(args.scenario_json.read_text(encoding='utf-8'))) if args.scenario_json else defaults()
    if args.scenario_overrides_json:
        s = merge(s, json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for key in PHYSICS_LIMITS:
        if getattr(args, key, None) is not None:
            s['physics'][key] = getattr(args, key)
    if getattr(args, 'remove_tableware', False):
        s['physics']['tableware_active'] = [0]
    for key in ('fps', 'duration_sec', 'slow_motion'):
        if getattr(args, key, None) is not None:
            s['render'][key] = getattr(args, key)
    validate(s)
    return s
