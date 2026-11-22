"""Current look: the handmade toy on an OSB workbench in a small home workshop.

A look module for render_scene.py: `apply()` runs once the toy, camera, render settings and ID-mask outputs
exist, so the native states, the camera, motion blur, every edit and the mask outputs stay those of the replay.
It replaces the replay's surroundings (BlenderKit farmhouse table and pencil, paper sketch with a handwritten
dimension, box offcuts, hidden area lights, room overlay) with:

* an oriented-strand-board bench top (Poly Haven `oriented_strand_board`, 2.51 m texture = real size) with
  handling wear, a few pencil layout lines and dust;
* daylight of a real small workshop (Poly Haven HDRI `small_workshop`, no lamps);
* the slider block in walnut (Poly Haven `walnut_veneer`; 36 g over 55 x 42 x 24 mm is 650 kg/m3, walnut's
  density) with darker end grain; guide, rails, clamp, pegs and band keep their replay geometry and materials;
* props of the job, all on the bench and outside the toy: a No. 4 hand plane on its side (Poly Haven
  `hand_plane_no4`), plane shavings, two offcuts, a carpenter's pencil without print, saw dust.

    blender -b --python-exit-code 1 --python appearance/realism.py -- --case source \
        --input <native case dir> --audit <capture_start_audit.json> --out OUT \
        [--frames 31] [--samples 256] [--width 1280] [--review-candidate --revision <name>_review] [--cpu]

Tuning for look development only (defaults are the published look): RBWS_HDRI_ROT (deg), RBWS_HDRI_STRENGTH,
RBWS_EXPOSURE.
"""
from pathlib import Path
import math
import os
import random
import sys

HERE = Path(__file__).resolve().parent
SCENE_DIR = HERE.parent
sys.path[:0] = [str(HERE), str(SCENE_DIR), str(HERE.parents[2])]
import pcve_realism_kit as kit  # noqa: E402
from pcve_assets import asset  # noqa: E402

# Everything that belongs to the toy (and therefore to the physics or its fixtures) is kept untouched.
TOY = ('six_mm_plywood_guide', 'handmade_guide_rail_', 'flush_small_brad', 'thin_glue_squeeze_out_', 'anchor_',
       'slider_', 'solid_wood_slider', 'low_wooden_pull_tab', 'added_stop_ear_', 'physical_closed_rubber_loop',
       'hand_pencil_measurement_tick_')
# Guide, rails, clamp, slider travel, band and the added stop, in every case (with a margin).
KEEPOUT = ((-.165, -.045, -.001), (.165, .045, .06))
HDRI = asset('polyhaven/small_workshop/small_workshop_4k.hdr')
HDRI_ROT = float(os.environ.get('RBWS_HDRI_ROT', '150'))
HDRI_STRENGTH = float(os.environ.get('RBWS_HDRI_STRENGTH', '0.8'))
EXPOSURE = float(os.environ.get('RBWS_EXPOSURE', '-0.6'))
ASSETS = {'oriented_strand_board': 2.51, 'walnut_veneer': 1.80}
# Plane footprint centre (x, y) and heading (deg).
PLANE = (.190, .150, 172.0)   # heel and tote towards the toy; the toe with its cast marks is beyond the frame
# Shavings lying on the bench: (kind, x, y, heading rad, width, length, radius, twist). 'roll': a thin ribbon rolled
# 1.5-2 turns, lying on its side (roll axis horizontal); 'flat': a short, gently wavy ribbon lying flat.
SHAVINGS = [('roll', -.062, .066, .35, .017, .085, .0048, .03),
            ('roll', -.004, .118, -.85, .021, .10, .0056, -.04),
            ('roll', .052, .060, 1.30, .011, .050, .0036, .05),
            ('flat', -.048, .150, .25, .015, .060, .020, .02),
            ('flat', .100, -.068, -1.70, .012, .045, .018, -.03)]
# Flattened small chips (x, y, size, heading rad): broken bits of shaving pressed flat.
CHIPS = [(.012, .074, .007, .4), (.078, .068, .005, 1.9), (-.026, .094, .006, -.7), (-.088, .128, .008, 2.6),
         (-.008, .070, .004, 1.1), (.163, -.058, .005, .2), (-.214, .060, .006, -1.4)]
# Late-afternoon sun through the workshop window on the left (azimuth: direction the light comes from).
SUN = {'azimuth_deg': 160.0, 'elevation_deg': 30.0, 'strength': float(os.environ.get('RBWS_SUN', '6.0')),
       'angle_deg': 1.2, 'color': (1.0, .91, .78)}
