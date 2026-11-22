"""Load the preserved scenario vocabulary with the shared strict policy."""
from pathlib import Path
import importlib.util
import sys

directory = Path(__file__).resolve().parent / "physics"
sys.path.insert(0, str(directory))
spec = importlib.util.spec_from_file_location("pcve_scene_vocabulary", directory / "edit_vocab.py")
vocab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vocab)
VOCAB = vocab.VOCAB


# --- Display-only ADD geometry --------------------------------------------------------------------------
# The published edit_dsl of the ADD case is in the shared BETWEEN form:
#   ADD landing_book BETWEEN scarf AND seat_middle AT 1/10 FROM seat_middle
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes of the repository declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# scarf: the scarf's frame-1 surface centroid (0, 0.0501, 0.8539) m. seat_middle: the middle of the chair seat as the
# native preset "seat_center" uses it, (0.025, 0.015) m in plan, at the seat-top height of the chair collision mesh,
# z = 0.4662 m (the top face's bounding-box centre is (0.000, -0.026) m, 4.8 cm away). The 1/10 point from
# seat_middle, (0.0225, 0.0185, 0.5050) m, is 1.0 cm from the book's frame-1 centre (0.025, 0.015, 0.496) m
# (0.43 cm in plan; the rest is height).
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "scarf": {
        "centre_m": [
            0.0,
            0.0501,
            0.8539
        ],
        "radius_m": 0.001
    },
    "seat_middle": {
        "zh": "木椅椅面中间",
        "en": "the middle of the wooden chair's seat",
        "centre_m": [
            0.025,
            0.015,
            0.4662
        ],
        "radius_m": 0.001
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "landing_book": 0.0185
}
DISPLAY_NAME_UPDATES = {
    "landing_book": {
        "zh": "平放的精装书",
        "en": "a hardcover book lying flat"
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
