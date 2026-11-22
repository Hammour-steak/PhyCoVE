"""PCVE edit vocabulary for the procedural wine-pour scene."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402
from simulate_wine_pour import PhysicsConfig  # noqa: E402


_BASELINE = PhysicsConfig()
BASELINE_PHYSICS = {
    name: getattr(_BASELINE, name)
    for name in (
        "wine_density_kg_m3",
        "wine_kinematic_viscosity_m2_s",
        "flow_rate_ml_s",
        "nozzle_speed_m_s",
        "nozzle_speed_change_frame",
        "nozzle_speed_after_m_s",
        "wine_presence",
        "glass_presence",
        "gravity_m_s2",
        "pour_start_sec",
        "pour_end_sec",
    )
}

OBJECTS = {
    "wine": {"zh": "倒出的红酒", "en": "the pouring red wine"},
    "bottle": {"zh": "酒瓶", "en": "the wine bottle"},
    "glass": {"zh": "透明酒杯", "en": "the transparent wine glass"},
}

PROPERTIES = {
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
    "flow_rate": dsl.PropertySpec("scalar", "mL/s", "体积流量", "volumetric flow rate"),
    "flow_speed": dsl.PropertySpec("scalar", "m/s", "流速", "flow speed"),
}

SIM_BINDINGS = {
    ("wine", "viscosity"): dsl.SimBinding("wine_kinematic_viscosity_m2_s"),
    ("bottle", "flow_rate"): dsl.SimBinding("flow_rate_ml_s"),
    ("bottle", "flow_speed"): dsl.SimBinding("nozzle_speed_m_s"),
}

DELETE_BINDINGS = {"wine": dsl.DeleteBinding("wine_presence", 0)}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics=BASELINE_PHYSICS,
    total_frames=round(_BASELINE.fps * _BASELINE.duration_sec),
)
