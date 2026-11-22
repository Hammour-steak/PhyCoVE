"""Current look of scarf_chair_slip, built directly from a case's native solver output.

    blender -b --factory-startup --disable-autoexec --python-exit-code 1 --python appearance/realism.py -- \
        --case CASE --native assets/scenes/scarf_chair_slip/native/CASE --out OUT \
        [--frames 1-96] [--samples 256] [--device OPTIX|CUDA|CPU] [--width 1280]

What comes from the solve: the scarf's 96 native shell states (written to OUT/cloth.mdd and played by a Mesh
Cache modifier, so motion blur sees the solver's own frame-to-frame motion, linearly interpolated), the chair
and book transforms (keyed per frame) and the frame clock. The chair is the accepted chair model, the
book the configured box size. What belongs to the look: a study corner of a lived-in bedroom (plastered walls,
oak floor, a timber window with sheer curtains in the left wall, desk, shelves, books, plants), daylight from that
window only (sun plus sky through the opening), scanned Poly Haven materials at real-world size, and the fixed
camera of appearance/view.py (also used by tools/export_ground_truth.py).
"""
from pathlib import Path
import argparse
import json
import math
import struct
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
SCENE_DIR = HERE.parent
REPO = SCENE_DIR.parents[2]
sys.path[:0] = [str(HERE), str(SCENE_DIR / "physics"), str(REPO / "scripts")]
from common import ASSETS, LAYOUT, sha  # noqa: E402
from edit_vocab import resolve  # noqa: E402
import render_replay as rr  # noqa: E402  accepted helpers: chair/desk loading, scarf fabric
import pcve_realism_kit as kit  # noqa: E402
from pcve_assets import asset  # noqa: E402
from view import CAMERA  # noqa: E402

PH = asset("polyhaven")
LOOK = "accepted_look"
# Room shell (metres). The chair stands at the origin facing -y; the desk is the accepted desk at x -1.49..-0.33.
WALL = dict(left=-1.58, right=3.00, back=1.80, front=-3.00, height=2.70, t=0.14)
WINDOW = dict(y0=-0.48, y1=0.88, z0=0.86, z1=2.28)        # opening in the left wall
SUN_DIR = Vector((0.72, 0.10, -0.69)).normalized()        # direction of travel: in through the window
# Swept volume of every case (chair, scarf on seat, scarf on floor when the chair is deleted) plus margin.
KEEPOUT = ((-0.36, -0.62, -0.01), (0.36, 0.42, 1.25))


# ------------------------------------------------------------------ materials
def _tex(nodes, links, path, vector, colour=False, box=0.0):
    node = nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(str(path), check_existing=True)
    node.image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    if box:
        node.projection = "BOX"
        node.projection_blend = box
    links.new(vector, node.inputs["Vector"])
    return node.outputs["Color"]


def _mapping(nodes, links, size, coord="Object", offset=(0.0, 0.0, 0.0), rot_z=0.0):
    tc = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    sx, sy = (size, size) if not isinstance(size, (tuple, list)) else size
    mp.inputs["Scale"].default_value = (1.0 / sx, 1.0 / sy, 1.0 / sx)
    mp.inputs["Location"].default_value = offset
    mp.inputs["Rotation"].default_value = (0.0, 0.0, rot_z)
    links.new(tc.outputs[coord], mp.inputs["Vector"])
    return mp.outputs["Vector"]


def scan(name, folder, prefix, size, res="2k", coord="Object", box=0.15, rough=(0.0, 1.0), normal=1.0,
         tint=None, tint_mix=0.0, specular=0.5, offset=(0.0, 0.0, 0.0), rot_z=0.0, coat=0.0, value=1.0):
    """PBR material from a Poly Haven diff/rough/nor_gl set mapped at its real-world size (metres per tile)."""
    folder = Path(folder)
    res = next((r for r in (res, "2k", "4k", "1k", "8k") if (folder / f"{prefix}_diff_{r}.jpg").is_file()), res)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = nodes.get("Principled BSDF")
    vec = _mapping(nodes, links, size, coord, offset, rot_z)
    b = box if coord == "Object" else 0.0
    color = _tex(nodes, links, folder / f"{prefix}_diff_{res}.jpg", vec, True, b)
    if tint is not None or value != 1.0:
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = tint_mix
        links.new(color, mix.inputs["A"])
        mix.inputs["B"].default_value = (*(tint or (1, 1, 1)), 1.0)
        hsv = nodes.new("ShaderNodeHueSaturation")
        hsv.inputs["Value"].default_value = value
        links.new(mix.outputs["Result"], hsv.inputs["Color"])
        color = hsv.outputs["Color"]
    links.new(color, bs.inputs["Base Color"])
    rough_path = folder / f"{prefix}_rough_{res}.jpg"
    if rough_path.is_file():
        r = _tex(nodes, links, rough_path, vec, False, b)
        rng = nodes.new("ShaderNodeMapRange")
        rng.inputs["To Min"].default_value, rng.inputs["To Max"].default_value = rough
        links.new(r, rng.inputs["Value"])
        links.new(rng.outputs["Result"], bs.inputs["Roughness"])
    else:
        bs.inputs["Roughness"].default_value = sum(rough) / 2
    nor_path = folder / f"{prefix}_nor_gl_{res}.jpg"
    if nor_path.is_file() and normal > 0:
        n = _tex(nodes, links, nor_path, vec, False, b)
        nm = nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal
        links.new(n, nm.inputs["Color"])
        links.new(nm.outputs["Normal"], bs.inputs["Normal"])
    bs.inputs["Specular IOR Level"].default_value = specular
    if coat:
        bs.inputs["Coat Weight"].default_value = coat
        bs.inputs["Coat Roughness"].default_value = 0.18
    return mat


