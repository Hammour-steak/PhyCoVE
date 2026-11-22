"""Current look of cabinet_towel_pinch, applied to a saved native scene.

Run inside Blender 4.3.2 on a case's saved scene (assets scenes/cabinet_towel_pinch/native/<case>/scene.blend,
written by appearance/render_replay.py --save-blend):

    blender -b --factory-startup --disable-autoexec <scene.blend> --python-exit-code 1 \
        --python appearance/realism.py -- --case CASE --out OUT [--frames 1-96] [--samples 256] [--device OPTIX]

The towel's 96 native shape keys, the native door/doorstop transforms, the camera and the frame timing are
those of the saved scene and are not touched. Only static room geometry, lights and materials change:
a closed kitchen lit by soft daylight through a window in the left wall (out of frame) and a ceiling
fitting, scanned Poly Haven surfaces at their real-world size (oak veneer fronts, polished concrete-look
floor tiles, dark stone worktop, gingham cotton tea towel) and glazed white wall tiles.
"""
from pathlib import Path
import argparse
import json
import math
import sys

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE), str(ROOT / "scripts")]
import pcve_realism_kit as kit
from pcve_assets import asset

PH = asset("polyhaven")
# Real-world edge length (m) of each scanned texture tile (Poly Haven "dimensions").
SIZE = {"silver_oak_veneer_01": 1.0, "granular_concrete": 2.4, "hangar_concrete_floor": 2.0,
        "gingham_check": (0.28365, 0.2968)}
TOWEL = (0.28, 0.60)                       # towel width x length (m); its UVs span [0, 1] on both
ROOM = dict(x0=-2.20, x1=2.20, y0=-2.15, y1=0.62, top=2.50)
WINDOW = (-1.90, -0.25, 0.85, 2.20)        # left wall opening: y0, y1, z0, z1 (out of frame)
STUDIO_LIGHTS = ("Large kitchen window", "Soft room bounce", "Countertop reflection")


# ---------------------------------------------------------------- material helpers
def _nodes(mat):
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return tree.nodes, tree.links, bsdf


def _image(nodes, links, set_id, kind, vector, colour=False, box=False):
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(PH / set_id / f"{set_id}_{kind}_2k.jpg"), check_existing=True)
    tex.image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    if box:
        tex.projection = "BOX"
        tex.projection_blend = 0.12
    links.new(vector, tex.inputs["Vector"])
    return tex.outputs["Color"]


def _math(nodes, links, op, a, b=None):
    node = nodes.new("ShaderNodeMath")
    node.operation = op
    for i, value in enumerate((a, b)):
        if value is None:
            continue
        if hasattr(value, "node"):
            links.new(value, node.inputs[i])
        else:
            node.inputs[i].default_value = value
    return node.outputs[0]


def _remap(nodes, links, value, low, high):
    node = nodes.new("ShaderNodeMapRange")
    node.inputs["To Min"].default_value = low
    node.inputs["To Max"].default_value = high
    links.new(value, node.inputs["Value"])
    return node.outputs[0]


def _object_vector(nodes, links, size, rotate_y=0.0, jitter=3.0):
    """Object-space metres -> texture space of one scanned tile, offset per object (no shared seams)."""
    coord = nodes.new("ShaderNodeTexCoord")
    info = nodes.new("ShaderNodeObjectInfo")
    offset = nodes.new("ShaderNodeVectorMath")
    offset.operation = "MULTIPLY"
    offset.inputs[1].default_value = (jitter, jitter * 0.61, jitter * 0.37)
    links.new(info.outputs["Random"], offset.inputs[0])
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0.0, rotate_y, 0.0)
    mapping.inputs["Scale"].default_value = (1 / size, 1 / size, 1 / size)
    links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    shifted = nodes.new("ShaderNodeVectorMath")
    shifted.operation = "ADD"
    links.new(mapping.outputs["Vector"], shifted.inputs[0])
    links.new(offset.outputs[0], shifted.inputs[1])
    return shifted.outputs[0], info.outputs["Random"]


