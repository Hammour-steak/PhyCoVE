"""Solve one case of the coupled foam / guided cup / rolling ball / hinged flag model (CPU, numpy + scipy)."""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END

import argparse
import subprocess

from edit_vocab import CASE_DSL, TIMED_DSL
from scene_paths import OUTPUT, output_path

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=[*CASE_DSL, *TIMED_DSL], default="source",
                   help="timed cases rerun the source to the edit frame in the same solve (run the source on the same host to pair them)")
    p.add_argument("--out-root", type=Path, default=OUTPUT, help="writes <root>/physics/<case>; default renders/silicone_block_chain/rebuild")
    p.add_argument("--out", type=Path, help="explicit case directory (overrides --out-root)")
    a = p.parse_args()
    out = output_path(a.out or a.out_root / "physics" / a.case)
    if out.exists():
        raise FileExistsError(out)
    subprocess.run([sys.executable, "-B", str(CASE / "physics/physics.py"), "--case", a.case, "--out", str(out)], check=True)
