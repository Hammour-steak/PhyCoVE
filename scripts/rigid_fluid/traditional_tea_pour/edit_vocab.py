"""PCVE edit vocabulary for the traditional tea pour.

The edits are built by build_traditional_tea_edits.py (workflow "edits"), which takes their physics from its
suite definition; this vocabulary states them in the edit DSL and generates their prompts with make_prompts. EDIT_DSL is
keyed by the workflow's case names (published as edit_<case>); SOURCE_PROMPTS is the source video's description.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
DURATION_SEC = 4.0

BASELINE_PHYSICS = {
    "tea_density_kg_m3": 1000.0,
    "tea_kinematic_viscosity_m2_s": 1.05e-6,
    "inlet_speed_m_s": 0.5,                 # at the spout, from 0.5 s to 3.5 s (about 11.7 mL/s)
    "tea_presence": [1],
    "gravity_m_s2": 9.81,
}

OBJECTS = {
    "tea": {"zh": "茶水", "en": "the tea"},
}

PROPERTIES = {
    "flow_speed": dsl.PropertySpec("scalar", "m/s", "出口流速", "outlet flow speed"),
}

SIM_BINDINGS = {
    ("tea", "flow_speed"): dsl.SimBinding("inlet_speed_m_s"),
}

DELETE_BINDINGS = {
    "tea": dsl.DeleteBinding("tea_presence", index=0),
}

VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS, delete_bindings=DELETE_BINDINGS,
                       baseline_physics=BASELINE_PHYSICS, total_frames=int(round(FPS * DURATION_SEC)))

# speed_scale and stop_flow_at_sec in build_traditional_tea_edits.py; the stop applies at solver time 2.0 s, frame 49
EDIT_DSL = {
    "speed_2x": "SET tea.flow_speed TIMES 2",
    "speed_0p5x": "SET tea.flow_speed TIMES 0.5",
    "remove_tea": "DELETE tea",
    "stop_flow_at_2s": "SET tea.flow_speed TO 0 AT FRAME 49",
}

SOURCE_PROMPTS = {
    "vague": {
        "zh": "木质茶桌上，一把白底蓝红花纹的瓷茶壶从壶嘴往杯垫上的白瓷小茶杯里倒茶，茶水落进杯中，杯里的茶慢慢变多，随后水流停下。",
        "en": "On a wooden tea table, a white porcelain teapot painted with blue and red flowers pours tea from its spout "
              "into a small white cup on a woven coaster; the tea falls into the cup, the cup slowly fills, and then the "
              "stream stops.",
    },
    "quantitative": {
        "zh": "茶水（密度 1000 kg/m³，运动黏度 1.05e-6 m²/s）从离桌面 12.5 cm 的壶嘴以 0.5 m/s 流出，约 11.7 mL/s，从 0.5 s "
              "倒到 3.5 s，落进杯口高 6.5 cm 的小茶杯，重力 9.81 m/s²。",
        "en": "Tea (1000 kg/m³, 1.05e-6 m²/s) leaves the spout 12.5 cm above the table at 0.5 m/s, about 11.7 mL/s, from "
              "0.5 s to 3.5 s, and falls into a small cup whose rim is 6.5 cm high, under 9.81 m/s² gravity.",
    },
}


def prompts(case: str) -> dict[str, dict[str, str]]:
    """The bilingual prompts of a workflow case ("source" or an EDIT_DSL key)."""
    if case == "source":
        return SOURCE_PROMPTS
    return dsl.make_prompts(dsl.parse(EDIT_DSL[case], VOCAB), VOCAB)
