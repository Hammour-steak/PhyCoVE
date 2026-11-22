"""Canonical surface entry point; execute the existing surface_genesis_toy_car_pool.py implementation."""
from pathlib import Path
import runpy
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if __name__ == "__main__":
    target = HERE / 'physics/surface_genesis_toy_car_pool.py'
    sys.argv[0] = str(target)
    runpy.run_path(str(target), run_name="__main__")
