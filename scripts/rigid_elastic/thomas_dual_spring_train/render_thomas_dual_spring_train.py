"""Lease an idle GPU and render the published look (appearance/realism.py over appearance/render.py) from the native
96-sample states."""
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
    work = CASE.parents[2] / "renders/thomas_dual_spring_train"
    for flag, default in [("--mode", "render"), ("--state-root", str(work / "simulation/accepted")),
                          ("--out", str(work / "renders"))]:
        if not any(x == flag or x.startswith(flag + "=") for x in sys.argv[1:]):
            sys.argv.extend([flag, default])
    runpy.run_path(str(CASE / "tools/worker.py"), run_name="__main__")
