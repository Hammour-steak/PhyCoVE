"""Current look: a spring launcher on a maple woodworking bench in a garage workshop.

appearance/render.py (with base_scene.py) builds the mechanism, block, board and
keys every moving body from the native 240 Hz states; nothing here moves a body,
changes a collision shape or reads a solver parameter other than for placement
checks. This file replaces the craft-desk dressing with a workshop: a butcher-block
maple bench (top surface at the solver's z=0), painted concrete-block walls, a
window in the left wall (sun and sky are the only daylight), a switched-on
LED batten on the ceiling, steel shelving, scanned hand tools and the two ADD
endpoints (wooden bowl, roll of tape). The camera is camera B of the approved
look (0.58,-1.64,0.38) -> (0.17,0,0.085), 58 mm.

    blender -b --factory-startup --python appearance/realism.py -- --case source --out DIR
        [--frames ...] [--samples 256] [--device optix|cuda|cpu] [--native DIR] [--no-blend] [--blend-only]
"""
from pathlib import Path
import argparse, hashlib, math, os, platform, random, sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT), str(ROOT.parents[1])]
import pcve_realism_kit as kit
from pcve_assets import asset
from scene_common import ASSETS, CASES, FPS, FRAMES, HEIGHT, NATIVE, WIDTH, load_physics, save
import edit_vocab

import base_scene as base  # noqa: E402
import render as mech  # noqa: E402  (shares the base_scene module above)
bpy, np, Vector = base.bpy, base.np, base.Vector

PH = asset("polyhaven")
OWN = ASSETS / "realism"            # scanned props of this look (oil can, pliers, wrench, plant)
LOOK = "workshop_bench"
# Union of every case's swept volume: block travel reaches x=0.629 (mass_half),
# the added block sits at x=0.31; the spring mechanism spans x=-0.30..-0.12.
KEEPOUT = ((-.33, -.075, -.01), (.70, .075, .30))
CAMERA = ((.58, -1.64, .38), (.17, 0, .085), 58.0)
FOCUS = (.12, 0, .06)
BENCH = {'x': (-.62, 1.18), 'y': (-.38, .38), 'thickness': .045, 'floor_z': -.76}
STATIC_REMOVE = ("Sketch sheet", "Sketched", "20 cm steel ruler", "Ruler", "Back wall", "Table leg",
                 "Tabletop plank", "Large left window", "Soft far wall bounce")


# ----------------------------------------------------------------------- helpers
def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def remove_tree(obj):
    for child in list(obj.children):
        remove_tree(child)
    bpy.data.objects.remove(obj, do_unlink=True)


def scan_files(folder, prefix):
    for where in (Path(folder), Path(folder) / "textures"):
        for res in ("2k", "4k", "1k"):
            for rough in ("rough", "arm"):  # arm = AO/roughness/metal packed; roughness is its green channel
                files = {kind: where / f"{prefix}_{kind}_{res}.jpg" for kind in ("diff", rough, "nor_gl")}
                if all(p.is_file() for p in files.values()):
                    return files
    raise FileNotFoundError(f"{folder}/{prefix}_*_{{2k,4k,1k}}.jpg")


def scanned(name, folder, prefix, period=None, tint=None, rough_scale=1.0, rough_add=0.0, normal=1.0):
    """Principled material from a diff/rough/nor_gl scan; UV mapped, or box-projected in object space with `period`."""
    files = scan_files(folder, prefix)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    coord = n.new("ShaderNodeTexCoord")
    vec = coord.outputs["UV"]
    if period:
        scale = n.new("ShaderNodeMapping")
        scale.inputs["Scale"].default_value = (1 / period, 1 / period, 1 / period)
        l.new(coord.outputs["Object"], scale.inputs["Vector"])
        vec = scale.outputs["Vector"]

    def image(kind, data):
        tex = n.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(files[kind]), check_existing=True)
        if data:
            tex.image.colorspace_settings.name = "Non-Color"
        if period:
            tex.projection = "BOX"
            tex.projection_blend = .25
        l.new(vec, tex.inputs["Vector"])
        return tex

    color = image("diff", False).outputs["Color"]
    if tint:
        mul = n.new("ShaderNodeMixRGB")
        mul.blend_type = "MULTIPLY"
        mul.inputs[0].default_value = 1
        mul.inputs[2].default_value = (*tint, 1)
        l.new(color, mul.inputs[1])
        color = mul.outputs[0]
    l.new(color, bs.inputs["Base Color"])
    r = n.new("ShaderNodeMath")
    r.operation = "MULTIPLY_ADD"
    r.use_clamp = True
    r.inputs[1].default_value = rough_scale
    r.inputs[2].default_value = rough_add
    if "rough" in files:
        l.new(image("rough", True).outputs["Color"], r.inputs[0])
    else:
        split = n.new("ShaderNodeSeparateColor")
        l.new(image("arm", True).outputs["Color"], split.inputs["Color"])
        l.new(split.outputs["Green"], r.inputs[0])
    l.new(r.outputs[0], bs.inputs["Roughness"])
    nm = n.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = normal
    l.new(image("nor_gl", True).outputs["Color"], nm.inputs["Color"])
    l.new(nm.outputs[0], bs.inputs["Normal"])
    return mat


def box(name, lo, hi, mat, bevel=0.0, period=.5, offset=(.13, .27)):
    centre = tuple((a + b) / 2 for a, b in zip(lo, hi))
    size = tuple(b - a for a, b in zip(lo, hi))
    return base.cube(name, centre, size, mat, bevel, period, offset)


def ring(name, centre, r_in, r_out, height, mat, segments=192):
    """Closed annular solid on z with its origin at the bottom centre `centre`."""
    verts, faces = [], []
    for z in (0.0, height):
        for r in (r_out, r_in):
            verts += [(r * math.cos(2 * math.pi * i / segments), r * math.sin(2 * math.pi * i / segments), z) for i in range(segments)]
    s = segments
    for i in range(s):
        j = (i + 1) % s
        faces += [(i, j, 2 * s + j, 2 * s + i),                 # outer wall
                  (s + j, s + i, 3 * s + i, 3 * s + j),         # inner wall
                  (s + i, s + j, j, i),                         # bottom annulus
                  (2 * s + i, 2 * s + j, 3 * s + j, 3 * s + i)]  # top annulus
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = centre
    mesh.materials.append(mat)
    for i, p in enumerate(mesh.polygons):
        p.use_smooth = i % 4 < 2
    bev = obj.modifiers.new("Soft edges", "BEVEL")
    bev.width = .0006
    bev.segments = 3
    bpy.context.view_layer.update()
    return obj


