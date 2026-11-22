"""Counterfactual validation without forcing source-specific contact outcomes."""
from __future__ import annotations

import math

from edit_vocab import edit_info
from scene_config import body_present, merge, signature
from .validate_ball_box_rebound import speed


def measured(result):
    ph, samples = result["configuration"]["physics"], result["trajectory_samples"]
    events = [e for e in result["contact_events"] if e["normal_impulse_Ns"] > .005]
    first = next((e for e in events if e["pair"] == ["ball", "box"]), None)
    second = next((e for e in events if e["pair"] == ["ball", "football"]), None)
    travel = {}
    for name in ("ball", "box", "football"):
        positions = [s["objects"][name]["location"] for s in samples if name in s["objects"]]
        travel[name] = max((math.dist(p[:2], ph[name]["initial_position_m"][:2]) for p in positions), default=0.0)
    metrics = {
        "first_contact_sec": first["time_sec"] if first else None,
        "second_contact_sec": second["time_sec"] if second else None,
        "major_contacts": [{"pair": e["pair"], "time_sec": e["time_sec"],
                             "normal_impulse_Ns": e["normal_impulse_Ns"]} for e in events],
        "maximum_horizontal_travel_m": travel,
        "final_speed_m_per_s": {k: speed(v) for k, v in result["final_state"]["objects"].items()},
        "final_to_initial_energy_ratio": result["final_state"]["mechanical_energy_J"] / samples[0]["mechanical_energy_J"],
        "minimum_signed_contact_gap_m": result["quality"]["minimum_signed_contact_gap_m"],
        "configured_pair_restitution": {"ball_box": ph["ball"]["restitution"] * ph["box"]["restitution"],
                                         "ball_football": ph["ball"]["restitution"] * ph["football"]["restitution"]},
    }
    if first:
        pre = first["pre_state"]["objects"]
        post = first.get("separation_state", first["last_contact_state"])["objects"]
        normal = first["contact_normal"]
        a = sum((pre["ball"]["linear_velocity"][i] - pre["box"]["linear_velocity"][i]) * normal[i] for i in range(3))
        b = sum((post["ball"]["linear_velocity"][i] - post["box"]["linear_velocity"][i]) * normal[i] for i in range(3))
        metrics["first_normal_separation_to_approach_speed_ratio"] = abs(b / a)
    return metrics


