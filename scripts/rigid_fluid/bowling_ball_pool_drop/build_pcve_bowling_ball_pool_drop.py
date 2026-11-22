"""Build the PhyCoVE bowling-ball pool-drop source/counterfactual suite.

The pool settles once and every case starts from that water. Each case evolves the water with the optional ball using
Genesis DFSPH (simulate_bowling_ball_pool_drop.py), then runs the render chain
(pipeline_bowling_ball_pool_drop.sh): splash, sun visibility, caustics, Cycles render and video.
GPU steps wait for an idle GPU (run_on_idle_gpu.sh).
"""

from __future__ import annotations
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
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1])]
import edit_vocab  # noqa: E402
import pcve_edit_dsl as dsl  # noqa: E402
import simulate_bowling_ball_pool_drop as simulation  # noqa: E402

PYTHON = ROOT / ".venv-genesis-mpm-sph/bin/python"
IDLE_GPU = HERE / "tools/run_on_idle_gpu.sh"
PIPELINE = HERE / "tools/pipeline_bowling_ball_pool_drop.sh"
SOURCE_CASE_ID = "bowling_ball_pool_drop_baseline"
RESOLUTION = (1280, 720)
SIMULATION_FLAGS = {"ball_mass": "--ball-mass", "liquid_density": "--liquid-density",
                    "liquid_kinematic_viscosity": "--liquid-nu"}
SOURCE_DESCRIPTION = {
    "vague": {
        "en": "A rigid bowling ball falls into a pool, creates an entry splash, and sinks through the liquid.",
        "zh": "一个刚性保龄球落入水池，激起水花并向液体深处下沉。",
    },
    "quantitative": {
        "en": "A 15 cm, 2.069 kg miniature bowling ball enters the frame already falling, drops into a full-size sunken pool and creates an entry splash.",
        "zh": "一个直径 15 cm、质量约 2.069 kg 的迷你保龄球进入画面时已在下落，随后落入全尺寸下沉式泳池并激起水花。",
    },
}


@dataclass(frozen=True)
class EditCase:
    case_id: str
    dsl: str
    edit_summary: str


EDIT_CASES = (
    EditCase(
        "edit_light_ball",
        "SET ball.mass TIMES 0.25626870931880164",
        "The ball's mass falls to about 0.530 kg (mean density about 300 kg/m^3): it enters with far less "
        "momentum, rises back and floats with about 30% of its volume submerged.",
    ),
    EditCase(
        "edit_high_density_liquid",
        "SET water.density TIMES 2",
        "The liquid density doubles to 2000 kg/m^3, above the ball's 1170.65 kg/m^3: the ball plunges in, rises "
        "back and floats with about 59% of its volume submerged.",
    ),
    EditCase(
        "edit_viscous_liquid",
        "SET water.viscosity TIMES 100000",
        "The liquid's kinematic viscosity rises to 0.1 m^2/s (Reynolds number about 9 at entry): the splash, "
        "cavity and waves are strongly damped and the ball creeps down at a few centimetres per second.",
    ),
    EditCase(
        "edit_delete_ball", "DELETE ball",
        "Remove the bowling ball from the beginning; the same settled pool evolves without its impact.",
    ),
    EditCase(
        "edit_light_ball_after_2s", "SET ball.mass TO 0.5301437603 AT FRAME 49",
        "At 2.00 s, reduce the ball's mass from 2.068702658637 kg to 0.5301437603 kg without an imposed "
        "impulse or size change; the ball rises from the floor and bobs at the surface. The continuation "
        "also retains the previously omitted floor-layer pressure reactions as a declared numerical repair.",
    ),
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root", type=Path, default=ROOT / "renders" / "bowling_ball_pool_drop" / "suite_build")
    p.add_argument("--dx", type=float, default=0.02, help="SPH particle size (m).")
    p.add_argument("--keep-intermediates", action="store_true",
                   help="Keep surfaces, caustics, frames and logs of every case.")
    p.add_argument("--skip-existing", action="store_true", help="Reuse cases whose video already verifies.")
    p.add_argument("--parallel", type=int, default=1,
                   help="Edit cases built concurrently; each GPU step still waits for its own idle GPU.")
    p.add_argument("--dry-run", action="store_true", help="Print the commands only.")
    p.add_argument("--cases", nargs="*", help="Edit case ids to build; the source is always included.")
    p.add_argument("--gpu", type=int, help="Use this inspected GPU; otherwise wait for an empty GPU.")
    p.add_argument("--resume-source", action="store_true",
                   help="Timed mass cases continue from the accepted source state at the edit frame.")
    return p.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def edit_info(case: EditCase) -> dict[str, Any]:
    parsed = dsl.parse(case.dsl, edit_vocab.VOCAB)
    if isinstance(parsed, dsl.DeleteEdit):
        difference = {f"presence ({parsed.object_id})": {"from": True, "to": False}}
    else:
        difference = {f"{parsed.property_name} ({parsed.object_id})": {
            "from": dsl.baseline_value_for(parsed, edit_vocab.VOCAB), "to": parsed.to_value}}
    return {
        "edit_dsl": case.dsl,
        "edit_summary": case.edit_summary,
        "applies_from_frame": dsl.starts_at_frame(parsed),
        "applies_from_time_s": (dsl.starts_at_frame(parsed) - 1) / simulation.FPS,
        "simulation_quality_diff": ({"floor_pressure_reaction": {
            "from": "floor_band_omitted", "to": "all_fluid", "from_time_s": 2.0}}
            if case.case_id == "edit_light_ball_after_2s" else {}),
        "prompts": dsl.make_prompts(parsed, edit_vocab.VOCAB),
        "physics_diff": {**difference, "timing": dsl.timing_diff(parsed, edit_vocab.VOCAB)},
        "physics_override": dsl.to_scenario_override(parsed, edit_vocab.VOCAB),
    }


def run(args: argparse.Namespace, cmd: list[str], log: Path) -> None:
    if args.dry_run:
        print(" ".join(cmd))
        return
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        env = dict(os.environ)
        if args.gpu is not None:
            env["PCVE_GPU"] = str(args.gpu)
        result = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT, env=env)
    if result.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-50:])
        raise RuntimeError(f"{log} reports a failure:\n{tail}")


