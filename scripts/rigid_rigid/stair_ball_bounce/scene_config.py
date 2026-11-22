"""SI-unit inputs, shared by solver, annotations and renderer."""
from __future__ import annotations
import copy
import hashlib
import json

BASELINE = {
    "physics": {
        "units": {"length": "m", "mass": "kg", "time": "s", "up_axis": "Z", "downstairs_axis": "+X"},
        "gravity": [0.0, 0.0, -9.81],
        "ball": {"id": "B01", "radius_m": 0.07, "mass_kg": 0.04,
                 "restitution": 0.55, "lateral_friction": 0.5,
                 "rolling_friction": 0.00115, "spinning_friction": 0.0001,
                 "linear_damping": 0.0, "angular_damping": 0.0,
                 "inertia_factor": 0.6666666666666666,
                 "initial_position_m": [0.038, 0.0, 1.02],
                 "initial_velocity_m_per_s": [1.35, 0.0, 0.0],
                 "initial_angular_velocity_rad_per_s": [0.0, 0.0, 0.0],
                 "initial_quaternion_xyzw": [0.0, 0.0, 0.0, 1.0]},
        "stairs": {"count": 5, "rise_m": 0.16, "tread_m": 0.28, "width_m": 0.90,
                   "edge_radius_m": 0.0025, "restitution": 1.0, "lateral_friction": 0.5,
                   "upper_length_m": 1.0, "lower_length_m": 3.4,
                   "platform_width_m": 6.0, "lower_floor_back_extent_m": 3.0},
    },
    "simulation_quality": {
        "substeps_per_frame": 400, "solver_iterations": 100,
        "collision_margin_m": 0.0, "contact_breaking_threshold_m": 0.00001,
        "contact_processing_threshold_m": 0.0,
        "contact_slop_m": 0.000001, "restitution_velocity_threshold_m_per_s": 0.08,
        "use_split_impulse": True, "split_impulse_penetration_threshold_m": 0.0,
        "edge_arc_segments": 8, "trajectory_hz": 240,
        "contact_force_threshold_N": 0.000001,
    },
    "appearance": {'preset': 'home_oak_stairwell',
     'seed': 409031,
     'camera': {'location': [2.0, -4.4, 1.65],
                'target': [1.8, 0.0, 0.95],
                'lens_mm': 30.0,
                'sensor_width_mm': 36.0},
     'wood': {'asset': 'wood_floor', 'repeat_m': 1.7, 'roughness': 0.48},
     'ball': {'roughness': 0.32,
              'coat_weight': 0.045,
              'red_srgb': [0.86, 0.055, 0.035],
              'yellow_srgb': [1.0, 0.69, 0.035],
              'blue_srgb': [0.035, 0.27, 0.8]},
     'window': {'location': [3.05, 1.05, 2.5],
                'target': [0.8, 0.0, 0.4],
                'power_w': 0.0,
                'size_m': 1.1,
                'opening_x_m': [1.9, 2.8],
                'opening_z_m': [0.85, 1.95]},
     'fill': {'location': [1.8, -2.5, 2.3], 'target': [1.0, 0.0, 0.5], 'power_w': 0.0, 'size_m': 3.0},
     'environment_strength': 12.0},
    "render": {"resolution": [1280, 720], "fps": 24, "duration_sec": 4.0,
               "samples": 64, "engine": "CYCLES", "denoising": True,
               "denoising_use_gpu": True,
               "motion_blur_shutter_frames": 0.0, "color_management": "AgX"},
}

CASES = {"source": None, "edit_low_restitution": 0.165, "edit_high_restitution": 0.649}
INITIAL_VELOCITY_CASES = {"edit_slow_initial_velocity": 0.65, "edit_fast_initial_velocity": 1.58}
FRICTION_CASES = {
    "edit_low_sliding_friction": {"field": "lateral_friction", "value": 0.05},
    "edit_low_rolling_friction": {"field": "rolling_friction", "value": 0.0002},
    "edit_high_rolling_friction": {"field": "rolling_friction", "value": 0.012},
}
COMBINED_FRICTION_CASES = {"edit_high_friction": 5.0}
SUPPORTED_CASES = tuple(CASES) + tuple(INITIAL_VELOCITY_CASES) + tuple(FRICTION_CASES) + tuple(COMBINED_FRICTION_CASES)

