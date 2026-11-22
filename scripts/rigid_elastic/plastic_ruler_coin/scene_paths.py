"""Input, delivery, media and output locations shared by this scene's entries and tools."""
from pathlib import Path
import json

from pcve_assets import asset, blender

CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
REPO = SCRIPTS.parent
SCENE = "plastic_ruler_coin"
CASES = ("source", "coin_mass_x02", "ruler_modulus_x025", "ruler_modulus_x8", "delete_coin", "add_second_coin")
CATALOG = {c: ("source" if c == "source" else "edit_" + c) for c in CASES}
SUITE_NAME = f"pcve_{SCENE}_suite"

# Reproduction inputs (assets/scenes/plastic_ruler_coin):
#   accepted/physics/<case>/{simulation.npz,simulation_config.json,simulation_report.json}  accepted native solves
ASSETS = asset(f"scenes/{SCENE}")
INPUTS = ASSETS / "accepted" / "physics"
# Accepted delivery: per-case artifact manifests, replay audits, render reports and reference videos.
DELIVERY = REPO / "renders" / SCENE / "accepted"
DELIVERED_SUITE = DELIVERY / SUITE_NAME
RUNTIME = REPO / ".runtime" / SCENE
# Default root of new simulate/render outputs.
OUTPUT = REPO / "renders" / SCENE / "rebuild"


def cache_dir(case):
    """Accepted native solve of one case: simulation.npz, simulation_config.json, simulation_report.json."""
    return INPUTS / case


def media():
    """Published video suite named by scene_manifest.json (canonical_suites; target relative to the repository)."""
    manifest = json.loads((CASE / "scene_manifest.json").read_text(encoding="utf-8"))
    return REPO / manifest["canonical_suites"][SUITE_NAME]["target"]


def output_path(value):
    """Reproduction output: never inside scripts/, the inputs, the accepted delivery or the published suite."""
    target = Path(value).expanduser().resolve()
    for protected in (SCRIPTS, ASSETS, DELIVERY, media()):
        protected = protected.resolve()
        if target == protected or protected in target.parents:
            raise ValueError(f"Reproduction output must stay outside {protected}: {target}")
    return target


def blender_runtime(value=None):
    pinned = REPO / "tools/blender-4.3.2-linux-x64/blender"
    return Path(value) if value else (pinned if pinned.is_file() else blender())


def python_runtime():
    venv = REPO / ".venv-rigid-elastic/bin/python"
    return venv if venv.is_file() else Path("python3")
