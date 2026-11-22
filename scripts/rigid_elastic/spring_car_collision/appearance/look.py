"""Current look of spring_car_collision: a sunlit living-room floor.

Appearance only. Nothing here reads or writes solver state: the floor is the
physical plane z = 0, every moving part keeps the pose and size the solver
gives it, and every static addition is checked to stay outside the swept
volume of all six cases (MOTION_KEEPOUT).

Room: 4.4 x 6.0 x 2.6 m with lacquered oak strip flooring, painted plaster
walls and ceiling and skirting boards. Daylight enters only through two
windows, both out of frame: a 1.9 x 1.95 m window in the left wall, through
which a 0.53 degree sun lamp throws a patch across the launch track, and a
1.8 x 1.4 m window in the wall behind the camera that lets sky light onto the
far wall and the floor; the sky is the Poly Haven panorama
kloofendal_48d_partly_cloudy_puresky. There are no hidden fill lights. Against the
far wall: a walnut sideboard with rattan doors (modern_wooden_cabinet), a
potted plant and a wicker basket on the floor, a vase, a wooden bowl and a
small succulent on the sideboard. Camera: 50 mm, f/4, on a low tripod 2.4 m in front of the track
and 0.42 m above the floor, looking 5.2 degrees down; it frames x = -0.77 ..
0.96 m on the track (the motion spans -0.71 .. 0.90 m).
"""
from __future__ import annotations

import math
from pathlib import Path


FLOOR_Z = 0.0
EXPOSURE = 0.85  # AgX exposure (EV) of the camera
ROOM = {"x_min": -2.00, "x_max": 2.40, "y_front": -3.40, "y_back": 2.60, "ceiling_z": 2.60, "wall": 0.25}
WINDOW = {"y0": -1.40, "y1": 0.50, "z0": 0.30, "z1": 2.25}   # in the left wall, x = ROOM["x_min"]
REAR_WINDOW = {"x0": -0.70, "x1": 1.10, "z0": 0.80, "z1": 2.20}   # in the wall behind the camera, y = ROOM["y_front"]
SUN = {"direction": (0.80, 0.30, -0.52), "energy": 1.7, "angle_deg": 0.53, "color": (1.0, 0.95, 0.88)}
CAMERA = {"location": (0.095, -2.40, 0.42), "target": (0.095, 0.0, 0.20), "lens_mm": 50.0, "fstop": 4.0,
          "focus": (0.095, 0.0, 0.04), "sensor_width_mm": 36.0}
# Union of every case's swept volume (car body, wheels, block, added block,
# spring and launcher frame) plus 2 cm; static dressing must stay outside it.
MOTION_KEEPOUT = ((-0.73, -0.13, -0.001), (0.92, 0.13, 0.11))
POLYHAVEN = {"floor": "wood_floor", "plaster": "painted_plaster_wall", "sky": "kloofendal_48d_partly_cloudy_puresky",
             "sideboard": "modern_wooden_cabinet", "plant": "potted_plant_02", "basket": "wicker_basket_02",
             "vase": "ceramic_vase_04", "bowl": "wooden_bowl_02", "succulent": "potted_plant_04"}


def _bpy():
    import bpy
    return bpy


def _bs(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def principled(name, color, roughness=0.5, metallic=0.0, coat=0.0, coat_rough=0.1):
    bpy = _bpy()
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bs = _bs(mat)
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = roughness
    bs.inputs["Metallic"].default_value = metallic
    bs.inputs["Coat Weight"].default_value = coat
    bs.inputs["Coat Roughness"].default_value = coat_rough
    return mat


def box(name, center, size, mat, bevel=0.0, segments=3):
    bpy = _bpy()
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        obj.data.materials.append(mat)
    if bevel:
        m = obj.modifiers.new("Rounded arris", "BEVEL")
        m.width, m.segments, m.limit_method = bevel, segments, "ANGLE"
        obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL").keep_sharp = True
        for p in obj.data.polygons:
            p.use_smooth = True
    obj["look_role"] = "static"
    return obj


def _image(nodes, path, data):
    bpy = _bpy()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(path), check_existing=True)
    tex.image.colorspace_settings.name = "Non-Color" if data else "sRGB"
    return tex


