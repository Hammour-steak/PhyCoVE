"""The portable goal, the ball and the hall, built for Cycles.

Every surface the ball can touch is drawn exactly where the simulator has it,
so a contact on screen is a contact in the solver:

* the backboard is the solver's board box (1.284 x 0.020 x 0.863 m, face at
  ``board_face_y``), shaded as tempered glass with painted white markings;
* the ring is a torus on the centreline of the 96-sphere rail with the rail's
  tube radius;
* the rim mount is the solver's bracket box, which a real breakaway rim's
  spring housing looks like;
* the base of the portable goal is the solver's eight-corner wedge.

The rest of the goal -- glass frame, back frame, boom arms, pole, pole pad,
wheels -- and the whole hall (``gym_hall``) are props: the renderer checks
every frame that the ball stays at least 2 cm clear of each of them and that
none of them hides the ball from the camera.

The pole stands at the back of the base, clear of where the edits roll the
ball, and the rim carries no net (the solver has none, and the shots leave the
ring sideways, through where a net would hang).
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import math
import bmesh
import bpy
from mathutils import Matrix, Vector
from scene_geometry import (BOARD_CENTER, BOARD_HALF, BRACKET_CENTER, BRACKET_HALF,
                            GOAL_BASE_FACES, GOAL_BASE_VERTICES, RIM_CENTER_X,
                            RIM_CENTER_Y, RIM_RADIUS, RIM_TUBE, RIM_Z)
import gym_hall as hall

FZ = hall.FZ
# The pole stands at the back of the base, clear of every bounce the edits
# make behind the board (the farthest reaches y = 7.63 m), and carries the board
# on a 1.65 m boom.
POLE_Y, POLE_HALF = 8.20, 0.05
BOOM_Z = (2.84, 3.20)
# FIBA board markings: 50 mm lines, a 0.59 x 0.45 m target whose bottom line
# sits level with the top of the ring.
MARK_W = 0.05
TARGET_HALF_W, TARGET_H = 0.295, 0.45


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def _mesh_object(name, verts, faces, mat):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def beam(name, p0, p1, width, height, mat, bevel=0.003):
    """A rectangular tube from p0 to p1 in a plane of constant x."""
    p0, p1 = Vector(p0), Vector(p1)
    length = (p1 - p0).length
    obj = hall.box(name, (-width / 2, -length / 2, -height / 2), (width / 2, length / 2, height / 2), mat, bevel)
    angle = math.atan2(p1.z - p0.z, p1.y - p0.y)
    obj.data.transform(Matrix.Translation((p0 + p1) / 2) @ Matrix.Rotation(angle, 4, 'X'))
    return obj


# ---------------------------------------------------------------- materials


def _mix_rgba(nodes, links, factor, color_a, color_b):
    """Blender 4's Mix node hides one socket per data type; take the RGBA pair."""
    node = nodes.new('ShaderNodeMix')
    node.data_type = 'RGBA'
    colors = [s for s in node.inputs if s.type == 'RGBA']
    output = [s for s in node.outputs if s.type == 'RGBA'][0]
    for socket, value in zip(colors, (color_a, color_b)):
        if isinstance(value, tuple):
            socket.default_value = (*value, 1.0)
        else:
            links.new(value, socket)
    if isinstance(factor, float):
        node.inputs['Factor'].default_value = factor
    else:
        links.new(factor, node.inputs['Factor'])
    return output


