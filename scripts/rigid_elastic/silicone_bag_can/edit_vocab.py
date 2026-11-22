"""Scene-level access to the shared-DSL vocabulary in physics/vocab.py."""
from pathlib import Path
import sys
CASE = Path(__file__).resolve().parent
sys.path[:0] = [str(CASE.parents[1]), str(CASE / 'physics')]
from vocab import *  # noqa: F401,F403

# --- Display-only ADD geometry --------------------------------------------------------------------------
# bag_bottom is a locating anchor, not a body: the bottom of the bag straight under the second can at frame 1 of
# add_second_can (bag already settled under it), (0.0020, -0.1488, 0.6236) m in the native frame. It is not an
# editable object and the solver never reads it; the native statement the solver executes stays in CASE_DSL and in
# the edit's native_edit_dsl.
# The published edit_dsl of the ADD case is in the shared BETWEEN form:
#   ADD second_can BETWEEN can AND bag_bottom AT 9/10 FROM can
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes of the repository declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# can: the falling can's release centre (0.012, -0.145, 1.095) m; bag_bottom as documented above. The 9/10 point is
# 0.92 cm from the second can's frame-1 centre (-0.0029, -0.1423, 0.6671) m.
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "can": {
        "centre_m": [
            0.012,
            -0.145,
            1.095
        ],
        "radius_m": 0.034
    },
    "bag_bottom": {
        "zh": "硅胶袋袋底",
        "en": "the bottom of the silicone bag",
        "centre_m": [
            0.002,
            -0.1488,
            0.6236
        ],
        "radius_m": 0.001
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "second_can": 0.034
}
DISPLAY_NAME_UPDATES = {}


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
