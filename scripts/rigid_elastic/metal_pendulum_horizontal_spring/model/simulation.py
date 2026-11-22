"""Integrate the pendulum and horizontal compression spring through native contact."""

import argparse
import json
import math
import platform
import sys
import time
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import mujoco
import numpy as np

from model.dynamics import build_model, centerline, contacts
from model.mesh import tube
from scene_config import CASES, configuration
from scene_paths import CACHE_FILES, cache_matches, sha256


def dump(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )


def simulate(c, out, reuse_cache=False):
    if (out / "metrics.json").exists():
        if not reuse_cache or not cache_matches(out, c):
            raise RuntimeError(
                "Completed cache cannot be overwritten; use a fresh directory or --reuse-cache with identical inputs, code and hashes"
            )
        result = json.loads((out / "metrics.json").read_text())
        print(json.dumps({"case": c["case"], "cache_reused": True}), flush=True)
        return result
    out.mkdir(parents=True, exist_ok=True)
    if (out / "actual_config.json").exists() and json.loads(
        (out / "actual_config.json").read_text()
    ) != c:
        raise RuntimeError(
            "Output contains a different configuration; use an independent directory"
        )
    dump(out / "actual_config.json", c)
    m, d, xml = build_model(c)
    (out / "model_input.xml").write_text(xml)
    mujoco.mj_saveLastXML(str(out / "model.xml"), m)
    mujoco.mj_saveModel(m, str(out / "model.mjb"))
    p = c["physics"]["pendulum"]
    s = c["physics"]["spring"]
    q = c["simulation_quality"]
    present = s["present"]
    # physics.pendulum.present (default true): false = no pendulum body, so no hinge coordinate and the
    # slider is native dof 0. Hinge quantities of a deleted pendulum are recorded as 0.
    ball = p.get("present", True)
    sj = 1 if ball else 0

    def H(values):
        return values[0] if ball else np.float64(0.0)

    steps = q["substeps_per_frame"]
    tn = q["trace_samples_per_frame"]
    batch = steps // tn
    if steps % tn:
        raise ValueError("Substeps must be divisible by trace sample count")
    native = {
        "nq": m.nq,
        "nv": m.nv,
        "actuators": m.nu,
        "armature": m.dof_armature.tolist(),
        "dt_s": float(m.opt.timestep),
        "hinge_inertia_kg_m2": float(H(m.dof_M0)),
        "joint_stiffness": m.jnt_stiffness.tolist(),
        "joint_damping": m.dof_damping.tolist(),
        "native_generalized_mass": m.dof_M0.tolist(),
        "contact_solref": m.geom_solref.tolist(),
        "contact_solimp": m.geom_solimp.tolist(),
        "spring_axis_world": [1, 0, 0],
        "model": "Reduced guided axial elastic mode, not full wire FEM",
    }
    dump(out / "native_model_audit.json", native)
    snapshots = {
        k: []
        for k in [
            "time",
            "theta",
            "omega",
            "compression",
            "qpos",
            "qvel",
            "spring_centerline",
        ]
    }
    rows = []
    windows = []
    active = None
    first = None
    last_free = 0.0
    prev = False
    start = time.monotonic()

    def frame():
        comp = float(d.qpos[sj]) if present else 0.0
        for key, value in [
            ("time", d.time),
            ("theta", H(d.qpos)),
            ("omega", H(d.qvel)),
            ("compression", comp),
            ("qpos", d.qpos),
            ("qvel", d.qvel),
            ("spring_centerline", centerline(c, comp)),
        ]:
            snapshots[key].append(np.array(value, copy=True))

    def trace():
        nonlocal active, first, last_free, prev
        n, f, tq, pen = contacts(m, d)
        comp = float(d.qpos[sj]) if present else 0.0
        cv = float(d.qvel[sj]) if present else 0.0
        terr = abs(tq - H(d.qfrc_constraint))
        eqerr = abs(
            p["hinge_inertia_kg_m2"] * H(d.qacc)
            + H(d.qfrc_bias)
            - H(d.qfrc_passive)
            - H(d.qfrc_constraint)
        )
        seqerr = (
            abs(
                s["slider_effective_mass_kg"] * d.qacc[sj]
                + d.qfrc_bias[sj]
                - d.qfrc_passive[sj]
                - d.qfrc_constraint[sj]
            )
            if present
            else 0.0
        )
        if n and not prev:
            active = {
                "start_s": float(d.time),
                "start_bracket_s": [last_free, float(d.time)],
                "omega_before_rad_s": float(rows[-1][2]) if rows else 0.0,
            }
            if first is None:
                first = active.copy()
        if not n and prev:
            active.update(end_s=float(d.time), omega_after_rad_s=float(H(d.qvel)))
            windows.append(active)
            active = None
        if not n:
            last_free = float(d.time)
        prev = bool(n)
        elastic = 0.5 * s["axial_stiffness_N_m"] * comp**2 if present else 0.0
        force = s["axial_stiffness_N_m"] * max(comp, 0.0) if present else 0.0
        shear = (
            s["wahl_factor"]
            * 8
            * force
            * (2 * s["mean_coil_radius_m"])
            / (math.pi * (2 * s["wire_radius_m"]) ** 3)
            if present
            else 0.0
        )
        rows.append(
            [
                d.time,
                H(d.qpos),
                H(d.qvel),
                H(d.qacc),
                comp,
                cv,
                n,
                np.linalg.norm(f),
                *f,
                tq,
                H(d.qfrc_constraint),
                pen,
                terr,
                eqerr,
                seqerr,
                d.energy[0],
                d.energy[1],
                elastic,
                np.dot(m.dof_damping, d.qvel**2),
                force,
                shear,
                s["free_length_m"] - comp if present else 0.0,
            ]
        )

    frame()
    trace()
    for k in range(q["frames"]):
        for sample in range(tn):
            mujoco.mj_step(m, d, nstep=batch)
            mujoco.mj_forward(m, d)
            trace()
            if not np.isfinite(d.qpos).all() or any(w.number for w in d.warning):
                raise RuntimeError("Nonfinite state or native warning")
        frame()
    if active:
        active.update(
            end_s=float(d.time), omega_after_rad_s=float(H(d.qvel)), ongoing=True
        )
        windows.append(active)
    cache = {k: np.asarray(v) for k, v in snapshots.items()}
    cache["rest_centerline"] = centerline(c)
    if present:
        meshes = [
            tube(x, s["wire_radius_m"], radial=12, subdiv=1)
            for x in cache["spring_centerline"]
        ]
        cache["spring_vertices"] = np.asarray([x[0] for x in meshes], dtype=np.float32)
        cache["surface_faces"] = meshes[0][1]
    else:
        cache["spring_vertices"] = np.empty((q["frames"] + 1, 0, 3), dtype=np.float32)
        cache["surface_faces"] = np.empty((0, 4), dtype=int)
    np.savez_compressed(out / "trajectory.npz", **cache)
    names = [
        "time",
        "theta_rad",
        "omega_rad_s",
        "alpha_rad_s2",
        "compression_m",
        "compression_velocity_m_s",
        "ball_contact_count",
        "contact_force_N",
        "force_x_N",
        "force_y_N",
        "force_z_N",
        "contact_torque_Nm",
        "native_hinge_contact_torque_Nm",
        "max_penetration_m",
        "torque_residual_Nm",
        "hinge_equation_residual_Nm",
        "slider_equation_residual_N",
        "gravity_and_elastic_potential_J",
        "kinetic_J",
        "spring_elastic_energy_J",
        "viscous_dissipation_power_W",
        "elastic_force_N",
        "wahl_shear_stress_Pa",
        "spring_length_m",
    ]
    t = np.asarray(rows)
    np.savez_compressed(out / "trace.npz", values=t, columns=np.array(names))
    np.savetxt(out / "trace.csv", t, delimiter=",", header=",".join(names), comments="")
    peak = int(np.argmax(t[:, 4]))
    events = []
    for i in range(1, len(t) - 1):
        if t[i - 1, 2] * t[i + 1, 2] < 0 and abs(t[i, 2]) <= min(
            abs(t[i - 1, 2]), abs(t[i + 1, 2])
        ):
            events.append(
                {
                    "time_s": float(t[i, 0]),
                    "angle_deg": float(np.degrees(t[i, 1])),
                    "ball_height_gain_m": p["length_m"] * (1 - math.cos(t[i, 1])),
                }
            )
    # Group all touches within one swing encounter, including short separation
    # while the light head runs ahead. A free left turning point separates swings.
    # Raw continuous-contact windows above retain every separation unchanged.
    episodes = []
    inds = np.flatnonzero(t[:, 6] > 0)
    if len(inds):
        left_turns = np.flatnonzero((t[:-1, 2] < 0) & (t[1:, 2] >= 0) & (t[:-1, 1] < 0))
        swing_ids = np.searchsorted(left_turns, inds)
        for group in np.split(inds, np.flatnonzero(np.diff(swing_ids) > 0) + 1):
            i, j = int(group[0]), int(group[-1])
            k = min(j + 1, len(t) - 1)
            end = min(int(np.searchsorted(t[:, 0], t[k, 0] + 0.12)), len(t))
            episodes.append(
                {
                    "start_s": float(t[i, 0]),
                    "last_touch_s": float(t[j, 0]),
                    "omega_before_rad_s": float(t[max(i - 1, 0), 2]),
                    "omega_after_rad_s": float(t[k, 2]),
                    "peak_compression_mm": float(t[group, 4].max() * 1000),
                    "minimum_compression_next_0_12s_mm": (
                        float(t[k:end, 4].min() * 1000) if end > k else 0.0
                    ),
                    "peak_force_N": float(t[group, 7].max()),
                }
            )
    recovery = []
    for at in [0.35, 0.5, 1.0, 2.0, 3.0, 4.0]:
        i = int(np.argmin(abs(t[:, 0] - at)))
        recovery.append(
            {
                "time_s": float(t[i, 0]),
                "compression_mm": float(t[i, 4] * 1000),
                "angle_deg": float(np.degrees(t[i, 1])),
                "omega_rad_s": float(t[i, 2]),
            }
        )
    metrics = {
        "case": c["case"],
        "first_contact": first,
        "contact_windows": windows,
        "contact_episodes": episodes,
        "max_compression_m": float(t[peak, 4]),
        "max_compression_time_s": float(t[peak, 0]),
        "min_compression_m": float(t[:, 4].min()),
        "max_contact_force_N": float(t[:, 7].max()),
        "max_contact_penetration_m": float(t[:, 13].max()),
        "max_contact_torque_residual_Nm": float(t[:, 14].max()),
        "max_hinge_equation_residual_Nm": float(t[:, 15].max()),
        "max_slider_equation_residual_N": float(t[:, 16].max()),
        "fixed_seat_error_m": 0.0,
        "recovery_samples": recovery,
        "angular_extrema": events,
        "final_angle_deg": float(np.degrees(H(d.qpos))),
        "final_omega_rad_s": float(H(d.qvel)),
        "native_hinge_inertia_kg_m2": float(H(m.dof_M0)),
        "native_slider_effective_mass_kg": float(m.dof_M0[sj]) if present else 0.0,
        "max_wahl_shear_stress_Pa": float(t[:, 22].max()),
        "minimum_spring_length_m": float(t[:, 23].min()) if present else None,
        "native_total_energy_initial_J": float(t[0, 17] + t[0, 18]),
        "native_total_energy_final_J": float(t[-1, 17] + t[-1, 18]),
        "native_total_energy_max_growth_J": float(
            max(0, np.max(t[:, 17] + t[:, 18]) - t[0, 17] - t[0, 18])
        ),
        "warnings": [int(w.number) for w in d.warning],
        "contact_time_resolution_s": batch * m.opt.timestep,
        "simulation_seconds": time.monotonic() - start,
        "coupling": "Native sphere/head contact couples a free dynamic hinge and a free dynamic slider with conservative axial elastic energy. No actuators, prescribed trajectory, force callbacks, or timed impulses.",
    }
    metrics["contact_episode_definition"] = (
        "Contacts within one swing encounter, separated by a free left turning point; raw continuous-contact windows and all gaps are retained."
    )
    dump(out / "metrics.json", metrics)
    dump(
        out / "software.json",
        {
            "mujoco": mujoco.__version__,
            "numpy": np.__version__,
            "python": platform.python_version(),
            "cache_hashes": {name: sha256(out / name) for name in CACHE_FILES},
        },
    )
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return metrics


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--case", choices=CASES, default="source")
    p.add_argument("--frames", type=int)
    p.add_argument("--substeps", type=int)
    p.add_argument("--young-modulus", type=float)
    p.add_argument("--reuse-cache", action="store_true")
    a = p.parse_args()
    overrides = {}
    for val, key in [
        (a.frames, "simulation_quality.frames"),
        (a.substeps, "simulation_quality.substeps_per_frame"),
        (a.young_modulus, "physics.spring.young_modulus_Pa"),
    ]:
        if val is not None:
            overrides[key] = val
    simulate(
        configuration(a.case, overrides), a.out.resolve(), reuse_cache=a.reuse_cache
    )


if __name__ == "__main__":
    main()
