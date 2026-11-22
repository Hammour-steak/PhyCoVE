"""Appearance overlay: the entryway slippers in real morning light with a lived-in hallway.

`render_hero.main` runs with one hook (`overlay`) right after the room is
applied, so the native slide surfaces,
the optional shoe tray, the camera and every edit stay those of the accepted
renderer. Only lights, room materials and static dressing change.

    CUDA_VISIBLE_DEVICES=<uuid> blender -b --python-exit-code 1 --python realism.py -- \
        --case source --cache <suite>/cases/source/simulation.npz --out OUT [--preview 41] [--samples 64]
"""
from pathlib import Path
import os
import sys

HERE = Path(__file__).resolve().parent            # .../entryway_eva_slippers/tools/native
SCENE = HERE.parents[1]
sys.path[:0] = [str(HERE), str(SCENE), str(SCENE.parents[1])]
import pcve_realism_kit as kit

REVISED = {"light_falling", "slippery_floor"}


def probe(scene):
    import bpy
    from collections import Counter
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    cam = scene.camera
    print("CAM", tuple(round(v, 3) for v in cam.location), cam.data.lens, scene.view_settings.look, scene.view_settings.exposure,
          "world", scene.world and [(n.bl_idname, n.inputs[1].default_value if n.bl_idname == "ShaderNodeBackground" else "") for n in scene.world.node_tree.nodes])
    for o in scene.objects:
        if o.type == "LIGHT":
            print("LIGHT", o.name, o.data.type, round(o.data.energy, 2), tuple(round(v, 2) for v in o.location))
    for o in scene.objects:
        if o.type == "MESH" and not o.hide_render:
            lo, hi = kit.world_bbox([o])
            pts = [world_to_camera_view(scene, cam, o.matrix_world @ Vector(c)) for c in o.bound_box]
            vis = any(0 <= p.x <= 1 and 0 <= p.y <= 1 and p.z > 0 for p in pts)
            print("OBJ", "vis" if vis else "-", o.name[:45], [round(v, 2) for v in lo], [round(v, 2) for v in hi],
                  [s.material.name[:35] for s in o.material_slots if s.material][:2])
    raise SystemExit(0)


# Both slides, the optional shoe tray and their bounce in every case stay inside this volume.
KEEPOUT = ((-.45, -.45, -.01), (.40, .45, .80))
LEFT_WALL_X = -1.90
WINDOW = (-.95, .35, .55, 2.05)               # y0, y1, z0, z1 of the new opening in the left wall


def left_wall_with_window(mat, trim):
    y0, y1, z0, z1 = WINDOW
    ya, yb, za, zb, t = -1.25, 1.78, 0.0, 2.40, .08
    x = LEFT_WALL_X - t / 2
    made = []
    for (a, b), (c, d) in (((ya, yb), (za, z0)), ((ya, yb), (z1, zb)), ((ya, y0), (z0, z1)), ((y1, yb), (z0, z1))):
        made.append(kit.plain_box("Left wall with window", (x, (a + b) / 2, (c + d) / 2), (t, b - a, d - c), mat))
    for yy in (y0 + .025, (y0 + y1) / 2, y1 - .025):
        made.append(kit.plain_box("Window stile", (x + t / 2, yy, (z0 + z1) / 2), (.05, .05, z1 - z0), trim))
    for zz in (z0 + .025, z1 - .025, (z0 + z1) / 2):
        made.append(kit.plain_box("Window rail", (x + t / 2, (y0 + y1) / 2, zz), (.05, y1 - y0, .05), trim))
    return made


