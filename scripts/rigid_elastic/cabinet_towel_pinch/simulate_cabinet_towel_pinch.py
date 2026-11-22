"""Run the accepted native libuipc shell/ABD solve for one case through tools/worker.py (staged runtime, GPU lease)."""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END

sys.path.insert(0, str(CASE))
import argparse
import json
from scene_paths import CASES, NATIVE, OUTPUT, SEED, output_path, pool

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=CASES, default="source")
    p.add_argument("--out", type=Path, help="fresh output directory (default renders/cabinet_towel_pinch/rebuild/<case>/simulation)")
    p.add_argument("--gpu-uuid", default="auto")
    p.add_argument("--cpu-threads", type=int, default=6)
    a = p.parse_args()
    out = output_path(a.out or OUTPUT / a.case / "simulation")
    if out.exists():
        raise FileExistsError(out)
    # Same clock and mesh pitch as the accepted native solve of this case.
    cfg = json.loads((NATIVE / a.case / "simulation_config.json").read_bytes())
    options = ["--case", a.case, "--out", out, "--dt", cfg["dt"], "--pitch", cfg["pitch"], "--duration", 4.,
               "--initial-state", SEED]
    pool("python", "physics/simulate.py", options, a.gpu_uuid, a.cpu_threads)
