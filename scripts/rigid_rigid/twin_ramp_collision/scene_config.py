"""SI inputs shared by rigid-body simulation, annotation and Cycles replay."""
from __future__ import annotations
import copy
import hashlib
import json
import math

BASELINE = {
    "physics": {
        "units": {"length": "m", "mass": "kg", "time": "s", "up_axis": "Z", "motion_axis": "X"},
        "gravity": [0., 0., -9.81],
        "ramp": {"horizontal_length_per_side_m": .5, "rise_m": .12,
                 "central_length_m": .20, "width_m": .25, "toe_transition_m": .035,
                 "central_surface_z_m": .79, "board_thickness_m": .014,
                 "table_top_z_m": .76, "restitution": 0., "lateral_friction": .3,
                 "rolling_friction": .00002, "spinning_friction": .00001},
        "balls": {
            name: {"radius_m": .025, "mass_kg": .075, "restitution": .98,
                   "lateral_friction": .3, "rolling_friction": .00002, "spinning_friction": .00001,
                   "inertia_factor": .4, "linear_damping": 0., "angular_damping": 0.,
                   "release_contact_abs_x_m": .53165, "initial_y_m": 0.,
                   "initial_velocity_m_per_s": [0., 0., 0.],
                   "initial_angular_velocity_rad_per_s": [0., 0., 0.],
                   "initial_quaternion_xyzw": [0., 0., 0., 1.], "present": True}
            for name in ["B_left", "B_right"]},
    },
    "simulation_quality": {"substeps_per_frame": 640, "solver_iterations": 100, "contact_erp": 0.,
        "contact_breaking_threshold_m": .00001, "contact_slop_m": .0000005,
        "collision_margin_m": 0., "restitution_velocity_threshold_m_per_s": .01,
        "split_impulse": True, "trajectory_hz": 240, "toe_segments": 48,
        "contact_force_threshold_N": .000001},
    "appearance": {'preset': 'natural_home_realism',
     'seed': 409031,
     'camera': {'location': [0.29, -1.99, 1.57],
                'target': [0.0, 0.025, 0.84],
                'lens_mm': 50.0,
                'sensor_width_mm': 36.0,
                'dof_enabled': True,
                'fstop': 8.0},
     'wood': {'asset': 'plywood',
              'repeat_m': 0.5,
              'table_asset': 'authored_laminate_steel_activity_table',
              'table_target_dimensions_m': [1.72, 0.86, 0.76],
              'grain_image_axis': 'U'},
     'ball': {'red_srgb': [0.73, 0.065, 0.045],
              'blue_srgb': [0.045, 0.27, 0.64],
              'roughness': 0.12,
              'coat_weight': 0.6,
              'roughness_range': [0.1, 0.15],
              'style': 'Cast hard-resin play balls with two plain ivory spots, no printed characters',
              'ivory_srgb': [0.88, 0.86, 0.79],
              'medallion_axis': [0.0, -0.92, 0.38],
              'medallion_angle_rad': 0.28,
              'coat_roughness': 0.04},
     'environment_strength': 6.0,
     'environment_rotation_rad': 0.6,
     'construction': {'open_transverse_trestles': True,
                      'table_plank_count': 0,
                      'ply_layers': 7,
                      'running_surface_displacement_m': 0.0,
                      'outer_edge_bevel_m': 0.0003,
                      'finite_room': True,
                      'table_original_materials': False,
                      'ply_glue_lines': 'thin irregular adhesive lines, 7 plies',
                      'finish_variation': True,
                      'lighting': 'Daylight only: the overcast residential_garden HDRI enters the closed room '
                                  'through the rear window and a second, out-of-frame casement in the left wall; '
                                  'both openings carry non-emitting Cycles portals; no lamps or hidden fill'},
     'background': {'books': None,
                    'chair': None,
                    'plant': 'potted_plant_02',
                    'curtain': 'Fabric034 with irregular gathered geometry',
                    'environment': 'residential_garden_4k',
                    'plant_placement': 'real window ledge',
                    'pencils': 0,
                    'book_count': 0,
                    'tabletop_props': ['alarm_clock_01', 'measuring_tape_01'],
                    'window': 'rebated painted timber double-glazed casement with recessed seals and latch',
                    'prop_texture_max_px': 2048,
                    'prop_selection': 'New asset IDs absent from existing PCVE scripts and manifests at pre-edit '
                                      'scan; no chairs'},
     'imaging': {'look': 'AgX - Medium High Contrast',
                 'exposure_stops': 1.8,
                 'gamma': 1.0,
                 'quaternion_interpolation': 'hemisphere-continuous equivalent solver quaternions'},
     'asset_manifest': 'realism_assets.json',
     'table': {'dimensions_m': [1.72, 0.86, 0.76],
               'top_thickness_m': 0.025,
               'corner_radius_m': 0.018,
               'top_srgb': [0.66, 0.665, 0.635],
               'frame_srgb': [0.43, 0.45, 0.435],
               'roughness': 0.49},
     'room_detail': {'curtain_forward_offset_m': 0.18,
                     'tile_pitch_m': 0.6,
                     'tile_joint_m': 0.002,
                     'tile_grid_origin_m': [0.0, 0.05],
                     'floor_srgb': [0.61, 0.605, 0.57],
                     'skirting_height_m': 0.096,
                     'purpose': 'Clear both linen panels from sill/masonry and establish visible floor depth '
                                'under table'},
     'window_portal': {'location': [-0.97, 1.516, 1.55],
                       'target': [-0.97, 0.0, 1.55],
                       'size_m': [1.26, 1.46],
                       'purpose': 'Cycles light portal covering the masonry window opening; emits nothing, only '
                                  'guides sky sampling'},
     'side_window': {'opening_y_m': [-1.45, -0.25],
                     'opening_z_m': [0.85, 2.25],
                     'portal_x_m': -2.455,
                     'purpose': 'Ordinary second casement in the left return wall, outside the camera frustum; '
                                'daylight enters through it'},
     'wall_paint': {'asset': 'beige_wall_001',
                    'repeat_m': 3.0,
                    'uv_seed': 5501,
                    'saturation': 0.4,
                    'value': 1.38,
                    'roughness_range': [0.78, 0.94],
                    'normal_strength': 0.6},
     'table_wear': {'asset': 'SurfaceImperfections018',
                    'repeat_m': 0.6,
                    'offset_m': [0.13, 0.41],
                    'rotation_rad': 0.37,
                    'map_from': [0.2, 0.7],
                    'roughness_range': [0.2, 0.5],
                    'specular_ior_level': 0.5},
     'floor_wear': {'asset': 'SurfaceImperfections018',
                    'repeat_m': 0.9,
                    'offset_m': [0.57, 0.21],
                    'rotation_rad': 1.21,
                    'map_from': [0.2, 0.7],
                    'roughness_range': [0.52, 0.8],
                    'albedo_scale': [1.03, 0.94]}},
    "render": {'resolution': [1280, 720],
     'fps': 24,
     'duration_sec': 4.0,
     'samples': 64,
     'engine': 'CYCLES',
     'denoising': True,
     'denoising_use_gpu': True,
     'motion_blur_shutter_frames': 0.25,
     'color_management': 'AgX',
     'persistent_data': False},
}

