"""Blender: the current phone_sofa_drop look, applied on top of a retimed packed scene.

Appearance only. No solver state, animation key, shape key, camera or object transform of
the simulated bodies (phone, middle seat cushion, landing pillow) is read or written; the
look changes materials, lights, the room shell around the existing set and render settings.
Every number lives in appearance.json next to this file.

What it does (see the scene README):
  * closes the room (ceiling, right wall, front wall) so daylight only enters through the
    existing left window instead of from an open sky dome, and lights it with a sky HDRI seen
    through the window plus a low sun; the old hidden 250 W area light becomes a window portal;
  * sofa upholstery (static sofa, middle cushion, removed-cushion deck) gets a scanned linen;
    the added pillow a scanned cotton weave; back wall a scanned painted plaster;
  * phone: the maker's logo and the lock-screen picture are removed (back glass everywhere,
    screen off), back glass gets a satin finish; the printed mug becomes a plain glazed mug;
  * render: more samples, OpenImageDenoise, persistent data off (motion blur is on), a mild
    lens vignette in the compositor, AgX.

usage inside Blender:  import realism_look; realism_look.apply(config_path, assets_root)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

UPHOLSTERY_MATERIALS = ("00-Grey Light_Fabric", "matching sofa deck cloth")
SIMULATED_OBJECTS = ("phone | rigid COM root", "Dynamic_Original_Middle_Seat", "landing_pillow.native_artwork")


def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _new_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat, mat.node_tree.nodes, mat.node_tree.links, _principled(mat)


def _image(nodes, path, data):
    node = nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(str(path), check_existing=True)
    if data:
        node.image.colorspace_settings.name = "Non-Color"
    return node


def _noise(nodes, links, scale, detail=5.0, coords="Object"):
    tc = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    links.new(tc.outputs[coords], noise.inputs["Vector"])
    return noise


def scanned_fabric(name, folder, prefix, res, cfg):
    """Scanned cloth on the object's own UVs: dyed albedo, roughness range, normal, sheen.

    `cfg`: uv_scale, saturation, tint [r,g,b], value, roughness [lo, hi], normal, sheen,
    sheen_roughness, mottle (fraction of slow tonal drift), mottle_scale.
    """
    mat, nodes, links, bs = _new_material(name)
    uv = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (cfg["uv_scale"], cfg["uv_scale"], 1.0)
    links.new(uv.outputs["UV"], mapping.inputs["Vector"])
    diff = _image(nodes, folder / f"{prefix}_diff_{res}.jpg", False)
    rough = _image(nodes, folder / f"{prefix}_rough_{res}.jpg", True)
    nor = _image(nodes, folder / f"{prefix}_nor_gl_{res}.jpg", True)
    for tex in (diff, rough, nor):
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    hsv = nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = cfg["saturation"]
    hsv.inputs["Value"].default_value = cfg["value"]
    links.new(diff.outputs["Color"], hsv.inputs["Color"])
    dye = nodes.new("ShaderNodeMixRGB")
    dye.blend_type = "MULTIPLY"
    dye.inputs[0].default_value = 1.0
    dye.inputs[2].default_value = (*cfg["tint"], 1.0)
    links.new(hsv.outputs["Color"], dye.inputs[1])
    color = dye.outputs["Color"]
    if cfg.get("mottle", 0.0):
        drift = _noise(nodes, links, cfg["mottle_scale"], 4.0, cfg.get("mottle_coords", "Object"))
        tone = nodes.new("ShaderNodeMapRange")
        tone.inputs["From Min"].default_value = 0.35
        tone.inputs["From Max"].default_value = 0.65
        tone.inputs["To Min"].default_value = 1.0 - cfg["mottle"]
        tone.inputs["To Max"].default_value = 1.0 + cfg["mottle"]
        links.new(drift.outputs["Fac"], tone.inputs["Value"])
        scale = nodes.new("ShaderNodeVectorMath")
        scale.operation = "SCALE"
        links.new(color, scale.inputs[0])
        links.new(tone.outputs[0], scale.inputs["Scale"])
        color = scale.outputs[0]
    links.new(color, bs.inputs["Base Color"])
    rr = nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value, rr.inputs["To Max"].default_value = cfg["roughness"]
    links.new(rough.outputs["Color"], rr.inputs["Value"])
    links.new(rr.outputs[0], bs.inputs["Roughness"])
    nm = nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = cfg["normal"]
    links.new(nor.outputs["Color"], nm.inputs["Color"])
    normal = nm.outputs["Normal"]
    if cfg.get("crumple"):
        # Fine, irregular creasing of a used pillow cover: a bump on top of the weave normal
        # (shading only; the simulated surface is not changed).
        c = cfg["crumple"]
        tc = nodes.new("ShaderNodeTexCoord")
        mapping2 = nodes.new("ShaderNodeMapping")
        mapping2.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
        links.new(tc.outputs["UV"], mapping2.inputs["Vector"])   # UV: the pattern stays on the cloth as it deforms
        wave = nodes.new("ShaderNodeTexNoise")
        wave.inputs["Scale"].default_value = c["scale"]
        wave.inputs["Detail"].default_value = 6.0
        wave.inputs["Roughness"].default_value = 0.6
        wave.inputs["Distortion"].default_value = c.get("distortion", 1.5)
        links.new(mapping2.outputs["Vector"], wave.inputs["Vector"])
        ridge = nodes.new("ShaderNodeMapRange")
        ridge.inputs["From Min"].default_value, ridge.inputs["From Max"].default_value = 0.42, 0.58
        links.new(wave.outputs["Fac"], ridge.inputs["Value"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = c["strength"]
        bump.inputs["Distance"].default_value = c["distance"]
        links.new(ridge.outputs[0], bump.inputs["Height"])
        links.new(normal, bump.inputs["Normal"])
        normal = bump.outputs["Normal"]
    links.new(normal, bs.inputs["Normal"])
    bs.inputs["Sheen Weight"].default_value = cfg["sheen"]
    bs.inputs["Sheen Roughness"].default_value = cfg["sheen_roughness"]
    bs.inputs["Specular IOR Level"].default_value = cfg.get("specular", 0.3)
    return mat


def box_plaster(name, folder, prefix, res, cfg):
    """Scanned painted plaster projected in world space (walls are plain boxes without useful UVs)."""
    mat, nodes, links, bs = _new_material(name)
    tc = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0 / cfg["tile_m"],) * 3
    links.new(tc.outputs["Object"], mapping.inputs["Vector"])
    diff = _image(nodes, folder / f"{prefix}_diff_{res}.jpg", False)
    rough = _image(nodes, folder / f"{prefix}_rough_{res}.jpg", True)
    nor = _image(nodes, folder / f"{prefix}_nor_gl_{res}.jpg", True)
    for tex in (diff, rough, nor):
        tex.projection = "BOX"
        tex.projection_blend = 0.2
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    hsv = nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = cfg["saturation"]
    hsv.inputs["Value"].default_value = cfg["value"]
    links.new(diff.outputs["Color"], hsv.inputs["Color"])
    dye = nodes.new("ShaderNodeMixRGB")
    dye.blend_type = "MULTIPLY"
    dye.inputs[0].default_value = 1.0
    dye.inputs[2].default_value = (*cfg["tint"], 1.0)
    links.new(hsv.outputs["Color"], dye.inputs[1])
    links.new(dye.outputs["Color"], bs.inputs["Base Color"])
    rr = nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value, rr.inputs["To Max"].default_value = cfg["roughness"]
    links.new(rough.outputs["Color"], rr.inputs["Value"])
    links.new(rr.outputs[0], bs.inputs["Roughness"])
    nm = nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = cfg["normal"]
    links.new(nor.outputs["Color"], nm.inputs["Color"])
    links.new(nm.outputs["Normal"], bs.inputs["Normal"])
    return mat


def plain(name, color, roughness, coat=0.0, coat_roughness=0.05, metallic=0.0):
    mat, nodes, links, bs = _new_material(name)
    bs.inputs["Base Color"].default_value = (*color, 1.0)
    bs.inputs["Roughness"].default_value = roughness
    bs.inputs["Metallic"].default_value = metallic
    bs.inputs["Coat Weight"].default_value = coat
    bs.inputs["Coat Roughness"].default_value = coat_roughness
    return mat


def replace_material(old_name, new):
    old = bpy.data.materials.get(old_name)
    count = 0
    if old is None:
        return count
    for obj in bpy.data.objects:
        for slot in getattr(obj, "material_slots", ()):
            if slot.material is old:
                slot.material = new
                count += 1
    return count


def box(name, centre, size, mat, collection):
    mesh = bpy.data.meshes.new(name)
    x, y, z = (s / 2 for s in size)
    verts = [(sx * x, sy * y, sz * z) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = centre
    mesh.materials.append(mat)
    collection.objects.link(obj)
    return obj


def _rounded_plate(name, x0, x1, y0, y1, z0, z1, radius, segments=10):
    """Closed rounded-rectangle slab (mesh coordinates = phone-root frame)."""
    import bmesh
    outline = []
    corners = ((x1 - radius, y1 - radius, 0), (x0 + radius, y1 - radius, 90),
               (x0 + radius, y0 + radius, 180), (x1 - radius, y0 + radius, 270))
    for cx, cy, start in corners:
        for i in range(segments + 1):
            a = math.radians(start + 90 * i / segments)
            outline.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    bm = bmesh.new()
    bottom = [bm.verts.new((x, y, z0)) for x, y in outline]
    top = [bm.verts.new((x, y, z1)) for x, y in outline]
    bm.faces.new(list(reversed(bottom)))
    bm.faces.new(top)
    m = len(outline)
    for i in range(m):
        j = (i + 1) % m
        bm.faces.new((bottom[i], bottom[j], top[j], top[i]))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _disc(name, x, y, z0, z1, radius, segments=32):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=z1 - z0)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(x, y, (z0 + z1) / 2))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def generic_camera_module(cfg, glass, collection):
    """Replace the flagship-looking triple-camera block by a plain dual-camera module.

    Same footprint and height as the original module plate; two of the original lens
    assemblies are kept and moved into one vertical column, the third lens and the plate
    (with its LiDAR, microphone and flash openings) are hidden, and a small flash is added.
    All parts are children of the phone root, so they follow the solver's rigid transform.
    """
    root = bpy.data.objects["phone | rigid COM root"]
    report = {"hidden": [], "moved": {}, "added": []}
    for name in cfg["hide"]:
        bpy.data.objects[name].hide_render = True
        report["hidden"].append(name)

    def add(mesh, material):
        obj = bpy.data.objects.new(mesh.name, mesh)
        mesh.materials.append(material)
        collection.objects.link(obj)
        obj.parent = root
        obj.matrix_parent_inverse.identity()
        obj.matrix_basis.identity()
        report["added"].append(obj.name)
        return obj

    p = cfg["plate"]
    module = plain("Look camera module finish", p["color"], p["roughness"], 0.6, 0.05)
    add(_rounded_plate("Look camera module", *p["x"], *p["y"], *p["z"], p["corner_radius"]), module)
    for name, (dx, dy) in cfg["move"].items():
        obj = bpy.data.objects[name]
        if obj.parent is not root or (obj.animation_data and obj.animation_data.action):
            raise ValueError(f"Unexpected lens setup: {name}")
        pi = obj.matrix_parent_inverse.copy()
        obj.matrix_basis = pi.inverted() @ Matrix.Translation((dx, dy, 0.0)) @ pi @ obj.matrix_basis
        report["moved"][name] = [dx, dy]
    f = cfg["flash"]
    flash = plain("Look phone flash", f["color"], 0.25, 1.0, 0.03)
    add(_disc("Look camera flash", f["x"], f["y"], f["z"][0], f["z"][1], f["radius"]), flash)
    return report


def lens_finish(scene, vignette):
    """Mild optical vignette in the compositor; no per-frame grain, so video stays stable."""
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    layers = tree.nodes.new("CompositorNodeRLayers")
    mask = tree.nodes.new("CompositorNodeEllipseMask")
    mask.width, mask.height = 1.18, 1.32
    blur = tree.nodes.new("CompositorNodeBlur")
    blur.filter_type = "GAUSS"
    blur.use_relative = True
    blur.factor_x = blur.factor_y = 30.0
    tree.links.new(mask.outputs["Mask"], blur.inputs["Image"])
    level = tree.nodes.new("CompositorNodeMapRange")
    level.inputs["To Min"].default_value = 1.0 - vignette
    level.inputs["To Max"].default_value = 1.0
    tree.links.new(blur.outputs["Image"], level.inputs["Value"])
    mix = tree.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    tree.links.new(layers.outputs["Image"], mix.inputs[1])
    tree.links.new(level.outputs[0], mix.inputs[2])
    out = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(mix.outputs[0], out.inputs["Image"])


def _fingerprint():
    """Transforms of the simulated bodies at the current frame (must be unchanged by the look)."""
    rows = {}
    for name in SIMULATED_OBJECTS:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            rows[name] = [list(r) for r in obj.matrix_world]
    rows["camera"] = [list(r) for r in bpy.context.scene.camera.matrix_world]
    return rows


def apply(config_path, assets_root):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    assets = Path(assets_root)
    scene = bpy.context.scene
    before = _fingerprint()
    report = {"config": str(config_path), "replaced": {}}
    room = bpy.data.collections.new("Look room shell")
    scene.collection.children.link(room)

    # ---- room shell: daylight now enters only through the existing left window
    shell = cfg["room"]
    plaster = box_plaster("Look painted plaster", assets / shell["plaster"]["folder"], shell["plaster"]["prefix"],
                          shell["plaster"]["res"], shell["plaster"])
    ceiling_mat = plain("Look ceiling paint", shell["ceiling_color"], 0.9)
    x0, x1, y0, y1, z1 = shell["x_min"], shell["x_max"], shell["y_min"], shell["y_back"], shell["ceiling_z"]
    t = 0.1
    box("Look ceiling", ((x0 + x1) / 2, (y0 + y1) / 2, z1 + t / 2), (x1 - x0 + 2 * t, y1 - y0 + 2 * t, t), ceiling_mat, room)
    box("Look right wall", (x1 + t / 2, (y0 + y1) / 2, z1 / 2), (t, y1 - y0, z1), plaster, room)
    box("Look front wall", ((x0 + x1) / 2, y0 - t / 2, z1 / 2), (x1 - x0, t, z1), plaster, room)
    report["replaced"]["wall_plaster"] = sum(replace_material(n, plaster) for n in shell["plaster"]["replaces"])

    # ---- daylight: sky HDRI through the window, a low sun, the old area light as a portal
    light = cfg["light"]
    world = scene.world
    env = next(n for n in world.node_tree.nodes if n.type == "TEX_ENVIRONMENT")
    env.image = bpy.data.images.load(str(assets / light["hdri"]), check_existing=True)
    mapping = world.node_tree.nodes.new("ShaderNodeMapping")
    coord = world.node_tree.nodes.new("ShaderNodeTexCoord")
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(light["hdri_rotation_deg"]))
    world.node_tree.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    world.node_tree.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs["Strength"].default_value = light["hdri_strength"]
    old = bpy.data.objects.get("Left window broad overcast sky")
    if old is not None:
        old.hide_render = True
    portal = bpy.data.lights.new("Look window portal", "AREA")
    portal.shape = "RECTANGLE"
    w = light["window"]
    portal.size, portal.size_y = w["z1"] - w["z0"], w["y1"] - w["y0"]
    portal.cycles.is_portal = True
    pobj = bpy.data.objects.new("Look window portal", portal)
    pobj.location = (w["x"] + 0.05, (w["y0"] + w["y1"]) / 2, (w["z0"] + w["z1"]) / 2)
    pobj.rotation_euler = (0.0, -math.pi / 2, 0.0)
    room.objects.link(pobj)
    if light["sun_strength"] > 0:
        sun = bpy.data.lights.new("Look sun", "SUN")
        sun.energy = light["sun_strength"]
        sun.angle = math.radians(light["sun_angle_deg"])
        sun.color = light["sun_color"]
        sobj = bpy.data.objects.new("Look sun", sun)
        sobj.rotation_euler = Vector(light["sun_direction"]).normalized().to_track_quat("-Z", "Y").to_euler()
        room.objects.link(sobj)

    # ---- materials
    mats = cfg["materials"]
    sofa = mats["upholstery"]
    if not sofa.get("keep_original"):
        linen = scanned_fabric("Look linen upholstery", assets / sofa["folder"], sofa["prefix"], sofa["res"], sofa)
        report["replaced"]["upholstery"] = sum(replace_material(n, linen) for n in UPHOLSTERY_MATERIALS)
    pil = mats["pillow"]
    cotton = scanned_fabric("Look pillow cotton", assets / pil["folder"], pil["prefix"], pil["res"], pil)
    report["replaced"]["pillow"] = replace_material("Pillow", cotton)
    ph = mats["phone"]
    back = plain("Look phone back glass", ph["back_color"], ph["back_roughness"], ph["back_coat"], ph["back_coat_roughness"])
    screen = plain("Look phone screen off", ph["screen_color"], ph["screen_roughness"], 1.0, 0.02)
    report["replaced"]["phone_body"] = replace_material("Body", back)
    report["replaced"]["phone_logo"] = replace_material("Logo", back)
    report["replaced"]["phone_screen"] = replace_material("Screen Image", screen)
    if ph.get("camera_module"):
        report["camera_module"] = generic_camera_module(ph["camera_module"], back, room)
    mug = mats["mug"]
    glaze = plain("Look mug glaze", mug["color"], mug["roughness"], mug["coat"], 0.03)
    report["replaced"]["mug_print"] = replace_material("coffee_cover designtexture", glaze)
    report["replaced"]["mug_body"] = replace_material("coffee_material white.001", glaze)

    # ---- render settings
    r = cfg["render"]
    cy = scene.cycles
    cy.samples = r["samples"]
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = r["adaptive_threshold"]
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.denoising_prefilter = "ACCURATE"
    cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    cy.seed = r["seed"]
    cy.use_animated_seed = False
    cy.blur_glossy = r["filter_glossy"]
    cy.sample_clamp_indirect = r["clamp_indirect"]
    cy.caustics_reflective = cy.caustics_refractive = False
    scene.render.use_persistent_data = False      # motion blur is on (Blender 4.3 persistent-data bug)
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = r["look"]
    scene.view_settings.exposure = r["exposure"]
    lens_finish(scene, r["vignette"])

    # The saved scene must render on any worker: pack the scanned images and the HDRI into it.
    report["packed_images"] = {}
    for image in bpy.data.images:
        if image.packed_file is None and image.filepath and Path(bpy.path.abspath(image.filepath)).is_file():
            source = Path(bpy.path.abspath(image.filepath)).resolve()
            image.pack()
            try:
                report["packed_images"][image.name] = "assets/" + str(source.relative_to(assets.resolve()))
            except ValueError:
                report["packed_images"][image.name] = str(source)
    after = _fingerprint()
    if after != before:
        raise RuntimeError("The look moved a simulated body or the camera")
    report["simulated_objects_and_camera_unchanged"] = True
    report["render"] = {"samples": cy.samples, "adaptive_threshold": cy.adaptive_threshold, "seed": cy.seed,
                        "denoiser": cy.denoiser, "persistent_data": scene.render.use_persistent_data,
                        "motion_blur": scene.render.use_motion_blur, "shutter_frames": scene.render.motion_blur_shutter,
                        "view_transform": "AgX", "look": r["look"], "exposure": r["exposure"]}
    return report
