"""Current look of football_goal_net, applied by appearance/render.py after the scene build.

Appearance only. Nothing here moves an object, changes a mesh, a key, the camera pose, the lens or the
solver state; the net, ball and turf bindings are re-checked by render.py on every frame.

- Light: the hazy midday of the stadium photograph. The sun keeps the photograph's own direction
  (render.py's backdrop step rotates it with the panorama) and gets the soft disc of a hazy sky;
  the panorama keeps lighting the scene.
- Pitch: natural grass in the colour of the photographed pitch (light, yellowish and not very
  saturated), broad mowing bands parallel to the goal line, metre-scale drift, centimetre tussocks and blades
  (colour and a slight relief) and a worn
  goalmouth (thin, dry patches in front of the goal). Shader colour only; the tufts are unchanged.
- Perimeter behind the goal: the frozen collision surfaces are drawn as switched-off LED boards
  (black satin modules with frame joints) in front of a painted concrete wall, no print.
- Ball: clean off-white PU panels with light scuffs and black pentagons.
- Training rebound board (only for a cache that contains the board; no published case does): rounded white HDPE panel, slightly glossy, with
  scratches and faint ball marks, bolted to galvanised uprights; render-only A-frame struts, ground
  runners, cross tubes and anchor bolts behind and below it (the five collider boxes are unchanged).
- Stadium photograph: a little more contrast and colour, as a camera would record it.
- Camera: the build's pose, lens and focus point; aperture f/4 (camera.py's recipe has f/5.6).
- Output: AgX Medium High Contrast, exposure +0.35, mild vignette and lateral colour.
"""
import math

SUN_ENERGY = 10.0
SUN_ANGLE_DEG = 2.0
SUN_COLOR = (1.0, 0.965, 0.91)
WORLD_STRENGTH = 1.3
EXPOSURE = 0.35
F_STOP = 4.0

TURF = {
    "hue": 0.476, "saturation": 0.70, "value": 1.55,        # towards the photographed pitch
    "stripe_m": 5.5, "stripe_low": 0.86, "stripe_high": 1.10, # mowing bands along the goal line (y)
    "drift_scale": 0.09, "drift": (0.92, 1.07),               # metre-scale tonal drift
    "clump_scale": 2.2, "clump": (0.94, 1.05),                # decimetre clumping of the sward
    "tussock_scale": 14.0, "tussock": (0.76, 1.20),           # 3-10 cm tussocks
    "blade_scale": 55.0, "blade": (0.62, 1.30),               # single blades / gaps to the soil
    "tip_scale": 90.0, "tip": 1.30,                           # sunlit blade tips (sparse bright specks)
    "wear_centre": (0.3, -3.2), "wear_radius": (4.2, 3.6),    # goalmouth in front of the goal line
    "wear_color": (0.30, 0.27, 0.13), "wear_max": 0.55,
}


def _nodes(mat):
    return mat.node_tree.nodes, mat.node_tree.links


def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _math(nodes, op, a=None, b=None, clamp=False):
    n = nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    if a is not None and not hasattr(a, "links"):
        n.inputs[0].default_value = a
    if b is not None and not hasattr(b, "links"):
        n.inputs[1].default_value = b
    return n


def light(scene):
    sun = next(o for o in scene.objects if o.type == "LIGHT" and o.data.type == "SUN")
    sun.data.energy, sun.data.color = SUN_ENERGY, SUN_COLOR
    sun.data.angle = math.radians(SUN_ANGLE_DEG)
    shadow_before = [sun.data.use_shadow, getattr(sun.data.cycles, "cast_shadow", None), sun.visible_shadow if hasattr(sun, "visible_shadow") else None]
    sun.data.use_shadow = True
    if hasattr(sun.data.cycles, "cast_shadow"):
        sun.data.cycles.cast_shadow = True
    background = next(n for n in scene.world.node_tree.nodes if n.type == "BACKGROUND")
    background.inputs["Strength"].default_value = WORLD_STRENGTH
    to_sun = sun.matrix_world.to_3x3().col[2]
    return {"sun": sun.name, "to_sun": [round(v, 4) for v in to_sun], "energy": SUN_ENERGY,
            "angle_deg": SUN_ANGLE_DEG, "world_strength": WORLD_STRENGTH, "shadow_flags_before": shadow_before}


