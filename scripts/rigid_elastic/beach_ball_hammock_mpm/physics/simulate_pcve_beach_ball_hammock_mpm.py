"""Run the accepted Taichi MPM rigid/elastic simulation for this scene."""
from __future__ import annotations

import argparse
import json
import math
import os
import runpy
import time
from pathlib import Path


SCENE_DIR = Path(__file__).resolve().parents[1]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=96)
    parser.add_argument("--grid-resolution", type=int, default=64)
    parser.add_argument("--substeps", type=int, default=100)
    parser.add_argument("--young-modulus", type=float, default=15000.0)
    parser.add_argument("--young-modulus-after", type=float)
    parser.add_argument("--young-modulus-change-time", type=float)
    parser.add_argument("--ball-mass", type=float, default=0.25)
    parser.add_argument("--ball-vz", type=float, default=-1.0)
    parser.add_argument("--ball-x", type=float, default=0.80)
    parser.add_argument("--ball-y", type=float, default=-8.92)
    parser.add_argument("--visible-damping", type=float, default=0.9999)
    parser.add_argument("--strain-limit-min", type=float)
    parser.add_argument("--strain-limit-max", type=float)
    parser.add_argument("--inplane-tether-hz", type=float, default=0.0)
    parser.add_argument("--inplane-tether-damping-ratio", type=float, default=0.0)
    parser.add_argument("--end-transition-width", type=float, default=0.0)
    parser.add_argument("--end-tether-hz", type=float, default=0.0)
    parser.add_argument("--end-tether-damping-ratio", type=float, default=0.0)
    parser.add_argument("--pre-roll-seconds", type=float, default=4.0)
    parser.add_argument("--pre-roll-damping", type=float, default=0.998)
    parser.add_argument("--variant-id", default="source")
    parser.add_argument("--max-lateral-displacement", type=float, default=0.02)
    parser.add_argument(
        "--cpu-threads", type=int, default=0,
        help="Taichi CPU threads; 0 = all cores. 1 makes the run bit-reproducible "
             "(the particle-to-grid atomic sums are then added in a fixed order).",
    )
    parser.add_argument(
        "--source-branch-work-dir", type=Path,
        help="Timed edit only: also write the unedited continuation (the source case) here. Both "
             "branches come from one run and share every frame up to the change frame; the "
             "directory needs the prepared scene.blend for its own render stage.",
    )
    parser.add_argument(
        "--source-branch-variant-id", default="source",
        help="variant id recorded for the --source-branch-work-dir case",
    )
    parser.add_argument("--no-ball", action="store_true", help="DELETE beach_ball: the hammock alone")
    parser.add_argument(
        "--no-hammock", action="store_true",
        help="DELETE hammock: the ball falls onto the sand (needs --ground-z, the sand height under the ball)")
    parser.add_argument("--ground-z", type=float)
    parser.add_argument("--ground-restitution", type=float, default=0.4)
    parser.add_argument(
        "--reuse-cache",
        action="store_true",
        help="Revalidate an existing cache/metrics pair without rerunning Taichi.",
    )
    return parser.parse_args()


def set_env(name: str, value) -> None:
    os.environ[name] = str(value)