PENCIL = (-.095, -.068, 6.0)


def _bpy():
    import bpy
    return bpy


def bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def new_material(name, color, rough=.6, metal=0.0):
    bpy = _bpy()
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = bsdf(m)
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    return m


def scan_material(name, key, coords='UV', rotate=0.0, value=1.0, saturation=1.0, rough=(.45, .85), normal=.6,
                  offset=(0.0, 0.0)):
    """Poly Haven scan at its real size: 1 texture repeat = ASSETS[key] metres of the object's metre coordinates."""
    bpy = _bpy()
    m = new_material(name, (.5, .4, .3))
    n, l = m.node_tree.nodes, m.node_tree.links
    b = bsdf(m)
    tc = n.new('ShaderNodeTexCoord')
    mp = n.new('ShaderNodeMapping')
    size = ASSETS[key]
    mp.inputs['Scale'].default_value = (1 / size, 1 / size, 1 / size)
    mp.inputs['Rotation'].default_value[2] = rotate
    mp.inputs['Location'].default_value = (offset[0], offset[1], 0)
    l.new(tc.outputs[coords], mp.inputs['Vector'])
    folder = asset(f'polyhaven/{key}')
    images = {}
    for channel in ('diff', 'nor_gl', 'rough'):
        im = n.new('ShaderNodeTexImage')
        im.image = bpy.data.images.load(str(folder / f'{key}_{channel}_4k.jpg'), check_existing=True)
        if channel != 'diff':
            im.image.colorspace_settings.name = 'Non-Color'
        im.interpolation = 'Cubic'
        l.new(mp.outputs[0], im.inputs['Vector'])
        images[channel] = im
    hsv = n.new('ShaderNodeHueSaturation')
    hsv.inputs['Value'].default_value = value
    hsv.inputs['Saturation'].default_value = saturation
    l.new(images['diff'].outputs['Color'], hsv.inputs['Color'])
    l.new(hsv.outputs[0], b.inputs['Base Color'])
    rr = n.new('ShaderNodeMapRange')
    rr.inputs['To Min'].default_value, rr.inputs['To Max'].default_value = rough
    l.new(images['rough'].outputs['Color'], rr.inputs['Value'])
    l.new(rr.outputs[0], b.inputs['Roughness'])
    nm = n.new('ShaderNodeNormalMap')
    nm.inputs['Strength'].default_value = normal
    if coords == 'UV':
        nm.space = 'TANGENT'
    l.new(images['nor_gl'].outputs['Color'], nm.inputs['Color'])
    l.new(nm.outputs[0], b.inputs['Normal'])
    b.inputs['Specular IOR Level'].default_value = .45
    return m


def clear_surroundings(scene):
    """Remove the replay's table, pencil, sketch, offcuts, chips and lamps; keep the toy and the camera."""
    bpy = _bpy()
    removed = []
    for o in list(scene.objects):
        if o.type == 'CAMERA' or o.name.startswith(TOY):
            continue
        removed.append(o.name)
        bpy.data.objects.remove(o, do_unlink=True)
    return sorted(removed)


def bench(scene):
    """OSB bench top: 1.6 m x 0.9 m x 18 mm sheet on a 40 mm frame; top face at z = 0 (the toy's support)."""
    bpy = _bpy()
    import render_base as base
    osb = scan_material('osb_bench_top', 'oriented_strand_board', coords='UV', value=.92, saturation=.95,
                        rough=(.38, .78), normal=.9, offset=(.137, .412))
    kit.add_surface_wear(osb, smudge=.10, grime=.12, scratch=.05, scale=.45)
    # render_base.box: per-face UVs in metres, so the scan keeps its real size and tangent frame.
    top = base.box('osb_bench_top', (0, .08, -.009), (1.6, .9, .018), osb, .0015)
    frame = new_material('bench_frame_pine', (.42, .30, .17), .7)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, .08, -.038))
    rail = bpy.context.object
    rail.name = 'bench_frame'
    rail.dimensions = (1.56, .86, .04)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    rail.data.materials.append(frame)
    # Layout lines from earlier jobs: faint graphite, none crossing the toy.
    graphite = new_material('graphite_layout_lines', (.05, .05, .052), .55)
    rng = random.Random(11)
    lines = [((-.30, .135), (-.12, .142)), ((-.27, .118), (-.265, .175)), ((.15, -.075), (.31, -.081)),
             ((-.33, -.06), (-.20, -.064)), ((-.24, -.052), (-.243, -.095))]
    for i, (a, b) in enumerate(lines):
        pts = []
        for u in [j / 30 for j in range(31)]:
            pts.append((a[0] + (b[0] - a[0]) * u + rng.uniform(-.00006, .00006),
                        a[1] + (b[1] - a[1]) * u + rng.uniform(-.00006, .00006), .00002))
        base.stroke(f'bench_pencil_line_{i}', pts, .00011, graphite)
    return [top, rail]


