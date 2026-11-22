"""Photographic finish over the room built by scene_geometry.py.

The room, track, car, guides, coil and camera are kept. This pass only
changes what a photographer would notice in the frames:

- no printed text, numbers or titles anywhere in frame: the "GRAVITY PLAY"
  print on the ramp cheek, the "07" door roundels, the "A"/"B" block letters,
  the generated "Woodland" picture-book cover and the printed covers of the
  seven CC0 shelf books are removed; the books keep their scanned meshes,
  page blocks and wear and get plain cloth/board covers;
- the flat sage wall paint gets Poly Haven beige_wall_001 (CC0, 3 m x 3 m
  scan) relief and roughness; the calibrated paint colour is kept;
- a CC0 scanned potted succulent (Poly Haven potted_plant_04, true size) on the
  cabinet top and a plain wall socket above the skirting;
- the coil is bright zinc-plated spring steel instead of dark blued steel, so
  its 0.78 mm wire reads as a continuous helix; guide rods are plain bright
  steel;
- the hidden camera-side fill light is removed (window, sky and sun only);
- camera motion blur (shutter 0.25 frame) from the solved poses, with
  persistent data off; samples raised so thin wire and metal do not flicker.

Nothing here moves a solved body or touches a contact surface; every added
solid is outside the car/baffle corridor (|y| <= 0.08 m, x in [-0.65, 0.74]).
"""
import math
import random
from pathlib import Path
import bpy
from mathutils import Vector, Matrix, Euler
import scene_geometry as sg
from pcve_assets import asset
# The files read here are listed (and hashed into the asset signature) in appearance_config.
from appearance_config import LOOK_ASSET_FILES

WALL_ASSET = 'polyhaven/beige_wall_001'
PLANT_ASSET = 'polyhaven/potted_plant_04'
WALL_MAPS = {c: f'{WALL_ASSET}/beige_wall_001_{c}_4k.jpg' for c in ('diff', 'rough', 'nor_gl')}
PLANT_FILES = [f'{PLANT_ASSET}/{rel}' for rel in LOOK_ASSET_FILES[PLANT_ASSET]]
assert all(Path(p).name in LOOK_ASSET_FILES[WALL_ASSET] for p in WALL_MAPS.values()) and PLANT_FILES[0].endswith('.blend')
# Linear channel means of beige_wall_001_diff_4k.jpg (as measured for this scan in
# rigid_rigid/stair_ball_bounce look): dividing by them keeps only the scanned
# blemish pattern on top of the calibrated paint colour.
WALL_DIFFUSE_LINEAR_MEAN = (.33939, .26212, .18853)
WALL_ROUGHNESS_SOURCE_RANGE = (.5647, .7098)

FACE_OUT_BOOK = ('Thick board book page core', 'Rounded laminated board book cover', 'UV printed watercolor picture book front',
                 'Face out case binding crease', 'Inclined face-out board book')
PRINTED_ROUNDELS = ('Thin pad printed door badge',)


def _delete(objects):
    names = set()
    for ob in objects:names |= {ob.name, *(c.name for c in ob.children_recursive)}
    for name in sorted(names):
        if name in bpy.data.objects:bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)


def remove_text(R):
    """Every FONT object (ramp print, door numbers, block letters) and the printed parts."""
    doomed = [ob for ob in bpy.data.objects if ob.type == 'FONT']
    doomed += [ob for ob in bpy.data.objects if ob.name.split('.')[0] in PRINTED_ROUNDELS + FACE_OUT_BOOK]
    R['removed_objects'] = sorted({ob.name for ob in doomed})
    _delete(doomed)


