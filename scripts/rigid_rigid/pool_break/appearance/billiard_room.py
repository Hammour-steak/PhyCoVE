"""The pub billiard room around the table: built brick walls, scanned boards,
a real fixture over the cloth and late-afternoon daylight through a side window.

This module builds an ordinary basement pub room:

* walls of scanned brick (Poly Haven ``brick_wall_001`` at 75 mm courses) over a
  scanned dark-wood skirting, a painted ceiling and scanned plank floor
  (``old_wooden_floor_02``), all UV-mapped in world metres so a brick is a brick
  next to a 57 mm ball;
* a vintage caged fluorescent fixture (``caged_hanging_light``) hung on its own
  chains over the table centre, its tubes the visible source of the light that
  falls on the cloth;
* three industrial wall sconces (two on the far wall, one over the barrel
  table), each lit by a bulb inside its own shade;
* one window in the right-hand brick wall: a real hole through the 0.2 m wall,
  a painted timber frame, thin float glass, a physical sky outside with a low
  sun that lays the window's patch on the far wall beyond the table, and a
  photograph of a
  distant city that only camera rays see through the glass;
* Poly Haven CC0 furniture by the walls -- a barrel table with two pub stools --
  and a wall clock, all placed by bounding-box anchors.

None of it is in the simulation. ``check_clearance`` refuses a take in which any
ball passes within 2 cm of a piece, and ``check_line_of_sight`` refuses one in
which a piece hides a ball from the camera, on every frame of the case being
rendered. The cloth, cushions and rails the balls touch are the table model
fitted to the simulation's planes (``table_model``).

All Poly Haven assets are CC0 (https://polyhaven.com/license) and are listed in
the repository's ``assets.json`` under ``polyhaven/pool_break``.
"""

from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

from pcve_assets import asset as _pcve_asset

ASSET_DIR = _pcve_asset("polyhaven/pool_break")

# ------------------------------------------------------------------ the plan
# Wall faces in world metres (felt plane is z = 0, table centred on the origin,
# long axis along x). The far wall and the two side walls frame the view of the
# fixed camera; the wall behind the camera (camera at x = 1.90) closes the room
# for the daylight.
ROOM_X = (-2.29, 2.30)
ROOM_Y = (-1.89, 1.89)
WALL_THICK = 0.20
# 2.30 m floor to ceiling, a basement bar. The fixture's chains are 0.55 m and
# its body 0.20 m, so this hangs the lamp's underside 1.56 m above the floor --
# 0.81 m above the cloth, inside the usual 0.8-0.9 m for a pool table light.
CEILING_ABOVE_FLOOR = 2.30
SKIRT_HEIGHT = 0.12
SKIRT_THICK = 0.018

# The one window: in the right-hand (+y) wall, beside the far half of the
# table. Span along x and sill/head heights above the floor.
WINDOW_X = (-1.55, -0.45)
WINDOW_Z = (0.85, 2.05)

# Late-afternoon sun. HEADING is the direction the light travels across the
# floor, in degrees from +x towards +y: it comes in through the +y window and
# runs towards the far wall, so its patch lands beyond the table's far end --
# on the boards and up the brick -- and not on the cloth.
SUN_ELEVATION_DEG = 30.0
SUN_HEADING_DEG = -135.0
SUN_ENERGY = 10.0
SKY_STRENGTH = 1.3
# What the camera sees through the glass: Poly Haven's dusseldorf_bridge, a
# riverside with the city across the water -- far enough away to pass for a
# view at infinity (near content would be magnified to fill the pane).
WINDOW_VIEW = "dusseldorf_bridge/dusseldorf_bridge_2k.hdr"
WINDOW_VIEW_ROTATION_DEG = 0.0
WINDOW_VIEW_STRENGTH = 0.9

