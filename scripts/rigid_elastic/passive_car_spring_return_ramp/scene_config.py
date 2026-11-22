"""SI configuration and native unactuated MuJoCo rigid/spring assembly."""
import copy
import hashlib
import json
import math
from pathlib import Path

SCENE = 'passive_car_spring_return_ramp'
CASES = ('source', 'soft_spring', 'stiff_spring', 'high_friction', 'heavy_car', 'delete_spring')

def baseline():
    return {
        'schema_version': 1, 'scene': SCENE, 'category': 'rigid_elastic',
        'physics': {
            'units': {'length': 'm', 'mass': 'kg', 'time': 's', 'up': 'Z'},
            'gravity_m_s2': [0, 0, -9.81],
            'road': {'ramp_start_x_m': -.65, 'slope': .22, 'transition_radius_m': .16,
                     'flat_top_z_m': .020, 'flat_end_x_m': .74, 'width_m': .154, 'board_thickness_m': .014},
            'car': {'mass_kg': .18, 'chassis_mass_fraction': 7/9, 'length_m': .143,
                    'chassis_size_m': [.136, .060, .055], 'chassis_com_z_m': .020,
                    'wheelbase_m': .092, 'track_m': .076, 'wheel_radius_m': .020,
                    'wheel_width_m': .014, 'release_x_m': -.54,
                    'axle_frictionloss_Nm': .00002, 'axle_damping_Nms': .0000003},
            'spring': {'present': True, 'stiffness_N_m': 12., 'damping_Ns_m': .12,
                       'rest_length_m': .32, 'wire_diameter_m': .00078,
                       'mean_coil_diameter_m': .028, 'active_turns': 14, 'closed_end_turns': 2,
                       'effective_stroke_m': .270, 'initial_compression_m': 0.},
            'baffle': {'mass_kg': .012, 'rest_x_m': .32, 'thickness_m': .006,
                       'width_m': .120, 'height_m': .080, 'center_z_m': .066,
                       'guide_frictionloss_N': .004, 'guide_damping_Ns_m': .002,
                       'guide_y_m': .052, 'guide_z_m': .084,
                       'stop_timeconst_s': .0004, 'stop_damping_ratio': 1.5},
            'contact': {'friction': [.65, .001, .000005], 'timeconst_s': .0004,
                        'damping_ratio': 1., 'solimp': [.99, .9999, .0001]},
        },
        'simulation_quality': {'solver': 'MuJoCo 3.17.0', 'timestep_s': 1/12000,
            'integrator': 'implicitfast', 'constraint_solver': 'Newton',
            'iterations': 100, 'tolerance': 1e-10, 'cone': 'elliptic', 'arc_segments': 32,
            'history_hz': 1200},
        'appearance': {'camera': [.43, -1.78, .86], 'target': [.040, 0, .080], 'lens_mm': 46.,
                       'seed': 41, 'car_color': [.63, .085, .035, 1],
                       'environment': 'original procedural child room, oak floor and beech gravity track'},
        'render': {'width': 1280, 'height': 720, 'fps': 24, 'frames': 96, 'duration_s': 4.,
                   'engine': 'CYCLES', 'samples': 128, 'denoise': True,
                   'motion_blur': False, 'color_management': 'AgX'},
    }

def config_for(case, base=None):
    cfg = copy.deepcopy(base or baseline())
    if case not in CASES: raise ValueError(case)
    p = cfg['physics']
    if case == 'soft_spring': p['spring']['stiffness_N_m'] /= 5
    if case == 'stiff_spring': p['spring']['stiffness_N_m'] *= 5
    if case == 'high_friction': p['car']['travel_resistance_multiplier'] = 20.0
    if case == 'heavy_car': p['car']['mass_kg'] *= 2
    if case == 'delete_spring':
        p['spring'].update(present=False, stiffness_N_m=0., damping_Ns_m=0.)
    return cfg

def differences(a, b, path=''):
    if isinstance(a, dict) and isinstance(b, dict):
        return [v for k in sorted(a.keys() | b.keys()) for v in differences(a.get(k), b.get(k), f'{path}.{k}' if path else k)]
    return [] if a == b else [{'path': path, 'before': a, 'after': b}]

def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
def save_json(path, value): Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
def fmt(a): return ' '.join(f'{x:.14g}' for x in a)