def image_node(n, l, path, vector, data=False, box=False):
    tex = n.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(path), check_existing=True)
    if data:
        tex.image.colorspace_settings.name = "Non-Color"
    if box:
        tex.projection = "BOX"
        tex.projection_blend = .25
    l.new(vector, tex.inputs["Vector"])
    return tex


def math_node(n, op, a=None, b=None, clamp=False):
    node = n.new("ShaderNodeMath")
    node.operation = op
    node.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if isinstance(v, (int, float)):
            node.inputs[i].default_value = v
    return node


def map_range(n, l, socket, a, b, c=0.0, d=1.0):
    node = n.new("ShaderNodeMapRange")
    node.inputs["From Min"].default_value, node.inputs["From Max"].default_value = a, b
    node.inputs["To Min"].default_value, node.inputs["To Max"].default_value = c, d
    l.new(socket, node.inputs["Value"])
    return node


def noise(n, l, vector, scale, detail=4.0, rough=.55):
    node = n.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = rough
    l.new(vector, node.inputs["Vector"])
    return node


def place_gltf(path, name, location, rot_z=0.0, lay_flat=False, keepout=True, scale=1.0, tilt=None):
    root, members = kit.import_prop(path, name, location, rot_z, scale=scale, tilt=tilt, lay_flat=lay_flat)
    record = kit.assert_clear(members, KEEPOUT, name) if keepout else {"label": name}
    record["location"] = [float(v) for v in location]
    return root, members, record


# ----------------------------------------------------------------------- scene parts
def strip_craft_desk():
    """Remove the craft-desk dressing of the base and mechanism builders (stationery, sketch, ruler, wall, desk, fill lights)."""
    removed = []
    root = bpy.data.objects.get("Scanned stationery common baseline")
    if root:
        removed.append(root.name)
        remove_tree(root)
    for obj in list(bpy.data.objects):
        if obj.name.startswith(STATIC_REMOVE):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    leftovers = [o.name for o in bpy.data.objects if o.type == "FONT"]
    if leftovers:
        raise RuntimeError("text objects left in the scene: " + ", ".join(leftovers))
    return len(removed)


def workbench():
    """Butcher-block maple top of 42 mm glued strips on pine legs; top surface at z=0."""
    bench = bpy.data.objects.new("Workbench", None)   # at the origin: its coordinates are world coordinates
    bpy.context.collection.objects.link(bench)
    maple = scanned("Workbench maple butcher block", PH / "white_maple_veneer", "white_maple_veneer",
                    rough_scale=.45, rough_add=.36, normal=.5)
    n, l = maple.node_tree.nodes, maple.node_tree.links
    bs = principled(maple)
    # Every strip is cut from a different board: per-object tone and warmth drift.
    info = n.new("ShaderNodeObjectInfo")
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (.47, .36, .25, 1)
    ramp.color_ramp.elements[1].color = (.76, .65, .51, 1)
    mid = ramp.color_ramp.elements.new(.45)
    mid.color = (.62, .50, .37, 1)
    l.new(info.outputs["Random"], ramp.inputs[0])
    tone = n.new("ShaderNodeMixRGB")
    tone.blend_type = "MULTIPLY"
    tone.inputs[0].default_value = 1
    l.new(bs.inputs["Base Color"].links[0].from_socket, tone.inputs[1])
    l.new(ramp.outputs[0], tone.inputs[2])
    # Years of use: oil and glue spots, darker toward the worked area.
    coord = n.new("ShaderNodeTexCoord")
    coord.object = bench
    stain_noise = n.new("ShaderNodeTexNoise")
    stain_noise.inputs["Scale"].default_value = 3.2
    stain_noise.inputs["Detail"].default_value = 9
    stain_noise.inputs["Roughness"].default_value = .62
    l.new(coord.outputs["Object"], stain_noise.inputs["Vector"])
    stain = n.new("ShaderNodeMapRange")
    stain.inputs["From Min"].default_value = .54
    stain.inputs["From Max"].default_value = .80
    stain.inputs["To Max"].default_value = .60
    l.new(stain_noise.outputs["Fac"], stain.inputs["Value"])
    dirty = n.new("ShaderNodeMixRGB")
    dirty.blend_type = "MULTIPLY"
    l.new(stain.outputs[0], dirty.inputs[0])
    l.new(tone.outputs[0], dirty.inputs[1])
    dirty.inputs[2].default_value = (.55, .44, .32, 1)
    l.new(dirty.outputs[0], bs.inputs["Base Color"])
    rough = bs.inputs["Roughness"].links[0].from_socket
    oily = n.new("ShaderNodeMath")
    oily.operation = "MULTIPLY_ADD"
    oily.use_clamp = True
    l.new(stain.outputs[0], oily.inputs[0])
    oily.inputs[1].default_value = -.30
    l.new(rough, oily.inputs[2])
    l.new(oily.outputs[0], bs.inputs["Roughness"])
    kit.add_surface_wear(maple, smudge=.12, grime=.16, scratch=.16, scale=.6)
    # Small dents and saw/knife nicks: sparse dark specks with a matching dip in the surface.
    nicks = n.new("ShaderNodeTexVoronoi")
    nicks.inputs["Scale"].default_value = 38
    nicks.inputs["Randomness"].default_value = 1
    l.new(coord.outputs["Object"], nicks.inputs["Vector"])
    nick = n.new("ShaderNodeMapRange")
    nick.inputs["From Min"].default_value, nick.inputs["From Max"].default_value = .035, .012
    l.new(nicks.outputs["Distance"], nick.inputs["Value"])
    dent = n.new("ShaderNodeBump")
    dent.invert = True
    dent.inputs["Strength"].default_value = .35
    dent.inputs["Distance"].default_value = .0004
    l.new(nick.outputs[0], dent.inputs["Height"])
    if bs.inputs["Normal"].is_linked:
        l.new(bs.inputs["Normal"].links[0].from_socket, dent.inputs["Normal"])
    l.new(dent.outputs[0], bs.inputs["Normal"])
    wear_marks(maple, coord.outputs["Object"])
    end = scanned("Workbench maple end grain", PH / "white_maple_veneer", "white_maple_veneer",
                  tint=(.74, .64, .52), rough_scale=.5, rough_add=.40, normal=.8)
    pine = scanned("Workbench pine frame", PH / "coated_pine", "coated_pine", tint=(.92, .88, .82),
                   rough_scale=.7, rough_add=.25, normal=.6)
    osb = scanned("Workbench shelf OSB", PH / "oriented_strand_board", "oriented_strand_board", rough_add=.2, normal=.6)
    (x0, x1), (y0, y1), t = BENCH['x'], BENCH['y'], BENCH['thickness']
    rng = random.Random(24)
    count = 18
    width = (y1 - y0) / count
    for i in range(count):
        lo, hi = (x0, y0 + i * width + .00012, -t), (x1, y0 + (i + 1) * width - .00012, 0.0)
        strip = box(f"Workbench strip {i:02d}", lo, hi, maple, .0008, .42, (rng.random(), rng.random()))
        strip.data.materials.append(end)
        for poly in strip.data.polygons:
            poly.material_index = 1 if abs(poly.normal.x) > .9 else 0
        strip.parent = bench
    glue = kit.diffuse("Workbench glue line", (.16, .12, .08), .7)
    box("Workbench glue layer", (x0 + .001, y0 + .001, -t + .002), (x1 - .001, y1 - .001, -.0007), glue).parent = bench
    for x in (x0 + .07, x1 - .07):
        for y in (y0 + .06, y1 - .06):
            box("Workbench leg", (x - .04, y - .04, BENCH['floor_z']), (x + .04, y + .04, -t), pine, .002, .5).parent = bench
        box("Workbench end rail", (x - .03, y0 + .06, -t - .09), (x + .03, y1 - .06, -t), pine, .002, .5).parent = bench
        box("Workbench low rail", (x - .03, y0 + .06, BENCH['floor_z'] + .10), (x + .03, y1 - .06, BENCH['floor_z'] + .17), pine, .002, .5).parent = bench
    for y in (y0 + .06, y1 - .06):
        box("Workbench apron", (x0 + .11, y - .015, -t - .09), (x1 - .11, y + .015, -t), pine, .002, .5).parent = bench
    box("Workbench lower shelf", (x0 + .03, y0 + .02, BENCH['floor_z'] + .17), (x1 - .03, y1 - .02, BENCH['floor_z'] + .188), osb, .001, 1.0).parent = bench
    bpy.context.view_layer.update()
    hit, point, _, _, obj, _ = bpy.context.scene.ray_cast(bpy.context.evaluated_depsgraph_get(), Vector((.45, .02, .05)), Vector((0, 0, -1)))
    assert hit and abs(point.z) < 1e-6 and obj.name.startswith("Workbench strip"), (hit, tuple(point), obj.name if obj else None)
    return {"strips": count, "strip_width_m": width, "top_z_m": 0.0, "size_m": [x1 - x0, y1 - y0, t], "probe": obj.name}


