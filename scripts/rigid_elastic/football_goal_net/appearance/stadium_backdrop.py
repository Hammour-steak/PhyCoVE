"""Common stadium backdrop aligned with the photographed stadium layout (render only).

The existing 3D goal is placed where the photographed stadium actually has its goal (in front
of a side stand it looked out of place):

- Poly Haven CC0 "Orlando Stadium" was shot from the centre spot. Measured on the
  12288x6144 panorama: the two goals are exactly opposite (u = 0.2476 / 0.7478), each spans
  8.15 deg (7.32 m -> 51.3 m away), goal R posts base at -2.16 deg -> local camera height
  1.94 m. End-stand wall base -1.93 deg (57.6 m), wall top -0.85 deg (1.1 m high).
  Side-stand wall bases: main stand (tunnel, u = 0.5) 41 m, opposite stand (u = 0) 38.5 m.
- World: the goal-free derivative (patch_hdri_remote.py) rotated 180.74 deg so that the
  photographed goal-R direction points from the centre spot C = (0, -51.3, 1.94) m along +y
  to the 3D goal (goal line y = 0). The solar key is rotated by the same delta.
- Stadium proxy: a closed ring (wall 0-1.1 m, 33 deg seating rake to 28 m, vertical to 90 m)
  at the measured wall positions. Its camera-only emission samples the same photograph in
  the direction from C, i.e. the photo is re-projected onto approximately correct stand
  geometry, so a fixed camera away from C still sees the end stand behind the goal with
  consistent perspective. Proxy is invisible to lighting/shadow rays.
- Hidden as before: Sketchfab stadium shell, chairs, rails, synthetic boards, crowd.
No physical object, cache, binding or transform of an existing actor is modified.
"""
import hashlib
import math
from pathlib import Path

STADIUM_ROOTS = ('Sketchfab_model', 'SketchUp', 'Collada visual scene group')
HIDE_PREFIXES = (
    'instanced curved polypropylene chairs',
    'anchored native rail feet and fasteners',
    'generic non-emissive board vector typography',
    'board edge print rule',
    'maintained printed pitchside panel',
)
HDRI_SHA256 = '87b6bbf20b7764d4aa17d25abd4c10c67d79bab6d934df823a58f0ae057dc2c1'
LAYOUT = {
    'capture_point_m': [0.0, -51.3, 1.94],
    'world_rotation_z_deg': 180.74,
    'previous_world_rotation_z_deg': 110.0,
    'end_wall_y_m': 6.3,
    'far_end_wall_y_m': -108.9,
    'main_stand_wall_x_m': -41.0,
    'opposite_stand_wall_x_m': 38.5,
    'wall_height_m': 1.1,
    'rake_deg': 33.0,
    'rake_top_z_m': 28.0,
    'proxy_top_z_m': 90.0,
    'sky_clamp': 16.0,
    'background_strength': 2.0,
}


def _sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _chain(obj):
    names = []
    while obj:
        names.append(obj.name)
        obj = obj.parent
    return names


def _hide_background(scene):
    hidden = []
    for obj in scene.objects:
        chain = _chain(obj)
        lowered = obj.name.lower()
        if (any(root in chain for root in STADIUM_ROOTS) or obj.name.startswith(HIDE_PREFIXES)
                or obj.get('pcve_role') == 'native_crowd' or 'spectator' in lowered or 'crowd' in lowered):
            if not obj.hide_render:
                hidden.append(obj.name)
            obj.hide_render = True
            obj.hide_viewport = True
    return hidden


def _ring(x0, x1, y0, y1, z):
    return [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]


def _proxy_mesh(bpy, scene):
    L = LAYOUT
    x0, x1 = L['main_stand_wall_x_m'], L['opposite_stand_wall_x_m']
    y0, y1 = L['far_end_wall_y_m'], L['end_wall_y_m']
    out = (L['rake_top_z_m'] - L['wall_height_m']) / math.tan(math.radians(L['rake_deg']))
    rings = [_ring(x0, x1, y0, y1, 0.), _ring(x0, x1, y0, y1, L['wall_height_m']),
             _ring(x0 - out, x1 + out, y0 - out, y1 + out, L['rake_top_z_m']),
             _ring(x0 - out, x1 + out, y0 - out, y1 + out, L['proxy_top_z_m'])]
    verts = [v for ring in rings for v in ring]
    faces = []
    for r in range(3):
        for k in range(4):
            a, b = r * 4 + k, r * 4 + (k + 1) % 4
            faces.append((a, b, b + 4, a + 4))
    mesh = bpy.data.meshes.new('photographed stadium re-projection proxy')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    scene.collection.objects.link(obj)
    obj['pcve_role'] = 'render_only_camera_visible_background'
    for attr in ('visible_diffuse', 'visible_glossy', 'visible_transmission', 'visible_volume_scatter', 'visible_shadow'):
        if hasattr(obj, attr):
            setattr(obj, attr, False)
    return obj, out


