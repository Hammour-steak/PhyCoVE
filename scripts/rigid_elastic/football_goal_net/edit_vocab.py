"""Strict single-variable edit vocabulary for ``football_goal_net``.

The SET and DELETE prompts of the builder catalog are pcve_edit_dsl.make_prompts output for this
vocabulary; solver_overrides() maps a parsed edit onto the fields of physics/strict_edit_plan.json, and
TIMED_DSL declares the timed edits that physics/solve_timed.py solves natively.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

BASELINE_PHYSICS = {
    "ball_mass_kg": 0.43,
    "ball_horizontal_velocity_mps": 16.0,
    "net_axial_young_modulus_Pa": 84415781.81594129,
    # DELETE operates on a presence list; the native case maps it to the solver's net_present flag.
    "net_present": [1],
    "ball_present": [1],
}

OBJECTS = {
    "ball": {"zh": "足球", "en": "the football"},
    "net": {"zh": "球门网", "en": "the goal net"},
}

PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "horizontal_velocity": dsl.PropertySpec("scalar", "m/s", "水平初速度", "initial horizontal speed"),
    "young_modulus": dsl.PropertySpec("scalar", "Pa", "杨氏模量", "Young's modulus"),
}

SIM_BINDINGS = {
    ("ball", "mass"): dsl.SimBinding("ball_mass_kg"),
    ("ball", "horizontal_velocity"): dsl.SimBinding("ball_horizontal_velocity_mps"),
    ("net", "young_modulus"): dsl.SimBinding("net_axial_young_modulus_Pa"),
}

DELETE_BINDINGS = {
    "net": dsl.DeleteBinding("net_present", index=0),
    "ball": dsl.DeleteBinding("ball_present", index=0),
}

TOTAL_FRAMES = 96

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics=BASELINE_PHYSICS,
    total_frames=TOTAL_FRAMES,
)

def solver_overrides(edit: Any) -> dict[str, Any]:
    """Translate one parsed DSL edit into the fields of physics/strict_edit_plan.json."""
    return dict(dsl.to_physics_override(edit, VOCAB))


# Timed edits (AT FRAME k), solved natively by physics/solve_timed.py: the source physics up to frame k,
# then the whole-clip edit's solver snapshot restored from the lossless checkpoint at the edit tick.
TIMED_DSL = {"mass_double_at_frame_8": "SET ball.mass TIMES 2 AT FRAME 8"}
TIMED_BASE = {"mass_double_at_frame_8": "mass_double"}


def timed_schedule(case: str) -> list[dict[str, Any]]:
    """[{'frame': k, 'params': {...}}] in the shared to_scenario_override form."""
    return dsl.to_scenario_override(dsl.parse(TIMED_DSL[case], VOCAB), VOCAB)[dsl.TIMED_EDITS_KEY]
