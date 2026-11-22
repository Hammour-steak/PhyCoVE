"""Render a completed physical case, encode it and verify the entire video."""
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
from balloon_config import (HERE, STEM, CAMERA, SAMPLES, KITCHEN,
    default_blender, choose_gpu, digest, read_json, write_json, files_manifest, verify_files, run)

def verify_video(path):
    probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-count_frames",
        "-show_entries","stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration","-of","json",str(path)],text=True))
    stream=probe["streams"][0]
    if (stream["width"],stream["height"],stream["r_frame_rate"],int(stream["nb_read_frames"]))!=(1280,720,"24/1",96):
        raise RuntimeError("Video specification mismatch: "+str(path))
    if abs(float(probe["format"]["duration"])-4.)>.001 or stream["avg_frame_rate"]!="24/1":
        raise RuntimeError("Video duration/frame-rate mismatch: "+str(path))
    subprocess.run(["ffmpeg","-v","error","-i",str(path),"-f","null","-"],check=True)
    return probe

def render_command(case,blender,kitchen):
    sim=read_json(case/"sim/membrane.json")["args"]
    if not sim["open_mouth"]:
        raise ValueError("The accepted kitchen pipeline requires an open mouth")
    command=[blender,"-b","--python-exit-code","1","--python",str(HERE/"appearance"/("scene_"+STEM+".py")),"--",
        "--mode","pour","--surface-dir",str(case/"surfaces"),"--out",str(case/"render"),
        "--scene",str(case/"render/scene.blend"),"--frames","1-96","--camera",CAMERA,"--samples",str(SAMPLES),
        "--flow-l-min",str(sim["flow_l_min"]),"--pour-start-frame",str(sim["pump_start_frame"]),"--kitchen",str(kitchen)]
    if sim["timed_edits_json"] is not None:
        timed=case/"timed_edits.json"
        if not timed.is_file():
            raise RuntimeError("Missing case-local timed schedule: "+str(timed))
        if read_json(Path(sim["timed_edits_json"]))!=read_json(timed):
            raise RuntimeError("Simulation/render timed schedules differ")
        command += ["--timed-edits-json",str(timed)]
    return command

def render_case(case,blender,kitchen,gpu="auto",skip_existing=False,dry_run=False):
    case=Path(case).resolve()
    kitchen=Path(kitchen).resolve()
    command=render_command(case,blender,kitchen)
    if dry_run:
        return {"command":command,"video":str(case/"video.mp4"),"resolution":[1280,720],"fps":24,"frames":96,"samples":96}
    with np.load(case/"surfaces/balloon_visual.npz") as cache:
        if len(cache["outer_vertices"])!=96:
            raise RuntimeError("Formal rendering requires exactly 96 physical frames")
    surface=read_json(case/"surfaces/surface_report.json")
    if [r["frame"] for r in surface["water"]]!=list(range(1,97)) or surface["frames_with_water_outside_latex"]:
        raise RuntimeError("Surfaces are incomplete or containment failed")
    inputs={"simulation_sha256":digest(case/"sim/membrane.npz"),
        "simulation_config_sha256":digest(case/"sim/membrane.json"),"surface_files":files_manifest(case/"surfaces"),
        "kitchen_sha256":digest(kitchen),"camera":CAMERA,"samples":SAMPLES}
    receipt=case/"render_receipt.json"
    if receipt.exists() and skip_existing:
        previous=read_json(receipt)
        if previous["inputs"]!=inputs or previous["video_sha256"]!=digest(case/"video.mp4"):
            raise RuntimeError("Existing render does not match the inputs")
        verify_files(case/"render",previous["render_files"])
        verify_video(case/"video.mp4")
        return previous
    if any((case/name).exists() for name in ("render","video.mp4","render.log","encode.log","render_receipt.json")):
        raise RuntimeError("Refusing to overwrite existing or partial render: "+str(case))
    gpu_id=choose_gpu(gpu)
    timings={}
    timings["render"]=run(command,case/"render.log",env=dict(os.environ,CUDA_VISIBLE_DEVICES=gpu_id))
    for frame in range(1,97):
        if not (case/"render/frames"/f"frame_{frame:04d}.png").is_file():
            raise RuntimeError(f"Missing rendered frame {frame}")
    timings["encode"]=run(["ffmpeg","-n","-loglevel","error","-framerate","24","-i",
        case/"render/frames/frame_%04d.png","-c:v","libx264","-pix_fmt","yuv420p","-crf","18",case/"video.mp4"],case/"encode.log")
    started=time.monotonic()
    probe=verify_video(case/"video.mp4")
    timings["verify"]=time.monotonic()-started
    result={"inputs":inputs,"video_sha256":digest(case/"video.mp4"),"probe":probe,"gpu":gpu_id,
        "seconds":timings,"render_files":files_manifest(case/"render"),"visual_review_required":True}
    write_json(receipt,result)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case-dir",type=Path,required=True,help="contains sim/ and surfaces/")
    p.add_argument("--blender",default=default_blender())
    p.add_argument("--kitchen",type=Path,default=KITCHEN)
    p.add_argument("--gpu",default="auto")
    p.add_argument("--skip-existing",action="store_true")
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    result=render_case(args.case_dir,args.blender,args.kitchen,args.gpu,args.skip_existing,args.dry_run)
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
