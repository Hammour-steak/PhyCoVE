"""An upper-floor open-plan office around the desk: a glass facade, overcast daylight.

The desk (feet on z=0, top at DESK_Z) faces a floor-to-ceiling window wall
0.46 m behind its far (+x) edge. The camera, at the desk's front-left corner,
looks across the desk towards that facade; its frame tops out 5.5 deg below
the horizontal, so of the room it only ever sees the window band above the
desk's far edge, and through it the street outside.

Light is overcast daylight only. Non-camera rays see a CIE standard overcast
sky (zenith three times as bright as the horizon, no sun) over a grey ground;
camera rays that leave through the glass see a street photograph instead
(Poly Haven potsdamer_platz, overcast) -- the same arrangement as the other
daylit rooms, where the photograph is what the window shows and the physical
sky is what lights the room. The photograph is turned so a glass office tower
and a brick office block stand behind the desk, and its lookup is tilted by
VIEW_TILT_DEG: the band the camera sees through the glass lies 5.5-14 deg
below the horizontal, and untilted that is the paving, a bench and an
advertising pillar a few metres from the photographer (magnified close-ups,
and lettering, through the glass); tilted, it is the lower office floors of
the buildings across the square. A sky portal over the glazing guides the
sampling; there is no other
lamp in the room except the ceiling's LED panels, which are real fittings
above the frame (visible in the bottle's reflections) and add a little top
light, as office lighting does on a dull day.

Also here: the stack of cloth-bound notebooks that stands where the solver's
telephone box (PHONE_BOX) is -- the pen comes to rest against that box's
-y face in the source clip, so a visible surface has to be exactly there --
and the clearance/occlusion checks the renderer runs on every case.
"""
import math
from pathlib import Path

from scene_geometry import DESK_Z, PHONE_BOX, KEYBOARD_BOX

# Room (metres, same frame as the solver; the desk spans x -0.453..0.402).
GLASS_X = 0.86                    # inner face of the glazing
ROOM_X = (-4.6, GLASS_X)
ROOM_Y = (-3.2, 4.2)
CEILING_Z = 2.85
GLAZING_Z = (0.10, 2.75)          # upstand below, bulkhead above
MULLION_Y = (-0.25, 1.25, 2.75)   # 1.5 m facade grid
MULLION_W, MULLION_D = .05, .12

# Daylight. SKY_ZENITH is the CIE overcast zenith radiance in Blender units;
# the horizon is a third of it, the ground below is an albedo-0.2 diffuser.
SKY_ZENITH = 1.0
SKY_TINT = (.93, .965, 1.0)
GROUND_ALBEDO = .20
# Window view: potsdamer_platz_4k. VIEW_AZIMUTH_DEG turns the photograph so its
# glass tower and brick block (u ~ 0.43-0.52 of the image) fill the band
# behind the desk -- clear of the advertising and station lettering elsewhere
# in it; VIEW_TILT_DEG lifts the lookup about the axis square to the camera's
# view azimuth (see the module docstring). VIEW_GAIN scales the photograph to the
# CIE sky (measured: the photograph's sky above 30 deg elevation averages
# VIEW_SKY_MEAN, against 0.84 x SKY_ZENITH for the CIE sky there).
VIEW_FILE = 'potsdamer_platz_4k.hdr'
VIEW_AZIMUTH_DEG = -5.3
VIEW_TILT_DEG = 17.0
VIEW_AXIS_AZIMUTH_DEG = 15.6       # camera view azimuth, from +x towards +y
VIEW_SKY_MEAN = 1.506
VIEW_GAIN = 0.84 * SKY_ZENITH / VIEW_SKY_MEAN
# Ceiling LED panels (600 x 600 recessed, 4000 K), radiance in Blender units.
LED_PANELS = ((-0.9, -0.9), (-0.9, 1.5), (-3.3, -0.9), (-3.3, 1.5))
LED_RADIANCE = 2.2

