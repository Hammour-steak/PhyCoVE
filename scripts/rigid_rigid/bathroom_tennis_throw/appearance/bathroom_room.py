"""A Nordic family bathroom built on the physics planes, read at 2x scale.

The simulation runs inside the collider boxes exported from big_project.glb
(assets/scenes/bathroom_tennis_throw/bathroom_colliders.json). That model is
authored at twice real size (shower glass 4.07 m, shower bench 0.89 m, ceiling
5.9 m, the slippers 0.65-0.73 m long), and the physics is kept exactly as it
is. So the picture is authored at the same 2x: every tile, window, fitting and
prop below is ``K`` times its real size, which makes the frame read as an
ordinary bathroom (the deliberately oversized 10 cm ball then reads as about
5 cm, and falls read slightly slow -- see README).

The GLB's own room meshes are not drawn. The room is rebuilt from the collider
list itself: every surface the ball can touch is a box face taken straight from
the JSON (walls, tiled skirting, floor, shower curb and tray, glass, bench, the
oak cabinet), and everything else is dressing placed clear of every
trajectory (checked per frame at render time).

All room meshes are written in world coordinates with the object at the
origin, so Object texture coordinates equal world coordinates and tiles,
grout and stone run on across neighbouring pieces without a seam.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

import bmesh
import bpy
from mathutils import Vector

K = 2.0                     # reading scale of the whole set (see module docstring)
FLOOR_Z = .042
CEILING_Z = 2.60 * K        # reads as a 2.6 m ceiling; the highest ball apex is 1.45 m
WALL_THICK = .25 * K

# --------------------------------------------------------------- geometry


def box(name, lo, hi, mat, bevel=0.0, props=None, collection=None):
    """Axis-aligned box written in world coordinates (object at the origin)."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector(((lo[0] + hi[0]) / 2 + v.co.x * (hi[0] - lo[0]),
                       (lo[1] + hi[1]) / 2 + v.co.y * (hi[1] - lo[1]),
                       (lo[2] + hi[2]) / 2 + v.co.z * (hi[2] - lo[2])))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)
    if isinstance(mat, (list, tuple)):
        for m in mat:
            obj.data.materials.append(m)
    elif mat is not None:
        obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Eased edges', 'BEVEL')
        mod.width, mod.segments, mod.limit_method = bevel, 2, 'ANGLE'
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    if props is not None:
        props.append(obj)
    return obj


