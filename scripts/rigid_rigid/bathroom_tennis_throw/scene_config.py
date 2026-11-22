"""Four seconds, fixed camera; presence-list stools and a mid-run gravity schedule."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json
import math
from scene_geometry import BALL_MASS

SCENE_NAME = 'bathroom_tennis_throw'
# stool_presence is [stool_a, stool_b].
BASELINE_PHYSICS = dict(
    ball_mass=BALL_MASS, initial_velocity=14.0, aim_shift=0.,
    # A pressurised tennis ball on marble/glass keeps ~0.4 of its normal speed
    # (0.60 x 0.63); a 0.60 x 0.30 pair (0.18) is a dead ball and makes
    # every rebound die on the floor.
    ball_restitution=.60, stool_restitution=.40, fixture_restitution=.63,
    stool_mass=2.5, stool_presence=[1, 1],
    gravity_z=-9.81, timed_edits=[])


def defaults():
    return dict(schema_version=1, scene=SCENE_NAME, seed=0, physics=deepcopy(BASELINE_PHYSICS),
                render=dict(fps=24, duration_sec=4., slow_motion=1, resolution=[1280, 720], samples=32),
                # Framing chosen for the glass -> south wall -> floor -> toilet
                # chain: spawn point, glass impact, wall bounce, toilet face and
                # comeback all project in-frame (bpy check on every case, worst
                # margin 0.09 at the north-shifted aim); ball spans 7-40 px @720p.
                camera=dict(location=[-2.9, 0.2, 2.05], target=[2.6, -3.9, .30], lens_mm=24))


def merge(base, overrides):
    result = deepcopy(base)
    for k, v in overrides.items():
        if k not in result:
            raise ValueError('Unknown field: ' + k)
        result[k] = merge(result[k], v) if isinstance(v, dict) else deepcopy(v)
    return result


def _finite(v):
    return type(v) in (float, int) and math.isfinite(v)


def validate(s):
    if s['scene'] != SCENE_NAME or s['schema_version'] != 1:
        raise ValueError('Wrong scene')
    if set(s['physics']) != set(BASELINE_PHYSICS):
        raise ValueError('Unknown physics field')
    ph = s['physics']
    r = s['render']
    for k, lo, hi in [('ball_mass', .01, .2), ('initial_velocity', 1., 65.), ('aim_shift', -1.2, 1.2),
                      ('stool_mass', .5, 8.), ('ball_restitution', 0., .95), ('stool_restitution', 0., .95),
                      ('fixture_restitution', 0., .95), ('gravity_z', -60., -1.)]:
        if not _finite(ph[k]) or not lo <= ph[k] <= hi:
            raise ValueError(k)
    presence = ph['stool_presence']
    if not isinstance(presence, list) or len(presence) != 2 or any(type(v) is not int or v not in (0, 1) for v in presence):
        raise ValueError('stool_presence must be two 0/1 entries for [stool_a, stool_b]')
    schedule = ph['timed_edits']
    if not isinstance(schedule, list):
        raise ValueError('timed_edits must be a list')
    seen = set()
    for event in schedule:
        if not isinstance(event, dict) or set(event) != {'frame', 'params'}:
            raise ValueError('timed_edits entry')
        frame = event['frame']
        params = event['params']
        if type(frame) is not int or not 2 <= frame <= 96 or frame in seen:
            raise ValueError('timed_edits frame')
        seen.add(frame)
        if not isinstance(params, dict) or not params or set(params) != {'gravity_z'}:
            raise ValueError('timed_edits params may set only gravity_z')
        value = params['gravity_z']
        if not _finite(value) or not -60. <= value <= -1.:
            raise ValueError('timed gravity_z must be finite and point down')
    if type(r['fps']) is not int or r['fps'] <= 0 or 1440 % r['fps']:
        raise ValueError('fps must divide 1440')
    if r['slow_motion'] != 1 or r['duration_sec'] != 4.:
        raise ValueError('Scene is fixed at 4 seconds in real time')
    if len(r['resolution']) != 2 or any(type(v) is not int or v < 1 for v in r['resolution']):
        raise ValueError('resolution')
    if type(r['samples']) is not int or r['samples'] < 1:
        raise ValueError('samples')
    for k in ('location', 'target'):
        if len(s['camera'][k]) != 3 or not all(_finite(v) for v in s['camera'][k]):
            raise ValueError('camera')
    if not _finite(s['camera']['lens_mm']) or s['camera']['lens_mm'] <= 0:
        raise ValueError('lens')


def add_scenario_arguments(p):
    from pathlib import Path
    p.add_argument('--scenario-json', type=Path)
    p.add_argument('--scenario-overrides-json', type=Path)
    p.add_argument('--initial-velocity', type=float)
    p.add_argument('--ball-mass', type=float)
    p.add_argument('--stool-mass', type=float)
    p.add_argument('--aim-shift', type=float)
    p.add_argument('--gravity-z', type=float)
    return p


def load_scenario(args):
    s = defaults()
    for k in ('scenario_json', 'scenario_overrides_json'):
        if getattr(args, k, None):
            s = merge(s, json.loads(getattr(args, k).read_text(encoding='utf-8')))
    for k in ('initial_velocity', 'ball_mass', 'stool_mass', 'aim_shift', 'gravity_z'):
        if getattr(args, k, None) is not None:
            s['physics'][k if k != 'gravity_z' else 'gravity_z'] = getattr(args, k)
    validate(s)
    return s