def _files(folder, prefix):
    folder = Path(folder)
    found = {}
    for kind in ("diff", "rough", "nor_gl", "arm"):
        hits = sorted(folder.rglob(f"{prefix}_{kind}_*.jpg"))
        if hits:
            found[kind] = hits[-1] if kind != "diff" else hits[-1]
    return found


def scanned(name, folder, prefix, tile_m, vector="object", axes=(0, 1), rough_range=(0.4, 0.9),
            normal=1.0, tint=None, coat=0.0, coat_rough=0.15, desaturate=0.0):
    """PBR material from a Poly Haven diff / rough (or arm) / nor_gl set at real size.

    The texture coordinate is two chosen object axes divided by the scan's
    physical size, so the pattern keeps its real scale on every object.
    """
    bpy = _bpy()
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = _bs(mat)
    coord = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord.outputs["Object"], sep.inputs[0])
    comb = nodes.new("ShaderNodeCombineXYZ")
    links.new(sep.outputs["XYZ"[axes[0]]], comb.inputs[0])
    links.new(sep.outputs["XYZ"[axes[1]]], comb.inputs[1])
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs[3].default_value = 1.0 / tile_m
    links.new(comb.outputs[0], scale.inputs[0])
    files = _files(folder, prefix)
    diff = _image(nodes, files["diff"], False)
    links.new(scale.outputs[0], diff.inputs["Vector"])
    color = diff.outputs["Color"]
    if desaturate:
        hsv = nodes.new("ShaderNodeHueSaturation")
        hsv.inputs["Saturation"].default_value = 1.0 - desaturate
        links.new(color, hsv.inputs["Color"])
        color = hsv.outputs["Color"]
    if tint:
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs[7].default_value = (*tint, 1)
        links.new(color, mix.inputs[6])
        color = mix.outputs[2]
    links.new(color, bs.inputs["Base Color"])
    if "rough" in files:
        rough = _image(nodes, files["rough"], True)
        rough_out = rough.outputs["Color"]
    else:
        arm = _image(nodes, files["arm"], True)
        split = nodes.new("ShaderNodeSeparateColor")
        links.new(arm.outputs["Color"], split.inputs[0])
        rough, rough_out = arm, split.outputs["Green"]
    links.new(scale.outputs[0], rough.inputs["Vector"])
    remap = nodes.new("ShaderNodeMapRange")
    remap.inputs["To Min"].default_value, remap.inputs["To Max"].default_value = rough_range
    links.new(rough_out, remap.inputs["Value"])
    links.new(remap.outputs["Result"], bs.inputs["Roughness"])
    nor = _image(nodes, files["nor_gl"], True)
    links.new(scale.outputs[0], nor.inputs["Vector"])
    nmap = nodes.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = normal
    links.new(nor.outputs["Color"], nmap.inputs["Color"])
    links.new(nmap.outputs["Normal"], bs.inputs["Normal"])
    bs.inputs["Coat Weight"].default_value = coat
    bs.inputs["Coat Roughness"].default_value = coat_rough
    mat["look_scan"] = f"{prefix} ({tile_m:.2f} m tile)"
    return mat


def plaster(folder, name, color):
    mat = scanned(name, folder, POLYHAVEN["plaster"], 2.0, axes=(0, 2), rough_range=(0.78, 0.95), normal=0.45,
                  tint=color, desaturate=0.85)
    return mat


