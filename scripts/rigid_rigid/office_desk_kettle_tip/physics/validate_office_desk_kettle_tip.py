"""Fingerprint solver, fixed geometry, initial conditions, and sampling clock."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_project_paths import project_relative as _pcve_project_relative
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib
import json
import math
from scene_config import validate, SCENE_NAME
from scene_geometry import KEYS



def simulation_signature(s):
    payload = dict(scenario=s)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False, default=str).encode()).hexdigest()


def validate_cache(d):
    validate(d['scenario'])
    if d.get('scene') != SCENE_NAME or d.get('schema_version') != 2: raise ValueError('Wrong cache scene/schema')
    if d.get('simulation_signature') != simulation_signature(d['scenario']): raise ValueError('Stale cache; resimulate')
    r = d['scenario']['render']; count = round(r['fps'] * r['slow_motion'] * r['duration_sec'])
    if d['frame_end'] != count or len(d['frames']) != count or set(d['objects']) != set(KEYS): raise ValueError('Incomplete cache')
    if not d['quality']['valid']: raise ValueError('Invalid physical trace')
    ph = d['scenario']['physics']
    pen_present = bool(ph['pen_present'][0])
    # A timed DELETE leaves the body built at frame 1 and gone from the
    # removal frame on, so for that object presence is a per-frame question;
    # the cache's object table still reports it as built.
    removal_frames = [entry['frame'] for entry in ph.get('timed_edits') or []
                      if 'pen_holder_present' in entry['params']]
    holder_removed_at = min(removal_frames) if removal_frames else None
    if holder_removed_at is not None:
        applied = [e for e in d.get('quality', {}).get('timed_events', [])
                   if e.get('parameter') == 'pen_holder_present' and e.get('applied_in_simulation')]
        if len(applied) != 1 or applied[0].get('frame') != holder_removed_at:
            raise ValueError('Timed pen-cup removal was scheduled but not applied in the simulation')
    for i, f in enumerate(d['frames']):
        if f['frame_index'] != i + 1 or abs(f['time_sec'] - i / d['sample_fps']) > 1e-9: raise ValueError('Bad frame clock')
        for key in KEYS:
            state = f[key]
            built_present = (pen_present if key == 'pen'
                             else bool(ph.get('kettle_present', [1])[0]) if key == 'kettle' else True)
            expected_present = (f['frame_index'] < holder_removed_at
                                if key == 'pen_holder' and holder_removed_at is not None
                                else built_present)
            if state.get('present') is not expected_present:
                raise ValueError('Cached object presence differs from scenario')
            if d['objects'][key].get('present') is not built_present:
                raise ValueError('Cached object table differs from scenario')
            if not expected_present:
                if set(state) != {'present'}: raise ValueError('Removed object must not carry transforms')
                continue
            if not all(math.isfinite(v) for row in state['matrix_world'] for v in row): raise ValueError('Nonfinite transform')
