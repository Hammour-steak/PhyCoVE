"""Checks actual solved motion against contact, ballistic and energy invariants."""
import math

def differences(a,b,prefix=""):
    changed=[]
    for key in sorted(set(a)|set(b)):
        path=(prefix+"."+key).lstrip(".")
        if key not in a or key not in b:changed.append(path)
        elif isinstance(a[key],dict) and isinstance(b[key],dict):changed.extend(differences(a[key],b[key],path))
        elif a[key]!=b[key]:changed.append(path)
    return changed

def validate_absent(result,case,source):
    cfg=result["configuration"];rd=cfg["render"]
    checks={
        "declared_ball_removed":case=="remove_ball" and cfg["physics"]["ball"].get("present") is False,
        "edited_case_identity":result.get("case_id")==case,
        "96_empty_real_time_frames":len(result["frames"])==96 and rd["fps"]==24 and rd["duration_sec"]==4 and all(
            f["frame_index"]==i+1 and abs(f["time_sec"]-i/24)<1e-12 and f.get("objects")==[] and not f.get("object_present",True) for i,f in enumerate(result["frames"])),
        "no_ball_built_in_solver":result.get("dynamic_body_count")==0 and result.get("actual_body_count")==1 and result.get("actual_ball_mass_kg") is None,
        "no_ball_trajectory_or_contacts":not result["trajectory_samples"] and not result["contact_events"],
        "no_phantom_velocity_initialization":result["velocity_initialization_count"]==0,
        "no_authored_motion_or_forces":not result["prescribed_motion"] and not result["external_forces"] and not result["constraints"],
    }
    diff=differences(source["configuration"],cfg) if source else None
    if source is not None:checks["only_declared_presence_changes"]=diff==["physics.ball.present"]
    return {"accepted":all(checks.values()),"checks":checks,"case_id":case,
        "paired_source_comparison":{"changed_fields":diff} if source else None,
        "major_contact_times_sec":[],"complete_rebound_bottom_heights_m":[],"contact_intervals_sec":[],
        "quality":result["quality"],"scope":"Empty rigid world: fixed floor only, no B01 body, trajectory or contact."}


