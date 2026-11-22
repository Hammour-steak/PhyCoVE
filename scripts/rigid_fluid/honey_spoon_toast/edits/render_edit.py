"""Insert reconstructed Genesis honey meshes and render the accepted camera."""

from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import bpy
import numpy as np


def parse_args():
    av = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input-blend", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--frames", nargs="*", type=int)
    p.add_argument("--resolution", nargs=2, type=int, default=(1280, 720))
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--engine", choices=("cycles", "eevee"), default="cycles")
    p.add_argument("--mesh-subdir", default="meshes")
    p.add_argument("--extra-mesh-subdir",
                   help="Optional physically separate reduced-model mesh cache")
    p.add_argument("--encode", action="store_true")
    p.add_argument("--no-honey", action="store_true")
    return p.parse_args(av)


def replace_mesh(obj, vertices, triangles, frame):
    old = obj.data
    mesh = bpy.data.meshes.new(f"PCVE_HoneyMesh_{frame:04d}")
    mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
    mesh.update()
    for mat in old.materials:
        if mat:
            mesh.materials.append(mat)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj.data = mesh
    if old and old.users == 0:
        bpy.data.meshes.remove(old)


args = parse_args()
bpy.ops.wm.open_mainfile(filepath=str(args.input_blend.resolve()))
scene = bpy.context.scene
scene.render.use_persistent_data = True
scene.render.resolution_x, scene.render.resolution_y = args.resolution
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.fps = 24
if args.engine == "cycles":
    scene.render.engine = "BLENDER_EEVEE_NEXT" if not hasattr(scene, "cycles") else "CYCLES"
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = backend
                prefs.get_devices()
                usable = [d for d in prefs.devices if d.type == backend]
                if usable:
                    for device in prefs.devices:
                        device.use = device in usable
                    scene.cycles.device = "GPU"
                    print("CYCLES_DEVICE",backend,[d.name for d in usable],flush=True)
                    break
            except (TypeError, RuntimeError):
                pass
        else:
            scene.cycles.device = "CPU"
            print("CYCLES_DEVICE CPU",flush=True)
else:
    scene.render.engine = "BLENDER_EEVEE_NEXT"

report_path = args.run / "simulation_report.json"
if report_path.exists():
    report = json.loads(report_path.read_text())
elif args.frames and "PCVE_SpoonRig" in bpy.data.objects:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from spoon_reservoir_geometry import tilt_at
    report = {"numerics":{"frames":max(args.frames)}, "frames":[
        {"spoon_tilt_deg":tilt_at(f/24)} for f in range(max(args.frames))]}
else:
    raise RuntimeError("No completed simulation report")
frames = args.frames or list(range(1, int(report["numerics"]["frames"]) + 1))
args.out_dir.mkdir(parents=True, exist_ok=True)
if args.no_honey:
    assert "PCVE_Honey" not in bpy.data.objects
    honey = None
else:
    honey = bpy.data.objects["PCVE_Honey"]
rows = []
for frame in frames:
    target = args.out_dir / f"frame_{frame:04d}.png"
    if target.exists() and target.stat().st_size > 0:
        continue
    if honey is not None:
        with np.load(args.run / args.mesh_subdir / f"honey_{frame:04d}.npz") as state:
            vertices, triangles = state["vertices"].astype(float), state["triangles"].astype(int)
        if args.extra_mesh_subdir:
            with np.load(args.run / args.extra_mesh_subdir / f"honey_{frame:04d}.npz") as extra:
                ev,et=extra["vertices"].astype(float),extra["triangles"].astype(int)
            triangles=np.concatenate((triangles,et+len(vertices)))
            vertices=np.concatenate((vertices,ev))
        replace_mesh(honey, vertices, triangles, frame)
    if "PCVE_SpoonRig" in bpy.data.objects:
        angle = report["frames"][frame-1]["spoon_tilt_deg"]
        bpy.data.objects["PCVE_SpoonRig"].rotation_euler[1] = math.radians(angle)
    scene.frame_set(frame)
    scene.render.filepath = str(target.resolve())
    tick = time.monotonic()
    bpy.ops.render.render(write_still=True)
    rows.append({"frame": frame, "seconds": time.monotonic() - tick, "file": target.name})
    print("RENDER", frame, rows[-1]["seconds"], flush=True)
(args.out_dir / "render_report.json").write_text(json.dumps({"frames": rows}, indent=2) + "\n")
if args.encode and frames == list(range(1, int(report["numerics"]["frames"]) + 1)):
    subprocess.run(["ffmpeg", "-y", "-framerate", "24", "-i", str(args.out_dir / "frame_%04d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                    str(args.out_dir / "honey_spoon_toast.mp4")], check=True)
