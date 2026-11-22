"""Materials for the stockpot, its lid and the ADDed bowl.

The pot GLB is the source of the lid's collision hull, so its geometry is kept
exactly as imported: only shading changes here, never a vertex. The asset's
own baked lambert textures read as grey plastic under daylight; real cookware
is 18/10 stainless (a polished body, a lid with a fine circular brushing and a
black phenolic knob) and the bowl is glazed stoneware.
"""
from __future__ import annotations

import math

# Lid parts above this height (lid frame, metres, +Z through the dome) and
# inside this radius are the knob; everything else is steel.
KNOB_MIN_Z = 0.0125
KNOB_MAX_R = 0.034


def _stainless(name, roughness, brushed, smudge=.05):
    """18/10 stainless: neutral, slightly warm metal; optional circular
    brushing (anisotropy around the lid's own axis) and faint handling marks."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (.60, .585, .56, 1)
    bsdf.inputs['Metallic'].default_value = 1.
    coord = nodes.new('ShaderNodeTexCoord')
    marks = nodes.new('ShaderNodeTexNoise')
    marks.inputs['Scale'].default_value = 14.
    marks.inputs['Detail'].default_value = 6.
    marks.inputs['Roughness'].default_value = .65
    links.new(coord.outputs['Object'], marks.inputs['Vector'])
    remap = nodes.new('ShaderNodeMapRange')
    remap.inputs['From Min'].default_value = .35
    remap.inputs['From Max'].default_value = .75
    remap.inputs['To Min'].default_value = roughness
    remap.inputs['To Max'].default_value = roughness + smudge
    links.new(marks.outputs['Fac'], remap.inputs['Value'])
    links.new(remap.outputs['Result'], bsdf.inputs['Roughness'])
    if brushed:
        bsdf.inputs['Anisotropic'].default_value = .75
        tangent = nodes.new('ShaderNodeTangent')
        tangent.direction_type = 'RADIAL'
        tangent.axis = 'Z'
        links.new(tangent.outputs['Tangent'], bsdf.inputs['Tangent'])
    return mat


def _phenolic():
    import bpy
    mat = bpy.data.materials.new('Black phenolic knob')
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (.010, .010, .011, 1)
    bsdf.inputs['Roughness'].default_value = .36
    bsdf.inputs['Coat Weight'].default_value = .4
    bsdf.inputs['Coat Roughness'].default_value = .18
    return mat


def _smooth(obj, angle_deg=35.):
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(angle_deg))


def dress_pot_and_lid(pot, lid):
    """Polished body, brushed lid with a black knob; no geometry change."""
    body = _stainless('Polished stainless pot body', .07, False, .04)
    pot.data.materials.clear()
    pot.data.materials.append(body)
    for poly in pot.data.polygons:
        poly.material_index = 0
    _smooth(pot)

    steel = _stainless('Brushed stainless lid', .16, True, .06)
    knob = _phenolic()
    lid.data.materials.clear()
    lid.data.materials.append(steel)
    lid.data.materials.append(knob)
    knob_faces = 0
    for poly in lid.data.polygons:
        c = poly.center
        is_knob = c.z > KNOB_MIN_Z and math.hypot(c.x, c.y) < KNOB_MAX_R
        poly.material_index = 1 if is_knob else 0
        knob_faces += is_knob
    _smooth(lid)
    return dict(pot_material=body.name, lid_material=steel.name, knob_material=knob.name, knob_faces=knob_faces)


def glaze_bowl(bowl, foot_top_z):
    """Glazed stoneware bowl: a soft oatmeal glaze, with the unglazed foot ring
    (object z below ``foot_top_z``) left as bare buff clay."""
    import bpy
    mat = bpy.data.materials.new('Oatmeal glazed stoneware')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    coord = nodes.new('ShaderNodeTexCoord')
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Object'], xyz.inputs['Vector'])
    foot = nodes.new('ShaderNodeMath')
    foot.operation = 'LESS_THAN'
    links.new(xyz.outputs['Z'], foot.inputs[0])
    foot.inputs[1].default_value = foot_top_z
    speckle = nodes.new('ShaderNodeTexVoronoi')
    speckle.inputs['Scale'].default_value = 260.
    links.new(coord.outputs['Object'], speckle.inputs['Vector'])
    dots = nodes.new('ShaderNodeValToRGB')
    dots.color_ramp.elements[0].position = .0
    dots.color_ramp.elements[0].color = (.30, .25, .20, 1)
    dots.color_ramp.elements[1].position = .06
    dots.color_ramp.elements[1].color = (.72, .68, .58, 1)
    links.new(speckle.outputs['Distance'], dots.inputs['Fac'])
    colour = nodes.new('ShaderNodeMix')
    colour.data_type = 'RGBA'
    links.new(foot.outputs[0], colour.inputs['Factor'])
    links.new(dots.outputs['Color'], colour.inputs['A'])
    colour.inputs['B'].default_value = (.52, .42, .31, 1)
    links.new(colour.outputs['Result'], bsdf.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMix')
    rough.data_type = 'FLOAT'
    links.new(foot.outputs[0], rough.inputs['Factor'])
    rough.inputs['A'].default_value = .22
    rough.inputs['B'].default_value = .85
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    coat = nodes.new('ShaderNodeMath')
    coat.operation = 'SUBTRACT'
    coat.inputs[0].default_value = 1.
    links.new(foot.outputs[0], coat.inputs[1])
    links.new(coat.outputs[0], bsdf.inputs['Coat Weight'])
    bsdf.inputs['Coat Roughness'].default_value = .04
    bowl.data.materials.clear()
    bowl.data.materials.append(mat)
    return mat
