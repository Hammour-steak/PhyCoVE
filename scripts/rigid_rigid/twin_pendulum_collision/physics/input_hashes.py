"""Hashes of the asset files a built case depends on (checked by --skip-existing)."""
import hashlib

from pcve_assets import asset as _pcve_asset
from pcve_project_paths import project_relative as _pcve_project_relative


def input_hashes():
    # Every file of this scene's own Poly Haven assets.
    files = sorted(_pcve_asset('polyhaven/twin_pendulum_collision').rglob('*'))
    return {str(_pcve_project_relative(p)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
