"""Photographic Cycles replay of one native case (current look).

Run inside Blender 4.3:
    blender -b --factory-startup --python appearance/render.py -- --simulation SIM --out OUT
            [--samples 256] [--device OPTIX|CUDA|CPU] [--stills 1,24,48,96 | --frame-start 1 --frame-end 96]

Every moving surface is the native solver output: the curtain mesh is driven by an exact MDD vertex cache
written from cache.npz (positions at i/24 s, linearly interpolated only inside the motion-blur shutter), the
vase (and the optional cup) by their native affine transforms. The camera is the fixed camera of physics/baseline.py
LAYOUT. Only light, materials and static dressing are authored here. The room is a closed box: daylight
enters only through the window (HDRI sky through a Cycles light portal), there is no hidden fill light.
"""
from pathlib import Path
import argparse, json, math, os, socket, struct, sys, time
import bpy
import numpy as np
from mathutils import Vector, Matrix

sys.dont_write_bytecode = True   # Blender ignores PYTHONDONTWRITEBYTECODE; keep scripts/ free of __pycache__
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'physics')]
from baseline import ASSETS, LAYOUT, FIGURE_ASSET, BASELINE_REVISION, REPO, save, sha

PH = REPO / 'assets/polyhaven'
IDS = dict(environment=0, figurine=1, curtain=2, ceramic_cup=3)
ASSETS_USED = []


# ----------------------------------------------------------------------------------------- helpers
def image(path, colour=True):
    path = Path(path); ASSETS_USED.append(str(path.relative_to(REPO)))
    im = bpy.data.images.load(str(path), check_existing=True)
    if not colour: im.colorspace_settings.name = 'Non-Color'
    return im


def principled(name, colour=(.8, .8, .8), rough=.5, metal=0., **extra):
    m = bpy.data.materials.new(name); m.use_nodes = True
    bs = m.node_tree.nodes['Principled BSDF']
    bs.inputs['Base Color'].default_value = (*colour, 1); bs.inputs['Roughness'].default_value = rough
    bs.inputs['Metallic'].default_value = metal
    for key, value in extra.items(): bs.inputs[key].default_value = value
    m.diffuse_color = (*colour, 1)
    return m


def scanned(name, prefix, size_m, *, tint=None, value=1., flatten=None, rough_range=None, normal=1., coat=0., coat_rough=.3,
            projection='BOX', uv=False, extra_scale=(1., 1., 1.)):
    """PBR scan (diff / rough / nor_gl) at its real-world tile size, box-projected in object metres."""
    m = principled(name); n = m.node_tree.nodes; l = m.node_tree.links; bs = n['Principled BSDF']
    if uv:
        tc = n.new('ShaderNodeTexCoord'); src = tc.outputs['UV']
    else:
        tc = n.new('ShaderNodeNewGeometry'); src = tc.outputs['Position']
    mp = n.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = tuple(e / size_m for e in extra_scale)
    l.new(src, mp.inputs['Vector'])
    def tex(kind, colour):
        t = n.new('ShaderNodeTexImage'); t.image = image(f'{prefix}_{kind}_2k.jpg', colour)
        if not uv: t.projection = projection; t.projection_blend = .25
        l.new(mp.outputs['Vector'], t.inputs['Vector']); return t
    d = tex('diff', True); col = d.outputs['Color']
    if value != 1.:
        hsv = n.new('ShaderNodeHueSaturation'); hsv.inputs['Value'].default_value = value
        l.new(col, hsv.inputs['Color']); col = hsv.outputs['Color']
    if flatten:   # (colour, weight): keep only part of the scan's albedo variation (e.g. fresh paint over plaster)
        fl = n.new('ShaderNodeMix'); fl.data_type = 'RGBA'; fl.inputs['Factor'].default_value = flatten[1]
        l.new(col, fl.inputs['A']); fl.inputs['B'].default_value = (*flatten[0], 1); col = fl.outputs['Result']
    if tint:
        mix = n.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'; mix.inputs['Factor'].default_value = 1.
        l.new(col, mix.inputs['A']); mix.inputs['B'].default_value = (*tint, 1); col = mix.outputs['Result']
    l.new(col, bs.inputs['Base Color'])
    r = tex('rough', False); rs = r.outputs['Color']
    if rough_range:
        mr = n.new('ShaderNodeMapRange'); mr.inputs['To Min'].default_value, mr.inputs['To Max'].default_value = rough_range
        l.new(rs, mr.inputs['Value']); rs = mr.outputs['Result']
    l.new(rs, bs.inputs['Roughness'])
    nm = n.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = normal
    l.new(tex('nor_gl', False).outputs['Color'], nm.inputs['Color']); l.new(nm.outputs['Normal'], bs.inputs['Normal'])
    if coat:
        bs.inputs['Coat Weight'].default_value = coat; bs.inputs['Coat Roughness'].default_value = coat_rough
    return m