CASES = {"source": {}, "edit_heavy_left": {"physics": {"balls": {"B_left": {"mass_kg": .1125}}}},
         "edit_low_restitution": {"physics": {"balls": {"B_left": {"restitution": .55}, "B_right": {"restitution": .55}}}},
         "edit_remove_right": {"physics": {"balls": {"B_right": {"present": False}}}}}

def merge(base, updates):
    result = copy.deepcopy(base)
    for k,v in updates.items():
        if k not in result: raise ValueError(f"Unknown configuration field: {k}")
        result[k] = merge(result[k],v) if isinstance(v,dict) and isinstance(result[k],dict) else copy.deepcopy(v)
    return result

def scenario(case="source", overrides=None):
    return merge(merge(BASELINE, CASES[case]), overrides or {})

def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def visual_override(configuration,override):
    """Only appearance and an explicitly recorded photographic shutter may change."""
    if 'appearance' not in override or set(override)-{'appearance','render'}:
        raise ValueError('Visual override contains unsupported configuration groups')
    result=copy.deepcopy(configuration);result['appearance']=copy.deepcopy(override['appearance'])
    render=override.get('render',{})
    if set(render)-{'motion_blur_shutter_frames','persistent_data'}:raise ValueError('Pixels, samples, frame rate and duration must stay frozen')
    if 'motion_blur_shutter_frames' in render:
        value=render['motion_blur_shutter_frames']
        if not 0.<=value<=.5:raise ValueError('Realism shutter must remain at most half a video frame')
        result['render']['motion_blur_shutter_frames']=value
    if 'persistent_data' in render:
        if not isinstance(render['persistent_data'],bool):raise ValueError('Persistent-data option must be boolean')
        result['render']['persistent_data']=render['persistent_data']
    return result

