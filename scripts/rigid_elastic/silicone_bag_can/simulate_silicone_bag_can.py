"""Native solve of one case (libuipc shell/ABD/IPC, physics/solver.py) from the empty or preloaded prepared bag state."""
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
from scene_paths import CASES, OUTPUT, PREPARED, launch, output_path, worker_only

if __name__ == "__main__":
    worker_only()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, default="source")
    parser.add_argument("--out", type=Path, help="output directory (default renders/silicone_bag_can/rebuild/native/<case>)")
    parser.add_argument("--initial", type=Path, help="prepared bag state (default: assets prepared_empty.npz, "
                                                     "or prepared_preloaded.npz for add_second_can)")
    parser.add_argument("--gpu-uuid", default="auto")
    parser.add_argument("--cpu-threads", type=int, default=4)
    a = parser.parse_args()
    out = output_path(a.out or OUTPUT / "native" / a.case)
    if out.exists():
        raise FileExistsError(out)
    command = [sys.executable, "-B", CASE / "physics/solver.py", "--case", a.case, "--out", out,
               "--duration", "4", "--dt", str(1 / 1920), "--velocity-tol", ".02"]
    if a.case != "delete_bag":
        initial = a.initial or PREPARED["preloaded" if a.case == "add_second_can" else "empty"]
        if not initial.is_file():
            raise FileNotFoundError(initial)
        command += ["--initial", initial]
    launch(command, a.gpu_uuid, a.cpu_threads)
