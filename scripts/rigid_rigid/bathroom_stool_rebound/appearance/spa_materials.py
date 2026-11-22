"""Surface materials for the dusk spa look: scanned stone and wood, metals, glass.

The GLB bathroom is modelled at twice real size (vanity top 1.81 m, shower
glass 4.07 m tall, the stool seat 1.37 m up), so every scanned texture is laid
at WORLD_SCALE times its documented size: the tiles and grain then read at
their real proportions next to the fittings. Texture coordinates are written
as a world-space box projection (``world_box_uv``) instead of trusting the
GLB's own UVs, which were authored for a different, much larger tile.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

WORLD_SCALE = 2.0
POLYHAVEN = _pcve_asset('polyhaven/bathroom_stool_rebound')
UV_NAME = 'world_box'

# Scanned sets (Poly Haven, CC0): stem -> documented tile edge in real metres.
SCANS = {
    'wall': ('floor_tiles_04', 4.0),       # large warm limestone slabs
    'floor': ('marble_01', 1.5),           # honed travertine tiles
    'walnut': ('walnut_veneer', 1.8),      # vanity joinery
    'teak': ('angli_veneer', 1.0),         # oiled bath-stool seat
}


def world_box_uv(bpy, obj, matrix=None):
    """Write a box-projected UV map in world metres (rest pose) onto obj's mesh.

    Up/down faces take (x, y); every other face takes (distance along its own
    horizontal direction, z), which also lays the 45-degree alcove chamfer
    straight instead of smearing it. Shared mesh data is written once.
    """
    from mathutils import Vector
    me = obj.data
    if UV_NAME in me.uv_layers:
        return me.uv_layers[UV_NAME]
    mw = matrix if matrix is not None else obj.matrix_world
    normal_matrix = mw.to_3x3().inverted().transposed()
    layer = me.uv_layers.new(name=UV_NAME)
    for poly in me.polygons:
        n = (normal_matrix @ poly.normal).normalized()
        if abs(n.z) > .7:
            u_axis, v_axis = Vector((1, 0, 0)), Vector((0, 1, 0))
        else:
            u_axis = Vector((-n.y, n.x, 0)).normalized()
            v_axis = Vector((0, 0, 1))
        for li in poly.loop_indices:
            p = mw @ me.vertices[me.loops[li].vertex_index].co
            layer.data[li].uv = (p.dot(u_axis), p.dot(v_axis))
    return layer


def _new(bpy, name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat, mat.node_tree.nodes, mat.node_tree.links, mat.node_tree.nodes['Principled BSDF']


def scanned(bpy, name, key, *, rough=(0.0, 1.0), hue=.5, sat=1.0, val=1.0, normal=1.0, rotate=False):
    """A Poly Haven colour/roughness/normal set on the world_box UVs at real size."""
    stem, size_m = SCANS[key]
    mat, nodes, links, bsdf = _new(bpy, name)
    uv = nodes.new('ShaderNodeUVMap'); uv.uv_map = UV_NAME
    mapping = nodes.new('ShaderNodeMapping')
    tile = size_m * WORLD_SCALE
    mapping.inputs['Scale'].default_value = (1 / tile, 1 / tile, 1)
    if rotate:
        mapping.inputs['Rotation'].default_value = (0, 0, 1.5707963)
    links.new(uv.outputs['UV'], mapping.inputs['Vector'])

    def image(kind, colour):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(POLYHAVEN / f'{stem}_{kind}_2k.jpg'), check_existing=True)
        if not colour:
            node.image.colorspace_settings.name = 'Non-Color'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node.outputs['Color']

    colour = image('diff', True)
    if (hue, sat, val) != (.5, 1.0, 1.0):
        grade = nodes.new('ShaderNodeHueSaturation')
        grade.inputs['Hue'].default_value, grade.inputs['Saturation'].default_value = hue, sat
        grade.inputs['Value'].default_value = val
        links.new(colour, grade.inputs['Color']); colour = grade.outputs['Color']
    links.new(colour, bsdf.inputs['Base Color'])
    rmap = nodes.new('ShaderNodeMapRange')
    rmap.inputs['To Min'].default_value, rmap.inputs['To Max'].default_value = rough
    links.new(image('rough', False), rmap.inputs['Value'])
    links.new(rmap.outputs['Result'], bsdf.inputs['Roughness'])
    nmap = nodes.new('ShaderNodeNormalMap'); nmap.uv_map = UV_NAME
    nmap.inputs['Strength'].default_value = normal
    links.new(image('nor_gl', False), nmap.inputs['Color'])
    links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def plain(bpy, name, colour, roughness, *, metallic=0.0, drift=0.0, subsurface=0.0, coat=0.0):
    """Uniform material with an optional slow tone/sheen drift in world space.

    A factory-moulded tub or a painted ceiling is one colour, but never one
    value: a few percent of drift over a metre is what stops it reading as CG.
    """
    mat, nodes, links, bsdf = _new(bpy, name)
    bsdf.inputs['Base Color'].default_value = (*colour, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    if subsurface:
        bsdf.inputs['Subsurface Weight'].default_value = subsurface
        bsdf.inputs['Subsurface Radius'].default_value = (.4, .3, .2)
        bsdf.inputs['Subsurface Scale'].default_value = .02
    if coat:
        bsdf.inputs['Coat Weight'].default_value = coat
        bsdf.inputs['Coat Roughness'].default_value = .08
    if drift:
        geo = nodes.new('ShaderNodeNewGeometry')
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = .6
        noise.inputs['Detail'].default_value = 4.0
        links.new(geo.outputs['Position'], noise.inputs['Vector'])
        ramp = nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = .3, .7
        ramp.color_ramp.elements[0].color = (*(c * (1 - drift) for c in colour), 1)
        ramp.color_ramp.elements[1].color = (*(min(1., c * (1 + drift * .6)) for c in colour), 1)
        links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
        sheen = nodes.new('ShaderNodeMapRange')
        sheen.inputs['To Min'].default_value = max(0., roughness - .05)
        sheen.inputs['To Max'].default_value = min(1., roughness + .05)
        links.new(noise.outputs['Fac'], sheen.inputs['Value'])
        links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    return mat


def brass(bpy, name='Satin brass', roughness=.3):
    return plain(bpy, name, (.80, .58, .30), roughness, metallic=1.0)


def thin_glass(bpy):
    """Thin float glass: 4 % Fresnel reflection over a see-through layer.

    Shaded transparent so camera rays through it stay camera rays (the dusk
    photograph outside is shown to the camera only). Back faces get the
    inverse IOR: Cycles' Fresnel node inverts the IOR on back faces, which
    otherwise totally reflects a ray leaving the pane past 41 degrees and turns
    a window seen at a glancing angle black.
    """
    existing = bpy.data.materials.get('Clear float glass')
    if existing is not None:
        return existing
    mat = bpy.data.materials.new('Clear float glass')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    clear = nodes.new('ShaderNodeBsdfTransparent')
    reflection = nodes.new('ShaderNodeBsdfGlossy'); reflection.inputs['Roughness'].default_value = 0.0
    fresnel = nodes.new('ShaderNodeFresnel')
    geometry = nodes.new('ShaderNodeNewGeometry')
    ior = nodes.new('ShaderNodeMath'); ior.operation = 'MULTIPLY_ADD'
    ior.inputs[1].default_value = 1.0 / 1.52 - 1.52; ior.inputs[2].default_value = 1.52
    links.new(geometry.outputs['Backfacing'], ior.inputs[0])
    links.new(ior.outputs['Value'], fresnel.inputs['IOR'])
    pane = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], pane.inputs['Fac'])
    links.new(clear.outputs['BSDF'], pane.inputs[1])
    links.new(reflection.outputs['BSDF'], pane.inputs[2])
    links.new(pane.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


def glowing(bpy, name, colour, strength, diffuse=(.85, .82, .78)):
    """A lit diffuser (opal glass, LED lens): emission over a matte surface."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*diffuse, 1)
    bsdf.inputs['Roughness'].default_value = .6
    bsdf.inputs['Emission Color'].default_value = (*colour, 1)
    bsdf.inputs['Emission Strength'].default_value = strength
    return mat


def amber_glass(bpy):
    mat, nodes, links, bsdf = _new(bpy, 'Amber bottle glass')
    bsdf.inputs['Base Color'].default_value = (.80, .42, .12, 1)
    bsdf.inputs['Transmission Weight'].default_value = 1.0
    bsdf.inputs['Roughness'].default_value = .04
    bsdf.inputs['IOR'].default_value = 1.5
    return mat


def tinted(bpy, source, name, multiply, roughness=None):
    """Copy a GLB material and multiply its base colour (texture or value)."""
    mat = source.copy(); mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    base = bsdf.inputs['Base Color']
    if base.is_linked:
        src = base.links[0].from_socket
        mix = nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        mix.inputs['B'].default_value = (*multiply, 1)
        links.new(src, mix.inputs['A']); links.new(mix.outputs['Result'], base)
    else:
        base.default_value = tuple(a * b for a, b in zip(base.default_value[:3], multiply)) + (1,)
    if roughness is not None and not bsdf.inputs['Roughness'].is_linked:
        bsdf.inputs['Roughness'].default_value = roughness
    return mat
