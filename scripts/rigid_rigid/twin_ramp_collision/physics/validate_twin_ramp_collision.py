"""Physics gates measured from solver state, contacts and energy, not visual intent."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import math
from scene_config import differences,surface

ALLOWED={"edit_heavy_left":{"physics.balls.B_left.mass_kg"},
    "edit_low_restitution":{"physics.balls.B_left.restitution","physics.balls.B_right.restitution"},
    "edit_remove_right":{"physics.balls.B_right.present"}}

def validate(r,case="source",source=None):
    cfg=r["configuration"];ph=cfg["physics"];q=r["quality"];events=r["contact_events"];first=events[0] if events else None
    # A secondary oblique sphere impact on a slope can physically lift a ball.
    # Assess seam-induced hops away from the measured ball-impact intervals.
    toe_clearance=0.;ramp=ph["ramp"]
    for sample in r["trajectory_samples"]:
        if any(abs(sample["time_sec"]-e["time_sec"])<.08 for e in events):continue
        for name,b in sample["objects"].items():
            x,y,z=b["location"]
            if ramp["central_length_m"]/2-.025<abs(x)<ramp["central_length_m"]/2+ramp["toe_transition_m"]+.025:
                sz,slope=surface(cfg,x)
                toe_clearance=max(toe_clearance,(z-sz)/math.sqrt(1+slope*slope)-ph["balls"][name]["radius_m"])
    checks={"initial_velocities_zero":all(max(abs(x) for x in b["linear_velocity"]+b["angular_velocity"])<1e-12 for b in r["frames"][0]["objects"].values()),
        "normal_gravity":ph["gravity"]==[0.,0.,-9.81],"independent_free_bodies":r["solver"]["constraints"]==0,
        "unforced":r["solver"]["external_forces"]==0 and r["solver"]["pose_resets_after_release"]==0 and r["solver"]["velocity_resets_after_release"]==0,
        "no_lateral_initial_offset":all(b["location"][1]==0. for b in r["frames"][0]["objects"].values()),
        "no_lateral_drift":q["max_abs_y_m"]<.00001,"ball_penetration_under_025mm":q["max_ball_penetration_m"]<.00025,
        "ramp_penetration_under_02mm":q["max_ramp_penetration_m"]<.00002,"no_toe_hop":toe_clearance<.0003,
        "no_energy_above_initial":q["max_total_energy_increase_J"]<.000001,
        "negligible_step_energy_error":q["max_step_energy_increase_J"]<.000001,
        "no_position_jump":q["max_frame_displacement_m"]<2.1/cfg["render"]["fps"],
        "all_balls_on_device":all(abs(b["location"][0])<.58 and b["location"][2]>.814 for f in r["frames"] for b in f["objects"].values()),
        "ramp_restitution_zero":all(v==0 for v in r["effective_contacts"]["ball_ramp_restitution"].values())}
    measured={"collision_times_sec":[e["time_sec"] for e in events],"first_rebound":r["first_rebound"],"quality":q,
        "max_toe_clearance_away_from_ball_collisions_m":toe_clearance,"ball_collision_exclusion_window_sec":.08}
    if case!="edit_remove_right":
        checks.update({"first_collision_in_flat":bool(first and first["both_in_horizontal"]),
            "first_collision_on_trajectory_sample":bool(first and abs(first["time_sec"]*cfg["simulation_quality"]["trajectory_hz"]-round(first["time_sec"]*cfg["simulation_quality"]["trajectory_hz"]))<.001),
            "first_collision_at_center":bool(first and abs(first["position_m"][0])<.001),
            "actual_restitution_matches_combination":bool(first and abs(first["measured_normal_restitution"]-r["effective_contacts"]["ball_ball_restitution"])<.002),
            "collision_does_not_add_energy":bool(first and first["energy_after_J"]<=first["energy_before_J"]+.000001),
            "spin_not_artificially_flipped":bool(first and all(first["before"][k]["angular_velocity"][1]*first["after"][k]["angular_velocity"][1]>0 for k in ["B_left","B_right"]))})
    if case=="source":
        turns=r["first_rebound"];valid=all(turns.get(k) is not None for k in ["B_left","B_right"])
        sym=max(abs(f["objects"]["B_left"]["location"][0]+f["objects"]["B_right"]["location"][0]) for f in r["frames"])
        checks.update({"equal_baseline_balls":ph["balls"]["B_left"]==ph["balls"]["B_right"],"symmetric_trajectories":sym<.0005,
            "both_reverse_at_collision":bool(first and first["after"]["B_left"]["linear_velocity"][0]<0<first["after"]["B_right"]["linear_velocity"][0]),
            "visible_reclimb":valid and all(t["height_above_horizontal_center_m"]>.025 for t in turns.values()),
            "return_to_original_slopes":valid and all(t["on_original_side"] for t in turns.values()),
            "reclimb_below_release":valid and all(t["location_m"][2]<r["frames"][0]["objects"][k]["location"][2]-.005 for k,t in turns.items()),
            "symmetric_first_heights":valid and abs(turns["B_left"]["location_m"][2]-turns["B_right"]["location_m"][2])<.0001,
            "roll_back_and_collide_again":len(events)>=2})
        measured["max_x_symmetry_error_m"]=sym
    else:
        assert source is not None
        diff=differences(source["configuration"],cfg);checks["exact_declared_input_differences"]=set(diff)==ALLOWED[case];measured["input_differences"]=diff
        cutoff=source["contact_events"][0]["time_sec"]-.02;err=0.;velerr=0.;straight_err=0.;straight_velerr=0.
        for a,b in zip(source["frames"],r["frames"]):
            if a["time_sec"]>cutoff:break
            for k,obj in b["objects"].items():
                err=max(err,max(abs(x-y) for x,y in zip(obj["location"],a["objects"][k]["location"])))
                velerr=max(velerr,max(abs(x-y) for x,y in zip(obj["linear_velocity"],a["objects"][k]["linear_velocity"])))
                if a["time_sec"]<=.6:
                    straight_err=max(straight_err,max(abs(x-y) for x,y in zip(obj["location"],a["objects"][k]["location"])))
                    straight_velerr=max(straight_velerr,max(abs(x-y) for x,y in zip(obj["linear_velocity"],a["objects"][k]["linear_velocity"])))
        checks["precollision_motion_unchanged"]=err<.00001 and velerr<.00002
        def acceleration(result):
            rows=[(f["time_sec"],f["objects"]["B_left"]["linear_velocity"][0]) for f in result["frames"] if .15<=f["time_sec"]<=.55]
            n=len(rows);st=sum(t for t,v in rows);sv=sum(v for t,v in rows)
            return (n*sum(t*v for t,v in rows)-st*sv)/(n*sum(t*t for t,v in rows)-st*st)
        acc_error=abs(acceleration(r)-acceleration(source))
        checks["straight_slope_mass_independent_acceleration"]=acc_error<.0001 and straight_err<.00001
        measured.update({"precollision_position_error_m":err,"precollision_velocity_error_m_per_s":velerr,
            "straight_slope_position_error_m":straight_err,"straight_slope_velocity_error_m_per_s":straight_velerr,
            "straight_slope_acceleration_error_m_per_s2":acc_error,"acceleration_tolerance_m_per_s2":.0001,
            "precollision_position_tolerance_m":.00001,"precollision_velocity_tolerance_m_per_s":.00002})
        if case=="edit_heavy_left":
            turns=r["first_rebound"]
            checks["unequal_reclimb"]=all(t is not None for t in turns.values()) and turns["B_right"]["location_m"][2]-turns["B_left"]["location_m"][2]>.05
            checks["different_velocity_distribution"]=first["after"]["B_right"]["linear_velocity"][0]>source["contact_events"][0]["after"]["B_right"]["linear_velocity"][0]+.3
        elif case=="edit_low_restitution":
            checks["effective_restitution_reduced"]=first["measured_normal_restitution"]<source["contact_events"][0]["measured_normal_restitution"]-.5
            maxpost=max(abs(b["location"][0]) for s in r["trajectory_samples"] if s["time_sec"]>first["time_sec"] for b in s["objects"].values())
            checks["stays_near_center"]=maxpost<.11;measured["max_postcollision_abs_x_m"]=maxpost
        else:
            checks["right_absent_before_release"]=set(r["frames"][0]["objects"])=={"B_left"}
            checks["no_ball_ball_contacts"]=len(events)==0
            turns=r["ramp_turning_points"]["B_left"]
            checks["crosses_and_climbs_opposite_slope"]=bool(turns and not turns[0]["on_original_side"] and turns[0]["location_m"][0]>.45)
            measured["first_opposite_turn"]=turns[0] if turns else None
    return {"schema_version":1,"case_id":case,"accepted":all(checks.values()),"checks":checks,"measurements":measured}
