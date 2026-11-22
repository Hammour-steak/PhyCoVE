"""Current look of silicone_bag_can, rendered over the packed counter kitchen.

Run inside Blender 4.3.2 on the packed kitchen (assets scenes/silicone_bag_can/source_scene.blend):

    blender -b <source_scene.blend> --disable-autoexec --python-exit-code 1 --python appearance/realism.py -- \
        --case CASE --source <native case dir> --out OUT [--frames 1-96] [--samples 256] [--device OPTIX]

The native states are bound exactly as the accepted renderer does it (optics_native.bind_native_cache: the 96
bag states as shape keys, the can transforms as linear keys, frame i = native state i-1), followed by the
accepted per-vertex wall-thickness skin (render_counter.apply_physical_skin); the dynamic signature of the bag
and cans is checked before and after the restyle, the camera is asserted unchanged, and the camera-coverage and
native-replay audits of the accepted renderer run on the restyled scene. Only static geometry, lights and
materials change: the open-sided set becomes a closed kitchen lit by daylight through a window in the back wall
and one in the left wall (both out of frame) and by a ceiling fitting with a real body; the cabinet fronts get a
satin sage paint over oak, the backsplash glossy hand-glazed tiles, the can loses its printed label (plain
tinplate), and the bag loses its moulded lettering.
"""
from pathlib import Path
import argparse
import math
import random
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE), str(ROOT / "scripts")]
import optics_native as utils
import render_counter as accepted
import pcve_realism_kit as kit
from pcve_assets import asset

HDRI = "polyhaven/pretoria_gardens/pretoria_gardens_2k.hdr"
# Oak veneer scan already packed in the kitchen (Poly Haven oak_veneer_01, 4k): its grain shows through the paint.
OAK = ("oak_veneer_01_diff_4k.jpg", "oak_veneer_01_nor_gl_4k.jpg")
# Bag, falling/added cans, hooks and the floor spot where the can lands in delete_bag (all cases).
KEEPOUT = ((-.25, -.35, .03), (.25, .08, 1.40))
# Closed room: inner faces of the left (x0) and right (x1) walls, front wall (y0), back wall (y1), ceiling, wall top.
ROOM = dict(x0=-1.78, x1=1.75, y0=-2.00, y1=0.67, ceiling=2.68, top=2.80)
SIDE_WINDOW = (-1.25, -.15, .85, 2.20)            # left wall opening: y0, y1, z0, z1 (out of frame)
BACK_WINDOW = (-1.295, -.555, 1.225, 2.115)       # existing back-wall opening: x0, x1, z0, z1 (out of frame)
STUDIO_LIGHTS = ("large left daylight", "kitchen warm ceiling", "soft frontal fill")


# ---------------------------------------------------------------- material helpers
def _nodes(mat):
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return tree.nodes, tree.links, bsdf


def _remap(nodes, links, value, low, high):
    node = nodes.new("ShaderNodeMapRange")
    node.inputs["To Min"].default_value = low
    node.inputs["To Max"].default_value = high
    links.new(value, node.inputs["Value"])
    return node.outputs[0]


def _noise(nodes, links, scale, detail=2.0, space="Object"):
    coord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    links.new(coord.outputs[space], noise.inputs["Vector"])
    return noise.outputs["Fac"]


def _image(nodes, links, name, colour):
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images[name]
    tex.image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    coord = nodes.new("ShaderNodeTexCoord")
    links.new(coord.outputs["UV"], tex.inputs["Vector"])
    return tex.outputs["Color"]


def plain(mat, colour, rough):
    nodes, links, bsdf = _nodes(mat)
    bsdf.inputs["Base Color"].default_value = (*colour, 1)
    bsdf.inputs["Roughness"].default_value = rough
    return nodes, links, bsdf


