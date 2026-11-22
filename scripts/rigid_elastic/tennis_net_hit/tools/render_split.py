"""Render one case as parallel frame ranges on one device, then merge and encode.

    python3 scripts/rigid_elastic/tennis_net_hit/tools/render_split.py --case <case> \
        --cache <dir>/render_cache.npz --out renders/tennis_net_hit/<folder>/<case> \
        [--parts 4] [--device OPTIX|CUDA|CPU] [--gpu-uuid <uuid>] [--threads-per-part 12]

With persistent data off (required with motion blur in Blender 4.3) most of a frame's time is the
CPU-side scene sync, so several Blender processes sharing one GPU finish a case several times faster
than one. A process peaks near 20 GB of GPU memory, so put at most two parts on a 48 GB card (pass
two same-model GPU UUIDs, comma-separated, for four parts). Each part runs appearance/realism.py with identical settings on the same device and writes to
<out>/parts/<a>-<b>/; the frames are then moved to <out>/frames/0001-0096.png and encoded exactly like
render_tennis_net_hit.py (H.264, crf 16, slow, yuv420p, 24 fps).
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCENE = HERE.parent
SCRIPTS = SCENE.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCENE))
sys.path.insert(0, str(SCENE / "physics"))
from pcve_assets import asset  # noqa: E402
from pcve_media_contract import require_video  # noqa: E402
from scene_paths import blender_runtime, output_path  # noqa: E402
from common import CASES, sha  # noqa: E402


def ranges(parts):
    edges = [round(1 + 96 * k / parts) for k in range(parts + 1)]
    return [(edges[k], edges[k + 1] - 1) for k in range(parts)]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", required=True, choices=tuple(CASES))
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--parts", type=int, default=4)
    p.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX")
    p.add_argument("--gpu-uuid", help="one UUID, or a comma-separated list of same-model GPUs; parts are dealt round-robin")
    p.add_argument("--threads-per-part", type=int, default=12)
    p.add_argument("--samples", type=int)
    p.add_argument("--blender-bin", type=Path)
    p.add_argument("--ffmpeg", default="ffmpeg")
    a = p.parse_args()
    out = output_path(a.out)
    if out.exists():
        p.error("Choose a fresh output directory")
    qual = json.loads(a.cache.with_name("qualification.json").read_text())
    if not qual["passed"] or qual["case_id"] != a.case or qual["render_cache_sha256"] != sha(a.cache):
        p.error("The cache is not a qualified match for this case")
    blender = str(blender_runtime(a.blender_bin))
    scene = asset("scenes/tennis_net_hit/inputs/scene.blend")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    gpus = [""] if a.device == "CPU" else (a.gpu_uuid or env.get("CUDA_VISIBLE_DEVICES", "")).split(",")
    (out / "parts").mkdir(parents=True)
    jobs = []
    for index, (first, last) in enumerate(ranges(a.parts)):
        part = out / "parts" / f"{first:04d}-{last:04d}"
        cmd = [blender, "--disable-autoexec", "-b", str(scene), "-t", str(a.threads_per_part), "--python-exit-code", "1",
               "--python", str(SCENE / "appearance/realism.py"), "--", "--case", a.case, "--cache", str(a.cache.resolve()),
               "--out", str(part), "--frames", f"{first}-{last}", "--device", a.device, "--threads", str(a.threads_per_part)]
        if a.samples:
            cmd += ["--samples", str(a.samples)]
        log = open(out / "parts" / f"{first:04d}-{last:04d}.log", "w")
        part_env = dict(env, CUDA_VISIBLE_DEVICES=gpus[index % len(gpus)])
        jobs.append((first, last, part, subprocess.Popen(cmd, env=part_env, stdout=log, stderr=subprocess.STDOUT), log))
    failed = []
    for first, last, part, proc, log in jobs:
        if proc.wait():
            failed.append(f"{first}-{last}")
        log.close()
    if failed:
        raise SystemExit(f"Parts failed: {failed}; see {out / 'parts'}")
    (out / "frames").mkdir()
    records = []
    for first, last, part, _, _ in jobs:
        for frame in range(first, last + 1):
            (part / "frames" / f"{frame:04d}.png").rename(out / "frames" / f"{frame:04d}.png")
        setup = part / f"render_setup_{first:04d}.json"
        setup.rename(out / setup.name)
        records.append(json.loads((part / "realism_provenance.json").read_text()))
    names = sorted(x.name for x in (out / "frames").glob("*.png"))
    if names != [f"{i:04d}.png" for i in range(1, 97)]:
        raise RuntimeError("The 96 native render frames are required")
    keys = ("revision", "render_cache_sha256", "device", "samples")
    if any(any(r[k] != records[0][k] for k in keys) for r in records):
        raise RuntimeError("Parts differ in renderer, look, cache, device or samples")
    video = out / "video.mp4"
    subprocess.run([a.ffmpeg, "-v", "error", "-framerate", "24", "-start_number", "1", "-i", str(out / "frames/%04d.png"),
                    "-frames:v", "96", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-threads", "4", str(video)], check=True)
    media = require_video(video)
    provenance = {k: records[0][k] for k in records[0] if k not in ("frames", "worker")}
    provenance.update(frames=[1, 96], parts=[{"frames": r["frames"], "worker": r["worker"]} for r in records],
                      split_renderer="scripts/rigid_elastic/tennis_net_hit/tools/render_split.py",
                      video_sha256=sha(video), encoder="ffmpeg libx264 crf 16 preset slow yuv420p, 24 fps")
    (out / "realism_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    for first, last, part, _, _ in jobs:
        for leftover in sorted(part.rglob("*"), key=lambda x: -len(x.parts)):
            if leftover.is_file() and leftover.name.startswith("render_progress_"):
                leftover.unlink()
            elif leftover.is_dir():
                leftover.rmdir()
        (part / "realism_provenance.json").unlink()
        part.rmdir()
        log = out / "parts" / f"{first:04d}-{last:04d}.log"
        tail = log.read_text(errors="replace").splitlines()[-60:]
        log.write_text("\n".join(tail) + "\n")
    print(json.dumps({"case": a.case, "video": str(video), "sha256": provenance["video_sha256"], "media": media}))


if __name__ == "__main__":
    main()