def settle(args: argparse.Namespace) -> Path:
    """The still pool every case starts from, settled once."""
    directory = args.out_root / "settle"
    state = directory / "water_state.npz"
    if not state.is_file():
        run(args, ["bash", str(IDLE_GPU), str(PYTHON), "-u", str(HERE / "simulate_bowling_ball_pool_drop.py"),
                   "settle", "--dx", str(args.dx), "--out", str(directory)], args.out_root / "logs" / "settle.log")
    return state


def verify_video(case_dir: Path) -> None:
    video = case_dir / "video.mp4"
    if not video.is_file():
        raise FileNotFoundError(video)
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames:format=duration",
        "-of", "json", str(video),
    ], text=True))
    stream = probe["streams"][0]
    assert (stream["width"], stream["height"]) == RESOLUTION, stream
    assert stream["avg_frame_rate"] == f"{simulation.FPS}/1", stream
    assert int(stream["nb_read_frames"]) == simulation.FRAMES, stream
    assert abs(float(probe["format"]["duration"]) - simulation.FRAMES / simulation.FPS) < 0.01, probe
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)


def retain_deliverables(case_dir: Path, keep_particles: bool) -> None:
    """Keep the video, prompts and simulation report (and the source's particles, so the frozen base can
    be re-rendered without re-simulating); drop surfaces, caustics, frames and logs."""
    simulation_dir = case_dir / "simulation"
    kept = {"simulation_report.json"} | ({"particles"} if keep_particles else set())
    for child in list(simulation_dir.iterdir()) if simulation_dir.is_dir() else ():
        if child.name in kept:
            continue
        if child.is_symlink():
            raise RuntimeError(f"Refusing to remove symlink from case output: {child}")
        shutil.rmtree(child) if child.is_dir() else child.unlink()


def run_case(args: argparse.Namespace, case_dir: Path, water_state: Path, overrides: dict[str, Any],
             is_source: bool) -> tuple[str, float]:
    if not args.dry_run:
        case_dir.mkdir(parents=True, exist_ok=True)
    if args.skip_existing and (case_dir / "video.mp4").is_file() and not args.dry_run:
        verify_video(case_dir)
        return "skipped_existing", 0.0
    start = time.perf_counter()
    simulation_dir = case_dir / "simulation"
    if simulation_dir.exists() and not args.dry_run:
        raise FileExistsError(f"Preserving existing simulation evidence: {simulation_dir}. Use a fresh directory.")
    flags = []
    for key, value in overrides.items():
        if key == "ball_present":
            if value != [0]:
                raise ValueError("Only whole-clip removal is supported")
            flags.append("--remove-ball")
        elif key == "timed_edits":
            schedule = case_dir / "timed_edits.json"
            if not args.dry_run:
                write_json(schedule, value)
            flags += ["--timed-edits-json", str(schedule)]
            flags.append("--conservative-floor-pressure")
            if args.resume_source:
                flags += ["--resume-source", str(args.out_root / "cases" / SOURCE_CASE_ID / "simulation")]
        else:
            flags += [SIMULATION_FLAGS[key], repr(float(value))]
    run(args, ["bash", str(IDLE_GPU), str(PYTHON), "-u", str(HERE / "simulate_bowling_ball_pool_drop.py"), "run",
               "--dx", str(args.dx), "--water-state", str(water_state), "--out", str(simulation_dir), *flags],
        case_dir / "simulate.log")
    run(args, ["bash", str(PIPELINE), str(simulation_dir), str(case_dir / "video.mp4")], case_dir / "pipeline.log")
    if args.dry_run:
        return "dry_run", 0.0
    verify_video(case_dir)
    if not args.keep_intermediates:
        retain_deliverables(case_dir, keep_particles=is_source)
        for log in ("simulate.log", "pipeline.log"):
            (case_dir / log).unlink(missing_ok=True)
    return "completed", time.perf_counter() - start