# Notebook stack on the telephone collider: (thickness, cloth, tint, x shift).
# Royal-octavo hardcovers (boards 240 x 162 mm), square-backed spines facing -y and
# flush with PHONE_BOX's -y face, which is the face the pen touches.
NOTEBOOKS = (
    (.034, 'book_pattern_col2', (1., 1., 1.), .000),
    (.031, 'poly_wool_herringbone', (.62, .62, .64), .005),
    (.035, 'book_pattern_col1', (1.2, 1.2, 1.2), -.004),
    (.030, 'poly_wool_herringbone', (1.25, 1.22, 1.15), .002),
)
BOARD = .0025                      # board + cloth
SQUARE = .0025                     # how far the boards overhang the page block
NOTEBOOK_SIZE = (.240, .162)       # along x (spine length), along y (spine -> fore-edge)
CLOTH_TILE = {'book_pattern_col1': .30, 'book_pattern_col2': .30, 'poly_wool_herringbone': .27}


# ------------------------------------------------------------------ helpers


def _aim(obj, point):
    from mathutils import Vector
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def _paint(bpy, name, colour, roughness, metallic=0.):
    m = bpy.data.materials.new(name); m.use_nodes = True
    bs = _bsdf(m)
    bs.inputs['Base Color'].default_value = (*colour, 1)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['Metallic'].default_value = metallic
    return m


WORLD_UV = 'WorldBox'


def world_uv(obj, mapping=None):
    """Bake a box projection in world metres into a UV map named WORLD_UV.

    Each face takes the two world axes across its dominant normal axis
    (``mapping(co, axis) -> (u, v)`` can rotate or offset them). Textures read
    through this map and normal maps that take their tangents from it then
    agree with each other, which object-coordinate box projection cannot
    give a tangent-space normal map.
    """
    me = obj.data; mw = obj.matrix_world; rot = mw.to_3x3()
    layer = me.uv_layers.get(WORLD_UV) or me.uv_layers.new(name=WORLD_UV)
    for poly in me.polygons:
        n = rot @ poly.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = mw @ me.vertices[me.loops[li].vertex_index].co
            if mapping is not None:
                u, v = mapping(co, axis)
            else:
                u, v = (co.x, co.y) if axis == 2 else (co.x, co.z) if axis == 1 else (co.y, co.z)
            layer.data[li].uv = (u, v)
    return layer


def _box(bpy, name, lo, hi, material, bevel=0.):
    """An axis-aligned box with real-size geometry (identity transform)."""
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
    world_uv(obj)
    if material is not None:
        me.materials.append(material)
    if bevel:
        mod = obj.modifiers.new('Edge', 'BEVEL'); mod.width = bevel; mod.segments = 3
        mod.limit_method = 'NONE'
        for poly in me.polygons: poly.use_smooth = True
        obj.modifiers.new('Normals', 'WEIGHTED_NORMAL').keep_sharp = True
    return obj


def _piece(name, objects, lo, hi):
    return dict(name=name, objects=[o.name for o in objects], bbox_min=list(lo), bbox_max=list(hi))


# ---------------------------------------------------------------- materials


def thin_glass(bpy):
    """Thin float glass: a 4 % Fresnel reflection over a see-through layer.

    Cycles' Fresnel node inverts the IOR on back faces, so a ray leaving the
    pane at a grazing angle would be totally reflected and the pane would go
    black; feeding 1/1.52 on back faces cancels that inversion. Transparent
    rays stay camera rays, which is what lets the window show the street
    photograph to the camera while the room is lit by the sky.
    """
    mat = bpy.data.materials.new('Clear float glass'); mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    clear = nodes.new('ShaderNodeBsdfTransparent')
    reflection = nodes.new('ShaderNodeBsdfGlossy'); reflection.inputs['Roughness'].default_value = 0.
    fresnel = nodes.new('ShaderNodeFresnel')
    geometry = nodes.new('ShaderNodeNewGeometry')
    ior = nodes.new('ShaderNodeMath'); ior.operation = 'MULTIPLY_ADD'
    ior.inputs[1].default_value = 1. / 1.52 - 1.52; ior.inputs[2].default_value = 1.52
    links.new(geometry.outputs['Backfacing'], ior.inputs[0]); links.new(ior.outputs['Value'], fresnel.inputs['IOR'])
    pane = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], pane.inputs['Fac'])
    links.new(clear.outputs['BSDF'], pane.inputs[1]); links.new(reflection.outputs['BSDF'], pane.inputs[2])
    links.new(pane.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


def cloth_cover(bpy, textures, stem, tint):
    """Book cloth from a Poly Haven scan at its real size, box-projected."""
    m = bpy.data.materials.new(f'Book cloth {stem}'); m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bs = _bsdf(m)
    # Read through the baked world UV (see world_uv) so the normal map's
    # tangents follow the weave on every face of the box.
    uv = nodes.new('ShaderNodeUVMap'); uv.uv_map = WORLD_UV
    mapping = nodes.new('ShaderNodeMapping')
    s = 1. / CLOTH_TILE[stem]
    mapping.inputs['Scale'].default_value = (s, s, s)
    links.new(uv.outputs['UV'], mapping.inputs['Vector'])
    base = stem.replace('_col1', '').replace('_col2', '')
    colour_file = f'{stem}_2k.jpg' if stem.startswith('book_pattern') else f'{stem}_diff_2k.jpg'

    def tex(file, colour):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(textures / file), check_existing=True)
        node.image.colorspace_settings.name = 'sRGB' if colour else 'Non-Color'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node
    col = tex(colour_file, True)
    mult = nodes.new('ShaderNodeMix'); mult.data_type = 'RGBA'; mult.blend_type = 'MULTIPLY'
    sock = {s.identifier: s for s in mult.inputs}
    sock['Factor_Float'].default_value = 1.
    sock['B_Color'].default_value = (*tint, 1)
    links.new(col.outputs['Color'], sock['A_Color'])
    links.new(next(s for s in mult.outputs if s.identifier == 'Result_Color'), bs.inputs['Base Color'])
    rough = tex(f'{base}_rough_2k.jpg', False)
    remap = nodes.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = .62, .92
    links.new(rough.outputs['Color'], remap.inputs['Value']); links.new(remap.outputs['Result'], bs.inputs['Roughness'])
    nor = tex(f'{base}_nor_gl_2k.jpg', False)
    nmap = nodes.new('ShaderNodeNormalMap'); nmap.inputs['Strength'].default_value = .6
    nmap.uv_map = WORLD_UV
    links.new(nor.outputs['Color'], nmap.inputs['Color']); links.new(nmap.outputs['Normal'], bs.inputs['Normal'])
    bs.inputs['Sheen Weight'].default_value = .25
    return m


def page_edges(bpy):
    """The paper block seen at a book's edges: off-white, faint sheet lines."""
    m = bpy.data.materials.new('Notebook page edges'); m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bs = _bsdf(m)
    coord = nodes.new('ShaderNodeTexCoord')
    squash = nodes.new('ShaderNodeMapping')
    # Lines run horizontally (sheets are stacked in z): stretch x and y.
    squash.inputs['Scale'].default_value = (40., 40., 2500.)
    links.new(coord.outputs['Object'], squash.inputs['Vector'])
    noise = nodes.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 1.
    noise.inputs['Detail'].default_value = 3.
    links.new(squash.outputs['Vector'], noise.inputs['Vector'])
    ramp = nodes.new('ShaderNodeMapRange')
    ramp.inputs['To Min'].default_value, ramp.inputs['To Max'].default_value = .66, .80
    links.new(noise.outputs['Fac'], ramp.inputs['Value'])
    tint = nodes.new('ShaderNodeCombineColor')
    links.new(ramp.outputs['Result'], tint.inputs['Red'])
    warm = nodes.new('ShaderNodeMath'); warm.operation = 'MULTIPLY'; warm.inputs[1].default_value = .975
    links.new(ramp.outputs['Result'], warm.inputs[0]); links.new(warm.outputs[0], tint.inputs['Green'])
    warmer = nodes.new('ShaderNodeMath'); warmer.operation = 'MULTIPLY'; warmer.inputs[1].default_value = .92
    links.new(ramp.outputs['Result'], warmer.inputs[0]); links.new(warmer.outputs[0], tint.inputs['Blue'])
    links.new(tint.outputs['Color'], bs.inputs['Base Color'])
    bs.inputs['Roughness'].default_value = .82
    bump = nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = .25
    bump.inputs['Distance'].default_value = .0002
    links.new(noise.outputs['Fac'], bump.inputs['Height']); links.new(bump.outputs['Normal'], bs.inputs['Normal'])
    return m


