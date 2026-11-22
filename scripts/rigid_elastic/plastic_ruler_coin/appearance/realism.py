"""Current look: a coin dropped on a clear ruler held down by a book at the edge of a home desk.

Blender 4.3.2 Cycles. The whole scene is built here: a lacquered oak-veneer desk (Poly Haven oak_veneer_01 scan), a
dark red cloth-bound hardcover without any title (Poly Haven rough_linen weave), a clear acrylic 30 cm ruler with
printed millimetre graduations and numerals only, a plain cupro-nickel coin without any design, an unprinted pencil
and a stoneware mug. Light, reflections and the defocused background are the HDR panorama of a real sunlit apartment
(Poly Haven photo_studio_loft_hall, 4k); it is rotated so the window wall is behind the desk on the camera's right.
No hidden lamps.

Only the native cache of the case moves anything (no keyframes, no interpolation between cached states):
- ruler: every rest vertex (x, y, z) with x >= 0 is carried by the cached Kirchhoff centreline of that frame
  (x' = X(x) - sin(theta(x)) z, z' = Z(x) + cos(theta(x)) z), the clamped part only shifts by the mid-plane height;
  the same mapping as the accepted renderer, re-checked per frame by tools/verify_replay.py;
- coins: cached (x, z, pitch) per frame, transform T(x, 0, z) R_y(-pitch).

    blender -b --factory-startup --python-exit-code 1 --python realism.py -- \\
        --cache-dir DIR --out DIR [--frames 1 30 ...] [--samples 512] [--device cpu|gpu] [--threads N]

Output in --out: frame_0001.png ... (video frame f = cached state f-1, t = (f-1)/24 s), camera.json,
ruler_render_binding.npz (rest vertices), render_replay.jsonl (per-frame receipts), realism_provenance.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[2])]
import pcve_realism_kit as kit  # noqa: E402
from pcve_assets import asset  # noqa: E402

LOOK = "sunlit_home_desk"
HDRI = asset("polyhaven/photo_studio_loft_hall/photo_studio_loft_hall_4k.hdr")
OAK = asset("polyhaven/oak_veneer_01")               # oak_veneer_01_{diff,rough,nor_gl}_8k.jpg (Poly Haven scan)
FLOOR = asset("polyhaven/wood_floor_worn")          # wood_floor_worn_{diff,rough,nor_gl}_4k.jpg (Poly Haven scan)
LINEN = asset("polyhaven/rough_linen/textures")      # rough_linen_{diff,nor_gl}_2k.jpg (Poly Haven scan)
DESK_TOP = 0.760                                      # the ruler's underside rests on it (physics: mid-plane 0.7608)
# Look parameters. PRC_LOOKDEV_<NAME> environment variables override them for look development only; every
# value used is written to realism_provenance.json.
LOOK_PARAMS = {
    # Fixed camera: three-quarter view from the front right, as a camera on a small tripod would see it.
    "camera_at": (0.470, -0.490, 1.040), "camera_aim": (0.055, 0.000, 0.770), "lens_mm": 85.0, "fstop": 22.0,
    "focus_at": (0.080, -0.010, 0.766),
    "hdri_rotation_deg": -100.0, "hdri_strength": 1.0, "exposure": -0.4,
}
for _k, _v in list(LOOK_PARAMS.items()):
    _env = os.environ.get("PRC_LOOKDEV_" + _k.upper())
    if _env:
        LOOK_PARAMS[_k] = tuple(float(x) for x in _env.split(",")) if isinstance(_v, tuple) else float(_env)
SEED = 9137
# Swept volume of the ruler and coins over all six cases (metres); static dressing must stay out of it.
KEEPOUT = ((-0.205, -0.095, 0.70), (0.20, 0.095, 0.90))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ----------------------------------------------------------------------------------------------- materials
def principled(name, color, rough=0.5, metal=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bs = mat.node_tree.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Metallic"].default_value = metal
    return mat, bs


def noise(nodes, links, scale, detail=4.0, stretch=None, coord="Object"):
    tc = nodes.new("ShaderNodeTexCoord")
    src = tc.outputs[coord]
    if stretch:
        mul = nodes.new("ShaderNodeVectorMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = stretch
        links.new(src, mul.inputs[0])
        src = mul.outputs[0]
    tex = nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = detail
    links.new(src, tex.inputs["Vector"])
    return tex


def maprange(nodes, links, src, a, b, c, d):
    m = nodes.new("ShaderNodeMapRange")
    m.inputs["From Min"].default_value = a
    m.inputs["From Max"].default_value = b
    m.inputs["To Min"].default_value = c
    m.inputs["To Max"].default_value = d
    links.new(src, m.inputs["Value"])
    return m.outputs[0]


def bump(nodes, links, height, strength, distance, normal_in=None):
    b = nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    links.new(height, b.inputs["Height"])
    if normal_in is not None:
        links.new(normal_in, b.inputs["Normal"])
    return b.outputs["Normal"]


def box_uv(obj, tile, offset=(0.0, 0.0)):
    """World-space box UVs at `tile` metres per texture repeat, so tangent-space scans have valid tangents."""
    me = obj.data
    uv = me.uv_layers.get("box") or me.uv_layers.new(name="box")
    mw = obj.matrix_world
    for poly in me.polygons:
        n = mw.to_3x3() @ poly.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        # grain (texture v) runs along y on the top and the long faces, so the desk reads as one veneer
        keep = {0: (2, 1), 1: (0, 2), 2: (0, 1)}[axis]
        for li in poly.loop_indices:
            co = mw @ me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (co[keep[0]] / tile + offset[0], co[keep[1]] / tile + offset[1])
    me.uv_layers.active = uv


def box_scan(mat, folder, prefix, res="4k", normal=0.6, rough_range=(0.3, 0.6), tint=None):
    """Scanned diff/rough/nor_gl set on the object's box UVs (see box_uv for the real-world tile size)."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = nodes["Principled BSDF"]
    uvn = nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "box"
    texs = {}
    for kind in ("diff", "rough", "nor_gl"):
        t = nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(str(Path(folder) / f"{prefix}_{kind}_{res}.jpg"), check_existing=True)
        if kind != "diff":
            t.image.colorspace_settings.name = "Non-Color"
        links.new(uvn.outputs["UV"], t.inputs["Vector"])
        texs[kind] = t
    color = texs["diff"].outputs["Color"]
    if tint is not None:
        mul = nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        links.new(color, mul.inputs["A"])
        mul.inputs["B"].default_value = (*tint, 1)
        color = mul.outputs["Result"]
    links.new(color, bs.inputs["Base Color"])
    links.new(maprange(nodes, links, texs["rough"].outputs["Color"], 0, 1, *rough_range), bs.inputs["Roughness"])
    nm = nodes.new("ShaderNodeNormalMap")
    nm.uv_map = "box"
    nm.inputs["Strength"].default_value = normal
    links.new(texs["nor_gl"].outputs["Color"], nm.inputs["Color"])
    links.new(nm.outputs[0], bs.inputs["Normal"])
    return texs


