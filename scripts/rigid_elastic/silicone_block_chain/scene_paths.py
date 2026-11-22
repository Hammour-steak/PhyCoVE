"""Input, delivery, media and output locations shared by this scene's entries and tools."""
from pathlib import Path
import json

from pcve_assets import asset, blender

CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
REPO = SCRIPTS.parent
SCENE = "silicone_block_chain"
CASES = ("source", "stiff_foam", "light_ball", "viscous_foam", "remove_foam")
TIMED_CASES = ("light_ball_at_frame_8",)
# The published videos of these cases replay the re-solve kept with the suite case
# (cases/<case_id>/native_metadata: simulation.npz, config.json, bake_report.json); the other four replay
# their accepted cache.
SUITE_SOLVES = ("source", "light_ball_at_frame_8")

# Reproduction inputs (assets.json group scenes/silicone_block_chain):
#   accepted_solves/physics/<case>/{simulation.npz,config.json}  accepted native caches (96 Hz) and solver reports
#   accepted_solves/packed/<case>.blend                          packed scenes the caches are baked into
#   workshop_template/packed/source.blend                                workshop template of the delivered look
INPUTS = asset(f"scenes/{SCENE}/accepted_solves")
TEMPLATE = asset(f"scenes/{SCENE}/workshop_template/packed/source.blend")
# Accepted native delivery: delivery_manifest.json (sha256 pins), physics_audit.json, step/mesh controls.
DELIVERY = REPO / "renders" / SCENE / "accepted"
# Default root of new simulate/render outputs.
OUTPUT = REPO / "renders" / SCENE / "rebuild"
SUITE_NAME = f"pcve_{SCENE}_suite"


def cache(case):
    return INPUTS / "physics" / case / "simulation.npz"


def packed(case):
    return INPUTS / "packed" / f"{case}.blend"


def catalog_id(case):
    """Suite case folder of a native case ID."""
    return "source" if case == "source" else "edit_" + case


def published_native(case):
    """Folder with simulation.npz and config.json of the solve that the published video of `case` replays."""
    if case in SUITE_SOLVES:
        return media() / "cases" / catalog_id(case) / "native_metadata"
    return cache(case).parent


def media():
    """Published video suite named by scene_manifest.json (canonical_suites)."""
    manifest = json.loads((CASE / "scene_manifest.json").read_text(encoding="utf-8"))
    target = Path(manifest["canonical_suites"][SUITE_NAME]["target"])
    if not target.is_absolute():
        return REPO / target
    if target.is_dir():
        return target
    # The same repository mounted elsewhere: keep the part from renders/ on.
    if "renders" in target.parts:
        index = len(target.parts) - 1 - target.parts[::-1].index("renders")
        return REPO.joinpath(*target.parts[index:])
    return target


def output_path(value):
    """Reproduction output: never inside scripts/, the inputs, the accepted delivery or the published suite."""
    target = Path(value).expanduser().resolve()
    for protected in (SCRIPTS, asset(f"scenes/{SCENE}"), DELIVERY, media()):
        protected = protected.resolve()
        if target == protected or protected in target.parents:
            raise ValueError(f"Reproduction output must stay outside {protected}: {target}")
    return target


def blender_runtime(value):
    pinned = REPO / "tools/blender-4.3.2-linux-x64/blender"
    return value or (pinned if pinned.is_file() else blender())
