"""Build the PhyCoVE toy boat glide source/counterfactual suite.

The source is not simulated again: the published source video (checked against the sha256 in
scene_manifest.json) and the accepted source run (--source-run; its report is copied, its particles stay there) are
adopted.
Each edit runs the whole chain (pipeline_toy_boat_pool_glide.sh) with its DSL's overrides: settle the
water around the held boat, push and release it, check it never reaches the wall, mesh the surfaces,
render camera kneeling_rim and encode. An edit that takes effect part-way ships its schedule to the simulation as
--timed-edits-json and continues the accepted source run's own state at that frame (--resume-from/--resume-frame).

With --reuse-sweep, an edit whose simulation already ran in sweep_edits.sh is not simulated again: its
settle/ and run/ are hard-linked into the case's work directory (the sweep copy is left untouched) after
checking that the run's physics is exactly the case's.

A full build takes a few hours.
"""

from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
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
sys.path[:0] = [str(HERE), str(ROOT / "scripts")]
import edit_vocab  # noqa: E402
import pcve_edit_dsl as dsl  # noqa: E402
import physics_toy_boat_pool_glide as physics  # noqa: E402

PIPELINE = HERE / "tools/pipeline_toy_boat_pool_glide.sh"
SCENE_MANIFEST = HERE / "scene_manifest.json"
SUITE_NAME = "pcve_toy_boat_pool_glide_suite"
SOURCE_VIDEO = ROOT / "renders/pcve_suites" / SUITE_NAME / "cases/source/video.mp4"
SOURCE_CASE_ID = "toy_boat_pool_glide_baseline"
RESOLUTION = (1280, 720)
SIMULATION_FLAGS = {"boat_mass": "--boat-mass", "boat_initial_speed": "--boat-speed",
                    "fluid_drag_rate": "--fluid-drag-rate", "liquid_density": "--water-density", "liquid_kinematic_viscosity": "--water-viscosity",
                    "boat_presence": "--boat-presence", "water_presence": "--water-presence"}
SOURCE_DESCRIPTION = {
    "vague": {
        "en": "A toy tugboat is pushed across a round inflatable kiddie pool on a garden lawn and glides on, "
              "trailing a bow wave and wake, until it almost stops.",
        "zh": "花园草坪上的圆形充气儿童泳池里，一只玩具拖船被推出后向前滑行，船头推起浪、身后拖出尾迹，直到几乎停下。",
    },
    "quantitative": {
        "en": "A 20 cm, 0.72 kg toy tugboat floating about 3.5 cm deep is released at 0.9 m/s in a 1.8 m "
              "three-ring kiddie pool filled 18 cm deep, and glides about 0.84 m without reaching the far wall.",
        "zh": "一只长 20 cm、质量约 0.72 kg、吃水约 3.5 cm 的玩具拖船，在直径 1.8 m、水深 18 cm 的三圈充气儿童池里"
              "以 0.9 m/s 松手，向前滑行约 0.84 m，没有碰到对面池壁。",
    },
}


@dataclass(frozen=True)
class EditCase:
    case_id: str
    dsl: str
    edit_summary: str