def oak_desk_material():
    """Oak-veneered desk with a worn satin lacquer.

    Poly Haven oak_veneer_01 at 8k over its real 1.83 m (45 texels per cm), plus open oak pores: fine pits about
    0.15 mm across and 1-2 mm long along the grain (world y), under the lacquer.
    """
    mat, bs = principled("Lacquered oak veneer desk", (0.4, 0.3, 0.2), 0.45)
    box_scan(mat, OAK, "oak_veneer_01", res="8k", normal=0.5, rough_range=(0.30, 0.55))
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    pores = noise(nodes, links, 5200.0, 2.0, stretch=(1.0, 0.09, 1.0))
    pits = maprange(nodes, links, pores.outputs["Fac"], 0.58, 0.68, 0.0, 1.0)
    rays = noise(nodes, links, 900.0, 3.0, stretch=(1.0, 0.04, 1.0))
    streak = maprange(nodes, links, rays.outputs["Fac"], 0.4, 0.7, 0.0, 0.35)
    height = nodes.new("ShaderNodeMath")
    height.operation = "SUBTRACT"
    links.new(streak, height.inputs[0])
    links.new(pits, height.inputs[1])
    previous = bs.inputs["Normal"].links[0].from_socket
    links.new(bump(nodes, links, height.outputs[0], 0.45, 0.00004, previous), bs.inputs["Normal"])
    # Pores collect a little dark grime under the finish.
    base = bs.inputs["Base Color"].links[0].from_socket
    dark = nodes.new("ShaderNodeMix")
    dark.data_type = "RGBA"
    dark.blend_type = "MULTIPLY"
    links.new(maprange(nodes, links, pores.outputs["Fac"], 0.6, 0.7, 0.0, 0.35), dark.inputs["Factor"])
    links.new(base, dark.inputs["A"])
    dark.inputs["B"].default_value = (0.45, 0.38, 0.30, 1)
    links.new(dark.outputs["Result"], bs.inputs["Base Color"])
    bs.inputs["Specular IOR Level"].default_value = 0.5
    bs.inputs["Coat Weight"].default_value = 0.25
    bs.inputs["Coat Roughness"].default_value = 0.22
    kit.add_surface_wear(mat, smudge=0.10, grime=0.05, scratch=0.05, scale=0.6)
    return mat


def floor_material():
    """Worn plank floor of the room (Poly Haven wood_floor_worn, 4k over its real 2 m)."""
    mat, bs = principled("Worn plank floor", (0.3, 0.2, 0.15), 0.6)
    box_scan(mat, FLOOR, "wood_floor_worn", res="4k", normal=0.6, rough_range=(0.35, 0.75))
    return mat


def bookcloth_material(color):
    """Dyed linen book cloth: the linen scan's weave as normal, roughness and luminance."""
    mat, bs = principled("Dyed linen book cloth", color, 0.8)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    uvn = nodes.new("ShaderNodeUVMap")       # box UVs at 0.11 m per repeat: ~0.35 mm threads, like real book cloth
    uvn.uv_map = "box"

    def img(kind):
        t = nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(str(LINEN / f"rough_linen_{kind}_2k.jpg"), check_existing=True)
        if kind != "diff":
            t.image.colorspace_settings.name = "Non-Color"
        links.new(uvn.outputs["UV"], t.inputs["Vector"])
        return t
    diff = img("diff")
    lum = nodes.new("ShaderNodeRGBToBW")
    links.new(diff.outputs["Color"], lum.inputs["Color"])
    shade = maprange(nodes, links, lum.outputs["Val"], 0.25, 0.75, 0.72, 1.18)
    grime = noise(nodes, links, 18.0, 5.0)
    worn = maprange(nodes, links, grime.outputs["Fac"], 0.35, 0.7, 0.9, 1.08)
    mul = nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    links.new(shade, mul.inputs[0])
    links.new(worn, mul.inputs[1])
    col = nodes.new("ShaderNodeVectorMath")
    col.operation = "SCALE"
    col.inputs[0].default_value = color
    links.new(mul.outputs[0], col.inputs["Scale"])
    # Rubbed board edges and corners: the cloth wears lighter where the edge is sharp (Cycles pointiness).
    geo = nodes.new("ShaderNodeNewGeometry")
    rub = maprange(nodes, links, geo.outputs["Pointiness"], 0.52, 0.60, 0.0, 0.75)
    rubn = noise(nodes, links, 900.0, 4.0)
    rubm = nodes.new("ShaderNodeMath")
    rubm.operation = "MULTIPLY"
    links.new(rub, rubm.inputs[0])
    links.new(rubn.outputs["Fac"], rubm.inputs[1])
    wornmix = nodes.new("ShaderNodeMix")
    wornmix.data_type = "RGBA"
    links.new(rubm.outputs[0], wornmix.inputs["Factor"])
    links.new(col.outputs[0], wornmix.inputs["A"])
    wornmix.inputs["B"].default_value = (0.42, 0.30, 0.26, 1)
    links.new(wornmix.outputs["Result"], bs.inputs["Base Color"])
    nm = nodes.new("ShaderNodeNormalMap")
    nm.uv_map = "box"
    nm.inputs["Strength"].default_value = 0.9
    links.new(img("nor_gl").outputs["Color"], nm.inputs["Color"])
    links.new(nm.outputs[0], bs.inputs["Normal"])
    links.new(maprange(nodes, links, lum.outputs["Val"], 0.2, 0.8, 0.86, 0.7), bs.inputs["Roughness"])
    bs.inputs["Sheen Weight"].default_value = 0.12
    bs.inputs["Sheen Roughness"].default_value = 0.6
    bs.inputs["Sheen Tint"].default_value = (*[min(1.0, 3 * c) for c in color], 1)
    return mat


