"""Scene contract: constants, baseline physics, cases and repository locations.

No Blender dependency; shared unchanged by all interventions.
"""
from pathlib import Path
import copy
import json
import math
import sys

CASE_ID = 'spring_block_step'
SCENE = Path(__file__).resolve().parent
CATEGORY = SCENE.parent
SCRIPTS = CATEGORY.parent
REPO = SCRIPTS.parent
FPS, FRAMES, RELEASE = 24, 96, 0.375
MOTION_FPS = 240
sys.path.insert(0, str(SCRIPTS))
from pcve_media_contract import CONTRACT as MEDIA_CONTRACT
from pcve_assets import asset
ASSETS = asset('scenes/spring_block_step')
# Accepted solver outputs (states.npz, motion_states.npz, resolved_physics.json,
# model.xml, scenario_overrides.json, native_*.bullet), one folder per native case.
NATIVE = ASSETS / 'native_states'
RENDERS = REPO / 'renders' / CASE_ID
RUNTIME = REPO / '.runtime' / CASE_ID
SUITE_KEY = 'pcve_spring_block_step_suite'
# Accepted delivery: solver audits, convergence runs, render records of its look.
DELIVERY = RENDERS / 'physics_audit/pcve_spring_block_step_suite'
WIDTH, HEIGHT = MEDIA_CONTRACT['width'], MEDIA_CONTRACT['height']
assert (FPS, FRAMES) == (MEDIA_CONTRACT['fps'], MEDIA_CONTRACT['frames'])
BASE = {
    'spring_present': [1], 'obstacle_present': [0],
    'block_mass_kg': 0.145, 'spring_young_modulus_pa': 200e9,
    'spring_poisson_ratio': 0.30, 'spring_wire_diameter_m': 0.00165,
    'spring_mean_diameter_m': 0.038, 'spring_active_turns': 20,
    'spring_rest_length_m': 0.160, 'spring_initial_compression_m': 0.075,
    'spring_anchor_x_m': -0.280, 'spring_density_kg_m3': 7850,
    'spring_axis_z_m': .090, 'pusher_mass_kg': 0.007, 'spring_damping_ns_m': 0.12,
    'guide_dry_friction_n': 0.040, 'guide_travel_limit_m': 0.115,
    'block_size_m': [0.074, 0.064, 0.050],
    'wood_edge_radius_m': 0.0008,
    'block_position_m': [-0.158, 0.0, 0.090],
    'block_quaternion_wxyz': [1, 0, 0, 0],
    'upper_friction': 0.22, 'table_friction': 0.24,
    'upper_size_m': [0.450, 0.270, 0.025],
    'upper_position_m': [-0.095, 0, 0.0525],
    'table_size_m': [1.800, 0.900, 0.050],
    'table_position_m': [0.280, 0, -0.025],
    'platform_riser_size_m': [0.045, 0.230, 0.040],
    'platform_riser_centres_m': [[-.26, 0, .020], [.075, 0, .020]],
    'obstacle_position_m': [0.31, 0, 0.025],
    'obstacle_size_m': [0.060, 0.080, 0.050],
    'obstacle_mass_kg': 0.150,
    'obstacle_quaternion_wxyz': [1, 0, 0, 0],
    'obstacle_friction': 0.42,
}
# Moving guide inertia is explicit: solid aluminium rod and half-speed steel sleeve.
BASE['plate_mass_kg'] = 0.010
BASE['guide_rod_mass_kg'] = math.pi * .0025**2 * .069 * 2700
BASE['guide_middle_mass_kg'] = math.pi * (.0034**2-.00265**2) * .067 * 7850
BASE['guide_effective_mass_kg'] = BASE['guide_rod_mass_kg'] + BASE['guide_middle_mass_kg']/4
BASE['pusher_mass_kg'] = BASE['plate_mass_kg'] + BASE['guide_effective_mass_kg']
BASE['pusher_size_m'] = [.002, .046, .042]
BASE['steel_free_seat_length_m'] = BASE['spring_rest_length_m']-.002
CASES = {
    'source': ('基准场景', None),
    'mass_half': ('木块质量 ×0.5', 'SET block.mass TIMES 0.5'),
    'young_quarter': ('弹簧杨氏模量 ×0.25', 'SET spring.young_modulus TIMES 0.25'),
    'friction_half': ('桌面摩擦系数 ×0.5', 'SET table.friction TIMES 0.5'),
    'remove_spring': ('删除弹簧及活动推板', 'DELETE spring'),
    'add_block': ('增加桌面自由木块', 'ADD obstacle AT PRESET landing'),
}

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf8')

def load_physics(path):
    """resolved_physics.json of a case. The accepted states store the two platform risers
    under platform_* keys outside BASE; they are returned as the platform_riser_* keys of BASE, values unchanged."""
    c = json.loads(Path(path).read_text(encoding='utf8'))
    for key in [k for k in c if k.startswith('platform_') and k not in BASE]:
        c['platform_riser_' + key.split('_', 2)[2]] = c.pop(key)
    return c

def spring_properties(c):
    d, D, n = c['spring_wire_diameter_m'], c['spring_mean_diameter_m'], c['spring_active_turns']
    G = c['spring_young_modulus_pa'] / (2*(1+c['spring_poisson_ratio']))
    k = G*d**4/(8*D**3*n)
    active_length = math.hypot(math.pi*D*n, c['spring_rest_length_m']-2*d)
    line_density = math.pi*d*d/4*c['spring_density_kg_m3']
    effective_mass = line_density*(active_length/3+math.pi*D)
    C = D/d
    wahl = (4*C-1)/(4*C-4)+0.615/C
    return {'stiffness_n_m': k, 'shear_modulus_pa': G,
            'effective_coil_mass_kg': effective_mass,
            'coil_mass_kg': line_density*(active_length+2*math.pi*D),
            'stored_energy_j': 0.5*k*c['spring_initial_compression_m']**2,
            'peak_wire_shear_pa': wahl*8*k*c['spring_initial_compression_m']*D/(math.pi*d**3),
            'solid_length_m': (n+2)*d,
            'helix_angle_deg': math.degrees(math.atan2(c['spring_rest_length_m']-2*d,math.pi*D*n))}

def vocabulary_module():
    import importlib.util
    path = Path(__file__).with_name('edit_vocab.py')
    spec = importlib.util.spec_from_file_location('spring_block_step_vocab',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def parameters(case):
    c = copy.deepcopy(BASE)
    _, command = CASES[case]
    overrides = {}
    if command:
        module = vocabulary_module()
        edit = module.dsl.parse(command, module.VOCAB)
        overrides = module.dsl.to_scenario_override(edit, module.VOCAB)
        module.policy.audit_scenario_override(edit,module.VOCAB,overrides,{})
        c.update(overrides)
    return c, overrides
