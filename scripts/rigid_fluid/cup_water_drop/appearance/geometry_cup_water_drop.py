"""Blender: export the hero mug for the simulation.

usage: blender -b coffee_cup_set.blend --python geometry_cup_water_drop.py -- <geometry_dir>
Writes cup_local.obj (the BlenderKit MUG.004 with its subdivision modifier evaluated at render level: 5920 vertices,
11840 triangles, watertight) and cup_export.json. The cup frame is the one the renderer places the mug in: x/y centred
on the asset's coffee surface (Circle.003), origin at the mug's mid-height, scaled to 72 mm tall."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layout_cup_water_drop as layout  # noqa: E402

out = Path(sys.argv[sys.argv.index("--") + 1])
out.mkdir(parents=True, exist_ok=True)
mug = bpy.data.objects[layout.CUP_ASSET_OBJECT]
coffee = bpy.data.objects[layout.CUP_ASSET_COFFEE]
for m in mug.modifiers:
    if m.type == "SUBSURF":
        m.levels = m.render_levels
dg = bpy.context.evaluated_depsgraph_get()


def world_mesh(o):
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    v = [o.matrix_world @ x.co for x in me.vertices]
    t = [tuple(x.vertices) for x in me.loop_triangles]
    ev.to_mesh_clear()
    return v, t


cv, _ = world_mesh(coffee)
mv, mt = world_mesh(mug)
lo = Vector([min(p[i] for p in mv) for i in range(3)])
hi = Vector([max(p[i] for p in mv) for i in range(3)])
clo = Vector([min(p[i] for p in cv) for i in range(3)])
chi = Vector([max(p[i] for p in cv) for i in range(3)])
centre = Vector(((clo.x + chi.x) / 2, (clo.y + chi.y) / 2, (lo.z + hi.z) / 2))
scale = layout.CUP_HEIGHT / (hi.z - lo.z)
with open(out / "cup_local.obj", "w") as f:
    for p in mv:
        q = (p - centre) * scale
        f.write(f"v {q.x:.7f} {q.y:.7f} {q.z:.7f}\n")
    for t in mt:
        f.write("f %d %d %d\n" % (t[0] + 1, t[1] + 1, t[2] + 1))
json.dump({"scale": scale, "centre": list(centre), "n_vertices": len(mv), "n_triangles": len(mt)},
          open(out / "cup_export.json", "w"), indent=1)
print("EXPORTED", len(mv), "vertices", len(mt), "triangles, scale", scale)
