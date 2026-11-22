"""PCVE edit vocabulary for the faucet-sink rigid-fluid scene."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402
from simulate_faucet_sink import PhysicsConfig  # noqa: E402


_BASELINE = PhysicsConfig()
BASELINE_PHYSICS = {
    name: getattr(_BASELINE, name)
    for name in (
        "faucet_inflow_velocity_m_s",
        "water_kinematic_viscosity_m2_s",
    )
}

OBJECTS = {
    "faucet": {"zh": "洗手台水龙头", "en": "the sink faucet"},
    "water": {"zh": "水龙头流出的液体", "en": "the liquid flowing from the faucet"},
}

PROPERTIES = {
    "inflow_velocity": dsl.PropertySpec("scalar", "m/s", "入流速度", "inflow velocity"),
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("faucet", "inflow_velocity"): dsl.SimBinding("faucet_inflow_velocity_m_s"),
    ("water", "viscosity"): dsl.SimBinding("water_kinematic_viscosity_m2_s"),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings={},
    baseline_physics=BASELINE_PHYSICS,
    total_frames=round(_BASELINE.fps * _BASELINE.duration_sec),
)
