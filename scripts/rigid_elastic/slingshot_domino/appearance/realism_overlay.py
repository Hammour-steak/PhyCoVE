"""Appearance overlay: the delivered slingshot and domino on a sunlit home making table.

`render_scene.py` is imported and runs with one hook after `polish_scene`
(`render_scene.OVERLAY`), so the native trajectories, ribbon
frames, camera and every edit stay those of the delivered renderer. Only static room geometry,
lights, materials and dressing change.

    CUDA_VISIBLE_DEVICES=<uuid> blender -b --python-exit-code 1 --python realism_overlay.py -- \
        --assets <assets/scenes/slingshot_domino> --simulation <case dir> --out OUT [--frames 1,31,96] [--samples 64]
"""
from pathlib import Path
import math
import os
import sys

HERE = Path(__file__).resolve().parent
SCENE = HERE.parent
sys.path[:0] = [str(HERE), str(SCENE), str(HERE.parents[2])]
import pcve_realism_kit as kit
from pcve_assets import asset

PROPS = asset("scenes/slingshot_domino/realism")
# Union over all six cases (ball, pouch, bands, dominoes), plus the delete_domino ball
# that leaves the table edge and lands on the floor near x = 2.3 m.
KEEPOUTS = (((-.14, -.06, -.01), (.66, .19, .16)), ((.60, -.04, -.774), (2.42, .05, .16)))  # floor top -.775 is its landing surface
BACKGROUND = ("Back workshop shelf", "Shelf upright", "Brush pot", "Wood brush handle", "Brush brass ferrule",
              "Linen sketchbook", "Cork inspiration board", "Pinned plan", "Brass board pin")


def clear(objects, label):
    return [kit.assert_clear(objects, box, label) for box in KEEPOUTS][0]


def in_frame(scene, objects, margin=.02):
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    pts = [world_to_camera_view(scene, scene.camera, o.matrix_world @ Vector(c)) for o in objects if o.type == "MESH" for c in o.bound_box]
    box = (min(q.x for q in pts), max(q.x for q in pts), min(q.y for q in pts), max(q.y for q in pts))
    return box, box[0] >= margin and box[1] <= 1 - margin and box[2] >= margin and box[3] <= 1 - margin


def pegboard_material(name, pitch=.0254, hole=.0032):
    """Tempered hardboard pegboard: 1-inch hole grid in the x-z plane, slight tone drift."""
    mat = kit.diffuse(name, (.34, .22, .12), .62)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = next(x for x in n if x.type == "BSDF_PRINCIPLED")
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(n.new("ShaderNodeTexCoord").outputs["Object"], sep.inputs[0])
    parts = []
    for axis in ("X", "Z"):
        scale = n.new("ShaderNodeMath")
        scale.operation = "DIVIDE"
        scale.inputs[1].default_value = pitch
        l.new(sep.outputs[axis], scale.inputs[0])
        frac = n.new("ShaderNodeMath")
        frac.operation = "FRACT"
        l.new(scale.outputs[0], frac.inputs[0])
        off = n.new("ShaderNodeMath")
        off.operation = "SUBTRACT"
        off.inputs[1].default_value = .5
        l.new(frac.outputs[0], off.inputs[0])
        sq = n.new("ShaderNodeMath")
        sq.operation = "MULTIPLY"
        l.new(off.outputs[0], sq.inputs[0])
        l.new(off.outputs[0], sq.inputs[1])
        parts.append(sq)
    add = n.new("ShaderNodeMath")
    l.new(parts[0].outputs[0], add.inputs[0])
    l.new(parts[1].outputs[0], add.inputs[1])
    edge = n.new("ShaderNodeMapRange")  # 1 inside a hole, soft 0.3 mm rim
    r0, r1 = (hole / pitch) ** 2 * .82, (hole / pitch) ** 2 * 1.18
    edge.inputs["From Min"].default_value = r1
    edge.inputs["From Max"].default_value = r0
    l.new(add.outputs[0], edge.inputs["Value"])
    mix = n.new("ShaderNodeMixRGB")
    mix.inputs[1].default_value = (.34, .22, .12, 1)
    mix.inputs[2].default_value = (.012, .010, .008, 1)
    l.new(edge.outputs[0], mix.inputs[0])
    l.new(mix.outputs[0], bs.inputs["Base Color"])
    bump = n.new("ShaderNodeBump")
    bump.invert = True
    bump.inputs["Distance"].default_value = .0015
    l.new(edge.outputs[0], bump.inputs["Height"])
    l.new(bump.outputs[0], bs.inputs["Normal"])
    kit.add_surface_wear(mat, smudge=.14, grime=.14, scratch=.06, scale=.4)
    return mat