def build_room(ph):
    """Floor, ceiling, four walls (window opening in the left one), skirting boards."""
    r, w = ROOM, WINDOW
    t = r["wall"]
    wall_back = plaster(ph / POLYHAVEN["plaster"], "Walls | warm white emulsion on plaster", (0.88, 0.83, 0.74))
    wall_side = scanned("Side walls | warm white emulsion", ph / POLYHAVEN["plaster"], POLYHAVEN["plaster"], 2.0,
                        axes=(1, 2), rough_range=(0.78, 0.95), normal=0.45, tint=(0.88, 0.83, 0.74), desaturate=0.85)
    ceiling = scanned("Ceiling | white emulsion", ph / POLYHAVEN["plaster"], POLYHAVEN["plaster"], 2.0,
                      axes=(0, 1), rough_range=(0.80, 0.95), normal=0.3, tint=(0.90, 0.89, 0.86), desaturate=0.9)
    floor = scanned("Floor | oak strip flooring, satin lacquer", ph / POLYHAVEN["floor"], POLYHAVEN["floor"], 1.7,
                    axes=(1, 0), rough_range=(0.30, 0.62), normal=0.7, tint=(0.92, 0.84, 0.74), coat=0.35, coat_rough=0.16)
    x_mid, y_mid = (r["x_min"] + r["x_max"]) / 2, (r["y_front"] + r["y_back"]) / 2
    sx, sy, sz = r["x_max"] - r["x_min"], r["y_back"] - r["y_front"], r["ceiling_z"] - FLOOR_Z
    zc = (FLOOR_Z + r["ceiling_z"]) / 2
    xl = r["x_min"] - t / 2
    parts = [box("Room | floor (physical plane z = 0)", (x_mid, y_mid, FLOOR_Z - 0.02), (sx + 2 * t, sy + 2 * t, 0.04), floor),
             box("Room | ceiling", (x_mid, y_mid, r["ceiling_z"] + 0.02), (sx + 2 * t, sy + 2 * t, 0.04), ceiling),
             box("Room | far wall", (x_mid, r["y_back"] + t / 2, zc), (sx + 2 * t, t, sz), wall_back),
             box("Room | right wall", (r["x_max"] + t / 2, y_mid, zc), (t, sy, sz), wall_side),
             box("Room | left wall below window", (xl, y_mid, (FLOOR_Z + w["z0"]) / 2), (t, sy, w["z0"] - FLOOR_Z), wall_side),
             box("Room | left wall above window", (xl, y_mid, (w["z1"] + r["ceiling_z"]) / 2), (t, sy, r["ceiling_z"] - w["z1"]), wall_side),
             box("Room | left wall, front pier", (xl, (r["y_front"] + w["y0"]) / 2, (w["z0"] + w["z1"]) / 2), (t, w["y0"] - r["y_front"], w["z1"] - w["z0"]), wall_side),
             box("Room | left wall, back pier", (xl, (w["y1"] + r["y_back"]) / 2, (w["z0"] + w["z1"]) / 2), (t, r["y_back"] - w["y1"], w["z1"] - w["z0"]), wall_side)]
    skirting = principled("Skirting | white satin paint on MDF", (0.80, 0.79, 0.76), 0.38, coat=0.2)
    h, d = 0.10, 0.016
    parts += [box("Room | skirting (far)", (x_mid, r["y_back"] - d / 2, h / 2), (sx, d, h), skirting, 0.003),
              box("Room | skirting (behind camera)", (x_mid, r["y_front"] + d / 2, h / 2), (sx, d, h), skirting, 0.003),
              box("Room | skirting (right)", (r["x_max"] - d / 2, y_mid, h / 2), (d, sy, h), skirting, 0.003),
              box("Room | skirting (left)", (r["x_min"] + d / 2, y_mid, h / 2), (d, sy, h), skirting, 0.003)]
    return parts