def page_edge_material():
    """Book block edges: off-white paper, irregular sheet lines and signature bands along the edge, edge soiling."""
    base = (0.72, 0.66, 0.54)
    mat, bs = principled("Book block page edges", base, 0.85)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    sheets = noise(nodes, links, 2600.0, 2.0, stretch=(0.005, 0.005, 1.0))
    bundles = noise(nodes, links, 330.0, 1.0, stretch=(0.01, 0.01, 1.0))
    broad = noise(nodes, links, 40.0, 3.0, stretch=(0.08, 0.08, 1.0))
    t1 = maprange(nodes, links, sheets.outputs["Fac"], 0.3, 0.7, 0.80, 1.05)
    t2 = maprange(nodes, links, bundles.outputs["Fac"], 0.35, 0.65, 0.92, 1.03)
    t3 = maprange(nodes, links, broad.outputs["Fac"], 0.3, 0.7, 0.88, 1.03)
    m = nodes.new("ShaderNodeMath")
    m.operation = "MULTIPLY"
    links.new(t1, m.inputs[0])
    links.new(t2, m.inputs[1])
    m2 = nodes.new("ShaderNodeMath")
    m2.operation = "MULTIPLY"
    links.new(m.outputs[0], m2.inputs[0])
    links.new(t3, m2.inputs[1])
    col = nodes.new("ShaderNodeVectorMath")
    col.operation = "SCALE"
    col.inputs[0].default_value = base
    links.new(m2.outputs[0], col.inputs["Scale"])
    links.new(col.outputs[0], bs.inputs["Base Color"])
    h = nodes.new("ShaderNodeMath")
    h.operation = "MULTIPLY_ADD"
    links.new(sheets.outputs["Fac"], h.inputs[0])
    h.inputs[1].default_value = 1.0
    links.new(bundles.outputs["Fac"], h.inputs[2])
    links.new(bump(nodes, links, h.outputs[0], 0.55, 0.00008), bs.inputs["Normal"])
    bs.inputs["Subsurface Weight"].default_value = 0.08
    bs.inputs["Subsurface Radius"].default_value = (0.002, 0.0018, 0.0012)
    return mat


def acrylic_material():
    """Clear cast acrylic: high transmission, slight cyan body tint visible through the edges, fine handling wear."""
    mat, bs = principled("Clear acrylic ruler", (0.97, 0.99, 0.99), 0.03)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs.inputs["Transmission Weight"].default_value = 1.0
    bs.inputs["IOR"].default_value = 1.49
    smear = noise(nodes, links, 260.0, 6.0)
    lines = noise(nodes, links, 900.0, 2.0, stretch=(1.0, 40.0, 1.0))
    r1 = maprange(nodes, links, smear.outputs["Fac"], 0.45, 0.75, 0.025, 0.09)
    r2 = maprange(nodes, links, lines.outputs["Fac"], 0.6, 0.7, 0.0, 0.08)
    add = nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    links.new(r1, add.inputs[0])
    links.new(r2, add.inputs[1])
    links.new(add.outputs[0], bs.inputs["Roughness"])
    absorb = nodes.new("ShaderNodeVolumeAbsorption")
    absorb.inputs["Color"].default_value = (0.80, 0.95, 0.93, 1)
    absorb.inputs["Density"].default_value = 18.0
    links.new(absorb.outputs[0], nodes["Material Output"].inputs["Volume"])
    return mat


def ink_material():
    mat, bs = principled("Printed black graduations", (0.012, 0.012, 0.013), 0.42)
    return mat


