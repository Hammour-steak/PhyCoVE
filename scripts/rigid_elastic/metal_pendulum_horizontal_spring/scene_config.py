"""SI configuration for a real hinge and a guided horizontal compression spring."""

from copy import deepcopy
from math import pi, sqrt

from edits.presets import CASES as CASES
from edits.presets import apply_preset

SCENE = "metal_pendulum_horizontal_spring"

R = 0.018
M0 = 7800 * 4 * pi * R**3 / 3
BASE = {
    "schema_version": 1,
    "scene": SCENE,
    "category": "rigid_elastic",
    "physics": {
        "units": "m, kg, s, Pa; Z up",
        "gravity_m_s2": 9.81,
        "pendulum": {
            "length_m": 0.23,
            "ball_radius_m": R,
            "ball_mass_kg": M0,
            "ball_density_kg_m3": 7800.0,
            "rod_radius_m": 0.0015,
            "rod_density_kg_m3": 7800.0,
            "release_angle_deg": -30.0,
            "initial_angular_velocity_rad_s": 0.0,
            "pivot_m": [0, 0, 0.32],
            "bearing_damping_Nm_s": 0.00065,
        },
        "spring": {
            "present": True,
            "axis": [1, 0, 0],
            "axis_z_m": 0.09,
            "head_rest_center_x_m": 0.027,
            "head_radius_m": 0.022,
            "head_thickness_m": 0.003,
            "head_density_kg_m3": 2700.0,
            "fixed_seat_x_m": 0.126,
            "mean_coil_radius_m": 0.011,
            "wire_radius_m": 0.00045,
            "active_turns": 8,
            "closed_end_turns": 2,
            "young_modulus_Pa": 200e9,
            "poisson_ratio": 0.3,
            "density_kg_m3": 7850.0,
            "guide_rod_radius_m": 0.0012,
            "guide_rod_length_m": 0.134,
            "guide_rod_density_kg_m3": 7800.0,
            "retaining_collar_radius_m": 0.0026,
            "retaining_collar_thickness_m": 0.002,
            "bushing_length_m": 0.013,
            "axial_viscous_damping_N_s_m": 1.0,
            "maximum_guide_stroke_m": 0.065,
        },
        "contact": {
            "model": "Native sphere / planar central area of guided end disk, frictionless; native revolute and prismatic constraints",
            "friction_coefficient": 0.0,
            "solref": [0.0003, 1.0],
            "solimp": [0.95, 0.999, 0.00005],
            "margin_m": 0.0,
        },
    },
    "simulation_quality": {
        "solver": "MuJoCo 3.15.0, native hinge plus guided axial elastic mode k=G*d^4/(8*D^3*Na), spring distributed modal mass",
        "substeps_per_frame": 1024,
        "integrator": "implicitfast",
        "solver_iterations": 50,
        "solver_tolerance": 1e-12,
        "float_precision": "f64",
        "duration_s": 4.0,
        "fps": 24,
        "frames": 96,
        "trace_samples_per_frame": 256,
        "visual_segments_per_turn": 48,
    },
    "appearance": {
        "camera_m": [0.40, -1.02, 0.43],
        "target_m": [-0.006, 0, 0.163],
        "lens_mm": 50.0,
        "base_dimensions_m": [0.43, 0.18, 0.018],
        "base_center_m": [-0.015, 0, 0.013],
        "table_dimensions_m": [1.4, 0.8, 0.028],
        "wood": "Satin-oiled dark hardwood plinth and stand with cross-cut end grain; used wood writing desk",
        "version": "photo_finish",
        "aperture_fstop": 5.6,
        "world_hdri": "small_empty_room_1",
        "world_strength": 0.14,
        "hdri_rotation_deg": 125.0,
        "window_power_W": 50.0,
        "room_bounce_power_W": 10.0,
        "window_visual_shift_x_m": -0.15,
        "upright_visual_top_m": 0.308,
        "upright_visual_bottom_m": 0.022,
        "walnut_scan_span_m": 0.80,
        "walnut_tint_linear": [0.50, 0.40, 0.28],
        "desk_scan_span_m": 0.55,
        "desk_tint_linear": [1.10, 1.10, 1.10],
        "window_position_m": [-0.64, 0.675, 0.66],
        "window_target_m": [-0.64, -0.30, 0.66],
        "window_color_linear": [0.97, 0.985, 1.0],
        "plant_base_m": [0.32, 0.34, 0.00002],
        "books_base_m": [-0.44, 0.31, 0.00002],
        "notebook_base_m": [0.36, 0.10, 0.00002],
        "background_books_height_m": 0.23,
        "background_plant_height_m": 0.30,
        "walnut_texture_span_m": [0.6, 2.4],
        "oak_texture_span_m": [0.6, 2.4],
        "base_corner_radius_m": 0.006,
        "base_edge_radius_m": 0.0018,
        "walnut_saturation": 0.70,
        "base_roughness_range": [0.53, 0.70],
        "stand_roughness_range": [0.45, 0.64],
        "desk_roughness_range": [0.45, 0.68],
        "ball_surface_roughness": 0.19,
        "lighting_revision": True,
        "window_emitter_size_m": [0.58, 0.96],
        "focus_m": [0.0, 0.0, 0.155],
        "fine_wood_scan_span_m": 0.6,
        "fine_wood_tint_linear": [1.05, 0.90, 0.75],
        "room_bounce_position_m": [-0.55, -0.45, 0.62],
        "room_bounce_target_m": [0.0, 0.0, 0.16],
        "room_bounce_size_m": [0.65, 0.85],
        # Photographic finish (appearance/photo_finish.py), applied last.
        "finish": {
            "version": "photo_finish",
            "wall_diffuse": "polyhaven/beige_wall_001/beige_wall_001_diff_4k.jpg",
            "wall_roughness": "polyhaven/beige_wall_001/beige_wall_001_rough_4k.jpg",
            "wall_normal_gl": "polyhaven/beige_wall_001/beige_wall_001_nor_gl_4k.jpg",
            "wall_texture_span_m": 3.0,
            "wall_albedo_gain": [1.62, 1.98, 2.43],
            "wall_roughness_range": [0.78, 0.92],
            "wall_normal_strength": 0.3,
            "view_hdri": "polyhaven/residential_garden/residential_garden_4k.hdr",
            "view_hdri_rotation_deg": -137.0,
            "view_strength": 6.0,
            "view_plane_center_m": [-0.64, 1.6, 0.66],
            "view_plane_size_m": [4.0, 3.0],
            "window_light_center_m": [-0.64, 0.80, 0.66],
            "window_light_size_m": [0.64, 1.0],
            "window_light_power_W": 120.0,
            "window_light_color_linear": [0.94, 0.97, 1.0],
            "sash_x_m": [-0.9675, -0.3125],
            "sash_z_m": [0.15, 1.17],
            "sash_profile_m": [0.045, 0.05],
            "sash_y_m": 0.75,
            "curtain_translucency": 0.55,
            "curtain_openness": 0.45,
            "bob_haze_scale": 90.0,
            "bob_roughness_range": [0.10, 0.24],
            "world_strength": 0.45,
        },
    },
    "render": {
        "engine": "CYCLES",
        "samples": 256,
        "adaptive_threshold": 0.01,
        "denoising": True,
        "resolution": [1280, 720],
        "fps": 24,
        "frames": 96,
        "duration_s": 4.0,
        "motion_blur": True,
        "motion_blur_shutter": 0.25,
        "denoiser": "OPENIMAGEDENOISE",
        "filter_glossy": 0.5,
        "caustics": False,
        "view_transform": "AgX",
        "look": "AgX - Medium High Contrast",
        "exposure": 0.0,
        "seed": 42,
        "max_bounces": 8,
        "codec": "libx264",
        "crf": 17,
        "pixel_format": "yuv420p",
    },
}


