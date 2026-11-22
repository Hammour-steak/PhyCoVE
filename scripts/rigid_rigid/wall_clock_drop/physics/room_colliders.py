"""Static colliders of the boot room, loaded from the scene's collider file.

The boxes are measured from a game-level room model (``futuristic_room.glb``;
the file records that model's name, hash and probe values as provenance). The
rendered room is built on these boxes (``appearance/boot_room.py``), so the
file itself is the room's definition and does not depend on that model.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import json

COLLIDER_PATH = _pcve_asset('scenes') / 'wall_clock_drop' / 'room_colliders.json'


def load_colliders():
    """Read and sanity-check the room boxes."""
    data = json.loads(COLLIDER_PATH.read_text(encoding='utf-8'))
    if data.get('scene') != 'wall_clock_drop':
        raise ValueError('room_colliders.json belongs to another scene')
    for box in data['boxes']:
        if len(box['center']) != 3 or len(box['half_extents']) != 3:
            raise ValueError('Malformed room box: ' + box['name'])
        if any(v <= 0 for v in box['half_extents']):
            raise ValueError('Degenerate room box: ' + box['name'])
    return data
