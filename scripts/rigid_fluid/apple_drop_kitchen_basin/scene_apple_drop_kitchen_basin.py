"""Kitchen-basin environment of the apple drop: the BlenderKit kitchen with the basin, apple,
cutting board and peppers placed as in the Mantaflow scene (build_scene.py), the hero camera and,
optionally, that scene's two added area lights. The kitchen towel that hung over the sink edge is left
out. Functions are copied from build_scene.py unchanged; the peppers now stand on the board with a skin
of their own (configure_pepper).
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import REPO

ROOT = REPO
ASSETS = {
    "kitchen": ROOT / "assets/blenderkit/modern_living_kitchen/modern_living_kitchen.blend",
    "basin": ROOT / "assets/blenderkit/round_counter_basin/round_counter_basin.blend",
    "apple": ROOT / "assets/blenderkit/red_apples/red_apples.blend",
    "board": ROOT / "assets/blenderkit/cutting_board/cutting_board.blend",
    "pepper": ROOT / "assets/blenderkit/bell_pepper/bell_pepper.blend",
}
COUNTER_Z = 2.1466
BASIN_CENTER = Vector((-1.80, 1.92, COUNTER_Z))
BASIN_OUTER_RADIUS = 0.215
APPLE_RADIUS = 0.040
# Bell pepper skins, linear colour in the folds and on the lobes.
PEPPER_SKINS = {"green": ((0.003, 0.035, 0.002), (0.018, 0.160, 0.006)),
                "yellow": ((0.42, 0.13, 0.002), (0.86, 0.42, 0.005))}
PEPPER_STEM = (0.084, 0.089, 0.104)  # asset-local heights: shoulders give way to the stem; its cut end
BOARD_SHIFT = (-0.06, -0.03)     # m; the cutting board clears the basin by about a centimetre
SODA_MAKER_SHIFT = (-0.12, 0.08)  # m; the soda maker clears the board by about a centimetre (BVH test)


def bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    pts = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector(tuple(min(p[i] for p in pts) for i in range(3))),
        Vector(tuple(max(p[i] for p in pts) for i in range(3))),
    )


def append_object(path: Path, object_name: str, name: str) -> bpy.types.Object:
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        if object_name not in source.objects:
            raise RuntimeError(f"{object_name!r} missing from {path}")
        target.objects = [object_name]
    obj = target.objects[0]
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.name = name
    return obj


def normalize_and_place(
    obj: bpy.types.Object,
    target_max_dimension: float,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    anchor: str = "bottom",
) -> dict:
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    lo, hi = bounds(obj)
    source_size = hi - lo
    scale = target_max_dimension / max(source_size)
    obj.scale = (scale,) * 3
    obj.rotation_euler = rotation
    bpy.context.view_layer.update()
    lo, hi = bounds(obj)
    center_xy = Vector(((lo.x + hi.x) * 0.5, (lo.y + hi.y) * 0.5, 0.0))
    if anchor == "bottom":
        offset = Vector((location[0], location[1], location[2])) - Vector(
            (center_xy.x, center_xy.y, lo.z)
        )
    else:
        center = (lo + hi) * 0.5
        offset = Vector(location) - center
    obj.location += offset
    bpy.context.view_layer.update()
    final_lo, final_hi = bounds(obj)
    return {
        "source_size_m": list(source_size),
        "uniform_scale": scale,
        "final_min_m": list(final_lo),
        "final_max_m": list(final_hi),
        "final_size_m": list(final_hi - final_lo),
    }


def rest_on(obj: bpy.types.Object, z: float) -> None:
    """Lower or raise obj so its lowest point is at z: a tilted object's box corners reach below its mesh."""
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    lowest = min((obj.matrix_world @ v.co).z for v in evaluated.to_mesh().vertices)
    evaluated.to_mesh_clear()
    obj.location.z += z - lowest
    bpy.context.view_layer.update()


