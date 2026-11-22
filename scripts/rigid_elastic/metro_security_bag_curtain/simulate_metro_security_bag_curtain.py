"""Run the float64 strip-shell and rigid-bag simulation (CPU, Numba).

Native options: --case {source,young_modulus_x100,belt_speed_x2,friction_x0p02,delete_curtain,delete_curtain_at_frame_12,all}
--tag NAME --out-root DIR --dt S --iterations N --duration S --source-cache DIR. A timed case (edit_vocab.TIMED_DSL,
e.g. delete_curtain_at_frame_12) restores the exact source state of its edit frame from --source-cache (default: the
accepted native source states), applies the edit there and keeps solving; frames before it are the source states.
Each case writes
<out-root>/<case>/{states.npz,simulation_config.json,simulation_report.json}; the default
out-root is renders/metro_security_bag_curtain/rebuild_<UTC stamp>/simulation.
"""

from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2]
# PCVE_UNIFIED_ENTRY_BEGIN
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, 'simulate')
# PCVE_UNIFIED_ENTRY_END

import runpy

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scene_paths import CASE, default_rebuild_root, ensure_numpy_runtime, stamp
    ensure_numpy_runtime()
    if not any(arg == "--tag" or arg.startswith("--tag=") for arg in sys.argv[1:]):
        sys.argv += ["--tag", f"reproduction_{stamp()}"]
    if not any(arg == "--out-root" or arg.startswith("--out-root=") for arg in sys.argv[1:]):
        sys.argv += ["--out-root", str(default_rebuild_root() / "simulation")]
    sys.path.insert(0, str(CASE / "physics"))
    runpy.run_path(str(CASE / "physics" / "simulate_case.py"), run_name="__main__")
