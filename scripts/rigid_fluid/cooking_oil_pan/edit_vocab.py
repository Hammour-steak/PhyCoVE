"""PCVE edit vocabulary for the cooking-oil pour (Genesis version)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
DURATION_SEC = 4.0
RAMP_SEC = 0.2                                       # a flow change during the clip: a bottle cannot change its pour instantly
JET_RADIUS_M = 0.0023033                             # the 4.6 mm stream at the rim at the baseline pour
FIXED_OPENING_MAX_ML_S = 30.0                        # above this the 4.6 mm stream would leave at more than 2 m/s (a squirt)
ROPE_MIN_NU = 1e-3                                   # from here on the oil lands in a coiling rope (surface --rope)
# the bottle's mouth in pan-local coordinates: centre of its end face, outward axis, inner radius of the rim
MOUTH_END_M = (-0.03175, -0.00511, 0.25532)
MOUTH_AXIS = (0.706, -0.131, -0.696)
RIM_INNER_RADIUS_M = 0.01346

BASELINE_PHYSICS = {
    "oil_density_kg_m3": 915.0,
    "oil_kinematic_viscosity_m2_s": 1.4e-4,
    "oil_surface_tension_n_m": 0.032,
    "flow_rate_ml_s": 10.0,
    "pour_start_sec": 7 / 24,
    "gravity_m_s2": 9.81,
    "pan_presence": [1],
}

OBJECTS = {
    "bottle": {"zh": "油瓶", "en": "the oil bottle"},
    "oil": {"zh": "食用油", "en": "the cooking oil"},
    "pan": {"zh": "平底锅", "en": "the frying pan"},
}

PROPERTIES = {
    "flow_rate": dsl.PropertySpec("scalar", "mL/s", "出油流量", "pour rate"),
    "kinematic_viscosity": dsl.PropertySpec("scalar", "m²/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("bottle", "flow_rate"): dsl.SimBinding("flow_rate_ml_s"),
    ("oil", "kinematic_viscosity"): dsl.SimBinding("oil_kinematic_viscosity_m2_s"),
}

DELETE_BINDINGS = {"pan": dsl.DeleteBinding("pan_presence", 0)}

VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS, delete_bindings=DELETE_BINDINGS,
                       baseline_physics=BASELINE_PHYSICS, total_frames=int(round(FPS * DURATION_SEC)))


def rim_exit(jet_radius):
    """pour exit for a stream of this radius: its outer edge stays on the lowest point of the rim, 1 mm past the rim face"""
    g = (0.0, 0.0, -1.0)
    along = sum(a * b for a, b in zip(g, MOUTH_AXIS))
    down = [a - along * b for a, b in zip(g, MOUTH_AXIS)]
    norm = math.sqrt(sum(a * a for a in down))
    r = RIM_INNER_RADIUS_M + 0.5e-3 - (jet_radius - JET_RADIUS_M)
    return [round(e + r * d / norm + 1e-3 * x, 5) for e, d, x in zip(MOUTH_END_M, down, MOUTH_AXIS)]


def poured_ml(physics, at_frame=None):
    base, flow, start = BASELINE_PHYSICS["flow_rate_ml_s"], physics["flow_rate_ml_s"], BASELINE_PHYSICS["pour_start_sec"]
    if at_frame is None:
        return flow * (DURATION_SEC - start)
    t = (at_frame - 1) / FPS
    return base * (t - start) + flow * (DURATION_SEC - t)


def ghost_radius(physics, at_frame=None):
    """how far the pan's boundary particles have to reach: the puddle's size, which the poured volume and viscosity set"""
    if physics["oil_kinematic_viscosity_m2_s"] >= ROPE_MIN_NU:
        return 0.09
    volume = poured_ml(physics, at_frame)
    return 0.12 if volume <= 40.0 else 0.13 if volume <= 100.0 else 0.14


def rope(physics):
    return physics["oil_kinematic_viscosity_m2_s"] >= ROPE_MIN_NU


def sim_args(physics, at_frame=None):
    """simulate_cooking_oil_pan.py flags for a case's physics (and an edit's frame). A flow edit keeps the 4.6 mm stream and
    changes its exit speed, up to FIXED_OPENING_MAX_ML_S. Beyond that a bottle tipped further pours a thicker sheet over the
    lip rather than a faster one (weir flow: speed ~ Q^(1/3), section ~ Q^(2/3)). An edit at frame F changes the flow from
    (F - 1) / FPS on, over RAMP_SEC."""
    base, flow = BASELINE_PHYSICS["flow_rate_ml_s"], physics["flow_rate_ml_s"]
    if flow <= 0:
        raise ValueError("the pour rate must be positive")
    flags = ["--mu", repr(physics["oil_kinematic_viscosity_m2_s"]), "--ghost-radius", repr(ghost_radius(physics, at_frame))]
    if at_frame is None:
        flags += ["--flow", repr(flow / 1e6)]
        if flow > FIXED_OPENING_MAX_ML_S:
            radius = JET_RADIUS_M * (flow / base) ** (1 / 3)
            flags += ["--jet-radius", repr(round(radius, 6)), "--exit", *map(repr, rim_exit(radius))]
    elif flow != base:
        if flow > FIXED_OPENING_MAX_ML_S:
            raise ValueError("timed edits above the fixed-opening range are not implemented")
        flags += ["--schedule", f"{(at_frame - 1) / FPS}:{flow / 1e6!r}:{RAMP_SEC}"]
    return flags
