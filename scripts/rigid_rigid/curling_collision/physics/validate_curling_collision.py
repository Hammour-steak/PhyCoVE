"""Independent collision invariants and complete-trajectory acceptance checks."""
from __future__ import annotations
import math

def validate(result):
    ph, rd = result["configuration"]["physics"], result["configuration"]["render"]
    ids, samples, events = ph["object_ids"], result["trajectory_samples"], result["contact_events"]
    case_id = result.get("case_id","source")
    checks = {}
    checks["requested_video_timebase"] = (rd["resolution"]==[1280,720] and rd["fps"]==24 and rd["total_frames"]==96 and rd["duration_sec"]==4.0)
    expected_by_case = {
        "source":[["R01","B01"],["B01","Y01"]],
        "edit_add_green_stone_midpoint":[["R01","B01"],["B01","G01"],["G01","Y01"]],
        "edit_delete_yellow_stone":[["R01","B01"]],
        "edit_delete_blue_stone":[["R01","Y01"]],
        "edit_blue_mass_x3":[["R01","B01"]],
        "edit_red_mass_x1p1":[["R01","B01"],["B01","Y01"]],
    }
    expected = expected_by_case.get(case_id,[[a,b] for a,b in zip(ids,ids[1:])])
    actual = [e["object_ids"] for e in events]
    checks["expected_contact_sequence"] = actual==expected
    metrics = {"contact_times_sec":[e["time_sec"] for e in events],"contact_frames_float":[e["frame_float"] for e in events]}
    if checks["expected_contact_sequence"]:
        checks["visibly_separated_contacts"] = all(b["time_sec"]-a["time_sec"] > 0.25 for a,b in zip(events,events[1:]))
        first_target_events = {}
        for event in events:
            first_target_events.setdefault(event["object_ids"][1],event)
        checks["stationary_until_first_struck"] = all(
            abs(s["bodies"][target]["linear_velocity"][0]) < 1e-12
            for target,event in first_target_events.items()
            for s in samples if s["time_sec"] < event["time_sec"]-1e-9)
        first_by_pair = {}
        for event in events:
            first_by_pair.setdefault(tuple(event["object_ids"]),event)
        slides = []
        for i in range(1,len(ids)-1):
            event = first_by_pair.get((ids[i],ids[i+1]))
            if event is not None:
                slides.append(event["contact_position_m"][0]-ph["radius_m"]-ph["initial_x_m"][i])
        metrics["middle_stone_free_slide_before_next_contact_m"] = slides
        checks["middle_stones_slide_clearly_between_contacts"] = all(slide > 0.25 for slide in slides)
        checks["striker_loses_speed_and_target_gains_speed"] = all(
            e["post_velocity_m_per_s"][e["object_ids"][0]] < e["pre_velocity_m_per_s"][e["object_ids"][0]]
            and e["post_velocity_m_per_s"][e["object_ids"][1]] > e["pre_velocity_m_per_s"][e["object_ids"][1]]
            for e in events)
        last_id,last_event = ids[-1],events[-1]
        last = result["final_state"]["bodies"][last_id]
        metrics["last_stone_speed_after_contact_m_per_s"] = last_event["post_velocity_m_per_s"][last_id]
        metrics["last_stone_speed_at_4s_m_per_s"] = last["linear_velocity"][0]
        metrics["last_stone_slide_after_contact_m"] = last["location"][0]-ph["initial_x_m"][-1]
        if case_id!="edit_blue_mass_x3":
            first_last_hit = next(e for e in events if e["object_ids"][1]==last_id)
            checks["last_stone_visibly_slows_due_to_friction"] = (
                0 < last["linear_velocity"][0] < first_last_hit["post_velocity_m_per_s"][last_id]
                and metrics["last_stone_slide_after_contact_m"]>0.8)
    if case_id=="edit_delete_yellow_stone":
        checks["yellow_stone_deleted"] = ids==["R01","B01"]
    elif case_id=="edit_delete_blue_stone":
        checks["blue_stone_deleted"] = ids==["R01","Y01"]
    elif case_id=="edit_blue_mass_x3":
        final = result["final_state"]["bodies"]
        final_gap = final["Y01"]["location"][0]-final["B01"]["location"][0]-2*ph["radius_m"]
        metrics["final_blue_yellow_clear_gap_m"] = final_gap
        checks["blue_mass_is_three_times_source"] = ph["mass_kg"]==[19.5,58.5,19.5]
        checks["blue_never_contacts_yellow"] = ["B01","Y01"] not in actual
        checks["blue_stops_before_yellow"] = final_gap>0.05 and final["B01"]["linear_velocity"][0]==0.0 and final["Y01"]["linear_velocity"][0]==0.0
    elif case_id=="edit_red_mass_x1p1":
        checks["red_mass_is_1p1_times_source"] = ph["mass_kg"]==[21.45,19.5,19.5]
    elif case_id=="edit_add_green_stone_midpoint":
        checks["green_stone_added"] = ids==["R01","B01","G01","Y01"]
    momentum_error = max((abs(e["momentum_after_kg_m_per_s"]-e["momentum_before_kg_m_per_s"]) for e in events),default=math.inf)
    restitution_error = max((abs(e["measured_restitution"]-ph["stone_pair_restitution"]) for e in events),default=math.inf)
    checks["collision_momentum_conserved"] = momentum_error < 1e-9
    checks["newton_restitution_satisfied"] = restitution_error < 1e-10
    checks["collision_energy_dissipated"] = all(e["kinetic_energy_after_J"] < e["kinetic_energy_before_J"] and e["energy_dissipated_J"] > 0 for e in events)
    energy_gains = [b["kinetic_energy_J"]-a["kinetic_energy_J"] for a,b in zip(samples,samples[1:])]
    checks["total_kinetic_energy_never_increases"] = max(energy_gains,default=math.inf) < 1e-8
    min_gap = min(s["bodies"][b]["location"][0]-s["bodies"][a]["location"][0]-2*ph["radius_m"] for s in samples for a,b in zip(ids,ids[1:]))
    checks["no_interpenetration"] = min_gap > -1e-9
    checks["straight_level_nonspinning_motion"] = all(b["location"][1:]==[ph["track_y_m"],ph["com_height_m"]] and b["quaternion_xyzw"]==[0.0,0.0,0.0,1.0] and b["angular_velocity"]==[0.0,0.0,0.0] and b["linear_velocity"][1:]==[0.0,0.0] for s in samples for b in s["bodies"].values())
    checks["finite_motion"] = all(math.isfinite(k) for s in samples for b in s["bodies"].values() for k in b["location"]+b["linear_velocity"])
    checks["motion_solved_from_physical_inputs"] = not result["prescribed_motion"] and not result["authored_collision_times"]
    # Verify analytical segments obey friction, independent of output sampling.
    deceleration = ph["ice_kinetic_friction"]*ph["gravity_m_per_s2"]
    checks["segment_accelerations_match_coulomb_friction"] = all(
        abs(a-(-math.copysign(deceleration,v) if abs(v)>1e-10 else 0)) < 1e-10
        for s in result["analytic_segments"] for a,v in zip(s["ax_m_per_s2"],s["vx_m_per_s"]))
    metrics.update(momentum_error_kg_m_per_s=momentum_error,restitution_error=restitution_error,
                   minimum_pair_gap_m=min_gap,maximum_sample_energy_gain_J=max(energy_gains),
                   ice_deceleration_m_per_s2=deceleration,
                   initial_clear_gaps_m=[b-a-2*ph["radius_m"] for a,b in zip(ph["initial_x_m"],ph["initial_x_m"][1:])])
    return {"accepted":all(checks.values()),"case_id":case_id,"checks":checks,"metrics":metrics,
            "scope":"Constrained 1D rigid-body solution, contact conservation and kinematics; no empirical stone calibration or unconstrained curling dynamics claimed."}
