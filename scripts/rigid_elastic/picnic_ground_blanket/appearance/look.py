"""Current photographic look of picnic_ground_blanket.

Applied by render_replay.py to the packed scene before any frame is replayed. It changes
light and materials only: no object that takes part in the physics moves, and the camera
is untouched.

* Daylight: the Poly Haven CC0 sky "kloofendal_48d_partly_cloudy_puresky" lights the scene
  and is seen in reflections. Its sun is cut out of the map and replaced by a sun lamp in the
  same direction with the same integrated irradiance and colour, so shadows are crisp and the
  sun/sky balance is the one that was photographed. The sky is turned so that the sun stands
  to the left of and slightly behind the camera (shadows fall to the right, away from the
  orange's path).
* Lawn: per-plant and metre-scale colour variation (lush, yellowing and darker patches) on the
  existing Poly Haven scanned grass and on the scanned ground texture.
* Picnic blanket: cotton gingham with the existing photographed weave normal/roughness, a
  softer two-tone dye, fibre-level colour noise and cotton sheen.
* Thermos: brushed stainless steel body (the packed model's printed decal is removed).
* ADD picnic cup: a hollow enamel camping tumbler whose outer surface is the solved contact
  cylinder (radius and height unchanged).
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

SKY_ID = "kloofendal_48d_partly_cloudy_puresky"
# Sun position seen from the scene: left of the camera and a little behind it.
SUN_AZIMUTH_DEG = -135.8
SUN_DISC_DEG = 0.6
EXPOSURE = 0.0
LOOK = "AgX - Medium High Contrast"


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _direction(u, v):
    """Blender equirectangular texture coordinate -> unit direction."""
    a = (u - 0.5) * 2 * math.pi
    el = (v - 0.5) * math.pi
    return np.array([-math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)])


def daylight(scene, sky_path):
    """Photographed sky + its own sun as a lamp. Returns a JSON-able record."""
    image = bpy.data.images.load(str(sky_path), check_existing=True)
    width, height = image.size
    pixels = np.empty(width * height * 4, np.float32)
    image.pixels.foreach_get(pixels)
    rgb = pixels.reshape(height, width, 4)[:, :, :3].astype(np.float64)
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    row, col = np.unravel_index(int(np.argmax(lum)), lum.shape)
    sun_tex = _direction((col + 0.5) / width, (row + 0.5) / height)
    # Angular distance of every texel to the sun texel.
    v = (np.arange(height) + 0.5) / height
    u = (np.arange(width) + 0.5) / width
    el = (v - 0.5) * np.pi
    az = (u - 0.5) * 2 * np.pi
    dirs = np.stack([-np.cos(az)[None, :] * np.cos(el)[:, None], np.sin(az)[None, :] * np.cos(el)[:, None],
                     np.broadcast_to(np.sin(el)[:, None], (height, width))], axis=-1)
    angle = np.degrees(np.arccos(np.clip(dirs @ sun_tex, -1, 1)))
    disc = angle < 3.0
    ceiling = float(np.percentile(lum[~disc], 99.995))
    solid = (2 * np.pi / width) * (np.pi / height) * np.cos(el)[:, None]
    excess = np.clip(rgb - ceiling, 0, None) * disc[..., None]
    irradiance = (excess * solid[..., None]).sum(axis=(0, 1))
    strength = float(irradiance @ np.array([0.2126, 0.7152, 0.0722]))
    color = irradiance / max(irradiance.max(), 1e-12)
    # Horizontal irradiance of the sky without its sun, against the sun's: the shadow contrast.
    sky_lum = np.minimum(lum, ceiling)
    up = (el > 0)[:, None]
    sky_horizontal = float((sky_lum * np.sin(np.clip(el, 0, None))[:, None] * solid * up).sum())
    sun_horizontal = strength * float(sun_tex[2])
    # Turn the sky so that its sun has the requested azimuth.
    sun_az_tex = math.atan2(sun_tex[1], sun_tex[0])
    theta = sun_az_tex - math.radians(SUN_AZIMUTH_DEG)
    rot = Matrix.Rotation(-theta, 3, "Z")
    sun_world = rot @ Vector(sun_tex)
    world = bpy.data.worlds.new("Photographed partly cloudy sky | Poly Haven CC0 " + SKY_ID)
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.vector_type = "POINT"
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, theta)
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = image
    env.interpolation = "Cubic"
    cut = nodes.new("ShaderNodeVectorMath")
    cut.operation = "MINIMUM"
    cut.inputs[1].default_value = (ceiling, ceiling, ceiling)
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = 1.0
    output = nodes.new("ShaderNodeOutputWorld")
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], cut.inputs[0])
    links.new(cut.outputs["Vector"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    scene.world = world
    lamp = bpy.data.lights.new("Sun of the photographed sky", "SUN")
    lamp.energy = strength
    lamp.color = tuple(float(c) for c in color)
    lamp.angle = math.radians(SUN_DISC_DEG)
    sun = bpy.data.objects.new(lamp.name, lamp)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (-sun_world).to_track_quat("-Z", "Y").to_euler()
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = LOOK
    scene.view_settings.exposure = EXPOSURE
    return dict(sky=SKY_ID, sky_file=Path(sky_path).name, sky_sha256=_sha(sky_path), sky_rotation_z_rad=theta,
                sun_direction=list(sun_world), sun_elevation_deg=math.degrees(math.asin(sun_world.z)),
                sun_azimuth_deg=SUN_AZIMUTH_DEG, sun_irradiance=strength, sun_color=[float(c) for c in color],
                sun_disc_deg=SUN_DISC_DEG, sky_ceiling=ceiling, sky_horizontal_irradiance=sky_horizontal,
                sun_horizontal_irradiance=sun_horizontal, view_transform="AgX", look=LOOK, exposure=EXPOSURE,
                fill_lights=0)


# Ground-shadow centre (x, y) and crown radius (m) of the park trees outside the picture.
# Each tree stands at its shadow centre plus the canopy-to-ground sun offset; every one of
# them lies outside the camera's horizontal field of view (checked in tree_shade).
CROWNS = ((-4.0, 6.2, 2.6), (-9.6, 14.5, 4.0), (-24.0, 26.0, 5.5))


def tree_shade(scene, sun_world, camera, clearing_center=(0.15, 0.12), clearing_radius=3.0):
    """Shade of park trees standing outside the picture, on the lawn left of the blanket.

    A horizontal canopy layer 8 m above the ground, seen only by shadow rays (it blocks sun
    and sky light; camera, diffuse and glossy rays pass through). It holds the crowns listed
    in CROWNS with irregular edges and leaf gaps. Shade never reaches within 3 m of the
    blanket centre, so the blanket, the props and every orange path stay in direct sun.
    """
    height = 8.0
    sun = Vector(sun_world)
    reach = Vector((sun.x, sun.y)) * (height / sun.z)  # ground shadow = canopy point - reach
    inverse = camera.matrix_world.inverted()
    focal = camera.data.lens / camera.data.sensor_width  # horizontal half-width at depth 1 = 0.5 / focal
    for cx, cy, radius in CROWNS:
        trunk = inverse @ Vector((cx + reach.x, cy + reach.y, 0.0))
        depth = -trunk.z
        if depth > 0 and abs(trunk.x) - radius < 0.5 / focal * depth:
            raise RuntimeError(f"Tree for shade at ({cx}, {cy}) would stand inside the picture")
        if math.hypot(cx - clearing_center[0], cy - clearing_center[1]) - radius - 1.2 < clearing_radius:
            raise RuntimeError(f"Shade at ({cx}, {cy}) reaches the picnic area")
    xs = [c[0] + reach.x for c in CROWNS]
    ys = [c[1] + reach.y for c in CROWNS]
    pad = 8.0
    lo = (min(xs) - pad, min(ys) - pad)
    hi = (max(xs) + pad, max(ys) + pad)
    mesh = bpy.data.meshes.new("Park tree crowns outside the picture (shadow only)")
    mesh.from_pydata([(lo[0], lo[1], height), (hi[0], lo[1], height), (hi[0], hi[1], height), (lo[0], hi[1], height)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new(mesh.name, mesh)
    for attr in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        setattr(obj, attr, False)
    obj.visible_shadow = True
    mat = bpy.data.materials.new("Leaf canopy | crowns with gaps")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    geo = nodes.new("ShaderNodeNewGeometry")
    ground = nodes.new("ShaderNodeVectorMath")  # the ground point this canopy point shades
    ground.operation = "SUBTRACT"
    ground.inputs[1].default_value = (reach.x, reach.y, height)
    links.new(geo.outputs["Position"], ground.inputs[0])
    flat = nodes.new("ShaderNodeVectorMath")
    flat.operation = "MULTIPLY"
    flat.inputs[1].default_value = (1.0, 1.0, 0.0)
    links.new(ground.outputs["Vector"], flat.inputs[0])
    edge = nodes.new("ShaderNodeTexNoise")  # irregular crown outline
    edge.inputs["Scale"].default_value = 0.45
    edge.inputs["Detail"].default_value = 5.0
    edge.inputs["Roughness"].default_value = 0.65
    links.new(flat.outputs["Vector"], edge.inputs["Vector"])
    wobble = nodes.new("ShaderNodeMapRange")
    wobble.inputs["To Min"].default_value = -1.4
    wobble.inputs["To Max"].default_value = 1.4
    links.new(edge.outputs["Fac"], wobble.inputs["Value"])
    crown = None
    for cx, cy, radius in CROWNS:
        dist = nodes.new("ShaderNodeVectorMath")
        dist.operation = "DISTANCE"
        dist.inputs[1].default_value = (cx, cy, 0.0)
        links.new(flat.outputs["Vector"], dist.inputs[0])
        rough = nodes.new("ShaderNodeMath")
        rough.operation = "ADD"
        links.new(dist.outputs["Value"], rough.inputs[0])
        links.new(wobble.outputs["Result"], rough.inputs[1])
        mask = nodes.new("ShaderNodeMapRange")
        mask.inputs["From Min"].default_value = radius - 0.3
        mask.inputs["From Max"].default_value = radius + 0.3
        mask.inputs["To Min"].default_value = 1.0
        mask.inputs["To Max"].default_value = 0.0
        links.new(rough.outputs["Value"], mask.inputs["Value"])
        if crown is None:
            crown = mask.outputs["Result"]
        else:
            both = nodes.new("ShaderNodeMath")
            both.operation = "MAXIMUM"
            links.new(crown, both.inputs[0])
            links.new(mask.outputs["Result"], both.inputs[1])
            crown = both.outputs["Value"]
    leaves = nodes.new("ShaderNodeTexNoise")  # sun flecks through the foliage
    leaves.inputs["Scale"].default_value = 2.4
    leaves.inputs["Detail"].default_value = 6.0
    leaves.inputs["Roughness"].default_value = 0.7
    links.new(flat.outputs["Vector"], leaves.inputs["Vector"])
    leaf_mask = nodes.new("ShaderNodeMapRange")
    leaf_mask.inputs["From Min"].default_value = 0.30
    leaf_mask.inputs["From Max"].default_value = 0.44
    leaf_mask.inputs["To Min"].default_value = 0.15
    links.new(leaves.outputs["Fac"], leaf_mask.inputs["Value"])
    cover = nodes.new("ShaderNodeMath")
    cover.operation = "MULTIPLY"
    cover.use_clamp = True
    links.new(crown, cover.inputs[0])
    links.new(leaf_mask.outputs["Result"], cover.inputs[1])
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    leaf = nodes.new("ShaderNodeBsdfDiffuse")
    leaf.inputs["Color"].default_value = (0.05, 0.09, 0.03, 1)
    mix = nodes.new("ShaderNodeMixShader")
    links.new(cover.outputs["Value"], mix.inputs[0])
    links.new(transparent.outputs["BSDF"], mix.inputs[1])
    links.new(leaf.outputs["BSDF"], mix.inputs[2])
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(mix.outputs["Shader"], output.inputs["Surface"])
    mesh.materials.append(mat)
    scene.collection.objects.link(obj)
    return dict(canopy_height_m=height, crowns_ground_xy_radius_m=[list(c) for c in CROWNS],
                trees_xy_m=[[c[0] + reach.x, c[1] + reach.y] for c in CROWNS], leaf_gap_noise_scale_per_m=2.4,
                min_distance_to_blanket_centre_m=clearing_radius,
                visibility="shadow rays only (sun and sky); not seen by camera, diffuse or glossy rays",
                meaning="crowns of park trees standing outside the camera view; no light is added")


def _variation_nodes(tree, color_socket, scale, strength):
    """Multiply a colour by plant/patch variation; returns the new colour socket."""
    nodes, links = tree.nodes, tree.links
    geometry = nodes.new("ShaderNodeNewGeometry")
    info = nodes.new("ShaderNodeObjectInfo")
    # Metre-scale patches: lush (darker, bluer) versus yellowing (drier) turf.
    patch = nodes.new("ShaderNodeTexNoise")
    patch.inputs["Scale"].default_value = scale
    patch.inputs["Detail"].default_value = 3.0
    patch.inputs["Roughness"].default_value = 0.55
    links.new(geometry.outputs["Position"], patch.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.70, 0.80, 0.68, 1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (1.28, 1.14, 0.60, 1)
    middle = ramp.color_ramp.elements.new(0.50)
    middle.color = (1.0, 1.0, 1.0, 1)
    links.new(patch.outputs["Fac"], ramp.inputs["Fac"])
    patch_mix = nodes.new("ShaderNodeMix")
    patch_mix.data_type = "RGBA"
    patch_mix.blend_type = "MULTIPLY"
    patch_mix.inputs["Factor"].default_value = strength
    links.new(color_socket, patch_mix.inputs["A"])
    links.new(ramp.outputs["Color"], patch_mix.inputs["B"])
    # Per-plant variation: brightness and a slight hue drift.
    jitter = nodes.new("ShaderNodeMapRange")
    jitter.inputs["To Min"].default_value = 0.82
    jitter.inputs["To Max"].default_value = 1.14
    links.new(info.outputs["Random"], jitter.inputs["Value"])
    hue = nodes.new("ShaderNodeMapRange")
    hue.inputs["To Min"].default_value = 0.485
    hue.inputs["To Max"].default_value = 0.515
    links.new(info.outputs["Random"], hue.inputs["Value"])
    hsv = nodes.new("ShaderNodeHueSaturation")
    links.new(patch_mix.outputs["Result"], hsv.inputs["Color"])
    links.new(hue.outputs["Result"], hsv.inputs["Hue"])
    links.new(jitter.outputs["Result"], hsv.inputs["Value"])
    return hsv.outputs["Color"]


def lawn(scene):
    changed = []
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        if "photographic leaf transmission" in mat.name:
            source = next(n for n in nodes if n.type == "HUE_SAT")
            source.inputs["Value"].default_value = 1.55
            source.inputs["Saturation"].default_value = 1.0
            out = _variation_nodes(mat.node_tree, source.outputs["Color"], 0.55, 1.0)
            # Blades crowded and shaded at the blanket border (edge_grass sets 'edge_shade').
            edge = nodes.new("ShaderNodeAttribute")
            edge.attribute_type = "INSTANCER"
            edge.attribute_name = "edge_shade"
            factor = nodes.new("ShaderNodeMapRange")
            factor.inputs["To Min"].default_value = 1.0
            factor.inputs["To Max"].default_value = 0.55
            links.new(edge.outputs["Fac"], factor.inputs["Value"])
            darken = nodes.new("ShaderNodeMix")
            darken.data_type = "RGBA"
            darken.blend_type = "MULTIPLY"
            darken.inputs["Factor"].default_value = 1.0
            links.new(out, darken.inputs["A"])
            gray = nodes.new("ShaderNodeCombineColor")
            for k in range(3):
                links.new(factor.outputs["Result"], gray.inputs[k])
            links.new(gray.outputs["Color"], darken.inputs["B"])
            out = darken.outputs["Result"]
            for n in nodes:
                if n.type in {"BSDF_PRINCIPLED", "BSDF_TRANSLUCENT"}:
                    links.new(out, n.inputs["Color" if n.type == "BSDF_TRANSLUCENT" else "Base Color"])
                if n.type == "BSDF_PRINCIPLED":
                    n.inputs["Specular IOR Level"].default_value = 0.32
                if n.type == "MIX_SHADER" and not n.inputs[0].is_linked:
                    n.inputs[0].default_value = 0.22
                if n.type == "NORMAL_MAP":
                    n.inputs["Strength"].default_value = 0.35
            changed.append(mat.name)
        elif mat.name.startswith("Grass Ground"):
            mix = next(n for n in nodes if n.type == "MIX_RGB" and n.blend_type == "HUE")
            mix.inputs[0].default_value = 0.40
            bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
            out = _variation_nodes(mat.node_tree, mix.outputs["Color"], 0.55, 0.70)
            links.new(out, bsdf.inputs["Base Color"])
            for n in nodes:
                if n.type == "NORMAL_MAP":
                    n.inputs["Strength"].default_value = 0.45
            changed.append(mat.name)
    return dict(materials=changed, patch_scale_per_m=0.55,
                source="Existing Poly Haven CC0 grass_bermuda_01, grass_medium_01, shrub_sorrel_01 and scanned ground")


HEM_WIDTH_M = 0.012
HEM_THICKNESS_M = 0.0013  # three cotton layers at the folded hem; the body stays 0.45 mm


def _node(nodes, kind, **inputs):
    node = nodes.new(kind)
    for key, value in inputs.items():
        node.inputs[key].default_value = value
    return node


def _math(nodes, links, operation, a, b=None, clamp=False):
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    node.use_clamp = clamp
    for index, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = value
        else:
            links.new(value, node.inputs[index])
    return node.outputs["Value"]


def blanket(cloth):
    """Woven cotton gingham with a sewn 12 mm hem. Shading only; the cloth mesh is the native one."""
    mat = bpy.data.materials["Soft woven cotton / 4K photographic weave and gingham dye"]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    ramp = next(n for n in nodes if n.type == "VALTORGB")
    elements = ramp.color_ramp.elements
    before = [tuple(round(c, 3) for c in e.color) for e in elements]
    # Woven gingham: unbleached cotton white, mid green where one dyed yarn crosses, deep green where both do.
    tones = [(0.70, 0.655, 0.555, 1), (0.21, 0.36, 0.25, 1), (0.04, 0.15, 0.08, 1)]
    for element, tone in zip(sorted(elements, key=lambda e: e.position), tones):
        element.color = tone
    # The packed material darkened a 5.5 mm edge band; the sewn hem below replaces it.
    old_edge = next(n for n in nodes if n.type == "MIX_RGB")
    for link in list(old_edge.inputs[0].links):
        links.remove(link)
    old_edge.inputs[0].default_value = 0.0
    # Fabric coordinates in metres (the MaterialMeters UV is 3.125 x the rest position), so
    # every texture stays attached to the cloth while it deforms.
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = cloth.data.uv_layers.active.name
    metres = nodes.new("ShaderNodeVectorMath")
    metres.operation = "SCALE"
    metres.inputs["Scale"].default_value = 1 / 3.125
    links.new(uv.outputs["UV"], metres.inputs[0])
    m = metres.outputs["Vector"]
    split = nodes.new("ShaderNodeSeparateXYZ")
    links.new(m, split.inputs["Vector"])
    # Colour: fibre-level speckle, yarn-to-yarn tone and faint soiling from use on grass.
    fibre = _node(nodes, "ShaderNodeTexNoise", Scale=650.0, Detail=2.0)
    links.new(m, fibre.inputs["Vector"])
    fibre_amount = _node(nodes, "ShaderNodeMapRange", **{"To Min": 0.88, "To Max": 1.07})
    links.new(fibre.outputs["Fac"], fibre_amount.inputs["Value"])
    soil = _node(nodes, "ShaderNodeTexNoise", Scale=5.0, Detail=4.0)
    links.new(m, soil.inputs["Vector"])
    soil_amount = _node(nodes, "ShaderNodeMapRange", **{"From Min": 0.45, "From Max": 0.75, "To Min": 1.0, "To Max": 0.92})
    links.new(soil.outputs["Fac"], soil_amount.inputs["Value"])
    tone = _math(nodes, links, "MULTIPLY", fibre_amount.outputs["Result"], soil_amount.outputs["Result"])
    # Hem: distance to the cut edge (metres) from the packed mesh attribute.
    hem = nodes.new("ShaderNodeAttribute")
    hem.attribute_name = "hem_distance_m"
    d = hem.outputs["Fac"]
    # Fold line of the turned-under hem: a soft ridge with a thin shadow just inside it.
    fold = _math(nodes, links, "ABSOLUTE", _math(nodes, links, "SUBTRACT", d, HEM_WIDTH_M))
    ridge = _math(nodes, links, "SUBTRACT", 1.0, _math(nodes, links, "DIVIDE", fold, 0.0011), clamp=True)
    # Running stitch 8.5 mm from the edge: 2.6 mm stitches, 0.6 mm gaps, along either edge direction.
    along = _math(nodes, links, "ADD", split.outputs["X"], split.outputs["Y"])
    phase = _math(nodes, links, "FRACT", _math(nodes, links, "DIVIDE", along, 0.0032))
    dash = _math(nodes, links, "LESS_THAN", phase, 0.80)
    line = _math(nodes, links, "LESS_THAN", _math(nodes, links, "ABSOLUTE", _math(nodes, links, "SUBTRACT", d, 0.0085)), 0.00035)
    stitch = _math(nodes, links, "MULTIPLY", dash, line)
    # Rounded folded edge instead of a cut sheet edge.
    rim = _math(nodes, links, "POWER", _math(nodes, links, "SUBTRACT", 1.0, _math(nodes, links, "DIVIDE", d, 0.0018), clamp=True), 2.0)
    inside = _math(nodes, links, "LESS_THAN", d, HEM_WIDTH_M)
    height = _math(nodes, links, "ADD", _math(nodes, links, "MULTIPLY", inside, 0.35), _math(nodes, links, "MULTIPLY", ridge, 0.55))
    height = _math(nodes, links, "ADD", height, _math(nodes, links, "MULTIPLY", stitch, 0.45))
    height = _math(nodes, links, "SUBTRACT", height, _math(nodes, links, "MULTIPLY", rim, 0.9))
    # Cotton yarn slubs: millimetre irregularity of the weave surface.
    slub = _node(nodes, "ShaderNodeTexNoise", Scale=320.0, Detail=3.0, Roughness=0.6)
    links.new(m, slub.inputs["Vector"])
    height = _math(nodes, links, "ADD", height, _math(nodes, links, "MULTIPLY", slub.outputs["Fac"], 0.25))
    weave_normal = bsdf.inputs["Normal"].links[0].from_socket
    bump = _node(nodes, "ShaderNodeBump", Strength=0.65, Distance=0.0006)
    links.new(height, bump.inputs["Height"])
    links.new(weave_normal, bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    # Colour: thin shade at the fold, stitches in undyed cotton thread.
    crease = _math(nodes, links, "SUBTRACT", 1.0, _math(nodes, links, "MULTIPLY", ridge, 0.12))
    tone = _math(nodes, links, "MULTIPLY", tone, crease)
    shade = nodes.new("ShaderNodeMix")
    shade.data_type = "RGBA"
    shade.blend_type = "MULTIPLY"
    shade.inputs["Factor"].default_value = 1.0
    base_link = bsdf.inputs["Base Color"].links[0]
    links.new(base_link.from_socket, shade.inputs["A"])
    gray = nodes.new("ShaderNodeCombineColor")
    for k in range(3):
        links.new(tone, gray.inputs[k])
    links.new(gray.outputs["Color"], shade.inputs["B"])
    thread = nodes.new("ShaderNodeMix")
    thread.data_type = "RGBA"
    links.new(stitch, thread.inputs["Factor"])
    links.new(shade.outputs["Result"], thread.inputs["A"])
    thread.inputs["B"].default_value = (0.66, 0.62, 0.53, 1)
    links.new(thread.outputs["Result"], bsdf.inputs["Base Color"])
    # Cotton fuzz: the loose fibres carry the yarn's own dye, so the sheen is tinted by it
    # (a white sheen would veil the green checks at this grazing view).
    fuzz = nodes.new("ShaderNodeMix")
    fuzz.data_type = "RGBA"
    fuzz.inputs["Factor"].default_value = 0.35
    links.new(thread.outputs["Result"], fuzz.inputs["A"])
    fuzz.inputs["B"].default_value = (1.0, 0.97, 0.92, 1)
    links.new(fuzz.outputs["Result"], bsdf.inputs["Sheen Tint"])
    bsdf.inputs["Sheen Weight"].default_value = 0.6
    bsdf.inputs["Sheen Roughness"].default_value = 0.45
    bsdf.inputs["Specular IOR Level"].default_value = 0.12
    for n in nodes:
        if n.type == "NORMAL_MAP":
            n.inputs["Strength"].default_value = 1.0
    # Folded hem is three layers thick: Solidify thickness follows a hem vertex group.
    distance = np.array([v.value for v in cloth.data.attributes["hem_distance_m"].data])
    weight = np.clip((HEM_WIDTH_M + 0.003 - distance) / 0.003, 0, 1)
    group = cloth.vertex_groups.new(name="Folded hem (three layers)")
    for value in np.unique(weight[weight > 0]):
        group.add([int(i) for i in np.flatnonzero(weight == value)], float(value), "REPLACE")
    solidify = next(mod for mod in cloth.modifiers if mod.type == "SOLIDIFY")
    body = solidify.thickness
    solidify.thickness = HEM_THICKNESS_M
    solidify.vertex_group = group.name
    solidify.thickness_vertex_group = body / HEM_THICKNESS_M
    return dict(material=mat.name, dye_before=before, dye_after=[t[:3] for t in tones], sheen=dict(weight=0.6, roughness=0.45, tint="yarn colour + 35% white"),
                hem=dict(width_m=HEM_WIDTH_M, stitch_from_edge_m=0.0085, stitch_length_m=0.0026, thickness_m=HEM_THICKNESS_M,
                         body_thickness_m=body, method="Solidify thickness by hem vertex group + shading; native cloth vertices unchanged"),
                weave="Poly Haven CC0 fabric_pattern_05 normal and roughness (packed) + millimetre yarn-slub bump; textures in fabric (UV) coordinates")


def edge_grass(scene, cloth, tracks):
    """Grass at the blanket border: darker crushed/shaded blades at the edge, and short upright
    tufts rooted just outside it whose tips rise above the hem (never under or through the cloth).

    tracks: native cloth positions (frames, vertices, 3) of every case of the scene. The layout
    is derived from all of them together (rest shape of the first, clearance against every frame
    of every case), and every candidate draws the same random numbers whether or not it is kept,
    so all cases get the same static tufts and edge shade.
    """
    distance = np.array([v.value for v in cloth.data.attributes["hem_distance_m"].data])
    border = np.flatnonzero(distance < 1e-6)
    track = np.concatenate([t[:, border] for t in tracks], axis=0)  # (cases*frames, n, 3)
    rest = tracks[0][0, border]
    half = np.abs(rest[:, :2]).max(axis=0)
    # Edge shade on the existing near-field grass points (instancer attribute 'edge_shade').
    shaded = 0
    for ob in scene.objects:
        if ob.type != "MESH" or "plant_scale" not in ob.data.attributes or "Grass patch" not in ob.name:
            continue
        n = len(ob.data.vertices)
        xyz = np.empty((n, 3), np.float32)
        ob.data.vertices.foreach_get("co", xyz.reshape(-1))
        outside = np.maximum(np.abs(xyz[:, :2]) - half, 0)
        gap = np.linalg.norm(outside, axis=1)
        value = np.clip(1 - gap / 0.035, 0, 1) ** 1.5
        attr = ob.data.attributes.get("edge_shade") or ob.data.attributes.new("edge_shade", "FLOAT", "POINT")
        attr.data.foreach_set("value", value.astype(np.float32))
        shaded += int((value > 0).sum())
    # Tufts along the border, 6-20 mm outside it.
    plants = [ob for ob in bpy.data.collections["Plant sources | Poly Haven CC0"].objects if ob.type == "MESH"]
    stats = []
    for ob in plants:
        v = np.array([p.co[:] for p in ob.data.vertices])
        stats.append((v[:, 2].max(), np.linalg.norm(v[:, :2], axis=1).max()))
    stats = np.array(stats)
    slender = [i for i, ob in enumerate(plants) if ob.name.startswith(("grass_bermuda_01", "grass_medium_01"))
               and stats[i, 1] <= 0.6 * stats[i, 0] and stats[i, 0] > 0.04]
    if not slender:
        slender = [int(np.argmin(stats[:, 1] / stats[:, 0]))]
    ground = bpy.data.objects["Photographed meadow ground"]
    tree = BVHTree.FromObject(ground, bpy.context.evaluated_depsgraph_get())
    draws = np.random.default_rng(20261109).random((len(border), 8))
    roots, ids, scales, rotations, clearances = [], [], [], [], []
    for k in range(len(border)):
        u = draws[k]
        if u[0] > 0.85:
            continue
        p = rest[k, :2]
        if abs(p[0]) / half[0] >= abs(p[1]) / half[1]:
            normal = np.array([math.copysign(1.0, p[0]), 0.0])
        else:
            normal = np.array([0.0, math.copysign(1.0, p[1])])
        root = p + normal * (0.006 + 0.014 * u[1]) + np.array([-normal[1], normal[0]]) * (0.008 * u[2] - 0.004)
        reach = np.linalg.norm(track[:, :, :2] - root, axis=2)
        clearance = float(reach.min())
        hit = tree.ray_cast(Vector((float(root[0]), float(root[1]), 0.2)), Vector((0, 0, -1)), 0.5)
        if hit[0] is None:
            continue
        z = float(hit[0].z) - 0.0004
        edge_top = float(track[:, :, 2][reach < 0.05].max())
        target = edge_top - z + 0.010 + 0.020 * u[3]
        i = int(slender[min(int(u[4] * len(slender)), len(slender) - 1)])
        s = target / stats[i, 0]
        tilt = (u[5:7] - 0.5) * 0.20
        footprint = stats[i, 1] * s + np.abs(tilt).max() * target
        squeeze = min(1.0, (clearance - 0.003) / max(footprint, 1e-9))
        if squeeze < 0.4:
            continue
        roots.append((root[0], root[1], z))
        ids.append(i)
        scales.append((s * squeeze, s * squeeze, s))
        rotations.append((tilt[0], tilt[1], (u[7] - 0.5) * 2 * math.pi))
        clearances.append(clearance - footprint * squeeze)
    template = bpy.data.objects["Lawn | instanced photographed plant species"].modifiers[0].node_group
    mesh = bpy.data.meshes.new("Edge tufts beside the blanket")
    mesh.from_pydata(roots, [], [])
    for key, kind, values in (("plant_id", "INT", np.array(ids, np.int32)), ("plant_scale", "FLOAT_VECTOR", np.array(scales, np.float32)),
                              ("plant_rotation", "FLOAT_VECTOR", np.array(rotations, np.float32))):
        attr = mesh.attributes.new(key, kind, "POINT")
        attr.data.foreach_set("value" if kind == "INT" else "vector", values.reshape(-1))
    obj = bpy.data.objects.new("Grass tufts | blanket border (static, outside the cloth)", mesh)
    scene.collection.objects.link(obj)
    obj.modifiers.new("Scanned plant instances", "NODES").node_group = template
    layout = hashlib.sha256(np.array(roots, np.float64).tobytes() + np.array(ids, np.int32).tobytes()
                            + np.array(scales, np.float64).tobytes() + np.array(rotations, np.float64).tobytes()).hexdigest()
    return dict(edge_shade_points=shaded, edge_shade_width_m=0.035, tufts=len(roots), tuft_layout_sha256=layout,
                tuft_sources=sorted({plants[i].name for i in ids}),
                tuft_root_offset_m=[0.006, 0.020], tuft_tip_above_hem_m=[0.010, 0.030],
                min_lateral_clearance_to_cloth_m=float(min(clearances)) if clearances else None,
                clearance_checked_over=f"{len(tracks)} native states x {tracks[0].shape[0]} frames")


def thermos():
    mat = bpy.data.materials["TB_Main Color"]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shell = next(n for n in nodes if n.type == "MIX_SHADER" and n.name == "Mix Shader")
    for link in list(shell.inputs[0].links):
        links.remove(link)
    shell.inputs[0].default_value = 0.0  # body BSDF only: the printed decal is not rendered
    bsdf = nodes["Principled BSDF"]
    for socket in ("Metallic",):
        for link in list(bsdf.inputs[socket].links):
            links.remove(link)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Base Color"].default_value = (0.74, 0.74, 0.73, 1)
    bsdf.inputs["Anisotropic"].default_value = 0.55
    ramp = next(n for n in nodes if n.type == "VALTORGB")
    ramp.color_ramp.elements[0].color = (0.30, 0.30, 0.30, 1)
    ramp.color_ramp.elements[-1].color = (0.44, 0.44, 0.44, 1)
    return dict(material=mat.name, finish="brushed stainless steel, metallic 1, roughness 0.30-0.44, decal removed")


def enamel_cup(radius, height, name="picnic_cup"):
    """Hollow enamel tumbler whose outside is exactly the solved cylinder (centred at origin)."""
    wall, base, rim = 0.0022, 0.0035, 0.0011
    h = height / 2
    sections = 96
    # (radius, z) outer profile from the base centre up the wall, over the rolled rim, and down inside.
    profile = [(0.0, -h), (radius - 0.0030, -h), (radius - 0.0009, -h + 0.0004), (radius, -h + 0.0030),
               (radius, h - rim)]
    for k in range(1, 8):
        a = math.pi * k / 8
        profile.append((radius - wall / 2 + (wall / 2) * math.cos(a), h - rim + rim * math.sin(a)))
    profile += [(radius - wall, h - rim), (radius - wall, -h + base + 0.004),
                (radius - wall - 0.004, -h + base), (0.0, -h + base)]
    verts, faces, starts = [], [], []
    for r, z in profile:
        starts.append(len(verts))
        if r == 0.0:
            verts.append((0.0, 0.0, z))
            continue
        for j in range(sections):
            t = 2 * math.pi * j / sections
            verts.append((r * math.cos(t), r * math.sin(t), z))
    for k in range(len(profile) - 1):
        a0, b0 = starts[k], starts[k + 1]
        a_pole, b_pole = profile[k][0] == 0.0, profile[k + 1][0] == 0.0
        for j in range(sections):
            jn = (j + 1) % sections
            if a_pole:
                faces.append((a0, b0 + jn, b0 + j))
            elif b_pole:
                faces.append((a0 + j, a0 + jn, b0))
            else:
                faces.append((a0 + j, a0 + jn, b0 + jn, b0 + j))
    mesh = bpy.data.meshes.new("Enamel camping tumbler (visual; outside = contact cylinder)")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    mat = bpy.data.materials.new("Enamelled steel | white body, navy rolled rim")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    coord = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord.outputs["Object"], sep.inputs["Vector"])
    band = nodes.new("ShaderNodeMath")
    band.operation = "GREATER_THAN"
    band.inputs[1].default_value = h - 0.0045
    links.new(sep.outputs["Z"], band.inputs[0])
    tint = nodes.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.inputs["A"].default_value = (0.86, 0.86, 0.83, 1)
    tint.inputs["B"].default_value = (0.03, 0.06, 0.16, 1)
    links.new(band.outputs["Value"], tint.inputs["Factor"])
    speck = nodes.new("ShaderNodeTexNoise")
    speck.inputs["Scale"].default_value = 260.0
    links.new(coord.outputs["Object"], speck.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    bump.inputs["Distance"].default_value = 0.0002
    links.new(speck.outputs["Fac"], bump.inputs["Height"])
    links.new(tint.outputs["Result"], bsdf.inputs["Base Color"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.12
    bsdf.inputs["Coat Weight"].default_value = 0.6
    bsdf.inputs["Coat Roughness"].default_value = 0.05
    mesh.materials.append(mat)
    return obj, dict(model="hollow enamel tumbler, 2.2 mm wall, rolled rim; outer radius and height equal the solved cylinder",
                     radius_m=radius, height_m=height, material=mat.name)


def apply(scene, sky_path, cloth):
    lighting = daylight(scene, sky_path)
    lighting["tree_shade"] = tree_shade(scene, lighting["sun_direction"], scene.camera)
    record = dict(lighting=lighting, lawn=lawn(scene), blanket=blanket(cloth), thermos=thermos())
    return record
