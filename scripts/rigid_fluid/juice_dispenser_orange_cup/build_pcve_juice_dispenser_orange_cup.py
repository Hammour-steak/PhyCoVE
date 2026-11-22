"""Build the juice-dispenser source and PCVE physical counterfactuals."""

from __future__ import annotations
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import asset, blender
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'build_pcve')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import math
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from simulate_juice_dispenser_orange_cup import PhysicsConfig, INLET_PROTOCOL, SOURCE_PRESET
import edit_vocab
import pcve_edit_dsl as dsl


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RENDER_SCRIPT = HERE / "render_juice_dispenser_orange_cup.py"
DEFAULT_TEMPLATE = asset("scenes/juice_dispenser_orange_cup/scene_template.blend")
DEFAULT_BLENDER = blender()
SOURCE_CASE_ID = "juice_dispenser_orange_cup_source"
SOURCE_DESCRIPTION = {
    "vague": {
        "en": "A countertop dispenser pours orange juice into a clear glass.",
        "zh": "台面饮料机把橙汁注入透明杯子。",
    },
    "quantitative": {
        "en": "Orange juice exits the dispenser at 1.20 m/s for four seconds into a 116 mm rigid glass.",
        "zh": "橙汁以 1.20 m/s 的出口流速流入 116 mm 高的刚性玻璃杯，持续 4 秒。",
    },
}


@dataclass(frozen=True)
class EditCase:
    case_id: str
    dsl: str
    edit_summary: str
    physics_override: dict[str, Any]
    physics_diff: dict[str, Any]
    simulation_quality_override: dict[str, Any] | None = None
    applies_from_sec: float = 0.0


