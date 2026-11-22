"""Input, delivery, media and output locations shared by this scene's entries and tools."""
from pathlib import Path
import datetime
import json

from pcve_assets import asset, blender

CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
REPO = SCRIPTS.parent
SCENE = "elastic_key_strap"
CASES = ("source", "keys_mass_5x", "strap_soft", "strap_stiff", "remove_strap")
# Timed edits continue the accepted source solve from their edit frame (edit_vocab.TIMED_DSL); the merged
# native solve is published with the suite in inputs/native_timed/<case>/.
TIMED_CASES = ("keys_mass_5x_at_frame_24",)
CATALOG = {case: case if case == "source" else "edit_" + case for case in CASES + TIMED_CASES}

# Baseline physical parameters and the clip contract (read by edit_vocab.py).
SPEC = CASE / "physics" / "scene_spec.json"
# Reproduction inputs under the asset store's scenes/elastic_key_strap:
#   native_solves/cases/<case>/{simulation.npz, resolved_config.json, scenario_overrides.json,
#                            physics_audit.json, trace_240hz.npz}   accepted native solves (assets.json)
#   prepared/key{1,2}.npz, keys.blend, cabinet.blend, oak_veneer_01/, white_plaster_02/  geometry and scans (assets.json)
ASSETS = asset(f"scenes/{SCENE}")
PHYSICS = ASSETS / "native_solves"
# Accepted delivery of the whole-clip cases (accepted_case.json, suite_manifest.json, per-case audits and the accepted
# videos cases/<case>/video.mp4, whose SHA-256 accepted_case.json records).
DELIVERY = REPO / "renders" / SCENE / "accepted_physics"
# Default root of new simulate/render outputs.
OUTPUT = REPO / "renders" / SCENE / "rebuild"
SUITE_NAME = f"pcve_{SCENE}_suite"


def cache_dir(case):
    """Folder with the accepted native solve of one case."""
    if case in TIMED_CASES:
        return media() / "inputs" / "native_timed" / case
    if case not in CASES:
        raise ValueError(f"unknown case {case!r}")
    return PHYSICS / "cases" / case


def manifest():
    return json.loads((CASE / "scene_manifest.json").read_text(encoding="utf-8"))


def media():
    """Published video suite named by scene_manifest.json (canonical_suites; target relative to the repository)."""
    target = Path(manifest()["canonical_suites"][SUITE_NAME]["target"])
    if not target.is_absolute():
        return REPO / target
    if target.is_dir():
        return target
    # The same repository mounted elsewhere: keep the part from renders/ on.
    if "renders" in target.parts:
        index = len(target.parts) - 1 - target.parts[::-1].index("renders")
        return REPO.joinpath(*target.parts[index:])
    return target


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def output_path(value):
    """Reproduction output: never inside scripts/, the inputs, the accepted delivery or the published suite."""
    target = Path(value).expanduser().resolve()
    for protected in (SCRIPTS, ASSETS, DELIVERY, REPO / "renders" / "pcve_suites"):
        protected = protected.resolve()
        if target == protected or protected in target.parents:
            raise ValueError(f"Reproduction output must stay outside {protected}: {target}")
    return target


def blender_runtime(value=None):
    pinned = REPO / "tools/blender-4.3.2-linux-x64/blender"
    return Path(value) if value else (pinned if pinned.is_file() else blender())
