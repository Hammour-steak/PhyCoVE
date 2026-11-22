"""Four independent edits: two masses, one deletion, one timed friction."""
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
    'driver_can': {'zh': '深蓝色圆形罐头', 'en': 'the round dark blue tin'},
    'receiver_can': {'zh': '银色长方形罐头',
                    'en': 'the rectangular silver tin'},
    'pair': {'zh': '两只罐头之间的碰撞', 'en': 'the collision between the two tins'},
    'table': {'zh': '餐桌桌面', 'en': 'the dining table'},
}
PROPERTIES = {
    'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
    'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '沿桌面 X 轴的初速度',
                                         'initial velocity along the tabletop X axis', initial_condition=True),
    'restitution': dsl.PropertySpec('scalar', '', '碰撞恢复系数', 'coefficient of restitution'),
    # Friction is per body because Bullet keeps one coefficient on each body:
    # "the struck tin stops being rough" is a write to that tin, not to a pair.
    'friction': dsl.PropertySpec('scalar', '', '滑动摩擦因数', 'sliding friction coefficient'),
}
SIM_BINDINGS = {
    ('driver_can', 'mass'): dsl.SimBinding('driver_mass'),
    ('receiver_can', 'mass'): dsl.SimBinding('receiver_mass'),
    ('driver_can', 'initial_velocity'): dsl.SimBinding('initial_velocity'),
    ('receiver_can', 'initial_velocity'): dsl.SimBinding('receiver_initial_velocity'),
    ('driver_can', 'friction'): dsl.SimBinding('driver_friction'),
    ('receiver_can', 'friction'): dsl.SimBinding('receiver_friction'),
    ('table', 'friction'): dsl.SimBinding('table_friction'),
    ('pair', 'restitution'): dsl.SimBinding('restitution'),
}
DELETE_BINDINGS = {'receiver_can': dsl.DeleteBinding('receiver_active', index=0, value_when_removed=0),
                   # The sliding tin's presence switch is only written by this
                   # DELETE (scene_config.OPTIONAL_PHYSICS); its baseline is present.
                   'driver_can': dsl.DeleteBinding('driver_active', index=0, value_when_removed=0)}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS, baseline_physics={**BASELINE_PHYSICS, **OPTIONAL_PHYSICS},
    total_frames=TOTAL_FRAMES)

# Four cases, one control each.  The numbers quoted in the docstrings and in the
# README are read back from simulation_metrics.json of the runs that produced
# the clips, not predicted.
EDIT_CASES = [
    # 0.20 -> 1.00 kg: the struck tin slides 0.337 m instead of 0.155 and
    # spins -251 deg instead of +79 -- five times the mass carries far more
    # momentum through the same off-centre contact.
    ('edit_heavy_driver', 'SET driver_can.mass TIMES 5'),
    # 0.125 -> 1.25 kg: the struck tin barely stirs -- 1 mm and under a degree.
    ('edit_heavy_receiver', 'SET receiver_can.mass TIMES 10'),
    # The struck (receiver) tin is removed outright: the driver slides straight
    # through the empty spot and stops on the table, never touching
    # anything, so the whole scene becomes a pure sliding pass with no collision.
    ('edit_remove_receiver', 'DELETE receiver_can'),
    # The struck tin's friction drops to a quarter at frame 11, 0.13 s after
    # the hit: instead of stopping at 0.70 s it glides until 1.50 s and covers
    # 0.364 m instead of 0.155.  Zero friction is not usable here -- the tin
    # runs off the cloth and topples on the floor.
    ('edit_receiver_friction_drop', 'SET receiver_can.friction TIMES 0.25 AT FRAME 11'),
    ('edit_remove_driver_can', 'DELETE driver_can'),
]

DESCRIPTION = {
    'vague': {'zh': '小酒馆的餐桌上，一只深蓝色圆形罐头滑向一只平放的银色长方形罐头，'
                    '撞在它朝向自己的长边上、偏离中点，把它撞得滑出去并转了一个角度。',
              'en': 'On a bistro table, a round dark blue tin slides into a flat rectangular silver tin, striking the long '
                    'face it presents off-centre and sending it sliding away with a twist.'},
    'quantitative': {'zh': (f'深蓝色圆形罐头重 {BASELINE_PHYSICS["driver_mass"]:g} kg、直径 8.0 cm、高 2.71 cm，'
                            f'平放着以 {BASELINE_PHYSICS["initial_velocity"]:g} m/s 滑向重 '
                            f'{BASELINE_PHYSICS["receiver_mass"]:g} kg 的银色长方形罐头（12.9 × 7.5 × 3.6 cm）；'
                            f'撞击点沿桌面 Y 轴偏离银色长方形罐头中心 2.2 cm，碰撞恢复系数 '
                            f'{BASELINE_PHYSICS["restitution"]:g}；罐头与桌布的摩擦因数 '
                            f'{BASELINE_PHYSICS["receiver_friction"]:g}，桌面取 1.0。'),
                      'en': (f'The round dark blue tin weighs {BASELINE_PHYSICS["driver_mass"]:g} kg and measures 8.0 cm across '
                             f'by 2.71 cm tall; it slides at {BASELINE_PHYSICS["initial_velocity"]:g} m/s into a '
                             f'{BASELINE_PHYSICS["receiver_mass"]:g} kg rectangular silver tin measuring 12.9 x 7.5 x 3.6 cm. '
                             f'The contact is 2.2 cm off the silver tin centre, the pair restitution is '
                             f'{BASELINE_PHYSICS["restitution"]:g}, and the tin-on-cloth friction is '
                             f'{BASELINE_PHYSICS["receiver_friction"]:g} against a table value of 1.0.')}}
