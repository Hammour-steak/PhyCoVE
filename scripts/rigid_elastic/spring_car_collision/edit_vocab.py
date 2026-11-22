"""Strict shared physical interventions for the spring/car collision scene."""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DSL_DIR = next((p for p in (HERE.parent, HERE.parents[1]) if (p / "pcve_edit_dsl.py").is_file()), HERE.parents[1])
sys.path.insert(0, str(DSL_DIR))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy

SPEC = json.loads((HERE / "scene_spec.json").read_text(encoding="utf-8"))
BASELINE_PHYSICS = dict(SPEC["baseline"])
TOTAL_FRAMES = int(SPEC["frame_count"])
AUTHORIZATION_ID = None
OBJECTS = {
    "spring": {"zh": "弹簧", "en": "the spring"},
    "car": {"zh": "玩具车", "en": "the toy car"},
    "block": {"zh": "木块", "en": "the wooden block"},
    "obstacle_block": {"zh": "第二个木块", "en": "another wooden block"},
}
PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "young_modulus": dsl.PropertySpec("scalar", "Pa", "杨氏模量", "Young's modulus"),
}
SIM_BINDINGS = {
    ("block", "mass"): dsl.SimBinding("block_mass_kg"),
    ("spring", "young_modulus"): dsl.SimBinding("spring_young_modulus_pa"),
}
DELETE_BINDINGS = {"spring": dsl.DeleteBinding("spring_present", 0), "block": dsl.DeleteBinding("block_present", 0),
                   "car": dsl.DeleteBinding("car_present", 0)}
NEW_BODY_PARAMETERS = (
    "obstacle_initial_position_m", "obstacle_size_m", "obstacle_mass_kg", "obstacle_ground_friction",
    "obstacle_car_friction", "obstacle_block_friction", "obstacle_initial_quaternion_wxyz",
)
DSL_BASELINE_PHYSICS = dict(BASELINE_PHYSICS)
for key in ("spring_present", "car_present", "block_present", "obstacle_present"):
    DSL_BASELINE_PHYSICS[key] = [int(BASELINE_PHYSICS[key])]
owned = tuple(dsl.SimBinding(key) for key in NEW_BODY_PARAMETERS)
ADD_BINDINGS = {"obstacle_block": dsl.AddBinding("obstacle_present", 0, "obstacle_initial_position_m", owned_parameters=owned)}
ADD_PRESETS = {("obstacle_block", "approach"): dsl.AddPreset(
    parameters=tuple((key, BASELINE_PHYSICS[key]) for key in NEW_BODY_PARAMETERS),
    zh="玩具车和木块连线的六等分点上、靠近木块的位置",
    en="on the line between the toy car and the wooden block, one sixth of the way from the block")}
OBJECT_PARAMETERS = {
    "car": tuple(dsl.SimBinding(key) for key in ("car_initial_x_m", "car_initial_y_m", "car_root_height_m", "car_mass_kg", "car_wheel_centers_local_m")),
    "block": tuple(dsl.SimBinding(key) for key in ("block_initial_x_m", "block_initial_y_m", "block_size_m", "block_mass_kg")),
    "spring": tuple(dsl.SimBinding(key) for key in ("spring_anchor_x_m", "spring_axis_z_m", "spring_rest_length_m", "spring_plate_size_m", "spring_initial_compression_m")),
    "obstacle_block": owned,
}
VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS, baseline_physics=DSL_BASELINE_PHYSICS,
    add_bindings=ADD_BINDINGS, total_frames=TOTAL_FRAMES, add_presets=ADD_PRESETS,
    object_parameters=OBJECT_PARAMETERS, scene_id="spring_car_collision", user_authorization_id=AUTHORIZATION_ID)
AUTHORIZATION = None


def scenario_override(edit):
    if getattr(edit, "at_frame", None) is not None:
        raise ValueError("This scene supports only whole-clip interventions beginning at physical t=0")
    override = dsl.to_scenario_override(edit, VOCAB)
    for key in ("spring_present", "car_present", "block_present", "obstacle_present"):
        if key in override:
            if len(override[key]) != 1:
                raise ValueError("A body owns exactly one dedicated presence slot")
            override[key] = bool(override[key][0])
    policy.audit_scenario_override(edit, VOCAB, override, {})
    return override


# --- Display-only ADD geometry -------------------------------------------------------------------------
# The published edit_dsl of the ADD case is the shared BETWEEN form:
#   ADD obstacle_block BETWEEN car AND block AT 5/6 FROM car
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# car (-0.382, 0, 0.040) m and block (0.28, 0, 0.0275) m: frame-1 centres. The 5/6 point (0.1697, 0, 0.0296) m is
# 0.02 cm from the added block's centre (0.1695, 0, 0.0296) m.
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "car": {
        "centre_m": [
            -0.382,
            0.0,
            0.04
        ],
        "radius_m": 0.039
    },
    "block": {
        "centre_m": [
            0.28,
            0.0,
            0.0275
        ],
        "radius_m": 0.0275
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "obstacle_block": 0.0296
}
DISPLAY_NAME_UPDATES = {
    "obstacle_block": {
        "zh": "大小相近的木块",
        "en": "another wooden block"
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
