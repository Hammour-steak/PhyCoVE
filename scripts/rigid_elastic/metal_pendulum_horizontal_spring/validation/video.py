"""Verify a complete formal video against its recorded render configuration."""

import argparse
import json
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import subprocess

from scene_paths import sha256


def validate(folder):
    config = json.loads((folder / "actual_config.json").read_text())["render"]
    video = folder / "video.mp4"
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    expected_rate = f"{config['fps']}/1"
    checks = {
        "resolution": [stream["width"], stream["height"]] == config["resolution"],
        "frame_rate": stream["r_frame_rate"]
        == stream["avg_frame_rate"]
        == expected_rate,
        "frames": int(stream["nb_read_frames"]) == config["frames"],
        "duration": abs(float(info["format"]["duration"]) - config["duration_s"])
        < 0.002,
        "complete_master_sequence": all(
            (folder / "frames" / f"{frame:04d}.png").is_file()
            for frame in range(1, config["frames"] + 1)
        ),
    }
    decode = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"],
        capture_output=True,
        check=True,
    )
    checks["full_decode"] = not decode.stderr
    result = {
        **info,
        "checks": checks,
        "passed": all(checks.values()),
        "full_decode_passed": checks["full_decode"],
        "sha256": sha256(video),
    }
    (folder / "video_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    if not result["passed"]:
        raise RuntimeError("Video specification rejected: " + str(checks))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.run), indent=2))


if __name__ == "__main__":
    main()
