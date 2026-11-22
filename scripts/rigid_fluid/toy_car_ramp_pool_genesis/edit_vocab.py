"""PCVE edit vocabulary for the toy car rolling into the courtyard pool (standard library only).

`pcve_edit_dsl.make_prompts(parse(EDIT_DSL[case], VOCAB), VOCAB)` gives each edit's published prompts;
SOURCE_PROMPTS is the published description of the source video. The case ids are those of
recipes/edit_plan.json; the published suite prefixes them with "edit_".
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
FRAMES = 96
BASELINE_PHYSICS = {
    "car_mass_kg": 0.42,
    "water_density_kg_m3": 998.0,
    "water_kinematic_viscosity_m2_s": 1.004e-6,
    "car_presence": [1],
    "water_presence": [1],
}

OBJECTS = {
    "car": {"zh": "玩具小车", "en": "the toy car"},
    "water": {"zh": "池水", "en": "the pool water"},
}

PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "density": dsl.PropertySpec("scalar", "kg/m^3", "密度", "density"),
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("car", "mass"): dsl.SimBinding("car_mass_kg"),
    ("water", "density"): dsl.SimBinding("water_density_kg_m3"),
    ("water", "viscosity"): dsl.SimBinding("water_kinematic_viscosity_m2_s"),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings={"car": dsl.DeleteBinding("car_presence", 0),
                     "water": dsl.DeleteBinding("water_presence", 0)},
    baseline_physics=BASELINE_PHYSICS,
    total_frames=FRAMES,
)

EDIT_DSL = {
    "no_car": "DELETE car",
    "heavy_car_x3": "SET car.mass TIMES 3",
    "low_density_div4": "SET water.density TIMES 0.25",
    "high_viscosity_x20000": "SET water.viscosity TIMES 20000",
    "mass_after_2s_x3": "SET car.mass TIMES 3 AT FRAME 49",
}

SOURCE_PROMPTS = {
    "vague": {
        "zh": "阳光下的庭院里，一辆白色玩具小车从橙色斜坡上滑下，冲进圆角充气泳池，溅起水花后浮在水面上，慢慢向前漂。",
        "en": "In a sunny courtyard, a white toy car slides down an orange ramp into a rounded inflatable pool, splashes "
              "in, and then floats on the water, drifting slowly forward.",
    },
    "quantitative": {
        "zh": "一辆长 16 cm、质量 0.42 kg 的玩具小车从静止开始沿 18° 的橙色斜坡滑下，约 1 s 时以约 1.8 m/s 冲进水深 10.5 cm "
              "的充气泳池（水的密度 998 kg/m³），溅起水花后浮在水面上，以不到 0.2 m/s 的速度慢慢向前漂。",
        "en": "A 16 cm, 0.42 kg toy car starts from rest on an 18° orange ramp, slides down and plunges at about 1.8 m/s, "
              "about 1 s in, into an inflatable pool filled 10.5 cm deep (998 kg/m³), splashes, and then floats, "
              "drifting forward at under 0.2 m/s.",
    },
}
