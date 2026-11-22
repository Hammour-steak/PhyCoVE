"""Current look of gym_landing_mat: a school gym with a maple sports floor.

`render_replay.py` (the renderer of the accepted delivery) runs with one overlay hook,
called right after it records the camera and every static
matrix, so the native states, the camera and the per-frame static-matrix assertions stay
those of the accepted delivery. The hook only restyles materials, lights and static
dressing; no solver state, collision shape or edit parameter is read or written.

    CUDA_VISIBLE_DEVICES=<GPU-uuid> blender -b --python-exit-code 1 --python realism.py -- \
        --scene <packed/<case>.blend> --reference-main <main dir> --simulation <simulation dir> --out OUT \
        [--still-frame 31] [--samples 192]
"""
from pathlib import Path
import math
import os
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parents[2])]
import pcve_realism_kit as kit
from pcve_assets import asset

FLOOR_TEX = asset("polyhaven/white_maple_veneer")  # CC0 scan, 1.0 x 1.0 m, grain along image x
VINYL_TEX = asset("polyhaven/leather_white")    # CC0 scan, 0.3 x 0.3 m tile, used for its grain only
# Mat (1.22 x 0.82 m), medicine ball and the add_path_obstacle bottle over every case and frame.
KEEPOUT = ((-.80, -.62, -.01), (.95, .62, .90))
FLOOR = "Photographic rectangular parquet / Poly Haven CC0"
COVER = "gym_landing_mat | actual physical surface"
LINE_PREFIXES = ("Basketball sideline", "Basketball baseline", "Basketball far lane", "Basketball far free throw",
                 "Basketball center circle")


def env(name, default):
    return float(os.environ.get("REALISM_" + name, default))


def in_frame(scene, objects, margin=.02):
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    pts = [world_to_camera_view(scene, scene.camera, o.matrix_world @ Vector(c)) for o in objects if o.type == "MESH" for c in o.bound_box]
    box = (min(q.x for q in pts), max(q.x for q in pts), min(q.y for q in pts), max(q.y for q in pts))
    return box, box[0] >= margin and box[1] <= 1 - margin and box[2] >= margin and box[3] <= 1 - margin


def _nodes(mat):
    return mat.node_tree.nodes, mat.node_tree.links


def _image(nodes, links, path, vector, data=True):
    import bpy
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(path), check_existing=True)
    if data:
        tex.image.colorspace_settings.name = "Non-Color"
    links.new(vector, tex.inputs["Vector"])
    return tex


def _math(nodes, links, op, *values):
    """Math node; each value is a number or an output socket (inputs in order)."""
    node = nodes.new("ShaderNodeMath")
    node.operation = op
    for i, v in enumerate(values):
        if isinstance(v, (int, float)):
            node.inputs[i].default_value = v
        else:
            links.new(v, node.inputs[i])
    return node.outputs[0]


def _range(nodes, links, value, f0, f1, t0, t1):
    node = nodes.new("ShaderNodeMapRange")
    node.inputs["From Min"].default_value, node.inputs["From Max"].default_value = f0, f1
    node.inputs["To Min"].default_value, node.inputs["To Max"].default_value = t0, t1
    links.new(value, node.inputs["Value"])
    return node.outputs[0]


def _noise(nodes, links, vector, scale, detail=4.0, rough=.5):
    node = nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = rough
    links.new(vector, node.inputs["Vector"])
    return node.outputs["Fac"]


def fresh(name):
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat, next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _hash(nodes, links, vector):
    """Per-cell random value and colour from a White Noise texture."""
    node = nodes.new("ShaderNodeTexWhiteNoise")
    node.noise_dimensions = "3D"
    links.new(vector, node.inputs["Vector"])
    return node.outputs["Value"], node.outputs["Color"]


def _combine(nodes, links, x, y, z):
    node = nodes.new("ShaderNodeCombineXYZ")
    for i, v in enumerate((x, y, z)):
        if isinstance(v, (int, float)):
            node.inputs[i].default_value = v
        else:
            links.new(v, node.inputs[i])
    return node.outputs[0]