def _normal(nodes, links, colour, strength):
    node = nodes.new("ShaderNodeNormalMap")
    node.inputs["Strength"].default_value = strength
    links.new(colour, node.inputs["Color"])
    return node.outputs[0]


def oak_veneer(mat, value=(0.86, 0.98), saturation=0.92):
    """Flat-sliced oak veneer, grain vertical on the fronts, under a satin lacquer; each panel its own leaf."""
    nodes, links, bsdf = _nodes(mat)
    vector, rnd = _object_vector(nodes, links, SIZE["silver_oak_veneer_01"], rotate_y=math.pi / 2)
    colour = _image(nodes, links, "silver_oak_veneer_01", "diff", vector, colour=True, box=True)
    tone = nodes.new("ShaderNodeHueSaturation")
    tone.inputs["Saturation"].default_value = saturation
    links.new(colour, tone.inputs["Color"])
    links.new(_remap(nodes, links, rnd, *value), tone.inputs["Value"])  # leaf-to-leaf tone change
    links.new(tone.outputs["Color"], bsdf.inputs["Base Color"])
    rough = _image(nodes, links, "silver_oak_veneer_01", "rough", vector, box=True)
    links.new(_remap(nodes, links, rough, 0.34, 0.55), bsdf.inputs["Roughness"])
    links.new(_normal(nodes, links, _image(nodes, links, "silver_oak_veneer_01", "nor_gl", vector, box=True), 0.6),
              bsdf.inputs["Normal"])
    bsdf.inputs["Coat Weight"].default_value = 0.22
    bsdf.inputs["Coat Roughness"].default_value = 0.32


def floor_porcelain(mat):
    """60 cm rectified porcelain tiles with a concrete-look face, lightly polished (soft reflections)."""
    nodes, links, bsdf = _nodes(mat)
    vector, rnd = _object_vector(nodes, links, SIZE["granular_concrete"], jitter=5.0)
    colour = _image(nodes, links, "granular_concrete", "diff", vector, colour=True)
    tone = nodes.new("ShaderNodeHueSaturation")
    tone.inputs["Saturation"].default_value = 0.45
    links.new(colour, tone.inputs["Color"])
    links.new(_remap(nodes, links, rnd, 1.48, 1.62), tone.inputs["Value"])
    links.new(tone.outputs["Color"], bsdf.inputs["Base Color"])
    rough = _image(nodes, links, "granular_concrete", "rough", vector)
    links.new(_remap(nodes, links, rough, 0.05, 0.16), bsdf.inputs["Roughness"])
    links.new(_normal(nodes, links, _image(nodes, links, "granular_concrete", "nor_gl", vector), 0.25), bsdf.inputs["Normal"])


def dark_worktop(mat):
    """Honed dark engineered-stone worktop."""
    nodes, links, bsdf = _nodes(mat)
    vector, _ = _object_vector(nodes, links, SIZE["hangar_concrete_floor"], jitter=0.0)
    colour = _image(nodes, links, "hangar_concrete_floor", "diff", vector, colour=True, box=True)
    tone = nodes.new("ShaderNodeHueSaturation")
    tone.inputs["Value"].default_value = 0.85
    links.new(colour, tone.inputs["Color"])
    links.new(tone.outputs["Color"], bsdf.inputs["Base Color"])
    rough = _image(nodes, links, "hangar_concrete_floor", "rough", vector, box=True)
    links.new(_remap(nodes, links, rough, 0.22, 0.40), bsdf.inputs["Roughness"])
    links.new(_normal(nodes, links, _image(nodes, links, "hangar_concrete_floor", "nor_gl", vector, box=True), 0.2),
              bsdf.inputs["Normal"])