def profile(cfg, x):
    r = cfg['physics']['road']; alpha = math.atan(r['slope']); radius = r['transition_radius_m']
    xa = -radius*math.sin(alpha)
    if x >= 0: return r['flat_top_z_m'], 0.
    if x >= xa:
        theta = math.asin(-x/radius)
        return r['flat_top_z_m']+radius*(1-math.cos(theta)), theta
    return r['flat_top_z_m']+radius*(1-math.cos(alpha))+(xa-x)*r['slope'], alpha

def road_points(cfg):
    r=cfg['physics']['road']; a=math.atan(r['slope']); radius=r['transition_radius_m']; n=cfg['simulation_quality']['arc_segments']
    xs=[r['ramp_start_x_m']]+[-radius*math.sin(a*(1-i/n)) for i in range(n+1)]+[r['flat_end_x_m']]
    return [(x,profile(cfg,x)[0]) for x in xs]

def car_properties(cfg):
    c=cfg['physics']['car']; m=c['mass_kg']*c['chassis_mass_fraction']; mw=(c['mass_kg']-m)/4
    l,w,h=c['chassis_size_m']; r=c['wheel_radius_m']; t=c['wheel_width_m']
    return {'chassis_mass_kg':m,'wheel_mass_kg':mw,
            'chassis_inertia_kg_m2':[m*(w*w+h*h)/12,m*(l*l+h*h)/12,m*(l*l+w*w)/12],
            'wheel_inertia_kg_m2':[mw*(3*r*r+t*t)/12,mw*r*r/2,mw*(3*r*r+t*t)/12]}

# MuJoCo 3.17.0 mjMINMU. Audit this against the installed runtime.
MUJOCO_MIN_FRICTION = 1e-5

def resistance_parameters(cfg):
    """Derived passive wheel resistance; no spring or guide terms are scaled.

    At identical normal load and angular velocity, a multiplier scales the
    rolling-resistance moment limit, axle Coulomb limit and axle viscous torque.
    The travel trajectory and dissipated work remain solver outputs.
    """
    c=cfg['physics']['car'];con=cfg['physics']['contact']
    factor=float(c.get('travel_resistance_multiplier',1.0))
    if not math.isfinite(factor) or factor<1:
        raise ValueError('travel_resistance_multiplier must be finite and >= 1')
    rolling=max(float(con.get('wheel_road_rolling_friction_m',con['friction'][2])),MUJOCO_MIN_FRICTION)
    return {'multiplier':factor,'axle_frictionloss_Nm':c['axle_frictionloss_Nm']*factor,
            'axle_damping_Nms':c['axle_damping_Nms']*factor,
            'wheel_road_rolling_friction_m':rolling*factor,
            'reference_wheel_road_rolling_friction_m':rolling}

