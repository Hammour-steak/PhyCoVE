"""Scene-owned SI inputs, isolated physical edits and measured construction."""
from __future__ import annotations
import copy
import hashlib
import json
import math

BASELINE = {
    "physics": {
        "units": {"length": "m", "mass": "kg", "time": "s", "up_axis": "Z"},
        "gravity": [0., 0., -9.81],
        "balls": {
            name: {"present": True, "radius_m": .03, "mass_kg": .12,
                   "inertia_factor": .4, "release_angle_deg": 35.,
                   "initial_linear_velocity": [0., 0., 0.],
                   "initial_angular_velocity": [0., 0., 0.],
                   "linear_drag_per_s": .012, "angular_drag_per_s": .008}
            for name in ["B_left", "B_right"]},
        "ropes": {
            name: {"present": True, "anchor_m": [x, 0., 1.60],
                   "attachment_local_m": [0., 0., .0365], "length_m": .5635,
                   "bend_damping_rate_per_s": 30.}
            for name,x in [("B_left", -.03), ("B_right", .03)]},
        "contacts": {"ball_ball": {"restitution": .90, "friction": .12},
                     "ball_fixture": {"restitution": .22, "friction": .35},
                     "ball_table": {"restitution": .28, "friction": .32}},
        "fixture": {"table_top_z_m": .76, "table_dimensions_m": [1.86, .88, .036],
                    "base_dimensions_m": [1.54, .35, .025],
                    "post_abs_x_m": .70, "post_dimensions_m": [.030, .030, .84],
                    "beam_dimensions_m": [1.43, .030, .030], "beam_center_z_m": 1.640},
    },
    "simulation_quality": {
        "substeps_per_frame": 640, "solver_iterations": 32,
        "rope_residual_tolerance_m": 2.e-11, "impulse_tolerance_Ns": 1.e-12,
        "contact_activation_gap_m": 0., "restitution_velocity_threshold_m_per_s": .015,
        "trajectory_hz": 240, "no_contact_velocity_bias": True,
    },
    "appearance": {
        "preset": "furnished_daylight_room", "seed": 409035,
        "camera": {"location": [.62, -2.80, 2.05], "target": [0., .04, 1.20],
                   "lens_mm": 45., "sensor_width_mm": 36.},
        "wood": {"table_asset": "blenderkit_bdff957c_steel_base_with_scanned_timber_top", "table_repeat_m": 1.5,
                 "longitudinal_grain_per_member": True},
        "tabletop": {"surface_asset": "wood_table_001", "board_count": 5,
                     "glue_joint_width_m": .00020, "edge_radius_m": .0015,
                     "roughness_range": [.50, .72], "normal_strength": .32,
                     "finish": "satin_oil_with_handling_smudges"},
        "base_board": {"surface_asset": "plywood", "repeat_m": .50, "roughness_range": [.55, .74],
                       "normal_strength": .30, "ply_pitch_m": .0019},
        "room": {"rear_wall_center_y_m": 3.20, "wall_thickness_m": .20,
                 "width_m": 6.4, "front_wall_y_m": -3.90, "height_m": 2.80,
                 "window_center_m": [-1.30, 3.20, 1.56],
                 "extra_windows": [{"wall": "left", "center_m": -.40, "center_z_m": 1.56},
                                   {"wall": "left", "center_m": -1.75, "center_z_m": 1.56},
                                   {"wall": "front", "center_m": -.90, "center_z_m": 1.56}],
                 "floor": {"asset": "wood_floor", "tile_m": 1.70, "offset": [.31, .17],
                           "saturation": .92, "value": .92, "roughness_range": [.42, .70], "normal_strength": .55}},
        "furniture": {"cabinet": {"asset": "drawer_cabinet", "center_xy_m": [1.18, 2.815], "rotation_z_deg": 0.},
                      "basket": {"asset": "wicker_basket_01", "center_xy_m": [.93, 2.83], "rotation_z_deg": 4., "surface_index": 2},
                      "succulent": {"asset": "potted_plant_04", "center_xy_m": [1.42, 2.80], "rotation_z_deg": -35., "surface_index": 1},
                      "floor_plant": {"asset": "potted_plant_01", "center_xy_m": [-2.64, 2.62], "rotation_z_deg": 40.}},
        "props": {"asset": "scene_specific_brass_and_glass_hourglass",
                  "center_m": [.53, .32, .760], "height_m": .195,
                  "radius_m": .053, "glass_wall_m": .0011,
                  "sand_state": "fully_settled_lower_bulb",
                  "stationery": {"notebook_center_m": [-.49, .330, .760],
                                 "notebook_rotation_z_rad": .08,
                                 "measuring_tape_asset": "polyhaven_measuring_tape_01",
                                 "tape_label_uv_rect": [.538, .582, .712, .757],
                                 "provenance": "Notebook and tape restored from the earlier version of this same scene at user request"},
                  "provenance": "Authored for opposing_pendulum_collision; no props or room imported from another scene"},
        "frame": {"profile": "30x30_slot8_anodized_aluminium_extrusion", "slot_width_m": .008,
                  "corner_bracket_leg_m": .028, "end_cap": "black_polyamide"},
        "ball": {"material": "solid_pigmented_ABS", "density_g_per_cm3": 1.05,
                 "red_srgb": [.66, .035, .030], "blue_srgb": [.035, .115, .52],
                 "roughness": .12, "roughness_range": [.10, .17], "ior": 1.53},
        "rope": {"radius_m": .001, "braid_pitch_m": .0062, "color_srgb": [.055, .055, .06]},
        "sky": {"asset": "polyhaven/suburban_field_01/suburban_field_01_4k.hdr", "strength": 1.0,
                "rotation_deg": 75.},
        "window_asset": "blenderkit_7f77e8d9_sliding_window",
    },
    "render": {"resolution": [1280, 720], "fps": 24, "duration_sec": 4.,
               "samples": 256, "adaptive_threshold": .01, "engine": "CYCLES", "denoising": True,
               "denoiser": "OPENIMAGEDENOISE", "denoising_use_gpu": True, "motion_blur_shutter_frames": .5,
               "exposure_ev": 5.7, "white_balance_k": 7000., "color_management": "AgX",
               "depth_of_field": {"fstop": 4., "focus_point_m": [0., 0., 1.10]},
               "vignette_strength": .18},
}