def glazed_tile(mat):
    """Hand-glazed white wall tile: per-tile tint, slightly wavy glossy glaze."""
    nodes, links, bsdf = _nodes(mat)
    info = nodes.new("ShaderNodeObjectInfo")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.80, 0.79, 0.75, 1)
    ramp.color_ramp.elements[1].color = (0.87, 0.86, 0.82, 1)
    links.new(info.outputs["Random"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.10
    coord = nodes.new("ShaderNodeTexCoord")
    wave = nodes.new("ShaderNodeTexNoise")
    wave.inputs["Scale"].default_value = 18.0
    wave.inputs["Detail"].default_value = 2.0
    links.new(coord.outputs["Object"], wave.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.0008
    links.new(wave.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def plain(mat, colour, rough):
    nodes, links, bsdf = _nodes(mat)
    bsdf.inputs["Base Color"].default_value = (*colour, 1)
    bsdf.inputs["Roughness"].default_value = rough


def gingham_towel(mat):
    """Green-and-white cotton gingham tea towel: weave normal at real scale, folded and stitched hem."""
    nodes, links, bsdf = _nodes(mat)
    coord = nodes.new("ShaderNodeTexCoord")
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = (TOWEL[0] / SIZE["gingham_check"][0], TOWEL[1] / SIZE["gingham_check"][1], 1)
    links.new(coord.outputs["UV"], scale.inputs[0])
    vector = scale.outputs[0]
    colour = _image(nodes, links, "gingham_check", "diff", vector, colour=True)
    cotton = nodes.new("ShaderNodeMixRGB")          # unbleached cotton white, not paper white
    cotton.blend_type = "MULTIPLY"
    cotton.inputs[0].default_value = 1.0
    cotton.inputs[2].default_value = (0.95, 0.92, 0.85, 1)
    links.new(colour, cotton.inputs[1])
    # Folded hem: 9 mm along the long sides, 12 mm across the ends; two layers read slightly darker.
    xy = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord.outputs["UV"], xy.inputs[0])
    u, v = xy.outputs["X"], xy.outputs["Y"]
    side = _math(nodes, links, "MAXIMUM", _math(nodes, links, "LESS_THAN", u, 0.009 / TOWEL[0]),
                 _math(nodes, links, "GREATER_THAN", u, 1 - 0.009 / TOWEL[0]))
    end = _math(nodes, links, "MAXIMUM", _math(nodes, links, "LESS_THAN", v, 0.012 / TOWEL[1]),
                _math(nodes, links, "GREATER_THAN", v, 1 - 0.012 / TOWEL[1]))
    hem = _math(nodes, links, "MAXIMUM", side, end)
    shade = nodes.new("ShaderNodeMixRGB")
    shade.blend_type = "MULTIPLY"
    links.new(_math(nodes, links, "MULTIPLY", hem, 0.12), shade.inputs[0])
    links.new(cotton.outputs[0], shade.inputs[1])
    shade.inputs[2].default_value = (0.7, 0.7, 0.7, 1)
    links.new(shade.outputs[0], bsdf.inputs["Base Color"])
    rough = _image(nodes, links, "gingham_check", "rough", vector)
    links.new(_remap(nodes, links, rough, 0.78, 0.95), bsdf.inputs["Roughness"])
    bsdf.inputs["Sheen Weight"].default_value = 0.35
    bsdf.inputs["Sheen Roughness"].default_value = 0.6
    weave = _normal(nodes, links, _image(nodes, links, "gingham_check", "nor_gl", vector), 1.0)
    # Hem relief: a raised fold edge and a stitch line 6 mm in from the towel edge.
    stitch = _math(nodes, links, "MAXIMUM",
                   _math(nodes, links, "MULTIPLY", _math(nodes, links, "GREATER_THAN", u, 0.0055 / TOWEL[0]),
                         _math(nodes, links, "LESS_THAN", u, 0.0068 / TOWEL[0])),
                   _math(nodes, links, "MULTIPLY", _math(nodes, links, "GREATER_THAN", u, 1 - 0.0068 / TOWEL[0]),
                         _math(nodes, links, "LESS_THAN", u, 1 - 0.0055 / TOWEL[0])))
    height = _math(nodes, links, "SUBTRACT", _math(nodes, links, "MULTIPLY", hem, 0.6), stitch)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.0004
    links.new(height, bump.inputs["Height"])
    links.new(weave, bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def brushed_steel(mat):
    nodes, links, bsdf = _nodes(mat)
    bsdf.inputs["Base Color"].default_value = (0.62, 0.62, 0.60, 1)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.30
    bsdf.inputs["Anisotropic"].default_value = 0.5


# ---------------------------------------------------------------- room and light
def box(name, centre, size, mat):
    obj = kit.plain_box(name, centre, size, mat)
    return obj


def room_shell():
    """Closed kitchen: plastered walls and ceiling, a large window in the left wall."""
    wall = bpy.data.materials.new("Painted plaster wall")
    plain(wall, (0.78, 0.76, 0.71), 0.85)
    ceiling = bpy.data.materials.new("Painted ceiling")
    plain(ceiling, (0.82, 0.81, 0.78), 0.9)
    frame = bpy.data.materials.new("White window frame")
    plain(frame, (0.82, 0.82, 0.80), 0.4)
    x0, x1, y0, y1, top = ROOM["x0"], ROOM["x1"], ROOM["y0"], ROOM["y1"], ROOM["top"]
    wy0, wy1, wz0, wz1 = WINDOW
    for label, (ya, yb, za, zb) in (("near", (y0, wy0, 0.0, top)), ("far", (wy1, y1, 0.0, top)),
                                    ("below", (wy0, wy1, 0.0, wz0)), ("above", (wy0, wy1, wz1, top))):
        box(f"Left wall {label} window", (x0 - 0.05, (ya + yb) / 2, (za + zb) / 2), (0.10, yb - ya, zb - za), wall)
    box("Window centre mullion", (x0 - 0.05, (wy0 + wy1) / 2, (wz0 + wz1) / 2), (0.10, 0.05, wz1 - wz0), frame)
    box("Window sill", (x0 + 0.02, (wy0 + wy1) / 2, wz0 - 0.015), (0.16, wy1 - wy0 + 0.06, 0.03), frame)
    box("Right wall", (x1 + 0.05, (y0 + y1) / 2, top / 2), (0.10, y1 - y0, top), wall)
    box("Front wall", (0.0, y0 - 0.05, top / 2), (x1 - x0 + 0.2, 0.10, top), wall)
    box("Back wall", (0.0, y1 + 0.05, top / 2), (x1 - x0 + 0.2, 0.10, top), wall)
    box("Ceiling", (0.0, (y0 + y1) / 2, top + 0.05), (x1 - x0 + 0.2, y1 - y0, 0.10), ceiling)
    # Grout bed under the 60 cm floor tiles (their 2 mm joints were open to the void).
    grout = bpy.data.materials.new("Floor tile grout")
    plain(grout, (0.30, 0.29, 0.27), 0.95)
    box("Floor tile grout bed", (0.0, (y0 + y1) / 2, -0.0085), (x1 - x0, y1 - y0, 0.013), grout)


def lights(scene, args):
    for name in STUDIO_LIGHTS:
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name])
    tree = scene.world.node_tree
    env = tree.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(asset("polyhaven/residential_garden/residential_garden_4k.hdr")))
    mapping, coord = tree.nodes.new("ShaderNodeMapping"), tree.nodes.new("ShaderNodeTexCoord")
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(200.0))
    tree.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    background = tree.nodes["Background"]
    tree.links.new(env.outputs["Color"], background.inputs["Color"])
    background.inputs["Strength"].default_value = args.sky
    # Light portal in the window opening: the sky is the light source, sampled through the opening.
    wy0, wy1, wz0, wz1 = WINDOW
    portal = bpy.data.lights.new("Window sky portal", "AREA")
    portal.shape, portal.size, portal.size_y = "RECTANGLE", wz1 - wz0, wy1 - wy0   # local x -> height
    portal.cycles.is_portal = True
    obj = bpy.data.objects.new("Window sky portal", portal)
    bpy.context.collection.objects.link(obj)
    obj.location = (ROOM["x0"] - 0.10, (wy0 + wy1) / 2, (wz0 + wz1) / 2)
    obj.rotation_euler = (0.0, math.radians(-90.0), 0.0)      # local -z -> +x: faces into the room
    # Flush ceiling fitting with a real body: an opal disc with a warm LED behind it.
    lamp = bpy.data.lights.new("Ceiling fitting LED", "AREA")
    lamp.shape, lamp.size, lamp.energy, lamp.color = "DISK", 0.34, args.lamp, (1.0, 0.87, 0.74)
    obj = bpy.data.objects.new("Ceiling fitting LED", lamp)
    bpy.context.collection.objects.link(obj)
    obj.location = (0.40, -0.85, ROOM["top"] - 0.045)
    diffuser = bpy.data.materials.new("Opal diffuser")
    plain(diffuser, (0.92, 0.92, 0.90), 0.3)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.19, depth=0.04,
                                        location=(0.40, -0.85, ROOM["top"] - 0.02))
    bpy.context.object.name = "Ceiling fitting body"
    bpy.context.object.data.materials.append(diffuser)


