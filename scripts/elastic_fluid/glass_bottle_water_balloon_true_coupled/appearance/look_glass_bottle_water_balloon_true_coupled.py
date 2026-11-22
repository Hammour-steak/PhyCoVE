"""Unmodified accepted kitchen geometry/material helpers; Blender only."""
from __future__ import annotations
import bpy
import numpy as np


def set_input(node, name, value) -> None:
    socket = node.inputs.get(name)
    if socket is not None:
        socket.default_value = value


def principled(name, color, roughness=0.4, metallic=0.0, transmission=0.0,
               ior=1.45, alpha=1.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    set_input(shader, "Base Color", color)
    set_input(shader, "Roughness", roughness)
    set_input(shader, "Metallic", metallic)
    set_input(shader, "Transmission Weight", transmission)
    set_input(shader, "IOR", ior)
    set_input(shader, "Alpha", alpha)
    if alpha < 1.0:
        material.surface_render_method = "DITHERED"
    return material


def glass_material(name, tint, alpha, roughness, ior):
    material = principled(name, tint, roughness, 0.0, 0.96, ior, alpha)
    shader = material.node_tree.nodes.get("Principled BSDF")
    set_input(shader, "Coat Weight", 0.18)
    set_input(shader, "Coat Roughness", 0.08)
    if alpha < 1.0:
        material.surface_render_method = "DITHERED"
    return material


def fresnel_glass_material(name, tint, roughness, ior):
    """Readable thin glass with physically motivated angle-dependent reflection.

    One constant glass mix at every viewing angle would keep the balloon
    visible but erase the grazing-angle reflections that make a clear vessel
    read as glass.  A bounded Fresnel response keeps that angle dependency
    while preserving visibility of the experiment through the curved shoulder.
    """
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    mix = nodes.new("ShaderNodeMixShader")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    glass = nodes.new("ShaderNodeBsdfGlass")
    fresnel = nodes.new("ShaderNodeFresnel")
    fresnel_scale = nodes.new("ShaderNodeMath")
    fresnel_scale.operation = "MULTIPLY"
    # Retain a restrained face-on reflection, then let the physically based
    # Fresnel term strengthen smoothly toward the silhouette.  This is enough
    # to reveal the cylindrical wall without turning it into a milky shell.
    fresnel_scale.inputs[1].default_value = 0.28
    fresnel_floor = nodes.new("ShaderNodeMath")
    fresnel_floor.operation = "ADD"
    fresnel_floor.inputs[1].default_value = 0.025
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    bump = nodes.new("ShaderNodeBump")

    output.location = (600, 0)
    mix.location = (390, 0)
    transparent.location = (120, 80)
    glass.location = (120, -90)
    fresnel.location = (120, 240)
    fresnel_scale.location = (300, 260)
    fresnel_floor.location = (470, 260)
    texcoord.location = (-620, -220)
    noise.location = (-420, -220)
    bump.location = (-160, -220)

    glass.inputs["Color"].default_value = tint
    glass.inputs["Roughness"].default_value = roughness
    glass.inputs["IOR"].default_value = ior
    fresnel.inputs["IOR"].default_value = ior
    noise.inputs["Scale"].default_value = 185.0
    noise.inputs["Detail"].default_value = 2.2
    noise.inputs["Roughness"].default_value = 0.56
    bump.inputs["Strength"].default_value = 0.018
    bump.inputs["Distance"].default_value = 0.00018
    transparent.inputs["Color"].default_value = (0.965, 0.985, 1.0, 1.0)

    material.node_tree.links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    material.node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    material.node_tree.links.new(bump.outputs["Normal"], glass.inputs["Normal"])
    material.node_tree.links.new(fresnel.outputs["Fac"], fresnel_scale.inputs[0])
    material.node_tree.links.new(fresnel_scale.outputs[0], fresnel_floor.inputs[0])
    material.node_tree.links.new(fresnel_floor.outputs[0], mix.inputs[0])
    material.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
    material.node_tree.links.new(glass.outputs[0], mix.inputs[2])
    material.node_tree.links.new(mix.outputs[0], output.inputs["Surface"])
    return material


def micro_surface_material(name, color, roughness, metallic=0.0,
                           noise_scale=120.0, bump_strength=0.05,
                           bump_distance=0.00035):
    """Principled material with restrained, real-scale surface variation."""
    material = principled(name, color, roughness, metallic)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    shader = nodes.get("Principled BSDF")
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    bump = nodes.new("ShaderNodeBump")
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.52
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = bump_distance
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return material


def mesh_object(name, vertices, faces, material, location=(0.0, 0.0, 0.0)):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(np.asarray(vertices).tolist(), [], np.asarray(faces).tolist())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.data.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return obj


def add_cylinder(name, radius, depth, location, material, vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def curve_tube(name, points, radius, material):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 16
    curve.bevel_depth = radius
    curve.bevel_resolution = 6
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, coordinate in zip(spline.bezier_points, points):
        point.co = coordinate
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj
