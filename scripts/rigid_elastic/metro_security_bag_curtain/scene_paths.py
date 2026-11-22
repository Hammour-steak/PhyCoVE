"""Repository locations shared by the simulation, the Blender replay and the delivery checks.

Everything is resolved from the repository, so nothing here is machine specific:
  assets/scenes/metro_security_bag_curtain/            registered inputs (assets.json)
  assets/scenes/metro_security_bag_curtain/native/     accepted native states of the source and the whole-clip edits
  .runtime/metro_security_bag_curtain/                 runtime receipts, numba cache, optional pinned tools
  renders/metro_security_bag_curtain/                  native deliveries and rebuild outputs
  renders/pcve_suites/pcve_metro_security_bag_curtain_suite/   published video suite
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys

from pcve_assets import asset

SCENE = "metro_security_bag_curtain"
CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
REPO = SCRIPTS.parent
ASSETS = asset("scenes/" + SCENE)
NATIVE_TAG = "accepted_states"
NATIVE = ASSETS / "native" / NATIVE_TAG
RUNTIME = REPO / ".runtime" / SCENE
RENDERS = REPO / "renders" / SCENE
DELIVERY = RENDERS / "accepted"
SUITE = REPO / "renders" / "pcve_suites" / f"pcve_{SCENE}_suite"
SCENE_MANIFEST = CASE / "scene_manifest.json"
VENV_PYTHON = REPO / ".venv-rigid-elastic" / "bin" / "python"


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def output_path(value):
    """Resolve an output directory; outputs never go inside scripts/."""
    path = Path(value).expanduser().resolve()
    scripts = SCRIPTS.resolve()
    if path == scripts or scripts in path.parents:
        raise ValueError("Write outputs outside scripts/ (default renders/metro_security_bag_curtain/rebuild_<stamp>/)")
    return path


def default_rebuild_root():
    return RENDERS / f"rebuild_{stamp()}"


def ffmpeg_binary():
    pinned = RUNTIME / "ffmpeg"
    if pinned.is_file():
        return pinned
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg is required to encode the frame sequence")
    return Path(found)


def ensure_numpy_runtime():
    """Re-run the current command with the repository venv when the caller's Python has no NumPy."""
    try:
        import numpy  # noqa: F401
    except ModuleNotFoundError:
        if VENV_PYTHON.is_file() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
            os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])
        raise
