"""Render one football_goal_net case with the current look, or export its published video.

Default: copy the case's video from the published suite named in scene_manifest.json to --out.
--render: replay the accepted native state with appearance/render.py (Blender 4.3.2) into --out.
    The requested frames are split into --parallel ranges, each rendered by its own Blender process
    on the same device with the same settings; when frames 1-96 are complete the movie is encoded
    (H.264 High, crf 16, yuv420p, 24 fps) as <out>/video.mp4 and <out>/render_setup.json lists every
    frame, its range report and the code/inputs it was made with.
--encode-only: encode an existing complete frame folder (frames rendered elsewhere).
--cache-dir: replay another native solve folder, e.g. the merged solve of the timed case mass_double_at_frame_8
    (simulation.npz, physics_report.json and the timed_edit.json receipt written by physics/solve_timed.py).
"""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

import argparse
import datetime
import json
import os
import subprocess
sys.path.insert(0, str(CASE))
from tools.retained import CASES, MANIFEST, REPO, catalog_id, export, read, sha  # noqa: E402
from edit_vocab import TIMED_DSL  # noqa: E402

RENDER = CASE / "appearance/render.py"


def blender_default():
    from pcve_assets import blender
    return blender()


def ranges(frames, parts):
    parts = max(1, min(parts, len(frames)))
    size = -(-len(frames) // parts)
    return [frames[i:i + size] for i in range(0, len(frames), size)]


def encode(out):
    frames = [out / f"frame_{k:04d}.png" for k in range(1, 97)]
    missing = [f.name for f in frames if not f.is_file()]
    if missing:
        raise RuntimeError(f"Incomplete frame set, missing {missing[:5]}")
    video = out / "video.mp4"
    if video.exists():
        raise FileExistsError(video)
    subprocess.run(["ffmpeg", "-v", "error", "-n", "-framerate", "24", "-i", str(out / "frame_%04d.png"),
                    "-frames:v", "96", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(video)], check=True)
    reports = sorted(out.glob("render_report_*.json"))
    rows = {}
    for report in reports:
        for row in read(report)["frames"]:
            rows[row["frame"]] = {**row, "report": report.name}
    if sorted(rows) != list(range(1, 97)):
        raise RuntimeError("The range reports do not cover frames 1-96 exactly once")
    for k, row in rows.items():
        if sha(out / row["file"]) != row["sha256"]:
            raise RuntimeError(f"frame {k} changed after rendering")
    first = read(reports[0])
    for report in reports[1:]:
        other = read(report)
        for key in ("case", "device", "samples", "seed", "cache_sha256", "look", "camera"):
            if other[key] != first[key]:
                raise RuntimeError(f"{report.name}: {key} differs between frame ranges")
    setup = {"case": first["case"], "video": "video.mp4",
             "video_sha256": sha(video), "frames": [rows[k] for k in range(1, 97)],
             "range_reports": [r.name for r in reports],
             "shared": {k: first[k] for k in ("device", "devices", "samples", "denoiser", "seed", "resolution", "fps",
                                              "native_fps", "shutter_seconds", "persistent_data", "view_transform",
                                              "camera", "cache_sha256", "scene_sha256", "look", "blender")},
             "hosts": sorted({read(r)["host"] for r in reports}),
             "encoder": "ffmpeg libx264 preset slow crf 16 yuv420p +faststart, 24 fps",
             "physics_changed": False, "encoded_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    (out / "render_setup.json").write_text(json.dumps(setup, indent=1) + "\n", encoding="utf-8")
    return setup


def render(a):
    out = a.out.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    first, last = (int(v) for v in a.frames.split("-"))
    frames = list(range(first, last + 1))
    env = dict(os.environ)
    if a.gpu is not None:
        env["CUDA_VISIBLE_DEVICES"] = a.gpu
    blender = str(a.blender_bin or blender_default())
    children = []
    for part in ranges(frames, a.parallel):
        command = [blender, "-b", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
                   "--python", str(RENDER), "--", "--case", a.case, "--out", str(out),
                   "--frames", f"{part[0]}-{part[-1]}", "--device", a.device, "--samples", str(a.samples)]
        if a.threads:
            command += ["--threads", str(a.threads)]
        if a.cache_dir:
            command += ["--cache-dir", str(a.cache_dir.expanduser().resolve())]
        log = (out / f"blender_{part[0]:04d}-{part[-1]:04d}.log").open("w")
        children.append((subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=REPO), log))
    failed = []
    for child, log in children:
        if child.wait() != 0:
            failed.append(log.name)
        log.close()
    if failed:
        raise RuntimeError(f"Blender failed: {failed}")
    if first == 1 and last == 96:
        return encode(out)
    return {"frames": [first, last], "out": str(out)}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", choices=CASES + tuple(TIMED_DSL), default="source")
    p.add_argument("--cache-dir", type=Path, help="native solve to replay (a timed case's merged solve from physics/solve_timed.py)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--render", action="store_true")
    p.add_argument("--encode-only", action="store_true")
    p.add_argument("--frames", default="1-96")
    p.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX")
    p.add_argument("--samples", type=int, default=256)
    p.add_argument("--parallel", type=int, default=1, help="frame ranges rendered at once on the same device")
    p.add_argument("--gpu", help="CUDA_VISIBLE_DEVICES for the Blender processes (index or UUID)")
    p.add_argument("--blender-bin", type=Path)
    p.add_argument("--threads", type=int, default=0, help="CPU threads per Blender process (0 = automatic)")
    a = p.parse_args()
    if a.encode_only:
        print(json.dumps(encode(a.out.expanduser().resolve()), indent=1))
    elif a.render:
        print(json.dumps(render(a), indent=1))
    else:
        pointer = next(iter(read(MANIFEST)["canonical_suites"].values()))
        cid = catalog_id(a.case)
        export(REPO / pointer["target"] / "cases" / cid / "video.mp4", a.out, pointer["case_video_sha256"][a.case])
