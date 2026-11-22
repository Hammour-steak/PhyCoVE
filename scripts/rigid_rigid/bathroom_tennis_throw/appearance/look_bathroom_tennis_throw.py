"""Bright Nordic family bathroom on a spring morning, built on the physics planes.

Look: white 15 cm glazed wall tile, grey
matt porcelain hexagon floor tiles, pale oiled oak joinery, black steel shower
fittings, a south window over the oak cabinet with low morning sun coming in,
a freestanding bath under the east window and a frosted window at the far end
of the shower. Everything is authored at K = 2 x real size, like the physics
(see bathroom_room.py). Room geometry lives in ``bathroom_room.py``; this
module adds the daylight, the dressing, the ball, the felt baskets / oak foot
rest standing in for the stool boxes, and the per-frame clearance / occlusion
checks.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import BALL_RADIUS, STOOL_HALF_A, STOOL_HALF_B, STOOL_TAG, KEYS
from bathroom_room import K

MODELS = _pcve_asset('models')
POLYHAVEN = _pcve_asset('polyhaven') / 'bathroom_tennis_throw'

# Optic-yellow felt. The ball is deliberately oversized and saturated so it
# reads at 7-10 px (see the Scene section of the README); the scanned felt map
# only contributes its seam, which a real tennis ball has and which reads as a
# fine pale curve once the ball is more than ~20 px across.
BALL_TINT = (.45, .78, .02, 1.)
SEAM_COLOUR = (.80, .80, .74, 1.)
# Optic-yellow felt is dyed with a fluorescent pigment: under daylight it
# returns more visible light than it receives in that band, which is why a
# tennis ball looks brighter than a white wall next to it. A small emission
# in the felt's own tint stands in for that fluorescence (it is not a lamp:
# 0.18 of the tint, no visible glow).
BALL_FLUORESCENCE = .18

# Morning sun from the east-south-east (compass azimuth, from +y = north
# clockwise towards +x = east), low enough to throw a long patch through the
# south window onto the floor in front of the cabinet.
SUN_AZIMUTH_DEG = 128.0
SUN_ELEVATION_DEG = 31.0
SUN_STRENGTH = 6.0
SKY_STRENGTH = .60
# autumn_hill_view's sun sits at u = 0.6003 (v = 0.579, ~14 deg up) in the
# equirectangular frame (measured: brightest texels of the 2k file) ->
# azimuth atan2(y, x) = (0.5 - u) * 360 deg in the photograph's own frame;
# the photograph is turned so its sun stands where the lamp is.
WINDOW_VIEW = 'autumn_hill_view_2k.hdr'
WINDOW_VIEW_SUN_U = .6003
WINDOW_VIEW_STRENGTH = 1.0

# Anything that is not a physics surface must stay this far from the ball's
# surface in every frame of the case being rendered.
CLEARANCE_M = .02

# Towel dyes (multiplied over the greyed waffle scan).
WHITE, SAGE, SAND = (1.0, 1.0, .97), (.66, .76, .64), (.92, .82, .66)


def _aim(obj, point):
    from mathutils import Vector
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def daylight(bpy, scene, room):
    """Sun lamp + Nishita sky outside; camera rays leaving through the clear
    window see the hill photograph. No lamp inside the room."""
    from mathutils import Vector
    az, el = math.radians(SUN_AZIMUTH_DEG), math.radians(SUN_ELEVATION_DEG)
    towards_sun = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    win = room['windows'][0]          # the south window the sun comes through
    target = Vector(((win['a0'] + win['a1']) / 2, win['inner'], (win['z0'] + win['z1']) / 2))
    data = bpy.data.lights.new('Morning sun', 'SUN')
    data.energy, data.angle, data.color = SUN_STRENGTH, math.radians(.53), (1.0, .93, .84)
    sun = bpy.data.objects.new('Morning sun', data)
    scene.collection.objects.link(sun)
    sun.location = target + 8 * towards_sun
    _aim(sun, target)

    world = bpy.data.worlds.new('Spring morning sky')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    sky.sun_elevation = el
    sky.sun_rotation = math.atan2(towards_sun.x, towards_sun.y)
    sky.air_density, sky.dust_density = 1.0, 1.6
    lighting = nodes['Background']
    links.new(sky.outputs['Color'], lighting.inputs['Color'])
    lighting.inputs['Strength'].default_value = SKY_STRENGTH
    coord = nodes.new('ShaderNodeTexCoord')
    turn = nodes.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    photo_sun = math.radians((.5 - WINDOW_VIEW_SUN_U) * 360)
    turn.inputs['Rotation'].default_value = (0, 0, photo_sun - math.atan2(towards_sun.y, towards_sun.x))
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(POLYHAVEN / WINDOW_VIEW), check_existing=True)
    links.new(coord.outputs['Generated'], turn.inputs['Vector'])
    links.new(turn.outputs['Vector'], photo.inputs['Vector'])
    view = nodes.new('ShaderNodeBackground')
    view.inputs['Strength'].default_value = WINDOW_VIEW_STRENGTH
    links.new(photo.outputs['Color'], view.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(lighting.outputs['Background'], mix.inputs[1])
    links.new(view.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['World Output'].inputs['Surface'])

    # Ground outside: blocks the sky from below for light, invisible to the camera.
    from bathroom_room import box, flat
    ground = box('Ground outside', (-40, -60, -.6), (60, 40, -.3), flat('Sunlit grass outside', (.10, .13, .06), .95))
    ground.visible_camera = False

    def portal(name, centre, size, inward):
        d = bpy.data.lights.new(name, 'AREA')
        d.shape = 'RECTANGLE'
        d.size, d.size_y = size
        d.cycles.is_portal = True
        o = bpy.data.objects.new(name, d)
        scene.collection.objects.link(o)
        o.location = centre
        _aim(o, Vector(centre) + Vector(inward))

    # Only the clear windows get portals: the frosted pane is a diffuse
    # transmitter, which shadow rays through a portal cannot cross anyway.
    for w in room['windows']:
        a, z = (w['a0'] + w['a1']) / 2, (w['z0'] + w['z1']) / 2
        d = w['outer'] - w['inward'] * .01
        centre = (a, d, z) if w['axis'] == 'x' else (d, a, z)
        inward = (0, w['inward'], 0) if w['axis'] == 'x' else (w['inward'], 0, 0)
        portal(f"{w['name']} sky portal", centre, (w['a1'] - w['a0'], w['z1'] - w['z0']), inward)
    return dict(sun_azimuth_deg=SUN_AZIMUTH_DEG, sun_elevation_deg=SUN_ELEVATION_DEG)


# --------------------------------------------------------------- dressing


def place_model(bpy, path, name, props, yaw_deg=0.0, scale=1.0, keep=None, **anchor):
    """Import a glTF, optionally keep only meshes whose name starts with
    ``keep``, turn/scale it and set its bounding box on the anchor
    (x/y = box centre, x_min/x_max/y_min/y_max = faces, z = bottom)."""
    from mathutils import Vector, Matrix
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == 'MESH' and (keep is None or o.name.startswith(keep))]
    if not meshes:
        raise RuntimeError(f'{path.name}: nothing matches {keep!r}')
    deps = bpy.context.evaluated_depsgraph_get()
    baked = []
    for o in meshes:
        mesh = bpy.data.meshes.new_from_object(o.evaluated_get(deps), preserve_all_data_layers=True, depsgraph=deps)
        mesh.transform(o.matrix_world)
        ob = bpy.data.objects.new(f'{name} / {o.name}', mesh)
        bpy.context.scene.collection.objects.link(ob)
        baked.append(ob)
    for o in imported:
        bpy.data.objects.remove(o, do_unlink=True)
    rot = Matrix.Rotation(math.radians(yaw_deg), 4, 'Z') @ Matrix.Scale(scale, 4)
    for ob in baked:
        ob.data.transform(rot)
    pts = [v.co for ob in baked for v in ob.data.vertices]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    shift = Vector((0, 0, 0))
    for axis, i in (('x', 0), ('y', 1)):
        if axis in anchor:
            shift[i] = anchor[axis] - (lo[i] + hi[i]) / 2
        elif axis + '_min' in anchor:
            shift[i] = anchor[axis + '_min'] - lo[i]
        elif axis + '_max' in anchor:
            shift[i] = anchor[axis + '_max'] - hi[i]
    shift.z = anchor.get('z', 0.0) - lo.z
    for ob in baked:
        ob.data.transform(Matrix.Translation(shift))
    props.extend(baked)
    return dict(name=name, bbox_min=list(lo + shift), bbox_max=list(hi + shift))


def folded_towel_stack(bpy, name, base, size, count, props, colours):
    """Folded waffle towels: rounded slabs with the scanned weave (K x real
    size), each a few millimetres off square so the stack does not look
    extruded."""
    from bathroom_room import box
    x, y, z = base
    w, d, h = size
    for i in range(count):
        dx, dy = (.006 * K, -.004 * K, .003 * K)[i % 3], (-.003 * K, .005 * K, -.006 * K)[i % 3]
        t = box(f'{name} {i + 1}', (x - w / 2 + dx, y - d / 2 + dy, z + i * h), (x + w / 2 + dx, y + d / 2 + dy, z + (i + 1) * h - .002 * K),
                waffle(bpy, colours[i % len(colours)]), props=props)
        mod = t.modifiers.new('Soft fold', 'BEVEL')
        mod.width, mod.segments = h * .45, 4
        sub = t.modifiers.new('Cloth softness', 'SUBSURF')
        sub.levels = sub.render_levels = 1


def waffle(bpy, colour):
    """Waffle-weave cotton: the scan (mustard) greyed, lifted from its ~0.4
    luminance to white-towel albedo, then dyed."""
    from bathroom_room import scanned
    name = 'Waffle cotton %.2f %.2f %.2f' % colour
    return bpy.data.materials.get(name) or scanned(name, POLYHAVEN / 'waffle_pique_cotton_diff_1k.jpg', .28 * K,
                                                   roughness_range=(.85, 1.0), normal_strength=.8, grey=True,
                                                   hue_sat_val=(.5, 1.0, 2.0), colour_gain=colour)


def shower_fittings(bpy, props, m):
    """Wall-arm rain shower, thermostatic bar mixer and hand shower on the south
    wall inside the enclosure, black steel, K x real size; all above or beside
    every ball path of edit_bouncier_bathroom (the only case that enters)."""
    from bathroom_room import box, cylinder, FLOOR_Z
    blk = m['black_metal']
    S = -4.770
    xs = 7.70

    def z(h):
        return FLOOR_Z + h * K
    cylinder('Rain shower wall arm', (xs, S + .20 * K, z(2.15)), .011 * K, .40 * K, blk, axis='Y', props=props)
    cylinder('Rain shower head', (xs, S + .42 * K, z(2.135)), .125 * K, .010 * K, blk, verts=64, props=props)
    cylinder('Shower riser', (xs, S + .028 * K, z(1.55)), .011 * K, 1.15 * K, blk, props=props)
    box('Thermostatic bar mixer', (xs - .19 * K, S, z(1.03)), (xs + .19 * K, S + .062 * K, z(1.09)), blk, .012 * K, props)
    cylinder('Mixer handle left', (xs - .22 * K, S + .035 * K, z(1.06)), .026 * K, .05 * K, blk, axis='X', props=props)
    cylinder('Mixer handle right', (xs + .22 * K, S + .035 * K, z(1.06)), .026 * K, .05 * K, blk, axis='X', props=props)
    cylinder('Hand shower', (xs + .32 * K, S + .06 * K, z(1.40)), .022 * K, .24 * K, blk, props=props)


def downlights(bpy, props, ceiling_z):
    """Recessed ceiling downlights, switched off (daylight only)."""
    from bathroom_room import cylinder, flat
    trim = flat('White downlight trim', (.82, .82, .80), .3)
    lens = flat('Downlight diffuser (off)', (.55, .55, .53), .15)
    for x, y in ((-.6, -2.3), (2.4, -3.2), (7.6, -3.4), (2.4, -.2), (7.6, -.4)):
        cylinder('Downlight trim', (x, y, ceiling_z - .002 * K), .052 * K, .004 * K, trim, props=props)
        cylinder('Downlight lens', (x, y, ceiling_z - .0045 * K), .040 * K, .002 * K, lens, props=props)


def dress(bpy, room):
    from bathroom_room import box, cylinder, flat, FLOOR_Z
    props = room['props']
    m = room['materials']
    placed = []
    top = 1.155                          # cabinet top (collider)
    # Two folded towels and a potted calathea on the cabinet top, pushed back
    # towards the wall, away from the throw line 0.3 m north of the cabinet.
    folded_towel_stack(bpy, 'Folded towel', (1.40, -4.45, top), (.30 * K, .22 * K, .045 * K), 2, props,
                       [WHITE, SAGE])
    pot = place_model(bpy, POLYHAVEN / 'planter_pot_clay' / 'planter_pot_clay_1k.gltf', 'Terracotta pot', props,
                      yaw_deg=20.0, scale=K, x=.80, y=-4.45, z=top)
    placed.append(pot)
    rim = pot['bbox_max'][2]
    cylinder('Potting soil', (.80, -4.45, rim - .028 * K), .118 * K, .006 * K, flat('Damp potting soil', (.035, .025, .018), .95),
             props=props)
    plant = place_model(bpy, POLYHAVEN / 'calathea_orbifolia_01' / 'calathea_orbifolia_01_1k.gltf', 'Calathea',
                        props, yaw_deg=-30.0, scale=K, keep='calathea_orbifolia_01_b', x=.80, y=-4.45, z=rim - .03 * K)
    placed.append(plant)
    folded_towel_stack(bpy, 'Shower towel', (10.20, -4.40, .887), (.32 * K, .24 * K, .05 * K), 2, props,
                       [WHITE, SAND])
    # Waffle bath mat on the floor by the bath, well away from every ball path.
    mat = box('Bath mat', (5.30, -1.42, FLOOR_Z), (6.50, -.62, FLOOR_Z + .012 * K), waffle(bpy, WHITE), props=props)
    mat.rotation_euler.z = 0.0
    soft = mat.modifiers.new('Soft edge', 'BEVEL')
    soft.width, soft.segments = .008 * K, 3
    shower_fittings(bpy, props, m)
    downlights(bpy, props, room['ceiling_z'])
    return placed


# --------------------------------------------------------------- environment


def build_environment(bpy, scene):
    from bathroom_colliders import load_colliders
    from bathroom_room import build_room
    room = build_room(load_colliders(), POLYHAVEN)
    room['daylight'] = daylight(bpy, scene, room)
    room['placed'] = dress(bpy, room)
    return room


# --------------------------------------------------------------- low boxes (the 'stools')
#
# The four stool bodies and the two static 'pouf' colliders are boxes 0.22 m
# high (in the GLB they were slippers). At the 2x reading scale they are
# 33-37 x 21-27 x 11 cm objects, so they become things of that size whose
# sides really are flat: grey wool-felt baskets of rolled hand towels by the
# shower entrance (stool_b: a shallow tray of folded washcloths), and an
# oiled-oak foot rest inside the shower. Their outer
# faces are the collider faces, so a ball rolling into one meets felt (or
# oak) exactly where the physics box stops it.

# The two static colliders overlap each other by 14 cm in y; the second basket
# is pouf_right minus that overlap, so both west faces the ball rolls into
# (x 2.920 and 2.965) are real faces.
STATIC_BOXES = {
    'pouf_left': ((2.920, -2.435, .042), (3.660, -2.005, .255)),
    'pouf_right': ((2.965, -2.005, .042), (3.615, -1.595, .255)),
}
BASKET_TOWELS = {'pouf_left': [WHITE, SAGE, WHITE],
                 'pouf_right': [SAND, WHITE],
                 'stool_b': [SAGE, WHITE, SAND]}


def felt(bpy):
    """Grey pressed wool felt: the knitted-fleece scan greyed, with a sheen
    lobe for the fibre fuzz that catches light at the folds."""
    from bathroom_room import scanned
    mat = bpy.data.materials.get('Grey wool felt')
    if mat is None:
        mat = scanned('Grey wool felt', POLYHAVEN / 'knitted_fleece_diff_1k.jpg', .27 * K, roughness_range=(.85, 1.0),
                      normal_strength=.6, hue_sat_val=(.5, .25, 1.15))
        bs = mat.node_tree.nodes['Principled BSDF']
        bs.inputs['Sheen Weight'].default_value = .8
        bs.inputs['Sheen Roughness'].default_value = .5
        bs.inputs['Sheen Tint'].default_value = (.75, .75, .75, 1)
    return mat


def _rounded_rect(lo, hi, rc, n_corner=6, n_side=6):
    """Counter-clockwise rounded rectangle in the xy plane: points, outward
    normals, and for each point how far along its straight side it lies (0 at
    the corners, 1 mid-side) -- which lets the rim slump between corners."""
    import math as m
    cs = [(hi[0] - rc, hi[1] - rc, 0.0), (lo[0] + rc, hi[1] - rc, m.pi / 2),
          (lo[0] + rc, lo[1] + rc, m.pi), (hi[0] - rc, lo[1] + rc, 3 * m.pi / 2)]
    pts, nrm, side = [], [], []
    for k, (cx, cy, a0) in enumerate(cs):
        for i in range(n_corner + 1):
            a = a0 + (m.pi / 2) * i / n_corner
            pts.append((cx + rc * m.cos(a), cy + rc * m.sin(a)))
            nrm.append((m.cos(a), m.sin(a)))
            side.append(0.0)
        nx_, ny_, a1 = cs[(k + 1) % 4][0], cs[(k + 1) % 4][1], a0 + m.pi / 2
        ex, ey = cx + rc * m.cos(a1), cy + rc * m.sin(a1)
        fx, fy = nx_ + rc * m.cos(a1), ny_ + rc * m.sin(a1)
        for i in range(1, n_side):
            t = i / n_side
            pts.append((ex + (fx - ex) * t, ey + (fy - ey) * t))
            nrm.append((m.cos(a1), m.sin(a1)))
            side.append(m.sin(m.pi * t))
    return pts, nrm, side


def felt_basket(bpy, key, lo, hi, towels, shallow=False):
    """Soft open felt basket lofted on the collider box.

    The straight outer walls lie exactly on the collider faces from the floor
    to 0.11 m (the ball meets them at 0.04-0.14 m); corners are rounded at
    2 cm (at most 4 mm off the box where a ball touches near a corner); above
    that the felt leans in and the rolled 2 cm-thick rim slumps between the
    corners, as pressed felt does. Rolled towels lie across it, proud of the
    rim but inside the collider box.

    ``shallow``: a 4 cm-deep (as read) tray of folded washcloths instead. The
    only face of stool_b the ball touches is its far (south) side, where the
    ball comes to rest in edit_heavy_gravity_after_impact; a 22 cm basket
    between it and the camera would hide the ball for the last second of that
    clip, a tray lets its upper half show over the rim.
    """
    from bathroom_room import ring_mesh
    pts, nrm, side = _rounded_rect(lo, hi, .02)
    z0 = lo[2]
    # (inset from the outline, height, slump weight)
    profile = [(.010, .000, 0), (.003, .005, 0), (.0, .018, 0), (.0, .060, 0), (.0, .110, 0),
               (.002, .138, .4), (.006, .156, .8), (.012, .165, 1), (.018, .167, 1), (.023, .162, 1),
               (.025, .148, .8), (.024, .100, .3), (.023, .040, 0), (.028, .020, 0), (.034, .016, 0)]
    if shallow:
        # same section, walls cut down to an 8.3 cm rim (still above the
        # 0.04-0.14 m band where the ball can touch the sides)
        profile = [(d, z if z <= .02 else .02 + (z - .02) * .43, w * .5) for d, z, w in profile]
    rings = []
    for d, z, w in profile:
        ring = []
        for (x, y), (nx, ny), sv in zip(pts, nrm, side):
            dd = d + w * .014 * sv
            ring.append((x - nx * dd, y - ny * dd, z0 + z))
        rings.append(ring)
    shell = ring_mesh(f'{key} / felt basket', rings, felt(bpy), subsurf=2)
    parts = [shell]
    wall = .025
    if shallow:
        from bathroom_room import box
        w_, d_, h_ = hi[0] - lo[0] - 2 * wall - .03, hi[1] - lo[1] - 2 * wall - .03, .028
        cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
        for i in range(2):
            dx, dy = (.006, -.008)[i], (-.004, .006)[i]
            cloth = box(f'{key} / folded washcloth {i + 1}', (cx - w_ / 2 + dx, cy - d_ / 2 + dy, z0 + .016 + i * h_),
                        (cx + w_ / 2 + dx, cy + d_ / 2 + dy, z0 + .016 + (i + 1) * h_ - .002), waffle(bpy, towels[i % len(towels)]))
            fold = cloth.modifiers.new('Soft fold', 'BEVEL')
            fold.width, fold.segments = h_ * .45, 4
            soft = cloth.modifiers.new('Cloth softness', 'SUBSURF')
            soft.levels = soft.render_levels = 1
            parts.append(cloth)
        return parts
    inner_x = hi[0] - lo[0] - 2 * wall
    r = min(.05 * K, (hi[2] - lo[2] - .016) / 2 - .004)
    n = max(1, int(inner_x // (2 * r * .96)))
    pitch = inner_x / n
    for i in range(n):
        cx = lo[0] + wall + pitch * (i + .5)
        parts.append(towel_roll(bpy, f'{key} / rolled towel {i + 1}', (cx, (lo[1] + hi[1]) / 2, z0 + .016 + r * .93),
                                r, hi[1] - lo[1] - 2 * wall - .006, waffle(bpy, towels[i % len(towels)]), phase=1.3 * i + .7))
    return parts


def towel_roll(bpy, name, centre, r, length, mat, phase=0.0, n=28, rings=9):
    """A rolled hand towel lying along y: a spiral lap (radius grows by one
    cloth thickness round the turn, so the loose edge shows as a step), soft
    lumpy creases along its length, rounded squashed ends."""
    import math as m
    from bathroom_room import ring_mesh
    cx, cy, cz = centre
    out = []
    for j in range(rings):
        t = j / (rings - 1)
        y = cy - length / 2 + length * t
        end = m.sin(m.pi * t) ** .35          # rounded ends
        ring = []
        for i in range(n):
            a = 2 * m.pi * i / n
            lap = .09 * (i / n)                 # one cloth thickness per turn
            crease = .055 * m.sin(3 * a + phase + 2.1 * t) * m.sin(m.pi * t) + .025 * m.sin(7 * a - phase * 1.7)
            rr = r * (1 + lap + crease) * (.86 + .14 * end)
            ring.append((cx + rr * m.cos(a + phase), y, cz + rr * m.sin(a + phase) * .92))
        out.append(ring)
    return ring_mesh(name, out, mat, subsurf=2)


def oak_foot_rest(bpy, key, lo, hi, oak, dark):
    """Oiled-oak shower foot rest: slatted top on a solid apron box."""
    from bathroom_room import box
    slat_t = .011 * K
    parts = [box(f'{key} / apron', (lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2] - slat_t), oak, .002 * K)]
    n, gap = 5, .004 * K
    w = (hi[1] - lo[1] - gap * (n - 1)) / n
    for i in range(n):
        y0 = lo[1] + i * (w + gap)
        parts.append(box(f'{key} / slat {i + 1}', (lo[0], y0, hi[2] - slat_t), (hi[0], y0 + w, hi[2]), oak, .0015 * K))
    parts.append(box(f'{key} / slat shadow', (lo[0] + .01 * K, lo[1] + .01 * K, hi[2] - slat_t - .002 * K),
                     (hi[0] - .01 * K, hi[1] - .01 * K, hi[2] - slat_t), dark))
    return parts


def _join(bpy, parts, name):
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:
        bpy.context.view_layer.objects.active = o
        for mod in list(o.modifiers):
            bpy.ops.object.modifier_apply(modifier=mod.name)
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = name
    return obj


def make_objects(bpy, room):
    """Ball and the stool_a and stool_b rigid bodies (centred on their physics
    boxes), plus the two static baskets on the pouf colliders."""
    oak, dark = room['materials']['oak'], room['materials']['grout_dark']
    result = {'tennis_ball': make_ball(bpy)}
    for key in KEYS[1:]:
        h = STOOL_HALF_A if STOOL_TAG[key] == 'a' else STOOL_HALF_B
        lo, hi = (-h[0], -h[1], -h[2]), (h[0], h[1], h[2])
        if key == 'stool_a':           # stands inside the shower
            parts = oak_foot_rest(bpy, key, lo, hi, oak, dark)
        else:
            parts = felt_basket(bpy, key, lo, hi, BASKET_TOWELS.get(key, BASKET_TOWELS['stool_b']),
                                shallow=(key == 'stool_b'))
        result[key] = _join(bpy, parts, key)
    for key, (lo, hi) in STATIC_BOXES.items():
        felt_basket(bpy, key, lo, hi, BASKET_TOWELS[key])
    return result


def make_ball(bpy):
    """tennis_ball.glb inner sphere, put exactly on the physics radius."""
    from mathutils import Vector
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(MODELS / 'tennis_ball.glb'))
    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == 'MESH']
    # The GLB holds the felt sphere (lambert1) and a slightly larger alpha
    # 'fuzz' shell (lambert3); the shell is dropped -- an alpha-cut shell is
    # transparent-bounce noise at this size -- and the fuzz comes from sheen.
    core = min(meshes, key=lambda o: max(o.dimensions))
    deps = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(core.evaluated_get(deps), preserve_all_data_layers=True, depsgraph=deps)
    mesh.transform(core.matrix_world)
    ball = bpy.data.objects.new('tennis_ball', mesh)
    bpy.context.scene.collection.objects.link(ball)
    for o in imported:
        bpy.data.objects.remove(o, do_unlink=True)
    pts = [v.co.copy() for v in mesh.vertices]
    centre = sum(pts, Vector()) / len(pts)
    for v in mesh.vertices:
        v.co -= centre
    bpy.context.view_layer.objects.active = ball
    sub = ball.modifiers.new('Round outline', 'SUBSURF')
    sub.levels = sub.render_levels = 2
    bpy.context.view_layer.objects.active = ball
    ball.select_set(True)
    bpy.ops.object.modifier_apply(modifier=sub.name)
    for v in ball.data.vertices:
        v.co = v.co.normalized() * BALL_RADIUS
    for poly in ball.data.polygons:
        poly.use_smooth = True
    for mat in ball.data.materials:
        if mat and mat.use_nodes:
            _felt(mat)
    return ball


def _felt(mat):
    """Optic-yellow felt with the scanned seam, sheen fuzz and fibre bump."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    scan = None
    if bs.inputs['Base Color'].is_linked:
        scan = bs.inputs['Base Color'].links[0].from_node
    for socket in ('Base Color', 'Metallic', 'Roughness', 'Normal', 'Emission Color', 'Emission Strength', 'Alpha'):
        for link in list(bs.inputs[socket].links):
            links.remove(link)
    bs.inputs['Metallic'].default_value = 0.0
    bs.inputs['Roughness'].default_value = .9
    bs.inputs['Alpha'].default_value = 1.0
    colour_out = None
    if scan is not None and scan.type == 'TEX_IMAGE':
        # Seam mask: the scan's felt is saturated yellow-green, the seam grey.
        hsv = nodes.new('ShaderNodeSeparateColor')
        hsv.mode = 'HSV'
        links.new(scan.outputs['Color'], hsv.inputs[0])
        seam = nodes.new('ShaderNodeMapRange')
        links.new(hsv.outputs[1], seam.inputs['Value'])
        seam.inputs['From Min'].default_value, seam.inputs['From Max'].default_value = .25, .45
        seam.inputs['To Min'].default_value, seam.inputs['To Max'].default_value = 1.0, 0.0
        mix = nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        links.new(seam.outputs['Result'], mix.inputs['Factor'])
        mix.inputs['A'].default_value = BALL_TINT
        mix.inputs['B'].default_value = SEAM_COLOUR
        colour_out = mix.outputs['Result']
        links.new(colour_out, bs.inputs['Base Color'])
        glow = nodes.new('ShaderNodeMath')
        glow.operation = 'MULTIPLY'
        links.new(seam.outputs['Result'], glow.inputs[0])
        glow.inputs[1].default_value = -BALL_FLUORESCENCE
        glow_add = nodes.new('ShaderNodeMath')
        glow_add.operation = 'ADD'
        links.new(glow.outputs[0], glow_add.inputs[0])
        glow_add.inputs[1].default_value = BALL_FLUORESCENCE
        links.new(glow_add.outputs[0], bs.inputs['Emission Strength'])
    else:
        bs.inputs['Base Color'].default_value = BALL_TINT
        bs.inputs['Emission Strength'].default_value = BALL_FLUORESCENCE
    bs.inputs['Emission Color'].default_value = BALL_TINT
    bs.inputs['Sheen Weight'].default_value = .6
    bs.inputs['Sheen Roughness'].default_value = .45
    bs.inputs['Sheen Tint'].default_value = (.85, .95, .55, 1)
    coord = nodes.new('ShaderNodeTexCoord')
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 900
    noise.inputs['Detail'].default_value = 3
    links.new(coord.outputs['Object'], noise.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .35
    bump.inputs['Distance'].default_value = .0004
    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bs.inputs['Normal'])


