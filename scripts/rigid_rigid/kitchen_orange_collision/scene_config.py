"""SI units; editable launch conditions, masses and pairwise coefficients."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json
import math

SCENE_NAME = 'kitchen_orange_collision'
# Two friction coefficients, one per body material rather than per contact pair:
# Bullet stores a single ``lateralFriction`` per body and multiplies the two
# values at a contact, so the honest declaration is "orange skin" and "table".
# The defaults (.72 and 1.0) are the source values, so the source clip is
# reproducible from this file alone.
#
# ``rear_oranges`` is a count, not a continuous knob: 0 is the source case
# (two oranges), 2 queues two whole oranges directly behind the struck one
# and turns the scene into a four-body transfer. It is the one property whose
# baseline is exactly 0, so its edit is spelled ``TO 2`` rather than ``TIMES``.
BASELINE_PHYSICS = dict(driver_mass=.17, cut_mass=.14, initial_velocity=.90,
                        restitution=.40, orange_friction=.72, table_friction=1.,
                        rear_oranges=0, timed_edits=[])
PHYSICS_LIMITS = dict(driver_mass=(.05,2.), cut_mass=(.05,2.),
                      initial_velocity=(.2,3.2), restitution=(0.,.95),
                      orange_friction=(.05,1.5), table_friction=(0.,2.))
REAR_ORANGES_RANGE = (0, 2)
# Presence switches of the rolling orange and of the sliced orange, written only
# by their DELETE edits. They are not part of the source scenario, so the source
# and the published edits keep their exact scenario (and simulation signature);
# a scenario without them has both oranges present.
OPTIONAL_PHYSICS = dict(driver_active=[1], cut_active=[1])
TOTAL_FRAMES = 96


def defaults():
    return dict(schema_version=1, scene=SCENE_NAME, seed=0, physics=deepcopy(BASELINE_PHYSICS),
                render=dict(fps=24, duration_sec=4., slow_motion=1, resolution=[1280,720], samples=48),
                camera=dict(location=[-1.34,-1.40,1.42], target=[.02,.08,.80], lens_mm=27))


def merge(base, overrides):
    result = deepcopy(base)
    if not isinstance(overrides, dict): raise ValueError('Scenario overrides must be an object')
    for key,value in overrides.items():
        if key not in result and key not in OPTIONAL_PHYSICS: raise ValueError(f'Unknown scenario field: {key}')
        result[key] = merge(result[key],value) if isinstance(value,dict) else deepcopy(value)
    return result


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def validate(s):
    if set(s) - {'schema_version','scene','physics','render','camera','seed'}:
        raise ValueError('Unknown scenario field')
    if s['scene'] != SCENE_NAME or s['schema_version'] != 1: raise ValueError('Wrong scene/schema')
    if not set(BASELINE_PHYSICS) <= set(s['physics']) <= set(BASELINE_PHYSICS) | set(OPTIONAL_PHYSICS):
        raise ValueError('Unknown editable physics parameter')
    for name in OPTIONAL_PHYSICS:
        active=s['physics'].get(name,[1])
        if not isinstance(active,list) or len(active)!=1 or type(active[0]) is not int or active[0] not in (0,1):
            raise ValueError(f'{name} must be [0] or [1]')
    for key,(low,high) in PHYSICS_LIMITS.items():
        if not finite(s['physics'][key]) or not low <= s['physics'][key] <= high:
            raise ValueError(f'{key} must be finite and within {low}..{high}')
    # The edit vocabulary can only spell counts as scalars (``TO 2``), so a whole
    # number written as 2.0 is accepted and normalised to the count it means.
    rear=s['physics']['rear_oranges']
    if isinstance(rear,bool) or not finite(rear) or float(rear)!=int(rear) \
            or not REAR_ORANGES_RANGE[0] <= rear <= REAR_ORANGES_RANGE[1]:
        raise ValueError(f'rear_oranges must be a whole number within {REAR_ORANGES_RANGE}')
    s['physics']['rear_oranges']=int(rear)
    r=s['render']
    if type(r['fps']) is not int or r['fps'] <= 0: raise ValueError('Invalid fps')
    if type(r['slow_motion']) is not int or r['slow_motion'] not in (1,2,4,8) or 1440 % (r['fps']*r['slow_motion']):
        raise ValueError('fps * slow_motion must divide the 1440 Hz simulation clock')
    if not finite(r['duration_sec']) or not 0 < r['duration_sec'] <= 30 or round(r['fps']*r['slow_motion']*r['duration_sec']) < 2:
        raise ValueError('Invalid duration')
    if len(r['resolution']) != 2 or any(type(v) is not int or v <= 0 for v in r['resolution']): raise ValueError('Invalid resolution')
    if type(r['samples']) is not int or r['samples'] < 1: raise ValueError('Invalid sample count')
    if set(r) != {'fps','duration_sec','slow_motion','resolution','samples'}: raise ValueError('Unknown render field')
    if set(s['camera']) != {'location','target','lens_mm'}: raise ValueError('Unknown camera field')
    for key in ('location','target'):
        if len(s['camera'][key]) != 3 or not all(finite(v) for v in s['camera'][key]): raise ValueError('Invalid camera vector')
    if not finite(s['camera']['lens_mm']) or s['camera']['lens_mm'] <= 0: raise ValueError('Invalid lens')


def load_scenario(args):
    s=merge(defaults(),json.loads(args.scenario_json.read_text(encoding='utf-8'))) if args.scenario_json else defaults()
    if args.scenario_overrides_json: s=merge(s,json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for key in BASELINE_PHYSICS:
        if key in ('rear_oranges','timed_edits'):continue
        if getattr(args,key,None) is not None: s['physics'][key]=getattr(args,key)
    if getattr(args,'rear_oranges',None) is not None:s['physics']['rear_oranges']=int(args.rear_oranges)
    for key in ('fps','duration_sec','slow_motion'):
        if getattr(args,key,None) is not None: s['render'][key]=getattr(args,key)
    validate(s)
    return s


def add_scenario_arguments(parser):
    from pathlib import Path
    parser.add_argument('--scenario-json',type=Path)
    parser.add_argument('--scenario-overrides-json',type=Path)
    for key in PHYSICS_LIMITS: parser.add_argument('--'+key.replace('_','-'),type=float)
    parser.add_argument('--rear-oranges',type=int,help='Whole oranges queued behind the struck one (0..2)')
    parser.add_argument('--fps',type=int)
    parser.add_argument('--duration-sec',type=float)
    parser.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    return parser
