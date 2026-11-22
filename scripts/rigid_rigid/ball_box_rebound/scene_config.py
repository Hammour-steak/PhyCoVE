"""SI-scale rigid toy rebound; physics, quality, appearance and render are separate."""
from __future__ import annotations

import copy
import hashlib
import json

SCENE = "ball_box_rebound"
SUPPORTED_CASES = (
    "source", "edit_high_restitution", "edit_low_restitution",
    "edit_fast_initial_velocity", "edit_slow_initial_velocity",
    "edit_high_ball_friction", "edit_high_football_friction",
    "edit_remove_football", "edit_remove_football_at_2s",
)
BASELINE = {
    "physics": {
        "units": {"length": "m", "mass": "kg", "time": "s", "up_axis": "Z"},
        "gravity": [0.0, 0.0, -9.81],
        "ball": {
            "id": "B01", "radius_m": 0.09, "mass_kg": 0.32,
            "inertia_factor": 0.6666666666666666,
            "initial_position_m": [-0.95, -0.75, 0.09001],
            "initial_quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
            "initial_velocity_m_per_s": [1.10, 1.10, 0.0],
            "initial_angular_velocity_rad_per_s": [-12.2222222222222, 12.2222222222222, 0.0],
            "restitution": 0.90, "lateral_friction": 0.32,
            "rolling_friction": 0.006, "spinning_friction": 0.0002,
            "linear_damping": 0.0, "angular_damping": 0.0,
        },
        "box": {
            "id": "C01", "dimensions_m": [0.72, 0.44, 0.40], "mass_kg": 8.0,
            "initial_position_m": [-0.10, 0.45, 0.20001],
            "initial_quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
            "restitution": 0.95, "lateral_friction": 0.18,
            "rolling_friction": 0.0, "spinning_friction": 0.0,
            "linear_damping": 0.0, "angular_damping": 0.0,
        },
        "football": {
            "id": "B02", "radius_m": 0.11, "mass_kg": 0.43,
            "remove_at_sec": None,
            "inertia_factor": 0.6666666666666666,
            "initial_position_m": [0.5648608467675057, -0.07256732223649942, 0.11001],
            "initial_quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
            "restitution": 0.62, "lateral_friction": 0.50,
            "rolling_friction": 0.002, "spinning_friction": 0.0002,
            "linear_damping": 0.0, "angular_damping": 0.0,
        },
        "floor": {
            "id": "F01", "dimensions_m": [8.0, 8.0, 0.12], "top_z_m": 0.0,
            "restitution": 0.04, "lateral_friction": 0.55,
        },
        "model": "Three free six-DOF rigid bodies on a fixed floor. Initial no-slip roll is set once; all subsequent motion comes from solved gravity, contact, restitution and Coulomb/rolling friction. The white storage box contains ballast. The 18 cm, 0.32 kg hard star toy ball uses a rigid thin-shell inertia approximation; the football is a rigid spherical approximation of an inflated 22 cm, 430 g ball with thin-shell inertia, without resolved shell deformation. No trajectory constraints, post-contact impulses, pose correction or deformation.",
    },
    "simulation_quality": {
        "substeps_per_frame": 80, "solver_iterations": 100, "trajectory_hz": 480,
        "contact_slop_m": 0.00001, "contact_breaking_threshold_m": 0.0002,
        "restitution_velocity_threshold_m_per_s": 0.04,
        "use_split_impulse": True, "split_impulse_penetration_threshold_m": 0.0,
        "contact_erp": 0.08,
    },
    "appearance": {
        "preset": "documentary_playroom", "seed": 4090, "exposure_stops": 3.10,
        "material_asset_directory": "scenes/ball_box_rebound/material_textures",
        "light_energy_scale": 0.28,
        "environment_refinement": {"enabled": True},
        "daylight": {"strength": 0.70, "rotation_degrees": 195.0,
                     "filtered_sun_energy": 1.25, "filtered_sun_angle_degrees": 8.0,
                     "sun_position_m": [-5.2, 0.0, 3.4], "sun_target_m": [0.0, 0.4, 0.0]},
        "room_dimensions_m": [6.5, 8.75, 2.8],
        "camera": {"position_m": [1.45, -3.80, 1.45],
                   "target_m": [-0.32, 0.27, 0.25], "lens_mm": 48.0,
                   "sensor_width_mm": 36.0, "aperture_fstop": 5.6, "focus_distance_m": 4.35},
        "scene_edits": {"curtain_depth_m": 0.11, "curtain_sill_clearance_m": 0.03,
                        "rocking_horse_offset_m": [-0.23, -0.18, 0.0],
                        "cabinet_car_asset": "vintage_fiat_500", "cabinet_car_length_m": 0.20, "football_asset": "stitched_soccer_ball",
                        "toy_chest_asset": "sketchfab/hayley_toy_box",
                        "toy_ball_asset": "sketchfab/hayley_toy_box/Ball1",
                        "chest_lower_rail_transition_m": [0.03, 0.08, 0.115, 0.328]},
        "finish": {"floor_roughness": [0.25, 0.43], "floor_normal_strength": 0.11,
                   "bin_roughness": [0.25, 0.44], "bin_normal_strength": 0.25,
                   "ball_roughness": [0.18, 0.28], "block_roughness": [0.19, 0.31]},
        "colors_srgb": {"ball": [0.87, 0.44, 0.44], "box": [0.87, 0.87, 0.85],
                        "block": [1.0, 0.82, 0.005]},
        "star_ball_finish": {"body_srgb": [0.80, 0.30, 0.31], "star_srgb": [0.95, 0.91, 0.81],
                             "star_count": 14, "seed": 17, "star_radius_rad": [0.25, 0.17],
                             "star_inner_ratio": 0.48, "print_edge_rad": 0.004,
                             "print_texture_px": [2048, 1024], "print_wear": 0.18,
                             "roughness": [0.30, 0.40], "print_roughness_offset": 0.06,
                             "coat_weight": 0.22, "coat_roughness": 0.16},
        "football_scuff_strength": 0.20,
        "floor_finish": {"asset": "polyhaven/wood_floor", "resolution": "4k", "tile_m": 1.7,
                         "rotation_degrees": 0.0, "offset_m": [0.13, 0.41],
                         "saturation": 0.88, "value": 1.12, "roughness": [0.24, 0.52],
                         "normal_strength": 0.45, "coat_weight": 0.10, "coat_roughness": 0.22},
    },
    "render": {
        "resolution": [1280, 720], "fps": 24, "duration_sec": 4.0, "total_frames": 96,
        "samples": 256, "adaptive_threshold": 0.005, "denoising": True,
        "max_bounces": 12, "diffuse_bounces": 8, "glossy_bounces": 3, "transmission_bounces": 6,
        "color_management": "AgX", "motion_blur_shutter_frames": 0.25,
        "encoding": {"codec": "libx264", "crf": 17, "pixel_format": "yuv420p"},
    },
}


