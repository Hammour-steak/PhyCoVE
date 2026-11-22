"""Run the native PyBullet solver at its original integration timestep.

Run with a Python that has numpy and pybullet (the repository's .venv-rigid-elastic).
Default output: renders/spring_block_step/resim/ (never under scripts/).
"""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END

import runpy

if __name__ == "__main__":
    sys.path.insert(0, str(CASE))
    runpy.run_path(str(CASE / "physics/simulate.py"), run_name="__main__")
