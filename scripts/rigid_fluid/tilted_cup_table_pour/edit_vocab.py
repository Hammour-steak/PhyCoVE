"""PCVE edit vocabulary for the tilted cup pour (Genesis version): whole-clip edits only."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
DURATION_SEC = 4.0

BASELINE_PHYSICS = {
    "water_density_kg_m3": 998.2,
    "water_kinematic_viscosity_m2_s": 1.004e-6,
    "water_surface_tension_n_m": 0.072,
    "water_volume_ml": 81.0,
    "cup_tilt_deg": 58.0,
    "table_adhesion_ratio": 1.0,          # oak-water cohesion relative to water-water (ghost wetting factor)
    "cup_presence": [1],
    "water_presence": [1],
    "gravity_m_s2": 9.81,
}

OBJECTS = {
    "water": {"zh": "液体", "en": "the liquid"},
    "table": {"zh": "木桌面", "en": "the wooden tabletop"},
    "cup": {"zh": "倾斜的陶瓷杯", "en": "the tilted ceramic cup"},
}

PROPERTIES = {
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
    "adhesion": dsl.PropertySpec("scalar", "ratio", "润湿黏附强度", "wetting adhesion strength"),
}

SIM_BINDINGS = {
    ("water", "viscosity"): dsl.SimBinding("water_kinematic_viscosity_m2_s"),
    ("table", "adhesion"): dsl.SimBinding("table_adhesion_ratio"),
}

DELETE_BINDINGS = {
    "cup": dsl.DeleteBinding("cup_presence", index=0),
    "water": dsl.DeleteBinding("water_presence", index=0),
}

VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS, delete_bindings=DELETE_BINDINGS,
                       baseline_physics=BASELINE_PHYSICS, total_frames=int(round(FPS * DURATION_SEC)))


def sim_args(physics):
    """simulate_tilted_cup_table_pour.py flags for a case's physics (None: no liquid, nothing to simulate)"""
    if not physics["water_presence"][0]:
        return None
    nu, ratio = physics["water_kinematic_viscosity_m2_s"], physics["table_adhesion_ratio"]
    if not (nu >= 0 and 0 <= ratio <= 1):
        raise ValueError("viscosity must be nonnegative and the table adhesion ratio in [0, 1]")
    flags = ["--mu", repr(nu), "--table-wet", repr(ratio)]
    if not physics["cup_presence"][0]:
        # the whole 81 mL lands at once and sheets out more than 30 cm every way: the tabletop patch is the whole worktop
        # (x +-0.60, front edge y = -0.42), and its back edge is the tiled wall (face at y = 0.296; domain stops 2 mm in)
        flags += ["--no-cup", "--table-x", "-0.60", "0.60", "--table-y", "-0.42", "0.298"]
    return flags
