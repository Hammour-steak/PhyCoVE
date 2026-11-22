"""An industrial loft kitchen built on the solver's own colliders.

Every surface a bowl can touch is drawn from ``room_colliders.json`` and
``scene_geometry`` -- the same numbers PyBullet collides -- so the visible
contact face *is* the collision face:

* the wall-run counter (cast concrete), its hob (black glass, 11 mm proud),
  the brick back wall, and the brick pier that closes the run on the right
  (the solver's ``wall_kitchen_end``, where the heavy-bowl case stops);
* the open wall cupboard over the hob, board for board as the solver builds it.

Around them: a loft shell (red brick, board-formed concrete soffit, an old
maple strip floor), black steel windows, oak joinery, and a few scanned props,
all checked against every solved frame (``check_props``). Light comes only
through the windows: a low late-afternoon sun through a big steel window in
the left wall, just out of frame, and sky through it, through the steel window
in the back wall and through one more behind the camera. No lamp is hidden
anywhere.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from room_colliders import load_colliders
from scene_geometry import (CABINET_X_MIN, CABINET_X_MAX, CABINET_Z_BOTTOM, CABINET_Z_TOP,
                            CABINET_FRONT_Y, CABINET_BACK_Y, PANEL_T, BOARD_TOP_Z, SHELF_Z,
                            SHELF_T, DOOR_T, DOOR_OPEN_DEG, DOOR_HINGE_X)
from look_kitchen_bowl_fall import (POLYHAVEN, plain, scanned, box, world_uv, lathe, fit_profile,
                                    dish_glazes, stack, PLATE, RICE_BOWL, SERVING_BOWL)

CEILING_Z = 3.30          # a loft soffit, 3.39 m clear (the solver has no ceiling below 2.75 m)
WALL_T = .35              # solid brick
# The big steel window in the back wall, left of the cupboard (x span, z span),
# on the shaded side of the building. Its glass sits 0.22 m into the 0.35 m
# reveal, as old steel windows do in masonry.
BACK_WINDOW = ((-1.62, -.62), (1.12, 3.00))
# The sun's window: as big again, in the left wall, just out of frame
# (y span, z span).
SIDE_WINDOW = ((.15, 2.70), (.75, 3.15))
# A second one on the front wall, behind the camera: the room's other light.
FRONT_WINDOW = ((-2.30, .70), (.75, 3.00))
SINK_CUT = ((.55, 1.15), (2.90, 3.30))     # undermount sink, clear of every bowl path
SINK_DEPTH = .20

# Late-afternoon sun. HEADING: direction the light travels, degrees from +x
# towards +y. It comes in low through the side window, rakes along the brick,
# reaches into the open cupboard (the bowl is in sun at frame 1) and lays the
# window grid over the hob and the counter the bowls land on.
SUN_HEADING_DEG = 20.
SUN_ELEVATION_DEG = 18.
SUN_STRENGTH = 3.6
SUN_COLOR = (1., .80, .60)
SKY_STRENGTH = .45
# What the camera sees through the back window: Poly Haven docklands_01, a
# river quay with far buildings across the water, shot from standing height --
# the outlook of a ground-floor warehouse loft. Its sun sits at pixel
# u = 0.6058 (measured: brightest pixel of the 4k file), i.e. azimuth
# (0.5 - u) * 360 = -38.1 deg in the photograph's frame; the photograph is turned
# so that sun stands where the lamp is, which puts the river and the far bank
# in the window. It is visible to camera rays only.
WINDOW_VIEW = 'docklands_01_4k.hdr'
WINDOW_VIEW_SUN_AZIMUTH_DEG = -38.1
WINDOW_VIEW_STRENGTH = 1.0

PROPS = []                # every non-collider object, checked against the solved frames


def _span(boxes, name):
    b = boxes[name]
    c, h = b['center'], b['half_extents']
    return [c[i] - h[i] for i in range(3)], [c[i] + h[i] for i in range(3)]


def _prop(obj):
    PROPS.append(obj)
    return obj


def _aim(obj, point):
    from mathutils import Vector
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


# ----------------------------------------------------------------- finishes

def finishes(bpy):
    f = {}
    f['brick'] = scanned(bpy, 'Red brick / red_bricks_04', 'red_bricks_04', 2.5, value=.92,
                         normal_strength=1.2)
    f['concrete_top'] = scanned(bpy, 'Cast concrete counter / concrete_floor_worn_001',
                                'concrete_floor_worn_001', 3.0, value=1.45, saturation=.85,
                                rough_scale=.85, rough_offset=-.04, normal_strength=.6)
    f['soffit'] = scanned(bpy, 'Board-formed concrete soffit / concrete', 'concrete', 4.0, value=.95,
                          normal_strength=.8)
    f['floor'] = scanned(bpy, 'Old maple strip floor / old_wooden_floor_01', 'old_wooden_floor_01', 2.0,
                         value=.82, saturation=.85, rough_scale=1.1, rough_offset=.05)
    f['oak'] = scanned(bpy, 'Smoked oak veneer / mocha_oak_veneer', 'mocha_oak_veneer', 1.0,
                       value=.58, saturation=1.35, tint=(.80, .60, .42), rough_scale=1., rough_offset=.08,
                       normal_strength=1.4)
    f['oak_board'] = scanned(bpy, 'Oiled oak boards / mocha_oak_veneer', 'mocha_oak_veneer', 1.0,
                             value=.70, saturation=1.30, tint=(.86, .66, .46), rough_offset=.02)
    f['steel'] = plain(bpy, 'Black painted steel', (.016, .016, .017), .46, grain=.25)
    f['steel_raw'] = plain(bpy, 'Blackened raw steel', (.06, .058, .055), .38, metallic=.85, grain=.35)
    f['carcass'] = plain(bpy, 'Cabinet carcass shadow', (.035, .032, .03), .8)
    f['stainless'] = plain(bpy, 'Brushed stainless sink', (.62, .62, .61), .27, metallic=1.)
    f['terracotta'] = plain(bpy, 'Unglazed terracotta', (.42, .19, .10), .85, grain=.12)
    f['glass'] = window_glass(bpy)
    f['hob'] = hob_glass(bpy)
    f.update(dish_glazes(bpy))
    return f


def window_glass(bpy):
    """Thin float glass: a Fresnel reflection over a see-through layer.

    A 6 mm pane displaces nothing worth refracting, so it is shaded as a
    transparent surface; camera rays through it stay camera rays (the world
    then shows them the city), and the panes are invisible to shadow rays so
    the sun lamp is not stopped by them either."""
    m = bpy.data.materials.new('Clear float glass')
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    for node in [x for x in n if x.type != 'OUTPUT_MATERIAL']:
        n.remove(node)
    clear = n.new('ShaderNodeBsdfTransparent')
    refl = n.new('ShaderNodeBsdfGlossy')
    refl.inputs['Roughness'].default_value = 0.
    fres = n.new('ShaderNodeFresnel')
    fres.inputs['IOR'].default_value = 1.52
    mix = n.new('ShaderNodeMixShader')
    l.new(fres.outputs['Fac'], mix.inputs['Fac'])
    l.new(clear.outputs['BSDF'], mix.inputs[1])
    l.new(refl.outputs['BSDF'], mix.inputs[2])
    l.new(mix.outputs['Shader'], n['Material Output'].inputs['Surface'])
    return m


HOB_ZONES = ((-.66, 2.83, .095), (-.66, 3.12, .085), (-.33, 2.99, .135), (-.02, 2.83, .085), (-.02, 3.12, .095))


def hob_glass(bpy):
    """Black ceramic glass with the five cooking zones screen-printed as thin
    grey rings -- no lettering, no display, no logo."""
    m = bpy.data.materials.new('Black ceramic hob glass')
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    bs = n.get('Principled BSDF')
    bs.inputs['Roughness'].default_value = .045
    bs.inputs['IOR'].default_value = 1.54
    pos = n.new('ShaderNodeNewGeometry')
    sep = n.new('ShaderNodeSeparateXYZ')
    l.new(pos.outputs['Position'], sep.inputs['Vector'])
    ring_sum = None
    for cx, cy, r in HOB_ZONES:
        dx = n.new('ShaderNodeMath'); dx.operation = 'SUBTRACT'; dx.inputs[1].default_value = cx
        dy = n.new('ShaderNodeMath'); dy.operation = 'SUBTRACT'; dy.inputs[1].default_value = cy
        l.new(sep.outputs['X'], dx.inputs[0]); l.new(sep.outputs['Y'], dy.inputs[0])
        vec = n.new('ShaderNodeCombineXYZ')
        l.new(dx.outputs['Value'], vec.inputs['X']); l.new(dy.outputs['Value'], vec.inputs['Y'])
        length = n.new('ShaderNodeVectorMath'); length.operation = 'LENGTH'
        l.new(vec.outputs['Vector'], length.inputs[0])
        off = n.new('ShaderNodeMath'); off.operation = 'SUBTRACT'; off.inputs[1].default_value = r
        l.new(length.outputs['Value'], off.inputs[0])
        ab = n.new('ShaderNodeMath'); ab.operation = 'ABSOLUTE'
        l.new(off.outputs['Value'], ab.inputs[0])
        line = n.new('ShaderNodeMath'); line.operation = 'LESS_THAN'; line.inputs[1].default_value = .0012
        l.new(ab.outputs['Value'], line.inputs[0])
        if ring_sum is None:
            ring_sum = line.outputs['Value']
        else:
            add = n.new('ShaderNodeMath'); add.operation = 'MAXIMUM'
            l.new(ring_sum, add.inputs[0]); l.new(line.outputs['Value'], add.inputs[1])
            ring_sum = add.outputs['Value']
    col = n.new('ShaderNodeMixRGB')
    col.inputs['Color1'].default_value = (.004, .004, .0045, 1)
    col.inputs['Color2'].default_value = (.10, .10, .10, 1)
    l.new(ring_sum, col.inputs['Fac'])
    l.new(col.outputs['Color'], bs.inputs['Base Color'])
    rough = n.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = .045
    rough.inputs['To Max'].default_value = .35
    l.new(ring_sum, rough.inputs['Value'])
    l.new(rough.outputs['Result'], bs.inputs['Roughness'])
    return m


# -------------------------------------------------------------- the shell

def wall_with_opening(bpy, name, axis, face, outward, u_span, z_span, hole, mat):
    """A brick wall of constant ``axis`` coordinate (inner face at ``face``,
    thickness running ``outward``), built as four pieces around an opening so
    the reveal shows the wall's real depth."""
    t0, t1 = sorted((face, face + outward * WALL_T))
    (u0, u1), (z0, z1) = u_span, z_span

    def piece(suffix, ua, ub, za, zb):
        if ub - ua < 1e-6 or zb - za < 1e-6:
            return None
        if axis == 'y':
            return box(bpy, f'{name} {suffix}', (ua, t0, za), (ub, t1, zb), mat)
        return box(bpy, f'{name} {suffix}', (t0, ua, za), (t1, ub, zb), mat)

    if hole is None:
        return [piece('', u0, u1, z0, z1)]
    (hu0, hu1), (hz0, hz1) = hole
    return [piece('below opening', hu0, hu1, z0, hz0), piece('above opening', hu0, hu1, hz1, z1),
            piece('beside opening (low)', u0, hu0, z0, z1), piece('beside opening (high)', hu1, u1, z0, z1)]


