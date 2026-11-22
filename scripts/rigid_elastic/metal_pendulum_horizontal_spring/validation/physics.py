"""Read-only engineering acceptance of compression, native coupling and recovery."""

import argparse
import json
import math
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import numpy as np


def validate(folder):
    c = json.loads((folder / "actual_config.json").read_text())
    m = json.loads((folder / "metrics.json").read_text())
    t = np.load(folder / "trace.npz")["values"]
    p = c["physics"]["pendulum"]
    s = c["physics"]["spring"]
    present = s["present"]
    e0 = (
        (p["ball_mass_kg"] * p["length_m"] + p["rod_mass_kg"] * p["rod_length_m"] / 2)
        * c["physics"]["gravity_m_s2"]
        * (1 - math.cos(math.radians(p["release_angle_deg"])))
    )
    checks = {
        "finite": bool(np.isfinite(t).all()),
        "no_native_warnings": not any(m["warnings"]),
        "initial_release_at_rest": abs(t[0, 2]) < 1e-12
        and abs(t[0, 1] - math.radians(p["release_angle_deg"])) < 1e-12,
        "hinge_inertia": abs(m["native_hinge_inertia_kg_m2"] - p["hinge_inertia_kg_m2"])
        < 1e-12,
        "hinge_contact_virtual_work": m["max_contact_torque_residual_Nm"] < 1e-8,
        "hinge_equation": m["max_hinge_equation_residual_Nm"] < 1e-8,
        "slider_equation": m["max_slider_equation_residual_N"] < 1e-8,
        "contact_penetration_below_0_2mm": m["max_contact_penetration_m"] < 0.0002,
        "native_energy_does_not_exceed_initial": m["native_total_energy_max_growth_J"]
        < 0.01 * e0,
    }
    if present:
        cache = np.load(folder / "trajectory.npz")
        root = cache["spring_centerline"][:, 0]
        rooterr = float(np.max(np.linalg.norm(root - root[0], axis=1)))
        m["fixed_seat_error_m"] = rooterr
        # Recovery speed is an outcome of E with the same guide loss, not a fixed
        # 120 ms requirement. Inspect every complete inter-encounter free interval.
        recovery = []
        episodes = m["contact_episodes"]
        for i, ep in enumerate(episodes):
            complete = i + 1 < len(episodes)
            end = episodes[i + 1]["start_s"] if complete else t[-1, 0]
            free = t[(t[:, 0] > ep["last_touch_s"]) & (t[:, 0] < end) & (t[:, 6] == 0)]
            hits = free[free[:, 4] <= 0.001]
            recovery.append(
                {
                    "encounter": i + 1,
                    "complete_before_next_encounter": complete,
                    "last_touch_s": ep["last_touch_s"],
                    "free_interval_end_s": float(end),
                    "minimum_compression_mm": (
                        float(free[:, 4].min() * 1000) if len(free) else None
                    ),
                    "time_to_within_1mm_after_last_touch_s": (
                        float(hits[0, 0] - ep["last_touch_s"]) if len(hits) else None
                    ),
                }
            )
        complete_intervals = [
            x for x in recovery if x["complete_before_next_encounter"]
        ]
        recovered = bool(complete_intervals) and all(
            x["time_to_within_1mm_after_last_touch_s"] is not None
            for x in complete_intervals
        )
        checks.update(
            first_contact=m["first_contact"] is not None,
            visible_axial_compression=0.005
            < m["max_compression_m"]
            < s["maximum_guide_stroke_m"],
            fixed_end=rooterr < 1e-12,
            slider_mass=abs(
                m["native_slider_effective_mass_kg"] - s["slider_effective_mass_kg"]
            )
            < 1e-12,
            coil_not_bound=m["minimum_spring_length_m"] > s["solid_length_m"] + 0.01,
            elastic_recovery=recovered,
            contact_reverses_ball=any(
                ep["omega_after_rad_s"] < -0.3 for ep in m["contact_episodes"]
            ),
            multiple_compression_rebound_cycles=len(
                [ep for ep in m["contact_episodes"] if ep["peak_compression_mm"] > 2]
            )
            >= 3,
            ball_rises_after_rebound=any(
                ev["angle_deg"] < -10 for ev in m["angular_extrema"]
            ),
        )
    else:
        checks.update(
            no_contact=m["first_contact"] is None and m["max_contact_force_N"] == 0,
            no_slider=np.load(folder / "trajectory.npz")["qpos"].shape[1] == 1,
            no_spring=np.load(folder / "trajectory.npz")["spring_vertices"].shape[1]
            == 0,
            free_pendulum_continues_both_sides=t[:, 1].min() < -0.3
            and t[:, 1].max() > 0.3,
        )
    checks = {k: bool(v) for k, v in checks.items()}
    result = {
        "case": c["case"],
        "engineering_accepted": all(checks.values()),
        "checks": checks,
        "initial_pendulum_energy_J": e0,
        "contact_resolution_s": m["contact_time_resolution_s"],
        "scope": "Conservative guided axial mode, real integrated native hinge/slider/contact; engineering validation, not a measured physical specimen.",
    }
    if present:
        result["recovery_definition"] = (
            "Within 1 mm of unloaded length during every complete free interval before the next swing encounter. A final truncated interval is measured but not required to finish recovery within the clip. The 120 ms observations remain in metrics; they are not a universal material-independent recovery deadline."
        )
        result["recovery_intervals"] = recovery
    (folder / "physics_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run", type=Path)
    a = p.parse_args()
    r = validate(a.run)
    print(json.dumps(r, indent=2))
    if not r["engineering_accepted"]:
        raise SystemExit(1)
