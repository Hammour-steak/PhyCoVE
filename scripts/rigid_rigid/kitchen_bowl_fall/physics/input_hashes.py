"""Hashes of the asset files a built case depends on (checked by --skip-existing)."""
import hashlib

from pcve_assets import asset as _pcve_asset
from pcve_project_paths import project_relative as _pcve_project_relative


# The collider file both the solve and the render build the kitchen from.
HASHED_ASSETS = ('scenes/kitchen_bowl_fall/room_colliders.json',)


def input_hashes():
    files = [_pcve_asset(rel) for rel in HASHED_ASSETS]
    return {str(_pcve_project_relative(p)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
