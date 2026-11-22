"""Four representative edits: spin, launch speed, bathtub deletion, timed friction."""
# PCVE_UNIFIED_ENTRY_BEGIN
# Scene-local modules live in this directory and its physics/, appearance/ and
# tools/ subdirectories; shared modules live in scripts/.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_BUNDLE_SCENE = _ScenePath(__file__).resolve().parent
_BUNDLE_SCRIPTS = _BUNDLE_SCENE.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _BUNDLE_SCENE.parents if (p / "assets").is_dir())
for _scene_sub in (_BUNDLE_SCRIPTS, _BUNDLE_SCENE, *(_BUNDLE_SCENE / _s for _s in ("physics", "appearance", "tools"))):
    if _scene_sub.is_dir() and str(_scene_sub) not in _scene_sys.path:
        _scene_sys.path.insert(1, str(_scene_sub))
# PCVE_UNIFIED_ENTRY_END

import pcve_edit_dsl as dsl
from scene_config import BASELINE_PHYSICS, TOTAL_FRAMES

OBJECTS = {'stool': {'zh': '木凳', 'en': 'the wooden stool'},
           'sink': {'zh': '洗手池', 'en': 'the washbasin cabinet'},
           'bathtub': {'zh': '浴缸', 'en': 'the marble bathtub'}}
PROPERTIES = {'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
              'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '平动初速度', 'launch speed'),
              'initial_angular_velocity': dsl.PropertySpec('scalar', 'rad/s', '初始角速度', 'initial angular velocity'),
              'friction': dsl.PropertySpec('scalar', '', '与地面的摩擦系数', 'friction against the floor')}
SIM_BINDINGS = {('stool', 'mass'): dsl.SimBinding('stool_mass'),
                ('stool', 'initial_velocity'): dsl.SimBinding('launch_speed'),
                ('stool', 'initial_angular_velocity'): dsl.SimBinding('launch_spin'),
                ('stool', 'friction'): dsl.SimBinding('stool_friction')}
DELETE_BINDINGS = {'bathtub': dsl.DeleteBinding('bathtub_active', index=0, value_when_removed=0)}
VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS,
                       delete_bindings=DELETE_BINDINGS,
                       baseline_physics=BASELINE_PHYSICS, total_frames=TOTAL_FRAMES)
# Four cases: three times the launch spin (13 rad/s at five times bounces
# upward off the sink and recreates a long floating drop), the bathtub
# removed outright, three times the launch speed, and a mid-run removal of ALL
# floor friction -- the airborne stool first touches the washbasin near
# frame 10, so frame 12 applies the edit just after impact and the stool keeps
# sliding without grip.
EDIT_CASES = [('edit_fast_spin', 'SET stool.initial_angular_velocity TIMES 3'),
              ('edit_remove_bathtub', 'DELETE bathtub'),
              ('edit_fast_throw', 'SET stool.initial_velocity TIMES 3'),
              ('edit_frictionless_floor_timed', 'SET stool.friction TIMES 0 AT FRAME 12')]