EDIT_CASES = (
    EditCase(
        "edit_stop_flow_at_2s",
        "SET dispenser.flow_speed TO 0 AT FRAME 48",
        "Keep the source outlet speed of 1.20 m/s until 2 seconds, then set it to zero. Stop new supply while the emitted orange juice keeps falling and settling.",
        {"nozzle_speed_change_sec": 2.0, "nozzle_speed_after_m_s": 0.0},
        {"nozzle_speed_m_s (dispenser)": {"from": 1.20, "to": 0.0, "at_sec": 2.0}},
        applies_from_sec=2.0,
    ),
    EditCase(
        "edit_high_flow_speed",
        "SET dispenser.flow_speed TO 2.4",
        "Increase the orange-juice outlet speed from 1.20 to 2.40 m/s with the emitter cross-section and four-second pour interval fixed.",
        {"nozzle_speed_m_s": 2.4},
        {"nozzle_speed_m_s (dispenser)": {"from": 1.20, "to": 2.4}},
    ),
    EditCase(
        "edit_low_flow_speed",
        "SET dispenser.flow_speed TO 0.60",
        "Reduce the orange-juice outlet speed from 1.20 to 0.60 m/s with the emitter cross-section and four-second pour interval fixed.",
        {"nozzle_speed_m_s": 0.60},
        {"nozzle_speed_m_s (dispenser)": {"from": 1.20, "to": 0.60}},
    ),
    EditCase(
        "edit_high_viscosity",
        "SET orange_juice.viscosity TO 0.0004",
        "Increase orange-juice kinematic viscosity by 100 times, from 4e-6 to 4e-4 m^2/s, with outlet speed, aperture and the four-second pour interval fixed.",
        {"orange_juice_kinematic_viscosity_m2_s": 4e-4},
        {"orange_juice_kinematic_viscosity_m2_s (orange_juice)": {"from": 4e-6, "to": 4e-4}},
    ),
    EditCase(
        "edit_paste_like_viscosity",
        "SET orange_juice.viscosity TO 0.04",
        "Increase nominal kinematic viscosity from 4e-6 to 0.04 m^2/s for a cohesive, folding paste-like stream at the same 1.20 m/s outlet speed and injected volume. Uses the explicitly selected N96 effect-quality preset.",
        {"orange_juice_kinematic_viscosity_m2_s": 0.04},
        {"orange_juice_kinematic_viscosity_m2_s (orange_juice)": {"from": 4e-6, "to": 0.04}},
        simulation_quality_override={
            "domain_resolution": 96, "timesteps_min": 8, "timesteps_max": 16,
            "inlet_aperture_mode": "fractional_circle", "inlet_target_area_m2": 3.8503125e-5,
            "inlet_plane_z_m": 0.19535, "viscosity_solver": "coupled_spd", "flip_ratio": 0.0,
            "viscosity_cg_accuracy": 1e-7,
        },
    ),
    EditCase(
        "edit_delete_orange_juice",
        "DELETE orange_juice",
        "Remove all orange juice from frame 1, including the dispenser reservoir, outlet stream and receiving-glass liquid. Keep the dispenser, glass and scene fixed.",
        {"orange_juice_presence": [0]},
        {"orange_juice_presence (orange_juice)": {"from": [1], "to": [0]}},
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the PCVE juice-dispenser suite.")
    parser.add_argument("--out-root", type=Path, default=ROOT / "renders/juice_dispenser_orange_cup/suite_build")
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--resolution", nargs=2, type=int, default=(1280, 720))
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--duration-sec", type=float, default=4.0)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--domain-resolution", type=int, default=160)
    parser.add_argument("--timesteps-min", type=int, default=8)
    parser.add_argument("--timesteps-max", type=int, default=16)
    parser.add_argument("--solver-vendor", type=Path, default=HERE.parents[2]/".runtime/juice_dispenser_orange_cup/solver_vendor")
    parser.add_argument("--threads", type=int, default=8, help="CPU threads per Blender process.")
    parser.add_argument("--skip-fluid-bake", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--render-stills-only", action="store_true")
    parser.add_argument("--preview-frames", nargs="+", type=int)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cases", nargs="*", help="Edit case ids; source is always included.")
    parser.add_argument("--reuse-source", type=Path, help="Reuse a verified accepted source case without rewriting its files or cache.")
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("threads must be positive")
    return args


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def edit_info(case: EditCase, fps: int = 24) -> dict[str, Any]:
    # Mantaflow's frame k is the state at t = k / fps, and the inlet integrator clips the substep that straddles a
    # timed change, so a change at t first shows in frame round(t * fps) (frame 48 for 2.0 s at 24 fps).
    frame = round(case.applies_from_sec * fps) if case.applies_from_sec else 1
    statement = case.dsl
    if case.applies_from_sec:
        statement = statement.split(" AT FRAME ")[0] + f" AT FRAME {frame}"
    return {
        "edit_dsl": statement,
        "edit_summary": case.edit_summary,
        "applies_from_frame": frame,
        "prompts": dsl.make_prompts(dsl.parse(statement, edit_vocab.VOCAB), edit_vocab.VOCAB),
        "physics_diff": {**case.physics_diff, "timing": {"from_frame": 1, "to_frame": frame}},
        "physics_override": case.physics_override,
        "simulation_quality_override": case.simulation_quality_override or {},
    }


def quality_settings(args: argparse.Namespace, overrides: Path | None) -> dict[str, Any]:
    quality = {key: getattr(args, key) for key in ("domain_resolution", "timesteps_min", "timesteps_max")}
    quality.update(inlet_aperture_mode="binary", inlet_target_area_m2=None,
                   inlet_plane_z_m=None, viscosity_solver="auto", viscosity_cg_accuracy=1e-7, flip_ratio=0.92)
    if overrides:
        quality.update(json.loads(overrides.read_text()).get("simulation_quality", {}))
    return quality


def command(args: argparse.Namespace, case_dir: Path, overrides: Path | None) -> list[str]:
    cmd = [
        str(args.blender.expanduser()),
        "-b",
        str(args.template.expanduser()),
        "-t",
        str(args.threads),
        "--python-exit-code",
        "1",
        "--python",
        str(RENDER_SCRIPT),
        "--",
        "--out-dir",
        str(case_dir),
        "--solver-vendor", str(args.solver_vendor),
        "--resolution",
        *map(str, args.resolution),
        "--fps",
        str(args.fps),
        "--duration-sec",
        str(args.duration_sec),
        "--samples",
        str(args.samples),
        "--domain-resolution",
        str(args.domain_resolution),
        "--timesteps-min", str(args.timesteps_min),
        "--timesteps-max", str(args.timesteps_max),
    ]
    if overrides:
        cmd += ["--scenario-overrides-json", str(overrides)]
    if args.skip_fluid_bake:
        cmd.append("--skip-fluid-bake")
    if args.skip_render:
        cmd.append("--skip-render")
    if args.render_stills_only:
        cmd.append("--render-stills-only")
    if args.preview_frames:
        cmd += ["--preview-frames", *map(str, args.preview_frames)]
    return cmd


def run_case(args: argparse.Namespace, case_dir: Path, overrides: Path | None) -> tuple[str, float]:
    cmd = command(args, case_dir, overrides)
    if args.dry_run:
        print(" ".join(cmd))
        return "dry_run", 0.0
    if args.skip_existing and (case_dir / "video.mp4").is_file():
        metadata_path = case_dir / "scenario_metadata.json"
        if not metadata_path.is_file():
            raise RuntimeError(f"Cannot reuse {case_dir}: missing physics metadata")
        metadata = json.loads(metadata_path.read_text())
        quality = quality_settings(args, overrides)
        expected_protocol = INLET_PROTOCOL if quality["inlet_aperture_mode"] == "binary" else "fixed_fractional_aperture_conservative_surface_inlet_7"
        if metadata.get("inlet_protocol") != expected_protocol:
            raise RuntimeError(f"Cannot reuse a cache without the conservative inlet: {case_dir}")
        if metadata.get("source_preset") != SOURCE_PRESET:
            raise RuntimeError(f"Cannot reuse another source preset: {case_dir}")
        for key in ("timesteps_min", "timesteps_max"):
            if metadata["simulation_quality"].get(key) != quality[key]:
                raise RuntimeError(f"Cannot reuse different {key}: {case_dir}")
        actual = metadata["physics"]
        expected = json.loads(json.dumps(asdict(PhysicsConfig())))
        expected.update({"fps": args.fps, "duration_sec": args.duration_sec})
        if overrides:
            expected.update(json.loads(overrides.read_text())["physics"])
        expected_solver = quality["viscosity_solver"]
        if expected_solver == "auto":
            expected_solver = "coupled_spd" if expected["orange_juice_kinematic_viscosity_m2_s"] >= 1e-3 else "diffusion"
        if metadata["simulation_quality"].get("viscosity_solver", "diffusion") != expected_solver:
            raise RuntimeError(f"Cannot reuse {case_dir}: different viscosity solver")
        for key, value in expected.items():
            if actual.get(key, None) != value:
                raise RuntimeError(f"Cannot reuse {case_dir}: mismatched {key}")
        if "flow_rate_ml_s" in actual:
            raise RuntimeError(f"Cannot reuse a historical flow-rate case as a speed case: {case_dir}")
        if not expected["orange_juice_presence"][0]:
            audit_path = case_dir / "liquid_presence_audit.json"
            if not audit_path.is_file():
                raise RuntimeError(f"Cannot reuse {case_dir}: missing liquid-deletion audit")
            audit = json.loads(audit_path.read_text())
            if metadata.get("simulation_mode") != "no_liquid" or metadata.get("cache_directory") is not None:
                raise RuntimeError(f"Cannot reuse {case_dir}: liquid still enabled")
            if audit.get("status") != "passed" or audit.get("remaining_liquid_objects") != []:
                raise RuntimeError(f"Cannot reuse {case_dir}: incomplete liquid deletion")
            measurements = json.loads((case_dir / "volume_measurements.json").read_text())
            if len(measurements["frames"]) != round(args.fps * args.duration_sec) or any(
                row[key] != 0 for row in measurements["frames"]
                for key in ("all_liquid_mesh_volume_ml", "retained_volume_ml", "injected_volume_ml", "triangles")
            ):
                raise RuntimeError(f"Cannot reuse {case_dir}: nonzero or incomplete absent-liquid volumes")
        for name in ("boundary_flux.json", "volume_measurements.json", "video_verification.json"):
            if not (case_dir / name).is_file():
                raise RuntimeError(f"Cannot reuse {case_dir}: missing {name}")
        if metadata["simulation_quality"]["domain_resolution"] != quality["domain_resolution"]:
            raise RuntimeError(f"Cannot reuse {case_dir}: different solver resolution")
        for key in ("inlet_aperture_mode", "inlet_target_area_m2", "inlet_plane_z_m"):
            default = "binary" if key == "inlet_aperture_mode" else None
            if metadata["simulation_quality"].get(key, default) != quality[key]:
                raise RuntimeError(f"Cannot reuse {case_dir}: different {key}")
        if not math.isclose(metadata["simulation_quality"].get("flip_ratio",0.92), quality["flip_ratio"],abs_tol=1e-7):
            raise RuntimeError(f"Cannot reuse {case_dir}: different particle/grid coupling")
        if expected_solver == "coupled_spd" and metadata["simulation_quality"].get("viscosity_cg_accuracy") != quality["viscosity_cg_accuracy"]:
            raise RuntimeError(f"Cannot reuse {case_dir}: different viscosity convergence accuracy")
        if metadata["render"] != {"resolution": list(args.resolution), "fps": args.fps,
                                   "frames": round(args.fps*args.duration_sec), "samples": args.samples}:
            raise RuntimeError(f"Cannot reuse {case_dir}: different render settings")
        verification = json.loads((case_dir / "video_verification.json").read_text())
        if verification.get("full_decode") != "passed" or verification.get("sha256") != hashlib.sha256((case_dir / "video.mp4").read_bytes()).hexdigest():
            raise RuntimeError(f"Cannot reuse {case_dir}: unverified or replaced video")
        return "skipped_existing", 0.0
    case_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    log_path = case_dir / "blender.log"
    with log_path.open("w", encoding="utf-8") as stream:
        result = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT)
    elapsed = time.perf_counter() - started
    if result.returncode:
        tail = "\n".join(log_path.read_text(errors="replace").splitlines()[-80:])
        raise RuntimeError(f"Blender failed for {case_dir.name}:\n{tail}")
    return "completed", elapsed


def outputs(case_dir: Path) -> dict[str, str]:
    names = (
        "video.mp4",
        "scene.blend",
        "scene_baked_final.blend",
        "ground_truth.json",
        "scenario_metadata.json",
        "video_verification.json",
        "parameter_audit.json",
        "boundary_flux.json",
        "volume_measurements.json",
        "liquid_presence_audit.json",
        "coupled_viscosity_trace.json",
    )
    return {
        name.rsplit(".", 1)[0]: str((case_dir / name).resolve())
        for name in names
        if (case_dir / name).exists()
    }


def main() -> None:
    args = parse_args()
    args.out_root = args.out_root.expanduser().resolve()
    args.template = args.template.expanduser().resolve()
    if not args.template.is_file():
        raise SystemExit(f"Missing approved scene template: {args.template}")
    selected = set(args.cases or [case.case_id for case in EDIT_CASES])
    unknown = selected - {case.case_id for case in EDIT_CASES}
    if unknown:
        raise SystemExit(f"Unknown case id(s): {sorted(unknown)}")

    defaults = PhysicsConfig()
    manifest: dict[str, Any] = {
        "schema_version": 4,
        "suite_name": "pcve_juice_dispenser_orange_cup_suite",
        "interaction_category": "rigid_fluid",
        "description": "A countertop dispenser pours orange juice into a stationary transparent glass.",
        "coupling": "prescribed inflow against a static rigid glass; no native two-way feedback",
        "template": str(args.template),
        "baseline_physics": {
            name: getattr(defaults, name)
            for name in (
                "orange_juice_density_kg_m3",
                "orange_juice_kinematic_viscosity_m2_s",
                "nozzle_speed_m_s",
                "orange_juice_presence",
                "glass_presence",
                "gravity_m_s2",
                "pour_start_sec",
                "pour_end_sec",
            )
        },
        "total_frames": int(round(args.fps * args.duration_sec)),
        "resolution": list(args.resolution),
        "fps": args.fps,
        "duration_sec": args.duration_sec,
        "fluid_domain_resolution": args.domain_resolution,
        "inlet_protocol": INLET_PROTOCOL,
        "source_preset": SOURCE_PRESET,
        "timesteps_min": args.timesteps_min,
        "timesteps_max": args.timesteps_max,
        "source": None,
        "edits": [],
    }
    manifest_path = args.out_root / "suite_manifest.json"
    write_json(manifest_path, manifest)

    source_dir = args.out_root / "cases" / SOURCE_CASE_ID
    source_args = args
    if args.reuse_source:
        source_dir = args.reuse_source.expanduser().resolve()
        if not (source_dir / "video.mp4").is_file():
            raise RuntimeError(f"Missing accepted source video: {source_dir}")
        source_args = argparse.Namespace(**{**vars(args), "skip_existing": True})
    status, elapsed = run_case(source_args, source_dir, None)
    manifest["source"] = {
        "case_id": SOURCE_CASE_ID,
        "kind": "source",
        "interaction_category": "rigid_fluid",
        "description": SOURCE_DESCRIPTION,
        "status": status,
        "elapsed_sec": round(elapsed, 3),
        "outputs": outputs(source_dir),
    }
    write_json(manifest_path, manifest)

    for case in EDIT_CASES:
        if case.case_id not in selected:
            continue
        case_dir = args.out_root / "cases" / case.case_id
        info = edit_info(case, fps=args.fps)
        override_path = case_dir / "scenario_overrides.json"
        write_json(override_path, {"physics": info["physics_override"],
                                   "simulation_quality": info["simulation_quality_override"]})
        write_json(case_dir / "prompts.json", {
            "schema_version": 2,
            "case_id": case.case_id,
            "source_case_id": SOURCE_CASE_ID,
            **{key: info[key] for key in (
                "edit_dsl",
                "edit_summary",
                "applies_from_frame",
                "physics_diff",
                "prompts",
                "simulation_quality_override",
            )},
        })
        status, elapsed = run_case(args, case_dir, override_path)
        manifest["edits"].append({
            "case_id": case.case_id,
            "kind": "edit",
            "source_case_id": SOURCE_CASE_ID,
            **{key: info[key] for key in (
                "edit_dsl",
                "edit_summary",
                "applies_from_frame",
                "physics_diff",
                "prompts",
                "simulation_quality_override",
            )},
            "status": status,
            "elapsed_sec": round(elapsed, 3),
            "outputs": outputs(case_dir),
        })
        write_json(manifest_path, manifest)
    print(manifest_path)


if __name__ == "__main__":
    main()
