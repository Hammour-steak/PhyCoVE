"""Combine native frames rendered by isolated workers into one delivered case.

Each worker runs the ordinary render entry (`--mode frames --keyframes ...`) on a disjoint
frame set of the same physics cache, for example one process per GPU. This tool checks that
every worker built the same scene (configuration, static background, render backend, ground
truth and settings), copies the 96 native PNGs unchanged, takes the packed scene and metadata
from the first worker, encodes video.mp4 with exactly the render entry's ffmpeg settings,
verifies it and writes render_report_animation.json. No frame is re-rendered or resampled.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
SCENE = "basketball_court_bounce"


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False)+"\n")


def mapped(text, pairs):
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case-dir", type=Path, required=True, help="Delivered case folder holding physics_transforms.json")
    p.add_argument("--worker-dirs", type=Path, nargs="+", required=True)
    p.add_argument("--path-map", nargs="*", default=[], metavar="OLD=NEW",
                   help="Replace worker-machine paths in copied logs and text records")
    a = p.parse_args()
    case = a.case_dir.resolve()
    pairs = [tuple(item.split("=", 1)) for item in a.path_map]
    physics = read(case/"physics_transforms.json")
    workers = [w.resolve() for w in a.worker_dirs]
    metas = [read(w/"scenario_metadata.json") for w in workers]
    for key in ["configuration_sha256", "static_background_sha256", "backend", "ball_present", "blender_version"]:
        values = {json.dumps(m[key]) for m in metas}
        if len(values) != 1:
            raise ValueError(f"Workers disagree on {key}: {values}")
    if metas[0]["configuration_sha256"] != physics["configuration_sha256"]:
        raise ValueError("Worker scenes were built from another physics cache")
    for name in ["ground_truth_transforms.json", "settings.json"]:
        digests = {hashlib.sha256((w/name).read_bytes()).hexdigest() for w in workers}
        if len(digests) != 1:
            raise ValueError(f"Workers disagree on {name}")
    owner = {}
    for w in workers:
        for frame in sorted((w/"frames").glob("frame_*.png")):
            index = int(frame.stem.split("_")[1])
            if index in owner:
                raise ValueError(f"Frame {index} rendered by two workers")
            owner[index] = frame
    if sorted(owner) != list(range(1, 97)):
        raise ValueError(f"Frames missing: {sorted(set(range(1, 97))-set(owner))}")
    frames = case/"frames"
    if frames.exists() and any(frames.iterdir()):
        raise FileExistsError(frames)
    frames.mkdir(exist_ok=True)
    for index in range(1, 97):
        shutil.copy2(owner[index], frames/f"frame_{index:04d}.png")
    first = workers[0]
    shutil.copy2(first/(SCENE+".blend"), case/(SCENE+".blend"))
    for name in ["scenario_metadata.json", "ground_truth_transforms.json", "settings.json"]:
        (case/name).write_text(mapped((first/name).read_text(), pairs))
    reports = [read(w/"render_report_frames.json") for w in workers]
    seconds = {}
    for r in reports:
        seconds.update(r["frame_seconds"])
    logs = []
    for w in workers:
        log = w.parent/(w.name+".log")
        if log.is_file():
            logs.append(f"===== worker {w.name}: frames {min(int(k) for k in read(w/'render_report_frames.json')['frame_seconds'])}"
                        f"-{max(int(k) for k in read(w/'render_report_frames.json')['frame_seconds'])} =====\n"+mapped(log.read_text(errors="replace"), pairs))
    (case/"render_animation.log").write_text("".join(logs))
    begin = time.perf_counter()
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", "24", "-start_number", "1",
                    "-i", str(frames/"frame_%04d.png"), "-frames:v", "96", "-an", "-c:v", "libx264", "-preset", "slow",
                    "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(case/"video.mp4")], check=True)
    encode = time.perf_counter()-begin
    subprocess.run([sys.executable, str(ROOT/"scripts/pcve_verify_video.py"), str(case/"video.mp4"),
                    "--out", str(case/"video_validation.json"), "--resolution", "1280", "720", "--fps", "24", "--frames", "96"], check=True)
    ordered = {str(i): seconds[str(i)] for i in range(1, 97)}
    write(case/"render_progress_animation.json", {"frames_completed": list(ordered), "frame_seconds": ordered})
    write(case/"render_report_animation.json", {
        "mode": "animation", "backend": metas[0]["backend"], "blender_version": metas[0]["blender_version"],
        "setup_sec": sum(r["setup_sec"] for r in reports), "render_sec": sum(ordered.values()), "encode_sec": encode,
        "frame_seconds": ordered, "reused_frames": 0, "samples": reports[0]["samples"], "resolution": [1280, 720],
        "split_render": {"tool": "tools/assemble_split_render.py", "workers": [
            {"frames": [min(int(k) for k in r["frame_seconds"]), max(int(k) for k in r["frame_seconds"])],
             "setup_sec": r["setup_sec"], "render_sec": r["render_sec"]} for r in reports],
            "identical_configuration_static_background_backend_ground_truth_and_settings": True,
            "packed_scene_from_first_worker": True, "frames_copied_unchanged": True}})
    print(json.dumps({"case": str(case), "workers": len(workers), "backend": metas[0]["backend"],
                      "video_sha256": hashlib.sha256((case/"video.mp4").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    sys.exit(main())
