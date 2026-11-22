"""The edit vocabulary for this scene, on top of the project's shared PCVE DSL."""
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


# What a viewer of the clip may change, where each change lands in the
# simulator's own parameters, and the edits the suite ships. Everything
# downstream (prompts, scenario overrides, physics_diff) is generated from this
# declaration by the shared DSL.
import json
from dataclasses import dataclass

import pcve_edit_dsl as dsl
from scene_config import BASELINE_METRICS_PATH, OPTIONAL_PHYSICS, load_scenario

BASELINE_PHYSICS = load_scenario()['physics']
TOTAL_FRAMES = round(BASELINE_PHYSICS['fps'] * BASELINE_PHYSICS['duration_sec'])

# "All the objects get bouncier" is one property to a viewer even though the
# simulator keeps one coefficient per body. The compound binding scales them
# together, and the first one is what the DSL quotes the value as.
RESTITUTION_PARTS = ('ball_restitution', 'board_restitution', 'rim_restitution',
                     'floor_restitution', 'goal_base_restitution')
# A coefficient cannot pass 1.0, so the shipped factor is whatever fits under
# that ceiling with room for the solver's own tolerance.
BOUNCE_FACTOR = round(min(1.5, .97 / max(BASELINE_PHYSICS[k] for k in RESTITUTION_PARTS)), 2)
GRAVITY_TIMES = 3.0
GRAVITY_BASE = BASELINE_PHYSICS['gravity_z']
GRAVITY_TO = round(GRAVITY_BASE * GRAVITY_TIMES, 3)

# The bank shot is read off the baseline run rather than recomputed here: this
# module is imported by tools that have no pybullet, and a number that only
# shifts when the baseline is re-audited belongs in the audit's own output.
_RECORDED = {}
if BASELINE_METRICS_PATH.is_file():
    _RECORDED = json.loads(BASELINE_METRICS_PATH.read_text(encoding='utf-8'))
BOARD_FRAME = int(_RECORDED.get('board_impact_frame', 14))
# One frame after the board, so the impact itself is still the source video's.
GRAVITY_FRAME = min(TOTAL_FRAMES, BOARD_FRAME + 1)

OBJECTS = {
    'ball': {'zh': '篮球', 'en': 'the basketball'},
    'backboard': {'zh': '篮板和篮筐', 'en': 'the backboard and rim'},
    'world': {'zh': '场景', 'en': 'the scene'},
}

PROPERTIES = {
    'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '初始速度大小',
                                         'initial speed', initial_condition=True),
    'aim_x': dsl.PropertySpec('scalar', 'm', '瞄准点的横向位置', 'aim point across the board'),
    'aim_z': dsl.PropertySpec('scalar', 'm', '瞄准点离地高度', 'aim point height'),
    'restitution': dsl.PropertySpec('scalar', '', '恢复系数', 'restitution'),
    'gravity': dsl.PropertySpec('scalar', 'm/s²', '重力加速度', 'gravity'),
}

SIM_BINDINGS = {
    ('ball', 'initial_velocity'): dsl.SimBinding('ball_initial_speed'),
    # The two aim coordinates are what a thrower actually chooses: which panel
    # of the board to hit, and how high up it. Keeping them separate means an
    # edit can move the bank point sideways without also changing the arc.
    ('ball', 'aim_x'): dsl.SimBinding('ball_aim_x'),
    ('ball', 'aim_z'): dsl.SimBinding('ball_aim_z'),
    ('world', 'restitution'): dsl.CompoundBinding(
        tuple(dsl.SimBinding(key) for key in RESTITUTION_PARTS)),
    ('world', 'gravity'): dsl.SimBinding('gravity_z'),
}

# This scene has no ADD edits: the only bodies a viewer may move are the ball and
# the environment's coefficients, so there are no geometry anchors to declare.
VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES,
                       sim_bindings=SIM_BINDINGS,
                       delete_bindings={'backboard': dsl.DeleteBinding('board_presence', 0, 0)},
                       baseline_physics={**BASELINE_PHYSICS, **OPTIONAL_PHYSICS}, total_frames=TOTAL_FRAMES)

FAST = 2 * BASELINE_PHYSICS['ball_initial_speed']


@dataclass(frozen=True)
class EditCase:
    """One instruction, plus the outcome a viewer is meant to see."""
    case_id: str
    dsl: str
    summary: str