def grime(mat, strength=.25, distance=.04, colour=(.42, .40, .36)):
    """Darken creases and corners the way dust and handling darken real joinery (AO-driven)."""
    n = mat.node_tree.nodes; l = mat.node_tree.links; bs = n['Principled BSDF']
    ao = n.new('ShaderNodeAmbientOcclusion'); ao.inputs['Distance'].default_value = distance; ao.samples = 8
    inv = n.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.
    l.new(ao.outputs['AO'], inv.inputs[1])
    noise = n.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 60.; noise.inputs['Detail'].default_value = 6
    fac = n.new('ShaderNodeMath'); fac.operation = 'MULTIPLY'; l.new(inv.outputs[0], fac.inputs[0]); l.new(noise.outputs['Fac'], fac.inputs[1])
    amt = n.new('ShaderNodeMath'); amt.operation = 'MULTIPLY'; amt.inputs[1].default_value = strength * 2; l.new(fac.outputs[0], amt.inputs[0])
    base = bs.inputs['Base Color']
    mix = n.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
    if base.links: l.new(base.links[0].from_socket, mix.inputs['A'])
    else: mix.inputs['A'].default_value = base.default_value[:]
    mix.inputs['B'].default_value = (*colour, 1); l.new(amt.outputs[0], mix.inputs['Factor']); l.new(mix.outputs['Result'], base)
    return mat


def cube(name, loc, dims, mat, bevel=0.):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object; o.name = name; o.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat: o.data.materials.append(mat)
    if bevel:
        b = o.modifiers.new('Edge radius', 'BEVEL'); b.width = bevel; b.segments = 3; b.limit_method = 'ANGLE'
        o.modifiers.new('Edge normals', 'WEIGHTED_NORMAL').keep_sharp = True
    return o


def cylinder(name, loc, radius, depth, mat, vertices=64, bevel=0.):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    o = bpy.context.object; o.name = name; o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = True
    if bevel:
        b = o.modifiers.new('Edge radius', 'BEVEL'); b.width = bevel; b.segments = 3; b.limit_method = 'ANGLE'
    o.modifiers.new('Edge normals', 'WEIGHTED_NORMAL').keep_sharp = True
    return o


def import_blend(key, width=None, height=None, loc=(0, 0, 0)):
    """A packed library asset of this scene, scaled uniformly to its real size and set on the desk."""
    path = ASSETS / key / 'asset.blend'; ASSETS_USED.append(str(path.relative_to(REPO)))
    with bpy.data.libraries.load(str(path), link=False) as (src, dst): dst.objects = src.objects
    imported = [o for o in dst.objects if o is not None and o.type in {'MESH', 'CURVE', 'EMPTY'}]
    for o in imported: bpy.context.collection.objects.link(o); o.animation_data_clear()
    bpy.context.view_layer.update()
    geo = [o for o in imported if o.type in {'MESH', 'CURVE'} and not o.hide_render]
    world = {o: o.matrix_world.copy() for o in imported}
    for o in imported: o.parent = None; o.matrix_world = world[o]
    pts = np.array([o.matrix_world @ Vector(p) for o in geo for p in o.bound_box])
    lo, hi = pts.min(0), pts.max(0); dims = hi - lo
    factor = width / dims[0] if width else height / dims[2]
    centre = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    for o in imported:
        T = o.matrix_world.copy(); T.translation -= Vector(centre)
        T = Matrix.Diagonal((factor, factor, factor, 1.)) @ T; T.translation += Vector(loc); o.matrix_world = T
    return imported


