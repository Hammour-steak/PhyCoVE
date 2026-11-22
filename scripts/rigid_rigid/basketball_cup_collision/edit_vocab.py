"""Independent physical and gravity edits."""
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
# Imported through the same alias path the simulate/build/render scripts use,
# so the vocabulary and the validator read one shared BASELINE_PHYSICS.
from scene_config import BASELINE_PHYSICS,OPTIONAL_PHYSICS,TOTAL_FRAMES

VOCAB = dsl.Vocabulary(
    objects={'basketball': {'zh': '篮球', 'en': 'the basketball'},
             'bottle': {'zh': '水壶', 'en': 'the bottle'},
             'world': {'zh': '场景', 'en': 'the world'}},
    properties={'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
                'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '出手速度', 'throw speed', initial_condition=True),
                'gravity': dsl.PropertySpec('scalar', 'm/s^2', '重力加速度', 'gravitational acceleration')},
    sim_bindings={('basketball', 'mass'): dsl.SimBinding('ball_mass'),
                  ('basketball', 'initial_velocity'): dsl.SimBinding('initial_velocity'),
                  ('bottle', 'mass'): dsl.SimBinding('bottle_mass'),
                  ('world', 'gravity'): dsl.SimBinding('gravity')},
    delete_bindings={'basketball': dsl.DeleteBinding('ball_presence', 0, 0),
                     'bottle': dsl.DeleteBinding('bottle_presence', 0, 0)},
    baseline_physics={**BASELINE_PHYSICS, **OPTIONAL_PHYSICS}, total_frames=TOTAL_FRAMES)

# First contact lands at 0.22 s (frame 6.3). Frame 8 sits just after it, with
# the ball and bottle separating and the bottle 65 deg over: from there the 5x
# gravity is what finishes the topple, so the bottle is flat on the desk by
# frame 9 instead of frame 13. Applied any later the bottle is already past
# 80 deg and the edit has nothing left to act on.
EDIT_CASES = [
    ('edit_fast_ball', 'SET basketball.initial_velocity TIMES 3'),
    ('edit_heavy_bottle', 'SET bottle.mass TIMES 10'),
    ('edit_heavy_ball', 'SET basketball.mass TIMES 5'),
    ('edit_heavy_gravity_after_impact', 'SET world.gravity TIMES 5 AT FRAME 8'),
    ('edit_delete_bottle', 'DELETE bottle'),
    ('edit_delete_basketball', 'DELETE basketball'),
]
