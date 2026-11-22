"""Export the static colliders of modern_kitchen.glb, verified against the model.

Run inside the Blender/bpy runtime:

    blender -b --python-exit-code 1 --python scripts/rigid_rigid/kitchen_bowl_fall/tools/export_room_colliders.py

Writes ``assets/scenes/kitchen_bowl_fall/room_colliders.json``:

* the room shell (floor + four walls + ceiling) and the island counter as boxes
  derived from the world bounds of the named GLB nodes, after the exact
  transform the renderer applies (scale 0.5, quarter turn about Z, translate).
* a set of ray probes re-run here so a moved surface fails the export instead
  of silently desynchronising the physics from the render.

The open wall cupboard the bowl falls out of is programme-built (both in the
renderer and the solver) and is NOT part of this export -- the GLB's wall units
are door panels with nothing behind them, so the carcass, its shelf and its
open door are created directly from ``scene_geometry`` (``CABINET_*``,
``BOARD_TOP_Z``, ``SHELF_Z``, ``DOOR_OPEN_DEG``).

The file records the GLB's sha256 so a changed model can be detected.
"""
# PCVE_UNIFIED_ENTRY_BEGIN
import sys as _export_sys
from pathlib import Path as _ExportPath
_SCENE_DIR = _ExportPath(__file__).resolve().parents[1]
for _sub in (_SCENE_DIR.parents[1], _SCENE_DIR, _SCENE_DIR / "physics"):
    if _sub.is_dir() and str(_sub) not in _export_sys.path:
        _export_sys.path.insert(1, str(_sub))
# PCVE_UNIFIED_ENTRY_END

import hashlib
import json
from pathlib import Path

SCENE = "kitchen_bowl_fall"
ASSET = "modern_kitchen.glb"