def glass_material():
    """Window glass: refracting for the camera, transparent for shadow and diffuse rays (no caustic blackout)."""
    bpy = _bpy()
    mat = bpy.data.materials.new("Window | float glass")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = next(n for n in nodes if n.type == "OUTPUT_MATERIAL")
    bs = _bs(mat)
    bs.inputs["Base Color"].default_value = (0.92, 0.96, 0.95, 1)
    bs.inputs["Roughness"].default_value = 0.0
    bs.inputs["Transmission Weight"].default_value = 1.0
    bs.inputs["IOR"].default_value = 1.52
    clear = nodes.new("ShaderNodeBsdfTransparent")
    path = nodes.new("ShaderNodeLightPath")
    either = nodes.new("ShaderNodeMath")
    either.operation = "MAXIMUM"
    links.new(path.outputs["Is Shadow Ray"], either.inputs[0])
    links.new(path.outputs["Is Diffuse Ray"], either.inputs[1])
    mix = nodes.new("ShaderNodeMixShader")
    links.new(either.outputs[0], mix.inputs["Fac"])
    links.new(bs.outputs[0], mix.inputs[1])
    links.new(clear.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def build_window():
    """Left-wall window: painted timber frame, one fixed pane, interior sill. Out of frame; it shapes the light."""
    w, r = WINDOW, ROOM
    paint = principled("Window | white gloss paint on timber", (0.82, 0.81, 0.78), 0.30, coat=0.3, coat_rough=0.2)
    glass = glass_material()
    x_in, depth, fw = r["x_min"] - 0.08, 0.07, 0.07
    ym, zm = (w["y0"] + w["y1"]) / 2, (w["z0"] + w["z1"]) / 2
    parts = [box("Window | frame head", (x_in, ym, w["z1"] - fw / 2), (depth, w["y1"] - w["y0"], fw), paint, 0.003),
             box("Window | frame bottom rail", (x_in, ym, w["z0"] + fw / 2), (depth, w["y1"] - w["y0"], fw), paint, 0.003),
             box("Window | frame jamb", (x_in, w["y0"] + fw / 2, zm), (depth, fw, w["z1"] - w["z0"]), paint, 0.003),
             box("Window | frame jamb", (x_in, w["y1"] - fw / 2, zm), (depth, fw, w["z1"] - w["z0"]), paint, 0.003),
             box("Window | pane", (x_in, ym, zm), (0.006, w["y1"] - w["y0"] - 2 * fw + 0.01, w["z1"] - w["z0"] - 2 * fw + 0.01), glass),
             box("Window | interior sill", (r["x_min"] + 0.03, ym, w["z0"] - 0.015), (0.22, w["y1"] - w["y0"] + 0.12, 0.03),
                 principled("Window | sill board, white paint", (0.80, 0.79, 0.76), 0.34, coat=0.25), 0.003)]
    return parts


def stands_on_surface(members, label, tolerance=0.012, inset=0.15):
    """Fail if a prop's footprint hangs in the air: rays down from five footprint points must hit at its base."""
    import pcve_realism_kit as kit
    from mathutils import Vector
    bpy = _bpy()
    low, high = kit.world_bbox(members)
    for m in members:
        m.hide_viewport = True
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    try:
        for fx, fy in ((.5, .5), (inset, inset), (1 - inset, inset), (inset, 1 - inset), (1 - inset, 1 - inset)):
            origin = Vector((low.x + (high.x - low.x) * fx, low.y + (high.y - low.y) * fy, low.z + tolerance))
            hit, point, *_ = bpy.context.scene.ray_cast(graph, origin, Vector((0, 0, -1)))
            if not hit or abs(point.z - low.z) > tolerance:
                raise RuntimeError(f"{label} overhangs at {fx},{fy}: surface {point.z if hit else None} vs base {low.z}")
    finally:
        for m in members:
            m.hide_viewport = False
        bpy.context.view_layer.update()


def build_rear_window(ph):
    """Wall behind the camera with a sky window: brings soft daylight onto the far wall and the floor."""
    r, w = ROOM, REAR_WINDOW
    t = r["wall"]
    wall = plaster(ph / POLYHAVEN["plaster"], "Walls | warm white emulsion on plaster (front)", (0.88, 0.83, 0.74))
    x_mid, sx = (r["x_min"] + r["x_max"]) / 2, r["x_max"] - r["x_min"]
    y = r["y_front"] - t / 2
    parts = [box("Room | front wall below window", (x_mid, y, (FLOOR_Z + w["z0"]) / 2), (sx + 2 * t, t, w["z0"] - FLOOR_Z), wall),
             box("Room | front wall above window", (x_mid, y, (w["z1"] + r["ceiling_z"]) / 2), (sx + 2 * t, t, r["ceiling_z"] - w["z1"]), wall),
             box("Room | front wall left pier", ((r["x_min"] - t + w["x0"]) / 2, y, (w["z0"] + w["z1"]) / 2), (w["x0"] - r["x_min"] + t, t, w["z1"] - w["z0"]), wall),
             box("Room | front wall right pier", ((w["x1"] + r["x_max"] + t) / 2, y, (w["z0"] + w["z1"]) / 2), (r["x_max"] + t - w["x1"], t, w["z1"] - w["z0"]), wall)]
    paint = principled("Window | white gloss paint on timber (front)", (0.82, 0.81, 0.78), 0.30, coat=0.3, coat_rough=0.2)
    yf, fw, depth = r["y_front"] - 0.08, 0.07, 0.07
    xm, zm = (w["x0"] + w["x1"]) / 2, (w["z0"] + w["z1"]) / 2
    parts += [box("Window (front) | head", (xm, yf, w["z1"] - fw / 2), (w["x1"] - w["x0"], depth, fw), paint, 0.003),
              box("Window (front) | bottom rail", (xm, yf, w["z0"] + fw / 2), (w["x1"] - w["x0"], depth, fw), paint, 0.003),
              box("Window (front) | jamb", (w["x0"] + fw / 2, yf, zm), (fw, depth, w["z1"] - w["z0"]), paint, 0.003),
              box("Window (front) | jamb", (w["x1"] - fw / 2, yf, zm), (fw, depth, w["z1"] - w["z0"]), paint, 0.003),
              box("Window (front) | mullion", (xm, yf, zm), (fw, depth, w["z1"] - w["z0"]), paint, 0.003),
              box("Window (front) | pane", (xm, yf, zm), (w["x1"] - w["x0"] - 2 * fw + 0.01, 0.006, w["z1"] - w["z0"] - 2 * fw + 0.01), glass_material())]
    return parts


def build_dressing(ph):
    """Furniture and props along the far wall (Poly Haven, real size), checked to stand and to stay clear."""
    import pcve_realism_kit as kit
    from mathutils import Vector
    r = ROOM
    placed = []

    def put(key, location, rot, rests=True):
        path = next((ph / POLYHAVEN[key]).glob("*.gltf"))
        root, members = kit.import_prop(path, "Dressing | " + POLYHAVEN[key], location, rot)
        if rests:
            stands_on_surface(members, POLYHAVEN[key])
        record = kit.assert_clear(members, MOTION_KEEPOUT, POLYHAVEN[key])
        for m in members:
            m.pass_index = 4
        placed.append(record)
        return members

    board = put("sideboard", (0.20, r["y_back"] - 0.30, FLOOR_Z), 0.0)
    top = max((m.matrix_world @ Vector(c)).z for m in board if m.type == "MESH" for c in m.bound_box)
    put("plant", (1.72, r["y_back"] - 0.42, FLOOR_Z), 0.6)
    put("basket", (-1.22, r["y_back"] - 0.30, FLOOR_Z), 2.4)
    put("vase", (-0.62, r["y_back"] - 0.28, top), 1.1)
    put("bowl", (0.35, r["y_back"] - 0.30, top), 0.3)
    put("succulent", (0.95, r["y_back"] - 0.26, top), 2.0)
    return placed, float(top)


def world(ph, scene, rotation_deg=0.0, strength=1.0):
    """Sky panorama seen through the window: the daylight besides the sun lamp."""
    bpy = _bpy()
    scene.world = bpy.data.worlds.new("World | partly cloudy sky")
    scene.world.use_nodes = True
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    env = nodes.new("ShaderNodeTexEnvironment")
    path = sorted((ph / POLYHAVEN["sky"]).glob("*.hdr"))[-1]
    env.image = bpy.data.images.load(str(path), check_existing=True)
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0, 0, math.radians(rotation_deg))
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    bg = nodes.get("Background")
    bg.inputs["Strength"].default_value = strength
    links.new(env.outputs["Color"], bg.inputs["Color"])
    return {"hdri": path.name, "rotation_deg": rotation_deg, "strength": strength}