def sage_paint(mat):
    """Satin sage-green paint on oak fronts: the grain telegraphs faintly through, fine roller stipple."""
    nodes, links, bsdf = _nodes(mat)
    grain = _image(nodes, links, OAK[0], True)
    grey = nodes.new("ShaderNodeRGBToBW")
    links.new(grain, grey.inputs["Color"])
    tone = nodes.new("ShaderNodeVectorMath")
    tone.operation = "SCALE"
    tone.inputs[0].default_value = (0.205, 0.262, 0.214)
    links.new(_remap(nodes, links, grey.outputs[0], 0.96, 1.04), tone.inputs["Scale"])
    links.new(tone.outputs[0], bsdf.inputs["Base Color"])
    links.new(_remap(nodes, links, _noise(nodes, links, 7.0, 4.0), 0.36, 0.46), bsdf.inputs["Roughness"])
    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.10
    links.new(_image(nodes, links, OAK[1], False), normal.inputs["Color"])
    stipple = nodes.new("ShaderNodeBump")
    stipple.inputs["Strength"].default_value = 0.05
    stipple.inputs["Distance"].default_value = 0.00005
    links.new(_noise(nodes, links, 900.0, 3.0), stipple.inputs["Height"])
    links.new(normal.outputs[0], stipple.inputs["Normal"])
    links.new(stipple.outputs[0], bsdf.inputs["Normal"])


