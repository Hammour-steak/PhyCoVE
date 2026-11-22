"""Strict edit vocabulary of the published cases (tools/native/vocab_revised.py) with display-only ADD anchors."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent/"tools/native"))
from vocab_revised import *

# --- Display-only ADD geometry -----------------------------------------------------------------------
# The published edit_dsl of the ADD case uses the shared BETWEEN form:
#   ADD shoe_tray BETWEEN resting_slipper AND left_floor_spot AT MIDPOINT
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# resting_slipper: the frame-1 centroid of the resting slide's surface vertices, (0.0006, 0.0095, 0.0253) m.
# left_floor_spot: the point on the floor (z = 0) to its left whose plan position mirrors it about the tray centre,
# (-0.4938, 0.1565, 0) m. Their midpoint (-0.2466, 0.0830, 0.0127) m is exactly above the tray's centre
# (-0.2466, 0.083, 0.0279) m, 1.5 cm lower (the tray stands on the floor; the display name says so).
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "resting_slipper": {
        "centre_m": [
            0.0006,
            0.0095,
            0.0253
        ],
        "radius_m": 0.02
    },
    "left_floor_spot": {
        "zh": "地面拖鞋左侧的空地",
        "en": "the empty floor to the left of the resting slide",
        "centre_m": [
            -0.4938,
            0.1565,
            0.0
        ],
        "radius_m": 0.001
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "shoe_tray": 0.02
}
DISPLAY_NAME_UPDATES = {
    "shoe_tray": {
        "zh": "平放在地面上的带边木质鞋托盘",
        "en": "a wooden shoe tray with a raised rim lying flat on the floor"
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

# DELETE falling_slipper replays a native cache that holds only the resting slide (the renderer builds the
# parts present in the cache). falling_present is a presence slot of this vocabulary only; the solver
# parameters (parameters(), BASELINE) are unchanged.
VOCAB = _dataclasses.replace(
    VOCAB,
    delete_bindings={**VOCAB.delete_bindings, "falling_slipper": _dsl.DeleteBinding("falling_present", 0)},
    baseline_physics={**VOCAB.baseline_physics, "falling_present": [1]},
)
