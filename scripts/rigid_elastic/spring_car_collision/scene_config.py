"""Scene-level locations and runtimes of spring_car_collision.

Nothing under scripts/ holds data. Inputs come from the asset store
(assets/scenes/spring_car_collision, PCVE_ASSETS_DIR overrides the root), the
MuJoCo runtime from .runtime/spring_car_collision, renders go to
renders/spring_car_collision/<run>/ and the published suite is
renders/pcve_suites/pcve_spring_car_collision_suite (scene_manifest.json).
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

CASE_DIR = Path(__file__).resolve().parent
SCRIPTS = CASE_DIR.parents[1]
REPO = CASE_DIR.parents[2]
SCENE = "spring_car_collision"
CATEGORY = "rigid_elastic"
CASES = ("source", "remove_spring", "remove_block", "heavier_block", "add_block", "stiffer_spring")
CATALOG = {case: ("source" if case == "source" else "edit_" + case) for case in CASES}
SUITE_NAME = "pcve_spring_car_collision_suite"
SUITE = REPO / "renders" / "pcve_suites" / SUITE_NAME
RENDERS = REPO / "renders" / SCENE
RUNTIME = REPO / ".runtime" / SCENE
MUJOCO_DEPS = RUNTIME / "deps"          # mujoco 3.3.7 (cp310) target install
VENV_PYTHON = REPO / ".venv-rigid-elastic" / "bin" / "python"   # CPython 3.10, numpy, scipy
PYTHON = VENV_PYTHON if VENV_PYTHON.is_file() else Path(sys.executable)
BLENDER = REPO / "tools" / "blender-4.3.2-linux-x64" / "blender"
DEFAULT_SIMULATE_OUT = RENDERS / "simulate"
DEFAULT_RENDER_OUT = RENDERS / "render"
FPS, FRAMES, RESOLUTION = 24, 96, (1280, 720)


def blender() -> Path:
    """The pinned Blender 4.3.2 of the repository root, else the shared lookup ($BLENDER, PATH, ~/.local/opt)."""
    if BLENDER.is_file():
        return BLENDER
    from pcve_assets import blender as shared_blender
    return shared_blender()


def asset_dir() -> Path:
    root = Path(os.environ.get("PCVE_ASSETS_DIR", REPO / "assets"))
    return root / "scenes" / SCENE


def native_case(case: str) -> Path:
    """Accepted solver output of one case (trajectory.npz, scene_params.json, audits)."""
    return asset_dir() / "native_cases" / case


def mujoco_env(env=None) -> dict:
    """Environment that puts the pinned MuJoCo 3.3.7 build ahead of any other."""
    env = dict(os.environ if env is None else env)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(MUJOCO_DEPS), env.get("PYTHONPATH", "")) if p)
    env.setdefault("MUJOCO_GL", "disable")
    return env