# ----------------------------------------------------------------------------------------- materials
def linen_material(hem=False):
    """Oatmeal cotton-linen: CC0 rough_linen scan at its 0.27 m tile on the material (rest) coordinates."""
    m = principled('Washed cotton-linen' + (', double-fold hem' if hem else ''))
    n = m.node_tree.nodes; l = m.node_tree.links; bs = n['Principled BSDF']; out = n['Material Output']
    uv = n.new('ShaderNodeUVMap'); uv.uv_map = 'Material coordinates'
    mp = n.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (MATERIAL_WIDTH / .2707, LAYOUT['cloth_height'] / .2713, 1.)
    l.new(uv.outputs['UV'], mp.inputs['Vector'])
    def tex(kind, colour):
        t = n.new('ShaderNodeTexImage'); t.image = image(PH / f'rough_linen/textures/rough_linen_{kind}_2k.jpg', colour)
        l.new(mp.outputs['Vector'], t.inputs['Vector']); return t
    d = tex('diff', True)
    # Re-dye the scan to unbleached cotton-linen (oatmeal off-white) without losing its slub contrast.
    hsv = n.new('ShaderNodeHueSaturation'); hsv.inputs['Saturation'].default_value = 0.   # the scan is a blue-grey linen: keep its luminance only
    hsv.inputs['Value'].default_value = 1.55 if not hem else 1.45
    l.new(d.outputs['Color'], hsv.inputs['Color'])
    warm = n.new('ShaderNodeMix'); warm.data_type = 'RGBA'; warm.blend_type = 'MULTIPLY'; warm.inputs['Factor'].default_value = 1.
    warm.inputs['B'].default_value = (.98, .90, .77, 1); l.new(hsv.outputs['Color'], warm.inputs['A'])
    l.new(warm.outputs['Result'], bs.inputs['Base Color'])
    arm = tex('arm', False); sep = n.new('ShaderNodeSeparateColor'); l.new(arm.outputs['Color'], sep.inputs['Color'])
    mr = n.new('ShaderNodeMapRange'); mr.inputs['To Min'].default_value = .78; mr.inputs['To Max'].default_value = .95
    l.new(sep.outputs['Green'], mr.inputs['Value']); l.new(mr.outputs['Result'], bs.inputs['Roughness'])
    nm = n.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = 1.2 if not hem else 1.5
    l.new(tex('nor_gl', False).outputs['Color'], nm.inputs['Color'])
    bs.inputs['Sheen Weight'].default_value = .35; bs.inputs['Sheen Roughness'].default_value = .5
    bs.inputs['Sheen Tint'].default_value = (1., .95, .86, 1)
    normal = nm.outputs['Normal']
    if hem:
        # A machine lock-stitch line 8 mm in from the folded edge (thread spacing ~2.5 mm).
        sep_uv = n.new('ShaderNodeSeparateXYZ'); l.new(uv.outputs['UV'], sep_uv.inputs['Vector'])
        stitch = n.new('ShaderNodeTexWave'); stitch.wave_type = 'BANDS'; stitch.bands_direction = 'X'
        stitch.inputs['Scale'].default_value = MATERIAL_WIDTH / .0025 / 2; stitch.inputs['Distortion'].default_value = 0
        l.new(uv.outputs['UV'], stitch.inputs['Vector'])
        bump = n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = .35; bump.inputs['Distance'].default_value = .0004
        l.new(stitch.outputs['Fac'], bump.inputs['Height']); l.new(normal, bump.inputs['Normal']); normal = bump.outputs['Normal']
    l.new(normal, bs.inputs['Normal'])
    # Thin open weave: a little daylight passes through (less where the hem doubles the fabric).
    trans = n.new('ShaderNodeBsdfTranslucent'); l.new(warm.outputs['Result'], trans.inputs['Color'])
    mix = n.new('ShaderNodeMixShader'); mix.inputs[0].default_value = .22 if hem else .40
    l.new(bs.outputs[0], mix.inputs[1]); l.new(trans.outputs[0], mix.inputs[2]); l.new(mix.outputs[0], out.inputs['Surface'])
    return m


def vase_material(mat):
    """Glossy glaze over the scanned transfer-print body: keep the scan maps, add the glassy coat."""
    bs = next(x for x in mat.node_tree.nodes if x.type == 'BSDF_PRINCIPLED')
    bs.inputs['Coat Weight'].default_value = .85; bs.inputs['Coat Roughness'].default_value = .045
    bs.inputs['Coat IOR'].default_value = 1.52
    return mat


def stoneware(name, colour):
    m = principled(name, colour, .32, **{'Coat Weight': .5, 'Coat Roughness': .12})
    n = m.node_tree.nodes; l = m.node_tree.links; bs = n['Principled BSDF']
    speck = n.new('ShaderNodeTexVoronoi'); speck.inputs['Scale'].default_value = 900.; speck.feature = 'F1'
    ramp = n.new('ShaderNodeValToRGB'); ramp.color_ramp.elements[0].position = .0; ramp.color_ramp.elements[1].position = .06
    ramp.color_ramp.elements[0].color = (.12, .10, .08, 1); ramp.color_ramp.elements[1].color = (*colour, 1)
    l.new(speck.outputs['Distance'], ramp.inputs['Fac']); l.new(ramp.outputs['Color'], bs.inputs['Base Color'])
    return m


