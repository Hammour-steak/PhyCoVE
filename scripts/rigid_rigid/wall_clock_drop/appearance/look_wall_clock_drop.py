"""The farmhouse boot room, the wall clock it carries, and the crate below.

The room is built by ``boot_room.build_room`` on the solver's own collision
planes (``assets/scenes/wall_clock_drop/room_colliders.json``), dressed with
Poly Haven CC0 scans from ``assets/polyhaven/wall_clock_drop``. The clock comes
from ``assets/models/wall_clock.glb`` and the crate from
``assets/models/wooden_crate.glb``; both are imported through ``bake_asset``
so every object carries its world transform in the mesh, then centred and
scaled onto exactly the collision shapes the solver uses, so the clock and the
crate that tumble on screen are the bodies that were solved.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
import random
from scene_geometry import CLOCK_DIAMETER, CRATE_HALF_EXTENTS

MODELS = _pcve_asset('models')
POLYHAVEN = _pcve_asset('polyhaven') / 'wall_clock_drop'
# Scanned wood for the moving bodies: (diffuse file, metres per tile).
CLOCK_CASE_TEX = ('walnut_veneer_02_diff_2k.jpg', 1.0)
CRATE_TEX = ('olive_veneer_diff_2k.jpg', 1.0)
# The GLB's hands stand at 12:15 with the hour hand exactly on 12. They are set
# to an early-afternoon time to match the daylight: (mesh name prefix, angle
# clockwise from 12 in degrees) for 1:52:20.
CLOCK_TIME = (('hour hand', (1 + 52 / 60) * 30.0), ('minute hand', (52 + 20 / 60) * 6.0),
              ('second hand', 20 * 6.0))


# ------------------------------------------------------------------ importing

def bake_asset(bpy, name):
    """Import a GLB, bake world transforms into the meshes, drop the originals."""
    old = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(MODELS / name))
    imported = [o for o in bpy.data.objects if o not in old]
    for o in imported:
        o.animation_data_clear()
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    result = []
    for o in imported:
        if o.type != 'MESH':
            continue
        mesh = bpy.data.meshes.new_from_object(o.evaluated_get(deps), preserve_all_data_layers=True, depsgraph=deps)
        mesh.transform(o.matrix_world)
        ob = bpy.data.objects.new(o.name + '_baked', mesh)
        bpy.context.collection.objects.link(ob)
        result.append(ob)
    for o in imported:
        bpy.data.objects.remove(o, do_unlink=True)
    return result


def bounds(parts):
    from mathutils import Vector
    pts = [v.co for o in parts for v in o.data.vertices]
    return (Vector([min(v[i] for v in pts) for i in range(3)]),
            Vector([max(v[i] for v in pts) for i in range(3)]))


def _principled(material):
    if not material or not material.use_nodes:
        return None
    return material.node_tree.nodes.get('Principled BSDF')


def _matte(bsdf, level):
    """Set the dielectric specular level (printed ink and paint are matte)."""
    socket = bsdf.inputs.get('Specular IOR Level')
    if socket is None:
        socket = bsdf.inputs.get('Specular')
    if socket is not None:
        socket.default_value = level


def _join(bpy, parts):
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    return bpy.context.object


def _wood(bpy, name, diffuse, tile_m, coords, tint, roughness_min, offset=(0.0, 0.0)):
    """A scanned wood set (colour, roughness, OpenGL normal) on the given
    texture coordinates ('Object' moves with the body, as does 'UV')."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1.0 / tile_m, 1.0 / tile_m, 1.0 / tile_m)
    mapping.inputs['Location'].default_value = (offset[0], offset[1], 0.0)
    links.new(coord.outputs[coords], mapping.inputs['Vector'])

    def scan(kind, colour_data):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(diffuse).replace('_diff_', f'_{kind}_'), check_existing=True)
        if not colour_data:
            node.image.colorspace_settings.name = 'Non-Color'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node
    mix = nodes.new('ShaderNodeMix')
    mix.data_type, mix.blend_type = 'RGBA', 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    links.new(scan('diff', True).outputs['Color'], mix.inputs[6])
    mix.inputs[7].default_value = (*tint, 1.0)
    links.new(mix.outputs[2], bsdf.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.clamp = True
    rough.inputs['To Min'].default_value = roughness_min
    links.new(scan('rough', False).outputs['Color'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(scan('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Metallic'].default_value = 0.0
    return mat


# -------------------------------------------------------------------- objects

def lift_material(clock, name, dz):
    """Push the faces of one material forward along local +z.

    The clock GLB carries its numerals, hour and minute marks as thin solids
    whose faces sit almost on the dial plane, so they z-fight with the face. A
    half-millimetre lift turns them into clean printed marks."""
    slot = None
    for index, mat in enumerate(clock.data.materials):
        if name in mat.name.lower():
            slot = index
            break
    if slot is None:
        raise RuntimeError('clock GLB has no %r material any more' % name)
    moved = set()
    for poly in clock.data.polygons:
        if poly.material_index == slot:
            moved.update(poly.vertices)
    for index in moved:
        vertex = clock.data.vertices[index]
        if vertex.co.z > 0.002:
            vertex.co.z += dz
    clock.data.update()


def set_hands(parts):
    """Turn each hand about the dial axis to the angle in ``CLOCK_TIME``.

    A hand's current angle is that of its vertex farthest from the axis (its
    tip), measured clockwise from 12 o'clock (+y) as seen from the dial side
    (+z); a counter-clockwise turn by phi moves it to angle - phi."""
    from mathutils import Matrix
    lo, hi = bounds(parts)
    cx, cy = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2
    for prefix, target in CLOCK_TIME:
        hand = next((o for o in parts if o.name.startswith(prefix)), None)
        if hand is None:
            raise RuntimeError('wall_clock.glb has no %r mesh any more' % prefix)
        tip = max(hand.data.vertices, key=lambda v: (v.co.x - cx) ** 2 + (v.co.y - cy) ** 2).co
        current = math.degrees(math.atan2(tip.x - cx, tip.y - cy))
        turn = Matrix.Translation((cx, cy, 0.)) @ Matrix.Rotation(math.radians(current - target), 4, 'Z')             @ Matrix.Translation((-cx, -cy, 0.))
        hand.data.transform(turn)
        hand.data.update()


def make_clock(bpy):
    """The clock GLB, centred on its case, scaled to a 44 cm dial and turned
    upright.

    The solver hangs its disc with the quaternion that sends the mesh's local
    +z (the dial normal) to world +y, which sends the mesh's 12 o'clock (local
    +y) straight down: rendered as authored the clock hangs upside down, its
    numerals reading as mirrored glyphs. The collision shape is a cylinder about
    local z, so turning the mesh 180 deg about that axis changes nothing the
    solver sees and puts 12 at the top, so the twelve numerals can stay."""
    parts = bake_asset(bpy, 'wall_clock.glb')
    if not parts:
        raise RuntimeError('wall_clock.glb imported nothing')
    numerals = [o for o in parts if o.name.split('_')[0].isdigit()]
    if len(numerals) != 12:
        raise RuntimeError('expected 12 numeral meshes in wall_clock.glb, found %d' % len(numerals))
    set_hands(parts)
    clock = _join(bpy, parts)
    lo, hi = bounds([clock])
    center = (lo + hi) / 2
    scale = CLOCK_DIAMETER / (hi.x - lo.x)
    for v in clock.data.vertices:
        p = (v.co - center) * scale
        v.co = (-p.x, -p.y, p.z)
    clock.data.update()
    lift_material(clock, 'numbers', .0005)
    # The GLB ships a pure-white dial and a glossy black plastic case. A hall
    # clock in an old house has a turned walnut case and a cream lacquered dial
    # printed in black; the walnut is a scanned veneer projected straight across
    # the face in the clock's own coordinates, so the grain travels with it.
    for slot in clock.material_slots:
        mat = slot.material
        bs = _principled(mat)
        if bs is None:
            continue
        name = mat.name.lower()
        if 'dial' in name:
            bs.inputs['Base Color'].default_value = (.70, .64, .50, 1)
            bs.inputs['Roughness'].default_value = .42
            bs.inputs['Metallic'].default_value = 0.
            _matte(bs, .35)
        elif 'hand' in name:
            bs.inputs['Base Color'].default_value = (.008, .008, .009, 1)
            bs.inputs['Roughness'].default_value = .62
            bs.inputs['Metallic'].default_value = 0.
            _matte(bs, .2)
        elif 'number' in name:
            bs.inputs['Base Color'].default_value = (.012, .011, .011, 1)
            bs.inputs['Roughness'].default_value = .7
            bs.inputs['Metallic'].default_value = 0.
            _matte(bs, 0.)
        elif 'metal' in name:
            slot.material = _wood(bpy, 'Walnut clock case', POLYHAVEN / CLOCK_CASE_TEX[0], CLOCK_CASE_TEX[1],
                                  'Object', (.80, .74, .70), .30, offset=(.31, .17))
    clock.name = 'Wall clock'
    return clock


CRATE_MODEL = 'wooden_crate.glb'


def _board_uvs(bpy, crate, centre, scale, seed=11):
    """Lay every board of the crate out along its own grain.

    The generator writes 33 planks with no UVs, and the GLB export splits every
    face off on its own vertices, so the planks are found again from the
    generator's own list of boxes (``tools/make_crate_asset.boxes``, moved by
    the same centring and scale as the mesh): each face belongs to the box that
    contains a point just behind it. On every face of a plank the texture's
    grain direction (u) runs along the plank's long axis, and each plank gets
    its own random patch of the scan, so neighbouring boards never repeat."""
    import bmesh
    from make_crate_asset import boxes
    planks = []
    for x0, x1, y0, y1, z0, z1, _slot in boxes():
        lo = [(a - centre[i]) * scale[i] for i, a in enumerate((x0, y0, z0))]
        hi = [(a - centre[i]) * scale[i] for i, a in enumerate((x1, y1, z1))]
        planks.append((lo, hi))
    bm = bmesh.new()
    bm.from_mesh(crate.data)
    layer = bm.loops.layers.uv.verify()
    members = [[] for _ in planks]
    for face in bm.faces:
        probe = face.calc_center_median() - face.normal * 1e-4
        owner = next((i for i, (lo, hi) in enumerate(planks)
                      if all(lo[k] - 1e-6 <= probe[k] <= hi[k] + 1e-6 for k in range(3))), None)
        if owner is None:
            bm.free()
            raise RuntimeError('a crate face lies outside every plank of make_crate_asset.boxes()')
        members[owner].append(face)
    rng = random.Random(seed)
    for (lo, hi), faces in zip(planks, members):
        ext = [hi[k] - lo[k] for k in range(3)]
        grain = max(range(3), key=lambda k: ext[k])
        du, dv = rng.uniform(0.0, 4.0), rng.uniform(0.0, 4.0)
        flip = rng.choice((1.0, -1.0))
        for f in faces:
            axis = max(range(3), key=lambda k: abs(f.normal[k]))
            plane = [k for k in range(3) if k != axis]
            if grain in plane:
                ua, va = grain, next(k for k in plane if k != grain)
            else:
                ua, va = sorted(plane, key=lambda k: -ext[k])
            for loop in f.loops:
                loop[layer].uv = (flip * loop.vert.co[ua] + du, loop.vert.co[va] + dv)
    bm.to_mesh(crate.data)
    bm.free()
    return sum(1 for faces in members if faces)


def make_crate(bpy):
    """The crate glb, scaled onto exactly the collision box the solver uses.

    The solver collides a ``GEOM_BOX`` of ``CRATE_HALF_EXTENTS``. For the two
    sides to agree each axis is scaled until the boards span exactly that box
    and the bounding-box centre is moved to the origin, so the object's
    ``location`` is the quantity the physics reports and the crate that tips
    over is the box that was solved. The boards are dressed in a scanned
    pale softwood (Poly Haven olive_veneer, whose flat-sawn figure reads as
    sawn pine), one random patch per board."""
    parts = bake_asset(bpy, CRATE_MODEL)
    if not parts:
        raise RuntimeError('wooden_crate.glb imported nothing; run tools/make_crate_asset.py')
    crate = _join(bpy, parts)
    lo, hi = bounds([crate])
    centre = (lo + hi) / 2
    scale = [2 * CRATE_HALF_EXTENTS[i] / (hi[i] - lo[i]) for i in range(3)]
    for v in crate.data.vertices:
        v.co = ((v.co[0] - centre.x) * scale[0], (v.co[1] - centre.y) * scale[1],
                (v.co[2] - centre.z) * scale[2])
    crate.data.update()
    boards = _board_uvs(bpy, crate, centre, scale)
    if boards != 33:
        raise RuntimeError('wooden_crate.glb should carry 33 boards, found %d' % boards)
    # The generator's three tints become three slightly different boards of
    # the same timber: the frame a touch darker, the two board sets either side.
    tints = [(.70, .64, .46), (.84, .78, .58), (.79, .73, .54)]
    for index, slot in enumerate(crate.material_slots):
        if slot.material is None:
            continue
        slot.material = _wood(bpy, 'Sawn pine %d' % index, POLYHAVEN / CRATE_TEX[0], CRATE_TEX[1], 'UV',
                              tints[index % len(tints)], .55)
    crate.name = 'Pine crate'
    return crate


# ------------------------------------------------------------------ lighting

def build_environment(bpy, scene):
    """The boot room with its daylight; returns what boot_room built."""
    from boot_room import build_room
    return build_room(POLYHAVEN)
