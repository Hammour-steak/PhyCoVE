"""Blender 4.3 / Cycles: render a simulated case in the modern-kitchen template
(assets/scenes/cooking_oil_pan/scene_template.blend).

Removes the template's Mantaflow inflow/domain objects, applies the daylight look (look_cooking_oil_pan.py) and shows each
frame's oil surface (surface_cooking_oil_pan.py, pan-local coordinates, placed at the pan origin) with its per-vertex velocity for
motion blur (180-degree shutter). Oil material: clear dielectric (IOR 1.47) whose colour comes from volume absorption,
so a 2 mm film over the dark pan is pale and a thick stream golden.
usage: blender -b assets/scenes/cooking_oil_pan/scene_template.blend --python render_cooking_oil_pan.py --
       --run RUN --out-dir DIR --frames 1 2 ... [--samples 64] [--mesh-dir meshes]"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import asset
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
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
from mathutils import Matrix

p = argparse.ArgumentParser()
p.add_argument("--run", type=Path, required=True)
p.add_argument("--out-dir", type=Path, required=True)
p.add_argument("--frames", type=int, nargs="+", required=True)
p.add_argument("--samples", type=int, default=64)
p.add_argument("--mesh-dir", default="meshes")
p.add_argument("--no-pan", action="store_true",
               help="DELETE pan: hide the frying pan (body, handle, bolt, rivets); the oil, simulated on the hob's flat glass "
                    "top, is placed on that glass")
a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
ORIGIN = (1.1, 3.405, 1.18233)                     # pan centre on its interior floor (world)

HERE = Path(__file__).resolve().parent
if bpy.data.objects.get("PCVE_BlenderKit_PhotorealisticFryingPan") is None:      # started without the template
    bpy.ops.wm.open_mainfile(filepath=str(asset("scenes/cooking_oil_pan/scene_template.blend")))
scene = bpy.context.scene
for name in ("OilInflow", "OilFluidDomain"):          # Mantaflow objects (their visibility is keyframed)
    ob = bpy.data.objects.get(name)
    if ob:
        bpy.data.objects.remove(ob, do_unlink=True)

mat = bpy.data.materials.new("Genesis cooking oil")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1)
bsdf.inputs["Roughness"].default_value = 0.03
bsdf.inputs["IOR"].default_value = 1.47
bsdf.inputs["Transmission Weight"].default_value = 1.0
absn = nt.nodes.new("ShaderNodeVolumeAbsorption")
# sigma_a = density (1 - colour) per metre = (8, 40, 220): transmittance over 5 mm (0.96, 0.82, 0.33), over 2 mm (0.98, 0.92, 0.64)
absn.inputs["Color"].default_value = (0.965, 0.826, 0.043, 1)
absn.inputs["Density"].default_value = 230.0
nt.links.new(absn.outputs["Volume"], nt.nodes["Material Output"].inputs["Volume"])

import look_cooking_oil_pan as look
look.apply()

me0 = bpy.data.meshes.new("Oil_empty")
oil = bpy.data.objects.new("GenesisOil", me0)
scene.collection.objects.link(oil)
origin = ORIGIN
if a.no_pan:
    for name in ("PCVE_BlenderKit_PhotorealisticFryingPan", "Cube.014", "Bolt", "Circle.044"):
        bpy.data.objects[name].hide_render = bpy.data.objects[name].hide_viewport = True
    glass = bpy.data.objects["PCVE_HobGlassTop"]
    origin = (ORIGIN[0], ORIGIN[1], max((glass.matrix_world @ v.co).z for v in glass.data.vertices))
oil.matrix_world = Matrix.Translation(origin)
oil.data.materials.append(mat)
_retired = []


def load_frame(scene_, depsgraph=None):
    f = scene_.frame_current
    path = a.run / a.mesh_dir / f"oil_{f:04d}.npz"
    if not path.exists():
        return
    with np.load(path) as d:
        v, t, n, vel = d["vertices"], d["triangles"], d["normals"], d["velocity"]
    me = bpy.data.meshes.new(f"Oil_{f:04d}")
    me.from_pydata(v.tolist(), [], t.tolist())
    me.update()
    me.materials.append(mat)
    if len(v):
        me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
        me.normals_split_custom_set_from_vertices(n.astype(float).tolist())
        attr = me.attributes.new("velocity", "FLOAT_VECTOR", "POINT")
        attr.data.foreach_set("vector", vel.astype(np.float32).ravel())
    # free the mesh retired one frame ago (the depsgraph may still reference the current one in this callback)
    while len(_retired) > 1:
        old = _retired.pop(0)
        if old.users == 0:
            bpy.data.meshes.remove(old)
    _retired.append(oil.data)
    oil.data = me


for h in list(bpy.app.handlers.frame_change_pre):
    if getattr(h, "__name__", "") == "load_frame":
        bpy.app.handlers.frame_change_pre.remove(h)
bpy.app.handlers.frame_change_pre.append(load_frame)

prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"; prefs.get_devices()
for dev in prefs.devices:
    dev.use = dev.type == "OPTIX"
scene.cycles.device = "GPU"
scene.cycles.samples = a.samples
scene.render.use_motion_blur = True
scene.render.motion_blur_shutter = 0.5
scene.render.use_persistent_data = False
out = a.out_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
times = {}
for f in a.frames:
    scene.frame_set(f)
    t0 = time.monotonic()
    scene.render.filepath = str(out / f"frame_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    times[f] = time.monotonic() - t0
    print("OIL_FRAME=" + json.dumps({"frame": f, "seconds": round(times[f], 2)}), flush=True)
(out / f"render_report_{min(a.frames):04d}_{max(a.frames):04d}.json").write_text(json.dumps({"seconds": times}, indent=2) + "\n")
