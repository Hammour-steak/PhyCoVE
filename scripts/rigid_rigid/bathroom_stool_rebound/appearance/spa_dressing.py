"""Window, dusk light, practical lamps and Poly Haven props for the spa bathroom.

Everything here is non-physical dressing. The renderer checks every frame of
every case that no prop comes within PROP_CLEARANCE_M of a stool and that no
prop hides a stool from the camera (check_props).
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from spa_materials import WORLD_SCALE, POLYHAVEN, world_box_uv, thin_glass, plain

PROP_CLEARANCE_M = .02

# ---------------------------------------------------------------- window
# A window in the north wall left of the vanity (x < -1.4 m, where no stool of
# any case ever goes: the trajectories stay at x > -0.22 m). It is the only
# stretch of wall the camera sees that no trajectory touches; the 45-degree
# alcove and the wall behind the tub are struck by edit_fast_throw. The GLB
# draws this wall as a single-sided plane at y = 4.49, so the opening is cut
# out of that plane and lined with a reveal of the wall's real thickness.
WALL_FACE_Y = 4.49
WALL_THICK = .33                      # 16.5 cm of masonry at real scale
WINDOW = dict(x0=-3.45, x1=-1.45, z0=2.40, z1=5.30)
FRAME_BAR, FRAME_DEPTH, FRAME_Y = .09, .10, 4.66


def _box(bpy, name, lo, hi, material):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = lo[0] + (v.co.x + .5) * (hi[0] - lo[0])
        v.co.y = lo[1] + (v.co.y + .5) * (hi[1] - lo[1])
        v.co.z = lo[2] + (v.co.z + .5) * (hi[2] - lo[2])
    bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    if material is not None:
        me.materials.append(material)
    return obj


def cut_window(bpy, wall):
    """Bisect the north-wall faces along the opening and delete what is inside."""
    import bmesh
    from mathutils import Vector
    w = WINDOW
    mw = wall.matrix_world; inv = mw.inverted(); rot = mw.to_3x3()
    bm = bmesh.new(); bm.from_mesh(wall.data)

    def on_wall(f):
        c = mw @ f.calc_center_median(); n = (rot @ f.normal).normalized()
        return abs(c.y - WALL_FACE_Y) < .02 and n.y < -.9
    for co, no in (((w['x0'], 0, 0), (1, 0, 0)), ((w['x1'], 0, 0), (1, 0, 0)),
                   ((0, 0, w['z0']), (0, 0, 1)), ((0, 0, w['z1']), (0, 0, 1))):
        faces = [f for f in bm.faces if on_wall(f)]
        geom = list(set(faces) | {e for f in faces for e in f.edges} | {v for f in faces for v in f.verts})
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=inv @ Vector(co),
                               plane_no=(inv.to_3x3() @ Vector(no)).normalized())
    doomed = []
    for f in bm.faces:
        c = mw @ f.calc_center_median()
        if on_wall(f) and w['x0'] < c.x < w['x1'] and w['z0'] < c.z < w['z1']:
            doomed.append(f)
    if not doomed:
        raise RuntimeError('window cut found no wall faces inside the opening')
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    bm.to_mesh(wall.data); bm.free()
    wall.data.update()


def build_window(bpy, stone, sill_stone):
    """Reveal, bronze frame, glass and a stone window board inside the opening."""
    w = WINDOW; y0, y1 = WALL_FACE_Y + .005, WALL_FACE_Y + WALL_THICK; t = .15
    parts = [
        _box(bpy, 'Window reveal left', (w['x0'] - t, y0, w['z0'] - t), (w['x0'], y1, w['z1'] + t), stone),
        _box(bpy, 'Window reveal right', (w['x1'], y0, w['z0'] - t), (w['x1'] + t, y1, w['z1'] + t), stone),
        _box(bpy, 'Window reveal head', (w['x0'], y0, w['z1']), (w['x1'], y1, w['z1'] + t), stone),
        _box(bpy, 'Window reveal bottom', (w['x0'], y0, w['z0'] - t), (w['x1'], y1, w['z0']), stone),
    ]
    bronze = plain(bpy, 'Dark bronze window frame', (.075, .058, .042), .42, metallic=1.0)
    b, fy0, fy1 = FRAME_BAR, FRAME_Y - FRAME_DEPTH / 2, FRAME_Y + FRAME_DEPTH / 2
    _box(bpy, 'Window frame head', (w['x0'], fy0, w['z1'] - b), (w['x1'], fy1, w['z1']), bronze)
    _box(bpy, 'Window frame sill', (w['x0'], fy0, w['z0']), (w['x1'], fy1, w['z0'] + b), bronze)
    _box(bpy, 'Window frame left', (w['x0'], fy0, w['z0'] + b), (w['x0'] + b, fy1, w['z1'] - b), bronze)
    _box(bpy, 'Window frame right', (w['x1'] - b, fy0, w['z0'] + b), (w['x1'], fy1, w['z1'] - b), bronze)
    # A transom two thirds up, as on a tilt-and-turn hotel window.
    zt = w['z0'] + (w['z1'] - w['z0']) * .68
    _box(bpy, 'Window frame transom', (w['x0'] + b, fy0 + .01, zt - b / 2), (w['x1'] - b, fy1 - .01, zt + b / 2), bronze)
    pane = _box(bpy, 'Window glass', (w['x0'] + b * .5, FRAME_Y - .006, w['z0'] + b * .5),
                (w['x1'] - b * .5, FRAME_Y + .006, w['z1'] - b * .5), thin_glass(bpy))
    pane.visible_shadow = False
    board = _box(bpy, 'Window board', (w['x0'] - .08, WALL_FACE_Y - .09, w['z0'] - .06),
                 (w['x1'] + .08, FRAME_Y - FRAME_DEPTH / 2, w['z0']), sill_stone)
    for obj in parts + [board]:
        world_box_uv(bpy, obj)
    portal = bpy.data.lights.new('Window sky portal', 'AREA')
    portal.shape = 'RECTANGLE'; portal.size, portal.size_y = w['x1'] - w['x0'], w['z1'] - w['z0']
    portal.cycles.is_portal = True
    obj = bpy.data.objects.new('Window sky portal', portal)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = ((w['x0'] + w['x1']) / 2, y1 + .01, (w['z0'] + w['z1']) / 2)
    obj.rotation_euler = (-math.pi / 2, 0, 0)        # area light emits along local -Z: point it at -y
    return pane


# ------------------------------------------------------------ dusk outside
# Poly Haven qwantani_dusk_2: a clear dusk over a distant lake and hills, the
# sun just set. Only camera rays see it (through the window); the room is lit
# by Blender's physical Nishita sky with the sun 1.5 degrees below the horizon,
# so the light through the glass is the cool, low twilight of the photograph.
# The photograph's afterglow peaks at pixel column GLOW_U; its azimuth
# atan2(y, x) = (0.5 - u) * 360 deg is turned onto the Nishita sun's azimuth.
DUSK_VIEW = 'qwantani_dusk_2_4k.hdr'
GLOW_U = .625                       # afterglow peak on the 4k file (band 2-10 deg above the horizon)
SUN_ELEVATION_DEG = -1.5
SUN_AZIMUTH_DEG = 102.0              # atan2(y, x): north-north-west, behind the window
SKY_STRENGTH = 4.0
VIEW_STRENGTH = .45


def dusk_world(bpy, scene, glow_u=GLOW_U, sky_strength=SKY_STRENGTH, view_strength=VIEW_STRENGTH,
               sun_elevation_deg=SUN_ELEVATION_DEG, sun_azimuth_deg=SUN_AZIMUTH_DEG):
    world = bpy.data.worlds.new('Dusk outside')
    world.use_nodes = True
    scene.world = world
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    sky.sun_elevation = math.radians(sun_elevation_deg)
    az = math.radians(sun_azimuth_deg)
    sky.sun_rotation = math.atan2(math.cos(az), math.sin(az))   # Nishita: sun at (sin r, cos r)
    sky.air_density, sky.dust_density, sky.ozone_density = 1.0, 1.5, 1.0
    lighting = nodes['Background']
    links.new(sky.outputs['Color'], lighting.inputs['Color'])
    lighting.inputs['Strength'].default_value = sky_strength
    coord = nodes.new('ShaderNodeTexCoord')
    turn = nodes.new('ShaderNodeMapping'); turn.vector_type = 'VECTOR'
    turn.inputs['Rotation'].default_value = (0, 0, math.radians((.5 - glow_u) * 360.0) - az)
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(POLYHAVEN / DUSK_VIEW), check_existing=True)
    links.new(coord.outputs['Generated'], turn.inputs['Vector'])
    links.new(turn.outputs['Vector'], photo.inputs['Vector'])
    view = nodes.new('ShaderNodeBackground')
    view.inputs['Strength'].default_value = view_strength
    links.new(photo.outputs['Color'], view.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(lighting.outputs['Background'], mix.inputs[1])
    links.new(view.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['World Output'].inputs['Surface'])
    return world


# ------------------------------------------------------------- practicals
SCONCE_COLOUR = (1.0, .74, .50)          # sconce lamps (warm white LED)
CAN_COLOUR = (1.0, .82, .64)          # ceiling cans


def downlights(bpy, scene, discs, power):
    """A soft spot at each recessed ceiling can of the GLB, aimed straight down.

    The cans are real fixtures in the model (emission discs in black trims at
    z = 5.86); the spot sits 2 cm under the disc so the trim casts the cut-off.
    """
    out = []
    for disc in discs:
        pts = [disc.matrix_world @ v.co for v in disc.data.vertices]
        c = [sum(p[i] for p in pts) / len(pts) for i in range(3)]
        data = bpy.data.lights.new(disc.name + ' spot', 'SPOT')
        data.energy = power; data.color = CAN_COLOUR
        data.spot_size = math.radians(110); data.spot_blend = .55
        data.shadow_soft_size = .14
        obj = bpy.data.objects.new(disc.name + ' spot', data)
        scene.collection.objects.link(obj)
        obj.location = (c[0], c[1], c[2] - .02)
        out.append(obj)
    return out


def bulb_in_shade(bpy, scene, shade, power, radius):
    """A small sphere lamp at the centre of an opal sconce shade.

    The shade itself glows (its material) and is made transparent to shadow
    rays, so the lamp inside lights the wall the way an opal cylinder does.
    """
    pts = [shade.matrix_world @ v.co for v in shade.data.vertices]
    c = [sum(p[i] for p in pts) / len(pts) for i in range(3)]
    data = bpy.data.lights.new(shade.name + ' lamp', 'POINT')
    data.energy = power; data.color = SCONCE_COLOUR; data.shadow_soft_size = radius
    obj = bpy.data.objects.new(shade.name + ' lamp', data)
    scene.collection.objects.link(obj)
    obj.location = c
    shade.visible_shadow = False
    return obj


# ------------------------------------------------------------------ props
def place_model(bpy, stem, name, *, face_towards=None, yaw_deg=0.0, scale=WORLD_SCALE, **anchor):
    """Import a Poly Haven glTF at WORLD_SCALE and set its bounding box on an anchor.

    Anchor keys: x / y (box centre) or x_min / x_max / y_min / y_max, and z
    (bottom of the box). face_towards=(x, y) turns the model so its front (the
    side away from its tall back, found from the geometry) looks at that point.
    """
    from mathutils import Vector
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(POLYHAVEN / stem / f'{stem}_1k.gltf'))
    imported = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    for obj in imported:
        obj.animation_data_clear()
        if obj.parent is None:
            world = obj.matrix_world.copy(); obj.parent = root; obj.matrix_world = world
    root.scale = (scale, scale, scale)
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == 'MESH']

    def points():
        return [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    if face_towards is not None:
        pts = points()
        lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
        top = [p for p in pts if p.z > lo.z + .7 * (hi.z - lo.z)]
        back = Vector((sum(p.x for p in top) / len(top) - (lo.x + hi.x) / 2,
                       sum(p.y for p in top) / len(top) - (lo.y + hi.y) / 2))
        front0 = math.atan2(-back.y, -back.x)
        target = Vector(face_towards) - Vector(((anchor.get('x', (lo.x + hi.x) / 2)), anchor.get('y', (lo.y + hi.y) / 2)))
        yaw_deg += math.degrees(math.atan2(target.y, target.x) - front0)
    root.rotation_euler.z = math.radians(yaw_deg)
    bpy.context.view_layer.update()
    pts = points()
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    shift = Vector((0, 0, 0))
    for axis, i in (('x', 0), ('y', 1)):
        if axis in anchor:
            shift[i] = anchor[axis] - (lo[i] + hi[i]) / 2
        elif f'{axis}_min' in anchor:
            shift[i] = anchor[f'{axis}_min'] - lo[i]
        elif f'{axis}_max' in anchor:
            shift[i] = anchor[f'{axis}_max'] - hi[i]
    if 'z' in anchor:
        shift.z = anchor['z'] - lo.z
    root.location = shift
    bpy.context.view_layer.update()
    return dict(name=name, model=stem, root=root, meshes=meshes,
                bbox_min=[round(v, 4) for v in lo + shift], bbox_max=[round(v, 4) for v in hi + shift])


def move_subtree_onto(bpy, root, x, y, z):
    """Translate a GLB decor group so its bounding box sits centred on (x, y) at height z."""
    from mathutils import Vector, Matrix
    stack, meshes = [root], []
    while stack:
        o = stack.pop(); stack.extend(o.children)
        if o.type == 'MESH':
            meshes.append(o)
    pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = [min(p[i] for p in pts) for i in range(3)]; hi = [max(p[i] for p in pts) for i in range(3)]
    delta = Vector((x - (lo[0] + hi[0]) / 2, y - (lo[1] + hi[1]) / 2, z - lo[2]))
    root.matrix_world = Matrix.Translation(delta) @ root.matrix_world
    bpy.context.view_layer.update()
    return meshes


# ------------------------------------------------------------ prop checks
def check_props(bpy, scene, camera, stool_pivots, frames, decor, margin=PROP_CLEARANCE_M, rays_per_frame=160):
    """Per frame: nearest distance from every stool to every decor mesh, and
    the share of camera rays to each stool that a decor mesh intercepts.

    ``decor`` maps a label to its mesh objects. Raises if anything comes
    within ``margin`` of a stool; returns the measured minima for the log.
    """
    import numpy as np
    from mathutils import Vector, Matrix
    from mathutils.bvhtree import BVHTree
    depsgraph = bpy.context.evaluated_depsgraph_get()
    trees, boxes = {}, {}
    for label, objs in decor.items():
        objs = [o for o in objs if not o.hide_render]
        if not objs:
            continue
        verts, polys = [], []
        for o in objs:
            ev = o.evaluated_get(depsgraph); me = ev.to_mesh()
            base = len(verts)
            verts += [tuple(o.matrix_world @ v.co) for v in me.vertices]
            polys += [[base + i for i in p.vertices] for p in me.polygons]
            ev.to_mesh_clear()
        trees[label] = BVHTree.FromPolygons(verts, polys)
        a = np.array(verts); boxes[label] = (a.min(0) - .25, a.max(0) + .25)
    # Stool surface points in each pivot's frame (rest pose).
    local = {}
    for key, pivot in stool_pivots.items():
        inv = pivot.matrix_world.inverted()
        pts = []
        stack = list(pivot.children)
        while stack:
            o = stack.pop(); stack.extend(o.children)
            if o.type == 'MESH':
                pts += [tuple(inv @ (o.matrix_world @ v.co)) for v in o.data.vertices]
        local[key] = np.array(pts)
    nearest = {label: 1e9 for label in trees}
    blocked = {label: 0.0 for label in trees}
    cam = camera.matrix_world.translation
    rng = np.random.default_rng(7)
    for f in frames:
        for key, pts in local.items():
            state = f.get(key) or {}
            if not state.get('present'):
                continue
            M = np.array(state['matrix_world'])
            world = pts @ M[:3, :3].T + M[:3, 3]
            for label, tree in trees.items():
                lo, hi = boxes[label]
                inside = world[np.all((world > lo) & (world < hi), axis=1)]
                for p in inside:
                    hit = tree.find_nearest(Vector(p))
                    if hit[0] is not None:
                        nearest[label] = min(nearest[label], hit[3])
            sample = world[rng.choice(len(world), size=min(rays_per_frame, len(world)), replace=False)]
            for label, tree in trees.items():
                hits = 0
                for p in sample:
                    d = Vector(p) - cam; dist = d.length
                    hit = tree.ray_cast(cam, d.normalized(), dist - .03)
                    hits += hit[0] is not None
                blocked[label] = max(blocked[label], hits / len(sample))
    # 1e9 = no stool point ever came within 0.25 m of the piece's bounding box.
    close = sorted((kv for kv in nearest.items() if kv[1] < 1e8), key=lambda kv: kv[1])
    bad = {k: v for k, v in close if v < margin}
    print('[props] nearest stool distance (pieces within 0.25 m): '
          + (', '.join(f'{k} {v:.3f} m' for k, v in close) or 'none'), flush=True)
    shown = [f'{k} {v:.0%}' for k, v in blocked.items() if v > 0]
    print('[props] worst share of stool rays blocked: ' + (', '.join(shown) or 'none'), flush=True)
    if bad:
        raise RuntimeError(f'props within {margin} m of a stool: {bad}')
    return dict(nearest_m={k: round(v, 4) for k, v in close},
                max_blocked_share={k: round(v, 3) for k, v in blocked.items() if v > 0})