# -------------------------------------------------------------------- props


def notebook_stack(bpy, textures):
    """Cloth-bound hardcover books squared up against PHONE_BOX's -y face.

    The solver's telephone stand-in is a 364 x 359 x 144 mm box; the pen
    touches its -y face (y = PHONE_BOX y-min) at x -0.225..-0.044, from the
    desk up to z 0.984, and comes to rest against it in the source clip. The
    GLB telephone itself is 7-13 cm behind that face at those points, so the
    replay showed the pen stopping on thin air. Each notebook here has a flat
    square-backed spine lying exactly in that plane, and the stack is
    130 mm tall (under the box's 144 mm), so the visible spines are the
    contact surface and the whole stack stays inside the box.
    """
    lo_box = [c - h for c, h in zip(PHONE_BOX['centre'], PHONE_BOX['half'])]
    hi_box = [c + h for c, h in zip(PHONE_BOX['centre'], PHONE_BOX['half'])]
    face_y = lo_box[1]
    x0 = -.2415
    pages = page_edges(bpy)
    objects = []
    z = DESK_Z
    for i, (t, stem, tint, dx) in enumerate(NOTEBOOKS):
        cloth = cloth_cover(bpy, textures, stem, tint)
        xa, xb = x0 + dx, x0 + dx + NOTEBOOK_SIZE[0]
        ya, yb = face_y, face_y + NOTEBOOK_SIZE[1]
        # Back board, front board, and the spine board that joins them.
        parts = [
            _box(bpy, f'Notebook {i} back board', (xa, ya, z), (xb, yb, z + BOARD), cloth, bevel=.0008),
            _box(bpy, f'Notebook {i} front board', (xa, ya, z + t - BOARD), (xb, yb, z + t), cloth, bevel=.0008),
            _box(bpy, f'Notebook {i} spine', (xa, ya, z + BOARD * .5), (xb, ya + BOARD, z + t - BOARD * .5), cloth,
                 bevel=.0006),
            _box(bpy, f'Notebook {i} pages', (xa + SQUARE, ya + BOARD, z + BOARD), (xb - SQUARE, yb - SQUARE, z + t - BOARD),
                 pages, bevel=.0004),
        ]
        objects += parts
        z += t
    if z > hi_box[2] or x0 + min(n[3] for n in NOTEBOOKS) < lo_box[0] or \
            x0 + max(n[3] for n in NOTEBOOKS) + NOTEBOOK_SIZE[0] > hi_box[0] or face_y + NOTEBOOK_SIZE[1] > hi_box[1]:
        raise ValueError('notebook stack does not fit inside PHONE_BOX')
    return objects, (x0 + min(n[3] for n in NOTEBOOKS), face_y, DESK_Z), \
        (x0 + max(n[3] for n in NOTEBOOKS) + NOTEBOOK_SIZE[0], face_y + NOTEBOOK_SIZE[1], z)


# --------------------------------------------------------------------- room


