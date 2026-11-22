"""Four seconds, one fixed camera: the clock's fall, the crate's answer."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json
import math
from scene_geometry import (CLOCK_MASS, CLOCK_TIP_SPIN, CLOCK_PUSH, CLOCK_RADIUS, CLOCK_HANG,
                            CRATE_MASS, CRATE_CENTER_XY, CRATE_CENTER_Z, CLOCK_FRICTION,
                            CRATE_FRICTION, CLOCK_RESTITUTION, CRATE_RESTITUTION, FIXTURE_RESTITUTION,
                            SINK_RESTITUTION, GRAVITY_Z)

SCENE_NAME = 'wall_clock_drop'

# Every editable number the scene has. The two anchor arrays exist so the edit
# vocabulary and the ADD-style helpers can talk about "where the clock hangs"
# and "where the crate stands" without scene coordinates leaking into the DSL.
BASELINE_PHYSICS = dict(
    clock_mass=CLOCK_MASS, clock_tip_spin=CLOCK_TIP_SPIN, clock_push=CLOCK_PUSH,
    clock_friction=CLOCK_FRICTION,
    crate_mass=CRATE_MASS, crate_friction=CRATE_FRICTION,
    clock_restitution=CLOCK_RESTITUTION, crate_restitution=CRATE_RESTITUTION,
    floor_restitution=SINK_RESTITUTION, fixture_restitution=FIXTURE_RESTITUTION,
    gravity_z=GRAVITY_Z, crate_active=[1],
    clock_hang=[CLOCK_HANG[0], CLOCK_HANG[1], CLOCK_HANG[2]],
    crate_center=[CRATE_CENTER_XY[0], CRATE_CENTER_XY[1], CRATE_CENTER_Z],
    clock_radius=CLOCK_RADIUS, timed_edits=[])

PHYSICS_LIMITS = {
    'clock_mass': (.05, 20.), 'clock_tip_spin': (-8., 8.), 'clock_push': (0., 2.),
    'clock_friction': (0., 1.5), 'crate_mass': (.05, 20.), 'crate_friction': (0., 1.5),
    'clock_restitution': (0., .95), 'crate_restitution': (0., .95),
    'floor_restitution': (0., .95), 'fixture_restitution': (0., .95),
    'gravity_z': (-60., 0.),
    'clock_radius': (.05, 1.),
}
VECTOR_KEYS = ('clock_hang', 'crate_center')
TOGGLE_KEYS = ('crate_active',)
# Presence of the clock. Optional and on by default, so the published cases
# keep their recorded scenarios; DELETE clock writes [0].
OPTIONAL_PHYSICS = dict(clock_active=[1])
TOTAL_FRAMES = 96


def defaults():
    return dict(schema_version=1, scene=SCENE_NAME, seed=0, physics=deepcopy(BASELINE_PHYSICS),
                render=dict(fps=24, duration_sec=4., slow_motion=1, resolution=[1280, 720], samples=48),
                camera=dict(location=[-3.200, 0.200, 2.050], target=[-0.620, -1.880, 0.700], lens_mm=30.0))


def merge(base, overrides):
    result = deepcopy(base)
    if not isinstance(overrides, dict):
        raise ValueError('Scenario overrides must be an object')
    for key, value in overrides.items():
        if key not in result and key not in OPTIONAL_PHYSICS:
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
    if set(ph) - set(OPTIONAL_PHYSICS) != set(BASELINE_PHYSICS):
        raise ValueError('Unknown editable physics parameter')
    for key in TOGGLE_KEYS + tuple(k for k in OPTIONAL_PHYSICS if k in ph):
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
    parser.add_argument('--remove-crate', dest='remove_crate', action='store_true',
                        help='Remove the pine crate from frame 1')
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
    if getattr(args, 'remove_crate', False):
        s['physics']['crate_active'] = [0]
    for key in ('fps', 'duration_sec', 'slow_motion'):
        if getattr(args, key, None) is not None:
            s['render'][key] = getattr(args, key)
    validate(s)
    return s
