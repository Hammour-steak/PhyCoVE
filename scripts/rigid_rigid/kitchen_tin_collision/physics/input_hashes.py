"""Hashes of the asset files a built case depends on (checked by --skip-existing)."""
import hashlib

from pcve_assets import asset as _pcve_asset
from pcve_project_paths import project_relative as _pcve_project_relative

MODEL_FILES = ('tuna_can.glb', 'sardine_can.glb')
# The bistro room's scanned furniture, textures and window view.
SCENE_ASSETS = 'polyhaven/kitchen_tin_collision'


def input_hashes():
    files = [(_pcve_asset('models') / n) for n in MODEL_FILES]
    files += sorted(p for p in _pcve_asset(SCENE_ASSETS).rglob('*') if p.is_file())
    return {str(_pcve_project_relative(p)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
