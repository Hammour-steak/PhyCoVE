"""Blender: put a packed reference scene on the 4 s / 24 FPS benchmark clock, apply the current look, save/render.

Run as  blender -b <assets/scenes/phone_sofa_drop/packed/CASE/scene.blend> --disable-autoexec
        --python retime_packed_scene.py -- --cache CASE_4s/simulation_dense.npz [--embedding E.npz]
        --out DIR [--look appearance.json --assets ASSETS_DIR] [--frames 1 2 ...]
        [--device GPU|CPU] [--no-render] [--save-blend PATH]

The packed scene keeps its objects, camera and the fixed tetrahedral FEM embedding of the
original sculpted cushion. The animation data is rebuilt from the 4 s native cache at its
240 Hz state rate, in exactly the form of the packed scene's own animation (absolute linear shape keys
driven by eval_time, linear phone location/quaternion keys), and the scene clock becomes 24 FPS,
frames 1-96 (t = (f-1)/24). The motion-blur shutter keeps the physical exposure of 1/300 s
(0.10 frame at 30 FPS -> 0.08 frame at 24 FPS). With --look, appearance/realism_look.py then
changes materials, lights, room shell and render settings (never the simulated bodies or camera).

Before anything is changed, the cache states inside the accepted 0-3 s window are compared
with the shape keys and phone keys stored in the packed scene and must agree to REF_TOLERANCE_M
(the 4 s re-run differs from the accepted 0-3 s reference run by at most ~35 um; a wrong embedding or vertex
order shows up as centimetres). After the rebuild every one of the 961 dense states is evaluated
back from Blender and must match the cache to 5 um.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import socket
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix

FPS, FRAMES, DENSE_HZ, DURATION = 24, 96, 240, 4.0
STRIDE = DENSE_HZ // FPS            # dense states per output frame
EXPOSURE_S = 0.10 / 30              # accepted reference exposure
REF_FPS, REF_FRAMES = 30, 91
CUSHION = "Dynamic_Original_Middle_Seat"
PILLOW = "landing_pillow.native_artwork"
PHONE = "phone | rigid COM root"
TOLERANCE_M = 5e-6
REF_TOLERANCE_M = 1e-4


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            h.update(block)
    return h.hexdigest()


def options():
    p = argparse.ArgumentParser(prog="retime_packed_scene.py")
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--embedding", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", type=int, nargs="+")
    p.add_argument("--device", choices=("GPU", "CPU"), default="GPU")
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--save-blend", type=Path)
    p.add_argument("--samples", type=int, help="Smoke tests only; the delivery uses the look's sample count")
    p.add_argument("--look", type=Path, help="appearance.json of the current look (appearance/realism_look.py)")
    p.add_argument("--assets", type=Path, help="Asset root the look's files are read from")
    return p.parse_args(sys.argv[sys.argv.index("--") + 1:])


def set_keys(fcurve, frames, values):
    points = fcurve.keyframe_points
    points.clear()
    points.add(len(frames))
    co = np.empty(2 * len(frames), dtype=np.float32)
    co[0::2], co[1::2] = frames, values
    points.foreach_set("co", co)
    for point in points:
        point.interpolation = "LINEAR"
    fcurve.update()


def curves(owner):
    action = owner.animation_data.action
    return {(c.data_path, c.array_index): c for c in action.fcurves}


def cushion_world(embedding, solid):
    ids, weights = embedding
    return np.einsum("nv,nvc->nc", weights, solid[ids])


def local(obj, world):
    inverse = np.linalg.inv(np.asarray(obj.matrix_world))
    return (world @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)


def evaluated(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = obj.evaluated_get(depsgraph).data
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def goto(frame):
    scene = bpy.context.scene
    whole = math.floor(frame + 1e-9)
    scene.frame_set(int(whole), subframe=float(frame - whole))
    bpy.context.view_layer.update()


def quaternions(transforms):
    q = np.array([tuple(Matrix(T.tolist()).to_quaternion()) for T in transforms])
    flips = 0
    for i in range(1, len(q)):
        if np.dot(q[i], q[i - 1]) < 0:
            q[i] = -q[i]
            flips += 1
    return q, flips


def main():
    a = options()
    started = time.time()
    scene = bpy.context.scene
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (bpy.app.version_string != "4.3.2" or (scene.frame_start, scene.frame_end) != (1, REF_FRAMES)
            or scene.render.fps / scene.render.fps_base != REF_FPS
            or (scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage) != (1280, 720, 100)
            or not math.isclose(scene.render.motion_blur_shutter, 0.10, abs_tol=1e-6)):
        raise ValueError("Expected an accepted reference packed scene (Blender 4.3.2, 30 FPS, frames 1-91, 1280x720)")
    cache = np.load(a.cache, allow_pickle=False)
    times = cache["times"]
    count = round(DURATION * DENSE_HZ) + 1
    if len(times) != count or np.max(np.abs(times - np.arange(count) / DENSE_HZ)) > 1e-12:
        raise ValueError("Expected the 0-4 s native cache sampled at exactly 240 Hz")
    T = cache["phone_transforms"]
    cushion = bool(cache["cushion_present"])
    pillow = bool(cache["pillow_present"])
    phone = bpy.data.objects[PHONE]
    report = {"blender_version": bpy.app.version_string,
              "packed_scene": bpy.data.filepath, "packed_scene_sha256": sha(bpy.data.filepath),
              "cache": str(a.cache), "cache_sha256": sha(a.cache),
              "host": socket.gethostname(), "cushion_present": cushion, "pillow_present": pillow,
              "dense_states": count, "fps": FPS, "frames": FRAMES, "exposure_s": EXPOSURE_S}

    # ---- 1. agreement with the packed reference animation inside the accepted 0-3 s window
    overlap = round(3.0 * DENSE_HZ) + 1
    embedding = None
    keys = None
    if cushion:
        if a.embedding is None:
            raise ValueError("The cushion needs its fixed tetrahedral embedding")
        with np.load(a.embedding, allow_pickle=False) as e:
            embedding = (e["vertex_ids"].astype(np.int64), e["weights"])
            report["embedding_sha256"] = sha(a.embedding)
        obj = bpy.data.objects[CUSHION]
        keys = obj.data.shape_keys
        if keys.use_relative or len(keys.key_blocks) != overlap + 1:
            raise ValueError("Unexpected packed cushion shape keys")
        solid = cache["solid_positions"]
        worst, first = 0.0, None
        for k in range(overlap):
            expected = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
            keys.key_blocks[k + 1].data.foreach_get("co", expected)
            error = float(np.max(np.abs(local(obj, cushion_world(embedding, solid[k])) - expected.reshape(-1, 3))))
            if k == 0:
                first = error
            worst = max(worst, error)
        report["ref_window_cushion_key_max_abs_m"] = worst
        report["initial_cushion_key_max_abs_m"] = first
    if pillow:
        pobj = bpy.data.objects[PILLOW]
        pkeys = pobj.data.shape_keys
        if pkeys.use_relative or len(pkeys.key_blocks) != overlap + 1:
            raise ValueError("Unexpected packed pillow shape keys")
        positions = cache["pillow_render_boundary_positions"]
        worst = 0.0
        for k in range(overlap):
            expected = np.empty(len(pobj.data.vertices) * 3, dtype=np.float32)
            pkeys.key_blocks[k + 1].data.foreach_get("co", expected)
            worst = max(worst, float(np.max(np.abs(positions[k].astype(np.float32) - expected.reshape(-1, 3)))))
        report["ref_window_pillow_key_max_abs_m"] = worst
    worst = 0.0
    for k in range(overlap):
        goto(1 + k * REF_FPS / DENSE_HZ)
        worst = max(worst, float(np.max(np.abs(np.asarray(phone.matrix_world) - T[k]))))
    report["ref_window_phone_matrix_max_abs"] = worst
    agreement = {k: report[k] for k in ("ref_window_cushion_key_max_abs_m", "ref_window_pillow_key_max_abs_m",
                                         "ref_window_phone_matrix_max_abs") if k in report}
    if max(agreement.values()) > REF_TOLERANCE_M:
        raise ValueError("The 4 s cache does not reproduce the packed reference animation (wrong embedding or vertex "
                         "order?): " + json.dumps(agreement))

    # ---- 2. rebuild the animation on the 4 s clock
    frames_of = 1 + times * FPS
    if cushion:
        obj = bpy.data.objects[CUSHION]
        for k in range(count):
            if k + 1 < len(keys.key_blocks):
                block = keys.key_blocks[k + 1]
            else:
                block = obj.shape_key_add(name=f"Native FEM state {k + 1:04d}", from_mix=False)
                block.interpolation = "KEY_LINEAR"
            block.data.foreach_set("co", local(obj, cushion_world(embedding, solid[k])).ravel())
        values = [float(b.frame) for b in keys.key_blocks]
        set_keys(curves(keys)[("eval_time", 0)], np.concatenate([[0.0], frames_of]), values)
    if pillow:
        pobj = bpy.data.objects[PILLOW]
        for k in range(count):
            if k + 1 < len(pkeys.key_blocks):
                block = pkeys.key_blocks[k + 1]
            else:
                block = pobj.shape_key_add(name=f"physical_{k:04d}", from_mix=False)
                block.interpolation = "KEY_LINEAR"
            block.data.foreach_set("co", positions[k].astype(np.float32).ravel())
        values = [float(b.frame) for b in pkeys.key_blocks[1:]]
        set_keys(curves(pkeys)[("eval_time", 0)], frames_of, values)
    if phone.rotation_mode != "QUATERNION":
        raise ValueError("Packed phone root must use quaternions")
    q, flips = quaternions(T)
    fc = curves(phone)
    for i in range(3):
        set_keys(fc[("location", i)], frames_of, T[:, i, 3])
    for i in range(4):
        set_keys(fc[("rotation_quaternion", i)], frames_of, q[:, i])
    report["phone_quaternion_sign_continuity_flips"] = flips
    scene.render.fps, scene.render.fps_base = FPS, 1.0
    scene.frame_start, scene.frame_end = 1, FRAMES
    scene.render.motion_blur_shutter = EXPOSURE_S * FPS
    if scene.node_tree:
        for node in scene.node_tree.nodes:
            if node.type == "OUTPUT_FILE":
                node.mute = True          # instance-mask EXRs are not part of the delivery

    # ---- 2b. render-side corrections of the cushion around the phone (appearance.json; physics untouched)
    look_cfg = json.loads(a.look.read_text()) if a.look else {}
    contact = look_cfg.get("cushion_render_contact", {})
    smoothing = look_cfg.get("cushion_render_smoothing", {})
    if cushion and (contact.get("enabled") or smoothing.get("enabled")):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import cushion_smoothing
        report["cushion_render_fix"] = cushion_smoothing.apply(obj, T, smoothing, contact)

    # ---- 3. every dense state replays from Blender (the cushion against the keys as written:
    #         the solver mapping exactly, or its smoothed render version when 2b ran)
    errors = {"phone": 0.0, "cushion": 0.0, "pillow": 0.0}
    for k in range(count):
        goto(frames_of[k])
        errors["phone"] = max(errors["phone"], float(np.max(np.abs(np.asarray(phone.matrix_world) - T[k]))))
        if cushion and "cushion_render_fix" in report:
            stored = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
            keys.key_blocks[k + 1].data.foreach_get("co", stored)
            errors["cushion"] = max(errors["cushion"], float(np.max(np.abs(evaluated(obj) - stored.reshape(-1, 3)))))
        elif cushion:
            errors["cushion"] = max(errors["cushion"], float(np.max(np.abs(
                evaluated(obj) - local(obj, cushion_world(embedding, solid[k]))))))
        if pillow:
            errors["pillow"] = max(errors["pillow"], float(np.max(np.abs(
                evaluated(pobj) - positions[k].astype(np.float32)))))
    report["replay_max_abs_error"] = errors
    if max(errors.values()) > TOLERANCE_M:
        raise ValueError("Rebuilt animation does not replay the native states: " + json.dumps(errors))

    # ---- 4. what Blender actually plays on each delivered frame (checked against the native states;
    #         the published ground truth is written from the cache by tools/export_ground_truth.py)
    fx = 1280 * scene.camera.data.lens / scene.camera.data.sensor_width
    check = {"fps": FPS, "frames": FRAMES,
             "camera": {"name": scene.camera.name, "matrix_world": [list(r) for r in scene.camera.matrix_world],
                        "lens_mm": scene.camera.data.lens, "sensor_width_mm": scene.camera.data.sensor_width,
                        "shift": [scene.camera.data.shift_x, scene.camera.data.shift_y],
                        "intrinsics": [[fx, 0, 640.0], [0, fx, 360.0], [0, 0, 1]]},
             "phone_matrix_world": {}}
    for f in range(1, FRAMES + 1):
        k = (f - 1) * STRIDE
        goto(f)
        played = np.asarray(phone.matrix_world)
        if float(np.max(np.abs(played - T[k]))) > TOLERANCE_M or abs(times[k] - (f - 1) / FPS) > 1e-12:
            raise ValueError(f"Frame {f} is not on the native state t={(f - 1) / FPS}")
        check["phone_matrix_world"][str(f)] = played.tolist()
    (out / "blender_replay_check.json").write_text(json.dumps(check) + "\n")

    # ---- 4b. the current look (appearance only; it refuses to move a simulated body or the camera)
    if a.look:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import realism_look
        report["look"] = realism_look.apply(a.look, a.assets)
        report["look_sha256"] = {"realism_look.py": sha(Path(__file__).resolve().parent / "realism_look.py"),
                                 "appearance.json": sha(a.look)}
    report["setup_seconds"] = time.time() - started
    if a.save_blend:
        scene.frame_set(1)
        bpy.ops.wm.save_as_mainfile(filepath=str(a.save_blend), compress=True, copy=True)
        report["saved_blend_sha256"] = sha(a.save_blend)

    # ---- 5. render
    report["rendered"] = {}
    if not a.no_render:
        scene.cycles.device = a.device
        if a.device == "GPU":
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "OPTIX"
            prefs.get_devices()
            for device in prefs.devices:
                device.use = device.type == "OPTIX"
            used = [d.name for d in prefs.devices if d.use]
            if not used:
                raise RuntimeError("No OptiX device visible to Cycles")
            report["devices"] = used
        if a.samples:
            scene.cycles.samples = a.samples
            report["smoke_test_samples"] = a.samples
        report["render_settings"] = {"engine": scene.render.engine, "samples": scene.cycles.samples,
                                     "seed": scene.cycles.seed, "use_animated_seed": scene.cycles.use_animated_seed,
                                     "denoising": scene.cycles.use_denoising,
                                     "motion_blur_shutter_frames": scene.render.motion_blur_shutter,
                                     "view_transform": scene.view_settings.view_transform, "look": scene.view_settings.look}
        (out / "frames").mkdir(exist_ok=True)
        for f in (a.frames or range(1, FRAMES + 1)):
            if not 1 <= f <= FRAMES:
                raise ValueError(f)
            t0 = time.time()
            scene.frame_set(f)
            scene.render.filepath = str(out / "frames" / f"{f:04d}.png")
            bpy.ops.render.render(write_still=True)
            report["rendered"][str(f)] = {"sha256": sha(out / "frames" / f"{f:04d}.png"), "seconds": time.time() - t0}
            print("RETIMED_FRAME", f, round(time.time() - t0, 1), flush=True)
    report["wall_seconds"] = time.time() - started
    name = ("scene_report.json" if a.no_render else
            "render_report.json" if not a.frames else f"render_report_{min(a.frames):04d}_{max(a.frames):04d}.json")
    (out / name).write_text(json.dumps(report, indent=2) + "\n")
    print("RETIME_OK", json.dumps({k: v for k, v in report.items() if k != "rendered"}), flush=True)


if __name__ == "__main__":
    main()