# ----------------------------------------------------------------------------------------- room
def environment(scene):
    plaster = scanned('Painted plaster, warm white', PH / 'painted_plaster_wall/painted_plaster_wall', 2.,
                      flatten=((.80, .775, .72), .8), rough_range=(.80, .92), normal=.5)
    grime(plaster, .10, .06)
    upvc = principled('White uPVC window profile', (.86, .86, .83), .30, **{'Coat Weight': .15, 'Coat Roughness': .2})
    grime(upvc, .35, .025, (.55, .53, .49))
    sill_mat = principled('Painted window board, satin', (.84, .83, .79), .36)
    grime(sill_mat, .25, .03, (.6, .58, .53))
    oak = scanned('Desk top, oiled solid wood', ASSETS / 'wood_table/wood_table', 1., tint=(1., .95, .9),
                  rough_range=(.30, .55), normal=.45, coat=.25, coat_rough=.22)
    legs = scanned('Desk frame, oiled solid wood', ASSETS / 'wood_table/wood_table', 1., tint=(.9, .85, .8),
                   rough_range=(.35, .6), normal=.4)
    floor = principled('Light oak floorboards (out of frame)', (.50, .38, .26), .45)

    # Desk: native collider top (LAYOUT table) with a real frame underneath.
    cube('Solid wood writing desk top', LAYOUT['table_center'], LAYOUT['table_dimensions'], oak, .003)
    for x in (-.70, .58):
        for y in (-.43, .32): cube('Desk leg', (x, y, -.405), (.05, .05, .74), legs, .003)
    cube('Desk front apron', (-.06, -.432, -.075), (1.26, .022, .085), legs, .002)
    cube('Desk drawer front', (-.36, -.446, -.075), (.46, .012, .068), oak, .0015)
    knob = principled('Brushed brass knob', (.66, .50, .26), .32, 1.)
    k = cylinder('Drawer knob', (-.36, -.458, -.075), .011, .016, knob, 48, .002); k.rotation_euler[0] = math.pi / 2
    cube('Room floor', (-.1, -.9, -.80), (4., 3.6, .04), floor)

    # Window wall (opening x in [-.66,.66], z in [.06,1.24]) and the surrounding closed room.
    for x, w in ((-1.40, 1.48), (1.40, 1.48)): cube('Plastered window wall', (x, .35, .5), (w, .08, 2.6), plaster)
    cube('Wall below window', (0, .35, -.45), (1.32, .08, 1.10), plaster)
    cube('Wall above window', (0, .35, 1.70), (1.32, .08, .92), plaster)
    cube('Opposite wall', (0, -2.70, .62), (4.0, .06, 2.9), plaster)
    for x in (-1.75, 1.75): cube('Side wall', (x, -1.2, .62), (.06, 3.2, 2.9), plaster)
    cube('Ceiling', (0, -1.2, 2.06), (4.0, 3.2, .06), principled('Ceiling paint', (.86, .85, .83), .9))
    for x in (-.635, .635): cube('Window frame jamb', (x, .29, .65), (.045, .12, 1.16), upvc, .003)
    for z in (.086, 1.21): cube('Window frame rail', (0, .29, z), (1.31, .12, .040), upvc, .003)
    cube('Window sash mullion', (.36, .284, .65), (.026, .08, 1.10), upvc, .0015)
    cube('Window board', (0, .227, .081), (1.40, .23, .036), sill_mat, .003)
    rubber = principled('EPDM glazing gasket', (.025, .027, .026), .7)
    for x in (-.606, .606): cube('Glazing gasket', (x, .293, .65), (.003, .005, 1.075), rubber)
    for z in (.108, 1.191): cube('Glazing gasket', (0, .293, z), (1.211, .005, .003), rubber)
    # Insulated glazing: two 4 mm float panes with a 16 mm gap.
    glass = principled('Float glass', (1., 1., 1.), 0., **{'Transmission Weight': 1., 'IOR': 1.52})
    gn = glass.node_tree.nodes; gl = glass.node_tree.links
    smudge = gn.new('ShaderNodeTexNoise'); smudge.inputs['Scale'].default_value = 7.; smudge.inputs['Detail'].default_value = 8
    sm = gn.new('ShaderNodeMapRange'); sm.inputs['From Min'].default_value = .55; sm.inputs['From Max'].default_value = .8
    sm.inputs['To Max'].default_value = .035; gl.new(smudge.outputs['Fac'], sm.inputs['Value']); gl.new(sm.outputs['Result'], gn['Principled BSDF'].inputs['Roughness'])
    for y in (.296, .316):
        pane = cube('Glass pane', (0, y, .65), (1.21, .004, 1.10), glass)
        pane.visible_shadow = False   # thin parallel panes: let daylight shadow rays through (no refraction offset)
    handle = principled('Satin aluminium handle', (.75, .76, .76), .28, 1.)
    cube('Window handle base', (.365, .233, .535), (.024, .012, .060), handle, .003)
    lever = cube('Window handle lever', (.365, .218, .505), (.012, .016, .095), handle, .004)
    # Double wall socket above the desk (plain plates, no lettering).
    plate = principled('Socket plate, white PC', (.88, .88, .86), .35)
    cube('Wall socket plate', (-1.02, .305, .22), (.158, .010, .086), plate, .004)
    holes = principled('Socket recess', (.70, .70, .68), .5)
    for dx in (-.039, .039):
        c = cylinder('Socket recess', (-1.02 + dx, .300, .22), .019, .004, holes, 48); c.rotation_euler[0] = math.pi / 2

    # Daylight: HDRI sky outside, sampled through a portal filling the window opening.
    sky = ASSETS / 'residential_garden/residential_garden_2k.hdr'
    world = bpy.data.worlds.new('Overcast garden daylight'); scene.world = world; world.use_nodes = True
    wn = world.node_tree.nodes; wl = world.node_tree.links
    env = wn.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load(str(sky)); ASSETS_USED.append(str(sky.relative_to(REPO)))
    tc = wn.new('ShaderNodeTexCoord'); mp = wn.new('ShaderNodeMapping'); mp.inputs['Rotation'].default_value[2] = 1.4
    wl.new(tc.outputs['Generated'], mp.inputs['Vector']); wl.new(mp.outputs['Vector'], env.inputs['Vector'])
    # Camera white balance for overcast daylight (~6500 K -> neutral): a warm gain on the incoming sky only.
    wb = wn.new('ShaderNodeMix'); wb.data_type = 'RGBA'; wb.blend_type = 'MULTIPLY'; wb.inputs['Factor'].default_value = 1.
    wb.inputs['B'].default_value = (1., .93, .84, 1); wl.new(env.outputs['Color'], wb.inputs['A'])
    wn['Background'].inputs['Strength'].default_value = 1.0; wl.new(wb.outputs['Result'], wn['Background'].inputs['Color'])
    portal = bpy.data.lights.new('Window light portal', 'AREA'); portal.shape = 'RECTANGLE'
    portal.size = 1.30; portal.size_y = 1.20; portal.cycles.is_portal = True
    po = bpy.data.objects.new('Window light portal', portal); bpy.context.collection.objects.link(po)
    po.location = (0, .385, .65); po.rotation_euler = (-math.pi / 2, 0, 0)   # faces -Y, into the room
    dressing = ([o.name for o in import_blend('notebook_compatible', width=.24, loc=LAYOUT['notebook_location'])] +
                [o.name for o in import_blend('pen_holder', height=.225, loc=LAYOUT['pen_holder_location'])] +
                sill_plant())
    # The packed pen holder references one external normal map that was never packed; use the CC0 wood normal.
    repaired = []
    for im in list(bpy.data.images):
        if im.source == 'FILE' and not im.packed_file and im.filepath and not Path(bpy.path.abspath(im.filepath)).is_file():
            im.filepath = str(ASSETS / 'wood_table/wood_table_nor_gl_2k.jpg'); im.colorspace_settings.name = 'Non-Color'
            im.reload(); repaired.append(im.name)
    return dict(objects=dressing, repaired_missing_images=repaired)


