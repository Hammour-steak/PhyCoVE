"""Appearance overlay: the spring balance on a daylit school physics bench.

`render_spring.py` and `render_helpers.py` run as imported modules with one hook
(`render_spring.OVERLAY`) after the delivered lights and compositor, so the native caches, the camera,
the baked keyframes, the instance-id masks and every edit stay those of the base look.
Only static room geometry, lights, materials and dressing change.

    CUDA_VISIBLE_DEVICES=<uuid> PCVE_SPRING_SCALE_INPUT=<delivery> \
    blender -b --python-exit-code 1 --python realism.py -- --case source --out OUT [--frames 31] [--samples 64]
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

PROPS = asset("scenes/spring_scale_weight_drop/realism")
# The whole instrument (base, upright, guides, dashpot, scale, pan, falling weight, added stop)
# lies inside this box in every case; dressing must stay out of it.
KEEPOUT = ((-.26, -.10, -.01), (.30, .27, 1.00))
BENCH = (-.90, 1.10, -.70, .70)              # top at z = 0, slab 54 mm
FLOOR_Z = -.90
BACK_Y = .77                                  # front face of the delivered wall slab


def box_uv(obj, tile):
    """World-space box projection so scanned textures keep their real size on room slabs."""
    me = obj.data
    uv = me.uv_layers.active or me.uv_layers.new()
    for poly in me.polygons:
        axis = max(range(3), key=lambda i: abs(poly.normal[i]))
        keep = [i for i in range(3) if i != axis]
        for li in poly.loop_indices:
            co = obj.matrix_world @ me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (co[keep[0]] / tile, co[keep[1]] / tile)


def glazed_tiles(name, size=.108, grout=.0035):
    """Square white wall tiles: slight per-tile tone and glaze waviness, recessed grey grout."""
    import bpy
    mat = kit.diffuse(name, (.76, .74, .68), .18)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = next(x for x in n if x.type == "BSDF_PRINCIPLED")
    co = n.new("ShaderNodeTexCoord")
    brick = n.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.squash = 1.0
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Brick Width"].default_value = size
    brick.inputs["Row Height"].default_value = size
    brick.inputs["Mortar Size"].default_value = grout
    brick.inputs["Mortar Smooth"].default_value = .35
    brick.inputs["Color1"].default_value = (.77, .75, .69, 1)
    brick.inputs["Color2"].default_value = (.70, .69, .64, 1)
    brick.inputs["Mortar"].default_value = (.52, .50, .45, 1)
    swiz = n.new("ShaderNodeVectorMath")  # Wall lies in the x-z plane.
    swiz.operation = "MULTIPLY"
    swiz.inputs[1].default_value = (1, 0, 1)
    sep = n.new("ShaderNodeSeparateXYZ")
    comb = n.new("ShaderNodeCombineXYZ")
    l.new(co.outputs["Object"], swiz.inputs[0])
    l.new(swiz.outputs[0], sep.inputs[0])
    l.new(sep.outputs["X"], comb.inputs["X"])
    l.new(sep.outputs["Z"], comb.inputs["Y"])
    l.new(comb.outputs[0], brick.inputs["Vector"])
    l.new(brick.outputs["Color"], bs.inputs["Base Color"])
    rough = n.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = .45
    rough.inputs["To Max"].default_value = .14
    l.new(brick.outputs["Fac"], rough.inputs["Value"])
    l.new(rough.outputs[0], bs.inputs["Roughness"])
    wave = n.new("ShaderNodeTexNoise")
    wave.inputs["Scale"].default_value = 9.0
    wave.inputs["Detail"].default_value = 2.0
    l.new(comb.outputs[0], wave.inputs["Vector"])
    height = n.new("ShaderNodeMath")
    height.operation = "MULTIPLY_ADD"
    l.new(brick.outputs["Fac"], height.inputs[0])
    height.inputs[1].default_value = -1.0
    l.new(wave.outputs["Fac"], height.inputs[2])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .0012
    bump.inputs["Strength"].default_value = .55
    l.new(height.outputs[0], bump.inputs["Height"])
    l.new(bump.outputs[0], bs.inputs["Normal"])
    kit.add_surface_wear(mat, smudge=.05, grime=.05, scratch=0.0, scale=.6)
    return mat


def socket_trunking(x0, x1, z, y):
    """PVC cable trunking along the backsplash with two double outlets, as on lab benches."""
    pvc = kit.diffuse("Bench trunking PVC", (.70, .70, .67), .42)
    kit.add_surface_wear(pvc, smudge=.10, grime=.10, scratch=.04, scale=.3)
    slot = kit.diffuse("Outlet contact slot", (.025, .025, .025), .6)
    made = [kit.plain_box("Bench cable trunking", ((x0 + x1) / 2, y - .025, z), (x1 - x0, .05, .075), pvc)]
    for cx in (x0 + .22, x1 - .30):
        for k in (-1, 1):
            px = cx + k * .045
            made.append(kit.plain_box("Outlet face", (px, y - .052, z), (.082, .006, .062), pvc))
            for dx in (-.011, .011):
                made.append(kit.plain_box("Outlet slot", (px + dx, y - .0552, z + .006), (.0025, .001, .009), slot))
            made.append(kit.plain_box("Outlet earth", (px, y - .0552, z - .012), (.0035, .001, .0045), slot))
    return made


def lens_into(scene, vignette=.13, dispersion=.003):
    """Kit lens finish spliced between render layer and composite, keeping the IndexOB file output."""
    tree = scene.node_tree
    rl = next(x for x in tree.nodes if x.bl_idname == "CompositorNodeRLayers")
    out = next(x for x in tree.nodes if x.bl_idname == "CompositorNodeComposite")
    for link in list(out.inputs[0].links):
        tree.links.remove(link)
    lens = tree.nodes.new("CompositorNodeLensdist")
    lens.use_fit = True
    lens.inputs["Distortion"].default_value = 0.0
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


def __overlay__(sc, cam, p, z, target):
    import bpy
    moving = {o.name: o.pass_index for o in bpy.data.objects if o.pass_index}
    obj = bpy.data.objects
    # Delivered flat wall and dark backboard give way to a real room.
    for name in ("Out of focus laboratory wall", "Bench backboard"):
        obj[name].hide_render = True
    room = kit.daylight_room(-2.0, 2.1, -2.7, BACK_Y, FLOOR_Z, 2.15, (-1.75, .45, .02, 1.95, 2, 1),
                             wall=(.50, .55, .49), floor=(.30, .28, .25), back_wall=True)
    wall = bpy.data.materials["Room wall"]
    kit.add_wall_mottling(wall, .07)
    floor = kit.scan_material("School lab linoleum", PROPS / "old_linoleum_flooring_01", "old_linoleum_flooring_01",
                              normal=.6, rough_floor=.45)
    for o in room:
        if o.name == "Room floor":
            o.data.materials[0] = floor
            box_uv(o, 1.6)
    # Bench body below the top: phenolic-faced cabinet carcass with a recessed plinth.
    carcass = kit.diffuse("Bench cabinet laminate", (.40, .42, .39), .5)
    kit.add_surface_wear(carcass, smudge=.12, grime=.12, scratch=.05, scale=.5)
    x0, x1, y0, y1 = BENCH
    kit.plain_box("Bench cabinet carcass", ((x0 + x1) / 2, (y0 + y1) / 2 + .03, (FLOOR_Z + .08 - .054) / 2),
                  (x1 - x0 - .06, y1 - y0 - .10, -.054 - FLOOR_Z - .08), carcass)
    kit.plain_box("Bench plinth", ((x0 + x1) / 2, (y0 + y1) / 2 + .06, FLOOR_Z + .04),
                  (x1 - x0 - .10, y1 - y0 - .20, .08), kit.diffuse("Plinth vinyl", (.06, .06, .06), .6))
    # Tiled splashback to the height of a bench shelf, with cable trunking and outlets.
    tiles = glazed_tiles("Glazed splashback tiles")
    kit.plain_box("Tiled splashback", ((x0 + x1) / 2, BACK_Y - .004, .2268), (x1 - x0, .008, .4536), tiles)
    kit.plain_box("Splashback capping", ((x0 + x1) / 2, BACK_Y - .008, .4566), (x1 - x0, .016, .006), kit.diffuse("Tile edge trim", (.66, .65, .60), .35))
    trunk = socket_trunking(.42, 1.40, .30, BACK_Y - .008)
    # Bench top: keep the delivered scan, add handling wear and chemical rings near the work area.
    bench = bpy.data.materials["Photographic worn laboratory bench"]
    kit.add_surface_wear(bench, smudge=.14, grime=.10, scratch=.08, scale=.8)
    for name in ("Deep grey green enamel", "Matte dark green instrument panel", "Aged ivory enamel scale"):
        kit.add_surface_wear(bpy.data.materials[name], smudge=.10, grime=.08, scratch=.05, scale=.25)
    for name in ("Spun aluminum pan", "Brass calibration weight with fine lathe marks", "Passivated spring steel"):
        kit.add_surface_wear(bpy.data.materials[name], smudge=.08, grime=.05, scratch=.03, scale=.12)
    kit.add_surface_wear(bpy.data.materials["Fine grain calibration weight case"], smudge=.12, grime=.12, scratch=.06, scale=.3)
    audit = [kit.assert_clear([o], KEEPOUT, o.name) for o in room + trunk]
    audit.append(kit.prop(PROPS, "retro_multimeter", (.70, .44, 0), -.35, KEEPOUT, rests=True))
    audit.append(kit.prop(PROPS, "magnifying_glass_01", (.47, .40, 0), 1.9, KEEPOUT, rests=True, lay_flat=True))
    kit.sawdust("Bench dust and eraser crumbs", [(-.85, -.65, 1.05, .66, 1)], 900, ((-.27, -.11), (.31, .28)),
                color=(.55, .52, .47), size=(.0004, .0014))
    # Light: low sun through the left window; delivered studio areas drop to fill level.
    for o in obj:
        if o.type == "LIGHT" and o.data.type == "AREA":
            o.data.energy *= .10
    kit.sun("Afternoon sun through lab window", (.75, .50, -.42), 12.0, angle_deg=1.0, color=(1.0, .93, .83))
    bg = sc.world.node_tree.nodes["Background"]
    bg.inputs["Strength"].default_value = .55
    window = bpy.data.lights.new("Window sky fill", "AREA")
    window.shape, window.size, window.size_y = "RECTANGLE", 2.1, 1.9
    window.energy, window.color = 12.0, (.82, .89, 1.0)
    wl = bpy.data.objects.new("Window sky fill", window)
    bpy.context.collection.objects.link(wl)
    wl.location = (-1.98, -.65, 1.0)
    wl.rotation_euler = (0, math.radians(-90), 0)
    sc.view_settings.exposure = .25
    if os.environ.get("REALISM_DEBUG") == "sun":  # Diagnostic: sun alone.
        bg.inputs["Strength"].default_value = 0
        for o in obj:
            if o.type == "LIGHT" and o.data.type != "SUN":
                o.data.energy = 0
    sc.view_settings.look = "AgX - Medium High Contrast"
    lens_into(sc)
    after = {o.name: o.pass_index for o in bpy.data.objects if o.pass_index}
    assert after == moving, "overlay touched instance identities"
    kit.write_json(Path(target) / "realism_provenance.json", {
        "overlay": "realism_overlay", "host": kit.host_record(),
        "assets": str(PROPS), "dressing": audit, "keepout_m": KEEPOUT})


# Allow explicitly selected high-memory GPU for this appearance pass;
# the active device is recorded in realism_provenance.json.
import appearance.render_helpers as helpers  # noqa: E402
import appearance.render_spring as render  # noqa: E402

helpers.GPU_POLICY_OVERRIDE = {'allowed': True, 'policy': 'appearance_pass_override'}
render.OVERLAY = __overlay__
render.main()