CASES = {
    "source": {},
    "edit_heavy_left": {"physics": {"balls": {"B_left": {"mass_kg": .36}}}},
    "edit_low_restitution": {"physics": {"contacts": {"ball_ball": {"restitution": .25}}}},
    "edit_remove_right": {"physics": {"balls": {"B_right": {"present": False}},
                                       "ropes": {"B_right": {"present": False}}}},
    "edit_remove_left_rope": {"physics": {"ropes": {"B_left": {"present": False}}}},
}

ASSET_MANIFEST_PATHS = [
    "assets/polyhaven/plywood/asset_manifest.json",
    "assets/polyhaven/wood_table_001/asset_manifest.json",
    "assets/polyhaven/measuring_tape_01/asset_manifest.json",
    "assets/polyhaven/suburban_field_01/asset_manifest.json",
    "assets/blenderkit/pendulum_wood_metal_table/asset_manifest.json",
    "assets/blenderkit/pendulum_sliding_window/asset_manifest.json",
    "assets/architecture_pbr/asset_manifest.json",
    # Scanned floor and furniture.
    "assets/polyhaven/wood_floor/asset_manifest.json",
    "assets/polyhaven/drawer_cabinet/asset_manifest.json",
    "assets/polyhaven/wicker_basket_01/asset_manifest.json",
    "assets/polyhaven/potted_plant_04/asset_manifest.json",
    "assets/polyhaven_models/asset_manifest.json",
]

def merge(base, updates):
    result=copy.deepcopy(base)
    for k,v in updates.items():
        if k not in result: raise ValueError("Unknown configuration field: "+k)
        result[k]=merge(result[k],v) if isinstance(v,dict) and isinstance(result[k],dict) else copy.deepcopy(v)
    return result

def scenario(case="source", overrides=None):
    return merge(merge(BASELINE,CASES[case]),overrides or {})

def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def differences(a,b,prefix=""):
    if isinstance(a,dict) and isinstance(b,dict):
        result={}
        for k in sorted(a.keys()|b.keys()): result.update(differences(a.get(k),b.get(k),f"{prefix}.{k}".strip(".")))
        return result
    return {} if a==b else {prefix:{"before":a,"after":b}}

def construction(cfg):
    """Exact collision boxes, shared with visible structural members (no guide)."""
    f=cfg["physics"]["fixture"];top=f["table_top_z_m"];bd=f["base_dimensions_m"]
    result=[{"id":"Table", "center":[0.,.04,top-f["table_dimensions_m"][2]/2],
             "dimensions":f["table_dimensions_m"], "material":"table"},
            {"id":"Base", "center":[0.,0.,top+bd[2]/2], "dimensions":bd,"material":"fixture"}]
    pd=f["post_dimensions_m"]
    for side in [-1,1]:
        result.append({"id":"Post_left" if side<0 else "Post_right",
                       "center":[side*f["post_abs_x_m"],0.,top+bd[2]+pd[2]/2],
                       "dimensions":pd,"material":"fixture"})
    result.append({"id":"Beam","center":[0.,0.,f["beam_center_z_m"]],
                   "dimensions":f["beam_dimensions_m"],"material":"fixture"})
    return result

def initial_state(cfg,name):
    b=cfg["physics"]["balls"][name];r=cfg["physics"]["ropes"][name]
    theta=math.radians(b["release_angle_deg"])*(-1 if name=="B_left" else 1)
    effective=r["length_m"]+r["attachment_local_m"][2]
    # Local +Z points toward the suspension; same construction even when removed.
    pos=[r["anchor_m"][0]+effective*math.sin(theta),r["anchor_m"][1],
         r["anchor_m"][2]-effective*math.cos(theta)]
    quat=[0.,math.sin(-theta/2),0.,math.cos(theta/2)]
    return pos,quat

def length_ledger(cfg):
    return {name:{"rope_endpoint_length_m":r["length_m"],
                  "body_attachment_local_m":r["attachment_local_m"],
                  "initial_anchor_to_center_m":r["length_m"]+r["attachment_local_m"][2],
                  "anchor_m":r["anchor_m"],"rope_present":r["present"]}
            for name,r in cfg["physics"]["ropes"].items()}