def steel_window(bpy, name, axis, plane, u_span, z_span, cols, rows, f):
    """A divided-lite steel window (Crittall-style) filling an opening.

    Outer frame 45 mm, glazing bars 22 mm, all black painted steel; one pane
    of thin glass behind the bars. ``axis`` is the wall's constant coordinate."""
    (u0, u1), (z0, z1) = u_span, z_span

    def bar(label, ua, ub, za, zb, depth):
        if axis == 'y':
            return box(bpy, f'{name} {label}', (ua, plane - depth / 2, za), (ub, plane + depth / 2, zb),
                       f['steel'], bevel=.0015)
        return box(bpy, f'{name} {label}', (plane - depth / 2, ua, za), (plane + depth / 2, ub, zb),
                   f['steel'], bevel=.0015)

    parts = []
    fw, fd, mw, md = .045, .06, .022, .04
    parts += [bar('head', u0, u1, z1 - fw, z1, fd), bar('sill', u0, u1, z0, z0 + fw, fd),
              bar('jamb a', u0, u0 + fw, z0 + fw, z1 - fw, fd), bar('jamb b', u1 - fw, u1, z0 + fw, z1 - fw, fd)]
    for i in range(1, cols):
        u = u0 + fw + (u1 - u0 - 2 * fw) * i / cols
        parts.append(bar(f'mullion {i}', u - mw / 2, u + mw / 2, z0 + fw, z1 - fw, md))
    for j in range(1, rows):
        z = z0 + fw + (z1 - z0 - 2 * fw) * j / rows
        parts.append(bar(f'transom {j}', u0 + fw, u1 - fw, z - mw / 2, z + mw / 2, md - .004))
    off = .012
    if axis == 'y':
        pane = box(bpy, f'{name} glass', (u0 + fw * .5, plane + off, z0 + fw * .5),
                   (u1 - fw * .5, plane + off + .006, z1 - fw * .5), f['glass'])
    else:
        pane = box(bpy, f'{name} glass', (plane - off - .006, u0 + fw * .5, z0 + fw * .5),
                   (plane - off, u1 - fw * .5, z1 - fw * .5), f['glass'])
    pane.visible_shadow = False
    parts.append(pane)
    for p in parts:
        _prop(p)
    return parts


