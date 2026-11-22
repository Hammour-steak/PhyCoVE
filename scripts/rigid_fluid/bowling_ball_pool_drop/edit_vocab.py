"""PCVE edit vocabulary for the bowling-ball pool-drop scene (standard library only)."""

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
import physics_bowling_ball_pool_drop as physics  # noqa: E402


BASELINE_PHYSICS = dict(physics.BASELINE_PHYSICS)

OBJECTS = {
    "ball": {"zh": "落水的保龄球", "en": "the falling bowling ball"},
    "water": {"zh": "水池中的液体", "en": "the liquid in the pool"},
}

PROPERTIES = {
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "density": dsl.PropertySpec("scalar", "kg/m^3", "密度", "density"),
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

SIM_BINDINGS = {
    ("ball", "mass"): dsl.SimBinding("ball_mass"),
    ("water", "density"): dsl.SimBinding("liquid_density"),
    ("water", "viscosity"): dsl.SimBinding("liquid_kinematic_viscosity"),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings={'ball': dsl.DeleteBinding('ball_present', 0), 'water': dsl.DeleteBinding('water_present', 0)},
    baseline_physics=BASELINE_PHYSICS,
    total_frames=physics.FRAMES,
)