def build_shell(bpy):
    """Floor, ceiling, solid walls and the glazed facade with its mullions."""
    x0, x1 = ROOM_X; y0, y1 = ROOM_Y; t = .15
    white = _paint(bpy, 'Matt white wall paint', (.78, .78, .76), .9)
    ceiling_m = _paint(bpy, 'White acoustic ceiling', (.80, .80, .79), .95)
    carpet = _paint(bpy, 'Charcoal carpet tiles', (.055, .057, .060), .95)
    alu = _paint(bpy, 'Grey anodised aluminium', (.16, .165, .17), .38, metallic=1.)
    upstand = _paint(bpy, 'Grey powder-coated convector cover', (.20, .20, .205), .5)
    glass = thin_glass(bpy)
    parts = {}
    parts['floor'] = _box(bpy, 'Office floor', (x0, y0, -.05), (x1 + .25, y1, 0.), carpet)
    parts['ceiling'] = _box(bpy, 'Office ceiling', (x0, y0, CEILING_Z), (x1 + .25, y1, CEILING_Z + .05), ceiling_m)
    parts['back_wall'] = _box(bpy, 'Back wall', (x0 - t, y0, 0.), (x0, y1, CEILING_Z), white)
    parts['side_wall_south'] = _box(bpy, 'Side wall south', (x0, y0 - t, 0.), (x1 + .25, y0, CEILING_Z), white)
    parts['side_wall_north'] = _box(bpy, 'Side wall north', (x0, y1, 0.), (x1 + .25, y1 + t, CEILING_Z), white)
    # Facade: upstand and bulkhead, frame sills, mullions, one glass sheet.
    gx = GLASS_X
    parts['upstand'] = _box(bpy, 'Window upstand', (gx - .02, y0, 0.), (gx + .10, y1, GLAZING_Z[0]), upstand)
    parts['bulkhead'] = _box(bpy, 'Window bulkhead', (gx - .02, y0, GLAZING_Z[1]), (gx + .10, y1, CEILING_Z), white)
    parts['sill_frame'] = _box(bpy, 'Window bottom frame', (gx - .02, y0, GLAZING_Z[0]), (gx + .10, y1, GLAZING_Z[0] + .04),
                               alu, bevel=.002)
    parts['head_frame'] = _box(bpy, 'Window head frame', (gx - .02, y0, GLAZING_Z[1] - .04), (gx + .10, y1, GLAZING_Z[1]),
                               alu, bevel=.002)
    for j, my in enumerate(MULLION_Y):
        parts[f'mullion_{j}'] = _box(bpy, f'Window mullion {j}', (gx - MULLION_D + .06, my - MULLION_W / 2, GLAZING_Z[0]),
                                     (gx + .06, my + MULLION_W / 2, GLAZING_Z[1]), alu, bevel=.002)
    pane = _box(bpy, 'Window glass', (gx + .02, y0, GLAZING_Z[0] + .04), (gx + .026, y1, GLAZING_Z[1] - .04), glass)
    pane.visible_shadow = False
    parts['glass'] = pane
    return parts


def led_panels(bpy):
    """Recessed 600 x 600 LED panels: frosted diffuser + aluminium trim."""
    diffuser = bpy.data.materials.new('LED panel diffuser'); diffuser.use_nodes = True
    nodes, links = diffuser.node_tree.nodes, diffuser.node_tree.links
    bs = _bsdf(diffuser)
    bs.inputs['Base Color'].default_value = (.85, .85, .85, 1); bs.inputs['Roughness'].default_value = .6
    bs.inputs['Emission Color'].default_value = (1., .93, .84, 1)
    bs.inputs['Emission Strength'].default_value = LED_RADIANCE
    trim = _paint(bpy, 'LED panel trim', (.75, .75, .74), .4, metallic=1.)
    objs = []
    for (x, y) in LED_PANELS:
        objs.append(_box(bpy, 'LED panel trim', (x - .31, y - .31, CEILING_Z - .012), (x + .31, y + .31, CEILING_Z), trim))
        objs.append(_box(bpy, 'LED panel', (x - .295, y - .295, CEILING_Z - .016), (x + .295, y + .295, CEILING_Z - .010),
                         diffuser))
    return objs