CUP_RINGS = (((.50, -.17), .041, 1.0), ((.535, -.145), .040, .45))   # (centre, radius, strength) in world metres


def wear_marks(mat, world):
    """Oil blotches, light and dark scratches in three directions, larger dents and two coffee-cup rings."""
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    color = bs.inputs["Base Color"].links[0].from_socket
    rough = bs.inputs["Roughness"].links[0].from_socket
    normal = bs.inputs["Normal"].links[0].from_socket
    # Oil: a few irregular dark, slightly glossier patches.
    oil = map_range(n, l, noise(n, l, world, 5.5, 8, .6).outputs["Fac"], .64, .74, 0, .75)
    dark = n.new("ShaderNodeMixRGB")
    dark.blend_type = "MULTIPLY"
    l.new(oil.outputs[0], dark.inputs[0])
    l.new(color, dark.inputs[1])
    dark.inputs[2].default_value = (.45, .35, .25, 1)
    color = dark.outputs[0]
    gloss = math_node(n, "MULTIPLY_ADD", None, -.25, True)
    l.new(oil.outputs[0], gloss.inputs[0])
    l.new(rough, gloss.inputs[2])
    rough = gloss.outputs[0]
    # Scratches: thin, long, of uneven depth; fresh ones pale, old ones filled with grime.
    for angle, light, scale in ((0.0, True, 16.0), (math.radians(38), False, 12.0), (math.radians(-61), True, 10.0)):
        m = n.new("ShaderNodeMapping")
        m.inputs["Rotation"].default_value = (0, 0, angle)
        m.inputs["Scale"].default_value = (1, 4, 1)
        l.new(world, m.inputs["Vector"])
        line = map_range(n, l, noise(n, l, m.outputs["Vector"], scale, 1, .5).outputs["Fac"], .47, .53, 0, 2)
        band = math_node(n, "PINGPONG", None, 1.0)
        l.new(line.outputs[0], band.inputs[0])
        depth = map_range(n, l, noise(n, l, world, 4.0, 2).outputs["Fac"], .58, .66, 0, 1)
        amount = math_node(n, "MULTIPLY", None, None, True)
        l.new(band.outputs[0], amount.inputs[0])
        l.new(depth.outputs[0], amount.inputs[1])
        mark = n.new("ShaderNodeMixRGB")
        mark.blend_type = "SCREEN" if light else "MULTIPLY"
        l.new(amount.outputs[0], mark.inputs[0])
        l.new(color, mark.inputs[1])
        mark.inputs[2].default_value = (.20, .15, .09, 1) if light else (.40, .32, .24, 1)
        color = mark.outputs[0]
        groove = n.new("ShaderNodeBump")
        groove.invert = True
        groove.inputs["Strength"].default_value = .25
        groove.inputs["Distance"].default_value = .0002
        l.new(amount.outputs[0], groove.inputs["Height"])
        l.new(normal, groove.inputs["Normal"])
        normal = groove.outputs[0]
    # A few larger dents (dropped tools), 2-4 mm across.
    v = n.new("ShaderNodeTexVoronoi")
    v.inputs["Scale"].default_value = 7.0
    l.new(world, v.inputs["Vector"])
    pit = map_range(n, l, v.outputs["Distance"], .022, .006, 0, 1)
    dip = n.new("ShaderNodeBump")
    dip.invert = True
    dip.inputs["Strength"].default_value = .6
    dip.inputs["Distance"].default_value = .0008
    l.new(pit.outputs[0], dip.inputs["Height"])
    l.new(normal, dip.inputs["Normal"])
    normal = dip.outputs[0]
    shade = n.new("ShaderNodeMixRGB")
    shade.blend_type = "MULTIPLY"
    pitdark = math_node(n, "MULTIPLY", None, .5)
    l.new(pit.outputs[0], pitdark.inputs[0])
    l.new(pitdark.outputs[0], shade.inputs[0])
    l.new(color, shade.inputs[1])
    shade.inputs[2].default_value = (.55, .45, .35, 1)
    color = shade.outputs[0]
    # Coffee-cup rings: darker at the rim, broken where the cup slid.
    for (cx, cy), radius, strength in CUP_RINGS:
        d = n.new("ShaderNodeVectorMath")
        d.operation = "DISTANCE"
        l.new(world, d.inputs[0])
        d.inputs[1].default_value = (cx, cy, 0)
        off = math_node(n, "SUBTRACT", None, radius)
        l.new(d.outputs["Value"], off.inputs[0])
        absd = math_node(n, "ABSOLUTE")
        l.new(off.outputs[0], absd.inputs[0])
        rim = map_range(n, l, absd.outputs[0], .0026, .0, 0, 1)
        inner = map_range(n, l, d.outputs["Value"], radius, radius - .006, 0, .25)
        both = math_node(n, "MAXIMUM")
        l.new(rim.outputs[0], both.inputs[0])
        l.new(inner.outputs[0], both.inputs[1])
        broken = map_range(n, l, noise(n, l, world, 60, 3).outputs["Fac"], .40, .62, .15, strength)
        ringmask = math_node(n, "MULTIPLY", None, None, True)
        l.new(both.outputs[0], ringmask.inputs[0])
        l.new(broken.outputs[0], ringmask.inputs[1])
        stain = n.new("ShaderNodeMixRGB")
        stain.blend_type = "MULTIPLY"
        l.new(ringmask.outputs[0], stain.inputs[0])
        l.new(color, stain.inputs[1])
        stain.inputs[2].default_value = (.52, .38, .26, 1)
        color = stain.outputs[0]
    l.new(color, bs.inputs["Base Color"])
    l.new(rough, bs.inputs["Roughness"])
    l.new(normal, bs.inputs["Normal"])


