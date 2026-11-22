"""Public PCVE edit vocabulary for the picnic ground-blanket case."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCENE_ID = "picnic_ground_blanket"
HERE = Path(__file__).resolve().parent
SOURCE = HERE / "physics"
sys.path.insert(0, str(SOURCE))
spec = importlib.util.spec_from_file_location(f"{SCENE_ID}_physics_edit_vocab", SOURCE / "edit_vocab.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load the scene edit vocabulary (physics/edit_vocab.py)")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

VOCAB = module.vocabulary(SCENE_ID)
BASELINE_PHYSICS = VOCAB.baseline_physics
EDIT_CASES = module.cases(SCENE_ID)
TIMED_EDIT_CASES = module.timed_cases(SCENE_ID)
