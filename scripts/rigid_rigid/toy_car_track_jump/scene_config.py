"""SI inputs shared by Bullet, Blender and frame annotations."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

BASELINE = {'physics': {'units': {'length': 'm', 'mass': 'kg', 'time': 's', 'up': 'Z', 'travel': '+X'},
             'gravity': [0.0, 0.0, -9.81],
             'interventions': [],
             'launcher': {'collisions_enabled': True,
                          'lateral_friction': 0.65,
                          'rolling_friction': 2e-05,
                          'spinning_friction': 1e-05},
             'car': {'present': True,
                     'length_m': 0.15,
                     'body_width_m': 0.0731,
                     'chassis_mass_kg': 0.09,
                     'wheel_mass_kg': 0.004,
                     'wheel_radius_m': 0.0127,
                     'wheel_width_m': 0.0127,
                     'wheelbase_m': 0.09363412,
                     'wheel_center_track_m': 0.0572,
                     'com_above_axle_m': 0.0078,
                     'initial_x_m': -0.2,
                     'initial_y_m': 0.0,
                     'initial_speed_m_s': 2.76,
                     'initial_lateral_speed_m_s': 0.006,
                     'initial_yaw_rate_rad_s': 0.02,
                     'com_lateral_offset_m': 0.0003,
                     'com_longitudinal_offset_m': -0.03,
                     'tire_contact_half_width_m': 0.0023,
                     'axle_damping_Nms': 1e-07,
                     'axle_friction_Nm': 8e-05,
                     'longitudinal_second_moment_factor': 2.4,
                     'transverse_second_moment_factor': 2.0},
             'track': {'blend_horizontal_length_m': 0.3,
                       'start_x_m': -0.36,
                       'curve_start_x_m': 0.1083,
                       'curve_horizontal_length_m': 0.4917,
                       'launch_height_m': 0.27,
                       'deck_z_m': 0.003,
                       'width_m': 0.097,
                       'thickness_m': 0.0025,
                       'edge_height_m': 0.0105,
                       'edge_width_m': 0.0026,
                       'lateral_friction': 0.65,
                       'rolling_friction': 2e-05,
                       'spinning_friction': 1e-05},
             'floor': {'lateral_friction': 0.8,
                       'rolling_friction': 0.001,
                       'spinning_friction': 2e-05,
                       'contact_stiffness_1_s2': 1000000.0,
                       'contact_damping_ratio': 0.95}},
 'simulation_quality': {'timestep_s': 0.00020833333333333335,
                        'solver_iterations': 100,
                        'impratio': 10.0,
                        'curve_segments': 240,
                        'trajectory_hz': 240,
                        'deck_contact_time_constant_s': 0.0008,
                        'deck_segment_overlap_m': 0.0001},
 'appearance': {'preset': 'activity_room',
                'seed': 409026,
                'camera': {'location': [-0.232, -1.214, 0.26],
                           'target': [1.03, 1.506, 0.378],
                           'lens_mm': 25.2,
                           'sensor_width_mm': 36.0,
                           'aperture_fstop': 8.0,
                           'focus_distance_m': 1.9},
                'car_local_bounds_m': [[-0.0813, -0.0366, -0.0205], [0.0688, 0.0366, 0.0274]],
                'room': {'floor_repeat_m': 1.3,
                         'floor_roughness': [0.26, 0.44],
                         'floor_value': 1.15,
                         'floor_color_linear': [0.46, 0.47, 0.475],
                         'floor_coat': 0.2,
                         'wall_color_linear': [0.5, 0.48, 0.41],
                         'wall_coat': 0.58,
                         'trim_color_linear': [0.66, 0.65, 0.6],
                         'shelf_yaw_rad': 1.5708,
                         'rug_extent_m': [[-0.3, 1.3], [0.36, 1.3]],
                         'lamp_glow': 0.25},
                'lighting': {'environment_strength': 4.5,
                             'environment_rotation_rad': 1.6,
                             'sun_energy': 10.0,
                             'sun_angle_deg': 0.6,
                             'sun_elevation_deg': 30.0,
                             'ceiling_bounce_w': 0.0,
                             'lamp_w': 1.8},
                'wheel_min_roughness': 0.42,
                'exposure_ev': 0.7,
                'daylight_finish': {'sun_azimuth_deg': 6.98,
                              'sun_color': [1.0, 0.84, 0.64],
                              'track_roughness': [0.13, 0.24],
                              'riser_roughness': [0.15, 0.27],
                              'launcher_roughness': [0.2, 0.32],
                              'plastic_specular_level': 0.5,
                              'track_subsurface': 0.12,
                              'rug_sheen': 0.3,
                              'rug_normal': 1.4,
                              'rug_value': 1.5,
                              'roof_roundel_uv': [0.752, 0.4365, 0.071],
                              'roof_roundel_color': [0.74, 0.74, 0.73],
                              'book_cloth_value': 0.32,
                              'book_cloth_roughness': 0.78,
                              'plant_yaw_rad': 0.6}},
 'render': {'resolution': [1280, 720],
            'fps': 24,
            'duration_sec': 4.0,
            'samples': 128,
            'supersample_percent': 150,
            'engine': 'CYCLES',
            'denoising': True,
            'motion_blur_shutter_frames': 0.15,
            'view_look': 'AgX - High Contrast',
            'encode_filter': 'scale=1280:720:flags=lanczos,vignette=PI/8,noise=c0s=4:c0f=t+u:c1s=2:c1f=t+u:c2s=2:c2f=t+u',
            'glare_threshold': 1.1,
            'glare_size': 8,
            'glare_mix': -0.86,
            'lens_dispersion': 0.0035,
            'color_management': 'AgX'}}

def merge(base, updates):
    out = copy.deepcopy(base)
    for k, v in updates.items():
        if k not in out:
            raise KeyError(k)
        out[k] = merge(out[k], v) if isinstance(v, dict) else copy.deepcopy(v)
    return out

def scenario(overrides=None):
    return merge(BASELINE, overrides or {})

def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def curve_point(cfg, u):
    """A straight incline, entered through a short parabola so the chassis clears the junction."""
    tr = cfg['physics']['track']
    length = tr['curve_horizontal_length_m']
    rise = tr['launch_height_m'] - tr['deck_z_m']
    blend = tr['blend_horizontal_length_m']
    slope = rise/(length-blend/2)
    run = length*u
    lift = slope*run*run/(2*blend) if run < blend else slope*(run-blend/2)
    return (tr['curve_start_x_m'] + run, tr['deck_z_m'] + lift)

def track_profile(cfg):
    tr = cfg['physics']['track']
    n = cfg['simulation_quality']['curve_segments']
    points = [(tr['start_x_m'], tr['deck_z_m']), (tr['curve_start_x_m'], tr['deck_z_m'])]
    points.extend(curve_point(cfg, i/n) for i in range(1, n+1))
    return points

def wheel_positions(cfg):
    c = cfg['physics']['car']
    return [[x, y, -c['com_above_axle_m']]
            for x in [c['wheelbase_m']/2, -c['wheelbase_m']/2]
            for y in [-c['wheel_center_track_m']/2, c['wheel_center_track_m']/2]]

def launcher_colliders(cfg):
    """Conservative proxies for the existing stationary launcher housing.
    The thin spring striker/rod are moving internals, not immovable blocks.
    Dimensions match appearance/look_toy_car_track_jump.py::track.
    """
    tr=cfg['physics']['track'];k=tr['width_m']/.084;x=tr['start_x_m']
    return [
        ('launcher_base',[x-.1*k,0,.0045*k],[.215*k,.135*k,.009*k]),
        ('launcher_housing',[x-.122*k,0,.026*k],[.15*k,.112*k,.036*k]),
        ('launcher_button',[x-.15*k,0,.0485*k],[.062*k,.07*k,.012*k]),
        ('launcher_entry',[x-.03*k,0,.0065*k],[.06*k,tr['width_m']+2*tr['edge_width_m']+.01,.007*k])]

def chassis_boxes(cfg):
    c = cfg['physics']['car']
    # Local COM origin; visual wheel arches remain outside these collision boxes.
    scale = c['length_m']/.38
    return [([c['length_m']*.46, c['body_width_m']*.455, .028*scale], [-.016*scale, 0., -.002*scale]),
            ([.076*scale, .057*scale, .020*scale], [-.015*scale, 0., .048*scale]),
            ([.009*scale, .073*scale, .010*scale], [.165*scale, 0., -.023*scale]),
            ([.009*scale, .073*scale, .010*scale], [-.197*scale, 0., -.023*scale])]
