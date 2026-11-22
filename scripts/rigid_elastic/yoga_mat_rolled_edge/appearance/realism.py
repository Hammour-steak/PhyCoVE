"""Appearance overlay for the accepted base replay: a daylit exercise nook.

`render_source_review.py` runs with its `OVERLAY` hook set to `overlay`, which
runs after its room, lights and camera exist. Cache replay,
the exact collision surfaces, frame timing and the camera stay those of the base replay.
`--look base` renders the base look through the same path, for comparisons.
    <blender> -b --python-exit-code 1 --python realism.py -- --cache SIM/simulation.npz --out OUT [--look nook] ...
"""
from pathlib import Path
import math
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE), str(ROOT / "scripts")]
import pcve_realism_kit as kit
from pcve_assets import asset

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
LOOK = argv[argv.index("--look") + 1] if "--look" in argv else "nook"
if "--look" in argv:
    del argv[argv.index("--look"):argv.index("--look") + 2]
    sys.argv[sys.argv.index("--") + 1:] = argv

# Union of all six cases: the ball rolls along y = 0 between x = -1.6 and +0.6 m,
# the mat and the added block stay inside the same strip.
KEEPOUT = ((-1.75, -0.40, -0.01), (0.85, 0.40, 0.45))
EXPOSURE = float(argv[argv.index("--exposure") + 1]) if "--exposure" in argv else 2.8
if "--exposure" in argv:
    del argv[argv.index("--exposure"):argv.index("--exposure") + 2]
    sys.argv[sys.argv.index("--") + 1:] = argv


# Poly Haven CC0 sets used here, copied unchanged (see the folder's manifest.json)
POLYHAVEN = asset("scenes/yoga_mat_rolled_edge/room_dressing")
WINDOW = (-1.745, -0.615, 0.625, 1.815)          # opening inside the ivory window frame of the base scene: x0, x1, z0, z1
SUN = (0.80, 0.15, -0.45)                        # way the light travels: low afternoon sun through the left wall's window
SIDE_WINDOW = (-2.30, 1.05, 0.45, 2.15)          # left wall (x = -2.2), out of frame: y0, y1, z0, z1


def append_prop(name, location, rot_z=0.0, scale=1.0):
    """Append every object of a Poly Haven .blend; its bbox bottom centre goes to `location`."""
    import bpy
    from mathutils import Vector
    path = next((POLYHAVEN / name).glob("*.blend"))
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = list(src.objects)
    root = bpy.data.objects.new("Dressing " + name, None)
    bpy.context.collection.objects.link(root)
    members = []
    for obj in dst.objects:
        if obj is None or obj.type not in ("MESH", "EMPTY"):
            continue
        bpy.context.collection.objects.link(obj)
        if obj.parent is None:
            obj.parent = root
        members.append(obj)
    root.scale = (scale,) * 3
    root.rotation_euler = (0.0, 0.0, rot_z)
    bpy.context.view_layer.update()
    low, high = kit.world_bbox(members)
    root.location = Vector(location) - Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    bpy.context.view_layer.update()
    return kit.assert_clear(members, KEEPOUT, name)