def walnut_block():
    """The slider body becomes walnut; its two end faces get dark walnut end grain."""
    bpy = _bpy()
    body = bpy.data.objects['solid_wood_slider']
    walnut = scan_material('walnut_slider_block', 'walnut_veneer', coords='UV', value=.62, saturation=.9,
                           rough=(.42, .72), normal=.5, offset=(.31, .07))
    # The scan's grain runs along V; the block's metre UVs have U along the block (x): swap so the grain runs
    # along the block on its top, bottom and sides (the two end faces carry end grain).
    uv = body.data.uv_layers[0]
    for item in uv.data:
        item.uv = (item.uv[1], item.uv[0])
    kit.add_surface_wear(walnut, smudge=.08, grime=.08, scratch=.04, scale=.05)
    end = bpy.data.materials['scanned_endgrain'].copy()
    end.name = 'walnut_endgrain'
    mix = next(nd for nd in end.node_tree.nodes if nd.bl_idname == 'ShaderNodeMixRGB')
    mix.inputs[0].default_value = .55
    mix.inputs[2].default_value = (.085, .055, .035, 1.)
    body.data.materials[0] = walnut
    body.data.materials[1] = end
    return body


def warm_toy_wood():
    """The replay's oak faces were desaturated to 65-88 %; sanded, unfinished oak keeps its honey colour."""
    bpy = _bpy()
    for name in ('sanded_oak_face_on_plywood', 'light_sanded_wood_rails'):
        for node in bpy.data.materials[name].node_tree.nodes:
            if node.bl_idname == 'ShaderNodeHueSaturation':
                node.inputs['Saturation'].default_value = 1.08


def shaving(name, kind, centre, rot_z, width, length, radius, twist, seed, material):
    """One plane shaving, a 0.12 mm wood ribbon with a slight cross-cup and torn, tapering edges.

    kind 'roll': rolled 1.5-2 turns, tighter towards the inner end, lying on its side (roll axis horizontal);
    kind 'flat': a short ribbon lying flat with gentle waves. `twist` skews it slightly about its length."""
    bpy = _bpy()
    from mathutils import Matrix, Vector
    rng = random.Random(seed)
    nt, nw = 160, 9
    verts, faces = [], []
    pos = Vector((0, 0, 0))
    tangent, normal, side = Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0))
    phases = [rng.uniform(0, math.tau) for _ in range(4)]
    dt = length / (nt - 1)
    for i in range(nt):
        u = i / (nt - 1)
        if i:
            if kind == 'roll':
                curvature = (.55 + .65 * u) / radius
            else:
                curvature = .35 / radius * math.sin(math.tau * 1.2 * u + phases[3])
            bend = Matrix.Rotation(curvature * dt, 3, side)
            tangent, normal = (bend @ tangent).normalized(), (bend @ normal).normalized()
            turn = Matrix.Rotation(twist * 6.0 * dt / length * math.sin(math.pi * u + phases[0]), 3, tangent)
            normal, side = (turn @ normal).normalized(), (turn @ side).normalized()
            pos = pos + tangent * dt
        torn = (.10 * math.sin(37 * u + phases[1]) + .06 * math.sin(91 * u + phases[2]) + rng.uniform(-.03, .03))
        half = .5 * width * (1 - .5 * u ** 1.5) * (1 + torn)
        for j in range(nw):
            s = (j / (nw - 1) * 2 - 1)
            cup = .0007 * s * s                                             # cross-curl of a thin shaving
            p = pos + side * (s * half) + normal * cup
            verts.append((p.x, p.y, p.z))
    for i in range(nt - 1):
        for j in range(nw - 1):
            a = i * nw + j
            faces.append((a, a + 1, a + nw + 1, a + nw))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    sol = obj.modifiers.new('ribbon_thickness', 'SOLIDIFY')
    sol.thickness = .00012
    mesh.materials.append(material)
    obj.rotation_euler.z = rot_z
    obj.location = centre
    bpy.context.view_layer.update()
    low, _ = kit.world_bbox([obj])
    obj.location.z -= low.z - .00001          # the lowest point of the shaving touches the bench
    return obj


