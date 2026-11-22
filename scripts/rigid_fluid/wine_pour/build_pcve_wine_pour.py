"""Build the wine-pour source and PCVE physical counterfactuals."""

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
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
from simulate_wine_pour import PhysicsConfig
import edit_vocab
import pcve_edit_dsl as dsl


RENDER_SCRIPT = HERE / "render_wine_pour.py"
DEFAULT_TEMPLATE = asset("scenes/wine_pour/scene_template.blend")
DEFAULT_BLENDER = blender()
DEFAULT_OUT_ROOT = ROOT / "renders/wine_pour/suite_build"
SOURCE_CASE_ID = "wine_pour_source"
SOURCE_DESCRIPTION = {
    "vague": {
        "en": "A dark bottle pours red wine into a clear stemless glass.",
        "zh": "深色酒瓶把红酒倒入透明无梗酒杯。",
    },
    "quantitative": {
        "en": "Wine at 990 kg/m³ flows at 60 mL/s for 3 seconds into a 125 mm rigid glass.",
        "zh": "密度 990 kg/m³ 的红酒以 60 mL/s 流入 125 mm 高的刚性酒杯，持续 3 秒。",
    },
}


@dataclass(frozen=True)
class EditCase:
    case_id: str
    dsl: str
    edit_summary: str
    physics_override: dict[str, Any]
    physics_diff: dict[str, Any]
    applies_from_frame: int = 1


