"""Repository paths, output protection and runtime selection for picnic_ground_blanket."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys

from pcve_assets import asset, blender

CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
REPO = SCRIPTS.parent
SCENE_ID = "picnic_ground_blanket"
SUITE = "pcve_picnic_ground_blanket_suite"
MANIFEST = json.loads((CASE / "scene_manifest.json").read_text(encoding="utf-8"))


def repo_path(value):
    """A recorded path inside this repository; absolute paths re-root from renders/ or assets/ on."""
    target = Path(value)
    if not target.is_absolute():
        return REPO / target
    if target.exists():
        return target
    for anchor in ("renders", "assets", "archive"):
        if anchor in target.parts:
            index = len(target.parts) - 1 - target.parts[::-1].index(anchor)
            return REPO.joinpath(*target.parts[index:])
    return target


# Current published suite (scene_manifest.json canonical_suites) and the native render
# delivery behind its videos (scene_manifest.json data.accepted_delivery).
SUITE_DIR = repo_path(MANIFEST["canonical_suites"][SUITE]["target"])
DELIVERY = repo_path(MANIFEST["data"]["accepted_delivery"])
OUTPUT = REPO / "renders" / SCENE_ID / "rebuild"


def require_linux():
    """The libuipc CUDA solve and its GPU launcher (tools/worker_run.py) run on Linux."""
    if sys.platform != "linux":
        raise RuntimeError("The native solve runs on Linux with a CUDA GPU (tools/worker_run.py)")


def output_path(value):
    target = Path(value).expanduser().resolve()
    for protected in (SUITE_DIR, DELIVERY, asset(f"scenes/{SCENE_ID}")):
        protected = protected.resolve()
        if target == protected or protected in target.parents:
            raise ValueError("Reproduction output must not be written into the published suite, "
                             "the accepted delivery or the asset store: " + str(target))
    return target


def blender_runtime(value):
    pinned = REPO / "tools/blender-4.3.2-linux-x64/blender"
    return value or (pinned if pinned.is_file() else blender())


def launch(command, gpu, threads, env=None):
    """Run a native solve through the GPU launcher (GPU lease, UUID binding, job record)."""
    require_linux()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    launcher = [sys.executable, "-B", str(CASE / "tools/worker_run.py"), "--gpu", gpu,
                "--name", f"{SCENE_ID}_{stamp}", "--wait", "--", *map(str, command)]
    payload = dict(os.environ if env is None else env, OMP_NUM_THREADS=str(threads))
    subprocess.run(launcher, env=payload, check=True)


def analysis_python():
    """Python with numpy and Pillow for verify, GT export and packaging (no solver or Blender)."""
    import importlib.util
    if all(importlib.util.find_spec(name) for name in ("numpy", "PIL")):
        return Path(sys.executable)
    venv = REPO / ".venv-rigid-elastic/bin/python"
    if venv.is_file():
        return venv
    raise RuntimeError("Needs a Python with numpy and Pillow, for example .venv-rigid-elastic/bin/python")