# Per-body DELETE time. The football carries it in BASELINE; an override may
# also give it to the star ball or the toy chest (frame 1 only, see scenario).
OPTIONAL_FIELDS = ("remove_at_sec",)


def merge(base, override):
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key not in result and key in OPTIONAL_FIELDS:
            result[key] = copy.deepcopy(value)
            continue
        if key not in result:
            raise ValueError(f"Unknown configuration field: {key}")
        if isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def scenario(override=None, case="source"):
    cfg = merge(BASELINE, override or {})
    if case not in SUPPORTED_CASES:
        raise ValueError(f"Unknown case: {case}")
    if case != "source":
        from edit_vocab import edit_info
        cfg = merge(cfg, edit_info(case, cfg)["physics_override"])
    rd = cfg["render"]
    if rd["total_frames"] != round(rd["fps"] * rd["duration_sec"]):
        raise ValueError("Frame count must equal fps times duration")
    removal = cfg["physics"]["football"]["remove_at_sec"]
    if removal is not None:
        steps = removal * rd["fps"] * cfg["simulation_quality"]["substeps_per_frame"]
        if not 0 <= removal < rd["duration_sec"] or abs(steps - round(steps)) > 1e-8:
            raise ValueError("Removal must lie on a solver step within the clip")
    for name in ("ball", "box"):
        if cfg["physics"][name].get("remove_at_sec") not in (None, 0, 0.0):
            raise ValueError(f"The {name} can only be deleted from frame 1 (remove_at_sec 0)")
    return cfg


def body_present(cfg, name, time_sec):
    removal = cfg["physics"][name].get("remove_at_sec")
    return removal is None or time_sec < removal


def signature(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
