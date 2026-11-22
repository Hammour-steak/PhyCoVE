"""Numerical, causal and event gates; visual acceptance is separately recorded."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import math
import numpy as np
from scene_config import scenario,differences
from rigid_solver import rotate
from motion_metrics import rocking_metrics

def ball_events(r):return [e for e in r["contact_events"] if e["kind"]=="ball_ball"]

def validate(r,case="source",source=None):
    cfg=r["configuration"];ph=cfg["physics"];q=r["quality"];events=ball_events(r)
    samples=r["trajectory_samples"];initial=samples[0]["objects"]
    checks={"finite_trajectory":all(np.isfinite([*b["location"],*b["quaternion_xyzw"],*b["linear_velocity"],*b["angular_velocity"]]).all()
                for s in samples for b in s["objects"].values()),
        "initial_zero_velocities":all(max(map(abs,b["linear_velocity"]+b["angular_velocity"]))==0 for b in initial.values()),
        "no_initial_rope_extension":all(not b["rope"]["present"] or abs(b["rope"]["endpoint_distance_m"]-b["rope"]["length_m"])<1.e-12 for b in initial.values()),
        "no_out_of_plane_drift":q["max_out_of_plane_m"]<1.e-6,
        "rope_extension_below_1micron":q["max_rope_extension_m"]<1.e-6,
        "contact_penetration_below_0p6mm":q["max_ball_or_box_penetration_m"]<.0006,
        "nonnegative_tension":q["minimum_tension_N"]>=0,
        "passive_constraints_have_no_positive_work":q["max_positive_passive_constraint_work_in_contact_free_step_J"]<1.e-8,
        "bend_damping_is_dissipative":q["max_positive_bend_damping_work_J"]<1.e-10,
        "bend_damping_constitutive_law_solved":q["max_bend_damping_constitutive_residual_rad_s"]<1.e-6,
        "no_energy_increase":q["max_total_energy_above_initial_J"]<1.e-7 and q["max_positive_energy_step_J"]<1.e-7,
        "event_is_actual_contact":all(e["gap_m"]<=0 for e in r["contact_events"]),
        "measured_ball_restitution_matches_pair":all(abs(e["measured_normal_restitution"]-(e["configured_restitution"] if
            -e["pre_normal_velocity_m_per_s"]>cfg["simulation_quality"]["restitution_velocity_threshold_m_per_s"] else 0.))<.004 for e in events),
        "correct_frame_count":r["frame_end"]==round(cfg["render"]["fps"]*cfg["render"]["duration_sec"]) and len(r["frames"])==r["frame_end"],
        "free_6dof_and_unilateral_model":r["initial_state_policy"]["free_rigid_body_dofs"]==6 and not r["initial_state_policy"]["prescribed_trajectory"]}
    min_exit_cosine=1.
    for s in samples:
        for n,b in s["objects"].items():
            if not b["rope"]["present"]:continue
            arm=rotate(np.array(b["quaternion_xyzw"]),np.array(ph["ropes"][n]["attachment_local_m"]))
            direction=np.array(b["rope"]["anchor_m"])-np.array(b["rope"]["attachment_world_m"])
            min_exit_cosine=min(min_exit_cosine,float(direction@arm)/(np.linalg.norm(direction)*np.linalg.norm(arm)))
    checks["cord_exits_away_from_ball_surface"]=min_exit_cosine>0
    metrics={"quality":q,"ball_collision_times_sec":[e["time_sec"] for e in events],"first_rebound":r["first_rebound"],
        "minimum_rope_exit_cosine":min_exit_cosine}
    rocking=rocking_metrics(r)
    metrics['attachment_rocking']={n:{k:v for k,v in values.items() if k!='signed_planar_relative_angle_deg'} for n,values in rocking.items()}
    if all(not spec['present'] or spec.get('bend_damping_rate_per_s',0)>0 for spec in ph['ropes'].values()):
        peak_limit=9. if case=='edit_heavy_left' else 6.
        tail_limit=2.5 if case=='edit_heavy_left' else 1.5
        checks['no_accumulating_fast_rocking']=all(v['max_relative_body_cord_angle_deg']<peak_limit for v in rocking.values())
        checks['relative_rocking_settles_after_contact']=all(v['max_relative_angle_after_150ms_deg']<tail_limit for v in rocking.values())
    if case=="source":
        symmetry=max(max(abs(a["location"][0]+b["location"][0]),abs(a["location"][2]-b["location"][2]))
            for s in samples for a,b in [(s["objects"]["B_left"],s["objects"]["B_right"])] )
        checks["mirror_symmetry_below_10micron"]=symmetry<1.e-5;metrics["max_mirror_error_m"]=symmetry
        checks["first_collision_near_lowest_point"]=bool(events) and .38<events[0]["time_sec"]<.42 and abs(events[0]["contact_point_m"][2]-1.)<.002
        checks["left_and_right_reverse"]=bool(events) and events[0]["post_linear_velocities"]["B_left"][0]<-.5 and events[0]["post_linear_velocities"]["B_right"][0]>.5
        h={name:a["height_above_initial_lowest_center_m"] for name,a in r["first_rebound"].items()}
        hi=.6*(1-math.cos(math.radians(35)))
        checks["lower_and_equal_first_return_heights"]=abs(h["B_left"]-h["B_right"])<1.e-5 and .05<h["B_left"]<hi-.005
        checks["return_to_central_second_contact"]=len(events)>=2 and events[1]["time_sec"]<1.25
        checks["frame_and_base_clearance"]=not any(e["kind"]=="ball_static" for e in r["contact_events"])
        measured_t=events[0]["time_sec"] if events else 0
        # Series expansion of the large-angle simple-pendulum quarter period.
        theta=math.radians(35);t=.5*math.pi*math.sqrt(.6/9.81)*(1+theta**2/16+11*theta**4/3072)
        metrics["simple_pendulum_quarter_period_sec"]=t;metrics["time_difference_fraction"]=abs(measured_t-t)/t
        checks["gravity_period_consistent_with_length"]=abs(measured_t-t)/t<.015
    else:
        checks["source_was_supplied"]=source is not None
        allowed=set(differences(scenario(),scenario(case)));actual=set(differences(scenario(),cfg))
        checks["only_declared_target_inputs_change"]=allowed==actual and all(k.startswith("physics.") for k in actual)
        metrics["actual_config_differences"]=differences(scenario(),cfg)
        if case=="edit_heavy_left":
            checks["collision_still_occurs"]=bool(events)
            if source is not None:
                before=[(a,b) for a,b in zip(samples,source["trajectory_samples"]) if a["time_sec"]<.39]
                error=max(np.linalg.norm(np.array(a["objects"][n]["location"])-b["objects"][n]["location"])
                    for a,b in before for n in initial)
                checks["gravity_trajectory_unchanged_before_collision"]=error<1.e-9;metrics["pre_collision_position_difference_m"]=error
            checks["asymmetric_height_transfer"]=r["first_rebound"]["B_right"]["height_above_initial_lowest_center_m"]>.11
        if case=="edit_low_restitution":
            checks["collision_and_lower_rebound"]=bool(events) and r["first_rebound"]["B_left"]["height_above_initial_lowest_center_m"]<.065
        if case=="edit_remove_right":
            checks["only_left_ball_and_rope_remain"]=set(initial)=={"B_left"} and initial["B_left"]["rope"]["present"]
            checks["no_ball_collision"]=not events
            checks["passes_center_and_swings_right"]=max(s["objects"]["B_left"]["location"][0] for s in samples)>.28
        if case=="edit_remove_left_rope":
            checks["left_ball_survives_without_rope"]=not initial["B_left"]["rope"]["present"] and "B_right" in initial
            free=[s["objects"]["B_left"] for s in samples if s["time_sec"]<.20]
            checks["left_falls_without_lateral_push"]=max(abs(b["location"][0]-initial["B_left"]["location"][0]) for b in free)<1.e-12
            checks["base_or_table_receives_fall"]=any(e["objects"][0]=="B_left" and e["objects"][1] in ["Base","Table"] for e in r["contact_events"])
    return {"schema_version":1,"case_id":case,"accepted":all(bool(v) for v in checks.values()),
        "checks":{k:bool(v) for k,v in checks.items()},"metrics":metrics,
        "scope":"Numerical, causal and event verification. Full rendered visual review is a separate gate."}