PLANT_BOX = dict(x=(.415, .585), y=(.118, .286), z=(.099, .40))   # window board, right of the mullion, clear of the glass


def sill_plant():
    """Poly Haven potted_plant_04 (CC0) at its real size on the window board, inside PLANT_BOX."""
    src = PH / 'potted_plant_04/potted_plant_04_2k.gltf'; ASSETS_USED.append(str(src.relative_to(REPO)))
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=str(src))
    parts = [o for o in bpy.data.objects if o not in before]; bpy.context.view_layer.update()
    meshes = [o for o in parts if o.type == 'MESH']
    pts = np.array([o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]); lo, hi = pts.min(0), pts.max(0)
    if hi[1] - lo[1] > hi[0] - lo[0]:   # put the narrower side across the board
        R = Matrix.Rotation(math.pi / 2, 4, 'Z')
        for o in parts:
            if o.parent is None: o.matrix_world = R @ o.matrix_world
        bpy.context.view_layer.update()
        pts = np.array([o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]); lo, hi = pts.min(0), pts.max(0)
    target = Vector((sum(PLANT_BOX['x']) / 2, sum(PLANT_BOX['y']) / 2, PLANT_BOX['z'][0]))
    shift = target - Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))
    for o in parts:
        if o.parent is None: o.location += shift
    bpy.context.view_layer.update()
    pts = np.array([o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]); lo, hi = pts.min(0), pts.max(0)
    PLANT_BOX['installed'] = [lo.tolist(), hi.tolist()]
    if hi[1] > PLANT_BOX['y'][1] + 1e-3 or lo[1] < PLANT_BOX['y'][0] - 1e-3: raise RuntimeError('Plant does not fit the window board')
    return [o.name for o in meshes]


