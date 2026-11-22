"""Physically lit look for the Neospace bathroom sink, applied to the built scene at render time.

Cycles path tracing in the closed room: daylight through the room's window, a ceiling downlight and a
vanity light above the mirror cabinet, with the glTF-import material losses (chrome, mirror, glass)
restored, clear water and a vinyl duck. Lighting changes therefore never require re-simulating.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

SAMPLES = 128         # with denoising: matches 256 spp at 42.7 dB PSNR, 1.7x faster
EXPOSURE = -1.0
SUN_STRENGTH = 4.0
SUN_ELEVATION_DEG = 32.0
SKY_STRENGTH = 0.6
CEILING_LIGHT_W = 40.0
VANITY_LIGHT_W = 70.0
WARM_WHITE = (1.0, 0.86, 0.72)      # about 3500 K
NEUTRAL_WHITE = (1.0, 0.93, 0.86)   # about 4500 K
WINDOW_CENTER = Vector((2.40, 4.45, 1.70))
DUCK_FOCUS = Vector((0.61, 1.70, 0.86))
DUCK_HUE_SHIFT = -0.015              # about 5 degrees from lemon towards warm yellow
DUCK_VALUE = 0.92
DUCK_ROUGHNESS = (0.28, 0.42)        # semi-gloss vinyl
WHITE_BALANCE_K = 5400.0             # neutralise most of the warm practical lights, keep a little warmth
SHUTTER = 0.5                        # 180 degree shutter: 1/48 s at 24 fps
BASIN_FLOOR_Z = 0.8052               # measured flat floor of the visible basin
WATER_MATERIAL = "Clear household tap water"
LENS_DISPERSION = 0.006
VIGNETTE_STRENGTH = 0.18


def bsdf(material):
    return next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")


def restore_materials():
    """The glTF import kept names but dropped metalness and transmission."""
    chrome = bsdf(bpy.data.materials["CHROME"])
    chrome.inputs["Base Color"].default_value = (0.62, 0.62, 0.64, 1.0)
    chrome.inputs["Metallic"].default_value = 1.0
    chrome.inputs["Roughness"].default_value = 0.06

    mirror = bsdf(bpy.data.materials["mirror"])
    mirror.inputs["Base Color"].default_value = (0.92, 0.93, 0.93, 1.0)
    mirror.inputs["Metallic"].default_value = 1.0
    mirror.inputs["Roughness"].default_value = 0.0

    glass = bsdf(bpy.data.materials["GLASS_SK"])
    glass.inputs["Base Color"].default_value = (0.96, 0.98, 0.98, 1.0)
    glass.inputs["Transmission Weight"].default_value = 1.0
    glass.inputs["Roughness"].default_value = 0.0
    glass.inputs["IOR"].default_value = 1.5

    porcelain = bsdf(bpy.data.materials["PORSALIN"])
    porcelain.inputs["Base Color"].default_value = (0.80, 0.80, 0.79, 1.0)
    porcelain.inputs["Roughness"].default_value = 0.16
    porcelain.inputs["Coat Weight"].default_value = 0.3
    porcelain.inputs["Coat Roughness"].default_value = 0.08


def world_noise(material, scale, detail=4.0):
    """Noise driven by world position, so feature sizes are in metres on every object."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    geometry = nodes.get("World geometry") or nodes.new("ShaderNodeNewGeometry")
    geometry.name = "World geometry"
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    links.new(geometry.outputs["Position"], noise.inputs["Vector"])
    return geometry, noise


def map_range(material, source, low, high, from_low=0.3, from_high=0.7):
    node = material.node_tree.nodes.new("ShaderNodeMapRange")
    node.inputs["From Min"].default_value = from_low
    node.inputs["From Max"].default_value = from_high
    node.inputs["To Min"].default_value = low
    node.inputs["To Max"].default_value = high
    material.node_tree.links.new(source, node.inputs["Value"])
    return node.outputs["Result"]


def roughness_variation(material, low, high, scale):
    """Wipe marks and wear: the glaze is never uniformly glossy."""
    _, noise = world_noise(material, scale)
    material.node_tree.links.new(map_range(material, noise.outputs["Fac"], low, high), bsdf(material).inputs["Roughness"])


