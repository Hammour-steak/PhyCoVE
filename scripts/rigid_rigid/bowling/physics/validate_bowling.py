"""Independent acceptance of the source collision chain and isolated physical edits."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import math
from scene_config import differences

ALLOWED={"edit_light_ball":["physics.ball.mass_kg"],"edit_heavy_P01":["physics.pins.masses_kg.0"],
 "edit_remove_P01":["physics.pins.active.0"],"edit_grippy_P01":["physics.pins.frictions.0"],
 "edit_grippy_P02":["physics.pins.frictions.1"],"edit_grippy_P03":["physics.pins.frictions.2"]}

def validate(r,case="source",source=None):
    q=r["quality"];cfg=r["configuration"];ph=cfg["physics"];ball=ph["ball"];contacts=r["contact_events"]
    checks={"SI_normal_gravity":ph["gravity"]==[0.,0.,-9.81],"finite_states":all(math.isfinite(x) for f in r["frames"] for o in f["objects"].values() for k in ["location","quaternion_xyzw","linear_velocity","angular_velocity"] for x in o[k]),
      "exact_initial_contact":q["initial_max_penetration_m"]<1e-6,"bounded_penetration":q["max_penetration_m"]<.0025,
      "no_premature_pin_motion":not q["premature_tipping_ids"],"no_drivers_or_constraints":not r["constraints"] and not r["external_forces"] and not r["prescribed_motion"] and r["initial_velocity_assignment_count"]==1,
      "actual_solver_rotation":r["orientation_source"]=="actual solver quaternion; no reconstructed roll",
      "bounded_speed":max(q["max_linear_speed_m_per_s"].values())<8.,
      "free_flight_gravity":q["max_free_flight_acceleration_residual_m_per_s2"]<1e-5,
      "zero_lateral_spin":ball["initial_velocity_m_per_s"]==[4.,0.,0.] and abs(ball["initial_angular_velocity_rad_per_s"][1]-4/ball["radius_m"])<1e-10 and ball["initial_angular_velocity_rad_per_s"][0]==0 and ball["initial_angular_velocity_rad_per_s"][2]==0,
      "full_frame_count":len(r["frames"])==round(cfg["render"]["duration_sec"]*r["fps"]),
      "compound_pin_proxies":all(d["constructed_convex_shape_count"]==d["actual_collision_shape_count"]==len(cfg["simulation_quality"]["pin_convex_boundaries_m"])-1<=16 for n,d in r["actual_dynamics"].items() if n.startswith("P"))}
    initial=r["frames"][0]["objects"]
    checks["initial_poses_and_velocities"]=initial["B01"]["location"]==ball["initial_position_m"] and initial["B01"]["linear_velocity"]==ball["initial_velocity_m_per_s"] and all(o["tilt_deg"]<1e-8 and sum(abs(x) for x in o["linear_velocity"]+o["angular_velocity"])==0 for n,o in initial.items() if n.startswith("P"))
    checks["mass_and_inertia_readback"]=all(abs(d["mass_kg"]-(ball["mass_kg"] if n=="B01" else ph["pins"]["masses_kg"][int(n[-1])-1]))<1e-12 and min(d["local_inertia_diagonal_kg_m2"])>0 for n,d in r["actual_dynamics"].items())
    if case=="source":
        checks["three_pins_topple"]=q["toppled_count"]==3
        checks["ball_hits_P01_first"]=bool(contacts) and contacts[0]["objects"]==["B01","P01"]
        first=contacts[0]["first_time_sec"] if contacts else math.inf
        chain=[c for c in contacts if "P01" in c["objects"] and any(n in c["objects"] for n in ["P02","P03"]) and c["first_time_sec"]>first]
        checks["head_pin_transmits_to_rear"]=bool(chain) and chain[0]["total_normal_impulse_Ns"]>.1
        checks["rear_response_is_delayed"]=all(r["tilt_threshold_times_sec"][name].get("10",0)>first+.015 for name in ["P02","P03"])
        checks["energy_does_not_increase"]=q["max_mechanical_energy_J"]<=q["initial_mechanical_energy_J"]+1e-5
    else:
        if source is None:raise ValueError("Edited acceptance requires source")
        diff=differences(source["configuration"],cfg)
        checks["only_declared_property_changes"]=set(diff)==set(ALLOWED[case])
        checks["unchanged_first_ball_pose_and_speed"]=initial["B01"]["location"]==source["frames"][0]["objects"]["B01"]["location"] and initial["B01"]["linear_velocity"]==source["frames"][0]["objects"]["B01"]["linear_velocity"] and initial["B01"]["angular_velocity"]==source["frames"][0]["objects"]["B01"]["angular_velocity"]
        if case=="edit_remove_P01":checks["P01_absent_from_start_to_end"]=all("P01" not in f["objects"] for f in r["frames"]) and all("P01" not in c["objects"] for c in contacts)
    return {"case_id":case,"accepted":all(checks.values()),"checks":checks,"quality":q,"observed_contact_order":[{"objects":c["objects"],"time_sec":c["first_time_sec"]} for c in contacts],"tilt_threshold_times_sec":r["tilt_threshold_times_sec"],"scope":"Engineering solver and scene validation, not experimental calibration against a real bowling shot"}
