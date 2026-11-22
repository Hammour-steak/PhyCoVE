"""Replay one native spring/car/block solve in Blender 4.3 Cycles (run by render_spring_car_collision.py).

    blender -b --factory-startup --python appearance/render_native.py -- --cache CASE/trajectory.npz \
        --case source --out OUT [--device optix|cuda|cpu] [--samples 384] [--frames 1 30 60]

Every moving pose is keyed from the solver cache at Blender frame f = native
sample f-1 (t = (f-1)/24 s): car chassis, four wheels, block, added block,
spring pusher, and the coil as one shape key per sample. Nothing is simulated
or smoothed here. After keying, every frame is read back from the evaluated
scene and compared with the cache (replay_audit.json). Motion blur (shutter
0.25 frame) interpolates between consecutive native samples.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
CASE_DIR = SCRIPT_DIR.parent
sys.path[:0] = [str(SCRIPT_DIR), str(CASE_DIR), str(CASE_DIR.parents[1])]
sys.dont_write_bytecode = True
from assets_scene import build_block, build_obstacle_block, build_spring, coil_vertices  # noqa: E402
from car_model import build_car  # noqa: E402
import look  # noqa: E402

SEMANTIC_IDS = {"spring": 1, "car": 2, "block": 3, "static_environment": 4, "obstacle_block": 5}


def arguments():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--case", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--asset-dir", type=Path, required=True)
    p.add_argument("--device", choices=["optix", "cuda", "cpu"], default="optix")
    p.add_argument("--samples", type=int, default=384)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--frame-start", type=int, default=1)
    p.add_argument("--frame-end", type=int, default=96)
    p.add_argument("--frames", type=int, nargs="+")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--save-blend", action="store_true")
    p.add_argument("--inspect-camera", type=float, nargs=7, metavar=("X", "Y", "Z", "TX", "TY", "TZ", "LENS"),
                   help="inspection stills only: replace the fixed camera")
    return p.parse_args(argv)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def action_fcurves(action):
    if hasattr(action, "fcurves"):
        yield from action.fcurves
    else:  # Blender 5 layered actions
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    yield from bag.fcurves


def pose_keyframes(obj, matrices):
    obj.rotation_mode = "QUATERNION"
    previous = None
    for index, matrix in enumerate(matrices):
        obj.matrix_world = Matrix(matrix.tolist())
        if previous is not None and previous.dot(obj.rotation_quaternion) < 0:
            obj.rotation_quaternion.negate()   # keep q continuous so subframes never flip
        previous = obj.rotation_quaternion.copy()
        for prop in ("location", "rotation_quaternion"):
            obj.keyframe_insert(prop, frame=index + 1)
    if obj.animation_data and obj.animation_data.action:
        for f in action_fcurves(obj.animation_data.action):
            for point in f.keyframe_points:
                point.interpolation = "LINEAR"


def bake_coil(obj, lengths, c):
    obj.shape_key_add(name="Basis")
    for index, length in enumerate(lengths):
        frame = index + 1
        key = obj.shape_key_add(name="Native sample %04d" % frame)
        v = coil_vertices(float(length), c["anchor_x"], c["axis_height"], c["mean_diameter"], c["wire_diameter"],
                          c["active_coils"], c["end_coils"])
        key.data.foreach_set("co", v.ravel())
        key.value = 0; key.keyframe_insert("value", frame=frame - 1)
        key.value = 1; key.keyframe_insert("value", frame=frame)
        key.value = 0; key.keyframe_insert("value", frame=frame + 1)
    action = obj.data.shape_keys.animation_data.action
    for fc in action_fcurves(action):
        for point in fc.keyframe_points:
            point.interpolation = "LINEAR"


def spring_config(p):
    return {"anchor_x": p["spring_anchor_x_m"], "free_length": p["spring_rest_length_m"],
            "axis_height": p["spring_axis_z_m"], "mean_diameter": p["spring_mean_diameter_m"],
            "wire_diameter": p["spring_wire_diameter_m"], "active_coils": p["spring_active_turns"],
            "end_coils": p["spring_total_turns"] - p["spring_active_turns"],
            "plate_dimensions": p["spring_plate_size_m"], "guide_y": p["spring_guide_y_m"],
            "guide_z": p["spring_guide_z_m"], "moving_assembly_mass": p["spring_plate_mass_kg"]}


def check_geometry(p, metadata):
    checks = {"car_length": abs(p["car_length_m"] - metadata["body_length_m"]),
              "wheel_radius": abs(p["wheel_radius_m"] - metadata["wheel_radius_m"]),
              "wheel_width": abs(p["wheel_width_m"] - metadata["wheel_width_m"]),
              "wheel_pivots": float(np.max(np.abs(np.array(p["car_wheel_centers_local_m"]) - np.array(metadata["wheel_centers_local_m"])))),
              "chassis_height": abs(p["car_root_height_m"] - metadata["chassis_com_above_table_m"])}
    if max(checks.values()) > 2e-7:
        raise RuntimeError("Render/solver geometry mismatch: " + json.dumps(checks))
    return {"maximum_difference_m": max(checks.values()), "checks_m": checks}


def audit_replay(scene, cache, car, block, spring, obstacle):
    worst = {"car": 0.0, "wheels": 0.0, "block": 0.0, "spring_plate": 0.0, "obstacle_block": 0.0, "coil_vertex": 0.0}
    for index in range(len(cache["times"])):
        scene.frame_set(index + 1)
        pairs = []
        if car:
            pairs.append(("car", car["root"], cache["car_transforms"][index]))
            pairs += [("wheels", obj, cache["wheel_transforms"][index, i]) for i, obj in enumerate(car["wheels"])]
        if block:
            pairs.append(("block", block["root"], cache["block_transforms"][index]))
        if obstacle:
            pairs.append(("obstacle_block", obstacle["root"], cache["obstacle_transforms"][index]))
        if spring["plate"] is not None:
            pairs.append(("spring_plate", spring["plate"], cache["spring_plate_transforms"][index]))
        for key, obj, matrix in pairs:
            worst[key] = max(worst[key], float(np.max(np.abs(np.asarray(obj.matrix_world) - matrix))))
        if spring["coil"] is not None:
            evaluated = spring["coil"].evaluated_get(bpy.context.evaluated_depsgraph_get())
            actual = np.empty(len(evaluated.data.vertices) * 3)
            evaluated.data.vertices.foreach_get("co", actual)
            c = spring["configuration"]
            expected = coil_vertices(float(cache["spring_length"][index]), c["anchor_x"], c["axis_height"],
                                     c["mean_diameter"], c["wire_diameter"], c["active_coils"], c["end_coils"])
            worst["coil_vertex"] = max(worst["coil_vertex"], float(np.max(np.linalg.norm(actual.reshape(-1, 3) - expected, axis=1))))
    scene.frame_set(1)
    if max(worst.values()) > 2e-6:
        raise RuntimeError("Evaluated Blender scene does not match the physics cache: " + json.dumps(worst))
    return {"frames_checked": len(cache["times"]), "maximum_error": worst, "tolerance": 2e-6, "passed": True,
            "method": "matrix_world of every keyed body and every coil vertex read back from the evaluated scene at each frame"}


def configure_render(scene, a):
    scene.render.engine = "CYCLES"
    c = scene.cycles
    c.samples = a.samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.005
    c.seed = a.seed
    c.use_animated_seed = False
    c.use_denoising = True
    c.denoiser = "OPENIMAGEDENOISE"
    c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces = 12, 5, 5
    c.transmission_bounces, c.transparent_max_bounces = 10, 16
    c.sample_clamp_indirect = 8.0
    c.blur_glossy = 0.5
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
    scene.render.fps = 24
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    # Motion blur between consecutive native samples. Blender 4.3 drops static
    # objects from later frames of one session when persistent data is on.
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.25
    scene.render.use_persistent_data = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = look.EXPOSURE
    devices = []
    if a.device == "cpu":
        c.device = "CPU"
    else:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = a.device.upper()
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type == a.device.upper()
            if d.use:
                devices.append({"name": d.name, "type": d.type})
        if not devices:
            raise RuntimeError(f"No {a.device.upper()} device visible (CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')})")
        c.device = "GPU"
    scene.render.threads_mode = "AUTO"
    return {"engine": "Cycles " + bpy.app.version_string, "device": a.device, "cycles_devices": devices,
            "samples": a.samples, "adaptive_threshold": 0.005, "denoiser": "OpenImageDenoise (albedo + normal)",
            "seed": a.seed, "bounces": {"max": 12, "diffuse": 5, "glossy": 5, "transmission": 10},
            "indirect_clamp": 8.0, "motion_blur_shutter_frames": 0.25, "persistent_data": False,
            "view_transform": "AgX", "look": "AgX - Medium High Contrast", "exposure": look.EXPOSURE,
            "resolution": [1280, 720], "fps": 24,
            "host": platform.node(), "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}


def configure_camera(scene, inspect=None):
    cfg = dict(look.CAMERA)
    if inspect:
        cfg.update(location=tuple(inspect[:3]), target=tuple(inspect[3:6]), focus=tuple(inspect[3:6]), lens_mm=inspect[6])
    data = bpy.data.cameras.new("Camera | fixed tripod, 50 mm")
    obj = bpy.data.objects.new("Camera | fixed tripod", data)
    scene.collection.objects.link(obj)
    obj.location = cfg["location"]
    obj.rotation_euler = (Vector(cfg["target"]) - obj.location).to_track_quat("-Z", "Y").to_euler()
    data.lens, data.sensor_width, data.sensor_fit = cfg["lens_mm"], cfg["sensor_width_mm"], "HORIZONTAL"
    data.clip_start, data.clip_end = 0.01, 30.0
    data.dof.use_dof = True
    data.dof.focus_distance = (Vector(cfg["focus"]) - obj.location).length
    data.dof.aperture_fstop = cfg["fstop"]
    data.dof.aperture_blades = 7
    data.dof.aperture_rotation = 0.2
    scene.camera = obj
    bpy.context.view_layer.update()
    w, h = 1280, 720
    fx = w * data.lens / data.sensor_width
    return {"name": obj.name, "location_m": list(obj.location), "target_m": list(cfg["target"]),
            "matrix_world": [list(r) for r in obj.matrix_world], "lens_mm": data.lens,
            "sensor_width_mm": data.sensor_width, "sensor_fit": "HORIZONTAL", "shift": [0.0, 0.0],
            "clip_start_m": data.clip_start, "clip_end_m": data.clip_end, "resolution": [w, h],
            "depth_of_field": True, "focus_distance_m": data.dof.focus_distance, "aperture_fstop": cfg["fstop"],
            "intrinsics": {"fx": fx, "fy": fx, "cx": w / 2, "cy": h / 2, "matrix": [[fx, 0, w / 2], [0, fx, h / 2], [0, 0, 1]]},
            "convention": "Blender camera: +X right, +Y up, looks along -Z; image origin top-left"}


def main():
    a = arguments()
    global bpy, Matrix, Vector
    import bpy
    from mathutils import Matrix, Vector
    started = time.time()
    a.out.mkdir(parents=True, exist_ok=True)
    params_bytes = (a.cache.parent / "scene_params.json").read_bytes()
    p = json.loads(params_bytes)
    cache_bytes = a.cache.read_bytes()
    with np.load(io.BytesIO(cache_bytes), allow_pickle=False) as z:
        cache = {k: z[k] for k in z.files}
    count = len(cache["times"])
    if count != 96 or not np.allclose(cache["times"], np.arange(96) / 24.0, atol=1e-9):
        raise RuntimeError("Native cache must hold 96 samples at t = (f-1)/24 s")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.frame_start, scene.frame_end = 1, count
    render = configure_render(scene, a)
    car_on = bool(np.asarray(cache.get("car_present", True)).reshape(-1)[0])
    car = build_car(bpy, a.asset_dir / "toy_car") if car_on else None
    geometry = check_geometry(p, car["metadata"]) if car else None
    spring = build_spring(bpy, spring_config(p), bool(p["spring_present"]))
    block = build_block(bpy, a.asset_dir, p["block_size_m"]) if p["block_present"] else None
    extra = bool(np.asarray(cache.get("obstacle_present", False)).reshape(-1)[0])
    obstacle = build_obstacle_block(bpy, a.asset_dir, p["obstacle_size_m"]) if extra else None
    environment = look.build(a.asset_dir, scene)
    camera = configure_camera(scene, a.inspect_camera)
    if car:
        pose_keyframes(car["root"], cache["car_transforms"])
        for i, pivot in enumerate(car["wheels"]):
            pose_keyframes(pivot, cache["wheel_transforms"][:, i])
    if block:
        pose_keyframes(block["root"], cache["block_transforms"])
    if obstacle:
        pose_keyframes(obstacle["root"], cache["obstacle_transforms"])
    if spring["plate"] is not None:
        pose_keyframes(spring["plate"], cache["spring_plate_transforms"])
        bake_coil(spring["coil"], cache["spring_length"], spring["configuration"])
    scene.frame_set(1)
    audit = audit_replay(scene, cache, car, block, spring, obstacle)
    save_json(a.out / "replay_audit.json", {"case": a.case, "cache_sha256": hashlib.sha256(cache_bytes).hexdigest(), **audit})
    metadata = {"schema_version": 2, "scene_id": "spring_car_collision", "case": a.case,
                "native_cache": str(a.cache), "native_cache_sha256": hashlib.sha256(cache_bytes).hexdigest(),
                "scene_params_sha256": hashlib.sha256(params_bytes).hexdigest(),
                "frame_mapping": "Blender frame f = native sample f-1, t = (f-1)/24 s", "frames_in_cache": count,
                "camera": camera, "render": render, "environment": environment,
                "car": {"model": car["metadata"], "geometry_check": geometry} if car else "removed_in_delete_car",
                "spring": spring["metadata"].get("removed_in_delete_spring") if spring["plate"] is None else "present",
                "semantic_instance_ids": SEMANTIC_IDS, "replay_audit": audit}
    save_json(a.out / "render_metadata.json", metadata)
    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(a.out / "scene.blend"))
    frames = a.frames or list(range(a.frame_start, min(a.frame_end, count) + 1))
    done = []
    for frame in frames:
        if not 1 <= frame <= count:
            raise ValueError(f"frame {frame} outside 1..{count}")
        target = a.out / ("frame_%04d.png" % frame)
        if a.resume and target.is_file():
            continue
        scene.frame_set(frame)
        scene.render.filepath = str(target)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        done.append(frame)
        print(json.dumps({"rendered_frame": frame, "seconds": round(time.time() - t0, 1), "out": str(target)}), flush=True)
    # A resumed run lists every requested frame on disk (frames of an interrupted run of the same
    # job were made with the same settings); rendered_now is what this run itself rendered.
    present = [f for f in frames if (a.out / ("frame_%04d.png" % f)).is_file()]
    part = {"frames": present, "rendered_now": done, "render": render,
            "native_cache_sha256": metadata["native_cache_sha256"], "seconds": round(time.time() - started, 1)}
    tag = f"f{min(frames):04d}_{max(frames):04d}" if frames else "none"
    save_json(a.out / f"render_part_{tag}.json", part)
    print(json.dumps({"complete": True, "case": a.case, "frames": len(done)}), flush=True)


if __name__ == "__main__":
    main()