# Source at release: 0.88 m/s, about 38 mm deep;
# glides 0.84 m and is still drifting at frame 96, 0.18 m from the wall at closest.
EDIT_CASES: tuple[EditCase, ...] = (
    EditCase("edit_heavy_boat", "SET toy_tug.mass TIMES 3",
             "Boat mass increases to 2.153 kg; after the supporting push ends it sinks to the pool floor."),
    EditCase("edit_slow_push", "SET toy_tug.initial_velocity TIMES 0.5",
             "A half-speed release produces a weaker bow wave and a shorter glide."),
    EditCase("edit_fast_push", "SET toy_tug.initial_velocity TIMES 1.5",
             "A faster release produces a larger bow wave and the boat reaches the far pool wall."),
    EditCase("edit_light_water", "SET water.density TIMES 0.25",
             "Water density decreases to 249.5 kg/m^3; the unchanged boat loses buoyant support and sinks."),
    EditCase("edit_viscous_water", "SET water.viscosity TIMES 3500",
             "Kinematic viscosity is 0.003514 m^2/s. Additional stationary-medium resistance gamma=6 s^-1 suppresses traveling surface waves while passive planar boat drag preserves a short free glide without visible recoil; clear-water appearance is unchanged. This case is not a property-only full two-way CFD counterfactual."),
    EditCase("edit_remove_boat", "DELETE toy_tug",
             "No boat is present from the first frame; the pool stays still."),
    EditCase("edit_heavy_boat_mid_glide", "SET toy_tug.mass TIMES 3 AT FRAME 24",
             "The run continues the source run's own frame-24 state, so frames 1-24 are the source's; at frame 24 (0.958 s) the boat's mass and inertia triple without a pose or velocity jump, then it sinks."),
)
SWEEP_RUNS = {case.case_id:case.case_id for case in EDIT_CASES}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root", type=Path, default=ROOT / "renders" / "toy_boat_pool_glide" / "suite_build")
    p.add_argument("--source-run", type=Path, default=ROOT / "renders/toy_boat_pool_glide/source/run",
                   help="The accepted source run (particles and simulation_report.json) that is adopted and that timed "
                        "edits continue.")
    p.add_argument("--keep-intermediates", action="store_true",
                   help="Keep every case's particles, surfaces, frames and logs.")
    p.add_argument("--skip-existing", action="store_true", help="Reuse cases whose video already verifies.")
    p.add_argument("--parallel", type=int, default=2, help="Edit cases built concurrently.")
    p.add_argument("--dry-run", action="store_true", help="Print the commands only.")
    p.add_argument("--reuse-sweep", type=Path, help="sweep_edits.sh output root whose runs the edits reuse")
    p.add_argument("--cases", nargs="*", help="Edit case ids to build; the source is always adopted.")
    return p.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def edit_info(case: EditCase) -> dict[str, Any]:
    parsed = dsl.parse(case.dsl, edit_vocab.VOCAB)
    if isinstance(parsed, dsl.DeleteEdit):
        diff = {f"presence ({parsed.object_id})": {"from": True, "to": False}}
    else:
        diff = {f"{parsed.property_name} ({parsed.object_id})": {
            "from": dsl.baseline_value_for(parsed, edit_vocab.VOCAB), "to": parsed.to_value}}
    diff["timing"] = dsl.timing_diff(parsed, edit_vocab.VOCAB)
    info = {
        "edit_dsl": case.dsl,
        "edit_summary": case.edit_summary,
        "applies_from_frame": dsl.starts_at_frame(parsed),
        "prompts": dsl.make_prompts(parsed, edit_vocab.VOCAB),
        "physics_diff": diff,
        "physics_override": dsl.to_scenario_override(parsed, edit_vocab.VOCAB),
    }

    if case.case_id == "edit_viscous_water":
        # This compound edit extends the viscosity DSL with a medium model. The prompts state only the DSL's viscosity
        # change; the extra physics is recorded in the machine-readable metadata.
        info["edit_dsl_scope"] = "viscosity component only; additional medium resistance is recorded separately"
        info["physics_override"]["fluid_drag_rate"] = 6.0
        info["physics_diff"]["stationary_medium_drag_rate_s_inv (water)"] = {"from": 0.0, "to": 6.0}
        info["simulation_quality_override"] = {"hull_viscous_shear": True, "steps_per_frame": 88, "substeps": 4,
            "single_force_integration": True, "record_coupling_forces": True, "initial_draft_ratio": 1.0, "pool_no_slip": True}
        info["simulation_model_override"] = {
            "classification": "reduced_order_hybrid_with_stationary_medium",
            "additional_medium_drag_rate_s_inv": 6.0, "medium_integration": "exact exponential decay per substep, operator split", "hull_pressure_mode": "hydrostatic",
            "quasistatic_planar_drag": True, "property_only_counterfactual": False,
            "horizontal_pair_momentum_conserved": False,
            "description": "Free rigid body with equivalent-displacement sphere drag in stationary far-field fluid; vertical SPH feedback, body-driven fluid and additional dissipative stationary-medium resistance. Not a resolved horizontal two-way CFD solve or calibrated mud rheology."}
    return info