# --------------------------------------------------------------- checks


def ball_samples(data, per_frame=8):
    """Ball centres along the case, linearly interpolated between frames (the
    flight covers up to 0.58 m per frame, so frame samples alone would skip)."""
    out = []
    frames = data['frames']
    for a, b in zip(frames, frames[1:] + frames[-1:]):
        pa, pb = a['tennis_ball']['location'], b['tennis_ball']['location']
        for k in range(per_frame):
            t = k / per_frame
            out.append((a['frame_index'], [pa[i] + (pb[i] - pa[i]) * t for i in range(3)]))
    return out


def check_clearance(bpy, room, data):
    """Every prop (anything not a physics surface) stays >= 2 cm from the ball."""
    from mathutils.bvhtree import BVHTree
    deps = bpy.context.evaluated_depsgraph_get()
    samples = ball_samples(data)
    worst = {}
    for obj in room['props']:
        tree = BVHTree.FromObject(obj, deps)
        best = (1e9, None)
        for frame, c in samples:
            hit = tree.find_nearest(c, 2.0)
            if hit[0] is not None:
                gap = hit[3] - BALL_RADIUS
                if gap < best[0]:
                    best = (gap, frame)
        worst[obj.name] = best
        if best[0] < CLEARANCE_M:
            raise RuntimeError(f'ball passes within {best[0]:.3f} m of prop {obj.name!r} at frame {best[1]}')
    tight = sorted(((g, f, n) for n, (g, f) in worst.items() if g < 1.0))[:6]
    print('[look] prop clearance OK; tightest: ' + ', '.join(f'{n} {g:.3f} m (f{f})' for g, f, n in tight), flush=True)
    return {n: round(g, 4) for n, (g, f) in worst.items() if g < 1.0}


