"""Repository locations of spring_scale_weight_drop and the guard for reproduction outputs."""
from pathlib import Path
import json

from pcve_assets import asset

CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
REPO = SCRIPTS.parent
SCENE = "spring_scale_weight_drop"
SUITE_NAME = f"pcve_{SCENE}_suite"
# Default parent of new simulate/render outputs.
OUTPUT = REPO / "renders" / SCENE / "rebuild"


def suite():
    """Published video suite named by scene_manifest.json (canonical_suites, target relative to the repository)."""
    manifest = json.loads((CASE / "scene_manifest.json").read_text(encoding="utf-8"))
    return REPO / manifest["canonical_suites"][SUITE_NAME]["target"]


def output_path(value):
    """A reproduction output: never inside scripts/ (code and the accepted delivery), the asset store or the suite."""
    target = Path(value).expanduser().resolve()
    for protected in (SCRIPTS, asset(f"scenes/{SCENE}"), suite()):
        protected = Path(protected).resolve()
        if target == protected or protected in target.parents:
            raise ValueError(f"Reproduction output must stay outside {protected}: {target}")
    return target