def validate(result, case='source', source=None):
    if not result["configuration"]["physics"]["ball"].get("present",True):
        return validate_absent(result,case,source)
    cfg = result["configuration"]
    ph, rd = cfg["physics"], cfg["render"]
    b = ph["ball"]
    release = b["initial_position_m"][2] - b["radius_m"] - ph["floor"]["top_z_m"]
    g = -ph["gravity"][2]
    events = [e for e in result["contact_events"] if e["major_impact"]]
    complete = [e for e in events if e["complete_rebound"]]
    heights = [e["apex_bottom_height_m"] for e in complete]
    intervals = [e["contact_interval_sec"] for e in complete]
    before = [s for s in result["trajectory_samples"] if s["time_sec"] < events[0]["time_sec"]] if events else []
    ballistic_error = max((abs(s["location"][2] - (b["initial_position_m"][2] - 0.5*g*s["time_sec"]**2)) for s in before), default=float("inf"))
    first_analytic_time = math.sqrt(2*release/g)
    checks = {
        "96_real_time_source_frames": len(result["frames"]) == rd["total_frames"] == 96 and rd["fps"] == 24 and rd["duration_sec"] == 4,
        "diameter_24cm_release_clearance_1p5m": abs(2*b["radius_m"]-0.24) < 1e-12 and abs(release-1.5) < 1e-12,
        "released_from_rest": all(abs(v) < 1e-12 for v in (*b["initial_velocity_m_per_s"], *b["initial_angular_velocity_rad_per_s"])),
        "free_rigid_body_no_authored_motion": not result["prescribed_motion"] and not result["constraints"] and not result["external_forces"] and result["velocity_initialization_count"] == 1,
        "at_least_four_major_bounces": len(events) >= 4,
        "first_contact_matches_free_fall_within_4ms": bool(events) and abs(events[0]["time_sec"]-first_analytic_time) < 0.004,
        "fall_trajectory_matches_gravity_within_2mm": ballistic_error < 0.002,
        "first_rebound_below_release": bool(heights) and 0.1 < heights[0] < release,
        "rebound_heights_strictly_decrease": len(heights) >= 3 and all(a > c for a, c in zip(heights, heights[1:])),
        "contact_intervals_strictly_decrease": len(intervals) >= 3 and all(a > c for a, c in zip(intervals, intervals[1:])),
        "fixed_landing_point_within_0p1mm": result["quality"]["maximum_horizontal_drift_m"] < 0.0001,
        "maximum_penetration_under_3mm": result["quality"]["minimum_bottom_clearance_m"] > -0.003,
        "ballistic_velocity_residual_under_1e_6": result["quality"]["maximum_free_flight_velocity_residual_m_per_s"] < 1e-6,
        "mass_and_hollow_sphere_inertia_applied": abs(result["actual_ball_mass_kg"]-b["mass_kg"]) < 1e-12 and all(abs(v-b["inertia_factor"]*b["mass_kg"]*b["radius_m"]**2) < 1e-12 for v in result["actual_ball_inertia_kg_m2"]),
        "measured_first_restitution_within_0p04": bool(events) and abs(events[0]["measured_restitution"]-result["effective_restitution"]) < 0.04,
        "rebound_potential_energies_decrease": all(b["mass_kg"]*g*c < b["mass_kg"]*g*a for a, c in zip([release]+heights, heights)),
    }
    paired = None
    if case != "source":
        checks["edited_case_identity"]=result.get("case_id")==case
        if case in ["low_restitution","high_restitution"]:
            checks["declared_restitution_applied"]=abs(b["restitution"]-{"low_restitution":.38,"high_restitution":.95}[case])<1e-12
        elif case=="heavy_ball":
            checks["declared_mass_applied"]=b["mass_kg"]==1.25 and result["actual_ball_mass_kg"]==1.25
        elif case=="restitution_at_1s":
            applied=result.get("applied_edits",[])
            scheduled=ph.get("timed_edits",[])
            checks["declared_schedule"]=scheduled==[{"frame":25,"params":{"ball_restitution":.95}}] and b["restitution"]==.76
            checks["one_real_solver_change_at_one_second"]=len(applied)==1 and applied[0]["frame"]==25 and applied[0]["time_sec"]==1.0 and applied[0]["commanded_before_restitution"]==.76 and applied[0]["commanded_after_restitution"]==.95
            checks["no_pose_or_velocity_reset_at_edit"]=len(applied)==1 and applied[0]["state_before"]==applied[0]["state_after"]
            checks["final_commanded_restitution_is_0p95"]=abs(result.get("final_commanded_effective_restitution",0)-.95)<1e-12
            after_impacts=[e for e in events if e["time_sec"]>=1]
            checks["actual_post_edit_contacts_verify_0p95"]=len(after_impacts)>=2 and all(abs(e["measured_restitution"]-.95)<.04 for e in after_impacts)
        else:checks["supported_case"]=False
        if source is not None:
            diff=differences(source["configuration"],cfg)
            allowed={"low_restitution":["physics.ball.restitution"],"high_restitution":["physics.ball.restitution"],
                     "heavy_ball":["physics.ball.mass_kg"],"restitution_at_1s":["physics.timed_edits"]}
            checks["only_declared_physics_changes"]=diff==allowed.get(case)
            src_events=[e for e in source["contact_events"] if e["major_impact"]]
            checks["first_contact_time_identical_to_source"]=events[0]["time_sec"]==src_events[0]["time_sec"]
            paired={"changed_fields":diff}
            if case in ["low_restitution","high_restitution"]:
                first=events[0]["time_sec"]
                before_edit=[s for s in result["trajectory_samples"] if s["time_sec"]<first]
                checks["preimpact_motion_identical_to_source"]=before_edit==[s for s in source["trajectory_samples"] if s["time_sec"]<first]
                checks["first_rebound_changes_in_declared_direction"]=(heights[0]<src_events[0]["apex_bottom_height_m"]) if case=="low_restitution" else (heights[0]>src_events[0]["apex_bottom_height_m"])
                paired.update(identical_preimpact_samples=len(before_edit),source_first_rebound_bottom_height_m=src_events[0]["apex_bottom_height_m"],edited_first_rebound_bottom_height_m=heights[0])
            elif case=="heavy_ball":
                fields=["time_sec","location","quaternion_xyzw","linear_velocity","angular_velocity","bottom_clearance_m","contact"]
                checks["all_heavy_ball_poses_and_velocities_equal_source"]=all(
                    all(a[k]==c[k] for k in fields) for a,c in zip(result["trajectory_samples"],source["trajectory_samples"])) and len(result["trajectory_samples"])==len(source["trajectory_samples"])
                checks["contact_times_equal_source"]=[e["time_sec"] for e in result["contact_events"]]==[e["time_sec"] for e in source["contact_events"]]
                ratios=[a["normal_impulse_Ns"]/c["normal_impulse_Ns"] for a,c in zip(events,src_events)]
                checks["all_major_collision_impulses_double"]=all(abs(r-2)<1e-10 for r in ratios)
                checks["mechanical_energy_doubles"]=all(abs(a["mechanical_energy_J"]-2*c["mechanical_energy_J"])<1e-10 for a,c in zip(result["trajectory_samples"],source["trajectory_samples"]))
                paired["major_impact_impulse_ratios"]=ratios
            elif case=="restitution_at_1s":
                before_edit=[s for s in result["trajectory_samples"] if s["time_sec"]<=1]
                checks["motion_through_edit_time_exactly_equals_source"]=before_edit==[s for s in source["trajectory_samples"] if s["time_sec"]<=1]
                next_time=src_events[1]["time_sec"]
                checks["motion_before_next_impact_exactly_equals_source"]=[s for s in result["trajectory_samples"] if s["time_sec"]<next_time]==[s for s in source["trajectory_samples"] if s["time_sec"]<next_time]
                checks["first_bounce_unchanged"]=events[0]["apex_bottom_height_m"]==src_events[0]["apex_bottom_height_m"]
                checks["next_impact_time_unchanged"]=events[1]["time_sec"]==next_time
                checks["next_impact_uses_higher_restitution"]=abs(events[1]["measured_restitution"]-.95)<.04 and events[1]["apex_bottom_height_m"]>src_events[1]["apex_bottom_height_m"]
                paired.update(identical_samples_through_edit=len(before_edit),first_affected_collision_time_sec=next_time,source_second_rebound_bottom_height_m=src_events[1]["apex_bottom_height_m"],edited_second_rebound_bottom_height_m=events[1]["apex_bottom_height_m"])
    return {"accepted": all(checks.values()), "checks": checks,"case_id":case,"paired_source_comparison":paired,
        "major_contact_times_sec": [e["time_sec"] for e in events],
        "complete_rebound_bottom_heights_m": heights, "contact_intervals_sec": intervals,
        "first_contact_analytic_sec": first_analytic_time, "maximum_initial_fall_position_error_m": ballistic_error,
        "quality": result["quality"],
        "scope": "Engineering checks against free fall and dissipative rigid contacts; no calibration to a measured physical basketball. No elastic deformation is simulated."}
