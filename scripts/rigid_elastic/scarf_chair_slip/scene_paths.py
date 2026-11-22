"""Paths and launchers for scarf_chair_slip: native inputs, accepted delivery, published suite, outputs."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys

CASE_DIR = Path(__file__).resolve().parent
SCRIPTS = CASE_DIR.parents[1]
REPO = SCRIPTS.parent
for _path in (SCRIPTS, CASE_DIR / "physics"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
from pcve_assets import blender

from common import ASSETS, NATIVE, RUNTIME, WORK  # noqa: E402  (physics/common.py owns the data layout)

SCENE_ID = "scarf_chair_slip"
SUITE = "pcve_scarf_chair_slip_suite"
CASES = ("source", "young_modulus_x10", "density_x2", "friction_x0_2", "add_landing_book", "delete_chair")
CATALOG = {case: "source" if case == "source" else "edit_" + case for case in CASES}


def manifest():
    return json.loads((CASE_DIR / "scene_manifest.json").read_text(encoding="utf-8"))


def _in_repo(value):
    """A recorded path, re-rooted at this checkout when the repository is mounted elsewhere."""
    target = Path(value)
    if not target.is_absolute():
        return REPO / target
    if target.exists() or "renders" not in target.parts:
        return target
    index = len(target.parts) - 1 - target.parts[::-1].index("renders")
    return REPO.joinpath(*target.parts[index:])


def accepted_delivery():
    """Accepted native delivery: audits, portable scenes, GT, receipts and reference videos."""
    return _in_repo(manifest()["data"]["accepted_delivery"])


def current_suite():
    """Published video suite, as named by scene_manifest.json canonical_suites."""
    return _in_repo(manifest()["canonical_suites"][SUITE]["target"])


DELIVERY = accepted_delivery()
OUTPUT = WORK


def worker_only():
    if sys.platform != "linux":
        raise RuntimeError("Solves and renders run on Linux")


def output_path(value):
    target = Path(value).expanduser().resolve()
    for protected in (DELIVERY, current_suite(), ASSETS):
        protected = protected.resolve()
        if target == protected or protected in target.parents:
            raise ValueError("Reproduction output must not be written into the accepted delivery, "
                             "the published suite or the asset store: " + str(target))
    return target


def blender_runtime(value=None):
    """Blender 5.1.0 rendered the accepted delivery; any 4.x+ Cycles build runs the current look."""
    if value:
        return Path(value)
    for pinned in (REPO / "tools/blender-5.1.0-linux-x64/blender",
                   REPO / "tools/blender-4.3.2-linux-x64/blender"):
        if pinned.is_file():
            return pinned
    return blender()


def pool(tool, script, args, gpu, threads, blender_bin=None):
    """Run scene-relative `script` through tools/worker.py (shared GPU policy, leases, receipts; the native
    libuipc runtime must be staged in this checkout's .runtime folder)."""
    worker_only()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    flags = ["--blender-bin", str(blender_bin)] if blender_bin else []
    subprocess.run([sys.executable, "-B", str(CASE_DIR / "tools/worker.py"), "--tool", tool, "--gpu", str(gpu),
                    "--threads", str(threads), "--name", f"{SCENE_ID}_{stamp}", *flags, "--", script,
                    *map(str, args)], check=True)


def direct(command, gpu, threads):
    """Run a command here on the GPU index/UUID the caller has claimed ("cpu" hides every GPU)."""
    worker_only()
    if str(gpu) == "auto":
        raise ValueError("Pass --gpu-uuid with the GPU you have claimed (or 'cpu')")
    env = dict(os.environ, OMP_NUM_THREADS=str(threads),
               CUDA_VISIBLE_DEVICES="" if str(gpu) == "cpu" else str(gpu))
    for key in ("PYTHONHOME", "PYTHONPATH", "LD_PRELOAD"):
        env.pop(key, None)
    subprocess.run([str(part) for part in command], env=env, check=True)
