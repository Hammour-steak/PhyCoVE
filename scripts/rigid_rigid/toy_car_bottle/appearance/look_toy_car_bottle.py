"""A tatami room in afternoon light, and a thin-walled PET bottle, for toy_car_bottle.

The simulator's floor plane z = 0 is the top of the tatami; everything else
here is scenery. Room lines, the mat plan, materials, openings, daylight and
furniture live in ``ROOM`` / ``LOOK``; ``washitsu.py`` builds them.
"""
from mathutils import Quaternion, Vector

from pcve_assets import asset as _pcve_asset

POLYHAVEN = _pcve_asset('polyhaven/toy_car_bottle')

# The room lines are the plaster faces (posts stand half out of the corners).
# The car runs along y = 0 from x = -0.60 (its tail at the start) and the
# farthest any body travels is the toppled bottle of edit_fast_car_midflight,
# to x = 0.88, so every wall stands about a metre clear (the render refuses
# anything closer than 2 cm to a wall or a prop).
# The camera (scenario layout) sits on the mats at y = -1.14 looking north,
# so the shoji wall fills the top of the frame and the side walls show as
# narrow strips at its two ends.
ROOM = dict(x=(-1.55, 2.05), y=(-1.85, 2.65), ceiling_m=2.40)

LOOK = dict(
    seed=7,
    # Ten mats, each (col0, row0, col1, row1) in 0.9 m units from the south-west
    # corner; no four meet at a point. The car starts on a mat laid north-south
    # and crosses the pair of heri between it and its neighbour at x = 0.25.
    tatami=[(0, 4, 2, 5), (2, 4, 4, 5), (0, 2, 1, 4), (1, 3, 3, 4), (3, 2, 4, 4),
            (1, 1, 2, 3), (2, 1, 3, 3), (0, 0, 1, 2), (3, 0, 4, 2), (1, 0, 3, 1)],
    # Poly Haven clay_plaster, lightened to the warm sand of a juraku wall.
    walls=dict(texture='clay_plaster', tile_m=2.0, tint=(1.0, 0.97, 0.92), value=1.75, saturation=0.6,
               normal_strength=0.35),
    shoji=dict(panels=4, kick_board_m=0.24, vertical_bars=3, bar_pitch_m=0.135),
    # Glazed sliding doors to the garden in the west wall, left of the frame.
    garden_door=dict(span=(-1.20, 1.20)),
    # Afternoon sun through the garden door; the light travels east and a
    # little north across the mats and lights the car's lane.
    daylight=dict(sun_elevation_deg=30.0, sun_heading_deg=15.0, sun_energy=3.0, sky_strength=0.8),
    table_material=dict(texture='lacquered_cherry_wood', tile_m=1.0),
    cushion_texture='denim_fabric_03',
    furniture=[
        dict(kind='low_table', name='Low table', centre=(1.10, 1.55), size=(1.20, 0.75), height_m=0.33),
        dict(kind='zabuton', name='Cushion 1', centre=(1.10, 0.85), size=(0.55, 0.59), yaw_deg=4.0),
        dict(kind='zabuton', name='Cushion 2', centre=(0.18, 1.60), size=(0.55, 0.59), yaw_deg=86.0),
        dict(model='ceramic_vase_04', name='Vase', x=-1.20, y=2.40),
    ],
    exposure=0.0,
)

# Bounding spheres of the moving bodies (box car; convex bottle hull).
def body_radius(layout, name):
    if name == 'car':
        return 0.5 * Vector((layout['car_length'], layout['car_width'], layout['car_height'])).length
    return 0.5 * Vector((2 * layout['bottle_radius'], 2 * layout['bottle_radius'], layout['bottle_height'])).length


def body_half_extents(layout, name):
    if name == 'car':
        return Vector((layout['car_length'], layout['car_width'], layout['car_height'])) / 2
    return Vector((layout['bottle_radius'], layout['bottle_radius'], layout['bottle_height'] / 2))


def build_environment(origin):
    from washitsu import build_room
    return build_room(ROOM, LOOK, POLYHAVEN, Vector(origin))


