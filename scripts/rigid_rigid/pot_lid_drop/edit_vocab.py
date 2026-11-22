"""Edit vocabulary for the pot_lid_drop scene.

The editable things are the lid (mass, restitution and rolling friction), the
world's gravity, and one ADD: a ceramic bowl placed on the floor between two
display anchors. The pot, the counter and the kitchen are the set the lid
falls into, not props.

Restitution controls the rebound; friction controls the settling motion.
Measurements for the aligned full-mesh collision model are recorded in the
render validation file.

The baseline is read from ``scenario.json`` rather than copied here. A scene
whose vocabulary and scenario disagree produces prompts that describe a video
nobody rendered, and that is exactly the bug this avoids: change the scene's
physics and the DSL, the prompts and the diffs follow.
"""
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

from pathlib import Path

HERE = Path(__file__).resolve().parent
import pcve_edit_dsl as dsl  # noqa: E402
import scene_config  # noqa: E402


SCENARIO = scene_config.load_scenario()
BASELINE_PHYSICS = SCENARIO['physics']


OBJECTS = {
    'lid': {'zh': '锅盖', 'en': 'the pot lid'},
    'world': {'zh': '世界（重力场）', 'en': 'the world'},
    'bowl': {'zh': '碗', 'en': 'a bowl'},
    # Display-only anchors for the bowl ADD (no body, no physics key of their
    # own): two floor points one lid-width (0.24 m) either side of where the
    # baseline lid comes to rest, along the camera's left-right axis, so both
    # endpoints can be found by watching the source video.
    'rest_left': {'zh': '原视频中锅盖停稳处往画面左边一个锅盖宽的地面',
                  'en': 'the floor one lid-width to the left of where the lid comes to rest in the source video'},
    'rest_right': {'zh': '原视频中锅盖停稳处往画面右边一个锅盖宽的地面',
                   'en': 'the floor one lid-width to the right of where the lid comes to rest in the source video'},
}
# Deliberately NOT editable: the pot, the counter and the floor. They are the
# kitchen the lid lands in, not props.


PROPERTIES = {
    'mass':             dsl.PropertySpec('scalar', 'kg',    '质量',         'mass'),
    'rolling_friction': dsl.PropertySpec('scalar', '',      '滚动摩擦因数', 'rolling friction coefficient'),
    'restitution':      dsl.PropertySpec('scalar', '',      '弹性因数',     'restitution'),
    'gravity':          dsl.PropertySpec('scalar', 'm/s²',  '重力加速度',   'gravity magnitude'),
}

SIM_BINDINGS = {
    ('lid', 'mass'):             dsl.SimBinding('lid_mass'),
    ('lid', 'rolling_friction'): dsl.SimBinding('lid_rolling_friction'),
    ('lid', 'restitution'):      dsl.SimBinding('lid_restitution'),
    # Gravity is a world-level knob bound straight onto the scenario's
    # gravity_z physics key, the same way ball_block_building binds
    # world.gravity -> gravity_strength.
    ('world', 'gravity'):        dsl.SimBinding('gravity_z'),
}


DELETE_BINDINGS: dict[str, dsl.DeleteBinding] = {}


# 4.0 s at 24 fps, which is what build_pcve_pot_lid_drop.py renders. An "AT
# FRAME n" edit is bounded by this, and the vague prompt reads n against it to
# say whether the edit lands early, midway or late in the clip.
TOTAL_FRAMES = 96