def model_xml(cfg):
    p=cfg['physics']; c=p['car']; b=p['baffle']; sp=p['spring']; r=p['road']; s=cfg['simulation_quality']; con=p['contact']; cp=car_properties(cfg)
    parts=[f'''<mujoco model="{SCENE}"><compiler angle="radian"/>
      <option timestep="{s['timestep_s']}" gravity="{fmt(p['gravity_m_s2'])}" integrator="{s['integrator']}"
        solver="{s['constraint_solver']}" iterations="{s['iterations']}" tolerance="{s['tolerance']}" cone="{s['cone']}">
        <flag energy="enable"/></option><size memory="32M"/>
      <default><geom friction="{fmt(con['friction'])}" solref="{con['timeconst_s']} {con['damping_ratio']}" solimp="{fmt(con['solimp'])}" condim="6"/>
        <joint damping="0"/></default><worldbody>
      <geom name="floor" type="plane" size="2 2 .01"/>
    ''']
    pts=road_points(cfg)
    # Original collision ordering/filtering is retained; native max mixing
    # combines the road material with unchanged tyre coefficients.
    resistance=resistance_parameters(cfg)
    road_friction=''
    if 'wheel_road_rolling_friction_m' in con or resistance['multiplier']!=1:
        rolling=resistance['wheel_road_rolling_friction_m']
        road_friction=f' friction="{fmt([con["friction"][0],con["friction"][1],rolling])}"'
    for i,((x1,z1),(x2,z2)) in enumerate(zip(pts,pts[1:])):
        angle=math.atan2(z1-z2,x2-x1); length=math.hypot(x2-x1,z2-z1); thick=r['board_thickness_m'] if x1<0 else r['flat_top_z_m']
        center=[(x1+x2)/2-math.sin(angle)*thick/2,0,(z1+z2)/2-math.cos(angle)*thick/2]
        parts.append(f'<geom name="road_{i}" type="box" pos="{fmt(center)}" euler="0 {angle} 0" size="{length/2+.0000005} {r["width_m"]/2} {thick/2}"{road_friction}/>')
    # World-fixed upright, guide rods and mechanical stops; the joint is the
    # exact horizontal guide constraint, so guide collisions are excluded.
    back=b['rest_x_m']+b['thickness_m']/2+sp['rest_length_m']
    for side in [-1,1]:
        parts.append(f'<geom name="fixed_support_{side}" type="box" pos="{back+.006} {side*.054} .065" size=".006 .013 .045"/>')
    parts.append(f'<geom name="fixed_spring_anchor" type="box" pos="{back+.006} 0 {b["center_z_m"]}" size=".006 .065 .008"/>')
    parts.append(f'''<body name="baffle" pos="{b['rest_x_m']} 0 {b['center_z_m']}">
      <joint name="guide" type="slide" axis="1 0 0" limited="true" range="0 {sp['effective_stroke_m']}"
       stiffness="{sp['stiffness_N_m']}" springref="0" damping="{sp['damping_Ns_m']+b['guide_damping_Ns_m']}"
       frictionloss="{b['guide_frictionloss_N']}" solreflimit="{b['stop_timeconst_s']} {b['stop_damping_ratio']}" solimplimit=".99 .9999 .0001"/>
      <inertial pos="0 0 0" mass="{b['mass_kg']}" diaginertia="{fmt([b['mass_kg']*(b['width_m']**2+b['height_m']**2)/12,b['mass_kg']*(b['thickness_m']**2+b['height_m']**2)/12,b['mass_kg']*(b['thickness_m']**2+b['width_m']**2)/12])}"/>
      <geom name="baffle_face" type="box" size="{b['thickness_m']/2} {b['width_m']/2} {b['height_m']/2}"/>
      </body>''')
    if not c.get('present',True):
        # DELETE car: no chassis or wheel bodies; track, plate, guides and spring are unchanged.
        parts.append('</worldbody></mujoco>')
        return '\n'.join(parts)
    z,angle=profile(cfg,c['release_x_m']); z+=c['wheel_radius_m']/math.cos(angle)-.000002
    parts.append(f'''<body name="chassis" pos="{c['release_x_m']} 0 {z}" euler="0 {angle} 0"><freejoint name="car_free"/>
      <inertial mass="{cp['chassis_mass_kg']}" pos="0 0 {c['chassis_com_z_m']}" diaginertia="{fmt(cp['chassis_inertia_kg_m2'])}"/>
      <geom name="chassis_base" type="box" pos="0 0 .019" size=".066 .029 .014"/>
      <geom name="cabin" type="box" pos="-.014 0 .043" size=".032 .027 .013"/>
      <geom name="front_bumper" type="box" pos=".068 0 .007" size=".0035 .033 .0045"/>
      <geom name="rear_bumper" type="box" pos="-.068 0 .007" size=".0035 .033 .0045"/>''')
    for i,(x,y) in enumerate([(x,y) for x in [-c['wheelbase_m']/2,c['wheelbase_m']/2] for y in [-c['track_m']/2,c['track_m']/2]]):
        parts.append(f'''<body name="wheel_{i}" pos="{x} {y} 0"><joint name="axle_{i}" type="hinge" axis="0 1 0"
          frictionloss="{resistance['axle_frictionloss_Nm']}" damping="{resistance['axle_damping_Nms']}"/>
          <inertial pos="0 0 0" mass="{cp['wheel_mass_kg']}" diaginertia="{fmt(cp['wheel_inertia_kg_m2'])}"/>
          <geom name="tire_{i}" type="cylinder" size="{c['wheel_radius_m']} {c['wheel_width_m']/2}" quat=".70710678118655 .70710678118655 0 0"/>
          </body>''')
    parts.append('</body></worldbody></mujoco>')
    return '\n'.join(parts)