def daylight(bpy, scene, textures):
    """CIE overcast sky for light, street photograph for the camera, a sky portal."""
    world = bpy.data.worlds.new('Overcast city daylight'); world.use_nodes = True
    scene.world = world
    nodes, links = world.node_tree.nodes, world.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    # --- lighting: L(theta) = Lz (1 + 2 sin theta) / 3 above the horizon,
    # an albedo-0.2 ground below it (radiance rho * 7/9 * Lz).
    sep = nodes.new('ShaderNodeSeparateXYZ'); links.new(coord.outputs['Generated'], sep.inputs['Vector'])
    up = nodes.new('ShaderNodeMath'); up.operation = 'MAXIMUM'; up.inputs[1].default_value = 0.
    links.new(sep.outputs['Z'], up.inputs[0])
    sky = nodes.new('ShaderNodeMath'); sky.operation = 'MULTIPLY_ADD'
    sky.inputs[1].default_value = 2. * SKY_ZENITH / 3.; sky.inputs[2].default_value = SKY_ZENITH / 3.
    links.new(up.outputs[0], sky.inputs[0])
    # Ground to sky over -8..+4 deg: a hazy city horizon is soft, and a sharp
    # step showed up as a bright line in the desk's sheen.
    horizon = nodes.new('ShaderNodeMapRange')
    horizon.inputs['From Min'].default_value, horizon.inputs['From Max'].default_value = -.139, .070
    horizon.interpolation_type = 'SMOOTHSTEP'
    links.new(sep.outputs['Z'], horizon.inputs['Value'])
    ground_level = GROUND_ALBEDO * 7. / 9. * SKY_ZENITH
    blend = nodes.new('ShaderNodeMix'); blend.data_type = 'FLOAT'
    blend.inputs['A'].default_value = ground_level
    links.new(horizon.outputs['Result'], blend.inputs['Factor']); links.new(sky.outputs[0], blend.inputs['B'])
    light = nodes['Background']
    light.inputs['Color'].default_value = (*SKY_TINT, 1)
    links.new(blend.outputs['Result'], light.inputs['Strength'])
    # --- camera: the street photograph, tilted then turned.
    # Tilt about the horizontal axis square to the camera's view azimuth:
    # rotate the lookup into the view frame (view along +x), tilt about y,
    # rotate back, then turn into the photograph's own frame.
    view_az = math.radians(VIEW_AXIS_AZIMUTH_DEG)
    to_view = nodes.new('ShaderNodeVectorRotate'); to_view.rotation_type = 'Z_AXIS'
    to_view.inputs['Angle'].default_value = -view_az
    tilt = nodes.new('ShaderNodeVectorRotate'); tilt.rotation_type = 'Y_AXIS'
    tilt.inputs['Angle'].default_value = -math.radians(VIEW_TILT_DEG)
    back = nodes.new('ShaderNodeVectorRotate'); back.rotation_type = 'Z_AXIS'
    back.inputs['Angle'].default_value = view_az
    turn = nodes.new('ShaderNodeVectorRotate'); turn.rotation_type = 'Z_AXIS'
    turn.inputs['Angle'].default_value = math.radians(VIEW_AZIMUTH_DEG)
    links.new(coord.outputs['Generated'], to_view.inputs['Vector'])
    links.new(to_view.outputs['Vector'], tilt.inputs['Vector'])
    links.new(tilt.outputs['Vector'], back.inputs['Vector'])
    links.new(back.outputs['Vector'], turn.inputs['Vector'])
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(textures / VIEW_FILE), check_existing=True)
    links.new(turn.outputs['Vector'], photo.inputs['Vector'])
    view = nodes.new('ShaderNodeBackground'); view.inputs['Strength'].default_value = VIEW_GAIN
    links.new(photo.outputs['Color'], view.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(light.outputs['Background'], mix.inputs[1]); links.new(view.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['World Output'].inputs['Surface'])
    # Portal over the glazing, facing into the room.
    data = bpy.data.lights.new('Facade sky portal', 'AREA')
    data.shape = 'RECTANGLE'; data.size = ROOM_Y[1] - ROOM_Y[0]; data.size_y = GLAZING_Z[1] - GLAZING_Z[0]
    data.cycles.is_portal = True
    portal = bpy.data.objects.new('Facade sky portal', data); scene.collection.objects.link(portal)
    portal.location = (GLASS_X + .03, (ROOM_Y[0] + ROOM_Y[1]) / 2, (GLAZING_Z[0] + GLAZING_Z[1]) / 2)
    _aim(portal, (portal.location.x - 1., portal.location.y, portal.location.z))
    return world


def build_office(bpy, scene, textures):
    """Room, light and desk props. Returns piece lists for the checks."""
    textures = Path(textures)
    shell = build_shell(bpy)
    panels = led_panels(bpy)
    daylight(bpy, scene, textures)
    books, b_lo, b_hi = notebook_stack(bpy, textures)
    x0, x1 = ROOM_X; y0, y1 = ROOM_Y
    decor = [
        _piece('Facade (glass, frames, mullions, upstand)', [o for k, o in shell.items()
                                                             if k not in ('floor', 'ceiling') and 'wall' not in k],
               (GLASS_X - MULLION_D + .06, y0, 0.), (GLASS_X + .10, y1, CEILING_Z)),
        _piece('Floor', [shell['floor']], (x0, y0, -.05), (x1, y1, 0.)),
        _piece('Ceiling and LED panels', [shell['ceiling'], *panels], (x0, y0, CEILING_Z - .016), (x1, y1, CEILING_Z)),
        _piece('Back wall', [shell['back_wall']], (x0 - .15, y0, 0.), (x0, y1, CEILING_Z)),
        _piece('Side wall south', [shell['side_wall_south']], (x0, y0 - .15, 0.), (x1, y0, CEILING_Z)),
        _piece('Side wall north', [shell['side_wall_north']], (x0, y1, 0.), (x1, y1 + .15, CEILING_Z)),
    ]
    supported = [dict(name='Notebook stack', objects=[o.name for o in books], box='PHONE_BOX',
                      bbox_min=list(b_lo), bbox_max=list(b_hi))]
    print(f'[office] notebook stack {[round(v, 4) for v in b_lo]} .. {[round(v, 4) for v in b_hi]}')
    return dict(decor=decor, supported=supported)


# ------------------------------------------------------------------- checks


def _box_distance(points, lo, hi):
    import numpy as np
    d = np.maximum(np.maximum(np.asarray(lo) - points, 0.), points - np.asarray(hi))
    return np.sqrt((d * d).sum(axis=1))


def _body_points(key):
    """Surface sample points of a moving body in its COM frame, plus a radius."""
    import numpy as np
    from scene_geometry import (kettle_hull_vertices, HOLDER_RADIUS, HOLDER_HEIGHT, HOLDER_COM_Z,
                                PEN_RADIUS, PEN_HALF_LENGTH)
    if key == 'kettle':
        return np.asarray(kettle_hull_vertices(32), dtype=float), 0.
    if key == 'pen_holder':
        a = np.linspace(0, 2 * math.pi, 24, endpoint=False)
        ring = np.stack([HOLDER_RADIUS * np.cos(a), HOLDER_RADIUS * np.sin(a)], axis=1)
        pts = [np.column_stack([ring, np.full(len(a), z)]) for z in
               np.linspace(-HOLDER_COM_Z, HOLDER_HEIGHT - HOLDER_COM_Z, 6)]
        return np.concatenate(pts), 0.
    z = np.linspace(-PEN_HALF_LENGTH, PEN_HALF_LENGTH, 13)
    return np.column_stack([np.zeros_like(z), np.zeros_like(z), z]), PEN_RADIUS


def _poses(frames, keys, substeps=4):
    from mathutils import Vector, Quaternion
    poses = {k: [] for k in keys}
    for a, b in zip(frames, frames[1:] + frames[-1:]):
        for k in keys:
            if not a[k]['present']:
                continue
            nb = b if b[k]['present'] else a
            pa, pb = Vector(a[k]['location']), Vector(nb[k]['location'])
            qa = Quaternion((a[k]['quaternion_xyzw'][3], *a[k]['quaternion_xyzw'][:3]))
            qb = Quaternion((nb[k]['quaternion_xyzw'][3], *nb[k]['quaternion_xyzw'][:3]))
            for s in range(substeps if nb is not a else 1):
                f = s / substeps
                poses[k].append((pa.lerp(pb, f), qa.slerp(qb, f)))
    return poses


def check_clearance(room, frames, keys, margin=.02):
    """Moving bodies vs everything that has no collider: >= 2 cm at all times.

    Bodies are their collision shapes (kettle hull vertices, cup rings, pen
    axis + radius) at every frame and at three sub-frame points between frames,
    which covers what motion blur draws. Pieces that DO have a collider (the
    notebook stack in PHONE_BOX, the keyboard in KEYBOARD_BOX) are instead
    required to lie inside it, so a moving body can never reach them.
    """
    import numpy as np
    poses = _poses(frames, keys)
    gaps = {}
    for piece in room['decor'] + room.get('computer', []):
        gap = float('inf')
        for k, ps in poses.items():
            pts, radius = _body_points(k)
            for p, q in ps:
                world = pts @ np.array(q.to_matrix()).T + np.array(list(p))
                gap = min(gap, float(_box_distance(world, piece['bbox_min'], piece['bbox_max']).min()) - radius)
        gaps[piece['name']] = round(gap, 4)
    print('[office] clearance to decor: ' + ', '.join(f'{k} {v:.3f} m' for k, v in sorted(gaps.items(), key=lambda kv: kv[1])))
    close = [n for n, g in gaps.items() if g < margin]
    if close:
        raise ValueError(f'a moving body passes within {margin} m of {close}')
    for piece in room['supported'] + [dict(p, box='KEYBOARD_BOX') for p in room.get('keyboard', [])]:
        box = PHONE_BOX if piece['box'] == 'PHONE_BOX' else KEYBOARD_BOX
        lo = [c - h - 5e-4 for c, h in zip(box['centre'], box['half'])]
        hi = [c + h + 5e-4 for c, h in zip(box['centre'], box['half'])]
        if any(piece['bbox_min'][i] < lo[i] or piece['bbox_max'][i] > hi[i] for i in range(3)):
            raise ValueError(f'{piece["name"]} sticks out of its collider {piece["box"]}')
    return gaps


def check_occlusion(bpy, scene, camera, room, frames, objects):
    """Rays from the camera to every moving body's centre, every frame: no
    piece of decor or desk prop may stand in front of one."""
    from mathutils import Vector
    blockers = {n for piece in room['decor'] + room['supported'] + room.get('computer', []) + room.get('keyboard', [])
                for n in piece['objects']}
    origin = camera.matrix_world.translation.copy()
    hits = 0
    for f in frames:
        scene.frame_set(f['frame_index'])
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for key, obj in objects.items():
            if not f[key]['present']:
                continue
            target = Vector(f[key]['location'])
            d = target - origin
            ok, loc, _n, _i, hit, _m = scene.ray_cast(depsgraph, origin, d.normalized(), distance=d.length)
            if ok and hit is not None and hit.name in blockers:
                hits += 1
                print(f'[office] frame {f["frame_index"]}: {key} hidden by {hit.name}')
    if hits:
        raise ValueError(f'{hits} body/frame sight lines blocked by props')
    print('[office] occlusion: every body centre visible in every frame')
