"""A physics teaching-lab bench against a painted brick wall, and the two rigid bodies.

Only geometry and appearance live here. Nothing in this module knows about
physics parameters, so a mass or speed edit changes the clip without touching
a single material, and the collision shapes in ``simulate_pendulum_box_collision.py``
stay the authority on size and contact.

The set is a real room at real scale, lit only by what such a room has:

* a 2.6 m lab bench with a lacquered sapele worktop (Poly Haven
  ``sapele_veneer_02``). The worktop slab *is* the solver's bench slab
  (``BENCH_SIZE`` centred under ``TABLE_Z``), so the block slides on the surface
  the camera sees. The bench's back edge meets the wall at ``WALL_Y``;
* an old painted brick wall (Poly Haven ``painted_worn_brick``) behind a
  sapele upstand;
* a retort stand whose clamp holds the thread at ``scene_geometry.PIVOT``, so
  the drawn thread leaves from the point the constraint hangs from;
* old demonstration and timing kit from Poly Haven scans along the back of the
  bench (a twin-bell alarm clock, a brass pocket compass and a
  pair of binder notebooks), all behind the block's lane;
* ceiling LED troffers whose diffusers are the emitters, and low daylight
  through two windows in the left wall (a sun lamp and a Nishita sky seen through
  window portals). Nothing that emits is in frame and there are no light cards.

The camera is the scenario's orthographic camera. Every camera ray is parallel,
so an environment map seen through a window would collapse to one flat colour;
that is why the background is a wall and the windows are out of frame.

The dressing is not simulated, so ``verify_dressing`` checks it against the
trajectory being rendered: every static prop must stay at least
``PROP_CLEARANCE`` from the block, the bob and the thread on every frame, and
no prop may stand between the camera and either body while it is in frame.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
from pcve_blender_compat import set_shader_input
from pcve_assets import asset as _pcve_asset
import math
from scene_geometry import (
    BENCH_SIZE, BOB_RADIUS, BOX_SIZE, PENDULUM_LENGTH, PIVOT, TABLE_Z)

ENVIRONMENT_THEME = 'physics_teaching_lab_painted_brick'

# The visible bench top must be the same surface the solver drops the block on.
BENCH_TOP = TABLE_Z
WALL_Y = BENCH_SIZE[1] / 2          # the bench is pushed against the back wall
STAND = (0.40, 0.19)                # foot of the retort stand, 8 cm behind the block's lane
STAND_TOP = PIVOT[2] + .055
THREAD_RADIUS = .0006

# Room shell. The heavy-bob edit knocks the block back off the left end of the
# bench onto the floor near x = -1.67, so nothing but the floor stands there.
ROOM_X = (-3.4, 3.4)
ROOM_FRONT_Y = -3.2
CEILING_Z = 3.0
WINDOW_SILL, WINDOW_HEAD = .90, 2.45
LAB_WINDOWS = ((-3.1, -2.2), (-1.9, -.3))      # spans along y in the left wall
# Low autumn-afternoon sun from the left windows, heading towards +x and +y so
# that it rakes across the bench and the shadows fall towards the wall. With
# these numbers the second window's light lands on the block's lane and on
# the wall behind the pendulum.
SUN_ELEVATION_DEG = 17.
SUN_HEADING_DEG = 24.               # direction of travel, measured from +x to +y
SUN_STRENGTH = 5.
SKY_STRENGTH = .30
TROFFER_STRENGTH = 6.

PROP_CLEARANCE = .02                # metres, from any moving body or the thread
THREAD_TIE_OFF = .04                # thread length inside/next to the arm clamp

TEXTURE_DIR = _pcve_asset('') / 'polyhaven' / 'pendulum_box_collision'
# Published widths of the Poly Haven scans, in metres.
PAINTED_BRICK_M = 1.8
SAPELE_M = 1.0
COATED_PINE_M = .74


# --------------------------------------------------------------- materials


def _material(bpy, name, color, rough=.6, metallic=0., coat=0., coat_rough=.2,
              noise_bump=0., noise_scale=200., bump_distance=.0002):
    """Plain Principled surface with an optional fine relief."""
    material = bpy.data.materials.new(name); material.use_nodes = True
    nodes = material.node_tree.nodes; links = material.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1.)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metallic
    if coat:
        set_shader_input(bsdf, 'Coat Weight', coat)
        set_shader_input(bsdf, 'Coat Roughness', coat_rough)
    if noise_bump:
        coord = nodes.new('ShaderNodeTexCoord')
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = noise_scale
        noise.inputs['Detail'].default_value = 4.
        links.new(coord.outputs['Object'], noise.inputs['Vector'])
        bump = nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = noise_bump
        bump.inputs['Distance'].default_value = bump_distance
        links.new(noise.outputs['Fac'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return material


def _scanned_material(bpy, name, stem, tile_m, rotate_deg=0., rough_range=None,
                      normal_strength=.8, coat=0., coat_rough=.2, hsv=None):
    """A Poly Haven scan (colour, roughness, OpenGL normal) at its real size.

    Box projection in object space, so every face of a slab or a block gets
    the scan at the same metric scale. ``rotate_deg`` turns it about Z;
    ``hsv`` = (hue, saturation, value) adjusts the scan's colour (0.5, 1, 1 = unchanged).
    """
    material = bpy.data.materials.new(name); material.use_nodes = True
    nodes = material.node_tree.nodes; links = material.node_tree.links
    bsdf = nodes['Principled BSDF']
    coord = nodes.new('ShaderNodeTexCoord'); mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / tile_m,) * 3
    mapping.inputs['Rotation'].default_value = (0., 0., math.radians(rotate_deg))
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])

    def scan(kind, colour):
        node = nodes.new('ShaderNodeTexImage'); node.projection = 'BOX'; node.projection_blend = .15
        node.image = bpy.data.images.load(str(TEXTURE_DIR / f'{stem}_{kind}_2k.jpg'), check_existing=True)
        if not colour:
            node.image.colorspace_settings.name = 'Non-Color'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node.outputs['Color']

    colour = scan('diff', True)
    if hsv is not None:
        adjust = nodes.new('ShaderNodeHueSaturation')
        for socket, value in zip(('Hue', 'Saturation', 'Value'), hsv):
            adjust.inputs[socket].default_value = value
        links.new(colour, adjust.inputs['Color']); colour = adjust.outputs['Color']
    links.new(colour, bsdf.inputs['Base Color'])
    rough = scan('rough', False)
    if rough_range is not None:
        remap = nodes.new('ShaderNodeMapRange')
        remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = rough_range
        links.new(rough, remap.inputs['Value']); rough = remap.outputs['Result']
    links.new(rough, bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value = normal_strength
    links.new(scan('nor_gl', False), normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    if coat:
        set_shader_input(bsdf, 'Coat Weight', coat)
        set_shader_input(bsdf, 'Coat Roughness', coat_rough)
    return material


# ------------------------------------------------------------------- meshes


def _cube_mesh(bpy, name, size):
    """A real-world-sized cube mesh, so Object texture coordinates stay metric."""
    x, y, z = (value * .5 for value in size)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
                      (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)], [],
                     [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                      (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    mesh.update()
    return mesh


def _tube_mesh(bpy, name, radius, length, segments=48):
    import bmesh
    mesh = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius, depth=length)
    bm.to_mesh(mesh); bm.free(); mesh.update()
    return mesh


def _sphere_mesh(bpy, name, radius, segments=64, rings=40):
    import bmesh
    mesh = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    bm.to_mesh(mesh); bm.free(); mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return mesh


def _import_scan(bpy, scene, folder, name, location, yaw=0.):
    """Import a Poly Haven glTF at its published (metric) size and seat it.

    The model is joined into one object, turned about Z by ``yaw`` and moved so
    its bounding box is centred on ``location`` in x/y with its lowest point at
    ``location[2]``. Poly Haven models are Y-up glTF with their front towards
    glTF +Z, which the importer turns into Blender -Y.
    """
    from mathutils import Matrix, Vector
    path = TEXTURE_DIR / folder / f'{folder}_1k.gltf'
    if not path.is_file():
        raise FileNotFoundError(path)
    existing = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in existing]
    parts = [obj for obj in imported if obj.type == 'MESH']
    if not parts:
        raise RuntimeError(f'{path} contained no mesh geometry')
    bpy.context.view_layer.update()
    for obj in scene.objects:
        obj.select_set(False)
    for part in parts:
        world = part.matrix_world.copy(); part.parent = None; part.matrix_world = world
        part.select_set(True)
    for stray in [obj for obj in imported if obj.type != 'MESH']:
        bpy.data.objects.remove(stray, do_unlink=True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    prop = bpy.context.view_layer.objects.active
    prop.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    prop.rotation_mode = 'XYZ'
    prop.matrix_world = Matrix.Rotation(yaw, 4, 'Z')
    bpy.context.view_layer.update()
    corners = [prop.matrix_world @ Vector(corner) for corner in prop.bound_box]
    low = Vector(tuple(min(c[i] for c in corners) for i in range(3)))
    high = Vector(tuple(max(c[i] for c in corners) for i in range(3)))
    prop.location += Vector((location[0] - (low.x + high.x) / 2,
                             location[1] - (low.y + high.y) / 2, location[2] - low.z))
    bpy.context.view_layer.update()
    prop['asset_path'] = f'assets/polyhaven/pendulum_box_collision/{folder}'
    # glTF ships the clock's dial cover as an alpha-blended surface, which
    # Cycles renders as an opaque dark disc; a real cover is thin clear glass.
    for slot in prop.material_slots:
        if slot.material is not None and 'glass' in slot.material.name.lower():
            slot.material = _thin_glass(bpy, f'{name} glass')
    return prop


def _thin_glass(bpy, name):
    """A clear pane with no thickness: Fresnel-weighted gloss over full transmission."""
    material = bpy.data.materials.new(name); material.use_nodes = True
    nodes = material.node_tree.nodes; links = material.node_tree.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    clear = nodes.new('ShaderNodeBsdfTransparent')
    gloss = nodes.new('ShaderNodeBsdfGlossy'); gloss.inputs['Roughness'].default_value = .03
    fresnel = nodes.new('ShaderNodeLayerWeight'); fresnel.inputs['Blend'].default_value = .12
    mix = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fresnel'], mix.inputs[0])
    links.new(clear.outputs[0], mix.inputs[1]); links.new(gloss.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs['Surface'])
    return material



# -------------------------------------------------------------------- set


def build_room(bpy, data):
    """Build the lab, the block and the bob.

    Returns ``(objects, rig)``: ``objects`` maps the simulation's body ids to the
    empties the renderer keyframes, ``rig`` carries the thread that has to be
    aimed at the bob every frame and the pivot it hangs from.
    """
    from mathutils import Vector
    scene = bpy.context.scene

    def mat(name, color, **kw):
        return _material(bpy, name, color, **kw)

    worktop = _scanned_material(bpy, 'Lacquered sapele worktop', 'sapele_veneer_02', SAPELE_M,
                                rough_range=(.30, .52), normal_strength=.35, coat=.35, coat_rough=.16,
                                hsv=(.5, 1.0, .62))
    brick = _scanned_material(bpy, 'Painted brick wall', 'painted_worn_brick', PAINTED_BRICK_M,
                              normal_strength=.9, hsv=(.5, .70, 1.12))
    # The coated-pine scan is a honey-toned varnished board; a bare pine lab
    # block is paler and less saturated.
    pine = _scanned_material(bpy, 'Pine block', 'coated_pine', COATED_PINE_M,
                             rough_range=(.50, .70), normal_strength=.45, hsv=(.525, .62, 2.0))
    plaster = mat('Painted plaster', (.62, .62, .60), rough=.85, noise_bump=.04)
    ceiling = mat('Ceiling tile', (.72, .72, .70), rough=.9)
    vinyl = mat('Grey vinyl floor', (.20, .21, .21), rough=.45, noise_bump=.02, noise_scale=60.)
    carcass = mat('Grey laminate carcass', (.30, .31, .31), rough=.42)
    plinth_black = mat('Black vinyl plinth', (.012, .012, .012), rough=.6)
    frame_paint = mat('Powder-coated window frame', (.78, .78, .76), rough=.35)
    zinc = mat('Zinc-plated rod', (.70, .71, .72), rough=.22, metallic=1.,
               noise_bump=.02, noise_scale=500., bump_distance=.00004)
    hammertone = mat('Hammertone stand foot', (.030, .045, .062), rough=.42, coat=.25,
                     coat_rough=.3, noise_bump=.6, noise_scale=140., bump_distance=.0005)
    die_cast = mat('Die-cast boss head', (.36, .37, .38), rough=.45, metallic=.9,
                   noise_bump=.15, noise_scale=300., bump_distance=.0001)
    rubber = mat('Rubber foot', (.025, .025, .027), rough=.9)
    # Polished, not mirror: a 48 mm chrome ball shows the room in a soft blur.
    steel_ball = mat('Polished steel bob', (.62, .62, .63), rough=.12, metallic=1.,
                     noise_bump=.004, noise_scale=600., bump_distance=.00003)
    eyelet_steel = mat('Eyelet steel', (.55, .55, .56), rough=.3, metallic=1.)
    # Dark braided line: it has to read against the cream painted brick.
    cotton = mat('Braided pendulum line', (.045, .043, .042), rough=.75)

    def tag(obj, kind):
        obj['pcve_role'] = kind
        return obj

    def cube(name, loc, size, material, parent=None, bevel=.002, rotation=None, kind='prop'):
        obj = bpy.data.objects.new(name, _cube_mesh(bpy, name, size))
        scene.collection.objects.link(obj); obj.location = loc; obj.data.materials.append(material)
        if bevel:
            modifier = obj.modifiers.new('Soft manufactured edges', 'BEVEL')
            modifier.width = bevel; modifier.segments = 4
            obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
        if rotation is not None:
            obj.rotation_euler = rotation
        if parent:
            obj.parent = parent
        return tag(obj, kind)

    def rod(name, start, end, radius, material, segments=32, kind='prop'):
        """Cylinder spanning two points; used for the stand, arm and thread."""
        begin = Vector(start); finish = Vector(end); direction = finish - begin
        obj = bpy.data.objects.new(name, _tube_mesh(bpy, name, radius, direction.length, segments))
        scene.collection.objects.link(obj); obj.data.materials.append(material)
        obj.location = (begin + finish) / 2
        obj.rotation_mode = 'QUATERNION'
        obj.rotation_quaternion = direction.to_track_quat('Z', 'Y')
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        return tag(obj, kind)

    # --- room shell -----------------------------------------------------
    x0, x1 = ROOM_X
    cube('Lab floor', (0, (ROOM_FRONT_Y + WALL_Y) / 2, -.05), (x1 - x0, WALL_Y - ROOM_FRONT_Y, .1),
         vinyl, bevel=0, kind='contact')
    cube('Painted brick wall', (0, WALL_Y + .11, CEILING_Z / 2), (x1 - x0, .22, CEILING_Z), brick, bevel=0)
    cube('Front wall', (0, ROOM_FRONT_Y - .1, CEILING_Z / 2), (x1 - x0, .2, CEILING_Z), plaster, bevel=0)
    cube('Right wall', (x1 + .1, (ROOM_FRONT_Y + WALL_Y) / 2, CEILING_Z / 2),
         (.2, WALL_Y - ROOM_FRONT_Y, CEILING_Z), plaster, bevel=0)
    cube('Ceiling', (0, (ROOM_FRONT_Y + WALL_Y) / 2, CEILING_Z + .05),
         (x1 - x0, WALL_Y - ROOM_FRONT_Y, .1), ceiling, bevel=0)
    # Left wall with two window openings (sills, heads and piers around them).
    wx = x0 - .1; (a0, a1), (b0, b1) = LAB_WINDOWS
    for name, y_lo, y_hi, z_lo, z_hi in (
            ('Left wall front pier', ROOM_FRONT_Y, a0, 0, CEILING_Z),
            ('Left wall middle pier', a1, b0, 0, CEILING_Z),
            ('Left wall back pier', b1, WALL_Y, 0, CEILING_Z),
            ('Left wall under first window', a0, a1, 0, WINDOW_SILL),
            ('Left wall under second window', b0, b1, 0, WINDOW_SILL),
            ('Left wall over first window', a0, a1, WINDOW_HEAD, CEILING_Z),
            ('Left wall over second window', b0, b1, WINDOW_HEAD, CEILING_Z)):
        cube(name, (wx, (y_lo + y_hi) / 2, (z_lo + z_hi) / 2), (.2, y_hi - y_lo, z_hi - z_lo),
             plaster, bevel=0)
    for lo, hi in LAB_WINDOWS:
        # Frame and one transom per opening; open, unglazed holes are enough
        # because the windows are never in frame.
        for name, loc, size in (
                ('Window frame head', ((wx, (lo + hi) / 2, WINDOW_HEAD - .03)), (.08, hi - lo, .06)),
                ('Window frame sill', ((wx, (lo + hi) / 2, WINDOW_SILL + .03)), (.08, hi - lo, .06)),
                ('Window frame jamb', ((wx, lo + .03, (WINDOW_SILL + WINDOW_HEAD) / 2)),
                 (.08, .06, WINDOW_HEAD - WINDOW_SILL)),
                ('Window frame jamb', ((wx, hi - .03, (WINDOW_SILL + WINDOW_HEAD) / 2)),
                 (.08, .06, WINDOW_HEAD - WINDOW_SILL)),
                ('Window mullion', ((wx, (lo + hi) / 2, (WINDOW_SILL + WINDOW_HEAD) / 2)),
                 (.06, .05, WINDOW_HEAD - WINDOW_SILL)),
                ('Window transom', ((wx, (lo + hi) / 2, WINDOW_HEAD - .30)), (.06, hi - lo, .05))):
            cube(name, loc, size, frame_paint, bevel=.004)

    # --- bench ----------------------------------------------------------
    # The worktop's upper face is exactly TABLE_Z: it is the slab the solver
    # uses, so the block never floats or sinks on screen.
    cube('Sapele worktop', (0, 0, BENCH_TOP - BENCH_SIZE[2] / 2), BENCH_SIZE, worktop, bevel=.003,
         kind='contact')
    # Cupboard carcass under the worktop, set back 4 cm from the front edge and
    # 6 cm from each end (the heavy-bob block tips off the left end).
    length = BENCH_SIZE[0] - .12
    cube('Bench carcass', (0, .02, (BENCH_TOP - BENCH_SIZE[2] + .10) / 2),
         (length, BENCH_SIZE[1] - .04, BENCH_TOP - BENCH_SIZE[2] - .10), carcass, bevel=.002)
    for index in range(4):
        door_x = -length / 2 + length * (index + .5) / 4
        cube('Cupboard door', (door_x, -BENCH_SIZE[1] / 2 + .025, (BENCH_TOP - BENCH_SIZE[2] + .12) / 2),
             (length / 4 - .006, .018, BENCH_TOP - BENCH_SIZE[2] - .14), carcass, bevel=.002)
    cube('Bench plinth', (0, .03, .05), (length - .02, BENCH_SIZE[1] - .08, .10), plinth_black, bevel=0)
    # Sapele upstand where the worktop meets the wall.
    cube('Worktop upstand', (0, WALL_Y - .009, BENCH_TOP + .035), (BENCH_SIZE[0], .018, .07),
         worktop, bevel=.002)

    # --- retort stand ---------------------------------------------------
    cube('Retort stand foot', (STAND[0], STAND[1], BENCH_TOP + .0085), (.24, .15, .015),
         hammertone, bevel=.005)
    for dx, dy in ((-.10, -.06), (.10, -.06), (-.10, .06), (.10, .06)):
        rod('Foot pad', (STAND[0] + dx, STAND[1] + dy, BENCH_TOP),
            (STAND[0] + dx, STAND[1] + dy, BENCH_TOP + .0012), .009, rubber)
    rod('Retort rod', (STAND[0], STAND[1], BENCH_TOP + .014),
        (STAND[0], STAND[1], STAND_TOP), .0065, zinc)
    cube('Boss head', (STAND[0], STAND[1], PIVOT[2]), (.034, .030, .044), die_cast, bevel=.004)
    rod('Boss thumbscrew', (STAND[0] + .017, STAND[1], PIVOT[2] + .010),
        (STAND[0] + .036, STAND[1], PIVOT[2] + .010), .0035, zinc, segments=16)
    rod('Boss thumbscrew head', (STAND[0] + .036, STAND[1], PIVOT[2] + .010),
        (STAND[0] + .042, STAND[1], PIVOT[2] + .010), .009, die_cast, segments=24)
    # Cross-arm along -x at the stand's y, then a double boss and a short rod
    # along -y to the pendulum clamp, so the drawn thread starts exactly where
    # the solver's point constraint is anchored. Arriving square to the swing
    # plane keeps the arm clear of the thread even at the fast-block edit's
    # 83-degree swing; a diagonal arm straight to the pivot came within 7 mm.
    arm_end = (PIVOT[0] - .03, STAND[1], PIVOT[2])
    rod('Cross arm', (STAND[0], STAND[1], PIVOT[2]), arm_end, .0045, zinc)
    cube('Double boss', (PIVOT[0], STAND[1], PIVOT[2]), (.026, .030, .040), die_cast, bevel=.003)
    rod('Double boss thumbscrew', (PIVOT[0], STAND[1], PIVOT[2] + .020),
        (PIVOT[0], STAND[1], PIVOT[2] + .032), .0035, zinc, segments=16)
    rod('Clamp rod', (PIVOT[0], STAND[1], PIVOT[2]), (PIVOT[0], PIVOT[1] + .008, PIVOT[2]), .004, zinc)
    cube('Pendulum clamp', (PIVOT[0], PIVOT[1], PIVOT[2]), (.016, .018, .018), die_cast, bevel=.002)

    # --- bench dressing (kept clear of the block's lane) ----------------
    # Old demonstration and timing kit along the back of the bench, turned a
    # little towards the camera. Nothing tall: the low sun would throw a tall prop's shadow
    # across the wall behind the pendulum. Nothing stands in front of the lane.
    for folder, name, location, yaw in (
            ('alarm_clock_01', 'Twin-bell alarm clock (Poly Haven)', (-.50, .36, BENCH_TOP), 18.),
            ('seadogs_compass', 'Brass pocket compass (Poly Haven)', (-.29, .33, BENCH_TOP), 30.),
            ('binder_notebook', 'Binder notebooks (Poly Haven)', (.30, .38, BENCH_TOP), 4.)):
        tag(_import_scan(bpy, scene, folder, name, location, yaw=math.radians(yaw)), 'prop')

    # --- the two rigid bodies -------------------------------------------
    objects = {}
    box_root = bpy.data.objects.new('box', None); scene.collection.objects.link(box_root)
    objects['box'] = box_root
    cube('Pine block', (0, 0, 0), BOX_SIZE, pine, box_root, bevel=.0025, kind='moving')

    bob_root = bpy.data.objects.new('bob', None); scene.collection.objects.link(bob_root)
    objects['bob'] = bob_root
    ball = bpy.data.objects.new('Steel bob', _sphere_mesh(bpy, 'Steel bob', BOB_RADIUS))
    scene.collection.objects.link(ball); ball.parent = bob_root; ball.data.materials.append(steel_ball)
    tag(ball, 'moving')

    # The thread and its eyelet live in the rod's frame, not the ball's: a real
    # bob turns freely on a swivel, so the eyelet must not whirl with the spin
    # the contact friction gives the ball.
    thread_obj = rod('Pendulum thread', PIVOT, (0, 0, PIVOT[2] - PENDULUM_LENGTH), THREAD_RADIUS,
                     cotton, segments=8, kind='moving')
    eyelet = bpy.data.objects.new('Eyelet', _tube_mesh(bpy, 'Eyelet', .0045, .010, 12))
    scene.collection.objects.link(eyelet); eyelet.data.materials.append(eyelet_steel)
    eyelet.parent = thread_obj; eyelet.location = (0, 0, PENDULUM_LENGTH / 2 - BOB_RADIUS - .001)
    tag(eyelet, 'moving')
    return objects, dict(thread=thread_obj, pivot=Vector(PIVOT), thread_length=PENDULUM_LENGTH)


def configure_lighting(bpy, scene):
    """The lab's own light: ceiling LED troffers and low sun through the left windows."""
    from mathutils import Vector
    world = bpy.data.worlds.new('Afternoon sky'); world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky'); sky.sky_type = 'NISHITA'; sky.sun_disc = False
    sky.sun_elevation = math.radians(SUN_ELEVATION_DEG)
    # Nishita measures the sun's azimuth from +Y towards +X; the sun sits
    # opposite its direction of travel.
    heading = math.radians(SUN_HEADING_DEG)
    sky.sun_rotation = math.atan2(-math.cos(heading), -math.sin(heading))
    sky.air_density, sky.dust_density = 1., 2.
    links.new(sky.outputs['Color'], nodes['Background'].inputs['Color'])
    nodes['Background'].inputs['Strength'].default_value = SKY_STRENGTH
    scene.world = world

    elevation = math.radians(SUN_ELEVATION_DEG)
    travel = Vector((math.cos(elevation) * math.cos(heading), math.cos(elevation) * math.sin(heading),
                     -math.sin(elevation)))
    sun_data = bpy.data.lights.new('Afternoon sun', 'SUN')
    sun_data.energy = SUN_STRENGTH; sun_data.angle = math.radians(.6)
    sun_data.color = (1., .93, .84)
    sun = bpy.data.objects.new('Afternoon sun', sun_data); scene.collection.objects.link(sun)
    sun.rotation_euler = travel.to_track_quat('-Z', 'Y').to_euler()
    sun.location = (-6., -3., 4.)

    for lo, hi in LAB_WINDOWS:
        data = bpy.data.lights.new('Window sky portal', 'AREA'); data.shape = 'RECTANGLE'
        data.size, data.size_y = hi - lo, WINDOW_HEAD - WINDOW_SILL; data.cycles.is_portal = True
        portal = bpy.data.objects.new('Window sky portal', data); scene.collection.objects.link(portal)
        portal.location = (ROOM_X[0] - .2, (lo + hi) / 2, (WINDOW_SILL + WINDOW_HEAD) / 2)
        portal.rotation_euler = Vector((1., 0., 0.)).to_track_quat('-Z', 'Y').to_euler()

    housing = _material(bpy, 'Troffer housing', (.80, .80, .78), rough=.45)
    diffuser = _material(bpy, 'Troffer opal diffuser', (.9, .9, .9), rough=.6)
    bsdf = diffuser.node_tree.nodes['Principled BSDF']
    set_shader_input(bsdf, 'Emission Color', (1., .955, .90, 1.))   # about 4000 K
    set_shader_input(bsdf, 'Emission Strength', TROFFER_STRENGTH)
    for x in (-1.8, .6, 3.0):
        for y in (-2.2, -.6):
            for name, loc, size, material in (
                    ('Troffer housing', (x - .6, y, CEILING_Z - .015), (.60, .60, .03), housing),
                    ('Troffer diffuser', (x - .6, y, CEILING_Z - .032), (.56, .56, .004), diffuser)):
                obj = bpy.data.objects.new(name, _cube_mesh(bpy, name, size))
                scene.collection.objects.link(obj); obj.location = loc
                obj.data.materials.append(material); obj['pcve_role'] = 'prop'


