"""Build the PCVE source and physical counterfactuals for the fish-tank scene."""

from __future__ import annotations
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender
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
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1])]
import edit_vocab  # noqa: E402
import pcve_edit_dsl as dsl  # noqa: E402


RENDER_SCRIPT = HERE / "render_fish_tank_toy.py"
DEFAULT_BLENDER = blender()
DEFAULT_OUT_ROOT = ROOT / "renders" / "fish_tank_toy" / "suite_build"
SOURCE_CASE_ID = "fish_tank_toy_baseline"


@dataclass(frozen=True)
class EditCase:
    case_id: str
    dsl: str
    edit_summary: str


# Values selected from a sweep of the reduced-order car/rock trajectory.
# The gel case is intentionally handled by the renderer's stable
# approximation because Blender 4.3's high-viscosity liquid path climbs the
# thin aquarium walls before impact.
EDIT_CASES = (
    EditCase(
        "edit_light_toy_car",
        "SET toy_car.mass TIMES 0.4",
        "The car weighs 34 g instead of 85 g, well below the 61 g of water it displaces: it dips "
        "below the surface after entry, then bobs back up and floats instead of sinking "
        "to the glass bottom.",
    ),
    EditCase(
        "edit_dense_water_float_rock",
        "SET water.density TIMES 3",
        "The liquid is three times denser than water (2994 kg/m³), above both the car and the "
        "275 g moss rock's mean density: the car floats and the rock rises from the glass floor.",
    ),
    EditCase(
        "edit_gel_water",
        "SET water.viscosity TIMES 500000",
        "The liquid behaves like a translucent gel (kinematic viscosity 0.5 m²/s): the car makes "
        "only a shallow, slowly increasing indentation and does not sink to the bottom.",
    ),
    EditCase(
        "edit_dense_water_at_2s",
        "SET water.density TIMES 3 AT FRAME 49",
        "The car trajectory in frames 1–48 matches the source exactly. At exactly 2.0 s the liquid density becomes 2994 kg/m³; "
        "the car and moss rock leave the glass floor and rise back to the surface.",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the PCVE fish-tank toy suite.")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--resolution", nargs=2, type=int, default=(1280, 720))
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--domain-resolution", type=int, default=160)
    parser.add_argument("--threads", type=int, default=64, help="Blender/OpenMP threads per case")
    parser.add_argument("--gpus", nargs="*", default=None,
                        help="GPU indices to spread cases over; defaults to CUDA_VISIBLE_DEVICES")
    parser.add_argument("--parallel", type=int, default=1, help="cases run at the same time")
    parser.add_argument("--source-video", type=Path, default=None,
                        help="reuse an accepted source render dir instead of re-rendering the baseline")
    parser.add_argument("--keep-intermediates", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cases", nargs="*", help="Edit case ids; the source is always included.")
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def edit_info(case: EditCase) -> dict[str, Any]:
    parsed = dsl.parse(case.dsl, edit_vocab.VOCAB)
    if isinstance(parsed, dsl.DeleteEdit):
        physical_diff = {f"presence ({parsed.object_id})": {"from": True, "to": False}}
    else:
        physical_diff = {
            f"{parsed.property_name} ({parsed.object_id})": {
                "from": dsl.baseline_value_for(parsed, edit_vocab.VOCAB),
                "to": parsed.to_value,
            }
        }
    return {
        "edit_dsl": case.dsl,
        "edit_summary": case.edit_summary,
        "applies_from_frame": dsl.starts_at_frame(parsed),
        "prompts": dsl.make_prompts(parsed, edit_vocab.VOCAB),
        "physics_diff": {**physical_diff, "timing": dsl.timing_diff(parsed, edit_vocab.VOCAB)},
        "physics_override": dsl.to_scenario_override(parsed, edit_vocab.VOCAB),
    }


def command(args: argparse.Namespace, case_dir: Path, overrides: Path | None) -> list[str]:
    cmd = [
        str(args.blender.expanduser()), "-b", "--factory-startup", "--python-exit-code", "1",
        "-t", str(args.threads), "--python", str(RENDER_SCRIPT), "--",
        "--out-dir", str(case_dir),
        "--resolution", *map(str, args.resolution),
        "--samples", str(args.samples),
        "--domain-resolution", str(args.domain_resolution),
    ]
    if overrides:
        cmd += ["--scenario-overrides-json", str(overrides)]
    if args.keep_intermediates:
        cmd.append("--keep-intermediates")
    return cmd


def run_case(args: argparse.Namespace, case_dir: Path, overrides: Path | None, gpu: str | None) -> tuple[str, float]:
    case_dir.mkdir(parents=True, exist_ok=True)
    cmd = command(args, case_dir, overrides)
    if args.dry_run:
        print(f"[gpu {gpu}]", " ".join(cmd))
        return "dry_run", 0.0
    if args.skip_existing and (case_dir / "video.mp4").is_file():
        return "skipped_existing", 0.0
    # The renderer refuses a non-empty output dir; keep only our own inputs.
    for stale in case_dir.iterdir():
        if stale.name not in {"scenario_overrides.json", "prompts.json"}:
            raise FileExistsError(f"{case_dir} already has {stale.name}; remove it or pass --skip-existing")
    env = dict(os.environ, OMP_NUM_THREADS=str(args.threads))
    if gpu is not None:
        env["CUDA_VISIBLE_DEVICES"] = gpu
    started = time.perf_counter()
    log_path = case_dir.parent / f"{case_dir.name}.blender.log"
    with log_path.open("w", encoding="utf-8") as stream:
        result = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, env=env)
    elapsed = time.perf_counter() - started
    if result.returncode:
        tail = "\n".join(log_path.read_text(errors="replace").splitlines()[-50:])
        raise RuntimeError(f"Blender failed for {case_dir.name}:\n{tail}")
    return "completed", elapsed


def outputs(case_dir: Path) -> dict[str, str]:
    names = ("video.mp4", "ground_truth_transforms.json", "scenario_metadata.json")
    return {
        name.removesuffix(".json").removesuffix(".mp4"): str((case_dir / name).resolve())
        for name in names
        if (case_dir / name).exists()
    }


def link_source(src: Path, case_dir: Path) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    for name in ("video.mp4", "ground_truth_transforms.json", "scenario_metadata.json"):
        target = case_dir / name
        if not target.exists():
            target.symlink_to((src / name).resolve())


def main() -> None:
    args = parse_args()
    args.out_root = args.out_root.expanduser().resolve()
    selected = set(args.cases or [case.case_id for case in EDIT_CASES])
    unknown = selected - {case.case_id for case in EDIT_CASES}
    if unknown:
        raise SystemExit(f"Unknown case id(s): {sorted(unknown)}")
    gpus = args.gpus or (os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if os.environ.get(
        "CUDA_VISIBLE_DEVICES") else [None])

    manifest: dict[str, Any] = {
        "schema_version": 3,
        "suite_name": "pcve_fish_tank_toy_suite",
        "interaction_category": "rigid_fluid",
        "description": "A die-cast toy car falls into a water-only aquarium, splashes, sinks and settles.",
        "coupling": "prescribed rigid trajectory drives Mantaflow; no native two-way feedback",
        "baseline_physics": edit_vocab.BASELINE_PHYSICS,
        "total_frames": edit_vocab.VOCAB.total_frames,
        "resolution": list(args.resolution),
        "fps": 24,
        "duration_sec": 4.0,
        "fluid_domain_resolution": args.domain_resolution,
        "source": None,
        "edits": [],
    }
    manifest_path = args.out_root / "suite_manifest.json"
    if not args.dry_run:
        write_json(manifest_path, manifest)

    source_dir = args.out_root / "cases" / SOURCE_CASE_ID
    reuse_source = bool(args.source_video) and not args.dry_run
    if reuse_source:
        link_source(args.source_video.expanduser().resolve(), source_dir)
    manifest["source"] = {
        "case_id": SOURCE_CASE_ID,
        "kind": "source",
        "interaction_category": "rigid_fluid",
        "description": {
            "vague": {
                "en": "A toy car falls into a fish tank full of water, splashes, sinks and settles on the bottom.",
                "zh": "一辆玩具车掉进装满水的鱼缸，溅起水花后沉到缸底。",
            },
            "quantitative": {
                "en": "A 90 mm, 85 g die-cast toy car is dropped from 22 cm above the water into a 27 cm deep "
                      "aquarium, enters at 2.0 m/s and comes to rest on the glass bottom about one second later.",
                "zh": "一辆长 90 mm、重 85 g 的合金玩具车从水面上方 22 cm 处落入 27 cm 深的鱼缸，"
                      "以 2.0 m/s 入水，约一秒后停在玻璃缸底。",
            },
        },
        "status": "reused_accepted_render" if reuse_source else "pending",
        "outputs": outputs(source_dir),
    }
    if not args.dry_run:
        write_json(manifest_path, manifest)

    # The source renders alongside the edits instead of before them.
    jobs = [] if reuse_source else [(None, source_dir, None, None)]
    for case in EDIT_CASES:
        if case.case_id not in selected:
            continue
        case_dir = args.out_root / "cases" / case.case_id
        info = edit_info(case)
        override_path = case_dir / "scenario_overrides.json"
        record = {key: info[key] for key in ("edit_dsl", "edit_summary", "applies_from_frame",
                                             "physics_diff", "prompts")}
        if args.dry_run:
            print(case.case_id, json.dumps({"override": info["physics_override"], **record}, ensure_ascii=False))
        else:
            write_json(override_path, {"physics": info["physics_override"]})
            write_json(case_dir / "prompts.json", {
                "schema_version": 2, "case_id": case.case_id, "source_case_id": SOURCE_CASE_ID, **record,
            })
        jobs.append((case, case_dir, override_path, record))

    def work(index_job):
        index, (case, case_dir, override_path, record) = index_job
        gpu = gpus[index % len(gpus)]
        status, elapsed = run_case(args, case_dir, override_path, gpu)
        return case, case_dir, record, status, elapsed

    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        for case, case_dir, record, status, elapsed in pool.map(work, enumerate(jobs)):
            if case is None:
                manifest["source"].update(status=status, elapsed_sec=round(elapsed, 3),
                                          outputs=outputs(case_dir))
                if not args.dry_run:
                    write_json(manifest_path, manifest)
                continue
            manifest["edits"].append({
                "case_id": case.case_id, "kind": "edit", "source_case_id": SOURCE_CASE_ID, **record,
                "status": status, "elapsed_sec": round(elapsed, 3), "outputs": outputs(case_dir),
            })
            if not args.dry_run:
                write_json(manifest_path, manifest)
    print(manifest_path)


if __name__ == "__main__":
    main()
