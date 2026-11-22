"""Export static bathroom fixture colliders from big_project.glb.

Run inside the Blender/bpy runtime:

    blender -b --python scripts/rigid_rigid/bathroom_tennis_throw/tools/export_bathroom_colliders.py

Writes ``assets/scenes/bathroom_tennis_throw/bathroom_colliders.json``:
one axis-aligned box per bathroom fixture the tennis ball can hit, plus the
room boundary walls and the marble skirting that keep the ball inside the
visible shell. Fixture boxes are measured from the GLB's named source
objects; the wall and skirting faces are RAYCAST out of the imported shell so
they land on the surface the camera actually sees (an AABB-based guess put the
south wall 44 cm too deep, and the ball spent 10 frames of the clip buried
inside it). The file records the GLB's sha256 so the physics side can detect
a stale export.
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

SCENE = "bathroom_tennis_throw"
ASSET = "big_project.glb"

# Fixture boxes measured from the GLB (world bounds of the named source
# objects, trimmed to the walkable action area). Coordinates in metres,
# Blender/world frame, floor top at z = 0.042.
FIXTURES = [
    # name, center, half extents, source objects
    ("toilet_bowl", [1.12, -4.07, 0.5985], [0.60, 0.70, 0.5565], "Cube.030_Bathtub maarble_0 + Cube.031_Bathtub maarble_0"),
    ("vanity_counter", [-2.55, -3.99, 0.806], [0.985, 0.725, 0.764], "Cube.002_wood sink_0 (+ shelves Cube.006/007)"),
    ("vanity_backsplash", [-2.55, -3.99, 3.18], [1.185, 0.755, 1.61], "Cube.003_black plastic_0, above the counter"),
    ("pouf_left", [3.29, -2.22, 0.145], [0.37, 0.215, 0.11], "Slippers_rubber_1 ( Wesley lounge set )"),
    ("pouf_right", [3.29, -1.87, 0.145], [0.325, 0.275, 0.11], "Slippers_leather_right ( Wesley lounge set )"),
    # Eastern shower zone: sliding glass door wall (two overlapping panes) and
    # the north-south fixed screen, both solid in physics like real glazing.
    ("glass_shower_door", [8.345, -1.995, 2.222], [2.624, 0.032, 2.036], "Cube.025 + Cube.014_improved glass_0 (sliding panes)"),
    ("glass_screen_south", [4.563, -3.8835, 2.222], [0.031, 0.8805, 2.036], "Cube.026 + Cube.019_improved glass_0 (N-S screen)"),
    # Bottom metal track of the glass enclosure (Cube.027_black plastic_0):
    # the frame's own AABB spans the whole enclosure, so only the low rail is
    # modelled. The rail is a chamfered profile: measured at roll height
    # (z ~ 0.17) its outer faces are x = 4.6436 (N-S rail, east side) and
    # y = -1.9155 (door rail, north side). Boxes reach the visible face and
    # grow inward, so the ball stops on the metal instead of sinking 30 mm
    # into it.
    ("glass_door_frame_rail", [7.728, -2.013, 0.176], [3.263, 0.098, 0.041], "Cube.027_black plastic_0 bottom track, north face y=-1.9155"),
    ("glass_screen_frame_rail", [4.612, -3.389, 0.176], [0.032, 1.359, 0.041], "Cube.027_black plastic_0 N-S bottom track, east face x=4.6436"),
    ("bathtub_east", [6.9915, 1.032, 0.72], [2.2795, 2.413, 0.685], "bathtub_Bathtub maarble_0"),
    # Walk-in shower slab (Cube.035). It is NOT a flat box: downward rays hit
    # z = 0.1357 on a raised marble border and z = 0.0538 across the recessed
    # floor inside it, so the AABB's top face floats 82 mm above the surface the
    # ball actually lands on. One box therefore made the ball bounce on an
    # invisible plane -- 0.8 of its own diameters -- everywhere in the shower.
    # Model it as the floor it is, plus the four borders that really are that
    # tall. Border widths were measured by walking a ray until the surface drops
    # below the rim: 260 mm west, 135 mm east, 80 mm south, 260 mm north.
    # Every box grows down to z = -0.05 so a fast ball cannot tunnel through a
    # 12 mm slab.
    ("shower_base", [7.771, -3.4415, 0.0019], [3.059, 1.2965, 0.0519], "Cube.035_Bathtub maarble_0 recessed floor, measured top z=0.0538"),
    ("shower_rim_west", [4.582, -3.3515, 0.04285], [0.130, 1.4665, 0.09285], "Cube.035 raised border, measured x 4.452..4.712 at z=0.1357"),
    ("shower_rim_east", [10.8975, -3.3515, 0.04285], [0.0675, 1.4665, 0.09285], "Cube.035 raised border, measured x 10.830..10.965 at z=0.1357"),
    ("shower_rim_south", [7.7085, -4.778, 0.04285], [3.2565, 0.040, 0.09285], "Cube.035 raised border, measured y -4.818..-4.738 at z=0.1357"),
    ("shower_rim_north", [7.7085, -2.015, 0.04285], [3.2565, 0.130, 0.09285], "Cube.035 raised border, measured y -2.145..-1.885 at z=0.1357"),
    ("basin_southeast", [10.174, -3.4415, 0.4675], [0.765, 1.2975, 0.4195], "Cube.037_Bathtub maarble_0"),
    ("north_counter", [1.6065, 3.795, 0.998], [2.2035, 0.698, 0.62], "Cube.040_wood sink_0 (north wall counter)"),
]

# Room boundary: solid in physics, aligned with the surfaces the camera sees.
# Measured by raycasting the imported shell, never assumed from the AABB.
SHELL_OBJECTS = ("Cube_Wall pattern",)          # hollow shell: 4 walls, no floor/ceiling
SKIRTING_OBJECT = "Cube.047_Bathtub maarble_0"  # marble baseboard ring, 45 mm proud of the walls
WALL_THICK = 0.5   # metres, grown outward so a fast bounce cannot tunnel
WALL_Z = (-1.0, 6.6)  # tall enough to reach the modelled ceiling
SKIRT_DEPTH = 0.30  # grow the baseboard back into the wall so it cannot be tunnelled
# Probe rays: origins inside the room, fired at the wall. The wall face is the
# innermost hit, so a wall-mounted protrusion can never push the face outward.
PROBE_X = (-6.0, -3.0, 0.0, 3.0, 6.0, 9.0)
PROBE_Y = (-3.0, -1.0, 1.0, 3.0)
PROBE_Z = (0.4, 0.8, 1.2, 1.8, 2.4)
SKIRT_Z = (0.10, 0.16, 0.22)

REGION = {"min": [-8.6, -5.6, -1.0], "max": [11.6, 5.0, 6.6]}  # render keep-box (whole room)
FLOOR_Z = 0.042


def _bvh(objects, Vector, BVHTree):
    verts, polys = [], []
    for ob in objects:
        mw = ob.matrix_world
        base = len(verts)
        verts += [mw @ v.co for v in ob.data.vertices]
        polys += [tuple(base + i for i in p.vertices) for p in ob.data.polygons]
    return BVHTree.FromPolygons(verts, polys, all_triangles=False)


def _faces(tree, Vector, zs, xprobe, yprobe):
    """Most common first-hit plane per direction.

    A single shell object also contains interior partitions and the far side of
    the plan, so a max/min pick latches onto the wrong surface. The wall the
    camera sees is the one most probe rays land on, so take the mode (1 mm
    bins) and report the histogram for eyeballing.
    """
    out = {}
    for axis, sign, name, pick in (
        (1, -1.0, "south", max), (1, 1.0, "north", min),
        (0, 1.0, "east", min), (0, -1.0, "west", max),
    ):
        direction = [0.0, 0.0, 0.0]
        direction[axis] = sign
        hits = []
        for a in xprobe:
            for b in yprobe:
                for z in zs:
                    origin = [a, b, z] if axis == 1 else [b, a, z]
                    loc, _n, _i, _d = tree.ray_cast(Vector(origin), Vector(direction), 40.0)
                    if loc is not None:
                        hits.append(round(loc[axis], 3))
        hist = {}
        for v in hits:
            hist[v] = hist.get(v, 0) + 1
        if not hist:
            out[name] = None
            out[name + "_hist"] = {}
            continue
        top = max(hist.values())
        # ties: keep the candidate closest to the room interior
        cands = [v for v, n in hist.items() if n == top]
        out[name] = pick(cands)
        out[name + "_hist"] = dict(sorted(hist.items(), key=lambda kv: -kv[1])[:4])
    return out


def _skirt_top(objects):
    return max((ob.matrix_world @ v.co).z for ob in objects for v in ob.data.vertices)


def measure_room(bpy, Vector, BVHTree):
    """Raycast the shell + baseboard and build the containment boxes."""
    shell = [o for o in bpy.data.objects
             if o.type == "MESH" and any(o.name.startswith(p) for p in SHELL_OBJECTS)]
    if not shell:
        raise RuntimeError("shell mesh %s not found in the GLB" % (SHELL_OBJECTS,))
    skirt = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith(SKIRTING_OBJECT)]
    if not skirt:
        raise RuntimeError("skirting mesh %s not found in the GLB" % SKIRTING_OBJECT)

    faces = _faces(_bvh(shell, Vector, BVHTree), Vector, PROBE_Z, PROBE_X, PROBE_Y)
    sfaces = _faces(_bvh(skirt, Vector, BVHTree), Vector, SKIRT_Z, PROBE_X, PROBE_Y)
    print("shell faces  :", {k: v for k, v in faces.items()})
    print("skirt faces  :", {k: v for k, v in sfaces.items()})
    skirt_top = _skirt_top(skirt)
    print("skirt top z  : %.4f" % skirt_top)

    boxes = []
    zc, zh = (WALL_Z[0] + WALL_Z[1]) / 2, (WALL_Z[1] - WALL_Z[0]) / 2
    west = faces["west"] if faces["west"] is not None else REGION["min"][0]
    east = faces["east"]
    south = faces["south"]
    north = faces["north"]
    # Cross-span of the y-walls / x-walls, one wall thickness of overlap so the
    # corners are sealed.
    xc, xh = (west + east) / 2, (east - west) / 2 + WALL_THICK
    yc, yh = (south + north) / 2, (north - south) / 2 + WALL_THICK
    boxes.append(("wall_south", [xc, south - WALL_THICK / 2, zc], [xh, WALL_THICK / 2, zh],
                  "measured shell inner face y=%.3f" % south))
    boxes.append(("wall_north", [xc, north + WALL_THICK / 2, zc], [xh, WALL_THICK / 2, zh],
                  "measured shell inner face y=%.3f" % north))
    boxes.append(("wall_east", [east + WALL_THICK / 2, yc, zc], [WALL_THICK / 2, yh, zh],
                  "measured shell inner face x=%.3f" % east))
    if faces["west"] is not None:
        boxes.append(("wall_west", [west - WALL_THICK / 2, yc, zc], [WALL_THICK / 2, yh, zh],
                      "measured shell inner face x=%.3f" % west))
    else:
        # No visible west wall inside 40 m (open plan); keep a containment box on
        # the keep-box boundary so a wild edit still cannot escape the room.
        boxes.append(("wall_west", [REGION["min"][0] - WALL_THICK / 2, yc, zc], [WALL_THICK / 2, yh, zh],
                      "synthetic: no visible west wall inside 40 m"))

    # Marble baseboard: 45 mm proud of each wall, up to the measured chamfer top.
    szc, szh = (FLOOR_Z + skirt_top) / 2, (skirt_top - FLOOR_Z) / 2
    for name, face, wall_face, axis, sign in (
        ("skirting_south", sfaces["south"], south, 1, -1.0),
        ("skirting_north", sfaces["north"], north, 1, 1.0),
        ("skirting_east", sfaces["east"], east, 0, 1.0),
        ("skirting_west", sfaces["west"], west, 0, -1.0),
    ):
        if face is None:
            continue
        # `sign` points into the room, so growing *into the wall* means moving
        # against it. With the sign flipped, the whole 300 mm of anti-tunnel
        # depth would sit on the room side: the collider would end 245 mm in
        # front of the visible board, and any ball landing within 245 mm of the
        # wall at z < 243 mm would rest on a marble shelf that does not exist.
        # Downward rays from those points miss the baseboard entirely.
        back = wall_face + sign * SKIRT_DEPTH
        lo, hi = min(face, back), max(face, back)
        c, h = (lo + hi) / 2, (hi - lo) / 2
        if axis == 1:
            boxes.append((name, [xc, c, szc], [xh, h, szh],
                          "measured baseboard face y=%.3f (%.0f mm proud)" % (face, (wall_face - face) * 1000 * sign)))
        else:
            boxes.append((name, [c, yc, szc], [h, yh, szh],
                          "measured baseboard face x=%.3f (%.0f mm proud)" % (face, (wall_face - face) * 1000 * sign)))
    return boxes, dict(south=south, north=north, east=east, west=west, skirt_top=skirt_top)


def main():
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    root = next(p for p in Path(__file__).resolve().parents if (p / "assets").is_dir())
    glb = root / "assets" / "models" / ASSET

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    bpy.context.view_layer.update()

    room_boxes, room = measure_room(bpy, Vector, BVHTree)
    boxes = list(FIXTURES) + room_boxes
    payload = {
        "schema_version": 2,
        "scene": SCENE,
        "asset": ASSET,
        "asset_sha256": hashlib.sha256(glb.read_bytes()).hexdigest(),
        "floor_z": FLOOR_Z,
        "region": REGION,
        "boxes": [{"name": n, "center": c, "half_extents": h, "source": s} for n, c, h, s in boxes],
    }
    out = root / "assets" / "scenes" / SCENE / "bathroom_colliders.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Sanity: the named fixture source objects must still exist, and every
    # fixture box must stay inside the measured room.
    have = {o.name: o for o in bpy.data.objects if o.type == 'MESH'}
    probes = {
        "Cube.030_Bathtub maarble_0": ("toilet_bowl",),
        "Cube.031_Bathtub maarble_0": ("toilet_bowl",),
        "Cube.002_wood sink_0": ("vanity_counter",),
        "Cube.003_black plastic_0": ("vanity_backsplash",),
        "Slippers_rubber_1_Wesley Faux Leather Lounge Chair Set-005_0": (),
        "z_Wesley Faux Leather Lounge Chair Set-left_0": ("pouf_left",),
        "Slippers_leather_right_Wesley Faux Leather Lounge Chair Set-rig": ("pouf_right",),
        "Cube.025_improved glass_0": ("glass_shower_door",),
        "Cube.014_improved glass_0": ("glass_shower_door",),
        "Cube.026_improved glass_0": ("glass_screen_south",),
        "Cube.019_improved glass_0": ("glass_screen_south",),
        "bathtub_Bathtub maarble_0": ("bathtub_east",),
        "Cube.035_Bathtub maarble_0": ("shower_base",),
        "Cube.037_Bathtub maarble_0": ("basin_southeast",),
        "Cube.040_wood sink_0": ("north_counter",),
        "Cube.027_black plastic_0": ("glass_door_frame_rail",),
    }
    missing = [n for n in probes if n not in have]
    if missing:
        raise RuntimeError("big_project.glb no longer contains: %s" % missing)
    # Fixtures legitimately embed a few cm into a wall (rails, slabs); flag only
    # the ones that would leave the room entirely, which means the measurement
    # went stale.
    for name, c, h, _src in FIXTURES:
        over = max(room["south"] - 0.10 - (c[1] - h[1]), (c[1] + h[1]) - (room["north"] + 0.10),
                   ((room["west"] or -99) - 0.10) - (c[0] - h[0]), (c[0] + h[0]) - (room["east"] + 0.10))
        if over > 0:
            raise RuntimeError("fixture %s pokes %.3f m through a wall" % (name, over))
    print("wrote", out)
    print("boxes:", len(boxes), "floor_z:", FLOOR_Z)


if __name__ == "__main__":
    main()