def surface_relief(material, scale, strength, distance=0.0005):
    """Glaze orange peel or tile waviness, visible only in reflections."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    _, noise = world_noise(material, scale, detail=2.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf(material).inputs["Normal"])


def per_tile_tint(material, spread):
    """Each tile is its own mesh island; real glazed tiles differ slightly from batch to batch."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    principled = bsdf(material)
    color = nodes.new("ShaderNodeRGB")
    color.outputs[0].default_value = tuple(principled.inputs["Base Color"].default_value)
    geometry = nodes.get("World geometry") or nodes.new("ShaderNodeNewGeometry")
    geometry.name = "World geometry"
    hsv = nodes.new("ShaderNodeHueSaturation")
    links.new(color.outputs[0], hsv.inputs["Color"])
    links.new(map_range(material, geometry.outputs["Random Per Island"], 1.0 - spread, 1.0 + spread, 0.0, 1.0),
              hsv.inputs["Value"])
    links.new(hsv.outputs["Color"], principled.inputs["Base Color"])


def surface_detail():
    porcelain = bpy.data.materials["PORSALIN"]
    roughness_variation(porcelain, 0.11, 0.19, scale=12.0)
    surface_relief(porcelain, scale=350.0, strength=0.03)

    tiles = bpy.data.materials["wall_tiles"]
    bsdf(tiles).inputs["Roughness"].default_value = 0.25    # glazed wall tile, not matte plaster
    per_tile_tint(tiles, spread=0.05)
    roughness_variation(tiles, 0.18, 0.32, scale=8.0)
    surface_relief(tiles, scale=6.0, strength=0.06, distance=0.002)

    roughness_variation(bpy.data.materials["cabinets2"], 0.28, 0.42, scale=10.0)
    roughness_variation(bpy.data.materials["CHROME"], 0.04, 0.12, scale=60.0)


def vinyl_duck():
    """The asset's lemon-green yellow at roughness 0.1 reads as wet hard plastic; a vinyl duck is a
    deeper, warmer yellow with a semi-gloss surface. Texture detail is kept, only remapped."""
    material = bpy.data.materials["material.001"]
    nodes, links = material.node_tree.nodes, material.node_tree.links
    principled = bsdf(material)
    tint = nodes.new("ShaderNodeHueSaturation")
    tint.inputs["Hue"].default_value = 0.5 + DUCK_HUE_SHIFT
    tint.inputs["Value"].default_value = DUCK_VALUE
    links.new(principled.inputs["Base Color"].links[0].from_socket, tint.inputs["Color"])
    links.new(tint.outputs["Color"], principled.inputs["Base Color"])
    roughness = principled.inputs["Roughness"].links[0].from_socket
    links.new(map_range(material, roughness, *DUCK_ROUGHNESS, 0.0, 0.2), principled.inputs["Roughness"])


def camera_lens(scene):
    """A real lens: slight corner falloff and a trace of lateral chromatic aberration."""
    scene.use_nodes = True
    tree = scene.node_tree
    nodes, links = tree.nodes, tree.links
    nodes.clear()
    layers = nodes.new("CompositorNodeRLayers")
    lens = nodes.new("CompositorNodeLensdist")
    lens.inputs["Dispersion"].default_value = LENS_DISPERSION
    links.new(layers.outputs["Image"], lens.inputs["Image"])
    ellipse = nodes.new("CompositorNodeEllipseMask")
    ellipse.width, ellipse.height = 1.05, 1.05
    soften = nodes.new("CompositorNodeBlur")
    soften.use_relative = True
    soften.factor_x = soften.factor_y = 40.0
    soften.filter_type = "GAUSS"
    links.new(ellipse.outputs["Mask"], soften.inputs["Image"])
    falloff = nodes.new("CompositorNodeMapRange")
    falloff.inputs["To Min"].default_value = 1.0 - VIGNETTE_STRENGTH
    links.new(soften.outputs["Image"], falloff.inputs["Value"])
    vignette = nodes.new("CompositorNodeMixRGB")
    vignette.blend_type = "MULTIPLY"
    links.new(lens.outputs["Image"], vignette.inputs[1])
    links.new(falloff.outputs["Value"], vignette.inputs[2])
    composite = nodes.new("CompositorNodeComposite")
    links.new(vignette.outputs["Image"], composite.inputs["Image"])


def film_water():
    """Clear water for the 1-2 mm floor film. Shadow rays pass straight through it: light reaching the
    floor under so thin a film is displaced by well under a millimetre, while forcing it through the
    refractive interface (a caustic path) leaves the wet floor unrealistically grey and noisy."""
    material = bpy.data.materials[WATER_MATERIAL].copy()
    material.name = "Basin floor water film"
    nodes, links = material.node_tree.nodes, material.node_tree.links
    output = next(node for node in nodes if node.type == "OUTPUT_MATERIAL")
    water = bsdf(material)
    light_path = nodes.new("ShaderNodeLightPath")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(light_path.outputs["Is Shadow Ray"], mix.inputs["Fac"])
    links.new(water.outputs[0], mix.inputs[1])
    links.new(transparent.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs["Surface"])
    return material


