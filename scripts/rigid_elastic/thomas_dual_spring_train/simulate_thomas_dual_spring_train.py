"""Run the original MuJoCo model at native substeps over four physical seconds."""
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
from physics.native import CASES, run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--out", type=Path, default=CASE.parents[2] / "renders/thomas_dual_spring_train/simulation")
    args = parser.parse_args()
    cases = [args.case] if args.case else CASES
    if any((args.out / case).exists() for case in cases):
        parser.error("Use a fresh output location")
    for case in cases:
        run(case, output=args.out, duration_s=4.)