def simulation_flags(override: dict[str, Any], case_dir: Path, source_run: Path) -> list[str]:
    flags = []
    for key, value in override.items():
        if key == dsl.TIMED_EDITS_KEY:
            schedule = case_dir / "timed_edits.json"
            write_json(schedule, value)
            # The edit continues the accepted source run's own state at its first frame, so every earlier frame is
            # the source's (not a re-solve of it).
            flags += ["--timed-edits-json", str(schedule), "--resume-from", str(source_run),
                      "--resume-frame", str(min(int(entry["frame"]) for entry in value))]
        elif isinstance(value, list):
            flags += [SIMULATION_FLAGS[key], str(int(value[0]))]
        else:
            flags += [SIMULATION_FLAGS[key], repr(float(value))]
    if override.get("liquid_kinematic_viscosity", 0) >= 0.003:
        flags += ["--hull-viscous-shear", "--single-force-integration", "--record-coupling-forces",
                  "--hull-pressure-mode", "hydrostatic", "--initial-draft-ratio", "1.0",
                  "--quasistatic-planar-drag", "--steps-per-frame", "88", "--pool-no-slip"]
    return flags


def run(args: argparse.Namespace, cmd: list[str], log: Path) -> None:
    if args.dry_run:
        print(" ".join(cmd))
        return
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT)
    if result.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-50:])
        raise RuntimeError(f"{log} reports a failure:\n{tail}")


def verify_video(video: Path) -> None:
    if not video.is_file():
        raise FileNotFoundError(video)
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames:format=duration",
        "-of", "json", str(video),
    ], text=True))
    stream = probe["streams"][0]
    assert (stream["width"], stream["height"]) == RESOLUTION, stream
    assert stream["avg_frame_rate"] == f"{physics.FPS}/1", stream
    assert int(stream["nb_read_frames"]) == physics.FRAMES, stream
    assert abs(float(probe["format"]["duration"]) - physics.FRAMES / physics.FPS) < 0.01, probe
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)


def check_baseline_mass() -> None:
    """physics.BOAT_MASS must be the mass the simulation derives for its default draft."""
    import simulate_toy_boat_pool_glide as simulation
    sys.argv = ["simulate", "run", "--out", "/dev/null"]
    mass, _ = simulation.boat_mass_and_draft(simulation.load_hull(), simulation.parse_args())
    if abs(mass - physics.BOAT_MASS) > 1e-9:
        raise SystemExit(f"physics.BOAT_MASS {physics.BOAT_MASS} != simulation default mass {mass}")


def adopt_source(args: argparse.Namespace, case_dir: Path) -> dict[str, Any]:
    """The accepted source, as rendered: the published source video (hash-checked against scene_manifest.json) and
    the accepted run's simulation report; its particles stay in the run directory."""
    suite = json.loads(SCENE_MANIFEST.read_text())["canonical_suites"][SUITE_NAME]
    expected = suite["case_video_sha256"][SOURCE_CASE_ID]
    run_dir = args.source_run.expanduser().resolve()
    if args.dry_run:
        print(f"adopt {SOURCE_VIDEO} -> {case_dir / 'video.mp4'}; source run {run_dir}")
        return {"source_run": str(run_dir)}
    if sha256(SOURCE_VIDEO) != expected:
        raise SystemExit(f"{SOURCE_VIDEO} does not match the accepted source")
    case_dir.mkdir(parents=True, exist_ok=True)
    if not (case_dir / "video.mp4").is_file() or sha256(case_dir / "video.mp4") != expected:
        shutil.copy2(SOURCE_VIDEO, case_dir / "video.mp4")
    (case_dir / "simulation").mkdir(exist_ok=True)
    shutil.copy2(run_dir / "simulation_report.json", case_dir / "simulation" / "simulation_report.json")
    verify_video(case_dir / "video.mp4")
    return {"source_run": str(run_dir), "particles": str(run_dir / "particles"), "video_sha256": expected}


