"""Vocabulary with the two production edits selected by native trials."""
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if (HERE / "scene_spec.json").is_file():
    SPEC_PATH = HERE / "scene_spec.json"
    sys.path.insert(0, str(HERE.parent))
else:
    from common import DATA, ROOT
    SPEC_PATH = DATA / "accepted_delivery/revised_scene_spec.json"
    if not SPEC_PATH.is_file():
        SPEC_PATH = DATA / "accepted_delivery/scene_spec.json"
    sys.path.insert(0, str(ROOT / "scripts"))

import pcve_edit_dsl as dsl
import pcve_edit_policy as policy

SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
BASELINE = SPEC["baseline"]
TRAY_FIELDS = tuple(name for name in BASELINE if name.startswith("tray_"))
TRAY_OWNED = tuple(dsl.SimBinding(name, 0 if name == "tray_present" else None) for name in TRAY_FIELDS)
VOCAB = dsl.Vocabulary(
    objects={
        "falling_slipper": {"zh": "上方落下的拖鞋", "en": "the falling slide"},
        "resting_slipper": {"zh": "地面上的拖鞋", "en": "the slide resting on the floor"},
        "shoe_tray": {"zh": "带边木质鞋托盘", "en": "a wooden shoe tray with a raised rim"},
        "stone_floor": {"zh": "石材地面", "en": "the stone floor"},
    },
    properties={
        "young_modulus": dsl.PropertySpec("scalar", "Pa", "杨氏模量", "Young's modulus"),
        "density": dsl.PropertySpec("scalar", "kg/m^3", "密度", "density"),
        "friction": dsl.PropertySpec("scalar", "", "接触摩擦系数", "contact friction coefficient"),
    },
    sim_bindings={
        ("falling_slipper", "young_modulus"): dsl.SimBinding("falling_young_modulus_pa"),
        ("resting_slipper", "young_modulus"): dsl.SimBinding("resting_young_modulus_pa"),
        ("falling_slipper", "density"): dsl.SimBinding("falling_density_kg_m3"),
        ("stone_floor", "friction"): dsl.SimBinding("floor_friction"),
    },
    delete_bindings={"resting_slipper": dsl.DeleteBinding("resting_present", 0)},
    add_bindings={"shoe_tray": dsl.AddBinding("tray_present", 0, "tray_center_m", owned_parameters=TRAY_OWNED)},
    add_presets={
        ("shoe_tray", "beside_resting_slide"): dsl.AddPreset(
            tuple((name, BASELINE[name]) for name in TRAY_FIELDS if name != "tray_present"),
            "地面那只拖鞋左侧，靠近悬空拖鞋鞋尖下方",
            "on the floor to the left of the resting slide, beneath the toe of the airborne slide",
        )
    },
    object_parameters={
        "falling_slipper": tuple(dsl.SimBinding(n) for n in ("falling_center_m", "falling_euler_deg", "falling_initial_velocity_m_s")),
        "resting_slipper": tuple(dsl.SimBinding(n) for n in ("resting_center_m", "resting_euler_deg")),
        "shoe_tray": TRAY_OWNED,
    },
    baseline_physics=BASELINE, total_frames=96, scene_id=SPEC["scene_id"],
)
CASE_DSL = SPEC.get("edit_dsl", {})


def override_for(case):
    text = CASE_DSL[case]
    if text is None:
        return {}
    edit = dsl.parse(text, VOCAB)
    override = dsl.to_scenario_override(edit, VOCAB)
    policy.audit_scenario_override(edit, VOCAB, override, {})
    return override


def parameters(case):
    result = copy.deepcopy(BASELINE)
    result.update(override_for(case))
    return result
