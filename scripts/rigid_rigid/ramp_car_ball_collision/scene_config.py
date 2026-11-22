"""SI input for a passive articulated toy car and a hollow rigid PVC ball."""
import copy
import hashlib
import json
import math
from pathlib import Path

# The scene: flat-runout toy ramp, diecast car, courtyard living room with the finishing pass.
BASELINE = {'physics': {'units': {'length': 'm', 'mass': 'kg', 'time': 's', 'up': 'Z', 'travel': '+X'},
             'gravity': [0.0, 0.0, -9.81],
             'ramp': {'length_m': 0.55,
                      'rise_m': 0.12,
                      'width_m': 0.18,
                      'thickness_m': 0.012,
                      'toe_transition_m': 0.08,
                      'lateral_friction': 0.65,
                      'restitution': 0.12,
                      'rolling_friction': 0.0,
                      'spinning_friction': 0.0,
                      'flat_runout_m': 0.16,
                      'flat_deck_height_m': 0.0032,
                      'exit_transition_m': 0.035},
             'floor': {'lateral_friction': 0.65,
                       'restitution': 0.12,
                       'rolling_friction': 0.0,
                       'spinning_friction': 0.0},
             'car': {'chassis_mass_kg': 0.2,
                     'wheel_mass_kg': 0.0125,
                     'wheel_radius_m': 0.014,
                     'wheel_width_m': 0.008,
                     'wheelbase_m': 0.076,
                     'wheel_center_track_m': 0.052,
                     'com_above_axle_m': 0.013,
                     'release_contact_center_x_m': -0.465,
                     'chassis_inertia_kg_m2': [5.2e-05, 0.00019, 0.000215],
                     'chassis_lateral_friction': 0.35,
                     'bumper_restitution': 0.8,
                     'tire_lateral_friction': 0.85,
                     'tire_restitution': 0.03,
                     'tire_rolling_friction': 0.0007,
                     'tire_spinning_friction': 5e-05,
                     'axle_damping_Nms': 2e-06,
                     'initial_linear_velocity': [0.0, 0.0, 0.0],
                     'initial_angular_velocity': [0.0, 0.0, 0.0],
                     'initial_wheel_angular_velocity': 0.0},
             'ball': {'present': True,
                      'radius_m': 0.03,
                      'mass_kg': 0.03,
                      'initial_position_m': [0.445, 0.0, 0.03],
                      'initial_quaternion_xyzw': [0.0, 0.0, 0.0, 1.0],
                      'inertia_factor': 0.6666666666666666,
                      'restitution': 0.8,
                      'lateral_friction': 0.45,
                      'rolling_friction': 0.003,
                      'spinning_friction': 0.0001,
                      'initial_linear_velocity': [0.0, 0.0, 0.0],
                      'initial_angular_velocity': [0.0, 0.0, 0.0]}},
 'simulation_quality': {'substeps_per_frame': 640,
                        'solver_iterations': 120,
                        'contact_erp': 0.0,
                        'contact_breaking_threshold_m': 0.0001,
                        'contact_slop_m': 1e-06,
                        'collision_margin_m': 2e-05,
                        'restitution_velocity_threshold_m_s': 0.02,
                        'trajectory_hz': 240,
                        'toe_segments': 64,
                        'exit_segments': 32},
 'appearance': {'seed': 409031,
                'preset': 'diecast_living_room_garden',
                'model_revision': 'car_concept_original_bonnet_raised_body',
                'camera': {'location': [1.95, -2.18, 0.65],
                           'target': [0.68, 0.1, 0.26],
                           'lens_mm': 40.5,
                           'sensor_width_mm': 36.0,
                           'use_depth_of_field': True,
                           'focus_distance_m': 2.6,
                           'f_stop': 6.3},
                'car_asset': 'khronos_models/car_concept/CarConcept.glb',
                'sofa_asset': 'blenderkit/cozy_living_room/cozy_living_room.blend',
                'car_color': [0.46, 0.105, 0.035],
                'ball_colors': [[0.72, 0.028, 0.018], [0.88, 0.61, 0.045], [0.022, 0.18, 0.54]],
                'floor_texture_repeat_m': 1.7,
                'floor_plank_width_m': 0.18888888888888888,
                'floor_plank_length_m': 1.25,
                'wheel_lot_dot_diameter_m': 0.0025,
                'ramp_finish': {'style': 'satin_molded_abs',
                                'deck_color_linear': [0.018, 0.21, 0.26],
                                'deck_roughness': 0.42,
                                'edge_color_linear': [0.018, 0.075, 0.085],
                                'support_color_linear': [0.045, 0.05, 0.052]},
                'ramp_construction': {'revision': 'flat_runout_toy',
                                      'deck_shell_thickness_m': 0.0032,
                                      'side_rail_width_m': 0.007,
                                      'side_rail_height_m': 0.003,
                                      'side_rail_drop_m': 0.015,
                                      'edge_radius_m': 0.0007,
                                      'exit_shoe_start_x_m': 0.16,
                                      'exit_shoe_front_width_m': 0.152,
                                      'exit_shoe_color_linear': [0.045, 0.058, 0.064],
                                      'exit_shoe_roughness': 0.54,
                                      'exit_shoe_thickness_fraction': 0.55,
                                      'support_foot_thickness_m': 0.0025},
                'window_curtain': {'revision': 'casement_linen_clearance',
                                   'rod_x_m': -1.52,
                                   'rod_height_m': 2.49,
                                   'rod_end_extension_m': 0.31,
                                   'hem_floor_clearance_m': 0.016},
                'car_body_vertical_scale': 1.45,
                'interior_lighting': {'environment_strength': 0.7,
                                'window_area_w': 180.0,
                                'sun_energy': 3.0,
                                'sun_angle_deg': 2.0,
                                'room_fill_w': 4.0,
                                'exposure_ev': 0.2},
                'courtyard': {'revision': 'physical_courtyard',
                               'ground_z_m': -0.06,
                               'patio_bounds_x_m': [-6.0, -1.86],
                               'plant_height_m': 1.6,
                               'glass_roughness': 0.002,
                               'both_casements_open_deg': 160.0,
                               'boundary_wall_x_m': -6.45,
                               'boundary_wall_height_m': 2.3,
                               'planted_containers_xyz_height_m': [[-4.1, -1.0, 1.55],
                                                                   [-4.6, 0.45, 1.85],
                                                                   [-4.0, 1.8, 1.35],
                                                                   [-5.25, 2.9, 1.65],
                                                                   [-5.0, -2.8, 1.7],
                                                                   [-4.1, 2.8, 1.45],
                                                                   [-4.8, 3.7, 1.8],
                                                                   [-5.6, 4.8, 2.0]]},
                'car_front_shape': {'revision': 'original_bonnet_raised_body',
                                    'bonnet_lift_m': 0.0,
                                    'bonnet_start_x_m': 0.02,
                                    'bonnet_full_x_m': 0.04,
                                    'lower_activation_z_m': -0.023,
                                    'full_activation_z_m': -0.011,
                                    'nose_shortening_m': 0.0023,
                                    'shorten_start_x_m': 0.04,
                                    'shorten_full_x_m': 0.0635,
                                    'body_lift_m': 0.007},
                'room_finish': {'revision': 'room_finish',
                              'base_template': 'packed source_template.blend (sha256 '
                                               '4c949e5b6e36f77d5aa0ac3c2328ad81ff32a86093b9f859736a37c147cbb698)',
                              'lighting': {'environment_strength': 1.0,
                                           'sun_energy': 3.0,
                                           'sun_angle_deg': 2.0,
                                           'exposure_ev': 2.2,
                                           'diffuse_bounces': 8},
                              'walls': {'asset': 'polyhaven/beige_wall_001',
                                        'files': {'diffuse': 'beige_wall_001_diff_4k.jpg',
                                                  'roughness': 'beige_wall_001_rough_4k.jpg',
                                                  'normal': 'beige_wall_001_nor_gl_4k.jpg'},
                                        'tile_m': 3.0,
                                        'paint_color_linear': [0.72, 0.71, 0.67],
                                        'scan_luminance_range': [0.262, 0.286],
                                        'tone_variation': 0.05,
                                        'roughness': [0.8, 0.95],
                                        'normal_strength': 0.35},
                              'sofa': {'upholstery_normal_strength': 0.3,
                                       'upholstery_roughness': [0.78, 0.95],
                                       'sheen_weight': 0.45,
                                       'sheen_roughness': 0.5,
                                       'linen_tile_m': 0.271,
                                       'linen_luminance_range': [0.3, 0.5],
                                       'pillow_weave_contrast': 0.1,
                                       'pillow_colors_linear': {'Natural unbleached cushion': [0.64,
                                                                                               0.6,
                                                                                               0.5],
                                                                'Muted blue gray woven pillow': [0.14,
                                                                                                 0.21,
                                                                                                 0.23]}}}},
 'render': {'resolution': [1280, 720],
            'fps': 24,
            'duration_sec': 4.0,
            'samples': 128,
            'engine': 'CYCLES',
            'denoising': True,
            'motion_blur_shutter_frames': 0.15,
            'color_management': 'AgX',
            'persistent_data': False}}

