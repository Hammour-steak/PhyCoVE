"""Measure the Sketchfab toy ship and inflatable pool and write what the simulation needs.

Run with Blender 4.3 from the repository root:

    blender -b --factory-startup --python scripts/rigid_fluid/toy_boat_pool_glide/appearance/prepare_assets_toy_boat_pool_glide.py

Writes to assets/sketchfab/toy_ship/prepared/ and assets/sketchfab/inflatable_swimming_pool/prepared/:

- boat_collider.obj: the ship below its deck line in the simulation's boat frame (+X bow, +Z up, keel at
  z = 0, hull centred on x/y), the shape the water sees;
- boat_frame.json: scale and transform from the GLB to that frame (the render applies the same one);
- pool_profile.json: scale, the inner floor and authored water plane heights, and the inner wall radius as a
  function of height above the ground, all in metres with the pool centred on the origin.
"""

import json
import math
from pathlib import Path

import bpy

ROOT = Path.cwd()
SHIP_GLB = ROOT / "assets/sketchfab/toy_ship/source/toy_ship.glb"
POOL_GLB = ROOT / "assets/sketchfab/inflatable_swimming_pool/source/inflatable_swimming_pool.glb"
SHIP_LENGTH = 0.20  # m, bow to stern: a bath-toy tug
POOL_OUTER_DIAMETER = 1.80  # m, a large three-ring kiddie pool (smaller pools let a 0.9 m/s glide reach the far wall)
DECK_FRACTION = 0.40  # the collider keeps the lowest 40 % of the ship's height (59 mm: the hull up into the bulwarks; the hull sides reach 84 mm)


def import_glb(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    meshes = {}
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            ev = o.evaluated_get(dg)
            m = ev.to_mesh()
            meshes[o.name] = ([tuple(o.matrix_world @ v.co) for v in m.vertices],
                              [tuple(p.vertices) for p in m.polygons])
            ev.to_mesh_clear()
    return meshes


def ship():
    meshes = import_glb(SHIP_GLB)
    pts = [p for verts, _ in meshes.values() for p in verts]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    scale = SHIP_LENGTH / (hi[1] - lo[1])
    # GLB +Y is the bow (the wheelhouse is forward); the boat frame puts the bow on +X: rotate -90 deg about Z.
    cx, cy = 0.5 * (lo[0] + hi[0]), 0.5 * (lo[1] + hi[1])

    def to_boat(p):
        x, y, z = (p[0] - cx) * scale, (p[1] - cy) * scale, (p[2] - lo[2]) * scale
        return (y, -x, z)

    deck = DECK_FRACTION * (hi[2] - lo[2]) * scale
    below = [to_boat(p) for p in pts if (p[2] - lo[2]) * scale <= deck]
    out = ROOT / "assets/sketchfab/toy_ship/prepared"
    out.mkdir(parents=True, exist_ok=True)
    # Genesis convexifies the collider anyway; give it the point cloud's hull as a closed mesh.
    bm_mesh = bpy.data.meshes.new("hull_pts")
    bm_mesh.from_pydata(below, [], [])
    obj = bpy.data.objects.new("hull_pts", bm_mesh)
    bpy.context.scene.collection.objects.link(obj)
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(bm_mesh)
    bmesh.ops.convex_hull(bm, input=bm.verts)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(bm_mesh)
    bm.free()
    lines = [f"v {v.co.x:.6f} {v.co.y:.6f} {v.co.z:.6f}" for v in bm_mesh.vertices]
    lines += ["f " + " ".join(str(i + 1) for i in p.vertices) for p in bm_mesh.polygons]
    (out / "boat_collider.obj").write_text("\n".join(lines) + "\n")
    frame = {
        "source": str(SHIP_GLB.relative_to(ROOT)),
        "scale": scale,
        "glb_offset_before_scale": [-cx, -cy, -lo[2]],
        "rotation_z_deg_after_scale": -90.0,
        "note": "boat = Rz(-90) * scale * (glb + offset); +X bow, +Z up, keel at z = 0",
        "size_m": [(hi[1] - lo[1]) * scale, (hi[0] - lo[0]) * scale, (hi[2] - lo[2]) * scale],
        "collider_top_m": deck,
        "collider_vertices": len(bm_mesh.vertices),
    }
    (out / "boat_frame.json").write_text(json.dumps(frame, indent=2) + "\n")
    print("SHIP", json.dumps(frame))


def pool():
    meshes = import_glb(POOL_GLB)
    verts, _ = meshes["Torus_Bubbles_solid_0"]
    lo_z = min(p[2] for p in verts)
    outer = max(math.hypot(p[0], p[1]) for p in verts)
    scale = 0.5 * POOL_OUTER_DIAMETER / outer
    water = meshes["Circle_Water_0"][0][0][2]
    floor = max(p[2] for p in verts if math.hypot(p[0], p[1]) < 0.4 * outer)
    # Inner wall: the smallest radius of the ring vertices (outside the floor disc) in 2 mm bands.
    ring = [((p[2] - lo_z) * scale, math.hypot(p[0], p[1]) * scale) for p in verts
            if math.hypot(p[0], p[1]) > 0.7 * outer]
    top = max(z for z, _ in ring)
    profile = []
    band = 0.002
    z = (floor - lo_z) * scale
    while z <= top:
        rs = [r for zz, r in ring if abs(zz - z) <= 0.5 * band + 1e-9]
        if rs:
            profile.append([round(z, 4), round(min(rs), 4)])
        z += band
    out = ROOT / "assets/sketchfab/inflatable_swimming_pool/prepared"
    out.mkdir(parents=True, exist_ok=True)
    info = {
        "source": str(POOL_GLB.relative_to(ROOT)),
        "scale": scale,
        "glb_offset_before_scale": [0.0, 0.0, -lo_z],
        "note": "world = scale * (glb + offset): pool centred on the origin, standing on z = 0",
        "outer_diameter_m": POOL_OUTER_DIAMETER,
        "height_m": (max(p[2] for p in verts) - lo_z) * scale,
        "inner_floor_z_m": (floor - lo_z) * scale,
        "authored_water_z_m": (water - lo_z) * scale,
        "inner_wall_profile_z_r_m": profile,
    }
    (out / "pool_profile.json").write_text(json.dumps(info, indent=2) + "\n")
    print("POOL", json.dumps({k: v for k, v in info.items() if k != "inner_wall_profile_z_r_m"}),
          "profile rows", len(profile))
    for row in profile[::5]:
        print("  wall", row)


ship()
pool()
