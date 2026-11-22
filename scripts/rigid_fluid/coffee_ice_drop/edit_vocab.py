"""PCVE edit vocabulary for the coffee ice drop scene and its mapping onto simulate_coffee_ice_drop.py flags."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
DURATION_SEC = 4.0

BASELINE_PHYSICS = {
    "ice_side_m": 0.016,
    "ice_density_kg_m3": 920.0,
    "coffee_density_kg_m3": 1030.0,
    "coffee_kinematic_viscosity_m2_s": 1.45e-6,
    "ice_presence": [1],
    "coffee_presence": [1],
    "gravity_m_s2": 9.81,
    "ice_drop_height_m": 0.04,
}

OBJECTS = {
    "ice": {"zh": "落入咖啡的冰块", "en": "the falling ice cube"},
    "coffee": {"zh": "杯中的咖啡", "en": "the coffee in the cup"},
}

PROPERTIES = {
    "density": dsl.PropertySpec("scalar", "kg/m^3", "密度", "density"),
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("ice", "density"): dsl.SimBinding("ice_density_kg_m3"),
    ("coffee", "density"): dsl.SimBinding("coffee_density_kg_m3"),
    ("coffee", "viscosity"): dsl.SimBinding("coffee_kinematic_viscosity_m2_s"),
}

DELETE_BINDINGS = {
    "ice": dsl.DeleteBinding("ice_presence", index=0),
    "coffee": dsl.DeleteBinding("coffee_presence", index=0),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics=BASELINE_PHYSICS,
    total_frames=round(FPS * DURATION_SEC),
)


def sim_args(physics: dict) -> list[str]:
    """Simulation flags for a physics dict (the baseline with an edit's override applied)."""
    args = []
    if physics["coffee_density_kg_m3"] != BASELINE_PHYSICS["coffee_density_kg_m3"]:
        args += ["--coffee-density", repr(float(physics["coffee_density_kg_m3"]))]
    if physics["ice_density_kg_m3"] != BASELINE_PHYSICS["ice_density_kg_m3"]:
        args += ["--ice-density", repr(float(physics["ice_density_kg_m3"]))]
    nu = float(physics["coffee_kinematic_viscosity_m2_s"])
    if nu != BASELINE_PHYSICS["coffee_kinematic_viscosity_m2_s"]:
        # explicit SPH viscosity is limited to dt < 0.01 h^2 / nu; beyond ~1e-4 m^2/s solve it implicitly
        args += ["--mu", "0", "--implicit-nu", repr(nu)] if nu > 1e-4 else ["--mu", repr(nu)]
    if not physics["ice_presence"][0]:
        args += ["--no-ice"]
    if not physics["coffee_presence"][0]:
        args += ["--no-coffee", "--floor-gap", "0"]   # the raised hidden floor only exists for the liquid
    return args