def block_wall_material(name, horizontal):
    """Painted concrete-block wall: 390 x 190 mm blocks in running bond with 10 mm tooled, recessed mortar
    joints; granular concrete face relief (Poly Haven granular_concrete) under two coats of off-white masonry paint."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    coord = n.new("ShaderNodeTexCoord")
    obj = coord.outputs["Object"]
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(obj, sep.inputs[0])
    plane = n.new("ShaderNodeCombineXYZ")
    l.new(sep.outputs[horizontal], plane.inputs["X"])
    l.new(sep.outputs["Z"], plane.inputs["Y"])
    brick = n.new("ShaderNodeTexBrick")
    brick.offset, brick.offset_frequency, brick.squash, brick.squash_frequency = .5, 2, 1.0, 2
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = .010
    brick.inputs["Mortar Smooth"].default_value = .35
    brick.inputs["Bias"].default_value = 0.0
    brick.inputs["Brick Width"].default_value = .40
    brick.inputs["Row Height"].default_value = .20
    brick.inputs["Color1"].default_value = (.735, .725, .69, 1)
    brick.inputs["Color2"].default_value = (.70, .69, .655, 1)
    brick.inputs["Mortar"].default_value = (.60, .59, .56, 1)
    l.new(plane.outputs[0], brick.inputs["Vector"])
    face = PH / "granular_concrete"
    nor = image_node(n, l, face / "granular_concrete_nor_gl_2k.jpg", obj, True, True)
    rgh = image_node(n, l, face / "granular_concrete_rough_2k.jpg", obj, True, True)
    dif = image_node(n, l, face / "granular_concrete_diff_2k.jpg", obj, False, True)
    # Paint hides the aggregate colour; what is left is a faint tonal echo and the relief.
    gray = n.new("ShaderNodeRGBToBW")
    l.new(dif.outputs["Color"], gray.inputs[0])
    echo = map_range(n, l, gray.outputs[0], .15, .65, .93, 1.03)
    mottle = map_range(n, l, noise(n, l, obj, 1.4, 6).outputs["Fac"], .35, .65, .95, 1.04)
    tone = math_node(n, "MULTIPLY")
    l.new(echo.outputs[0], tone.inputs[0])
    l.new(mottle.outputs[0], tone.inputs[1])
    paint = n.new("ShaderNodeVectorMath")
    paint.operation = "SCALE"
    l.new(brick.outputs["Color"], paint.inputs[0])
    l.new(tone.outputs[0], paint.inputs["Scale"])
    l.new(paint.outputs[0], bs.inputs["Base Color"])
    rough = map_range(n, l, rgh.outputs["Color"], 0, 1, .72, .92)
    l.new(rough.outputs[0], bs.inputs["Roughness"])
    nm = n.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = .8
    l.new(nor.outputs["Color"], nm.inputs["Color"])
    grain = n.new("ShaderNodeBump")   # roller stipple of the paint film
    grain.inputs["Strength"].default_value = .18
    grain.inputs["Distance"].default_value = .00015
    l.new(noise(n, l, obj, 650, 2).outputs["Fac"], grain.inputs["Height"])
    l.new(nm.outputs[0], grain.inputs["Normal"])
    joint = n.new("ShaderNodeBump")   # joints sit 3-4 mm behind the block face
    joint.invert = True
    joint.inputs["Strength"].default_value = 1.0
    joint.inputs["Distance"].default_value = .0035
    l.new(brick.outputs["Fac"], joint.inputs["Height"])
    l.new(grain.outputs[0], joint.inputs["Normal"])
    l.new(joint.outputs[0], bs.inputs["Normal"])
    return mat


def room():
    """Garage corner: painted concrete-block walls, concrete floor, a glazed window in the left wall."""
    win = (-1.25, .55, .12, 1.45, 1, 1)
    made = kit.daylight_room(-1.65, 2.6, -3.0, 1.21, BENCH['floor_z'], 2.2, win,
                             wall=(.70, .69, .66), ceiling=(.80, .80, .78), floor=(.36, .35, .33), mullion=.05, back_wall=True)
    block_x = block_wall_material("Painted concrete block wall (x run)", "X")
    block_y = block_wall_material("Painted concrete block wall (y run)", "Y")
    floor = scanned("Garage concrete floor", PH / "hangar_concrete_floor", "hangar_concrete_floor", period=3.0, rough_add=.15) \
        if any((PH / "hangar_concrete_floor").glob("hangar_concrete_floor_diff_*.jpg")) else None
    for obj in made:
        if obj.name.startswith(("Room back wall", "Room front wall")):
            obj.data.materials.clear()
            obj.data.materials.append(block_x)
        elif obj.name.startswith(("Window wall", "Room right wall")):
            obj.data.materials.clear()
            obj.data.materials.append(block_y)
        elif obj.name == "Room floor" and floor:
            obj.data.materials.clear()
            obj.data.materials.append(floor)
    frame = kit.diffuse("Window timber frame", (.78, .77, .73), .45)
    glass = bpy.data.materials.new("Window glass")
    glass.use_nodes = True
    g = principled(glass)
    g.inputs["Transmission Weight"].default_value = 1.0
    g.inputs["Roughness"].default_value = 0.0
    g.inputs["IOR"].default_value = 1.5
    y0, y1, z0, z1 = win[:4]
    kit.plain_box("Window pane", (-1.65 - .02, (y0 + y1) / 2, (z0 + z1) / 2), (.004, y1 - y0, z1 - z0), glass).visible_shadow = False
    for name, centre, size in (("Window sill", (-1.60, (y0 + y1) / 2, z0 - .02), (.14, y1 - y0 + .12, .04)),
                               ("Window frame head", (-1.64, (y0 + y1) / 2, z1 + .025), (.06, y1 - y0 + .10, .05)),
                               ("Window frame near", (-1.64, y0 - .025, (z0 + z1) / 2), (.06, .05, z1 - z0 + .10)),
                               ("Window frame far", (-1.64, y1 + .025, (z0 + z1) / 2), (.06, .05, z1 - z0 + .10))):
        kit.plain_box(name, centre, size, frame)
    portal = bpy.data.lights.new("Window light portal", "AREA")
    portal.shape = "RECTANGLE"
    portal.size, portal.size_y = z1 - z0, y1 - y0
    portal.cycles.is_portal = True
    pobj = bpy.data.objects.new("Window light portal", portal)
    bpy.context.collection.objects.link(pobj)
    pobj.location = (-1.60, (y0 + y1) / 2, (z0 + z1) / 2)
    pobj.rotation_euler = (0, math.radians(90), 0)  # area lights face -Z; +90 deg about Y turns them to +X, into the room
    return {"walls": "painted concrete block, 390 x 190 mm running bond, 10 mm recessed joints; face relief from granular_concrete", "floor": "hangar_concrete_floor" if floor else "plain",
            "window": {"wall_x_m": -1.65, "y_m": [y0, y1], "z_m": [z0, z1]}}


def tape_roll(xy):
    """A part-used roll of 48 mm crepe masking tape lying flat (modelled; no printing): cream crepe paper
    with creases across the width, slightly frayed grubby edges, wound layers and dust on the upper side,
    brown cardboard core."""
    h, r_out, r_in, r_core = .048, .050, .0395, .0372
    tape = bpy.data.materials.new("Masking tape crepe paper")
    tape.use_nodes = True
    n, l = tape.node_tree.nodes, tape.node_tree.links
    bs = principled(tape)
    coord = n.new("ShaderNodeTexCoord")
    obj = coord.outputs["Object"]
    geo = n.new("ShaderNodeNewGeometry")
    tnorm = n.new("ShaderNodeVectorTransform")
    tnorm.vector_type, tnorm.convert_from, tnorm.convert_to = "NORMAL", "WORLD", "OBJECT"
    l.new(geo.outputs["Normal"], tnorm.inputs["Vector"])
    nz = n.new("ShaderNodeSeparateXYZ")
    l.new(tnorm.outputs["Vector"], nz.inputs[0])
    absz = math_node(n, "ABSOLUTE")
    l.new(nz.outputs["Z"], absz.inputs[0])
    side = map_range(n, l, absz.outputs[0], .5, .8, 0, 1)      # 1 on the wound side faces
    top = map_range(n, l, nz.outputs["Z"], .5, .8, 0, 1)        # 1 on the upper side only
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(obj, sep.inputs[0])
    flat = n.new("ShaderNodeCombineXYZ")
    l.new(sep.outputs["X"], flat.inputs["X"])
    l.new(sep.outputs["Y"], flat.inputs["Y"])
    radius = n.new("ShaderNodeVectorMath")
    radius.operation = "LENGTH"
    l.new(flat.outputs[0], radius.inputs[0])
    # Wound layers: irregular 1-3 mm bands where the roll was wound at uneven tension.
    wobble = noise(n, l, obj, 90, 3)
    warp = math_node(n, "MULTIPLY", None, 7.0)
    l.new(wobble.outputs["Fac"], warp.inputs[0])
    phase = math_node(n, "MULTIPLY_ADD", None, 2 * math.pi / .0028)
    l.new(radius.outputs["Value"], phase.inputs[0])
    l.new(warp.outputs[0], phase.inputs[2])
    sine = math_node(n, "SINE")
    l.new(phase.outputs[0], sine.inputs[0])
    layers = map_range(n, l, sine.outputs[0], -1, 1, .80, 1.0)
    layer_side = n.new("ShaderNodeMix")
    layer_side.data_type = "FLOAT"
    l.new(side.outputs[0], layer_side.inputs["Factor"])
    layer_side.inputs["A"].default_value = 1.0
    l.new(layers.outputs[0], layer_side.inputs["B"])
    # Crepe creases run across the tape (parallel to the roll axis) on the outer face.
    crease_space = n.new("ShaderNodeMapping")
    crease_space.inputs["Scale"].default_value = (1, 1, .06)
    l.new(obj, crease_space.inputs["Vector"])
    crepe = noise(n, l, crease_space.outputs["Vector"], 900, 3, .6)
    # Frayed, slightly grubby edges: the last ~1.5 mm of each edge, broken up.
    zc = math_node(n, "SUBTRACT", None, h / 2)
    l.new(sep.outputs["Z"], zc.inputs[0])
    zabs = math_node(n, "ABSOLUTE")
    l.new(zc.outputs[0], zabs.inputs[0])
    edge = map_range(n, l, zabs.outputs[0], h / 2 - .0018, h / 2 - .0002, 0, 1)
    fray = map_range(n, l, noise(n, l, obj, 260, 4).outputs["Fac"], .35, .65, .3, 1)
    edgy = math_node(n, "MULTIPLY", None, None, True)
    l.new(edge.outputs[0], edgy.inputs[0])
    l.new(fray.outputs[0], edgy.inputs[1])
    # Colour: cream-tan crepe, darker grubby edges, dust settled on the upper side.
    tone = map_range(n, l, noise(n, l, obj, 40, 6).outputs["Fac"], .3, .7, .84, 1.06)
    shade = math_node(n, "MULTIPLY")
    l.new(tone.outputs[0], shade.inputs[0])
    l.new(layer_side.outputs["Result"], shade.inputs[1])
    paper = n.new("ShaderNodeVectorMath")
    paper.operation = "SCALE"
    paper.inputs[0].default_value = (.58, .45, .25)
    l.new(shade.outputs[0], paper.inputs["Scale"])
    grubby = n.new("ShaderNodeMixRGB")
    grubby.blend_type = "MULTIPLY"
    edge_amount = math_node(n, "MULTIPLY", None, .7)
    l.new(edgy.outputs[0], edge_amount.inputs[0])
    l.new(edge_amount.outputs[0], grubby.inputs[0])
    l.new(paper.outputs[0], grubby.inputs[1])
    grubby.inputs[2].default_value = (.48, .42, .34, 1)
    dust_noise = map_range(n, l, noise(n, l, obj, 140, 5).outputs["Fac"], .38, .68, .25, .75)
    dust = math_node(n, "MULTIPLY", None, None, True)
    l.new(dust_noise.outputs[0], dust.inputs[0])
    l.new(top.outputs[0], dust.inputs[1])
    dusty = n.new("ShaderNodeMixRGB")
    l.new(dust.outputs[0], dusty.inputs[0])
    l.new(grubby.outputs[0], dusty.inputs[1])
    dusty.inputs[2].default_value = (.56, .54, .50, 1)
    l.new(dusty.outputs[0], bs.inputs["Base Color"])
    rough = math_node(n, "MULTIPLY_ADD", None, .12, True)
    l.new(dust.outputs[0], rough.inputs[0])
    rough.inputs[2].default_value = .80
    l.new(rough.outputs[0], bs.inputs["Roughness"])
    relief = n.new("ShaderNodeMix")   # creases on the outer face, wound layers on the sides
    relief.data_type = "FLOAT"
    l.new(side.outputs[0], relief.inputs["Factor"])
    l.new(crepe.outputs["Fac"], relief.inputs["A"])
    l.new(layers.outputs[0], relief.inputs["B"])
    b1 = n.new("ShaderNodeBump")
    b1.inputs["Strength"].default_value = .8
    b1.inputs["Distance"].default_value = .0004
    l.new(relief.outputs["Result"], b1.inputs["Height"])
    b2 = n.new("ShaderNodeBump")
    b2.inputs["Strength"].default_value = .5
    b2.inputs["Distance"].default_value = .0003
    l.new(edgy.outputs[0], b2.inputs["Height"])
    l.new(b1.outputs[0], b2.inputs["Normal"])
    l.new(b2.outputs[0], bs.inputs["Normal"])
    card = bpy.data.materials.new("Tape cardboard core")
    card.use_nodes = True
    cn, cl = card.node_tree.nodes, card.node_tree.links
    cb = principled(card)
    cb.inputs["Roughness"].default_value = .9
    ccoord = cn.new("ShaderNodeTexCoord")
    fib = map_range(cn, cl, noise(cn, cl, ccoord.outputs["Object"], 300, 6).outputs["Fac"], .3, .7, .80, 1.08)
    cardc = cn.new("ShaderNodeVectorMath")
    cardc.operation = "SCALE"
    cardc.inputs[0].default_value = (.27, .18, .105)
    cl.new(fib.outputs[0], cardc.inputs["Scale"])
    cl.new(cardc.outputs[0], cb.inputs["Base Color"])
    x, y = xy
    roll = ring("ADD endpoint roll of tape", (x, y, 0), r_in, r_out, h, tape)
    core = ring("ADD endpoint roll of tape core", (x, y, 0), r_core, r_in + .0002, h + .0004, card)
    return [roll, core]


def pencil(xy, angle):
    """Unpainted cedar carpenter's pencil, flat section, graphite at the sharpened end."""
    cedar = kit.diffuse("Carpenter pencil cedar", (.62, .40, .24), .55)
    lead = kit.diffuse("Pencil graphite", (.05, .05, .055), .35)
    holder = bpy.data.objects.new("Carpenter pencil", None)
    bpy.context.collection.objects.link(holder)
    body = box("Carpenter pencil body", (-.0825, -.0062, 0), (.0825, .0062, .0072), cedar, .0012)
    tip = box("Carpenter pencil lead", (.0825, -.0016, .0026), (.0915, .0016, .0046), lead, .0004)
    for part in (body, tip):
        part.parent = holder
    holder.location = (*xy, 0)
    holder.rotation_euler = (0, 0, angle)
    bpy.context.view_layer.update()
    return [body, tip]


