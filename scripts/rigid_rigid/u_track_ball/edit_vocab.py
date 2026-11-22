# PCVE_UNIFIED_ENTRY_BEGIN
# Scene-local modules live in this directory and its physics/, appearance/ and
# tools/ subdirectories; shared modules live in scripts/.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_BUNDLE_SCENE = _ScenePath(__file__).resolve().parent
_BUNDLE_SCRIPTS = _BUNDLE_SCENE.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _BUNDLE_SCENE.parents if (p / 'scripts').is_dir())
for _scene_sub in (_BUNDLE_SCRIPTS, _BUNDLE_SCENE, *(_BUNDLE_SCENE / _s for _s in ("physics", "appearance", "tools"))):
    if _scene_sub.is_dir() and str(_scene_sub) not in _scene_sys.path:
        _scene_sys.path.insert(1, str(_scene_sub))
# PCVE_UNIFIED_ENTRY_END

import pcve_edit_dsl as dsl
from scene_config import BASELINE_PHYSICS,OPTIONAL_PHYSICS

# DELETE box flips this presence mask; the timed form arrives as a schedule
# under timed_edits and is applied inside the simulator's frame loop.
# DELETE ball flips the optional ball_presence mask.

BASELINE=BASELINE_PHYSICS
VOCAB=dsl.Vocabulary(objects={'ball':{'zh':'木质球','en':'the wooden ball'},'box':{'zh':'桌面纸盒','en':'the cardboard box on the table'}},
    properties={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
                'initial_velocity':dsl.PropertySpec('scalar','m/s','沿轨道初速度','initial tangential speed'),
                'initial_position':dsl.PropertySpec('scalar','m','沿坡的初始释放位置','initial release position along the slope')},
    sim_bindings={('ball','mass'):dsl.SimBinding('ball_mass'),('ball','initial_velocity'):dsl.SimBinding('initial_speed'),('ball','initial_position'):dsl.SimBinding('initial_position')},
    delete_bindings={'box':dsl.DeleteBinding('box_presence',0,0),'ball':dsl.DeleteBinding('ball_presence',0,0)},baseline_physics={**BASELINE,**OPTIONAL_PHYSICS},total_frames=96)

# Baseline releases the ball from rest at the top of the drive branch. The two
# position edits exploit the energy budget: -0.70 m still clears the exit lip
# but arrives with much less momentum, while -0.45 m cannot climb out of the
# valley and the ball keeps rocking between the branches.
EDIT_CASES=[('edit_lower_release','SET ball.initial_position TO -0.7'),
    ('edit_shallow_release','SET ball.initial_position TO -0.45'),
    ('edit_fast_launch','SET ball.initial_velocity TO 1.8'),
    ('edit_heavy_ball','SET ball.mass TIMES 2.5'),
    ('edit_box_vanishes_before_impact','DELETE box AT FRAME 33'),
    ('edit_delete_ball','DELETE ball')]