def finish_cabinet_run():
    """Fitter's details the earlier kitchen lacked; all static and well clear of the towel and door sweep."""
    oak = bpy.data.materials["Pale oak · open pores and photographic growth rings"]
    # 16 cm oak filler between the last door (x = 1.41 m) and the right end panel, as fitted kitchens have.
    box("Oak filler panel", ((1.411 + 1.570) / 2, -0.010, 0.445), (0.159, 0.018, 0.650), oak)
    # The earlier door carried a surface hinge leaf and pin on its front; this door hangs on concealed cup
    # hinges (their cups are on the inside face), so the front shows no hardware.
    for obj in bpy.data.objects:
        if obj.name.split(".")[0] in ("Hinge leaf", "Hinge pin"):
            obj.hide_render = True
    # Push-to-open fronts along the run: the bar pulls of the other doors are not shown. They are static
    # parts of the fixed collider that no case ever touches (the towel stays within x = 0.03..0.59 m).
    # The towel door keeps its vertical pull: it is part of that door's simulated body and the towel
    # rests against it at the start of every case.
    for obj in bpy.data.objects:
        if obj.name.split(".")[0] in ("Neighbor handle", "Neighbor handle foot", "Far left handle", "Far left handle foot"):
            obj.hide_render = True
    # The bay's bottom rail shows in the gap under the closed door: face-frame oak like its neighbours.
    rail = bpy.data.objects["bottom_rail"]
    rail.material_slots[0].material = oak


