"""Render one case of the current look from the registered native states (Blender 4.3.2, GPU or CPU).

See tools/render_case.py --help for the native options.
"""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

import runpy

if __name__ == "__main__":
    runpy.run_path(str(CASE / "tools/render_case.py"), run_name="__main__")