def maple_floor():
    """Maple strip sports floor: 57 mm boards of random length laid along the court, each cut from a
    different part of a scanned maple veneer, under a satin polyurethane coat with traffic wear."""
    mat, bs = fresh("Maple strip sports floor / Poly Haven white_maple_veneer CC0")
    n, l = _nodes(mat)
    obj = n.new("ShaderNodeTexCoord").outputs["Object"]
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(obj, sep.inputs[0])
    width = env("BOARD_W", .057)
    # Strips across x, boards along y (the court's length).
    sx = _math(n, l, "DIVIDE", sep.outputs["X"], width)
    strip_id = _math(n, l, "FLOOR", sx)
    across = _math(n, l, "FRACT", sx)
    strip_rand, _ = _hash(n, l, _combine(n, l, strip_id, 17.3, 0.0))
    # Board ends: a 1-D Voronoi along each strip gives boards of random length (mean ~1.1 m).
    along = _math(n, l, "MULTIPLY_ADD", strip_rand, 97.0, sep.outputs["Y"])
    cells = n.new("ShaderNodeTexVoronoi")
    cells.voronoi_dimensions = "1D"
    cells.inputs["Scale"].default_value = 1 / env("BOARD_L", 1.1)
    cells.inputs["Randomness"].default_value = .85
    l.new(along, cells.inputs["W"])
    ends = n.new("ShaderNodeTexVoronoi")
    ends.voronoi_dimensions = "1D"
    ends.feature = "DISTANCE_TO_EDGE"
    ends.inputs["Scale"].default_value = 1 / env("BOARD_L", 1.1)
    ends.inputs["Randomness"].default_value = .85
    l.new(along, ends.inputs["W"])
    board_rand, board_col = _hash(n, l, _combine(n, l, strip_id, cells.outputs["W"], 3.1))
    # Veneer coordinates: grain (image x) along the board, each board shifted to its own patch.
    off = n.new("ShaderNodeVectorMath")
    off.operation = "MULTIPLY_ADD"
    off.inputs[1].default_value = (7.31, 5.17, 0.0)
    l.new(board_col, off.inputs[0])
    l.new(_combine(n, l, sep.outputs["Y"], sep.outputs["X"], 0.0), off.inputs[2])
    uv = off.outputs[0]
    diff = _image(n, l, FLOOR_TEX / "white_maple_veneer_diff_2k.jpg", uv, data=False)
    rough = _image(n, l, FLOOR_TEX / "white_maple_veneer_rough_2k.jpg", uv)
    nor = _image(n, l, FLOOR_TEX / "white_maple_veneer_nor_gl_2k.jpg", uv)
    # Finished maple: amber under the coat, board-to-board tone spread, a few darker heartwood boards.
    amber = n.new("ShaderNodeMixRGB")
    amber.blend_type = "MULTIPLY"
    amber.inputs[0].default_value = 1.0
    amber.inputs[2].default_value = (*(float(v) for v in os.environ.get("REALISM_FLOOR_TINT", ".95,.72,.48").split(",")), 1)
    grain_c = n.new("ShaderNodeBrightContrast")
    grain_c.inputs["Contrast"].default_value = env("GRAIN_CONTRAST", .4)
    l.new(diff.outputs["Color"], grain_c.inputs["Color"])
    l.new(grain_c.outputs["Color"], amber.inputs[1])
    heart = n.new("ShaderNodeMixRGB")
    heart.blend_type = "MULTIPLY"
    heart.inputs[2].default_value = (.90, .80, .68, 1)
    l.new(_range(n, l, board_rand, .93, .99, 0., 1.), heart.inputs[0])
    l.new(amber.outputs[0], heart.inputs[1])
    spread = _range(n, l, board_rand, 0., 1., env("BOARD_TONE0", .92), env("BOARD_TONE1", 1.02))
    broad = _range(n, l, _noise(n, l, obj, .35, 3.0), .3, .7, .94, 1.04)
    tone = n.new("ShaderNodeVectorMath")
    tone.operation = "SCALE"
    l.new(heart.outputs[0], tone.inputs[0])
    l.new(_math(n, l, "MULTIPLY", spread, broad), tone.inputs["Scale"])
    # Joints: hairline gaps along every strip and at the board ends, darkened by dirt.
    side = _range(n, l, _math(n, l, "MINIMUM", across, _math(n, l, "SUBTRACT", 1.0, across)), 0., .012, 1., 0.)
    end = _range(n, l, ends.outputs["Distance"], 0., .0006 / env("BOARD_L", 1.1), 1., 0.)
    joint = _math(n, l, "MAXIMUM", side, end)
    dirty = n.new("ShaderNodeMixRGB")
    dirty.inputs[2].default_value = (.10, .07, .045, 1)
    l.new(_math(n, l, "MULTIPLY", joint, env("JOINT_DARK", .6)), dirty.inputs[0])
    l.new(tone.outputs[0], dirty.inputs[1])
    # Sparse black sneaker-rubber scuffs: short streaks from a stretched, warped noise, mostly absent.
    warp = n.new("ShaderNodeVectorMath")
    warp.operation = "MULTIPLY_ADD"
    warp.inputs[1].default_value = (.4, .4, .4)
    l.new(n.new("ShaderNodeTexNoise").outputs["Color"], warp.inputs[0])
    l.new(obj, warp.inputs[2])
    stretch = n.new("ShaderNodeVectorMath")
    stretch.operation = "MULTIPLY"
    stretch.inputs[1].default_value = (2.5, 11.0, 1.0)
    l.new(warp.outputs[0], stretch.inputs[0])
    marks = _range(n, l, _noise(n, l, stretch.outputs[0], 2.4, 3.0), .73, .78, 0., env("SCUFF", .45))
    scuff = n.new("ShaderNodeMixRGB")
    scuff.inputs[2].default_value = (.03, .028, .026, 1)
    l.new(marks, scuff.inputs[0])
    l.new(dirty.outputs[0], scuff.inputs[1])
    l.new(scuff.outputs[0], bs.inputs["Base Color"])
    # Wood under the coat: scanned roughness in a satin range; grain and joints in the base normal.
    l.new(_range(n, l, rough.outputs["Color"], 0, 1, .32, .55), bs.inputs["Roughness"])
    nmap = n.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = .35
    l.new(nor.outputs["Color"], nmap.inputs["Color"])
    groove = n.new("ShaderNodeBump")
    groove.inputs["Strength"].default_value = .6
    groove.inputs["Distance"].default_value = .0003
    l.new(_math(n, l, "MULTIPLY", joint, -1.0), groove.inputs["Height"])
    l.new(nmap.outputs["Normal"], groove.inputs["Normal"])
    l.new(groove.outputs["Normal"], bs.inputs["Normal"])
    # Polyurethane coat: glossy, duller where people walk (broad smudges), faint swirl marks.
    bs.inputs["Coat Weight"].default_value = env("COAT", 1.0)
    bs.inputs["Coat IOR"].default_value = 1.5
    traffic = _range(n, l, _noise(n, l, obj, .9, 5.0, .55), .35, .7, 0., 1.)
    swirl = _range(n, l, _noise(n, l, obj, 9.0, 6.0, .6), .45, .6, 0., 1.)
    coat_rough = _math(n, l, "MULTIPLY_ADD", traffic, env("COAT_WEAR", .10), env("COAT_ROUGH", .06))
    coat_rough = _math(n, l, "MULTIPLY_ADD", swirl, .025, coat_rough)
    l.new(coat_rough, bs.inputs["Coat Roughness"])
    # The coat follows the boards: each board sits a few hundredths of a millimetre proud or low,
    # with slight cupping, plus orange peel, so reflections break at the joints as on a real floor.
    level = _math(n, l, "MULTIPLY_ADD", board_rand, .6, _math(n, l, "MULTIPLY", _math(n, l, "SINE", _math(n, l, "MULTIPLY", across, 3.14159)), .5))
    peel = _math(n, l, "MULTIPLY_ADD", _noise(n, l, obj, 45.0, 2.0), .35, level)
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = env("COAT_BUMP", .25)
    bump.inputs["Distance"].default_value = .0002
    l.new(peel, bump.inputs["Height"])
    l.new(bump.outputs["Normal"], bs.inputs["Coat Normal"])
    return mat, coat_rough


