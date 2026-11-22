"""Render frozen Genesis flag caches, encode and verify complete videos."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import numpy as np
from wind_flag_config import HERE, ROOT, choose_gpu, default_blender, digest, read_json, write_json


def verify_video(path, frames=96, fps=24, resolution=(1280,720)):
    result = json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-count_frames",
        "-show_entries","stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration","-of","json",str(path)],text=True))
    stream = result["streams"][0]
    if ((stream["width"],stream["height"]) != tuple(resolution) or int(stream["nb_read_frames"]) != frames
        or stream["r_frame_rate"] != f"{fps}/1" or stream["avg_frame_rate"] != f"{fps}/1"
        or abs(float(result["format"]["duration"])-frames/fps) > .001):
        raise RuntimeError(f"Video specification mismatch: {path}: {result}")
    subprocess.run(["ffmpeg","-v","error","-i",str(path),"-f","null","-"],check=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--simulation-dir",type=Path,required=True)
    p.add_argument("--out-dir",type=Path,required=True)
    p.add_argument("--asset-dir",type=Path,default=ROOT/"assets/blenderkit/un_ceremonial_flag")
    p.add_argument("--blender",default=default_blender())
    p.add_argument("--gpu",default="auto")
    p.add_argument("--frames",help="Optional diagnostic range; defaults to the complete cache")
    p.add_argument("--preview",action="store_true",help="640x360 diagnostic, not formal quality")
    p.add_argument("--skip-existing",action="store_true")
    p.add_argument("--dry-run",action="store_true")
    args = p.parse_args()
    cache = args.simulation_dir.resolve()/"genesis_flag_cache.npz"
    with np.load(cache) as data:
        count, fps = len(data["vertices"]),int(data["fps"])
    if fps != 24:
        p.error("The frozen look is validated at 24 fps only")
    start, end = map(int,(args.frames or f"1-{count}").split("-"))
    if not (1 <= start <= end <= count):
        p.error("Frame range outside the physical cache")
    resolution = (640,360) if args.preview else (1280,720)
    receipt_path = args.out_dir/"render_receipt.json"
    expected_cache = digest(cache)
    if args.skip_existing and receipt_path.is_file():
        receipt = read_json(receipt_path)
        assert receipt["cache_sha256"] == expected_cache
        assert receipt["video_sha256"] == digest(args.out_dir/"video.mp4")
        assert receipt["frame_range"] == [start,end] and receipt["resolution"] == list(resolution)
        verify_video(args.out_dir/"video.mp4",end-start+1,fps,resolution)
        print("SKIPPED_VERIFIED",args.out_dir)
        return
    if any((args.out_dir/name).exists() for name in ("scene.blend","video.mp4","frames","render.log")):
        raise RuntimeError("Refusing to overwrite existing or partial render: "+str(args.out_dir))
    command = [args.blender,"-b","-t","8","--python-exit-code","1","--python",str(HERE/"appearance/scene_wind_flag.py"),"--",
        "--cache",str(cache),"--scene",str(args.out_dir.resolve()/"scene.blend"),"--out",str(args.out_dir.resolve()),
        "--assets-root",str(args.asset_dir.resolve().parents[1]),"--environment",str(args.asset_dir.resolve()/"rooftop_environment.jpg"),
        "--flag-asset",str(args.asset_dir.resolve()/"un_flag_1k.blend"),"--flag-texture-dir",str(args.asset_dir.resolve()/"extracted_textures"),
        "--frames",f"{start}-{end}"]
    if args.preview:
        command.append("--preview")
    if args.dry_run:
        print(json.dumps(command))
        return
    gpu = choose_gpu(args.gpu)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    started = time.monotonic()
    with (args.out_dir/"render.log").open("xb") as log:
        subprocess.run(command,env=dict(os.environ,CUDA_VISIBLE_DEVICES=gpu),stdout=log,stderr=subprocess.STDOUT,check=True)
    render_seconds = time.monotonic()-started
    for i in range(start,end+1):
        if not (args.out_dir/"frames"/f"frame_{i:04d}.png").is_file():
            raise RuntimeError(f"Missing rendered frame {i}")
    encode_started = time.monotonic()
    subprocess.run(["ffmpeg","-y","-loglevel","error","-framerate",str(fps),"-start_number",str(start),
        "-i",str(args.out_dir/"frames/frame_%04d.png"),"-frames:v",str(end-start+1),"-c:v","libx264","-threads","4",
        "-preset","slow","-crf","17","-pix_fmt","yuv420p","-movflags","+faststart",str(args.out_dir/"video.mp4")],check=True)
    encode_seconds = time.monotonic()-encode_started
    verification_started = time.monotonic()
    probe = verify_video(args.out_dir/"video.mp4",end-start+1,fps,resolution)
    verification_seconds = time.monotonic()-verification_started
    write_json(receipt_path,{"cache_sha256":expected_cache,"video_sha256":digest(args.out_dir/"video.mp4"),
        "frame_range":[start,end],"resolution":list(resolution),"fps":fps,"render_samples":64,
        "diagnostic_partial_or_preview":bool(args.preview or count!=96 or start!=1 or end!=count),"gpu":gpu,
        "render_wall_seconds":render_seconds,"encode_wall_seconds":encode_seconds,
        "verification_wall_seconds":verification_seconds,"total_wall_seconds":time.monotonic()-started,"probe":probe})
    print("RENDERED_AND_DECODE_VERIFIED",args.out_dir)


if __name__ == "__main__":
    main()