def plain(name, color, rough=0.6, metal=0.0, specular=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1.0)
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Metallic"].default_value = metal
    bs.inputs["Specular IOR Level"].default_value = specular
    return mat


def box(name, lo, hi, mat, bevel=0.0):
    lo, hi = Vector(lo), Vector(hi)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(lo + hi) / 2)
    ob = bpy.context.object
    ob.name = name
    ob.dimensions = hi - lo
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        ob.data.materials.append(mat)
    if bevel:
        m = ob.modifiers.new("Eased edge", "BEVEL")
        m.width = bevel
        m.segments = 3
        m.limit_method = "ANGLE"
        ob.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
        for p in ob.data.polygons:
            p.use_smooth = True
    return ob


# ------------------------------------------------------------------ room
def room():
    W, Wi = WALL, WINDOW
    t = W["t"]
    floor = scan("Oak strip floor, oiled (Poly Haven wood_floor scan)", ASSETS / "wood_floor", "wood_floor", 2.0,
                 rough=(0.30, 0.62), normal=0.45, value=0.92)
    box("Floor", (W["left"] - t, W["front"] - t, -0.05), (W["right"] + t, W["back"] + t, 0.0), floor)
    plaster = scan("Warm white emulsion over plaster (Poly Haven painted_plaster_wall)", PH / "painted_plaster_wall",
                   "painted_plaster_wall", 2.4, rough=(0.80, 0.95), normal=0.25, tint=(0.93, 0.90, 0.84),
                   tint_mix=0.55, value=1.05, specular=0.3)
    kit.add_wall_mottling(plaster, 0.035, 0.00012)
    ceiling = plain("Flat white ceiling paint", (0.80, 0.79, 0.76), 0.92, specular=0.25)
    H = W["height"]
    box("Back wall", (W["left"] - t, W["back"], 0), (W["right"] + t, W["back"] + t, H), plaster)
    box("Right wall", (W["right"], W["front"], 0), (W["right"] + t, W["back"], H), plaster)
    box("Front wall", (W["left"] - t, W["front"] - t, 0), (W["right"] + t, W["front"], H), plaster)
    box("Ceiling", (W["left"] - t, W["front"] - t, H), (W["right"] + t, W["back"] + t, H + 0.1), ceiling)
    x0, x1 = W["left"] - t, W["left"]
    box("Left wall below window", (x0, W["front"], 0), (x1, W["back"], Wi["z0"]), plaster)
    box("Left wall above window", (x0, W["front"], Wi["z1"]), (x1, W["back"], H), plaster)
    box("Left wall near pier", (x0, W["front"], Wi["z0"]), (x1, Wi["y0"], Wi["z1"]), plaster)
    box("Left wall far pier", (x0, Wi["y1"], Wi["z0"]), (x1, W["back"], Wi["z1"]), plaster)
    # Painted timber skirting with a rounded top and a hairline caulk joint.
    trim = plain("Satin white skirting paint", (0.78, 0.77, 0.73), 0.38, specular=0.45)
    box("Back skirting", (W["left"], W["back"] - 0.018, 0), (W["right"], W["back"], 0.11), trim, 0.004)
    box("Right skirting", (W["right"] - 0.018, W["front"], 0), (W["right"], W["back"], 0.11), trim, 0.004)
    box("Left skirting near", (W["left"], W["front"], 0), (W["left"] + 0.018, W["back"], 0.11), trim, 0.004)
    # Window: painted softwood casement frame, double glazing, deep sill.
    frame = plain("Window frame, white gloss paint on timber", (0.80, 0.79, 0.76), 0.30, specular=0.5)
    xf0, xf1 = W["left"] - 0.10, W["left"] - 0.02
    b = 0.055
    box("Window head", (xf0, Wi["y0"], Wi["z1"] - b), (xf1, Wi["y1"], Wi["z1"]), frame, 0.003)
    box("Window bottom rail", (xf0, Wi["y0"], Wi["z0"]), (xf1, Wi["y1"], Wi["z0"] + 0.07), frame, 0.003)
    box("Window near jamb", (xf0, Wi["y0"], Wi["z0"]), (xf1, Wi["y0"] + b, Wi["z1"]), frame, 0.003)
    box("Window far jamb", (xf0, Wi["y1"] - b, Wi["z0"]), (xf1, Wi["y1"], Wi["z1"]), frame, 0.003)
    ym = (Wi["y0"] + Wi["y1"]) / 2
    box("Window meeting stiles", (xf0, ym - 0.045, Wi["z0"]), (xf1, ym + 0.045, Wi["z1"]), frame, 0.003)
    zt = Wi["z0"] + 0.66 * (Wi["z1"] - Wi["z0"])
    box("Window transom", (xf0, Wi["y0"], zt - 0.03), (xf1, Wi["y1"], zt + 0.03), frame, 0.003)
    glass = bpy.data.materials.new("Float glass")
    glass.use_nodes = True
    gb = glass.node_tree.nodes.get("Principled BSDF")
    gb.inputs["Transmission Weight"].default_value = 1.0
    gb.inputs["Roughness"].default_value = 0.02
    gb.inputs["IOR"].default_value = 1.5
    gb.inputs["Base Color"].default_value = (0.94, 0.97, 0.96, 1)
    pane = box("Window glazing", (xf0 + 0.035, Wi["y0"], Wi["z0"]), (xf0 + 0.041, Wi["y1"], Wi["z1"]), glass)
    pane.visible_shadow = False
    box("Window sill board", (W["left"] - 0.02, Wi["y0"] - 0.05, Wi["z0"] - 0.025),
        (W["left"] + 0.05, Wi["y1"] + 0.05, Wi["z0"]), frame, 0.004)
    # Reveal linings inside the opening.
    box("Window reveal head", (W["left"] - t, Wi["y0"], Wi["z1"]), (W["left"], Wi["y1"], Wi["z1"] + 0.01), plaster)
    return dict(walls="painted_plaster_wall 2.4 m tile", floor="wood_floor 2.0 m tile",
                window_opening_m=[Wi["y0"], Wi["y1"], Wi["z0"], Wi["z1"]])