def append_blend(path, location, rot_z=0.0):
    """Append every mesh of a Poly Haven .blend at true scale, bounding-box bottom centre on `location`."""
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = list(src.objects)
    root = bpy.data.objects.new("Dressing " + path.stem, None)
    bpy.context.collection.objects.link(root)
    members = []
    for obj in dst.objects:
        if obj is None or obj.type not in ("MESH", "EMPTY"):
            continue
        bpy.context.collection.objects.link(obj)
        if obj.parent is None:
            obj.parent = root
        members.append(obj)
    root.rotation_euler = (0.0, 0.0, rot_z)
    bpy.context.view_layer.update()
    low, high = kit.world_bbox(members)
    root.location = Vector(location) - Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    bpy.context.view_layer.update()
    return members


def furnish_bay():
    """The towel bay's carcass: melamine gables and an adjustable shelf with an enamel pot on it.

    All of it sits behind the face frame (y >= 0.02 m); across every case the towel never passes
    y = 0.004 m and the door closes in front of y = 0, so nothing here meets a simulated body.
    """
    melamine = bpy.data.materials["Warm white cabinet interior"]
    for label, x in (("left", -0.019), ("right", 0.429)):
        box(f"Bay {label} gable", (x, 0.255, 0.4375), (0.018, 0.47, 0.625), melamine)
    box("Bay adjustable shelf", (0.205, 0.2625, 0.439), (0.43, 0.445, 0.018), melamine)
    members = append_blend(asset("polyhaven/pot_enamel_01/pot_enamel_01_2k.blend"), (0.25, 0.30, 0.448), rot_z=0.15)
    low, high = kit.world_bbox(members)
    assert low.y > 0.02 and high.z < 0.75 and low.x > -0.01 and high.x < 0.42, (tuple(low), tuple(high))
    return {"label": "pot_enamel_01", "bbox_low_m": list(low), "bbox_high_m": list(high)}