def main():
    args = parse_args()
    work = args.work_dir.expanduser().resolve()
    surface = work / "mpm_hammock_surface.npz"
    if not surface.is_file():
        raise FileNotFoundError(surface)

    set_env("PCVE_SCENE_ROOT", SCENE_DIR)
    set_env("PCVE_WORK_DIR", work)
    set_env("MPM_RUN_NAME", "mpm_flat_drop_final")
    set_env("MPM_FRAMES", args.frames)
    set_env("MPM_GRID", args.grid_resolution)
    set_env("MPM_SUBSTEPS", args.substeps)
    set_env("MPM_THICKNESS", 0.15)
    set_env("MPM_YOUNG", args.young_modulus)
    timed_young_edit = args.young_modulus_after is not None or args.young_modulus_change_time is not None
    if timed_young_edit and (
        args.young_modulus_after is None or args.young_modulus_change_time is None
    ):
        raise ValueError(
            "--young-modulus-after and --young-modulus-change-time must be provided together"
        )
    if timed_young_edit and not (0.0 <= args.young_modulus_change_time < args.frames / 24.0):
        raise ValueError("Young's modulus change time must fall inside the visible simulation")
    set_env(
        "MPM_YOUNG_AFTER",
        args.young_modulus_after if timed_young_edit else args.young_modulus,
    )
    set_env(
        "MPM_YOUNG_CHANGE_TIME",
        args.young_modulus_change_time if timed_young_edit else -1.0,
    )
    set_env("MPM_POISSON", 0.30)
    set_env("MPM_DENSITY", 6)
    set_env("MPM_BALL_MASS", args.ball_mass)
    set_env("MPM_BALL_VZ", args.ball_vz)
    set_env("MPM_BALL_X", args.ball_x)
    set_env("MPM_BALL_Y", args.ball_y)
    set_env("MPM_LOCK_LATERAL", 0)
    set_env("MPM_RESTITUTION", 0.0)
    set_env("MPM_BALL_DAMPING", 0.9995)
    set_env("MPM_PRE_ROLL_SECONDS", args.pre_roll_seconds)
    set_env("MPM_PRE_ROLL_DAMPING", args.pre_roll_damping)
    set_env("MPM_VISIBLE_DAMPING", args.visible_damping)
    strain_limit_enabled = args.strain_limit_min is not None or args.strain_limit_max is not None
    if strain_limit_enabled and (args.strain_limit_min is None or args.strain_limit_max is None):
        raise ValueError("--strain-limit-min and --strain-limit-max must be provided together")
    if strain_limit_enabled and not (0.0 < args.strain_limit_min < 1.0 < args.strain_limit_max):
        raise ValueError("strain limits must satisfy 0 < min < 1 < max")
    set_env("MPM_STRAIN_LIMIT_ENABLED", int(strain_limit_enabled))
    set_env("MPM_STRAIN_LIMIT_MIN", args.strain_limit_min if strain_limit_enabled else 0.0)
    set_env("MPM_STRAIN_LIMIT_MAX", args.strain_limit_max if strain_limit_enabled else 1000000.0)
    set_env("MPM_INPLANE_TETHER_HZ", args.inplane_tether_hz)
    set_env("MPM_INPLANE_TETHER_DAMPING_RATIO", args.inplane_tether_damping_ratio)
    if args.end_transition_width and args.end_transition_width <= 0.14:
        raise ValueError("--end-transition-width must be greater than the 0.14 m hard-pin width")
    set_env("MPM_END_TRANSITION_WIDTH", args.end_transition_width)
    set_env("MPM_END_TETHER_HZ", args.end_tether_hz)
    set_env("MPM_END_TETHER_DAMPING_RATIO", args.end_tether_damping_ratio)

    set_env("MPM_CPU_THREADS", args.cpu_threads)
    if args.no_ball and args.no_hammock:
        raise ValueError("--no-ball and --no-hammock cannot be combined")
    if args.no_hammock and args.ground_z is None:
        raise ValueError("--no-hammock needs --ground-z")
    set_env("MPM_BALL_PRESENT", int(not args.no_ball))
    set_env("MPM_HAMMOCK_PRESENT", int(not args.no_hammock))
    if args.no_hammock:
        set_env("MPM_GROUND_Z", args.ground_z)
        set_env("MPM_GROUND_RESTITUTION", args.ground_restitution)
    branch = None
    if args.source_branch_work_dir is not None:
        if not timed_young_edit:
            raise ValueError("--source-branch-work-dir needs --young-modulus-after/--young-modulus-change-time")
        if args.reuse_cache:
            raise ValueError("--source-branch-work-dir cannot be combined with --reuse-cache")
        branch = args.source_branch_work_dir.expanduser().resolve()
        if branch == work:
            raise ValueError("--source-branch-work-dir must differ from --work-dir")
        branch.mkdir(parents=True, exist_ok=True)
        set_env("MPM_SOURCE_BRANCH_WORK_DIR", branch)
    else:
        os.environ.pop("MPM_SOURCE_BRANCH_WORK_DIR", None)

    cache_path = work / "mpm_flat_drop_final_cache.npz"
    metrics_path = work / "mpm_flat_drop_final_metrics.json"
    if args.reuse_cache:
        if not cache_path.is_file() or not metrics_path.is_file():
            raise FileNotFoundError("--reuse-cache requires the existing cache and metrics files")
        seconds = 0.0
    else:
        start = time.monotonic()
        runpy.run_path(str(SCENE_DIR / "physics/run_taichi_mpm_hammock.py"), run_name="__main__")
        seconds = time.monotonic() - start

    finalize(work, args, args.variant_id, seconds)
    if branch is not None:
        finalize(branch, args, args.source_branch_variant_id, seconds)
    print(f"PCVE_SIMULATION_SECONDS={seconds:.3f}", flush=True)


