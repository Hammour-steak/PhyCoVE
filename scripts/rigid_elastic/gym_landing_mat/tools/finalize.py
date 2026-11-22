"""Finalize one remote-rendered 96-frame gym edit without invoking Blender."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", type=Path, required=True)
    args = parser.parse_args()
    main_dir = args.render.resolve()
    frames, raw = main_dir / "frames", main_dir / "masks_raw"
    expected = [frames / f"{index:04d}.png" for index in range(1, 97)]
    if not all(path.is_file() for path in expected):
        raise RuntimeError("The 96-frame render is incomplete")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "24", "-i", str(frames / "%04d.png"),
                    "-frames:v", "96", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(main_dir / "video.mp4")], check=True)
    report = json.loads((main_dir / "simulation_report.json").read_text(encoding="utf-8"))
    config = json.loads((main_dir / "simulation_config.json").read_text(encoding="utf-8"))
    shutil.copy2(expected[0], main_dir / "first_frame.png")
    peak = max(1, min(96, int(report["peak_frame"])))
    shutil.copy2(frames / f"{peak:04d}.png", main_dir / "hero.png")
    impact_rows = [row for row in report["frames"] if 0.12 <= row["time_sec"] <= 0.35]
    impact = max(impact_rows, key=lambda row: row["local_depression_m"])["frame_index"]
    shutil.copy2(frames / f"{impact:04d}.png", main_dir / "first_impact.png")
    canvas = Image.new("RGB", (1280, 1116), (16, 16, 16)); draw = ImageDraw.Draw(canvas)
    for slot, frame in enumerate((1, impact, min(96, impact + 4), peak, 48, 96)):
        image = Image.open(frames / f"{frame:04d}.png").convert("RGB").resize((640, 360), Image.Resampling.LANCZOS)
        x, y = (slot % 2) * 640, (slot // 2) * 372
        canvas.paste(image, (x, y)); draw.rectangle((x, y + 344, x + 640, y + 372), fill=(16, 16, 16))
        draw.text((x + 8, y + 350), f"frame {frame} | {(frame - 1) / 24:.3f} s", fill=(235, 235, 235))
    canvas.save(main_dir / "contact_sheet.jpg", quality=93, subsampling=0)
    masks = []
    for frame in range(1, 97):
        label = np.zeros((720, 1280), np.uint8)
        for instance_id in (1, 2, 3):
            path = raw / f"id{instance_id}_{frame:04d}.png"
            if not path.is_file():
                raise RuntimeError(f"Missing instance mask: {path}")
            label[np.asarray(Image.open(path).convert("L")) > 127] = instance_id
        masks.append(label)
    np.savez_compressed(main_dir / "instance_masks.npz", masks=np.stack(masks),
                        frame_numbers=np.arange(1, 97, dtype=np.int32), fps=np.array([24], np.int32),
                        resolution=np.array([1280, 720], np.int32))
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "stream=width,height,avg_frame_rate,nb_read_frames:format=duration", "-of", "json", str(main_dir / "video.mp4")]))
    stream = probe["streams"][0]
    if ([stream["width"], stream["height"]] != [1280, 720] or stream["avg_frame_rate"] != "24/1"
            or int(stream["nb_read_frames"]) != 96 or abs(float(probe["format"]["duration"]) - 4.0) > 1e-6):
        raise RuntimeError(f"Video contract failed: {probe}")
    save(main_dir / "video_probe.json", probe)
    save(main_dir / "scenario_metadata.json", {"scene_id": "gym_landing_mat", "case": config["case"],
        "category": "rigid_elastic", "source_or_edit": "edit" if config["edit"] else "source", "edit": config["edit"], "fps": 24,
        "duration_seconds": 4.0, "frame_count": 96, "resolution": [1280, 720],
        "release_status": config["release_status"], "server_blender_only": True})
    wanted = []
    for path in main_dir.rglob("*"):
        if not path.is_file() or "frames" in path.parts or "masks_raw" in path.parts or path.name in {"scene.blend", "artifact_manifest.json"}:
            continue
        wanted.append({"path": path.relative_to(main_dir).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    save(main_dir / "artifact_manifest.json", {"schema_version": 1, "scene_id": "gym_landing_mat",
        "release_status": config["release_status"], "files": sorted(wanted, key=lambda item: item["path"])})
    print("FINALIZED gym_landing_mat", config["case"], flush=True)


if __name__ == "__main__":
    main()
