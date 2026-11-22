"""PCVE edit vocabulary for the milk carton pour."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
DURATION_SEC = 4.0
EMITTER_AREA_M2 = 233 * 0.00093 ** 2                 # 233 rest-lattice particles in the 8 mm spout jet

BASELINE_PHYSICS = {
    "milk_density_kg_m3": 1030.0,
    "milk_kinematic_viscosity_m2_s": 2.2e-6,
    "milk_surface_tension_n_m": 0.046,
    "spout_flow_speed_m_s": 75e-6 / EMITTER_AREA_M2,  # 0.372 m/s through the spout: 75 mL/s
    "pour_start_sec": 0.25,
    "milk_presence": [1],
    "gravity_m_s2": 9.81,
}

OBJECTS = {
    "milk": {"zh": "牛奶", "en": "the milk"},
    "carton": {"zh": "牛奶盒", "en": "the milk carton"},
    "glass": {"zh": "玻璃杯", "en": "the glass cup"},
}

PROPERTIES = {
    "flow_speed": dsl.PropertySpec("scalar", "m/s", "出口流速", "outlet flow speed"),
}

SIM_BINDINGS = {
    ("milk", "flow_speed"): dsl.SimBinding("spout_flow_speed_m_s"),
}

DELETE_BINDINGS = {
    "milk": dsl.DeleteBinding("milk_presence", index=0),
}

VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS, delete_bindings=DELETE_BINDINGS,
                       baseline_physics=BASELINE_PHYSICS, total_frames=int(round(FPS * DURATION_SEC)))


def sim_args(physics, at_frame=None):
    """simulate_milk_pitcher_glass.py flags for a case's physics (None: no milk, nothing to simulate). The spout area is
    fixed, so a flow-speed edit scales the volume flow; an edit at frame F changes the flow from (F - 1) / FPS on."""
    if not physics["milk_presence"][0]:
        return None
    speed = physics["spout_flow_speed_m_s"]
    if speed < 0:
        raise ValueError("flow speed must be nonnegative")
    if at_frame is None:
        return ["--flow", repr(speed * EMITTER_AREA_M2)]
    if speed != 0.0:
        raise ValueError("timed edits other than stopping the pour are not implemented")
    return ["--stop", repr((at_frame - 1) / FPS)]