def line_paint(name, color, coat_rough_like=.08):
    """Court-line paint sealed under the same floor coat."""
    mat, bs = fresh(name)
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = .45
    bs.inputs["Coat Weight"].default_value = env("COAT", 1.0)
    bs.inputs["Coat Roughness"].default_value = coat_rough_like
    kit.add_surface_wear(mat, smudge=.05, grime=.08, scratch=.03, scale=1.5)
    return mat


def strip(name, x0, y0, x1, y1, width, z, mat):
    """Flat painted line between two floor points."""
    import bpy
    import bmesh
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    nx, ny = -dy / length * width / 2, dx / length * width / 2
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in ((x0 + nx, y0 + ny, z), (x0 - nx, y0 - ny, z), (x1 - nx, y1 - ny, z), (x1 + nx, y1 + ny, z))]
    bm.faces.new(vs)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(mat)
    return obj


def vinyl_cover(name, color, seams=None):
    """18 oz vinyl-coated polyester: fine embossed grain, satin sheen with irregular gloss, handling grime.

    Grain uses the cover's metre UVs. Everything that has to stay on the cloth while it deforms
    (seams, corner creases, gloss and grime patches) is placed in the cover's rest coordinates,
    read from the "rest" point attribute (the native cloth_rest_positions). `seams` = (z_top, z_bottom)
    rest heights of the two stitched seams on the side walls; None for the separate edge binding.
    """
    mat, bs = fresh(name)
    n, l = _nodes(mat)
    uvn = n.new("ShaderNodeUVMap")
    uvn.uv_map = "MaterialMeters"
    scale = n.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs["Scale"].default_value = 1 / env("VINYL_TILE", .16)
    l.new(uvn.outputs["UV"], scale.inputs[0])
    uv = scale.outputs[0]
    rough = _image(n, l, VINYL_TEX / "leather_white_rough_2k.jpg", uv)
    nor = _image(n, l, VINYL_TEX / "leather_white_nor_gl_2k.jpg", uv)
    grain = _image(n, l, VINYL_TEX / "leather_white_diff_2k.jpg", uv)
    if seams:
        attr = n.new("ShaderNodeAttribute")
        attr.attribute_type = "GEOMETRY"
        attr.attribute_name = "rest"
        rest = attr.outputs["Vector"]
    else:
        rest = n.new("ShaderNodeTexCoord").outputs["Object"]
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(rest, sep.inputs[0])
    # Tone: scanned grain modulates the dye a few percent; broad grime, darker towards the floor edge.
    bw = n.new("ShaderNodeRGBToBW")
    l.new(grain.outputs["Color"], bw.inputs["Color"])
    mod = _range(n, l, bw.outputs["Val"], .55, .9, .9, 1.05)
    dirt = _range(n, l, _noise(n, l, rest, 3.0, 6.0, .6), .35, .75, .84, 1.04)
    smear = _range(n, l, _noise(n, l, rest, 11.0, 4.0, .55), .55, .7, 1.0, .93)
    low = _range(n, l, sep.outputs["Z"], .0, .05, .86, 1.0)
    total = _math(n, l, "MULTIPLY", _math(n, l, "MULTIPLY", mod, dirt), _math(n, l, "MULTIPLY", smear, low))
    tint = n.new("ShaderNodeVectorMath")
    tint.operation = "SCALE"
    tint.inputs[0].default_value = color
    l.new(total, tint.inputs["Scale"])
    base = tint.outputs[0]
    # Gloss: scanned micro-roughness plus faint irregular patches (handling, wiping) of +-0.07.
    patches = _range(n, l, _noise(n, l, rest, 4.5, 5.0, .6), .3, .7, -env("VINYL_GLOSS_VAR", .07), env("VINYL_GLOSS_VAR", .07))
    rough_v = _math(n, l, "ADD", _range(n, l, rough.outputs["Color"], 0, 1, env("VINYL_ROUGH0", .42), env("VINYL_ROUGH1", .66)), patches)
    nmap = n.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = env("VINYL_NOR", .8)
    l.new(nor.outputs["Color"], nmap.inputs["Color"])
    normal = nmap.outputs["Normal"]
    if seams:
        z_top, z_bot = seams
        x, y, z = sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]
        # Seam lines: a 3 mm pulled-in groove with a lock-stitch of 4 mm stitches every 6 mm.
        height = None
        thread = None
        for zl in (z_top, z_bot):
            dz = _math(n, l, "ABSOLUTE", _math(n, l, "SUBTRACT", z, zl))
            groove = _range(n, l, dz, .0004, .0018, 1., 0.)
            along = _math(n, l, "ADD", _math(n, l, "ABSOLUTE", x), _math(n, l, "ABSOLUTE", y))
            dash = _range(n, l, _math(n, l, "FRACT", _math(n, l, "DIVIDE", along, .006)), .62, .7, 1., 0.)
            stitch = _math(n, l, "MULTIPLY", _range(n, l, dz, .0003, .0007, 1., 0.), dash)
            height = groove if height is None else _math(n, l, "MAXIMUM", height, groove)
            thread = stitch if thread is None else _math(n, l, "MAXIMUM", thread, stitch)
        # Corner creases: loose vinyl bunches in short diagonal folds within ~12 cm of each vertical corner.
        hx, hy = .6048, .4032                                     # rest half-extents of the cover
        dxc = _math(n, l, "SUBTRACT", hx, _math(n, l, "ABSOLUTE", x))
        dyc = _math(n, l, "SUBTRACT", hy, _math(n, l, "ABSOLUTE", y))
        near = _range(n, l, _math(n, l, "ADD", dxc, dyc), .02, .16, 1., 0.)
        wob = _noise(n, l, rest, 22.0, 3.0, .5)
        phase = _math(n, l, "MULTIPLY_ADD", _math(n, l, "SUBTRACT", dxc, dyc), 95.0,
                      _math(n, l, "MULTIPLY_ADD", z, 60.0, _math(n, l, "MULTIPLY", wob, 6.0)))
        crease = _math(n, l, "MULTIPLY", _math(n, l, "MULTIPLY", _math(n, l, "SINE", phase), near),
                       _range(n, l, wob, .3, .7, .3, 1.0))
        bump = n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 1.0
        bump.inputs["Distance"].default_value = .0012
        # The foam under the vinyl is not machined flat: a faint low undulation over the whole cover.
        swell = _math(n, l, "MULTIPLY", _noise(n, l, rest, 6.0, 2.0, .4), env("SWELL", .5))
        folds = _math(n, l, "MULTIPLY_ADD", crease, env("CREASE", 1.6), swell)
        l.new(_math(n, l, "MULTIPLY_ADD", height, -.6, folds), bump.inputs["Height"])
        l.new(normal, bump.inputs["Normal"])
        normal = bump.outputs["Normal"]
        sewn = n.new("ShaderNodeMixRGB")
        sewn.inputs[2].default_value = (*(c * .55 for c in color), 1)
        l.new(_math(n, l, "MAXIMUM", _math(n, l, "MULTIPLY", height, .35), thread), sewn.inputs[0])
        l.new(base, sewn.inputs[1])
        base = sewn.outputs[0]
        rough_v = _math(n, l, "MULTIPLY_ADD", thread, .2, rough_v)
    l.new(base, bs.inputs["Base Color"])
    l.new(rough_v, bs.inputs["Roughness"])
    l.new(normal, bs.inputs["Normal"])
    bs.inputs["Specular IOR Level"].default_value = .5
    bs.inputs["Sheen Weight"].default_value = .15
    bs.inputs["Sheen Tint"].default_value = (.7, .75, .85, 1)
    return mat


