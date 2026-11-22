"""Explicit spatial additions plus independent physical and deletion edits."""
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
from scene_config import BASELINE_PHYSICS

# The suite's videos are 4 s at 24 fps; the vocabulary needs the frame count
# to accept AT FRAME edits.
TOTAL_FRAMES = 96

# Frame of the timed gravity edit: the baseline throw smashes the shower
# glass at 0.498 s (frame 13, measured from the baseline physics run), so the
# clip shows the glass impact, then the heavier drop into the south wall.
GRAVITY_EDIT_FRAME = 13

VOCAB = dsl.Vocabulary(
    objects={'tennis_ball': {'zh': '网球', 'en': 'the tennis ball'},
             'stools': {'zh': '所有木凳', 'en': 'the wooden stools'},
             'stool_a': {'zh': '淋浴区木凳', 'en': 'the shower-side wooden stool'},
             'stool_b': {'zh': '中部木凳', 'en': 'the mid-floor wooden stool'},
             'toilet': {'zh': '马桶', 'en': 'the toilet'},
             'glass_door': {'zh': '淋浴玻璃门', 'en': 'the glass shower door'},
             'world': {'zh': '整个场景', 'en': 'the whole scene'}},
    properties={'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
                'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '初速度', 'initial speed', initial_condition=True),
                'aim_shift': dsl.PropertySpec('scalar', 'm', '瞄准横移', 'aim shift'),
                'gravity': dsl.PropertySpec('scalar', 'm/s²', '重力加速度', 'gravity'),
                'restitution': dsl.PropertySpec('scalar', '', '恢复系数', 'restitution')},
    sim_bindings={('tennis_ball', 'mass'): dsl.SimBinding('ball_mass'),
                  ('tennis_ball', 'initial_velocity'): dsl.SimBinding('initial_velocity'),
                  ('tennis_ball', 'aim_shift'): dsl.SimBinding('aim_shift'),
                  ('stools', 'mass'): dsl.SimBinding('stool_mass'),
                  ('world', 'gravity'): dsl.SimBinding('gravity_z'),
                  ('world', 'restitution'): dsl.CompoundBinding(
                      components=(dsl.SimBinding('ball_restitution'),
                                  dsl.SimBinding('stool_restitution'),
                                  dsl.SimBinding('fixture_restitution')))},
    delete_bindings={'stool_a': dsl.DeleteBinding('stool_presence', 0, 0),
                     'stool_b': dsl.DeleteBinding('stool_presence', 1, 0)},
    baseline_physics=BASELINE_PHYSICS, total_frames=TOTAL_FRAMES)

# Four edits, one per physical axis the scene can carry without touching the
# set dressing: launch speed, aim, restitution, and a timed gravity change.
#
# Speed is the *slow* direction (x0.5). Speeding up past x1.30 sends the ball
# past the camera plane and the renderer refuses the whole case; see README.
EDIT_CASES = [
    ('edit_slow_ball', 'SET tennis_ball.initial_velocity TIMES 0.5'),
    ('edit_aim_south', 'SET tennis_ball.aim_shift TO 0.2'),
    ('edit_aim_north', 'SET tennis_ball.aim_shift TO -1.05'),
    ('edit_bouncier_bathroom', 'SET world.restitution TIMES 1.5'),
    ('edit_heavy_gravity_after_impact', 'SET world.gravity TIMES 3 AT FRAME %d' % GRAVITY_EDIT_FRAME),
]
