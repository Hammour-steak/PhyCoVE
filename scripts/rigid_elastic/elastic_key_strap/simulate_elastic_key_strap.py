"""Run the native CPU membrane and rigid-key solve of one case.

    simulate_elastic_key_strap.py --case CASE [--out-root DIR | --out DIR] [--duration S] [--dt-factor F] [--rows N]
                                  [--source-cache DIR]

A timed case (keys_mass_5x_at_frame_24) restores the exact source state (qpos, qvel) of its edit frame from
--source-cache (default: the accepted native_solves source solve), applies the edit there and keeps solving.

Writes simulation.npz, trace_240hz.npz, resolved_config.json, scenario_overrides.json, physics_audit.json and
model.xml to DIR/physics/CASE (default root renders/elastic_key_strap/rebuild/<UTC stamp>). Requires numpy,
numba, scipy and mujoco==3.3.7; the accepted solves are in assets/scenes/elastic_key_strap/native_solves.
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

import runpy

sys.path.insert(0, str(CASE))
from scene_paths import CASES, OUTPUT, TIMED_CASES, output_path, stamp

if __name__ == "__main__":
    from pcve_scene_entry import _take
    args, root = _take(sys.argv[1:], "--out-root")
    args, out = _take(args, "--out")
    _, case = _take(args, "--case")
    case = case or "source"
    if case not in CASES + TIMED_CASES:
        raise SystemExit(f"--case must be one of {', '.join(CASES + TIMED_CASES)}")
    target = output_path(Path(out) if out else Path(root or OUTPUT / stamp()) / "physics" / case)
    if target.is_dir() and any(target.iterdir()):
        raise FileExistsError(f"Choose a fresh simulation output: {target}")
    sys.argv[1:] = [*args, "--out", str(target)]
    runpy.run_path(str(CASE / "physics/physics_model.py"), run_name="__main__")