# The bowl ADD's anchor set. The bowl's footprint centre (bowl_start_position,
# the base of the bowl on the floor) is the baseline lid's measured resting
# point P: the source lid settles with its centre at (0.1736, 0.2432), 0.5 mm
# from P. The DSL only places an ADD strictly between two endpoints, so the
# endpoints are two display anchors on the floor, one lid-width either side of
# P along the camera's left-right axis (the camera's x axis projected on the
# floor, (0.9062, 0.4229)); their MIDPOINT resolves back to exactly P. Both
# endpoints are floor points a viewer can find in the source video.
_BOWL_LANDING = [0.174, 0.243, 0.0]
_LID_WIDTH_M = 0.24
_FRAME_RIGHT_XY = (0.9062, 0.4229)
_REST_OFFSET = [round(_LID_WIDTH_M * c, 4) for c in _FRAME_RIGHT_XY]  # (0.2175, 0.1015)
_REST_LEFT_ANCHOR = [round(_BOWL_LANDING[0] - _REST_OFFSET[0], 4), round(_BOWL_LANDING[1] - _REST_OFFSET[1], 4), 0.0]
_REST_RIGHT_ANCHOR = [round(_BOWL_LANDING[0] + _REST_OFFSET[0], 4), round(_BOWL_LANDING[1] + _REST_OFFSET[1], 4), 0.0]
# The bowl reuses kitchen_tableware_collision's ceramic rice bowl: a shared
# lathe cross-section (closed solid, foot -> lip -> inner floor) whose convex
# hull is the collision body in that scene. The simulator builds the hull from
# the same PROFILE scaled to bowl_radius_m, and the renderer lathes the same
# PROFILE for the visible mesh, so visual and collision shapes cannot drift
# apart. The bowl has mass -- the falling lid genuinely knocks it over, which
# is the visible proof of contact.
BOWL_PROFILE_BASE_RADIUS_M = 0.085
BOWL_COM_HEIGHT_M = 0.018
BOWL_PROFILE_TOP_Z_M = 0.042
BOWL_PROFILE = ((0.,.004),(.030,.004),(.037,.000),(.044,.000),(.046,.003),(.047,.008),
                (.055,.012),(.067,.020),(.078,.030),(.0835,.036),(.085,.039),
                (.0845,.041),(.0825,.042),(.0805,.040),(.077,.034),(.066,.025),
                (.054,.019),(.043,.014),(.030,.011),(0.,.011))
_BOWL_DEFAULTS = (
    ('bowl_mass_kg', 0.08),
    ('bowl_radius_m', 0.11),
    ('bowl_restitution', 0.2),
    ('bowl_friction', 0.4),
)

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics={
        **BASELINE_PHYSICS,
        'bowl_presence': [0],
        'bowl_start_position': list(_BOWL_LANDING),
        'rest_left_anchor': list(_REST_LEFT_ANCHOR),
        'rest_right_anchor': list(_REST_RIGHT_ANCHOR),
        'display_anchor_radius_m': 0.001,
        'lid_start_position': [0.0, 0.0, 1.16],
        **dict(_BOWL_DEFAULTS),
    },
    total_frames=TOTAL_FRAMES,
    geometry={
        'lid': dsl.GeometryAnchor('lid_start_position', 'lid_radius_m'),
        'rest_left': dsl.GeometryAnchor('rest_left_anchor', 'display_anchor_radius_m'),
        'rest_right': dsl.GeometryAnchor('rest_right_anchor', 'display_anchor_radius_m'),
        'bowl': dsl.GeometryAnchor('bowl_start_position', 'bowl_radius_m'),
    },
    add_bindings={'bowl': dsl.AddBinding(
        presence_key='bowl_presence', presence_index=0,
        location_key='bowl_start_position', value_when_present=1,
        defaults=_BOWL_DEFAULTS)},
)


# Exactly five single-variable edits. Four hold from frame 1; the last one
# lands partway through -- the baseline lid first touches down during frame
# 13 and its rebound carries it up through frame 14, so at the top of frame
# 14 the schedule switches gravity off inside the running simulation: the
# free fall, the impact and the start of the rebound (frames 1-13) are the
# baseline clip bit for bit, and from there the lid coasts upward instead of
# ever coming back down.
EDIT_CASES = [
    ('edit_light_gravity', 'SET world.gravity TIMES 0.3'),
    ('edit_add_bowl_at_landing', 'ADD bowl BETWEEN rest_left AND rest_right AT MIDPOINT'),
    ('edit_slick_rim', 'SET lid.rolling_friction TIMES 0.1'),
    ('edit_bouncy_lid', 'SET lid.restitution TO 0.45'),
    ('edit_zero_gravity_timed', 'SET world.gravity TO 0 AT FRAME 14'),
]