def curtains():
    """Two sheer voile panels on a rod, mostly drawn; they diffuse the sun instead of blocking it."""
    Wi = WINDOW
    rod_mat = plain("Brushed steel curtain rod", (0.55, 0.55, 0.53), 0.32, metal=1.0)
    x = WALL["left"] + 0.09
    bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=Wi["y1"] - Wi["y0"] + 0.5, location=(x, (Wi["y0"] + Wi["y1"]) / 2, Wi["z1"] + 0.14),
                                        rotation=(math.pi / 2, 0, 0))
    rod = bpy.context.object
    rod.name = "Curtain rod"
    rod.data.materials.append(rod_mat)
    for y in (Wi["y0"] - 0.2, Wi["y1"] + 0.2):
        box("Curtain rod bracket", (WALL["left"], y - 0.008, Wi["z1"] + 0.125), (x + 0.012, y + 0.008, Wi["z1"] + 0.155), rod_mat)
    voile = bpy.data.materials.new("Sheer cotton voile")
    voile.use_nodes = True
    nodes, links = voile.node_tree.nodes, voile.node_tree.links
    out = nodes.get("Material Output")
    bs = nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (0.86, 0.85, 0.80, 1)
    bs.inputs["Roughness"].default_value = 0.9
    bs.inputs["Sheen Weight"].default_value = 0.3
    trans = nodes.new("ShaderNodeBsdfTranslucent")
    trans.inputs["Color"].default_value = (0.86, 0.84, 0.78, 1)
    clear = nodes.new("ShaderNodeBsdfTransparent")
    m1 = nodes.new("ShaderNodeMixShader")
    m1.inputs[0].default_value = 0.45
    links.new(bs.outputs[0], m1.inputs[1])
    links.new(trans.outputs[0], m1.inputs[2])
    m2 = nodes.new("ShaderNodeMixShader")
    m2.inputs[0].default_value = 0.42   # open weave: share of light passing straight through
    links.new(m1.outputs[0], m2.inputs[1])
    links.new(clear.outputs[0], m2.inputs[2])
    links.new(m2.outputs[0], out.inputs["Surface"])
    record = []
    span = Wi["y1"] - Wi["y0"]
    for k, (ya, yb) in enumerate(((Wi["y0"] - 0.22, Wi["y0"] + 0.40 * span), (Wi["y0"] + 0.53 * span, Wi["y1"] + 0.22))):
        import random
        rng = random.Random(41 + k)
        n_u, n_v = 140, 70
        width = yb - ya
        # Irregular gathered folds: alternating crests and troughs at random spacing and depth, fanning out
        # slightly towards the hem as a hanging voile does.
        stops, s = [0.0], 0.0
        while s < width:
            s += rng.uniform(0.045, 0.085)
            stops.append(min(s, width))
        amps = [rng.uniform(0.012, 0.03) * (1 if n % 2 else -1) for n in range(len(stops))]
        verts, faces = [], []
        z_top, z_bot = Wi["z1"] + 0.12, 0.015 if k == 0 else 0.025
        for j in range(n_v):
            v = j / (n_v - 1)
            z = z_top + (z_bot - z_top) * v
            fan = [c + (c - width / 2) * 0.05 * v for c in stops]
            for i in range(n_u):
                um = width * i / (n_u - 1)
                n = max(0, min(len(fan) - 2, next((q for q in range(len(fan) - 1) if fan[q + 1] >= um), len(fan) - 2)))
                f = (um - fan[n]) / max(fan[n + 1] - fan[n], 1e-6)
                f = 0.5 - 0.5 * math.cos(math.pi * min(max(f, 0.0), 1.0))
                depth = (amps[n] * (1 - f) + amps[n + 1] * f) * (0.75 + 0.45 * v) \
                    + 0.003 * math.sin(um * 61.0 + v * 7.0 + k) * v
                verts.append((x + 0.05 + depth, ya + um, z + 0.004 * math.sin(um * 23.0 + k) * v))
        for j in range(n_v - 1):
            for i in range(n_u - 1):
                a = j * n_u + i
                faces.append((a, a + 1, a + n_u + 1, a + n_u))
        mesh = bpy.data.meshes.new(f"Sheer curtain panel {k}")
        mesh.from_pydata(verts, [], faces)
        for p in mesh.polygons:
            p.use_smooth = True
        ob = bpy.data.objects.new(f"Sheer curtain panel {k}", mesh)
        bpy.context.collection.objects.link(ob)
        mesh.materials.append(voile)
        record.append(dict(panel=k, y_m=[ya, yb]))
    return record


