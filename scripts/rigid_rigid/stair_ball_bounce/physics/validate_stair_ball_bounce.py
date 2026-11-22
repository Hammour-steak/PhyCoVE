"""Meaningful source, stability, and declared counterfactual target gates."""
from __future__ import annotations
from scene_config import BASELINE, INITIAL_VELOCITY_CASES, FRICTION_CASES, COMBINED_FRICTION_CASES, edited_ball_fields, scenario, differences

def validate(result,case="source",source=None):
    q=result["quality"];cfg=result["configuration"];ph=cfg["physics"]
    events=result["contact_events"];major=[e for e in events if e["major_impact"]]
    first=major[0];first_contact=result["contact_events"][0]
    checks={"no_initial_intersection":min(result["initial_clearance_m"].values())>.001,
            "one_initial_velocity":result["velocity_initialization_count"]==1,
            "no_constraints_or_external_actuation":not result["constraints"] and not result["external_forces"] and not result["prescribed_motion"],
            "normal_gravity":ph["gravity"]==[0,0,-9.81],
            "configured_size_40g_hollow_rigid_sphere":ph["ball"]["radius_m"]==BASELINE["physics"]["ball"]["radius_m"] and ph["ball"]["mass_kg"]==.04 and abs(ph["ball"]["inertia_factor"]-2/3)<1e-12,
            "initial_gap_15cm":abs(ph["ball"]["initial_position_m"][2]-ph["ball"]["radius_m"]-ph["stairs"]["count"]*ph["stairs"]["rise_m"]-.15)<1e-12,
            "configured_horizontal_release_velocity":ph["ball"]["initial_velocity_m_per_s"]==scenario(case=case)["physics"]["ball"]["initial_velocity_m_per_s"] and ph["ball"]["initial_velocity_m_per_s"][1:]==[0,0],
            "actual_initial_velocity_matches_input":result["frames"][0]["linear_velocity"]==ph["ball"]["initial_velocity_m_per_s"],
            "initial_zero_spin":ph["ball"]["initial_angular_velocity_rad_per_s"]==[0,0,0],
            "no_tunneling_penetration_under_0p8mm":q["max_penetration_m"]<.0008,
            "contact_gaps_under_10um":q["max_positive_contact_gap_m"]<.00001,
            "no_abnormal_energy_injection":q["max_single_step_energy_gain_J"]<.000015,
            "ballistic_free_flight":q["max_free_flight_velocity_residual_m_per_s"]<1e-8,
            "spin_generated_by_contact":q["max_angular_speed_rad_per_s"]>5 and all(sum(x*x for x in f["angular_velocity"])<1e-12 for f in result["frames"] if f["time_sec"]<first_contact["time_sec"]),
            "actual_first_major_contact_on_expected_stairs":first["collider_id"] in [c['id'] for c in result['colliders'] if c['id'].startswith('S')] if case in INITIAL_VELOCITY_CASES else first["collider_id"]=="S01",
            "rebounds_follow_actual_contact":all(e["initial_signed_gap_m"]<=1e-8 for e in major),
            "reached_lower_platform":any(e["collider_id"]=="lower_platform" for e in major),
            "laterally_stable":max(abs(f["location"][1]) for f in result["frames"])<.001,
            "inside_lower_landing":result["final_state"]["location"][0]<result["colliders"][-1]["xmax"]-.1,
            "no_pose_jump":all(sum((a-b)**2 for a,b in zip(x["location"],y["location"]))**.5 <q["max_speed_m_per_s"]/result["fps"]+.001 for x,y in zip(result["frames"],result["frames"][1:])),
            "dense_pose_and_frame_counts":len(result["frames"])==result["frame_end"] and len(result["trajectory_samples"])>=result["frame_end"]*4}
    if case=="source":
        checks.update({"exact_sequential_main_contacts":[e["collider_id"] for e in major[:6]]==["S01","S02","S03","S04","S05","lower_platform"],
            "five_clear_tread_rebounds":all(e["surface"]=="tread" and e["rebound_height_above_contact_m"]>.025 for e in major[:5]),
            "source_rebounds_under_10cm":all(e["rebound_height_above_contact_m"]<.10 for e in major[:5]),
            "source_first_rebound_3_to_6cm":.03<first["rebound_height_above_contact_m"]<.06,
            "floor_bounces_then_rolling":q["lower_platform_rolling_start_sec"] is not None and q["lower_platform_rolling_start_sec"]<result["duration_sec"]-.5})
    audit=None
    if source is not None:
        diff=differences(source["configuration"],cfg)
        fields=["physics.ball."+field for field in edited_ball_fields(case)]
        audit={"before":source["configuration"],"after":cfg,"actual_diff":diff,"expected_changed_fields":fields,
               "accepted":set(diff)==set(fields)}
        checks["declared_joint_friction_edit" if case in COMBINED_FRICTION_CASES else "single_attribute_edit"]=audit["accepted"]
        if case in INITIAL_VELOCITY_CASES:
            before_v=source["configuration"]["physics"]["ball"]["initial_velocity_m_per_s"]
            after_v=ph["ball"]["initial_velocity_m_per_s"]
            stop=min(source["contact_events"][0]["time_sec"],first_contact["time_sec"])
            pairs=[(a,b) for a,b in zip(source["frames"],result["frames"]) if a["time_sec"]<stop]
            checks["velocity_edit_applied_before_first_contact"]=any(a["time_sec"]>0 for a,b in pairs) and all(
                abs((b["location"][k]-a["location"][k])-(after_v[k]-before_v[k])*a["time_sec"])<1e-8
                for a,b in pairs for k in range(3))
            checks["different_precontact_horizontal_motion"]=any(abs(b["location"][0]-a["location"][0])>.001 for a,b in pairs)
            checks["clearly_changed_contact_pattern_or_timing"]=[e["collider_id"] for e in major]!=[e["collider_id"] for e in source["contact_events"] if e["major_impact"]] or abs(first["time_sec"]-next(e["time_sec"] for e in source["contact_events"] if e["major_impact"]))>.02
        elif case in COMBINED_FRICTION_CASES:
            stop=min(source['contact_events'][0]['time_sec'],first_contact['time_sec'])
            checks['same_preimpact_motion']=all(
                all(a[k]==b[k] for k in ['location','quaternion_xyzw','linear_velocity','angular_velocity'])
                for a,b in zip(source['frames'],result['frames']) if a['time_sec']<stop)
            before=source['configuration']['physics']['ball'];expected=scenario(case=case)['physics']['ball']
            checks['both_friction_coefficients_increase']=all(ph['ball'][field]>before[field] for field in edited_ball_fields(case))
            checks['both_friction_coefficients_match_registered_case']=all(ph['ball'][field]==expected[field] for field in edited_ball_fields(case))
            checks['visibly_shorter_travel']=result['final_state']['location'][0]<source['final_state']['location'][0]-.5
            if result['duration_sec']>=4.5:
                checks['comes_to_rest_on_lower_platform']=sum(v*v for v in result['final_state']['linear_velocity'])<.005**2 and 'lower_platform' in result['final_state']['contact_ids']
                checks['sustained_rest_last_0p2s']=all(sum(v*v for v in f['linear_velocity'])<.005**2 for f in result['frames'] if f['time_sec']>result['duration_sec']-.2)
            else:
                # The 4 s benchmark clip ends at 3.96 s; this ball stops at 4.16 s, so it is gated as rolling
                # to a near stop on the landing and slowing down monotonically over the last 0.5 s.
                speeds=[sum(v*v for v in f['linear_velocity'])**.5 for f in result['frames'] if f['time_sec']>result['duration_sec']-.5]
                checks['nearly_at_rest_on_lower_platform']=sum(v*v for v in result['final_state']['linear_velocity'])<.1**2 and 'lower_platform' in result['final_state']['contact_ids']
                checks['decelerating_through_last_0p5s']=len(speeds)>2 and all(b<=a for a,b in zip(speeds,speeds[1:]))
        elif case in FRICTION_CASES:
            stop=min(source['contact_events'][0]['time_sec'],first_contact['time_sec'])
            checks['same_preimpact_motion']=all(
                all(a[k]==b[k] for k in ['location','quaternion_xyzw','linear_velocity','angular_velocity'])
                for a,b in zip(source['frames'],result['frames']) if a['time_sec']<stop)
            target=FRICTION_CASES[case]
            checks['friction_target_matches_registered_case']=ph['ball'][target['field']]==target['value']
            src_contact=source['contact_events'][0]
            if target['field']=='lateral_friction':
                # First impact is on the horizontal interior of S01; measure the
                # tangential impulse and spin that the actual solver generated.
                radius=ph['ball']['radius_m']
                slip=abs(first_contact['post_linear_velocity'][0]-radius*first_contact['post_angular_velocity'][1])
                checks['clearly_more_slip_after_first_contact']=slip>.2
                checks['clearly_less_contact_generated_spin']=abs(first_contact['post_angular_velocity'][1])<.5*abs(src_contact['post_angular_velocity'][1])
                actual_mu=abs(ph['ball']['mass_kg']*(first_contact['post_linear_velocity'][0]-first_contact['pre_linear_velocity'][0]))/first_contact['normal_impulse_Ns']
                checks['measured_tangent_impulse_at_lower_coulomb_bound']=abs(actual_mu-ph['ball']['lateral_friction']*ph['stairs']['lateral_friction'])<1e-6
                checks['normal_impulse_unchanged_on_first_tread']=abs(first_contact['normal_impulse_Ns']-src_contact['normal_impulse_Ns'])<1e-8
            elif target['value']<source['configuration']['physics']['ball']['rolling_friction']:
                checks['rolls_visibly_farther_by_end']=result['final_state']['location'][0]>source['final_state']['location'][0]+.25
                checks['retains_more_forward_speed']=result['final_state']['linear_velocity'][0]>source['final_state']['linear_velocity'][0]+.1
            else:
                checks['visibly_shorter_travel']=result['final_state']['location'][0]<source['final_state']['location'][0]-.5
                checks['comes_to_rest_on_lower_platform']=sum(v*v for v in result['final_state']['linear_velocity'])<.005**2 and 'lower_platform' in result['final_state']['contact_ids']
                checks['sustained_rest_last_0p2s']=all(sum(v*v for v in f['linear_velocity'])<.005**2 for f in result['frames'] if f['time_sec']>result['duration_sec']-.2)
        else:
            checks["same_preimpact_motion"]=all(a["location"]==b["location"] and a["quaternion_xyzw"]==b["quaternion_xyzw"] for a,b in zip(source["frames"],result["frames"]) if a["time_sec"]<first["time_sec"])
            src_first=next(e for e in source["contact_events"] if e["major_impact"])
            ratio=first["rebound_height_above_contact_m"]/src_first["rebound_height_above_contact_m"]
            checks["clearly_changed_rebound"]=ratio<.2 if case=="edit_low_restitution" else ratio>1.35
    return {"accepted":all(checks.values()),"case":case,"checks":checks,"quality":q,"parameter_audit":audit,
            "scope":"Solver-based quantitative engineering gates. Render appearance and complete video review are recorded separately."}
