"""Paths and launchers for silicone_bag_can: native inputs, accepted delivery, published suite, outputs."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys

CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
REPO = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from pcve_assets import asset, blender

SCENE_ID = "silicone_bag_can"
SUITE = "pcve_silicone_bag_can_suite"
CASES = ("source", "can_mass_x2", "bag_young_x0_25", "bag_young_x5", "delete_bag", "add_second_can")
CATALOG = {case: "source" if case == "source" else "edit_" + case for case in CASES}
ASSETS = asset("scenes/" + SCENE_ID)
# Per-case native solver output of the accepted delivery (simulation.npz with the shell states,
# rigid transforms and sample clock, plus simulation_config.json).
NATIVE = ASSETS / "native"
# Packed kitchen that both renderers open, and the two prepared bag states the native solve starts from.
TEMPLATE = ASSETS / "source_scene.blend"
PREPARED = {"empty": ASSETS / "prepared_empty.npz", "preloaded": ASSETS / "prepared_preloaded.npz"}


def manifest():
    return json.loads((CASE / "scene_manifest.json").read_text(encoding="utf-8"))


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
    """Accepted native delivery: audits, GT, receipts and the six reference videos."""
    return _in_repo(manifest()["data"]["accepted_delivery"])


def current_suite():
    """Published video suite, as named by scene_manifest.json canonical_suites."""
    return _in_repo(manifest()["canonical_suites"][SUITE]["target"])


DELIVERY = accepted_delivery()
OUTPUT = REPO / "renders" / SCENE_ID / "rebuild"


def worker_only():
    """Native solves and accepted-look renders run on Linux through tools/worker_run.py (staged libuipc runtime)."""
    if sys.platform != "linux":
        raise RuntimeError("Native solves run on Linux with the staged libuipc runtime")


def output_path(value):
    target = Path(value).expanduser().resolve()
    for protected in (DELIVERY, current_suite(), ASSETS):
        protected = protected.resolve()
        if target == protected or protected in target.parents:
            raise ValueError("Reproduction output must not be written into the accepted delivery, "
                             "the published suite or the asset store: " + str(target))
    return target


def blender_runtime(value=None):
    pinned = REPO / "tools/blender-4.3.2-linux-x64/blender"
    return Path(value) if value else (pinned if pinned.is_file() else blender())


def launch(command, gpu, threads, env=None):
    """Run a native or accepted-look job on a pool worker through tools/worker_run.py (GPU lease, receipt)."""
    worker_only()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    launcher = [sys.executable, "-B", str(CASE / "tools/worker_run.py"), "--gpu", str(gpu), "--name", f"bag_{stamp}",
                "--wait", "--", *map(str, command)]
    payload = dict(os.environ if env is None else env, OMP_NUM_THREADS=str(threads))
    subprocess.run(launcher, env=payload, check=True)


def direct(command, gpu, threads):
    """Run a command here on the GPU index/UUID the caller has claimed ("cpu" hides every GPU)."""
    if sys.platform != "linux":
        raise RuntimeError("Render on Linux")
    if str(gpu) == "auto":
        raise ValueError("Pass --gpu-uuid with the GPU you have claimed (or 'cpu')")
    env = dict(os.environ, OMP_NUM_THREADS=str(threads),
               CUDA_VISIBLE_DEVICES="" if str(gpu) == "cpu" else str(gpu))
    for key in ("PYTHONHOME", "PYTHONPATH", "LD_PRELOAD"):
        env.pop(key, None)
    subprocess.run([str(part) for part in command], env=env, check=True)
