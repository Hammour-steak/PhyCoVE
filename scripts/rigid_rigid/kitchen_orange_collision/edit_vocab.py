"""Exactly five independent edits: two masses, a launch speed, a rear queue, a mid-run surge."""
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

OBJECTS = {'driver_orange': {'zh': '完整的橙子', 'en': 'the whole orange'},
           'cut_orange': {'zh': '切开的橙子', 'en': 'the sliced orange'},
           'pair': {'zh': '两只橙子之间的碰撞', 'en': 'the collision between the two oranges'},
           # Bullet keeps one friction value per body, so the two contacts are
           # declared as the two surfaces that meet in them.
           'orange': {'zh': '橙子表皮', 'en': 'the orange skin'},
           'table': {'zh': '餐桌桌布', 'en': 'the table cloth'}}
PROPERTIES = {'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
              'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '沿桌面 X 轴的初速度',
                                                   'initial velocity along the tabletop X axis',
                                                   initial_condition=True),
              # The rolling orange's speed as a live quantity rather than a launch
              # condition: same physics key, but the simulator may write it into a
              # body that is already rolling, which is what an AT FRAME speed edit
              # needs.
              'speed': dsl.PropertySpec('scalar', 'm/s', '滚动速度', 'rolling speed'),
              'restitution': dsl.PropertySpec('scalar', '', '碰撞恢复系数', 'coefficient of restitution'),
              'friction': dsl.PropertySpec('scalar', '', '滑动摩擦因数', 'sliding friction coefficient'),
              # A count, not a continuous knob: 0 is the source case, 2 queues
              # two more whole oranges tight behind the sliced one and turns the
              # scene into a four-body transfer. Its baseline is exactly 0, so the
              # edit is spelled TO 2 rather than TIMES anything.
              'rear_oranges': dsl.PropertySpec('scalar', '', '从动橙子后方紧挨着的整只橙子数量',
                                               'whole oranges queued behind the struck one')}
SIM_BINDINGS = {('driver_orange', 'mass'): dsl.SimBinding('driver_mass'),
                ('cut_orange', 'mass'): dsl.SimBinding('cut_mass'),
                ('driver_orange', 'initial_velocity'): dsl.SimBinding('initial_velocity'),
                ('driver_orange', 'speed'): dsl.SimBinding('initial_velocity'),
                ('pair', 'restitution'): dsl.SimBinding('restitution'),
                ('orange', 'friction'): dsl.SimBinding('orange_friction'),
                ('table', 'friction'): dsl.SimBinding('table_friction'),
                ('cut_orange', 'rear_oranges'): dsl.SimBinding('rear_oranges')}
# The two presence switches are only written by these DELETEs
# (scene_config.OPTIONAL_PHYSICS); their baseline is present.
DELETE_BINDINGS = {'driver_orange': dsl.DeleteBinding('driver_active', index=0, value_when_removed=0),
                   'cut_orange': dsl.DeleteBinding('cut_active', index=0, value_when_removed=0)}
VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS,
                       delete_bindings=DELETE_BINDINGS, baseline_physics={**BASELINE_PHYSICS, **OPTIONAL_PHYSICS},
                       total_frames=TOTAL_FRAMES)

# Exactly five cases, one per row, each moving one declared control. The listed
# outcome is the sliced orange's travel along the table, measured with this
# scene's simulator (24 fps, 4 s): the source knocks it 0.147 m while rolling 173 deg, the
# driving orange covers 0.913 m of its own, and it arrives with a pre-impact slip
# ratio of 1e-15 (it rolls, it does not skid). First contact is frame 18.
#   * 5 x driver mass   : a 0.85 kg orange arrives with five times the momentum.
#   * 10 x sliced mass  : a 1.4 kg sliced orange, hit by the same orange.
#   * 3 x launch speed  : 2.7 m/s off the mark; the clip reaches contact sooner
#                         and everything runs further.
#   * rear queue TO 2   : two whole oranges tight behind the sliced one, so the
#                         impact is carried through a chain of four bodies.
#   * 8 x speed at 10   : the surge lands on the frame where the driving orange
#                         has covered half of the 0.60 m run-up, so the clip is
#                         the source up to frame 9 and re-solved after it.
EDIT_CASES = [('edit_heavy_driver', 'SET driver_orange.mass TIMES 5'),
              ('edit_heavy_cut', 'SET cut_orange.mass TIMES 10'),
              ('edit_fast_driver', 'SET driver_orange.initial_velocity TIMES 3'),
              ('edit_rear_queue', 'SET cut_orange.rear_oranges TO 2'),
              ('edit_midframe_surge', 'SET driver_orange.speed TIMES 8 AT FRAME 10'),
              ('edit_delete_cut_orange', 'DELETE cut_orange'),
              ('edit_delete_driver_orange', 'DELETE driver_orange')]

DESCRIPTION = {
    'vague': {'zh': '厨房餐桌上，一只完整的橙子滚向一只切掉顶部的橙子，把它撞得滚开一段距离。',
              'en': 'On a kitchen dining table, a whole orange rolls into a sliced orange and knocks it away.'},
    'quantitative': {'zh': (f'完整橙子 {BASELINE_PHYSICS["driver_mass"]:g} kg、切开的橙子 '
                            f'{BASELINE_PHYSICS["cut_mass"]:g} kg，直径均 7.7 cm；'
                            f'完整橙子以 {BASELINE_PHYSICS["initial_velocity"]:g} m/s 沿桌面滚向切开的橙子，'
                            f'碰撞恢复系数 {BASELINE_PHYSICS["restitution"]:g}；'
                            f'橙皮摩擦因数 {BASELINE_PHYSICS["orange_friction"]:g}、桌布摩擦因数 '
                            f'{BASELINE_PHYSICS["table_friction"]:g}。'),
                     'en': (f'The whole orange weighs {BASELINE_PHYSICS["driver_mass"]:g} kg and the sliced one '
                            f'{BASELINE_PHYSICS["cut_mass"]:g} kg, both 7.7 cm across; the whole one rolls at '
                            f'{BASELINE_PHYSICS["initial_velocity"]:g} m/s into the sliced one with a pair '
                            f'restitution of {BASELINE_PHYSICS["restitution"]:g}; the orange skin and the cloth '
                            f'carry friction coefficients of {BASELINE_PHYSICS["orange_friction"]:g} and '
                            f'{BASELINE_PHYSICS["table_friction"]:g}.')}}