def rubber_ball(name):
    """Molded rubber medicine ball: fine pebble grip, satin rubber sheen, two shallow mould lines."""
    mat, bs = fresh(name)
    n, l = _nodes(mat)
    obj = n.new("ShaderNodeTexCoord").outputs["Object"]
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(obj, sep.inputs[0])
    vor = n.new("ShaderNodeTexVoronoi")
    vor.feature = "SMOOTH_F1"
    vor.inputs["Scale"].default_value = env("PEBBLE", 620.0)          # ~1.6 mm pebbles
    vor.inputs["Randomness"].default_value = .9
    l.new(obj, vor.inputs["Vector"])
    pebble = _range(n, l, vor.outputs["Distance"], 0, .6, 1., 0.)
    # Mould lines: equator and one meridian, hairline (0.6 mm) and shallow.
    seam_z = _range(n, l, _math(n, l, "ABSOLUTE", sep.outputs["Z"]), .0002, .0004, 1., 0.)
    seam_x = _range(n, l, _math(n, l, "ABSOLUTE", sep.outputs["X"]), .0002, .0004, 1., 0.)
    seam = _math(n, l, "MAXIMUM", seam_z, seam_x)
    height = _math(n, l, "MULTIPLY_ADD", seam, -.5, pebble)
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 1.0
    bump.inputs["Distance"].default_value = env("PEBBLE_DEPTH", .0002)
    l.new(height, bump.inputs["Height"])
    # The contact mesh (shared with the solver, so it stays as is) still carries the 2 mm channels of the
    # basketball it was made from. Shade it with the smooth sphere normal instead, so the channels do not
    # read; the silhouette moves by at most 2 mm (about one pixel).
    radial = n.new("ShaderNodeVectorMath")
    radial.operation = "NORMALIZE"
    l.new(obj, radial.inputs[0])
    to_world = n.new("ShaderNodeVectorTransform")
    to_world.vector_type = "NORMAL"
    to_world.convert_from = "OBJECT"
    to_world.convert_to = "WORLD"
    l.new(radial.outputs["Vector"], to_world.inputs["Vector"])
    unit = n.new("ShaderNodeVectorMath")
    unit.operation = "NORMALIZE"
    l.new(to_world.outputs["Vector"], unit.inputs[0])
    l.new(unit.outputs["Vector"], bump.inputs["Normal"])
    l.new(bump.outputs["Normal"], bs.inputs["Normal"])
    base = tuple(float(v) for v in os.environ.get("REALISM_BALL_RGB", ".030,.031,.034").split(","))
    wear = _range(n, l, _noise(n, l, obj, 18.0, 6.0, .6), .35, .7, .9, 1.12)
    col = n.new("ShaderNodeVectorMath")
    col.operation = "SCALE"
    col.inputs[0].default_value = base
    l.new(wear, col.inputs["Scale"])
    l.new(col.outputs[0], bs.inputs["Base Color"])
    # Rubber sheen: pebble tops polished by hands (0.45), valleys and grime patches duller (0.55).
    rough_b = _range(n, l, pebble, 0, 1, env("BALL_ROUGH1", .55), env("BALL_ROUGH0", .45))
    rough_b = _math(n, l, "MULTIPLY_ADD", _range(n, l, _noise(n, l, obj, 9.0, 4.0), .3, .7, -.03, .03), 1.0, rough_b)
    l.new(rough_b, bs.inputs["Roughness"])
    bs.inputs["Specular IOR Level"].default_value = .5
    return mat


