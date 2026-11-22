"""Render an immutable prepared source project with a bounded CPU worker pool."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--threads", type=int, default=32)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 16 or args.threads < 1:
        raise ValueError("Invalid worker budget")
    if args.workers * args.threads > max(1, (os.cpu_count() or 1) - 32):
        raise ValueError("Leave at least 32 logical CPUs outside this worker pool")
    out = args.out_dir.expanduser().resolve()
    cfg = json.loads((out / "settings.json").read_text())
    project = out / "ball_box_rebound.blend"
    project_sha = hashlib.sha256(project.read_bytes()).hexdigest()
    if not args.skip_existing and (out / "frames").exists() and any((out / "frames").iterdir()):
        raise FileExistsError("Choose a fresh prepared case or explicitly resume it")
    begin = time.perf_counter()
    processes, commands = [], []
    for index in range(args.workers):
        start = 1 + index * 96 // args.workers
        end = (index + 1) * 96 // args.workers
        worker = f"cpu_{index:02d}"
        command = [str(args.blender), "--factory-startup", "-b", str(project), "-t", str(args.threads),
                   "--python-exit-code", "1", "--python", str(HERE / "tools/render_frozen_frames.py"), "--",
                   "--out-dir", str(out), "--frame-start", str(start), "--frame-end", str(end),
                   "--worker-id", worker, "--threads", str(args.threads)]
        if args.skip_existing:
            command.append("--skip-existing")
        log = (out / ("render_worker_" + worker + ".log")).open("w")
        processes.append((subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT), log, worker))
        commands.append(command)
    execution = {"backend": "CPU", "workers": args.workers, "threads_per_worker": args.threads,
                 "total_thread_budget": args.workers * args.threads, "logical_cpus": os.cpu_count(),
                 "host_load_at_start": list(os.getloadavg()), "prepared_project_sha256": project_sha,
                 "commands": commands, "configuration": cfg}
    dump(out / "parallel_render_execution.json", execution)
    try:
        for process, log, worker in processes:
            code = process.wait()
            log.close()
            if code:
                raise RuntimeError("Worker failed: " + worker)
    except BaseException:
        for process, log, worker in processes:
            if process.poll() is None:
                process.terminate()
        raise
    wall = time.perf_counter() - begin
    if hashlib.sha256(project.read_bytes()).hexdigest() != project_sha:
        raise RuntimeError("Prepared project changed")
    reports = [json.loads((out / ("render_worker_" + worker + ".json")).read_text()) for _, _, worker in processes]
    assert all(r["status"] == "complete" and r["prepared_project_sha256"] == project_sha for r in reports)
    for frame in range(1, 97):
        file = out / "frames" / f"frame_{frame:04d}.png"
        with file.open("rb") as stream:
            header = stream.read(24)
        assert header[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", header[16:24]) == (1280, 720)
    start = time.perf_counter()
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-threads", "4", "-framerate", "24",
                    "-start_number", "1", "-i", str(out / "frames/frame_%04d.png"), "-frames:v", "96", "-an",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out / "video.mp4")], check=True)
    encode = time.perf_counter() - start
    subprocess.run([sys.executable, str(ROOT / "scripts/pcve_verify_video.py"), str(out / "video.mp4"), "--out",
                    str(out / "video_validation.json"), "--resolution", "1280", "720", "--fps", "24", "--frames", "96"], check=True)
    times = {f: seconds for r in reports for f, seconds in r["frame_seconds"].items()}
    metadata = json.loads((out / "scenario_metadata.json").read_text())
    dump(out / "render_report_animation.json", {"mode": "animation", "backend": "CPU parallel",
         "blender_version": metadata["blender_version"], "render_sec": sum(times.values()), "render_wall_sec": wall,
         "encode_sec": encode, "samples": cfg["render"]["samples"], "resolution": [1280, 720],
         "frame_seconds": times, "workers": args.workers, "threads_per_worker": args.threads,
         "reused_frames": 96 - len(times), "prepared_project_sha256": project_sha})
    execution.update(status="complete", render_wall_sec=wall, encode_sec=encode)
    dump(out / "parallel_render_execution.json", execution)
    print("Complete: 96 frames, 720P, 24 fps, 4 seconds", flush=True)


if __name__ == "__main__":
    main()
