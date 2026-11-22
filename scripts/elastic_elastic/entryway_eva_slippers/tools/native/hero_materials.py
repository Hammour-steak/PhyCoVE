"""Rest-space EVA skin, restrained wear, soft grip and moulded edge finish."""
import bpy
import numpy as np

import render as base
from common import INPUTS


def smooth_range(nodes, links, source, low, high, out_low=0.0, out_high=1.0):
    node = nodes.new("ShaderNodeMapRange")
    node.interpolation_type = "SMOOTHSTEP"
    for key, value in (("From Min", low), ("From Max", high), ("To Min", out_low), ("To Max", out_high)):
        node.inputs[key].default_value = value
    links.new(source, node.inputs["Value"])
    return node.outputs[0]


def material(name, upper):
    mat = base.material(name, (0.115, 0.139, 0.127), 0.5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["IOR"].default_value = 1.47
    shader.inputs["Coat Weight"].default_value = 0.0
    shader.inputs["Subsurface Weight"].default_value = 0.012
    shader.inputs["Subsurface Scale"].default_value = 0.0007
    coordinate = nodes.new("ShaderNodeAttribute")
    coordinate.attribute_name = "foam_local"
    split = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coordinate.outputs["Vector"], split.inputs[0])

    pigment = nodes.new("ShaderNodeTexNoise")
    pigment.inputs["Scale"].default_value = 85
    pigment.inputs["Detail"].default_value = 3
    links.new(coordinate.outputs["Vector"], pigment.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.111, 0.133, 0.121, 1)
    ramp.color_ramp.elements[1].color = (0.124, 0.147, 0.134, 1)
    links.new(pigment.outputs["Fac"], ramp.inputs[0])
    links.new(ramp.outputs[0], shader.inputs["Base Color"])

    pores = nodes.new("ShaderNodeTexVoronoi")
    pores.inputs["Scale"].default_value = 1450
    pores.inputs["Randomness"].default_value = 0.92
    links.new(coordinate.outputs["Vector"], pores.inputs["Vector"])
    height = smooth_range(nodes, links, pores.outputs["Distance"], 0.11, 0.37)
    grain = nodes.new("ShaderNodeBump")
    grain.inputs["Strength"].default_value = 0.30
    grain.inputs["Distance"].default_value = 0.000045
    links.new(height, grain.inputs["Height"])
    normal = grain.outputs[0]

    roughness = smooth_range(nodes, links, pigment.outputs["Fac"], 0, 1,
                            0.40 if upper else 0.45, 0.55 if upper else 0.59)
    if upper:
        # Recessed rounded cells stop short of the rounded front/rear cuff.
        pebbles = nodes.new("ShaderNodeTexVoronoi")
        pebbles.inputs["Scale"].default_value = 690
        pebbles.inputs["Randomness"].default_value = 0.78
        links.new(coordinate.outputs["Vector"], pebbles.inputs["Vector"])
        cells = smooth_range(nodes, links, pebbles.outputs["Distance"], 0.24, 0.54)
        interior = nodes.new("ShaderNodeAttribute")
        interior.attribute_name = "vamp_interior"
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Distance"].default_value = 0.000105
        links.new(interior.outputs["Fac"], bump.inputs["Strength"])
        links.new(cells, bump.inputs["Height"])
        links.new(normal, bump.inputs["Normal"])
        normal = bump.outputs[0]
    else:
        footbed = nodes.new("ShaderNodeAttribute")
        footbed.attribute_name = "foam_footbed"
        wave = nodes.new("ShaderNodeTexWave")
        wave.bands_direction = "Y"
        wave.inputs["Scale"].default_value = 94
        wave.inputs["Distortion"].default_value = 0.15
        links.new(coordinate.outputs["Vector"], wave.inputs["Vector"])
        grip = smooth_range(nodes, links, wave.outputs["Fac"], 0.47, 0.82)
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Distance"].default_value = 0.00018
        links.new(footbed.outputs["Fac"], bump.inputs["Strength"])
        links.new(grip, bump.inputs["Height"])
        links.new(normal, bump.inputs["Normal"])
        normal = bump.outputs[0]

        # A fine parting line is an optical normal detail, with no render displacement.
        subtract = nodes.new("ShaderNodeMath")
        subtract.operation = "SUBTRACT"
        subtract.inputs[1].default_value = 0.0105
        links.new(split.outputs["Z"], subtract.inputs[0])
        absolute = nodes.new("ShaderNodeMath")
        absolute.operation = "ABSOLUTE"
        links.new(subtract.outputs[0], absolute.inputs[0])
        seam = smooth_range(nodes, links, absolute.outputs[0], 0.00002, 0.00023, 1, 0)
        mould = nodes.new("ShaderNodeBump")
        mould.inputs["Strength"].default_value = 0.30
        mould.inputs["Distance"].default_value = 0.00010
        links.new(seam, mould.inputs["Height"])
        links.new(normal, mould.inputs["Normal"])
        normal = mould.outputs[0]

        mark = nodes.new("ShaderNodeTexImage")
        mark.image = bpy.data.images.load(str(INPUTS / "assets/size_mark/size_42.png"), check_existing=True)
        mark.image.colorspace_settings.name = "Non-Color"
        mark.extension = "CLIP"
        mapping = nodes.new("ShaderNodeVectorMath")
        mapping.operation = "MULTIPLY_ADD"
        mapping.inputs[1].default_value = (1 / 0.014, 1 / 0.007, 0)
        mapping.inputs[2].default_value = (0.5, 0.5 - 0.111 / 0.007, 0)
        links.new(coordinate.outputs["Vector"], mapping.inputs[0])
        links.new(mapping.outputs[0], mark.inputs["Vector"])
        engraving = nodes.new("ShaderNodeBump")
        engraving.invert = True
        engraving.inputs["Strength"].default_value = 0.4
        engraving.inputs["Distance"].default_value = 0.00016
        links.new(mark.outputs["Color"], engraving.inputs["Height"])
        links.new(normal, engraving.inputs["Normal"])
        normal = engraving.outputs[0]

        wear = nodes.new("ShaderNodeAttribute")
        wear.attribute_name = "footbed_polish"
        amount = nodes.new("ShaderNodeMath")
        amount.operation = "MULTIPLY"
        amount.inputs[1].default_value = 0.055
        links.new(wear.outputs["Fac"], amount.inputs[0])
        polish = nodes.new("ShaderNodeMath")
        polish.operation = "SUBTRACT"
        links.new(roughness, polish.inputs[0])
        links.new(amount.outputs[0], polish.inputs[1])
        roughness = polish.outputs[0]
    links.new(roughness, shader.inputs["Roughness"])
    links.new(normal, shader.inputs["Normal"])
    mat["pcve_detail_scope"] = "Shader normals only, maximum distance 0.18 mm. All broad shape and edge rounding are native collision geometry."
    return mat