def coin_material():
    """Cupro-nickel: bright worn rim, duller toned field, fine circulation scratches and a reeded edge."""
    mat, bs = principled("Cupro-nickel coin", (0.80, 0.78, 0.74), 0.24, 1.0)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    geo = nodes.new("ShaderNodeNewGeometry")
    tc = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(tc.outputs["Object"], sep.inputs[0])
    # Radius in object space -> rim mask (the last ~1 mm is the raised, polished rim).
    xy = nodes.new("ShaderNodeCombineXYZ")
    links.new(sep.outputs["X"], xy.inputs["X"])
    links.new(sep.outputs["Y"], xy.inputs["Y"])
    rad = nodes.new("ShaderNodeVectorMath")
    rad.operation = "LENGTH"
    links.new(xy.outputs[0], rad.inputs[0])
    rim = maprange(nodes, links, rad.outputs["Value"], 0.0101, 0.0106, 0.0, 1.0)
    tarnish = noise(nodes, links, 220.0, 3.0)
    tone = maprange(nodes, links, tarnish.outputs["Fac"], 0.35, 0.7, 0.90, 1.0)
    field_col = nodes.new("ShaderNodeVectorMath")
    field_col.operation = "SCALE"
    field_col.inputs[0].default_value = (0.70, 0.68, 0.64)
    links.new(tone, field_col.inputs["Scale"])
    mixc = nodes.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    links.new(rim, mixc.inputs["Factor"])
    links.new(field_col.outputs[0], mixc.inputs["A"])
    mixc.inputs["B"].default_value = (0.86, 0.84, 0.80, 1)
    links.new(mixc.outputs["Result"], bs.inputs["Base Color"])
    rough_field = maprange(nodes, links, tarnish.outputs["Fac"], 0.3, 0.7, 0.22, 0.32)
    mixr = nodes.new("ShaderNodeMix")
    mixr.data_type = "FLOAT"
    links.new(rim, mixr.inputs["Factor"])
    links.new(rough_field, mixr.inputs["A"])
    mixr.inputs["B"].default_value = 0.16
    links.new(mixr.outputs["Result"], bs.inputs["Roughness"])
    # Reeding: ~150 grooves around the edge, only where the surface faces sideways.
    ang = nodes.new("ShaderNodeMath")
    ang.operation = "ARCTAN2"
    links.new(sep.outputs["Y"], ang.inputs[0])
    links.new(sep.outputs["X"], ang.inputs[1])
    reeds = nodes.new("ShaderNodeMath")
    reeds.operation = "SINE"
    sc = nodes.new("ShaderNodeMath")
    sc.operation = "MULTIPLY"
    sc.inputs[1].default_value = 150.0
    links.new(ang.outputs[0], sc.inputs[0])
    links.new(sc.outputs[0], reeds.inputs[0])
    nz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geo.outputs["Normal"], nz.inputs[0])
    absz = nodes.new("ShaderNodeMath")
    absz.operation = "ABSOLUTE"
    links.new(nz.outputs["Z"], absz.inputs[0])
    side = maprange(nodes, links, absz.outputs[0], 0.35, 0.15, 0.0, 1.0)
    edge_h = nodes.new("ShaderNodeMath")
    edge_h.operation = "MULTIPLY"
    links.new(reeds.outputs[0], edge_h.inputs[0])
    links.new(side, edge_h.inputs[1])
    scratches = noise(nodes, links, 2600.0, 3.0, stretch=(1.0, 18.0, 1.0))
    sh = maprange(nodes, links, scratches.outputs["Fac"], 0.66, 0.72, 0.0, 1.0)
    wear = noise(nodes, links, 3000.0, 8.0)
    h = nodes.new("ShaderNodeMath")
    h.operation = "ADD"
    links.new(edge_h.outputs[0], h.inputs[0])
    hs = nodes.new("ShaderNodeMath")
    hs.operation = "MULTIPLY_ADD"
    links.new(sh, hs.inputs[0])
    hs.inputs[1].default_value = -0.4
    links.new(wear.outputs["Fac"], hs.inputs[2])
    links.new(hs.outputs[0], h.inputs[1])
    links.new(bump(nodes, links, h.outputs[0], 0.2, 0.00003), bs.inputs["Normal"])
    return mat


# ----------------------------------------------------------------------------------------------- geometry
def link(obj):
    bpy.context.collection.objects.link(obj)
    return obj


def mesh_object(name, bm, mat=None, smooth_angle=30.0):
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if e.is_boundary or (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(smooth_angle)):
            e.smooth = False
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = link(bpy.data.objects.new(name, me))
    if mat is not None:
        me.materials.append(mat)
    return obj


def rounded_box(name, lo, hi, radius, mat, segments=3):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    lo, hi = Vector(lo), Vector(hi)
    for v in bm.verts:
        v.co = Vector((lo.x if v.co.x < 0 else hi.x, lo.y if v.co.y < 0 else hi.y, lo.z if v.co.z < 0 else hi.z))
    if radius > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=radius, segments=segments, profile=0.5, affect="EDGES",
                        clamp_overlap=True)
    return mesh_object(name, bm, mat)


def lathe(name, profile, mat, steps=128):
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0.0, z)) for r, z in profile]
    edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1), angle=math.tau, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    return mesh_object(name, bm, mat, 40.0)


def build_desk():
    oak = oak_desk_material()
    top = rounded_box("Oak desk top", (-0.74, -0.72, DESK_TOP - 0.026), (0.0, 1.05, DESK_TOP), 0.0025, oak, 4)
    parts = [top]
    parts.append(rounded_box("Desk front rail", (-0.045, -0.66, DESK_TOP - 0.11), (-0.025, 0.99, DESK_TOP - 0.026), 0.0015, oak))
    parts.append(rounded_box("Desk back rail", (-0.715, -0.66, DESK_TOP - 0.11), (-0.695, 0.99, DESK_TOP - 0.026), 0.0015, oak))
    for x0 in (-0.70, -0.07):
        for y0 in (-0.69, 0.98):
            parts.append(rounded_box("Desk leg", (x0, y0 - 0.02, 0.0), (x0 + 0.045, y0 + 0.025, DESK_TOP - 0.026), 0.002, oak))
    for i, part in enumerate(parts):
        box_uv(part, 1.83, (0.137 * i, 0.291 * i))
    # Room floor 0.76 m below the desk top (the legs stand on it), large enough to fill every downward view.
    floor = rounded_box("Room floor", (-6.0, -6.0, -0.02), (6.0, 6.0, 0.0), 0.0, floor_material())
    box_uv(floor, 2.0, (0.31, 0.17))
    parts.append(floor)
    return parts


