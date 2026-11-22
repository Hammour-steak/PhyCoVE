"""PCVE edit vocabulary for the orange-juice dispenser scene."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402
from simulate_juice_dispenser_orange_cup import PhysicsConfig  # noqa: E402


_BASELINE = PhysicsConfig()
BASELINE_PHYSICS = {
    name: getattr(_BASELINE, name)
    for name in (
        "orange_juice_density_kg_m3",
        "orange_juice_kinematic_viscosity_m2_s",
        "nozzle_speed_m_s",
        "orange_juice_presence",
        "glass_presence",
        "gravity_m_s2",
        "pour_start_sec",
        "pour_end_sec",
    )
}

OBJECTS = {
    "orange_juice": {"zh": "橙汁", "en": "the orange juice"},
    "dispenser": {"zh": "果汁机", "en": "the juice dispenser"},
    "glass": {"zh": "透明接汁杯", "en": "the transparent receiving glass"},
}

PROPERTIES = {
    "flow_speed": dsl.PropertySpec("scalar", "m/s", "出口流速", "outlet flow speed"),
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("dispenser", "flow_speed"): dsl.SimBinding("nozzle_speed_m_s"),
    ("orange_juice", "viscosity"): dsl.SimBinding("orange_juice_kinematic_viscosity_m2_s"),
}

DELETE_BINDINGS = {
    "orange_juice": dsl.DeleteBinding("orange_juice_presence", index=0),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics=BASELINE_PHYSICS,
    total_frames=round(_BASELINE.fps * _BASELINE.duration_sec),
)