def natural_bowl(mat):
    """The scan's lacquered orange turned into used, oiled natural wood: less saturation, visible grain, wear."""
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    hsv = n.new("ShaderNodeHueSaturation")
    hsv.inputs["Hue"].default_value = .515
    hsv.inputs["Saturation"].default_value = .72
    hsv.inputs["Value"].default_value = .78
    if bs.inputs["Base Color"].is_linked:
        l.new(bs.inputs["Base Color"].links[0].from_socket, hsv.inputs["Color"])
    else:
        hsv.inputs["Color"].default_value = bs.inputs["Base Color"].default_value
    coord = n.new("ShaderNodeTexCoord")
    grain_space = n.new("ShaderNodeMapping")
    grain_space.inputs["Scale"].default_value = (5, 5, 5)
    l.new(coord.outputs["Object"], grain_space.inputs["Vector"])
    grain = image_node(n, l, PH / "white_maple_veneer/white_maple_veneer_diff_2k.jpg", grain_space.outputs["Vector"], False, True)
    gray = n.new("ShaderNodeRGBToBW")
    l.new(grain.outputs["Color"], gray.inputs[0])
    figure = map_range(n, l, gray.outputs[0], .35, .75, .70, 1.12)
    wood = n.new("ShaderNodeVectorMath")
    wood.operation = "SCALE"
    l.new(hsv.outputs["Color"], wood.inputs[0])
    l.new(figure.outputs[0], wood.inputs["Scale"])
    l.new(wood.outputs[0], bs.inputs["Base Color"])
    if not bs.inputs["Roughness"].is_linked:
        bs.inputs["Roughness"].default_value = max(.55, bs.inputs["Roughness"].default_value)
    kit.add_surface_wear(mat, smudge=.10, grime=.16, scratch=.10, scale=.18)