def outputs(case_dir: Path) -> dict[str, str]:
    names = ("video.mp4", "prompts.json")
    return {name.removesuffix(".json").removesuffix(".mp4"): str((case_dir / name).resolve())
            for name in names if (case_dir / name).exists()}


def main() -> None:
    args = parse_args()
    args.out_root = args.out_root.expanduser().resolve()
    selected = set(args.cases or [case.case_id for case in EDIT_CASES])
    unknown = selected - {case.case_id for case in EDIT_CASES}
    if unknown:
        raise SystemExit(f"Unknown case id(s): {sorted(unknown)}")
    if not args.dry_run and not args.skip_existing:
        existing = [args.out_root / "cases" / name for name in (SOURCE_CASE_ID, *sorted(selected))
                    if (args.out_root / "cases" / name / "simulation").exists()
                    or (args.out_root / "cases" / name / "video.mp4").exists()]
        if existing:
            raise SystemExit("Preserving existing cases; use --skip-existing or a fresh suite: "
                             + ", ".join(str(path) for path in existing))
    manifest: dict[str, Any] = {
        "schema_version": 3,
        "suite_name": "pcve_bowling_ball_pool_drop_suite",
        "interaction_category": "rigid_fluid",
        "description": "A rigid sphere enters a pool; edits remove the ball, change mass or liquid properties, including a mass change at 2 seconds.",
        "baseline_physics": edit_vocab.BASELINE_PHYSICS,
        "total_frames": simulation.FRAMES,
        "resolution": list(RESOLUTION),
        "fps": simulation.FPS,
        "duration_sec": simulation.FRAMES / simulation.FPS,
        "simulation": {
            "engine": "Genesis DFSPH water with a rigid ball coupled through pressure-boundary ghost particles",
            "particle_size_m": args.dx,
            "pool": "authored deck opening, parallelogram 3.03 x 2.17 m, floor z -1.25, still water z -0.25",
            "pool_corners_m": simulation.POOL.tolist(),
            "domain_top_m": simulation.DOMAIN_TOP,
        },
        "render": {"engine": "Cycles", "samples": 64, "exposure": -0.75, "sun_strength": 15.0},
        "source": None,
        "edits": [],
    }
    manifest_path = args.out_root / "suite_manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    for key, value in previous.items():
        if key not in manifest:
            manifest[key] = value
    manifest["simulation"] = {**previous.get("simulation", {}), **manifest["simulation"]}
    manifest["source"] = previous.get("source")
    manifest["edits"] = list(previous.get("edits", []))
    if not args.dry_run:
        write_json(manifest_path, manifest)
    water_state = settle(args)

    source_dir = args.out_root / "cases" / SOURCE_CASE_ID
    status, elapsed = run_case(args, source_dir, water_state, {}, is_source=True)
    if not args.dry_run:
        write_json(source_dir / "prompts.json", {"schema_version": 1, "case_id": SOURCE_CASE_ID, "kind": "source",
                                                 "prompts": SOURCE_DESCRIPTION})
    manifest["source"] = {"case_id": SOURCE_CASE_ID, "kind": "source", "interaction_category": "rigid_fluid",
                          "description": SOURCE_DESCRIPTION, "status": status, "elapsed_sec": round(elapsed, 3),
                          "outputs": outputs(source_dir)}
    if status == "skipped_existing" and previous.get("source"):
        manifest["source"] = previous["source"]   # the frozen base keeps its acceptance record
    if not args.dry_run:
        write_json(manifest_path, manifest)

    jobs = [(case, args.out_root / "cases" / case.case_id, edit_info(case))
            for case in EDIT_CASES if case.case_id in selected]
    for case, case_dir, info in jobs:
        if not args.dry_run:
            write_json(case_dir / "prompts.json", {
                "schema_version": 2, "case_id": case.case_id, "source_case_id": SOURCE_CASE_ID,
                **{key: info[key] for key in ("edit_dsl", "edit_summary", "applies_from_frame", "applies_from_time_s", "simulation_quality_diff", "physics_diff", "prompts")},
            })

    def work(job):
        _, case_dir, info = job
        return run_case(args, case_dir, water_state, info["physics_override"], is_source=False)

    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        for (case, case_dir, info), (status, elapsed) in zip(jobs, pool.map(work, jobs)):
            prior = next((entry for entry in manifest["edits"] if entry["case_id"] == case.case_id), None)
            entry = {
                "case_id": case.case_id, "kind": "edit", "source_case_id": SOURCE_CASE_ID,
                **{key: info[key] for key in ("edit_dsl", "edit_summary", "applies_from_frame", "applies_from_time_s", "simulation_quality_diff", "physics_diff", "prompts")},
                "status": status, "elapsed_sec": round(elapsed, 3), "outputs": outputs(case_dir),
            }
            manifest["edits"] = [old for old in manifest["edits"] if old["case_id"] != case.case_id]
            manifest["edits"].append(prior if status == "skipped_existing" and prior else entry)
            if not args.dry_run:
                write_json(manifest_path, manifest)
    print(manifest_path)


if __name__ == "__main__":
    main()
