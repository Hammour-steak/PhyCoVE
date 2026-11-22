"""Blender 4.3 / Cycles: render a simulated case in the milk scene's template (assets/scenes/milk_pitcher_glass/milk_carton_kitchen.blend).

The template is the daylight kitchen with the clear handled glass, the opaque 1 L milk carton whose spout exit is the
simulator's emitter, and an empty 'Milk' object (whole-milk material, subsurface scattering on the closed meshes).
Each frame's surface (surface_milk_pitcher_glass.py) is swapped into 'Milk' with its per-vertex velocity for motion
blur (180-degree shutter). --no-milk renders the scene without milk (DELETE milk). Cycles renders on the GPU with OptiX;
--device CUDA uses the CUDA backend instead (for hosts where OptiX crashes).
usage: blender -b assets/scenes/milk_pitcher_glass/milk_carton_kitchen.blend --python render_milk_pitcher_glass.py --
       --run RUN --out-dir DIR --frames 1 2 ... [--samples 64] [--no-milk] [--mesh-dir meshes] [--device OPTIX|CUDA]"""
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import asset
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END
import argparse
import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np

p = argparse.ArgumentParser()
p.add_argument("--run", type=Path, required=True)
p.add_argument("--out-dir", type=Path, required=True)
p.add_argument("--frames", type=int, nargs="+", required=True)
p.add_argument("--samples", type=int, default=64)
p.add_argument("--mesh-dir", default="meshes")
p.add_argument("--no-milk", action="store_true")
p.add_argument("--device", choices=("OPTIX", "CUDA"), default="OPTIX", help="Cycles GPU backend (default OPTIX)")
a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])

if "milk_template" not in bpy.context.scene.keys():          # started without the template (e.g. the unified entry)
    bpy.ops.wm.open_mainfile(filepath=str(asset("scenes/milk_pitcher_glass/milk_carton_kitchen.blend")))
scene = bpy.context.scene
assert "milk_template" in scene.keys(), "assets/scenes/milk_pitcher_glass/milk_carton_kitchen.blend did not load"
milk = bpy.data.objects["Milk"]
mat = milk.data.materials[0]
milk.hide_render = a.no_milk
_retired = []


def load_frame(scene_, depsgraph=None):
    path = a.run / a.mesh_dir / f"milk_{scene_.frame_current:04d}.npz"
    if a.no_milk or not path.exists():
        return
    with np.load(path) as d:
        v, t, n, vel = d["vertices"], d["triangles"], d["normals"], d["velocity"]
    me = bpy.data.meshes.new(f"Milk_{scene_.frame_current:04d}")
    me.from_pydata(v.tolist(), [], t.tolist())
    me.update()
    me.materials.append(mat)
    if len(v):
        me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
        me.normals_split_custom_set_from_vertices(n.astype(float).tolist())
        attr = me.attributes.new("velocity", "FLOAT_VECTOR", "POINT")
        attr.data.foreach_set("vector", vel.astype(np.float32).ravel())
    # free the mesh retired one frame ago (the depsgraph may still reference the current one in this callback);
    # keeping every frame made Blender grow to ~53 GB at 700k particles
    while len(_retired) > 1:
        old = _retired.pop(0)
        if old.users == 0:
            bpy.data.meshes.remove(old)
    _retired.append(milk.data)
    milk.data = me


bpy.app.handlers.frame_change_pre.clear()
bpy.app.handlers.frame_change_pre.append(load_frame)
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = a.device
prefs.get_devices()
for dev in prefs.devices:
    dev.use = dev.type == a.device
scene.cycles.device = "GPU"
scene.cycles.samples = a.samples
scene.render.use_motion_blur = True
scene.render.motion_blur_shutter = 0.5
scene.render.image_settings.file_format = "PNG"
out = a.out_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
times = {}
for f in a.frames:
    scene.frame_set(f)
    t0 = time.monotonic()
    scene.render.filepath = str(out / f"frame_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    times[f] = round(time.monotonic() - t0, 2)
    print("MILK_FRAME=" + json.dumps({"frame": f, "seconds": times[f]}), flush=True)
(out / f"render_report_{min(a.frames):04d}_{max(a.frames):04d}.json").write_text(json.dumps({"seconds": times}, indent=2) + "\n")
