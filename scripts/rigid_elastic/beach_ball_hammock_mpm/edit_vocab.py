"""Editable physical properties of the beach-ball / hammock scene and its published cases.

BASELINE_PHYSICS are the values of the published source run. make_prompts(parse(case["edit_dsl"], VOCAB), VOCAB)
gives the published prompts of each edit in EDIT_CASES; SOURCE_PROMPTS are the published source prompts. `flags`
are the simulator options of each run on top of SHARED_FLAGS (see README.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402


BASELINE_PHYSICS = {
    "ball_mass": 0.25,
    "ball_initial_speed": 1.0,
    "hammock_young_modulus": 15000.0,
    # presence lists for DELETE (the simulator's --no-ball / --no-hammock)
    "ball_present": [1],
    "hammock_present": [1],
}

OBJECTS = {
    "beach_ball": {"zh": "沙滩球", "en": "the beach ball"},
    "hammock": {"zh": "吊床", "en": "the hammock"},
}

PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "initial_velocity": dsl.PropertySpec("scalar", "m/s", "初速度大小", "initial speed"),
    "young_modulus": dsl.PropertySpec("scalar", "Pa", "杨氏模量", "Young's modulus"),
}

SIM_BINDINGS = {
    ("beach_ball", "mass"): dsl.SimBinding("ball_mass"),
    ("beach_ball", "initial_velocity"): dsl.SimBinding("ball_initial_speed"),
    ("hammock", "young_modulus"): dsl.SimBinding("hammock_young_modulus"),
}

TOTAL_FRAMES = 96

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings={"beach_ball": dsl.DeleteBinding("ball_present", 0), "hammock": dsl.DeleteBinding("hammock_present", 0)},
    baseline_physics=BASELINE_PHYSICS,
    total_frames=TOTAL_FRAMES,
)

SHARED_FLAGS = (
    "--ball-mass", "0.25", "--ball-vz", "-1.0", "--visible-damping", "0.9995",
    "--strain-limit-min", "0.80", "--strain-limit-max", "1.20",
    "--inplane-tether-hz", "4.0", "--inplane-tether-damping-ratio", "0.35",
    "--end-transition-width", "0.45", "--end-tether-hz", "8.0", "--end-tether-damping-ratio", "0.60",
    "--pre-roll-seconds", "12", "--pre-roll-damping", "0.998", "--max-lateral-displacement", "0.20",
)

SOURCE_CASE = {
    "case_id": "source",
    "variant_id": "source_young_15000pa_preroll12",
    "flags": ("--young-modulus", "15000"),
}

EDIT_CASES = (
    {
        "case_id": "edit_hammock_young_1500pa",
        "variant_id": "edit_hammock_young_1500pa",
        "edit_dsl": "SET hammock.young_modulus TIMES 0.1",
        "flags": ("--young-modulus", "1500"),
    },
    {
        "case_id": "edit_young_15000_to_1500pa_at_2_5s",
        "variant_id": "edit_young_15000_to_1500pa_at_2_5s",
        "edit_dsl": "SET hammock.young_modulus TIMES 0.1 AT FRAME 61",
        "flags": ("--young-modulus", "15000", "--young-modulus-after", "1500", "--young-modulus-change-time", "2.5"),
    },
    {
        "case_id": "edit_young_70000pa_hard",
        "variant_id": "edit_young_70000pa_hard",
        "edit_dsl": "SET hammock.young_modulus TO 70000",
        "flags": ("--young-modulus", "70000"),
    },
)

SOURCE_PROMPTS = {
    "vague": {
        "zh": "海滩上，一个沙滩球从上方落进两根木桩之间拉着的弹性吊床里，把吊床压下去，上下晃动后停在吊床中。",
        "en": "On a beach, a beach ball drops into an elastic hammock strung between two posts, presses it down, "
              "bobs and comes to rest in it.",
    },
    "quantitative": {
        "zh": "一个直径 32 cm、质量 0.25 kg 的沙滩球以 1 m/s 的速度向下落进杨氏模量 15 kPa 的弹性吊床，"
              "把吊床中部压下约 3 cm 后停在其中。",
        "en": "A 32 cm, 0.25 kg beach ball falls at 1 m/s into an elastic hammock with a Young's modulus of 15 kPa, "
              "pushes its middle down by about 3 cm and comes to rest in it.",
    },
}