def sun_lamp():
    bpy = _bpy()
    from mathutils import Vector
    data = bpy.data.lights.new("Sun | afternoon sun through the left window", "SUN")
    data.energy, data.angle, data.color = SUN["energy"], math.radians(SUN["angle_deg"]), SUN["color"]
    obj = bpy.data.objects.new(data.name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.rotation_euler = Vector(SUN["direction"]).normalized().to_track_quat("-Z", "Y").to_euler()
    return dict(SUN)


def build(asset_dir, scene):
    """Whole static set. Returns a record for render_metadata.json."""
    ph = Path(asset_dir).parents[1] / "polyhaven"
    parts = build_room(ph) + build_window() + build_rear_window(ph)
    for obj in parts:
        obj.pass_index = 4
    dressing, sideboard_top = build_dressing(ph)
    light = {"world": world(ph, scene, rotation_deg=0.0, strength=7.0), "sun": sun_lamp()}
    return {"look": "sunlit living-room floor (appearance/look.py)", "room_m": ROOM, "window_m": WINDOW,
            "rear_window_m": REAR_WINDOW, "floor_z_m": FLOOR_Z, "polyhaven_assets": POLYHAVEN, "dressing": dressing,
            "sideboard_top_m": sideboard_top, "light": light, "motion_keepout_m": MOTION_KEEPOUT, "hidden_lights": 0}
