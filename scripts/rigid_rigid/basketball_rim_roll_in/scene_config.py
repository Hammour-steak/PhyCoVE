"""Single source of truth for simulation, edit vocabulary and visual geometry."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import copy
import json
import math
from pathlib import Path
from scene_geometry import (BOARD_FACE_Y, RIM_Z, RIM_TUBE, GRAVITY,
                            fixed_constants)

SCENE_NAME = 'basketball_rim_roll_in'
ROOT = _PCVE_ROOT
HERE = _PCVE_SCENE_ROOT
SCENARIO_DIR = _pcve_asset('scenes') / SCENE_NAME
# What the baseline run actually did, written by the builder from the source
# run. The edit vocabulary quotes frame numbers out of it, and the builder runs
# where pybullet exists, so the vocabulary itself never has to start a simulation.
BASELINE_METRICS_PATH = SCENARIO_DIR / 'baseline_metrics.json'
MODELS = _pcve_asset('models')

# The court's own furniture, measured off the GLB. Kept next to the parameters
# the edits may move, because the two must agree: the ball is aimed at
# ``board_face_y`` and the board's collision box is built at the same y.
COURT = fixed_constants()

BASELINE_PHYSICS = {
    'fps': 24, 'duration_sec': 4.0, 'substeps_per_frame': 60, 'solver_iterations': 120,
    'gravity_z': GRAVITY,
    'board_face_y': BOARD_FACE_Y, 'rim_z': RIM_Z, 'rim_tube': RIM_TUBE,
    # Launch: release point, the point on the board it is aimed at, how hard.
    # The velocity is solved from these three, so an edit to the aim point
    # really is "throw at a different place" and an edit to the speed really is
    # "throw harder", not a reshuffled velocity vector.
    #
    # The decimals are deliberate and must not be tidied. A ball circling a rigid
    # rim is a chaotic phase: 2600 random bank shots produced six that circle a
    # turn and drop, and even a 0.3% nudge to the numbers below drops the ball
    # out of the ring. The seventeen digits are what makes the source run
    # reproducible. Measured, one rounding at a time: rounding the spin to 65.5
    # leaves the run alone (1.71 turns, through at frame 40), but rounding the aim
    # x/z to three decimals drops it to 0.67 turns and frame 23, and rounding the
    # speed to 6.357 drops it to 0.56 turns and frame 22. Edits are meant to leave
    # this trajectory, which is the point of the scene.
    'ball_release_location': [-1.4109697333214992, 4.3874928889031555, 2.118986435584994],
    'ball_aim_x': -0.29914972931499595, 'ball_aim_z': 3.0507626001542465, 'ball_arc': 'low',
    'ball_initial_speed': 6.357398983455729,
    'ball_spin': 65.46606352310818, 'ball_spin_tilt_deg': -40.72197790125275,
    'ball_mass': 0.62, 'ball_radius': 0.105,
    # The two coefficients on the ball and the board are ordinary rubber-on-wood
    # and rubber-on-acrylic numbers. The two on the rim are *effective* values:
    # a rigid ring has neither the compliance of a real rim nor the net's
    # damping, and a live coefficient there sends the ball straight back out.
    # 0.05 restitution / 1.20 friction is the pair that reproduces what a rim
    # plus net does to a ball that lands on it.
    'ball_restitution': 0.60, 'ball_friction': 0.72,
    'ball_rolling_friction': 0.004, 'ball_spinning_friction': 0.0002,
    'ball_linear_damping': 0.006, 'ball_angular_damping': 0.006,
    'board_restitution': 0.55, 'board_friction': 0.3304260964469999,
    'rim_restitution': 0.05, 'rim_friction': 1.20,
    'floor_restitution': 0.60, 'floor_friction': 0.62, 'floor_rolling_friction': 0.004,
    # The counterweight box: powder-coated steel over concrete. It only carries
    # the end of the shot, so its coefficients are ordinary platemail numbers
    # rather than the rim's effective ones.
    'goal_base_restitution': 0.34, 'goal_base_friction': 0.45,
    'timed_edits': [],
}

PHYSICS_LIMITS = {
    'ball_initial_speed': (2.0, 20.0), 'ball_spin': (0.0, 90.0),
    'ball_spin_tilt_deg': (-180.0, 180.0),
    'ball_mass': (0.1, 10.0), 'ball_radius': (0.05, 0.16),
    'ball_restitution': (0.0, 1.0), 'board_restitution': (0.0, 1.0),
    'goal_base_restitution': (0.0, 1.0),
    'rim_restitution': (0.0, 1.0), 'floor_restitution': (0.0, 1.0),
    'ball_friction': (0.0, 2.0), 'board_friction': (0.0, 2.0), 'goal_base_friction': (0.0, 2.0),
    'rim_friction': (0.0, 2.0), 'floor_friction': (0.0, 2.0),
}
VECTOR_KEYS = ('ball_release_location',)
# Presence switch of the backboard with its rim, carried only by a DELETE
# backboard override. It is not in BASELINE_PHYSICS, so the published cases'
# scenarios stay unchanged; an absent key means the board is there.
OPTIONAL_PHYSICS = {'board_presence': [1]}


# The ball is the shared library model; the hall and the goal are built by
# appearance/ from the solver's own geometry, with Poly Haven CC0 textures and
# props from assets/polyhaven/basketball_rim_roll_in.
ASSETS = dict(ball='basketball.glb')
DESCRIPTION = ('A basketball is thrown at an angle into the backboard, banks off it into the '
               'rim, spins around the inside of the rim a few times and drops through.')


def defaults():
    return dict(schema_version=1, scene=SCENE_NAME, seed=0, description=DESCRIPTION,
                assets=copy.deepcopy(ASSETS),
                physics=copy.deepcopy(BASELINE_PHYSICS),
                render=dict(fps=24, duration_sec=4.0, resolution=[1280, 720], samples=48),
                # Three-quarter view from the open side of the court, high
                # enough to look down into the ring: the swirl is only readable
                # if the camera sees the inside of the hoop, and the board has
                # to stay behind it so the bank still reads as a bank.
                camera=dict(location=[3.00, 2.60, 3.50], target=[0.45, 6.15, 1.85],
                            lens_mm=24.0),
                # A school sports hall (appearance/gym_hall.py): afternoon sun
                # through the high windows of the left wall, a physical sky, and
                # the pendant high-bay lamps under the roof.
                layout=dict(sun_elevation_deg=47.9, sun_heading_deg=-10.0, sun_strength=4.5,
                            sky_strength=1.0, window_view_strength=0.6, lamp_power=45.0,
                            exposure=0.6, look='AgX - Base Contrast'))


def merge(base, overrides):
    result = copy.deepcopy(base)
    if not isinstance(overrides, dict):
        raise ValueError('Scenario overrides must be an object')
    for key, value in overrides.items():
        if key in OPTIONAL_PHYSICS and key not in result:
            result[key] = copy.deepcopy(value)
            continue
        if key not in result:
            raise ValueError(f'Unknown scenario field: {key}')
        result[key] = merge(result[key], value) if isinstance(value, dict) else copy.deepcopy(value)
    return result


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(s, check_assets=True):
    for key in ('schema_version', 'scene', 'description', 'assets', 'physics', 'render',
                'camera', 'layout'):
        if key not in s:
            raise ValueError(f'Missing scenario field: {key}')
    if s['scene'] != SCENE_NAME or s['schema_version'] != 1:
        raise ValueError('Wrong scene or schema version')
    p, r, cam = s['physics'], s['render'], s['camera']
    if set(p) - set(OPTIONAL_PHYSICS) != set(BASELINE_PHYSICS):
        raise ValueError(f'Unknown editable physics parameter: {sorted((set(p) - set(OPTIONAL_PHYSICS)) ^ set(BASELINE_PHYSICS))}')
    for key in OPTIONAL_PHYSICS:
        if key in p and (not isinstance(p[key], list) or len(p[key]) != 1 or p[key][0] not in (0, 1)):
            raise ValueError(f'{key} must be [0] or [1]')
    for key, (low, high) in PHYSICS_LIMITS.items():
        if not finite(p[key]) or not low <= p[key] <= high:
            raise ValueError(f'{key} must be finite and within {low}..{high}')
    if p['ball_arc'] not in ('low', 'high'):
        raise ValueError("ball_arc must be 'low' or 'high'")
    for key in VECTOR_KEYS:
        vec = p[key]
        if not isinstance(vec, list) or len(vec) != 3 or not all(finite(v) for v in vec):
            raise ValueError(f'{key} must be a 3-vector')
    # A shot that cannot reach its aim point is not a scenario, it is a typo.
    release, face = p['ball_release_location'], p['board_face_y']
    horizontal = math.hypot(p['ball_aim_x'] - release[0], face - release[1])
    dz = p['ball_aim_z'] - release[2]
    reach = (p['ball_initial_speed'] ** 4
             - abs(p['gravity_z']) * (abs(p['gravity_z']) * horizontal ** 2 + 2 * dz * p['ball_initial_speed'] ** 2))
    if reach < 0:
        raise ValueError('ball_initial_speed cannot reach the aim point')
    if not (release[1] < face and release[2] > p['ball_radius']):
        raise ValueError('the ball must be released in front of the board and above the floor')
    half_board = COURT['board_half']
    if abs(p['ball_aim_x']) > half_board[0] - p['ball_radius']:
        raise ValueError('the aim point is off the side of the backboard')
    if not (COURT['board_center'][2] - half_board[2] < p['ball_aim_z']
            < COURT['board_center'][2] + half_board[2]):
        raise ValueError('the aim point is above or below the backboard')
    if type(r['fps']) is not int or r['fps'] <= 0:
        raise ValueError('Invalid fps')
    if not finite(r['duration_sec']) or not 0 < r['duration_sec'] <= 30:
        raise ValueError('Invalid duration')
    if (not isinstance(r['resolution'], list) or len(r['resolution']) != 2
            or any(type(v) is not int or v <= 0 for v in r['resolution'])):
        raise ValueError('Invalid resolution')
    if type(r['samples']) is not int or r['samples'] < 1:
        raise ValueError('Invalid sample count')
    for key in ('location', 'target'):
        if len(cam[key]) != 3 or not all(finite(v) for v in cam[key]):
            raise ValueError(f'Invalid camera {key}')
    if not finite(cam['lens_mm']) or cam['lens_mm'] <= 0:
        raise ValueError('Invalid lens')
    if check_assets:
        for name in ('ball',):
            if not (MODELS / s['assets'][name]).is_file():
                raise FileNotFoundError(f"{s['assets'][name]} is missing from assets/models")


def load_scenario(overrides=None, check_assets=True):
    """Resolved scenario: defaults, the on-disk recipe, then the case's override."""
    result = defaults()
    recipe = SCENARIO_DIR / 'scenario.json'
    if recipe.is_file():
        result = merge(result, json.loads(recipe.read_text(encoding='utf-8')))
    if overrides is not None:
        patch = (json.loads(Path(overrides).read_text(encoding='utf-8'))
                 if isinstance(overrides, (str, Path)) else copy.deepcopy(overrides))
        result = merge(result, patch)
    result['physics'].setdefault('timed_edits', [])
    validate(result, check_assets)
    return result


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def runtime(kind):
    # Same lookup as the other scenes (scripts/pcve_scene_runtime.py): PCVE_PHYSICS_PYTHON /
    # PCVE_RENDER_PYTHON, then <repo>/.runtime/{sim,render}/..., then a Python on PATH.
    from pcve_scene_runtime import python_for
    path = python_for('render' if kind == 'render' else 'physics')
    if Path(path).is_file():
        return str(path)
    raise FileNotFoundError(f'No {kind} Python runtime; use an environment with bpy/pybullet')