def cylinder(name, centre, radius, depth, mat, axis='Z', verts=48, props=None):
    """Closed cylinder; axis is the world axis it runs along."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=radius, radius2=radius, depth=depth)
    rot = {'Z': None, 'X': ('Y', math.pi / 2), 'Y': ('X', math.pi / 2)}[axis]
    if rot:
        from mathutils import Matrix
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(rot[1], 3, rot[0]))
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(centre))
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    mod = obj.modifiers.new('Crisp caps', 'EDGE_SPLIT')
    mod.split_angle = math.radians(40)
    if props is not None:
        props.append(obj)
    return obj


def pane(name, lo, hi, glass, edge, props=None):
    """A glass sheet: the two broad faces are glass, the four thin edges carry
    the green of float glass seen end-on (that edge line is what tells the eye a
    clear panel is there at all)."""
    obj = box(name, lo, hi, [glass, edge], props=props)
    thin = min(range(3), key=lambda i: hi[i] - lo[i])
    for poly in obj.data.polygons:
        poly.material_index = 0 if abs(poly.normal[thin]) > .5 else 1
    return obj


def ring_mesh(name, rings, mat, props=None, cap_first=True, cap_last=True, subsurf=2):
    """Skin a list of equal-length closed rings (bottom to top) into a smooth
    shell, with optional n-gon caps on the first and last ring."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(rings[0])
    for a, b in zip(vs, vs[1:]):
        for i in range(n):
            bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    if cap_first:
        bm.faces.new(list(reversed(vs[0])))
    if cap_last:
        bm.faces.new(vs[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    if subsurf:
        mod = obj.modifiers.new('Smooth shell', 'SUBSURF')
        mod.levels = mod.render_levels = subsurf
    if props is not None:
        props.append(obj)
    return obj


def lathe(name, centre, profile, mat, props, segments=64, subsurf=1):
    cx, cy, z0 = centre
    rings = [[(cx + r * math.cos(2 * math.pi * i / segments), cy + r * math.sin(2 * math.pi * i / segments), z0 + z)
              for i in range(segments)] for r, z in profile]
    return ring_mesh(name, rings, mat, props, subsurf=subsurf)


def _superellipse(a, b, p, n=72):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s_ = math.cos(t), math.sin(t)
        pts.append((a * math.copysign(abs(c) ** (2 / p), c), b * math.copysign(abs(s_) ** (2 / p), s_)))
    norms = []
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i - 1], pts[(i + 1) % n]
        tx, ty = x1 - x0, y1 - y0
        ln = math.hypot(tx, ty) or 1.0
        norms.append((ty / ln, -tx / ln))      # outward for a counter-clockwise outline
    return pts, norms


# --------------------------------------------------------------- materials


def _principled(name, colour, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*colour, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    mat.diffuse_color = (*colour, 1)
    return mat, mat.node_tree.nodes, mat.node_tree.links, bsdf


def flat(name, colour, roughness=.5, metallic=0.0):
    mat, _, _, bsdf = _principled(name, colour, roughness)
    bsdf.inputs['Metallic'].default_value = metallic
    return mat


def _math(nodes, links, op, a, b=None):
    n = nodes.new('ShaderNodeMath')
    n.operation = op
    for i, src in enumerate((a, b)):
        if src is None:
            continue
        if isinstance(src, (int, float)):
            n.inputs[i].default_value = float(src)
        else:
            links.new(src, n.inputs[i])
    return n.outputs[0]


def glazed_tile(name, axes, size, grout, offset=(0.0, 0.0), colour=(.86, .87, .86),
                grout_colour=(.50, .50, .48), roughness=.05, seed=1.0):
    """White glazed ceramic wall tile in stack bond, laid out on world
    coordinates (``axes`` = the two world axes spanning the wall).

    No usable scanned white wall tile exists in the library (the only one is
    already on a kitchen wall), so the tile is procedural. What makes glazed tile
    read as real rather than as a grid decal is that no two tiles are coplanar or
    identical: each gets its own slight tilt, a +-2 % shift in white, a rounded
    glaze edge falling into recessed grout, and a soft low-frequency waviness in
    the glaze, so window reflections break up from tile to tile. All relief
    dimensions scale with K like the tile itself.
    """
    mat, nodes, links, bsdf = _principled(name, colour, roughness)
    geo = nodes.new('ShaderNodeNewGeometry')
    sep = nodes.new('ShaderNodeSeparateXYZ')
    links.new(geo.outputs['Position'], sep.inputs[0])
    index = {'x': 0, 'y': 1, 'z': 2}
    w, h = size
    pu, pv = w + grout, h + grout
    u = _math(nodes, links, 'ADD', sep.outputs[index[axes[0]]], offset[0])
    v = _math(nodes, links, 'ADD', sep.outputs[index[axes[1]]], offset[1])
    su = _math(nodes, links, 'DIVIDE', u, pu)
    sv = _math(nodes, links, 'DIVIDE', v, pv)
    cu = _math(nodes, links, 'FLOOR', su)
    cv = _math(nodes, links, 'FLOOR', sv)
    fu = _math(nodes, links, 'SUBTRACT', su, cu)
    fv = _math(nodes, links, 'SUBTRACT', sv, cv)
    du = _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'MINIMUM', fu, _math(nodes, links, 'SUBTRACT', 1.0, fu)), pu)
    dv = _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'MINIMUM', fv, _math(nodes, links, 'SUBTRACT', 1.0, fv)), pv)
    d = _math(nodes, links, 'MINIMUM', du, dv)
    is_grout = _math(nodes, links, 'LESS_THAN', d, grout / 2)
    edge_w = .0025 * K
    edge = _math(nodes, links, 'MINIMUM', _math(nodes, links, 'MAXIMUM',
                 _math(nodes, links, 'DIVIDE', _math(nodes, links, 'SUBTRACT', d, grout / 2), edge_w), 0.0), 1.0)
    rounded = _math(nodes, links, 'MULTIPLY', edge, _math(nodes, links, 'SUBTRACT', 2.0, edge))
    cell = nodes.new('ShaderNodeCombineXYZ')
    links.new(cu, cell.inputs[0])
    links.new(cv, cell.inputs[1])
    cell.inputs[2].default_value = seed
    rnd = nodes.new('ShaderNodeTexWhiteNoise')
    rnd.noise_dimensions = '3D'
    links.new(cell.outputs[0], rnd.inputs['Vector'])
    rsep = nodes.new('ShaderNodeSeparateColor')
    links.new(rnd.outputs['Color'], rsep.inputs[0])
    tilt_u = _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', rsep.outputs[0], .5),
                   _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', fu, .5), pu * .0045))
    tilt_v = _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', rsep.outputs[1], .5),
                   _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', fv, .5), pv * .0045))
    wave = nodes.new('ShaderNodeTexNoise')
    wave.inputs['Scale'].default_value = 9.0 / K
    wave.inputs['Detail'].default_value = 1.0
    links.new(geo.outputs['Position'], wave.inputs['Vector'])
    waviness = _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', wave.outputs['Fac'], .5), .00025 * K)
    height = _math(nodes, links, 'ADD', _math(nodes, links, 'MULTIPLY', rounded, .0007 * K),
                   _math(nodes, links, 'ADD', _math(nodes, links, 'ADD', tilt_u, tilt_v), waviness))
    height = _math(nodes, links, 'MULTIPLY', height, _math(nodes, links, 'SUBTRACT', 1.0, is_grout))
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 1.0
    bump.inputs['Distance'].default_value = 1.0
    links.new(height, bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    shade = _math(nodes, links, 'ADD', .98, _math(nodes, links, 'MULTIPLY', rsep.outputs[2], .04))
    tint = nodes.new('ShaderNodeMix')
    tint.data_type = 'RGBA'
    tint.blend_type = 'MULTIPLY'
    tint.inputs['Factor'].default_value = 1.0
    tint.inputs['A'].default_value = (*colour, 1)
    grey = nodes.new('ShaderNodeCombineColor')
    for i in range(3):
        links.new(shade, grey.inputs[i])
    links.new(grey.outputs[0], tint.inputs['B'])
    mix = nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    links.new(is_grout, mix.inputs['Factor'])
    links.new(tint.outputs['Result'], mix.inputs['A'])
    mix.inputs['B'].default_value = (*grout_colour, 1)
    links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    links.new(is_grout, rough.inputs['Value'])
    rough.inputs['To Min'].default_value = roughness
    rough.inputs['To Max'].default_value = .85
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    return mat


def hex_tile(name, across, grout, colour=(.46, .46, .44), grout_colour=(.36, .36, .35), roughness=.44, seed=3.0):
    """Matt porcelain hexagon floor tile laid out on world x/y (pointy-top
    hexes, ``across`` = distance between flats).

    Indoor porcelain is flat and fine: the relief is only a 1.5 mm-scale eased
    edge running down into a shallow, narrow, pale grout line, plus a few
    microradians of tilt per tile. Each tile gets its own +-3 % shade and a
    slight roughness offset (no two pressings are identical), and a slow
    world-space mottle breaks up the large flat field without any repeat.
    """
    mat, nodes, links, bsdf = _principled(name, colour, roughness)
    geo = nodes.new('ShaderNodeNewGeometry')
    sep = nodes.new('ShaderNodeSeparateXYZ')
    links.new(geo.outputs['Position'], sep.inputs[0])
    u, v = sep.outputs[0], sep.outputs[1]
    W = across
    H = W * math.sqrt(3) / 2

    def lattice(ox, oy):
        uu = _math(nodes, links, 'SUBTRACT', u, ox)
        vv = _math(nodes, links, 'SUBTRACT', v, oy)
        qx = _math(nodes, links, 'SUBTRACT', uu, _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'ROUND', _math(nodes, links, 'DIVIDE', uu, W)), W))
        qy = _math(nodes, links, 'SUBTRACT', vv, _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'ROUND', _math(nodes, links, 'DIVIDE', vv, 2 * H)), 2 * H))
        d2 = _math(nodes, links, 'ADD', _math(nodes, links, 'MULTIPLY', qx, qx), _math(nodes, links, 'MULTIPLY', qy, qy))
        return qx, qy, d2

    ax, ay, da = lattice(0.0, 0.0)
    bx, by, db = lattice(W / 2, H)
    use_b = _math(nodes, links, 'GREATER_THAN', da, db)
    qx = _math(nodes, links, 'ADD', ax, _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', bx, ax), use_b))
    qy = _math(nodes, links, 'ADD', ay, _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', by, ay), use_b))
    aqx = _math(nodes, links, 'ABSOLUTE', qx)
    aqy = _math(nodes, links, 'ABSOLUTE', qy)
    hexr = _math(nodes, links, 'MAXIMUM', aqx, _math(nodes, links, 'ADD', _math(nodes, links, 'MULTIPLY', aqx, .5),
                                                       _math(nodes, links, 'MULTIPLY', aqy, math.sqrt(3) / 2)))
    e = _math(nodes, links, 'SUBTRACT', W / 2, hexr)          # distance to the tile edge
    is_grout = _math(nodes, links, 'LESS_THAN', e, grout / 2)
    edge = _math(nodes, links, 'MINIMUM', _math(nodes, links, 'MAXIMUM',
                 _math(nodes, links, 'DIVIDE', _math(nodes, links, 'SUBTRACT', e, grout / 2), .0015 * K), 0.0), 1.0)
    rounded = _math(nodes, links, 'MULTIPLY', edge, _math(nodes, links, 'SUBTRACT', 2.0, edge))
    cell = nodes.new('ShaderNodeCombineXYZ')
    links.new(_math(nodes, links, 'SUBTRACT', u, qx), cell.inputs[0])
    links.new(_math(nodes, links, 'SUBTRACT', v, qy), cell.inputs[1])
    cell.inputs[2].default_value = seed
    rnd = nodes.new('ShaderNodeTexWhiteNoise')
    rnd.noise_dimensions = '3D'
    links.new(cell.outputs[0], rnd.inputs['Vector'])
    rsep = nodes.new('ShaderNodeSeparateColor')
    links.new(rnd.outputs['Color'], rsep.inputs[0])
    tilt = _math(nodes, links, 'ADD',
                 _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', rsep.outputs[0], .5), _math(nodes, links, 'MULTIPLY', qx, .004)),
                 _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', rsep.outputs[1], .5), _math(nodes, links, 'MULTIPLY', qy, .004)))
    height = _math(nodes, links, 'ADD', _math(nodes, links, 'MULTIPLY', rounded, .0004 * K), tilt)
    height = _math(nodes, links, 'MULTIPLY', height, _math(nodes, links, 'SUBTRACT', 1.0, is_grout))
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 1.0
    bump.inputs['Distance'].default_value = 1.0
    links.new(height, bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    mottle = nodes.new('ShaderNodeTexNoise')
    mottle.inputs['Scale'].default_value = 1.1 / K
    mottle.inputs['Detail'].default_value = 4.0
    links.new(geo.outputs['Position'], mottle.inputs['Vector'])
    fine = nodes.new('ShaderNodeTexNoise')
    fine.inputs['Scale'].default_value = 140 / K
    fine.inputs['Detail'].default_value = 3.0
    links.new(geo.outputs['Position'], fine.inputs['Vector'])
    shade = _math(nodes, links, 'ADD', .955, _math(nodes, links, 'ADD',
                  _math(nodes, links, 'MULTIPLY', rsep.outputs[2], .06),
                  _math(nodes, links, 'ADD', _math(nodes, links, 'MULTIPLY', mottle.outputs['Fac'], .05),
                        _math(nodes, links, 'MULTIPLY', fine.outputs['Fac'], .03))))
    shade = _math(nodes, links, 'SUBTRACT', shade, .04)
    grey = nodes.new('ShaderNodeCombineColor')
    for i in range(3):
        links.new(shade, grey.inputs[i])
    tint = nodes.new('ShaderNodeMix')
    tint.data_type = 'RGBA'
    tint.blend_type = 'MULTIPLY'
    tint.inputs['Factor'].default_value = 1.0
    tint.inputs['A'].default_value = (*colour, 1)
    links.new(grey.outputs[0], tint.inputs['B'])
    mix = nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    links.new(is_grout, mix.inputs['Factor'])
    links.new(tint.outputs['Result'], mix.inputs['A'])
    mix.inputs['B'].default_value = (*grout_colour, 1)
    links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    tile_rough = _math(nodes, links, 'ADD', roughness, _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', fine.outputs['Fac'], .5), .10))
    rough = _math(nodes, links, 'ADD', tile_rough, _math(nodes, links, 'MULTIPLY', is_grout, _math(nodes, links, 'SUBTRACT', .88, tile_rough)))
    links.new(rough, bsdf.inputs['Roughness'])
    return mat


def scanned(name, diffuse, tile_m, roughness_range=None, normal_strength=1.0, hue_sat_val=None,
            colour_gain=None, box_blend=.2, coords='Object', grey=False):
    """A Poly Haven texture set (colour, roughness, OpenGL normal) tiled at
    ``tile_m`` metres (= K x the scan's real size). Box projection, so one
    material wraps every face of a box without streaking; on room meshes Object
    coordinates are world space, on moving bodies their own frame."""
    mat, nodes, links, bsdf = _principled(name, (.6, .6, .6), .5)
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / tile_m, 1 / tile_m, 1 / tile_m)
    links.new(coord.outputs[coords], mapping.inputs['Vector'])

    def tex(kind, colour_data):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(diffuse).replace('_diff_', f'_{kind}_'), check_existing=True)
        if not colour_data:
            node.image.colorspace_settings.name = 'Non-Color'
        node.projection = 'BOX'
        node.projection_blend = box_blend
        node.extension = 'REPEAT'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    colour = tex('diff', True).outputs['Color']
    if grey:
        bw = nodes.new('ShaderNodeRGBToBW')
        links.new(colour, bw.inputs[0])
        colour = bw.outputs[0]
    if hue_sat_val is not None:
        hsv = nodes.new('ShaderNodeHueSaturation')
        hsv.inputs['Hue'].default_value, hsv.inputs['Saturation'].default_value, hsv.inputs['Value'].default_value = hue_sat_val
        links.new(colour, hsv.inputs['Color'])
        colour = hsv.outputs['Color']
    if colour_gain is not None:
        gain = nodes.new('ShaderNodeMix')
        gain.data_type = 'RGBA'
        gain.blend_type = 'MULTIPLY'
        gain.inputs['Factor'].default_value = 1.0
        links.new(colour, gain.inputs['A'])
        gain.inputs['B'].default_value = (*colour_gain, 1)
        colour = gain.outputs['Result']
    links.new(colour, bsdf.inputs['Base Color'])
    rough = tex('rough', False).outputs['Color']
    if roughness_range is not None:
        remap = nodes.new('ShaderNodeMapRange')
        links.new(rough, remap.inputs['Value'])
        remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = roughness_range
        rough = remap.outputs['Result']
    links.new(rough, bsdf.inputs['Roughness'])
    nmap = nodes.new('ShaderNodeNormalMap')
    nmap.inputs['Strength'].default_value = normal_strength
    links.new(tex('nor_gl', False).outputs['Color'], nmap.inputs['Color'])
    links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def plaster(name, colour, roughness=.9):
    """Matt emulsion: one colour, never one value (slow tonal drift)."""
    mat, nodes, links, bsdf = _principled(name, colour, roughness)
    geo = nodes.new('ShaderNodeNewGeometry')
    drift = nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value = .7 / K
    drift.inputs['Detail'].default_value = 3.0
    links.new(geo.outputs['Position'], drift.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].position, tone.color_ramp.elements[1].position = .3, .7
    tone.color_ramp.elements[0].color = (*(c * .96 for c in colour), 1)
    tone.color_ramp.elements[1].color = (*(min(1., c * 1.02) for c in colour), 1)
    links.new(drift.outputs['Fac'], tone.inputs['Fac'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    return mat


def honed_stone(name, colour=(.74, .73, .70), roughness=.42):
    """Light honed composite stone (shower curb, bench top): fine speckle, no
    veins -- it is seen at 8-14 m, where only its value and soft sheen matter."""
    mat, nodes, links, bsdf = _principled(name, colour, roughness)
    geo = nodes.new('ShaderNodeNewGeometry')
    speck = nodes.new('ShaderNodeTexNoise')
    speck.inputs['Scale'].default_value = 260 / K
    speck.inputs['Detail'].default_value = 4
    links.new(geo.outputs['Position'], speck.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = .42, .62
    ramp.color_ramp.elements[0].color = (*(c * .86 for c in colour), 1)
    ramp.color_ramp.elements[1].color = (*colour, 1)
    links.new(speck.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    return mat


def thin_glass(name='Clear shower glass', tint=(1.0, 1.0, 1.0)):
    """Thin float glass: Fresnel reflection over a see-through layer.

    Shaded as transparent so camera rays stay camera rays (the window view is a
    camera-only photograph) and so the panes add no refraction caustics/noise.
    Cycles' Fresnel node inverts the IOR on back faces, which would make a ray
    leaving the pane at > 41 deg totally reflect and turn the glass black; the
    inverse IOR fed on back faces cancels that.
    """
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    clear = nodes.new('ShaderNodeBsdfTransparent')
    clear.inputs['Color'].default_value = (*tint, 1)
    reflection = nodes.new('ShaderNodeBsdfGlossy')
    reflection.inputs['Roughness'].default_value = 0.0
    fresnel = nodes.new('ShaderNodeFresnel')
    geometry = nodes.new('ShaderNodeNewGeometry')
    ior = nodes.new('ShaderNodeMath')
    ior.operation = 'MULTIPLY_ADD'
    ior.inputs[1].default_value = 1.0 / 1.52 - 1.52
    ior.inputs[2].default_value = 1.52
    links.new(geometry.outputs['Backfacing'], ior.inputs[0])
    links.new(ior.outputs['Value'], fresnel.inputs['IOR'])
    mix = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], mix.inputs['Fac'])
    links.new(clear.outputs['BSDF'], mix.inputs[1])
    links.new(reflection.outputs['BSDF'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


def glass_edge():
    mat, _, _, bsdf = _principled('Float glass edge', (.30, .42, .36), .08)
    bsdf.inputs['Transmission Weight'].default_value = .6
    return mat


def frosted_glass():
    """Acid-etched privacy glass: a diffuse transmitter with a glossy face.
    Light comes through it scattered -- a bright panel, no sun patch."""
    mat = bpy.data.materials.new('Acid-etched privacy glass')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    through = nodes.new('ShaderNodeBsdfTranslucent')
    through.inputs['Color'].default_value = (.92, .93, .93, 1)
    face = nodes.new('ShaderNodeBsdfGlossy')
    face.inputs['Roughness'].default_value = .25
    fres = nodes.new('ShaderNodeFresnel')
    fres.inputs['IOR'].default_value = 1.52
    mix = nodes.new('ShaderNodeMixShader')
    links.new(fres.outputs['Fac'], mix.inputs['Fac'])
    links.new(through.outputs['BSDF'], mix.inputs[1])
    links.new(face.outputs['BSDF'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


def mirror_material():
    mat, _, _, bsdf = _principled('Silvered mirror', (.92, .92, .92), .02)
    bsdf.inputs['Metallic'].default_value = 1.0
    return mat


# --------------------------------------------------------------- room


def build_room(colliders, assets):
    """Build shell, shower, cabinet and fixed fittings on the collider faces.

    Returns a dict with the props (objects that are NOT physics surfaces and
    must stay clear of the ball), the windows for the daylight and the
    materials the look module reuses.
    """
    col = {b['name']: b for b in colliders['boxes']}

    def lo_hi(name):
        c, h = col[name]['center'], col[name]['half_extents']
        return [c[i] - h[i] for i in range(3)], [c[i] + h[i] for i in range(3)]

    props = []
    S, N, E, W = -4.770, 4.493, 10.950, -8.600
    assert abs(lo_hi('wall_south')[1][1] - S) < 1e-6 and abs(lo_hi('wall_north')[0][1] - N) < 1e-6
    assert abs(lo_hi('wall_east')[0][0] - E) < 1e-6 and abs(lo_hi('wall_west')[1][0] - W) < 1e-6
    skirt_top = lo_hi('skirting_south')[1][2]

    m = {}
    # Matt light-grey porcelain hexagons, 13 cm across the flats, 3 mm pale
    # grout (all x K).
    m['floor'] = hex_tile('Matt porcelain hexagon floor tile', .13 * K, .003 * K)
    # 147 mm white tiles with 3 mm grout; courses start at the top of the tiled
    # skirting so the first full course sits on it, as a tiler would set out.
    tile, grout = .147 * K, .003 * K
    m['tile_x'] = glazed_tile('White glazed tile 15x15 (x-z walls)', ('x', 'z'), (tile, tile), grout, offset=(.0, -skirt_top))
    m['tile_y'] = glazed_tile('White glazed tile 15x15 (y-z walls)', ('y', 'z'), (tile, tile), grout, offset=(.0, -skirt_top), seed=2.0)
    m['ceiling'] = plaster('Ceiling white emulsion', (.80, .80, .78))
    m['stone'] = honed_stone('Honed light stone')
    m['oak'] = scanned('Oiled white oak', assets / 'oak_veneer_02_diff_2k.jpg', 1.0 * K,
                       roughness_range=(.40, .64), normal_strength=.7, hue_sat_val=(.5, .62, 1.0),
                       colour_gain=(.95, .93, .91))
    m['glass'] = thin_glass()
    m['glass_edge'] = glass_edge()
    m['black_metal'] = flat('Powder-coated black steel', (.018, .018, .018), .38)
    m['white_paint'] = flat('Satin white joinery paint', (.80, .80, .78), .35)
    m['grout_dark'] = flat('Shadow gap', (.02, .02, .02), .9)
    m['tub'] = flat('White cast stone resin', (.86, .86, .85), .16)
    m['ceramic'] = flat('White glazed porcelain', (.88, .88, .87), .07)
    m['mirror'] = mirror_material()

    # ---- floor slab and the shower tray --------------------------------
    box('Floor / porcelain hexagon tiles', (W - .6, S - .6, FLOOR_Z - .40), (E + .6, N + .6, FLOOR_Z), m['floor'])
    lo, hi = lo_hi('shower_base')
    box('Shower tray floor', (lo[0], lo[1], FLOOR_Z - .01), (hi[0], hi[1], hi[2]), m['floor'])
    for name in ('shower_rim_west', 'shower_rim_north', 'shower_rim_east', 'shower_rim_south'):
        lo, hi = lo_hi(name)
        box(f'Shower curb / {name}', (lo[0], max(lo[1], S - .01), FLOOR_Z - .01),
            (min(hi[0], E + .01), hi[1], hi[2]), m['stone'], bevel=.004 * K)

    # ---- walls: tiled inner faces on the measured planes ---------------
    # Each wall is a slab built in pieces around its openings, so every window
    # sits in a real reveal. Clear windows: a wide south window over the
    # cabinet (the morning sun comes through it), a tall east window beyond the
    # shower door, and one in the north wall behind the camera (soft fill, as
    # any real room has light from more than one side). The frosted pane is in
    # the east wall inside the shower, above the bench.
    windows = [
        dict(name='South window', axis='x', outer=S - WALL_THICK, inner=S, inward=1,
             a0=-.55, a1=2.25, z0=FLOOR_Z + .74 * K, z1=FLOOR_Z + 2.06 * K, mullions=1),
        dict(name='East window', axis='y', outer=E + WALL_THICK, inner=E, inward=-1,
             a0=-1.70, a1=-.10, z0=FLOOR_Z + .80 * K, z1=FLOOR_Z + 2.06 * K, mullions=0),
        dict(name='North window', axis='x', outer=N + WALL_THICK, inner=N, inward=-1,
             a0=-4.80, a1=-1.00, z0=FLOOR_Z + .70 * K, z1=FLOOR_Z + 2.06 * K, mullions=1),
    ]
    fw = dict(y0=-4.30, y1=-2.70, z0=FLOOR_Z + 1.05 * K, z1=FLOOR_Z + 1.95 * K)
    wall_with_openings('South wall', 'x', S - WALL_THICK, S, (W - .6, E + .6),
                       [(w['a0'], w['a1'], w['z0'], w['z1']) for w in windows if w['name'].startswith('South')], m['tile_x'])
    wall_with_openings('North wall', 'x', N, N + WALL_THICK, (W - .6, E + .6),
                       [(w['a0'], w['a1'], w['z0'], w['z1']) for w in windows if w['name'].startswith('North')], m['tile_x'])
    wall_with_openings('East wall', 'y', E, E + WALL_THICK, (S - .6, N + .6),
                       [(w['a0'], w['a1'], w['z0'], w['z1']) for w in windows if w['name'].startswith('East')]
                       + [(fw['y0'], fw['y1'], fw['z0'], fw['z1'])], m['tile_y'])
    box('West wall', (W - WALL_THICK, S - .6, FLOOR_Z - .4), (W, N + .6, CEILING_Z + .4), m['tile_y'])
    box('Ceiling', (W - .6, S - .6, CEILING_Z), (E + .6, N + .6, CEILING_Z + .4), m['ceiling'])

    # ---- skirting: tiled upstand exactly on the measured baseboard faces
    # (45 mm proud, 0.20 m high: reads as an ordinary 10 cm tiled skirting)
    for name, mat in (('skirting_south', m['tile_x']), ('skirting_north', m['tile_x']), ('skirting_east', m['tile_y'])):
        lo, hi = lo_hi(name)
        lo = [max(lo[0], W), max(lo[1], S - .01), FLOOR_Z - .005]
        hi = [min(hi[0], E + .01), min(hi[1], N + .01), hi[2]]
        box(f'Tiled skirting / {name}', lo, hi, mat, bevel=.003 * K)

    # ---- clear windows: white timber casements, oak window boards ------
    win_glass = thin_glass('Window float glass')
    for w in windows:
        casement(w, m, props, win_glass)

    # ---- east frosted window -------------------------------------------
    fd = E + WALL_THICK - .07 * K
    fb = .05 * K
    box('Frosted window frame sill', (fd - .03 * K, fw['y0'], fw['z0']), (fd + .03 * K, fw['y1'], fw['z0'] + fb), m['white_paint'], .002 * K, props)
    box('Frosted window frame head', (fd - .03 * K, fw['y0'], fw['z1'] - fb), (fd + .03 * K, fw['y1'], fw['z1']), m['white_paint'], .002 * K, props)
    box('Frosted window jamb south', (fd - .03 * K, fw['y0'], fw['z0'] + fb), (fd + .03 * K, fw['y0'] + fb, fw['z1'] - fb), m['white_paint'], .002 * K, props)
    box('Frosted window jamb north', (fd - .03 * K, fw['y1'] - fb, fw['z0'] + fb), (fd + .03 * K, fw['y1'], fw['z1'] - fb), m['white_paint'], .002 * K, props)
    box('Frosted pane', (fd - .004 * K, fw['y0'] + fb, fw['z0'] + fb), (fd + .004 * K, fw['y1'] - fb, fw['z1'] - fb), frosted_glass(), props=props)

    # ---- shower glass: the pane faces are the collider faces -----------
    # West screen: a fixed pane whose west face is the collider's west face,
    # with the sliding pane parked behind it whose east face is the collider's
    # east face (edit_bouncier_bathroom hits it from inside the shower).
    # Glass stands the collider's full 4.07 m (reads 2.03 m).
    lo, hi = lo_hi('glass_screen_south')
    gt = .010 * K
    gz0, gz1 = .150, hi[2]
    pane('Shower screen / fixed pane', (lo[0], S + .012, gz0), (lo[0] + gt, hi[1], gz1), m['glass'], m['glass_edge'])
    pane('Shower screen / parked slider', (hi[0] - gt, S + .012, gz0), (hi[0], -3.354, gz1), m['glass'], m['glass_edge'])
    lo2, hi2 = lo_hi('glass_shower_door')
    pane('Shower door / inner pane', (lo2[0], lo2[1], gz0), (8.959, lo2[1] + gt, gz1), m['glass'], m['glass_edge'])
    pane('Shower door / outer pane', (7.72, hi2[1] - gt, gz0), (E - .012, hi2[1], gz1), m['glass'], m['glass_edge'])
    # Top track, slim floor channels and wall profile in black steel (not
    # physics: above every ball path / sitting on the curb under the rail
    # collider / against the wall).
    tr = .016 * K
    box('Screen top track', (lo[0] - .003 * K, S, gz1), (hi[0] + .003 * K, hi[1], gz1 + tr), m['black_metal'], .001 * K, props)
    box('Door top track', (lo2[0], lo2[1] - .003 * K, gz1), (E, hi2[1] + .003 * K, gz1 + tr), m['black_metal'], .001 * K, props)
    box('Screen floor channel', (lo[0] - .005, S, .1357), (lo[0] + .015, hi[1], gz0 + .006), m['black_metal'], .001, props)
    box('Door floor channel', (lo2[0], lo2[1] - .004, .1357), (E, hi2[1] + .004, gz0 + .006), m['black_metal'], .001, props)
    box('Screen wall profile', (lo[0] - .008, S, gz0), (hi[0] + .008, S + .012, gz1), m['black_metal'], .001, props)
    # Door handle bar on the outer sliding pane (outside face, north).
    box('Door pull bar', (8.30, hi2[1], .95 * K), (8.33, hi2[1] + .05, 1.25 * K), m['black_metal'], .004, props)

    # ---- shower bench (the collider block at the far end; reads 44 cm) --
    lo, hi = lo_hi('basin_southeast')
    st = .03 * K
    box('Shower bench / tiled block', (lo[0], max(lo[1], S - .01), FLOOR_Z - .01), (min(hi[0], E + .01), hi[1], hi[2] - st), m['tile_y'], .002 * K)
    box('Shower bench / stone top', (lo[0], max(lo[1], S - .01), hi[2] - st), (min(hi[0], E + .01), hi[1], hi[2]), m['stone'], .003 * K)

    # ---- oak cabinet = the 'toilet_bowl' collider block ----------------
    cabinet = build_cabinet(lo_hi('toilet_bowl'), m, props)

    # ---- fixtures that are pure dressing (no collider, clear of every path)
    freestanding_tub('Freestanding bath', (8.85, -.90, FLOOR_Z), m, props)
    floor_tub_filler('Bath filler', (6.75, -.90, FLOOR_Z), m, props, towards=(1, 0))
    wall_vanity('Vanity', -2.50, -.75, S, m, props)

    return dict(props=props, materials=m, windows=windows, frosted=dict(E=E, **fw), cabinet=cabinet,
                ceiling_z=CEILING_Z)


def wall_with_openings(name, axis, d0, d1, span, openings, mat):
    """A wall slab d0..d1 thick (across the wall), running along ``axis`` over
    ``span``, floor to ceiling, cut around rectangular openings
    [(a0, a1, z0, z1), ...]."""
    zb, zt = FLOOR_Z - .4, CEILING_Z + .4

    def piece(label, a0, a1, z0, z1):
        if a1 - a0 < 1e-6 or z1 - z0 < 1e-6:
            return
        if axis == 'x':
            box(f'{name} / {label}', (a0, d0, z0), (a1, d1, z1), mat)
        else:
            box(f'{name} / {label}', (d0, a0, z0), (d1, a1, z1), mat)

    cur = span[0]
    for i, (a0, a1, z0, z1) in enumerate(sorted(openings)):
        piece(f'pier {i}', cur, a0, zb, zt)
        piece(f'below opening {i}', a0, a1, zb, z0)
        piece(f'above opening {i}', a0, a1, z1, zt)
        cur = a1
    piece('end pier', cur, span[1], zb, zt)


def casement(w, m, props, glass):
    """White timber casement set into the reveal from the outside face,
    glazed with thin float glass (transparent to shadow rays: the sun comes
    in), plus an oiled-oak window board proud of the tiles. Sections are real
    joinery sizes times K."""
    inward, axis = w['inward'], w['axis']
    d_a = w['outer'] + inward * .06 * K
    d_b = d_a + inward * .068 * K
    dlo, dhi = min(d_a, d_b), max(d_a, d_b)
    dmid = (dlo + dhi) / 2
    a0, a1, z0, z1 = w['a0'], w['a1'], w['z0'], w['z1']
    bar = .056 * K

    def member(label, al, ah, zl, zh, lo_d=dlo, hi_d=dhi, mat=None, bevel=.002 * K):
        mat = mat or m['white_paint']
        if axis == 'x':
            return box(f"{w['name']} {label}", (al, lo_d, zl), (ah, hi_d, zh), mat, bevel, props)
        return box(f"{w['name']} {label}", (lo_d, al, zl), (hi_d, ah, zh), mat, bevel, props)

    member('head', a0, a1, z1 - bar, z1)
    member('sill rail', a0, a1, z0, z0 + bar)
    member('jamb A', a0, a0 + bar, z0 + bar, z1 - bar)
    member('jamb B', a1 - bar, a1, z0 + bar, z1 - bar)
    for k in range(1, w['mullions'] + 1):
        am = a0 + (a1 - a0) * k / (w['mullions'] + 1)
        member(f'mullion {k}', am - .028 * K, am + .028 * K, z0 + bar, z1 - bar, dlo + .006 * K, dhi - .006 * K)
    glass_pane = member('pane', a0 + bar, a1 - bar, z0 + bar, z1 - bar, dmid - .003 * K, dmid + .003 * K, glass, 0)
    glass_pane.visible_shadow = False
    board_lo = w['outer'] + inward * .13 * K
    board_hi = w['inner'] + inward * .025 * K
    member('board (oak)', a0 - .03 * K, a1 + .03 * K, z0 - .03 * K, z0, min(board_lo, board_hi), max(board_lo, board_hi),
           m['oak'], .003 * K)


def build_cabinet(extent, m, props):
    """Low built-in oak cabinet on the collider block (reads 60 x 70 x 56 cm).

    The ball strikes its east face (z 0.09-0.79 across the suite), so that
    side is one solid oak panel flush with the collider face down to the
    floor; the toe-kick recess is only on the north front, which no ball
    touches. Push-to-open doors, a thick oak top.
    """
    (x0, y0, z0), (x1, y1, z1) = extent
    oak = m['oak']
    parts = []
    t = .019 * K
    top = .04 * K
    kick = .09 * K
    parts.append(box('Cabinet / east side (impact face)', (x1 - t, y0, z0), (x1, y1, z1 - top), oak, .0015 * K))
    parts.append(box('Cabinet / west side', (x0, y0, z0), (x0 + t, y1, z1 - top), oak, .0015 * K))
    parts.append(box('Cabinet / top slab', (x0, y0, z1 - top), (x1, y1, z1), oak, .003 * K))
    parts.append(box('Cabinet / toe kick', (x0 + t, y1 - .05 * K, z0), (x1 - t, y1 - .045 * K, z0 + kick), m['grout_dark']))
    parts.append(box('Cabinet / carcass core', (x0 + t, y0, z0), (x1 - t, y1 - .05 * K, z1 - top), oak))
    gap = .003 * K
    door_z0, door_z1 = z0 + kick + gap, z1 - top - gap
    xm = (x0 + x1) / 2
    parts.append(box('Cabinet / door west', (x0 + t + gap, y1 - t, door_z0), (xm - gap / 2, y1, door_z1), oak, .0015 * K))
    parts.append(box('Cabinet / door east', (xm + gap / 2, y1 - t, door_z0), (x1 - t - gap, y1, door_z1), oak, .0015 * K))
    parts.append(box('Cabinet / door reveal shadow', (x0 + t, y1 - t - .003 * K, z0 + kick), (x1 - t, y1 - t, z1 - top), m['grout_dark']))
    # No knobs: anything proud of the front would stand between the camera
    # and the ball where it passes behind the cabinet (edit_aim_north f21,
    # edit_bouncier_bathroom f20), so the doors are push-to-open.
    return parts


def freestanding_tub(name, centre, m, props, length=1.70 * K, width=.80 * K, height=.58 * K):
    """Double-ended freestanding bath in white cast stone resin: a rounded
    superellipse plan lofted from a slightly tucked-in base to a rolled rim,
    with the bowl lofted down inside it (sections in K x real size)."""
    cx, cy, z0 = centre
    pts, norms = _superellipse(length / 2, width / 2, 2.6)

    def ring(d, z):
        return [(cx + x - nx * d * K, cy + y - ny * d * K, z0 + z * K) for (x, y), (nx, ny) in zip(pts, norms)]

    h = height / K
    profile = [(.075, 0.0), (.055, .025), (.028, .12), (.009, .30), (.0, .47), (.0, h - .02),
               (.004, h - .003), (.017, h + .004), (.030, h - .004),
               (.036, h - .03), (.048, .44), (.075, .30), (.125, .17), (.185, .10), (.225, .082)]
    tub = ring_mesh(name, [ring(d, z) for d, z in profile], m['tub'], props)
    cylinder(f'{name} waste', (cx + length * .28, cy, z0 + .084 * K), .028 * K, .004 * K, m['black_metal'], props=props)
    return tub


def floor_tub_filler(name, base, m, props, towards=(-1, 0)):
    """Floor-standing bath mixer in black steel: riser and spout over the rim."""
    bx, by, bz = base
    blk = m['black_metal']
    cylinder(f'{name} floor rose', (bx, by, bz + .006 * K), .045 * K, .012 * K, blk, props=props)
    cylinder(f'{name} riser', (bx, by, bz + .46 * K), .016 * K, .90 * K, blk, props=props)
    dx, dy = towards
    reach = .22 * K
    if dx:
        cylinder(f'{name} spout arm', (bx + dx * reach / 2, by, bz + .90 * K), .013 * K, reach, blk, axis='X', props=props)
    else:
        cylinder(f'{name} spout arm', (bx, by + dy * reach / 2, bz + .90 * K), .013 * K, reach, blk, axis='Y', props=props)
    cylinder(f'{name} spout tip', (bx + dx * reach, by + dy * reach, bz + .875 * K), .013 * K, .05 * K, blk, props=props)
    cylinder(f'{name} handle', (bx, by, bz + .80 * K), .022 * K, .05 * K, blk, props=props)


def wall_vanity(name, x0, x1, wall_y, m, props):
    """Wall-hung oak vanity (floor visible beneath it), oak top, round
    ceramic vessel basin, wall spout and a round mirror above."""
    d, ztop, zbot = .46 * K, FLOOR_Z + .85 * K, FLOOR_Z + .42 * K
    box(f'{name} carcass', (x0, wall_y, zbot), (x1, wall_y + d, ztop - .03 * K), m['oak'], .002 * K, props)
    box(f'{name} drawer reveal', (x0 + .01 * K, wall_y + d - .002, zbot + .22 * K), (x1 - .01 * K, wall_y + d + .0008, zbot + .226 * K),
        m['grout_dark'], 0, props)
    box(f'{name} top', (x0 - .01 * K, wall_y, ztop - .03 * K), (x1 + .01 * K, wall_y + d + .01 * K, ztop), m['oak'], .003 * K, props)
    bx, by = (x0 + x1) / 2 + .08 * K, wall_y + d / 2 + .02 * K
    lathe(f'{name} basin', (bx, by, ztop),
          [(r * K, z * K) for r, z in [(.0, .012), (.09, .014), (.155, .045), (.185, .10), (.193, .135), (.196, .145),
                                       (.205, .14), (.203, .10), (.185, .045), (.13, .008), (.10, .0)]],
          m['ceramic'], props)
    sz = ztop + .30 * K
    cylinder(f'{name} wall spout', (bx, wall_y + .10 * K, sz), .011 * K, .20 * K, m['black_metal'], axis='Y', props=props)
    cylinder(f'{name} spout rose', (bx, wall_y + .004 * K, sz), .03 * K, .008 * K, m['black_metal'], axis='Y', props=props)
    cylinder(f'{name} mixer', (bx + .16 * K, wall_y + .02 * K, sz), .022 * K, .04 * K, m['black_metal'], axis='Y', props=props)
    mx = (x0 + x1) / 2
    cylinder(f'{name} mirror frame', (mx, wall_y + .010 * K, FLOOR_Z + 1.60 * K), .335 * K, .020 * K, m['black_metal'], axis='Y', verts=96, props=props)
    cylinder(f'{name} mirror', (mx, wall_y + .021 * K, FLOOR_Z + 1.60 * K), .325 * K, .004 * K, m['mirror'], axis='Y', verts=96, props=props)