def build_book(on_ruler=True):
    """Hardcover, cloth-bound, no title: boards overhang the text block by 3 mm, rounded spine at the back (-x).

    on_ruler=False (DELETE ruler): the book lies directly on the desk top instead of on the 1.6 mm ruler."""
    x0, x1, y0, y1 = -0.200, 0.000, -0.0875, 0.0875
    z0 = DESK_TOP + (0.0016 if on_ruler else 0.0)   # resting on the ruler
    z1 = z0 + 0.060
    board = 0.0028
    cloth = bookcloth_material((0.12, 0.026, 0.028))
    pages = page_edge_material()
    objs = [rounded_box("Book lower board", (x0 + 0.004, y0, z0), (x1, y1, z0 + board), 0.0009, cloth),
            rounded_box("Book upper board", (x0 + 0.004, y0, z1 - board), (x1, y1, z1), 0.0009, cloth)]
    # Text block: slightly convex at the head/tail, concave fore-edge as on a rounded-and-backed book.
    bm = bmesh.new()
    nx, ny, nz = 24, 24, 12
    gx = np.linspace(x0 + 0.006, x1 - 0.003, nx)
    gy = np.linspace(y0 + 0.003, y1 - 0.003, ny)
    gz = np.linspace(z0 + board + 0.0002, z1 - board - 0.0002, nz)
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=10, use_grid_fill=True)
    zc, zh = (gz[0] + gz[-1]) / 2, (gz[-1] - gz[0]) / 2
    for v in bm.verts:
        u = Vector(v.co) * 2            # -1..1
        x = gx[0] + (u.x + 1) / 2 * (gx[-1] - gx[0])
        y = gy[0] + (u.y + 1) / 2 * (gy[-1] - gy[0])
        z = zc + u.z * zh
        if u.x > 0.999:
            x -= 0.0016 * (1 - u.z ** 2)        # concave fore-edge
        v.co = Vector((x, y, z))
    objs.append(mesh_object("Book text block", bm, pages, 50.0))
    # Spine: half-round cloth shell joining the boards at the back.
    bm = bmesh.new()
    steps = 24
    rings = []
    for yy in (y0, y1):
        ring = []
        for i in range(steps + 1):
            a = -math.pi / 2 + math.pi * i / steps
            r = (z1 - z0) / 2
            ring.append(bm.verts.new((x0 + 0.006 - 0.0075 * math.cos(a), yy, (z0 + z1) / 2 + r * math.sin(a))))
        rings.append(ring)
    for i in range(steps):
        bm.faces.new((rings[0][i], rings[0][i + 1], rings[1][i + 1], rings[1][i]))
    bmesh.ops.solidify(bm, geom=list(bm.faces), thickness=0.0012)
    objs.append(mesh_object("Book spine", bm, cloth, 60.0))
    for o in objs:
        if o.data.materials[0].name == cloth.name:
            box_uv(o, 0.11)
    return objs


def build_ruler(cfg):
    """Rest geometry (mid-plane at z = 0) of the 317.5 x 31 x 1.6 mm strip and its printed scale.

    Returns the objects whose vertices the cache bends. The strip has a 2 mm drawing bevel along its -y edge,
    1 mm stations along the free length and 5 mm under the book.
    """
    L_c, L_f = cfg["ruler_clamped_length_m"], cfg["ruler_free_length_m"]
    w, t = cfg["ruler_width_m"], cfg["ruler_thickness_m"]
    y0, y1, h = -w / 2, w / 2, t / 2
    r = 0.00025
    section = [(y0, -h + r), (y0 + r, -h), (y1 - r, -h), (y1, -h + r), (y1, h - r), (y1 - r, h),
               (y0 + 0.0021, h), (y0 + 0.0003, -h + 0.00075), (y0, -h + 0.0006)]
    xs = np.unique(np.round(np.r_[np.arange(-L_c, 0.0, 0.005), np.arange(0.0, L_f + 1e-9, 0.001), L_f], 9))
    bm = bmesh.new()
    rows = [[bm.verts.new((float(x), yy, zz)) for yy, zz in section] for x in xs]
    n = len(section)
    for a, b in zip(rows, rows[1:]):
        for i in range(n):
            bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n]))
    bm.faces.new(list(reversed(rows[0])))
    bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    body = mesh_object("Clear acrylic ruler", bm, acrylic_material(), 35.0)
    # Printed scale on the top face: mm ticks from the bevel line, 0-30 cm, numerals only, readable from -y.
    bm = bmesh.new()
    zt = h + 0.00002
    edge = y0 + 0.0022
    origin = -L_c + 0.00875
    for k in range(301):
        x = origin + 0.001 * k
        length = 0.0055 if k % 10 == 0 else (0.0040 if k % 5 == 0 else 0.0026)
        hw = 0.00011
        q = [bm.verts.new((x - hw, edge, zt)), bm.verts.new((x + hw, edge, zt)),
             bm.verts.new((x + hw, edge + length, zt)), bm.verts.new((x - hw, edge + length, zt))]
        bm.faces.new(q)
    for cm in range(31):
        txt = bpy.data.curves.new(f"numeral_{cm}", "FONT")
        txt.body = str(cm)
        txt.size = 0.0029
        txt.align_x = "CENTER"
        tob = link(bpy.data.objects.new(f"numeral_{cm}", txt))
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(tob.evaluated_get(dg))
        off = Vector((origin + 0.01 * cm, edge + 0.0064, zt))
        lut = {}
        for v in me.vertices:
            lut[v.index] = bm.verts.new(Vector((v.co.x, v.co.y, 0.0)) + off)
        for p in me.polygons:
            try:
                bm.faces.new([lut[i] for i in p.vertices])
            except ValueError:
                pass
        bpy.data.objects.remove(tob)
        bpy.data.meshes.remove(me)
        bpy.data.curves.remove(txt)
    me = bpy.data.meshes.new("Ruler printed scale")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False
    printed = link(bpy.data.objects.new("Ruler printed scale", me))
    me.materials.append(ink_material())
    printed.visible_shadow = True
    return [body, printed]


