"""Replay a native cache in the published look (tools/native/realism.py) through the GPU launcher (tools/launch.py)."""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

from tools.launch import run

if __name__=="__main__":run("blender")
