"""PCVE edit vocabulary for the cup water drop scene (Genesis version)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
DURATION_SEC = 4.0
ST_GAMMA_PER_N_M = 1.5 / 0.072   # Akinci surface-tension gamma per N/m at 1 mm particles (Rayleigh-calibrated)

BASELINE_PHYSICS = {
    "cup_mass_kg": 0.32,
    "cup_height_m": 0.072,
    "cup_release_bottom_height_m": 0.284,
    "cup_yaw_deg": 12.0,
    "water_density_kg_m3": 998.2,
    "water_kinematic_viscosity_m2_s": 1.0e-6,
    "water_surface_tension_n_m": 0.072,
    "water_fill_top_in_cup_frame_m": 0.022,
    "cup_presence": [1],
    "water_presence": [1],
    "gravity_m_s2": 9.81,
}

OBJECTS = {
    "cup": {"zh": "下落的陶瓷杯", "en": "the falling ceramic mug"},
    "water": {"zh": "杯中的水", "en": "the water in the mug"},
}

PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "density": dsl.PropertySpec("scalar", "kg/m^3", "密度", "density"),
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("cup", "mass"): dsl.SimBinding("cup_mass_kg"),
    ("water", "density"): dsl.SimBinding("water_density_kg_m3"),
    ("water", "viscosity"): dsl.SimBinding("water_kinematic_viscosity_m2_s"),
}

DELETE_BINDINGS = {
    "water": dsl.DeleteBinding("water_presence", index=0),
    "cup": dsl.DeleteBinding("cup_presence", index=0),
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
    for key, flag in (("cup_mass_kg", "--cup-mass"), ("water_density_kg_m3", "--density"),
                      ("water_kinematic_viscosity_m2_s", "--mu")):
        if physics[key] != BASELINE_PHYSICS[key]:
            args += [flag, repr(float(physics[key]))]
    if not physics["water_presence"][0]:
        args += ["--no-water"]
    if not physics["cup_presence"][0]:
        args += ["--no-cup"]
    return args
