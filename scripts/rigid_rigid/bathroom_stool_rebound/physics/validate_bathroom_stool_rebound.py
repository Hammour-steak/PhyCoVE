"""Fingerprint solver, fixed geometry, initial conditions, and sampling clock."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_project_paths import project_relative as _pcve_project_relative
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib
import math
from scene_config import validate, SCENE_NAME
from scene_geometry import KEYS


def simulation_signature(s):
    # Collision meshes are physics inputs: re-exporting bathtub_collision.obj or
    # alcove_collision.obj moves contact surfaces, so `--render-only` must not
    # reuse a trace computed against different geometry.
    meshes = sorted(_pcve_asset("scenes/bathroom_stool_rebound").glob("*collision*.obj"))
    inputs = {str(_pcve_project_relative(path)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in meshes if path.is_file()}
    payload = dict(inputs=inputs, scenario=s)
    return hashlib.sha256(json_payload(payload).encode()).hexdigest()


def json_payload(payload):
    import json
    return json.dumps(payload, sort_keys=True, allow_nan=False, default=str)


def validate_cache(d):
    import json
    validate(d['scenario'])
    if d.get('scene') != SCENE_NAME or d.get('schema_version') != 2: raise ValueError('Wrong cache scene/schema')
    if d.get('simulation_signature') != simulation_signature(d['scenario']): raise ValueError('Stale cache; resimulate')
    r = d['scenario']['render']; count = round(r['fps'] * r['slow_motion'] * r['duration_sec'])
    if d['frame_end'] != count or len(d['frames']) != count or set(d['objects']) != set(KEYS): raise ValueError('Incomplete cache')
    if not d['quality']['valid']: raise ValueError('Invalid physical trace')
    ph = d['scenario']['physics']
    for i, f in enumerate(d['frames']):
        if f['frame_index'] != i + 1 or abs(f['time_sec'] - i / d['sample_fps']) > 1e-9: raise ValueError('Bad frame clock')
        expected = {'stool': True}
        for key in KEYS:
            state = f[key]
            if state.get('present') is not expected[key] or d['objects'][key].get('present') is not expected[key]:
                raise ValueError('Cached object presence differs from scenario')
            if not expected[key]:
                if set(state) != {'present'}: raise ValueError('Removed object must not carry transforms')
                continue
            if not all(math.isfinite(v) for row in state['matrix_world'] for v in row): raise ValueError('Nonfinite transform')
