"""Edit DSL vocabulary and benchmark prompts for the pendulum / spring edits.

`pcve_edit_dsl.make_prompts(pcve_edit_dsl.parse(dsl, VOCAB), VOCAB)` reproduces the
published edit prompts; the physical edits themselves are applied by edits/presets.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl

SOURCE_CASE_ID = "source"
VOCAB = dsl.Vocabulary(
    objects={"ball": {"zh": "金属摆球", "en": "the steel ball"}, "spring": {"zh": "水平弹簧", "en": "the horizontal spring"}},
    properties={"mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
                "young_modulus": dsl.PropertySpec("scalar", "Pa", "杨氏模量", "Young's modulus")},
    sim_bindings={("ball", "mass"): dsl.SimBinding("physics.pendulum.ball_mass_kg"),
                  ("spring", "young_modulus"): dsl.SimBinding("physics.spring.young_modulus_Pa")},
    # DELETE ball removes the swinging pendulum body (bob with its rod, eye and neck: one rigid body on the
    # hinge); the native switch is physics.pendulum.present (default true, see model/dynamics.py).
    delete_bindings={"spring": dsl.DeleteBinding("spring_present", 0, 0),
                     "ball": dsl.DeleteBinding("ball_present", 0, 0)},
    baseline_physics={"physics.pendulum.ball_mass_kg": 0.19055, "physics.spring.young_modulus_Pa": 200e9,
                      "spring_present": [1], "ball_present": [1]},
    total_frames=96)
# (native case, published case, edit DSL); every case starts from the same released state.
EDIT_CASES = (
    ("soft_spring", "edit_soft_spring", "SET spring.young_modulus TIMES 0.1"),
    ("stiff_spring", "edit_stiff_spring", "SET spring.young_modulus TIMES 10"),
    ("heavy_ball", "edit_heavy_ball", "SET ball.mass TIMES 2"),
    ("delete_spring", "edit_delete_spring", "DELETE spring"),
)
SOURCE_PROMPTS = {
    "vague": {
        "zh": "桌面支架上的金属摆球从一侧被松开，摆下来撞上水平弹簧的端板，把弹簧压缩后被弹回，之后继续来回摆动。",
        "en": "A steel ball on a desktop pendulum stand is released from one side, swings down into the end plate of a horizontal coil spring, compresses the spring, is pushed back and keeps swinging.",
    },
    "quantitative": {
        "zh": "直径 36 mm、质量约 0.19 kg 的钢球挂在 23 cm 长的摆杆上，从 30 度处静止释放，撞上自由长度 97.5 mm、刚度约 74 N/m 的水平螺旋弹簧的端板，把弹簧压缩约 30 mm 后被弹回。",
        "en": "A 36 mm steel ball of about 0.19 kg on a 23 cm pendulum arm is released from rest at 30 degrees, hits the end plate of a horizontal coil spring with a free length of 97.5 mm and a stiffness of about 74 N/m, compresses it by about 30 mm and is pushed back.",
    },
}


def prompts(native_case):
    """Bilingual vague/quantitative prompts of one native case."""
    if native_case == SOURCE_CASE_ID:
        return SOURCE_PROMPTS
    text = next(row[2] for row in EDIT_CASES if row[0] == native_case)
    return dsl.make_prompts(dsl.parse(text, VOCAB), VOCAB)
