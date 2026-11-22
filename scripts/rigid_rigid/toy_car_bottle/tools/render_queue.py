"""Batch sampling for toy_car_bottle: the builder's ``batch_main``.

Each sample scales every simulated parameter of the vocabulary by a seeded
random factor in 0.8-1.2 and is built with the builder's own run_case.
"""
# PCVE_UNIFIED_ENTRY_BEGIN

# Resolve this scene folder and the repository assets directory.
import sys as _pcve_local_sys
from pathlib import Path as _PcveLocalPath
_pcve_scene_dir = _PcveLocalPath(__file__).resolve().parents[1]
_pcve_scripts_root = _pcve_scene_dir.parents[1]
_pcve_local_sys.path.insert(0, str(_pcve_scripts_root))
_PCVE_PROJECT_ROOT = next(p for p in _pcve_scene_dir.parents if (p / 'scripts').is_dir())
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _pcve_scene_dir / _scene_sub if _scene_sub else _pcve_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _pcve_local_sys.path:
        _pcve_local_sys.path.insert(1, str(_scene_sub_dir))
# PCVE_UNIFIED_ENTRY_END

from build_pcve_toy_car_bottle import batch_main


if __name__ == "__main__":
    batch_main("toy_car_bottle")