def visual_difference(path):
    return path.startswith('appearance.') or path in ['render.motion_blur_shutter_frames','render.persistent_data']

def formal_quality_equal(before,after):
    return {k:v for k,v in before['render'].items() if k not in ['motion_blur_shutter_frames','persistent_data']}=={k:v for k,v in after['render'].items() if k not in ['motion_blur_shutter_frames','persistent_data']}

def differences(a,b,prefix=""):
    if isinstance(a,dict) and isinstance(b,dict):
        result={}
        for k in sorted(a.keys()|b.keys()): result.update(differences(a.get(k),b.get(k),f"{prefix}.{k}".strip(".")))
        return result
    return {} if a==b else {prefix:{"before":a,"after":b}}

def surface(cfg,x):
    r=cfg["physics"]["ramp"];d=abs(x)-r["central_length_m"]/2
    a=r["toe_transition_m"];m=r["rise_m"]/(r["horizontal_length_per_side_m"]-a/2)
    if d<=0: return r["central_surface_z_m"],0.
    h,s=(m*d*d/(2*a),m*d/a) if d<a else (m*(d-a/2),m)
    return r["central_surface_z_m"]+h, math.copysign(s,x)

def initial_position(cfg,name):
    b=cfg["physics"]["balls"][name];x=b["release_contact_abs_x_m"]*(-1 if name=="B_left" else 1)
    z,slope=surface(cfg,x);norm=math.sqrt(1+slope*slope)
    return [x-b["radius_m"]*slope/norm,b["initial_y_m"],z+b["radius_m"]/norm]

def profile(cfg):
    r=cfg["physics"]["ramp"];c=r["central_length_m"]/2;a=r["toe_transition_m"];n=cfg["simulation_quality"]["toe_segments"]
    half=[0.,c]+[c+a*i/n for i in range(1,n+1)]+[c+r["horizontal_length_per_side_m"]]
    xs=[-x for x in half[:0:-1]]+half
    return [(x,surface(cfg,x)[0]) for x in xs]

def ramp_mesh(cfg):
    r=cfg["physics"]["ramp"];p=profile(cfg);w=r["width_m"]/2;t=r["board_thickness_m"];n=len(p)
    vertices=[(x,y,z-drop) for drop in [0.,t] for y in [-w,w] for x,z in p]
    faces=[]
    for i in range(n-1):
        faces += [(i,i+1,n+i+1,n+i), (2*n+i,3*n+i,3*n+i+1,2*n+i+1),
                  (i,2*n+i,2*n+i+1,i+1),(n+i,n+i+1,3*n+i+1,3*n+i)]
    faces += [(0,n,3*n,2*n),(n-1,3*n-1,4*n-1,2*n-1)]
    return vertices,faces