def restyle_materials():
    M = bpy.data.materials
    oak_veneer(M["Pale oak · open pores and photographic growth rings"])
    floor_porcelain(M["Warm porcelain with mineral speckling"])
    dark_worktop(M["Honed warm limestone · mineral inclusions and micro pits"])
    glazed_tile(M["Satin ivory glaze with orange peel"])
    plain(M["Grout"], (0.62, 0.61, 0.58), 0.9)
    plain(M["Warm white cabinet interior"], (0.80, 0.79, 0.76), 0.38)
    plain(M["Toe kick shadow"], (0.055, 0.052, 0.048), 0.55)
    brushed_steel(M["Brushed steel · directional machining and fingerprint roughnes"])
    gingham_towel(M["Unbleached cotton · woven navy bands, sewn hem and fibre nap"])
    for mat in list(M):
        if mat.name.startswith("Stoneware glaze"):      # the two stacks of 12 mm discs: oiled wooden coasters
            oak_veneer(mat, value=(0.42, 0.52), saturation=1.15)


def render_settings(scene, args):
    scene.render.engine = "CYCLES"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = args.exposure
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.sample_clamp_indirect = 10.0
    scene.cycles.caustics_reflective = scene.cycles.caustics_refractive = False
    # Motion blur needs persistent data off in Blender 4.3 (bodies that come to rest vanish otherwise).
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.25
    scene.render.use_persistent_data = False
    kit.lens_finish(scene, vignette=0.10, dispersion=0.002)
    prefs = bpy.context.preferences.addons["cycles"].preferences
    if args.device == "CPU":
        scene.cycles.device = "CPU"
    else:
        prefs.compute_device_type = args.device
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == args.device
        if not any(d.use for d in prefs.devices):
            raise RuntimeError("No " + args.device + " device")
        scene.cycles.device = "GPU"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--case", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", default="1-96", help="'a-b' or a comma list")
    p.add_argument("--samples", type=int, default=256)
    p.add_argument("--exposure", type=float, default=0.5)
    p.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX")
    p.add_argument("--sky", type=float, default=12.0, help="strength of the daylight HDRI seen through the window")
    p.add_argument("--lamp", type=float, default=10.0, help="ceiling fitting power (W)")
    args = p.parse_args(argv)
    frames = (list(range(int(args.frames.split("-")[0]), int(args.frames.split("-")[1]) + 1))
              if "-" in args.frames else [int(f) for f in args.frames.split(",")])
    scene = bpy.context.scene
    saved = Path(bpy.data.filepath)
    camera_before = [list(row) for row in scene.camera.matrix_world]
    room_shell()
    lights(scene, args)
    finish_cabinet_run()
    dressing = [furnish_bay()]
    restyle_materials()
    render_settings(scene, args)
    assert [list(row) for row in scene.camera.matrix_world] == camera_before, "camera must stay unchanged"
    args.out.mkdir(parents=True, exist_ok=True)
    kit.write_json(args.out / "realism_provenance.json", {
        "look": "appearance/realism.py", "case": args.case, "worker": kit.host_record(),
        "blender": bpy.app.version_string, "saved_scene": saved.name, "saved_scene_sha256": kit.sha256(saved),
        "samples": args.samples, "exposure": args.exposure, "sky_strength": args.sky, "ceiling_lamp_w": args.lamp, "device": args.device,
        "motion_blur_shutter": scene.render.motion_blur_shutter, "frames": [frames[0], frames[-1]],
        "textures": sorted(SIZE) + ["residential_garden (HDRI)"], "dressing": dressing})
    for f in frames:
        scene.frame_set(f)
        scene.render.filepath = str(args.out / "frames" / f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("LOOK_FRAME", f, flush=True)


main()