CASES = {'source': {},
    'edit_heavy_ball': {'physics': {'ball': {'mass_kg': .8}}},
    'edit_low_restitution': {'physics': {'ball': {'restitution': .1}}},
    'edit_remove_ball': {'physics': {'ball': {'present': False}}},
    'edit_light_ball': {'physics': {'ball': {'mass_kg': .01}}},
    'edit_remove_car': {'physics': {'car': {'present': False}}},
    'edit_remove_car_at_2s': {'physics': {'car': {'remove_at_sec': 2.}}}}

def merge(base, override, path=()):
    out=copy.deepcopy(base)
    for k,v in override.items():
        if k not in out:
            if path==('physics','car') and k in {'present','remove_at_sec'}:
                out[k]=copy.deepcopy(v)
                continue
            raise KeyError(k)
        out[k]=merge(out[k],v,path+(k,)) if isinstance(v,dict) else copy.deepcopy(v)
    return out

def scenario(case='source', override=None):
    return merge(merge(BASELINE,CASES[case]),override or {})

def configured_scenario(case='source', configuration_path=None, override=None):
    base=json.loads(Path(configuration_path).read_text()) if configuration_path else BASELINE
    return merge(merge(base,CASES[case]),override or {})

def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def differences(a,b,prefix=''):
    if isinstance(a,dict) and isinstance(b,dict):
        out={}
        for k in sorted(a.keys()|b.keys()): out.update(differences(a.get(k),b.get(k),(prefix+'.'+k).strip('.')))
        return out
    return {} if a==b else {prefix:{'before':a,'after':b}}