def daylight(scene, hdri="residential_garden", sun_energy=3.2, sky=1.0, rotation_deg=0.0):
    world = bpy.data.worlds.new("Daylight outside the window")
    world.use_nodes = True
    scene.world = world
    nodes, links = world.node_tree.nodes, world.node_tree.links
    bg = nodes.get("Background")
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(next((PH / hdri).glob("*.hdr"))), check_existing=True)
    tc = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(rotation_deg))
    links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    links.new(mp.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = sky
    sun = kit.sun("Afternoon sun", tuple(SUN_DIR), sun_energy, angle_deg=1.0, color=(1.0, 0.93, 0.84))
    # Sky portal over the opening: guides sky sampling through the window, adds no light of its own.
    Wi = WINDOW
    data = bpy.data.lights.new("Window sky portal", "AREA")
    data.shape = "RECTANGLE"
    data.size, data.size_y = Wi["y1"] - Wi["y0"], Wi["z1"] - Wi["z0"]
    try:
        data.cycles.is_portal = True
    except AttributeError:
        data.is_portal = True
    portal = bpy.data.objects.new("Window sky portal", data)
    bpy.context.collection.objects.link(portal)
    portal.location = (WALL["left"] - 0.12, (Wi["y0"] + Wi["y1"]) / 2, (Wi["z0"] + Wi["z1"]) / 2)
    portal.rotation_euler = Vector((1, 0, 0)).to_track_quat("-Z", "Y").to_euler()
    return dict(hdri=hdri, sky_strength=sky, sun_energy=sun_energy, sun_direction=list(SUN_DIR))


# ------------------------------------------------------------------ furniture and props
def furniture():
    oak = scan("Ash veneer desk, satin lacquer (Poly Haven ash_veneer)", PH / "ash_veneer", "ash_veneer", 1.0,
               res="4k", rough=(0.30, 0.52), normal=0.35, coat=0.25, specular=0.5, tint=(0.92, 0.80, 0.64), tint_mix=0.6)
    desk = rr.asset("desk", loc=(-0.91, -0.035, 0.0), width=1.16)
    for ob in desk.children:
        if ob.type == "MESH":
            ob.data.materials.clear()
            ob.data.materials.append(oak)
    lo, hi = kit.world_bbox([o for o in desk.children if o.type == "MESH"])
    record = dict(desk=dict(bbox_low=list(lo), bbox_high=list(hi), material="ash_veneer"))
    top = hi.z
    props = []
    props.append(kit.prop(PH, "potted_plant_04", (-1.30, 0.20, top), rot_z=0.4, keepout=KEEPOUT))
    props.append(kit.prop(PH, "ceramic_vase_04", (-0.62, 0.17, top), rot_z=1.1, keepout=KEEPOUT))
    props.append(kit.prop(PH, "wooden_bowl_02", (-1.22, -0.18, top), rot_z=0.3, keepout=KEEPOUT))
    props.append(kit.prop(PH, "wooden_display_shelves_01", (1.10, WALL["back"] - 0.20, 0.0), rot_z=math.pi / 2, keepout=KEEPOUT))
    props.append(desk_things(top))
    # Double socket on the back wall at skirting height: off-white plate, no lettering.
    plate = plain("Socket plate, off-white plastic", (0.74, 0.73, 0.69), 0.45, specular=0.4)
    dark = plain("Socket apertures", (0.03, 0.03, 0.03), 0.8)
    box("Double socket plate", (0.20, WALL["back"] - 0.009, 0.25), (0.346, WALL["back"], 0.336), plate, 0.002)
    for xc in (0.237, 0.309):
        for dx, dz in ((-0.009, 0.006), (0.009, 0.006), (0.0, -0.009)):
            box("Socket pin hole", (xc + dx - 0.002, WALL["back"] - 0.0095, 0.293 + dz - 0.003),
                (xc + dx + 0.002, WALL["back"] - 0.0085, 0.293 + dz + 0.003), dark)
    record["props"] = props
    record["shelf_dressing"] = shelf_dressing()
    return record


def desk_things(top):
    """A closed notebook, a pencil and a glazed mug with tea on the desk, clear of the chair."""
    cover = plain("Notebook cloth cover, slate blue", (0.10, 0.14, 0.19), 0.85, specular=0.3)
    paper = plain("Notebook page edges", (0.76, 0.73, 0.66), 0.9, specular=0.3)
    box("Notebook pages", (-1.02, -0.27, top + 0.0012), (-0.80, -0.11, top + 0.0128), paper, 0.0008)
    for z in (top, top + 0.0128):
        box("Notebook cover", (-1.025, -0.275, z), (-0.795, -0.105, z + 0.0012), cover, 0.0005)
    box("Notebook spine", (-1.027, -0.275, top), (-1.019, -0.105, top + 0.014), cover, 0.002)
    lacquer = plain("Pencil, yellow lacquer", (0.62, 0.42, 0.06), 0.4, specular=0.5)
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.0036, depth=0.175,
                                        location=(-0.70, -0.20, top + 0.0036), rotation=(0, math.pi / 2, 0.35))
    pencil = bpy.context.object
    pencil.name = "Pencil"
    pencil.data.materials.append(lacquer)
    glaze = plain("Mug, speckled stoneware glaze", (0.70, 0.66, 0.58), 0.22, specular=0.5)
    verts, faces = [], []
    rings = [(0.0, 0.0), (0.036, 0.0), (0.040, 0.004), (0.041, 0.090), (0.0405, 0.094), (0.037, 0.094), (0.036, 0.010), (0.0, 0.010)]
    cx, cy = -0.58, -0.24
    for r, z in rings:
        for j in range(64):
            a = 2 * math.pi * j / 64
            verts.append((cx + r * math.cos(a), cy + r * math.sin(a), top + z))
    for q in range(len(rings) - 1):
        for j in range(64):
            faces.append((q * 64 + j, q * 64 + (j + 1) % 64, (q + 1) * 64 + (j + 1) % 64, (q + 1) * 64 + j))
    mesh = bpy.data.meshes.new("Mug")
    mesh.from_pydata(verts, [], faces)
    for p in mesh.polygons:
        p.use_smooth = True
    mug = bpy.data.objects.new("Mug", mesh)
    bpy.context.collection.objects.link(mug)
    mesh.materials.append(glaze)
    handle = bpy.data.curves.new("Mug handle", "CURVE")
    handle.dimensions = "3D"
    handle.bevel_depth = 0.006
    spline = handle.splines.new("POLY")
    pts = [(cx + 0.040 + 0.026 * math.sin(t), cy, top + 0.048 + 0.028 * math.cos(t)) for t in np.linspace(0.15, math.pi - 0.15, 17)]
    spline.points.add(len(pts) - 1)
    for pt, co in zip(spline.points, pts):
        pt.co = (*co, 1)
    hob = bpy.data.objects.new("Mug handle", handle)
    bpy.context.collection.objects.link(hob)
    handle.materials.append(glaze)
    tea = plain("Tea", (0.05, 0.022, 0.008), 0.05, specular=0.5)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.0362, depth=0.001, location=(cx, cy, top + 0.072))
    bpy.context.object.name = "Tea surface"
    bpy.context.object.data.materials.append(tea)
    kit.assert_clear([mug, pencil], KEEPOUT, "desk things")
    return dict(label="notebook, pencil, mug", desk_top_m=top)