def edited_ball_field(case):
    if case in COMBINED_FRICTION_CASES:
        raise ValueError("Combined friction changes two fields; use edited_ball_fields")
    if case in FRICTION_CASES:
        return FRICTION_CASES[case]["field"]
    return "initial_velocity_m_per_s" if case in INITIAL_VELOCITY_CASES else "restitution"

def edited_ball_fields(case):
    if case in COMBINED_FRICTION_CASES:
        return ("lateral_friction", "rolling_friction")
    return (edited_ball_field(case),)

def merge(base, updates):
    result = copy.deepcopy(base)
    for k, v in updates.items():
        if k not in result:
            raise ValueError(f"Unknown configuration field: {k}")
        result[k] = merge(result[k], v) if isinstance(v, dict) and isinstance(result[k], dict) else copy.deepcopy(v)
    return result

def scenario(overrides=None, case="source"):
    cfg = copy.deepcopy(BASELINE)
    if case in COMBINED_FRICTION_CASES:
        for field in edited_ball_fields(case):
            cfg["physics"]["ball"][field] = round(BASELINE["physics"]["ball"][field]*COMBINED_FRICTION_CASES[case], 12)
    elif case in FRICTION_CASES:
        edit = FRICTION_CASES[case]
        cfg["physics"]["ball"][edit["field"]] = edit["value"]
    elif case in INITIAL_VELOCITY_CASES:
        cfg["physics"]["ball"]["initial_velocity_m_per_s"] = [INITIAL_VELOCITY_CASES[case], 0.0, 0.0]
    elif CASES[case] is not None:
        cfg["physics"]["ball"]["restitution"] = CASES[case]
    return merge(cfg, overrides or {})

def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def differences(a, b, prefix=""):
    if isinstance(a, dict) and isinstance(b, dict):
        result = {}
        for k in sorted(a.keys() | b.keys()):
            result.update(differences(a.get(k), b.get(k), f"{prefix}.{k}".strip(".")))
        return result
    return {} if a == b else {prefix: {"before": a, "after": b}}

def colliders(cfg):
    s = cfg["physics"]["stairs"]
    n, h, d, w = s["count"], s["rise_m"], s["tread_m"], s["width_m"]
    objects = [{"id": f"S{i+1:02d}", "xmin": i*d, "xmax": (i+1)*d,
                "ymin": -w/2, "ymax": w/2, "zmin": -0.10, "zmax": (n-i)*h,
                "radius": s["edge_radius_m"]} for i in range(n)]
    objects += [{"id": "upper_platform", "xmin": -s["upper_length_m"], "xmax": 0.0,
                 "ymin": -w/2, "ymax": w/2,
                 "zmin": -0.10, "zmax": (n+1)*h, "radius": s["edge_radius_m"]},
                {"id": "lower_platform", "xmin": -s["lower_floor_back_extent_m"], "xmax": n*d+s["lower_length_m"],
                 "ymin": -s["platform_width_m"]/2, "ymax": s["platform_width_m"]/2,
                 "zmin": -0.10, "zmax": 0.0, "radius": s["edge_radius_m"]}]
    return objects

def rounded_profile(c, segments=8):
    """Convex XZ profile; a 2.5 mm nosing is shared by visual and collision meshes."""
    import math
    x0, x1, z0, z1, r = (c[k] for k in ("xmin", "xmax", "zmin", "zmax", "radius"))
    pts = [(x0, z0), (x1, z0), (x1, z1-r)]
    for j in range(1, segments+1):
        a = j/segments*math.pi/2
        pts.append((x1-r+r*math.cos(a), z1-r+r*math.sin(a)))
    pts.append((x0, z1))
    return pts

def collider_mesh(c, segments=8):
    profile = rounded_profile(c, segments)
    k = len(profile)
    vertices = [(x, c["ymin"], z) for x,z in profile] + [(x, c["ymax"], z) for x,z in profile]
    faces = [tuple(range(k)), tuple(reversed(range(k,2*k)))]
    faces += [(i, i+k, (i+1)%k+k, (i+1)%k) for i in range(k)]
    return vertices, faces
