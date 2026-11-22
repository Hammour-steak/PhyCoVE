"""PCVE edit vocabulary for the toy boat glide (standard library only)."""

from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcve_edit_dsl as dsl  # noqa: E402
import physics_toy_boat_pool_glide as physics  # noqa: E402


BASELINE_PHYSICS = dict(physics.BASELINE_PHYSICS)

OBJECTS = {
    "toy_tug": {"zh": "玩具拖船", "en": "the toy tugboat"},
    "water": {"zh": "池水", "en": "the pool water"},
}

PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "initial_velocity": dsl.PropertySpec("scalar", "m/s", "初速度大小", "initial speed"),
    "density": dsl.PropertySpec("scalar", "kg/m^3", "密度", "density"),
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("toy_tug", "mass"): dsl.SimBinding("boat_mass"),
    # The speed the hidden push brings the boat to and releases it at, along the base's heading.
    ("toy_tug", "initial_velocity"): dsl.SimBinding("boat_initial_speed"),
    ("water", "density"): dsl.SimBinding("liquid_density"),
    ("water", "viscosity"): dsl.SimBinding("liquid_kinematic_viscosity"),
}

DELETE_BINDINGS = {
    "toy_tug": dsl.DeleteBinding("boat_presence", index=0),
    "water": dsl.DeleteBinding("water_presence", index=0),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics=BASELINE_PHYSICS,
    total_frames=physics.FRAMES,
)