BOOK_CLOTH = ((0.075, 0.105, 0.17), (0.32, 0.12, 0.07), (0.20, 0.23, 0.15), (0.42, 0.40, 0.36), (0.55, 0.47, 0.33),
              (0.12, 0.12, 0.12), (0.30, 0.18, 0.20), (0.62, 0.58, 0.50))


def books_row(x0, z, y_front, rng, count, lean_last=True):
    """Upright clothbound books (cover boards around an off-white page block, plain spines) from x0 towards +x."""
    pages = bpy.data.materials.get("Book page edges, off-white") or plain("Book page edges, off-white", (0.74, 0.70, 0.60), 0.85, specular=0.3)
    x = x0
    made = []
    for k in range(count):
        h, d, t = rng.uniform(0.19, 0.27), rng.uniform(0.13, 0.19), rng.uniform(0.018, 0.042)
        name = f"Shelf book cloth {k}"
        cloth = plain(name, BOOK_CLOTH[rng.randrange(len(BOOK_CLOTH))], rng.uniform(0.55, 0.8), specular=0.35)
        cover = box("Shelf book cover", (x, y_front, z), (x + t, y_front + d, z + h), cloth, 0.0012)
        block = box("Shelf book pages", (x + 0.0015, y_front + 0.004, z + 0.002), (x + t - 0.0015, y_front + d + 0.002, z + h - 0.002), pages)
        made += [cover, block]
        x += t + rng.uniform(0.0, 0.002)
    return made, x