# The pool table light: centred over the table, long axis along it.
LAMP_XY = (0.0, 0.0)
# Two 1.2 m T8 tubes' worth of light leaving the underside of the fixture.
LAMP_POWER_W = 95.0
LAMP_COLOR = (1.0, 0.91, 0.80)          # ~3500 K
SCONCE_POWER_W = 18.0
SCONCE_COLOR = (1.0, 0.76, 0.52)        # ~2600 K incandescent
# Wall sconces: (wall, position along it, centre height above the floor). Two
# on the far wall either side of the table; one on the left wall over the barrel
# table, which no other source reaches.
SCONCES = (("far", -1.15, 1.62), ("far", 1.15, 1.62), ("left", -1.05, 1.62))

# Furniture: model, name, yaw, and a bounding-box anchor (x/y = box centre,
# x_min/x_max/y_min/y_max = box faces). Everything stands on the floor.
FURNITURE = (
    dict(model="wine_barrel_01", name="barrel table", yaw_deg=20.0, x=-1.80, y=-1.42),
    dict(model="bar_chair_round_01", name="pub stool near", yaw_deg=-30.0, x=-1.12, y=-1.52),
    dict(model="bar_chair_round_01", name="pub stool far", yaw_deg=60.0, x=-1.86, y=-0.78),
)
# On the far wall between the left sconce and the lamp: further right it hangs
# straight behind the fixture as seen from the camera.
WALL_CLOCK = dict(model="wall_clock", y=-0.45, height=1.50)

# A moving ball may come no closer than this to anything the simulator does not see.
CLEARANCE_M = 0.02


# ---------------------------------------------------------------- geometry


def _asset(relative: str) -> Path:
    path = ASSET_DIR / relative
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; run scripts/download_assets.py --scene pool_break")
    return path


def _box(name: str, lo, hi, material, *, uv: bool = True) -> bpy.types.Object:
    """An axis-aligned box from ``lo`` to ``hi`` with world-metre UVs.

    The mesh is built in world coordinates (object at the origin), and every
    face gets UVs from the two world axes in its plane, oriented so the image
    reads upright from inside the room. Neighbouring boxes therefore continue
    the same brick courses and boards, and the tangent-space normal maps get a
    proper tangent frame.
    """
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    lo, hi = Vector(lo), Vector(hi)
    for v in bm.verts:
        v.co = Vector(tuple(lo[i] if v.co[i] < 0 else hi[i] for i in range(3)))
    if uv:
        layer = bm.loops.layers.uv.new("UVMap")
        for face in bm.faces:
            n = face.normal
            axis = max(range(3), key=lambda i: abs(n[i]))
            for loop in face.loops:
                p = loop.vert.co
                if axis == 0:
                    loop[layer].uv = (p.y if n.x > 0 else -p.y, p.z)
                elif axis == 1:
                    loop[layer].uv = (-p.x if n.y > 0 else p.x, p.z)
                else:
                    loop[layer].uv = (p.x, p.y)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _aim(obj: bpy.types.Object, point) -> None:
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


# --------------------------------------------------------------- materials


def _principled(name: str, color, roughness: float) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = (*color, 1.0)
    return mat