def glazed_tile(mat):
    """Hand-glazed off-white wall tile: per-tile tint, glossy slightly wavy glaze."""
    nodes, links, bsdf = _nodes(mat)
    info = nodes.new("ShaderNodeObjectInfo")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.74, 0.73, 0.69, 1)
    ramp.color_ramp.elements[1].color = (0.82, 0.81, 0.77, 1)
    links.new(info.outputs["Random"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(_remap(nodes, links, _noise(nodes, links, 30.0, 3.0), 0.06, 0.12), bsdf.inputs["Roughness"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.0008
    links.new(_noise(nodes, links, 16.0, 2.0), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def brushed_steel(mat, colour=(0.63, 0.63, 0.62), rough=0.24, aniso=0.45):
    nodes, links, bsdf = plain(mat, colour, rough)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Anisotropic"].default_value = aniso
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.03
    bump.inputs["Distance"].default_value = 0.00002
    links.new(_noise(nodes, links, 2500.0, 2.0), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def restyle_materials(args):
    M = bpy.data.materials
    sage_paint(M["photo6 oak_veneer_01 measured scan"])
    for mat in list(M):
        if mat.name.startswith("photo6 ivory ceramic tile"):
            glazed_tile(mat)
    plain(M["photo6 warm limestone grout"], (0.40, 0.385, 0.35), 0.95)
    wall = M["photo6 warm limewashed wall"]
    plain(wall, (0.60, 0.58, 0.53), 0.88)
    kit.add_wall_mottling(wall, 0.05)
    plain(M["photo6 painted window timber"], (0.76, 0.75, 0.71), 0.45)
    brushed_steel(M["brushed 304 stainless"])
    # Plain tinplate can (the printed label objects are hidden): bright, finely brushed along the wall.
    brushed_steel(M["fine directional tinplate steel"], colour=(0.70, 0.70, 0.68), rough=0.20, aniso=0.35)
    floor = M["photo6 laminate_floor_03 measured scan"]
    rough = next(n for n in floor.node_tree.nodes if n.type == "MAP_RANGE")
    rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = 0.20, 0.40
    # The bag's moulded front lettering: the relief mask is (y < -0.183 m) x image; no rest vertex is that far out.
    node = M["molded matte silicone outer"].node_tree.nodes["Math.021"]
    assert node.operation == "LESS_THAN"
    node.inputs[1].default_value = -10.0
    # Clearer, satin food-grade silicone: the accepted thin-sheet optics (transparency exp(-k h / |cos|) with the
    # replayed local wall thickness h) with k = 200 /m instead of 300 /m, a neutral milky tint and a satin sheen.
    for name in ("molded matte silicone outer", "dry food contact inner wall", "rounded molded edge"):
        nodes = M[name].node_tree.nodes
        depth = nodes["physical optical depth"]
        assert depth.operation == "MULTIPLY" and abs(depth.inputs[1].default_value + 300.0) < 1e-6
        depth.inputs[1].default_value = -args.bag_k
        for node in nodes:
            if node.type in ("BSDF_DIFFUSE", "BSDF_TRANSLUCENT"):
                node.inputs["Color"].default_value = (0.84, 0.86, 0.85, 1)
            elif node.type == "MAP_RANGE":
                node.inputs["To Min"].default_value, node.inputs["To Max"].default_value = 0.26, 0.34


def hide_label():
    hidden = []
    for obj in bpy.data.objects:
        if obj.name.startswith(("printed label paper", "printed label rule")):
            obj.hide_render = True
            hidden.append(obj.name)
    return hidden


# ---------------------------------------------------------------- room and light
def box(name, centre, size, mat):
    return kit.plain_box(name, centre, size, mat)


def tilt_tiles(seed=14):
    """Hand-set tiles are never perfectly coplanar: tilt each one by up to 0.2 degrees about its own centre."""
    rng = random.Random(seed)
    count = 0
    for obj in sorted(bpy.data.objects, key=lambda o: o.name):
        if not obj.name.startswith("photo6 ceramic subway tile"):
            continue
        centre = sum((obj.matrix_world @ Vector(c) for c in obj.bound_box), Vector()) / 8
        rot = (Matrix.Rotation(math.radians(rng.uniform(-.2, .2)), 4, "X")
               @ Matrix.Rotation(math.radians(rng.uniform(-.2, .2)), 4, "Z"))
        obj.matrix_world = Matrix.Translation(centre) @ rot @ Matrix.Translation(-centre) @ obj.matrix_world
        count += 1
    return count


def room_shell():
    """Close the open-sided set into a kitchen: left wall with a window, right and front walls, a ceiling slab.

    The walls overlap the existing back wall and ceiling so no daylight leaks in except through the two windows.
    """
    wall = bpy.data.materials["photo6 warm limewashed wall"]
    frame = bpy.data.materials["photo6 painted window timber"]
    glass = bpy.data.materials["photo6 window clean glass"]
    made = []
    left = bpy.data.objects["photo6 room left wall"]
    lo = [min((left.matrix_world @ Vector(c))[i] for c in left.bound_box) for i in range(3)]
    hi = [max((left.matrix_world @ Vector(c))[i] for c in left.bound_box) for i in range(3)]
    left.hide_render = True
    ya, yb, za, zb = ROOM["y0"] - .10, ROOM["y1"] + .08, 0.0, ROOM["top"]
    y0, y1, z0, z1 = SIDE_WINDOW
    x, t = (lo[0] + hi[0]) / 2, hi[0] - lo[0]
    for (a, b), (c, d) in (((ya, yb), (za, z0)), ((ya, yb), (z1, zb)), ((ya, y0), (z0, z1)), ((y1, yb), (z0, z1))):
        made.append(box("Left wall around window", (x, (a + b) / 2, (c + d) / 2), (t, b - a, d - c), wall))
    made.append(box("Left window sill", (x + t / 2 + .02, (y0 + y1) / 2, z0 - .012), (.12, y1 - y0 + .06, .024), frame))
    made.append(box("Left window mullion", (x, (y0 + y1) / 2, (z0 + z1) / 2), (t * .6, .045, z1 - z0), frame))
    made.append(box("Left window transom", (x, (y0 + y1) / 2, z0 + .62 * (z1 - z0)), (t * .6, y1 - y0, .045), frame))
    pane = box("Left window glass", (x + .01, (y0 + y1) / 2, (z0 + z1) / 2), (.004, y1 - y0, z1 - z0), glass)
    pane.visible_shadow = False
    made.append(pane)
    made.append(box("Right wall", (ROOM["x1"] + .05, (ya + yb) / 2, zb / 2), (.10, yb - ya, zb), wall))
    made.append(box("Front wall", ((ROOM["x0"] + ROOM["x1"]) / 2, ROOM["y0"] - .05, zb / 2),
                    (ROOM["x1"] - ROOM["x0"] + .3, .10, zb), wall))
    made.append(box("Ceiling slab", ((ROOM["x0"] + ROOM["x1"]) / 2, (ya + yb) / 2, ROOM["ceiling"] + .07),
                    (ROOM["x1"] - ROOM["x0"] + .3, yb - ya, .12), bpy.data.materials["photo6 painted window timber"]))
    bpy.data.objects["photo6 window glass"].visible_shadow = False
    return [obj.name for obj in made]


def lights(scene, args):
    for name in STUDIO_LIGHTS:
        bpy.data.objects[name].hide_render = True
    tree = scene.world.node_tree
    env = next(n for n in tree.nodes if n.type == "TEX_ENVIRONMENT")
    env.image = bpy.data.images.load(str(asset(HDRI)), check_existing=True)
    mapping = next(n for n in tree.nodes if n.type == "MAPPING")
    coord = next(n for n in tree.nodes if n.type == "TEX_COORD")
    tree.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(args.sky_rotation))
    tree.nodes["Background"].inputs["Strength"].default_value = args.sky
    if args.sun_scale != 1.0:
        # Dim only the sun disk of the HDRI (pixels above 100; the sky stays below 21 except 0.01 % of it), so the
        # sun patch on the worktop keeps its marble veins without darkening the sky-lit rest of the kitchen.
        grey = tree.nodes.new("ShaderNodeRGBToBW")
        tree.links.new(env.outputs["Color"], grey.inputs["Color"])
        disk = tree.nodes.new("ShaderNodeMath")
        disk.operation = "GREATER_THAN"
        disk.inputs[1].default_value = 100.0
        tree.links.new(grey.outputs["Val"], disk.inputs[0])
        factor = tree.nodes.new("ShaderNodeMath")
        factor.operation = "MULTIPLY_ADD"
        factor.inputs[1].default_value = args.sun_scale - 1.0
        factor.inputs[2].default_value = 1.0
        tree.links.new(disk.outputs[0], factor.inputs[0])
        dim = tree.nodes.new("ShaderNodeVectorMath")
        dim.operation = "SCALE"
        tree.links.new(env.outputs["Color"], dim.inputs[0])
        tree.links.new(factor.outputs[0], dim.inputs["Scale"])
        tree.links.new(dim.outputs["Vector"], tree.nodes["Background"].inputs["Color"])
    made = []
    # Light portals in both openings: the sky is the source, sampled through the windows.
    x0, x1, z0, z1 = BACK_WINDOW
    portal = bpy.data.lights.new("Back window sky portal", "AREA")
    portal.shape, portal.size, portal.size_y = "RECTANGLE", x1 - x0, z1 - z0
    portal.cycles.is_portal = True
    obj = bpy.data.objects.new("Back window sky portal", portal)
    scene.collection.objects.link(obj)
    obj.location = ((x0 + x1) / 2, ROOM["y1"] + .02, (z0 + z1) / 2)
    obj.rotation_euler = (math.radians(-90.0), 0.0, 0.0)      # local -z -> -y: faces into the room
    made.append(obj.name)
    y0, y1, z0, z1 = SIDE_WINDOW
    portal = bpy.data.lights.new("Left window sky portal", "AREA")
    portal.shape, portal.size, portal.size_y = "RECTANGLE", z1 - z0, y1 - y0
    portal.cycles.is_portal = True
    obj = bpy.data.objects.new("Left window sky portal", portal)
    scene.collection.objects.link(obj)
    obj.location = (ROOM["x0"] - .06, (y0 + y1) / 2, (z0 + z1) / 2)
    obj.rotation_euler = (0.0, math.radians(-90.0), 0.0)      # local -z -> +x
    made.append(obj.name)
    if args.sun > 0:
        made.append(kit.sun("Low sun through the left window", (.86, .30, -.42), args.sun, angle_deg=2.5,
                            color=(1.0, .94, .84)).name)
    # Flush ceiling fitting with a real body: an opal disc with a warm LED behind it (out of frame).
    lamp = bpy.data.lights.new("Ceiling fitting LED", "AREA")
    lamp.shape, lamp.size, lamp.energy, lamp.color = "DISK", .30, args.lamp, (1.0, .86, .72)
    obj = bpy.data.objects.new("Ceiling fitting LED", lamp)
    scene.collection.objects.link(obj)
    obj.location = (.30, -.55, ROOM["ceiling"] - .05)
    made.append(obj.name)
    diffuser = bpy.data.materials.new("Opal ceiling diffuser")
    plain(diffuser, (.92, .92, .90), .3)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=.17, depth=.035, location=(.30, -.55, ROOM["ceiling"] - .018))
    bpy.context.object.name = "Ceiling fitting body"
    bpy.context.object.data.materials.append(diffuser)
    return made


def render_settings(scene, args):
    scene.render.engine = "CYCLES"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, args.percent
    if args.threads:
        scene.render.threads_mode, scene.render.threads = "FIXED", args.threads
    scene.render.fps = 24
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = args.exposure
    scene.cycles.samples = args.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = .01
    scene.cycles.adaptive_min_samples = 64
    scene.cycles.seed = 731
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.sample_clamp_indirect = 10.0
    scene.cycles.caustics_reflective = scene.cycles.caustics_refractive = False
    # Motion blur needs persistent data off in Blender 4.3 (bodies that come to rest vanish otherwise).
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = .25
    scene.render.motion_blur_position = "CENTER"
    scene.render.use_persistent_data = False
    kit.lens_finish(scene, vignette=.10, dispersion=.002)
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


def interpolation_report():
    bag = bpy.data.objects.get("silicone bag native FEM")
    rows = {}
    if bag:
        for fc in bag.data.shape_keys.animation_data.action.fcurves:
            for key in fc.keyframe_points:
                rows[key.interpolation] = rows.get(key.interpolation, 0) + 1
    return rows


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--case", required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", default="1-96", help="'a-b' or a comma list")
    p.add_argument("--samples", type=int, default=256)
    p.add_argument("--exposure", type=float, default=1.25)
    p.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX")
    p.add_argument("--sky", type=float, default=4.0, help="strength of the daylight HDRI seen through the windows")
    p.add_argument("--sky-rotation", type=float, default=225.0, help="HDRI yaw; 225: the sun falls through the back window")
    p.add_argument("--bag-k", type=float, default=200.0, help="bag optical depth per metre of wall (accepted look: 300)")
    p.add_argument("--sun-scale", type=float, default=0.4, help="scale of the HDRI sun disk (1: as captured)")
    p.add_argument("--sun", type=float, default=0.0, help="sun strength through the left window (0: none)")
    p.add_argument("--lamp", type=float, default=12.0, help="ceiling fitting power (W)")
    p.add_argument("--percent", type=int, default=100, help="resolution percentage (previews only)")
    p.add_argument("--threads", type=int, default=0, help="CPU render threads (0: Blender default)")
    args = p.parse_args(argv)
    frames = (list(range(int(args.frames.split("-")[0]), int(args.frames.split("-")[1]) + 1))
              if "-" in args.frames else [int(f) for f in args.frames.split(",")])
    scene = bpy.context.scene
    template = Path(bpy.data.filepath)
    native = np.load(args.source / "simulation.npz")
    assert np.array_equal(native["times"], np.arange(97) / 24)
    camera_before = [list(row) for row in scene.camera.matrix_world]
    lens_before = scene.camera.data.lens
    utils.bind_native_cache(native)
    signature = utils.dynamic_signature()
    skin = accepted.apply_physical_skin(native)
    assert utils.dynamic_signature() == signature
    room = room_shell()
    lit = lights(scene, args)
    tiles = tilt_tiles()
    restyle_materials(args)
    label = hide_label()
    render_settings(scene, args)
    assert utils.dynamic_signature() == signature, "native bag/can states must stay untouched"
    assert [list(row) for row in scene.camera.matrix_world] == camera_before and scene.camera.data.lens == lens_before
    assert scene.camera.data.shift_x == 0 and scene.camera.data.shift_y == 0
    for name in room:
        kit.assert_clear([bpy.data.objects[name]], KEEPOUT, name)
    coverage = utils.coverage(native)
    assert coverage["passed"], coverage
    replay = accepted.replay_audit(native)
    args.out.mkdir(parents=True, exist_ok=True)
    kit.write_json(args.out / "realism_provenance.json", {
        "look": "appearance/realism.py (accepted look)", "case": args.case, "worker": kit.host_record(),
        "blender": bpy.app.version_string, "template": template.name, "template_sha256": kit.sha256(template),
        "native_cache_sha256": kit.sha256(args.source / "simulation.npz"), "native_signature": signature,
        "native_replay_audit": replay, "camera_coverage": coverage, "physical_skin": skin,
        "camera_matrix_world": camera_before, "camera_lens_mm": lens_before,
        "samples": args.samples, "exposure": args.exposure, "sky_hdri": HDRI, "sky_strength": args.sky,
        "sky_rotation_deg": args.sky_rotation, "sun_strength": args.sun, "ceiling_lamp_w": args.lamp, "bag_optical_k_per_m": args.bag_k, "hdri_sun_scale": args.sun_scale,
        "device": args.device, "motion_blur_shutter": scene.render.motion_blur_shutter,
        "shape_key_interpolation": interpolation_report(), "frames": [frames[0], frames[-1]],
        "room_additions": room, "lights": lit, "tilted_tiles": tiles, "hidden_label_objects": label,
        "textures": ["oak_veneer_01 (packed in the template)", HDRI]})
    for f in frames:
        scene.frame_set(f)
        scene.render.filepath = str(args.out / "frames" / f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("RENDER_FRAME", f, flush=True)


main()