def plain_notebook_cover():
    """The packed notebook carries a printed title page; replace it with plain unprinted cover board."""
    cover = principled('Unprinted cover board', (.80, .78, .73), .7)
    n = cover.node_tree.nodes; l = cover.node_tree.links
    fib = n.new('ShaderNodeTexNoise'); fib.inputs['Scale'].default_value = 900.; fib.inputs['Detail'].default_value = 4
    b = n.new('ShaderNodeBump'); b.inputs['Strength'].default_value = .08; l.new(fib.outputs['Fac'], b.inputs['Height'])
    l.new(b.outputs['Normal'], n['Principled BSDF'].inputs['Normal'])
    replaced = []
    for o in bpy.data.objects:
        for slot in o.material_slots:
            m = slot.material
            if m and m.use_nodes and any(x.type == 'TEX_IMAGE' and x.image and 'notes' in x.image.name.lower() for x in m.node_tree.nodes):
                slot.material = cover; replaced.append(o.name)
    return replaced


def vase():
    prep = json.loads((FIGURE_ASSET / 'preparation.json').read_text())
    src = PH / 'antique_ceramic_vase_01/antique_ceramic_vase_01_2k.gltf'; ASSETS_USED.append(str(src.relative_to(REPO)))
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(src))
    parts = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new('FIGURINE native rigid transform', None); bpy.context.collection.objects.link(root)
    s = prep['install']['scale']; c = Vector(prep['install']['source_centre_m'])
    install = Matrix.Diagonal((s, s, s, 1.)) @ Matrix.Translation(-c)
    for o in parts:
        if o.type != 'MESH': continue
        o.matrix_world = install @ o.matrix_world; o.parent = root; o.pass_index = IDS['figurine']
        for slot in o.material_slots:
            if slot.material: vase_material(slot.material)
        for p in o.data.polygons: p.use_smooth = True
    for o in parts:
        if o.type != 'MESH': bpy.data.objects.remove(o, do_unlink=True)
    return root


# ----------------------------------------------------------------------------------------- replay
def write_mdd(path, positions, times):
    with open(path, 'wb') as f:
        f.write(struct.pack('>2i', len(positions), positions.shape[1]))
        f.write(np.asarray(times, '>f4').tobytes()); f.write(positions.astype('>f4').tobytes())


