"""The five edits: heavier bowl, stronger gravity, no tableware, bouncier kitchen, gravity off mid-run."""
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

OBJECTS = {'falling_bowl': {'zh': '吊柜里的白碗', 'en': 'the white cupboard bowl'},
           'tableware': {'zh': '灶台上的小白碗', 'en': 'the small white bowl on the hob'},
           'world': {'zh': '整个场景', 'en': 'the whole scene'}}

# "Elasticity" is spelled the way a physicist spells it: the coefficient of
# restitution. One property covers every pair of surfaces in the kitchen,
# because a viewer reads "everything bounces more" as one change, not four.
PROPERTIES = {'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
              'gravity': dsl.PropertySpec('scalar', 'm/s²', '重力加速度', 'gravity'),
              'restitution': dsl.PropertySpec('scalar', '', '恢复系数（物体的“弹性”）',
                                              'coefficient of restitution (how elastic every surface is)')}

SIM_BINDINGS = {('falling_bowl', 'mass'): dsl.SimBinding('falling_bowl_mass'),
                ('tableware', 'mass'): dsl.SimBinding('tableware_mass'),
                ('world', 'gravity'): dsl.SimBinding('gravity_z'),
                ('world', 'restitution'): dsl.CompoundBinding(
                    components=(dsl.SimBinding('falling_bowl_restitution'),
                                dsl.SimBinding('tableware_restitution'),
                                dsl.SimBinding('counter_restitution'),
                                dsl.SimBinding('cupboard_restitution')))}
DELETE_BINDINGS = {'tableware': dsl.DeleteBinding('tableware_active', index=0, value_when_removed=0),
                   'falling_bowl': dsl.DeleteBinding('falling_bowl_active', index=0, value_when_removed=0)}

# falling_bowl_active is an optional presence switch (absent = present, see scene_config.OPTIONAL_TOGGLE_KEYS);
# the vocabulary reads its baseline here so a DELETE of the falling bowl can be written.
VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS,
                       delete_bindings=DELETE_BINDINGS, baseline_physics={**BASELINE_PHYSICS, 'falling_bowl_active': [1]},
                       total_frames=TOTAL_FRAMES)

# The rim strikes the bowl on the cooktop at 0.596 s, which is frame 15.3 of 24
# fps. Cutting at the very next whole frame (16) looks right but is not: the
# impulse has barely been absorbed, both bodies are still climbing out of the
# contact, and once gravity is gone there is no normal load left to give either
# one friction -- the falling bowl keeps the whole 0.9 m/s the strike handed it
# and coasts 2.9 m into the far wall before the clip ends. Frame 19 (0.75 s) is
# two tenths of a second after contact, when the falling bowl is already
# tumbling clear at 0.75 m/s, 5 cm above the cooktop and never landing, and the
# bowl it hit is still sliding at 0.35 m/s. Both are then left to keep exactly
# the momentum the collision gave them for the remaining three seconds.
GRAVITY_CUT_FRAME = 19

EDIT_CASES = [
    ('edit_heavy_bowl', 'SET falling_bowl.mass TIMES 10'),
    ('edit_strong_gravity', 'SET world.gravity TIMES 3'),
    ('edit_remove_tableware', 'DELETE tableware'),
    ('edit_bouncier_kitchen', 'SET world.restitution TIMES 2'),
    ('edit_gravity_off_after_impact', 'SET world.gravity TIMES 0 AT FRAME %d' % GRAVITY_CUT_FRAME),
    ('edit_remove_falling_bowl', 'DELETE falling_bowl'),
]
