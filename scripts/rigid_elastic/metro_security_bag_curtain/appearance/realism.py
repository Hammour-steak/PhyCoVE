"""Current look: the checkpoint photographed as a working metro concourse.

render_scene.py calls apply() right after the station, scanner, outfeed, curtain and bags exist,
and finish() when it builds the compositor. Only appearance changes here: no support surface,
actor transform, camera or native state is touched, so every replay audit still holds.

* no printed text, logos or labels anywhere; the hanging wayfinding box shows plain pictograms;
* polished sesame-white granite floor (ambientCG Granite002A scan, one crop per 600 mm tile,
  base roughness 0.09-0.19 under a 0.06-0.12 polish coat, with polished lanes, stains, scratches and
  dark joint arrises);
* light only from luminaires that exist: an area light per linear diffuser (110 degree spread, so
  pools form under the runs) and two ceiling slots washing the back and return walls from the top;
  the lower walls and far corners stay darker;
* glazed wall panels from the Poly Haven plaster_grey_04 scan with a dirty kick band; brushed
  stainless with anisotropic grain and fingerprints at hand height;
* scanner: rounded hood with anthracite end caps, cover seam, top service hatch with screws,
  handles, yellowing and handprints around the tunnel mouths, scuffs at shoe height; textured belt
  (ambientCG Rubber002 relief) with a splice and wear tracks that travel with the belt; lead strips
  with satin sheen, hanging creases and a scuffed lower edge;
* a slim backlit poster box (CC0 landscape photo), a recessed fire-hose cabinet with hose reel and
  valve behind clear glass, a litter bin and a yellow caution stand, all clear of the bag path;
* AgX medium-high contrast, exposure set so the luminaires just clip; faint fog glow, lateral colour
  and vignette in the compositor.
"""
from pathlib import Path
import math
import os
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parents[2])]
import pcve_realism_kit as kit
from pcve_assets import asset

LED = (1.0, 0.925, 0.86)          # about 5000 K in linear Rec.709
LED_W_PER_M = float(os.environ.get("LOOK_LED_W_PER_M", "45"))
EXPOSURE = float(os.environ.get("LOOK_EXPOSURE", "-1.0"))
VIEW_LOOK = os.environ.get("LOOK_VIEW_LOOK", "AgX - Medium High Contrast")
PLASTER = asset("polyhaven/plaster_grey_04")
LOOK_ASSETS = asset("scenes/metro_security_bag_curtain/station_look")
GRANITE = asset("ambientcg/Granite002A")
RUBBER = asset("ambientcg/Rubber002")
WASH_W_PER_M = float(os.environ.get("LOOK_WASH_W_PER_M", "12"))
FLOOR_TOP = -.005                 # top of the granite tiles (scene datum used by every grounded prop)

TEXT_PREFIXES = (
    "Station bilingual sign", "Station sign backing", "Metro train direction sign", "Train direction sign backing",
    "Wayfinding aluminium side extrusion", "Wayfinding aluminium horizontal extrusion", "Wall sign captive standoff",
    "Rail directory", "Directory frame fixing", "Detector bilingual face", "Tray return instructions",
    "Tray information holder", "Tray information mounting bracket", "X-ray warning label",
    "Safety label laminated adhesive edge", "Pickup notice", "Utility room", "Scanner equipment identification plate",
    "Etched equipment data rule", "Nameplate rivet")
HIDDEN_LIGHTS = ("Ceiling over scanner", "Broad station fill", "Exit material edge", "Back concourse light",
                 "Gate concourse overhead", "Concourse side illumination", "Utility doorway wall wash")

WEAR = {  # material: (smudge, grime, scratch, scale)
    "Satin 304 stainless sliding and collection sheet": (.06, 0.0, .015, .6),
    "Dark graphite coated steel": (.08, .06, .05, .12),
    "Warm grey fine powder-coat": (.12, .12, .06, .3),
    "Glazed teal station enamel": (.08, .08, .04, .4),
    "Injection moulded blue polypropylene": (.10, .14, .08, .15),
    "Utility door satin powder coating": (.12, .14, .06, .3),
    "Dark keyboard keycaps": (.12, .10, .02, .05),
    "Muted safety orange powder coat": (.10, .12, .06, .3),
}


def _bpy():
    import bpy
    return bpy


def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _bounds(ob):
    from mathutils import Vector
    pts = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
    return [min(p[k] for p in pts) for k in range(3)], [max(p[k] for p in pts) for k in range(3)]


def strip_text():
    bpy = _bpy()
    removed = 0
    for ob in list(bpy.context.scene.objects):
        if ob.name.startswith(TEXT_PREFIXES):
            bpy.data.objects.remove(ob, do_unlink=True)
            removed += 1
    return removed


def _flat(name, polygons, y, mat):
    """Flat mesh in the x-z plane at depth y, facing -y (towards the camera side)."""
    bpy = _bpy()
    verts, faces = [], []
    for poly in polygons:
        start = len(verts)
        verts += [(x, y, z) for x, z in poly]
        faces.append(tuple(range(start, start + len(poly))))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for poly in mesh.polygons:   # make every face point to -y
        if poly.normal.y > 0:
            poly.flip()
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    mesh.materials.append(mat)
    return ob


def _rect(cx, cz, w, h):
    return [(cx - w / 2, cz - h / 2), (cx + w / 2, cz - h / 2), (cx + w / 2, cz + h / 2), (cx - w / 2, cz + h / 2)]


def _arrow(cx, cz, size, direction):
    """Arrow as a shaft rectangle and a triangular head (two convex faces)."""
    s = size
    if direction == "up":
        return [_rect(cx, cz - .12 * s, .16 * s, .56 * s), [(cx - .34 * s, cz + .12 * s), (cx + .34 * s, cz + .12 * s), (cx, cz + .48 * s)]]
    return [_rect(cx - .12 * s, cz, .56 * s, .16 * s), [(cx + .12 * s, cz - .34 * s), (cx + .48 * s, cz), (cx + .12 * s, cz + .34 * s)]]


