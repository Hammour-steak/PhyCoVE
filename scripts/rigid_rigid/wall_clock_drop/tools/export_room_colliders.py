"""Export the static colliders of futuristic_room.glb, verified against the model.

Run inside Blender from the repository root:

    blender -b --python scripts/rigid_rigid/wall_clock_drop/tools/export_room_colliders.py

Writes ``assets/scenes/wall_clock_drop/room_colliders.json``:

* the room shell (two floor levels, four walls and the south plinth) as boxes
  derived from ray probes of the model, each probe re-run here so a moved wall
  fails the export instead of silently desynchronising the physics from the
  render;
* the furniture the crate can slide into, as axis-aligned boxes measured from
  the world bounds of the named GLB nodes.

The file records the GLB's sha256 and the probe values as provenance.
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

SCENE = "wall_clock_drop"
ASSET = "futuristic_room.glb"

# Room shell, in the model's own world frame. (name, centre, half extents)
SHELL = [
    ("floor_sunken", [-0.511, -1.8495, -0.150], [4.489, 0.7295, 0.150]),
    ("floor_platform", [-0.511, 1.0800, -0.100], [4.489, 2.2000, 0.150]),
    ("wall_south", [-0.511, -2.6690, 1.300], [4.489, 0.0900, 1.300]),
    # The plinth is the same wall's 128 mm base course; its face stands 79 mm
    # proud of the panels, so it gets its own box. Without it a body that slides
    # along the floor is pushed eight centimetres into the visible wall.
    ("plinth_south", [-0.511, -2.5500, 0.0643], [4.489, 0.0500, 0.0643]),
    ("wall_north", [-0.511, 3.3686, 1.300], [4.489, 0.0900, 1.300]),
    ("wall_west", [-5.0900, 0.3000, 1.300], [0.090, 3.0500, 1.300]),
    ("wall_east", [4.0680, 0.3000, 1.300], [0.090, 3.0500, 1.300]),
]

# Ray probes that pin the shell down: (label, origin, direction, expected hit).
PROBES = [
    ("sunken floor top", [-0.66, -2.20, 1.20], [0, 0, -1], 0.000),
    ("platform floor top", [-0.66, -0.90, 1.20], [0, 0, -1], 0.050),
    ("south wall face", [-0.60, -1.20, 1.50], [0, -1, 0], -2.579),
    ("south plinth face", [-0.60, -1.20, 0.06], [0, -1, 0], -2.500),
    ("south plinth top", [-0.60, -2.52, 0.40], [0, 0, -1], 0.1285),
    ("west wall face", [-3.00, -1.00, 1.50], [-1, 0, 0], -5.000),
    ("ceiling underside", [-0.60, -2.00, 1.20], [0, 0, 1], 2.5056),
]
PROBE_TOLERANCE = 0.012

# Furniture the crate may reach: one box per named node (a trio of stacked
# crates is unioned into one box). Clamped in z where a full bounding box
# would wall off air the crate can actually slide through.
FURNITURE = [
    ("crate_stack", ["Ammobox.003_AmmoBox_0", "Ammobox.004_AmmoBox_0", "Ammobox.005_AmmoBox_0"], None),
    ("books_on_floor", ["Books.010_Books_0"], None),
    ("office_table", ["OfficeTable_Tables_0"], None),
    ("office_chair", ["OfficeChair_OfficeChair_0"], 0.900),
]


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
    from mathutils import Vector

    root = next(p for p in Path(__file__).resolve().parents if (p / "assets").is_dir())
    glb = root / "assets" / "models" / ASSET
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    deps = bpy.context.evaluated_depsgraph_get()

    found = {o.name: o for o in bpy.data.objects if o.type == "MESH"}
    checks = []
    for label, origin, direction, expected in PROBES:
        hit, loc, _nor, _idx, obj, _mat = scene.ray_cast(deps, Vector(origin), Vector(direction))
        if not hit:
            raise RuntimeError("probe %r missed the room entirely" % label)
        axis = 2 if direction[2] else (1 if direction[1] else 0)
        value = loc[axis]
        if abs(value - expected) > PROBE_TOLERANCE:
            raise RuntimeError("probe %r landed at %.4f, expected %.4f (+/- %.3f); "
                               "the room model moved" % (label, value, expected, PROBE_TOLERANCE))
        checks.append(dict(label=label, value=round(value, 4), expected=expected, object=obj.name))

    boxes = [dict(name=n, center=c, half_extents=h, source="room shell") for n, c, h in SHELL]
    for name, nodes, z_cap in FURNITURE:
        missing = [n for n in nodes if n not in found]
        if missing:
            raise RuntimeError("futuristic_room.glb no longer contains %s" % missing)
        lo, hi = bounds([found[n] for n in nodes])
        if z_cap is not None:
            hi[2] = min(hi[2], z_cap)
        boxes.append(dict(name=name,
                          center=[round((lo[i] + hi[i]) / 2, 4) for i in range(3)],
                          half_extents=[round((hi[i] - lo[i]) / 2, 4) for i in range(3)],
                          source=" + ".join(nodes)))

    payload = dict(schema_version=1, scene=SCENE, asset=ASSET,
                   asset_sha256=hashlib.sha256(glb.read_bytes()).hexdigest(),
                   floor_z=0.0, step_y=-1.12, upper_floor_z=0.05, wall_y=-2.579,
                   plinth_y=-2.500, plinth_top_z=0.1285,
                   probes=checks, boxes=boxes)
    out = root / "assets" / "scenes" / SCENE / "room_colliders.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)
    print("boxes:", len(boxes), "probes:", len(checks))
    for box in boxes:
        print("  %-16s c=%s h=%s" % (box["name"], box["center"], box["half_extents"]))


if __name__ == "__main__":
    main()