def check_props(environment, physics, layout, camera, origin):
    """Props are not simulated: no moving body may come within 2 cm of one
    (or of a wall), and none may hide a moving body from the camera, in any
    frame of this take."""
    import bpy
    from washitsu import check_clearance, check_line_of_sight
    samples, bodies = [], []
    origin = Vector(origin)
    for frame in physics['frames']:
        for name, state in frame['objects'].items():
            if not state.get('present', True):
                continue
            centre = Vector(state['position'])
            samples.append((centre, body_radius(layout, name)))
            x, y, z, w = state['quaternion_xyzw']
            bodies.append((f'{name}@{frame["frame"]}', centre + origin, Quaternion((w, x, y, z)),
                           body_half_extents(layout, name)))
    clearance = check_clearance(ROOM, environment['furniture'] + environment['posts'], samples)
    static = [bpy.data.objects[n] for n in environment['objects'] if n in bpy.data.objects]
    static += [child for obj in list(static) for child in obj.children_recursive]
    rays = check_line_of_sight(camera.matrix_world.translation.copy(), static, bodies)
    return clearance, sum(rays.values())


# ------------------------------------------------------------------ bodies


def _pet_label(bpy, bottle, z0, z1):
    """A printed shrink-sleeve label: the bottle's own outer wall between
    z0 and z1 (bottle frame, metres), lifted 0.4 mm off it."""
    import bmesh
    mesh = bottle.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    body_slots = {i for i, slot in enumerate(bottle.material_slots)
                  if slot.material and slot.material.name.startswith('PET')}
    keep = []
    for face in bm.faces:
        c = face.calc_center_median()
        radial = Vector((c.x, c.y, 0.0))
        if face.material_index in body_slots and z0 <= c.z <= z1 and radial.length > 1e-6 \
                and face.normal.dot(radial.normalized()) > 0.3:
            keep.append(face)
    drop = [f for f in bm.faces if f not in set(keep)]
    bmesh.ops.delete(bm, geom=drop, context='FACES')
    if len(bm.faces) < 100:
        raise RuntimeError(f'{bottle.name}: found no bottle wall to carry the label')
    for vert in bm.verts:
        vert.co += vert.normal * 0.0004
    label_mesh = bpy.data.meshes.new(bottle.name + '_label')
    bm.to_mesh(label_mesh)
    bm.free()
    label = bpy.data.objects.new(bottle.name + '_label', label_mesh)
    bpy.context.collection.objects.link(label)
    label.data.materials.clear()
    label.data.materials.append(_label_material(bpy, z0, z1))
    label.parent = bottle
    label.matrix_parent_inverse.identity()
    return label