def turf_color(mat):
    """Re-colour one turf material: hue/saturation/value, mowing bands, drift and goalmouth wear."""
    nodes, links = _nodes(mat)
    base = _principled(mat).inputs["Base Color"]
    if base.is_linked:
        source = base.links[0].from_socket
    else:
        rgb = nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = tuple(base.default_value)
        source = rgb.outputs[0]
    T = TURF
    hsv = nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Hue"].default_value = T["hue"]
    hsv.inputs["Saturation"].default_value = T["saturation"]
    hsv.inputs["Value"].default_value = T["value"]
    links.new(source, hsv.inputs["Color"])
    geo = nodes.new("ShaderNodeNewGeometry")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geo.outputs["Position"], sep.inputs["Vector"])
    # mowing bands: soft-edged alternation every stripe_m metres along y
    band = _math(nodes, "DIVIDE", b=T["stripe_m"])
    links.new(sep.outputs["Y"], band.inputs[0])
    tri = _math(nodes, "PINGPONG", b=1.0)
    links.new(band.outputs[0], tri.inputs[0])
    edge = nodes.new("ShaderNodeMapRange")
    edge.interpolation_type = "SMOOTHSTEP"
    edge.inputs["From Min"].default_value, edge.inputs["From Max"].default_value = 0.475, 0.525
    edge.inputs["To Min"].default_value, edge.inputs["To Max"].default_value = T["stripe_low"], T["stripe_high"]
    links.new(tri.outputs[0], edge.inputs["Value"])
    # metre-scale tonal drift
    drift = nodes.new("ShaderNodeTexNoise")
    drift.inputs["Scale"].default_value = T["drift_scale"]
    drift.inputs["Detail"].default_value = 4.0
    drift.inputs["Roughness"].default_value = 0.55
    links.new(geo.outputs["Position"], drift.inputs["Vector"])
    patch = nodes.new("ShaderNodeMapRange")
    patch.inputs["From Min"].default_value, patch.inputs["From Max"].default_value = 0.35, 0.65
    patch.inputs["To Min"].default_value, patch.inputs["To Max"].default_value = T["drift"]
    links.new(drift.outputs["Fac"], patch.inputs["Value"])
    # sub-metre clumping of the sward (decimetre scale), so the bands are not flat paint
    clump = nodes.new("ShaderNodeTexNoise")
    clump.inputs["Scale"].default_value = T["clump_scale"]
    clump.inputs["Detail"].default_value = 3.0
    links.new(geo.outputs["Position"], clump.inputs["Vector"])
    grain = nodes.new("ShaderNodeMapRange")
    grain.inputs["From Min"].default_value, grain.inputs["From Max"].default_value = 0.3, 0.7
    grain.inputs["To Min"].default_value, grain.inputs["To Max"].default_value = T["clump"]
    links.new(clump.outputs["Fac"], grain.inputs["Value"])
    gain0 = _math(nodes, "MULTIPLY")
    links.new(edge.outputs[0], gain0.inputs[0])
    links.new(patch.outputs[0], gain0.inputs[1])
    gain1 = _math(nodes, "MULTIPLY")
    links.new(gain0.outputs[0], gain1.inputs[0])
    links.new(grain.outputs[0], gain1.inputs[1])
    # sward texture: tussocks of a few centimetres to a decimetre and single blades, aperiodic world-space
    # noise (no lattice, so no moire against the tuft grid), stronger on the leaves than on the soil
    gain = gain1
    for scale, low_high in ((T["tussock_scale"], T["tussock"]), (T["blade_scale"], T["blade"])):
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 2.0
        tex.inputs["Roughness"].default_value = 0.6
        links.new(geo.outputs["Position"], tex.inputs["Vector"])
        rng = nodes.new("ShaderNodeMapRange")
        rng.inputs["From Min"].default_value, rng.inputs["From Max"].default_value = 0.38, 0.62
        rng.inputs["To Min"].default_value, rng.inputs["To Max"].default_value = low_high
        links.new(tex.outputs["Fac"], rng.inputs["Value"])
        nxt = _math(nodes, "MULTIPLY")
        links.new(gain.outputs[0], nxt.inputs[0])
        links.new(rng.outputs[0], nxt.inputs[1])
        gain = nxt
        if scale == T["tussock_scale"]:
            tussock = tex
    # sparse bright specks: blade tips catching the light (Voronoi cells about 1 cm)
    tips = nodes.new("ShaderNodeTexVoronoi")
    tips.inputs["Scale"].default_value = T["tip_scale"]
    links.new(geo.outputs["Position"], tips.inputs["Vector"])
    speck = nodes.new("ShaderNodeMapRange")
    speck.interpolation_type = "SMOOTHSTEP"
    speck.inputs["From Min"].default_value, speck.inputs["From Max"].default_value = 0.0, 0.22
    speck.inputs["To Min"].default_value, speck.inputs["To Max"].default_value = T["tip"], 1.0
    links.new(tips.outputs["Distance"], speck.inputs["Value"])
    lit = _math(nodes, "MULTIPLY")
    links.new(gain.outputs[0], lit.inputs[0])
    links.new(speck.outputs[0], lit.inputs[1])
    gain = lit
    # the same tussocks as a slight relief of the sward surface
    surface = _principled(mat)
    relief = nodes.new("ShaderNodeBump")
    relief.inputs["Strength"].default_value, relief.inputs["Distance"].default_value = 0.25, 0.004
    if surface.inputs["Normal"].is_linked:
        links.new(surface.inputs["Normal"].links[0].from_socket, relief.inputs["Normal"])
    links.new(tussock.outputs["Fac"], relief.inputs["Height"])
    links.new(relief.outputs["Normal"], surface.inputs["Normal"])
    scaled = nodes.new("ShaderNodeVectorMath")
    scaled.operation = "SCALE"
    links.new(hsv.outputs["Color"], scaled.inputs[0])
    links.new(gain.outputs[0], scaled.inputs["Scale"])
    # goalmouth wear: an elliptical zone in front of the goal, broken into irregular dry patches
    cx, cy = T["wear_centre"]
    rx, ry = T["wear_radius"]
    dx = _math(nodes, "SUBTRACT", b=cx)
    links.new(sep.outputs["X"], dx.inputs[0])
    dy = _math(nodes, "SUBTRACT", b=cy)
    links.new(sep.outputs["Y"], dy.inputs[0])
    nx = _math(nodes, "DIVIDE", b=rx)
    links.new(dx.outputs[0], nx.inputs[0])
    ny = _math(nodes, "DIVIDE", b=ry)
    links.new(dy.outputs[0], ny.inputs[0])
    nx2 = _math(nodes, "MULTIPLY")
    links.new(nx.outputs[0], nx2.inputs[0]); links.new(nx.outputs[0], nx2.inputs[1])
    ny2 = _math(nodes, "MULTIPLY")
    links.new(ny.outputs[0], ny2.inputs[0]); links.new(ny.outputs[0], ny2.inputs[1])
    r2 = _math(nodes, "ADD")
    links.new(nx2.outputs[0], r2.inputs[0]); links.new(ny2.outputs[0], r2.inputs[1])
    zone = nodes.new("ShaderNodeMapRange")
    zone.interpolation_type = "SMOOTHSTEP"
    zone.inputs["From Min"].default_value, zone.inputs["From Max"].default_value = 1.0, 0.25
    zone.inputs["To Min"].default_value, zone.inputs["To Max"].default_value = 0.0, 1.0
    links.new(r2.outputs[0], zone.inputs["Value"])
    blotch = nodes.new("ShaderNodeTexNoise")
    blotch.inputs["Scale"].default_value = 1.6
    blotch.inputs["Detail"].default_value = 6.0
    blotch.inputs["Roughness"].default_value = 0.62
    links.new(geo.outputs["Position"], blotch.inputs["Vector"])
    holes = nodes.new("ShaderNodeMapRange")
    holes.interpolation_type = "SMOOTHSTEP"
    holes.inputs["From Min"].default_value, holes.inputs["From Max"].default_value = 0.47, 0.66
    links.new(blotch.outputs["Fac"], holes.inputs["Value"])
    wear = _math(nodes, "MULTIPLY", clamp=True)
    links.new(zone.outputs[0], wear.inputs[0]); links.new(holes.outputs[0], wear.inputs[1])
    amount = _math(nodes, "MULTIPLY", b=T["wear_max"])
    links.new(wear.outputs[0], amount.inputs[0])
    dry = nodes.new("ShaderNodeMix")
    dry.data_type = "RGBA"
    dry.inputs[7].default_value = (*T["wear_color"], 1.0)
    links.new(amount.outputs[0], dry.inputs[0])
    links.new(scaled.outputs[0], dry.inputs[6])
    links.new(dry.outputs[2], base)
    for translucent in [n for n in nodes if n.type == "BSDF_TRANSLUCENT"]:
        links.new(dry.outputs[2], translucent.inputs["Color"])