def shoe_scuffs(mat, amount=.35, scale=2.6):
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = next(x for x in n if x.type == "BSDF_PRINCIPLED")
    co = n.new("ShaderNodeTexCoord")
    warp = n.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 1.3
    l.new(co.outputs["Object"], warp.inputs["Vector"])
    bend = n.new("ShaderNodeVectorMath")
    bend.operation = "MULTIPLY_ADD"
    bend.inputs[1].default_value = (.35, .35, .35)
    l.new(warp.outputs["Color"], bend.inputs[0])
    l.new(co.outputs["Object"], bend.inputs[2])
    stretch = n.new("ShaderNodeVectorMath")
    stretch.operation = "MULTIPLY"
    stretch.inputs[1].default_value = (3.0, 14.0, 1.0)
    l.new(bend.outputs[0], stretch.inputs[0])
    marks = n.new("ShaderNodeTexNoise")
    marks.inputs["Scale"].default_value = scale
    l.new(stretch.outputs[0], marks.inputs["Vector"])
    mask = n.new("ShaderNodeMapRange")
    mask.inputs["From Min"].default_value = .71
    mask.inputs["From Max"].default_value = .76
    mask.inputs["To Max"].default_value = amount
    l.new(marks.outputs["Fac"], mask.inputs["Value"])
    color = bs.inputs["Base Color"]
    src = color.links[0].from_socket if color.is_linked else None
    dark = n.new("ShaderNodeMixRGB")
    dark.inputs[2].default_value = (.03, .028, .026, 1)
    l.new(mask.outputs[0], dark.inputs[0])
    if src:
        l.new(src, dark.inputs[1])
    else:
        dark.inputs[1].default_value = tuple(color.default_value)
    l.new(dark.outputs[0], color)


def __overlay__(scene):
    import bpy
    if os.environ.get("REALISM_PROBE"):
        probe(scene)
    mats = bpy.data.materials
    made = left_wall_with_window(mats["Warm mineral paint"], mats["Soft white painted skirting"])
    for o in made:
        kit.assert_clear([o], KEEPOUT, o.name)
    for o in scene.objects:
        if o.type == "LIGHT" and o.data.type == "AREA":
            o.data.energy *= float(os.environ.get("REALISM_FILL", ".08"))
    kit.sun("Morning sun through the hall window", (.86, .30, -.42), float(os.environ.get("REALISM_SUN", "13.0")),
            angle_deg=.8, color=(1.0, .92, .80))
    floor = next(m for m in mats if m.name.startswith("4K scanned stone tile entryway"))
    kit.add_surface_wear(floor, smudge=.12, grime=.10, scratch=.06, scale=1.0)
    shoe_scuffs(floor)
    kit.add_surface_wear(mats["Natural coir woven doormat"], smudge=.20, grime=.28, scratch=0.0, scale=.6)
    kit.add_wall_mottling(mats["Warm mineral paint"], .07)
    for name, amt in (("Sage grey enamel door", .10), ("Soft white painted skirting", .10), ("Warm off-white eggshell cabinet", .08),
                      ("Satin nickel hardware", .06), ("Brushed threshold aluminium", .08)):
        if name in mats:
            kit.add_surface_wear(mats[name], smudge=amt, grime=amt, scratch=amt * .5, scale=.3)
    kit.sawdust("Grit tracked in from outside", [(-1.15, .6, -.25, 1.6, 3), (-1.4, -.8, 1.4, 1.6, 1)], 900,
                ((KEEPOUT[0][0], KEEPOUT[0][1]), (KEEPOUT[1][0], KEEPOUT[1][1])), color=(.38, .35, .31), seed=16,
                size=(.0005, .0018), z=.0)
    scene.view_settings.exposure = float(os.environ.get("REALISM_EXPOSURE", "-.25"))
    scene.world.node_tree.nodes["Background"].inputs[1].default_value *= .35
    if os.environ.get("REALISM_DEBUG") == "sun":
        scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0
        for o in scene.objects:
            if o.type == "LIGHT" and o.data.type != "SUN":
                o.data.energy = 0


# The artist slide materials of the scene assets (their SHA-256 is recorded in materials_original.json beside them),
# which render.py loads from the same asset folder.
import hashlib
from pcve_assets import asset
SLIDE_BLEND = asset("scenes/entryway_eva_slippers/geometry/slide_cc0_artist/materials_original.blend")
assert hashlib.sha256(SLIDE_BLEND.read_bytes()).hexdigest() == "620f2c37bff9b4c3aa83633aba2b0742b48cccdc9d619c72bf47aa95100c53bf"
import render  # noqa: E402  (imported first, as the renderers below expect)
import render_replay  # noqa: E402
import render_hero as hero  # noqa: E402
case = sys.argv[sys.argv.index("--case") + 1]
if case in REVISED:  # the two revised cases replay with the production-edit vocabulary
    import vocab_revised as vocab
    hero.SPEC, hero.SPEC_PATH, hero.parameters = vocab.SPEC, vocab.SPEC_PATH, vocab.parameters
hero.main(overlay=__overlay__)