def check_run_matches(run_dir: Path, override: dict[str, Any]) -> None:
    """A reused run must be exactly the case: every edited parameter at its value, all others at baseline."""
    expected = dict(edit_vocab.BASELINE_PHYSICS)
    timed = override.get(dsl.TIMED_EDITS_KEY, [])
    expected.update({k: v for k, v in override.items() if k != dsl.TIMED_EDITS_KEY})
    report = json.loads((run_dir / "simulation_report.json").read_text())
    physics_report = report["physics"]
    if expected["liquid_kinematic_viscosity"] >= 0.003 and not report.get("hull_viscous_shear", False):
        raise SystemExit(f"{run_dir}: current viscous preset requires --hull-viscous-shear")
    if expected["liquid_kinematic_viscosity"] >= 0.003:
        required = {"single_force_integration": True, "quasistatic_planar_drag": True,
                    "hull_pressure_mode": "hydrostatic", "steps_per_frame": 88, "substeps_per_step": 4, "pool_no_slip": True}
        if any(report.get("numerics", {}).get(k) != v for k, v in required.items()):
            raise SystemExit(f"{run_dir}: incompatible with the current reduced-order viscous preset")
        if physics_report.get("additional_medium_drag_rate_s_inv", 0.0) != 6.0:
            raise SystemExit(f"{run_dir}: current swamp-motion preset requires medium resistance gamma=6 s^-1")
        if not math.isclose(report["placed_rest_draft_m"], report["draft_m"], abs_tol=1e-8):
            raise SystemExit(f"{run_dir}: expected the corrected equilibrium initialization")
    actual = {
        "fluid_drag_rate": physics_report.get("additional_medium_drag_rate_s_inv", 0.0),
        "boat_mass": report["boat_mass_kg"],
        "boat_initial_speed": float(sum(c * c for c in physics_report["boat_initial_velocity_m_s"]) ** 0.5),
        "liquid_density": physics_report["water_density_kg_m3"],
        "liquid_kinematic_viscosity": physics_report["water_kinematic_viscosity_m2_s"],
        "boat_presence": physics_report["boat_presence"],
        "water_presence": physics_report["water_presence"],
    }
    for key, value in expected.items():
        same = actual[key] == value if isinstance(value, list) else abs(actual[key] - value) <= 1e-6 * abs(value)
        if not same:
            raise SystemExit(f"{run_dir}: {key} is {actual[key]}, the case needs {value}")
    actual_timed = physics_report.get("timed_edits", [])
    def same_value(a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            return a.keys() == b.keys() and all(same_value(a[k], b[k]) for k in a)
        if isinstance(a, list) and isinstance(b, list):
            return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-10)
        return a == b
    if not same_value(actual_timed, timed):
        raise SystemExit(f"{run_dir}: timed edits {actual_timed} != {timed}")


def place_sweep_run(args: argparse.Namespace, case: EditCase, work: Path, override: dict[str, Any]) -> None:
    source = args.reuse_sweep / SWEEP_RUNS[case.case_id]
    check_run_matches(source / "run", override)
    if args.dry_run:
        print(f"reuse {source} -> {work}")
        return
    work.mkdir(parents=True)
    for part in ("settle", "run"):
        subprocess.run(["cp", "-al", str(source / part), str(work / part)], check=True)


def run_case(args: argparse.Namespace, case: EditCase, case_dir: Path, override: dict[str, Any]) -> tuple[str, float]:
    if args.skip_existing and (case_dir / "video.mp4").is_file() and not args.dry_run:
        if case.case_id == "edit_viscous_water":
            check_run_matches(case_dir / "simulation", override)
        verify_video(case_dir / "video.mp4")
        return "skipped_existing", 0.0
    start = time.perf_counter()
    work = case_dir / "work"
    if work.exists() and not args.dry_run:
        shutil.rmtree(work)
    if not args.dry_run:
        case_dir.mkdir(parents=True, exist_ok=True)
    if args.reuse_sweep:
        place_sweep_run(args, case, work, override)
    elif case.case_id == "edit_viscous_water":
        run(args, ["bash", str(HERE / "tools/run_viscous_glide.sh"), str(work)], case_dir / "simulation.log")
    flags = simulation_flags(override, case_dir, args.source_run.expanduser().resolve())
    run(args, ["bash", str(PIPELINE), str(work), *flags], case_dir / "pipeline.log")
    if args.dry_run:
        return "dry_run", 0.0
    verify_video(work / "video.mp4")
    shutil.move(str(work / "video.mp4"), case_dir / "video.mp4")
    (case_dir / "simulation").mkdir(exist_ok=True)
    shutil.copy2(work / "run" / "simulation_report.json", case_dir / "simulation" / "simulation_report.json")
    if not args.keep_intermediates:
        shutil.rmtree(work)
        (case_dir / "pipeline.log").unlink(missing_ok=True)
    return "completed", time.perf_counter() - start


