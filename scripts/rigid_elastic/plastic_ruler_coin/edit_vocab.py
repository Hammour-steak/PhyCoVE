"""Strict edit bindings of plastic_ruler_coin (objects, properties, presets; see physics/vocabulary.py)."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "physics"))
from vocabulary import SPEC, VOCAB  # noqa: E402,F401

CASE_DSL = {case: row["dsl"] for case, row in SPEC["cases"].items()}

# Display-only endpoints of the BETWEEN-form ADD in the builder's PCVE_EDITS (add_second_coin):
#   ADD second_coin BETWEEN book_edge AND ruler_end AT MIDPOINT, with a HINT that the coin lies flat on the ruler
# Locating anchors, not bodies (x from the desk edge, native frame): book_edge is the book's front edge where the
# ruler comes out from under it, (0, 0, 0.7616) m on the ruler's top face (appearance/realism.py build_book: the
# book spans x -0.200..0.000 and rests on the ruler); ruler_end is the free end of the ruler, (0.140, 0, 0.7608) m
# (scene_spec.json ruler_free_length_m, ruler_midplane_z_m). Their midpoint (0.070, 0, 0.7612) m is 0.25 cm from the
# added coin's centre (0.068, 0, 0.762765) m (second_coin_initial_location_m). The solver never reads them; the
# native statement stays in scene_spec.json and in the edit's native_edit_dsl.
PROMPT_ANCHORS = {'book_edge': {'zh': '书的边缘', 'en': 'the edge of the book'},
                  'ruler_end': {'zh': '尺子末端', 'en': 'the end of the ruler'}}


# --- Display-only ADD geometry -------------------------------------------------------------------------
# The published edit_dsl of the ADD case is the shared DSL's BETWEEN form:
#   ADD second_coin BETWEEN book_edge AND ruler_end AT MIDPOINT
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# Coordinates as documented above: book_edge (0, 0, 0.7616) m, ruler_end (0.140, 0, 0.7608) m; their midpoint is
# 0.25 cm from the added coin's centre (0.068, 0, 0.762765) m.
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "book_edge": {
        "zh": "书的边缘",
        "en": "the edge of the book",
        "centre_m": [
            0.0,
            0.0,
            0.7616
        ],
        "radius_m": 0.001
    },
    "ruler_end": {
        "zh": "尺子末端",
        "en": "the end of the ruler",
        "centre_m": [
            0.14,
            0.0,
            0.7608
        ],
        "radius_m": 0.001
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "second_coin": 0.011625
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