# ----------------------------------------------------------- dressing checks


def _body_samples(size, steps=(7, 5, 5)):
    """Points on the surface of a box of ``size`` centred on its origin."""
    half = [s / 2 for s in size]
    axes = [[-h + 2 * h * i / (n - 1) for i in range(n)] for h, n in zip(half, steps)]
    points = []
    for x in axes[0]:
        for y in axes[1]:
            for z in axes[2]:
                if abs(abs(x) - half[0]) < 1e-12 or abs(abs(y) - half[1]) < 1e-12 or abs(abs(z) - half[2]) < 1e-12:
                    points.append((x, y, z))
    return points


def verify_dressing(bpy, scene, camera, frames, clearance=PROP_CLEARANCE):
    """Check every static prop against one trajectory; raise if any is too close.

    For each frame the block (an oriented box), the bob (a sphere) and the
    thread (pivot to bob centre) are tested against every mesh tagged as a prop:
    exact nearest-surface distances from sample points on the bodies, plus the
    distance from every prop vertex to the block's box. The worktop and floor
    are the solver's own contact surfaces and are left out. Then a ray from the
    camera-facing point of each body towards the (orthographic) camera must not
    be stopped by a prop while that body is in frame.
    """
    import numpy as np
    from mathutils import Matrix, Vector
    from mathutils.bvhtree import BVHTree
    from bpy_extras.object_utils import world_to_camera_view
    depsgraph = bpy.context.evaluated_depsgraph_get()
    props = []
    for obj in scene.objects:
        if obj.type != 'MESH' or obj.get('pcve_role') != 'prop':
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        verts = [obj.matrix_world @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
        evaluated.to_mesh_clear()
        if not polys:
            continue
        props.append((obj.name, BVHTree.FromPolygons(verts, polys), np.array([tuple(v) for v in verts])))
    box_points = _body_samples(BOX_SIZE)
    half = np.array(BOX_SIZE) / 2
    back = (camera.matrix_world.to_3x3() @ Vector((0., 0., 1.))).normalized()
    worst = dict(distance=float('inf'), prop=None, frame=None, body=None)
    occluded = []

    def note(distance, name, frame, body):
        if distance < worst['distance']:
            worst.update(distance=distance, prop=name, frame=frame, body=body)

    def surface_distance(tree, point):
        hit = tree.find_nearest(point)
        if hit[0] is None:
            return float('inf')
        location, normal, _, distance = hit
        # Inside a closed prop the nearest face looks away from the point;
        # far outside, near the plane of a face, the sign alone is unreliable.
        if distance > 1e-9 and (point - location).normalized().dot(normal) < -.5:
            return 0.
        return distance

    for frame in frames:
        index = frame['frame_index']
        # A body removed by its DELETE edit is absent and has nothing to check.
        box_on = frame['box'].get('present', True); bob_on = frame['bob'].get('present', True)
        if box_on:
            box_matrix = Matrix(frame['box']['matrix_world'])
            rotation = np.array(box_matrix.to_3x3()); origin = np.array(box_matrix.translation)
            box_world = [box_matrix @ Vector(p) for p in box_points]
        if bob_on:
            bob = Vector(frame['bob']['location'])
            # The thread is tied off in the arm clamp, so its first 4 cm are exempt.
            tied = THREAD_TIE_OFF / PENDULUM_LENGTH
            thread = [Vector(PIVOT).lerp(bob, tied + (1 - tied) * t / 24) for t in range(25)]
        for name, tree, verts in props:
            if box_on:
                local = (verts - origin) @ rotation
                gap = np.linalg.norm(local - np.clip(local, -half, half), axis=1).min()
                note(float(gap), name, index, 'box')
                note(min(surface_distance(tree, p) for p in box_world), name, index, 'box')
            if bob_on:
                note(surface_distance(tree, bob) - BOB_RADIUS, name, index, 'bob')
                note(min(surface_distance(tree, p) for p in thread) - THREAD_RADIUS, name, index, 'thread')
        # Line of sight from the camera-facing point of each body: the bob's
        # point nearest the camera, and the centre of the block face that
        # looks most directly at it.
        sights = []
        if bob_on:
            sights.append(('bob', bob + back * BOB_RADIUS))
        if box_on:
            axes = [box_matrix.to_3x3() @ Vector(axis) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
            face = max(range(3), key=lambda i: abs(axes[i].dot(back)))
            box_face = box_matrix.translation + axes[face] * (
                BOX_SIZE[face] / 2 * (1 if axes[face].dot(back) > 0 else -1))
            sights.append(('box', box_face))
        for body, point in sights:
            view = world_to_camera_view(scene, camera, point)
            if not (0. <= view.x <= 1. and 0. <= view.y <= 1.):
                continue
            origin_ray = point + back * .001
            reach = (camera.matrix_world.translation - origin_ray).dot(back)
            while reach > 0:
                hit, location, _, _, obj, _ = scene.ray_cast(depsgraph, origin_ray, back, distance=reach)
                if not hit:
                    break
                if obj.get('pcve_role') == 'prop':
                    occluded.append((index, body, obj.name))
                    break
                step = (location - origin_ray).dot(back) + .0005
                origin_ray = origin_ray + back * step; reach -= step
    report = dict(min_prop_clearance_m=worst['distance'], closest_prop=worst['prop'],
                  closest_frame=worst['frame'], closest_body=worst['body'],
                  required_clearance_m=clearance, occluded_samples=[list(o) for o in occluded])
    if worst['distance'] < clearance or occluded:
        raise RuntimeError(f'Set dressing too close to or hiding a moving body: {report}')
    return report