def check_occlusion(bpy, scene, camera, room, data):
    """No prop may stand between the camera and the ball (centre + 4 rim points)."""
    from mathutils import Vector
    props = {o.name for o in room['props']}
    see_through = {o.name for o in bpy.data.objects if o.type == 'MESH' and o.data.materials and
                   all(m is not None and m.name.startswith('Clear shower glass') or (m is not None and m.name == 'Float glass edge')
                       for m in o.data.materials)}
    deps = bpy.context.evaluated_depsgraph_get()
    cam = camera.matrix_world.translation
    blocked = []
    for f in data['frames']:
        c = Vector(f['tennis_ball']['location'])
        view = (c - cam).normalized()
        side = view.cross(Vector((0, 0, 1))).normalized()
        up = side.cross(view).normalized()
        for p in (c, c + side * BALL_RADIUS * .7, c - side * BALL_RADIUS * .7, c + up * BALL_RADIUS * .7, c - up * BALL_RADIUS * .7):
            origin, left = cam.copy(), (p - cam).length - BALL_RADIUS * .2
            direction = (p - cam).normalized()
            for _ in range(16):          # step through the clear shower panes
                hit, loc, nrm, idx, obj, mat = scene.ray_cast(deps, origin, direction, distance=left)
                if not hit:
                    break
                if obj.name in props:
                    blocked.append((f['frame_index'], obj.name))
                    break
                if obj.name not in see_through:
                    break
                step = (loc - origin).length + 1e-4
                origin, left = loc + direction * 1e-4, left - step
    if blocked:
        raise RuntimeError(f'props hide the ball: {sorted(set(blocked))[:8]}')
    print('[look] no prop occludes the ball', flush=True)