def pictogram_sign():
    """Wayfinding box: dark face with white pictograms only (no letters or numbers)."""
    bpy = _bpy()
    face = bpy.data.objects.get("Wayfinding recessed backlit face")
    if face is None:
        return False
    lo, hi = _bounds(face)
    x0, x1, z0, z1, y = lo[0], hi[0], lo[2], hi[2], lo[1]
    cz, h = (z0 + z1) / 2, (z1 - z0)
    slate = bpy.data.materials.new("Wayfinding face dark satin print")
    slate.use_nodes = True
    bs = _principled(slate)
    bs.inputs["Base Color"].default_value = (.020, .028, .034, 1)
    bs.inputs["Roughness"].default_value = .38
    face.data.materials.clear()
    face.data.materials.append(slate)
    white = bpy.data.materials.new("Wayfinding backlit white pictogram")
    white.use_nodes = True
    bw = _principled(white)
    bw.inputs["Base Color"].default_value = (.85, .86, .85, 1)
    bw.inputs["Roughness"].default_value = .4
    bw.inputs["Emission Color"].default_value = (*LED, 1)
    bw.inputs["Emission Strength"].default_value = 2.2
    grey = bpy.data.materials.new("Wayfinding divider")
    grey.use_nodes = True
    _principled(grey).inputs["Base Color"].default_value = (.20, .21, .21, 1)
    yy = y - .0008
    width = x1 - x0
    s = h * .62
    shapes = []
    shapes += _arrow(x0 + .10 * width, cz, s, "up")
    # train front: body, windscreen cut-out drawn darker on top, two feet
    tx = x0 + .23 * width
    body = [(tx - .30 * s, cz - .34 * s), (tx + .30 * s, cz - .34 * s), (tx + .34 * s, cz - .20 * s), (tx + .34 * s, cz + .30 * s),
            (tx + .22 * s, cz + .42 * s), (tx - .22 * s, cz + .42 * s), (tx - .34 * s, cz + .30 * s), (tx - .34 * s, cz - .20 * s)]
    shapes.append(body)
    feet = [[(tx - .26 * s, cz - .38 * s), (tx - .14 * s, cz - .38 * s), (tx - .24 * s, cz - .52 * s), (tx - .36 * s, cz - .52 * s)],
            [(tx + .14 * s, cz - .38 * s), (tx + .26 * s, cz - .38 * s), (tx + .36 * s, cz - .52 * s), (tx + .24 * s, cz - .52 * s)]]
    shapes += feet
    _flat("Wayfinding pictogram shapes left", shapes, yy, white)
    _flat("Wayfinding pictogram train windows", [_rect(tx, cz + .14 * s, .50 * s, .20 * s), _rect(tx - .18 * s, cz - .16 * s, .10 * s, .08 * s),
                                                  _rect(tx + .18 * s, cz - .16 * s, .10 * s, .08 * s)], yy - .0006, slate)
    _flat("Wayfinding divider bar", [_rect((x0 + x1) / 2, cz, .006, h * .78)], yy, grey)
    # exit: open door frame with an arrow leaving it, then a right arrow
    ex = x0 + .66 * width
    door = [_rect(ex - .24 * s, cz, .07 * s, .86 * s), _rect(ex, cz + .395 * s, .55 * s, .07 * s), _rect(ex + .24 * s, cz + .18 * s, .07 * s, .50 * s)]
    _flat("Wayfinding pictogram shapes right", door + _arrow(ex + .16 * s, cz - .14 * s, .62 * s, "right") + _arrow(x0 + .90 * width, cz, s, "right"), yy, white)
    return True


# ----------------------------------------------------------------------------- node helpers

def _new(nodes, kind, **values):
    node = nodes.new(kind)
    for key, value in values.items():
        node.inputs[key].default_value = value
    return node


def _feed(links, value, socket):
    if isinstance(value, (int, float, tuple)):
        socket.default_value = value
    else:
        links.new(value, socket)


def _math(nt, op, a, b=0.0, clamp=False):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    node.use_clamp = clamp
    _feed(nt.links, a, node.inputs[0])
    _feed(nt.links, b, node.inputs[1])
    return node.outputs[0]


def _range(nt, value, a, b, c, d, smooth=True):
    node = nt.nodes.new("ShaderNodeMapRange")
    node.interpolation_type = "SMOOTHSTEP" if smooth else "LINEAR"
    node.clamp = True
    _feed(nt.links, value, node.inputs["Value"])
    node.inputs["From Min"].default_value, node.inputs["From Max"].default_value = a, b
    node.inputs["To Min"].default_value, node.inputs["To Max"].default_value = c, d
    return node.outputs[0]


def _noise(nt, vector, scale, detail=4.0, rough=.55, stretch=None):
    if stretch is not None:
        vm = nt.nodes.new("ShaderNodeVectorMath")
        vm.operation = "MULTIPLY"
        nt.links.new(vector, vm.inputs[0])
        vm.inputs[1].default_value = stretch
        vector = vm.outputs[0]
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = rough
    nt.links.new(vector, node.inputs["Vector"])
    return node.outputs["Fac"]


def _world(nt):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    return geo.outputs["Position"], sep.outputs


def _input_source(nt, socket):
    """Current driver of a principled input: its linked socket, or its constant value."""
    return socket.links[0].from_socket if socket.is_linked else (
        tuple(socket.default_value) if hasattr(socket.default_value, "__len__") else float(socket.default_value))


def _scale_colour(nt, colour, factor):
    node = nt.nodes.new("ShaderNodeVectorMath")
    node.operation = "SCALE"
    _feed(nt.links, colour if not isinstance(colour, tuple) else colour[:3], node.inputs[0])
    _feed(nt.links, factor, node.inputs["Scale"])
    return node.outputs[0]


def _mix_colour(nt, a, b, factor):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    _feed(nt.links, factor, node.inputs["Factor"])
    _feed(nt.links, a if not isinstance(a, tuple) else (*a[:3], 1.0), node.inputs[6])
    _feed(nt.links, b if not isinstance(b, tuple) else (*b[:3], 1.0), node.inputs[7])
    return node.outputs[2]


def _image(nt, path, vector, data=True):
    bpy = _bpy()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(path), check_existing=True)
    if data:
        tex.image.colorspace_settings.name = "Non-Color"
    nt.links.new(vector, tex.inputs["Vector"])
    return tex.outputs["Color"]


# ----------------------------------------------------------------------------- floor

