from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib
import json
import math
from scene_geometry import KEYS
from scene_config import validate, SCENE_NAME

from pcve_project_paths import project_relative as _pcve_project_relative
def signature(s):
    import hashlib, json
    payload = dict(scenario=s)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False, default=str).encode()).hexdigest()
def validate_cache(d):
    s=d['scenario']; validate(s)
    if d['scene'] != SCENE_NAME or d.get('simulation_signature') != signature(s):
        raise ValueError('Stale or foreign physics cache; resimulate')
    count=round(s['render']['fps']*s['render']['duration_sec'])
    if len(d['frames']) != count or d['frame_end'] != count: raise ValueError('Incomplete trajectory')
    if not d['quality']['valid']: raise ValueError('Physics trace failed validation')
    for i,row in enumerate(d['frames']):
        if row['frame_index'] != i+1 or abs(row['time_sec']-i/d['fps'])>1e-9:
            raise ValueError('Invalid frame clock')
        for k in KEYS:
            if row[k].get('present') is False: continue
            if not all(math.isfinite(v) for field in ('location','quaternion_xyzw','linear_velocity','angular_velocity') for v in row[k][field]):
                raise ValueError('Nonfinite rigid-body state')
