"""Randomized batch workflow (tools/render_queue.py) for scenes backed by a scenario.json file."""

import argparse
import hashlib
import importlib
import json
import random
import subprocess
import time
from pathlib import Path

from pcve_scene_runtime import ROOT, add_build_arguments, append_render_options, render_prefix, case_outputs

import pcve_edit_dsl as dsl


SCRIPTS = {
    "home_basketball_door": ("render_home_basketball_door.py", "simulate_home_basketball_door.py"),
    "pot_lid_drop": ("render_pot_lid_drop.py", "simulate_pot_lid_drop.py"),
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def parser(scene):
    p = argparse.ArgumentParser(description=f"Build randomized samples for {scene}.")
    p.add_argument("--out-root", type=Path, default=ROOT / "renders" / f"batch_{scene}")
    p.add_argument("--resolution", nargs=2, type=int, default=[1280, 720])
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--duration-sec", type=float, default=4.0)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--engine", choices=("cycles",), default="cycles")
    p.add_argument("--mode", choices=("preview", "animation"), default="preview")
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose-render", action="store_true")
    p.add_argument("--simulate-only", action="store_true")
    p.add_argument("--count", type=int, default=4)
    p.add_argument("--start-index", type=int, default=0)
    p.add_argument("--seed-base", type=int, default=7200)
    return add_build_arguments(p)


def scene_directory(scene):
    candidates = (ROOT / "scripts" / "rigid_rigid" / scene, ROOT / "scripts" / scene)
    for directory in candidates:
        if directory.is_dir():
            return directory
    raise FileNotFoundError(f"No scene directory found for {scene}: {candidates}")


def command_for(scene, folder, args, seed, overrides):
    render, simulate = SCRIPTS[scene]
    directory = scene_directory(scene)
    if args.simulate_only:
        command = [str(args.physics_python), str(directory / simulate), "--out", str(folder / "physics_transforms.json")]
    else:
        command = render_prefix(args, directory / render)
        command += ["--out-dir", str(folder), "--mode", args.mode,
                    "--resolution", *map(str, args.resolution), "--samples", str(args.samples),
                    "--physics-python", str(args.physics_python), "--seed", str(seed)]
        append_render_options(command, args)
    command += ["--fps", str(args.fps), "--duration-sec", str(args.duration_sec)]
    if overrides is not None:
        command += ["--scenario-overrides-json", str(overrides)]
    return command


def run_case(scene, folder, args, seed, override):
    folder = folder.resolve()
    overrides = folder / "scenario_overrides.json" if override else None
    command = command_for(scene, folder, args, seed, overrides)
    if args.dry_run:
        print(subprocess.list2cmdline(command))
        return {"status": "dry_run"}
    payload = dict(override=override, seed=seed, fps=args.fps,
                   duration=args.duration_sec, mode=args.mode, samples=args.samples,
                   resolution=args.resolution, engine=args.engine, device=args.device,
                   preview_frame=args.preview_frame, simulation_only=args.simulate_only)
    fp = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    status_path = folder / "run_status.json"
    required = ["physics_transforms.json"] if args.simulate_only else [
        "ground_truth_transforms.json", "scenario_metadata.json",
        "video.mp4" if args.mode == "animation" else "preview.png"]
    if args.skip_existing and status_path.is_file():
        previous = json.loads(status_path.read_text(encoding="utf-8"))
        if previous.get("fingerprint") == fp and all((folder / p).is_file() for p in required):
            return dict(previous, status="skipped_existing")
    if overrides is not None:
        write_json(overrides, override)
    folder.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    if args.verbose_render:
        subprocess.run(command, check=True)
    else:
        with (folder / "render.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    for name in required:
        if not (folder / name).is_file():
            raise FileNotFoundError(folder / name)
    status = dict(status="completed", valid=True, fingerprint=fp, simulation_only=args.simulate_only,
                  render_mode=args.mode, elapsed_sec=round(time.perf_counter() - start, 3),
                  outputs=case_outputs(folder))
    write_json(status_path, status)
    return status


def batch_main(scene, argv=None):
    args = parser(scene).parse_args(argv)
    args.out_root = args.out_root.resolve()
    if args.count < 1 or args.start_index < 0:
        raise ValueError("Count must be positive and start index nonnegative")
    directory = scene_directory(scene)
    import sys
    for entry in (directory, directory.parents[1], directory / "physics", directory / "appearance"):
        if entry.is_dir() and str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    vocab = importlib.import_module("edit_vocab").VOCAB
    manifest = dict(schema_version=1, scene=scene, mode=args.mode, count=args.count,
                    start_index=args.start_index, seed_base=args.seed_base, samples=[])
    for offset in range(args.count):
        index = args.start_index + offset
        seed = args.seed_base + index
        rng = random.Random(seed)
        params = dict(vocab.baseline_physics)
        for binding in vocab.sim_bindings.values():
            if isinstance(binding, dsl.SimBinding) and isinstance(params[binding.key], (int, float)):
                params[binding.key] *= rng.uniform(.8, 1.2)
        folder = args.out_root / f"sample_{index:04d}"
        result = run_case(scene, folder, args, seed, {"physics": params})
        manifest["samples"].append(dict(sample_index=index, seed=seed, params=params,
                                         out_dir=str(folder), **result))
        if not args.dry_run:
            write_json(args.out_root / "batch_manifest.json", manifest)

