"""Encode a rendered case folder (frame_0000.png ... frame_0095.png) exactly as render_scene.py does.

    python3 scripts/rigid_elastic/metro_security_bag_curtain/tools/encode_case.py <case render dir> [--native DIR]

Used when the frames were rendered on a host without ffmpeg: writes video.mp4 (libx264 CRF 16, yuv420p,
24 fps, 96 frames) and encoding_receipt.json with the same fields render_scene.py writes; the renderer and
environment hashes are taken from the case's render_report.json.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]
from scene_paths import NATIVE, ffmpeg_binary  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--native", type=Path, default=NATIVE)
    a = ap.parse_args()
    out = a.folder.resolve()
    report = json.loads((out / "render_report.json").read_text())
    frames = sorted(out.glob("frame_*.png"))
    if len(frames) != 96 or report["frames"] != list(range(96)):
        raise SystemExit("96 rendered frames and a matching render_report.json are required")
    states = a.native / report["case_id"] / "states.npz"
    if sha(states) != report["simulation_cache_sha256"]:
        raise SystemExit("render_report.json does not belong to these native states")
    ffmpeg = ffmpeg_binary()
    subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-framerate", "24", "-i", str(out / "frame_%04d.png"),
                    "-frames:v", "96", "-c:v", "libx264", "-threads", "4", "-preset", "slow", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out / "video.mp4")], check=True)
    receipt = {"video_sha256": sha(out / "video.mp4"), "encoder": "CPU ffmpeg/libx264 CRF16", "ffmpeg_binary_sha256": sha(ffmpeg),
               "input_state_sha256": report["simulation_cache_sha256"], "frames": 96, "fps": 24}
    (out / "encoding_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=1))


if __name__ == "__main__":
    main()
