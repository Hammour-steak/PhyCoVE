"""Render the solved rigid-stone poses with a fixed camera, at normal speed."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
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
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(ROOT/"scripts"))
from scene_config import SCENE, signature
from pcve_assets import ASSETS
from appearance.look_curling_collision import rink, build_stone, lighting, look_at, camera_finish

def dump(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")

def setup(physics,choice,threads,asset_root=ASSETS):
    cfg = physics["configuration"]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene,rd = bpy.context.scene,cfg["render"]
    scene.unit_settings.system,scene.unit_settings.scale_length = "METRIC",1
    scene.render.engine = "CYCLES"
    scene.cycles.samples = rd["samples"]
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = rd["adaptive_threshold"]
    scene.cycles.use_denoising = rd["denoising"]
    scene.cycles.denoising_use_gpu = False
    scene.cycles.max_bounces = rd["path_bounces"]["total"]
    scene.cycles.diffuse_bounces = rd["path_bounces"]["diffuse"]
    scene.cycles.glossy_bounces = rd["path_bounces"]["glossy"]
    scene.cycles.transmission_bounces = rd["path_bounces"]["transmission"]
    scene.cycles.seed = cfg["appearance"]["seed"]
    scene.cycles.use_animated_seed = False
    scene.cycles.device,backend = "CPU","CPU"
    if choice == "gpu":
        if not os.environ.get("CUDA_VISIBLE_DEVICES"):
            raise ValueError("GPU rendering requires an explicitly selected idle --gpu")
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        devices = [d for d in prefs.devices if d.type == "OPTIX"]
        if not devices:
            raise RuntimeError("No selected OptiX device")
        for device in prefs.devices:
            device.use = device in devices
        scene.cycles.device,backend = "GPU","OPTIX: "+", ".join(d.name for d in devices)
    scene.render.threads_mode,scene.render.threads = "FIXED",threads
    scene.render.resolution_x,scene.render.resolution_y = rd["resolution"]
    scene.render.resolution_percentage,scene.render.fps,scene.render.fps_base = 100,rd["fps"],1
    scene.frame_start,scene.frame_end = 1,rd["total_frames"]
    scene.view_settings.view_transform = rd["color_management"]
    scene.view_settings.look,scene.view_settings.exposure = rd["look"],rd["exposure"]
    scene.render.use_motion_blur = rd["motion_blur_shutter_frames"]>0
    scene.render.motion_blur_shutter = rd["motion_blur_shutter_frames"]
    # Blender 4.3: with motion blur, persistent data drops objects that have come to rest in later frames.
    scene.render.use_persistent_data = not scene.render.use_motion_blur
    scene.render.image_settings.file_format,scene.render.image_settings.color_mode = "PNG","RGB"
    scene.render.image_settings.compression = 15
    ledger = rink(cfg)
    roots = {name:build_stone(cfg,i,asset_root) for i,name in enumerate(cfg["physics"]["object_ids"])}
    visual_dimensions = {name:list(root["visual_asset_dimensions_m"]) for name,root in roots.items()}
    for key in ["granite_height_m","stone_total_height_m","running_band_radius_m","visual_collision_proxy"]:
        ledger.pop(key,None)
    ledger.update(visual_asset_dimensions_m=visual_dimensions,
        stone_geometry_source="Handle and cap from the registered Sketchfab model by FilinMX; granite body lathed from its measured profile",
        collision_proxy_maximum_radius_m=cfg["physics"]["radius_m"],
        prescribed_orientation="All imported asset orientations and root quaternions are constant")
    lighting(cfg)
    c = cfg["appearance"]["camera"]
    data = bpy.data.cameras.new("Fixed low oblique camera")
    camera = bpy.data.objects.new(data.name,data)
    bpy.context.collection.objects.link(camera)
    camera.location = c["position_m"]
    look_at(camera,c["target_m"])
    data.lens,data.sensor_width = c["lens_mm"],c["sensor_width_mm"]
    data.clip_start,data.clip_end,data.dof.use_dof = .025,150,True
    data.dof.aperture_fstop = c["dof_fstop"]
    data.dof.focus_distance = c["focus_distance_m"]
    scene.camera = camera
    finish = camera_finish(scene,cfg)
    for sample in physics["trajectory_samples"]:
        frame = 1+sample["time_sec"]*rd["fps"]
        for name,body in sample["bodies"].items():
            obj = roots[name]
            obj.location = body["location"]
            x,y,z,w = body["quaternion_xyzw"]
            obj.rotation_quaternion = (w,x,y,z)
            obj.keyframe_insert(data_path="location",frame=frame,group="Solved rigid translation")
    for obj in roots.values():
        for curve in obj.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    gt,minimum_width = [],float("inf")
    for frame in physics["frames"]:
        scene.frame_set(frame["frame_index"])
        row = {"frame_index":frame["frame_index"],"time_sec":frame["time_sec"],"bodies":{}}
        for name,root in roots.items():
            corners = [world_to_camera_view(scene,camera,child.matrix_world@Vector(corner))
                for child in root.children if child.type in ["MESH","CURVE"] for corner in child.bound_box]
            bounds = [min(p.x for p in corners),min(p.y for p in corners),max(p.x for p in corners),max(p.y for p in corners)]
            center = world_to_camera_view(scene,camera,Vector(frame["bodies"][name]["location"]))
            contact = world_to_camera_view(scene,camera,Vector((*frame["bodies"][name]["location"][:2],0)))
            width = (bounds[2]-bounds[0])*rd["resolution"][0]
            minimum_width = min(width,minimum_width)
            row["bodies"][name] = {**frame["bodies"][name],"center_px":[center.x*1280,(1-center.y)*720],
                "bounds_normalized_bottom_left":bounds,"width_px":width,
                "floor_contact_px":[contact.x*1280,(1-contact.y)*720],
                "complete_object_in_frame":min(bounds[:2])>=0.0 and max(bounds[2:])<=1.0,
                "contact_in_frame":.02<contact.x<.98 and .02<contact.y<.98}
        gt.append(row)
    animated = set(roots.values())
    static = [{"name":o.name,"matrix_world":[list(row) for row in o.matrix_world]}
        for o in sorted(scene.objects,key=lambda o:o.name) if o not in animated and o.parent not in animated]
    metadata = {"scene":SCENE,"blender_version":bpy.app.version_string,"backend":backend,
        "configuration":cfg,"configuration_sha256":physics["configuration_sha256"],"scale_ledger":ledger,
        "fixed_camera":not bool(camera.animation_data),"static_background_sha256":signature(static),
        "animated_object_ids":list(roots),"only_animated_root_dof":"location.x; orientations constant",
        "all_stones_in_frame":all(b["complete_object_in_frame"] for f in gt for b in f["bodies"].values()),
        "all_ground_contacts_in_frame":all(b["contact_in_frame"] for f in gt for b in f["bodies"].values()),
        "minimum_stone_width_px":minimum_width,
        "shared_3d_lighting_shadows_and_occlusion":True,"depth_of_field":True,"camera_optics":{"fstop":data.dof.aperture_fstop,"focus_distance_m":data.dof.focus_distance},
        "appearance_preset":cfg["appearance"]["preset"],"camera_finish":finish,
        "persistent_data":scene.render.use_persistent_data,
        "asset_dependencies":[cfg["appearance"]["stone_asset"]],"playback_rate":1.0}
    if not metadata["all_stones_in_frame"] or not metadata["all_ground_contacts_in_frame"]:
        raise RuntimeError("Camera clips a stone or contact point")
    scene.frame_set(1)
    return scene,metadata,gt

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-json",type=Path,required=True)
    parser.add_argument("--out-dir",type=Path,required=True)
    parser.add_argument("--asset-root",type=Path,default=ASSETS)
    parser.add_argument("--mode",choices=["prepare","frames","animation"],default="animation")
    parser.add_argument("--keyframes",type=int,nargs="+")
    parser.add_argument("--device",choices=["cpu","gpu"],default="cpu")
    parser.add_argument("--threads-native",type=int,default=64)
    parser.add_argument("--skip-existing",action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:])
    physics = json.loads(args.physics_json.read_text())
    out,cfg = args.out_dir.expanduser().resolve(),physics["configuration"]
    out.mkdir(parents=True,exist_ok=True)
    previous = out/"scenario_metadata.json"
    if previous.exists() and json.loads(previous.read_text())["configuration_sha256"]!=physics["configuration_sha256"]:
        raise ValueError("Changed inputs require a fresh output directory")
    begin = time.perf_counter()
    scene,metadata,gt = setup(physics,args.device,args.threads_native,args.asset_root)
    setup_seconds = time.perf_counter()-begin
    dump(previous,metadata); dump(out/"ground_truth_transforms.json",gt); dump(out/"settings.json",cfg)
    scene["pcve_scene_id"],scene["pcve_configuration_sha256"] = SCENE,physics["configuration_sha256"]
    scene["physics_cache_sha256"] = hashlib.sha256(args.physics_json.read_bytes()).hexdigest()
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(out/(SCENE+".blend")))
    times,frames = {},out/"frames"
    if args.mode!="prepare":
        frames.mkdir(exist_ok=True)
        requested = args.keyframes or [1,14,15,24,35,36,60,96]
        if args.mode=="animation":
            requested = list(range(1,97))
        for index in requested:
            if not 1<=index<=96:
                raise ValueError(index)
            dest = frames/f"frame_{index:04d}.png"
            if dest.exists():
                if args.skip_existing:
                    continue
                raise FileExistsError(dest)
            begin = time.perf_counter()
            scene.frame_set(index)
            scene.render.filepath = str(dest)
            bpy.ops.render.render(write_still=True)
            times[str(index)] = time.perf_counter()-begin
            dump(out/f"render_progress_{args.mode}.json",{"frames_completed":list(times),"frame_seconds":times})
            print(f"PCVE_FRAME {index} {times[str(index)]:.3f}s",flush=True)
    encode_seconds = 0.0
    if args.mode=="animation":
        if not all((frames/f"frame_{i:04d}.png").is_file() for i in range(1,97)):
            raise RuntimeError("Incomplete frame sequence")
        begin = time.perf_counter()
        encoding = cfg["render"]["encoding"]
        subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-framerate","24","-start_number","1",
            "-i",str(frames/"frame_%04d.png"),"-frames:v","96","-an","-c:v",encoding["codec"],"-preset","slow",
            "-crf",str(encoding["crf"]),"-threads",str(min(16,args.threads_native)),"-pix_fmt",encoding["pixel_format"],
            "-movflags","+faststart",str(out/"video.mp4")],check=True)
        encode_seconds = time.perf_counter()-begin
        subprocess.run([sys.executable,str(ROOT/"scripts/pcve_verify_video.py"),str(out/"video.mp4"),
            "--out",str(out/"video_validation.json"),"--resolution","1280","720","--fps","24","--frames","96"],check=True)
    dump(out/f"render_report_{args.mode}.json",{"mode":args.mode,"backend":metadata["backend"],
        "blender_version":bpy.app.version_string,"setup_sec":setup_seconds,"render_sec":sum(times.values()),
        "encode_sec":encode_seconds,"frame_seconds":times,"reused_frames":96-len(times) if args.mode=="animation" else 0,
        "samples":cfg["render"]["samples"],"resolution":[1280,720]})

if __name__ == "__main__":
    main()