def chip(name, centre, size, rot_z, seed, material):
    """A small broken piece of shaving pressed flat: jagged outline, 0.15 mm thick, faintly warped."""
    bpy = _bpy()
    rng = random.Random(seed)
    n = 9
    verts = [(0.0, 0.0, .00012)]
    for k in range(n):
        a = k / n * math.tau + rng.uniform(-.2, .2)
        r = size * rng.uniform(.45, 1.0) * (1.0 if k % 2 else .8)
        verts.append((r * math.cos(a) * 1.4, r * math.sin(a) * .7, rng.uniform(0, .00025)))
    faces = [(0, 1 + k, 1 + (k + 1) % n) for k in range(n)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    sol = obj.modifiers.new('chip_thickness', 'SOLIDIFY')
    sol.thickness = .00015
    mesh.materials.append(material)
    obj.rotation_euler.z = rot_z
    obj.location = (centre[0], centre[1], .00016)
    return obj


def carpenters_pencil(material_lacquer, material_wood, material_lead):
    """Flat carpenter's pencil, 175 x 12 x 6.5 mm, red lacquer, knife-sharpened end; no print."""
    bpy = _bpy()
    import bmesh
    parts = []
    bpy.ops.mesh.primitive_cube_add(size=1, location=(-.0105, 0, .00325))
    body = bpy.context.object
    body.name = 'carpenters_pencil_body'
    body.dimensions = (.155, .012, .0065)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    body.data.materials.append(material_lacquer)
    bev = body.modifiers.new('rounded_corners', 'BEVEL')
    bev.width, bev.segments = .0012, 3
    parts.append(body)
    # Knife-cut tip: a frustum from the 12 x 6.5 mm section to the exposed 3 x 1.2 mm lead.
    mesh = bpy.data.meshes.new('carpenters_pencil_tip')
    bm = bmesh.new()
    x0, x1 = .067, .086
    ring0 = [(x0, -.0058, .0003), (x0, .0058, .0003), (x0, .0058, .0062), (x0, -.0058, .0062)]
    ring1 = [(x1, -.0016, .0026), (x1, .0016, .0026), (x1, .0016, .0039), (x1, -.0016, .0039)]
    v0 = [bm.verts.new(p) for p in ring0]
    v1 = [bm.verts.new(p) for p in ring1]
    for k in range(4):
        bm.faces.new((v0[k], v0[(k + 1) % 4], v1[(k + 1) % 4], v1[k]))
    bm.faces.new(list(reversed(v0)))
    bm.faces.new(v1)
    bm.to_mesh(mesh)
    bm.free()
    tip = bpy.data.objects.new('carpenters_pencil_tip', mesh)
    bpy.context.scene.collection.objects.link(tip)
    mesh.materials.append(material_wood)
    parts.append(tip)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(.0875, 0, .00325))
    lead = bpy.context.object
    lead.name = 'carpenters_pencil_lead'
    lead.dimensions = (.004, .0031, .0012)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    lead.data.materials.append(material_lead)
    parts.append(lead)
    return parts