def build_shell(bpy, f, boxes):
    floor_lo, floor_hi = _span(boxes, 'floor')
    fz = floor_hi[2]
    back_y = _span(boxes, 'wall_tiles')[0][1]
    left_x = _span(boxes, 'wall_left')[1][0]
    right_x = _span(boxes, 'wall_right')[0][0]
    front_y = _span(boxes, 'wall_front')[1][1]
    # The floor runs under every wall so no seam can leak daylight.
    box(bpy, 'Maple strip floor', (left_x - WALL_T, front_y - WALL_T, fz - .12),
        (right_x + WALL_T, back_y + WALL_T, fz), f['floor'])
    box(bpy, 'Concrete soffit', (left_x - WALL_T, front_y - WALL_T, CEILING_Z),
        (right_x + WALL_T, back_y + WALL_T, CEILING_Z + .25), f['soffit'])
    xs = (left_x - WALL_T, right_x + WALL_T)
    ys = (front_y - WALL_T, back_y + WALL_T)
    wall_with_opening(bpy, 'Back wall (brick)', 'y', back_y, 1, xs, (fz, CEILING_Z), BACK_WINDOW, f['brick'])
    wall_with_opening(bpy, 'Front wall (brick)', 'y', front_y, -1, xs, (fz, CEILING_Z), FRONT_WINDOW, f['brick'])
    wall_with_opening(bpy, 'Left wall (brick)', 'x', left_x, -1, (front_y, back_y), (fz, CEILING_Z),
                      SIDE_WINDOW, f['brick'])
    wall_with_opening(bpy, 'Right wall (brick)', 'x', right_x, 1, (front_y, back_y), (fz, CEILING_Z), None,
                      f['brick'])
    # The brick pier that ends the counter run: the solver's wall_kitchen_end,
    # carried on up to the soffit.
    plo, phi = _span(boxes, 'wall_kitchen_end')
    box(bpy, 'Brick pier (kitchen end wall)', (plo[0], plo[1], fz), (phi[0], back_y, CEILING_Z), f['brick'])
    # Windows, set into their reveals, with concrete sills inside.
    steel_window(bpy, 'Back window', 'y', back_y + .22, *BACK_WINDOW, 3, 5, f)
    steel_window(bpy, 'Side window', 'x', left_x - .22, *SIDE_WINDOW, 4, 4, f)
    steel_window(bpy, 'Front window', 'y', front_y - .22, *FRONT_WINDOW, 4, 4, f)
    (sx0, sx1), (sz0, _) = BACK_WINDOW
    _prop(box(bpy, 'Back window sill', (sx0, back_y - .015, sz0 - .03), (sx1, back_y + .19, sz0),
              f['concrete_top'], bevel=.003))
    return dict(floor_z=fz, back_y=back_y, left_x=left_x, right_x=right_x, front_y=front_y)


# ------------------------------------------------------------ the kitchen

