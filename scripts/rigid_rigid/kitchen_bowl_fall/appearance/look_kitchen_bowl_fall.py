"""Materials, the two stoneware bowls and the dishes around them.

The room is built from the solver's own colliders (``loft_kitchen.py``); this
module holds what both of them share -- the scanned
Poly Haven surfaces, the painted and metal finishes, and the lathe-turned
ceramics. Both moving bowls are turned from profiles whose envelope is exactly
their collision shape (the falling bowl's cylinder, the tableware's box
footprint and height), so the bowl that moves on screen is the body solved.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import (FALLING_BOWL_RADIUS, FALLING_BOWL_HEIGHT, TABLEWARE_PARTS,
                            TABLEWARE_BOWL_DIAMETER, TABLEWARE_BOWL_HEIGHT)

POLYHAVEN = _pcve_asset('polyhaven') / 'kitchen_bowl_fall'


# ------------------------------------------------------------------ helpers

def _new_material(bpy, name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree.nodes, m.node_tree.links, m.node_tree.nodes.get('Principled BSDF')


def plain(bpy, name, color, roughness=.5, metallic=0., specular=.5, grain=0.):
    """A uniform finish (paint, powder coat, rubber). ``grain`` adds a faint
    world-space drift in tone and sheen: a real painted surface is never one
    flat value, and a perfectly uniform albedo is what reads as CG."""
    m, n, l, bs = _new_material(bpy, name)
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['Metallic'].default_value = metallic
    bs.inputs['Specular IOR Level'].default_value = specular
    if grain:
        pos = n.new('ShaderNodeNewGeometry')
        noise = n.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 3.0
        noise.inputs['Detail'].default_value = 6.0
        l.new(pos.outputs['Position'], noise.inputs['Vector'])
        tone = n.new('ShaderNodeValToRGB')
        tone.color_ramp.elements[0].color = (*(c * (1 - grain) for c in color), 1)
        tone.color_ramp.elements[1].color = (*(min(1., c * (1 + grain)) for c in color), 1)
        l.new(noise.outputs['Fac'], tone.inputs['Fac'])
        l.new(tone.outputs['Color'], bs.inputs['Base Color'])
        sheen = n.new('ShaderNodeMapRange')
        sheen.inputs['To Min'].default_value = max(0., roughness - .08)
        sheen.inputs['To Max'].default_value = min(1., roughness + .08)
        l.new(noise.outputs['Fac'], sheen.inputs['Value'])
        l.new(sheen.outputs['Result'], bs.inputs['Roughness'])
    return m


def scanned(bpy, name, stem, tile_m, value=1., saturation=1., hue=.5, tint=None,
            rough_scale=1., rough_offset=0., normal_strength=1., rotate=False, specular=.5):
    """A Poly Haven 2k surface (diff / rough / nor_gl) laid at its real size.

    Every mesh that uses it carries a world-metre UV map (``world_uv``), so the
    mapping only has to divide by the scan's own physical size: bricks stay
    78 mm a course, floor strips keep their real width, and two boxes that meet
    continue the same texture instead of restarting it.
    """
    m, n, l, bs = _new_material(bpy, name)
    bs.inputs['Specular IOR Level'].default_value = specular
    uv = n.new('ShaderNodeUVMap')
    uv.uv_map = 'WorldMetres'
    mapping = n.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / tile_m, 1 / tile_m, 1)
    if rotate:
        mapping.inputs['Rotation'].default_value = (0, 0, math.pi / 2)
    l.new(uv.outputs['UV'], mapping.inputs['Vector'])

    def image(kind, colour):
        node = n.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(POLYHAVEN / f'{stem}_{kind}_2k.jpg'), check_existing=True)
        if not colour:
            node.image.colorspace_settings.name = 'Non-Color'
        node.interpolation = 'Cubic'
        l.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    diff = image('diff', True)
    hsv = n.new('ShaderNodeHueSaturation')
    hsv.inputs['Hue'].default_value = hue
    hsv.inputs['Saturation'].default_value = saturation
    hsv.inputs['Value'].default_value = value
    l.new(diff.outputs['Color'], hsv.inputs['Color'])
    out = hsv.outputs['Color']
    if tint:
        mix = n.new('ShaderNodeMixRGB')
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Fac'].default_value = 1.
        l.new(out, mix.inputs['Color1'])
        mix.inputs['Color2'].default_value = (*tint, 1)
        out = mix.outputs['Color']
    l.new(out, bs.inputs['Base Color'])
    rough = image('rough', False)
    scale = n.new('ShaderNodeMath')
    scale.operation = 'MULTIPLY_ADD'
    scale.use_clamp = True
    scale.inputs[1].default_value = rough_scale
    scale.inputs[2].default_value = rough_offset
    l.new(rough.outputs['Color'], scale.inputs[0])
    l.new(scale.outputs['Value'], bs.inputs['Roughness'])
    nor = image('nor_gl', False)
    nmap = n.new('ShaderNodeNormalMap')
    nmap.uv_map = 'WorldMetres'
    nmap.inputs['Strength'].default_value = normal_strength
    l.new(nor.outputs['Color'], nmap.inputs['Color'])
    l.new(nmap.outputs['Normal'], bs.inputs['Normal'])
    return m


def world_uv(obj, swap_vertical=False):
    """Planar UVs in metres from each face's dominant axis (in the object's
    own frame, which is the world frame for every unrotated box).

    ``swap_vertical`` turns the map a quarter on vertical faces, so a veneer
    whose grain runs along U reads as vertical grain on a door.
    """
    mesh = obj.data
    layer = mesh.uv_layers.get('WorldMetres') or mesh.uv_layers.new(name='WorldMetres')
    mesh.uv_layers.active = layer
    for poly in mesh.polygons:
        nx, ny, nz = (abs(c) for c in poly.normal)
        for li in poly.loop_indices:
            co = mesh.vertices[mesh.loops[li].vertex_index].co
            if nz >= nx and nz >= ny:
                u, v = co.x, co.y
            elif ny >= nx:
                u, v = (co.z, co.x) if swap_vertical else (co.x, co.z)
            else:
                u, v = (co.z, co.y) if swap_vertical else (co.y, co.z)
            layer.data[li].uv = (u, v)


def box(bpy, name, lo, hi, mat, bevel=0., swap_vertical=False, collection=None):
    """An axis-aligned box from world corners, mapped in world metres.

    Bevelled edges use hardened normals so the faces stay flat and only the
    radius catches light, the way a machined or sanded edge does."""
    import bmesh
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.)
    for v in bm.verts:
        v.co.x = lo[0] if v.co.x < 0 else hi[0]
        v.co.y = lo[1] if v.co.y < 0 else hi[1]
        v.co.z = lo[2] if v.co.z < 0 else hi[2]
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)
    mesh.materials.append(mat)
    world_uv(obj, swap_vertical)
    if bevel:
        for p in mesh.polygons:
            p.use_smooth = True
        mod = obj.modifiers.new('Eased edges', 'BEVEL')
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = 'ANGLE'
        mod.harden_normals = True
    return obj


def lathe(bpy, name, profile, mat, segments=144):
    """A closed lathe profile (r, z), z-up, origin on the axis at z = 0."""
    verts = [(r * math.cos(i * 2 * math.pi / segments), r * math.sin(i * 2 * math.pi / segments), z)
             for r, z in profile for i in range(segments)]
    faces = []
    for j in range(len(profile) - 1):
        for i in range(segments):
            a = j * segments + i
            b = j * segments + (i + 1) % segments
            faces.append((a, b, b + segments, a + segments))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.validate()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(mat)
    for p in mesh.polygons:
        p.use_smooth = True
    return o


def fit_profile(profile, radius, height):
    """Scale a hand-drawn profile so its envelope is exactly radius x height."""
    r_max = max(r for r, _ in profile)
    z_max = max(z for _, z in profile)
    return [(r / r_max * radius, z / z_max * height) for r, z in profile]


# ------------------------------------------------------------------ ceramics

def stoneware(bpy, name, glaze, glaze_pool, rim, clay, top_z, foot_z, gloss=.10,
              speckle=.55, speck_color=(.11, .075, .05)):
    """Hand-thrown stoneware: a glossy glaze that pools darker in places,
    thins and breaks to the clay body on the rim, iron speckle from the clay
    showing through, and an unglazed sandy foot.

    ``top_z`` / ``foot_z`` are in the object's own frame (the lathe's local z),
    so the glaze bands stay on the pot however the body tumbles.
    """
    m, n, l, bs = _new_material(bpy, name)
    tc = n.new('ShaderNodeTexCoord')
    sep = n.new('ShaderNodeSeparateXYZ')
    l.new(tc.outputs['Object'], sep.inputs['Vector'])
    # Pooling: the glaze is thicker (darker) in the hollows and runs.
    pool = n.new('ShaderNodeTexNoise')
    pool.inputs['Scale'].default_value = 26.
    pool.inputs['Detail'].default_value = 5.
    pool.inputs['Roughness'].default_value = .6
    l.new(tc.outputs['Object'], pool.inputs['Vector'])
    tone = n.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].position = .32
    tone.color_ramp.elements[0].color = (*glaze_pool, 1)
    tone.color_ramp.elements[1].position = .72
    tone.color_ramp.elements[1].color = (*glaze, 1)
    l.new(pool.outputs['Fac'], tone.inputs['Fac'])
    # Rim break: the glaze thins over the last few millimetres of the rim.
    rim_mask = n.new('ShaderNodeMapRange')
    rim_mask.inputs['From Min'].default_value = top_z - .0055
    rim_mask.inputs['From Max'].default_value = top_z - .0008
    l.new(sep.outputs['Z'], rim_mask.inputs['Value'])
    rim_mix = n.new('ShaderNodeMixRGB')
    l.new(rim_mask.outputs['Result'], rim_mix.inputs['Fac'])
    l.new(tone.outputs['Color'], rim_mix.inputs['Color1'])
    rim_mix.inputs['Color2'].default_value = (*rim, 1)
    # Iron speckle: sparse dark dots a fraction of a millimetre across.
    vor = n.new('ShaderNodeTexVoronoi')
    vor.inputs['Scale'].default_value = 520.
    l.new(tc.outputs['Object'], vor.inputs['Vector'])
    dot = n.new('ShaderNodeMath')
    dot.operation = 'LESS_THAN'
    dot.inputs[1].default_value = .16
    l.new(vor.outputs['Distance'], dot.inputs[0])
    sparse = n.new('ShaderNodeMath')
    sparse.operation = 'GREATER_THAN'
    sparse.inputs[1].default_value = 1. - .45 * speckle
    sep_c = n.new('ShaderNodeSeparateColor')
    l.new(vor.outputs['Color'], sep_c.inputs['Color'])
    l.new(sep_c.outputs['Red'], sparse.inputs[0])
    speck = n.new('ShaderNodeMath')
    speck.operation = 'MULTIPLY'
    l.new(dot.outputs['Value'], speck.inputs[0])
    l.new(sparse.outputs['Value'], speck.inputs[1])
    speck_mix = n.new('ShaderNodeMixRGB')
    l.new(speck.outputs['Value'], speck_mix.inputs['Fac'])
    l.new(rim_mix.outputs['Color'], speck_mix.inputs['Color1'])
    speck_mix.inputs['Color2'].default_value = (*speck_color, 1)
    # Unglazed foot: raw clay below the glaze line.
    foot = n.new('ShaderNodeMapRange')
    foot.inputs['From Min'].default_value = foot_z + .0015
    foot.inputs['From Max'].default_value = foot_z
    l.new(sep.outputs['Z'], foot.inputs['Value'])
    clay_mix = n.new('ShaderNodeMixRGB')
    l.new(foot.outputs['Result'], clay_mix.inputs['Fac'])
    l.new(speck_mix.outputs['Color'], clay_mix.inputs['Color1'])
    clay_mix.inputs['Color2'].default_value = (*clay, 1)
    l.new(clay_mix.outputs['Color'], bs.inputs['Base Color'])
    rough = n.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = gloss
    rough.inputs['To Max'].default_value = .82
    l.new(foot.outputs['Result'], rough.inputs['Value'])
    l.new(rough.outputs['Result'], bs.inputs['Roughness'])
    bs.inputs['Coat Weight'].default_value = .0
    # Glaze ripple: a very low, broad undulation, not a texture.
    ripple = n.new('ShaderNodeTexNoise')
    ripple.inputs['Scale'].default_value = 140.
    ripple.inputs['Detail'].default_value = 2.
    l.new(tc.outputs['Object'], ripple.inputs['Vector'])
    bump = n.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .06
    bump.inputs['Distance'].default_value = .0002
    l.new(ripple.outputs['Fac'], bump.inputs['Height'])
    l.new(bump.outputs['Normal'], bs.inputs['Normal'])
    return m


# Profiles are drawn in millimetres-ish units and fitted to the solver sizes.
# (r, z): outer wall from the foot up to the rim, then the inner wall back down.
SERVING_BOWL = [
    (0.000, 0.004), (0.040, 0.004), (0.043, 0.000), (0.051, 0.000), (0.055, 0.006),
    (0.060, 0.014), (0.070, 0.030), (0.082, 0.049), (0.093, 0.067), (0.099, 0.079),
    (0.1000, 0.0838), (0.0990, 0.0850), (0.0968, 0.0846),
    (0.0920, 0.0790), (0.0840, 0.0680), (0.0720, 0.0560), (0.0560, 0.0450),
    (0.0380, 0.0372), (0.0190, 0.0334), (0.000, 0.0326),
]
RICE_BOWL = [
    (0.000, 0.0030), (0.0220, 0.0030), (0.0240, 0.0000), (0.0310, 0.0000), (0.0330, 0.0060),
    (0.0370, 0.0110), (0.0470, 0.0190), (0.0560, 0.0300), (0.0635, 0.0450), (0.0680, 0.0580),
    (0.0697, 0.0680), (0.0700, 0.0712), (0.0688, 0.0720), (0.0672, 0.0710),
    (0.0655, 0.0650), (0.0612, 0.0520), (0.0540, 0.0385), (0.0440, 0.0265),
    (0.0320, 0.0185), (0.0160, 0.0142), (0.000, 0.0132),
]
PLATE = [
    (0.000, 0.0030), (0.070, 0.0030), (0.074, 0.0000), (0.084, 0.0000), (0.090, 0.0040),
    (0.105, 0.0080), (0.121, 0.0150), (0.1290, 0.0205), (0.1300, 0.0222), (0.1285, 0.0230),
    (0.1265, 0.0222), (0.1180, 0.0160), (0.1020, 0.0105), (0.0880, 0.0085), (0.000, 0.0075),
]


def make_falling_bowl(bpy):
    """The falling serving bowl: lathe of exactly the solver's cylinder.

    16 cm across, 7 cm tall, 0.55 kg -- a heavy-walled stoneware serving bowl.
    Glaze: a pale celadon that pools greener and breaks to toasted clay on the
    rim -- light enough to read inside the shaded cupboard and on black glass.
    The mesh is centred on the cylinder centre the solver reports.
    """
    R, H = FALLING_BOWL_RADIUS, FALLING_BOWL_HEIGHT
    profile = [(r, z - H / 2) for r, z in fit_profile(SERVING_BOWL, R, H)]
    glaze = stoneware(bpy, 'Falling bowl / celadon glaze',
                      glaze=(.42, .52, .44), glaze_pool=(.20, .32, .26),
                      rim=(.50, .38, .25), clay=(.50, .42, .33),
                      top_z=H / 2, foot_z=-H / 2 + .0042, gloss=.08, speckle=.4)
    bowl = lathe(bpy, 'Falling bowl', profile, glaze)
    return bowl


def make_tableware(bpy):
    """The bowl standing on the cooktop: a 14 cm rice/soup bowl, 7.2 cm tall,
    0.25 kg -- turned to exactly the footprint and height of its collision box.
    Glaze: oatmeal speckled stoneware. Returns {part key: object}."""
    R, H = TABLEWARE_BOWL_DIAMETER / 2, TABLEWARE_BOWL_HEIGHT
    profile = [(r, z - H / 2) for r, z in fit_profile(RICE_BOWL, R, H)]
    glaze = stoneware(bpy, 'Tableware bowl / oatmeal speckle glaze',
                      glaze=(.70, .655, .56), glaze_pool=(.56, .50, .41),
                      rim=(.46, .34, .23), clay=(.47, .40, .32),
                      top_z=H / 2, foot_z=-H / 2 + .0050, gloss=.22, speckle=1.)
    objects = {}
    for key in TABLEWARE_PARTS:
        objects[key] = lathe(bpy, f'Tableware {key}', profile, glaze)
    return objects


def dish_glazes(bpy):
    """The rest of the same set, for the shelves and the cupboard."""
    return {
        'oatmeal': stoneware(bpy, 'Dishes / oatmeal speckle', (.70, .655, .56), (.56, .50, .41),
                             (.46, .34, .23), (.47, .40, .32), top_z=1., foot_z=.003, gloss=.22, speckle=1.),
        'cobalt': stoneware(bpy, 'Dishes / cobalt', (.045, .085, .19), (.012, .028, .075),
                            (.42, .30, .19), (.50, .42, .33), top_z=1., foot_z=.003, gloss=.09, speckle=.35),
        'charcoal': stoneware(bpy, 'Dishes / charcoal matte', (.055, .052, .05), (.03, .029, .028),
                              (.30, .25, .20), (.40, .34, .28), top_z=1., foot_z=.003, gloss=.38, speckle=.2,
                              speck_color=(.30, .27, .24)),
    }


def stack(bpy, name, profile, radius, height, mat, base, count, step, top_rim=None):
    """``count`` identical pieces nested/stacked from ``base`` upward by ``step``."""
    shape = fit_profile(profile, radius, height)
    pieces = []
    for i in range(count):
        o = lathe(bpy, f'{name} {i + 1}', shape, mat, segments=96)
        o.location = (base[0], base[1], base[2] + i * step)
        o.rotation_euler = (0, 0, i * 1.7)
        pieces.append(o)
    return pieces