def shelf_dressing():
    """Props in the cubbies of the display shelves (boards measured on the scanned model: tops at 0.413, 0.790,
    1.165 and 1.542 m; cubby columns 0.56-0.92, 0.92-1.28, 1.28-1.64 m; depth 1.414-1.786 m)."""
    import random
    rng = random.Random(22)
    yf = 1.47
    made = []
    rows, x_end = books_row(0.60, 1.165, yf, rng, 7)
    made += rows
    rows, _ = books_row(0.96, 0.79, yf, rng, 5)
    made += rows
    # A short stack lying flat in the left cubby of the middle board.
    for k, (t, w, d) in enumerate(((0.03, 0.24, 0.17), (0.025, 0.22, 0.16), (0.035, 0.205, 0.15))):
        z0 = 0.79 + sum(s[0] for s in ((0.03, 0, 0), (0.025, 0, 0), (0.035, 0, 0))[:k])
        cloth = plain(f"Stacked book cloth {k}", BOOK_CLOTH[(k * 3 + 1) % len(BOOK_CLOTH)], 0.7, specular=0.35)
        made.append(box("Stacked book", (0.62, yf, z0), (0.62 + w, yf + d, z0 + t), cloth, 0.0012))
    placed = [kit.prop(PH, "antique_ceramic_vase_01", (0.78, 1.60, 0.413), rot_z=0.8, keepout=KEEPOUT),
              kit.prop(PH, "potted_plant_04", (0.80, 1.60, 1.542), rot_z=1.9, keepout=KEEPOUT),
              kit.prop(PH, "wooden_bowl_02", (1.10, 1.60, 1.165), rot_z=0.2, keepout=KEEPOUT)]
    return dict(books=len(made), props=placed, books_end_x=x_end)


def chair_look(chair_root):
    oak = scan("Beech, honey-stained, satin (Poly Haven white_maple_veneer)", PH / "white_maple_veneer",
               "white_maple_veneer", 0.9, res="4k", rough=(0.30, 0.52), normal=0.30, tint=(0.86, 0.64, 0.42),
               tint_mix=0.75, coat=0.3, specular=0.5)
    for ob in chair_root.children:
        if ob.type == "MESH":
            ob.data.materials.clear()
            ob.data.materials.append(oak)
    return "white_maple_veneer, honey stain, satin coat"


def book(root, physics):
    loc = np.array(physics["book_location"])
    dims = physics["book_dimensions"]
    cloth = scan("Book cloth cover, dark green (Poly Haven rough_linen texture)", PH / "rough_linen/textures",
                 "rough_linen", 0.25, rough=(0.62, 0.85), normal=0.6, tint=(0.10, 0.20, 0.15), tint_mix=1.0)
    pages = plain("Book page edges, off-white", (0.78, 0.74, 0.64), 0.85, specular=0.3)
    parts = [box("Book page block", loc - np.array([dims[0] / 2 - 0.004, dims[1] / 2 - 0.003, dims[2] / 2 - 0.0025]),
                 loc + np.array([dims[0] / 2 - 0.001, dims[1] / 2 - 0.003, dims[2] / 2 - 0.0025]), pages, 0.001)]
    for s in (-1, 1):
        zc = loc[2] + s * (dims[2] / 2 - 0.00125)
        parts.append(box("Book board cover", (loc[0] - dims[0] / 2, loc[1] - dims[1] / 2, zc - 0.00125),
                         (loc[0] + dims[0] / 2, loc[1] + dims[1] / 2, zc + 0.00125), cloth, 0.0008))
    parts.append(box("Book spine", (loc[0] - dims[0] / 2, loc[1] - dims[1] / 2, loc[2] - dims[2] / 2),
                     (loc[0] - dims[0] / 2 + 0.004, loc[1] + dims[1] / 2, loc[2] + dims[2] / 2), cloth, 0.0015))
    for p in parts:
        p.parent = root
    return "clothbound hardcover, configured box size"


