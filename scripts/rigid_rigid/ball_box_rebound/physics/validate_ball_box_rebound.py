"""Accept the event order, free rigid response, contact gaps and dissipative motion."""
from __future__ import annotations

import json
import math
from pathlib import Path


def speed(item):
    return math.sqrt(sum(v * v for v in item["linear_velocity"]))


def horizontal_angle(a, b):
    return math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0],
                                   a[0] * b[0] + a[1] * b[1]))


def validate_source(result):
    cfg = result["configuration"]
    ph = cfg["physics"]
    samples = result["trajectory_samples"]
    events = result["contact_events"]
    first = next((e for e in events if e["pair"] == ["ball", "box"]), None)
    second = next((e for e in events if e["pair"] == ["ball", "football"]), None)
    box_drift = max(math.dist(s["objects"]["box"]["location"][:2], ph["box"]["initial_position_m"][:2]) for s in samples)
    football_travel = max(math.dist(s["objects"]["football"]["location"][:2], ph["football"]["initial_position_m"][:2]) for s in samples)
    initial_energy = samples[0]["mechanical_energy_J"]
    peak_energy = result["quality"]["maximum_mechanical_energy_J"]
    last = result["final_state"]["objects"]
    metrics = {"first_contact_sec": first["time_sec"] if first else None,
        "second_contact_sec": second["time_sec"] if second else None,
        "box_maximum_horizontal_drift_m": box_drift, "football_maximum_horizontal_travel_m": football_travel,
        "ball_final_speed_m_per_s": speed(last["ball"]), "football_final_speed_m_per_s": speed(last["football"]),
        "initial_mechanical_energy_J": initial_energy, "peak_mechanical_energy_J": peak_energy,
        "final_mechanical_energy_J": result["final_state"]["mechanical_energy_J"],
        "minimum_signed_contact_gap_m": result["quality"]["minimum_signed_contact_gap_m"]}
    if first:
        vin = first["pre_state"]["objects"]["ball"]["linear_velocity"]
        vout = first.get("separation_state", first["last_contact_state"])["objects"]["ball"]["linear_velocity"]
        metrics["incidence_angle_to_face_normal_degrees"] = math.degrees(math.atan2(abs(vin[0]), abs(vin[1])))
        metrics["first_pre_velocity_m_per_s"] = vin
        metrics["first_separated_velocity_m_per_s"] = vout
    if first and second:
        lo, hi = first["time_sec"], second["time_sec"]
        between = [s["objects"]["ball"]["location"] for s in samples if lo <= s["time_sec"] <= hi]
        metrics["between_impacts_time_sec"] = hi - lo
        metrics["between_impacts_path_length_m"] = sum(math.dist(a, b) for a, b in zip(between, between[1:]))
    if second:
        before = second["pre_state"]["objects"]
        after = second.get("separation_state", second["last_contact_state"])["objects"]
        incoming = before["ball"]["linear_velocity"][:2]
        magnitude = math.hypot(*incoming)
        direction = [v / magnitude for v in incoming]
        cross = [-direction[1], direction[0]]
        axis = [before["football"]["location"][k] - before["ball"]["location"][k] for k in (0, 1)]
        metrics["second_horizontal_incidence_degrees"] = horizontal_angle(direction, axis)
        metrics["second_heading_change_degrees"] = {
            name: horizontal_angle(direction, after[name]["linear_velocity"][:2])
            for name in ("ball", "football")}
        metrics["second_maximum_cross_track_m"] = {
            name: max(abs(sum((s["objects"][name]["location"][k] - before[name]["location"][k]) * cross[k]
                              for k in (0, 1))) for s in samples if s["time_sec"] >= second["time_sec"])
            for name in ("ball", "football")}
        metrics["football_final_to_post_impact_speed_ratio"] = speed(last["football"]) / speed(after["football"])
    ball_r = ph["ball"]["radius_m"]
    w = ph["ball"]["initial_angular_velocity_rad_per_s"]
    v = ph["ball"]["initial_velocity_m_per_s"]
    no_slip = math.hypot(v[0] - w[1] * ball_r, v[1] + w[0] * ball_r)
    checks = {
        "96_sampled_frames_at_24_fps": len(result["frames"]) == 96 and result["fps"] == 24,
        "no_prescribed_motion_or_external_forcing": not result["prescribed_motion"] and not result["constraints"] and not result["external_forces"],
        "initial_no_slip_roll": no_slip < 1e-8,
        "actual_masses_match_configuration": all(abs(result["actual_dynamics"][name]["mass_kg"] - ph[name]["mass_kg"]) < 1e-12 for name in ("ball", "box", "football")),
        "both_balls_use_sphere_colliders": all(result["actual_dynamics"][name]["collision_geometry_type"] == 2 for name in ("ball", "football")),
        "toy_ball_configured_inertia": all(abs(i - ph["ball"]["inertia_factor"] * ph["ball"]["mass_kg"] * ph["ball"]["radius_m"] ** 2) < 1e-10 for i in result["actual_dynamics"]["ball"]["inertia_kg_m2"]),
        "football_shell_inertia": all(abs(i - ph["football"]["inertia_factor"] * ph["football"]["mass_kg"] * ph["football"]["radius_m"] ** 2) < 1e-10 for i in result["actual_dynamics"]["football"]["inertia_kg_m2"]),
        "both_required_contacts": bool(first and second),
        "correct_contact_order": bool(first and second and first["time_sec"] < second["time_sec"] < 2.9),
        "45_degree_oblique_approach": abs(metrics.get("incidence_angle_to_face_normal_degrees", 0) - 45) < 4,
        "oblique_rebound_toward_right_foreground": bool(first and metrics["first_separated_velocity_m_per_s"][0] > 0.1 and metrics["first_separated_velocity_m_per_s"][1] < -0.1),
        "clear_free_travel_between_contacts": metrics.get("between_impacts_path_length_m", 0) > 0.42 and metrics.get("between_impacts_time_sec", 0) > 0.45,
        "heavy_box_stable": box_drift < 0.004,
        "football_rolls_a_short_distance": 0.025 < football_travel < 0.70,
        # A central impact transfers more forward momentum than the former
        # glancing collision. Require low residual speed and strong relative
        # deceleration while retaining the actual physical friction parameters.
        "ball_and_football_slow_down": speed(last["ball"]) < 0.28 and speed(last["football"]) < 0.15
            and metrics.get("football_final_to_post_impact_speed_ratio", 1) < 0.30,
        "near_central_head_on_second_contact": abs(metrics.get("second_horizontal_incidence_degrees", 90)) < 1.0,
        "no_visible_heading_change_at_second_contact": bool(second) and all(abs(a) < 0.25 for a in metrics.get("second_heading_change_degrees", {}).values()),
        "post_contact_cross_track_below_2mm": bool(second) and all(x < 0.002 for x in metrics.get("second_maximum_cross_track_m", {}).values()),
        "no_material_interpenetration": metrics["minimum_signed_contact_gap_m"] > -0.0015,
        "no_unexplained_energy_creation": peak_energy < initial_energy * 1.025,
        "energy_dissipates": result["final_state"]["mechanical_energy_J"] < initial_energy * 0.08,
    }
    return {"accepted": all(checks.values()), "checks": checks, "metrics": metrics,
        "scope": "SI-scale solved contacts and qualitative engineering acceptance; no claim of calibration against measured toy experiments."}


def validate(result, case=None, source=None):
    case = case or result.get("case_id", "source")
    if case == "source":
        return validate_source(result)
    from .validate_edits import validate_edit
    return validate_edit(result, case, source)


if __name__ == "__main__":
    import sys
    report = validate(json.loads(Path(sys.argv[1]).read_text()))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["accepted"] else 1)