def _scanned(name: str, asset_id: str, tile_m: float, *, roughness_min: float = 0.0,
             value: float = 1.0) -> bpy.types.Material:
    """A Poly Haven texture set (colour, roughness, OpenGL normal) at its real size.

    ``value`` scales the albedo, for a scan photographed lighter than the
    surface it stands in for; ``roughness_min`` keeps a lacquered scan from
    mirroring the lamp.
    """
    mat = _principled(name, (0.3, 0.2, 0.15), 0.6)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0 / tile_m, 1.0 / tile_m, 1.0)
    links.new(coord.outputs["UV"], mapping.inputs["Vector"])

    def scan(kind: str, colour: bool):
        node = nodes.new("ShaderNodeTexImage")
        # Poly Haven names the colour map "_diff_" on most sets and "_diffuse_" on older ones.
        name = f"{asset_id}/{asset_id}_{kind}_2k.jpg"
        if kind == "diff" and not (ASSET_DIR / name).is_file():
            name = f"{asset_id}/{asset_id}_diffuse_2k.jpg"
        node.image = bpy.data.images.load(str(_asset(name)), check_existing=True)
        if not colour:
            node.image.colorspace_settings.name = "Non-Color"
        node.extension = "REPEAT"
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node.outputs["Color"]

    color = scan("diff", True)
    if value != 1.0:
        grade = nodes.new("ShaderNodeHueSaturation")
        grade.inputs["Value"].default_value = value
        links.new(color, grade.inputs["Color"])
        color = grade.outputs["Color"]
    links.new(color, bsdf.inputs["Base Color"])
    rough = scan("rough", False)
    if roughness_min > 0.0:
        clamp = nodes.new("ShaderNodeMath")
        clamp.operation = "MAXIMUM"
        clamp.inputs[1].default_value = roughness_min
        links.new(rough, clamp.inputs[0])
        rough = clamp.outputs["Value"]
    links.new(rough, bsdf.inputs["Roughness"])
    normal = nodes.new("ShaderNodeNormalMap")
    normal.uv_map = "UVMap"
    links.new(scan("nor_gl", False), normal.inputs["Color"])
    links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _ceiling_paint() -> bpy.types.Material:
    """Flat white emulsion that drifts a few percent over a metre."""
    mat = _principled("ceiling emulsion", (0.70, 0.69, 0.66), 0.9)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    position = nodes.new("ShaderNodeNewGeometry")
    drift = nodes.new("ShaderNodeTexNoise")
    drift.inputs["Scale"].default_value = 0.8
    links.new(position.outputs["Position"], drift.inputs["Vector"])
    tone = nodes.new("ShaderNodeValToRGB")
    tone.color_ramp.elements[0].color = (0.66, 0.65, 0.62, 1.0)
    tone.color_ramp.elements[1].color = (0.72, 0.71, 0.68, 1.0)
    links.new(drift.outputs["Fac"], tone.inputs["Fac"])
    links.new(tone.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    return mat


def _thin_glass() -> bpy.types.Material:
    """Thin float glass: a Fresnel reflection over a see-through layer.

    Shaded as transparent so rays through it stay camera rays (the world shows
    the city photograph to the camera alone, while the room is lit by the
    physical sky). Cycles' Fresnel node treats a back face as glass-to-air, so
    a ray leaving the pane past 41 degrees would be totally reflected and the
    window would turn black at the grazing angle this camera sees it at;
    feeding the inverse IOR on back faces cancels that.
    """
    mat = bpy.data.materials.new("clear float glass")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != "OUTPUT_MATERIAL"]:
        nodes.remove(node)
    clear = nodes.new("ShaderNodeBsdfTransparent")
    reflection = nodes.new("ShaderNodeBsdfGlossy")
    reflection.inputs["Roughness"].default_value = 0.0
    fresnel = nodes.new("ShaderNodeFresnel")
    geometry = nodes.new("ShaderNodeNewGeometry")
    ior = nodes.new("ShaderNodeMath")
    ior.operation = "MULTIPLY_ADD"
    ior.inputs[1].default_value = 1.0 / 1.52 - 1.52
    ior.inputs[2].default_value = 1.52
    links.new(geometry.outputs["Backfacing"], ior.inputs[0])
    links.new(ior.outputs["Value"], fresnel.inputs["IOR"])
    pane = nodes.new("ShaderNodeMixShader")
    links.new(fresnel.outputs["Fac"], pane.inputs["Fac"])
    links.new(clear.outputs["BSDF"], pane.inputs[1])
    links.new(reflection.outputs["BSDF"], pane.inputs[2])
    links.new(pane.outputs["Shader"], nodes["Material Output"].inputs["Surface"])
    return mat


# --------------------------------------------------------------- the shell


