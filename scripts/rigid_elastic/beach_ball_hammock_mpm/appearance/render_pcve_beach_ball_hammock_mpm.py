"""Apply the MPM cache, render, encode and verify the source video."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

import bpy


SCENE_DIR = Path(__file__).resolve().parents[1]
# Photographic beach look (appearance/look_beach.py) configured by appearance/appearance.json.
DEFAULT_APPEARANCE = SCENE_DIR / "appearance/appearance.json"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--appearance-json", default=str(DEFAULT_APPEARANCE),
                        help='appearance JSON of the photographic beach look')
    parser.add_argument("--device", choices=("auto", "CPU", "GPU", "OPTIX", "CUDA"), default="auto",
                        help="Cycles device; auto uses the GPU when CUDA_VISIBLE_DEVICES is set (build --gpu)")
    parser.add_argument("--frames-only", action="store_true",
                        help="render work/frames and stop (for distributed rendering; a later run with "
                             "SKIP_EXISTING=1 encodes and verifies)")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# Objects of each body that a DELETE edit removes from the render (the look builds them all). The posts stay:
# deleting the hammock removes the canvas, its rope ends and whippings, not the two timber posts.
BODY_OBJECTS = {"ball_present": ("BeachBall_RigidBody",),
                "hammock_present": ("Hammock_ElasticBody_ORIGINAL", "Hammock_Fabric_Visible", "Hammock_Rope_",
                                    "Hammock_Whipping_")}


def hide_absent_bodies(metrics):
    """Hide (from every ray) the bodies the solve ran without; a no-op for every published case."""
    hidden = []
    for key, names in BODY_OBJECTS.items():
        if metrics.get(key, True):
            continue
        roots = [o for o in bpy.data.objects if any(o.name == n or (n.endswith("_") and o.name.startswith(n))
                                                   for n in names)]
        for obj in roots + [c for o in roots for c in o.children_recursive]:
            obj.hide_render = True
            obj.hide_viewport = True
            hidden.append(obj.name)
    return sorted(set(hidden))


def main():
    args = parse_args()
    work = args.work_dir.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    source = work / "scene.blend"
    cache = work / "mpm_flat_drop_final_cache.npz"
    metrics = work / "mpm_flat_drop_final_metrics.json"
    for path in (source, cache, metrics):
        if not path.is_file():
            raise FileNotFoundError(path)
    output.mkdir(parents=True, exist_ok=True)

    os.environ["PCVE_SCENE_ROOT"] = str(SCENE_DIR)
    os.environ["PCVE_WORK_DIR"] = str(work)
    os.environ["PCVE_OUTPUT_DIR"] = str(output)
    os.environ["MPM_CACHE_NAME"] = cache.name
    os.environ["MPM_METRICS_NAME"] = metrics.name
    os.environ["MPM_BLEND_OUTPUT_NAME"] = "scene_simulated.blend"
    os.environ["MPM_EXPERIMENT_OUTPUT_NAME"] = "experiment.json"
    os.environ["MPM_FRAME_DIR"] = "frames"

    bpy.ops.wm.open_mainfile(filepath=str(source))
    runpy.run_path(str(SCENE_DIR / "appearance/apply_mpm_cache_to_blender.py"), run_name="__main__")
    runpy.run_path(str(SCENE_DIR / "appearance/validate_mpm_blend.py"), run_name="__main__")
    appearance = None
    sys.path.insert(0, str(SCENE_DIR / "appearance"))
    import look_beach as look
    device = args.device
    if device == "auto":
        device = "GPU" if os.environ.get("CUDA_VISIBLE_DEVICES", "").strip() not in ("", "-1") else "CPU"
    appearance = look.apply_look(Path(args.appearance_json).resolve(), device)
    appearance["appearance_json_sha256"] = sha256(Path(args.appearance_json).resolve())
    hidden = hide_absent_bodies(json.loads(metrics.read_text(encoding="utf-8")))
    if hidden:
        appearance["hidden_absent_bodies"] = hidden
    (output / "appearance_report.json").write_text(
        json.dumps(appearance, ensure_ascii=False, indent=2, default=float) + "\n", encoding="utf-8")

    frames_before = len(list((work / "frames").glob("frame_*.png"))) if (work / "frames").is_dir() else 0
    start = time.monotonic()
    runpy.run_path(str(SCENE_DIR / "appearance/render_mpm_full.py"), run_name="__main__")
    render_seconds = time.monotonic() - start
    separate_report = work / "frames_render_report.json"
    if args.frames_only:
        scene = bpy.context.scene
        separate_report.write_text(json.dumps({
            "frames": len(list((work / "frames").glob("frame_*.png"))),
            "render_seconds": render_seconds,
            "device": scene.get("pcve_render_device", scene.cycles.device),
            "samples": scene.cycles.samples,
            "blender": bpy.app.version_string,
            "appearance": appearance["preset"],
            "appearance_json_sha256": appearance["appearance_json_sha256"],
        }, indent=2) + "\n", encoding="utf-8")
        print(f"PCVE_FRAMES_ONLY={work / 'frames'}", flush=True)
        return

    frames = work / "frames"
    frame_paths = sorted(frames.glob("frame_*.png"))
    if len(frame_paths) != 96:
        raise RuntimeError(f"Expected 96 frames, found {len(frame_paths)}")

    video = output / "video.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", "24", "-start_number", "1",
            "-i", str(frames / "frame_%04d.png"), "-c:v", "libx264",
            "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(video),
        ],
        check=True,
    )
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-count_frames", "-show_entries",
                "stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames:format=duration,size",
                "-of", "json", str(video),
            ],
            text=True,
        )
    )
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)
    stream = probe["streams"][0]
    if not (
        stream["width"] == 1280
        and stream["height"] == 720
        and stream["r_frame_rate"] == "24/1"
        and int(stream["nb_read_frames"]) == 96
    ):
        raise RuntimeError(f"Unexpected video specification: {probe}")

    report = {
        "status": "technical_checks_passed_visual_review_pending",
        "render_seconds": render_seconds,
        "video": str(video),
        "video_sha256": sha256(video),
        "ffprobe": probe,
        "frame_files": len(frame_paths),
        "blender_cloth_used": False,
        "solver": "Taichi MLS-MPM fixed-corotated elasticity",
        "frames_present_before_render_stage": frames_before,
        "frames_rendered_separately": json.loads(separate_report.read_text()) if separate_report.is_file() else None,
        "appearance": appearance["preset"],
        "render_device": "scene default" if appearance is None else appearance["render_device"],
    }
    (output / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    spec_path = work / "scene_spec.json"
    if spec_path.is_file():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["status"] = report["status"]
        spec["verification"] = {
            "report": str(output / "verification.json"),
            "video": str(video),
            "video_sha256": report["video_sha256"],
        }
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PCVE_VIDEO={video}", flush=True)
    print(f"PCVE_VIDEO_SHA256={report['video_sha256']}", flush=True)


if __name__ == "__main__":
    main()

