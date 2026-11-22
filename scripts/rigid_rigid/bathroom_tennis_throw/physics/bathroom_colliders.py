"""Static bathroom fixture colliders exported from big_project.glb."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib
import json

COLLIDER_PATH = _pcve_asset('scenes') / 'bathroom_tennis_throw' / 'bathroom_colliders.json'


def load_colliders():
    """Read the fixture boxes and verify the source GLB is unchanged."""
    data = json.loads(COLLIDER_PATH.read_text(encoding='utf-8'))
    asset = _pcve_asset('models') / data['asset']
    if hashlib.sha256(asset.read_bytes()).hexdigest() != data['asset_sha256']:
        raise ValueError('Bathroom collider export is stale; run tools/export_bathroom_colliders.py again')
    for box in data['boxes']:
        if len(box['center']) != 3 or len(box['half_extents']) != 3:
            raise ValueError('Malformed fixture box: ' + box['name'])
        if any(v <= 0 for v in box['half_extents']):
            raise ValueError('Degenerate fixture box: ' + box['name'])
    return data