def build_shell(floor_z: float) -> dict:
    """Floor, ceiling, four brick walls (one with a window), skirting."""
    ceiling_z = floor_z + CEILING_ABOVE_FLOOR
    (x0, x1), (y0, y1) = ROOM_X, ROOM_Y
    t = WALL_THICK
    # Poly Haven lists this scan as 3 m across, but it holds 24 courses: at 3 m
    # a course is 125 mm and every brick reads twice life size next to the
    # table. 1.8 m gives the 75 mm course of a standard 65 mm brick.
    brick = _scanned("brick wall (scanned)", "brick_wall_001", 1.8, roughness_min=0.55)
    boards = _scanned("plank floor (scanned)", "old_wooden_floor_02", 2.03, roughness_min=0.32)
    skirting = _scanned("dark wood skirting (scanned)", "dark_wood", 2.0, roughness_min=0.38)

    # The floor and ceiling run under and over the walls: a seam where two boxes
    # only touch along an edge shows as a pinhole of daylight.
    _box("floor", (x0 - t, y0 - t, floor_z - 0.10), (x1 + t, y1 + t, floor_z), boards)
    _box("ceiling", (x0 - t, y0 - t, ceiling_z), (x1 + t, y1 + t, ceiling_z + 0.12), _ceiling_paint())

    z_lo, z_hi = floor_z - 0.05, ceiling_z + 0.05
    _box("wall far (x-)", (x0 - t, y0 - t, z_lo), (x0, y1 + t, z_hi), brick)
    _box("wall behind camera (x+)", (x1, y0 - t, z_lo), (x1 + t, y1 + t, z_hi), brick)
    _box("wall left (y-)", (x0, y0 - t, z_lo), (x1, y0, z_hi), brick)
    # The right wall is four pieces round the window opening, so the reveal
    # shows the wall's full thickness.
    wx0, wx1 = WINDOW_X
    wz0, wz1 = (floor_z + v for v in WINDOW_Z)
    _box("wall right (y+) before window", (x0, y1, z_lo), (wx0, y1 + t, z_hi), brick)
    _box("wall right (y+) after window", (wx1, y1, z_lo), (x1, y1 + t, z_hi), brick)
    _box("wall right (y+) below window", (wx0, y1, z_lo), (wx1, y1 + t, wz0), brick)
    _box("wall right (y+) above window", (wx0, y1, wz1), (wx1, y1 + t, z_hi), brick)

    # Skirting proud of the brick, mitred by overlap at the corners.
    s, h = SKIRT_THICK, floor_z + SKIRT_HEIGHT
    _box("skirting far", (x0, y0, floor_z), (x0 + s, y1, h), skirting)
    _box("skirting behind camera", (x1 - s, y0, floor_z), (x1, y1, h), skirting)
    _box("skirting left", (x0, y0, floor_z), (x1, y0 + s, h), skirting)
    _box("skirting right", (x0, y1 - s, floor_z), (x1, y1, h), skirting)

    window = build_window(floor_z, skirting)
    print(f"[room] shell: floor z={floor_z:.4f}, ceiling z={ceiling_z:.4f}, "
          f"walls x={ROOM_X} y={ROOM_Y}", flush=True)
    return {"floor_z": floor_z, "ceiling_z": ceiling_z, "window": window}