def props(scene):
    """Bench props of the job. Every one rests on the bench and stays outside KEEPOUT."""
    bpy = _bpy()
    from mathutils import Matrix, Vector
    import render_base as base
    placed = []
    # No. 4 hand plane standing on its sole behind the toy, top right (partly beyond the frame edge).
    with bpy.data.libraries.load(str(asset('polyhaven/hand_plane_no4/hand_plane_no4_2k.blend')), link=False) as (src, dst):
        dst.objects = [name for name in src.objects if name == 'hand_plane_no4']
    plane = dst.objects[0]
    scene.collection.objects.link(plane)
    plane.rotation_euler = (0, 0, math.radians(PLANE[2]))
    bpy.context.view_layer.update()
    low, high = kit.world_bbox([plane])
    plane.location += Vector((PLANE[0] - (low.x + high.x) / 2, PLANE[1] - (low.y + high.y) / 2, -low.z))
    placed.append(plane)
    # Shavings: pine curls from the plane's mouth, and one by the offcuts.
    pine = new_material('pine_shaving', (.80, .62, .40), .62)
    b = bsdf(pine)
    b.inputs['Subsurface Weight'].default_value = .25
    b.inputs['Subsurface Radius'].default_value = (.004, .0025, .0012)
    b.inputs['Subsurface Scale'].default_value = .4
    fibre = pine.node_tree.nodes.new('ShaderNodeTexNoise')
    fibre.inputs['Scale'].default_value = 1.0
    fibre.inputs['Detail'].default_value = 6.0
    tc = pine.node_tree.nodes.new('ShaderNodeTexCoord')
    st = pine.node_tree.nodes.new('ShaderNodeMapping')
    st.inputs['Scale'].default_value = (900, 25, 25)
    pine.node_tree.links.new(tc.outputs['Object'], st.inputs['Vector'])
    pine.node_tree.links.new(st.outputs[0], fibre.inputs['Vector'])
    ramp = pine.node_tree.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (.50, .33, .18, 1)
    ramp.color_ramp.elements[1].color = (.74, .56, .36, 1)
    pine.node_tree.links.new(fibre.outputs['Fac'], ramp.inputs['Fac'])
    pine.node_tree.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
    for i, (kind, cx, cy, rz, w, ln, r, twist) in enumerate(SHAVINGS):
        placed.append(shaving(f'plane_shaving_{i}', kind, (cx, cy, 0), rz, w, ln, r, twist, 31 + i, pine))
    for i, (cx, cy, size, rz) in enumerate(CHIPS):
        placed.append(chip(f'shaving_chip_{i}', (cx, cy), size, rz, 71 + i, pine))
    # Two offcuts of the rail stock (sawn ends show end grain), top left.
    rails = bpy.data.materials['light_sanded_wood_rails']
    endgrain = bpy.data.materials['scanned_endgrain']
    for i, (x, y, sx, angle) in enumerate([(-.150, .080, .062, .10), (-.128, .101, .048, -.16)]):
        ob = base.box('rail_offcut_' + str(i), (x, y, .006), (sx, .010, .012), rails, .00025)
        ob.rotation_euler.z = angle
        ob.data.materials.append(endgrain)
        for face in ob.data.polygons:
            if abs(face.normal.x) > .5:
                face.material_index = 1
        placed.append(ob)
    # Carpenter's pencil in front of the toy, bottom right.
    lacquer = new_material('pencil_red_lacquer', (.30, .032, .022), .36)
    kit.add_surface_wear(lacquer, smudge=.10, grime=.08, scratch=.10, scale=.04)
    cedar = new_material('pencil_cut_cedar', (.62, .43, .27), .75)
    lead = new_material('pencil_graphite', (.06, .06, .065), .38, .35)
    pencil = carpenters_pencil(lacquer, cedar, lead)
    holder = bpy.data.objects.new('carpenters_pencil', None)
    scene.collection.objects.link(holder)
    for part in pencil:
        part.parent = holder
    holder.location = (PENCIL[0], PENCIL[1], 0)
    holder.rotation_euler.z = math.radians(PENCIL[2])
    placed += pencil
    bpy.context.view_layer.update()
    # Saw and sanding dust on the bench, never inside the toy footprint.
    dust = kit.sawdust('bench_sawdust', [(-.24, .06, -.09, .13, 4), (-.22, -.10, -.12, -.05, 3), (.0, .10, .14, .16, 2),
                                         (-.2, -.12, .2, .2, 1)], 700, ((KEEPOUT[0][0], KEEPOUT[0][1]), (KEEPOUT[1][0], KEEPOUT[1][1])),
                       color=(.70, .55, .36), seed=23, size=(.00015, .0006), z=0.0)
    # (the dust is one mesh around the toy; kit.sawdust already rejects every fleck inside the keep-out)
    audit = [kit.assert_clear([o], KEEPOUT, o.name) for o in placed if o.type == 'MESH']
    audit.append({'label': dust.name, 'flecks': len(dust.data.polygons), 'note': 'each fleck placed outside the keep-out'})
    # Props may not interpenetrate: footprints (x-y bounds) of different props must be disjoint.
    groups = {}
    for o in placed:
        key = o.name.split('.')[0]
        key = 'carpenters_pencil' if key.startswith('carpenters_pencil') else key
        groups.setdefault(key, []).append(o)
    boxes = {k: kit.world_bbox(v) for k, v in groups.items()}
    names = sorted(boxes)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            (la, ha), (lb, hb) = boxes[a], boxes[b]
            if la.x < hb.x and lb.x < ha.x and la.y < hb.y and lb.y < ha.y:
                raise RuntimeError(f'props overlap: {a} {tuple(la)}..{tuple(ha)} and {b} {tuple(lb)}..{tuple(hb)}')
    return audit