def granite_floor():
    """Polished sesame-white granite, 600 mm tiles: scanned ambientCG Granite002A, one crop per tile,
    base roughness 0.09-0.19 with traffic polish, stains and fine scratches; darker arrises at the joints."""
    bpy = _bpy()
    mat = bpy.data.materials["Honed granite tile with physical joints"]
    mat.name = "Polished granite floor tile"
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bs.outputs[0], out.inputs[0])
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "Single-granite-tile photo crop"
    five = nt.nodes.new("ShaderNodeVectorMath")
    five.operation = "SCALE"
    five.inputs["Scale"].default_value = 5.0
    nt.links.new(uv.outputs["UV"], five.inputs[0])
    local = nt.nodes.new("ShaderNodeVectorMath")
    local.operation = "FRACTION"
    nt.links.new(five.outputs[0], local.inputs[0])
    cell = nt.nodes.new("ShaderNodeVectorMath")
    cell.operation = "FLOOR"
    nt.links.new(five.outputs[0], cell.inputs[0])
    crop = nt.nodes.new("ShaderNodeVectorMath")          # 0.57 of the ~1 m scan on each 0.6 m tile
    crop.operation = "SCALE"
    crop.inputs["Scale"].default_value = 3.0
    nt.links.new(uv.outputs["UV"], crop.inputs[0])
    colour = _image(nt, GRANITE / "Granite002A_2K-JPG_Color.jpg", crop.outputs[0], data=False)
    rough_map = _image(nt, GRANITE / "Granite002A_2K-JPG_Roughness.jpg", crop.outputs[0])
    normal_map = _image(nt, GRANITE / "Granite002A_2K-JPG_NormalGL.jpg", crop.outputs[0])
    white = nt.nodes.new("ShaderNodeTexWhiteNoise")       # each tile cut from a slightly different block
    white.noise_dimensions = "3D"
    nt.links.new(cell.outputs[0], white.inputs["Vector"])
    tile_tone = _range(nt, white.outputs["Value"], 0, 1, .93, 1.04, smooth=False)
    # joints: the tile-local coordinate lies in [0.025, 0.975]; darken a ~5 mm arris band
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(local.outputs[0], sep.inputs[0])
    ex = _math(nt, "MINIMUM", _math(nt, "SUBTRACT", sep.outputs[0], .025), _math(nt, "SUBTRACT", .975, sep.outputs[0]))
    ey = _math(nt, "MINIMUM", _math(nt, "SUBTRACT", sep.outputs[1], .025), _math(nt, "SUBTRACT", .975, sep.outputs[1]))
    arris = _range(nt, _math(nt, "MINIMUM", ex, ey), 0.0, .009, 1.0, 0.0)
    pos, xyz = _world(nt)
    traffic = _range(nt, _noise(nt, pos, .45, 2.0), .42, .62, 0.0, 1.0)            # polished walking lanes
    stain = _range(nt, _noise(nt, pos, 2.4, 5.0, .6), .63, .74, 0.0, 1.0)         # dried water and dirt
    scratch = _range(nt, _noise(nt, pos, 3.0, 3.0, .5, (1.0, 38.0, 1.0)), .66, .72, 0.0, 1.0)
    tone = _math(nt, "MULTIPLY", tile_tone, _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", stain, .10)))
    tone = _math(nt, "MULTIPLY", tone, _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", arris, .55)))
    base = _scale_colour(nt, colour, _math(nt, "MULTIPLY", tone, .72))
    nt.links.new(base, bs.inputs["Base Color"])
    rough = _range(nt, rough_map, 0.0, 1.0, .09, .19, smooth=False)
    rough = _math(nt, "SUBTRACT", rough, _math(nt, "MULTIPLY", traffic, .04))
    rough = _math(nt, "ADD", rough, _math(nt, "MULTIPLY", stain, .14))
    rough = _math(nt, "ADD", rough, _math(nt, "MULTIPLY", scratch, .05))
    rough = _math(nt, "ADD", rough, _math(nt, "MULTIPLY", arris, .30), clamp=True)
    nt.links.new(rough, bs.inputs["Roughness"])
    # crystallised polish layer: sharper reflections, dulled by stains and along the joints
    # coat roughness 0.06 on polished lanes to 0.12 elsewhere, dulled further by stains and at the joints
    bs.inputs["Coat Weight"].default_value = .85
    coat = _math(nt, "ADD", .06, _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 1.0, traffic), .06))
    coat = _math(nt, "ADD", coat, _math(nt, "ADD", _math(nt, "MULTIPLY", stain, .15), _math(nt, "MULTIPLY", arris, .4)), clamp=True)
    nt.links.new(coat, bs.inputs["Coat Roughness"])
    normal = _new(nt.nodes, "ShaderNodeNormalMap", Strength=.18)
    nt.links.new(normal_map, normal.inputs["Color"])
    nt.links.new(normal.outputs[0], bs.inputs["Normal"])
    shoe_scuffs(mat, amount=.55, scale=3.0)
    grout = bpy.data.materials["Recessed real epoxy tile grout"]
    gb = _principled(grout)
    gb.inputs["Base Color"].default_value = (.045, .048, .047, 1)
    gb.inputs["Roughness"].default_value = .85
    return mat.name


# ----------------------------------------------------------------------------- light

def _emitter(name, strength=18.0):
    bpy = _bpy()
    mat = bpy.data.materials.get(name)
    bs = _principled(mat)
    bs.inputs["Emission Color"].default_value = (*LED, 1)
    bs.inputs["Base Color"].default_value = (.85, .86, .86, 1)
    bs.inputs["Emission Strength"].default_value = strength
    return mat


def _area(name, location, size_x, size_y, power, rotation=(0.0, 0.0, 0.0), spread=110.0):
    bpy = _bpy()
    data = bpy.data.lights.new(name, "AREA")
    data.shape = "RECTANGLE"
    data.size, data.size_y = size_x, size_y
    data.energy = power
    data.color = LED
    data.spread = math.radians(spread)
    ob = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(ob)
    ob.location = location
    ob.rotation_euler = rotation
    ob.visible_camera = False      # the diffuser mesh is what the camera sees
    return ob