def configuration(case="source", overrides=None):
    c = deepcopy(BASE)
    apply_preset(c, case)
    for dotted, value in (overrides or {}).items():
        parts = dotted.split(".")
        obj = c
        for key in parts[:-1]:
            obj = obj[key]
        obj[parts[-1]] = value
    q = c["simulation_quality"]
    q["duration_s"] = q["frames"] / q["fps"]
    p = c["physics"]["pendulum"]
    p["rod_length_m"] = p["length_m"] - p["ball_radius_m"] * 0.5
    p["rod_mass_kg"] = (
        pi * p["rod_radius_m"] ** 2 * p["rod_length_m"] * p["rod_density_kg_m3"]
    )
    p["ball_inertia_cm_kg_m2"] = 0.4 * p["ball_mass_kg"] * p["ball_radius_m"] ** 2
    p["hinge_inertia_kg_m2"] = (
        p["ball_mass_kg"] * p["length_m"] ** 2
        + p["ball_inertia_cm_kg_m2"]
        + p["rod_mass_kg"] * p["rod_length_m"] ** 2 / 3
    )
    s = c["physics"]["spring"]
    d = 2 * s["wire_radius_m"]
    D = 2 * s["mean_coil_radius_m"]
    n = s["active_turns"]
    s["shear_modulus_Pa"] = s["young_modulus_Pa"] / (2 * (1 + s["poisson_ratio"]))
    s["axial_stiffness_N_m"] = s["shear_modulus_Pa"] * d**4 / (8 * D**3 * n)
    s["free_length_m"] = (
        s["fixed_seat_x_m"] - s["head_rest_center_x_m"] - s["head_thickness_m"] / 2
    )
    s["active_length_m"] = s["free_length_m"] - s["closed_end_turns"] * d
    active_wire = sqrt((pi * D * n) ** 2 + s["active_length_m"] ** 2)
    end_wire = sqrt((pi * D) ** 2 + d * d)
    s["wire_length_m"] = active_wire + s["closed_end_turns"] * end_wire
    area = pi * s["wire_radius_m"] ** 2
    s["wire_mass_kg"] = s["density_kg_m3"] * area * s["wire_length_m"]
    s["spring_effective_axial_mass_kg"] = (
        s["density_kg_m3"] * area * (active_wire / 3 + end_wire)
    )
    s["head_mass_kg"] = (
        s["head_density_kg_m3"] * pi * s["head_radius_m"] ** 2 * s["head_thickness_m"]
    )
    s["guide_rod_mass_kg"] = (
        s["guide_rod_density_kg_m3"]
        * pi
        * s["guide_rod_radius_m"] ** 2
        * s["guide_rod_length_m"]
    )
    s["retaining_collar_mass_kg"] = (
        p["rod_density_kg_m3"]
        * pi
        * (s["retaining_collar_radius_m"] ** 2 - s["guide_rod_radius_m"] ** 2)
        * s["retaining_collar_thickness_m"]
    )
    s["slider_effective_mass_kg"] = (
        s["head_mass_kg"]
        + s["guide_rod_mass_kg"]
        + s["spring_effective_axial_mass_kg"]
        + s["retaining_collar_mass_kg"]
    )
    s["solid_length_m"] = (n + s["closed_end_turns"]) * d
    s["wahl_factor"] = (4 * (D / d) - 1) / (4 * (D / d) - 4) + 0.615 / (D / d)
    return c