def build_coin(cfg, label):
    R, T = cfg["coin_radius_m"], cfg["coin_thickness_m"]
    h = T / 2
    rim_in, rim_out, field = R - 0.00105, R - 0.00025, h - 0.00013
    profile = [(0.0, field), (rim_in - 0.0002, field), (rim_in, field + 0.00004), (rim_in + 0.00012, h),
               (rim_out - 0.0001, h), (rim_out, h - 0.00004), (R - 0.00005, h - 0.00018), (R, h - 0.0003),
               (R, -h + 0.0003), (R - 0.00005, -h + 0.00018), (rim_out, -h + 0.00004), (rim_out - 0.0001, -h),
               (rim_in + 0.00012, -h), (rim_in, -field - 0.00004), (rim_in - 0.0002, -field), (0.0, -field)]
    return lathe(label, profile, coin_material(), 160)


def stoneware_mug(at):
    """Lathed hollow mug with coffee and a side handle (oatmeal speckled glaze), as in the previous look."""
    profile = [(0.0, .0045), (.0290, .0045), (.0302, .0018), (.0318, 0.0), (.0336, .0012), (.0346, .0060),
               (.0360, .0300), (.0372, .0620), (.0378, .0790), (.0377, .0822), (.0366, .0838), (.0352, .0834),
               (.0344, .0812), (.0338, .0700), (.0326, .0200), (.0300, .0108), (.0240, .0092), (0.0, .0090)]
    glaze, bs = principled("Speckled stoneware glaze", (0.55, 0.50, 0.42), 0.22)
    n, l = glaze.node_tree.nodes, glaze.node_tree.links
    speck = n.new("ShaderNodeTexVoronoi")
    speck.inputs["Scale"].default_value = 420.0
    tc = n.new("ShaderNodeTexCoord")
    l.new(tc.outputs["Object"], speck.inputs["Vector"])
    dots = maprange(n, l, speck.outputs["Distance"], 0.10, 0.05, 0.0, 1.0)
    mix = n.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    l.new(dots, mix.inputs["Factor"])
    mix.inputs["A"].default_value = (0.55, 0.50, 0.42, 1)
    mix.inputs["B"].default_value = (0.20, 0.14, 0.09, 1)
    l.new(mix.outputs["Result"], bs.inputs["Base Color"])
    ripple = noise(n, l, 90.0, 4.0)
    l.new(bump(n, l, ripple.outputs["Fac"], 0.3, 0.00025), bs.inputs["Normal"])
    body = lathe("Stoneware mug", profile, glaze, 96)
    body.location = at
    curve = bpy.data.curves.new("Mug handle", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = .0052
    curve.bevel_resolution = 4
    sp = curve.splines.new("BEZIER")
    pts = [(.0355, .0680), (.0560, .0700), (.0650, .0480), (.0570, .0250), (.0360, .0210)]
    sp.bezier_points.add(len(pts) - 1)
    for bp, (x, z) in zip(sp.bezier_points, pts):
        bp.co = (x, 0, z)
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    handle = link(bpy.data.objects.new("Stoneware mug handle", curve))
    curve.materials.append(glaze)
    handle.parent = body
    handle.scale = (1.0, 1.5, 1.0)
    body.rotation_euler.z = math.radians(-115)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=96, radius=.03395)
    for v in bm.verts:
        v.co.z = .0690 + .0004 * (Vector((v.co.x, v.co.y)).length / .034) ** 6
    coffee_mat, cbs = principled("Black coffee", (0.03, 0.014, 0.006), 0.04)
    coffee = mesh_object("Coffee in mug", bm, coffee_mat)
    coffee.parent = body
    return [body, handle, coffee]


def pencil(at, yaw):
    """Unprinted yellow hexagonal pencil (175 mm), sharpened cedar tip, brass ferrule and eraser."""
    paint, _ = principled("Yellow pencil lacquer", (0.80, 0.52, 0.06), 0.28)
    cedar, _ = principled("Cedar", (0.62, 0.42, 0.26), 0.7)
    graphite, _ = principled("Graphite", (0.05, 0.05, 0.055), 0.35, 0.3)
    brass, _ = principled("Ferrule brass", (0.72, 0.58, 0.32), 0.3, 1.0)
    eraser, _ = principled("Pink eraser", (0.72, 0.36, 0.34), 0.75)
    r = 0.0036
    objs = []
    bm = bmesh.new()
    hexa = [(r * math.cos(i * math.pi / 3), r * math.sin(i * math.pi / 3)) for i in range(6)]   # a flat face down
    a = [bm.verts.new((0.0, y, z)) for y, z in hexa]
    b = [bm.verts.new((0.150, y, z)) for y, z in hexa]
    for i in range(6):
        bm.faces.new((a[i], b[i], b[(i + 1) % 6], a[(i + 1) % 6]))
    bm.faces.new(list(reversed(a)))
    bm.faces.new(b)
    bmesh.ops.bevel(bm, geom=[e for e in bm.edges], offset=0.0003, segments=2, affect="EDGES", clamp_overlap=True)
    objs.append(mesh_object("Pencil body", bm, paint, 25.0))
    objs.append(lathe_x("Pencil tip", [(r * 0.98, 0.150), (0.0011, 0.1665), (0.0007, 0.1675)], cedar))
    objs.append(lathe_x("Pencil lead", [(0.0007, 0.1675), (0.00012, 0.1700), (0.0, 0.1701)], graphite))
    rf = r * math.cos(math.pi / 6)          # crimped ferrule: as wide as the flats, so the pencil lies level
    objs.append(lathe_x("Pencil ferrule", [(0.0, -0.0001), (rf, -0.0001), (rf, -0.0095), (0.0, -0.0095)], brass))
    objs.append(lathe_x("Pencil eraser", [(0.0, -0.0095), (rf * 0.95, -0.0095), (rf * 0.93, -0.0160), (rf * 0.6, -0.0168), (0.0, -0.0169)], eraser))
    m = Matrix.Translation(Vector(at)) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Translation((0, 0, r * math.cos(math.pi / 6)))
    for o in objs:
        o.matrix_world = m
    return objs