def image_material(name, stem, folder, scale, tint=None, normal=0.6):
    """Poly Haven PBR set on object coordinates (`scale` repeats per metre)."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    coord, mapping = nodes.new("ShaderNodeTexCoord"), nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale,) * 3
    links.new(coord.outputs["Object"], mapping.inputs["Vector"])

    def tex(suffix, data):
        path = next(folder.glob(f"{stem}_{suffix}_*"))
        node = nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(path), check_existing=True)
        node.image.colorspace_settings.name = "Non-Color" if data else "sRGB"
        node.projection = "BOX"
        node.projection_blend = 0.2
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node
    color = tex("diff", False).outputs["Color"]
    if tint:
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs[7].default_value = (*tint, 1.0)
        links.new(color, mix.inputs[6])
        color = mix.outputs[2]
    links.new(color, bsdf.inputs["Base Color"])
    links.new(tex("rough", True).outputs["Color"], bsdf.inputs["Roughness"])
    nmap = nodes.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = normal
    links.new(tex("nor_gl", True).outputs["Color"], nmap.inputs["Color"])
    links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def linen_curtain(name, x0, x1, linen):
    """Sheer curtain panel: a pleated sheet hanging from z = 2.05 m, hem 25 mm above the floor."""
    import bpy
    nx, nz = 90, 40
    y0, top, bottom = 1.43, 2.05, 0.025
    verts, faces = [], []
    for k in range(nz + 1):
        z = bottom + (top - bottom) * k / nz
        flare = 1.0 + 0.35 * (1.0 - k / nz)             # pleats open towards the hem
        for i in range(nx + 1):
            u = i / nx
            x = x0 + (x1 - x0) * u
            y = y0 - 0.013 * flare * math.sin(2 * math.pi * u * (x1 - x0) / 0.11 + 0.6 * math.sin(3.1 * z))
            verts.append((x, y, z))
    for k in range(nz):
        for i in range(nx):
            a = k * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    solid = obj.modifiers.new("Woven thickness", "SOLIDIFY")
    solid.thickness = 0.0012
    mesh.materials.append(linen)
    return obj


def sheer_linen():
    """Linen weave that lets the window glow through it."""
    import bpy
    mat = image_material("Sheer natural linen (Poly Haven rough_linen)", "rough_linen", POLYHAVEN / "rough_linen", 6.0,
                         tint=(1.18, 1.14, 1.04), normal=0.4)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    out = nodes.get("Material Output")
    translucent = nodes.new("ShaderNodeBsdfTranslucent")
    translucent.inputs["Color"].default_value = (0.92, 0.86, 0.74, 1.0)
    links.new(bsdf.inputs["Normal"].links[0].from_socket, translucent.inputs["Normal"])
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.5
    links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    links.new(translucent.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def window_glass():
    """Clear float glass; shadow rays pass so the sun reaches the room without caustics."""
    import bpy
    mat = bpy.data.materials.new("Clear float glass")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    glass = nodes.new("ShaderNodeBsdfGlass")
    glass.inputs["Roughness"].default_value = 0.0
    glass.inputs["IOR"].default_value = 1.52
    glass.inputs["Color"].default_value = (0.93, 0.97, 0.96, 1.0)
    clear = nodes.new("ShaderNodeBsdfTransparent")
    clear.inputs["Color"].default_value = (0.90, 0.94, 0.93, 1.0)
    path = nodes.new("ShaderNodeLightPath")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(path.outputs["Is Shadow Ray"], mix.inputs["Fac"])
    links.new(glass.outputs["BSDF"], mix.inputs[1])
    links.new(clear.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def room_shell():
    """Walls, ceiling and a floor behind the camera, so all ambient light is the window's bounce."""
    wall = bpy_data().materials["Sage limewash plaster"]
    ceiling = kit.diffuse("Matt white ceiling", (0.80, 0.79, 0.76), 0.92)
    boards = kit.diffuse("Floor beyond the parquet", (0.30, 0.17, 0.08), 0.5)
    y0, y1, z0, z1 = SIDE_WINDOW
    front, back = -4.40, 1.60
    for label, (ya, yb, za, zb) in (("near", (front, y0, 0.0, 2.6)), ("far", (y1, back, 0.0, 2.6)),
                                    ("below", (y0, y1, 0.0, z0)), ("above", (y0, y1, z1, 2.6))):
        kit.plain_box(f"Room left wall {label} window", (-2.20, (ya + yb) / 2, (za + zb) / 2), (0.10, yb - ya, zb - za), wall)
    frame = kit.diffuse("Side window frame", (0.78, 0.75, 0.68), 0.45)
    for k in range(1, 4):
        kit.plain_box(f"Side window mullion {k}", (-2.20, y0 + (y1 - y0) * k / 4, (z0 + z1) / 2), (0.10, 0.045, z1 - z0), frame)
    kit.plain_box("Side window transom", (-2.20, (y0 + y1) / 2, z0 + 0.62 * (z1 - z0)), (0.10, y1 - y0, 0.045), frame)
    kit.plain_box("Room right wall", (2.90, (front + back) / 2, 1.30), (0.10, back - front, 2.60), wall)
    kit.plain_box("Room front wall", (0.35, front - 0.05, 1.30), (5.20, 0.10, 2.60), wall)
    kit.plain_box("Rear wall above 2.1 m", (0.35, 1.55, 2.35), (5.00, 0.10, 0.50), wall)
    kit.plain_box("Room ceiling", (0.35, (front + back) / 2, 2.65), (5.20, back - front, 0.10), ceiling)
    kit.plain_box("Floor behind the camera", (0.35, (front - 1.8) / 2, -0.035), (5.00, -1.8 - front, 0.07), boards)


def bpy_data():
    import bpy
    return bpy.data