def bounds(objects):
    from mathutils import Vector
    pts = []
    for o in objects:
        pts += [o.matrix_world @ Vector(corner) for corner in o.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi


def main():
    import bpy
    from mathutils import Vector, Matrix

    root = next(p for p in Path(__file__).resolve().parents if (p / "assets").is_dir())
    glb = root / "assets" / "models" / ASSET
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    bpy.context.view_layer.update()

    import math
    transform = Matrix.Translation(Vector((-0.65, 0, 0))) @ Matrix.Rotation(math.pi / 2, 4, 'Z') @ Matrix.Scale(0.5, 4)
    for o in bpy.data.objects:
        if o.parent is None and o.type in {'MESH', 'EMPTY'}:
            o.matrix_world = transform @ o.matrix_world
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    deps = bpy.context.evaluated_depsgraph_get()

    meshes = {o.name: o for o in bpy.data.objects if o.type == 'MESH'}

    def node_bounds(name):
        return bounds([meshes[name]])

    floor_lo, floor_hi = node_bounds('Floor_Wall_0')
    struct_lo, struct_hi = node_bounds('Structure_Wall_0')
    counter_lo, counter_hi = node_bounds('Counters_Counter_0')
    hob_lo, hob_hi = node_bounds('Hob_Hob_0')
    tile_lo, tile_hi = node_bounds('Tiles_Tiles_0')

    # The island counter: a thin bar at y ~ 0. Its true footprint (the raised
    # surface the tableware and the falling bowl touch) is the y ~ -0.25..0.25
    # strip, not the full bounding box (which also spans the wall-side counters).
    counter_top_z = counter_hi[2]

    probes = [
        ("counter top",      [-1.14, 0.27, 1.60], [0, 0, -1], counter_top_z),
        ("wall counter top", [-1.00, 2.58, 1.60], [0, 0, -1], counter_top_z),
        ("hob glass top",    [-0.30, 3.00, 1.60], [0, 0, -1], hob_hi[2]),
        ("floor top",        [-0.40, -1.00, 1.00], [0, 0, -1], floor_hi[2]),
        # The kitchen does not run to the far side of the flat: it stops at a
        # real wall behind the sink (below). The building's outer shell, which is
        # what the bounds of Structure_Wall_0 give, is one room further right.
        ("kitchen end wall inner face", [1.00, 2.80, 1.30], [1, 0, 0], 1.496),
        ("kitchen end wall outer face", [2.40, 2.80, 1.30], [-1, 0, 0], 1.740),
        ("kitchen end wall front face", [1.62, 1.20, 1.30], [0, 1, 0], 2.498),
        ("kitchen open in front of it", [-0.40, 2.30, 1.30], [1, 0, 0], floor_hi[0]),
    ]
    PROBE_TOLERANCE = 0.012
    checks = []
    for label, origin, direction, expected in probes:
        hit, loc, _nor, _idx, obj, _mat = scene.ray_cast(deps, Vector(origin), Vector(direction))
        if not hit:
            raise RuntimeError("probe %r missed the kitchen entirely" % label)
        axis = 2 if direction[2] else (1 if direction[1] else 0)
        value = loc[axis]
        if abs(value - expected) > PROBE_TOLERANCE:
            raise RuntimeError("probe %r landed at %.4f, expected %.4f (+/- %.3f); "
                               "the kitchen model moved" % (label, value, expected, PROBE_TOLERANCE))
        checks.append(dict(label=label, value=round(value, 4), expected=round(expected, 4), object=obj.name))

    def box(name, lo, hi, source):
        center = [(lo[i] + hi[i]) / 2 for i in range(3)]
        half = [(hi[i] - lo[i]) / 2 for i in range(3)]
        return dict(name=name, center=[round(v, 4) for v in center],
                    half_extents=[round(v, 4) for v in half], source=source)

    boxes = [
        # The floor slab: give it a minimum thickness so the collision box is not degenerate.
        box("floor", [floor_lo[0], floor_lo[1], floor_lo[2] - 0.05],
            [floor_hi[0], floor_hi[1], floor_hi[2]], "Floor_Wall_0"),
        # The island counter surface: a thin slab over the y ~ 0 bar.
        box("counter", [counter_lo[0], -0.30, counter_lo[2]],
            [counter_hi[0], 0.30, counter_top_z], "Counters_Counter_0 (island top)"),
        # The wall-side counter run under the cupboard: measured top-surface
        # vertices put it at y 2.509..3.466, the same quartz height as the island.
        box("counter_wall", [counter_lo[0], 2.509, counter_lo[2]],
            [counter_hi[0], counter_hi[1], counter_top_z], "Counters_Counter_0 (wall run)"),
        # The hob glass sits ~11 mm proud of the quartz; the bowls stand on it.
        # Its top is the model's own measured surface, not a re-probe: the probe
        # can land on the surrounding stainless frame.
        box("hob", [hob_lo[0], hob_lo[1], counter_top_z],
            [hob_hi[0], hob_hi[1], hob_hi[2]], "Hob_Hob_0"),
        # The tiled splashback the cupboard hangs from.
        box("wall_tiles", [tile_lo[0], tile_lo[1], tile_lo[2]],
            [tile_hi[0], tile_lo[1] + 0.06, tile_hi[2]], "Tiles_Tiles_0 (splashback)"),
        # The kitchen's own right-hand end: a 0.244 m wall behind the sink, from
        # the counter front back into the splashback and from the floor to the
        # ceiling. It is NOT the building's outer wall (x 3.261, one room away);
        # without this box a bowl shoved down the counter would slide through
        # into the next room.
        box("wall_kitchen_end", [1.496, 2.498, floor_hi[2]],
            [1.740, tile_hi[1], tile_hi[2]], "Structure_Wall_0 (kitchen end wall)"),
        # Four walls and the ceiling to catch anything that flies out.
        box("wall_back", [struct_lo[0], struct_hi[1] - 0.06, 0.0],
            [struct_hi[0], struct_hi[1], struct_hi[2]], "Structure_Wall_0 (back wall)"),
        box("wall_front", [struct_lo[0], struct_lo[1], 0.0],
            [struct_hi[0], struct_lo[1] + 0.06, struct_hi[2]], "Structure_Wall_0 (front wall)"),
        box("wall_left", [struct_lo[0], struct_lo[1], 0.0],
            [struct_lo[0] + 0.06, struct_hi[1], struct_hi[2]], "Structure_Wall_0 (left wall)"),
        # The right-hand wall of the *room*: its inner face is the floor/ceiling
        # edge (3.074), not the outer face of the building shell (3.321).
        box("wall_right", [floor_hi[0], struct_lo[1], 0.0],
            [struct_hi[0], struct_hi[1], struct_hi[2]], "Structure_Wall_0 (right wall)"),
    ]

    payload = dict(schema_version=1, scene=SCENE, asset=ASSET,
                   asset_sha256=hashlib.sha256(glb.read_bytes()).hexdigest(),
                   counter_z=counter_top_z, floor_z=floor_hi[2], hob_top_z=hob_hi[2],
                   probes=checks, boxes=boxes)
    out = root / "assets" / "scenes" / SCENE / "room_colliders.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)
    print("counter_z =", counter_top_z, " floor_z =", floor_hi[2])
    print("boxes:", len(boxes), "probes:", len(checks))
    for b in boxes:
        print("  %-16s c=%s h=%s" % (b["name"], b["center"], b["half_extents"]))


if __name__ == "__main__":
    main()