def lathe_x(name, profile, mat):
    """Lathe about the object x axis; profile is (radius, x)."""
    obj = lathe(name, [(rr, xx) for rr, xx in profile], mat, 48)
    me = obj.data
    me.transform(Matrix.Rotation(math.pi / 2, 4, "Y"))
    return obj


# ----------------------------------------------------------------------------------------------- world, camera
def hdri_world():
    """The panorama lights the scene and is the defocused background; only rotated (no extra lamps)."""
    world = bpy.data.worlds.new("Sunlit apartment (photo_studio_loft_hall)")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(HDRI), check_existing=True)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value[2] = math.radians(LOOK_PARAMS["hdri_rotation_deg"])
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = LOOK_PARAMS["hdri_strength"]
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return {"hdri": str(HDRI), "rotation_z_deg": LOOK_PARAMS["hdri_rotation_deg"], "strength": LOOK_PARAMS["hdri_strength"]}


def camera():
    data = bpy.data.cameras.new("Fixed tabletop camera")
    cam = link(bpy.data.objects.new("Fixed tabletop camera", data))
    P = LOOK_PARAMS
    cam.location = P["camera_at"]
    cam.rotation_euler = (Vector(P["camera_aim"]) - Vector(P["camera_at"])).to_track_quat("-Z", "Y").to_euler()
    data.lens = P["lens_mm"]
    data.sensor_width = 36.0
    data.sensor_fit = "HORIZONTAL"
    data.clip_start = 0.01
    data.clip_end = 60.0
    data.dof.use_dof = True
    data.dof.aperture_fstop = P["fstop"]
    data.dof.focus_distance = (Vector(P["focus_at"]) - Vector(P["camera_at"])).length
    bpy.context.scene.camera = cam
    return cam


def camera_record(scene, cam):
    bpy.context.view_layer.update()
    w, h = scene.render.resolution_x, scene.render.resolution_y
    fx = cam.data.lens / cam.data.sensor_width * w
    return {"object_name": cam.name, "matrix_world": [list(map(float, r)) for r in cam.matrix_world],
            "lens_mm": cam.data.lens, "sensor_width_mm": cam.data.sensor_width, "sensor_fit": cam.data.sensor_fit,
            "shift": [cam.data.shift_x, cam.data.shift_y], "clip": [cam.data.clip_start, cam.data.clip_end],
            "resolution": [w, h], "intrinsics": [[fx, 0, w / 2 - cam.data.shift_x * w], [0, fx, h / 2 + cam.data.shift_y * w], [0, 0, 1]],
            "dof": {"fstop": cam.data.dof.aperture_fstop, "focus_distance_m": cam.data.dof.focus_distance},
            "convention": "Blender camera: looks along its local -Z, +Y up; world z up, metres; desk top at z = 0.760",
            "evaluated_after_view_layer_update": True}


# ----------------------------------------------------------------------------------------------- replay
def ruler_world(rest, curve, ss, z0):
    """The accepted renderer's mapping (render_scene.animate_state), unchanged."""
    xxx = rest[:, 0]
    free = xxx >= 0
    xyz = rest.copy()
    xyz[:, 2] += z0
    theta = np.interp(xxx[free], ss, curve[:, 2])
    xyz[free, 0] = np.interp(xxx[free], ss, curve[:, 0]) - np.sin(theta) * rest[free, 2]
    xyz[free, 2] = np.interp(xxx[free], ss, curve[:, 1]) + np.cos(theta) * rest[free, 2]
    return xyz


def coin_matrix(state):
    x, z, angle = (float(v) for v in state)
    # Pitch reduced to (-pi, pi] before mathutils builds the rotation in single precision: unchanged for every published
    # case (|pitch| < pi), and exact to float32 for a coin that has spun many turns (DELETE ruler: the coin on the floor).
    angle = math.remainder(angle, math.tau)
    return Matrix.Translation((x, 0, z)) @ Matrix.Rotation(-angle, 4, "Y")


def apply_state(frame, cache, z0, ruler, rests, coins):
    curve = cache["beam_curves"][frame]
    for obj, rest in zip(ruler, rests):
        obj.data.vertices.foreach_set("co", ruler_world(rest, curve, cache["arc_length"], z0).astype(np.float32).ravel())
        obj.data.update()
    for b, coin in enumerate(coins):
        if coin is not None:
            coin.matrix_world = coin_matrix(cache["coin_states"][frame, b])
    bpy.context.view_layer.update()


def ruler_hash(ruler):
    parts = []
    for o in ruler:
        co = np.empty(len(o.data.vertices) * 3, np.float32)
        o.data.vertices.foreach_get("co", co)
        parts.append(co.tobytes())
    return hashlib.sha256(b"".join(parts)).hexdigest()


# ----------------------------------------------------------------------------------------------- render setup
def render_settings(scene, a):
    scene.render.engine = "CYCLES"
    cy = scene.cycles
    cy.samples = a.samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.006
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    cy.denoising_prefilter = "ACCURATE"
    cy.max_bounces = 12
    cy.diffuse_bounces = 4
    cy.glossy_bounces = 6
    cy.transmission_bounces = 12
    cy.transparent_max_bounces = 12
    cy.sample_clamp_indirect = 4.0
    cy.blur_glossy = 0.5
    cy.caustics_reflective = False
    cy.caustics_refractive = True
    cy.seed = SEED
    cy.use_animated_seed = False
    scene.render.use_motion_blur = False
    scene.render.use_persistent_data = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.fps, scene.render.fps_base = 24, 1
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = LOOK_PARAMS["exposure"]
    scene.render.film_transparent = False
    devices = []
    if a.device == "gpu":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = backend
                prefs.get_devices_for_type(backend)
            except (TypeError, ValueError):
                continue
            gpus = [d for d in prefs.devices if d.type == backend]
            if gpus:
                for d in prefs.devices:
                    d.use = d.id == gpus[0].id
                devices = [{"name": d.name, "type": d.type, "id": d.id} for d in gpus[:1]]
                break
        if not devices:
            raise RuntimeError("no OptiX/CUDA device visible (set CUDA_VISIBLE_DEVICES to one idle GPU)")
        cy.device = "GPU"
    else:
        cy.device = "CPU"
        scene.render.threads_mode = "FIXED"
        scene.render.threads = a.threads
    kit.lens_finish(scene, vignette=0.12, dispersion=0.003)
    return devices


