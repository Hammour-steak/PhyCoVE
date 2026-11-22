"""Blender 4.3: export the restaurant stage's cup set as simulation geometry (cup-centred x/y, world z).

usage: blender -b loft_restaurant_stage.blend --python geometry_coffee_ice_drop.py -- <geometry_dir>
Writes cup_world.obj (MUG.004), saucer_world.obj (PCVE_CoffeeCupSet), spoon_world.obj, beans_world.obj and
geom_info.json (bounds, cup centre = centre of the authored coffee surface Circle.028). The measured cavity and the
solid saucer collider are derived from these by cavity_coffee_ice_drop.py.
"""
import json
import sys
from pathlib import Path

import bpy

out = Path(sys.argv[sys.argv.index("--") + 1])
out.mkdir(parents=True, exist_ok=True)
dg = bpy.context.evaluated_depsgraph_get()


def world_mesh(names):
    verts, tris, off = [], [], 0
    for name in names:
        obj = bpy.data.objects[name]
        ev = obj.evaluated_get(dg)
        mesh = ev.to_mesh()
        mesh.calc_loop_triangles()
        verts += [obj.matrix_world @ v.co for v in mesh.vertices]
        tris += [tuple(i + off for i in t.vertices) for t in mesh.loop_triangles]
        off += len(mesh.vertices)
        ev.to_mesh_clear()
    return verts, tris


info = {}
for name in ("Circle.028", "MUG.004", "PCVE_IceCube_16mm", "PCVE_CoffeeCupSet", "Plane.049", "spoon.000"):
    if bpy.data.objects.get(name) is None:
        info[name] = None
        continue
    v, _ = world_mesh([name])
    info[name] = {"lo": [min(p[i] for p in v) for i in range(3)], "hi": [max(p[i] for p in v) for i in range(3)], "nverts": len(v)}
coffee = info["Circle.028"]
cx = (coffee["lo"][0] + coffee["hi"][0]) / 2
cy = (coffee["lo"][1] + coffee["hi"][1]) / 2
info["cup_center_xy"] = [cx, cy]

beans = [o.name for o in bpy.data.objects if o.name.startswith("coffee bean")]
for fname, names in (("cup_world.obj", ["MUG.004"]), ("saucer_world.obj", ["PCVE_CoffeeCupSet"]),
                     ("spoon_world.obj", ["spoon.000"]), ("beans_world.obj", beans)):
    v, t = world_mesh(names)
    with open(out / fname, "w") as f:
        for p in v:
            f.write(f"v {p.x - cx:.6f} {p.y - cy:.6f} {p.z:.6f}\n")
        for tri in t:
            f.write("f %d %d %d\n" % (tri[0] + 1, tri[1] + 1, tri[2] + 1))
    print("EXPORTED", fname, len(v))
json.dump(info, open(out / "geom_info.json", "w"), indent=1)