def build_counter(bpy, f, boxes, shell):
    clo, chi = _span(boxes, 'counter_wall')
    plo, _ = _span(boxes, 'wall_kitchen_end')
    back_y = shell['back_y']
    x0, x1 = clo[0], plo[0]
    # The slab is one mesh with the sink hole cut through it, so the eased
    # edge runs round the hole and no joint shows on the top.
    slab = box(bpy, 'Cast concrete counter', (x0, clo[1], clo[2]), (x1, back_y, chi[2]), f['concrete_top'])
    cut = box(bpy, 'sink cut', (SINK_CUT[0][0], SINK_CUT[1][0], clo[2] - .05),
              (SINK_CUT[0][1], SINK_CUT[1][1], chi[2] + .05), f['concrete_top'])
    boolean = slab.modifiers.new('Sink cut', 'BOOLEAN')
    boolean.operation = 'DIFFERENCE'
    boolean.solver = 'EXACT'
    boolean.object = cut
    bpy.context.view_layer.objects.active = slab
    bpy.ops.object.modifier_apply(modifier=boolean.name)
    bpy.data.objects.remove(cut, do_unlink=True)
    world_uv(slab)
    for p in slab.data.polygons:
        p.use_smooth = True
    bevel = slab.modifiers.new('Eased edges', 'BEVEL')
    bevel.width, bevel.segments, bevel.limit_method, bevel.harden_normals = .003, 2, 'ANGLE', True
    # Hob glass: exactly the solver's hob box, with a ground facet on the edge.
    hlo, hhi = _span(boxes, 'hob')
    box(bpy, 'Induction hob glass', hlo, hhi, f['hob'], bevel=.003)
    # Undermount stainless basin hanging under the hole.
    (ax0, ax1), (ay0, ay1) = SINK_CUT
    import bmesh
    mesh = bpy.data.meshes.new('Sink basin')
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.)
    zb, zt = chi[2] - SINK_DEPTH, clo[2] + .001
    for v in bm.verts:
        v.co.x = ax0 - .002 if v.co.x < 0 else ax1 + .002
        v.co.y = ay0 - .002 if v.co.y < 0 else ay1 + .002
        v.co.z = zb if v.co.z < 0 else zt
    top = [face for face in bm.faces if face.normal.z > .5]
    bmesh.ops.delete(bm, geom=top, context='FACES')
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    basin = bpy.data.objects.new('Sink basin', mesh)
    bpy.context.scene.collection.objects.link(basin)
    mesh.materials.append(f['stainless'])
    for p in mesh.polygons:
        p.use_smooth = True
    sol = basin.modifiers.new('Sheet', 'SOLIDIFY')
    sol.thickness = .0012
    bev = basin.modifiers.new('Coved corners', 'BEVEL')
    bev.width, bev.segments, bev.limit_method = .025, 4, 'ANGLE'
    _prop(basin)
    drain = lathe(bpy, 'Sink drain', [(0., .0), (.040, .0), (.043, .003), (.0, .003)], f['stainless'], 48)
    drain.location = ((ax0 + ax1) / 2, (ay0 + ay1) / 2 + .05, zb + .0005)
    hole = lathe(bpy, 'Sink drain grate', [(0., .0), (.030, .0), (.030, .0035), (.0, .0035)], f['carcass'], 48)
    hole.location = drain.location
    _prop(drain); _prop(hole)
    build_faucet(bpy, f, ((ax0 + ax1) / 2, ay1 + .065, chi[2]))
    return dict(x0=x0, x1=x1, front_y=clo[1], top_z=chi[2], bottom_z=clo[2])