def plain_book_covers(R, colours):
    """Replace each printed cover image with a plain cloth/board colour; geometry, page blocks and wear stay."""
    rng = random.Random(1306);changed = []
    mats = sorted({m for ob in bpy.data.objects if ob.type == 'MESH' and ob.name.startswith('CC0 bound book mesh') for m in ob.data.materials if m and m.use_nodes}, key=lambda m: m.name)
    for i, mat in enumerate(mats):
        nt = mat.node_tree;n = nt.nodes;l = nt.links
        covers = [node for node in n if node.type == 'TEX_IMAGE' and node.image and 'cover' in Path(node.image.filepath or node.image.name).stem.lower()
                  and any(lk.to_socket.name == 'input_cover' for lk in node.outputs['Color'].links)]
        for tex in covers:
            col = colours[i % len(colours)]
            rgb = n.new('ShaderNodeRGB');rgb.outputs[0].default_value = (*col, 1)
            # Faint cloth/board unevenness in object space, a few percent only.
            tc = n.new('ShaderNodeTexCoord');noise = n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value = 140 + 40 * rng.random();noise.inputs['Detail'].default_value = 4
            l.new(tc.outputs['Object'], noise.inputs['Vector'])
            vary = n.new('ShaderNodeMapRange');vary.inputs['To Min'].default_value = .90;vary.inputs['To Max'].default_value = 1.06;l.new(noise.outputs['Fac'], vary.inputs[0])
            mix = n.new('ShaderNodeMixRGB');mix.blend_type = 'MULTIPLY';mix.inputs[0].default_value = 1;l.new(rgb.outputs[0], mix.inputs[1]);l.new(vary.outputs[0], mix.inputs[2])
            for lk in list(tex.outputs['Color'].links):
                to = lk.to_socket;l.remove(lk);l.new(mix.outputs[0], to)
            changed.append({'material': mat.name, 'replaced_image': tex.image.name, 'cover_rgb': list(col)})
    R['plain_book_covers'] = changed


def scanned_wall_paint(R, look, gray):
    if gray:return
    mat = bpy.data.materials.get('Subtle sage grey wall paint')
    nt = mat.node_tree;n = nt.nodes;l = nt.links
    for node in list(n):n.remove(node)
    out = n.new('ShaderNodeOutputMaterial');p = n.new('ShaderNodeBsdfPrincipled');l.new(p.outputs[0], out.inputs[0])
    tc = n.new('ShaderNodeTexCoord');sc = n.new('ShaderNodeVectorMath');sc.operation = 'SCALE';sc.inputs[3].default_value = 1 / look['tile_m'];l.new(tc.outputs['UV'], sc.inputs[0])
    tex = {}
    for c, rel in WALL_MAPS.items():
        t = n.new('ShaderNodeTexImage');t.image = bpy.data.images.load(str(asset(rel)), check_existing=True)
        t.image.colorspace_settings.name = 'sRGB' if c == 'diff' else 'Non-Color';l.new(sc.outputs[0], t.inputs['Vector']);tex[c] = t
    norm = n.new('ShaderNodeMixRGB');norm.blend_type = 'DIVIDE';norm.inputs[0].default_value = 1;norm.inputs[2].default_value = (*WALL_DIFFUSE_LINEAR_MEAN, 1)
    l.new(tex['diff'].outputs['Color'], norm.inputs[1])
    bw = n.new('ShaderNodeRGBToBW');l.new(norm.outputs[0], bw.inputs[0])  # luminance pattern only, no beige cast
    paint = n.new('ShaderNodeMixRGB');paint.blend_type = 'MULTIPLY';paint.inputs[0].default_value = 1;paint.inputs[1].default_value = look['colour']
    l.new(bw.outputs[0], paint.inputs[2]);l.new(paint.outputs[0], p.inputs['Base Color'])
    rr = n.new('ShaderNodeMapRange');rr.inputs['From Min'].default_value, rr.inputs['From Max'].default_value = WALL_ROUGHNESS_SOURCE_RANGE
    rr.inputs['To Min'].default_value, rr.inputs['To Max'].default_value = look['roughness_range'];l.new(tex['rough'].outputs['Color'], rr.inputs[0]);l.new(rr.outputs[0], p.inputs['Roughness'])
    nm = n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value = look['normal_strength'];l.new(tex['nor_gl'].outputs['Color'], nm.inputs['Color']);l.new(nm.outputs[0], p.inputs['Normal'])
    R['wall_paint'] = {'asset': WALL_ASSET, **look}