def dress():
    audit = []
    ends = edit_vocab.ADD_ENDPOINTS
    _, bowl, rec = place_gltf(PH / "wooden_bowl_02/wooden_bowl_02_2k.gltf", "ADD endpoint wooden bowl", (*ends['bowl']['xy_m'], 0), .6)
    for mat in {m for o in bowl if o.type == "MESH" for m in o.data.materials}:
        natural_bowl(mat)
    tape = tape_roll(ends['tape']['xy_m'])
    trec = kit.assert_clear(tape, KEEPOUT, "ADD endpoint roll of tape")
    for record, members in ((rec, bowl), (trec, tape)):
        low, high = kit.world_bbox(members)
        record["plan_centre_m"] = [(low.x + high.x) / 2, (low.y + high.y) / 2]
        audit.append(record)
    mid = [(audit[0]["plan_centre_m"][i] + audit[1]["plan_centre_m"][i]) / 2 for i in (0, 1)]
    assert abs(mid[0] - .31) < .002 and abs(mid[1]) < .002, mid
    for path, name, loc, rot, flat in (
            (PH / "flathead_screwdriver/flathead_screwdriver_2k.gltf", "Dressing screwdriver", (-.02, -.31, 0), 35, True),
            (PH / "wooden_hammer_01/wooden_hammer_01_2k.gltf", "Dressing hammer", (.55, .28, 0), 85, True),
            (OWN / "pliers/pliers_2k.gltf", "Dressing pliers", (.47, -.44, 0), 29, True),
            (OWN / "adjustable_wrench/adjustable_wrench_2k.gltf", "Dressing wrench", (.13, -.48, 0), 149, True)):
        _, _, record = place_gltf(path, name, loc, math.radians(rot), lay_flat=flat)
        audit.append(record)
    audit.append(kit.assert_clear(pencil((.25, .17), math.radians(-12)), KEEPOUT, "carpenter pencil"))
    # Background: steel-frame shelving and a tall plant against the back wall.
    place_gltf(PH / "steel_frame_shelves_02/steel_frame_shelves_02_2k.gltf", "Back shelving", (.30, .95, BENCH['floor_z']), 0.0, keepout=False)
    levels = sorted({round(kit.surface_z(.30, .95, start=s, ignore=("Shelf item",)), 4) for s in (1.5, .9, .5, .2, -.1)})
    visible = [z for z in levels if -.25 < z < .25]
    if visible:
        place_gltf(PH / "metal_toolbox/metal_toolbox_2k.gltf", "Shelf item toolbox", (.30, .98, visible[0]), math.pi, keepout=False)
    if len(visible) > 1:
        place_gltf(next((PH / "wicker_basket_02").glob("*.gltf")), "Shelf item basket", (.28, .96, visible[1]), .15, keepout=False)
    place_gltf(OWN / "potted_plant_01/potted_plant_01_2k.gltf", "Background plant", (-.66, .96, BENCH['floor_z']), .9, keepout=False)
    kit.sawdust("Sawdust in the back-left corner", [(-.62, .22, -.38, .375, 5), (-.62, .10, -.45, .22, 2)], 2600,
                ((-.34, -.085), (.72, .085)), color=(.78, .66, .47), seed=11, size=(.0005, .0022))
    kit.sawdust("Sawdust along the back edge", [(-.30, .30, .75, .375, 3), (.62, .10, .78, .375, 2)], 1600,
                ((-.34, -.085), (.72, .085)), color=(.74, .62, .44), seed=12, size=(.0005, .0020))
    kit.sawdust("Sawdust round the board feet", [(-.34, -.20, .15, -.14, 2), (-.34, .14, .15, .20, 2), (.40, -.38, .78, -.28, 1)], 1400,
                ((-.34, -.085), (.72, .085)), color=(.80, .69, .50), seed=13, size=(.0004, .0018))
    return {"props": audit, "add_endpoint_midpoint_m": mid, "shelf_levels_m": levels}


