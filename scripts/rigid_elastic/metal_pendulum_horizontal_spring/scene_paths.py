"""Scene-local paths and provenance; no physical or image defaults live here."""

import hashlib
import json
from pathlib import Path
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender, scene_asset

SCENE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCENE_DIR.parents[2]
ASSET_DIR = scene_asset(SCENE_DIR, "assets")
CATALOG_DIR = SCENE_DIR / "asset_tools" / "catalogs"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "metal_pendulum_horizontal_spring_run"
DEFAULT_PYTHON = REPO_ROOT / ".venv-genesis-mpm-sph" / "bin" / "python"
DEFAULT_BLENDER = blender()
CACHE_FILES = (
    "actual_config.json",
    "model_input.xml",
    "model.xml",
    "model.mjb",
    "native_model_audit.json",
    "trajectory.npz",
    "trace.npz",
    "trace.csv",
    "metrics.json",
)


def sha256(path):
    """Hash without loading large assets or videos into memory."""
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(2**20), b""):
            value.update(chunk)
    return value.hexdigest()


def cache_matches(folder, config):
    """Reuse only a complete cache from this exact preset."""
    try:
        software = json.loads((folder / "software.json").read_text())
        return (
            json.loads((folder / "actual_config.json").read_text()) == config
            and all(
                software["cache_hashes"][name] == sha256(folder / name)
                for name in CACHE_FILES
            )
        )
    except (OSError, KeyError, ValueError):
        return False


def render_signature():
    return {
        "asset_manifest_sha256": sha256(SCENE_DIR / "asset_manifest.json"),
    }