def steel_finishes(R, look, gray):
    if gray:return
    for name, key in [('Tempered spring steel', 'spring_wire'), ('Brushed steel guides', 'guide_steel')]:
        p = bpy.data.materials[name].node_tree.nodes.get('Principled BSDF');f = look[key]
        p.inputs['Base Color'].default_value = (*f['base_color'], 1);p.inputs['Metallic'].default_value = f['metallic'];p.inputs['Roughness'].default_value = f['roughness']
        if 'anisotropic' in f:p.inputs['Anisotropic'].default_value = f['anisotropic']
    R['steel_finishes'] = look


def potted_plant(R, look):
    path = asset(PLANT_FILES[0]);before = set(bpy.data.objects)
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):dst.objects = list(src.objects)
    obs = [ob for ob in dst.objects if ob is not None and ob.type == 'MESH']
    for ob in obs:bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.update()
    for im in bpy.data.images:
        if im.filepath.startswith('//textures/'):im.filepath = str(path.parent / im.filepath[2:]);im.reload()
    root = sg.empty('CC0 scanned potted succulent (Poly Haven potted_plant_04)')
    for ob in obs:
        if ob.parent is None or ob.parent not in obs:
            world = ob.matrix_world.copy();ob.parent = root;ob.matrix_world = world
    bpy.context.view_layer.update()
    pts = [ob.matrix_world @ Vector(c) for ob in obs for c in ob.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]);hi = Vector([max(p[i] for p in pts) for i in range(3)])
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for ob in obs:
        if ob.parent == root:ob.matrix_world = Matrix.Translation(-centre) @ ob.matrix_world
    root.rotation_euler[2] = look['yaw_rad'];root.location = look['base_centre_m']
    bpy.context.view_layer.update()
    # Rest the actual lowest vertex on the support (bound boxes are slightly loose).
    root.location.z += look['base_centre_m'][2] - min((ob.matrix_world @ Vector(v.co)).z for ob in obs for v in ob.data.vertices)
    bpy.context.view_layer.update()
    pts = [ob.matrix_world @ Vector(v.co) for ob in obs for v in ob.data.vertices]
    root['measured_world_dimensions_m'] = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
    root['lowest_point_z_m'] = min(p.z for p in pts);root['support'] = look['support']
    R['potted_plant'] = {'asset': PLANT_ASSET, 'objects': sorted(o.name for o in obs), 'dimensions_m': list(root['measured_world_dimensions_m']),
                         'lowest_point_z_m': root['lowest_point_z_m'], **look}


def wall_socket(R, look):
    """Plain surface-mounted double socket outlet above the skirting, no markings.

    One moulded plate with two real round recesses (cut into the plate) and two
    pin holes at the bottom of each recess; the plate's back face is the wall face.
    """
    white = sg.material('Moulded white PC socket plate', look['plastic_rgb'] + [1], .33)
    sg.micro_surface(white, 2400, .33, .000004, .06)
    hole = sg.material('Socket pin hole shadow', (.010, .010, .010, 1), .85)
    x, y, z = look['centre_m'];w, h, t = look['plate_m'];depth = look['recess_depth_m'];rad = look['recess_radius_m']
    plate = sg.box('Wall double socket plate', (x, y - t / 2, z), (w, t, h), white, .0028)
    parts = [plate]
    for dx in look['recess_offsets_m']:
        cutter = sg.cylinder('Socket recess cutter', (x + dx, y - t, z), rad, 2 * depth, white, 'Y', 0, 64)
        sg.cut_mesh(plate, cutter)
        for px in (-look['pin_spacing_m'] / 2, look['pin_spacing_m'] / 2):
            parts.append(sg.cylinder('Socket pin hole', (x + dx + px, y - t + depth - .00016, z), .0024, .0003, hole, 'Y', 0, 24))
    R['wall_socket'] = {'objects': [o.name for o in parts], **look}