def apply_hero_finish(scene, cache, geometry):
    sole = material("Contoured EVA footbed and moulded sole", False)
    vamp = material("Fine pebbled EVA with smooth cuff borders", True)
    vertices, faces = geometry["vertices"], geometry["faces"]
    labels = geometry["material_ids"]
    triangle_normals = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]],
                                vertices[faces[:, 2]] - vertices[faces[:, 0]])
    normals = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(normals, faces[:, corner], triangle_normals)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-15)
    footbed = np.clip((normals[:, 2] - 0.55) / 0.35, 0, 1)
    footbed *= np.clip((vertices[:, 2] - 0.017) / 0.004, 0, 1) * 0.80
    unit = triangle_normals / np.maximum(np.linalg.norm(triangle_normals, axis=1, keepdims=True), 1e-15)
    edge_faces = (labels == 1) & (np.abs(unit[:, 1]) > 0.55)
    edge_vertices = np.unique(faces[edge_faces])
    distance = np.zeros(len(vertices))
    if len(edge_vertices):
        edge = vertices[edge_vertices]
        for start in range(0, len(vertices), 512):
            delta = vertices[start:start + 512, None] - edge[None]
            distance[start:start + 512] = np.sqrt(np.sum(delta * delta, axis=2).min(1))
    interior = np.clip((distance - 0.0015) / 0.003, 0, 1) * 0.55
    x, y = vertices[:, 0], vertices[:, 1]
    polish = np.exp(-((x / 0.032) ** 2 + ((y - 0.082) / 0.036) ** 2))
    polish += 0.7 * np.exp(-((x / 0.044) ** 2 + ((y + 0.088) / 0.032) ** 2))
    polish *= footbed
    for actor in scene.objects:
        if "part_id" not in actor:
            continue
        part = actor["part_id"]
        original = np.flatnonzero(cache["part_ids"] == part)
        surface = cache["faces"][np.all(cache["part_ids"][cache["faces"]] == part, axis=1)]
        local = np.searchsorted(original, np.unique(surface))
        attribute = actor.data.attributes.new("foam_local", "FLOAT_VECTOR", "POINT")
        attribute.data.foreach_set("vector", vertices[local].astype(np.float32).ravel())
        for name, values in (("foam_footbed", footbed), ("vamp_interior", interior),
                             ("footbed_polish", polish)):
            attribute = actor.data.attributes.new(name, "FLOAT", "POINT")
            attribute.data.foreach_set("value", values[local].astype(np.float32))
        actor.data.materials[0] = sole
        actor.data.materials[1] = vamp
        actor.data.polygons.foreach_set("material_index", labels.astype(np.int32))
