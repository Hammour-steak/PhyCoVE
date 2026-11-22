"""Hashes of the asset files a built case depends on (checked by --skip-existing)."""
import hashlib

from pcve_assets import asset as _pcve_asset
from pcve_project_paths import project_relative as _pcve_project_relative


def input_hashes():
    files = [_pcve_asset('models') / n for n in ('hotwheels_technetium__www.vecarz.com.glb', 'cartoonish_toy_car.glb')]
    # The playroom: scanned floor maps and the furniture (glTF, buffers, textures).
    files += sorted(p for p in (_pcve_asset('') / 'polyhaven' / 'toy_car_collision').rglob('*') if p.is_file())
    return {str(_pcve_project_relative(p)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
