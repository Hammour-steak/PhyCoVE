"""The five edits: heavier clock, stronger gravity, no crate, bouncier room, gravity off mid-run."""
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
from scene_config import BASELINE_PHYSICS, OPTIONAL_PHYSICS, TOTAL_FRAMES

OBJECTS = {'clock': {'zh': '挂钟', 'en': 'the wall clock'},
           'crate': {'zh': '木箱', 'en': 'the pine crate'},
           'world': {'zh': '整个场景', 'en': 'the whole scene'}}

# "Elasticity" is spelled the way a physicist spells it: the coefficient of
# restitution. One property covers every pair of surfaces in the room, because
# a viewer reads "everything bounces more" as one change, not four.
PROPERTIES = {'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
              'gravity': dsl.PropertySpec('scalar', 'm/s²', '重力加速度', 'gravity'),
              'restitution': dsl.PropertySpec('scalar', '', '恢复系数（物体的“弹性”）',
                                              'coefficient of restitution (how elastic every surface is)')}

SIM_BINDINGS = {('clock', 'mass'): dsl.SimBinding('clock_mass'),
                ('crate', 'mass'): dsl.SimBinding('crate_mass'),
                ('world', 'gravity'): dsl.SimBinding('gravity_z'),
                ('world', 'restitution'): dsl.CompoundBinding(
                    components=(dsl.SimBinding('clock_restitution'), dsl.SimBinding('crate_restitution'),
                                dsl.SimBinding('floor_restitution'), dsl.SimBinding('fixture_restitution')))}
DELETE_BINDINGS = {'crate': dsl.DeleteBinding('crate_active', index=0, value_when_removed=0),
                   'clock': dsl.DeleteBinding('clock_active', index=0, value_when_removed=0)}

VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS,
                       delete_bindings=DELETE_BINDINGS, baseline_physics={**BASELINE_PHYSICS, **OPTIONAL_PHYSICS},
                       total_frames=TOTAL_FRAMES)

# The rim reaches the crate on frame 10 (0.375 s); gravity is switched off on
# frame 24 (0.958 s), a second after the impact, while the crate is tipping.
# Cutting this late is what makes the edit legible: both bodies are already in
# contact and already moving, so from frame 24 on they keep exactly the velocity
# they had and nothing else -- the clock ends up suspended 0.54 m above the floor
# and the crate stops 73 deg into a topple it can no longer finish. Cutting on
# frame 12 gives the same physics but the clock then slides straight at the
# camera and leaves the frame a second before the clip ends.
GRAVITY_CUT_FRAME = 24

EDIT_CASES = [
    ('edit_heavy_clock', 'SET clock.mass TIMES 10'),
    ('edit_strong_gravity', 'SET world.gravity TIMES 3'),
    ('edit_remove_crate', 'DELETE crate'),
    ('edit_bouncier_room', 'SET world.restitution TIMES 4'),
    ('edit_gravity_off_after_impact', 'SET world.gravity TIMES 0 AT FRAME %d' % GRAVITY_CUT_FRAME),
    ('edit_remove_clock', 'DELETE clock'),
]