EDIT_CASES = (
    EditCase('edit_fast_ball', 'SET ball.initial_velocity TIMES 2',
             f'出手速度由 {BASELINE_PHYSICS["ball_initial_speed"]:g} m/s 加倍到 {FAST:g} m/s，'
             f'出手点与瞄准点不动：飞行时间缩短，第 6 帧就撞板（原片第 {BOARD_FRAME} 帧），'
             f'撞板速度与反弹速度同时翻倍，球从筐上方掠过、一次也没碰到筐（筐接触 0 次），'
             f'一路飞到场地右侧边线附近才落地（终点 x=6.34 m、y=-0.54 m），'
             f'绕圈与落筐整段消失。'),
    EditCase('edit_aim_high', 'SET ball.aim_z TO 3.14',
             f'砸板点从离地 {BASELINE_PHYSICS["ball_aim_z"]:.2f} m 抬到 3.14 m（接近篮板上沿）：'
             f'回弹的弧线更平、进筐角度更陡，第 21 帧触筐、只绕了 0.64 周'
             f'（原片 1.71 周）就在第 24 帧落筐，比原片早 16 帧；'
             f'球穿了筐继续飞，第 39 帧落在板后的地面（y=6.86 m），弹起来正好撞在'
             f'篮球架配重箱的斜面上（第 53–57 帧，箱面 y=7.5 m、高 0.35 m），'
             f'顺着箱面滑回来，最后停在箱体前方 x=+0.11 m、y=6.71 m。'),
    EditCase('edit_aim_left', 'SET ball.aim_x TO -0.42',
             f'砸板点从横向 {BASELINE_PHYSICS["ball_aim_x"]:+.2f} m 移到 −0.42 m（左移 0.12 m，'
             f'靠近板面左侧）：反弹回筐的入射角变浅，第 19 帧球撞在筐的**左前侧筐管**上而不是'
             f'落进筐口，筐把球顶回场地——球只碰筐 1 次、绕圈 0 周、全程没进筐，'
             f'第 41 帧就落在篮下 1 m 处的场内（y=5.04 m，原片停在配重箱前的 y=6.93 m，近了 1.9 m），'
             f'之后在地上弹了几下停在场内。原片那种"撞板→绕筐→落筐"在这里变成了"撞板→打铁→弹回"。'),
    EditCase('edit_bouncier', f'SET world.restitution TIMES {BOUNCE_FACTOR:g}',
             f'所有物体的恢复系数乘 {BOUNCE_FACTOR:g}（篮球 '
             f'{BASELINE_PHYSICS["ball_restitution"]:g}→'
             f'{round(BASELINE_PHYSICS["ball_restitution"] * BOUNCE_FACTOR, 2):g}、篮板 '
             f'{BASELINE_PHYSICS["board_restitution"]:g}→'
             f'{round(BASELINE_PHYSICS["board_restitution"] * BOUNCE_FACTOR, 2):g}、筐 '
             f'{BASELINE_PHYSICS["rim_restitution"]:g}→'
             f'{round(BASELINE_PHYSICS["rim_restitution"] * BOUNCE_FACTOR, 2):g}、'
             f'地面 {BASELINE_PHYSICS["floor_restitution"]:g}→'
             f'{round(BASELINE_PHYSICS["floor_restitution"] * BOUNCE_FACTOR, 2):g}）：'
             f'撞板后反弹更陡，球从筐上方越过、一次也没碰到筐；第 33 帧首次触地，'
             f'之后在第 62、87 帧再触地，一次比一次弹得低（两次弹起的球心最高点 2.07 m → 1.48 m，'
             f'触地间隔 29 帧 → 25 帧），但仍弹得很高，到第 96 帧（片尾）球还在 1.09 m 高的空中，'
             f'已经退到罚球线外（x=+1.91 m、y=+0.60 m），与"落筐"完全无关了。'),
    EditCase('edit_gravity_midway',
             f'SET world.gravity TIMES {GRAVITY_TIMES:g} AT FRAME {GRAVITY_FRAME}',
             f'在第 {GRAVITY_FRAME} 帧（第一次撞板之后一帧）把重力加速度改为原来的 '
             f'{GRAVITY_TIMES:g} 倍（{GRAVITY_BASE:g}→{GRAVITY_TO:g} m/s²）：'
             f'前 {GRAVITY_FRAME - 1} 帧与原片逐位相同，之后球被"加重"，'
             f'回弹弧线下坠得更快，进筐时只剩 0.26 周（原片 1.71 周）、'
             f'第 21 帧就落筐（原片第 40 帧）、第 28 帧落地，'
             f'筐内绕圈几乎被压没了。'),
    EditCase('edit_delete_backboard', 'DELETE backboard',
             '从第 1 帧起把篮板和篮筐移出场景，其余条件与原片相同。'),
)

DESCRIPTION = {
    'vague': {'zh': '篮球以一定角度砸向篮板，弹进篮筐后沿筐内沿转了几周，最后从筐中落下。',
              'en': 'A basketball is thrown at an angle into the backboard; it banks off the '
                    'board into the rim, circles the inside of the rim a few times and drops '
                    'through the ring.'},
    'quantitative': {
        'zh': f'半径 {BASELINE_PHYSICS["ball_radius"]:g} m、质量 {BASELINE_PHYSICS["ball_mass"]:g} kg 的'
              f'篮球以 {BASELINE_PHYSICS["ball_initial_speed"]:g} m/s 出手，瞄向篮板'
              f'（横向 {BASELINE_PHYSICS["ball_aim_x"]:+.2f} m、离地 '
              f'{BASELINE_PHYSICS["ball_aim_z"]:.2f} m），第 {BOARD_FRAME} 帧撞板反弹进筐；'
              f'恢复系数 篮球 {BASELINE_PHYSICS["ball_restitution"]:g} / 篮板 '
              f'{BASELINE_PHYSICS["board_restitution"]:g} / 筐 '
              f'{BASELINE_PHYSICS["rim_restitution"]:g}。',
        'en': f'A {BASELINE_PHYSICS["ball_mass"]:g} kg basketball of radius '
              f'{BASELINE_PHYSICS["ball_radius"]:g} m leaves the hand at '
              f'{BASELINE_PHYSICS["ball_initial_speed"]:g} m/s aimed at the backboard '
              f'({BASELINE_PHYSICS["ball_aim_x"]:+.2f} m across, '
              f'{BASELINE_PHYSICS["ball_aim_z"]:.2f} m up), and banks in on frame '
              f'{BOARD_FRAME} with restitution {BASELINE_PHYSICS["ball_restitution"]:g} / '
              f'{BASELINE_PHYSICS["board_restitution"]:g} / '
              f'{BASELINE_PHYSICS["rim_restitution"]:g}.'},
}
