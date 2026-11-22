"""SI-scale basketball source; physical, numerical and visual inputs are separate."""
from __future__ import annotations
import copy
import hashlib
import json

SCENE = "basketball_court_bounce"
CASES = ("source", "low_restitution", "high_restitution", "remove_ball", "heavy_ball", "restitution_at_1s")
BASELINE = {
    "physics": {
        "units": {"length": "m", "mass": "kg", "time": "s", "up_axis": "Z"},
        "gravity": [0.0, 0.0, -9.81],
        "ball": {
            "id": "B01", "radius_m": 0.12, "mass_kg": 0.625,
            "inertia_factor": 2.0 / 3.0,
            "initial_position_m": [0.0, -0.6, 1.62],
            "initial_quaternion_xyzw": [0.106714, 0.068547, 0.166586, 0.977863],
            "initial_velocity_m_per_s": [0.0, 0.0, 0.0],
            "initial_angular_velocity_rad_per_s": [0.0, 0.0, 0.0],
            "restitution": 0.76, "lateral_friction": 0.70,
            "rolling_friction": 0.001, "spinning_friction": 0.001,
            "linear_damping": 0.0, "angular_damping": 0.0,
        },
        "floor": {
            "id": "F01", "dimensions_m": [18.0, 32.0, 0.12],
            "top_z_m": 0.0, "restitution": 1.0, "lateral_friction": 0.60,
        },
        "model": "Free six-DOF hollow rigid sphere against a fixed rigid wood floor; effective restitution models the aggregate ball/floor collision. No deformation, air drag, imposed trajectory or external impulses.",
    },
    "simulation_quality": {
        "substeps_per_frame": 80, "solver_iterations": 80,
        "trajectory_hz": 480, "contact_slop_m": 0.00001,
        "contact_breaking_threshold_m": 0.0002,
        "restitution_velocity_threshold_m_per_s": 0.08,
        "use_split_impulse": True, "split_impulse_penetration_threshold_m": 0.0,
        "contact_erp": 0.0,
    },
    "appearance": {
        "preset": 'gym_look', "seed": 4090,
        "court_dimensions_m": [15.0, 28.0], "court_line_width_m": 0.05,
        "plank_width_m": 0.05715, "plank_nominal_length_m": 1.80,
        "wood_asset": "bowling_documentary/white_maple_veneer",
        "basketball_asset": "innerscene/basketball",
        "ball_visual_rotation_euler_deg": [0.0, 0.0, 45.0],
        "ball_print_text": None,
        "floor_surface_model": "strip_maple",
        "floor_scan_asset": "polyhaven/wood_floor", "floor_scan_repeat_m": 1.7,
        "floor_scan_tint_rgb": [1.12, 0.98, 0.80],
        "plank_joint_width_m": 0.0003, "floor_normal_strength": 0.1,
        "daylight_asset": "polyhaven/residential_garden",
        "daylight_strength": 1.0, "daylight_rotation_deg": 73.0,
        "daylight_coordinates": "Generated",
        "ball_specular_ior_level": 0.42, "ball_roughness_range": [0.48, 0.62],
        "ball_normal_strength": 0.75,
        "floor_tint_rgb": [0.65, 0.46, 0.25],
        "floor_coat_weight": 0.72, "floor_coat_roughness": 0.17,
        "floor_coat_roughness_range": [0.12, 0.22],
        "floor_roughness_range": [0.34, 0.46],
        "floor_swell_m": 0.00012, "plank_tilt_rad": 0.00015,
        "court_key_rgb": [0.035, 0.085, 0.21],
        "light_energy_watts": {"left_window": 180, "ceiling": 50, "right_fill": 70},
        "sun": {"strength": 14.0, "elevation_deg": 20.0, "yaw_deg": 35.0, "angular_diameter_deg": 2.4, "rgb": [1.0, 0.91, 0.79]},
        "lens_response": {"glow_threshold": 6.0, "glow_size": 7, "glow_mix": -0.98, "dispersion": 0.00035, "vignette_edge": 0.9},
        "camera": {"position_m": [2.0, -6.15, 1.20],
                   "target_m": [0.0, -0.6, 1.0], "lens_mm": 46.0,
                   "sensor_width_mm": 36.0, "dof_fstop": 16,
                   "focus_point_m": [0.0, -0.6, 0.9]},
        "room_dimensions_m": [18.0, 32.0, 7.0],
        "wall_dado_height_m": 1.20,
        "wall_dado_rgb": [0.045, 0.10, 0.23],
        "wall_upper_rgb": [0.66, 0.62, 0.52],
        "wall_stripe_rgb": [0.66, 0.44, 0.07], "wall_stripe_height_m": 0.10,
        "wall_relief_asset": "polyhaven/concrete_block_wall",
        "wall_relief_tile_m": [2.0, 1.6], "wall_relief_depth_m": 0.006,
        "wall_joint_height_range": [0.62, 0.68], "wall_joint_shade": 0.84,
        "bleacher_wood_asset": "polyhaven/oak_veneer_01", "bleacher_wood_tint_rgb": [0.62, 0.48, 0.34],
        "basket_pad_rgb": [0.022, 0.05, 0.135], "door_rgb": [0.05, 0.10, 0.22],
        "prop_broom_asset": "polyhaven/plastic_broom", "prop_broom_yaw_deg": 0.0,
        "prop_clock_asset": "polyhaven/wall_clock", "prop_clock_yaw_deg": 0.0,
        "ball_cover_tint_rgb": [0.86, 0.74, 0.66], "ball_grime_rgb": [0.74, 0.70, 0.66],
        "wall_mortar_width_m": 0.0035, "wall_mortar_depth_m": 0.002,
        "basket_wall_pad_dimensions_m": [4.2, 1.8, 0.045],
        "basket_wall_pad_enabled": False,
        "bench_props_enabled": False, "wall_extinguisher_enabled": False,
        "ball_pebble_spacing_m": 0.0015, "ball_seam_width_m": 0.0038,
        "bench_towel": {"center_x_m": -5.1, "width_m": 0.55, "rear_y_m": 15.60,
                        "hanging_length_m": 0.165, "thickness_m": 0.0024, "surface_clearance_m": 0.0004},
        "furniture_wood_tint_rgb": [0.59, 0.43, 0.27],
        "furniture": {
            "bench": {"length_m": 2.60, "centre_y_m": 15.46,
                      "centres_x_m": [-4.4, 4.5], "seat_top_m": 0.455},
            "bin": {"centre_xy_m": [-2.55, 15.62]},
        },
        "backstop": {"truss_x_m": [-0.42, 0.42], "top_chord_z_m": 3.90, "bottom_chord_z_m": 3.02,
                     "panels": 4, "steel_rgb": [0.035, 0.040, 0.043]},
        "bleacher_sections": {"section_count": 3, "tint_rgb": [0.60, 0.45, 0.28]},
    },
    "render": {
        "resolution": [1280, 720], "fps": 24, "duration_sec": 4.0,
        "total_frames": 96, "samples": 128, "adaptive_threshold": 0.008,
        "denoising": True, "color_management": "AgX", "exposure": 0.0,
        "motion_blur_shutter_frames": 0.25, "ball_motion_steps": 3,
        "max_bounces": 14, "diffuse_bounces": 8, "glossy_bounces": 6,
        "view_look": "AgX - High Contrast", "film_grain_sigma_8bit": 0.45,
        "persistent_data": False,
        "encoding": {"codec": "libx264", "crf": 17, "pixel_format": "yuv420p"},
    },
}

