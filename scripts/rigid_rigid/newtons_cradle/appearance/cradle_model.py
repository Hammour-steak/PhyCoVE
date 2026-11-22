"""The desk cradle at its simulated size: chrome-plated steel balls on nylon
lines from a bent chrome tube frame, on a black lacquered base.

Everything here follows the simulator's numbers (scene_geometry.pivots and the
physics block of the scenario):

* the balls are ``ball_radius`` spheres keyed to the simulated poses;
* each top rail runs through the pivot points at ``pivot_height`` and
  y = +/-SUSPENSION_HALF_SPAN, so the two lines of every ball hang from the
  pendulum's own hinge axis;
* each line ends at a screw eye on top of its ball. Both ends are fixed in the
  pendulum's rigid frame (the rail point lies on the hinge axis), so the lines
  are children of their ball: they swing with it and never stretch.

The frame posts stand outside the widest swing of any case (the posts are at
+/-FRAME_HALF_LENGTH; the farthest ball centre in the six cases reaches
0.232 m). Nothing here takes part in the simulation.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

# Base and frame (metres). The frame is two tubes bent into an inverted U; the
# posts stand at +/- FRAME_HALF_LENGTH.
BASE_SIZE = (.60, .23, .036)
BASE_EDGE_RADIUS = .010
FRAME_HALF_LENGTH = .265      # x of the posts
SUSPENSION_HALF_SPAN = .065   # y of the two top rails = line anchors
TUBE_RADIUS = .005            # 10 mm chrome tube
TUBE_BEND_RADIUS = .024
LINE_RADIUS = .00025          # 0.5 mm nylon monofilament
EYE_RING_MAJOR = .0022
EYE_RING_MINOR = .0006

# Keep-out box around the cradle and every ball position of every case. The
# renderer checks each frame's balls are inside it and every prop stays at
# least PROP_CLEARANCE_M outside it.
KEEP_OUT = dict(x=(-.31, .31), y=(-.125, .125), z=(.0, 1.02))
PROP_CLEARANCE_M = .02


def chrome(name, roughness=.035):
    """Polished chrome plating: a near-white metal whose roughness drifts a
    little with handling marks, so reflections stay crisp but not CG-perfect."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (.62, .63, .64, 1)
    bsdf.inputs['Metallic'].default_value = 1.
    bsdf.inputs['Specular Tint'].default_value = (.82, .84, .86, 1)
    coord = nodes.new('ShaderNodeTexCoord')
    smudge = nodes.new('ShaderNodeTexNoise')
    smudge.inputs['Scale'].default_value = 60.
    smudge.inputs['Detail'].default_value = 4.
    smudge.inputs['Roughness'].default_value = .65
    links.new(coord.outputs['Object'], smudge.inputs['Vector'])
    ramp = nodes.new('ShaderNodeMapRange')
    ramp.inputs['From Min'].default_value = .45
    ramp.inputs['From Max'].default_value = .85
    ramp.inputs['To Min'].default_value = roughness
    ramp.inputs['To Max'].default_value = roughness * 2.4
    links.new(smudge.outputs['Fac'], ramp.inputs['Value'])
    links.new(ramp.outputs['Result'], bsdf.inputs['Roughness'])
    mat.diffuse_color = (.62, .63, .64, 1)
    return mat


def black_lacquer(name):
    """Piano-black lacquer on the base: a clear coat over near-black paint,
    with faint dust and polishing marks in the coat's roughness."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (.010, .010, .011, 1)
    bsdf.inputs['Roughness'].default_value = .35
    bsdf.inputs['Coat Weight'].default_value = 1.
    coord = nodes.new('ShaderNodeTexCoord')
    marks = nodes.new('ShaderNodeTexNoise')
    marks.inputs['Scale'].default_value = 35.
    marks.inputs['Detail'].default_value = 6.
    links.new(coord.outputs['Object'], marks.inputs['Vector'])
    coat = nodes.new('ShaderNodeMapRange')
    coat.inputs['From Min'].default_value = .4
    coat.inputs['From Max'].default_value = .8
    coat.inputs['To Min'].default_value = .025
    coat.inputs['To Max'].default_value = .09
    links.new(marks.outputs['Fac'], coat.inputs['Value'])
    links.new(coat.outputs['Result'], bsdf.inputs['Coat Roughness'])
    mat.diffuse_color = (.01, .01, .011, 1)
    return mat


def nylon(name):
    """Clear nylon monofilament: pale, glossy and a little translucent."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (.78, .78, .76, 1)
    bsdf.inputs['Roughness'].default_value = .22
    bsdf.inputs['Transmission Weight'].default_value = .35
    mat.diffuse_color = (.78, .78, .76, 1)
    return mat


def _tag(obj):
    obj['cradle_part'] = True
    return obj


def _rounded_box(bpy, name, centre, size, radius, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=centre)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    mod = obj.modifiers.new('Rounded edges', 'BEVEL')
    mod.width, mod.segments, mod.limit_method = radius, 6, 'ANGLE'
    obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return _tag(obj)


