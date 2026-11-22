"""Hashes of the asset files a built case depends on (checked by --skip-existing)."""
import hashlib

from pcve_assets import asset as _pcve_asset
from pcve_project_paths import project_relative as _pcve_project_relative


def input_hashes():
    files = [(_pcve_asset('models') / n) for n in ('fresh_orange.glb', 'orange_fruit.glb')]
    files += sorted(p for p in _pcve_asset('polyhaven/kitchen_orange_collision').rglob('*') if p.is_file())
    return {str(_pcve_project_relative(p)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
