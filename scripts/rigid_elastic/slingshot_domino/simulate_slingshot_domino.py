"""Run the audited CPU solver (physics/simulate_cli.py) with the original case controls."""
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
    sys.path.insert(0,str(CASE/"physics"))
    runpy.run_path(str(CASE/"physics/simulate_cli.py"),run_name="__main__")