def _label_material(bpy, z0, z1):
    existing = bpy.data.materials.get('Water label')
    if existing is not None:
        return existing
    mat = bpy.data.materials.new('Water label')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    split = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Object'], split.inputs['Vector'])
    angle = nodes.new('ShaderNodeMath')
    angle.operation = 'ARCTAN2'
    links.new(split.outputs['Y'], angle.inputs[0])
    links.new(split.outputs['X'], angle.inputs[1])
    wave = nodes.new('ShaderNodeMath')
    wave.operation = 'SINE'
    triple = nodes.new('ShaderNodeMath')
    triple.operation = 'MULTIPLY'
    triple.inputs[1].default_value = 2.0
    links.new(angle.outputs['Value'], triple.inputs[0])
    links.new(triple.outputs['Value'], wave.inputs[0])
    height = nodes.new('ShaderNodeMapRange')
    height.inputs['From Min'].default_value = z0
    height.inputs['From Max'].default_value = z1
    links.new(split.outputs['Z'], height.inputs['Value'])
    crest = nodes.new('ShaderNodeMath')
    crest.operation = 'MULTIPLY_ADD'
    crest.inputs[1].default_value = 0.08
    crest.inputs[2].default_value = 0.42
    links.new(wave.outputs['Value'], crest.inputs[0])
    edge = nodes.new('ShaderNodeMath')
    edge.operation = 'SUBTRACT'
    links.new(height.outputs['Result'], edge.inputs[0])
    links.new(crest.outputs['Value'], edge.inputs[1])

    def compare(operation, socket, threshold):
        node = nodes.new('ShaderNodeMath')
        node.operation = operation
        links.new(socket, node.inputs[0])
        node.inputs[1].default_value = threshold
        return node.outputs['Value']

    def mix(a, b, factor):
        node = nodes.new('ShaderNodeMix')
        node.data_type = 'RGBA'
        links.new(factor, node.inputs['Factor'])
        if isinstance(a, tuple):
            node.inputs[6].default_value = a
        else:
            links.new(a, node.inputs[6])
        node.inputs[7].default_value = b
        return node.outputs[2]

    # Print: a sky-blue field fading paler upwards, a deep-blue wave along the
    # bottom with a white rule on its crest, and a deep-blue rim at the top.
    sky = nodes.new('ShaderNodeValToRGB')
    sky.color_ramp.elements[0].color = (0.30, 0.56, 0.82, 1.0)
    sky.color_ramp.elements[1].color = (0.72, 0.85, 0.94, 1.0)
    links.new(height.outputs['Result'], sky.inputs['Fac'])
    deep = (0.010, 0.075, 0.30, 1.0)
    colour = mix(sky.outputs['Color'], (0.86, 0.88, 0.90, 1.0), compare('LESS_THAN', edge.outputs['Value'], 0.045))
    colour = mix(colour, deep, compare('LESS_THAN', edge.outputs['Value'], 0.0))
    colour = mix(colour, deep, compare('GREATER_THAN', height.outputs['Result'], 0.92))
    # The inside of the sleeve, seen through the empty bottle, is unprinted film.
    backface = nodes.new('ShaderNodeNewGeometry')
    colour = mix(colour, (0.70, 0.72, 0.74, 1.0), backface.outputs['Backfacing'])
    links.new(colour, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.28
    return mat


def dress_bottle(bpy, bottle):
    """A thin-walled empty PET bottle with its moulded cap and a label.

    The scan's body is a solid-looking transmissive glass; a real bottle wall
    is a fraction of a millimetre thick, so light goes straight through it
    and the wall only shows by its Fresnel reflections. The cap keeps its
    colour as matt HDPE.
    """
    from washitsu import thin_film_shader
    pet = bpy.data.materials.get('PET bottle wall') or thin_film_shader(
        bpy.data.materials.new('PET bottle wall'), 1.575, (0.975, 0.99, 1.0), 0.035, shadow_transmission=0.75)
    # The importer names the GLB's two materials differently on a second
    # import, so they are told apart by what they are: the body is the
    # transmissive one, the cap the opaque one.
    for slot in bottle.material_slots:
        material = slot.material
        shader = material.node_tree.nodes.get('Principled BSDF') if material and material.use_nodes else None
        if shader is None:
            continue
        if shader.inputs['Transmission Weight'].default_value > 0.5:
            slot.material = pet
        else:
            cap = bpy.data.materials.get('HDPE cap')
            if cap is None:
                cap = material.copy()
                cap.name = 'HDPE cap'
                shader = cap.node_tree.nodes.get('Principled BSDF')
                shader.inputs['Metallic'].default_value = 0.0
                shader.inputs['Roughness'].default_value = 0.42
                if shader.inputs.get('Coat Weight'):
                    shader.inputs['Coat Weight'].default_value = 0.0
            slot.material = cap
    lo = min((v.co.z for v in bottle.data.vertices))
    hi = max((v.co.z for v in bottle.data.vertices))
    height = hi - lo
    return _pet_label(bpy, bottle, lo + 0.27 * height, lo + 0.50 * height)


def configure_render(bpy, scene):
    """AgX, a half-frame shutter and light paths for a thin glassy bottle."""
    scene.view_settings.view_transform = 'AgX'
    for look in ('AgX - Base Contrast', 'Base Contrast'):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    scene.view_settings.exposure = float(LOOK['exposure'])
    # Half-frame shutter, as a phone films at 24 fps. Persistent data must stay
    # off with motion blur: in Blender 4.3 the pair makes a body that has come
    # to rest vanish from every later frame rendered in the same session.
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.render.use_persistent_data = False
    cycles = scene.cycles
    cycles.max_bounces = 10
    cycles.diffuse_bounces = 4
    cycles.glossy_bounces = 4
    cycles.transmission_bounces = 8
    # A ray through a bottle and its label crosses up to eight thin walls.
    cycles.transparent_max_bounces = 24
    cycles.sample_clamp_indirect = 8.0
    cycles.blur_glossy = 1.0
    cycles.caustics_reflective = False
    cycles.caustics_refractive = False
