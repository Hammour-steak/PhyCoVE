"""Static colliders of the kitchen, shared by the solver and the renderer.

Each box records where it was measured (``source`` and the file's
``asset_sha256``). The renderer builds the visible room from these same boxes,
so this file is the single source of both the collision and the visible
surfaces.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import json

COLLIDER_PATH = _pcve_asset('scenes') / 'kitchen_bowl_fall' / 'room_colliders.json'


def load_colliders():
    """Read the kitchen boxes and check they are well formed."""
    data = json.loads(COLLIDER_PATH.read_text(encoding='utf-8'))
    if data.get('scene') != 'kitchen_bowl_fall':
        raise ValueError('room_colliders.json belongs to another scene')
    for box in data['boxes']:
        if len(box['center']) != 3 or len(box['half_extents']) != 3:
            raise ValueError('Malformed room box: ' + box['name'])
        if any(v <= 0 for v in box['half_extents']):
            raise ValueError('Degenerate room box: ' + box['name'])
    return data