def merge(base, override, prefix=""):
    result = copy.deepcopy(base)
    for key, value in override.items():
        path=(prefix+"."+key).lstrip(".")
        if key not in result:
            if path in ["physics.ball.present","physics.timed_edits"]:
                result[key]=copy.deepcopy(value)
                continue
            raise ValueError(f"Unknown configuration field: {path}")
        if isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge(result[key], value, path)
        else:
            result[key] = copy.deepcopy(value)
    return result

def scenario(override=None, case="source"):
    if case not in CASES:
        raise ValueError(f"Unknown case: {case}")
    cfg = merge(BASELINE, override or {})
    if case != "source":
        if cfg["physics"]["ball"]["restitution"] != BASELINE["physics"]["ball"]["restitution"]:
            raise ValueError("A declared edit requires the baseline source restitution")
        if case in ["low_restitution","high_restitution"]:
            cfg["physics"]["ball"]["restitution"] = {"low_restitution":.38,"high_restitution":.95}[case]
        elif case=="remove_ball":
            cfg["physics"]["ball"]["present"]=False
        elif case=="heavy_ball":
            if cfg["physics"]["ball"]["mass_kg"]!=.625:raise ValueError("Declared mass edit requires source mass 0.625 kg")
            cfg["physics"]["ball"]["mass_kg"]=1.25
        elif case=="restitution_at_1s":
            cfg["physics"]["timed_edits"]=[{"frame":25,"params":{"ball_restitution":.95}}]
    r = cfg["render"]
    if r["total_frames"] != round(r["fps"] * r["duration_sec"]):
        raise ValueError("Frame count must equal fps times duration")
    return cfg

def signature(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
