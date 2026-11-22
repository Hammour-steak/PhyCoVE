"""Package one rendered case: video, instance masks, GT, contact sheet and audits (CPU only).

Input is a render directory written by render_picnic_ground_blanket.py (frames/0001-0096.png,
masks_raw/, render_report.json, simulation_config.json, ...). The native state it replayed is
--simulation (a new solve) or, by default, the accepted state in the asset store. Needs numpy,
Pillow and ffmpeg/ffprobe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

CASE_DIR = Path(__file__).resolve().parents[1]
REPO = CASE_DIR.parents[2]
for _path in (CASE_DIR, REPO / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from pcve_media_contract import CONTRACT, require_times, require_video  # noqa: E402
from scene_inputs import CASES, TIMED_CASES, native  # noqa: E402
from tools.export_ground_truth import write as write_ground_truth  # noqa: E402

MASK_IDS = {1: "mandarin_orange", 2: "cotton_blanket", 3: "picnic_cup"}


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def merge_parts(out):
    """Combine the part reports of a case rendered as frame ranges (same device type and settings)."""
    parts = sorted(out.glob("render_report_*.json"))
    if (out / "render_report.json").is_file() or not parts:
        return
    reports = [json.loads(p.read_text()) for p in parts]
    varying = {"rendered_frames", "max_surface_replay_error_m"}
    first = {k: v for k, v in reports[0].items() if k not in varying}
    for report in reports[1:]:
        if {k: v for k, v in report.items() if k not in varying} != first:
            raise RuntimeError("Part renders of this case used different settings, inputs or appearance")
    frames = sorted(f for r in reports for f in r["rendered_frames"])
    if frames != list(range(1, 97)):
        raise RuntimeError(f"Part renders cover {len(frames)} frames, not 1-96 exactly once")
    merged = dict(reports[0], rendered_frames=frames, max_surface_replay_error_m=max(r["max_surface_replay_error_m"] for r in reports),
                  parts=[dict(file=p.name, frames=[min(r["rendered_frames"]), max(r["rendered_frames"])]) for p, r in zip(parts, reports)])
    audits = [json.loads(p.read_text()) for p in sorted(out.glob("evaluated_surface_audit_*.json"))]
    audit = dict(audits[0], evaluated_samples=sum(a["evaluated_samples"] for a in audits), max_error_m=max(a["max_error_m"] for a in audits))
    if any(a["status"] != "passed" for a in audits):
        raise RuntimeError("A part's evaluated cloth audit failed")
    provenance = [json.loads(p.read_text()) for p in sorted(out.glob("execution_provenance_*.json"))]
    if len({(p["device"], p["cycles_backend"], p["blender_version"], (p["gpus"] or "").split(",")[-1].strip()) for p in provenance}) != 1:
        raise RuntimeError("Part renders of this case ran on different device types")
    save(out / "render_report.json", merged)
    save(out / "evaluated_surface_audit.json", audit)
    save(out / "execution_provenance.json", dict(provenance[0], parts=provenance))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--render", type=Path, required=True)
    parser.add_argument("--case", choices=CASES + TIMED_CASES, required=True)
    parser.add_argument("--simulation", type=Path, help="Native state the render replayed (default: asset store; required for the timed edit)")
    args = parser.parse_args()
    if args.case in TIMED_CASES and args.simulation is None:
        parser.error("The timed edit has no accepted native state: pass the --simulation its render replayed")
    out = args.render.resolve()
    simulation = (args.simulation or native(args.case)).resolve()
    frames = out / "frames"
    expected = [frames / f"{i:04d}.png" for i in range(1, 97)]
    missing = [p.name for p in expected if not p.is_file()]
    if missing:
        raise RuntimeError(f"Missing rendered frames: {missing[:5]} ... ({len(missing)})")
    merge_parts(out)
    config = json.loads((out / "simulation_config.json").read_text())
    if config != json.loads((simulation / "simulation_config.json").read_text()) or config["case"] != args.case:
        raise RuntimeError("The render's native configuration differs from --simulation")
    render = json.loads((out / "render_report.json").read_text())
    if render["physics_cache_sha256"] != sha(simulation / "cache.npz"):
        raise RuntimeError("The render replayed a different native cache")
    if render["rendered_frames"] != list(range(1, 97)):
        # Frames may come from several render processes of the same case; each wrote its own
        # report. The caller merges them before packaging and records the ranges.
        raise RuntimeError("render_report.json must cover frames 1-96")
    if not render["evaluated_surface_verified"] or render["max_surface_replay_error_m"] > 2e-6 or render["surface_amplification"] != 1.0:
        raise RuntimeError("Cloth replay audit failed")
    require_times(render["native_sample_times_s"])
    video = out / "video.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "24", "-i", str(frames / "%04d.png"),
                    "-frames:v", "96", "-c:v", "libx264", "-threads", "8", "-preset", "slow", "-crf", "17",
                    "-pix_fmt", "yuv420p", "-r", "24", "-movflags", "+faststart", str(video)], check=True)
    shutil.copy2(expected[0], out / "first_frame.png")
    simulation_report = json.loads((out / "simulation_report.json").read_text())
    peak = max(1, min(96, int(simulation_report["peak_frame"])))
    shutil.copy2(frames / f"{peak:04d}.png", out / "hero.png")
    canvas = Image.new("RGB", (1280, 1116), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)
    for slot, frame in enumerate((1, 20, 40, 60, 80, 96)):
        image = Image.open(frames / f"{frame:04d}.png").convert("RGB").resize((640, 360), Image.Resampling.LANCZOS)
        x, y = slot % 2 * 640, slot // 2 * 372
        canvas.paste(image, (x, y))
        draw.text((x + 8, y + 360), f"frame {frame} | {(frame - 1) / 24:.3f} s", fill=(240, 240, 240))
    canvas.save(out / "contact_sheet.jpg", quality=93, subsampling=0)
    labels = []
    for frame in range(1, 97):
        label = np.zeros((720, 1280), np.uint8)
        for instance_id in MASK_IDS:
            path = out / "masks_raw" / f"id{instance_id}_{frame:04d}.png"
            if not path.is_file():
                raise RuntimeError(f"Missing visibility mask: {path}")
            label[np.asarray(Image.open(path).convert("L")) > 127] = instance_id
        labels.append(label)
    labels = np.stack(labels)
    if args.case == "delete_actor" and np.any(labels == 1):
        raise RuntimeError("The deleted orange is visible in the instance masks")
    if np.any(labels == 3):
        raise RuntimeError("The picnic-cup ADD object (in no published case) is visible")
    np.savez_compressed(out / "instance_masks.npz", masks=labels, frame_numbers=np.arange(1, 97, dtype=np.int32),
                        fps=np.array([24], np.int32), resolution=np.array([1280, 720], np.int32))
    gt = write_ground_truth(args.case, out / "ground_truth_transforms.json", simulation)
    require_times([frame["time_sec"] for frame in gt["frames"]])
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "stream=width,height,avg_frame_rate,nb_read_frames:format=duration", "-of", "json", str(video)]))
    stream = probe["streams"][0]
    if ([stream["width"], stream["height"]] != [1280, 720] or stream["avg_frame_rate"] != "24/1"
            or int(stream["nb_read_frames"]) != 96 or abs(float(probe["format"]["duration"]) - 4.0) > 1e-6):
        raise RuntimeError(f"Video contract failed: {probe}")
    media = require_video(video)
    save(out / "video_probe.json", probe)
    save(out / "media_contract_audit.json", dict(status="passed", contract_id=CONTRACT["contract_id"], actual_mp4_sample_table=media,
                                                 native_times_verified=True, gt_times_verified=True))
    save(out / "encoding_provenance.json", dict(host=socket.gethostname().split(".")[0], encoder="ffmpeg libx264 CRF 17 preset slow, yuv420p",
                                                frames="frames/0001.png-0096.png at 24 fps"))
    save(out / "visual_revision_audit.json", dict(status="passed", case=args.case, physics_cache_sha256=render["physics_cache_sha256"],
                                                  native_config_unchanged=True, masks_regenerated=True,
                                                  mask_ids={str(k): v for k, v in MASK_IDS.items() if k in np.unique(labels)},
                                                  frames=96, fps=24, resolution=[1280, 720], duration_seconds=4.0, video_sha256=sha(video)))
    products = []
    for path in sorted(out.rglob("*")):
        if not path.is_file() or any(part in {"frames", "masks_raw"} for part in path.relative_to(out).parts) or path.name == "artifact_manifest.json":
            continue
        products.append(dict(path=path.relative_to(out).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    save(out / "artifact_manifest.json", dict(schema_version=1, scene_id="picnic_ground_blanket", case=args.case, files=products))
    print("FINALIZED", args.case, sha(video), flush=True)


if __name__ == "__main__":
    main()