def overhead_batten():
    """Ceiling-mounted 1.2 m LED batten over the bench: white steel housing, opal diffuser that emits."""
    housing = kit.diffuse("Batten white steel housing", (.82, .82, .80), .45)
    diffuser = bpy.data.materials.new("Batten opal diffuser")
    diffuser.use_nodes = True
    bs = principled(diffuser)
    bs.inputs["Base Color"].default_value = (.9, .9, .9, 1)
    bs.inputs["Emission Color"].default_value = (1.0, .93, .84, 1)   # 3500 K
    bs.inputs["Emission Strength"].default_value = 28.0
    z = 2.2
    x0, x1, y = -.35, .85, .05
    box("Ceiling batten housing", (x0, y - .035, z - .045), (x1, y + .035, z), housing, .003)
    tube = box("Ceiling batten diffuser", (x0 + .02, y - .028, z - .062), (x1 - .02, y + .028, z - .045), diffuser, .006)
    box("Ceiling batten end caps", (x0 - .01, y - .036, z - .05), (x0 + .02, y + .036, z), housing, .002)
    box("Ceiling batten end caps", (x1 - .02, y - .036, z - .05), (x1 + .01, y + .036, z), housing, .002)
    return {"x_m": [x0, x1], "y_m": y, "z_m": z, "emission_strength": 28.0, "color": "3500 K"}


