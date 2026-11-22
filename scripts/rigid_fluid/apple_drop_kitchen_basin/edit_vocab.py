"""PCVE edit vocabulary for the apple kitchen-basin drop (standard library only).

`pcve_edit_dsl.make_prompts(parse(EDIT_DSL[case], VOCAB), VOCAB)` gives each edit's published prompts;
SOURCE_PROMPTS is the published description of the source video.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
FRAMES = 96
# The baseline of simulate_apple_drop_kitchen_basin.py (BALL_MASS, LIQUID_DENSITY, LIQUID_NU).
BASELINE_PHYSICS = {
    "ball_mass": 850.0 * 4 / 3 * math.pi * 0.04 ** 3,
    "liquid_density": 998.2,
    "liquid_nu": 1.004e-6,
    "water_presence": [1],
    "apple_presence": [1],
}

OBJECTS = {
    "apple": {"zh": "苹果", "en": "the apple"},
    "water": {"zh": "盆里的水", "en": "the water in the basin"},
}

PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "density": dsl.PropertySpec("scalar", "kg/m^3", "密度", "density"),
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("apple", "mass"): dsl.SimBinding("ball_mass"),
    ("water", "density"): dsl.SimBinding("liquid_density"),
    ("water", "viscosity"): dsl.SimBinding("liquid_nu"),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings={"water": dsl.DeleteBinding("water_presence", 0), "apple": dsl.DeleteBinding("apple_presence", 0)},
    baseline_physics=BASELINE_PHYSICS,
    total_frames=FRAMES,
)

# Builder case id -> edit DSL (the published suite prefixes the water-removal cases with "edit_").
EDIT_DSL = {
    "edit_heavy_apple": "SET apple.mass TIMES 1.5",
    "edit_high_density_liquid": "SET water.density TIMES 2",
    "edit_viscous_liquid": "SET water.viscosity TIMES 10000",
    "delete_water": "DELETE water",
    "delete_water_at_2s": "DELETE water AT FRAME 49",
}

SOURCE_PROMPTS = {
    "vague": {
        "zh": "一个红苹果从厨房台面上的圆形水盆上方落下,掉进盆里的水中溅起水花,碰到盆底后又浮上来,漂在水面上。",
        "en": "A red apple falls into a round basin of water on a kitchen counter, splashes in, touches the bottom of "
              "the basin, then bobs back up and floats.",
    },
    "quantitative": {
        "zh": "一个直径 8 cm、质量 228 g(密度 850 kg/m³)的红苹果从底部离水面约 37 cm 处落下,掉进圆形水盆的水中,"
              "碰到盆底后浮起并漂在水面上。",
        "en": "A red apple 8 cm across weighing 228 g (density 850 kg/m³) is dropped with its bottom about 37 cm above "
              "the water into a round basin, touches the basin floor, then bobs back up and floats.",
    },
}
