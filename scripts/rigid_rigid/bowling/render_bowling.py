"""Fixed-camera Cycles replay of actual bowling rigid-body positions and quaternions."""
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
from scene_config import signature
from look_bowling import architecture,asset_pin_mesh,ball_asset_finish,build_ball,idle_lane_racks,lighting,look_at,pin_visual_mesh

ROOT=Path(__file__).resolve().parents[3]

def dump(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")

def select_device(choice):
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

def geometry_signature(o):
    if o.type!="MESH":return None
    return signature({"vertices":[list(v.co) for v in o.data.vertices],"polygons":[list(p.vertices) for p in o.data.polygons],
        "materials":[m.name for m in o.data.materials],"material_indices":[p.material_index for p in o.data.polygons],
        "uv":[list(v.uv) for v in o.data.uv_layers.active.data] if o.data.uv_layers.active else [],
        "scale":list(o.scale)})

def shading_signatures(scene):
    def value(v):
        if v is None or isinstance(v,(str,bool,int,float)):return v
        try:return list(v)
        except TypeError:return str(v)
    mats={}
    for m in bpy.data.materials:
        if not m.use_nodes:continue
        nodes=[]
        for n in m.node_tree.nodes:
            row={"name":n.name,"type":n.bl_idname,"inputs":[[s.name,value(s.default_value)] for s in n.inputs if hasattr(s,"default_value")]}
            for prop in ["operation","blend_type","noise_dimensions","normalize","interpolation","extension"]:
                if hasattr(n,prop):row[prop]=value(getattr(n,prop))
            if hasattr(n,"color_ramp"):row["color_ramp"]=[[e.position,list(e.color)] for e in n.color_ramp.elements]
            if getattr(n,"image",None):row["image"]={"name":n.image.name,"colorspace":n.image.colorspace_settings.name,"sha256":hashlib.sha256(bytes(n.image.packed_file.data) if n.image.packed_file else Path(bpy.path.abspath(n.image.filepath)).read_bytes()).hexdigest()}
            nodes.append(row)
        mats[m.name]={"nodes":nodes,"links":[[l.from_node.name,l.from_socket.identifier,l.to_node.name,l.to_socket.identifier] for l in m.node_tree.links]}
    lights={o.name:{"location":list(o.location),"rotation":list(o.rotation_euler),"type":o.data.type,"energy":o.data.energy,"color":list(o.data.color),"size":getattr(o.data,"size",getattr(o.data,"shadow_soft_size",None)),"size_y":getattr(o.data,"size_y",None),**({"spot_size":o.data.spot_size,"spot_blend":o.data.spot_blend} if o.data.type=="SPOT" else {})} for o in scene.objects if o.type=="LIGHT"}
    return {"materials":signature(mats),"lighting":signature(lights),"material_manifest":mats}

def setup(cfg,physics,asset_root):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s=bpy.context.scene;s.unit_settings.system="METRIC";s.unit_settings.scale_length=1.
    rd=cfg["render"];s.render.engine="CYCLES";s.cycles.samples=rd["samples"];s.cycles.use_denoising=rd["denoising"]
    s.cycles.denoising_use_gpu=rd["denoising_use_gpu"];s.cycles.max_bounces=8;s.cycles.diffuse_bounces=4;s.cycles.glossy_bounces=4
    s.render.use_persistent_data=not rd["motion_blur_shutter_frames"]>0;s.render.resolution_x,s.render.resolution_y=rd["resolution"];s.render.resolution_percentage=100
    s.render.fps=rd["fps"];s.frame_start=1;s.frame_end=physics["frame_end"]
    s.view_settings.view_transform=rd["color_management"];s.view_settings.look="AgX - Medium High Contrast";s.view_settings.exposure=cfg["appearance"]["exposure_ev"]
    s.render.use_motion_blur=rd["motion_blur_shutter_frames"]>0;s.render.motion_blur_shutter=rd["motion_blur_shutter_frames"]
    s.render.image_settings.file_format="PNG";s.render.image_settings.color_mode="RGB";s.render.image_settings.compression=15
    root=Path(asset_root)/cfg['appearance']['asset_root_relative']
    objects={}
    if cfg['physics']['ball'].get('active',1):
        objects['B01']=build_ball(cfg)
        ball_asset_finish(objects['B01'],root)
    ledger=architecture(cfg,root);base_pin=asset_pin_mesh(cfg,root)
    for index,(name,active) in enumerate(zip(cfg['physics']['pins']['ids'],cfg['physics']['pins']['active'])):
        if active:
            o=bpy.data.objects.new(name,pin_visual_mesh(base_pin,index));bpy.context.collection.objects.link(o);o.rotation_mode='QUATERNION';objects[name]=o
    idle_lane_racks(cfg,base_pin)
    lighting(cfg)
    for sample in physics["trajectory_samples"]:
        frame=sample["time_sec"]*rd["fps"]+1
        for name,o in objects.items():
            st=sample["objects"][name];o.location=st["location"];x,y,z,w=st["quaternion_xyzw"];o.rotation_quaternion=(w,x,y,z)
            o.keyframe_insert(data_path="location",frame=frame);o.keyframe_insert(data_path="rotation_quaternion",frame=frame)
    for o in objects.values():
        for fc in o.animation_data.action.fcurves:
            for k in fc.keyframe_points:k.interpolation="LINEAR"
    camcfg=cfg["appearance"]["camera"];bpy.ops.object.camera_add(location=camcfg["location"])
    camera=bpy.context.object;camera.name="Fixed oblique view";look_at(camera,camcfg["target"])
    camera.data.shift_x=camcfg.get("shift_x",0.);camera.data.shift_y=camcfg.get("shift_y",0.);camera.data.lens=camcfg["lens_mm"];camera.data.sensor_width=camcfg["sensor_width_mm"];camera.data.clip_start=.01;camera.data.clip_end=80.
    camera.data.dof.use_dof=False;s.camera=camera;s.frame_set(1);bpy.context.view_layer.update()
    projections=[];pose_error=0.;occlusion=[]
    for f in physics["frames"]:
        s.frame_set(f["frame_index"]);entry={"frame":f["frame_index"],"objects":{}}
        for name,o in objects.items():
            expected=f["objects"][name];pose_error=max(pose_error,(o.location-Vector(expected["location"])).length)
            uv=[world_to_camera_view(s,camera,o.matrix_world@Vector(c)) for c in o.bound_box]
            center=world_to_camera_view(s,camera,o.location)
            entry["objects"][name]={"center_uv":[center.x,center.y],"bounds_uv":[min(u.x for u in uv),min(u.y for u in uv),max(u.x for u in uv),max(u.y for u in uv)],"depth_m":center.z}
        projections.append(entry)
        if f["frame_index"] in [1,15,16,17,18,21,26,37,49,73,96]:
            depsgraph=bpy.context.evaluated_depsgraph_get();fractions={}
            origin=camera.matrix_world.translation
            for name,o in objects.items():
                verts=list(o.data.vertices);stride=max(1,len(verts)//192);seen=0;total=0
                for vertex in verts[::stride]:
                    target=o.matrix_world@vertex.co;direction=target-origin
                    hit=s.ray_cast(depsgraph,origin,direction.normalized(),distance=direction.length+.001)
                    total+=1;seen+=bool(hit[0] and hit[4] is not None and hit[4].name==o.name)
                fractions[name]=seen/max(1,total)
            occlusion.append({"frame":f["frame_index"],"object_ray_visibility_fraction":fractions})
    s.frame_set(1)
    static={o.name:{"geometry":geometry_signature(o),"transform":[list(v) for v in o.matrix_world]} for o in s.objects if o.type=="MESH" and o.name not in objects}
    return s,objects,ledger,projections,pose_error,{"static":signature(static),"dynamic_visuals":{n:geometry_signature(o) for n,o in objects.items()}},occlusion

def main():
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out-dir",type=Path,required=True);p.add_argument("--physics-json",type=Path,required=True)
    p.add_argument("--asset-root",type=Path,default=ROOT/"assets");p.add_argument("--mode",choices=["animation","frames","prepare"],default="animation")
    p.add_argument("--keyframes",nargs="+",type=int);p.add_argument("--device",choices=["auto","cpu"],default="auto");p.add_argument("--appearance-json",type=Path)
    p.add_argument("--skip-existing",action="store_true");a=p.parse_args(argv)
    out=a.out_dir.resolve();out.mkdir(parents=True,exist_ok=True);physics=json.loads(a.physics_json.read_text());cfg=copy.deepcopy(physics["configuration"])
    if a.appearance_json:
        override=json.loads(a.appearance_json.read_text())
        if set(override)!={"appearance"}:raise ValueError("Appearance override must contain only appearance")
        cfg["appearance"]=override["appearance"]
    s,objects,ledger,projections,pose_error,geomsig,occlusion=setup(cfg,physics,a.asset_root);backend=select_device(a.device)
    shaders=shading_signatures(s)
    bpy.context.view_layer.update()
    metadata={"schema_version":2,**cfg,"configuration_sha256":signature(cfg),"blender_version":bpy.app.version_string,
      "physics_input":str(a.physics_json.resolve()),"physics_input_sha256":hashlib.sha256(a.physics_json.read_bytes()).hexdigest(),
      "render_backend":backend,"CUDA_VISIBLE_DEVICES":os.environ.get("CUDA_VISIBLE_DEVICES"),"dimension_ledger":ledger,
      "camera_is_static":True,"camera_keyframes":0,"playback_rate":1.,"motion_source":"unmodified actual PyBullet poses at 240 Hz",
      "max_replay_position_error_m":pose_error,"geometry_signatures":geomsig,"projected_objects":projections,
      "material_signature":shaders["materials"],"lighting_signature":shaders["lighting"],
      "occlusion_samples":occlusion,"occlusion_method":"Rays to approximately 192 actual mesh vertices per object; same-object first hit counts as visible; a diagnostic sampling metric, not a pixel mask",
      "invariant_appearance_sha256":signature(cfg["appearance"]),"invariant_simulation_quality_sha256":signature(cfg["simulation_quality"]),
      "denoiser":{"algorithm":s.cycles.denoiser,"use_gpu":s.cycles.denoising_use_gpu,"prefilter":s.cycles.denoising_prefilter,"passes":s.cycles.denoising_input_passes},
      "visual_dimensions_m":{n:list(o.dimensions) for n,o in objects.items()},"rigid_body_world_present":s.rigidbody_world is not None}
    dump(out/"scenario_metadata.json",metadata)
    dump(out/"material_manifest.json",shaders["material_manifest"])
    dump(out/"ground_truth_transforms.json",{"schema_version":2,"units":cfg["physics"]["units"],"fps":physics["fps"],"frames":physics["frames"],
      "contact_events":physics["contact_events"],"tilt_threshold_times_sec":physics["tilt_threshold_times_sec"],"camera":cfg["appearance"]["camera"],"playback_rate":1.})
    bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/"bowling.blend"))
    start=time.perf_counter();rendered=[]
    if a.mode!="prepare":
        dest=out/"frames";dest.mkdir(exist_ok=True)
        requested=list(range(1,physics["frame_end"]+1)) if a.mode=="animation" else (a.keyframes or [1,14,15,17,18,21,27,37,61,96])
        for frame in requested:
            path=dest/f"frame_{frame:04d}.png"
            if a.skip_existing and path.exists():continue
            s.frame_set(frame);s.render.filepath=str(path);bpy.ops.render.render(write_still=True);rendered.append(frame)
    render_sec=time.perf_counter()-start;encode_sec=0.
    if a.mode=="animation":
        start=time.perf_counter();subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-threads","4","-framerate",str(cfg["render"]["fps"]),"-start_number","1",
            "-i",str(out/"frames/frame_%04d.png"),"-frames:v",str(physics["frame_end"]),"-c:v","libx264","-preset","slow","-crf","17","-pix_fmt","yuv420p","-movflags","+faststart",str(out/"video.mp4")],check=True)
        encode_sec=time.perf_counter()-start
        subprocess.run([sys.executable,str(ROOT/"scripts/pcve_verify_video.py"),str(out/"video.mp4"),"--out",str(out/"video_validation.json"),"--resolution",*[str(x) for x in cfg["render"]["resolution"]],"--fps",str(cfg["render"]["fps"]),"--frames",str(physics["frame_end"])],check=True)
    dump(out/"render_report.json",{"render_sec":render_sec,"encode_sec":encode_sec,"backend":backend,"mode":a.mode,"rendered_frames":rendered})
    print(json.dumps({"render_sec":render_sec,"encode_sec":encode_sec,"backend":backend,"max_replay_position_error_m":pose_error}),flush=True)

if __name__=="__main__":main()