def _cylinder(bpy, name, centre, radius, depth, axis, mat, vertices=32):
    rotation = {'x': (0, math.pi / 2, 0), 'y': (math.pi / 2, 0, 0), 'z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=centre, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    mod = obj.modifiers.new('Eased edges', 'BEVEL')
    mod.width, mod.segments, mod.limit_method = min(radius, depth) * .18, 2, 'ANGLE'
    return _tag(obj)


def _bent_tube(bpy, name, y, z_foot, z_top, mat):
    """One inverted-U frame: two posts and the top rail, bent from a single
    tube with TUBE_BEND_RADIUS corners. The rail's axis is at z_top."""
    points = [(-FRAME_HALF_LENGTH, y, z_foot), (-FRAME_HALF_LENGTH, y, z_top - TUBE_BEND_RADIUS)]
    steps = 14
    for side, cx in ((-1, -FRAME_HALF_LENGTH + TUBE_BEND_RADIUS), (1, FRAME_HALF_LENGTH - TUBE_BEND_RADIUS)):
        arc = []
        for k in range(1, steps):
            a = math.pi / 2 * k / steps
            # left corner turns from straight up to +x; right corner from +x to down.
            if side < 0:
                arc.append((cx - TUBE_BEND_RADIUS * math.cos(a), y, z_top - TUBE_BEND_RADIUS + TUBE_BEND_RADIUS * math.sin(a)))
            else:
                arc.append((cx + TUBE_BEND_RADIUS * math.sin(a), y, z_top - TUBE_BEND_RADIUS + TUBE_BEND_RADIUS * math.cos(a)))
        if side < 0:
            points += arc + [(cx, y, z_top)]
        else:
            points += [(cx, y, z_top)] + arc
    points += [(FRAME_HALF_LENGTH, y, z_top - TUBE_BEND_RADIUS), (FRAME_HALF_LENGTH, y, z_foot)]
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = TUBE_RADIUS
    curve.bevel_resolution = 6
    curve.use_fill_caps = True
    spline = curve.splines.new('POLY')
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1.)
    spline.use_smooth = True
    curve.materials.append(mat)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    return _tag(obj)


def _line(bpy, name, start, end, mat, parent):
    """A nylon line between two points given in the parent's local frame."""
    from mathutils import Vector
    a, b = Vector(start), Vector(end)
    delta = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=LINE_RADIUS, depth=1., location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.parent = parent
    obj.matrix_parent_inverse.identity()
    obj.location = (a + b) / 2
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = delta.to_track_quat('Z', 'Y')
    obj.scale = (1., 1., delta.length)
    return _tag(obj)


def build_cradle(bpy, c, anchors, presence):
    """Base, frame and the present balls with their lines.

    Returns ``(balls, parts)``: the ball objects by simulator key (the only
    objects keyed to the simulation) and every other cradle object.
    """
    top = c['table_height']
    radius, length, pivot_z = c['ball_radius'], c['pendulum_length'], c['pivot_height']
    steel = chrome('Chrome-plated steel balls', .03)
    tube = chrome('Chrome-plated frame tube', .045)
    lacquer = black_lacquer('Piano-black lacquered base')
    line = nylon('Clear nylon monofilament')
    parts = []
    base_top = top + BASE_SIZE[2]
    parts.append(_rounded_box(bpy, 'Cradle base', (0, 0, top + BASE_SIZE[2] / 2), BASE_SIZE, BASE_EDGE_RADIUS, lacquer))
    for y in (-SUSPENSION_HALF_SPAN, SUSPENSION_HALF_SPAN):
        parts.append(_bent_tube(bpy, f'Frame tube y{y:+.3f}', y, base_top - .006, pivot_z, tube))
        for x in (-FRAME_HALF_LENGTH, FRAME_HALF_LENGTH):
            parts.append(_cylinder(bpy, 'Frame post ferrule', (x, y, base_top + .0025), .0085, .005, 'z', tube))
    balls = {}
    for i, anchor in enumerate(anchors):
        key = f'ball_{i:02d}'
        if not presence[i]:
            # Deleted slot: no ball, no lines and no line clamps; the GT marks
            # the object absent on every frame, matching the simulation.
            continue
        for y in (-SUSPENSION_HALF_SPAN, SUSPENSION_HALF_SPAN):
            parts.append(_cylinder(bpy, f'{key} line clamp', (anchor[0], y, pivot_z), .0068, .007, 'x', tube, 24))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=radius)
        ball = bpy.context.object
        ball.name = key
        ball.data.materials.append(steel)
        for poly in ball.data.polygons:
            poly.use_smooth = True
        _tag(ball)
        balls[key] = ball
        # Screw eye on top of the ball, in the ball's own frame: a short shank
        # and a ring in the y-z plane that the two lines pass through.
        shank = _cylinder(bpy, f'{key} screw eye shank', (0, 0, radius + .0012), .0014, .0040, 'z', tube, 16)
        shank.parent = ball
        bpy.ops.mesh.primitive_torus_add(major_radius=EYE_RING_MAJOR, minor_radius=EYE_RING_MINOR, major_segments=24,
                                         minor_segments=8, location=(0, 0, radius + .0032 + EYE_RING_MAJOR),
                                         rotation=(0, math.pi / 2, 0))
        ring = bpy.context.object
        ring.name = f'{key} screw eye ring'
        ring.data.materials.append(tube)
        for poly in ring.data.polygons:
            poly.use_smooth = True
        ring.parent = ball
        _tag(ring)
        parts += [shank, ring]
        eye = (0., 0., radius + .0032 + 2 * EYE_RING_MAJOR - EYE_RING_MINOR)
        for y in (-SUSPENSION_HALF_SPAN, SUSPENSION_HALF_SPAN):
            # The rail point (0, y, length) in the ball frame is the hinge axis.
            parts.append(_line(bpy, f'{key} nylon line y{y:+.3f}', (0., y, length), eye, line, ball))
    return balls, parts
