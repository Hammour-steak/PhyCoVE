"""Native solve of one case: closed finite-strain rubber shell + MuJoCo 3.17.0 CPU contacts (physics/physics.py).

Starts from the shared prepared initial state stored in the accepted increment, 160 loop segments x 2 rows,
dt = 1/384000 s, 4.000 s, states saved at 480 Hz. The accepted states themselves are in the increment; a new
solve goes to a fresh folder outside scripts/ (default renders/rubber_band_wood_slider/rebuild_<UTC>/simulation/<case>).
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

sys.path.insert(0, str(CASE))
import argparse
import os
import subprocess
from scene_paths import CASES, MUJOCO, RENDERS, extract, output_path, python_runtime, stamp

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", choices=CASES, default="source")
    p.add_argument("--out", type=Path, help="fresh case folder (default renders/rubber_band_wood_slider/rebuild_<UTC>/simulation/<case>)")
    p.add_argument("--python-runtime", type=Path, help="Python 3.12 with numpy 1.26.4 and numba 0.60.0 (default: .venv-rigid-elastic)")
    p.add_argument("--mujoco-runtime", type=Path, default=MUJOCO, help="folder holding the unpacked mujoco 3.17.0 package")
    p.add_argument("--cpu-threads", type=int, default=1)
    a = p.parse_args()
    target = output_path(a.out or RENDERS / f"rebuild_{stamp()}" / "simulation" / a.case)
    if target.exists():
        p.error("Choose a fresh case output folder")
    if not (a.mujoco_runtime / "mujoco").is_dir():
        p.error(f"MuJoCo 3.17.0 is not unpacked in {a.mujoco_runtime} (see the scene README, 'Running')")
    initial = extract("reproduction/prepared_initial.npz", target.parent / "prepared_initial.npz")
    env = dict(os.environ, PCVE_MUJOCO_RUNTIME=str(a.mujoco_runtime), OMP_NUM_THREADS=str(a.cpu_threads),
               NUMBA_NUM_THREADS=str(a.cpu_threads), CUDA_VISIBLE_DEVICES="")
    raise SystemExit(subprocess.run([str(python_runtime(a.python_runtime)), "-B", str(CASE / "physics/physics.py"),
                                     "--case", a.case, "--out", str(target), "--n", "160", "--dt", str(1 / 384000),
                                     "--seconds", "4", "--initial", str(initial)], env=env).returncode)