def clear_water():
    """Tap water is clear: a refractive dielectric."""
    material = bpy.data.materials.get(WATER_MATERIAL) or bpy.data.materials.new(WATER_MATERIAL)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    water = nodes.new("ShaderNodeBsdfPrincipled")
    water.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    water.inputs["Transmission Weight"].default_value = 1.0
    water.inputs["Roughness"].default_value = 0.0
    water.inputs["IOR"].default_value = 1.333
    links.new(water.outputs[0], output.inputs[0])


def close_room():
    ceiling = bpy.data.objects["Line024_ceiling one_0"]
    ceiling.hide_render = False
    ceiling.hide_set(False)
    # Line021__0 is a whole-ceiling emissive slab; real light comes from fixtures below.
    bpy.data.objects["Line021__0"].hide_render = True


def add_light(scene, name, kind, location, energy, color, target=None, **settings):
    data = bpy.data.lights.new(name + "Data", kind)
    data.energy = energy
    data.color = color
    for key, value in settings.items():
        setattr(data, key, value)
    light = bpy.data.objects.new(name, data)
    scene.collection.objects.link(light)
    light.location = location
    if target is not None:
        light.rotation_euler = (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
    return light


def daylight(scene):
    world = bpy.data.worlds.new("BathroomDaylight")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    background = nodes["Background"]
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(SUN_ELEVATION_DEG)
    sky.sun_rotation = math.radians(-90.0)
    links.new(sky.outputs[0], background.inputs["Color"])
    background.inputs["Strength"].default_value = SKY_STRENGTH
    scene.world = world

    # Sun enters through the window on the far (+y) wall and lands on the floor of the room.
    sun = add_light(scene, "WindowSun", "SUN", WINDOW_CENTER, SUN_STRENGTH, (1.0, 0.95, 0.88), angle=math.radians(0.53))
    elevation = math.radians(SUN_ELEVATION_DEG)
    direction = Vector((0.15, -math.cos(elevation), -math.sin(elevation))).normalized()
    sun.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def practical_lights(scene):
    add_light(scene, "CeilingDownlight", "AREA", (1.05, 1.70, 2.47), CEILING_LIGHT_W, WARM_WHITE,
              target=(1.05, 1.70, 0.0), shape="DISK", size=0.18)
    add_light(scene, "VanityBar", "AREA", (0.58, 1.67, 2.08), VANITY_LIGHT_W, NEUTRAL_WHITE,
              target=(0.95, 1.67, 0.95), shape="RECTANGLE", size=0.06, size_y=0.60)


def configure_cycles(scene):
    scene.render.engine = "CYCLES"
    cycles = scene.cycles
    cycles.device = "GPU"
    cycles.samples = SAMPLES
    cycles.use_denoising = True
    cycles.max_bounces = 16
    cycles.diffuse_bounces = 4
    cycles.glossy_bounces = 8
    cycles.transmission_bounces = 16
    cycles.transparent_max_bounces = 16
    cycles.caustics_reflective = True
    cycles.caustics_refractive = True
    cycles.blur_glossy = 0.5
    cycles.sample_clamp_indirect = 10.0
    scene.render.use_persistent_data = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = EXPOSURE
    scene.view_settings.use_white_balance = True
    scene.view_settings.white_balance_temperature = WHITE_BALANCE_K
    # The water mesh carries per-vertex velocity (surface_*), so the falling stream and
    # droplets streak the way they do on a real 1/48 s exposure.
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = SHUTTER

    camera = scene.camera.data
    camera.dof.use_dof = True
    camera.dof.focus_distance = (scene.camera.location - DUCK_FOCUS).length
    camera.dof.aperture_fstop = 5.6


def configure_gpu():
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
        except TypeError:
            continue
        devices = [device for device in prefs.devices if device.type == backend]
        if devices:
            for device in prefs.devices:
                device.use = device in devices
            return backend, [device.name for device in devices]
    raise RuntimeError("No GPU for Cycles: refusing a silent CPU fallback.")


def apply_look(scene):
    restore_materials()
    surface_detail()
    vinyl_duck()
    clear_water()
    close_room()
    daylight(scene)
    practical_lights(scene)
    configure_cycles(scene)
    camera_lens(scene)
    backend, devices = configure_gpu()
    scene["pcve_look"] = "cycles_closed_room_daylight"
    print(f"PCVE_LOOK=cycles_closed_room_daylight GPU={backend} {devices}", flush=True)