def relight():
    """Only luminaires light the room. Each linear diffuser carries an area light of its own size
    (110 degree spread, so pools form under the runs); two ceiling slots wash the back and return
    walls from the top, leaving the lower wall and the far corners darker."""
    bpy = _bpy()
    scene = bpy.context.scene
    for ob in list(scene.objects):
        if ob.type == "LIGHT" and ob.name.split(".")[0] in HIDDEN_LIGHTS:
            bpy.data.objects.remove(ob, do_unlink=True)
    from scene_environment import cube
    dark = bpy.data.materials["Dark graphite coated steel"]
    diffuse = _emitter("Ceiling diffusers")
    # the middle ceiling run continues over the camera side of the hall
    cube("Linear ceiling light housing", (0.0, -3.35, 3.14), (.12, 2.30, .055), dark, .004)
    cube("Linear ceiling diffuser", (0.0, -3.35, 3.106), (.09, 2.24, .008), diffuse, .002)
    lights = 0
    for ob in list(scene.objects):
        if ob.name.split(".")[0] not in ("Linear ceiling diffuser", "Gate hall light diffuser"):
            continue
        lo, hi = _bounds(ob)
        sx, sy = hi[0] - lo[0], hi[1] - lo[1]
        _area("Luminaire " + ob.name, ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2] - .003), sx, sy,
              LED_W_PER_M * max(sx, sy))
        lights += 1
    # ceiling wall-wash slots: a narrow diffuser 0.25 m from each wall, aimed at the wall
    slot = _emitter("Ceiling diffusers")
    cube("Back wall wash slot housing", (0.0, 4.86, 3.14), (9.0, .07, .05), dark, .002)
    cube("Back wall wash slot diffuser", (0.0, 4.86, 3.112), (8.94, .035, .006), slot, .001)
    _area("Luminaire back wall wash", (0.0, 4.86, 3.105), 8.94, .035, WASH_W_PER_M * 8.94,
          rotation=(math.radians(24), 0.0, 0.0), spread=50.0)
    cube("Return wall wash slot housing", (-4.67, 1.0, 3.14), (.07, 8.2, .05), dark, .002)
    cube("Return wall wash slot diffuser", (-4.67, 1.0, 3.112), (.035, 8.14, .006), slot, .001)
    _area("Luminaire return wall wash", (-4.67, 1.0, 3.105), .035, 8.14, WASH_W_PER_M * 8.14,
          rotation=(0.0, math.radians(24), 0.0), spread=50.0)
    lights += 2
    wall = bpy.data.objects.get("Utility door wall light diffuser")
    if wall:
        lo, hi = _bounds(wall)
        # local x -> world -z, local y -> world y; local -z (emission) -> world +x, away from the wall
        _area("Luminaire staff door wall light", (hi[0] + .003, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2),
              hi[2] - lo[2], hi[1] - lo[1], 14.0, rotation=(0.0, math.radians(-90), 0.0))
        lights += 1
    world = scene.world.node_tree.nodes.get("Background")
    world.inputs["Color"].default_value = (.60, .62, .64, 1)
    world.inputs["Strength"].default_value = .004
    return lights


# ----------------------------------------------------------------------------- wear

