"""Reproduce the accepted native spring-balance trajectories and compare them with the caches, or solve into a new directory."""

from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END

import argparse
import json

from physics.scene import DELIVERY
from scene_paths import output_path, suite


def main():
    from edit_vocab import CASE_DSL, TIMED_DSL

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=[*CASE_DSL, *TIMED_DSL, "all"], default="all",
                        help="all: the five whole-clip cases")
    parser.add_argument("--output-dir", type=Path,
                        help="new output root (cases/<case>/), outside scripts/, the assets and the suite; "
                             "without it the solve is compared with the accepted cache")
    parser.add_argument("--verify-cache", action="store_true", help="compare with the accepted cache (the default without --output-dir)")
    parser.add_argument("--source-cache", type=Path,
                        help="timed edits: accepted source native_dynamics.npz (default: the delivered source case)")
    args = parser.parse_args()
    if args.verify_cache and args.output_dir:
        parser.error("Choose cache comparison or a new simulation directory")
    cases = list(CASE_DSL) if args.case == "all" else [args.case]
    if args.output_dir:
        try:
            output = output_path(args.output_dir)
        except ValueError as error:
            parser.error(str(error))
        if any((output / "cases" / name).exists() for name in cases):
            parser.error("An output for a selected case already exists")
    from physics import simulate_spring as solver
    import numpy as np

    if args.output_dir:
        solver.OUT = output
    source_cache = args.source_cache or DELIVERY / "cases" / "source" / "native_dynamics.npz"
    for name in cases:
        report, states, _ = solver.solve(name, write=args.output_dir is not None,
                                         source_cache=source_cache if name in TIMED_DSL else None)
        if args.output_dir:
            print(json.dumps({"case": name, "native_cache_sha256": report["native_cache_sha256"]}))
            continue
        # Timed cases are not part of the accepted delivery; their cache is published with the suite case.
        reference = (suite() / "cases" / f"edit_{name}" / "native_metadata"
                     if name in TIMED_DSL else DELIVERY / "cases" / name)
        with np.load(reference / "native_dynamics.npz", allow_pickle=False) as saved:
            error = float(np.max(np.abs(states - saved["states"])))
        if error >= 1e-9:
            raise ValueError(f"{name}: state difference {error}")
        print(json.dumps({"case": name, "reproduced": True, "maximum_state_error": error}))


if __name__ == "__main__":
    main()
