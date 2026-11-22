"""Blender: export the fitted bathtub shell's profile rings (appearance/bathroom_finish.py) as geometry/tub_shell.npz, the
simulation's bathtub (its interior surface and rim), and list the room's objects next to it.
usage: blender -b --python tools/export_tub_shell.py -- [OUT_NPZ]"""
import json, sys
from pathlib import Path
import bpy, numpy as np
SCENE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCENE / "appearance"), str(SCENE.parents[1])]
from pcve_assets import scene_asset
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = argv[0] if argv else str(SCENE / "geometry/tub_shell.npz")
import bathroom_finish
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
before = set(scene.objects)
bpy.ops.import_scene.gltf(filepath=str(scene_asset(SCENE, "assets/sketchfab_bathroom/bathroom.glb")))
imported = [o for o in scene.objects if o not in before]
root = bpy.data.objects.new("root", None); scene.collection.objects.link(root)
s = set(imported)
for o in [o for o in imported if o.parent not in s]:
    m = o.matrix_world.copy(); o.parent = root; o.matrix_world = m
root.location = (1.6419553756713867, 0.8095061779022217, 0.007460540160536766)
bpy.context.view_layer.update()
led = bathroom_finish.smooth_tub(scene, bathroom_finish.FINISH_SETTINGS)
shell = bpy.data.objects["PCVE_BathtubShell"]
v = np.array([tuple(shell.matrix_world @ x.co) for x in shell.data.vertices])
n = bathroom_finish.FINISH_SETTINGS["tub_radial_segments"]
np.savez(out, rings=v.reshape(-1, n, 3), center=np.array([0.0132777, 0.0108457]))
rows = []
for o in scene.objects:
    if o.type == "MESH" and not o.hide_render:
        bb = np.array([o.matrix_world @ __import__("mathutils").Vector(c) for c in o.bound_box])
        rows.append((o.name, [round(x, 3) for x in bb.min(0)], [round(x, 3) for x in bb.max(0)], [m.name for m in o.data.materials][:3]))
rows.sort(key=lambda r: -np.prod(np.array(r[2]) - np.array(r[1]) + 1e-3))
Path(out).with_suffix(".objects.json").write_text(json.dumps(rows, indent=0))
print("EXPORTED", v.shape, led["profile_rings"], len(rows))