def warm_table(mat, tint=(1.0, .90, .78)):
    """Pull the scanned top away from pink toward an oiled brown."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    src = bs.inputs["Base Color"].links[0].from_socket
    mul = nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    mul.inputs[2].default_value = (*tint, 1)
    links.new(src, mul.inputs[1])
    links.new(mul.outputs[0], bs.inputs["Base Color"])


def lens_finish(scene, vignette=.12, dispersion=.0025):
    scene.use_nodes = True
    tree = scene.node_tree
    rl = next((x for x in tree.nodes if x.bl_idname == "CompositorNodeRLayers"), None) or tree.nodes.new("CompositorNodeRLayers")
    out = next((x for x in tree.nodes if x.bl_idname == "CompositorNodeComposite"), None) or tree.nodes.new("CompositorNodeComposite")
    for link in list(out.inputs[0].links):
        tree.links.remove(link)
    lens = tree.nodes.new("CompositorNodeLensdist")
    lens.use_fit = True
    lens.inputs["Dispersion"].default_value = dispersion
    tree.links.new(rl.outputs["Image"], lens.inputs["Image"])
    mask = tree.nodes.new("CompositorNodeEllipseMask")
    mask.width, mask.height = 1.18, 1.32
    blur = tree.nodes.new("CompositorNodeBlur")
    blur.filter_type = "GAUSS"
    blur.use_relative = True
    blur.factor_x = blur.factor_y = 30.0
    tree.links.new(mask.outputs["Mask"], blur.inputs["Image"])
    level = tree.nodes.new("CompositorNodeMapRange")
    level.inputs["To Min"].default_value = 1.0 - vignette
    tree.links.new(blur.outputs["Image"], level.inputs["Value"])
    mix = tree.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    tree.links.new(lens.outputs["Image"], mix.inputs[1])
    tree.links.new(level.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], out.inputs[0])


def __overlay__(out):
    import bpy
    scene = bpy.context.scene
    bpy.context.view_layer.update()  # evaluate the delivered camera aim before snapshotting
    before = {o.name: [list(r) for r in o.matrix_world] for o in scene.objects}
    for o in scene.objects:
        if o.name.startswith(BACKGROUND) or o.name == "Room floor":
            o.hide_render = True
    room = kit.daylight_room(-1.4, 2.6, -1.9, .68, -.775, 1.55, (-1.2, .55, .05, 1.45, 2, 1),
                             wall=(.62, .60, .55), floor=(.24, .17, .11), back_wall=False)
    audit = [clear([o], o.name) for o in room]
    # A pegboard over the bench, as in most home making corners; only its lowest rows show; it runs down into the gap behind the bench.
    board = kit.plain_box("Workbench pegboard", (.375, .6735, .35), (1.75, .006, 1.10), pegboard_material("Tempered hardboard pegboard"))
    for x in (-.485, 1.235):  # wooden furring strips that space it off the wall
        kit.plain_box("Pegboard furring strip", (x, .677, .35), (.03, .006, 1.10), kit.diffuse("Pine furring", (.45, .32, .18), .7))
    audit.append(clear([board], board.name))
    kit.add_wall_mottling(bpy.data.materials["Sage limewash wall"], .08)
    table = bpy.data.materials["wooden_table_02"]
    warm_table(table)
    kit.add_surface_wear(table, smudge=.16, grime=.12, scratch=.10, scale=.4)
    for name, amt in (("4K open-grain oiled maple", .08), ("Oiled workshop mounting foot", .10),
                      ("Dark gunmetal clamp", .12), ("Satin machined steel", .08), ("Moulded petrol-blue solid polymer", .06),
                      ("Bone plastic", .06), ("Ruler pale beech", .10), ("Warm uncoated drawing paper", .04)):
        if name in bpy.data.materials:
            kit.add_surface_wear(bpy.data.materials[name], smudge=amt, grime=amt, scratch=amt * .5, scale=.08)
    if os.environ.get("REALISM_PROBE"):  # placement search: [[name, x, y, yaw, lay_flat], ...]
        import json
        for name, x, y, r, flat in json.loads(os.environ["REALISM_PROBE"]):
            root, tool = kit.import_prop(next((PROPS / name).glob("*.gltf")), "probe " + name, (x, y, 0), r, lay_flat=flat)
            bpy.context.view_layer.update()
            lo, hi = kit.world_bbox(tool)
            box, ok = in_frame(scene, tool)
            hit = any(lo.x < b[1][0] and hi.x > b[0][0] and lo.y < b[1][1] and hi.y > b[0][1] for b in KEEPOUTS)
            print("PROBE", name, (x, y, r, flat), "frame", [round(v, 3) for v in box], ok, "corridor", hit,
                  "bbox", [round(v, 3) for v in (lo.x, hi.x, lo.y, hi.y, hi.z)], flush=True)
            for o in [root] + tool:
                bpy.data.objects.remove(o, do_unlink=True)
        raise SystemExit(0)
    driver = kit.prop(PROPS, "flathead_screwdriver", (.50, .38, 0), 1.1, rests=True, lay_flat=True)
    members = [o for o in scene.objects if o.parent and o.parent.name == "Dressing flathead_screwdriver"]
    audit.append(clear(members, "flathead_screwdriver"))
    box, ok = in_frame(scene, members)
    if not ok:
        raise RuntimeError(f"screwdriver is cut by the frame edge: {box}")
    # Back edge of the bench, left of the fork: the lidded box that keeps spare balls and bands,
    # low enough to sit wholly inside the frame.
    back = []
    # (A tape measure was tried beside it: wherever it fits in frame it sits right behind the drawn-back pouch.)
    for name, at, yaw in (("CheeseBox_01", (.09, .50, 0), .15),):
        back.append(kit.prop(PROPS, name, at, yaw, rests=True))
        members = [o for o in scene.objects if o.parent and o.parent.name == "Dressing " + name]
        audit.append(clear(members, name))
        box, ok = in_frame(scene, members)
        if not ok:
            raise RuntimeError(f"{name} is cut by the frame edge: {box}")
    kit.sawdust("Maple dust around the base", [(-.08, -.07, .06, .07, 3), (-.25, .05, .05, .45, 1)], 700,
                ((-.03, -.05), (.03, .05)), color=(.60, .45, .30), seed=19, size=(.00012, .0005))
    # Light: low afternoon sun through the left window; delivered studio areas become weak fill.
    for o in scene.objects:
        if o.type == "LIGHT" and o.data.type == "AREA":
            o.data.energy *= .10
    kit.sun("Afternoon sun through side window", (.80, -.25, -.50), 13.0, angle_deg=1.0, color=(1.0, .91, .78))
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Strength"].default_value = .45
    sky = bpy.data.lights.new("Window sky fill", "AREA")
    sky.shape, sky.size, sky.size_y = "RECTANGLE", 1.7, 1.4
    sky.energy, sky.color = 9.0, (.80, .88, 1.0)
    sl = bpy.data.objects.new("Window sky fill", sky)
    scene.collection.objects.link(sl)
    sl.location = (-1.38, -.32, .75)
    sl.rotation_euler = (0, math.radians(-90), 0)
    scene.view_settings.exposure = float(os.environ.get("REALISM_EXPOSURE", ".1"))
    if os.environ.get("REALISM_DEBUG") == "sun":
        bg.inputs["Strength"].default_value = 0
        for o in scene.objects:
            if o.type == "LIGHT" and o.data.type != "SUN":
                o.data.energy = 0
    lens_finish(scene)
    moved = [n for n, m in before.items() if [list(r) for r in scene.objects[n].matrix_world] != m]
    assert not moved, f"overlay moved delivered objects: {moved}"
    kit.write_json(Path(out) / "realism_provenance.json", {
        "overlay": "realism_overlay", "host": kit.host_record(), "assets": str(PROPS),
        "hidden_background": list(BACKGROUND) + ["Room floor"], "dressing": audit + [driver] + back, "keepouts_m": KEEPOUTS})


import render_scene  # noqa: E402

render_scene.OVERLAY = __overlay__
render_scene.main()
