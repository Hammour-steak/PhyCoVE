"""SI units; editable initial conditions and event edits for the desk scene."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json
import math

SCENE_NAME = 'office_desk_kettle_tip'
# Mass ratio chosen so a PURE GRAVITY topple can knock the cup over: a
# half-full small bottle (0.90 kg) falling onto a thin plastic pen cup
# (0.080 kg) and a plastic ballpoint (0.012 kg). A 0.20 kg ceramic mug is only
# rocked to ~20 deg by the gravity strike. Swept
# 0.05/0.06/0.08/0.10/0.12 kg: the topple is insensitive across that band, so
# 0.080 is picked from the middle rather than from a single lucky cell.
# pen_present and pen_holder_present are one-slot lists so the DSL's DELETE
# binding can switch those bodies off -- either from frame 1 (whole-clip) or
# at a frame partway through, where the body is removed from the live
# simulation instead of never being built.
BASELINE_PHYSICS = dict(kettle_mass=0.90, pen_holder_mass=0.080, pen_mass=0.012,
                        pen_present=[1], pen_holder_present=[1],
                        timed_edits=[])
PHYSICS_LIMITS = dict(kettle_mass=(0.3, 6.0), pen_holder_mass=(0.02, 3.5),
                      pen_mass=(0.004, 1.2))
MASS_KEYS = ('kettle_mass', 'pen_holder_mass', 'pen_mass')
# A timed edit may also switch a body off. Only bodies that the frame loop can
# really drop from the world are listed: a mass can be rewritten at any step,
# but a body that other code still dereferences cannot simply disappear.
TIMED_PRESENCE_KEYS = ('pen_holder_present',)
# Presence switch of the bottle (``kettle``), written only by ``DELETE kettle``.
# It is not part of the source scenario, so the source and the published edits
# keep their exact scenario (and simulation signature); a scenario without it
# has the bottle present.
OPTIONAL_PHYSICS = dict(kettle_present=[1])
TOTAL_FRAMES = 96


def defaults():
    # Camera from the desk's FRONT-LEFT corner, so the topple crosses the
    # frame: |sin| between the view axis and the topple heading is 0.85, and
    # the bottle stays fully visible lying on the desk next to the toppled cup.
    # A 60 mm lens makes the action fill ~40% of the width while keeping every
    # body inside the frame in every case and all 96 frames.
    # Sight-line audit at this position: 8% of sampled body points blocked,
    # all of them grazing the file boxes behind the action rather than the
    # action itself.
    return dict(schema_version=1, scene=SCENE_NAME, seed=0, physics=deepcopy(BASELINE_PHYSICS),
                render=dict(fps=24, duration_sec=4., slow_motion=1, resolution=[960, 540], samples=48),
                camera=dict(location=[-1.13, 0.31, 1.24], target=[-0.02, 0.62, 0.93], lens_mm=60))


def merge(base, overrides):
    result = deepcopy(base)
    if not isinstance(overrides, dict): raise ValueError('Scenario overrides must be an object')
    for key, value in overrides.items():
        if key not in result and key not in OPTIONAL_PHYSICS: raise ValueError(f'Unknown scenario field: {key}')
        result[key] = merge(result[key], value) if isinstance(value, dict) else deepcopy(value)
    return result


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(s):
    if set(s) - {'schema_version', 'scene', 'physics', 'render', 'camera', 'seed'}:
        raise ValueError('Unknown scenario field')
    if s['scene'] != SCENE_NAME or s['schema_version'] != 1: raise ValueError('Wrong scene/schema')
    if not set(BASELINE_PHYSICS) <= set(s['physics']) <= set(BASELINE_PHYSICS) | set(OPTIONAL_PHYSICS):
        raise ValueError('Unknown editable physics parameter')
    kettle_present = s['physics'].get('kettle_present', [1])
    if not isinstance(kettle_present, list) or len(kettle_present) != 1 or type(kettle_present[0]) is not int or kettle_present[0] not in (0, 1):
        raise ValueError('kettle_present must be [0] or [1]')
    present = s['physics']['pen_present']
    if not isinstance(present, list) or len(present) != 1 or type(present[0]) is not int or present[0] not in (0, 1):
        raise ValueError('pen_present must be [0] or [1]')
    holder_present = s['physics']['pen_holder_present']
    if not isinstance(holder_present, list) or len(holder_present) != 1 or type(holder_present[0]) is not int or holder_present[0] not in (0, 1):
        raise ValueError('pen_holder_present must be [0] or [1]')
    if holder_present[0] != 1:
        raise ValueError(
            'pen_holder_present must start at [1]: the pen cup is always in the '
            'source clip. Remove it partway through with a timed DELETE '
            '(DELETE pen_holder AT FRAME n) rather than from frame 1.'
        )
    for key, (low, high) in PHYSICS_LIMITS.items():
        if not finite(s['physics'][key]) or not low <= s['physics'][key] <= high:
            raise ValueError(f'{key} must be finite and within {low}..{high}')
    for entry in s['physics']['timed_edits']:
        if not isinstance(entry, dict) or set(entry) != {'frame', 'params'}:
            raise ValueError(f'Invalid timed edit: {entry!r}')
        frame, params = entry['frame'], entry['params']
        if not isinstance(frame, int) or not 2 <= frame <= TOTAL_FRAMES:
            raise ValueError(f'Timed edit frame must be an int within 2..{TOTAL_FRAMES}')
        allowed = set(MASS_KEYS) | set(TIMED_PRESENCE_KEYS)
        if not isinstance(params, dict) or not params or set(params) - allowed:
            raise ValueError(f'Timed edit may only change {sorted(allowed)}: {entry!r}')
        for key, value in params.items():
            if key in TIMED_PRESENCE_KEYS:
                if value != [0]:
                    raise ValueError(f'Timed {key} must be [0] (the only timed presence change is removal)')
                continue
            low, high = PHYSICS_LIMITS[key]
            if not finite(value) or not low <= value <= high:
                raise ValueError(f'Timed {key} must be finite and within {low}..{high}')
    r = s['render']
    if type(r['fps']) is not int or r['fps'] <= 0: raise ValueError('Invalid fps')
    if type(r['slow_motion']) is not int or r['slow_motion'] not in (1, 2, 4, 8) or 1440 % (r['fps'] * r['slow_motion']):
        raise ValueError('fps * slow_motion must divide the 1440 Hz simulation clock')
    if not finite(r['duration_sec']) or not 0 < r['duration_sec'] <= 30 or round(r['fps'] * r['slow_motion'] * r['duration_sec']) < 2:
        raise ValueError('Invalid duration')
    if len(r['resolution']) != 2 or any(type(v) is not int or v <= 0 for v in r['resolution']): raise ValueError('Invalid resolution')
    if type(r['samples']) is not int or r['samples'] < 1: raise ValueError('Invalid sample count')
    if set(r) != {'fps', 'duration_sec', 'slow_motion', 'resolution', 'samples'}: raise ValueError('Unknown render field')
    if set(s['camera']) != {'location', 'target', 'lens_mm'}: raise ValueError('Unknown camera field')
    for key in ('location', 'target'):
        if len(s['camera'][key]) != 3 or not all(finite(v) for v in s['camera'][key]): raise ValueError('Invalid camera vector')
    if not finite(s['camera']['lens_mm']) or s['camera']['lens_mm'] <= 0: raise ValueError('Invalid lens')


def load_scenario(args):
    s = merge(defaults(), json.loads(args.scenario_json.read_text(encoding='utf-8'))) if args.scenario_json else defaults()
    if args.scenario_overrides_json: s = merge(s, json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for key in PHYSICS_LIMITS:
        if getattr(args, key, None) is not None: s['physics'][key] = getattr(args, key)
    if getattr(args, 'remove_pen', False): s['physics']['pen_present'] = [0]
    for key in ('fps', 'duration_sec', 'slow_motion'):
        if getattr(args, key, None) is not None: s['render'][key] = getattr(args, key)
    validate(s)
    return s


def add_scenario_arguments(parser):
    from pathlib import Path
    parser.add_argument('--scenario-json', type=Path)
    parser.add_argument('--scenario-overrides-json', type=Path)
    for key in PHYSICS_LIMITS: parser.add_argument('--' + key.replace('_', '-'), type=float)
    parser.add_argument('--remove-pen', action='store_true', help='Remove the ballpoint pen from frame 1')
    parser.add_argument('--fps', type=int)
    parser.add_argument('--duration-sec', type=float)
    parser.add_argument('--slow-motion', type=int, choices=(1, 2, 4, 8))
    return parser
