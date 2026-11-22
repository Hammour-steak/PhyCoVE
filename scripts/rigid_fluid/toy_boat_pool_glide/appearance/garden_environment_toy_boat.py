"""Continuous, metre-scale 3D backyard for the toy boat. Appearance only; no colliders."""
import random

import bpy
from mathutils import Matrix, Vector


def cube(name, center, size, material, bevel=0.003):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new("Soft real edges", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj


def cedar():
    mat = bpy.data.materials.new("Garden_weathered_cedar")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.76
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeVectorMath")
    mapping.operation = "MULTIPLY"
    mapping.inputs[1].default_value = (85, 85, 1.2)
    links.new(coord.outputs["Object"], mapping.inputs[0])
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 1.0
    grain.inputs["Detail"].default_value = 3.0
    links.new(mapping.outputs["Vector"], grain.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.12
    ramp.color_ramp.elements[0].color = (0.235, 0.175, 0.115, 1)
    ramp.color_ramp.elements[1].position = 0.88
    ramp.color_ramp.elements[1].color = (0.32, 0.255, 0.18, 1)
    links.new(grain.outputs["Fac"], ramp.inputs["Fac"])
    info = nodes.new("ShaderNodeObjectInfo")
    variation = nodes.new("ShaderNodeMapRange")
    variation.inputs["To Min"].default_value = 0.72
    variation.inputs["To Max"].default_value = 1.08
    links.new(info.outputs["Random"], variation.inputs["Value"])
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    links.new(ramp.outputs["Color"], mix.inputs[1])
    links.new(variation.outputs["Result"], mix.inputs[2])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.00035
    links.new(grain.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def plant(renderer, stem, position, height, angle):
    path = renderer.ASSETS / f"polyhaven_models/{stem}/{stem}_1k.gltf"
    root, objects = renderer.import_gltf(path, "Garden_" + stem)
    bpy.context.view_layer.update()
    points = [o.matrix_world @ Vector(v) for o in objects if o.type == "MESH" for v in o.bound_box]
    lo = Vector([min(v[i] for v in points) for i in range(3)])
    hi = Vector([max(v[i] for v in points) for i in range(3)])
    scale = height / (hi.z - lo.z)
    root.matrix_world = (Matrix.Translation(position) @ Matrix.Rotation(angle, 4, "Z")
                         @ Matrix.Diagonal((scale, scale, scale, 1))
                         @ Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
    bpy.context.view_layer.update()
    world_points = [o.matrix_world @ Vector(v) for o in objects if o.type == "MESH" for v in o.bound_box]
    return {"asset": str(path.relative_to(renderer.ROOT)), "height_m": height,
            "world_min_z_m": min(v.z for v in world_points), "position_m": list(position)}


def build(scene, renderer):
    # A maintained lawn, rather than tall clumps and conspicuous weeds around a small pool.
    renderer.GRASS_RADIUS = 6.5
    renderer.LAWN_STRANDS = 180_000
    renderer.BLADE_LENGTH = 0.032
    renderer.HAIR_CHILDREN = 24
    renderer.GRASS_HEIGHT.update({"grass_medium_01_1k": 0.055, "grass_bermuda_01_1k": 0.045, "dandelion_01_1k": 0.075})
    renderer.GRASS_SHARE.update({"grass_medium_01_1k": 0.0, "grass_bermuda_01_1k": 0.0, "dandelion_01_1k": 0.0})
    record = renderer.setup_lawn(scene)
    catcher = bpy.data.objects.get("PCVE_FarGround")
    bpy.data.objects.remove(catcher, do_unlink=True)
    ground = bpy.data.objects["PCVE_Lawn"]
    for vertex in ground.data.vertices:
        vertex.co.x *= 18 / (renderer.GRASS_RADIUS + 0.2)
        vertex.co.y *= 18 / (renderer.GRASS_RADIUS + 0.2)
    # The entire visible middle distance is real geometry. The HDRI supplies daylight only.
    wood = cedar()
    rng = random.Random(2601026)
    for i in range(121):
        x = -8.5 + i * 0.144
        top = 1.68 + rng.uniform(-0.008, 0.008)
        cube(f"Garden_fence_board_{i:03d}", (x, 4.75, top / 2), (0.139, 0.026, top), wood)
    for x in range(-8, 10, 2):
        cube(f"Garden_fence_post_{x}", (x, 4.72, 0.86), (0.085, 0.085, 1.72), wood)
    cube("Garden_fence_cap", (0, 4.74, 1.71), (17.4, 0.11, 0.045), wood)
    for z in (0.24, 1.25):
        cube(f"Garden_fence_rail_{z}", (0, 4.785, z), (17.4, 0.05, 0.075), wood)
    # A handful of existing CC0 plants establish a domestic garden without a photographic backdrop.
    plants = []
    for stem, pos, height, angle in [
        ("potted_plant_02", (-2.65, 4.20, 0.0), 1.10, 0.8),
        ("potted_plant_01", (-1.25, 4.30, 0.0), 0.78, 2.1),
        ("potted_plant_02", (2.50, 4.28, 0.0), 1.18, 2.7),
        ("potted_plant_01", (3.4, 4.24, 0.0), 0.82, 0.0),
    ]:
        plants.append(plant(renderer, stem, pos, height, angle))
    record.update({"version": "continuous_backyard", "ground_radius_m": 18,
                   "fence_y_m": 4.75, "fence_height_m": 1.73, "plants": plants,
                   "light": "unchanged sunny_rose_garden HDRI; background occluded by 3D fence",
                   "physics": "Existing particles, boat poses, water meshes, camera unchanged"})
    return record
