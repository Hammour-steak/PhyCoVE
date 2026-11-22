"""Current look of book_pillow_bedroom: a real bedroom lit by afternoon sun through a side window.

Called by appearance/render.py after the frozen kit has built the bed, quilt, pillow and books.
It never touches a pose, a shape key or cache data (render.py checks every non-light transform and
the camera afterwards, then audits the book pose, the quilt binding and the contact gaps).

What it does:
* runs the frozen photographed-cloth finish of the kit (it pins each cloth vertex's rest
  position as an attribute, so textures stay attached to the deforming quilt and pillow), then
* replaces the hidden studio lights and the interior HDRI with a closed room (painted plaster walls,
  ceiling, white skirting, a window in the left wall) lit only by a sun lamp and a physical sky
  seen through that window, with camera white balance for that light;
* dresses the bedding as real cloth (bedding_cloth): scanned linen (quilt) and cotton (sheet,
  pillowcase) weaves at their true scale, slubs and mottling, three layers of soft wrinkles, matte
  sheen; topstitching beside the pillowcase welt (pillow_seam); normals and colour only;
* re-dresses the headboard in scanned wool herringbone with fabric-covered buttons seated in the
  tufts, and the walls in a scanned plaster painted warm white;
* replaces the box-built bedside cabinet and lathe lamp with a scanned oak side table, a potted
  succulent and a ceramic jug;
* removes the printed titles and border from both books (plain cloth covers, no lettering);
* sets Cycles for production (render_settings): motion blur, OIDN, fixed seed, no compositing.
"""
from pathlib import Path
import hashlib
import json
import math
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import lookdev_albedo  # frozen kit module: photographed cloth/wood finish with its albedo corrections
from pcve_assets import asset

HERE = Path(__file__).resolve().parent
SAMPLES = 512

# Room: the bed head stands against the back wall (inner face y = 1.22); the camera looks in from
# the front right. The left wall is close enough to show as a narrow corner strip at the frame edge.
LEFT_WALL_X = -1.70
RIGHT_WALL_X = 2.45
FRONT_WALL_Y = -2.70
BACK_WALL_Y = 1.22
CEILING_Z = 2.70
WINDOW = dict(y=(-1.45, 0.35), z=(0.80, 2.30))   # opening in the left wall, out of frame
SUN = dict(elevation_deg=40.0, azimuth_deg=20.0, strength=3.0, angle_deg=0.6, kelvin=5200)
SKY_STRENGTH = 1.0
EXPOSURE = 1.7
SHUTTER = 0.25            # fraction of a frame (1/96 s at 24 fps)
WHITE_BALANCE_K = 9000    # camera white balance for window light in a white room
WHITE_BALANCE_TINT = 22.0  # towards magenta: sky light through the window otherwise reads green-grey on white cloth
WALL_TINT = (.93, .88, .80)   # warm white paint over the neutralised plaster scan
VIEW_LOOK = 'AgX - Medium High Contrast'

# Static props on the side table (all inside the left 30 % of the frame, far from the falling book).
SIDE_TABLE = dict(xy=(-1.24, 0.60), rot_z_deg=90.0)

# Bedding cloth: tint, weave bump, slub/mottle amplitude and wrinkle bumps (coarse, medium, fine).
CLOTH = dict(duvet=dict(tint=(.62, .57, .49), weave=.9, slub=.22, mottle=.07, wrinkles=(.8, .8, .6)),
             cotton=dict(tint=(.80, .79, .76), weave=.6, slub=.07, mottle=.05, wrinkles=(.5, .6, .45)))
DEV_ZOOM = None   # look development only: [percent, x0, x1, y0, y1] render border at a higher resolution
TEXTURE_SIZE_M = {'poly_wool_herringbone': .270, 'stretch_poplin': .286, 'plastered_wall_04': 3.2}

# Look-development override (JSON object of the constants above); never set for delivered renders,
# and recorded in render_report.json when it is.
_DEV = json.loads(os.environ.get('BOOK_PILLOW_LOOKDEV', '{}'))
for _k, _v in _DEV.items():
    if _k not in {'WINDOW', 'SUN', 'SKY_STRENGTH', 'EXPOSURE', 'WHITE_BALANCE_K', 'WHITE_BALANCE_TINT', 'VIEW_LOOK',
                  'CLOTH', 'SHUTTER', 'WALL_TINT', 'DEV_ZOOM'}:
        raise KeyError(_k)
    globals()[_k] = {**globals()[_k], **_v} if isinstance(_v, dict) and isinstance(globals()[_k], dict) else _v


# ----------------------------------------------------------------------------------------- helpers
def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')


def world_bbox(objects):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objects if o.type == 'MESH' for c in o.bound_box]
    return (Vector([min(p[i] for p in pts) for i in range(3)]),
            Vector([max(p[i] for p in pts) for i in range(3)]))


def box(name, lo, hi, mat, bevel=.0):
    lo, hi = Vector(lo), Vector(hi)
    bpy.ops.mesh.primitive_cube_add(location=(lo + hi) / 2)
    o = bpy.context.object
    o.name = name
    o.scale = (hi - lo) / 2
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        m = o.modifiers.new('edge', 'BEVEL'); m.width = bevel; m.segments = 3
    o.data.materials.append(mat)
    return o