def training_cone(name, at, rot, scale=1.0):
    """23 cm soft PE training cone with a square foot, slightly scuffed orange plastic."""
    import bpy
    import bmesh
    mat = kit.diffuse(name + " PE orange", (.85, .22, .025), .48)
    kit.add_surface_wear(mat, smudge=.14, grime=.22, scratch=.10, scale=.05)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=40, radius1=.068, radius2=.012, depth=.215)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, .1075 + .012))
    foot = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    bmesh.ops.scale(bm, vec=(.18, .18, .012), verts=foot)
    bmesh.ops.translate(bm, verts=foot, vec=(0, 0, .006))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = at
    obj.rotation_euler.z = rot
    obj.scale = (scale, scale, scale)
    solid = obj.modifiers.new("Wall", "SOLIDIFY")
    solid.thickness = .0025
    obj.modifiers.new("Rounded", "BEVEL").width = .0012
    for p in mesh.polygons:
        p.use_smooth = True
    mesh.materials.append(mat)
    return obj


def hula_hoop(name, at, rot, radius=.37, tube=.0095, bands=24):
    """PE hula hoop lying on the court: glossy tubing wrapped in alternating coloured tape, slightly out of round."""
    import bpy
    import bmesh
    bm = bmesh.new()
    seg, ring = 160, 18
    rows = []
    for i in range(seg):
        t = i / seg * math.tau
        rr = radius * (1 + .012 * math.cos(2 * t + .7))   # gentle ovality from being stored hung
        row = []
        for j in range(ring):
            p = j / ring * math.tau
            r = rr + tube * math.cos(p)
            row.append(bm.verts.new((r * math.cos(t), r * math.sin(t), tube + tube * math.sin(p))))
        rows.append(row)
    for i in range(seg):
        a_, b_ = rows[i], rows[(i + 1) % seg]
        for j in range(ring):
            bm.faces.new((a_[j], b_[j], b_[(j + 1) % ring], a_[(j + 1) % ring]))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for p in mesh.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = at
    obj.rotation_euler.z = rot
    mat = kit.diffuse(name + " taped PE", (.78, .07, .05), .28)
    n, l = _nodes(mat)
    bs = next(x for x in n if x.type == "BSDF_PRINCIPLED")
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(n.new("ShaderNodeTexCoord").outputs["Object"], sep.inputs[0])
    ang = _math(n, l, "ARCTAN2", sep.outputs["Y"], sep.outputs["X"])
    tilt = _math(n, l, "MULTIPLY", sep.outputs["Z"], 22.0)
    wrap = _math(n, l, "MULTIPLY_ADD", ang, bands / math.tau, tilt)   # helical tape
    band = _range(n, l, _math(n, l, "FRACT", wrap), .48, .52, 0., 1.)
    mix = n.new("ShaderNodeMixRGB")
    mix.inputs[1].default_value = (.78, .07, .05, 1)
    mix.inputs[2].default_value = (.85, .82, .74, 1)
    l.new(band, mix.inputs[0])
    l.new(mix.outputs[0], bs.inputs["Base Color"])
    kit.add_surface_wear(mat, smudge=.12, grime=.14, scratch=.08, scale=.06)
    mesh.materials.append(mat)
    return obj