def outputs(case_dir: Path) -> dict[str, str]:
    names = ("video.mp4", "prompts.json", "scenario_overrides.json")
    return {name.rsplit(".", 1)[0]: str((case_dir / name).resolve()) for name in names if (case_dir / name).exists()}


def main() -> None:
    args = parse_args()
    args.out_root = args.out_root.expanduser().resolve()
    selected = set(args.cases or [case.case_id for case in EDIT_CASES])
    unknown = selected - {case.case_id for case in EDIT_CASES}
    if unknown:
        raise SystemExit(f"Unknown case id(s): {sorted(unknown)}")
    check_baseline_mass()
    manifest: dict[str, Any] = {
        "schema_version": 3,
        "suite_name": SUITE_NAME,
        "interaction_category": "rigid_fluid",
        "description": "A floating toy tugboat is pushed across a kiddie pool and glides to rest; counterfactuals "
                       "edit the boat's mass or speed, the water's density or viscosity, or remove the boat.",
        "baseline_physics": edit_vocab.BASELINE_PHYSICS,
        "total_frames": physics.FRAMES,
        "resolution": list(RESOLUTION),
        "fps": physics.FPS,
        "duration_sec": physics.FRAMES / physics.FPS,
        "simulation": {
            "engine": "Genesis 1.4.3 DFSPH water with the rigid boat coupled two-way (native rigid_sph)",
            "case_exceptions": {"edit_viscous_water": "Reduced-order hybrid with passive planar boat drag and additional fluid-medium resistance gamma=6 s^-1; not a property-only two-way CFD comparison. See case simulation_model_override."},
            "particle_size_m": 0.005,
            "pool": "round three-ring kiddie pool, 1.80 m outer, water held by a 0.723 m cylinder, floor z 0.150, "
                    "still water z 0.334",
            "release": "hidden 8-frame push ramps the boat's horizontal velocity to its initial speed; released at frame 1",
        },
        "render": {"engine": "Cycles", "samples": 64, "camera": "kneeling_rim", "view_transform": "AgX Base Contrast"},
        "source": None,
        "edits": [],
    }
    manifest_path = args.out_root / "suite_manifest.json"

    source_dir = args.out_root / "cases" / SOURCE_CASE_ID
    adopted = adopt_source(args, source_dir)
    if not args.dry_run:
        write_json(source_dir / "prompts.json", {"schema_version": 1, "case_id": SOURCE_CASE_ID, "kind": "source",
                                                 "prompts": SOURCE_DESCRIPTION})
    manifest["source"] = {"case_id": SOURCE_CASE_ID, "kind": "source", "interaction_category": "rigid_fluid",
                          "description": SOURCE_DESCRIPTION, "status": "adopted_accepted_base", **adopted,
                          "outputs": outputs(source_dir)}
    if not args.dry_run:
        write_json(manifest_path, manifest)

    jobs = [(case, args.out_root / "cases" / case.case_id, edit_info(case))
            for case in EDIT_CASES if case.case_id in selected]
    for case, case_dir, info in jobs:
        if args.dry_run:
            print(case.case_id, json.dumps(info["physics_override"]), "|", info["prompts"]["quantitative"]["zh"])
            continue
        write_json(case_dir / "prompts.json", {
            "schema_version": 2, "case_id": case.case_id, "source_case_id": SOURCE_CASE_ID,
            **info,
        })
        write_json(case_dir / "scenario_overrides.json", {"physics": info["physics_override"],
            **({"simulation_quality": info["simulation_quality_override"]} if "simulation_quality_override" in info else {}),
            **({"simulation_model": info["simulation_model_override"]} if "simulation_model_override" in info else {})})

    def work(job):
        case, case_dir, info = job
        return run_case(args, case, case_dir, info["physics_override"])

    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        for (case, case_dir, info), (status, elapsed) in zip(jobs, pool.map(work, jobs)):
            manifest["edits"].append({
                "case_id": case.case_id, "kind": "edit", "source_case_id": SOURCE_CASE_ID,
                **info,
                "status": status, "elapsed_sec": round(elapsed, 3), "outputs": outputs(case_dir),
            })
            if not args.dry_run:
                write_json(manifest_path, manifest)
    print(manifest_path)


if __name__ == "__main__":
    main()