def _projection_material(bpy, image):
    L = LAYOUT
    mat = bpy.data.materials.new('camera-only stadium photograph re-projection')
    mat.use_nodes = True
    if hasattr(mat, 'cycles') and hasattr(mat.cycles, 'emission_sampling'):
        mat.cycles.emission_sampling = 'NONE'  # background only, never a light source
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new('ShaderNodeOutputMaterial')
    emit = tree.nodes.new('ShaderNodeEmission')
    emit.inputs['Strength'].default_value = L['background_strength']
    geo = tree.nodes.new('ShaderNodeNewGeometry')
    sub = tree.nodes.new('ShaderNodeVectorMath'); sub.operation = 'SUBTRACT'
    sub.inputs[1].default_value = L['capture_point_m']
    norm = tree.nodes.new('ShaderNodeVectorMath'); norm.operation = 'NORMALIZE'
    mapping = tree.nodes.new('ShaderNodeMapping')
    mapping.inputs['Rotation'].default_value[2] = math.radians(L['world_rotation_z_deg'])
    env = tree.nodes.new('ShaderNodeTexEnvironment'); env.image = image
    cap = tree.nodes.new('ShaderNodeVectorMath'); cap.operation = 'MINIMUM'
    cap.inputs[1].default_value = (L['sky_clamp'],) * 3
    pos = tree.nodes.new('ShaderNodeVectorMath'); pos.operation = 'MAXIMUM'
    pos.inputs[1].default_value = (0., 0., 0.)
    tree.links.new(geo.outputs['Position'], sub.inputs[0])
    tree.links.new(sub.outputs[0], norm.inputs[0])
    tree.links.new(norm.outputs[0], mapping.inputs['Vector'])
    tree.links.new(mapping.outputs[0], env.inputs['Vector'])
    tree.links.new(env.outputs['Color'], cap.inputs[0])
    tree.links.new(cap.outputs[0], pos.inputs[0])
    tree.links.new(pos.outputs[0], emit.inputs['Color'])
    tree.links.new(emit.outputs[0], out.inputs['Surface'])
    return mat


def _rotate_world_and_sun(bpy, scene, image):
    from mathutils import Matrix, Vector
    L = LAYOUT
    tree = scene.world.node_tree
    env = [n for n in tree.nodes if n.bl_idname == 'ShaderNodeTexEnvironment']
    mapping = [n for n in tree.nodes if n.bl_idname == 'ShaderNodeMapping']
    assert len(env) == 1 and len(mapping) == 1
    old = math.degrees(mapping[0].inputs['Rotation'].default_value[2])
    assert abs(old - L['previous_world_rotation_z_deg']) < 1e-3, old
    env[0].image = image
    mapping[0].inputs['Rotation'].default_value[2] = math.radians(L['world_rotation_z_deg'])
    delta = math.radians(L['world_rotation_z_deg'] - old)
    suns = [o for o in scene.objects if o.type == 'LIGHT' and o.data.type == 'SUN']
    assert len(suns) == 1
    sun = suns[0]
    before = tuple(sun.matrix_world.to_3x3() @ Vector((0, 0, -1)))
    sun.matrix_world = Matrix.Rotation(-delta, 4, 'Z') @ sun.matrix_world
    after = tuple(sun.matrix_world.to_3x3() @ Vector((0, 0, -1)))
    return {'world_rotation_z_deg': [old, L['world_rotation_z_deg']], 'sun': sun.name,
            'sun_travel_direction_before': [round(v, 5) for v in before],
            'sun_travel_direction_after': [round(v, 5) for v in after]}


def apply(bpy, scene, eye, inputs):
    path = Path(inputs['hdri'])
    actual = _sha(path)
    assert actual == HDRI_SHA256, actual
    image = bpy.data.images.load(str(path), check_existing=True)
    image.colorspace_settings.name = 'Linear Rec.709'
    hidden = _hide_background(scene)
    lighting = _rotate_world_and_sun(bpy, scene, image)
    proxy, rake_out = _proxy_mesh(bpy, scene)
    proxy.data.materials.append(_projection_material(bpy, image))
    ex, ey = float(eye[0]), float(eye[1])
    L = LAYOUT
    inside = L['main_stand_wall_x_m'] < ex < L['opposite_stand_wall_x_m'] and L['far_end_wall_y_m'] < ey < L['end_wall_y_m']
    assert inside, 'camera must be inside the stadium proxy'
    return {
        'hdri': str(path), 'hdri_sha256': actual,
        'layout': LAYOUT, 'rake_horizontal_extent_m': rake_out,
        'camera_offset_from_capture_point_m': math.hypot(ex - L['capture_point_m'][0], ey - L['capture_point_m'][1]),
        'lighting': lighting,
        'hidden_background_objects': len(hidden), 'hidden_examples': hidden[:8],
        'proxy_object': proxy.name, 'proxy_camera_ray_only': True,
        'physics_objects_touched': False, 'object_transforms_of_actors_edited': False,
        'crowd_present': False,
    }