def daylight(scene):
    """Light of a real small workshop (equirectangular HDRI) plus the low sun through its window; no lamps."""
    bpy = _bpy()
    from mathutils import Vector
    az, el = math.radians(SUN['azimuth_deg']), math.radians(SUN['elevation_deg'])
    towards = -Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    sun = bpy.data.lights.new('window_sun', 'SUN')
    sun.energy, sun.angle, sun.color = SUN['strength'], math.radians(SUN['angle_deg']), SUN['color']
    lamp = bpy.data.objects.new('window_sun', sun)
    scene.collection.objects.link(lamp)
    lamp.rotation_euler = towards.to_track_quat('-Z', 'Y').to_euler()
    world = bpy.data.worlds.new('small_workshop_daylight')
    scene.world = world
    world.use_nodes = True
    n, l = world.node_tree.nodes, world.node_tree.links
    bg = n.get('Background')
    env = n.new('ShaderNodeTexEnvironment')
    env.image = bpy.data.images.load(str(HDRI), check_existing=True)
    tc = n.new('ShaderNodeTexCoord')
    mp = n.new('ShaderNodeMapping')
    mp.inputs['Rotation'].default_value[2] = math.radians(HDRI_ROT)
    l.new(tc.outputs['Generated'], mp.inputs['Vector'])
    l.new(mp.outputs[0], env.inputs['Vector'])
    l.new(env.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = HDRI_STRENGTH
    world.cycles.sampling_method = 'MANUAL'
    world.cycles.sample_map_resolution = 2048


def lens_finish(scene, vignette=.10):
    """Mild optical vignette between render layer and composite; the ID-mask outputs keep their own links."""
    tree = scene.node_tree
    rl = next(x for x in tree.nodes if x.bl_idname == 'CompositorNodeRLayers')
    out = next(x for x in tree.nodes if x.bl_idname == 'CompositorNodeComposite')
    for link in list(out.inputs[0].links):
        tree.links.remove(link)
    mask = tree.nodes.new('CompositorNodeEllipseMask')
    mask.width, mask.height = 1.2, 1.35
    blur = tree.nodes.new('CompositorNodeBlur')
    blur.filter_type = 'GAUSS'
    blur.use_relative = True
    blur.factor_x = blur.factor_y = 30.0
    tree.links.new(mask.outputs['Mask'], blur.inputs['Image'])
    level = tree.nodes.new('CompositorNodeMapRange')
    level.inputs['To Min'].default_value = 1.0 - vignette
    tree.links.new(blur.outputs['Image'], level.inputs['Value'])
    mix = tree.nodes.new('CompositorNodeMixRGB')
    mix.blend_type = 'MULTIPLY'
    tree.links.new(rl.outputs['Image'], mix.inputs[1])
    tree.links.new(level.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], out.inputs[0])


def apply(scene, cam, p, moving, out):
    bpy = _bpy()
    tagged = {o.name: o.pass_index for o in bpy.data.objects if o.pass_index}
    removed = clear_surroundings(scene)
    surfaces = bench(scene)
    walnut_block()
    warm_toy_wood()
    audit = props(scene)
    daylight(scene)
    lens_finish(scene)
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = EXPOSURE
    # Motion blur stays on (1/72 s): Blender 4.3 drops static objects from later frames with persistent data.
    scene.render.use_persistent_data = False
    scene.cycles.use_light_tree = True
    scene.cycles.sample_clamp_indirect = 8.0
    scene.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    after = {o.name: o.pass_index for o in bpy.data.objects if o.pass_index}
    assert after == tagged, 'look changed instance identities'
    kit.write_json(Path(out) / 'realism_provenance.json', {
        'look': 'appearance/realism.py', 'host': kit.host_record(),
        'removed_surroundings': removed, 'bench_top': [o.name for o in surfaces], 'props_clearance': audit,
        'keepout_m': KEEPOUT, 'hdri': str(HDRI.name), 'hdri_rotation_deg': HDRI_ROT, 'hdri_strength': HDRI_STRENGTH,
        'exposure_ev': EXPOSURE, 'sun': SUN, 'view_transform': 'AgX - Medium High Contrast', 'persistent_data': False,
        'assets': ['polyhaven/oriented_strand_board', 'polyhaven/walnut_veneer', 'polyhaven/hand_plane_no4',
                   'polyhaven/small_workshop']})


if __name__ == '__main__':
    import render_scene
    render_scene.main(render_scene.parse_args(), look=apply)