def kick_grime(mat, height=.32, amount=.22):
    """Darker, rougher band where shoes, mops and trolleys touch the bottom of walls and equipment."""
    if mat is None:
        return
    nt = mat.node_tree
    bs = _principled(mat)
    pos, xyz = _world(nt)
    mask = _math(nt, "MULTIPLY", _range(nt, xyz[2], 0.0, height, 1.0, 0.0),
                 _range(nt, _noise(nt, pos, 7.0, 4.0), .35, .70, .45, 1.0))
    base = _input_source(nt, bs.inputs["Base Color"])
    nt.links.new(_scale_colour(nt, base, _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", mask, amount))), bs.inputs["Base Color"])
    rough = _input_source(nt, bs.inputs["Roughness"])
    nt.links.new(_math(nt, "ADD", rough, _math(nt, "MULTIPLY", mask, .14), clamp=True), bs.inputs["Roughness"])


def stainless_finish():
    """Brushed stainless: anisotropic grain around the vertical axis, fingerprints at hand height."""
    bpy = _bpy()
    mat = bpy.data.materials["Brushed satin stainless steel"]
    nt = mat.node_tree
    bs = _principled(mat)
    tangent = nt.nodes.new("ShaderNodeTangent")
    tangent.direction_type = "RADIAL"
    tangent.axis = "Z"
    nt.links.new(tangent.outputs[0], bs.inputs["Tangent"])
    bs.inputs["Anisotropic"].default_value = .55
    co = nt.nodes.new("ShaderNodeTexCoord")
    pos, xyz = _world(nt)
    hand = _math(nt, "MULTIPLY", _range(nt, xyz[2], .70, .92, 0.0, 1.0), _range(nt, xyz[2], 1.05, 1.30, 1.0, 0.0))
    prints = _range(nt, _noise(nt, co.outputs["Object"], 34.0, 6.0, .65), .58, .70, 0.0, 1.0)
    smudge = _range(nt, _noise(nt, co.outputs["Object"], 5.0, 3.0), .40, .70, 0.0, 1.0)
    rough = _input_source(nt, bs.inputs["Roughness"])
    rough = _math(nt, "ADD", rough, _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", prints, hand), .16))
    rough = _math(nt, "ADD", rough, _math(nt, "MULTIPLY", smudge, .05), clamp=True)
    nt.links.new(rough, bs.inputs["Roughness"])


def scanner_wear():
    """Powder coat of the scanner (and detector posts): slight yellowing and handprints around the tunnel
    mouths, scuffs at shoe height."""
    bpy = _bpy()
    mat = bpy.data.materials["Warm grey fine powder-coat"]
    nt = mat.node_tree
    bs = _principled(mat)
    co = nt.nodes.new("ShaderNodeTexCoord")
    pos, xyz = _world(nt)
    near_exit = _range(nt, _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", xyz[0], .02)), 0.0, .55, 1.0, 0.0)
    near_entry = _range(nt, _math(nt, "ABSOLUTE", _math(nt, "ADD", xyz[0], 1.59)), 0.0, .55, 1.0, 0.0)
    mouths = _math(nt, "MULTIPLY", _math(nt, "MAXIMUM", near_exit, near_entry), _range(nt, xyz[2], .55, .80, 0.0, 1.0))
    yellow = _math(nt, "ADD", .06, _math(nt, "MULTIPLY", mouths, .28))
    base = _input_source(nt, bs.inputs["Base Color"])
    tinted = _mix_colour(nt, base, (.47, .43, .31), yellow)
    prints = _math(nt, "MULTIPLY", _range(nt, _noise(nt, co.outputs["Object"], 26.0, 6.0, .65), .57, .68, 0.0, 1.0), mouths)
    kick = _math(nt, "MULTIPLY", _range(nt, xyz[2], .05, .30, 1.0, 0.0), _range(nt, _noise(nt, pos, 9.0, 4.0), .40, .70, .3, 1.0))
    shade = _math(nt, "SUBTRACT", 1.0, _math(nt, "ADD", _math(nt, "MULTIPLY", prints, .07), _math(nt, "MULTIPLY", kick, .22)))
    nt.links.new(_scale_colour(nt, tinted, shade), bs.inputs["Base Color"])
    rough = _input_source(nt, bs.inputs["Roughness"])
    rough = _math(nt, "ADD", rough, _math(nt, "MULTIPLY", prints, .20))
    nt.links.new(_math(nt, "ADD", rough, _math(nt, "MULTIPLY", kick, .12), clamp=True), bs.inputs["Roughness"])


def scanner_hardware():
    """Top-cover service hatch with captive screws and two recessed lifting handles on the exit end."""
    bpy = _bpy()
    from scene_environment import cube
    from detail_refinement import bolt
    dark = bpy.data.materials["Dark graphite coated steel"]
    steel = bpy.data.materials["Brushed satin stainless steel"]
    shell = bpy.data.objects.get("Scanner upper shell")
    if shell is None:
        return 0
    lo, hi = _bounds(shell)
    top = hi[2]
    cx, w, d = -.62, .62, .46
    for y in (-d / 2, d / 2):
        cube("Scanner top hatch seam", (cx, y, top + .0003), (w, .003, .0012), dark, 0)
    for x in (cx - w / 2, cx + w / 2):
        cube("Scanner top hatch seam", (x, 0.0, top + .0003), (.003, d, .0012), dark, 0)
    n = 0
    for x in (cx - w / 2 + .03, cx + w / 2 - .03):
        for y in (-d / 2 + .03, d / 2 - .03):
            bolt("Scanner top hatch captive screw", (x, y, top), "Z", steel, dark, .0045)
            n += 1
    for y in (-.20, .20):
        cube("Scanner exit end recessed handle", (hi[0] + .001, y, .93), (.004, .12, .028), dark, .002)
    return n


def belt_texture():
    """Black PVC belt: scanned rubber micro-relief (ambientCG Rubber002) in belt coordinates, so it travels
    with the belt; one skived splice, longitudinal wear tracks and dust along the edges."""
    bpy = _bpy()
    mat = bpy.data.materials["Conveyor continuous rubber top cover"]
    nt = mat.node_tree
    keep = {n.name for n in nt.nodes if n.type in ("TEX_COORD", "MAPPING")}
    metric = next(n for n in nt.nodes if n.type == "VECT_MATH" and n.operation == "MULTIPLY"
                  and abs(n.inputs[1].default_value[1] - .55) < 1e-6)
    keep.add(metric.name)
    for node in list(nt.nodes):
        if node.name not in keep:
            nt.nodes.remove(node)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bs.outputs[0], out.inputs[0])
    loop = metric.inputs[1].default_value[0]
    s = metric.outputs[0]
    tile = nt.nodes.new("ShaderNodeVectorMath")
    tile.operation = "SCALE"
    tile.inputs["Scale"].default_value = 2.2
    nt.links.new(s, tile.inputs[0])
    rough_map = _image(nt, RUBBER / "Rubber002_4K-JPG_Roughness.jpg", tile.outputs[0])
    normal_map = _image(nt, RUBBER / "Rubber002_4K-JPG_NormalGL.jpg", tile.outputs[0])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(s, sep.inputs[0])
    along, across = sep.outputs[0], sep.outputs[1]
    tracks = _range(nt, _noise(nt, s, 1.0, 3.0, .5, (.25, 30.0, 1.0)), .45, .75, 0.0, 1.0)
    edge = _math(nt, "MAXIMUM", _range(nt, across, 0.0, .05, 1.0, 0.0), _range(nt, across, .50, .55, 0.0, 1.0))
    skew = _math(nt, "ADD", _math(nt, "SUBTRACT", along, loop * .37), _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", across, .275), .35))
    splice = _range(nt, _math(nt, "ABSOLUTE", skew), 0.0, .004, 1.0, 0.0)
    grey = _math(nt, "ADD", .011, _math(nt, "ADD", _math(nt, "MULTIPLY", tracks, .010),
                                         _math(nt, "ADD", _math(nt, "MULTIPLY", edge, .028), _math(nt, "MULTIPLY", splice, .02))))
    combine = nt.nodes.new("ShaderNodeCombineXYZ")
    for k in range(3):
        nt.links.new(grey, combine.inputs[k])
    nt.links.new(combine.outputs[0], bs.inputs["Base Color"])
    rough = _range(nt, rough_map, 0.0, 1.0, .55, .80, smooth=False)
    rough = _math(nt, "SUBTRACT", rough, _math(nt, "MULTIPLY", tracks, .14))
    nt.links.new(_math(nt, "ADD", rough, _math(nt, "MULTIPLY", edge, .12), clamp=True), bs.inputs["Roughness"])
    bs.inputs["Specular IOR Level"].default_value = .35
    normal = _new(nt.nodes, "ShaderNodeNormalMap", Strength=.45)
    nt.links.new(normal_map, normal.inputs["Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .6
    bump.inputs["Distance"].default_value = .0004
    nt.links.new(_math(nt, "SUBTRACT", 1.0, splice), bump.inputs["Height"])
    nt.links.new(normal.outputs[0], bump.inputs["Normal"])
    nt.links.new(bump.outputs[0], bs.inputs["Normal"])
    return loop


def curtain_strips(curtain):
    """Lead-rubber strips: satin sheen, vertical creases from hanging, a scuffed lower edge."""
    if curtain is None:
        return 0
    n = 0
    for mat in curtain.data.materials:
        nt = mat.node_tree
        bs = _principled(mat)
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "Rest material coordinates"
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(uv.outputs["UV"], sep.inputs[0])
        creases = _noise(nt, uv.outputs["UV"], 1.0, 3.0, .5, (55.0, 3.5, 1.0))
        scuff = _math(nt, "MULTIPLY", _range(nt, sep.outputs[1], .23, .29, 0.0, 1.0),
                      _range(nt, _noise(nt, uv.outputs["UV"], 60.0, 4.0), .40, .70, .4, 1.0))
        base = _input_source(nt, bs.inputs["Base Color"])
        nt.links.new(_mix_colour(nt, base, (.05, .052, .052), _math(nt, "MULTIPLY", scuff, .7)), bs.inputs["Base Color"])
        rough = _range(nt, _noise(nt, uv.outputs["UV"], 18.0, 3.0), .3, .7, .36, .52, smooth=False)
        nt.links.new(_math(nt, "ADD", rough, _math(nt, "MULTIPLY", scuff, .25), clamp=True), bs.inputs["Roughness"])
        bs.inputs["Specular IOR Level"].default_value = .45
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = .35
        bump.inputs["Distance"].default_value = .0015
        nt.links.new(creases, bump.inputs["Height"])
        nt.links.new(bump.outputs[0], bs.inputs["Normal"])
        n += 1
    return n


# ----------------------------------------------------------------------------- wall fittings and props

def lightbox(x, z, width, height, image):
    """Slim backlit poster box: 35 mm deep, anodised aluminium bezel, glossy face, photo without text."""
    bpy = _bpy()
    from scene_environment import cube, material
    wall = 5.108
    depth, bezel = .035, .024
    alu = material("Anodised aluminium poster frame", (.62, .62, .61), .32, 1.0)
    back = bpy.data.materials["Dark graphite coated steel"]
    cube("Poster lightbox back tray", (x, wall - .0125, z), (width - .01, .025, height - .01), back, .002)
    for sx in (-1, 1):
        cube("Poster lightbox side bezel", (x + sx * (width - bezel) / 2, wall - depth / 2, z), (bezel, depth, height), alu, .003)
    for sz in (-1, 1):
        cube("Poster lightbox top and bottom bezel", (x, wall - depth / 2, z + sz * (height - bezel) / 2), (width - 2 * bezel, depth, bezel), alu, .003)
    photo = bpy.data.materials.new("Poster lightbox printed film")
    photo.use_nodes = True
    nt = photo.node_tree
    bs = _principled(photo)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(image), check_existing=True)
    nt.links.new(tex.outputs["Color"], bs.inputs["Base Color"])
    nt.links.new(tex.outputs["Color"], bs.inputs["Emission Color"])
    bs.inputs["Emission Strength"].default_value = 1.15
    bs.inputs["Roughness"].default_value = .10
    bs.inputs["Coat Weight"].default_value = .7
    bs.inputs["Coat Roughness"].default_value = .03
    bpy.ops.mesh.primitive_plane_add(size=1, location=(x, wall - depth + .003, z), rotation=(math.pi / 2, 0, 0))
    face = bpy.context.object
    face.name = "Poster lightbox acrylic face"
    face.scale = (width - 2 * bezel, height - 2 * bezel, 1)
    face.data.materials.append(photo)
    return face.name


def _torus(name, location, major, minor, mat, rotation=(math.pi / 2, 0, 0)):
    bpy = _bpy()
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=64, minor_segments=12,
                                     location=location, rotation=rotation)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(mat)
    for poly in ob.data.polygons:
        poly.use_smooth = True
    return ob


def fire_cabinet(x):
    """Recessed fire-hose cabinet: red steel case and door frame, clear glass, a reel of red rubber hose,
    a brass landing valve with red handwheel and a folded canvas hose roll inside; no lettering."""
    bpy = _bpy()
    from scene_environment import cube, cylinder, material
    wall = 5.108
    red = material("Fire cabinet red powder coat", (.23, .014, .010), .40)
    inside = material("Fire cabinet pale interior", (.42, .41, .39), .65)
    hose = material("Red rubber fire hose", (.34, .022, .014), .42)
    canvas = material("Folded canvas fire hose", (.58, .56, .50), .88)
    brass = material("Cast brass valve", (.62, .42, .17), .32, 1.0)
    steel = bpy.data.materials["Brushed satin stainless steel"]
    glass = material("Cabinet door clear glass", (.97, .98, .98), .01)
    gb = _principled(glass)
    gb.inputs["Transmission Weight"].default_value = 1.0
    gb.inputs["IOR"].default_value = 1.5
    w, d, h, z0 = .70, .24, 1.60, FLOOR_TOP
    yc = wall - d / 2
    t = .012
    cube("Fire hose cabinet back panel", (x, wall - t / 2, z0 + h / 2), (w, t, h), inside, .002)
    for sx in (-1, 1):
        cube("Fire hose cabinet side panel", (x + sx * (w / 2 - t / 2), yc, z0 + h / 2), (t, d, h), red, .003)
    for zz in (z0 + t / 2, z0 + h - t / 2):
        cube("Fire hose cabinet top and bottom panel", (x, yc, zz), (w, d, t), red, .003)
    cube("Fire hose cabinet shelf", (x, yc, z0 + .34), (w - 2 * t, d - t, t), inside, .002)
    shelf = z0 + .34 + t / 2
    # hose reel on a swing arm from the left side wall
    rx, rz, ry = x + .08, z0 + 1.08, yc + .01
    cylinder("Fire hose reel drum", (rx, ry, rz), .055, .085, red, "Y")
    for i in range(6):
        for dy in (-.021, .021):
            _torus("Fire hose reel coil", (rx, ry + dy, rz), .082 + i * .0195, .0095, hose)
    cube("Fire hose reel swing arm", ((x - w / 2 + t + rx) / 2, ry + .055, rz), (rx - (x - w / 2 + t), .02, .03), steel, .003)
    cylinder("Fire hose reel nozzle", (rx + .19, ry - .03, rz - .21), .014, .11, hose)
    cylinder("Fire hose reel nozzle brass tip", (rx + .19, ry - .03, rz - .275), .009, .03, brass)
    # landing valve on its standpipe, lower left
    vx, vz, vy = x - .20, z0 + .62, yc + .02
    cylinder("Fire hydrant standpipe", (vx, vy, (shelf + vz) / 2), .026, vz - shelf, red)        # stands on the shelf
    cylinder("Fire hydrant landing valve body", (vx, vy - .02, vz), .036, .09, brass, "Y")
    _torus("Fire hydrant valve handwheel", (vx, vy - .070, vz), .052, .0065, red)                # seated on the bonnet
    for a in (0.0, math.pi / 3, 2 * math.pi / 3):
        spoke = cube("Fire hydrant handwheel spoke", (vx, vy - .070, vz), (.10, .006, .006), red, .001)
        spoke.rotation_euler.y = a
    # folded canvas hose roll, lower right
    roll = cylinder("Folded canvas hose roll", (x + .13, yc + .015, shelf + .155), .155, .065, canvas, "Y")   # rests on the shelf
    # door: red frame, clear glass, steel latch handle
    front = wall - d - .006
    gz0, gz1 = z0 + .34, z0 + h - .08
    for sx in (-1, 1):
        cube("Fire hose cabinet door stile", (x + sx * (w / 2 - .03), front, z0 + h / 2), (.06, .014, h), red, .003)
    cube("Fire hose cabinet door top rail", (x, front, (gz1 + z0 + h) / 2), (w - .12, .014, z0 + h - gz1), red, .003)
    cube("Fire hose cabinet door bottom panel", (x, front, (z0 + gz0) / 2), (w - .12, .014, gz0 - z0), red, .003)
    cube("Fire hose cabinet door glazing", (x, front, (gz0 + gz1) / 2), (w - .12, .005, gz1 - gz0), glass, .001)
    cylinder("Fire hose cabinet door handle", (x + w / 2 - .055, front - .016, z0 + .90), .008, .13, steel)
    kick_grime(red, .25, .18)
    return True


def trash_bin(x, y):
    """Round brushed-steel litter bin with a dark lid ring and opening; stands on the floor."""
    bpy = _bpy()
    from scene_environment import cylinder
    steel = bpy.data.materials["Brushed satin stainless steel"]
    dark = bpy.data.materials["Dark graphite coated steel"]
    z = FLOOR_TOP
    cylinder("Litter bin plinth ring", (x, y, z + .0175), .155, .035, dark)
    cylinder("Litter bin brushed body", (x, y, z + .035 + .27), .160, .54, steel)
    cylinder("Litter bin lid ring", (x, y, z + .575 + .025), .165, .05, dark)
    cylinder("Litter bin dark opening", (x, y, z + .6255), .11, .002, bpy.data.materials["Deep tunnel liner"])
    return True


def wet_floor_sign(x, y, yaw_deg):
    """Yellow A-frame caution stand; the only marking is a warning triangle with an exclamation bar."""
    bpy = _bpy()
    from scene_environment import cube, cylinder, material
    yellow = material("Moulded yellow caution stand", (.62, .40, .02), .45)
    black = material("Caution pictogram black print", (.012, .012, .012), .5)
    root = bpy.data.objects.new("Caution stand", None)
    bpy.context.collection.objects.link(root)
    root.location = (x, y, FLOOR_TOP + .0015)   # panel feet rest on the tile surface
    root.rotation_euler.z = math.radians(yaw_deg)
    height, splay = .62, .15
    tilt = math.atan2(splay, height)
    length = math.hypot(splay, height)
    panels = []
    for side in (-1, 1):
        panel = cube("Caution stand panel", (0, side * splay / 2, height / 2), (.30, .012, length), yellow, .01)
        panel.rotation_euler.x = side * tilt
        panel.parent = root
        panels.append(panel)
    handle = cylinder("Caution stand handle", (0, 0, height + .015), .012, .16, yellow, "X")
    handle.parent = root
    # pictogram on the front panel (local -y face), drawn in the panel's own frame
    front = panels[0]
    tri = [(-.10, -.035), (.10, -.035), (0.0, .14)]
    inner = [(-.072, -.019), (.072, -.019), (0.0, .108)]
    mark = [_rect(0.0, .058, .016, .07), _rect(0.0, .002, .016, .016)]
    for name, polys, offset, mat in (("Caution pictogram triangle", [tri], -.0068, black),
                                     ("Caution pictogram field", [inner], -.0072, yellow),
                                     ("Caution pictogram mark", mark, -.0076, black)):
        ob = _flat(name, polys, offset, mat)
        ob.parent = front
    bpy.context.view_layer.update()
    return True


def glazed_walls():
    """Glazed wall panels: tone, gloss and relief from the scanned plaster_grey_04 maps (1.5 m tile)."""
    bpy = _bpy()
    out = []
    for name, base in (("Large ceramic wall panels", (.47, .475, .46)), ("Subway porcelain panel warm variation", (.45, .45, .43))):
        mat = bpy.data.materials.get(name)
        if mat is None:
            continue
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        nodes.clear()
        outp = nodes.new("ShaderNodeOutputMaterial")
        bs = nodes.new("ShaderNodeBsdfPrincipled")
        links.new(bs.outputs[0], outp.inputs[0])
        co = nodes.new("ShaderNodeTexCoord")
        scale = nodes.new("ShaderNodeVectorMath")
        scale.operation = "SCALE"
        scale.inputs["Scale"].default_value = 1 / 1.5
        links.new(co.outputs["Object"], scale.inputs[0])
        info = nodes.new("ShaderNodeObjectInfo")
        shift = nodes.new("ShaderNodeVectorMath")
        shift.operation = "MULTIPLY_ADD"
        shift.inputs[1].default_value = (7.3, 3.1, 5.7)
        links.new(info.outputs["Random"], shift.inputs[0])
        links.new(scale.outputs[0], shift.inputs[2])
        tex = {}
        for role in ("diff", "rough", "nor_gl"):
            t = nodes.new("ShaderNodeTexImage")
            t.image = bpy.data.images.load(str(PLASTER / f"plaster_grey_04_{role}_2k.jpg"), check_existing=True)
            if role != "diff":
                t.image.colorspace_settings.name = "Non-Color"
            t.projection = "BOX"
            t.projection_blend = .2
            links.new(shift.outputs[0], t.inputs["Vector"])
            tex[role] = t
        lum = nodes.new("ShaderNodeRGBToBW")
        links.new(tex["diff"].outputs["Color"], lum.inputs[0])
        tone = nodes.new("ShaderNodeMapRange")
        tone.inputs["From Min"].default_value, tone.inputs["From Max"].default_value = .25, .65
        tone.inputs["To Min"].default_value, tone.inputs["To Max"].default_value = .90, 1.06
        links.new(lum.outputs[0], tone.inputs["Value"])
        panel = nodes.new("ShaderNodeMapRange")       # each panel fired slightly differently
        panel.inputs["To Min"].default_value, panel.inputs["To Max"].default_value = .965, 1.035
        links.new(info.outputs["Random"], panel.inputs["Value"])
        both = nodes.new("ShaderNodeMath")
        both.operation = "MULTIPLY"
        links.new(tone.outputs[0], both.inputs[0])
        links.new(panel.outputs[0], both.inputs[1])
        colour = nodes.new("ShaderNodeVectorMath")
        colour.operation = "SCALE"
        colour.inputs[0].default_value = base
        links.new(both.outputs[0], colour.inputs["Scale"])
        links.new(colour.outputs[0], bs.inputs["Base Color"])
        rough = nodes.new("ShaderNodeMapRange")
        rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = .14, .34
        links.new(tex["rough"].outputs["Color"], rough.inputs["Value"])
        links.new(rough.outputs[0], bs.inputs["Roughness"])
        normal = nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = .12
        links.new(tex["nor_gl"].outputs["Color"], normal.inputs["Color"])
        links.new(normal.outputs[0], bs.inputs["Normal"])
        bs.inputs["Coat Weight"].default_value = .25
        bs.inputs["Coat Roughness"].default_value = .08
        out.append(name)
    return out


def scanner_edges():
    bpy = _bpy()
    radii = {"Scanner upper shell": (.022, 6), "Tunnel side shielding cabinet": (.010, 4),
             "Lower cabinet folded top return": (.004, 3), "Cabinet corner folded return": (.006, 3)}
    for ob in bpy.context.scene.objects:
        spec = radii.get(ob.name.split(".")[0])
        if spec and "Manufactured edge radius" in ob.modifiers:
            mod = ob.modifiers["Manufactured edge radius"]
            mod.width, mod.segments = spec
            mod.limit_method = "ANGLE"
    cream = bpy.data.materials["Warm grey fine powder-coat"]
    _principled(cream).inputs["Base Color"].default_value = (.50, .52, .51, 1)
    # anthracite end caps of the top cover and a two-piece cover seam, as on production scanners;
    # each cap stands 1 mm proud of the shell's end face, so the two faces never coincide
    from scene_environment import cube
    dark = bpy.data.materials["Dark graphite coated steel"]
    shell = bpy.data.objects.get("Scanner upper shell")
    if shell:
        lo, hi = _bounds(shell)
        for x in (lo[0] + .069, hi[0] - .069):
            cap = cube("Scanner hood anthracite end cap", (x, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2 + .001),
                       (.14, hi[1] - lo[1] + .004, hi[2] - lo[2] + .002), dark, .018)
        cube("Scanner hood cover seam", ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2] + .0002), (.003, hi[1] - lo[1] - .04, .0012), dark, 0)


def shoe_scuffs(mat, amount=.5, scale=2.2):
    """Black rubber sole marks: short curved streaks, sparse, darker and slightly glossier."""
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = _principled(mat)
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
    marks.inputs["Detail"].default_value = 3.0
    l.new(stretch.outputs[0], marks.inputs["Vector"])
    mask = n.new("ShaderNodeMapRange")
    mask.inputs["From Min"].default_value = .70
    mask.inputs["From Max"].default_value = .76
    mask.inputs["To Max"].default_value = amount
    l.new(marks.outputs["Fac"], mask.inputs["Value"])
    color = bs.inputs["Base Color"]
    src = color.links[0].from_socket if color.is_linked else None
    dark = n.new("ShaderNodeMixRGB")
    dark.inputs[2].default_value = (.02, .018, .016, 1)
    l.new(mask.outputs[0], dark.inputs[0])
    if src:
        l.new(src, dark.inputs[1])
    else:
        dark.inputs[1].default_value = tuple(color.default_value)
    l.new(dark.outputs[0], color)


def apply(p, c, curtain, bags):
    bpy = _bpy()
    mats = bpy.data.materials
    removed = strip_text()
    sign = pictogram_sign()
    walls = glazed_walls()
    for name in walls:
        kick_grime(mats[name], .32, .22)
    kick_grime(mats.get("Utility door satin powder coating"), .30, .20)
    floor = granite_floor()
    scanner_edges()
    for name, (sm, gr, sc, s) in WEAR.items():
        if name in mats:
            kit.add_surface_wear(mats[name], smudge=sm, grime=gr, scratch=sc, scale=s)
    scanner_wear()
    screws = scanner_hardware()
    belt_loop = belt_texture()
    strips = curtain_strips(curtain)
    stainless_finish()
    box = lightbox(-0.35, 1.62, 1.00, 1.50, LOOK_ASSETS / "lightbox_kloofendal_portrait.jpg")
    cabinet = fire_cabinet(-1.85)
    trash_bin(-4.70, 0.85)
    wet_floor_sign(-3.90, 0.95, 52.0)
    lights = relight()
    bpy.context.view_layer.update()
    bpy.context.scene["look"] = "station_look"
    return {"look": "station_look", "text_objects_removed": removed, "pictogram_sign": sign, "glazed_walls": walls,
            "floor": floor, "hatch_screws": screws, "belt_loop_m": belt_loop, "curtain_materials": strips,
            "luminaire_lights": lights, "led_w_per_m": LED_W_PER_M, "wash_w_per_m": WASH_W_PER_M,
            "lightbox": box, "fire_cabinet": cabinet, "props": ["litter bin", "caution stand"],
            "view_look": VIEW_LOOK, "exposure": EXPOSURE, "adaptive_threshold": .01,
            "assets": ["ambientcg/Granite002A", "ambientcg/Rubber002", "polyhaven/plaster_grey_04",
                       "scenes/metro_security_bag_curtain/station_look"]}


def finish(tree, image):
    """Faint fog glow around the luminaires, mild lateral colour and vignette; returns the Composite input."""
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.mix = -.88
    glare.threshold = 1.0
    glare.size = 8
    tree.links.new(image, glare.inputs["Image"])
    lens = tree.nodes.new("CompositorNodeLensdist")
    lens.use_fit = True
    lens.inputs["Distortion"].default_value = 0.0
    lens.inputs["Dispersion"].default_value = .003
    tree.links.new(glare.outputs["Image"], lens.inputs["Image"])
    mask = tree.nodes.new("CompositorNodeEllipseMask")
    mask.width, mask.height = 1.18, 1.32
    blur = tree.nodes.new("CompositorNodeBlur")
    blur.filter_type = "GAUSS"
    blur.use_relative = True
    blur.factor_x = blur.factor_y = 30.0
    tree.links.new(mask.outputs["Mask"], blur.inputs["Image"])
    level = tree.nodes.new("CompositorNodeMapRange")
    level.inputs["To Min"].default_value = .84
    level.inputs["To Max"].default_value = 1.0
    tree.links.new(blur.outputs["Image"], level.inputs["Value"])
    mix = tree.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    tree.links.new(lens.outputs["Image"], mix.inputs[1])
    tree.links.new(level.outputs[0], mix.inputs[2])
    return mix.outputs[0]
