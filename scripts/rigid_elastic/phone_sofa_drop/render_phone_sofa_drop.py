"""Build the current-look 24 FPS scene of a case and render its frames, or check its published video.

--stage scene:  Blender opens assets/scenes/phone_sofa_drop/packed/<case>/scene.blend, rebuilds the
                animation from the registered 0-4 s cache on the 24 FPS clock
                (appearance/retime_packed_scene.py), applies the current look
                (appearance/realism_look.py + appearance.json) and saves <out>/<case>/scene.blend
                plus scene_report.json. No rendering.
--stage frames: renders --frames (default 1-96) of <out>/<case>/scene.blend to <out>/<case>/frames/
                (appearance/render_frames.py); one Blender process per call.
--stage all:    scene, then all 96 frames.
--stage verify (default): check the case's video in the published suite (sha256 against
                scene_manifest.json, MP4 sample table).
Default --out-root: renders/phone_sofa_drop/render.
"""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END
from pathlib import Path
import argparse
import json
import os
import subprocess

from pcve_assets import ASSETS, asset
from tools.scene_common import (BLENDER_DEFAULT, CASE_IDS, RENDER_ROOT, SCENE_ASSETS, canonical_suite, catalog_id,
                                native_cache, sha256)

HERE = Path(__file__).resolve().parent


def blender_command(binary, blend, script, threads, script_args):
    command = [str(binary), "-b", str(blend), "--disable-autoexec", "--python-exit-code", "1"]
    if threads:
        command += ["-t", str(threads)]
    return command + ["--python", str(script), "--", *map(str, script_args)]


def run(command, log, gpu):
    env = dict(os.environ)
    if gpu is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as stream:
        stream.write("$ " + " ".join(command) + "\n")
        stream.flush()
        code = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
    if code:
        raise SystemExit(f"Blender failed ({code}); see {log}")


def build_scene(case, out, binary, threads):
    cache, _, _ = native_cache(case, "4s")
    case_dir = out / case
    args = ["--cache", cache, "--out", case_dir, "--no-render", "--save-blend", case_dir / "scene.blend",
            "--look", HERE / "appearance/appearance.json", "--assets", ASSETS]
    if case != "remove_cushion":
        args += ["--embedding", asset(f"{SCENE_ASSETS}/embedding/{case}/native_embedding.npz")]
    packed = asset(f"{SCENE_ASSETS}/packed/{case}/scene.blend")
    run(blender_command(binary, packed, HERE / "appearance/retime_packed_scene.py", threads, args),
        case_dir / "logs/scene.log", None)


def render_frames(case, out, frames, device, gpu, binary, threads):
    case_dir = out / case
    blend = case_dir / "scene.blend"
    if not blend.is_file():
        raise SystemExit(f"Build the scene first: {blend}")
    args = ["--out", case_dir, "--device", device, "--frames", *frames]
    run(blender_command(binary, blend, HERE / "appearance/render_frames.py", threads, args),
        case_dir / f"logs/frames_{min(frames):04d}_{max(frames):04d}.log", gpu)


def verify(case):
    from pcve_media_contract import probe_mp4
    suite, pointer = canonical_suite()
    video = suite / "cases" / catalog_id(case) / "video.mp4"
    digest = sha256(video)
    if digest != pointer[case]:
        raise SystemExit(f"{case}: published video differs from scene_manifest.json")
    return {"case_id": case, "video": str(video), "sha256": digest, "media": probe_mp4(video)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=CASE_IDS, default="source")
    parser.add_argument("--stage", choices=("verify", "scene", "frames", "all"), default="verify")
    parser.add_argument("--out", type=Path, default=RENDER_ROOT)
    parser.add_argument("--frames", type=int, nargs="+", help="24 FPS frames 1-96 (default: all)")
    parser.add_argument("--device", choices=("GPU", "CPU"), default="GPU")
    parser.add_argument("--gpu", help="CUDA device for --stage frames/all")
    parser.add_argument("--blender-bin", type=Path)
    parser.add_argument("--render-threads", type=int)
    args = parser.parse_args()
    binary = args.blender_bin or (BLENDER_DEFAULT if BLENDER_DEFAULT.is_file() else None)
    if args.stage == "verify":
        if args.frames:
            parser.error("--frames needs --stage frames")
        print(json.dumps(verify(args.case)))
        raise SystemExit()
    if binary is None:
        from pcve_assets import blender
        binary = blender()
    out = args.out.resolve()
    frames = args.frames or list(range(1, 97))
    if not all(1 <= f <= 96 for f in frames) or len(set(frames)) != len(frames):
        parser.error("--frames are distinct 24 FPS frame numbers 1-96")
    if args.stage in ("scene", "all"):
        build_scene(args.case, out, binary, args.render_threads)
    if args.stage in ("frames", "all"):
        render_frames(args.case, out, frames, args.device, args.gpu, binary, args.render_threads)
    print(json.dumps({"case_id": args.case, "stage": args.stage, "out": str(out / args.case)}))
