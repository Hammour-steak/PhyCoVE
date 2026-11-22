"""PCVE edit vocabulary for the toy car dropped onto a bathtub float (Genesis DFSPH version)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
DURATION_SEC = 4.0

BASELINE_PHYSICS = {
    "car_mass_kg": 2.0,
    "float_mass_kg": 0.15,
    "water_density_kg_m3": 998.0,
    "car_presence": [1],
    "float_presence": [1],
    "water_presence": [1],
    "gravity_m_s2": 9.81,
    "water_height_m": 0.42,                       # still surface above the room floor; the water is 0.31 m deep
}

OBJECTS = {
    "toy_car": {"zh": "下落的玩具小车", "en": "the falling toy car"},
    "float": {"zh": "浴缸里的紫色浮垫", "en": "the bathtub float"},
    "water": {"zh": "浴缸里的水", "en": "the bathtub water"},
}

PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "density": dsl.PropertySpec("scalar", "kg/m^3", "密度", "density"),
}

SIM_BINDINGS = {
    ("toy_car", "mass"): dsl.SimBinding("car_mass_kg"),
    ("float", "mass"): dsl.SimBinding("float_mass_kg"),
    ("water", "density"): dsl.SimBinding("water_density_kg_m3"),
}

DELETE_BINDINGS = {
    "toy_car": dsl.DeleteBinding("car_presence", index=0),
    "float": dsl.DeleteBinding("float_presence", index=0),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics=BASELINE_PHYSICS,
    total_frames=round(FPS * DURATION_SEC),
)


def has_float(physics):
    return bool(physics["float_presence"][0])


def sim_args(physics, at_frame=None):
    """simulate_toy_car_float_bathtub.py run flags for a case's physics. A density change applies from the clip's start, or
    from (at_frame - 1) / FPS for a timed edit (which continues the source's state at that frame)."""
    flags = ["--car-mass", repr(float(physics["car_mass_kg"])), "--float-mass", repr(float(physics["float_mass_kg"]))]
    if not physics["car_presence"][0]:
        flags.append("--no-car")
    if not has_float(physics):
        flags.append("--no-float")
    rho = float(physics["water_density_kg_m3"])
    if rho != BASELINE_PHYSICS["water_density_kg_m3"]:
        flags += ["--density-after", repr(rho), "--density-time", repr((at_frame - 1) / FPS if at_frame else 0.0)]
    return flags