def build_faucet(bpy, f, base):
    """A matte black gooseneck mixer behind the sink: deck flange, riser, a
    120 mm bend, the spout pointing down into the basin, side lever."""
    bx, by, bz = base
    flange = lathe(bpy, 'Faucet flange', [(0, 0), (.029, 0), (.030, .004), (.026, .010), (.020, .014), (0, .014)],
                   f['steel'], 48)
    flange.location = (bx, by, bz)
    _prop(flange)
    curve = bpy.data.curves.new('Faucet spout', 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = .0145
    curve.bevel_resolution = 6
    curve.use_fill_caps = True
    spline = curve.splines.new('POLY')
    pts = [(bx, by, bz + .010), (bx, by, bz + .30)]
    r, cz, cy = .095, bz + .30, by - .095
    for k in range(1, 25):
        a = math.pi * k / 24
        pts.append((bx, cy + r * math.cos(a), cz + r * math.sin(a)))
    pts.append((bx, by - 2 * r, bz + .245))
    spline.points.add(len(pts) - 1)
    for p, co in zip(spline.points, pts):
        p.co = (*co, 1)
    spout = bpy.data.objects.new('Faucet spout', curve)
    bpy.context.scene.collection.objects.link(spout)
    curve.materials.append(f['steel'])
    _prop(spout)
    lever = box(bpy, 'Faucet lever', (bx + .014, by - .006, bz + .085), (bx + .085, by + .006, bz + .097),
                f['steel'], bevel=.004)
    hub = lathe(bpy, 'Faucet lever hub', [(0, 0), (.018, 0), (.018, .03), (0, .03)], f['steel'], 32)
    hub.rotation_euler = (0, math.pi / 2, 0)
    hub.location = (bx + .005, by, bz + .091)
    _prop(lever); _prop(hub)


def bar_pull(bpy, f, name, centre, length, vertical):
    """A 12 mm black steel bar pull on two standoffs, 32 mm proud of the front."""
    x, y, z = centre
    r = .006
    if vertical:
        parts = [box(bpy, f'{name} bar', (x - r, y - .032 - r, z - length / 2), (x + r, y - .032 + r, z + length / 2),
                     f['steel_raw'], bevel=.0045)]
        for s in (-1, 1):
            zz = z + s * (length / 2 - .025)
            parts.append(box(bpy, f'{name} post', (x - .004, y - .032, zz - .004), (x + .004, y, zz + .004),
                             f['steel_raw'], bevel=.002))
    else:
        parts = [box(bpy, f'{name} bar', (x - length / 2, y - .032 - r, z - r), (x + length / 2, y - .032 + r, z + r),
                     f['steel_raw'], bevel=.0045)]
        for s in (-1, 1):
            xx = x + s * (length / 2 - .025)
            parts.append(box(bpy, f'{name} post', (xx - .004, y - .032, z - .004), (xx + .004, y, z + .004),
                             f['steel_raw'], bevel=.002))
    for p in parts:
        _prop(p)
    return parts


def build_base_units(bpy, f, counter, shell):
    """Slab-front oak base units under the run, recessed 23 mm under the
    concrete, on a black plinth; pan drawers under the hob, doors under the sink."""
    fz = shell['floor_z']
    front, t = counter['front_y'] + .023, .019
    top = counter['bottom_z'] - .009
    plinth_top = fz + .10
    x0, x1 = counter['x0'] + .018, counter['x1']
    gap = .003
    # Dark carcass behind the fronts so the 3 mm gaps read as gaps.
    _prop(box(bpy, 'Base units carcass', (x0, front + t, plinth_top), (x1, shell['back_y'], counter['bottom_z']),
              f['carcass']))
    _prop(box(bpy, 'Base units plinth', (x0, front + .06, fz), (x1, shell['back_y'], plinth_top + .004), f['steel']))
    _prop(box(bpy, 'Base units end panel', (counter['x0'], front, fz), (counter['x0'] + .018, shell['back_y'],
                                                                        counter['bottom_z']),
              f['oak'], bevel=.0015, swap_vertical=True))
    columns = [(x0, -.86, 'drawers3'), (-.86, .20, 'drawers2'), (.20, .50, 'door_r'),
               (.50, .85, 'door_l'), (.85, 1.20, 'door_r'), (1.20, x1, 'door_l')]
    z0 = plinth_top + gap
    for k, (a, b, kind) in enumerate(columns):
        a, b = a + gap / 2, b - gap / 2
        if kind.startswith('drawers'):
            splits = [.20, .36] if kind == 'drawers3' else [.31]
            edges = [z0]
            for s in splits:
                edges.append(edges[-1] + s)
            edges.append(top)
            for j in range(len(edges) - 1):
                lo = (a, front, edges[j] + gap / 2)
                hi = (b, front + t, edges[j + 1] - gap / 2)
                _prop(box(bpy, f'Base drawer {k}.{j}', lo, hi, f['oak'], bevel=.0015))
                bar_pull(bpy, f, f'Drawer pull {k}.{j}', ((a + b) / 2, front, hi[2] - .045),
                         min(.42, (b - a) * .55), False)
        else:
            _prop(box(bpy, f'Base door {k}', (a, front, z0), (b, front + t, top), f['oak'], bevel=.0015,
                      swap_vertical=True))
            px = b - .04 if kind == 'door_l' else a + .04
            bar_pull(bpy, f, f'Door pull {k}', (px, front, top - .14), .18, True)


def build_island(bpy, f, boxes, shell):
    """The island behind the camera, on the solver's island box: never in
    frame, but it is in the room, so it shades and bounces the light."""
    lo, hi = _span(boxes, 'counter')
    box(bpy, 'Island concrete top', lo, hi, f['concrete_top'], bevel=.003)
    _prop(box(bpy, 'Island base', (lo[0] + .03, lo[1] + .03, shell['floor_z']), (hi[0] - .03, hi[1] - .03, lo[2]),
              f['oak']))


def build_cupboard(bpy, f):
    """The open wall cupboard over the hob, board for board as the solver
    builds it (scene_geometry): carcass, fixed shelf, door open 104 deg on its
    right hinge. Smoked oak outside and in."""
    t = PANEL_T
    oak = f['oak']
    cx = (CABINET_X_MIN + CABINET_X_MAX) / 2
    box(bpy, 'Cupboard bottom', (CABINET_X_MIN, CABINET_FRONT_Y, CABINET_Z_BOTTOM),
        (CABINET_X_MAX, CABINET_BACK_Y, BOARD_TOP_Z), oak, bevel=.0012)
    box(bpy, 'Cupboard top', (CABINET_X_MIN, CABINET_FRONT_Y, CABINET_Z_TOP - t),
        (CABINET_X_MAX, CABINET_BACK_Y, CABINET_Z_TOP), oak, bevel=.0012)
    for name, xa in (('left', CABINET_X_MIN), ('right', CABINET_X_MAX - t)):
        box(bpy, f'Cupboard side {name}', (xa, CABINET_FRONT_Y, BOARD_TOP_Z),
            (xa + t, CABINET_BACK_Y, CABINET_Z_TOP - t), oak, bevel=.0012, swap_vertical=True)
    box(bpy, 'Cupboard back', (CABINET_X_MIN, CABINET_BACK_Y - t, BOARD_TOP_Z),
        (CABINET_X_MAX, CABINET_BACK_Y, CABINET_Z_TOP - t), oak, swap_vertical=True)
    box(bpy, 'Cupboard shelf', (CABINET_X_MIN + t, CABINET_FRONT_Y + .004, SHELF_Z - SHELF_T),
        (CABINET_X_MAX - t, CABINET_BACK_Y - t, SHELF_Z), oak, bevel=.0012)
    # Door leaf: built closed, in the hinge's frame, then swung about the hinge.
    angle = math.radians(DOOR_OPEN_DEG)
    leaf_half_x = (CABINET_X_MAX - CABINET_X_MIN) / 2 - .002
    hz = (CABINET_Z_TOP - CABINET_Z_BOTTOM) / 2 - .002
    zc = (CABINET_Z_BOTTOM + CABINET_Z_TOP) / 2
    door = box(bpy, 'Cupboard door', (-2 * leaf_half_x - .002, -DOOR_T, zc - hz), (-.002, 0., zc + hz), oak,
               bevel=.0012, swap_vertical=True)
    door.location = (DOOR_HINGE_X, CABINET_FRONT_Y, 0.)
    door.rotation_euler = (0., 0., angle)
    # The pull is on the door's outer face, near its free edge.
    pull = bar_pull(bpy, f, 'Cupboard door pull', (-2 * leaf_half_x + .04, -DOOR_T, zc - .30), .18, True)
    for p in pull:
        p.parent = door
    # Two concealed cup hinges: the 35 mm cup in the door's inner face, and
    # the arm reaching to its mounting plate on the side panel.
    from mathutils import Matrix, Vector
    hinge_steel = plain(bpy, 'Nickel-plated hinge steel', (.55, .55, .53), .32, metallic=1.)
    to_world = Matrix.Translation((DOOR_HINGE_X, CABINET_FRONT_Y, 0.)) @ Matrix.Rotation(angle, 4, 'Z')
    for k, dz in enumerate((-.32, .32)):
        cup = lathe(bpy, f'Cupboard hinge cup {k + 1}', [(0, 0), (.0175, 0), (.0230, .0015), (.0230, .0025),
                                                        (0, .0025)], hinge_steel, 40)
        cup.rotation_euler = (-math.pi / 2, 0, 0)
        cup.location = (-.0245, 0., zc + dz)
        cup.parent = door
        _prop(cup)
        a = to_world @ Vector((-.0245, .009, zc + dz))
        b = Vector((CABINET_X_MAX - t - .006, CABINET_FRONT_Y + .037, zc + dz))
        _prop(bar_between(bpy, f'Cupboard hinge arm {k + 1}', a, b, .016, .010, hinge_steel))
        _prop(box(bpy, f'Cupboard hinge plate {k + 1}', (CABINET_X_MAX - t - .004, CABINET_FRONT_Y + .022, zc + dz - .025),
                  (CABINET_X_MAX - t, CABINET_FRONT_Y + .058, zc + dz + .025), hinge_steel, bevel=.0015))
    return door


def bar_between(bpy, name, a, b, width, thick, mat):
    """A small rectangular bar from point a to point b (hinge arms)."""
    from mathutils import Matrix
    d = b - a
    obj = box(bpy, name, (-width / 2, -thick / 2, 0.), (width / 2, thick / 2, d.length), mat, bevel=.002)
    obj.matrix_world = Matrix.Translation(a) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    return obj


def build_open_shelves(bpy, f, glazes):
    """Two oiled oak boards on black steel brackets left of the cupboard,
    with the rest of the bowl's set on them."""
    x0, x1, depth, t = .42, 1.38, .28, .038
    for k, ztop in enumerate((1.46, 1.84)):
        _prop(box(bpy, f'Open shelf {k + 1}', (x0, 3.45 - depth, ztop - t), (x1, 3.45, ztop), f['oak_board'],
                  bevel=.003))
        for bxk in (x0 + .11, x1 - .11):
            _prop(box(bpy, f'Shelf bracket {k + 1} arm', (bxk - .003, 3.45 - depth + .03, ztop - t - .006),
                      (bxk + .003, 3.45, ztop - t), f['steel'], bevel=.001))
            _prop(box(bpy, f'Shelf bracket {k + 1} upright', (bxk - .003, 3.444, ztop - t - .16),
                      (bxk + .003, 3.45, ztop - t), f['steel'], bevel=.001))
    for o in stack(bpy, 'Shelf plates', PLATE, .13, .023, glazes['oatmeal'], (1.18, 3.31, 1.46), 6, .0125):
        _prop(o)
    for o in stack(bpy, 'Shelf bowls', SERVING_BOWL, .08, .07, glazes['cobalt'], (.82, 3.31, 1.46), 3, .022):
        _prop(o)
    for o in stack(bpy, 'Shelf small bowls', RICE_BOWL, .07, .072, glazes['charcoal'], (.86, 3.31, 1.84), 3, .024):
        _prop(o)
    _prop(import_model(bpy, 'ceramic_vase_03', (.56, 3.33, 1.84)))


def build_cupboard_contents(bpy, glazes):
    """Plates at the back of the bottom board and bowls on the shelf: the
    bowl that falls was simply the one left askew at the front."""
    for o in stack(bpy, 'Cupboard plates', PLATE, .12, .022, glazes['oatmeal'], (.02, 3.24, BOARD_TOP_Z), 7, .012):
        _prop(o)
    for o in stack(bpy, 'Cupboard rice bowls', RICE_BOWL, .07, .072, glazes['oatmeal'], (-.26, 3.21, SHELF_Z), 3,
                   .026):
        _prop(o)
    for o in stack(bpy, 'Cupboard serving bowls', SERVING_BOWL, .08, .07, glazes['cobalt'], (.02, 3.20, SHELF_Z), 2,
                   .022):
        _prop(o)


# ----------------------------------------------------------------- props

def import_model(bpy, asset_id, location, rotation=(0., 0., 0.), keep=None):
    """Import a Poly Haven glTF (already at real size), merge it into one
    object, turn it by ``rotation`` (degrees, XYZ), then stand the base centre
    of its bounding box on ``location``. Returns the object."""
    from mathutils import Vector, Matrix, Euler
    import bmesh
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(POLYHAVEN / asset_id / f'{asset_id}_1k.gltf'))
    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == 'MESH' and (keep is None or o.name.startswith(keep))]
    if not meshes:
        raise RuntimeError(f'{asset_id}: nothing to import')
    for o in imported:
        o.animation_data_clear()
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new(asset_id)
    bm = bmesh.new()
    materials = []
    for o in meshes:
        tmp = bpy.data.meshes.new_from_object(o.evaluated_get(deps), preserve_all_data_layers=True, depsgraph=deps)
        tmp.transform(o.matrix_world)
        offset = len(materials)
        materials += list(tmp.materials)
        for p in tmp.polygons:
            p.material_index += offset
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    bm.to_mesh(mesh)
    bm.free()
    for m in materials:
        mesh.materials.append(m)
    for o in imported:
        bpy.data.objects.remove(o, do_unlink=True)
    obj = bpy.data.objects.new(asset_id, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for m in materials:
        if m and m.use_nodes:
            for node in m.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED' and node.inputs.get('Emission Strength'):
                    node.inputs['Emission Strength'].default_value = 0.
    mesh.transform(Euler([math.radians(a) for a in rotation], 'XYZ').to_matrix().to_4x4())
    lo = Vector([min(v.co[i] for v in mesh.vertices) for i in range(3)])
    hi = Vector([max(v.co[i] for v in mesh.vertices) for i in range(3)])
    base = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    mesh.transform(Matrix.Translation(Vector(location) - base))
    mesh.update()
    return obj


def build_props(bpy, f, glazes, counter):
    top = counter['top_z']
    # A freestanding steel-and-oak pantry unit beyond the end of the run
    # (its back 14 mm off the brick).
    _prop(import_model(bpy, 'drawer_cabinet', (-2.25, 3.192, -.092)))
    # Utensil crock with two wooden spoons, handles down, between hob and sink.
    crock_profile = fit_profile([(0, .004), (.050, .004), (.052, 0), (.058, .003), (.060, .03), (.060, .145),
                                 (.0585, .15), (.054, .148), (.054, .02), (0, .018)], .060, .150)
    crock = lathe(bpy, 'Utensil crock', crock_profile, glazes['oatmeal'], 72)
    crock.location = (.33, 3.29, top)
    _prop(crock)
    for k, (dx, tilt, yaw) in enumerate(((-.012, 9., 20.), (.013, -7., 200.))):
        spoon = import_model(bpy, 'wooden_spoon', (0, 0, -.139), rotation=(-90., 0., 0.))
        spoon.rotation_euler = (math.radians(tilt), 0, math.radians(yaw))
        spoon.location = (.33 + dx, 3.29, top + .162)
        _prop(spoon)
    # A cutting board leaning on the brick: it rests on its wall-side bottom
    # edge (3.4 mm below the front edge at a 9 deg lean) with its top on the wall.
    lean = math.radians(9.)
    board = box(bpy, 'Cutting board', (-.20, 0., 0.), (.20, .022, .42), f['oak_board'], bevel=.006,
                swap_vertical=True)
    board.rotation_euler = (-lean, 0, 0)
    board.location = (-1.30, 3.45 - .002 - (.022 * math.cos(lean) + .42 * math.sin(lean)),
                      top + .022 * math.sin(lean))
    _prop(board)
    # A cobalt fruit bowl of the same set with avocados in it.
    fruit_bowl = lathe(bpy, 'Fruit bowl', fit_profile(SERVING_BOWL, .085, .065), glazes['cobalt'], 96)
    fruit_bowl.location = (-1.02, 3.18, top)
    _prop(fruit_bowl)
    inner = top + .065 * .0326 / .085
    for k, (dx, dy, yaw, roll) in enumerate(((-.022, -.012, 30., 78.), (.026, .010, -60., 95.), (.0, .030, 110., 84.))):
        _prop(import_model(bpy, 'food_avocado_01', (-1.02 + dx, 3.18 + dy, inner + .006 + .006 * k),
                           rotation=(roll, 0., yaw)))
    # A terracotta pot with a low anthurium on the window sill.
    (sx0, sx1), (sill_z, _) = BACK_WINDOW
    px, py = sx0 + .16, 3.45 + .095
    pot = lathe(bpy, 'Terracotta pot', fit_profile(
        [(0, 0), (.050, 0), (.054, .004), (.068, .11), (.072, .112), (.072, .125), (.064, .125), (.062, .115),
         (.0, .11)], .072, .125), f['terracotta'], 64)
    pot.location = (px, py, sill_z)
    _prop(pot)
    soil = lathe(bpy, 'Potting soil', [(0, 0), (.062, 0), (.062, .004), (0, .006)],
                 plain(bpy, 'Damp potting soil', (.035, .025, .018), .95), 48)
    soil.location = (px, py, sill_z + .108)
    _prop(soil)
    _prop(import_model(bpy, 'anthurium_botany_01', (px, py, sill_z + .110), keep='anthurium_botany_05_e'))



# ---------------------------------------------------------------- daylight

def daylight(bpy, scene, target):
    from mathutils import Vector
    el, hd = math.radians(SUN_ELEVATION_DEG), math.radians(SUN_HEADING_DEG)
    travel = Vector((math.cos(el) * math.cos(hd), math.cos(el) * math.sin(hd), -math.sin(el)))
    data = bpy.data.lights.new('Late afternoon sun', 'SUN')
    data.energy, data.angle, data.color = SUN_STRENGTH, math.radians(.53), SUN_COLOR
    sun = bpy.data.objects.new('Late afternoon sun', data)
    scene.collection.objects.link(sun)
    sun.location = Vector(target) - 8 * travel
    _aim(sun, sun.location + travel)
    world = bpy.data.worlds.new('Late afternoon sky')
    scene.world = world
    world.use_nodes = True
    n, l = world.node_tree.nodes, world.node_tree.links
    sky = n.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    sky.sun_elevation = el
    sky.sun_rotation = math.atan2(-travel.x, -travel.y)
    sky.air_density, sky.dust_density = 1.0, 3.0
    bg = n['Background']
    l.new(sky.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = SKY_STRENGTH
    coord = n.new('ShaderNodeTexCoord')
    turn = n.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    towards_sun = -travel
    turn.inputs['Rotation'].default_value = (0, 0, math.radians(WINDOW_VIEW_SUN_AZIMUTH_DEG)
                                             - math.atan2(towards_sun.y, towards_sun.x))
    photo = n.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(POLYHAVEN / WINDOW_VIEW), check_existing=True)
    l.new(coord.outputs['Generated'], turn.inputs['Vector'])
    l.new(turn.outputs['Vector'], photo.inputs['Vector'])
    view = n.new('ShaderNodeBackground')
    view.inputs['Strength'].default_value = WINDOW_VIEW_STRENGTH
    l.new(photo.outputs['Color'], view.inputs['Color'])
    path = n.new('ShaderNodeLightPath')
    mix = n.new('ShaderNodeMixShader')
    l.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    l.new(bg.outputs['Background'], mix.inputs[1])
    l.new(view.outputs['Background'], mix.inputs[2])
    l.new(mix.outputs['Shader'], n['World Output'].inputs['Surface'])
    return sun


def sky_portal(bpy, scene, name, centre, size, inward):
    """An area-light portal across an opening (it emits nothing itself): Cycles
    then samples the sky through the hole instead of waiting for a bounce."""
    from mathutils import Vector
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = size
    data.cycles.is_portal = True
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = centre
    _aim(obj, Vector(centre) + Vector(inward))
    return obj


# ------------------------------------------------------------------ build

def build_loft_kitchen(bpy, scene):
    """Build the whole room; return the list of objects the moving bowls must
    keep clear of (everything that is not a collider surface)."""
    PROPS.clear()
    boxes = {b['name']: b for b in load_colliders()['boxes']}
    f = finishes(bpy)
    shell = build_shell(bpy, f, boxes)
    counter = build_counter(bpy, f, boxes, shell)
    build_base_units(bpy, f, counter, shell)
    build_island(bpy, f, boxes, shell)
    build_cupboard(bpy, f)
    build_open_shelves(bpy, f, f)
    build_cupboard_contents(bpy, f)
    build_props(bpy, f, f, counter)
    daylight(bpy, scene, (-.15, 2.95, 1.6))
    (sx0, sx1), (sz0, sz1) = BACK_WINDOW
    sky_portal(bpy, scene, 'Back window portal', ((sx0 + sx1) / 2, shell['back_y'] + .002, (sz0 + sz1) / 2),
               (sx1 - sx0, sz1 - sz0), (0, -1, 0))
    (wy0, wy1), (wz0, wz1) = SIDE_WINDOW
    sky_portal(bpy, scene, 'Side window portal', (shell['left_x'] - .002, (wy0 + wy1) / 2, (wz0 + wz1) / 2),
               (wy1 - wy0, wz1 - wz0), (1, 0, 0))
    (fx0, fx1), (fz0, fz1) = FRONT_WINDOW
    sky_portal(bpy, scene, 'Front window portal', ((fx0 + fx1) / 2, shell['front_y'] - .002, (fz0 + fz1) / 2),
               (fx1 - fx0, fz1 - fz0), (0, 1, 0))
    return list(PROPS)


# --------------------------------------------------------------- checks

def body_samples(key):
    """Points on each moving body's collision surface (body frame). The
    visible bowl lies inside this surface, so a gap measured from it is a
    lower bound on the real gap."""
    from mathutils import Vector
    from scene_geometry import (FALLING_BOWL_RADIUS, FALLING_BOWL_HEIGHT, TABLEWARE_BOWL_RADIUS,
                                TABLEWARE_BOWL_HEIGHT)
    pts = []
    if key == 'falling_bowl':
        r, h = FALLING_BOWL_RADIUS, FALLING_BOWL_HEIGHT
        for k in range(24):
            a = 2 * math.pi * k / 24
            for z in (-h / 2, 0., h / 2):
                pts.append(Vector((r * math.cos(a), r * math.sin(a), z)))
        pts += [Vector((0, 0, -h / 2)), Vector((0, 0, h / 2))]
    else:
        r, h = TABLEWARE_BOWL_RADIUS, TABLEWARE_BOWL_HEIGHT
        for i in range(-2, 3):
            for j in range(-2, 3):
                for z in (-h / 2, 0., h / 2):
                    if abs(i) == 2 or abs(j) == 2 or z != 0.:
                        pts.append(Vector((r * i / 2, r * j / 2, z)))
    return pts


def check_props(bpy, scene, props, frames, keys, camera, margin=.02):
    """Fail the render if any prop comes within ``margin`` of a moving bowl in
    any solved frame, or stands between the camera and one."""
    from mathutils import Matrix, Vector
    from mathutils.bvhtree import BVHTree
    deps = bpy.context.evaluated_depsgraph_get()
    trees = {}
    for o in props:
        eo = o.evaluated_get(deps)
        me = eo.to_mesh()
        verts = [o.matrix_world @ v.co for v in me.vertices]
        polys = [tuple(p.vertices) for p in me.polygons]
        if polys:
            trees[o.name] = BVHTree.FromPolygons(verts, polys)
        eo.to_mesh_clear()
    samples = {k: body_samples(k) for k in keys}
    gaps = {}
    for fr in frames:
        for key in keys:
            st = fr[key]
            if not st['present']:
                continue
            m = Matrix(st['matrix_world'])
            pts = [m @ p for p in samples[key]]
            for name, tree in trees.items():
                for p in pts:
                    hit = tree.find_nearest(p, 1.0)
                    if hit[0] is not None and hit[3] < gaps.get(name, (9., 0, ''))[0]:
                        gaps[name] = (hit[3], fr['frame_index'], key)
    close = {k: v for k, v in gaps.items() if v[0] < margin}
    if close:
        raise RuntimeError('props too close to a moving bowl: ' + ', '.join(
            f'{k} {v[0] * 1000:.1f} mm ({v[2]}, frame {v[1]})' for k, v in sorted(close.items())))
    nearest = sorted(gaps.items(), key=lambda kv: kv[1][0])[:4]
    print('[loft] nearest props: ' + ', '.join(f'{k} {v[0] * 1000:.0f} mm' for k, v in nearest), flush=True)
    # Occlusion: rays from the camera to points on each bowl.
    names = {o.name for o in props}
    cam = camera.matrix_world.translation.copy()
    blocked = []
    for fr in frames:
        scene.frame_set(fr['frame_index'])
        deps = bpy.context.evaluated_depsgraph_get()
        for key in keys:
            st = fr[key]
            if not st['present']:
                continue
            m = Matrix(st['matrix_world'])
            for p in [m @ Vector((0, 0, 0))] + [m @ q for q in samples[key][::6]]:
                d = p - cam
                hit, loc, nor, idx, obj, _ = scene.ray_cast(deps, cam, d.normalized(), distance=d.length - .004)
                if hit and obj is not None and obj.name in names:
                    blocked.append((fr['frame_index'], key, obj.name))
    if blocked:
        raise RuntimeError('props hide a moving bowl: ' + ', '.join(f'{k} by {o} (frame {f})' for f, k, o in blocked[:8]))
    return {k: round(v[0], 4) for k, v in gaps.items()}