# ------------------------------------------------------------------ scarf
def scarf_look(cfg, positions0, faces, uv, mdd):
    mesh = bpy.data.meshes.new("Native cotton triangles")
    mesh.from_pydata(positions0.tolist(), [], faces.tolist())
    mesh.update()
    ob = bpy.data.objects.new("Cotton scarf / native shell", mesh)
    bpy.context.collection.objects.link(ob)
    layer = mesh.uv_layers.new(name="Material UV")
    for poly in mesh.polygons:
        poly.use_smooth = True
        for li in poly.loop_indices:
            layer.data[li].uv = uv[mesh.loops[li].vertex_index]
    mat = rr.cotton(cfg["material_length_m"])
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    # Plain-weave relief at the real thread pitch (~0.9 mm) and a 6 mm rolled selvedge along both long edges.
    tc = next(n for n in nodes if n.type == "TEX_COORD" and n.outputs["UV"].links)
    metric = nodes.new("ShaderNodeVectorMath")
    metric.operation = "MULTIPLY"
    metric.inputs[1].default_value = (LAYOUT["width"], cfg["material_length_m"], 1.0)
    links.new(tc.outputs["UV"], metric.inputs[0])
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(metric.outputs["Vector"], sep.inputs[0])
    warp = nodes.new("ShaderNodeMath")
    warp.operation = "SINE"
    weft = nodes.new("ShaderNodeMath")
    weft.operation = "SINE"
    for node, axis in ((warp, "X"), (weft, "Y")):
        scale = nodes.new("ShaderNodeMath")
        scale.operation = "MULTIPLY"
        scale.inputs[1].default_value = 2 * math.pi / 0.0009
        links.new(sep.outputs[axis], scale.inputs[0])
        links.new(scale.outputs[0], node.inputs[0])
    weave = nodes.new("ShaderNodeMath")
    weave.operation = "MULTIPLY"
    links.new(warp.outputs[0], weave.inputs[0])
    links.new(weft.outputs[0], weave.inputs[1])
    edge = nodes.new("ShaderNodeMath")       # distance to the nearer long edge, metres
    edge.operation = "MINIMUM"
    links.new(sep.outputs["X"], edge.inputs[0])
    far = nodes.new("ShaderNodeMath")
    far.operation = "SUBTRACT"
    far.inputs[0].default_value = LAYOUT["width"]
    links.new(sep.outputs["X"], far.inputs[1])
    links.new(far.outputs[0], edge.inputs[1])
    hem = nodes.new("ShaderNodeMapRange")
    hem.inputs["From Min"].default_value = 0.0045
    hem.inputs["From Max"].default_value = 0.0065
    hem.inputs["To Min"].default_value = 1.0
    hem.inputs["To Max"].default_value = 0.0
    links.new(edge.outputs[0], hem.inputs["Value"])
    height = nodes.new("ShaderNodeMath")
    height.operation = "MULTIPLY_ADD"
    links.new(hem.outputs["Result"], height.inputs[0])
    height.inputs[1].default_value = 0.6
    links.new(weave.outputs[0], height.inputs[2])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.0002
    links.new(height.outputs[0], bump.inputs["Height"])
    if bs.inputs["Normal"].is_linked:
        links.new(bs.inputs["Normal"].links[0].from_socket, bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bs.inputs["Normal"])
    shade = nodes.new("ShaderNodeMix")      # the rolled hem is denser, so slightly darker
    shade.data_type = "RGBA"
    shade.blend_type = "MULTIPLY"
    links.new(hem.outputs["Result"], shade.inputs["Factor"])
    links.new(bs.inputs["Base Color"].links[0].from_socket, shade.inputs["A"])
    shade.inputs["B"].default_value = (0.78, 0.76, 0.74, 1)
    links.new(shade.outputs["Result"], bs.inputs["Base Color"])
    mesh.materials.append(mat)
    cache = ob.modifiers.new("Native scarf states (cloth.mdd)", "MESH_CACHE")
    cache.cache_format = "MDD"
    cache.filepath = str(mdd)
    cache.frame_start = 1.0
    cache.frame_scale = 1.0
    cache.interpolation = "LINEAR"
    solid = ob.modifiers.new("Textile thickness", "SOLIDIFY")
    solid.thickness = cfg["physics"]["scarf_thickness"]
    solid.offset = 0.0
    return ob


def write_mdd(path, positions, times):
    n, p = positions.shape[:2]
    with open(path, "wb") as f:
        f.write(struct.pack(">2i", n, p))
        f.write(np.asarray(times, ">f4").tobytes())
        f.write(np.asarray(positions, ">f4").tobytes())