def make_principled(name: str, base, roughness: float, metallic: float = 0.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = (*base, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return material


def configure_apple_material(obj: bpy.types.Object) -> None:
    skin = obj.data.materials[0] if obj.data.materials else None
    if skin is None:
        skin = bpy.data.materials.new("PCVE Apple Skin")
        obj.data.materials.append(skin)
    skin.name = "PCVE Apple Skin Red Speckled"
    skin.use_nodes = True
    nodes = skin.node_tree.nodes
    links = skin.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    noise.inputs["Scale"].default_value = 82.0
    noise.inputs["Detail"].default_value = 4.2
    noise.inputs["Roughness"].default_value = 0.72
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.003, 0.00015, 0.00008, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.20, 0.0035, 0.0015, 1.0)
    fleck = ramp.color_ramp.elements.new(0.55)
    fleck.color = (0.52, 0.045, 0.008, 1.0)
    shader.inputs["Roughness"].default_value = 0.37
    shader.inputs["Specular IOR Level"].default_value = 0.32
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    if len(obj.data.materials) > 1 and obj.data.materials[1]:
        stem = obj.data.materials[1]
        stem.use_nodes = True
        stem_shader = next(
            (n for n in stem.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None
        )
        if stem_shader:
            stem_shader.inputs["Base Color"].default_value = (0.055, 0.022, 0.008, 1.0)
            stem_shader.inputs["Roughness"].default_value = 0.62


def configure_pepper(obj: bpy.types.Object, name: str, folds, lobes) -> None:
    """A bell pepper: the asset is 500 flat-shaded vertices with no material, and one flat colour on it
    read as a faceted plastic toy. Smooth it, and give it a glossy waxy skin, deeper in colour in its
    folds, and a green stem with a dry, browner cut end. The stem starts at PEPPER_STEM local height."""
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    smooth = obj.modifiers.new("Smooth", "SUBSURF")
    smooth.levels = smooth.render_levels = 2
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    coords = nodes.new("ShaderNodeTexCoord")
    height = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coords.outputs["Object"], height.inputs["Vector"])

    def ramp(value, low, high, start=0.0, end=1.0):
        node = nodes.new("ShaderNodeMapRange")
        node.inputs["From Min"].default_value, node.inputs["From Max"].default_value = low, high
        node.inputs["To Min"].default_value, node.inputs["To Max"].default_value = start, end
        links.new(value, node.inputs["Value"])
        return node.outputs["Result"]

    stem = ramp(height.outputs["Z"], *PEPPER_STEM[:2])
    cut = ramp(height.outputs["Z"], *PEPPER_STEM[1:])
    # Skin colour: darker where the lobes fold in (local occlusion) and mottled.
    occlusion = nodes.new("ShaderNodeAmbientOcclusion")
    occlusion.only_local = True
    occlusion.inputs["Distance"].default_value = 0.02
    mottle = nodes.new("ShaderNodeTexNoise")
    mottle.inputs["Scale"].default_value = 18.0
    mottle.inputs["Detail"].default_value = 3.0
    links.new(coords.outputs["Object"], mottle.inputs["Vector"])
    shade = nodes.new("ShaderNodeMath")
    shade.operation = "MULTIPLY"
    links.new(occlusion.outputs["AO"], shade.inputs[0])
    links.new(ramp(mottle.outputs["Fac"], 0.3, 0.7, 0.88, 1.0), shade.inputs[1])
    skin = nodes.new("ShaderNodeValToRGB")
    skin.color_ramp.elements[0].position, skin.color_ramp.elements[0].color = 0.45, (*folds, 1.0)
    skin.color_ramp.elements[1].position, skin.color_ramp.elements[1].color = 0.95, (*lobes, 1.0)
    links.new(shade.outputs["Value"], skin.inputs["Fac"])
    stalk = nodes.new("ShaderNodeMixRGB")
    stalk.inputs["Color1"].default_value = (0.030, 0.075, 0.012, 1.0)
    stalk.inputs["Color2"].default_value = (0.085, 0.070, 0.030, 1.0)
    links.new(cut, stalk.inputs["Fac"])
    colour = nodes.new("ShaderNodeMixRGB")
    links.new(stem, colour.inputs["Fac"])
    links.new(skin.outputs["Color"], colour.inputs["Color1"])
    links.new(stalk.outputs["Color"], colour.inputs["Color2"])
    links.new(colour.outputs["Color"], shader.inputs["Base Color"])
    # The skin's gloss is all its wax (a sharp coat): a broad sheen on the flesh under it washed the dark
    # green out to grey wherever it faced the white basin. The stem is dry and matt.
    links.new(ramp(stem, 0.0, 1.0, 0.3, 0.6), shader.inputs["Roughness"])
    links.new(ramp(stem, 0.0, 1.0, 0.0, 0.4), shader.inputs["Specular IOR Level"])
    links.new(ramp(stem, 0.0, 1.0, 0.5, 0.0), shader.inputs["Coat Weight"])
    shader.inputs["Coat Roughness"].default_value = 0.05
    # Fine unevenness of the skin, coarser fibres on the stem.
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 260.0
    grain.inputs["Detail"].default_value = 2.0
    links.new(coords.outputs["Object"], grain.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.0004
    links.new(ramp(stem, 0.0, 1.0, 0.12, 0.5), bump.inputs["Strength"])
    links.new(grain.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    obj.data.materials.clear()
    obj.data.materials.append(material)


def aim_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()



def build_environment(apple_center, added_lights=True):
    """Open the kitchen and place the props; returns (apple visual, its offset from the sphere centre, camera)."""
    bpy.ops.wm.open_mainfile(filepath=str(ASSETS["kitchen"]))
    basin = append_object(ASSETS["basin"], "Basin", "PCVE_BlenderKit_Basin")
    normalize_and_place(basin, 2 * BASIN_OUTER_RADIUS, tuple(BASIN_CENTER), anchor="bottom")
    basin.data.materials.clear()
    basin.data.materials.append(make_principled("PCVE Warm Gray Basin Plastic", (0.64, 0.61, 0.55), 0.31))
    apple_center = Vector(apple_center)
    apple_visual = append_object(ASSETS["apple"], "RedXx", "PCVE_BlenderKit_RedApple")
    normalize_and_place(apple_visual, 2 * APPLE_RADIUS, tuple(apple_center), anchor="center")
    configure_apple_material(apple_visual)
    apple_offset = apple_visual.location.copy() - apple_center
    # The board lies on the counter (the Mantaflow scene raised it 6 mm), BOARD_SHIFT left of where that
    # scene put it, which ran it 5 cm into the basin's wall.
    bx, by = -2.18 + BOARD_SHIFT[0], 1.92 + BOARD_SHIFT[1]
    board = append_object(ASSETS["board"], "Wooden Cutting Board", "PCVE_BlenderKit_CuttingBoard")
    normalize_and_place(board, 0.34, (bx, by, COUNTER_Z), (0.0, 0.0, math.radians(-18)))
    # The kitchen's soda maker stood with its base and column through the board; it moves back off it.
    soda_maker = bpy.data.objects["Carbonation Machine in Olive color"]
    soda_maker.location.x += SODA_MAKER_SHIFT[0]
    soda_maker.location.y += SODA_MAKER_SHIFT[1]
    # The peppers stand on the board (its top is 3.4 cm up; placed at the counter they sank 2.6 cm into
    # it) and are turned apart, so the two copies of one asset do not show the same face. The asset keys
    # its rotation as a quaternion, so the Mantaflow scene's Euler turns never applied.
    board_top = bounds(board)[1].z
    for key, size, xy, turn, skin in (("Green", 0.095, (bx - .01, by - .04), (0.0, 0.0, 18.0), PEPPER_SKINS["green"]),
                                      ("Yellow", 0.087, (bx + .10, by - .09), (4.0, 0.0, -115.0), PEPPER_SKINS["yellow"])):
        pepper = append_object(ASSETS["pepper"], "Bell Pepper", f"PCVE_BlenderKit_{key}Pepper")
        pepper.rotation_mode = "XYZ"
        configure_pepper(pepper, f"PCVE {key} Pepper", *skin)
        normalize_and_place(pepper, size, (*xy, board_top), tuple(math.radians(a) for a in turn))
        rest_on(pepper, board_top)
    bpy.ops.object.camera_add(location=(-0.58, 0.43, 3.28))
    camera = bpy.context.object
    camera.name = "PCVE_HeroCamera"
    camera.data.lens = 50.0
    camera.data.sensor_width = 36.0
    camera.data.dof.use_dof = False
    aim_camera(camera, Vector((BASIN_CENTER.x, BASIN_CENTER.y, 2.2676 + 0.03)))
    bpy.context.scene.camera = camera
    if added_lights:
        bpy.ops.object.light_add(type="AREA", location=(-0.95, 1.18, 3.75))
        daylight = bpy.context.object
        daylight.name = "PCVE Soft Window Daylight"
        daylight.data.energy = 280.0
        daylight.data.shape = "RECTANGLE"
        daylight.data.size = 2.2
        daylight.data.size_y = 1.5
        daylight.data.color = (0.76, 0.88, 1.0)
        aim_camera(daylight, Vector((BASIN_CENTER.x, BASIN_CENTER.y, 2.2676)))
        bpy.ops.object.light_add(type="AREA", location=(-2.85, 1.25, 2.85))
        warm = bpy.context.object
        warm.name = "PCVE Warm Interior Fill"
        warm.data.energy = 90.0
        warm.data.shape = "DISK"
        warm.data.size = 1.1
        warm.data.color = (1.0, 0.60, 0.34)
        aim_camera(warm, Vector((BASIN_CENTER.x, BASIN_CENTER.y, 2.2676)))
    return apple_visual, apple_offset, camera