def lens_finish(scene, vignette=.12, dispersion=.0015):
    tree = scene.node_tree
    rl = next(x for x in tree.nodes if x.bl_idname == "CompositorNodeRLayers")
    out = next(x for x in tree.nodes if x.bl_idname == "CompositorNodeComposite")
    src = out.inputs[0].links[0].from_socket if out.inputs[0].is_linked else rl.outputs["Image"]
    for link in list(out.inputs[0].links):
        tree.links.remove(link)
    lens = tree.nodes.new("CompositorNodeLensdist")
    lens.use_fit = True
    lens.inputs["Dispersion"].default_value = dispersion
    tree.links.new(src, lens.inputs["Image"])
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


def __overlay__(scene, args, cache):
    import bpy
    import numpy as np
    out = args.out
    audit = []
    # Floor, court lines and a second set of volleyball lines in another colour, as school halls have.
    floor_obj = next(o for o in scene.objects if o.type == "MESH" and FLOOR in [s.material.name for s in o.material_slots if s.material])
    floor, _ = maple_floor()
    for slot in floor_obj.material_slots:
        slot.material = floor
    white = line_paint("Court line paint, white", (.80, .80, .76))
    lines = [o for o in scene.objects if o.name.startswith(LINE_PREFIXES)]
    line_z = max((o.matrix_world @ v.co).z for o in lines for v in o.data.vertices)
    for o in lines:
        for slot in o.material_slots:
            slot.material = white
    blue = line_paint("Court line paint, volleyball blue", (.04, .16, .42))
    z = line_z + .00025
    volley = [strip("Volleyball sideline", 4.5, -1.5, 4.5, 16.5, .05, z, blue),
              strip("Volleyball sideline.001", -4.5, -1.5, -4.5, 16.5, .05, z, blue),
              strip("Volleyball attack line", -4.5, 4.5, 4.5, 4.5, .05, z, blue),
              strip("Volleyball attack line.001", -4.5, 10.5, 4.5, 10.5, .05, z, blue)]
    for obj in volley:
        audit.append(kit.assert_clear([obj], KEEPOUT, obj.name))
    # Landing mat: royal-blue vinyl with stitched seams along the top and bottom of the side walls,
    # same-colour binding, black webbing handles. The cover mesh (the native shell) is not changed:
    # its rest coordinates are attached as a point attribute so seams and creases ride on the cloth.
    cover = bpy.data.objects[COVER]
    rest = np.asarray(cache["cloth_rest_positions"], dtype=np.float32)
    if len(rest):  # no cover shell when the landing mat is deleted (render_replay.py does not render the mat)
        if len(rest) != len(cover.data.vertices):
            raise RuntimeError("cloth_rest_positions does not match the cover mesh")
        if "rest" in cover.data.attributes:
            cover.data.attributes.remove(cover.data.attributes["rest"])
        cover.data.attributes.new("rest", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", rest.reshape(-1))
    vinyl_rgb = tuple(float(v) for v in os.environ.get("REALISM_MAT_RGB", ".018,.055,.20").split(","))
    vinyl = vinyl_cover("Royal blue vinyl landing-mat cover", vinyl_rgb, seams=(env("SEAM_TOP", .114), env("SEAM_BOT", .022)))
    for slot in cover.material_slots:
        slot.material = vinyl
    piping = vinyl_cover("Royal blue vinyl edge binding", tuple(c * .8 for c in vinyl_rgb))
    for o in scene.objects:
        if o.name.startswith("Sewn white cover piping"):
            for slot in o.material_slots:
                slot.material = piping
    webbing = bpy.data.materials["Woven black carry webbing"]
    kit.add_surface_wear(webbing, smudge=.06, grime=.12, scratch=.04, scale=.02)
    # Medicine ball: replace the photographic basketball bake (it carried printed lettering).
    ball = bpy.data.objects["medicine_ball"]
    rubber = rubber_ball("Molded rubber medicine ball")
    for slot in ball.material_slots:
        slot.material = rubber
    # Walls behind the court: padded wall protection reads as vinyl, plaster keeps its mottling.
    kit.add_wall_mottling(bpy.data.materials["Warm off-white gym plaster"], .06)
    kit.add_surface_wear(bpy.data.materials["Muted blue-green wall protection"], smudge=.10, grime=.10, scratch=.05, scale=.4)
    # Dressing far from the mat.
    hoop = hula_hoop("PE hula hoop", HOOP_AT, .4)
    audit.append(kit.assert_clear([hoop], KEEPOUT, hoop.name))
    cones = [training_cone(f"Training cone {i}", at, r) for i, (at, r) in enumerate(CONES)]
    for obj in cones:
        audit.append(kit.assert_clear([obj], KEEPOUT, obj.name))
    for label, objs in (("hula hoop", [hoop]), ("cones", cones)):
        box, ok = in_frame(scene, objs)
        if not ok:
            raise RuntimeError(f"{label} is cut by the frame edge: {box}")
    # Light: overcast daylight through the left-wall windows and a full grid of overhead fixtures.
    # The packed hall had two rows of three; a school hall this size has three rows of six, so the
    # existing luminaire (housing, diffuser, emitter) is repeated on that grid.
    kit_parts = ("Gym linear ceiling luminaire", "Gym ceiling diffuser", "Gym overhead soft fixture")
    taken = {(round(o.location.x, 2), round(o.location.y, 2)) for o in scene.objects if o.name.startswith(kit_parts[2])}
    template = [next(o for o in scene.objects if o.name == name) for name in kit_parts]
    added = 0
    for x in (-4.5, 0.0, 4.5):
        for y in (-3.5, 1.0, 5.5, 10.0, 14.5, 19.0):
            if (x, y) in taken:
                continue
            for part in template:
                twin = part.copy()
                twin.name = part.name + f" grid {x:+.1f} {y:+.1f}"
                twin.location.x, twin.location.y = x, y
                bpy.context.collection.objects.link(twin)
            added += 1
    fixtures = [o for o in scene.objects if o.type == "LIGHT" and o.data.type == "AREA"]
    for light in {o.data for o in fixtures}:
        light.energy = env("FIXTURE_W", 140.0)
        light.color = (1.0, .97, .92)
    for o in scene.objects:
        if o.name.startswith("Clear closed gym window glass"):
            o.visible_shadow = False
    world = scene.world.node_tree.nodes["Background"]
    world.inputs["Strength"].default_value *= env("WORLD", 1.0)
    sun_energy = env("SUN", 0.0)
    if sun_energy > 0:
        kit.sun("Morning sun through gym windows", (.85, .33, -.55), sun_energy, angle_deg=.6, color=(1.0, .93, .83))
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = os.environ.get("REALISM_LOOK", "AgX - Medium High Contrast")
    scene.view_settings.exposure = env("EXPOSURE", 0.0)
    cam = scene.camera.data
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = env("FSTOP", 5.6)      # focus distance (on the mat) unchanged
    lens_finish(scene)
    kit.write_json(Path(out) / "realism_provenance.json", {
        "overlay": "realism", "host": kit.host_record(),
        "assets": {"floor_grain": str(FLOOR_TEX), "vinyl_grain": str(VINYL_TEX)},
        "settings": {k: v for k, v in os.environ.items() if k.startswith("REALISM_")},
        "overhead_fixtures": {"count": len(fixtures), "added": added, "energy_w_each": env("FIXTURE_W", 140.0)},
        "dressing": audit, "keepout_m": KEEPOUT})


HOOP_AT = (-2.1, 1.4, 0)                      # lying flat, back left of the mat
CONES = (((-.6, 4.2, 0), .6), ((-.8, 5.1, 0), .2), ((-1.0, 6.0, 0), .4))  # a receding drill line
import render_replay  # noqa: E402  (HERE is on sys.path)
render_replay.main(overlay=__overlay__)