def powder_coated_steel(name, dark, light):
    """Powder-coated steel: a dielectric with orange peel, mottle and grime.

    The spray leaves a faint orange-peel relief, a decade in a hall leaves the
    paint mottled, and the bottom half metre collects scuffs and wash marks.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Metallic'].default_value = 0.0
    bsdf.inputs['Specular IOR Level'].default_value = 0.40
    coord = nodes.new('ShaderNodeTexCoord')
    geometry = nodes.new('ShaderNodeNewGeometry')
    grain = nodes.new('ShaderNodeTexNoise')
    grain.inputs['Scale'].default_value = 55.0
    grain.inputs['Detail'].default_value = 8.0
    grain.inputs['Roughness'].default_value = 0.62
    links.new(coord.outputs['Object'], grain.inputs['Vector'])
    peel = nodes.new('ShaderNodeBump')
    peel.inputs['Strength'].default_value = 0.35
    peel.inputs['Distance'].default_value = 0.0008
    links.new(grain.outputs['Fac'], peel.inputs['Height'])
    links.new(peel.outputs['Normal'], bsdf.inputs['Normal'])
    mottle = nodes.new('ShaderNodeTexNoise')
    mottle.inputs['Scale'].default_value = 2.4
    mottle.inputs['Detail'].default_value = 4.0
    links.new(coord.outputs['Object'], mottle.inputs['Vector'])
    paint = _mix_rgba(nodes, links, mottle.outputs['Fac'], dark, light)
    # Grime: strongest in the bottom half metre above the floor, patchy.
    height = nodes.new('ShaderNodeSeparateXYZ')
    links.new(geometry.outputs['Position'], height.inputs['Vector'])
    fade = nodes.new('ShaderNodeMapRange')
    fade.inputs['From Min'].default_value = FZ + 0.02
    fade.inputs['From Max'].default_value = FZ + 0.6
    fade.inputs['To Min'].default_value = 0.8
    fade.inputs['To Max'].default_value = 0.0
    fade.clamp = True
    links.new(height.outputs['Z'], fade.inputs['Value'])
    patches = nodes.new('ShaderNodeTexNoise')
    patches.inputs['Scale'].default_value = 6.5
    patches.inputs['Detail'].default_value = 5.0
    links.new(coord.outputs['Object'], patches.inputs['Vector'])
    amount = nodes.new('ShaderNodeMath')
    amount.operation = 'MULTIPLY'
    links.new(fade.outputs['Result'], amount.inputs[0])
    links.new(patches.outputs['Fac'], amount.inputs[1])
    grimy = _mix_rgba(nodes, links, amount.outputs[0], paint, tuple(c * 0.55 for c in dark))
    # Chips: sparse, hard-edged, the paler primer showing through.
    chips = nodes.new('ShaderNodeTexNoise')
    chips.inputs['Scale'].default_value = 15.0
    chips.inputs['Detail'].default_value = 8.0
    chips.inputs['Roughness'].default_value = 0.65
    links.new(coord.outputs['Object'], chips.inputs['Vector'])
    chip = nodes.new('ShaderNodeMapRange')
    chip.inputs['From Min'].default_value = 0.735
    chip.inputs['From Max'].default_value = 0.76
    links.new(chips.outputs['Fac'], chip.inputs['Value'])
    links.new(_mix_rgba(nodes, links, chip.outputs['Result'], grimy, (0.09, 0.092, 0.095)),
              bsdf.inputs['Base Color'])
    sheen = nodes.new('ShaderNodeMapRange')
    sheen.inputs['To Min'].default_value = 0.24
    sheen.inputs['To Max'].default_value = 0.40
    links.new(mottle.outputs['Fac'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    return mat


def glass_board_material():
    """12 mm tempered glass with the FIBA markings painted on it.

    The paint mask is drawn from world x/z on the board plane: a border line
    round the edge and the shooter's target above the ring. Shadow rays pass
    the clear glass (Cycles would otherwise shade it like an opaque slab) but
    not the paint.
    """
    mat = bpy.data.materials.new('Tempered glass backboard')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    glass = nodes.new('ShaderNodeBsdfPrincipled')
    glass.inputs['Base Color'].default_value = (0.90, 0.96, 0.94, 1.0)
    glass.inputs['Roughness'].default_value = 0.0
    glass.inputs['IOR'].default_value = 1.52
    glass.inputs['Transmission Weight'].default_value = 1.0
    paint = nodes.new('ShaderNodeBsdfPrincipled')
    paint.inputs['Base Color'].default_value = (0.80, 0.80, 0.78, 1.0)
    paint.inputs['Roughness'].default_value = 0.42

    geometry = nodes.new('ShaderNodeNewGeometry')
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(geometry.outputs['Position'], xyz.inputs['Vector'])
    x, z = xyz.outputs['X'], xyz.outputs['Z']

    def m(op, a, b=None):
        node = nodes.new('ShaderNodeMath')
        node.operation = op
        for socket, value in zip(node.inputs, (a, b)):
            if value is None:
                continue
            if isinstance(value, (int, float)):
                socket.default_value = value
            else:
                links.new(value, socket)
        return node.outputs[0]

    def inside(v, lo, hi):
        return m('MULTIPLY', m('GREATER_THAN', v, lo), m('LESS_THAN', v, hi))

    def frame(x0, x1, z0, z1):
        outer = m('MULTIPLY', inside(x, x0, x1), inside(z, z0, z1))
        inner = m('MULTIPLY', inside(x, x0 + MARK_W, x1 - MARK_W), inside(z, z0 + MARK_W, z1 - MARK_W))
        return m('SUBTRACT', outer, inner)

    cx, cz = BOARD_CENTER[0], BOARD_CENTER[2]
    hx, hz = BOARD_HALF[0], BOARD_HALF[2]
    ring_top = RIM_Z + RIM_TUBE
    # The border line starts where the frame's lip ends.
    border = frame(cx - hx + 0.006, cx + hx - 0.006, cz - hz + 0.006, cz + hz - 0.006)
    target = frame(RIM_CENTER_X - TARGET_HALF_W, RIM_CENTER_X + TARGET_HALF_W, ring_top, ring_top + TARGET_H)
    mask = m('MAXIMUM', border, target)
    surface = nodes.new('ShaderNodeMixShader')
    links.new(mask, surface.inputs['Fac'])
    links.new(glass.outputs['BSDF'], surface.inputs[1])
    links.new(paint.outputs['BSDF'], surface.inputs[2])
    clear = nodes.new('ShaderNodeBsdfTransparent')
    clear.inputs['Color'].default_value = (0.86, 0.93, 0.90, 1.0)
    path = nodes.new('ShaderNodeLightPath')
    see_through = m('MULTIPLY', path.outputs['Is Shadow Ray'], m('SUBTRACT', 1.0, mask))
    final = nodes.new('ShaderNodeMixShader')
    links.new(see_through, final.inputs['Fac'])
    links.new(surface.outputs['Shader'], final.inputs[1])
    links.new(clear.outputs['BSDF'], final.inputs[2])
    links.new(final.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


# ---------------------------------------------------------------------- goal


def build_goal():
    """The portable goal. Returns (collider surfaces, props)."""
    rim_paint = hall.plain_material('Orange rim powder coat', (0.62, 0.115, 0.018), 0.40,
                                    bump=0.0003, scale=420)
    frame_steel = powder_coated_steel('Goal powder coat', (0.012, 0.013, 0.016), (0.034, 0.037, 0.042))
    aluminium = hall.plain_material('Board frame aluminium', (0.56, 0.57, 0.58), 0.30, metallic=1.0)
    pad = hall.vinyl_material('Navy vinyl pole pad', (0.012, 0.030, 0.105))
    rubber = hall.plain_material('Castor rubber', (0.02, 0.02, 0.02), 0.6)

    colliders, props = [], []
    # Backboard: exactly the solver's board box.
    centre, half = Vector(BOARD_CENTER), Vector(BOARD_HALF)
    board = hall.box('Glass backboard', centre - half, centre + half, glass_board_material())
    colliders.append(board)
    # Ring: a torus on the rail centreline.
    bpy.ops.mesh.primitive_torus_add(major_radius=RIM_RADIUS, minor_radius=RIM_TUBE,
                                     major_segments=160, minor_segments=24,
                                     location=(RIM_CENTER_X, RIM_CENTER_Y, RIM_Z))
    ring = bpy.context.object
    ring.name = 'Rim ring'
    ring.data.materials.append(rim_paint)
    for poly in ring.data.polygons:
        poly.use_smooth = True
    colliders.append(ring)
    # Rim mount: exactly the solver's bracket box (edges eased by 1.5 mm).
    bc, bh = Vector(BRACKET_CENTER), Vector(BRACKET_HALF)
    colliders.append(hall.box('Rim mount housing', bc - bh, bc + bh, rim_paint, bevel=0.0015))
    # Base: the solver's wedge, corner for corner.
    faces = [tuple(reversed(f)) for f in GOAL_BASE_FACES]
    wedge = _mesh_object('Goal base', GOAL_BASE_VERTICES, faces, frame_steel)
    me = wedge.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    mod = wedge.modifiers.new('Eased edges', 'BEVEL')
    mod.width, mod.segments, mod.limit_method = 0.0015, 2, 'ANGLE'
    colliders.append(wedge)

    face_y = centre.y - half.y
    back_y = centre.y + half.y
    x0, x1 = centre.x - half.x, centre.x + half.x
    z0, z1 = centre.z - half.z, centre.z + half.z
    # Rim flange: the plate the housing is bolted through, on the glass face.
    props.append(hall.box('Rim flange plate', (-0.095, face_y - 0.012, RIM_Z - 0.145),
                          (0.095, face_y, RIM_Z + 0.012), rim_paint, bevel=0.002))
    # Aluminium channel round the glass: its lip stands 3 mm proud of the face
    # and covers the outer 6 mm of the pane, well away from any bank point.
    f, lip, cover = 0.032, 0.003, 0.006
    fy0, fy1 = face_y - lip, back_y + 0.03
    props += [hall.box('Board frame top', (x0 - f, fy0, z1 - cover), (x1 + f, fy1, z1 + f), aluminium, 0.002),
              hall.box('Board frame bottom', (x0 - f, fy0, z0 - f), (x1 + f, fy1, z0 + cover), aluminium, 0.002),
              hall.box('Board frame left', (x0 - f, fy0, z0 + cover), (x0 + cover, fy1, z1 - cover), aluminium, 0.002),
              hall.box('Board frame right', (x1 - cover, fy0, z0 + cover), (x1 + f, fy1, z1 - cover), aluminium, 0.002)]
    # Steel back frame the boom bolts to.
    by0, by1 = back_y + 0.002, back_y + 0.052
    t = 0.04
    props += [hall.box('Back frame top', (x0 + 0.06, by0, z1 - 0.10 - t), (x1 - 0.06, by1, z1 - 0.10), frame_steel, 0.002),
              hall.box('Back frame bottom', (x0 + 0.06, by0, z0 + 0.06), (x1 - 0.06, by1, z0 + 0.06 + t), frame_steel, 0.002),
              hall.box('Back frame left', (x0 + 0.06, by0, z0 + 0.06), (x0 + 0.06 + t, by1, z1 - 0.10), frame_steel, 0.002),
              hall.box('Back frame right', (x1 - 0.06 - t, by0, z0 + 0.06), (x1 - 0.06, by1, z1 - 0.10), frame_steel, 0.002)]
    for side in (-1, 1):
        xs = side * 0.16
        props.append(hall.box(f'Back frame upright {side:+d}', (xs - t / 2, by0, z0 + 0.06),
                              (xs + t / 2, by1, z1 - 0.10), frame_steel, 0.002))
        # Two boom arms per side, parallel, from the back frame to the pole.
        for k, zb in enumerate(BOOM_Z):
            props.append(hall.box(f'Boom arm {k} {side:+d}', (xs - 0.02, by1, zb - 0.035),
                                  (xs + 0.02, POLE_Y - POLE_HALF, zb + 0.035), frame_steel, 0.003))
    # Pole on the rising back of the base, padded to 2 m.
    ramp = lambda y: 0.145 + (0.412 - 0.145) * (y - 7.03) / (8.50 - 7.03)
    p0 = ramp(POLE_Y - POLE_HALF) - 0.03
    props.append(hall.box('Goal pole', (-POLE_HALF, POLE_Y - POLE_HALF, p0),
                          (POLE_HALF, POLE_Y + POLE_HALF, BOOM_Z[1] + 0.12), frame_steel, 0.004))
    props.append(hall.box('Goal pole cap', (-POLE_HALF - 0.01, POLE_Y - POLE_HALF - 0.01, BOOM_Z[1] + 0.12),
                          (POLE_HALF + 0.01, POLE_Y + POLE_HALF + 0.01, BOOM_Z[1] + 0.13), frame_steel, 0.003))
    props.append(hall.box('Goal pole pad', (-0.09, POLE_Y - 0.09, ramp(POLE_Y + 0.09) + 0.03),
                          (0.09, POLE_Y + 0.09, FZ + 2.0), pad, bevel=0.012, segments=3))
    # A diagonal strut from the pole up under the lower arms.
    props.append(beam('Boom strut', (0.0, POLE_Y - POLE_HALF, 1.95), (0.0, 7.25, BOOM_Z[0] - 0.035),
                      0.05, 0.05, frame_steel))
    props.append(hall.box('Boom strut crossbar', (-0.18, 7.22, BOOM_Z[0] - 0.07), (0.18, 7.28, BOOM_Z[0] - 0.035),
                          frame_steel, 0.003))
    # Two castors at the back of the base, outside its flanks.
    for side in (-1, 1):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.075, depth=0.045, vertices=40,
                                            location=(side * 0.62, 8.42, FZ + 0.075),
                                            rotation=(0.0, math.pi / 2, 0.0))
        wheel = bpy.context.object
        wheel.name = f'Base castor {side:+d}'
        wheel.data.materials.append(rubber)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        bevel = wheel.modifiers.new('Rounded tyre', 'BEVEL')
        bevel.width, bevel.segments = 0.01, 3
        for poly in wheel.data.polygons:
            poly.use_smooth = True
        props.append(wheel)
        xa, xb = sorted((side * 0.552, side * 0.598))
        props.append(hall.box(f'Castor axle block {side:+d}', (xa, 8.40, FZ + 0.055), (xb, 8.44, FZ + 0.095),
                              frame_steel, 0.003))
    return colliders, props


# ---------------------------------------------------------------------- ball

# The library ball's 1024 px texture set carries two trademarks: a league logo on
# one of the upper lenses and a maker's name with its emblem on one of the lower
# lenses. Each sits on a lens whose neighbour (155 / 154 px to the side in the
# atlas, the same shape and orientation) is plain pebbled leather, so inside a
# box round each mark the lookup is slid onto the neighbour: colour, ORM and
# normal maps all move together, and the box edge lies on leather. Boxes are
# (u0, u1, v0, v1) in UV, with the u shift that lands on the plain lens.
_ATLAS = 1024.0
LOGO_PATCHES = (
    ((792, 894), (215, 270), -155),    # league logo, upper right lens
    ((645, 708), (668, 895), +154),    # maker's name, lower left lens
    ((700, 748), (748, 812), +154),    # maker's emblem beside it
)


def cover_logos(mat):
    """Re-point every image lookup of the ball material away from the marks."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    images = [n for n in nodes if n.type == 'TEX_IMAGE']
    if not images:
        return 0
    uv = nodes.new('ShaderNodeUVMap')
    parts = nodes.new('ShaderNodeSeparateXYZ')
    links.new(uv.outputs['UV'], parts.inputs['Vector'])
    u, v = parts.outputs['X'], parts.outputs['Y']

    def m(op, a, b):
        node = nodes.new('ShaderNodeMath')
        node.operation = op
        for socket, value in zip(node.inputs, (a, b)):
            if isinstance(value, (int, float)):
                socket.default_value = value
            else:
                links.new(value, socket)
        return node.outputs[0]

    # Boxes that share a shift are united (maximum), so where two of them
    # overlap the lookup moves once, not twice.
    masks = {}
    for (x0, x1), (y0, y1), du in LOGO_PATCHES:
        # Pixel rows count from the top of the atlas, v from the bottom.
        inside = m('MULTIPLY',
                   m('MULTIPLY', m('GREATER_THAN', u, x0 / _ATLAS), m('LESS_THAN', u, x1 / _ATLAS)),
                   m('MULTIPLY', m('GREATER_THAN', v, 1 - y1 / _ATLAS), m('LESS_THAN', v, 1 - y0 / _ATLAS)))
        masks[du] = inside if du not in masks else m('MAXIMUM', masks[du], inside)
    shift = None
    for du, inside in masks.items():
        term = m('MULTIPLY', inside, du / _ATLAS)
        shift = term if shift is None else m('ADD', shift, term)
    moved = nodes.new('ShaderNodeCombineXYZ')
    links.new(m('ADD', u, shift), moved.inputs['X'])
    links.new(v, moved.inputs['Y'])
    for node in images:
        links.new(moved.outputs['Vector'], node.inputs['Vector'])
    return len(images)