# ------------------------------------------------------------------ camera and render settings
def camera(scene, view=None):
    view = view or CAMERA
    loc = Vector(view["location_m"])
    cam_data = bpy.data.cameras.new("Tripod camera")
    cam_data.lens = view["lens_mm"]
    cam_data.sensor_width = CAMERA["sensor_width_mm"]
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.shift_x, cam_data.shift_y = CAMERA["shift"]
    cam = bpy.data.objects.new("Tripod camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(view["target_m"]) - loc).to_track_quat("-Z", "Y").to_euler()
    cam_data.dof.use_dof = True
    cam_data.dof.focus_distance = (Vector((0.0, 0.0, 0.62)) - loc).length
    cam_data.dof.aperture_fstop = 5.6
    scene.camera = cam
    return cam


def settings(scene, args):
    scene.render.engine = "CYCLES"
    cy = scene.cycles
    if args.device == "CPU":
        cy.device = "CPU"
    else:
        pref = bpy.context.preferences.addons["cycles"].preferences
        pref.compute_device_type = args.device
        pref.get_devices()
        for d in pref.devices:
            d.use = d.type == args.device
        if not any(d.use for d in pref.devices):
            raise RuntimeError("No " + args.device + " device visible")
        cy.device = "GPU"
    cy.samples = args.samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.006
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 10, 5, 4
    cy.transmission_bounces, cy.transparent_max_bounces = 8, 16
    cy.sample_clamp_indirect = 8.0
    cy.blur_glossy = 0.6
    cy.seed = 20261110
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.30
    scene.render.use_persistent_data = False     # required with motion blur (static objects otherwise drop out)
    scene.render.resolution_x = args.width
    scene.render.resolution_y = round(args.width * 9 / 16)
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, 96
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = args.exposure
    scene.render.film_transparent = False


def frames_arg(text):
    if "-" in text:
        a, b = map(int, text.split("-"))
        return list(range(a, b + 1))
    return [int(x) for x in text.split(",")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--native", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frames", default="1-96")
    ap.add_argument("--samples", type=int, default=256)
    ap.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--exposure", type=float, default=2.3, help="EV; interior exposure of the look")
    ap.add_argument("--save-blend", action="store_true")
    ap.add_argument("--view", help="development override x,y,z/tx,ty,tz/lens (the look itself uses appearance/view.py)")
    ap.add_argument("--probe", action="store_true", help="print the bounds of the built objects and stop")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    cfg = json.loads((a.native / "simulation_config.json").read_text())
    if cfg["case_id"] != a.case or cfg["layout"] != LAYOUT or cfg["physics"] != resolve(a.case)[0]:
        raise RuntimeError("Native output does not belong to this case and layout")
    c = np.load(a.native / "cache.npz")
    positions, faces, uv, times = c["positions"], c["faces"], c["uv"], c["times"]
    names = list(c["rigid_names"])
    out = a.out
    (out / "frames").mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    scene = bpy.context.scene
    settings(scene, a)
    record = dict(look=LOOK, case=a.case, room=room(), curtains=curtains(), light=daylight(scene))
    record["furniture"] = furniture()
    roots = {}
    if cfg["physics"]["chair_active"][0]:
        chair = rr.asset("prepared")
        for o in chair.children:
            o.location.z += LAYOUT["chair_ground_clearance"]
        roots["chair"] = chair
        record["chair"] = chair_look(chair)
    if cfg["physics"]["book_active"][0]:
        r = bpy.data.objects.new("Hardcover book transform", None)
        bpy.context.collection.objects.link(r)
        roots["landing_book"] = r
        record["book"] = book(r, cfg["physics"])
    mdd = out / "cloth.mdd"
    write_mdd(mdd, positions, times)
    scarf_look(cfg, positions[0], faces, uv, mdd)
    for name, root in roots.items():
        root.rotation_mode = "QUATERNION"
        for i in range(len(times)):
            T = Matrix(c["rigid_transforms"][i, names.index(name)].tolist())
            loc, rot, scale = T.decompose()
            root.location, root.rotation_quaternion, root.scale = loc, rot, scale
            for prop in ("location", "rotation_quaternion", "scale"):
                root.keyframe_insert(prop, frame=i + 1)
        if root.animation_data and root.animation_data.action:
            for fc in getattr(root.animation_data.action, "fcurves", []):
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
    view = None
    if a.view:
        p, t, lens = a.view.split("/")
        view = dict(CAMERA, location_m=tuple(map(float, p.split(","))), target_m=tuple(map(float, t.split(","))),
                    lens_mm=float(lens), note="development override")
    cam = camera(scene, view)
    if a.probe:
        bpy.context.view_layer.update()
        for ob in sorted(bpy.data.objects, key=lambda o: o.name):
            if ob.type == "MESH" and not ob.parent:
                lo, hi = kit.world_bbox([ob])
                print("PROBE", ob.name[:50], [round(v, 3) for v in lo], [round(v, 3) for v in hi])
        for ob in bpy.data.objects:
            if ob.type == "EMPTY":
                kids = [k for k in ob.children_recursive if k.type == "MESH"]
                if kids:
                    lo, hi = kit.world_bbox(kids)
                    print("PROBE_GROUP", ob.name[:50], [round(v, 3) for v in lo], [round(v, 3) for v in hi])
        graph = bpy.context.evaluated_depsgraph_get()
        for x in (0.95, 1.10, 1.25, 1.45, 1.65):
            hits, z = [], 1.7
            while z > 0.02:
                hit, point, _, _, obj, _ = scene.ray_cast(graph, Vector((x, WALL["back"] - 0.2, z)), Vector((0, 0, -1)))
                if not hit:
                    break
                hits.append((round(point.z, 3), obj.name[:20]))
                z = point.z - 0.02
            print("PROBE_SHELF", x, hits)
        return
    record.update(camera=dict(view or CAMERA, matrix_world=[list(r) for r in cam.matrix_world]),
                  samples=a.samples, device=a.device, resolution=[scene.render.resolution_x, scene.render.resolution_y],
                  motion_blur_shutter=scene.render.motion_blur_shutter, exposure=a.exposure,
                  native=dict(cache=str(a.native / "cache.npz"), cache_sha256=sha(a.native / "cache.npz")),
                  blender=bpy.app.version_string, worker=kit.host_record())
    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"))
    kit.write_json(out / "realism_provenance.json", record)
    start = time.monotonic()
    for frame in frames_arg(a.frames):
        scene.frame_set(frame)
        scene.render.filepath = str(out / "frames" / f"{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("RENDERED", frame, "wall", round(time.monotonic() - start, 1), flush=True)


if __name__ == "__main__":
    main()