def build_window(floor_z: float, board_material) -> dict:
    """A painted timber casement set in the middle of the reveal, glazed with thin glass."""
    (wx0, wx1), y1, t = WINDOW_X, ROOM_Y[1], WALL_THICK
    wz0, wz1 = (floor_z + v for v in WINDOW_Z)
    paint = _principled("window frame paint", (0.045, 0.075, 0.058), 0.42)
    bsdf = paint.node_tree.nodes["Principled BSDF"]
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.25
    ya, yb = y1 + 0.075, y1 + 0.125            # frame depth inside the reveal
    bar = 0.06
    _box("window head", (wx0, ya, wz1 - bar), (wx1, yb, wz1), paint)
    _box("window bottom rail", (wx0, ya, wz0), (wx1, yb, wz0 + bar), paint)
    _box("window jamb far", (wx0, ya, wz0 + bar), (wx0 + bar, yb, wz1 - bar), paint)
    _box("window jamb near", (wx1 - bar, ya, wz0 + bar), (wx1, yb, wz1 - bar), paint)
    xm = (wx0 + wx1) / 2.0
    _box("window mullion", (xm - 0.025, ya + 0.004, wz0 + bar), (xm + 0.025, yb - 0.004, wz1 - bar), paint)
    zt = wz0 + 0.68 * (wz1 - wz0)
    _box("window transom", (wx0 + bar, ya + 0.004, zt - 0.022), (wx1 - bar, yb - 0.004, zt + 0.022), paint)
    glass = _box("window glass", (wx0 + 0.02, (ya + yb) / 2 - 0.003, wz0 + 0.02),
                 (wx1 - 0.02, (ya + yb) / 2 + 0.003, wz1 - 0.02), _thin_glass(), uv=False)
    # Sunlight and skylight are not stopped by 6 mm of float glass.
    glass.visible_shadow = False
    glass.visible_diffuse = False
    # Interior window board in the same dark wood as the skirting.
    _box("window board", (wx0 - 0.04, y1 - 0.025, wz0 - 0.028), (wx1 + 0.04, ya, wz0), board_material)

    portal_data = bpy.data.lights.new("window sky portal", "AREA")
    portal_data.shape = "RECTANGLE"
    portal_data.size, portal_data.size_y = wx1 - wx0, wz1 - wz0
    portal_data.cycles.is_portal = True
    portal = bpy.data.objects.new("window sky portal", portal_data)
    bpy.context.scene.collection.objects.link(portal)
    portal.location = (xm, y1 + t + 0.01, (wz0 + wz1) / 2.0)
    _aim(portal, portal.location + Vector((0.0, -1.0, 0.0)))

    # The ground outside stops sky light coming up from below; the camera looks
    # through it to the photograph.
    ground = _box("ground outside", (-60.0, y1 + t, floor_z - 0.4), (60.0, 60.0, floor_z - 0.1),
                  _principled("pavement outside", (0.20, 0.19, 0.17), 0.9), uv=False)
    ground.visible_camera = False
    return {"x": [wx0, wx1], "z": [round(wz0, 4), round(wz1, 4)], "wall_y": y1}


def daylight() -> None:
    """A sun lamp and a physical sky outside the window; the city photograph for camera rays."""
    el, heading = math.radians(SUN_ELEVATION_DEG), math.radians(SUN_HEADING_DEG)
    travel = Vector((math.cos(el) * math.cos(heading), math.cos(el) * math.sin(heading), -math.sin(el)))
    sun_data = bpy.data.lights.new("late afternoon sun", "SUN")
    sun_data.energy = SUN_ENERGY
    sun_data.angle = math.radians(0.53)
    sun_data.color = (1.0, 0.90, 0.78)
    sun = bpy.data.objects.new("late afternoon sun", sun_data)
    bpy.context.scene.collection.objects.link(sun)
    sun.location = Vector((sum(WINDOW_X) / 2.0, ROOM_Y[1], 1.0)) - 6.0 * travel
    _aim(sun, sun.location + travel)

    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new("late afternoon sky")
    scene.world.use_nodes = True
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts the sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(-travel.x, -travel.y)
    sky.air_density, sky.dust_density = 1.0, 2.5
    lighting = nodes["Background"]
    links.new(sky.outputs["Color"], lighting.inputs["Color"])
    lighting.inputs["Strength"].default_value = SKY_STRENGTH

    coord = nodes.new("ShaderNodeTexCoord")
    turn = nodes.new("ShaderNodeMapping")
    turn.vector_type = "VECTOR"
    turn.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(WINDOW_VIEW_ROTATION_DEG))
    photo = nodes.new("ShaderNodeTexEnvironment")
    photo.image = bpy.data.images.load(str(_asset(WINDOW_VIEW)), check_existing=True)
    links.new(coord.outputs["Generated"], turn.inputs["Vector"])
    links.new(turn.outputs["Vector"], photo.inputs["Vector"])
    view = nodes.new("ShaderNodeBackground")
    view.inputs["Strength"].default_value = WINDOW_VIEW_STRENGTH
    links.new(photo.outputs["Color"], view.inputs["Color"])
    path = nodes.new("ShaderNodeLightPath")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    links.new(lighting.outputs["Background"], mix.inputs[1])
    links.new(view.outputs["Background"], mix.inputs[2])
    links.new(mix.outputs["Shader"], nodes["World Output"].inputs["Surface"])


