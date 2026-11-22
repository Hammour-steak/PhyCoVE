"""Export the accepted native state of one case, or solve the timed edit natively.

--mode native     copy the 120 Hz native state (481 samples, 0-4 s) from assets/scenes/football_goal_net/native/<case>/
--mode canonical  copy the 24 Hz evaluation subset (every fifth native sample, 96 samples) of the accepted media delivery
--mode solve      timed case mass_double_at_frame_8 only: run physics/solve_timed.py (source physics to frame 8 on the
                  accepted solver snapshot, then the edit); the whole-clip cases are kept as their accepted native states
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

import argparse
sys.path.insert(0, str(CASE))
from tools.retained import CASES, SUITE, export, full_input, read  # noqa: E402
from edit_vocab import TIMED_DSL  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", choices=CASES + tuple(TIMED_DSL), default="source")
    p.add_argument("--mode", choices=("native", "canonical", "solve"), default="native")
    p.add_argument("--out", type=Path, required=True, help="fresh output path (a file for native/canonical, a folder for solve)")
    a = p.parse_args()
    if a.case in TIMED_DSL:
        if a.mode != "solve":
            p.error("a timed case exists only as a native solve (--mode solve)")
        import subprocess
        raise SystemExit(subprocess.run([sys.executable, "-B", str(CASE / "physics/solve_timed.py"), "--case", a.case, "--out", str(a.out)]).returncode)
    if a.mode == "solve":
        p.error("--mode solve applies to a timed case; a whole-clip case is exported from its accepted native state")
    else:
        bind = read(SUITE / "cases" / a.case / "canonical_export_manifest.json")
        if a.mode == "native":
            source, digest = full_input(a.case) / "simulation.npz", bind["source_native_sha256"]
        else:
            source, digest = SUITE / "cases" / a.case / "simulation.npz", bind["canonical_state_sha256"]
        export(source, a.out, digest)