def keyframe(obj, transforms):
    obj.rotation_mode = 'QUATERNION'
    for frame, T in enumerate(transforms, 1):
        loc, rot, scl = Matrix(T.tolist()).decompose()
        obj.location = loc; obj.rotation_quaternion = rot; obj.scale = scl
        for prop in ('location', 'rotation_quaternion', 'scale'): obj.keyframe_insert(prop, frame=frame)
    for fc in obj.animation_data.action.fcurves:
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--simulation', type=Path, required=True); ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--samples', type=int, default=256); ap.add_argument('--width', type=int, default=1280)
    ap.add_argument('--device', choices=('OPTIX', 'CUDA', 'CPU'), default='OPTIX')
    ap.add_argument('--stills'); ap.add_argument('--frame-start', type=int, default=1); ap.add_argument('--frame-end', type=int, default=96)
    ap.add_argument('--shutter', type=float, default=.25)
    ap.add_argument('--exposure', type=float, default=3.0, help='AgX exposure (EV); daylight enters only through the window')
    ap.add_argument('--allow-other-baseline', action='store_true', help='look development on a native state of another baseline revision only')
    a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
    global MATERIAL_WIDTH
    out = a.out; (out / 'rgb').mkdir(parents=True, exist_ok=True); (out / 'ids').mkdir(exist_ok=True)
    cfg = json.loads((a.simulation / 'simulation_config.json').read_text())
    if not a.allow_other_baseline and (cfg.get('baseline_revision') != BASELINE_REVISION
                                       or cfg.get('figure_collision_sha256', sha(FIGURE_ASSET / 'collision.npz')) != sha(FIGURE_ASSET / 'collision.npz')):
        raise RuntimeError('Native state belongs to another baseline/figure asset: ' + str(cfg.get('baseline_revision')))
    if cfg['layout'] != LAYOUT: raise RuntimeError('Native layout differs from physics/baseline.py')
    MATERIAL_WIDTH = float(cfg['cloth_material_width_m'])
    cache = a.simulation / 'cache.npz'; z = np.load(cache)
    positions = z['positions']; faces = z['faces']; uv = z['uv']; names = list(z['rigid_names'])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene; scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences; devices = []
    if a.device != 'CPU':
        prefs.compute_device_type = a.device; prefs.get_devices()
        for d in prefs.devices: d.use = d.type == a.device; devices.append(dict(name=d.name, type=d.type, use=d.use))
        if not any(d['use'] for d in devices): raise RuntimeError('No usable ' + a.device + ' device')
        scene.cycles.device = 'GPU'
    else:
        scene.cycles.device = 'CPU'
    scene.cycles.samples = a.samples; scene.cycles.use_adaptive_sampling = True; scene.cycles.adaptive_threshold = .006
    scene.cycles.use_denoising = True; scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    scene.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'; scene.cycles.denoising_prefilter = 'ACCURATE'
    scene.cycles.max_bounces = 12; scene.cycles.diffuse_bounces = 6; scene.cycles.glossy_bounces = 6
    scene.cycles.transmission_bounces = 12; scene.cycles.transparent_max_bounces = 12
    scene.cycles.use_animated_seed = False; scene.cycles.seed = 20261110
    scene.cycles.light_sampling_threshold = .01
    scene.render.resolution_x = a.width; scene.render.resolution_y = round(a.width * 9 / 16); scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_mode = 'RGB'; scene.render.image_settings.color_depth = '8'
    scene.render.fps = 24; scene.frame_start = 1; scene.frame_end = len(positions)
    scene.view_settings.view_transform = 'AgX'; scene.view_settings.look = 'AgX - Base Contrast'; scene.view_settings.exposure = a.exposure
    scene.render.use_motion_blur = a.shutter > 0; scene.render.motion_blur_shutter = max(a.shutter, 1e-3)
    scene.render.use_persistent_data = False   # Blender 4.3: persistent data + motion blur drops settled objects

    dressing = environment(scene); replaced = plain_notebook_cover()
    roots = {}
    if cfg['physics']['figure_active'][0]:
        roots['figurine'] = vase(); keyframe(roots['figurine'], z['rigid_transforms'][:, names.index('figurine')])
    if cfg['physics']['cup_active'][0]:
        g = np.load(a.simulation / 'ceramic_cup_geometry.npz')
        mesh = bpy.data.meshes.new('Stoneware tumbler'); mesh.from_pydata(g['vertices'].tolist(), [], g['faces'].tolist()); mesh.update()
        cup = bpy.data.objects.new('Added glazed ceramic tumbler', mesh); bpy.context.collection.objects.link(cup)
        cup.data.materials.append(stoneware('Speckled stoneware glaze, sage', (.52, .60, .50)))
        for p in mesh.polygons: p.use_smooth = True
        cup.modifiers.new('Edge normals', 'WEIGHTED_NORMAL'); cup.pass_index = IDS['ceramic_cup']
        keyframe(cup, z['rigid_transforms'][:, names.index('ceramic_cup')]); roots['ceramic_cup'] = cup

    mesh = bpy.data.meshes.new('Native thin-shell triangles'); mesh.from_pydata(positions[0].tolist(), [], faces.tolist()); mesh.update()
    cloth = bpy.data.objects.new('CURTAIN exact native thin shell', mesh); bpy.context.collection.objects.link(cloth)
    cloth.pass_index = IDS['curtain']
    layer = mesh.uv_layers.new(name='Material coordinates')
    loops = np.zeros(len(mesh.loops), np.int64); mesh.loops.foreach_get('vertex_index', loops)
    layer.data.foreach_set('uv', uv[loops].astype(np.float32).ravel())
    mesh.polygons.foreach_set('use_smooth', np.ones(len(mesh.polygons), bool))
    mesh.materials.append(linen_material()); mesh.materials.append(linen_material(hem=True))
    # Hems (2.5 cm at the bottom and sides) and the 6 cm heading at the top: double fabric, stitched.
    centres = uv[faces].mean(1); w, h = MATERIAL_WIDTH, LAYOUT['cloth_height']
    hemmed = (centres[:, 1] * h < .025) | ((1 - centres[:, 1]) * h < .06) | (np.minimum(centres[:, 0], 1 - centres[:, 0]) * w < .025)
    mesh.polygons.foreach_set('material_index', hemmed.astype(np.int32))
    mdd = out / 'cloth.mdd'; write_mdd(mdd, positions, z['times'])
    cache_mod = cloth.modifiers.new('Native exact vertex cache', 'MESH_CACHE'); cache_mod.cache_format = 'MDD'
    cache_mod.filepath = str(mdd); cache_mod.frame_start = 1.; cache_mod.frame_scale = 1.; cache_mod.interpolation = 'LINEAR'
    solid = cloth.modifiers.new('Woven thickness', 'SOLIDIFY'); solid.thickness = .0006; solid.offset = 0.

    cam_data = bpy.data.cameras.new('Fixed camera'); cam = bpy.data.objects.new('Fixed camera', cam_data)
    bpy.context.collection.objects.link(cam); scene.camera = cam
    cam.location = LAYOUT['camera_location']
    cam.rotation_euler = (Vector(LAYOUT['camera_target']) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam_data.lens = LAYOUT['camera_lens']; cam_data.dof.use_dof = True
    cam_data.dof.focus_distance = (Vector((0, 0, .22)) - cam.location).length; cam_data.dof.aperture_fstop = 6.3

    scene.view_layers[0].use_pass_object_index = True; scene.use_nodes = True
    n = scene.node_tree.nodes; n.clear(); l = scene.node_tree.links
    rl = n.new('CompositorNodeRLayers'); comp = n.new('CompositorNodeComposite'); l.new(rl.outputs['Image'], comp.inputs['Image'])
    ids = n.new('CompositorNodeOutputFile'); ids.base_path = str(out / 'ids'); ids.format.file_format = 'OPEN_EXR'
    ids.format.color_mode = 'BW'; ids.format.color_depth = '32'; ids.format.exr_codec = 'ZIP'; ids.file_slots[0].path = 'instance_'
    l.new(rl.outputs['IndexOB'], ids.inputs[0])

    bpy.context.view_layer.update()  # matrix_world is stale (identity) until the depsgraph is evaluated
    camera = dict(matrix_world=[list(r) for r in cam.matrix_world], lens_mm=cam_data.lens, sensor_width_mm=cam_data.sensor_width,
                  sensor_fit=cam_data.sensor_fit, shift=[cam_data.shift_x, cam_data.shift_y],
                  focus_distance_m=cam_data.dof.focus_distance, fstop=cam_data.dof.aperture_fstop)
    manifest = dict(look='appearance/render.py', worker_host=socket.gethostname(),
        gpu=os.environ.get('CUDA_VISIBLE_DEVICES'), blender_version=bpy.app.version_string, device=a.device, devices=devices,
        simulation_cache_sha256=sha(cache), baseline_revision=cfg.get('baseline_revision'), camera_layout=LAYOUT, camera=camera,
        resolution=[scene.render.resolution_x, scene.render.resolution_y], fps=24, samples=a.samples, denoiser='OpenImageDenoise',
        motion_blur_shutter_frames=a.shutter if a.shutter > 0 else 0, persistent_data=False, view_transform='AgX',
        figure_preparation_sha256=sha(FIGURE_ASSET / 'preparation.json'), notebook_cover_replaced_on=replaced,
        assets=sorted(set(ASSETS_USED)), dressing=dressing, sill_plant_box=PLANT_BOX,
        rendered_surface='Native vertex positions through an MDD cache; smooth normals and a 0.6 mm solidify only')
    save(out / 'scene_manifest.json', manifest)
    frames = [int(v) for v in a.stills.split(',')] if a.stills else list(range(a.frame_start, min(a.frame_end, len(positions)) + 1))
    start = time.monotonic()
    for k, frame in enumerate(frames):
        scene.frame_set(frame); scene.render.filepath = str(out / 'rgb' / f'{frame:04d}.png')
        if k == 0:
            bpy.ops.file.pack_all(); bpy.ops.wm.save_as_mainfile(filepath=str(out / 'scene.blend'), compress=True)
        bpy.ops.render.render(write_still=True)
        print('RENDERED', frame, 'wall', round(time.monotonic() - start, 1), flush=True)
    save(out / 'render_completion.json', dict(complete=True, frames=frames, runtime_seconds=time.monotonic() - start,
        cache_sha256=sha(cache), worker_host=socket.gethostname(), gpu=os.environ.get('CUDA_VISIBLE_DEVICES')))


MATERIAL_WIDTH = .916
if __name__ == '__main__':
    main()