def remove_fill_light(R):
    ob = bpy.data.objects.get('Camera side room fill')
    if ob:bpy.data.objects.remove(ob, do_unlink=True)
    R['removed_lights'] = ['Camera side room fill']


def key_solved_motion(cfg, data, objects):
    """Key every solved frame so Cycles motion blur sees the real sub-frame motion.

    Frame f shows solver row f-1 exactly (as apply_frame does); keys are linear and
    quaternion signs are made continuous, so a 0.25-frame shutter samples the
    solver path between neighbouring rows only.
    """
    frames = len(data['time']);poses = data['body_pose']
    for i, ob in enumerate([*([objects['car'], *objects['wheels']] if objects['car'] else []), objects['baffle']]):
        ob.rotation_mode = 'QUATERNION';ob.animation_data_clear();act = bpy.data.actions.new(ob.name + ' solved motion')
        ob.animation_data_create();ob.animation_data.action = act;prev = None;rows = []
        for f in range(frames):
            q = [float(v) for v in poses[f, i, 3:]]
            if prev is not None and sum(a * b for a, b in zip(q, prev)) < 0:q = [-v for v in q]
            rows.append([float(v) for v in poses[f, i, :3]] + q);prev = q
        for path, idx, col in [('location', k, k) for k in range(3)] + [('rotation_quaternion', k, 3 + k) for k in range(4)]:
            fc = act.fcurves.new(path, index=idx);fc.keyframe_points.add(frames)
            fc.keyframe_points.foreach_set('co', [v for f in range(frames) for v in (f + 1, rows[f][col])])
            for kp in fc.keyframe_points:kp.interpolation = 'LINEAR'
            fc.update()
    helix = objects['helix']
    if helix:
        cu = helix.data;cu.animation_data_clear();act = bpy.data.actions.new('Coil solved length');cu.animation_data_create();cu.animation_data.action = act
        series = [sg.spring_points(cfg, float(data['spring_compression'][f])) for f in range(frames)]
        for j in range(len(series[0])):
            fc = act.fcurves.new(f'splines[0].points[{j}].co', index=0);fc.keyframe_points.add(frames)
            fc.keyframe_points.foreach_set('co', [v for f in range(frames) for v in (f + 1, series[f][j][0])])
            for kp in fc.keyframe_points:kp.interpolation = 'LINEAR'
            fc.update()


def render_quality(R, q):
    sc = bpy.context.scene;cy = sc.cycles
    cy.samples = q['samples'];cy.use_adaptive_sampling = True;cy.adaptive_threshold = q['adaptive_threshold'];cy.adaptive_min_samples = q['adaptive_min_samples']
    cy.use_denoising = True;cy.denoiser = 'OPENIMAGEDENOISE';cy.denoising_input_passes = 'RGB_ALBEDO_NORMAL';cy.denoising_prefilter = 'ACCURATE'
    cy.seed = q['seed'];cy.use_animated_seed = False
    sc.render.use_motion_blur = q['motion_blur'];sc.render.motion_blur_shutter = q['shutter_frames'];sc.render.motion_blur_position = 'CENTER'
    # Blender 4.3: with motion blur, persistent data drops objects that came to rest.
    sc.render.use_persistent_data = q['persistent_data']
    assert not (sc.render.use_motion_blur and sc.render.use_persistent_data)
    R['render_quality'] = q


def apply(cfg, data, objects, gray=False):
    look = cfg['appearance']['finish'];R = {'revision': cfg['appearance'].get('revision')}
    remove_text(R)
    if not gray:plain_book_covers(R, [tuple(c) for c in look['book_cover_rgb']])
    scanned_wall_paint(R, look['wall_paint'], gray)
    steel_finishes(R, look['steel'], gray)
    potted_plant(R, look['potted_plant'])
    wall_socket(R, look['wall_socket'])
    remove_fill_light(R)
    key_solved_motion(cfg, data, objects)
    render_quality(R, look['render_quality'])
    bpy.context.scene['look_record'] = str(R)
    return R
