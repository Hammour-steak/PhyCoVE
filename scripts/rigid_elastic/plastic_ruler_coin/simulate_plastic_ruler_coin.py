"""Run the native CPU solver of one case (coin, cantilevered ruler) into a fresh folder.

Default output: renders/plastic_ruler_coin/rebuild/physics/<case>; --out-root DIR writes DIR/physics/<case>,
--out DIR writes exactly DIR. Runtime: .venv-rigid-elastic (numpy, scipy, numba); CPU only.
"""

from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, 'simulate')
# PCVE_UNIFIED_ENTRY_END

import os
import runpy
sys.path.insert(0, str(CASE))
from scene_paths import OUTPUT, RUNTIME, output_path

if __name__ == "__main__":
    from pcve_scene_entry import _take
    args, out = _take(sys.argv[1:], "--out")
    args, root = _take(args, "--out-root")
    _, case = _take(args, "--case")
    path = output_path(Path(out) if out else Path(root or OUTPUT) / "physics" / (case or "source"))
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Choose a fresh simulation output: {path}")
    os.environ.setdefault("NUMBA_CACHE_DIR", str(RUNTIME / "numba_cache"))
    sys.argv[1:] = [*args, "--out", str(path)]
    runpy.run_path(str(CASE / "physics/physics.py"), run_name="__main__")