def materials():
    for mat in bpy.data.materials:
        if mat.name.startswith(("Mechanism scanned plywood", "Scanned plywood")):
            bs = principled(mat)
            if bs.inputs["Base Color"].is_linked:  # aged birch ply, a shade darker and warmer than the new maple
                n, l = mat.node_tree.nodes, mat.node_tree.links
                age = n.new("ShaderNodeMixRGB")
                age.blend_type = "MULTIPLY"
                age.inputs[0].default_value = 1
                age.inputs[2].default_value = (.80, .70, .56, 1)
                l.new(bs.inputs["Base Color"].links[0].from_socket, age.inputs[1])
                l.new(age.outputs[0], bs.inputs["Base Color"])
            kit.add_surface_wear(mat, smudge=.08, grime=.10, scratch=.06, scale=.25)


def light(scene):
    world = bpy.data.worlds.new("Partly cloudy sky through the window")
    world.use_nodes = True
    n, l = world.node_tree.nodes, world.node_tree.links
    n.clear()
    env = n.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(PH / "kloofendal_48d_partly_cloudy_puresky/kloofendal_48d_partly_cloudy_puresky_2k.hdr"))
    bg = n.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    out = n.new("ShaderNodeOutputWorld")
    l.new(env.outputs["Color"], bg.inputs["Color"])
    l.new(bg.outputs[0], out.inputs[0])
    scene.world = world
    kit.sun("Afternoon sun", (.82, .32, -.47), 4.5, angle_deg=.53, color=(1.0, .94, .86))
    batten = overhead_batten()
    scene.cycles.max_bounces = 10
    scene.cycles.diffuse_bounces = 6
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 6
    scene.cycles.sample_clamp_indirect = 6.0
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Base Contrast"
    scene.view_settings.exposure = .3
    kit.lens_finish(scene, vignette=.16)
    return {"sun_direction": [.82, .32, -.47], "sun_strength": 4.5, "sky": "kloofendal_48d_partly_cloudy_puresky 2k",
            "overhead_batten": batten}


def camera(scene):
    location, target, lens = CAMERA
    cam = scene.camera
    cam.location = location
    base.aim(cam, target)
    cam.data.lens = lens
    cam.data.sensor_width = 36
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = (cam.location - Vector(FOCUS)).length
    cam.data.dof.aperture_fstop = 5.6
    bpy.context.view_layer.update()
    return {"location": list(location), "target": list(target), "lens_mm": lens, "sensor_width_mm": 36,
            "focus_m": list(FOCUS), "fstop": 5.6, "matrix_world": [list(r) for r in cam.matrix_world]}


def render_settings(scene, samples, device):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = .01
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.denoising_prefilter = "ACCURATE"
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = .25
    scene.render.use_persistent_data = False  # required with motion blur (Blender 4.3)
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    if device == "cpu":
        scene.cycles.device = "CPU"
        return "CPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = device.upper()
    prefs.get_devices()
    for dev in prefs.devices:
        dev.use = dev.type == device.upper()
    if not any(dev.use for dev in prefs.devices):
        raise RuntimeError(f"no {device.upper()} device visible")
    scene.cycles.device = "GPU"
    return f"{device.upper()} " + ", ".join(dev.name for dev in prefs.devices if dev.use)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case", default="source", choices=list(CASES))
    p.add_argument("--native", type=Path, default=NATIVE)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", nargs="+", type=int, default=list(range(1, FRAMES + 1)))
    p.add_argument("--samples", type=int, default=256)
    p.add_argument("--device", choices=("optix", "cuda", "cpu"), default="optix")
    p.add_argument("--no-blend", action="store_true", help="do not save scene.blend (preview renders)")
    p.add_argument("--blend-only", action="store_true", help="build and save scene.blend, render nothing")
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    folder = args.native / args.case
    c = load_physics(folder / "resolved_physics.json")
    states, motion = np.load(folder / "states.npz"), np.load(folder / "motion_states.npz")
    contract = mech.build(c, states, motion)
    removed = strip_craft_desk()
    bench = workbench()
    shell = room()
    materials()
    dressing = dress()
    scene = bpy.context.scene
    lights = light(scene)
    cam = camera(scene)
    device = render_settings(scene, args.samples, "cpu" if args.blend_only else args.device)
    out = args.out
    (out / "frames").mkdir(parents=True, exist_ok=True)
    report = {
        "look": LOOK, "case": args.case, "host": platform.node(), "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
        "device": device, "blender": bpy.app.version_string, "samples": args.samples, "adaptive_threshold": .01,
        "denoiser": "OpenImageDenoise", "motion_blur_shutter_frames": .25, "persistent_data": False,
        "view_transform": "AgX - Base Contrast", "exposure": scene.view_settings.exposure,
        "resolution": [WIDTH, HEIGHT], "fps": FPS, "camera": cam, "lighting": lights, "room": shell, "workbench": bench,
        "dressing": dressing, "removed_craft_desk_objects": removed, "mechanism_geometry_audit": contract["geometry_audit"],
        "states_sha256": sha(folder / "states.npz"), "motion_states_sha256": sha(folder / "motion_states.npz"),
        "resolved_physics_sha256": sha(folder / "resolved_physics.json"),
        "status": "rendering",
    }
    save(out / "render_report.json", report)
    if not args.no_blend:
        scene.frame_set(1)
        bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"), relative_remap=True, compress=True)
    if args.blend_only:
        return
    names = list(states["body_names"])
    for f in args.frames:
        scene.frame_set(f)
        for i, name in enumerate(names):
            placed = np.array(bpy.data.objects[name].matrix_world.translation)
            expected = states["positions"][f - 1, i] + (np.array([-.001, 0, 0]) if name == "pusher" else 0)
            if np.abs(placed - expected).max() > 1e-5:
                raise RuntimeError(f"{name} moved at frame {f}: {placed} vs {expected}")
        scene.render.filepath = str(out / "frames" / f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("LOOK_FRAME", args.case, f, flush=True)
    report["status"] = "frames_rendered"
    report["frames_rendered"] = list(args.frames)
    save(out / "render_report.json", report)


if __name__ == "__main__":
    main()
