"""PCVE edit vocabulary for the fish-tank toy-car scene."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402
from simulate_fish_tank_toy import PhysicsConfig  # noqa: E402


_BASELINE = PhysicsConfig()
BASELINE_PHYSICS = {
    name: getattr(_BASELINE, name)
    for name in (
        "toy_mass_kg",
        "water_density_kg_m3",
        "water_kinematic_viscosity_m2_s",
        "toy_presence",
        "water_presence",
        "gravity_m_s2",
        "release_time_sec",
    )
}

OBJECTS = {
    "toy_car": {"zh": "掉进鱼缸的玩具车", "en": "the toy car"},
    "water": {"zh": "鱼缸里的水", "en": "the tank water"},
}

PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "density": dsl.PropertySpec("scalar", "kg/m^3", "密度", "density"),
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("toy_car", "mass"): dsl.SimBinding("toy_mass_kg"),
    ("water", "density"): dsl.SimBinding("water_density_kg_m3"),
    ("water", "viscosity"): dsl.SimBinding("water_kinematic_viscosity_m2_s"),
}

DELETE_BINDINGS = {
    "toy_car": dsl.DeleteBinding("toy_presence", index=0),
    "water": dsl.DeleteBinding("water_presence", index=0),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics=BASELINE_PHYSICS,
    total_frames=round(_BASELINE.fps * _BASELINE.duration_sec),
)
