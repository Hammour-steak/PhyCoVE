"""Render the solved rigid toy cache with one fixed camera and real-time playback."""
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
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scripts"))
from scene_config import SCENE, signature
from appearance.look_ball_box_rebound import look_at


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def rigid_mesh_points(obj, depsgraph):
    """Cache evaluated polygon vertices in the rigid body's local coordinates."""
    points = []
    inverse = obj.matrix_world.inverted()
    for child in obj.children_recursive:
        if child.type != "MESH":
            continue
        evaluated = child.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        xyz = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", xyz)
        homogeneous = np.column_stack((xyz.reshape(-1, 3), np.ones(len(mesh.vertices))))
        points.append(homogeneous @ np.asarray(inverse @ evaluated.matrix_world).T)
        evaluated.to_mesh_clear()
    return np.concatenate(points)


def setup(physics, choice, threads):
    cfg = physics["configuration"]
    from appearance.look_ball_box_rebound import room, toys, lighting
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
    scene.cycles.max_bounces = rd.get("max_bounces", 6)
    scene.cycles.diffuse_bounces = rd.get("diffuse_bounces", 3)
    scene.cycles.glossy_bounces = rd.get("glossy_bounces", 3)
    scene.cycles.transmission_bounces = rd.get("transmission_bounces", 3)
    scene.cycles.seed = cfg["appearance"]["seed"]
    scene.cycles.use_animated_seed = False
    scene.cycles.device = "CPU"
    backend = "CPU"
    if choice in ("gpu", "metal"):
        compute_type = "METAL" if choice == "metal" else "OPTIX"
        if choice == "gpu" and not os.environ.get("CUDA_VISIBLE_DEVICES"):
            raise ValueError("GPU rendering requires an explicitly selected idle --gpu")
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = compute_type
        preferences.get_devices()
        selected = [d for d in preferences.devices if d.type == compute_type]
        if not selected:
            raise RuntimeError("No selected " + compute_type + " device")
        for device in preferences.devices:
            device.use = device in selected
        scene.cycles.device = "GPU"
        backend = compute_type + ": " + ", ".join(d.name for d in selected)
    scene.render.threads_mode = "FIXED"
    scene.render.threads = threads
    # Blender 4.3: persistent data with motion blur drops objects that come to
    # rest in later frames of the same session, so it is only kept without blur.
    scene.render.use_persistent_data = not rd["motion_blur_shutter_frames"] > 0
    scene.render.resolution_x, scene.render.resolution_y = rd["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.fps, scene.render.fps_base = rd["fps"], 1
    scene.frame_start, scene.frame_end = 1, rd["total_frames"]
    scene.view_settings.view_transform = rd["color_management"]
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = cfg["appearance"]["exposure_stops"]
    scene.render.use_motion_blur = rd["motion_blur_shutter_frames"] > 0
    scene.render.motion_blur_shutter = rd["motion_blur_shutter_frames"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15
    ledger = room(cfg)
    objects = toys(cfg)
    for name in ("ball", "box"):
        # DELETE of the star ball or the toy chest holds from frame 1: the body
        # and every child mesh are removed before anything is keyed.
        if cfg["physics"][name].get("remove_at_sec") == 0:
            target = objects.pop(name)
            for obj in [*target.children_recursive, target]:
                bpy.data.objects.remove(obj, do_unlink=True)
    removal = cfg["physics"]["football"].get("remove_at_sec")
    if removal == 0:
        football = objects.pop("football")
        for obj in [*football.children_recursive, football]:
            bpy.data.objects.remove(obj, do_unlink=True)
    elif removal is not None:
        # Visibility is stepped at the same physical instant as removeBody.
        # Apply it to every renderable child; hiding only an Empty leaves ghosts.
        frame = 1 + removal * rd["fps"]
        for obj in [objects["football"], *objects["football"].children_recursive]:
            for field in ("hide_render", "hide_viewport"):
                setattr(obj, field, False)
                obj.keyframe_insert(data_path=field, frame=1, group="Solved object lifecycle")
                setattr(obj, field, True)
                obj.keyframe_insert(data_path=field, frame=frame, group="Solved object lifecycle")
            for curve in obj.animation_data.action.fcurves:
                if curve.data_path in ("hide_render", "hide_viewport"):
                    for point in curve.keyframe_points:
                        point.interpolation = "CONSTANT"
    lighting(cfg)
    cc = cfg["appearance"]["camera"]
    data = bpy.data.cameras.new("Fixed elevated oblique camera")
    camera = bpy.data.objects.new("Fixed elevated oblique camera", data)
    bpy.context.collection.objects.link(camera)
    camera.location = cc["position_m"]
    look_at(camera, cc["target_m"])
    data.lens, data.sensor_width = cc["lens_mm"], cc["sensor_width_mm"]
    data.clip_start, data.clip_end = 0.03, 100
    data.dof.use_dof = cc.get("aperture_fstop", 0) > 0
    if data.dof.use_dof:
        data.dof.aperture_fstop = cc["aperture_fstop"]
        data.dof.focus_distance = cc["focus_distance_m"]
    scene.camera = camera
    for sample in physics["trajectory_samples"]:
        frame = 1 + sample["time_sec"] * rd["fps"]
        for name, obj in objects.items():
            if name not in sample["objects"]:
                continue
            state = sample["objects"][name]
            obj.location = state["location"]
            x, y, z, w = state["quaternion_xyzw"]
            obj.rotation_quaternion = (w, x, y, z)
            obj.keyframe_insert(data_path="location", frame=frame, group="Solved rigid pose")
            obj.keyframe_insert(data_path="rotation_quaternion", frame=frame, group="Solved rigid pose")
    for obj in objects.values():
        for fcurve in obj.animation_data.action.fcurves:
            for point in fcurve.keyframe_points:
                point.interpolation = "CONSTANT" if fcurve.data_path in ("hide_render", "hide_viewport") else "LINEAR"
    # A rotating sphere's bounding-box corners include empty space and can
    # incorrectly fail framing. Project its actual evaluated geometry instead;
    # retain the same 2.5% safety margin and include all modifier geometry.
    scene.frame_set(1)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    local_points = {name: rigid_mesh_points(obj, depsgraph) for name, obj in objects.items()}
    projection = np.asarray(camera.calc_matrix_camera(depsgraph, x=1280, y=720)
                            @ camera.matrix_world.inverted())
    gt, margins = [], []
    for frame in physics["frames"]:
        scene.frame_set(frame["frame_index"])
        for name in ("ball", "box", "football"):
            if name not in frame["objects"]:
                gt.append({"frame_index": frame["frame_index"], "time_sec": frame["time_sec"],
                    "object_id": cfg["physics"][name]["id"], "present": False,
                    "center_px": None, "conservative_visual_bounds_normalized_bottom_left": None,
                    "complete_object_in_frame": None, "visible_in_frame": False})
                continue
            obj = objects[name]
            clip = local_points[name] @ (projection @ np.asarray(obj.matrix_world)).T
            if not np.all(clip[:, 3] > 0):
                raise RuntimeError("Rigid geometry extends behind the fixed camera")
            screen = (clip[:, :2] / clip[:, 3, None] + 1) / 2
            bounds = screen.min(axis=0).tolist() + screen.max(axis=0).tolist()
            center = world_to_camera_view(scene, camera, obj.location)
            gt.append({"frame_index": frame["frame_index"], "time_sec": frame["time_sec"],
                "object_id": cfg["physics"][name]["id"], **frame["objects"][name],
                "present": True,
                "center_px": [center.x * 1280, (1 - center.y) * 720],
                "conservative_visual_bounds_normalized_bottom_left": bounds,
                "visible_in_frame": bounds[2] > 0 and bounds[3] > 0 and bounds[0] < 1 and bounds[1] < 1,
                "complete_object_in_frame": min(bounds[:2]) > 0.025 and max(bounds[2:]) < 0.975})
            margins.append(min(bounds[0], bounds[1], 1 - bounds[2], 1 - bounds[3]))
    contacts_visible = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for event in physics["contact_events"]:
        if event["normal_impulse_Ns"] < 0.005:
            continue
        scene.frame_set(math.floor(event["frame_float"]), subframe=event["frame_float"] % 1)
        point = Vector(event["contact_position_m"])
        origin = camera.location.copy()
        hit, pos, normal, index, obj, matrix = scene.ray_cast(depsgraph, origin, (point - origin).normalized(), distance=(point - origin).length + 0.002)
        prefix = tuple(cfg["physics"][name]["id"] for name in event["pair"])
        contacts_visible.append({"pair": event["pair"], "time_sec": event["time_sec"],
            "first_visible_surface": obj.name if hit else None,
            "not_occluded_by_unrelated_object": not hit or obj.name.startswith(prefix)})
    static = [{"name": obj.name, "matrix_world": [list(row) for row in obj.matrix_world]}
              for obj in sorted(scene.objects, key=lambda item: item.name)
              if obj not in objects.values() and not obj.parent]
    edited_case = physics.get("case_id", "source") != "source"
    metadata = {"scene": SCENE, "case_id": physics.get("case_id", "source"), "blender_version": bpy.app.version_string, "backend": backend,
        "configuration": cfg, "configuration_sha256": physics["configuration_sha256"],
        "scale_ledger": ledger, "fixed_camera": not bool(camera.animation_data),
        "static_background_sha256": signature(static), "animated_object_ids": [cfg["physics"][name]["id"] for name in objects],
        "all_object_bounds_in_frame": all(item["complete_object_in_frame"] for item in gt if item["present"]),
        "framing_bounds_method": "Projected evaluated rigid-mesh vertices, including modifiers; 2.5 percent margin recorded",
        "offscreen_motion_allowed": edited_case,
        "framing_policy": "Source retains the complete-path margin. User permits counterfactual bodies to leave the unchanged camera; no path clamp or recentering.",
        "incomplete_framing": [{"frame": item["frame_index"], "object_id": item["object_id"],
                               "visible_in_frame": item["visible_in_frame"]}
                              for item in gt if item["present"] and not item["complete_object_in_frame"]],
        "object_lifecycle": physics.get("object_lifecycle", {}),
        "intervention_events": [{key: e[key] for key in ("operation", "object_id", "time_sec", "frame_float")}
                                for e in physics.get("intervention_events", [])],
        "minimum_frame_margin_normalized": min(margins), "contact_visibility": contacts_visible,
        "shared_3d_lighting_shadows_and_occlusion": True, "no_depth_of_field": not data.dof.use_dof,
        "camera_focus_distance_m": data.dof.focus_distance if data.dof.use_dof else None,
        "camera_aperture_fstop": data.dof.aperture_fstop if data.dof.use_dof else None,
        "no_motion_blur": not scene.render.use_motion_blur,
        "pose_source": "480 Hz solved SI-unit rigid transforms; linear sampling at original physical time."}
    if (not edited_case and not metadata["all_object_bounds_in_frame"]) or not all(c["not_occluded_by_unrelated_object"] for c in contacts_visible):
        raise RuntimeError("Camera validation failed: " + json.dumps({"all_object_bounds_in_frame": metadata["all_object_bounds_in_frame"], "minimum_margin": min(margins), "contacts": contacts_visible}))
    scene.frame_set(1)
    return scene, metadata, gt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=["prepare", "frames", "animation"], default="animation")
    parser.add_argument("--keyframes", type=int, nargs="+")
    parser.add_argument("--device", choices=["cpu", "gpu", "metal"], default="cpu")
    parser.add_argument("--threads-native", type=int, default=64)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    physics = json.loads(args.physics_json.read_text())
    cfg = physics["configuration"]
    out = args.out_dir.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "scenario_metadata.json").exists() and json.loads((out / "scenario_metadata.json").read_text())["configuration_sha256"] != physics["configuration_sha256"]:
        raise ValueError("Choose a fresh output directory for changed inputs")
    start = time.perf_counter()
    scene, metadata, gt = setup(physics, args.device, args.threads_native)
    setup_seconds = time.perf_counter() - start
    dump(out / "scenario_metadata.json", metadata)
    dump(out / "ground_truth_transforms.json", gt)
    dump(out / "settings.json", cfg)
    scene["pcve_scene_id"] = SCENE
    scene["pcve_configuration_sha256"] = physics["configuration_sha256"]
    scene["physics_cache_sha256"] = hashlib.sha256(args.physics_json.read_bytes()).hexdigest()
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(out / (SCENE + ".blend")))
    times = {}
    frames = out / "frames"
    if args.mode != "prepare":
        frames.mkdir(exist_ok=True)
        contacts = [round(e["frame_float"]) for e in physics["contact_events"] if e["normal_impulse_Ns"] > 0.005]
        requested = args.keyframes or sorted(set([1, 12, 36, 60, 78, 96] + [max(1, min(96, f + delta)) for f in contacts for delta in (-1, 0, 1)]))
        if args.mode == "animation":
            requested = list(range(1, 97))
        for index in requested:
            if not 1 <= index <= 96:
                raise ValueError(index)
            dest = frames / f"frame_{index:04d}.png"
            if dest.exists():
                if args.skip_existing:
                    continue
                raise FileExistsError(dest)
            begin = time.perf_counter()
            scene.frame_set(index)
            scene.render.filepath = str(dest)
            bpy.ops.render.render(write_still=True)
            times[str(index)] = time.perf_counter() - begin
            dump(out / f"render_progress_{args.mode}.json", {"frames_completed": list(times), "frame_seconds": times})
            print(f"PCVE_FRAME {index} {times[str(index)]:.3f}s", flush=True)
    encode_seconds = 0
    if args.mode == "animation":
        for index in range(1, 97):
            if not (frames / f"frame_{index:04d}.png").is_file():
                raise FileNotFoundError(index)
        begin = time.perf_counter()
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-threads", "4", "-framerate", "24", "-start_number", "1",
            "-i", str(frames / "frame_%04d.png"), "-frames:v", "96", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out / "video.mp4")], check=True)
        encode_seconds = time.perf_counter() - begin
        subprocess.run([sys.executable, str(ROOT / "scripts/pcve_verify_video.py"), str(out / "video.mp4"),
            "--out", str(out / "video_validation.json"), "--resolution", "1280", "720", "--fps", "24", "--frames", "96"], check=True)
    dump(out / f"render_report_{args.mode}.json", {"mode": args.mode, "backend": metadata["backend"],
        "blender_version": bpy.app.version_string, "setup_sec": setup_seconds, "render_sec": sum(times.values()),
        "encode_sec": encode_seconds, "frame_seconds": times, "reused_frames": 96 - len(times) if args.mode == "animation" else 0,
        "samples": cfg["render"]["samples"], "resolution": cfg["render"]["resolution"]})


if __name__ == "__main__":
    main()