EDIT_CASES = (
    EditCase(
        "edit_high_viscosity_wine",
        "SET wine.viscosity TIMES 2000",
        "Increase wine kinematic viscosity from 1.7e-6 to 0.0034 m²/s, producing a very thick, syrup-like stream and sluggish surface response.",
        {"wine_kinematic_viscosity_m2_s": 0.0034},
        {"kinematic_viscosity_m2_s (wine)": {"from": 1.7e-6, "to": 0.0034}},
    ),
    EditCase(
        "edit_high_flow_rate",
        "SET bottle.flow_rate TO 180",
        "Increase the prescribed volumetric flow rate from 60 to 180 mL/s while retaining the same outlet speed and pour interval.",
        {"flow_rate_ml_s": 180.0},
        {"flow_rate_ml_s (bottle)": {"from": 60.0, "to": 180.0}},
    ),
    EditCase(
        "edit_low_flow_rate",
        "SET bottle.flow_rate TO 20",
        "Reduce the prescribed volumetric flow rate from 60 to 20 mL/s while retaining the same outlet speed and pour interval.",
        {"flow_rate_ml_s": 20.0},
        {"flow_rate_ml_s (bottle)": {"from": 60.0, "to": 20.0}},
    ),
    EditCase(
        "edit_delete_wine",
        "DELETE wine",
        "Remove all wine from the scene from the first frame.",
        {"wine_presence": [0]},
        {"wine_presence": {"from": [1], "to": [0]}},
    ),
    EditCase(
        "edit_stop_flow_at_1s",
        "SET bottle.flow_speed TO 0 AT FRAME 25",
        "Set the wine outlet speed to zero and disable inflow from frame 25 (1.0 second) onwards.",
        {"nozzle_speed_change_frame": 25, "nozzle_speed_after_m_s": 0.0},
        {
            "nozzle_speed_change_frame": {"from": None, "to": 25},
            "nozzle_speed_after_m_s": {"from": None, "to": 0.0},
        },
        applies_from_frame=25,
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the PCVE wine-pour suite.")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--resolution", nargs=2, type=int, default=(1280, 720))
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--duration-sec", type=float, default=4.0)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--domain-resolution", type=int, default=144)
    parser.add_argument("--skip-fluid-bake", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--render-stills-only", action="store_true")
    parser.add_argument("--preview-frames", nargs="+", type=int)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cases", nargs="*", help="Edit case ids; source is always included.")
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def edit_info(case: EditCase) -> dict[str, Any]:
    return {
        "edit_dsl": case.dsl,
        "edit_summary": case.edit_summary,
        "applies_from_frame": case.applies_from_frame,
        "prompts": dsl.make_prompts(dsl.parse(case.dsl, edit_vocab.VOCAB), edit_vocab.VOCAB),
        "physics_diff": {
            **case.physics_diff,
            "timing": {
                "from_frame": case.applies_from_frame,
                "to_frame": case.applies_from_frame,
            },
        },
        "physics_override": case.physics_override,
    }


def command(
    args: argparse.Namespace,
    case_dir: Path,
    overrides: Path | None,
    case: EditCase | None = None,
) -> list[str]:
    cmd = [
        str(args.blender.expanduser()), "-b", str(args.template.expanduser()), "--python-exit-code", "1",
        "--python", str(RENDER_SCRIPT), "--", "--out-dir", str(case_dir),
        "--resolution", *map(str, args.resolution), "--fps", str(args.fps),
        "--duration-sec", str(args.duration_sec), "--samples", str(args.samples),
        "--domain-resolution", str(args.domain_resolution),
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


def run_case(
    args: argparse.Namespace,
    case_dir: Path,
    overrides: Path | None,
    case: EditCase | None = None,
) -> tuple[str, float]:
    cmd = command(args, case_dir, overrides, case)
    if args.dry_run:
        print(" ".join(cmd))
        return "dry_run", 0.0
    if args.skip_existing and (case_dir / "video.mp4").is_file():
        return "skipped_existing", 0.0
    case_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    log_path = case_dir / "blender.log"
    with log_path.open("w", encoding="utf-8") as stream:
        result = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT)
    elapsed = time.perf_counter() - started
    if result.returncode:
        tail = "\n".join(log_path.read_text(errors="replace").splitlines()[-60:])
        raise RuntimeError(f"Blender failed for {case_dir.name}:\n{tail}")
    return "completed", elapsed


def outputs(case_dir: Path) -> dict[str, str]:
    names = (
        "video.mp4", "scene.blend", "scene_baked_final.blend",
        "ground_truth.json", "scenario_metadata.json", "video_verification.json",
    )
    return {
        name.rsplit(".", 1)[0]: str((case_dir / name).resolve())
        for name in names if (case_dir / name).exists()
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

    manifest: dict[str, Any] = {
        "schema_version": 3,
        "suite_name": "pcve_wine_pour_suite",
        "interaction_category": "rigid_fluid",
        "description": "A tilted bottle pours red wine into a stationary transparent glass.",
        "coupling": "prescribed inflow drives Mantaflow against a static rigid glass; no native two-way feedback",
        "template": str(args.template),
        "baseline_physics": {
            name: getattr(PhysicsConfig(), name)
            for name in (
                "wine_density_kg_m3", "wine_kinematic_viscosity_m2_s", "flow_rate_ml_s",
                "nozzle_speed_m_s", "wine_presence", "glass_presence", "gravity_m_s2",
                "pour_start_sec", "pour_end_sec", "nozzle_speed_change_frame",
                "nozzle_speed_after_m_s",
            )
        },
        "total_frames": int(round(args.fps * args.duration_sec)),
        "resolution": list(args.resolution),
        "fps": args.fps,
        "duration_sec": args.duration_sec,
        "fluid_domain_resolution": args.domain_resolution,
        "source": None,
        "edits": [],
    }
    manifest_path = args.out_root / "suite_manifest.json"
    write_json(manifest_path, manifest)

    source_dir = args.out_root / "cases" / SOURCE_CASE_ID
    status, elapsed = run_case(args, source_dir, None)
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
        info = edit_info(case)
        override_path = case_dir / "scenario_overrides.json"
        write_json(override_path, {"physics": info["physics_override"]})
        write_json(case_dir / "prompts.json", {
            "schema_version": 2,
            "case_id": case.case_id,
            "source_case_id": SOURCE_CASE_ID,
            **{key: info[key] for key in (
                "edit_dsl", "edit_summary", "applies_from_frame", "physics_diff", "prompts"
            )},
        })
        status, elapsed = run_case(args, case_dir, override_path, case)
        manifest["edits"].append({
            "case_id": case.case_id,
            "kind": "edit",
            "source_case_id": SOURCE_CASE_ID,
            **{key: info[key] for key in (
                "edit_dsl", "edit_summary", "applies_from_frame", "physics_diff", "prompts"
            )},
            "status": status,
            "elapsed_sec": round(elapsed, 3),
            "outputs": outputs(case_dir),
        })
        write_json(manifest_path, manifest)
    print(manifest_path)


if __name__ == "__main__":
    main()