def image_node(nodes, links, path, vector, noncolor=False, projection='FLAT'):
    t = nodes.new('ShaderNodeTexImage')
    t.image = bpy.data.images.load(str(path), check_existing=True)
    if noncolor:
        t.image.colorspace_settings.name = 'Non-Color'
    t.projection = projection
    if projection == 'BOX':
        t.projection_blend = .2
    t.interpolation = 'Linear'
    links.new(vector, t.inputs['Vector'])
    return t


def scanned(mat, folder, size_m, tint, coords='rest', rough=(None, None), bump=.35,
            bump_distance=.0004, sheen=0.0, saturation=1.0, value=1.0):
    """Rebuild `mat` from a scanned Poly Haven PBR set (diffuse, roughness, displacement).

    coords='rest' reads the per-vertex rest position the frozen cloth finish pinned on deforming
    cloth (metres), so the weave stays attached to the fabric; 'object' uses object coordinates.
    """
    root = asset('polyhaven/' + folder)
    name = folder
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    links.new(bsdf.outputs[0], out.inputs['Surface'])
    if coords == 'rest':
        src = nodes.new('ShaderNodeAttribute'); src.attribute_name = 'rest_position_m'; vec = src.outputs['Vector']
    else:
        src = nodes.new('ShaderNodeTexCoord'); vec = src.outputs['Object']
    scale = nodes.new('ShaderNodeVectorMath'); scale.operation = 'SCALE'
    scale.inputs['Scale'].default_value = 1 / size_m
    links.new(vec, scale.inputs[0])
    uv = scale.outputs[0]
    diff = image_node(nodes, links, root / f'{name}_diff_2k.jpg', uv, projection='BOX')
    hsv = nodes.new('ShaderNodeHueSaturation')
    hsv.inputs['Saturation'].default_value = saturation
    hsv.inputs['Value'].default_value = value
    links.new(diff.outputs['Color'], hsv.inputs['Color'])
    mix = nodes.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'; mix.inputs[0].default_value = 1
    mix.inputs[2].default_value = (*tint, 1)
    links.new(hsv.outputs['Color'], mix.inputs[1])
    links.new(mix.outputs[0], bsdf.inputs['Base Color'])
    r = image_node(nodes, links, root / f'{name}_rough_2k.jpg', uv, True, 'BOX')
    if rough[0] is None:
        links.new(r.outputs['Color'], bsdf.inputs['Roughness'])
    else:
        mr = nodes.new('ShaderNodeMapRange')
        mr.inputs['To Min'].default_value, mr.inputs['To Max'].default_value = rough
        links.new(r.outputs['Color'], mr.inputs['Value'])
        links.new(mr.outputs['Result'], bsdf.inputs['Roughness'])
    h = image_node(nodes, links, root / f'{name}_disp_2k.png', uv, True, 'BOX')
    b = nodes.new('ShaderNodeBump')
    b.inputs['Strength'].default_value = bump
    b.inputs['Distance'].default_value = bump_distance
    links.new(h.outputs['Color'], b.inputs['Height'])
    links.new(b.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Sheen Weight'].default_value = sheen
    bsdf.inputs['Sheen Roughness'].default_value = .6
    bsdf.inputs['Specular IOR Level'].default_value = .35
    return mat


def paint(name, color, rough=.45):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = principled(m)
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    return m


def import_gltf(folder, name):
    path = asset('polyhaven/' + folder) / f'{folder}_2k.gltf'
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    bpy.context.view_layer.update()
    return root, [o for o in new if o.type == 'MESH']


def place_on(root, meshes, xy, z, rot_z_deg=0.0):
    """Rotate about z, then put the lowest point at height z and the footprint centre at xy."""
    root.rotation_euler = (0, 0, math.radians(rot_z_deg))
    bpy.context.view_layer.update()
    lo, hi = world_bbox(meshes)
    root.location += Vector((xy[0] - (lo.x + hi.x) / 2, xy[1] - (lo.y + hi.y) / 2, z - lo.z))
    bpy.context.view_layer.update()
    return world_bbox(meshes)


def clearance(meshes, others, frames):
    """Smallest distance from any prop vertex to the evaluated `others` at the given frames (m)."""
    scene = bpy.context.scene
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    best, where = 1e9, None
    for f in frames:
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        for other in others:
            ev = other.evaluated_get(deps)
            mesh = ev.to_mesh()
            tree = BVHTree.FromPolygons([other.matrix_world @ v.co for v in mesh.vertices],
                                        [tuple(p.vertices) for p in mesh.polygons])
            ev.to_mesh_clear()
            for p in points:
                hit = tree.find_nearest(p)
                if hit[0] is not None and hit[3] < best:
                    best, where = hit[3], (f, other.name, [round(v, 3) for v in p])
    scene.frame_set(1)
    return best, where


def remove(names):
    gone = []
    for o in list(bpy.context.scene.objects):
        if any(o.name == n or o.name.startswith(n + '.') for n in names):
            gone.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    return sorted(gone)


def bedding_cloth(mat, kind, files, weave_size_m):
    """Matte cotton/linen bedding: a scanned weave at its true scale, slubs and mottling, and three
    layers of soft elongated wrinkles. Everything reads the rest position the frozen cloth finish
    pinned on the cloth (metres), so nothing swims on the deforming quilt and pillow; only shading
    normals change, the simulated mesh is untouched. `files` = (diffuse, roughness, height) paths."""
    c = CLOTH[kind]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    links.new(bsdf.outputs[0], out.inputs['Surface'])
    rest = nodes.new('ShaderNodeAttribute'); rest.attribute_name = 'rest_position_m'
    uv = nodes.new('ShaderNodeVectorMath'); uv.operation = 'SCALE'; uv.inputs['Scale'].default_value = 1 / weave_size_m
    links.new(rest.outputs['Vector'], uv.inputs[0])
    diff = image_node(nodes, links, files[0], uv.outputs[0], projection='BOX')
    grey = nodes.new('ShaderNodeRGBToBW'); links.new(diff.outputs['Color'], grey.inputs[0])
    # Weave luminance mapped around 1: the tint sets the albedo, the scan only adds yarn contrast.
    norm = nodes.new('ShaderNodeMapRange')
    norm.inputs['To Min'].default_value, norm.inputs['To Max'].default_value = .82, 1.12
    links.new(grey.outputs[0], norm.inputs['Value'])

    def stretched(scale, ratio, angle_deg, detail=3.0):
        m = nodes.new('ShaderNodeMapping')
        m.inputs['Rotation'].default_value = (0, 0, math.radians(angle_deg))
        m.inputs['Scale'].default_value = (scale, scale * ratio, scale)
        links.new(rest.outputs['Vector'], m.inputs['Vector'])
        n = nodes.new('ShaderNodeTexNoise'); n.noise_dimensions = '3D'
        n.inputs['Scale'].default_value = 1.0; n.inputs['Detail'].default_value = detail
        n.inputs['Roughness'].default_value = .5; n.inputs['Distortion'].default_value = .25
        links.new(m.outputs['Vector'], n.inputs['Vector'])
        return n.outputs['Fac']

    # Slubs: short thick yarns along warp and weft (about 3 mm by 5 cm), and blotchy dye mottling.
    slub = nodes.new('ShaderNodeMath'); slub.operation = 'MAXIMUM'
    links.new(stretched(300, .06, 0), slub.inputs[0]); links.new(stretched(300, .06, 90), slub.inputs[1])
    slub_c = nodes.new('ShaderNodeMapRange')
    slub_c.inputs['From Min'].default_value, slub_c.inputs['From Max'].default_value = .55, .8
    slub_c.inputs['To Min'].default_value, slub_c.inputs['To Max'].default_value = 1.0, 1.0 + c['slub']
    links.new(slub.outputs[0], slub_c.inputs['Value'])
    mottle = nodes.new('ShaderNodeMapRange')
    mottle.inputs['To Min'].default_value, mottle.inputs['To Max'].default_value = 1.0 - c['mottle'], 1.0 + c['mottle']
    links.new(stretched(60, 1.0, 0, 4.0), mottle.inputs['Value'])
    shade = nodes.new('ShaderNodeMath'); shade.operation = 'MULTIPLY'
    links.new(norm.outputs['Result'], shade.inputs[0]); links.new(mottle.outputs['Result'], shade.inputs[1])
    heather = nodes.new('ShaderNodeMapRange')   # uneven yarn colour at the millimetre scale
    heather.inputs['To Min'].default_value, heather.inputs['To Max'].default_value = 1.0 - c['mottle'] * .6, 1.0 + c['mottle'] * .6
    links.new(stretched(900, 1.0, 0, 2.0), heather.inputs['Value'])
    shade1 = nodes.new('ShaderNodeMath'); shade1.operation = 'MULTIPLY'
    links.new(shade.outputs[0], shade1.inputs[0]); links.new(heather.outputs['Result'], shade1.inputs[1])
    shade2 = nodes.new('ShaderNodeMath'); shade2.operation = 'MULTIPLY'
    links.new(shade1.outputs[0], shade2.inputs[0]); links.new(slub_c.outputs['Result'], shade2.inputs[1])
    col = nodes.new('ShaderNodeMixRGB'); col.blend_type = 'MULTIPLY'; col.inputs[0].default_value = 1
    col.inputs[1].default_value = (*c['tint'], 1)
    links.new(shade2.outputs[0], col.inputs[2])
    links.new(col.outputs[0], bsdf.inputs['Base Color'])
    rough = image_node(nodes, links, files[1], uv.outputs[0], True, 'BOX')
    rr = nodes.new('ShaderNodeMapRange')
    rr.inputs['To Min'].default_value, rr.inputs['To Max'].default_value = .86, .98
    links.new(rough.outputs['Color'], rr.inputs['Value']); links.new(rr.outputs['Result'], bsdf.inputs['Roughness'])
    bsdf.inputs['Specular IOR Level'].default_value = .22
    bsdf.inputs['Sheen Weight'].default_value = .55
    bsdf.inputs['Sheen Roughness'].default_value = .45
    # Normal chain: wrinkles (about 5 cm, 1.6 cm, 6 mm), slubs, then the scanned weave height on top.
    normal = None
    for (scale, ratio, angle, distance), strength in zip(((20, 3.0, 25, .012), (60, 2.5, -55, .002), (160, 2.0, 70, .0006)),
                                                         c['wrinkles']):
        b = nodes.new('ShaderNodeBump'); b.inputs['Strength'].default_value = strength; b.inputs['Distance'].default_value = distance
        links.new(stretched(scale, ratio, angle), b.inputs['Height'])
        if normal is not None:
            links.new(normal, b.inputs['Normal'])
        normal = b.outputs['Normal']
    bs = nodes.new('ShaderNodeBump'); bs.inputs['Strength'].default_value = c['slub'] * 2
    bs.inputs['Distance'].default_value = .0003
    links.new(slub.outputs[0], bs.inputs['Height']); links.new(normal, bs.inputs['Normal'])
    height = image_node(nodes, links, files[2], uv.outputs[0], True, 'BOX')
    bw = nodes.new('ShaderNodeBump'); bw.inputs['Strength'].default_value = c['weave']; bw.inputs['Distance'].default_value = .0004
    links.new(height.outputs['Color'], bw.inputs['Height']); links.new(bs.outputs['Normal'], bw.inputs['Normal'])
    links.new(bw.outputs['Normal'], bsdf.inputs['Normal'])
    return bsdf


def pillow_seam(scene, body):
    """Topstitching beside the welt of the pillowcase (a vertex attribute plus shading).

    The pillow mesh has a welt: a ring of sharp folds about 6.5 cm inside its outline (rest shape),
    found as edges whose two faces meet at more than 50 degrees 4.5-8.5 cm inside the bounding
    rectangle. Its inset is taken per 5-degree sector around the pillow (median, then smoothed), so
    the stitch line is one smooth loop 5 mm outside the welt, parallel to the edge like real
    topstitching; each vertex stores its inset relative to that loop."""
    from mathutils.kdtree import KDTree
    pillow = scene.objects.get('Sleeping_Pillow')
    if pillow is None:
        return 0
    mesh = pillow.data
    rest = mesh.attributes['rest_position_m'].data
    co = [Vector(rest[i].vector) for i in range(len(mesh.vertices))]
    xs, ys = [p.x for p in co], [p.y for p in co]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    hx, hy = (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2
    inset = [min(hx - abs(p.x - cx), hy - abs(p.y - cy)) for p in co]
    normals = []
    for poly in mesh.polygons:
        pts = [co[v] for v in poly.vertices]
        n = Vector((0, 0, 0))
        for i, a in enumerate(pts):
            n += a.cross(pts[(i + 1) % len(pts)])
        normals.append(n.normalized())
    faces = {}
    for poly in mesh.polygons:
        for key in poly.edge_keys:
            faces.setdefault(key, []).append(poly.index)
    ring = set()
    for (u, v), f in faces.items():
        if len(f) == 2 and normals[f[0]].angle(normals[f[1]], 0.0) > math.radians(50) \
                and .045 < inset[u] < .085 and .045 < inset[v] < .085:
            ring.update((u, v))
    ring = sorted(ring)
    if not ring:
        return 0

    def sector(p):
        return int((math.degrees(math.atan2((p.y - cy) / hy, (p.x - cx) / hx)) % 360) // 5)

    bins = [[] for _ in range(72)]
    for v in ring:
        bins[sector(co[v])].append(inset[v])
    med = [sorted(b)[len(b) // 2] if b else None for b in bins]
    known = [i for i, m in enumerate(med) if m is not None]
    for i in range(72):                      # fill empty sectors from the nearest known ones
        if med[i] is None:
            med[i] = med[min(known, key=lambda k: min(abs(k - i), 72 - abs(k - i)))]
    welt = [sum(med[(i + k) % 72] for k in range(-3, 4)) / 7 for i in range(72)]

    def welt_at(p):                          # linear between sector centres: no steps in the loop
        t = (math.degrees(math.atan2((p.y - cy) / hy, (p.x - cx) / hx)) % 360) / 5 - .5
        i = math.floor(t)
        return welt[i % 72] * (1 - (t - i)) + welt[(i + 1) % 72] * (t - i)

    signed = [inset[i] - welt_at(p) for i, p in enumerate(co)]
    attr = mesh.attributes.get('seam_d_m') or mesh.attributes.new('seam_d_m', 'FLOAT', 'POINT')
    attr.data.foreach_set('value', signed)
    # Stitching lies on the flat faces of the case only: fade it out where the rest surface turns
    # steep (folds of the flange), where an inset line would otherwise cross the fold.
    vn = [Vector((0, 0, 0)) for _ in co]
    for poly, n in zip(mesh.polygons, normals):
        for v in poly.vertices:
            vn[v] += n
    flat = [min(1.0, max(0.0, (abs(n.normalized().z) - .25) / .2)) for n in vn]
    mask = mesh.attributes.get('seam_flat') or mesh.attributes.new('seam_flat', 'FLOAT', 'POINT')
    mask.data.foreach_set('value', flat)
    nodes, links = body.node_tree.nodes, body.node_tree.links
    bsdf = principled(body)
    top = bsdf.inputs['Normal'].links[0].from_node
    d = nodes.new('ShaderNodeAttribute'); d.attribute_name = 'seam_d_m'
    sub = nodes.new('ShaderNodeMath'); sub.operation = 'ADD'; sub.inputs[1].default_value = .005
    dist = nodes.new('ShaderNodeMath'); dist.operation = 'ABSOLUTE'
    links.new(d.outputs['Fac'], sub.inputs[0]); links.new(sub.outputs[0], dist.inputs[0])
    # 1.2 mm groove centred 5 mm outside the welt: 1 on the stitch line, 0 elsewhere.
    line = nodes.new('ShaderNodeMapRange'); line.interpolation_type = 'SMOOTHSTEP'
    line.inputs['From Min'].default_value, line.inputs['From Max'].default_value = .0006, .0002
    links.new(dist.outputs[0], line.inputs['Value'])
    fl = nodes.new('ShaderNodeAttribute'); fl.attribute_name = 'seam_flat'
    line_on = nodes.new('ShaderNodeMath'); line_on.operation = 'MULTIPLY'
    links.new(line.outputs['Result'], line_on.inputs[0]); links.new(fl.outputs['Fac'], line_on.inputs[1])
    # Stitches: 2 mm thread, 2 mm gap along the seam.
    r = nodes.new('ShaderNodeAttribute'); r.attribute_name = 'rest_position_m'
    sep = nodes.new('ShaderNodeSeparateXYZ'); links.new(r.outputs['Vector'], sep.inputs[0])
    add = nodes.new('ShaderNodeMath'); add.operation = 'ADD'
    links.new(sep.outputs['X'], add.inputs[0]); links.new(sep.outputs['Y'], add.inputs[1])
    k = nodes.new('ShaderNodeMath'); k.operation = 'MULTIPLY'; k.inputs[1].default_value = 2 * math.pi / .004
    wave = nodes.new('ShaderNodeMath'); wave.operation = 'SINE'
    links.new(add.outputs[0], k.inputs[0]); links.new(k.outputs[0], wave.inputs[0])
    dash = nodes.new('ShaderNodeMapRange')
    dash.inputs['From Min'].default_value, dash.inputs['From Max'].default_value = -.2, .2
    links.new(wave.outputs[0], dash.inputs['Value'])
    stitch = nodes.new('ShaderNodeMath'); stitch.operation = 'MULTIPLY'
    links.new(line_on.outputs[0], stitch.inputs[0]); links.new(dash.outputs['Result'], stitch.inputs[1])
    groove = nodes.new('ShaderNodeMath'); groove.operation = 'MULTIPLY_ADD'; groove.inputs[1].default_value = .6
    links.new(line_on.outputs[0], groove.inputs[0]); links.new(stitch.outputs[0], groove.inputs[2])
    neg = nodes.new('ShaderNodeMath'); neg.operation = 'MULTIPLY'; neg.inputs[1].default_value = -1
    links.new(groove.outputs[0], neg.inputs[0])
    b = nodes.new('ShaderNodeBump'); b.inputs['Strength'].default_value = .8; b.inputs['Distance'].default_value = .0006
    links.new(neg.outputs[0], b.inputs['Height']); links.new(top.outputs['Normal'], b.inputs['Normal'])
    links.new(b.outputs['Normal'], bsdf.inputs['Normal'])
    base = bsdf.inputs['Base Color'].links[0].from_socket
    dark = nodes.new('ShaderNodeMixRGB'); dark.blend_type = 'MULTIPLY'
    dark.inputs[2].default_value = (.80, .79, .77, 1)
    links.new(line_on.outputs[0], dark.inputs[0]); links.new(base, dark.inputs[1])
    links.new(dark.outputs[0], bsdf.inputs['Base Color'])
    return len(ring)


def headboard_buttons(scene, upholstery):
    """Buttons covered in the headboard fabric, one per tuft. The artist's tufts are narrow funnels
    (the upholstery is 22 mm proud of the deepest point 10 mm away), so each dome rests in the funnel
    mouth with its face just clear of the fabric, the way a real button is pulled into its tuft."""
    from mathutils.kdtree import KDTree
    hb = scene.objects['Plane.008']
    M = hb.matrix_world; R = M.to_3x3()
    # Tufted field only: inside the piped border, above the mattress.
    front = [p for p in ((M @ v.co) for v in hb.data.vertices if (R @ v.normal).normalized().y < -.6)
             if abs(p.x) < .74 and .45 < p.z < .92]   # rows below the mattress top are hidden by the bed
    tree = KDTree(len(front))
    for i, p in enumerate(front):
        tree.insert(p, i)
    tree.balance()
    hollows = []
    for p in front:
        near = tree.find_range(p, .06)
        if all(q[0].y <= p.y + 1e-6 for q in near) and p.y - min(q[0].y for q in near) > .008:
            if not any((p - h).length < .06 for h in hollows):
                hollows.append(p.copy())
    radius, half_depth = .010, .0055
    every = [M @ v.co for v in hb.data.vertices]   # including the steep walls of the pinch
    whole = KDTree(len(every))
    for i, q in enumerate(every):
        whole.insert(q, i)
    whole.balance()
    seated = []
    for p in hollows:
        # Seat the dome in the dimple: as far back as possible while its whole face stays 0.5 mm in
        # front of the upholstery within its radius (otherwise the pinched fabric swallows it).
        limits = []
        for q, _, _ in whole.find_range(p, radius + .03):
            r = math.hypot(q.x - p.x, q.z - p.z)
            if r < radius and q.y < p.y + .002:   # front skin only, not the back of the panel
                limits.append(q.y - .0005 + half_depth * math.sqrt(1 - (r / radius) ** 2))
        y = min(limits) if limits else p.y
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius, location=(p.x, y, p.z))
        o = bpy.context.object; o.name = 'Headboard_Button'; o.scale = (1, half_depth / radius, 1)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        o.data.materials.append(upholstery)   # same scanned fabric, read at the button's own position
        rest = o.data.attributes.new('rest_position_m', 'FLOAT_VECTOR', 'POINT')
        rest.data.foreach_set('vector', [c for v in o.data.vertices for c in (o.matrix_world @ v.co)])
        bpy.ops.object.shade_smooth()
        seated.append(round((p.y - (y - half_depth)) * 1000, 1))
    return [[round(v, 3) for v in p] for p in hollows], seated


# -------------------------------------------------------------------------------------------- look
def room(walls, skirting, frame_paint):
    """Closed room around the existing back wall, with a window opening in the left wall."""
    t = .10
    made = []
    y0, y1 = WINDOW['y']; z0, z1 = WINDOW['z']
    x0, x1 = LEFT_WALL_X - t, LEFT_WALL_X
    # Left wall in four pieces around the opening.
    made += [box('Room_Left_Wall', (x0, FRONT_WALL_Y, 0), (x1, y0, CEILING_Z), walls),
             box('Room_Left_Wall', (x0, y1, 0), (x1, BACK_WALL_Y + .06, CEILING_Z), walls),
             box('Room_Left_Wall', (x0, y0, 0), (x1, y1, z0), walls),
             box('Room_Left_Wall', (x0, y0, z1), (x1, y1, CEILING_Z), walls)]
    made += [box('Room_Right_Wall', (RIGHT_WALL_X, FRONT_WALL_Y, 0), (RIGHT_WALL_X + t, BACK_WALL_Y + .06, CEILING_Z), walls),
             box('Room_Front_Wall', (x0, FRONT_WALL_Y - t, 0), (RIGHT_WALL_X + t, FRONT_WALL_Y, CEILING_Z), walls),
             box('Room_Ceiling', (x0, FRONT_WALL_Y - t, CEILING_Z), (RIGHT_WALL_X + t, BACK_WALL_Y + .06, CEILING_Z + t), walls),
             box('Room_Subfloor', (x0, FRONT_WALL_Y - t, -.02), (RIGHT_WALL_X + t, BACK_WALL_Y + .06, .0), skirting)]
    # Painted window frame: jambs, head, sill and one vertical mullion (casts a soft line of shadow).
    d, w = .07, .05
    made += [box('Window_Frame', (x1 - d, y0, z0), (x1, y0 + w, z1), frame_paint, .003),
             box('Window_Frame', (x1 - d, y1 - w, z0), (x1, y1, z1), frame_paint, .003),
             box('Window_Frame', (x1 - d, y0, z1 - w), (x1, y1, z1), frame_paint, .003),
             box('Window_Frame', (x1 - d, y0 - .03, z0 - .03), (x1 + .04, y1 + .03, z0), frame_paint, .003),
             box('Window_Frame', (x1 - d, (y0 + y1) / 2 - .025, z0), (x1 - .02, (y0 + y1) / 2 + .025, z1), frame_paint, .003)]
    # White skirting on the left wall, matching the back-wall skirting.
    made.append(box('Room_Left_Skirting', (x1, FRONT_WALL_Y, 0), (x1 + .018, BACK_WALL_Y, .11), skirting, .003))
    return made


def daylight(scene):
    """Sun lamp plus a physical sky; the room is lit only through the window."""
    el, az = math.radians(SUN['elevation_deg']), math.radians(SUN['azimuth_deg'])
    # Direction of travel of sunlight: into the room through the left wall (+x), slightly towards the back wall.
    travel = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), -math.sin(el)))
    data = bpy.data.lights.new('Afternoon_Sun', 'SUN')
    data.energy = SUN['strength']
    data.angle = math.radians(SUN['angle_deg'])
    data.use_nodes = True
    bb = data.node_tree.nodes.new('ShaderNodeBlackbody'); bb.inputs['Temperature'].default_value = SUN['kelvin']
    data.node_tree.links.new(bb.outputs[0], data.node_tree.nodes['Emission'].inputs['Color'])
    sun = bpy.data.objects.new('Afternoon_Sun', data)
    scene.collection.objects.link(sun)
    sun.rotation_mode = 'QUATERNION'
    sun.rotation_quaternion = travel.to_track_quat('-Z', 'Y')
    world = bpy.data.worlds.new('Afternoon_Sky'); world.use_nodes = True; scene.world = world
    n, l = world.node_tree.nodes, world.node_tree.links
    n.clear()
    sky = n.new('ShaderNodeTexSky'); sky.sky_type = 'NISHITA'; sky.sun_disc = False
    sky.sun_elevation = el
    sky.sun_rotation = math.atan2(-travel.y, -travel.x) - math.pi / 2  # Nishita rotation is measured from +y
    sky.altitude = 200; sky.air_density = 1.2; sky.dust_density = 2.0; sky.ozone_density = 1.0
    bg = n.new('ShaderNodeBackground'); bg.inputs['Strength'].default_value = SKY_STRENGTH
    out = n.new('ShaderNodeOutputWorld')
    l.new(sky.outputs['Color'], bg.inputs['Color']); l.new(bg.outputs[0], out.inputs['Surface'])
    # Sunlit paved courtyard outside the window: daylight entering a real room is sky plus ground bounce.
    box('Garden_Ground', (-40, -40, -.05), (LEFT_WALL_X - .12, 40, 0), paint('Paved_Courtyard', (.16, .15, .13), .9))
    return {'sun_travel_direction': [round(v, 4) for v in travel], **SUN, 'sky': 'Nishita, no sun disc',
            'sky_strength': SKY_STRENGTH}


def props(scene):
    """Scanned side table with a potted succulent and a ceramic jug, in place of the box cabinet and lamp."""
    floor_z = .03  # top of the existing floor planks
    table, table_meshes = import_gltf('side_table_01', 'Bedside_Table')
    lo, hi = place_on(table, table_meshes, SIDE_TABLE['xy'], floor_z, SIDE_TABLE['rot_z_deg'])
    top = hi.z
    plant, plant_meshes = import_gltf('potted_plant_04', 'Bedside_Succulent')
    place_on(plant, plant_meshes, (hi.x - .12, lo.y + .13), top, 15)
    jug, jug_meshes = import_gltf('ceramic_vase_04', 'Bedside_Jug')
    place_on(jug, jug_meshes, (lo.x + .12, hi.y - .16), top, -40)
    return {'table_bbox_m': [list(map(lambda v: round(v, 3), lo)), list(map(lambda v: round(v, 3), hi))],
            'table_top_m': round(top, 4)}, table_meshes + plant_meshes + jug_meshes


def apply(scene, assets, case):
    finish = lookdev_albedo.apply(assets / 'cloth_finish', scene)          # frozen photographed-cloth finish
    mats = bpy.data.materials

    # Lights and objects this look replaces.
    removed = remove(['Soft_Window', 'Soft_Reflected_Daylight', 'Point', 'Cabinet', 'Cabinet_Top', 'Cabinet_Leg',
                      'Drawer_Front', 'Drawer_Gap', 'Brass_Drawer_Pull', 'Handmade_Ceramic_Lamp', 'Linen_Shade',
                      'Cylinder'])
    # Plain cloth covers: no lettering on either book.
    for o in scene.objects:
        if o.type == 'FONT':
            o.hide_render = True

    # Scanned surfaces.
    walls = mats['Finish_Fine_Lime_Plaster']
    scanned(walls, 'plastered_wall_04', TEXTURE_SIZE_M['plastered_wall_04'], WALL_TINT, coords='object',
            rough=(.82, .95), bump=.18, bump_distance=.0015, saturation=0.0, value=1.45)
    skirting = paint('Warm_White_Skirting', (.70, .68, .63), .38)
    frame = paint('Painted_Window_Frame', (.72, .70, .66), .35)
    for name in ('Oak_Skirting',):
        o = scene.objects.get(name)
        if o: o.data.materials[0] = skirting
    scanned(mats['Finish_Woven_Taupe_Upholstery'], 'poly_wool_herringbone', TEXTURE_SIZE_M['poly_wool_herringbone'],
            (.62, .58, .53), rough=(.80, .96), bump=.45, bump_distance=.0006, sheen=.35, saturation=.35)
    # Bedding: washed linen quilt (the kit's scanned rough_linen, true 0.271 m tile, oatmeal), white cotton
    # sheet, pillowcase and piping (scanned stretch_poplin, true 0.286 m tile), stitched pillowcase seam.
    linen, poplin = assets / 'cloth_finish', asset('polyhaven/stretch_poplin')
    bedding_cloth(mats['Finish_Washed_Linen_Duvet'], 'duvet', (linen / 'rough_linen_diffuse_4k.jpg',
                  linen / 'rough_linen_roughness_4k.jpg', linen / 'rough_linen_height_4k.png'), .271)
    for name in ('Finish_Ivory_Cotton_Sheet', 'Finish_Grey_Sage_Cotton', 'Finish_Pillow_Piping'):
        bedding_cloth(mats[name], 'cotton', (poplin / 'stretch_poplin_diff_2k.jpg', poplin / 'stretch_poplin_rough_2k.jpg',
                      poplin / 'stretch_poplin_disp_2k.png'), TEXTURE_SIZE_M['stretch_poplin'])
    seam_vertices = pillow_seam(scene, mats['Finish_Grey_Sage_Cotton'])
    # Book cloth: same scanned linen weave, slightly lighter blue / warm brown, matte.
    for name, tint in (('Finish_Blue_Bookcloth', (.020, .080, .20)), ('Finish_Brown_Bookcloth', (.20, .095, .04))):
        m = mats.get(name)
        if m is None:
            continue
        for node in m.node_tree.nodes:
            if node.bl_idname == 'ShaderNodeMixRGB' and node.blend_type == 'MULTIPLY':
                node.inputs[2].default_value = (*tint, 1)

    made = room(walls, skirting, frame)
    buttons, proud = headboard_buttons(scene, mats['Finish_Woven_Taupe_Upholstery'])
    print('HEADBOARD_BUTTONS', len(buttons), 'dome front ahead of the deepest tuft point (mm)', proud, flush=True)
    light = daylight(scene)
    placed, prop_meshes = props(scene)
    # Props must stay clear of the bedding at the start and end of the clip.
    bedding = [o for o in scene.objects if o.type == 'MESH' and o.name in {'Cube.003', 'Plane.003', 'Plane.004'}]
    gap, where = clearance(prop_meshes, bedding, (1, 96))
    print('PROP_CLEARANCE', gap, where, placed, flush=True)
    if gap < .01:
        raise RuntimeError(f'Bedside props touch the bedding ({gap * 1000:.1f} mm at {where})')

    # Straight-line sub-frame motion of the books for the motion blur; keyed frame poses are unchanged.
    for name in ('Falling_Blue_Hardcover', 'Resting_Atlas'):
        o = scene.objects.get(name)
        if o is not None and o.animation_data and o.animation_data.action:
            for fc in o.animation_data.action.fcurves:
                for k in fc.keyframe_points:
                    k.interpolation = 'LINEAR'
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = VIEW_LOOK
    scene.view_settings.exposure = EXPOSURE
    scene.view_settings.use_white_balance = True
    scene.view_settings.white_balance_temperature = WHITE_BALANCE_K
    scene.view_settings.white_balance_tint = WHITE_BALANCE_TINT
    return {'look': 'daylight bedroom (2026-11-09)',
            'removed_objects': removed, 'room_objects': len(made), 'daylight': light, 'props': placed,
            'prop_bedding_clearance_m': round(gap, 4), 'book_titles_hidden': True, 'headboard_buttons': len(buttons), 'pillow_seam_edge_vertices': seam_vertices,
            'scanned_materials': {'walls': 'polyhaven/plastered_wall_04', 'headboard': 'polyhaven/poly_wool_herringbone',
                                  'sheet_and_pillowcase': 'polyhaven/stretch_poplin',
                                  'quilt_and_book_cloth': 'Poly Haven rough_linen (kit cloth_finish)',
                                  'floor': 'Poly Haven wood_table_001 (kit cloth_finish)',
                                  'cloth_detail': 'slubs, mottling and three wrinkle bumps on the rest position'},
            'exposure_ev': EXPOSURE, 'view': VIEW_LOOK, 'white_balance_k': WHITE_BALANCE_K, 'white_balance_tint': WHITE_BALANCE_TINT, 'motion_blur_shutter_frames': SHUTTER, 'wall_tint': WALL_TINT,
            'lookdev_override': _DEV or None}


def render_settings(scene, samples):
    c = scene.cycles
    c.samples = samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = .008
    c.adaptive_min_samples = 64
    c.max_bounces = 12; c.diffuse_bounces = 6; c.glossy_bounces = 4; c.transmission_bounces = 6
    c.sample_clamp_indirect = 8.0
    c.use_denoising = True
    c.denoiser = 'OPENIMAGEDENOISE'
    c.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    c.denoising_prefilter = 'ACCURATE'
    c.seed = 29; c.use_animated_seed = False
    scene.render.film_transparent = False
    # Camera-like motion blur on the falling book and the deforming bedding. Persistent data must be
    # off while motion blur is on (Blender 4.3 drops objects that come to rest in later frames).
    scene.render.use_motion_blur = SHUTTER > 0
    scene.render.motion_blur_shutter = SHUTTER
    scene.render.motion_blur_position = 'CENTER'
    scene.render.use_persistent_data = not scene.render.use_motion_blur
    if DEV_ZOOM:
        pct, x0, x1, y0, y1 = DEV_ZOOM
        scene.render.resolution_percentage = pct
        scene.render.use_border = True; scene.render.use_crop_to_border = True
        scene.render.border_min_x, scene.render.border_max_x = x0, x1
        scene.render.border_min_y, scene.render.border_max_y = y0, y1


def fingerprint():
    h = hashlib.sha256()
    for name in ('realism_look.py', 'render.py'):
        h.update((HERE / name).read_bytes())
    return h.hexdigest()[:16]


def probe(scene):
    bpy.context.view_layer.update()
    for o in sorted(scene.objects, key=lambda o: o.name):
        if o.type == 'MESH':
            lo, hi = world_bbox([o])
            print('OBJ', o.name, 'hide', o.hide_render, [round(v, 3) for v in lo], [round(v, 3) for v in hi],
                  [m.name for m in o.data.materials if m][:3])
        else:
            print('OBJ', o.name, o.type, tuple(round(v, 3) for v in o.matrix_world.translation))