# ----------------------------------------------------------------------------------------------- main
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--cache-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", type=int, nargs="*", help="1-based video frames; default all")
    p.add_argument("--samples", type=int, default=512)
    p.add_argument("--device", choices=("cpu", "gpu"), default="gpu")
    p.add_argument("--threads", type=int, default=32)
    p.add_argument("--save-scene", action="store_true")
    a = p.parse_args(argv)
    sim = json.loads((a.cache_dir / "simulation_config.json").read_text())
    cfg, count, fps = sim["physics"], sim["video_frames"], sim["fps"]
    cache = {k: v for k, v in np.load(a.cache_dir / "simulation.npz").items()}
    if not np.allclose(cache["times"], np.arange(count + 1) / fps, atol=1e-13, rtol=0):
        raise RuntimeError("cached sample times differ from the video clock i/24")
    frames = a.frames or list(range(1, count + 1))
    if any(f < 1 or f > count for f in frames):
        raise ValueError("frames are 1..%d" % count)
    a.out.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    world = hdri_world()
    desk = build_desk()
    ruler_present = bool(cfg.get("ruler_present", [1])[0])   # DELETE ruler: no strip, no printed scale
    book = build_book(on_ruler=ruler_present)
    ruler = build_ruler(cfg) if ruler_present else []
    rests = [np.array([v.co[:] for v in o.data.vertices], float) for o in ruler]
    present = [bool(x) for x in cache["present"]]
    coins = [build_coin(cfg, "Coin" if b == 0 else "Second coin") if present[b] else None for b in range(2)]
    mug = stoneware_mug((-0.33, 0.30, DESK_TOP))
    pen = pencil((-0.135, -0.150, DESK_TOP), math.radians(-28))
    dust = kit.sawdust("Desk dust and eraser crumbs", [(-0.70, -0.65, -0.01, 0.95, 1)], 700,
                       ((KEEPOUT[0][0], KEEPOUT[0][1]), (KEEPOUT[1][0], KEEPOUT[1][1])),
                       color=(0.58, 0.55, 0.50), seed=11, size=(0.0002, 0.0007), z=DESK_TOP)
    # Dust flecks are rejected one by one inside the keep-out footprint (kit.sawdust); props are checked whole.
    audit = {name: kit.assert_clear(objs, KEEPOUT, name) for name, objs in (("mug", mug), ("pencil", pen))}
    audit["dust_flecks"] = len(dust.data.polygons)
    cam = camera()
    devices = render_settings(scene, a)
    record = camera_record(scene, cam)
    kit.write_json(a.out / "camera.json", record)
    np.savez_compressed(a.out / "ruler_render_binding.npz", midplane_z_m=np.array(cfg["ruler_midplane_z_m"]),
                        **{f"rest_{i}": r for i, r in enumerate(rests)})
    definition = hashlib.sha256((str(a.samples) + json.dumps(record, sort_keys=True) + json.dumps(LOOK_PARAMS, sort_keys=True)
                                 + sha(a.cache_dir / "simulation.npz")).encode()).hexdigest()
    journal = a.out / "render_replay.jsonl"
    done = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            e = json.loads(line)
            if e["definition_sha256"] == definition:
                done[e["frame"]] = e
    t0 = time.time()
    for f in frames:
        apply_state(f - 1, cache, cfg["ruler_midplane_z_m"], ruler, rests, coins)
        if a.save_scene and f == frames[0]:
            bpy.ops.wm.save_as_mainfile(filepath=str(a.out / "scene.blend"), compress=True)
        target = a.out / f"frame_{f:04d}.png"
        if target.exists() and f in done:
            continue
        scene.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        entry = {"frame": f, "time_s": float(cache["times"][f - 1]), "definition_sha256": definition,
                 "coin_matrices": [[list(map(float, r)) for r in c.matrix_world] if c is not None else None for c in coins],
                 "ruler_vertex_sha256": ruler_hash(ruler), "host": platform.node(),
                 "device": devices[0]["name"] if devices else "CPU"}
        with journal.open("a") as s:
            s.write(json.dumps(entry) + "\n")
        print("RENDERED", f, round(time.time() - t0, 1), flush=True)
    kit.write_json(a.out / "realism_provenance.json", {
        "look": LOOK,
        "blender": bpy.app.version_string, "host": kit.host_record(), "devices": devices or "CPU",
        "samples": a.samples, "adaptive_threshold": scene.cycles.adaptive_threshold, "denoiser": "OpenImageDenoise",
        "seed": SEED, "resolution": [1280, 720], "fps": fps, "frames": [min(frames), max(frames), len(frames)],
        "native_cache": str(a.cache_dir / "simulation.npz"), "native_cache_sha256": sha(a.cache_dir / "simulation.npz"),
        "look_params": LOOK_PARAMS, "world": world, "camera": record, "keepout_m": KEEPOUT, "dressing": audit,
        "assets": {"hdri": str(HDRI), "desk_wood": str(OAK), "floor": str(FLOOR), "book_cloth": str(LINEN)},
        "definition_sha256": definition})
    print("COMPLETE", a.out, flush=True)


if __name__ == "__main__":
    main()