def import_ball(path, radius):
    """Bring the ball in at its true radius, its outline the solver's sphere."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.animation_data_clear()
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ball = bpy.context.object
    world = ball.matrix_world.copy()
    ball.parent = None
    ball.matrix_world = world
    for obj in imported:
        if obj != ball and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if ball.data.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    lo = Vector(tuple(min(v.co[i] for v in ball.data.vertices) for i in range(3)))
    hi = Vector(tuple(max(v.co[i] for v in ball.data.vertices) for i in range(3)))
    centre = (lo + hi) / 2
    for vertex in ball.data.vertices:
        vertex.co = (vertex.co - centre) * (2 * radius / max(hi - lo))
    ball.location = (0, 0, 0)
    ball.name = 'Basketball'
    # Subdivide, then put every vertex back on the physical radius: the outline
    # is then the solver's sphere, not a polygon or a cage shrunk inside it.
    smooth = ball.modifiers.new('Round outline', 'SUBSURF')
    smooth.levels = smooth.render_levels = 2
    bpy.ops.object.modifier_apply(modifier=smooth.name)
    for vertex in ball.data.vertices:
        vertex.co = vertex.co.normalized() * radius
    for poly in ball.data.polygons:
        poly.use_smooth = True
    # The model's own colour, ORM and normal maps, without the trademarks; a fine
    # bump and a matte sheen only where the model has no maps of its own.
    for mat in ball.data.materials:
        if not mat or not mat.use_nodes:
            continue
        if not cover_logos(mat):
            raise ValueError('the ball material has no textures to cover the logos in')
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        bsdf.inputs['Emission Strength'].default_value = 0.0
        if not bsdf.inputs['Roughness'].is_linked:
            bsdf.inputs['Roughness'].default_value = 0.62
        if not bsdf.inputs['Normal'].is_linked:
            coord = nodes.new('ShaderNodeTexCoord')
            pebble = nodes.new('ShaderNodeTexVoronoi')
            pebble.inputs['Scale'].default_value = 260.0
            links.new(coord.outputs['Object'], pebble.inputs['Vector'])
            bump = nodes.new('ShaderNodeBump')
            bump.inputs['Strength'].default_value = 0.25
            bump.inputs['Distance'].default_value = 0.0006
            links.new(pebble.outputs['Distance'], bump.inputs['Height'])
            links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return ball


# ---------------------------------------------------------------------- hall


def build_room(scenario):
    """Hall, goal, lamps, daylight. Returns the collider surfaces and the props."""
    layout = scenario['layout']
    shell, windows = hall.build_shell()
    hall.pendant_lamps(float(layout['lamp_power']))
    crate = hall.props()
    hall.daylight(layout, target=(-6.0, 6.0, FZ))
    colliders, goal_props = build_goal()
    floor = bpy.data.objects['Hall floor']
    skip = {o.name for o in colliders} | {floor.name}
    props = [o for o in bpy.context.scene.objects
             if o.type == 'MESH' and o.name not in skip and o.visible_camera
             and not o.name.startswith('Ground outside')]
    return {'colliders': colliders + [floor], 'props': props, 'windows': windows}