def open_window(scene):
    import bpy
    O = bpy.data.objects
    x0, x1, z0, z1 = WINDOW
    cutter = kit.plain_box("Window opening cutter", ((x0 + x1) / 2, 1.55, (z0 + z1) / 2), (x1 - x0, 0.4, z1 - z0), None)
    cutter.hide_render = cutter.hide_viewport = True
    wall = O["Sage limewash rear wall"]
    hole = wall.modifiers.new("Window opening", "BOOLEAN")
    hole.operation, hole.object, hole.solver = "DIFFERENCE", cutter, "EXACT"
    bpy.data.objects.remove(O["Window daylight"])
    kit.plain_box("Window pane", ((x0 + x1) / 2, 1.56, (z0 + z1) / 2), (x1 - x0, 0.006, z1 - z0), window_glass())
    sill = kit.diffuse("Painted window sill", (0.78, 0.75, 0.68), 0.4)
    kit.plain_box("Window sill", ((x0 + x1) / 2, 1.555, z0 - 0.012), (x1 - x0 + 0.12, 0.11, 0.024), sill)
    world = scene.world.node_tree
    env = world.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(POLYHAVEN / "residential_garden/residential_garden_4k.hdr"))
    mapping, coord = world.nodes.new("ShaderNodeMapping"), world.nodes.new("ShaderNodeTexCoord")
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(110.0))
    world.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    world.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    background = world.nodes["Background"]
    world.links.new(env.outputs["Color"], background.inputs["Color"])
    background.inputs["Strength"].default_value = 1.0
    kit.sun("Afternoon sun through the side window", SUN, 3.5, angle_deg=0.8, color=(1.0, 0.94, 0.85))


def overlay(scene, args, ball_obj):
    import bpy
    if LOOK == "base":
        return
    O, M = bpy.data.objects, bpy.data.materials
    for name in ("Window key", "Room fill", "Ceiling bounce"):
        bpy.data.objects.remove(O[name])        # the base scene's studio disks: daylight now comes only through the window
    open_window(scene)
    room_shell()
    linen = sheer_linen()
    for obj in [o for o in O if "linen curtain fold" in o.name]:
        bpy.data.objects.remove(obj)
    linen_curtain("Left sheer linen curtain", -2.10, -1.70, linen)
    linen_curtain("Right sheer linen curtain", -0.66, -0.30, linen)
    O["Folded linen throw"].data.materials[0] = linen
    O["Grounded woven exercise-prop basket"].hide_render = True

    kit.add_wall_mottling(M["Sage limewash plaster"], amount=0.07)
    kit.add_surface_wear(M["Poly Haven rectangular parquet 2K (CC0)"], smudge=0.10, grime=0.08, scratch=0.07, scale=0.6)
    kit.add_surface_wear(M["Warm white paint"], smudge=0.06, grime=0.10, scratch=0.05, scale=0.3)

    walnut = image_material("Oiled walnut veneer (Poly Haven oak_veneer_01, darkened)", "oak_veneer_01",
                            POLYHAVEN / "oak_veneer_01", 1.2, tint=(0.24, 0.14, 0.085), normal=0.5)
    kit.add_surface_wear(walnut, smudge=0.07, grime=0.05, scratch=0.05, scale=0.5)
    for obj in O:
        if obj.type == "MESH" and obj.data.materials and obj.data.materials[0].name in (
                "Smoked walnut cabinetry", "Book-matched walnut sliding fronts"):
            obj.data.materials[0] = walnut
    audit = [append_prop("wicker_basket_01", (-1.32, 1.20, 0.0), 0.4),
             append_prop("potted_plant_04", (-0.92, 1.22, 0.0), 1.2)]

    scene.view_settings.look = "AgX - Base Contrast"
    scene.view_settings.exposure = EXPOSURE
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.cycles.max_bounces, scene.cycles.diffuse_bounces, scene.cycles.glossy_bounces = 10, 6, 4
    scene.cycles.transmission_bounces = 8
    scene.cycles.sample_clamp_indirect = 8.0
    scene.cycles.caustics_reflective = scene.cycles.caustics_refractive = False
    scene.camera.data.dof.aperture_fstop = 8.0
    kit.lens_finish(scene)
    kit.write_json(args.out.with_name(args.out.name + "_realism.json"), {
        "revision": "realism_overlay", "worker": kit.host_record(), "dressing_audit": audit,
        "cache_sha256": kit.sha256(args.cache)})


if __name__ == "__main__":
    import render_source_review as review
    review.OVERLAY = overlay
    review.main()
