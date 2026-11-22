"""Fixed-camera Cycles replay of actual solver poses at 1x real time."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=="__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,"render")
# PCVE_UNIFIED_ENTRY_END
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parent/"appearance"))
from scene_config import signature,merge
from look_stair_ball_bounce import architecture,build_ball,lighting,look_at

ROOT=Path(__file__).resolve().parents[3]

def dump(path,data):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")

def device(choice):
    if choice=="cpu":bpy.context.scene.cycles.device="CPU";return "CPU"
    prefs=bpy.context.preferences.addons["cycles"].preferences
    for backend in ["OPTIX","CUDA","METAL"]:
        try:
            prefs.compute_device_type=backend;prefs.get_devices()
            selected=[d for d in prefs.devices if d.type==backend]
            if not selected:continue
            for d in prefs.devices:d.use=d in selected
            bpy.context.scene.cycles.device="GPU"
            return backend+": "+", ".join(d.name for d in selected)
        except Exception:continue
    bpy.context.scene.cycles.device="CPU";return "CPU"

def setup(cfg,physics,asset_root):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s=bpy.context.scene;s.unit_settings.system="METRIC";s.unit_settings.scale_length=1
    rd=cfg["render"]
    s.render.engine="CYCLES";s.cycles.samples=rd["samples"];s.cycles.use_denoising=rd["denoising"]
    s.cycles.denoising_use_gpu=rd["denoising_use_gpu"]
    s.cycles.max_bounces=8;s.cycles.diffuse_bounces=4;s.cycles.glossy_bounces=4
    s.render.use_persistent_data=True;s.render.resolution_x,s.render.resolution_y=rd["resolution"]
    s.render.resolution_percentage=100;s.render.fps=rd["fps"];s.frame_start=1;s.frame_end=physics["frame_end"]
    s.view_settings.view_transform=rd["color_management"];s.view_settings.look="AgX - Medium High Contrast";s.view_settings.exposure=0
    s.render.use_motion_blur=rd["motion_blur_shutter_frames"]>0
    s.render.motion_blur_shutter=rd["motion_blur_shutter_frames"]
    s.render.image_settings.file_format="PNG";s.render.image_settings.color_mode="RGB";s.render.image_settings.compression=15
    ledger=architecture(cfg,asset_root);ball=build_ball(cfg);lighting(cfg)
    # These keys are a dense cache of simulated poses, not authored bounce animation or solver inputs.
    for sample in physics["trajectory_samples"]:
        ball.location=sample["location"];x,y,z,w=sample["quaternion_xyzw"];ball.rotation_quaternion=(w,x,y,z)
        frame=sample["time_sec"]*rd["fps"]+1
        ball.keyframe_insert(data_path="location",frame=frame);ball.keyframe_insert(data_path="rotation_quaternion",frame=frame)
    for fc in ball.animation_data.action.fcurves:
        for key in fc.keyframe_points:key.interpolation="LINEAR"
    camcfg=cfg["appearance"]["camera"];bpy.ops.object.camera_add(location=camcfg["location"])
    camera=bpy.context.object;camera.name="Fixed oblique side view, no tracking";look_at(camera,camcfg["target"])
    camera.data.lens=camcfg["lens_mm"];camera.data.sensor_width=camcfg["sensor_width_mm"]
    camera.data.clip_start=.01;camera.data.clip_end=50;camera.data.dof.use_dof=False;s.camera=camera
    bpy.context.view_layer.update()
    projections=[]
    for frame in physics["frames"]:
        xyz=Vector(frame["location"]);uv=world_to_camera_view(s,camera,xyz)
        edge=world_to_camera_view(s,camera,xyz+camera.matrix_world.to_quaternion()@Vector((cfg["physics"]["ball"]["radius_m"],0,0)))
        projections.append({"frame":frame["frame_index"],"uv":[uv.x,uv.y],"diameter_px":abs(edge.x-uv.x)*2*rd["resolution"][0]})
    s.frame_set(1)
    return s,ball,ledger,projections

def main():
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir",type=Path,required=True);p.add_argument("--physics-json",type=Path,required=True)
    p.add_argument("--asset-root",type=Path,default=ROOT/"assets")
    p.add_argument("--mode",choices=["animation","frames","prepare"],default="animation")
    p.add_argument("--keyframes",nargs="+",type=int);p.add_argument("--device",choices=["auto","cpu"],default="auto")
    p.add_argument("--appearance-json",type=Path);p.add_argument("--skip-existing",action="store_true")
    args=p.parse_args(argv);out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=json.loads(args.physics_json.read_text());cfg=copy.deepcopy(physics["configuration"])
    if args.appearance_json:
        override=json.loads(args.appearance_json.read_text())
        if set(override)!={"appearance"}:raise ValueError("Only an appearance override is accepted.")
        cfg=merge(cfg,override)
    s,ball,ledger,projections=setup(cfg,physics,args.asset_root.expanduser().resolve());backend=device(args.device)
    metadata={"schema_version":1,**cfg,"configuration_sha256":signature(cfg),"blender_version":bpy.app.version_string,
        "physics_input":str(args.physics_json.resolve()),"physics_input_sha256":hashlib.sha256(args.physics_json.read_bytes()).hexdigest(),
        "render_backend":backend,"CUDA_VISIBLE_DEVICES":os.environ.get("CUDA_VISIBLE_DEVICES"),"dimension_ledger":ledger,
        "denoiser":{"algorithm":s.cycles.denoiser,"use_gpu":s.cycles.denoising_use_gpu,"prefilter":s.cycles.denoising_prefilter,"input_passes":s.cycles.denoising_input_passes},
        "camera_is_static":True,"camera_keyframes":0,"playback_rate":1.0,
        "animation_source":"unmodified 240 Hz sampled PyBullet pose cache; no authored trajectories", "projected_ball":projections,
        "minimum_ball_diameter_px":min(v["diameter_px"] for v in projections),
        "all_ball_centers_in_frame":all(.02<v["uv"][0]<.98 and .02<v["uv"][1]<.98 for v in projections),
        "all_ball_silhouettes_in_frame":all(v["diameter_px"]/2+2<v["uv"][0]*cfg["render"]["resolution"][0]<cfg["render"]["resolution"][0]-v["diameter_px"]/2-2 and v["diameter_px"]/2+2<v["uv"][1]*cfg["render"]["resolution"][1]<cfg["render"]["resolution"][1]-v["diameter_px"]/2-2 for v in projections),
        "invariant_appearance_sha256":signature(cfg["appearance"]),"invariant_simulation_quality_sha256":signature(cfg["simulation_quality"])}
    dump(out/"scenario_metadata.json",metadata)
    dump(out/"ground_truth_transforms.json",{"schema_version":1,"units":cfg["physics"]["units"],
        "objects":{"B01":cfg["physics"]["ball"]},"fps":physics["fps"],
        "frames":[{"frame_index":f["frame_index"],"time_sec":f["time_sec"],"objects":{"B01":f}} for f in physics["frames"]],
        "contact_events":physics["contact_events"],"camera":cfg["appearance"]["camera"],"playback_rate":1.0})
    bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/"stair_ball_bounce.blend"))
    begin=time.perf_counter();rendered=[]
    if args.mode!="prepare":
        frames=out/"frames";frames.mkdir(exist_ok=True)
        requested=args.keyframes if args.mode=="frames" else list(range(1,physics["frame_end"]+1))
        requested=requested or [1,5,13,23,33,43,53,73,96]
        for frame in requested:
            dest=frames/f"frame_{frame:04d}.png"
            if args.skip_existing and dest.is_file():continue
            s.frame_set(frame);s.render.filepath=str(dest);bpy.ops.render.render(write_still=True);rendered.append(frame)
    render_sec=time.perf_counter()-begin;encode_sec=0
    if args.mode=="animation":
        begin=time.perf_counter()
        subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-framerate",str(cfg["render"]["fps"]),"-start_number","1",
            "-i",str(out/"frames/frame_%04d.png"),"-frames:v",str(physics["frame_end"]),"-c:v","libx264","-preset","slow","-crf","17",
            "-pix_fmt","yuv420p","-movflags","+faststart",str(out/"video.mp4")],check=True)
        encode_sec=time.perf_counter()-begin
        subprocess.run([sys.executable,str(ROOT/"scripts/pcve_verify_video.py"),str(out/"video.mp4"),"--out",str(out/"video_validation.json"),
            "--resolution",*[str(x) for x in cfg["render"]["resolution"]],"--fps",str(cfg["render"]["fps"]),"--frames",str(physics["frame_end"])],check=True)
    dump(out/"render_report.json",{"render_sec":render_sec,"encode_sec":encode_sec,"backend":backend,"mode":args.mode,"rendered_frames":rendered})
    print(json.dumps({"render_sec":render_sec,"encode_sec":encode_sec,"backend":backend,"minimum_ball_diameter_px":metadata["minimum_ball_diameter_px"],
        "all_ball_centers_in_frame":metadata["all_ball_centers_in_frame"]}),flush=True)

if __name__=="__main__":main()
