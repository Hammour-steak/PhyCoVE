"""Four edits: two mass changes and two deletions (one whole-clip, one timed)."""
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


OBJECTS = {
    'kettle': {'zh': '桌面上的水壶', 'en': 'the kettle on the desk'},
    'pen_holder': {'zh': '装着圆珠笔的笔筒', 'en': 'the pen cup holding the ballpoint'},
    'pen': {'zh': '笔筒里的圆珠笔', 'en': 'the ballpoint pen inside the pen cup'},
}
PROPERTIES = {
    'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
}
SIM_BINDINGS = {('kettle', 'mass'): dsl.SimBinding('kettle_mass'),
                ('pen_holder', 'mass'): dsl.SimBinding('pen_holder_mass'),
                ('pen', 'mass'): dsl.SimBinding('pen_mass')}
DELETE_BINDINGS = {'pen': dsl.DeleteBinding('pen_present', index=0, value_when_removed=0),
                   'pen_holder': dsl.DeleteBinding('pen_holder_present', index=0, value_when_removed=0),
                   # The bottle's presence switch is only written by this DELETE
                   # (scene_config.OPTIONAL_PHYSICS); its baseline is present.
                   'kettle': dsl.DeleteBinding('kettle_present', index=0, value_when_removed=0)}
VOCAB = dsl.Vocabulary(
    objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS, baseline_physics={**BASELINE_PHYSICS, **OPTIONAL_PHYSICS},
    total_frames=TOTAL_FRAMES)

# Four edits: two whole-clip mass changes, one whole-clip delete, and one
# delete that lands partway through the clip.
EDIT_CASES = [('edit_heavy_kettle', 'SET kettle.mass TIMES 5'),
              ('edit_heavy_pen_holder', 'SET pen_holder.mass TIMES 10'),
              ('edit_remove_pen', 'DELETE pen'),
              ('edit_remove_pen_holder', 'DELETE pen_holder AT FRAME 8'),
              ('edit_remove_kettle', 'DELETE kettle')]
