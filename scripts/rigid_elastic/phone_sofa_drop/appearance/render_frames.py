"""Blender: render frames of a scene saved by retime_packed_scene.py --look ... --save-blend.

Run as  blender -b CASE/scene.blend --disable-autoexec --python render_frames.py --
        --out DIR --frames F [F ...] [--device GPU|CPU]

The saved scene already carries the 4 s / 24 FPS animation (checked against the native states
when it was built) and the current look, so this only re-checks clock, resolution, shutter and
look, and renders with the settings stored in the scene. Frames go to DIR/frames/NNNN.png and a
worker report DIR/render_worker_FIRST_LAST.json lists every frame's sha256, host and device.
All frames of one case must come from one device type (the packager refuses mixed cases).
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import time

import bpy


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(prog="render_frames.py")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", type=int, nargs="+", required=True)
    p.add_argument("--device", choices=("GPU", "CPU"), default="GPU")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    scene = bpy.context.scene
    if (bpy.app.version_string != "4.3.2" or (scene.frame_start, scene.frame_end) != (1, 96)
            or scene.render.fps / scene.render.fps_base != 24
            or (scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage) != (1280, 720, 100)
            or abs(scene.render.motion_blur_shutter - 0.08) > 1e-6):
        raise ValueError("Expected a retimed 24 FPS phone_sofa_drop scene")
    if "Look room shell" not in bpy.data.collections or scene.render.use_persistent_data:
        raise ValueError("The saved scene does not carry the current look")
    scene.cycles.device = a.device
    devices = ["CPU"]
    if a.device == "GPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        devices = [d.name for d in prefs.devices if d.use]
        if not devices:
            raise RuntimeError("No OptiX device visible to Cycles")
    out = a.out.resolve()
    (out / "frames").mkdir(parents=True, exist_ok=True)
    report = {"blend_sha256": sha(bpy.data.filepath),
              "host": socket.gethostname(), "device_type": a.device, "devices": devices,
              "blender": bpy.app.version_string,
              "settings": {"samples": scene.cycles.samples, "adaptive_threshold": scene.cycles.adaptive_threshold,
                           "seed": scene.cycles.seed, "use_animated_seed": scene.cycles.use_animated_seed,
                           "denoising": scene.cycles.use_denoising, "denoiser": scene.cycles.denoiser,
                           "motion_blur": scene.render.use_motion_blur,
                           "motion_blur_shutter_frames": scene.render.motion_blur_shutter,
                           "persistent_data": scene.render.use_persistent_data,
                           "view_transform": scene.view_settings.view_transform, "look": scene.view_settings.look,
                           "exposure": scene.view_settings.exposure},
              "frames": {}}
    for f in a.frames:
        if not 1 <= f <= 96:
            raise ValueError(f)
        t0 = time.time()
        scene.frame_set(f)
        target = out / "frames" / f"{f:04d}.png"
        scene.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        report["frames"][str(f)] = {"sha256": sha(target), "seconds": round(time.time() - t0, 2)}
        print("RENDERED_FRAME", f, round(time.time() - t0, 1), flush=True)
    (out / f"render_worker_{min(a.frames):04d}_{max(a.frames):04d}.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
