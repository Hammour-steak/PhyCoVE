"""Public PCVE edit vocabulary for the gym landing-mat case."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCENE_ID = "gym_landing_mat"
HERE = Path(__file__).resolve().parent
SOURCE = HERE / "physics"
sys.path.insert(0, str(SOURCE))
spec = importlib.util.spec_from_file_location(f"{SCENE_ID}_physics_edit_vocab", SOURCE / "edit_vocab.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load the physics edit vocabulary")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

VOCAB = module.vocabulary(SCENE_ID)
BASELINE_PHYSICS = VOCAB.baseline_physics
_DELIVERED = ("source", "mass_double", "faster", "young_modulus_rebound", "add_path_obstacle", "delete_actor")
EDIT_CASES = {key: module.cases(SCENE_ID)[key] for key in _DELIVERED}

# --- Display-only ADD geometry --------------------------------------------------------------------------
# The published edit_dsl of the ADD case is in the shared BETWEEN form:
#   ADD gym_water_bottle BETWEEN medicine_ball AND ball_heading_point AT 1/10 FROM ball_heading_point
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes of the repository declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# medicine_ball keeps its native GeometryAnchor (body_initial_location (-0.09, -0.035, 0.515) m, body_radius).
# ball_heading_point: where the ball's t=0 line of motion (velocity (0.44, 0, -0.668) m/s) meets the mat top plane
# z = 0.14 m, (0.156957, -0.035, 0.14) m. The 1/10 point from it, (0.1322, -0.035, 0.1775) m, is 0.23 cm from the
# bottle's frame-1 centre (0.1300, -0.0350, 0.1772) m. gym_water_bottle keeps its native anchor.
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "ball_heading_point": {
        "zh": "实心球运动方向与垫面的交点",
        "en": "the point where the medicine ball's line of motion meets the mat",
        "centre_m": [
            0.156957,
            -0.035,
            0.14
        ],
        "radius_m": 0.005
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {}
DISPLAY_NAME_UPDATES = {
    "gym_water_bottle": {
        "zh": "横放的运动水壶",
        "en": "a sports water bottle lying on its side"
    }
}


def _with_display_add_anchors(vocab):
    objects = {k: dict(v) for k, v in vocab.objects.items()}
    physics = dict(vocab.baseline_physics)
    geometry = dict(vocab.geometry)
    for name, names in DISPLAY_NAME_UPDATES.items():
        objects[name] = dict(names)
    for name, anchor in DISPLAY_ADD_ANCHORS.items():
        if name not in objects:
            objects[name] = {'zh': anchor['zh'], 'en': anchor['en']}
        if name in geometry:
            continue
        physics[f'display_anchor_{name}_centre_m'] = list(anchor['centre_m'])
        physics[f'display_anchor_{name}_radius_m'] = anchor['radius_m']
        geometry[name] = _dsl.GeometryAnchor(f'display_anchor_{name}_centre_m', f'display_anchor_{name}_radius_m')
    for name, radius in DISPLAY_ADD_NEW_BODY_RADIUS_M.items():
        if name in geometry:
            continue
        physics[f'display_anchor_{name}_radius_m'] = radius
        geometry[name] = _dsl.GeometryAnchor(vocab.add_bindings[name].location_key, f'display_anchor_{name}_radius_m')
    return _dataclasses.replace(vocab, objects=objects, baseline_physics=physics, geometry=geometry)


VOCAB = _with_display_add_anchors(VOCAB)
