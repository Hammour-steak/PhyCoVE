"""Physical edit vocabulary of the phone / sofa scene (DSL -> exact solver parameters)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DSL_DIR = next((p for p in (HERE.parent, HERE.parents[1]) if (p / "pcve_edit_dsl.py").is_file()), HERE.parents[1])
sys.path.insert(0, str(DSL_DIR))
import pcve_edit_dsl as dsl  # noqa: E402

SPEC = json.loads((HERE / "scene_spec.json").read_text(encoding="utf-8"))
BASELINE_PHYSICS = dict(SPEC["baseline"])
TOTAL_FRAMES = int(SPEC["frame_count"])
# Names as a viewer of the video would say them (the same names the PCVE prompts use).
OBJECTS = {
    "phone": {"zh": "手机", "en": "the phone"},
    "cushion": {"zh": "中间的沙发坐垫", "en": "the middle sofa cushion"},
    "landing_pillow": {"zh": "浅蓝灰色小枕头", "en": "a small blue-grey pillow"},
}
# Names for the prompts of the published ADD DSL
# ("ADD landing_pillow BETWEEN phone AND cushion_below_phone AT 1/4 FROM cushion_below_phone").
# cushion_below_phone is a positioning anchor only, like the shared scenes' anchors: the point of the
# middle cushion's top surface on the phone's drop line, (0, -0.18, 0.4727) m at t = 0 in the
# source. It has no physics binding; VOCAB carries it as a display-only GeometryAnchor (see the end of
# this file).
PROMPT_OBJECTS = {**OBJECTS,
                  "cushion_below_phone": {"zh": "手机正下方的坐垫面", "en": "the cushion surface directly below the phone"}}
PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "young_modulus": dsl.PropertySpec("scalar", "Pa", "杨氏模量", "Young's modulus"),
}
SIM_BINDINGS = {
    ("phone", "mass"): dsl.SimBinding("phone_mass_kg"),
    ("cushion", "young_modulus"): dsl.SimBinding("cushion_young_modulus_pa"),
}
DSL_BASELINE_PHYSICS = dict(BASELINE_PHYSICS)
for key in ("phone_present", "cushion_present", "pillow_present"):
    DSL_BASELINE_PHYSICS[key] = [int(BASELINE_PHYSICS[key])]
DELETE_BINDINGS = {"cushion": dsl.DeleteBinding("cushion_present", 0),
                   "phone": dsl.DeleteBinding("phone_present", 0)}
PILLOW_PARAMETERS = (
    "pillow_asset_scale", "pillow_center_m",
    "pillow_orientation_quaternion_wxyz", "pillow_young_modulus_pa",
    "pillow_poisson_ratio", "pillow_density_kg_m3",
    "pillow_shear_viscosity_pa_s", "pillow_bulk_viscosity_pa_s",
    "pillow_contact_friction",
)
PILLOW_OWNED = tuple(dsl.SimBinding(key) for key in PILLOW_PARAMETERS)
ADD_BINDINGS = {
    "landing_pillow": dsl.AddBinding(
        "pillow_present", 0, "pillow_center_m", owned_parameters=PILLOW_OWNED
    )
}
ADD_PRESETS = {
    ("landing_pillow", "middle_seat"): dsl.AddPreset(
        parameters=tuple((key, BASELINE_PHYSICS[key]) for key in PILLOW_PARAMETERS),
        zh="平放在中间的沙发坐垫上、手机正下方的浅蓝灰色小枕头",
        en="a small blue-grey pillow lying flat on the middle sofa cushion directly below the phone",
    )
}
OBJECT_PARAMETERS = {
    "phone": (dsl.SimBinding("phone_mass_kg"),),
    "cushion": (dsl.SimBinding("cushion_young_modulus_pa"),),
    "landing_pillow": PILLOW_OWNED,
}
VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics=DSL_BASELINE_PHYSICS,
    add_bindings=ADD_BINDINGS,
    add_presets=ADD_PRESETS,
    object_parameters=OBJECT_PARAMETERS,
    total_frames=TOTAL_FRAMES,
    scene_id="phone_sofa_drop",
)


def scenario_override(edit: dsl.Edit) -> dict:
    """Resolve one whole-clip edit to the exact physical override in scene_spec.json."""
    if getattr(edit, "at_frame", None) is not None:
        raise ValueError("phone_sofa_drop edits are whole-clip interventions beginning at physical t=0")
    override = dsl.to_scenario_override(edit, VOCAB)
    for key in ("phone_present", "cushion_present", "pillow_present"):
        if key in override:
            if len(override[key]) != 1:
                raise ValueError(f"Presence binding must contain one slot: {key}")
            override[key] = bool(override[key][0])
    return override


def resolved_edit(case_id: str) -> dict:
    """DSL of one case checked against scene_spec.json (source: no edit)."""
    if case_id == "source":
        return {"case_id": "source", "edit_dsl": None, "physics_override": {}}
    text = SPEC["edit_dsl"][case_id]
    override = scenario_override(dsl.parse(text, VOCAB))
    if override != SPEC["cases"][case_id]:
        raise ValueError(f"DSL disagrees with scene_spec.json for {case_id}: {override} != {SPEC['cases'][case_id]}")
    return {"case_id": case_id, "edit_dsl": text, "edit_summary": SPEC["edit_semantics"][case_id],
            "physics_override": override}


# --- Display-only ADD geometry -------------------------------------------------------------------------
# The published edit_dsl of the ADD case is the shared BETWEEN form:
#   ADD landing_pillow BETWEEN phone AND cushion_below_phone AT 1/4 FROM cushion_below_phone
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# phone: its release centre (0, -0.18, 0.7586) m. cushion_below_phone: the point of the middle cushion's top surface
# on the phone's drop line, (0, -0.18, 0.4727) m (highest source cache surface vertex within 1 cm of the drop line at
# t = 0). The 1/4 point from it, (0, -0.18, 0.5442) m, is 0.55 cm from the pillow's frame-1 centroid
# (0.0016, -0.1810, 0.5390) m. The pillow's radius here is only the overlap-check value.
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "phone": {
        "centre_m": [
            0.0,
            -0.18,
            0.758602134
        ],
        "radius_m": 0.004
    },
    "cushion_below_phone": {
        "zh": "手机正下方的坐垫面",
        "en": "the cushion surface directly below the phone",
        "centre_m": [
            0.0,
            -0.18,
            0.4727
        ],
        "radius_m": 0.001
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "landing_pillow": 0.05
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