def grade_backdrop(mat):
    """The re-projected photograph is flat and milky; give it the contrast a camera would record."""
    nodes, links = _nodes(mat)
    emission = next(n for n in nodes if n.type == "EMISSION")
    socket = emission.inputs["Color"]
    source = socket.links[0].from_socket
    gamma = nodes.new("ShaderNodeGamma")
    gamma.inputs["Gamma"].default_value = 1.28
    contrast = nodes.new("ShaderNodeBrightContrast")
    contrast.inputs["Bright"].default_value, contrast.inputs["Contrast"].default_value = -0.02, 0.13
    sat = nodes.new("ShaderNodeHueSaturation")
    sat.inputs["Saturation"].default_value = 1.15
    links.new(source, gamma.inputs["Color"])
    links.new(gamma.outputs["Color"], contrast.inputs["Color"])
    links.new(contrast.outputs["Color"], sat.inputs["Color"])
    links.new(sat.outputs["Color"], socket)


def led_boards(bpy):
    """Switched-off LED perimeter boards: black satin modules, aluminium joints every 0.96 m, dust low down."""
    mat = bpy.data.materials.new("Look perimeter LED boards (switched off)")
    mat.use_nodes = True
    nodes, links = _nodes(mat)
    bsdf = _principled(mat)
    geo = nodes.new("ShaderNodeNewGeometry")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geo.outputs["Position"], sep.inputs["Vector"])
    module = _math(nodes, "DIVIDE", b=0.96)
    links.new(sep.outputs["X"], module.inputs[0])
    frac = _math(nodes, "FRACT")
    links.new(module.outputs[0], frac.inputs[0])
    dist = _math(nodes, "PINGPONG", b=0.5)        # 0 at a joint, 0.5 mid-module
    links.new(frac.outputs[0], dist.inputs[0])
    joint = _math(nodes, "LESS_THAN", b=0.012)
    links.new(dist.outputs[0], joint.inputs[0])
    dust = nodes.new("ShaderNodeMapRange")
    dust.inputs["From Min"].default_value, dust.inputs["From Max"].default_value = 0.0, 0.35
    dust.inputs["To Min"].default_value, dust.inputs["To Max"].default_value = 1.0, 0.0
    links.new(sep.outputs["Z"], dust.inputs["Value"])
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    noise.inputs["Detail"].default_value = 5.0
    links.new(geo.outputs["Position"], noise.inputs["Vector"])
    face = nodes.new("ShaderNodeMix"); face.data_type = "RGBA"
    face.inputs[6].default_value = (0.010, 0.011, 0.012, 1)
    face.inputs[7].default_value = (0.055, 0.052, 0.045, 1)      # grass-side dust
    dusty = _math(nodes, "MULTIPLY", b=0.6)
    links.new(dust.outputs[0], dusty.inputs[0])
    links.new(dusty.outputs[0], face.inputs[0])
    col = nodes.new("ShaderNodeMix"); col.data_type = "RGBA"
    links.new(joint.outputs[0], col.inputs[0])
    links.new(face.outputs[2], col.inputs[6])
    col.inputs[7].default_value = (0.32, 0.33, 0.34, 1)           # anodised joint strip
    links.new(col.outputs[2], bsdf.inputs["Base Color"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = 0.30, 0.46
    links.new(noise.outputs["Fac"], rough.inputs["Value"])
    rmix = _math(nodes, "MAXIMUM")
    links.new(rough.outputs[0], rmix.inputs[0])
    links.new(dust.outputs[0], rmix.inputs[1])
    rclamp = _math(nodes, "MINIMUM", b=0.75)
    links.new(rmix.outputs[0], rclamp.inputs[0])
    links.new(rclamp.outputs[0], bsdf.inputs["Roughness"])
    return mat


def painted_wall(bpy):
    """Painted concrete behind the boards: dark grey-green paint, roller tone drift, rain streaks."""
    mat = bpy.data.materials.new("Look painted concrete perimeter wall")
    mat.use_nodes = True
    nodes, links = _nodes(mat)
    bsdf = _principled(mat)
    geo = nodes.new("ShaderNodeNewGeometry")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.4
    noise.inputs["Detail"].default_value = 8.0
    links.new(geo.outputs["Position"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.050, 0.060, 0.056, 1)
    ramp.color_ramp.elements[1].color = (0.085, 0.096, 0.090, 1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.82
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = 0.002
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 60.0
    links.new(geo.outputs["Position"], fine.inputs["Vector"])
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def perimeter(bpy, scene):
    boards, wall = led_boards(bpy), painted_wall(bpy)
    concrete = next((m for m in bpy.data.materials if m.name.startswith("maintained cast concrete")), wall)
    changed = {}
    for obj in scene.objects:
        if not obj.name.startswith("frozen physical surface"):
            continue
        for slot in obj.material_slots:
            old = slot.material.name if slot.material else None
            if obj.name.endswith("Material2.026"):
                new = concrete                      # coping on top of the wall
            elif old and old.startswith(("auto_25",)):
                new = wall
            else:
                new = boards                        # former printed panels and black board backs
            slot.link = "OBJECT"
            slot.material = new
            changed.setdefault(obj.name, []).append([old, new.name])
    return changed


def ball(bpy):
    """Clean off-white PU panels with light scuffs; black pentagons satin. No image textures."""
    white = bpy.data.materials["soccer_ball_white_parts"]
    nodes, links = _nodes(white)
    target = next(n for n in nodes if n.type == "BSDF_PRINCIPLED" and n.inputs["Base Color"].is_linked)
    for link in list(target.inputs["Base Color"].links) + list(target.inputs["Roughness"].links):
        links.remove(link)
    geo = nodes.new("ShaderNodeTexCoord")
    scuff = nodes.new("ShaderNodeTexNoise")
    scuff.inputs["Scale"].default_value = 9.0
    scuff.inputs["Detail"].default_value = 8.0
    links.new(geo.outputs["Object"], scuff.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.80, 0.80, 0.77, 1)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (0.62, 0.63, 0.57, 1)   # faint grass/dust scuffs
    links.new(scuff.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], target.inputs["Base Color"])
    target.inputs["Roughness"].default_value = 0.42
    for mix in [n for n in nodes if n.type == "MIX_SHADER"]:       # the dirt-map mask over a black shader
        for link in list(mix.inputs[0].links):
            links.remove(link)
        first = mix.inputs[1].links[0].from_node if mix.inputs[1].is_linked else None
        mix.inputs[0].default_value = 0.0 if first == target else 1.0
    black = bpy.data.materials["soccer_ball_black_parts"]
    bb = _principled(black)
    for link in list(bb.inputs["Roughness"].links):
        black.node_tree.links.remove(link)
    bb.inputs["Roughness"].default_value = 0.45
    removed = []
    for mat in (white, black):
        for n in [n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeTexImage"]:
            removed.append(n.image.name if n.image else None)
            mat.node_tree.nodes.remove(n)
    return {"dirt_map_nodes_removed": removed}


BOARD_MARKS = ((0.46, 1.04), (0.74, 0.88), (0.30, 0.74), (0.97, 1.12), (0.60, 0.56), (0.18, 1.08))   # (x, z) of ball marks


def _hdpe(bpy):
    """White HDPE, a little glossy: fine scratches, a few faint ball marks."""
    mat = bpy.data.materials.new("Look rebound board | white HDPE")
    mat.use_nodes = True
    nodes, links = _nodes(mat)
    bsdf = _principled(mat)
    geo = nodes.new("ShaderNodeNewGeometry")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geo.outputs["Position"], sep.inputs["Vector"])
    # ball marks: soft discs about 22 cm across, broken up by noise
    marks = None
    for mx, mz in BOARD_MARKS:
        cx = _math(nodes, "SUBTRACT", b=mx); links.new(sep.outputs["X"], cx.inputs[0])
        cz = _math(nodes, "SUBTRACT", b=mz); links.new(sep.outputs["Z"], cz.inputs[0])
        d = nodes.new("ShaderNodeVectorMath"); d.operation = "LENGTH"
        comb = nodes.new("ShaderNodeCombineXYZ")
        links.new(cx.outputs[0], comb.inputs["X"]); links.new(cz.outputs[0], comb.inputs["Y"])
        links.new(comb.outputs[0], d.inputs[0])
        disc = nodes.new("ShaderNodeMapRange"); disc.interpolation_type = "SMOOTHSTEP"
        disc.inputs["From Min"].default_value, disc.inputs["From Max"].default_value = 0.115, 0.03
        links.new(d.outputs["Value"], disc.inputs["Value"])
        marks = disc if marks is None else _join_max(nodes, links, marks, disc)
    breakup = nodes.new("ShaderNodeTexNoise"); breakup.inputs["Scale"].default_value = 18.0; breakup.inputs["Detail"].default_value = 6.0
    links.new(geo.outputs["Position"], breakup.inputs["Vector"])
    mask = _math(nodes, "MULTIPLY", clamp=True); links.new(marks.outputs[0], mask.inputs[0]); links.new(breakup.outputs["Fac"], mask.inputs[1])
    amount = _math(nodes, "MULTIPLY", b=0.38); links.new(mask.outputs[0], amount.inputs[0])
    # fine horizontal scratches (stretched noise) and slight tonal drift
    stretch = nodes.new("ShaderNodeMapping"); stretch.inputs["Scale"].default_value = (2.0, 60.0, 90.0)
    links.new(geo.outputs["Position"], stretch.inputs["Vector"])
    scratch = nodes.new("ShaderNodeTexNoise"); scratch.inputs["Scale"].default_value = 6.0; scratch.inputs["Detail"].default_value = 8.0
    links.new(stretch.outputs[0], scratch.inputs["Vector"])
    lines = nodes.new("ShaderNodeMapRange"); lines.inputs["From Min"].default_value, lines.inputs["From Max"].default_value = 0.62, 0.75
    links.new(scratch.outputs["Fac"], lines.inputs["Value"])
    base = nodes.new("ShaderNodeMix"); base.data_type = "RGBA"
    base.inputs[6].default_value = (0.80, 0.81, 0.79, 1)
    base.inputs[7].default_value = (0.47, 0.46, 0.42, 1)
    links.new(amount.outputs[0], base.inputs[0])
    scr = nodes.new("ShaderNodeMix"); scr.data_type = "RGBA"
    links.new(base.outputs[2], scr.inputs[6]); scr.inputs[7].default_value = (0.70, 0.71, 0.69, 1)
    sa = _math(nodes, "MULTIPLY", b=0.5); links.new(lines.outputs[0], sa.inputs[0]); links.new(sa.outputs[0], scr.inputs[0])
    links.new(scr.outputs[2], bsdf.inputs["Base Color"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = 0.24, 0.52
    rsum = _math(nodes, "ADD", clamp=True); links.new(lines.outputs[0], rsum.inputs[0]); links.new(mask.outputs[0], rsum.inputs[1])
    links.new(rsum.outputs[0], rough.inputs["Value"])
    links.new(rough.outputs[0], bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    return mat


def _join_max(nodes, links, a, b):
    m = _math(nodes, "MAXIMUM")
    links.new(a.outputs[0], m.inputs[0]); links.new(b.outputs[0], m.inputs[1])
    return m


def _galvanised(bpy):
    """Hot-dip galvanised steel: metallic grey with spangle and some ground dirt at the bottom."""
    mat = bpy.data.materials.new("Look rebound board | galvanised steel")
    mat.use_nodes = True
    nodes, links = _nodes(mat)
    bsdf = _principled(mat)
    geo = nodes.new("ShaderNodeNewGeometry")
    spangle = nodes.new("ShaderNodeTexVoronoi"); spangle.inputs["Scale"].default_value = 35.0
    links.new(geo.outputs["Position"], spangle.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.56, 0.57, 0.56, 1)
    ramp.color_ramp.elements[1].color = (0.70, 0.71, 0.70, 1)
    links.new(spangle.outputs["Distance"], ramp.inputs["Fac"])
    sep = nodes.new("ShaderNodeSeparateXYZ"); links.new(geo.outputs["Position"], sep.inputs["Vector"])
    dirt = nodes.new("ShaderNodeMapRange"); dirt.inputs["From Min"].default_value, dirt.inputs["From Max"].default_value = 0.0, 0.08
    dirt.inputs["To Min"].default_value, dirt.inputs["To Max"].default_value = 0.45, 0.0
    links.new(sep.outputs["Z"], dirt.inputs["Value"])
    col = nodes.new("ShaderNodeMix"); col.data_type = "RGBA"
    links.new(dirt.outputs[0], col.inputs[0]); links.new(ramp.outputs["Color"], col.inputs[6])
    col.inputs[7].default_value = (0.20, 0.19, 0.15, 1)
    links.new(col.outputs[2], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 1.0
    rough = nodes.new("ShaderNodeMapRange"); rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = 0.30, 0.52
    links.new(spangle.outputs["Distance"], rough.inputs["Value"])
    links.new(rough.outputs[0], bsdf.inputs["Roughness"])
    return mat


def _mesh_object(bpy, name, verts, faces, mat, parent, smooth=False):
    import bmesh
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    bm = bmesh.new(); bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh); bm.free()
    if smooth:
        mesh.shade_smooth()
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    obj["pcve_role"] = "render_only_detail_of_training_rebound_board"
    return obj


def _prism(bpy, name, a, b, radius, sides, mat, parent, smooth=True):
    """Closed prism (tube with caps) from point a to point b."""
    from mathutils import Vector
    a, b = Vector(a), Vector(b)
    axis = (b - a).normalized()
    helper = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(helper).normalized()
    v = axis.cross(u)
    ring = [(u * math.cos(2 * math.pi * k / sides) + v * math.sin(2 * math.pi * k / sides)) * radius for k in range(sides)]
    verts = [tuple(a + r) for r in ring] + [tuple(b + r) for r in ring]
    faces = [(k, (k + 1) % sides, sides + (k + 1) % sides, sides + k) for k in range(sides)]
    faces += [tuple(range(sides))[::-1], tuple(range(sides, 2 * sides))]
    return _mesh_object(bpy, name, verts, faces, mat, parent, smooth=smooth)


def _rounded_slab(bpy, obj, radius=0.07, segments=8):
    """Same extents as the collider box, with rounded corners in the panel plane."""
    co = [obj.matrix_world @ v.co for v in obj.data.vertices]
    lo = [min(c[i] for c in co) for i in range(3)]
    hi = [max(c[i] for c in co) for i in range(3)]
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    hx, hz = (hi[0] - lo[0]) / 2, (hi[2] - lo[2]) / 2
    outline = []
    for ox, oz, a0 in ((hx - radius, hz - radius, 0), (-hx + radius, hz - radius, 90),
                       (-hx + radius, -hz + radius, 180), (hx - radius, -hz + radius, 270)):
        for k in range(segments + 1):
            a = math.radians(a0 + 90 * k / segments)
            outline.append((cx + ox + radius * math.cos(a), cz + oz + radius * math.sin(a)))
    n = len(outline)
    verts = [(x, lo[1], z) for x, z in outline] + [(x, hi[1], z) for x, z in outline]
    faces = [tuple(range(n)), tuple(range(n, 2 * n))[::-1]] + [(i, n + i, n + (i + 1) % n, (i + 1) % n) for i in range(n)]
    import bmesh
    mesh = bpy.data.meshes.new("Look rounded HDPE rebound panel")
    mesh.from_pydata(verts, [], faces)
    bm = bmesh.new(); bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh); bm.free()
    from mathutils import Matrix
    obj.matrix_world = Matrix.Identity(4)
    obj.data = mesh
    bevel = obj.modifiers.new("soft moulded edges", "BEVEL")
    bevel.width, bevel.segments, bevel.limit_method = 0.006, 3, "ANGLE"
    return {"bbox_min": lo, "bbox_max": hi, "corner_radius_m": radius}


def training_board(bpy, state):
    """add_training_board only: the five collider boxes drawn as a real rebounder; supports added behind it."""
    parts = {o.name.rsplit("/ ", 1)[-1]: o for o in bpy.data.objects if o.name.startswith("ADDED training_rebound_board / ")}
    if not parts:
        return None
    root = parts["panel"].parent
    hdpe, steel = _hdpe(bpy), _galvanised(bpy)
    record = {"panel": _rounded_slab(bpy, parts["panel"])}
    parts["panel"].data.materials.clear(); parts["panel"].data.materials.append(hdpe)
    for key in ("upright_left", "upright_right", "foot_left", "foot_right"):
        parts[key].data.materials.clear(); parts[key].data.materials.append(steel)
    added = []
    front = record["panel"]["bbox_min"][1]
    for xu in (-0.12, 1.28):
        for zb in (0.30, 0.68):              # carriage bolts through the panel into each upright
            added.append(_prism(bpy, "bolt washer", (xu, front, zb), (xu, front - 0.002, zb), 0.017, 16, steel, root))
            added.append(_prism(bpy, "bolt head", (xu, front - 0.002, zb), (xu, front - 0.009, zb), 0.011, 6, steel, root, smooth=False))
        # A-frame: rear strut from the upright top to the ground, ground runner from the footplate
        added.append(_prism(bpy, "rear strut", (xu, 0.43, 0.74), (xu, 1.02, 0.024), 0.0165, 16, steel, root))
        added.append(_prism(bpy, "ground runner", (xu, 0.54, 0.0215), (xu, 1.10, 0.0215), 0.0165, 16, steel, root))
        for yb in (0.33, 0.47):              # footplate anchor bolts
            for dx in (-0.07, 0.07):
                added.append(_prism(bpy, "anchor bolt", (xu + dx, yb, 0.012), (xu + dx, yb, 0.022), 0.009, 6, steel, root, smooth=False))
    added.append(_prism(bpy, "low cross tube", (-0.09, 0.40, 0.055), (1.25, 0.40, 0.055), 0.0165, 16, steel, root))
    added.append(_prism(bpy, "rear cross tube", (-0.12, 0.98, 0.07), (1.28, 0.98, 0.07), 0.0165, 16, steel, root))
    # none of the visual additions may come near any ball centre of this case (ball radius 0.11 m)
    import numpy as np
    balls = np.asarray(state["cache"]["ball_positions"])
    clearance = []
    for obj in added:
        pts = np.array([obj.matrix_world @ v.co for v in obj.data.vertices])
        clearance.append(float(np.min(np.linalg.norm(balls[:, None, :] - pts[None, :, :], axis=2))))
    if min(clearance) < 0.11 + 0.02:
        raise RuntimeError(f"Rebound-board detail too close to the ball path: {min(clearance)}")
    record.update(render_only_parts=len(added), min_distance_ball_centre_to_added_parts_m=min(clearance),
                  colliders_unchanged="the five preset boxes keep their extents; the panel corners are rounded (r 0.07 m) "
                                      "and its edges softened (6 mm); bolts, struts, runners and cross tubes are render-only")
    return record


def apply(bpy, scene, state):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    import pcve_realism_kit as kit
    record = {"light": light(scene)}
    record["objects_without_shadow"] = [o.name for o in scene.objects if o.type in {"MESH", "CURVE"} and not o.hide_render and not o.visible_shadow][:40]
    turf = [m for m in bpy.data.materials if m.users and m.use_nodes and m.name.startswith(
        ("canopy", "leaves", "fine living grass"))]
    for mat in turf:
        turf_color(mat)
    record["turf_materials"] = [m.name for m in turf]
    grade_backdrop(next(m for m in bpy.data.materials if m.name.startswith("camera-only stadium photograph")))
    record["perimeter"] = perimeter(bpy, scene)
    record["ball"] = ball(bpy)
    record["training_board"] = training_board(bpy, state)
    cam = scene.camera.data
    record["camera_f_stop"] = [cam.dof.aperture_fstop, F_STOP]
    cam.dof.aperture_fstop = F_STOP
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = EXPOSURE
    kit.lens_finish(scene, vignette=0.12, dispersion=0.002)
    record.update(turf=TURF, exposure=EXPOSURE, lens_finish={"vignette": 0.12, "dispersion": 0.002})
    return record
