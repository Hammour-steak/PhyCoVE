"""Render a disjoint frame range from the prepared, immutable source project."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scene_config import signature


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--frame-start", type=int, required=True)
    parser.add_argument("--frame-end", type=int, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--device", choices=["cpu", "optix", "cuda"], default="cpu",
                        help="GPU backends render on the CUDA_VISIBLE_DEVICES-selected card; keep one device per case")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.worker_id):
        raise ValueError("Worker ID must be a simple filename component")
    if not 1 <= args.frame_start <= args.frame_end <= 96:
        raise ValueError("Frame range must be within the requested 96 frames")
    out = args.out_dir.expanduser().resolve()
    settings = json.loads((out / "settings.json").read_text())
    scene = bpy.context.scene
    if scene.get("pcve_configuration_sha256") != signature(settings):
        raise ValueError("Loaded project and output settings differ")
    project = Path(bpy.data.filepath)
    project_sha = hashlib.sha256(project.read_bytes()).hexdigest()
    scene.cycles.device = "CPU"
    backend = "CPU"
    if args.device != "cpu":
        compute = args.device.upper()
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = compute
        preferences.get_devices()
        selected = [d for d in preferences.devices if d.type == compute]
        if not selected:
            raise RuntimeError("No " + compute + " device visible")
        for device in preferences.devices:
            device.use = device in selected
        scene.cycles.device = "GPU"
        backend = compute + ": " + ", ".join(d.name for d in selected)
    scene.cycles.denoising_use_gpu = False
    scene.render.threads_mode = "FIXED"
    scene.render.threads = args.threads
    # Blender 4.3 drops objects that come to rest when persistent data is
    # combined with motion blur; keep it only for unblurred projects.
    scene.render.use_persistent_data = not scene.render.use_motion_blur
    frames = out / "frames"
    frames.mkdir(exist_ok=True)
    report_path = out / ("render_worker_" + args.worker_id + ".json")
    report = {"worker_id": args.worker_id, "backend": backend, "threads": args.threads,
              "motion_blur_shutter_frames": scene.render.motion_blur_shutter if scene.render.use_motion_blur else 0,
              "persistent_data": scene.render.use_persistent_data,
              "prepared_project_sha256": project_sha, "configuration_sha256": signature(settings),
              "samples": scene.cycles.samples, "frame_range": [args.frame_start, args.frame_end],
              "frame_seconds": {}, "frame_sha256": {}, "reused_frames": [], "status": "running"}
    begin = time.perf_counter()
    for frame in range(args.frame_start, args.frame_end + 1):
        dest = frames / f"frame_{frame:04d}.png"
        if dest.exists():
            if args.skip_existing:
                report["reused_frames"].append(frame)
                continue
            raise FileExistsError(dest)
        scene.frame_set(frame)
        scene.render.filepath = str(dest)
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        report["frame_seconds"][str(frame)] = time.perf_counter() - start
        report["frame_sha256"][str(frame)] = hashlib.sha256(dest.read_bytes()).hexdigest()
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"PCVE_WORKER {args.worker_id} FRAME {frame}", flush=True)
    report["worker_wall_sec"] = time.perf_counter() - begin
    report["status"] = "complete"
    if hashlib.sha256(project.read_bytes()).hexdigest() != project_sha:
        raise RuntimeError("Prepared source project changed during rendering")
    report_path.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