def finalize(work: Path, args, variant_id: str, seconds: float) -> None:
    """Check one simulated case and write its simulation_report, scene_spec and edit_manifest."""
    cache_path = work / "mpm_flat_drop_final_cache.npz"
    metrics_path = work / "mpm_flat_drop_final_metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    finite_values = [
        metrics["center_rest_z_m"],
        metrics["center_min_z_m"],
        metrics["ball_final_z_m"],
        metrics["final_ball_vertical_speed_m_s"],
        metrics["ball_max_lateral_displacement_m"],
    ]
    finite_values.extend(sample["max_speed_m_s"] for sample in metrics["pre_roll_samples"])
    if not all(math.isfinite(value) for value in finite_values):
        raise RuntimeError("MPM simulation produced non-finite values; increase substeps or inspect stability")
    deleted = not metrics.get("ball_present", True) or not metrics.get("hammock_present", True)
    if args.frames == 96 and deleted:
        # DELETE edits: no ball/hammock contact exists; the remaining body must still settle and stay put
        # (the hammock alone keeps the residual creep of its pre-rolled state, a few millimetres over the clip).
        if not metrics.get("ball_present", True) and metrics["post_settle_frame48_to_end_max_surface_vertex_delta_m"] >= 1.0e-2:
            raise RuntimeError("Hammock without the ball did not stay at rest")
        if not metrics.get("hammock_present", True) and metrics["settled_frame_12_frame_window"] is None:
            raise RuntimeError("Ball on the sand did not settle")
    elif args.frames == 96:
        if metrics["contact_frame"] is None:
            raise RuntimeError("Accepted 96-frame run did not register ball/hammock contact")
        # A timed Young's modulus edit is documented to keep moving after the change (the
        # README keeps the 15 -> 1.5 kPa @ 2.5 s run as the more visible version), so only
        # constant-stiffness runs must settle inside the clip.
        if metrics["settled_frame_12_frame_window"] is None and metrics.get("young_modulus_change_time_s") is None:
            raise RuntimeError("Accepted 96-frame run did not settle")
        if metrics["pre_contact_max_surface_vertex_drift_m"] >= 1.0e-3:
            raise RuntimeError("Hammock drifted before contact")
        if metrics["ball_max_lateral_displacement_m"] >= args.max_lateral_displacement:
            raise RuntimeError(
                "Ball lateral displacement exceeded the configured acceptance limit "
                f"({args.max_lateral_displacement} m)"
            )
    baseline = {
        "ball_mass_kg": 0.25,
        "ball_initial_speed_m_s": 1.0,
        "hammock_young_modulus_pa": 15000.0,
    }
    actual = {
        "ball_mass_kg": metrics["ball_mass_kg"],
        "ball_initial_speed_m_s": abs(metrics["ball_initial_velocity_m_s"][2]),
        "hammock_young_modulus_pa": metrics["young_modulus_pa"],
    }
    changed = {
        key: {"before": baseline[key], "after": actual[key]}
        for key in baseline
        if actual[key] != baseline[key]
    }
    timed_edit = None
    if metrics.get("young_modulus_change_time_s") is not None:
        timed_edit = {
            "parameter": "hammock_young_modulus_pa",
            "before": metrics["young_modulus_pa"],
            "after": metrics["young_modulus_after_pa"],
            "time_s": metrics["young_modulus_change_time_s"],
            "frame": metrics["young_modulus_change_frame"],
        }
        changed["hammock_young_modulus_pa_at_time"] = timed_edit
    report = {
        "status": "simulated",
        "variant_id": variant_id,
        "seconds": seconds,
        "reused_existing_cache": args.reuse_cache,
        "cache": str(cache_path),
        "metrics": str(metrics_path),
        "contact_frame": metrics["contact_frame"],
        "max_center_deflection_m": metrics["max_center_deflection_m"],
        "ball_max_lateral_displacement_m": metrics["ball_max_lateral_displacement_m"],
        "ball_final_lateral_displacement_m": metrics["ball_final_lateral_displacement_m"],
        "edit": {"baseline": baseline, "actual": actual, "changed": changed},
        "timed_edit": timed_edit,
    }
    if deleted:
        report["deleted_bodies"] = [name for name, key in (("beach_ball", "ball_present"), ("hammock", "hammock_present"))
                                    if not metrics.get(key, True)]
        report["sand_contact"] = metrics.get("sand_contact")
    if metrics.get("same_run_branch") is not None:
        report["same_run_branch"] = metrics["same_run_branch"]
    (work / "simulation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    spec_path = work / "scene_spec.json"
    if spec_path.is_file():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec.pop("verification", None)
        spec["status"] = "simulated_unrendered"
        spec["variant_id"] = variant_id
        spec["physics"]["ball_mass_kg"] = metrics["ball_mass_kg"]
        spec["physics"]["ball_initial_velocity_m_s"] = metrics["ball_initial_velocity_m_s"]
        spec["physics"]["young_modulus_pa"] = metrics["young_modulus_pa"]
        spec["simulation_report"] = report
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (work / "edit_manifest.json").write_text(
        json.dumps(
            {
                "variant_id": variant_id,
                "before": baseline,
                "after": actual,
                "changed": changed,
                "timed_edit": timed_edit,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"PCVE_MPM_CACHE={report['cache']}", flush=True)


if __name__ == "__main__":
    main()