def save_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def surface(cfg,x):
    r=cfg['physics']['ramp'];d=-x;a=r['toe_transition_m']
    h=r.get('flat_deck_height_m',0.);flat=r.get('flat_runout_m',0.)
    m=(r['rise_m']-h)/(r['length_m']-a/2)
    if flat and x>=0:
        if x<=flat:return h,0.
        lip=r['exit_transition_m'];t=min(1.,(x-flat)/lip)
        return h*(1.-3*t*t+2*t*t*t),h*(-6*t+6*t*t)/lip
    if d<=0: return 0.,0.
    return (h+m*d*d/(2*a),-m*d/a) if d<a else (h+m*(d-a/2),-m)

def ramp_end_x(cfg):
    r=cfg['physics']['ramp']
    return r.get('flat_runout_m',0.)+r.get('exit_transition_m',0.)

def profile(cfg):
    r=cfg['physics']['ramp'];n=cfg['simulation_quality']['toe_segments'];a=r['toe_transition_m']
    xs=[-r['length_m']]+[-a+a*i/n for i in range(n+1)]
    if r.get('flat_runout_m',0.):
        flat=r['flat_runout_m'];lip=r['exit_transition_m'];count=cfg['simulation_quality']['exit_segments']
        xs += [flat]+[flat+lip*i/count for i in range(1,count+1)]
    return [(x,surface(cfg,x)[0]) for x in xs]

def initial_car_pose(cfg):
    c=cfg['physics']['car'];x=c['release_contact_center_x_m'];z,slope=surface(cfg,x)
    theta=math.atan(-slope);h=c['wheel_radius_m']+c['com_above_axle_m']
    return [x+math.sin(theta)*h,0.,z+math.cos(theta)*h],theta

def wheel_positions(cfg):
    c=cfg['physics']['car']
    return [[x,y,-c['com_above_axle_m']] for x in [c['wheelbase_m']/2,-c['wheelbase_m']/2]
            for y in [-c['wheel_center_track_m']/2,c['wheel_center_track_m']/2]]

def car_collision_boxes():
    # Extents align with the visual chassis, cabin and actual front contact face.
    return [([.052,.022,.009],[0.,0.,0.]),
            ([.023,.019,.009],[-.007,0.,.014]),
            ([.003,.027,.006],[.058,0.,.003]),
            ([.003,.025,.004],[-.055,0.,-.001])]

CONTACT_REFERENCE = 'https://github.com/bulletphysics/bullet3/blob/3.25/src/BulletCollision/CollisionDispatch/btManifoldResult.cpp'
