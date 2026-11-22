"""Strict single-variable edit vocabulary for ``tennis_net_hit``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402


BASELINE_PHYSICS = {
    "ball_initial_velocity_y_m_s": 8.0,
    "net_young_modulus_pa": 25_000_000.0,
    # The generic DELETE binding operates on a presence list.  The build
    # entry point maps its sole value to the solver's scalar ``net_present``.
    "net_active": [1],
    "ball_mass_kg": 0.0576,
}

OBJECTS = {
    "tennis_ball": {"zh": "网球", "en": "the tennis ball"},
    "tennis_net": {"zh": "球网", "en": "the tennis net"},
}

PROPERTIES = {
    "initial_velocity": dsl.PropertySpec("scalar", "m/s", "初速度", "initial speed"),
    "young_modulus": dsl.PropertySpec("scalar", "Pa", "杨氏模量", "Young's modulus"),
}

SIM_BINDINGS = {
    ("tennis_ball", "initial_velocity"): dsl.SimBinding("ball_initial_velocity_y_m_s"),
    ("tennis_net", "young_modulus"): dsl.SimBinding("net_young_modulus_pa"),
}

DELETE_BINDINGS = {
    "tennis_net": dsl.DeleteBinding("net_active", index=0),
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


# Vocabulary of the staged DELETE tennis_ball case (outside the published catalog): the scene vocabulary plus the
# ball's presence slot. Kept apart from VOCAB, whose editable objects the published catalog records.
STAGED_VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings={**DELETE_BINDINGS, "tennis_ball": dsl.DeleteBinding("ball_active", index=0)},
    baseline_physics={**BASELINE_PHYSICS, "ball_active": [1]},
    total_frames=TOTAL_FRAMES,
)
STAGED_DSL = {"remove_tennis_ball": "DELETE tennis_ball"}


def solver_overrides(edit: Any) -> dict[str, Any]:
    """Translate one parsed DSL edit into the production solver's fields."""
    staged = isinstance(edit, dsl.DeleteEdit) and edit.object_id not in DELETE_BINDINGS
    values = dict(dsl.to_physics_override(edit, STAGED_VOCAB if staged else VOCAB))
    if "net_active" in values:
        active = values.pop("net_active")
        values["net_present"] = bool(active[0])
    if "ball_active" in values:
        active = values.pop("ball_active")
        values["ball_present"] = bool(active[0])
    return values