def validate_edit(result, case, source):
    if source is None:
        return {"accepted": False, "checks": {"paired_source_available": False},
                "metrics": measured(result), "scope": "A counterfactual requires its matching source for validation."}
    cfg, base = result["configuration"], source["configuration"]
    ph, samples = cfg["physics"], result["trajectory_samples"]
    info = edit_info(case, base)
    actual = result["actual_dynamics"]
    expected_created = {name for name in ("ball", "box", "football") if body_present(cfg, name, 0)}
    initial = samples[0]
    energy = initial["mechanical_energy_J"]
    removal = ph["football"]["remove_at_sec"]
    events = result["contact_events"]
    interventions = result.get("intervention_events", [])
    metrics = measured(result)
    source_metrics = measured(source)
    velocity = ph["ball"]["initial_velocity_m_per_s"]
    omega = ph["ball"]["initial_angular_velocity_rad_per_s"]
    r = ph["ball"]["radius_m"]
    all_states = samples + result["frames"] + [result["final_state"]]
    checks = {
        "configuration_contains_only_declared_edit": cfg == merge(base, info["physics_override"]),
        "appearance_camera_and_render_frozen": cfg["appearance"] == base["appearance"] and cfg["render"] == base["render"],
        "solver_quality_frozen": cfg["simulation_quality"] == base["simulation_quality"],
        "configuration_signature_correct": signature(cfg) == result["configuration_sha256"],
        "96_frames_at_original_physical_times": len(result["frames"]) == 96 and result["fps"] == 24
            and all(abs(f["time_sec"] - (f["frame_index"] - 1) / 24) < 1e-12 for f in result["frames"]),
        "initial_no_slip_roll": math.hypot(velocity[0] - omega[1] * r, velocity[1] + omega[0] * r) < 1e-8,
        "free_motion_without_constraints_or_forcing": not result["prescribed_motion"] and not result["constraints"] and not result["external_forces"],
        "velocity_initialized_only_once": result["velocity_initialization_counts"] == {name: 1 for name in expected_created},
        "correct_bodies_created": set(actual) == expected_created,
        "actual_masses_match": all(abs(actual[name]["mass_kg"] - ph[name]["mass_kg"]) < 1e-12 for name in expected_created),
        "actual_friction_parameters_match": all(abs(actual[name][field] - ph[name][field]) < 1e-12
            for name in expected_created for field in ("lateral_friction", "rolling_friction", "spinning_friction")),
        "normal_impact_response_matches_configured_restitution": abs(metrics.get(
            "first_normal_separation_to_approach_speed_ratio", -1) - metrics["configured_pair_restitution"]["ball_box"]) < .02,
        "sphere_colliders_and_inertia_match": all(actual[name]["collision_geometry_type"] == 2
            and all(abs(i - ph[name]["inertia_factor"] * ph[name]["mass_kg"] * ph[name]["radius_m"] ** 2) < 1e-10
                    for i in actual[name]["inertia_kg_m2"]) for name in expected_created if "radius_m" in ph[name]),
        "presence_matches_schedule_at_every_sample": all(set(s["objects"]) == {name for name in ("ball", "box", "football")
            if body_present(cfg, name, s["time_sec"])} for s in all_states),
        "finite_states": all(math.isfinite(x) for s in all_states for body in s["objects"].values()
            for field in ("location", "quaternion_xyzw", "linear_velocity", "angular_velocity") for x in body[field]),
        "first_box_contact_occurs": metrics["first_contact_sec"] is not None,
        "contact_order_valid_if_second_occurs": metrics["second_contact_sec"] is None or metrics["first_contact_sec"] < metrics["second_contact_sec"],
        "heavy_box_remains_stable": metrics["maximum_horizontal_travel_m"]["box"] < .01,
        "no_material_interpenetration": metrics["minimum_signed_contact_gap_m"] > -.0015,
        "no_unexplained_energy_creation": result["quality"]["maximum_mechanical_energy_J"] < energy * 1.025,
        "remaining_energy_dissipates": result["final_state"]["mechanical_energy_J"] < energy,
    }
    if removal is None:
        checks["no_unrequested_intervention"] = not interventions
    else:
        checks["one_correct_removal_event"] = len(interventions) == 1 and interventions[0]["operation"] == "DELETE" \
            and interventions[0]["object_id"] == "B02" and abs(interventions[0]["time_sec"] - removal) < 1e-12
        checks["no_football_contact_after_removal"] = not any("football" in e["pair"] and
            (e["time_sec"] >= removal or e["last_contact_state"]["time_sec"] >= removal) for e in events)
        if interventions:
            event = interventions[0]
            checks["surviving_body_states_unchanged_at_removal"] = all(
                event["before_state"]["objects"][name] == event["after_state"]["objects"][name] for name in ("ball", "box"))
            checks["removed_body_energy_accounted_for"] = event["removed_mechanical_energy_J"] >= 0
        if removal == 0:
            checks["football_never_created"] = "football" not in actual and not any("football" in e["pair"] for e in events)
        else:
            prefix = [s for s in samples if s["time_sec"] < removal]
            source_prefix = [s for s in source["trajectory_samples"] if s["time_sec"] < removal]
            checks["pre_edit_motion_bit_identical_to_source"] = prefix == source_prefix
            at_time = next(s for s in source["trajectory_samples"] if abs(s["time_sec"] - removal) < 1e-12)
            checks["state_at_removal_matches_source_before_deletion"] = interventions[0]["before_state"] == at_time
            checks["all_prior_collisions_preserved"] = [e for e in events if e["time_sec"] < removal] == [e for e in source["contact_events"] if e["time_sec"] < removal]
            checks["frame_48_present_frame_49_absent"] = "football" in result["frames"][47]["objects"] and "football" not in result["frames"][48]["objects"]
            metrics["source_identical_prefix_samples"] = len(prefix)
            metrics["removal_time_sec"] = removal
    if "initial_velocity" in case:
        first, original = metrics["first_contact_sec"], source_metrics["first_contact_sec"]
        checks["launch_edit_changes_impact_timing_as_expected"] = first < original if "fast" in case else first > original
    if "restitution" in case:
        ratio = metrics["first_normal_separation_to_approach_speed_ratio"]
        original = source_metrics["first_normal_separation_to_approach_speed_ratio"]
        checks["normal_rebound_response_changes_as_expected"] = ratio > original if "high" in case else ratio < original
    differences = []
    for edited, original in zip(samples, source["trajectory_samples"]):
        for name in set(edited["objects"]) & set(original["objects"]):
            differences.append(math.dist(edited["objects"][name]["location"], original["objects"][name]["location"]))
    metrics["maximum_position_difference_from_source_m"] = max(differences)
    checks["edit_has_observable_state_or_presence_effect"] = removal is not None or max(differences) > .0001
    return {"accepted": all(checks.values()), "case_id": case, "checks": checks, "metrics": metrics,
            "before": base, "after": cfg, "edit": info,
            "scope": "Physical configuration, actual solver parameters and independent trajectory checks. Edited contacts need not reproduce the source path; offscreen motion is allowed. Full video not yet rendered or visually accepted."}
