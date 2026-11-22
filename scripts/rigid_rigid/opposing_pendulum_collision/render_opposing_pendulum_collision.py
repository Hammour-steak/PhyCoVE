"""Fixed-camera Cycles render of unmodified 240 Hz solver poses at real time."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=="__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,"render")
# PCVE_UNIFIED_ENTRY_END
import argparse
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
from scene_config import signature,length_ledger
import look_opposing_pendulum_collision as look

ROOT=Path(__file__).resolve().parents[3]
def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")

def device(choice):
    if choice=="cpu":bpy.context.scene.cycles.device="CPU";return "CPU"
    prefs=bpy.context.preferences.addons["cycles"].preferences
    for backend in ["OPTIX","CUDA","METAL"]:
        try:
            prefs.compute_device_type=backend;prefs.get_devices();selected=[d for d in prefs.devices if d.type==backend]
            if not selected:continue
            for d in prefs.devices:d.use=d in selected
            bpy.context.scene.cycles.device="GPU";return backend+": "+", ".join(d.name for d in selected)
        except Exception:continue
    bpy.context.scene.cycles.device="CPU";return "CPU"

def vignette(s,strength):
    """Radial lens fall-off applied to scene-linear light before the view transform; geometry untouched."""
    s.use_nodes=True;tree=s.node_tree;n,l=tree.nodes,tree.links
    for node in list(n):n.remove(node)
    rl=n.new("CompositorNodeRLayers");comp=n.new("CompositorNodeComposite")
    ellipse=n.new("CompositorNodeEllipseMask");ellipse.width=1.25;ellipse.height=1.25
    blur=n.new("CompositorNodeBlur");blur.filter_type="FAST_GAUSS";blur.use_relative=True;blur.factor_x=blur.factor_y=45.
    l.new(ellipse.outputs["Mask"],blur.inputs["Image"])
    falloff=n.new("CompositorNodeMapRange");falloff.inputs["To Min"].default_value=1.-strength;l.new(blur.outputs["Image"],falloff.inputs["Value"])
    mix=n.new("CompositorNodeMixRGB");mix.blend_type="MULTIPLY";l.new(rl.outputs["Image"],mix.inputs[1]);l.new(falloff.outputs["Value"],mix.inputs[2])
    l.new(mix.outputs["Image"],comp.inputs["Image"])

def setup(cfg,physics,assets):
    bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene;rd=cfg["render"]
    s.unit_settings.system="METRIC";s.unit_settings.scale_length=1.
    s.render.engine="CYCLES";s.cycles.samples=rd["samples"];s.cycles.use_denoising=rd["denoising"];s.cycles.denoising_use_gpu=rd["denoising_use_gpu"]
    s.cycles.max_bounces=8;s.cycles.diffuse_bounces=4;s.cycles.glossy_bounces=4
    if "denoiser" in rd:s.cycles.denoiser=rd["denoiser"]
    if "adaptive_threshold" in rd:s.cycles.use_adaptive_sampling=True;s.cycles.adaptive_threshold=rd["adaptive_threshold"]
    s.render.resolution_x,s.render.resolution_y=rd["resolution"];s.render.resolution_percentage=100;s.render.fps=rd["fps"]
    s.frame_start=1;s.frame_end=physics["frame_end"];s.view_settings.view_transform=rd["color_management"];s.view_settings.look="AgX - Medium High Contrast"
    s.view_settings.exposure=rd.get("exposure_ev",0.)
    if "white_balance_k" in rd:s.view_settings.use_white_balance=True;s.view_settings.white_balance_temperature=rd["white_balance_k"]
    s.render.use_motion_blur=rd["motion_blur_shutter_frames"]>0;s.render.motion_blur_shutter=rd["motion_blur_shutter_frames"]
    # Blender 4.3: with motion blur on, persistent data drops objects that come to rest in later frames.
    s.render.use_persistent_data=not s.render.use_motion_blur
    s.render.image_settings.file_format="PNG";s.render.image_settings.color_mode="RGB";s.render.image_settings.compression=15
    ledger=look.architecture(cfg,assets);balls=look.build_balls(cfg);ropes,rope_reports=look.build_ropes(cfg,physics);sky=look.lighting(cfg,assets)
    ledger["ropes"]=rope_reports;ledger["length_ledger"]=length_ledger(cfg);ledger["lighting"]=sky
    # Dense cache keys are solved output only, and never feed the dynamics.
    for sample in physics["trajectory_samples"]:
        frame=sample["time_sec"]*rd["fps"]+1
        for name,b in sample["objects"].items():
            obj=balls[name];obj.location=b["location"];x,y,z,w=b["quaternion_xyzw"];obj.rotation_quaternion=(w,x,y,z)
            obj.keyframe_insert(data_path="location",frame=frame);obj.keyframe_insert(data_path="rotation_quaternion",frame=frame)
    for ball in balls.values():
        for fc in ball.animation_data.action.fcurves:
            for key in fc.keyframe_points:key.interpolation="LINEAR"
    camera_cfg=cfg["appearance"]["camera"];bpy.ops.object.camera_add(location=camera_cfg["location"])
    cam=bpy.context.object;cam.name="Fixed oblique side camera";look.look_at(cam,camera_cfg["target"])
    cam.data.lens=camera_cfg["lens_mm"];cam.data.sensor_width=camera_cfg["sensor_width_mm"];cam.data.clip_start=.01;cam.data.clip_end=30;s.camera=cam
    dof=rd.get("depth_of_field");cam.data.dof.use_dof=bool(dof)
    if dof:
        # Focus distance is measured along the optical axis to the swing plane.
        bpy.context.view_layer.update();axis=cam.matrix_world.to_quaternion()@Vector((0.,0.,-1.))
        cam.data.dof.focus_distance=(Vector(dof["focus_point_m"])-cam.location).dot(axis);cam.data.dof.aperture_fstop=dof["fstop"]
    if rd.get("vignette_strength",0.)>0:vignette(s,rd["vignette_strength"])
    bpy.context.view_layer.update();projections=[]
    for f in physics["frames"]:
        row={"frame_index":f["frame_index"],"objects":{}}
        for name,b in f["objects"].items():
            xyz=Vector(b["location"]);uv=world_to_camera_view(s,cam,xyz);r=cfg["physics"]["balls"][name]["radius_m"]
            edge=world_to_camera_view(s,cam,xyz+cam.matrix_world.to_quaternion()@Vector((r,0.,0.)))
            row["objects"][name]={"uv":[uv.x,uv.y],"diameter_px":abs(edge.x-uv.x)*2*rd["resolution"][0]}
        projections.append(row)
    s.frame_set(1);return s,balls,ledger,projections

def main():
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--out-dir",type=Path,required=True);ap.add_argument("--physics-json",type=Path,required=True)
    ap.add_argument("--asset-root",type=Path,default=ROOT/"assets");ap.add_argument("--mode",choices=["animation","frames","prepare"],default="animation")
    ap.add_argument("--keyframes",nargs="+",type=int);ap.add_argument("--device",choices=["auto","cpu"],default="auto");ap.add_argument("--skip-existing",action="store_true")
    a=ap.parse_args(argv);out=a.out_dir.resolve();out.mkdir(parents=True,exist_ok=True);physics=json.loads(a.physics_json.read_text());cfg=physics["configuration"]
    s,balls,ledger,projections=setup(cfg,physics,a.asset_root);backend=device(a.device)
    projected=[b for f in projections for b in f["objects"].values()];width,height=cfg["render"]["resolution"]
    metadata={"schema_version":1,**cfg,"configuration_sha256":signature(cfg),"blender_version":bpy.app.version_string,"render_backend":backend,
        "physics_input":str(a.physics_json.resolve()),"physics_input_sha256":hashlib.sha256(a.physics_json.read_bytes()).hexdigest(),
        "CUDA_VISIBLE_DEVICES":os.environ.get("CUDA_VISIBLE_DEVICES"),"dimension_ledger":ledger,"camera_is_static":True,"camera_keyframes":0,
        "playback_rate":1.,"animation_source":"Unmodified solved 240 Hz poses; no authored forces, trajectories or spin",
        "projected_balls":projections,"minimum_ball_diameter_px":min(b["diameter_px"] for b in projected),
        "all_ball_silhouettes_in_frame":all(b["diameter_px"]/2+2<b["uv"][0]*width<width-b["diameter_px"]/2-2 and
            b["diameter_px"]/2+2<b["uv"][1]*height<height-b["diameter_px"]/2-2 for b in projected),
        "invariant_appearance_sha256":signature(cfg["appearance"]),"invariant_simulation_quality_sha256":signature(cfg["simulation_quality"])}
    dump(out/"scenario_metadata.json",metadata)
    dump(out/"ground_truth_transforms.json",{"schema_version":1,"units":cfg["physics"]["units"],"objects":cfg["physics"]["balls"],
        "fps":physics["fps"],"frames":physics["frames"],"contact_events":physics["contact_events"],"length_ledger":physics["length_ledger"],"camera":cfg["appearance"]["camera"],"playback_rate":1.})
    bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/"opposing_pendulum_collision.blend"))
    begin=time.perf_counter();rendered=[]
    if a.mode!="prepare":
        (out/"frames").mkdir(exist_ok=True)
        requested=(a.keyframes or [1,7,10,11,15,20,25,30,49,73,96]) if a.mode=="frames" else range(1,physics["frame_end"]+1)
        for frame in requested:
            dest=out/"frames"/f"frame_{frame:04d}.png"
            if a.skip_existing and dest.is_file():continue
            s.frame_set(frame);s.render.filepath=str(dest);bpy.ops.render.render(write_still=True);rendered.append(frame)
    render_sec=time.perf_counter()-begin;encode_sec=0
    if a.mode=="animation":
        begin=time.perf_counter();subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-framerate",str(cfg["render"]["fps"]),
            "-start_number","1","-i",str(out/"frames/frame_%04d.png"),"-frames:v",str(physics["frame_end"]),"-c:v","libx264","-threads","6","-preset","slow","-crf","17",
            "-pix_fmt","yuv420p","-movflags","+faststart",str(out/"video.mp4")],check=True);encode_sec=time.perf_counter()-begin
    dump(out/"render_report.json",{"render_sec":render_sec,"encode_sec":encode_sec,"backend":backend,"mode":a.mode,"rendered_frames":rendered})
    print(json.dumps({"render_sec":render_sec,"encode_sec":encode_sec,"backend":backend,"minimum_ball_diameter_px":metadata["minimum_ball_diameter_px"],
        "all_ball_silhouettes_in_frame":metadata["all_ball_silhouettes_in_frame"]}),flush=True)

if __name__=="__main__":main()
