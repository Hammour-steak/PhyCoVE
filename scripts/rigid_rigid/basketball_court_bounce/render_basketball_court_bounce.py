"""Fixed-camera Cycles rendering of the actual rigid solver cache at real time."""
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
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT/"scripts"))
from pcve_assets import ASSETS
from scene_config import SCENE, signature
from appearance.look_basketball_court_bounce import gym, build_ball, lighting, look_at, camera_response, film_response

def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False)+"\n")

def setup(physics, asset_root, choice, threads):
    cfg = physics["configuration"]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    rd = cfg["render"]
    scene.render.engine = "CYCLES"
    scene.cycles.samples = rd["samples"]
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = rd["adaptive_threshold"]
    scene.cycles.use_denoising = rd["denoising"]
    scene.cycles.denoising_use_gpu = False
    scene.cycles.max_bounces = rd.get("max_bounces",6)
    scene.cycles.diffuse_bounces = rd.get("diffuse_bounces",3)
    scene.cycles.glossy_bounces = rd.get("glossy_bounces",3)
    scene.cycles.transmission_bounces = 4
    scene.cycles.seed = cfg["appearance"]["seed"]
    scene.cycles.use_animated_seed = False
    scene.cycles.device = "CPU"
    backend = "CPU"
    if choice == "gpu":
        if not os.environ.get("CUDA_VISIBLE_DEVICES"):
            raise ValueError("GPU rendering needs an explicitly selected idle --gpu")
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        devices = [d for d in prefs.devices if d.type == "OPTIX"]
        if not devices:
            raise RuntimeError("No selected OptiX device")
        for d in prefs.devices:
            d.use = d in devices
        scene.cycles.device = "GPU"
        backend = "OPTIX: " + ", ".join(d.name for d in devices)
    scene.render.threads_mode = "FIXED"
    scene.render.threads = threads
    # Blender 4.3 drops objects that come to rest from later frames when persistent data is
    # combined with motion blur, so the render configuration keeps it off.
    scene.render.use_persistent_data = rd.get("persistent_data", True)
    scene.render.resolution_x, scene.render.resolution_y = rd["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.fps = rd["fps"]
    scene.render.fps_base = 1
    scene.frame_start, scene.frame_end = 1, rd["total_frames"]
    scene.view_settings.view_transform = rd["color_management"]
    scene.view_settings.look = rd.get("view_look","AgX - Medium High Contrast")
    scene.view_settings.exposure = rd["exposure"]
    scene.render.use_motion_blur = rd["motion_blur_shutter_frames"] > 0
    scene.render.motion_blur_shutter = rd["motion_blur_shutter_frames"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15
    scene.cycles.motion_blur_position = "CENTER"
    ledger = gym(cfg, asset_root)
    ball = build_ball(cfg, asset_root)
    lighting(cfg, asset_root)
    camera_response(cfg)
    ball_present=cfg["physics"]["ball"].get("present",True)
    if not ball_present:
        bpy.data.objects.remove(ball,do_unlink=True)
        ball=None
    camcfg = cfg["appearance"]["camera"]
    data = bpy.data.cameras.new("Fixed side camera")
    camera = bpy.data.objects.new("Fixed side camera",data)
    bpy.context.collection.objects.link(camera)
    camera.location = camcfg["position_m"]
    look_at(camera,camcfg["target_m"])
    data.lens, data.sensor_width = camcfg["lens_mm"], camcfg["sensor_width_mm"]
    data.clip_start, data.clip_end = 0.03, 150
    data.dof.use_dof = "dof_fstop" in camcfg
    if data.dof.use_dof:
        data.dof.aperture_fstop = camcfg["dof_fstop"]
        data.dof.focus_distance = (Vector(camcfg["focus_point_m"])-camera.location).length
    scene.camera = camera
    if ball_present:
        ball.rotation_mode = "QUATERNION"
        for sample in physics["trajectory_samples"]:
            t = sample["time_sec"]
            frame = 1+t*rd["fps"]
            ball.location = sample["location"]
            x,y,z,w = sample["quaternion_xyzw"]
            ball.rotation_quaternion = (w,x,y,z)
            ball.keyframe_insert(data_path="location",frame=frame,group="Solved rigid pose")
            ball.keyframe_insert(data_path="rotation_quaternion",frame=frame,group="Solved rigid pose")
        for fcurve in ball.animation_data.action.fcurves:
            for point in fcurve.keyframe_points:
                point.interpolation = "LINEAR"
        radius = cfg["physics"]["ball"]["radius_m"]
        gt = []
        for f in physics["frames"]:
            scene.frame_set(f["frame_index"])
            point = Vector(f["location"])
            corners = [world_to_camera_view(scene,camera,point+Vector((a*radius,b*radius,c*radius)))
                       for a in [-1,1] for b in [-1,1] for c in [-1,1]]
            center = world_to_camera_view(scene,camera,point)
            contact = world_to_camera_view(scene,camera,Vector((*f["location"][:2],0)))
            bounds = [min(p.x for p in corners),min(p.y for p in corners),max(p.x for p in corners),max(p.y for p in corners)]
            gt.append({"frame_index": f["frame_index"], "time_sec": f["time_sec"],
                "object_id": "B01", "location_m": f["location"], "quaternion_xyzw": f["quaternion_xyzw"],
                "center_px": [center.x*rd["resolution"][0],(1-center.y)*rd["resolution"][1]],
                "conservative_bounds_normalized_bottom_left": bounds,
                "floor_contact_px": [contact.x*rd["resolution"][0],(1-contact.y)*rd["resolution"][1]],
                "complete_ball_in_frame": min(bounds[:2]) > 0.025 and max(bounds[2:]) < 0.975,
                "ground_contact_in_frame": 0.02 < contact.x < 0.98 and 0.02 < contact.y < 0.98})
    else:
        gt=[{"frame_index":f["frame_index"],"time_sec":f["time_sec"],"object_id":"B01",
             "present":False,"objects":[],"location_m":None,"quaternion_xyzw":None,
             "center_px":None,"floor_contact_px":None} for f in physics["frames"]]
    # Empty cases have no pose loop to flush newly created camera/object transforms.
    bpy.context.view_layer.update()
    static = [{"name":o.name,"matrix_world":[list(row) for row in o.matrix_world]}
              for o in sorted(scene.objects,key=lambda o:o.name) if o != ball]
    metadata = {"scene": SCENE,"case_id":physics.get("case_id","source"),"blender_version":bpy.app.version_string,"backend":backend,
        "configuration_sha256":physics["configuration_sha256"],"configuration":cfg,"scale_ledger":ledger,
        "fixed_camera":not bool(camera.animation_data),"static_background_sha256":signature(static),
        "ball_present":ball_present,"animated_object_ids":["B01"] if ball_present else [],"ball_dimensions_m":list(ball.dimensions) if ball_present else None,
        "all_ball_bounds_in_frame":all(f["complete_ball_in_frame"] for f in gt) if ball_present else None,
        "all_ground_contact_points_in_frame":all(f["ground_contact_in_frame"] for f in gt) if ball_present else None,
        "minimum_conservative_diameter_px":min(min((f["conservative_bounds_normalized_bottom_left"][2]-f["conservative_bounds_normalized_bottom_left"][0])*1280,
            (f["conservative_bounds_normalized_bottom_left"][3]-f["conservative_bounds_normalized_bottom_left"][1])*720) for f in gt) if ball_present else None,
        "no_depth_of_field":not data.dof.use_dof,"no_motion_blur":not scene.render.use_motion_blur,
        "shared_3d_lighting_shadows_and_occlusion":True}
    if ball_present and (not metadata["all_ball_bounds_in_frame"] or not metadata["all_ground_contact_points_in_frame"]):
        raise RuntimeError("Camera clips the trajectory or contact point")
    scene.frame_set(1)
    return scene, metadata, gt

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--physics-json",type=Path,required=True)
    p.add_argument("--out-dir",type=Path,required=True)
    p.add_argument("--asset-root",type=Path,default=ASSETS)
    p.add_argument("--mode",choices=["prepare","frames","animation"],default="animation")
    p.add_argument("--keyframes",type=int,nargs="+")
    p.add_argument("--device",choices=["cpu","gpu"],default="cpu")
    p.add_argument("--threads-native",type=int,default=64)
    p.add_argument("--skip-existing",action="store_true")
    args = p.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:])
    physics = json.loads(args.physics_json.read_text())
    cfg = physics["configuration"]
    out = args.out_dir.expanduser().resolve()
    out.mkdir(parents=True,exist_ok=True)
    previous = out/"scenario_metadata.json"
    if previous.exists() and json.loads(previous.read_text())["configuration_sha256"] != physics["configuration_sha256"]:
        raise ValueError("Choose a fresh output directory for changed inputs")
    start = time.perf_counter()
    scene, metadata, gt = setup(physics,args.asset_root,args.device,args.threads_native)
    setup_seconds = time.perf_counter()-start
    dump(previous,metadata)
    dump(out/"ground_truth_transforms.json",gt)
    dump(out/"settings.json",cfg)
    scene["pcve_scene_id"] = SCENE
    scene["pcve_configuration_sha256"] = physics["configuration_sha256"]
    scene["physics_cache_sha256"] = hashlib.sha256(args.physics_json.read_bytes()).hexdigest()
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(out/(SCENE+".blend")))
    times = {}
    frames = out/"frames"
    if args.mode != "prepare":
        frames.mkdir(exist_ok=True)
        requested = args.keyframes or [1,14,25,34,48,66,80,96]
        if args.mode == "animation":
            requested = list(range(1,97))
        for index in requested:
            if not 1 <= index <= 96:
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
            if cfg["render"].get("film_grain_sigma_8bit"):
                film_response(dest,index,cfg)
            times[str(index)] = time.perf_counter()-begin
            dump(out/f"render_progress_{args.mode}.json",{"frames_completed":list(times),"frame_seconds":times})
            print(f"PCVE_FRAME {index} {times[str(index)]:.3f}s",flush=True)
    encode_seconds = 0
    if args.mode == "animation":
        for index in range(1,97):
            if not (frames/f"frame_{index:04d}.png").is_file():
                raise FileNotFoundError(index)
        begin = time.perf_counter()
        subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-framerate","24","-start_number","1",
            "-i",str(frames/"frame_%04d.png"),"-frames:v","96","-an","-c:v","libx264","-preset","slow","-crf","17",
            "-pix_fmt","yuv420p","-movflags","+faststart",str(out/"video.mp4")],check=True)
        encode_seconds = time.perf_counter()-begin
        subprocess.run([sys.executable,str(ROOT/"scripts/pcve_verify_video.py"),str(out/"video.mp4"),
            "--out",str(out/"video_validation.json"),"--resolution","1280","720","--fps","24","--frames","96"],check=True)
    dump(out/f"render_report_{args.mode}.json",{"mode":args.mode,"backend":metadata["backend"],
        "blender_version":bpy.app.version_string,"setup_sec":setup_seconds,"render_sec":sum(times.values()),
        "encode_sec":encode_seconds,"frame_seconds":times,"reused_frames":96-len(times) if args.mode=="animation" else 0,
        "samples":cfg["render"]["samples"],"resolution":[1280,720]})

if __name__ == "__main__":
    main()
