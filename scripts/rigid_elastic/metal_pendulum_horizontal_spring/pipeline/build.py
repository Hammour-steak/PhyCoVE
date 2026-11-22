"""Orchestrate isolated simulation, static review, rendering and verification."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from scene_config import CASES, configuration
from scene_paths import (
    DEFAULT_BLENDER,
    DEFAULT_OUTPUT,
    DEFAULT_PYTHON,
    REPO_ROOT,
    SCENE_DIR,
    cache_matches,
    render_signature,
    sha256,
)

KEYFRAMES = [1, 6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 19, 21, 25, 49, 73, 96]


def call(command, log, env):
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with log.open("w") as output:
        subprocess.run(
            list(map(str, command)),
            cwd=REPO_ROOT,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=True,
        )
    return time.monotonic() - start


@contextmanager
def case_lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".pipeline.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def source_config_signature():
    return hashlib.sha256(
        json.dumps(configuration("source"), sort_keys=True).encode()
    ).hexdigest()


def require_static_acceptance(root):
    path = root / "static_acceptance" / "acceptance.json"
    if not path.is_file():
        raise RuntimeError(
            "Static review is required. Run --stage keyframes, review the full-quality stills, and record static_acceptance/acceptance.json; see README.md."
        )
    result = json.loads(path.read_text())
    expected = render_signature()
    checks = [
        result.get("accepted") is True,
        result.get("source_config_sha256") == source_config_signature(),
    ]
    keys = {
        "asset_manifest_sha256": "asset_manifest_sha256",
    }
    checks.extend(result.get(keys[name]) == value for name, value in expected.items())
    if not all(checks):
        raise RuntimeError(
            "Static acceptance is stale for this configuration, renderer or asset manifest. Use a fresh review/output directory."
        )


def render_command(args, folder, output, frames=None):
    command = [
        args.blender,
        "--factory-startup",
        "-b",
        "-t",
        args.threads,
        "--python-exit-code",
        "1",
        "--python",
        SCENE_DIR / "render_metal_pendulum_horizontal_spring.py",
        "--",
        "--run",
        folder,
        "--out-root",
        output,
        "--save-blend",
        "--skip-existing",
    ]
    if frames:
        command += ["--frame-list", ",".join(map(str, frames))]
    return command


def build_case(args, case, stage, env):
    folder = args.out / "cases" / case
    logs = args.out / "logs"
    with case_lock(folder):
        path = folder / "pipeline_manifest.json"
        state = (
            json.loads(path.read_text())
            if path.exists()
            else {"case": case, "directory": str(folder)}
        )
        state.pop("error", None)
        state["status"] = stage + "_running"
        try:
            if stage == "simulate":
                state["simulate_wall_seconds"] = call(
                    [
                        args.python,
                        SCENE_DIR / "simulate_metal_pendulum_horizontal_spring.py",
                        "--out-root",
                        folder,
                        "--case",
                        case,
                        "--reuse-cache",
                    ],
                    logs / f"{case}_simulate.log",
                    env,
                )
                call(
                    [args.python, SCENE_DIR / "validation/physics.py", folder],
                    logs / f"{case}_physics_validation.log",
                    env,
                )
                state["simulation"] = "completed_or_hash_verified_reuse"
            elif stage == "keyframes":
                if not json.loads((folder / "physics_validation.json").read_text())[
                    "engineering_accepted"
                ]:
                    raise RuntimeError("Physical graybox has not passed")
                state["keyframes_wall_seconds"] = call(
                    render_command(
                        args, folder, args.out / "static_review" / case, [1, 9, 17]
                    ),
                    logs / f"{case}_keyframes.log",
                    env,
                )
            elif stage == "render":
                require_static_acceptance(args.out)
                if not json.loads((folder / "physics_validation.json").read_text())[
                    "engineering_accepted"
                ]:
                    raise RuntimeError("Physical graybox has not passed")
                if (folder / "video.mp4").exists():
                    # Existing products must be complete and match their recorded hash.
                    report = json.loads(
                        (folder / "frames/render_report.json").read_text()
                    )
                    if (
                        report["config"] != configuration(case)
                        or any(
                            report.get(k) != v for k, v in render_signature().items()
                        )
                        or report["trajectory_sha256"]
                        != sha256(folder / "trajectory.npz")
                    ):
                        raise RuntimeError(
                            "Existing video inputs differ from the current code/configuration"
                        )
                    if not (folder / "video_validation.json").is_file():
                        call(
                            [args.python, SCENE_DIR / "validation/video.py", folder],
                            logs / f"{case}_video_validation.log",
                            env,
                        )
                    validation = json.loads(
                        (folder / "video_validation.json").read_text()
                    )
                    if (
                        not validation["passed"]
                        or sha256(folder / "video.mp4") != validation["sha256"]
                    ):
                        raise RuntimeError(
                            "Existing video is unverified or changed; use a fresh output root"
                        )
                    state["render"] = "existing_verified_video"
                else:
                    state["render_wall_seconds"] = call(
                        render_command(args, folder, folder / "frames"),
                        logs / f"{case}_render.log",
                        env,
                    )
                    state["playback_export_seconds"] = call(
                        [
                            args.blender,
                            "--factory-startup",
                            "-b",
                            "-t",
                            args.threads,
                            "--python-exit-code",
                            "1",
                            "--python",
                            SCENE_DIR / "tools/export_playback.py",
                            "--",
                            "--run",
                            folder,
                        ],
                        logs / f"{case}_playback.log",
                        env,
                    )
                    render = configuration(case)["render"]
                    state["encode_seconds"] = call(
                        [
                            "ffmpeg",
                            "-n",
                            "-framerate",
                            render["fps"],
                            "-start_number",
                            "1",
                            "-i",
                            folder / "frames/%04d.png",
                            "-frames:v",
                            render["frames"],
                            "-c:v",
                            render["codec"],
                            "-preset",
                            "slow",
                            "-crf",
                            render["crf"],
                            "-pix_fmt",
                            render["pixel_format"],
                            "-movflags",
                            "+faststart",
                            folder / "video.mp4",
                        ],
                        logs / f"{case}_encode.log",
                        env,
                    )
                    call(
                        [args.python, SCENE_DIR / "validation/video.py", folder],
                        logs / f"{case}_video_validation.log",
                        env,
                    )
                    state["render"] = "completed"
                for frame in KEYFRAMES:
                    target = folder / "keyframes"
                    target.mkdir(exist_ok=True)
                    shutil.copy2(
                        folder / "frames" / f"{frame:04d}.png",
                        target / f"{frame:04d}.png",
                    )
                alias = args.out / f"{case}.mp4"
                if alias.exists() and sha256(alias) != sha256(folder / "video.mp4"):
                    raise RuntimeError(
                        "Root video alias differs; use a fresh output root"
                    )
                if not alias.exists():
                    shutil.copy2(folder / "video.mp4", alias)
            elif stage == "verify":
                call(
                    [args.python, SCENE_DIR / "validation/physics.py", folder],
                    logs / f"{case}_physics_validation.log",
                    env,
                )
                call(
                    [args.python, SCENE_DIR / "validation/video.py", folder],
                    logs / f"{case}_video_validation.log",
                    env,
                )
                state["status"] = "physics_and_technical_verified"
            if stage != "verify":
                state["status"] = stage + "_completed"
        except BaseException as error:
            state.update(status="failed", error=str(error))
            raise
        finally:
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(state, indent=2) + "\n")
            temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    parser.add_argument(
        "--stage",
        choices=["all", "prepare", "simulate", "keyframes", "render", "verify"],
        default="all",
    )
    parser.add_argument("--python", default=str(DEFAULT_PYTHON))
    parser.add_argument("--blender", default=str(DEFAULT_BLENDER))
    parser.add_argument("--gpu")
    parser.add_argument("--threads", type=int, default=6)
    args = parser.parse_args()
    args.out = args.out.resolve()
    # Reject another implementation's accepted run before writing logs or state.
    for case in CASES:
        folder = args.out / "cases" / case
        if (folder / "metrics.json").exists() and not cache_matches(
            folder, configuration(case)
        ):
            raise RuntimeError(
                "Existing run has another configuration, implementation or cache hash; use a fresh --out-root: "
                + str(folder)
            )
    args.out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if args.gpu is not None:
        env["CUDA_VISIBLE_DEVICES"] = args.gpu
    env.update(
        OMP_NUM_THREADS=str(args.threads), OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1"
    )
    if args.stage in ["all", "prepare"]:
        call(
            [
                args.python,
                SCENE_DIR / "asset_tools/prepare.py",
                "--report",
                args.out / "asset_validation.json",
            ],
            args.out / "logs/assets.log",
            env,
        )
    stages = (
        ["simulate", "keyframes", "render", "verify"]
        if args.stage == "all"
        else [args.stage]
    )
    for stage in stages:
        if stage == "prepare":
            continue
        selected = (
            ["source"] if stage == "keyframes" and args.stage == "all" else args.cases
        )
        for case in selected:
            build_case(args, case, stage, env)
    print(args.out)
