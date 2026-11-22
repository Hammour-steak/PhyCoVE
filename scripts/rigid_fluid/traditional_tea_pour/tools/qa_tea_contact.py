"""Encode the actual 96 renders, verify decoding, and make review sheets.

This script does not render, interpolate, smooth, or edit simulation geometry.
Visual review is explicitly separate from these machine checks.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("case", type=Path)
args = parser.parse_args()
case = args.case.resolve()
frames = case / "frames"
expected = [frames / f"frame_{f:04d}.png" for f in range(1, 97)]
if not all(p.is_file() and p.stat().st_size > 0 for p in expected):
    raise RuntimeError("Require all 96 nonempty rendered frames")
if len(list(frames.glob("frame_*.png"))) != 96:
    raise RuntimeError("Unexpected image sequence length")
video = case / "video_contact_fixed.mp4"
if video.exists():
    raise RuntimeError("Do not silently replace an existing video")

encoding_start=time.monotonic()
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                "-framerate", "24", "-start_number", "1", "-i", str(frames / "frame_%04d.png"),
                "-frames:v", "96", "-c:v", "libx264", "-preset", "slow", "-crf", "14",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video)], check=True)
encoding_seconds=time.monotonic()-encoding_start
probe = json.loads(subprocess.check_output([
    "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format",
    "-of", "json", str(video)]))
stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
checks = {
    "frames_96": int(stream["nb_read_frames"]) == 96,
    "1280x720": (stream["width"], stream["height"]) == (1280, 720),
    "24fps": stream["avg_frame_rate"] == "24/1",
    "4seconds": abs(float(probe["format"]["duration"]) - 4.) < .001,
    "h264_yuv420p": stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p",
}
decode = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror",
                         "-i", str(video), "-f", "null", "-"], capture_output=True, text=True)
checks["full_decode_no_errors"] = decode.returncode == 0 and not decode.stderr.strip()

review = case / "evidence"
review.mkdir(exist_ok=True)
for block in range(4):
    start = block * 24 + 1
    # Consecutive frames, left-to-right then top-to-bottom, in each sheet.
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                    "-start_number", str(start), "-i", str(frames / "frame_%04d.png"),
                    "-vf", "crop=320:320:480:352,tile=6x4", "-frames:v", "1",
                    str(review / f"cup_frames_{start:04d}_{start+23:04d}.png")], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                    "-start_number", str(start), "-i", str(frames / "frame_%04d.png"),
                    "-vf", "scale=320:180,tile=6x4", "-frames:v", "1",
                    str(review / f"environment_frames_{start:04d}_{start+23:04d}.png")], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                    "-start_number", str(start), "-i", str(frames / "frame_%04d.png"),
                    "-vf", "crop=240:200:320:430,tile=6x4", "-frames:v", "1",
                    str(review / f"table_left_frames_{start:04d}_{start+23:04d}.png")], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                    "-start_number", str(start), "-i", str(frames / "frame_%04d.png"),
                    "-vf", "crop=240:200:780:430,tile=6x4", "-frames:v", "1",
                    str(review / f"table_right_frames_{start:04d}_{start+23:04d}.png")], check=True)
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                "-start_number", "1", "-i", str(frames / "frame_%04d.png"),
                "-vf", "select=not(mod(n\\,8)),scale=480:270,tile=4x3", "-frames:v", "1",
                str(review / "scene_contact_sheet.png")], check=True)

report = {"video": str(video), "checks": checks, "passed": all(checks.values()),
          "encode_seconds":encoding_seconds,"review_crop_xywh":[480,352,320,320],"encoding_crf":14,
          "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
          "image_sequence_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in expected},
          "probe": probe, "decode_stderr": decode.stderr,
          "visual_review_required": True,
          "visual_review_sheets": [f"cup_frames_{s:04d}_{s+23:04d}.png" for s in (1,25,49,73)]}
(case / "video_validation.json").write_text(json.dumps(report, indent=2) + "\n")
print("GENESIS_VIDEO=" + json.dumps({k: v for k, v in report.items() if k in ("checks", "passed", "video_sha256")}), flush=True)
if not report["passed"]:
    raise SystemExit(2)
