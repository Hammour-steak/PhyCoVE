"""Edit DSL vocabulary and benchmark prompts for the toy car / silicone bridge edits.

`pcve_edit_dsl.make_prompts(pcve_edit_dsl.parse(dsl, VOCAB), VOCAB)` reproduces the
published edit prompts; the physical edits themselves are applied by bridge_physics.config_for.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl

SOURCE_CASE_ID = "source"
VOCAB = dsl.Vocabulary(
    objects={"car": {"zh": "玩具车", "en": "the toy car"}, "bridge": {"zh": "硅胶桥", "en": "the silicone bridge"}},
    properties={"mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
                "young_modulus": dsl.PropertySpec("scalar", "MPa", "杨氏模量", "Young's modulus")},
    sim_bindings={("car", "mass"): dsl.SimBinding("physics.car.mass_kg"),
                  ("bridge", "young_modulus"): dsl.SimBinding("physics.bridge.young_mpa")},
    delete_bindings={"bridge": dsl.DeleteBinding("present_bridge", 0, 0), "car": dsl.DeleteBinding("present_car", 0, 0)},
    baseline_physics={"physics.car.mass_kg": 0.15, "physics.bridge.young_mpa": 0.9, "present_bridge": [1], "present_car": [1]},
    total_frames=96)
# (native case, published case, edit DSL). E/3 has no exact decimal factor, so the soft
# bridge uses the absolute form (0.9 -> 0.3 MPa).
EDIT_CASES = (
    ("soft_bridge", "edit_soft_bridge", "SET bridge.young_modulus TO 0.3"),
    ("stiff_bridge", "edit_stiff_bridge", "SET bridge.young_modulus TIMES 3"),
    ("heavy_car", "edit_heavy_car", "SET car.mass TIMES 2"),
    ("delete_bridge", "edit_delete_bridge", "DELETE bridge"),
)
SOURCE_PROMPTS = {
    "vague": {
        "zh": "一辆玩具小汽车在木制路面上被推了一下，滚过两端固定的硅胶桥，桥面在车下凹陷后又弹回。",
        "en": "A toy car gets one push on a wooden road and rolls across a silicone bridge clamped at both ends; the bridge sags under the car and springs back.",
    },
    "quantitative": {
        "zh": "一辆长 11 cm、质量 150 g 的玩具车以约 0.65 m/s 的速度被推出，驶过一座长 32 cm、厚 6 mm、杨氏模量 0.9 MPa 的硅胶桥，桥面最多下陷约 27 mm。",
        "en": "An 11 cm, 150 g toy car is pushed off at about 0.65 m/s and rolls across a 32 cm long, 6 mm thick silicone bridge with a Young's modulus of 0.9 MPa, which sags by up to about 27 mm.",
    },
}


def _row(native_case):
    return next(row for row in EDIT_CASES if row[0] == native_case)


def public_case_id(native_case):
    return SOURCE_CASE_ID if native_case == SOURCE_CASE_ID else _row(native_case)[1]


def edit_dsl(native_case):
    return None if native_case == SOURCE_CASE_ID else _row(native_case)[2]


def prompts(native_case):
    """Bilingual vague/quantitative prompts of one native case."""
    if native_case == SOURCE_CASE_ID:
        return SOURCE_PROMPTS
    return dsl.make_prompts(dsl.parse(_row(native_case)[2], VOCAB), VOCAB)