# ------------------------------------------------------------- furniture


def place_model(model: str, name: str, *, yaw_deg: float = 0.0, **anchor: float) -> dict:
    """Import a Poly Haven glTF, turn it about z and set its bounding box on an anchor.

    Anchor keys: ``x`` / ``y`` (box centre), ``x_min`` / ``x_max`` / ``y_min`` /
    ``y_max`` (box faces) and ``z`` (bottom of the box). Returns the placed
    world bounding box and the objects, for the clearance check.
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(_asset(f"{model}/{model}_1k.gltf")))
    imported = [o for o in bpy.data.objects if o not in before]
    for obj in imported:
        obj.animation_data_clear()
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world
    root.rotation_euler.z = math.radians(yaw_deg)
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == "MESH"]
    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material is not None and "glass" in slot.material.name.lower():
                slot.material = bpy.data.materials.get("clear float glass") or _thin_glass()
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    shift = Vector((0.0, 0.0, 0.0))
    for axis, index in (("x", 0), ("y", 1)):
        if axis in anchor:
            shift[index] = anchor[axis] - (lo[index] + hi[index]) / 2.0
        elif f"{axis}_min" in anchor:
            shift[index] = anchor[f"{axis}_min"] - lo[index]
        elif f"{axis}_max" in anchor:
            shift[index] = anchor[f"{axis}_max"] - hi[index]
    if "z" in anchor:
        shift.z = anchor["z"] - lo.z
    root.location = shift
    bpy.context.view_layer.update()
    return {"name": name, "model": model, "yaw_deg": yaw_deg, "objects": meshes,
            "bbox_min": [round(v, 4) for v in lo + shift], "bbox_max": [round(v, 4) for v in hi + shift]}


def _bbox_of(objs, predicate=None) -> tuple[Vector, Vector]:
    pts = []
    for obj in objs:
        for poly in obj.data.polygons:
            if predicate is None or predicate(obj, poly):
                pts.extend(obj.matrix_world @ obj.data.vertices[i].co for i in poly.vertices)
    return (Vector([min(p[i] for p in pts) for i in range(3)]),
            Vector([max(p[i] for p in pts) for i in range(3)]))


def _uses(material_word: str):
    def predicate(obj, poly) -> bool:
        mat = obj.data.materials[poly.material_index] if obj.data.materials else None
        return mat is not None and material_word in mat.name.lower()
    return predicate


def _area(name: str, location, size, size_y, power: float, color, *, camera=False, glossy=False):
    data = bpy.data.lights.new(name, "AREA")
    data.shape = "RECTANGLE"
    data.size, data.size_y = size, size_y
    data.energy = power
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    _aim(obj, Vector(location) + Vector((0.0, 0.0, -1.0)))
    obj.visible_camera = camera
    obj.visible_glossy = glossy
    return obj


def _glow_only_where_seen(material: bpy.types.Material, strength: float, *, color=None,
                          shadow_transparent: bool = False) -> None:
    """Let an emissive tube or bulb glow for camera and reflection rays only.

    The light it puts on the room comes from the lamp object inside the
    fixture; letting diffuse rays pick up the emissive mesh as well would count
    the same light twice and make the fixture a noisy mesh light. A bulb that
    has a point light at its centre must also let shadow rays through, or its
    own glass would shade the lamp inside it.
    """
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    if color is not None:
        for link in list(bsdf.inputs["Emission Color"].links):
            links.remove(link)
        bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
    path = nodes.new("ShaderNodeLightPath")
    seen = nodes.new("ShaderNodeMath")
    seen.operation = "MAXIMUM"
    links.new(path.outputs["Is Camera Ray"], seen.inputs[0])
    links.new(path.outputs["Is Glossy Ray"], seen.inputs[1])
    gain = nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = strength
    links.new(seen.outputs["Value"], gain.inputs[0])
    links.new(gain.outputs["Value"], bsdf.inputs["Emission Strength"])
    if shadow_transparent:
        output = next(n for n in nodes if n.type == "OUTPUT_MATERIAL")
        surface = output.inputs["Surface"].links[0].from_socket
        mix = nodes.new("ShaderNodeMixShader")
        clear = nodes.new("ShaderNodeBsdfTransparent")
        links.new(path.outputs["Is Shadow Ray"], mix.inputs["Fac"])
        links.new(surface, mix.inputs[1])
        links.new(clear.outputs["BSDF"], mix.inputs[2])
        links.new(mix.outputs["Shader"], output.inputs["Surface"])
    if hasattr(material, "cycles") and hasattr(material.cycles, "emission_sampling"):
        material.cycles.emission_sampling = "NONE"


def hang_lamp(ceiling_z: float) -> dict:
    """The caged fluorescent fixture on its chains, and the light leaving its tubes.

    The model's origin is the ceiling plates, so it hangs from the ceiling as
    authored. The light is a rectangle the size of the tube pair just under the
    tubes, aimed down: the fixture's own housing and cage shadow it, and the
    tubes' emissive faces are what the camera and the balls' reflections see.
    """
    piece = place_model("caged_hanging_light", "pool table light", yaw_deg=0.0,
                        x=LAMP_XY[0], y=LAMP_XY[1], z=ceiling_z - 0.7501)
    meshes = piece["objects"]
    for obj in meshes:
        for mat in obj.data.materials:
            if mat is not None and mat.use_nodes:
                _glow_only_where_seen(mat, 40.0)
    lo, hi = Vector(piece["bbox_min"]), Vector(piece["bbox_max"])
    under = lo.z + 0.035
    _area("pool table light tubes", (LAMP_XY[0], LAMP_XY[1], under),
          0.94 * (hi.x - lo.x), 0.55 * (hi.y - lo.y), LAMP_POWER_W, LAMP_COLOR)
    print(f"[room] lamp: bbox {piece['bbox_min']} .. {piece['bbox_max']}, "
          f"underside {lo.z:.3f} m ({lo.z:.3f} above the cloth), light plane z={under:.3f}", flush=True)
    return piece


def hang_sconces(floor_z: float) -> list[dict]:
    """The wall sconces, each with a bulb-sized light inside its own shade."""
    pieces = []
    for index, (wall, along, height) in enumerate(SCONCES):
        # The sconce's backplate is its +y face and the arm reaches to -y: a
        # +90 degree turn stands it on the far wall facing into the room, a
        # 180 degree turn on the left (-y) wall.
        if wall == "far":
            anchor = dict(yaw_deg=90.0, x_min=ROOM_X[0] + 0.001, y=along)
        else:
            anchor = dict(yaw_deg=180.0, y_min=ROOM_Y[0] + 0.001, x=along)
        piece = place_model("industrial_wall_sconce", f"wall sconce {index + 1}",
                            z=floor_z + height - 0.17, **anchor)
        bulb_lo, bulb_hi = _bbox_of(piece["objects"], _uses("bulb"))
        bulb = (bulb_lo + bulb_hi) / 2.0
        data = bpy.data.lights.new(f"sconce bulb {index + 1}", "POINT")
        data.energy = SCONCE_POWER_W
        data.color = SCONCE_COLOR
        data.shadow_soft_size = 0.025
        light = bpy.data.objects.new(f"sconce bulb {index + 1}", data)
        bpy.context.scene.collection.objects.link(light)
        light.location = bulb
        light.visible_camera = False
        light.visible_glossy = False
        for obj in piece["objects"]:
            for mat in obj.data.materials:
                if mat is not None and "bulb" in mat.name.lower() and not mat.get("pcve_glow"):
                    _glow_only_where_seen(mat, 25.0, color=SCONCE_COLOR, shadow_transparent=True)
                    mat["pcve_glow"] = True
        piece["bulb"] = [round(v, 4) for v in bulb]
        pieces.append(piece)
    return pieces


def furnish(floor_z: float) -> list[dict]:
    pieces = [place_model(spec["model"], spec["name"], yaw_deg=spec.get("yaw_deg", 0.0),
                          **{k: v for k, v in spec.items() if k not in ("model", "name", "yaw_deg")},
                          z=floor_z)
              for spec in FURNITURE]
    clock = place_model(WALL_CLOCK["model"], "wall clock", yaw_deg=90.0, x_min=ROOM_X[0] + 0.001,
                        y=WALL_CLOCK["y"], z=floor_z + WALL_CLOCK["height"] - 0.16)
    pieces.append(clock)
    return pieces


# ------------------------------------------------------------------ build


def build(floor_z: float) -> dict:
    """The whole room. Returns every placed piece for the clearance checks."""
    shell = build_shell(floor_z)
    daylight()
    pieces = [hang_lamp(shell["ceiling_z"])]
    pieces += hang_sconces(floor_z)
    pieces += furnish(floor_z)
    for piece in pieces:
        print(f"[room] {piece['name']}: {piece['bbox_min']} .. {piece['bbox_max']}", flush=True)
    return {"shell": shell, "pieces": pieces}


# ----------------------------------------------------------------- checks


def check_clearance(pieces: list[dict], frames: list[dict], slots, radius: float,
                    margin: float = CLEARANCE_M) -> dict:
    """Smallest gap between any ball, on any frame, and each piece's bounding box."""
    centres = [Vector(frame[f"{slot}_location"]) for frame in frames for slot in slots]
    gaps = {}
    for piece in pieces:
        lo, hi = Vector(piece["bbox_min"]), Vector(piece["bbox_max"])
        gap = min(math.sqrt(sum(max(lo[i] - c[i], 0.0, c[i] - hi[i]) ** 2 for i in range(3)))
                  for c in centres) - radius
        gaps[piece["name"]] = round(gap, 3)
        if gap < margin:
            raise ValueError(f"a ball passes within {gap:.3f} m of {piece['name']}; move the piece")
    print("[room] clearance to balls: " + ", ".join(f"{k} {v:.2f} m" for k, v in gaps.items()), flush=True)
    return gaps


def check_line_of_sight(pieces: list[dict], frames: list[dict], slots, radius: float,
                        camera: bpy.types.Object) -> int:
    """Refuse a take in which a placed piece stands between the camera and a ball.

    Rays go from the camera to the ball's centre and to its top; whatever they
    hit first short of the ball is looked up, and only the pieces built here
    count (the table's own rails may legitimately hide a ball's lower half).
    """
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ours = {obj.name for piece in pieces for obj in piece["objects"]}
    origin = camera.matrix_world.translation.copy()
    rays = 0
    for frame in frames:
        for slot in slots:
            centre = Vector(frame[f"{slot}_location"])
            for target in (centre, centre + Vector((0.0, 0.0, radius))):
                direction = target - origin
                distance = direction.length - radius
                hit, _loc, _n, _i, obj, _m = scene.ray_cast(depsgraph, origin, direction.normalized(),
                                                            distance=distance)
                rays += 1
                if hit and obj is not None and obj.name in ours:
                    raise ValueError(f"{obj.name} hides {slot} from the camera on frame "
                                     f"{frame['frame_index']}; move the piece")
    print(f"[room] line of sight: {rays} camera-to-ball rays, none blocked by room pieces", flush=True)
    return rays
