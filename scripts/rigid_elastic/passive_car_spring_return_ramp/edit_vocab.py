"""Edit DSL vocabulary and benchmark prompts for the passive car / spring edits.

`pcve_edit_dsl.make_prompts(pcve_edit_dsl.parse(dsl, VOCAB), VOCAB)` reproduces the
published edit prompts; the physical edits themselves are applied by scene_config.config_for.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl

SOURCE_CASE_ID = "source"
VOCAB = dsl.Vocabulary(
    objects={"car": {"zh": "玩具车", "en": "the toy car"}, "spring": {"zh": "金属弹簧", "en": "the metal spring"}},
    properties={"mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
                "rolling_resistance": dsl.PropertySpec("scalar", "", "滚动阻力", "rolling resistance"),
                "stiffness": dsl.PropertySpec("scalar", "N/m", "刚度", "stiffness")},
    sim_bindings={("car", "mass"): dsl.SimBinding("physics.car.mass_kg"),
                  ("car", "rolling_resistance"): dsl.SimBinding("physics.car.travel_resistance_multiplier"),
                  ("spring", "stiffness"): dsl.SimBinding("physics.spring.stiffness_N_m")},
    delete_bindings={"spring": dsl.DeleteBinding("present_spring", 0, 0),
                     "car": dsl.DeleteBinding("present_car", 0, 0)},
    baseline_physics={"physics.car.mass_kg": 0.18, "physics.car.travel_resistance_multiplier": 1.0,
                      "physics.spring.stiffness_N_m": 12.0, "present_spring": [1], "present_car": [1]},
    total_frames=96)
# (native case, published case, edit DSL); every case starts from the same resting state.
EDIT_CASES = (
    ("soft_spring", "edit_soft_spring", "SET spring.stiffness TIMES 0.2"),
    ("stiff_spring", "edit_stiff_spring", "SET spring.stiffness TIMES 5"),
    ("high_friction", "edit_high_friction", "SET car.rolling_resistance TIMES 20"),
    ("heavy_car", "edit_heavy_car", "SET car.mass TIMES 2"),
    ("delete_spring", "edit_delete_spring", "DELETE spring"),
)
SOURCE_PROMPTS = {
    "vague": {
        "zh": "一辆没有动力的玩具越野车从木制坡道上滑下，沿平直轨道撞上后面装有螺旋弹簧的挡板，把弹簧压缩后被推回，又倒退着冲上坡道。",
        "en": "An unpowered toy SUV rolls down a wooden ramp and along a short flat track into a bumper plate backed by a coil spring, compresses the spring, is pushed back and rolls backwards up the ramp.",
    },
    "quantitative": {
        "zh": "一辆长 14.3 cm、质量 0.18 kg 的无动力玩具车从静止开始沿坡度 0.22 的木坡道滑下，以约 1.4 m/s 撞上由刚度 12 N/m 的螺旋弹簧支撑的挡板，把弹簧压缩约 16 cm 后被推回，倒退冲上坡道约 7 cm 高。",
        "en": "A 14.3 cm, 0.18 kg unpowered toy car starts from rest on a wooden ramp with a slope of 0.22, hits a bumper plate backed by a 12 N/m coil spring at about 1.4 m/s, compresses the spring by about 16 cm, is pushed back and climbs about 7 cm back up the ramp.",
    },
}


def prompts(native_case):
    """Bilingual vague/quantitative prompts of one native case."""
    if native_case == SOURCE_CASE_ID:
        return SOURCE_PROMPTS
    text = next(row[2] for row in EDIT_CASES if row[0] == native_case)
    return dsl.make_prompts(dsl.parse(text, VOCAB), VOCAB)
