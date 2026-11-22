"""Natural-grass stadium pitch under the measured Orlando Stadium sky.

Everything the fixed camera sees is turf, so the turf carries the realism:
mown ryegrass blades are generated once per quarter-metre tile (a handful of
variants), instanced over the visible ground with mowing stripes, and stand
on a scanned thatch layer. The touchline is paint on those blades, not a flat
card. Light is Poly Haven's unclipped ``orlando_stadium`` HDRI: its sun is
located in the pixels at render time, cut out of the map and replaced by a
sun lamp with the same bearing, elevation, colour and irradiance, so the
shadows are crisp and the sun is not counted twice.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import RADIUS, KEYS

ROOT = _PCVE_ROOT
from pcve_assets import asset as _pcve_asset
MODELS = _pcve_asset('models')
ASSETS = _pcve_asset('') / 'polyhaven' / 'soccer_ball_collision'
HDRI = ASSETS / 'orlando_stadium_2k.hdr'
# AgX - Medium High Contrast; a sunlit pitch at noon sits about here.
EXPOSURE = -.25

# The physics ground plane z = 0 is where the balls touch: the top of a pitch
# mown to about 25 mm. Thatch/soil is the layer below it and the blades rise
# from there, so the lowest centimetre of every ball sits in the grass the way
# it does on a real pitch.
THATCH_Z = -.014
TILE = .25                      # m; one instanced patch of turf
BLADES_PER_TILE = 1500          # 24 000 shoots per square metre
TILE_VARIANTS = 10
TILE_SEED = 618
# Region tiled with blades: the camera's ground footprint (about
# x -3.5..2.0 at y 5.5, x -0.6..0.9 at y -1.2) plus room for the reflections
# in the balls and their shadows. Outside it only the thatch plane remains.
TURF_X = (-5.25, 3.5)
TURF_Y = (-3.0, 6.5)
# Mowing stripes run across the pitch (constant x), the mower driving along y:
# blades lean away from the camera on one stripe and towards it on the next.
STRIPE_WIDTH = 5.5
STRIPE_EDGE_X = -1.5
TOUCHLINE_Y = 3.5               # far edge of the pitch; 12 cm line (Law 1 maximum)
LINE_HALF_WIDTH = .06
# Bearing (atan2(y, x), scene frame) the sky is turned to put its sun at:
# left of and a little behind the camera, so the balls are lit three-quarter
# from the front-left and their shadows fall back-right across the turf.
SUN_AZIMUTH_DEG = 200.
SUN_ANGLE_DEG = .6              # hazy noon sun: a little wider than the 0.53 deg disc


def _rgb(n, l, fac, a, b, blend='MIX'):
    """MixRGB with each input either a socket or a constant; returns the output."""
    node = n.new('ShaderNodeMixRGB'); node.blend_type = blend
    for socket, value in zip(node.inputs, (fac, a, b)):
        if hasattr(value, 'is_linked'): l.new(value, socket)
        else: socket.default_value = value
    return node.outputs['Color']


def _hdri_sun(np, image):
    """Sun of an equirectangular map: direction in the map's own frame, its
    irradiance at normal incidence (with the surrounding sky subtracted), the
    sky radiance just around it, and the cone that contains the disc."""
    w, h = image.size
    px = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(px)
    rgb = px.reshape(h, w, 4)[..., :3].astype(np.float64)
    lum = rgb @ np.array([.2126, .7152, .0722])
    row, col = np.unravel_index(np.argmax(lum), lum.shape)
    # Blender equirect: u = 0.5 - atan2(y, x) / 2pi; image rows run bottom-up.
    lon = (.5 - (np.arange(w) + .5) / w) * 2 * math.pi
    lat = ((np.arange(h) + .5) / h - .5) * math.pi
    azimuth, elevation = lon[col], lat[row]
    sun = np.array([math.cos(elevation) * math.cos(azimuth),
                    math.cos(elevation) * math.sin(azimuth), math.sin(elevation)])
    cos_lat = np.cos(lat)[:, None]
    cos_angle = (cos_lat * np.cos(lon)[None, :] * sun[0] + cos_lat * np.sin(lon)[None, :] * sun[1]
                 + np.sin(lat)[:, None] * sun[2])
    ring = (cos_angle < math.cos(math.radians(3))) & (cos_angle > math.cos(math.radians(6)))
    fill = rgb[ring].mean(0)
    disc = (cos_angle > math.cos(math.radians(3))) & (lum > 3 * float(fill @ np.array([.2126, .7152, .0722])))
    solid_angle = (2 * math.pi / w) * (math.pi / h) * np.broadcast_to(cos_lat, lum.shape)
    irradiance = (np.clip(rgb - fill, 0, None)[disc] * solid_angle[disc][:, None]).sum(0)
    radius = math.degrees(math.acos(min(1., float(cos_angle[disc].min())))) + 360 / w
    return dict(azimuth_deg=math.degrees(azimuth), elevation_deg=math.degrees(elevation),
                irradiance=irradiance, fill=fill, radius_deg=radius)


def build_sky(bpy, scene):
    import numpy as np
    from mathutils import Vector
    image = bpy.data.images.load(str(HDRI), check_existing=True)
    image.colorspace_settings.name = 'Linear Rec.709'
    sun = _hdri_sun(np, image)
    # The mapping turns lookups by `turn`; the map's sun then appears at
    # azimuth (hdri azimuth - turn) in the scene.
    turn = sun['azimuth_deg'] - SUN_AZIMUTH_DEG
    azimuth, elevation = math.radians(SUN_AZIMUTH_DEG), math.radians(sun['elevation_deg'])
    toward_sun = Vector((math.cos(elevation) * math.cos(azimuth),
                         math.cos(elevation) * math.sin(azimuth), math.sin(elevation)))
    world = bpy.data.worlds.new('Orlando Stadium noon sky'); world.use_nodes = True
    scene.world = world
    n, l = world.node_tree.nodes, world.node_tree.links
    coord = n.new('ShaderNodeTexCoord')
    mapping = n.new('ShaderNodeMapping'); mapping.inputs['Rotation'].default_value[2] = math.radians(turn)
    env = n.new('ShaderNodeTexEnvironment'); env.image = image
    l.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    l.new(mapping.outputs['Vector'], env.inputs['Vector'])
    # Inside the disc cone the map shows the sky around the sun instead; the
    # lamp below carries the disc's energy.
    unit = n.new('ShaderNodeVectorMath'); unit.operation = 'NORMALIZE'
    l.new(coord.outputs['Generated'], unit.inputs[0])
    dot = n.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = toward_sun
    l.new(unit.outputs['Vector'], dot.inputs[0])
    inside = n.new('ShaderNodeMath'); inside.operation = 'GREATER_THAN'
    inside.inputs[1].default_value = math.cos(math.radians(sun['radius_deg']))
    l.new(dot.outputs['Value'], inside.inputs[0])
    cut = _rgb(n, l, inside.outputs['Value'], env.outputs['Color'], (*map(float, sun['fill']), 1))
    background = n.get('Background')
    l.new(cut, background.inputs['Color'])
    background.inputs['Strength'].default_value = 1.
    peak = float(sun['irradiance'].max())
    bpy.ops.object.light_add(type='SUN', location=(0, 0, 8))
    lamp = bpy.context.object; lamp.name = 'Noon sun (from HDRI)'
    lamp.rotation_euler = (-toward_sun).to_track_quat('-Z', 'Y').to_euler()
    lamp.data.energy = peak
    lamp.data.color = tuple(float(v) / peak for v in sun['irradiance'])
    lamp.data.angle = math.radians(SUN_ANGLE_DEG)
    print(f"[sky] HDRI sun azimuth {sun['azimuth_deg']:.2f} elevation {sun['elevation_deg']:.2f} deg, "
          f"disc {sun['radius_deg']:.2f} deg, irradiance {peak:.3f}; sky turned {turn:.2f} deg", flush=True)


def _turf_tile(bpy, np, rng, index):
    """One square of mown turf, centred on the origin, blades leaning to +y."""
    n = BLADES_PER_TILE
    root = np.column_stack([rng.uniform(-TILE / 2, TILE / 2, n), rng.uniform(-TILE / 2, TILE / 2, n),
                            np.full(n, THATCH_Z - .002)])
    length = rng.uniform(.018, .034, n)
    width = rng.uniform(.0018, .0036, n)
    # Most blades were laid over by the mower; a few stand up or lie anywhere.
    mown = rng.random(n) < .62
    heading = np.where(mown, math.pi / 2 + rng.normal(0, .65, n), rng.uniform(0, 2 * math.pi, n))
    lean_root = np.radians(rng.uniform(6, 40, n))
    lean_tip = lean_root + np.radians(rng.uniform(12, 42, n))
    t = np.array([0, 1 / 3, 2 / 3, 1.])
    angle = lean_root[:, None] + (lean_tip - lean_root)[:, None] * t[None, :] ** 2
    ch, sh = np.cos(heading)[:, None], np.sin(heading)[:, None]
    tangent = np.stack([np.sin(angle) * ch, np.sin(angle) * sh, np.cos(angle)], -1)
    step = (tangent[:, :-1] + tangent[:, 1:]) * .5 * (length / 3)[:, None, None]
    centre = root[:, None, :] + np.concatenate([np.zeros((n, 1, 3)), np.cumsum(step, 1)], 1)
    across = np.stack([-np.sin(heading), np.cos(heading), np.zeros(n)], -1)[:, None, :]
    face = np.cross(across, tangent)
    twist = (rng.normal(0, .45, n)[:, None] * t[None, :])[..., None]
    side = across * np.cos(twist) + face * np.sin(twist)
    normal = face * np.cos(twist) - across * np.sin(twist)
    # Mown blades end blunt: the tip row keeps most of the width.
    half = (width[:, None] * np.array([1., .96, .86, .66])[None, :] * .5)[..., None]
    rows = np.stack([centre - side * half, centre + normal * half * .45, centre + side * half], 2)
    verts = rows.reshape(-1, 3)
    b = np.arange(n)[:, None, None] * 12
    r = np.arange(3)[None, :, None] * 3
    c = np.arange(2)[None, None, :]
    v0 = b + r + c
    quads = np.stack([v0, v0 + 1, v0 + 4, v0 + 3], -1).reshape(-1, 4)
    mesh = bpy.data.meshes.new(f'Mown turf tile {index}')
    mesh.vertices.add(len(verts)); mesh.vertices.foreach_set('co', verts.astype(np.float32).ravel())
    mesh.loops.add(quads.size); mesh.loops.foreach_set('vertex_index', quads.astype(np.int32).ravel())
    mesh.polygons.add(len(quads))
    mesh.polygons.foreach_set('loop_start', np.arange(0, quads.size, 4, dtype=np.int32))
    mesh.polygons.foreach_set('use_smooth', np.ones(len(quads), bool))
    mesh.update(calc_edges=True)
    uv = mesh.uv_layers.new(name='UVMap')
    row_v = np.repeat(np.arange(4) / 3, 3).reshape(4, 3)
    col_u = np.tile(np.array([0., .5, 1.]), (4, 1))
    loop_vert = quads.reshape(-1) % 12
    uv.data.foreach_set('uv', np.column_stack([col_u.ravel()[loop_vert], row_v.ravel()[loop_vert]])
                        .astype(np.float32).ravel())
    tint = mesh.attributes.new('blade_tint', 'FLOAT', 'FACE')
    tint.data.foreach_set('value', np.repeat(rng.random(n), 6).astype(np.float32))
    return mesh


def _paint_mask(n, l, position):
    """1 on the touchline, with a slightly ragged sprayed edge."""
    sep = n.new('ShaderNodeSeparateXYZ'); l.new(position, sep.inputs[0])
    off = n.new('ShaderNodeMath'); off.operation = 'SUBTRACT'
    off.inputs[1].default_value = TOUCHLINE_Y
    l.new(sep.outputs['Y'], off.inputs[0])
    dist = n.new('ShaderNodeMath'); dist.operation = 'ABSOLUTE'; l.new(off.outputs[0], dist.inputs[0])
    rag = n.new('ShaderNodeTexNoise'); rag.inputs['Scale'].default_value = 22.
    rag.inputs['Detail'].default_value = 6.
    l.new(position, rag.inputs['Vector'])
    jitter = n.new('ShaderNodeMath'); jitter.operation = 'MULTIPLY_ADD'
    jitter.inputs[1].default_value = .016; jitter.inputs[2].default_value = LINE_HALF_WIDTH - .008
    l.new(rag.outputs['Fac'], jitter.inputs[0])
    edge = n.new('ShaderNodeMath'); edge.operation = 'LESS_THAN'
    l.new(dist.outputs[0], edge.inputs[0]); l.new(jitter.outputs[0], edge.inputs[1])
    return edge.outputs[0]


def _patchiness(n, l, position):
    """Large-scale (metre) variation of the sward: vigour and dry patches."""
    vigour = n.new('ShaderNodeTexNoise'); vigour.inputs['Scale'].default_value = .55
    vigour.inputs['Detail'].default_value = 4.; l.new(position, vigour.inputs['Vector'])
    dry = n.new('ShaderNodeTexNoise'); dry.inputs['Scale'].default_value = 1.7
    dry.inputs['Detail'].default_value = 3.; l.new(position, dry.inputs['Vector'])
    dryness = n.new('ShaderNodeMapRange'); dryness.inputs['From Min'].default_value = .56
    dryness.inputs['From Max'].default_value = .75; dryness.inputs['To Max'].default_value = .55
    l.new(dry.outputs['Fac'], dryness.inputs['Value'])
    gain = n.new('ShaderNodeMapRange'); gain.inputs['From Min'].default_value = .3
    gain.inputs['From Max'].default_value = .7; gain.inputs['To Min'].default_value = .98
    gain.inputs['To Max'].default_value = 1.45
    l.new(vigour.outputs['Fac'], gain.inputs['Value'])
    return gain.outputs['Result'], dryness.outputs['Result']


def blade_material(bpy):
    mat = bpy.data.materials.new('Mown ryegrass blades'); mat.use_nodes = True
    n, l = mat.node_tree.nodes, mat.node_tree.links
    n.remove(n.get('Principled BSDF'))
    geo = n.new('ShaderNodeNewGeometry')
    tint = n.new('ShaderNodeAttribute'); tint.attribute_type = 'GEOMETRY'; tint.attribute_name = 'blade_tint'
    ramp = n.new('ShaderNodeValToRGB'); stops = ramp.color_ramp.elements
    palette = [(0., (.028, .066, .010)), (.3, (.046, .104, .015)), (.62, (.070, .142, .024)),
               (.85, (.105, .160, .034)), (.95, (.170, .165, .068)), (1., (.215, .195, .095))]
    stops[0].position, stops[0].color = palette[0][0], (*palette[0][1], 1)
    stops[1].position, stops[1].color = palette[-1][0], (*palette[-1][1], 1)
    for pos, col in palette[1:-1]:
        e = stops.new(pos); e.color = (*col, 1)
    l.new(tint.outputs['Fac'], ramp.inputs['Fac'])
    gain, dryness = _patchiness(n, l, geo.outputs['Position'])
    straw = _rgb(n, l, dryness, ramp.outputs['Color'], (.20, .18, .075, 1))
    # Along the blade: paler, shaded sheath at the root; frayed, bleached cut at the tip.
    uv = n.new('ShaderNodeUVMap'); uv.uv_map = 'UVMap'
    along = n.new('ShaderNodeSeparateXYZ'); l.new(uv.outputs['UV'], along.inputs[0])
    root = n.new('ShaderNodeMapRange'); root.inputs['To Min'].default_value = .62
    l.new(along.outputs['Y'], root.inputs['Value'])
    shade = n.new('ShaderNodeMath'); shade.operation = 'MULTIPLY'
    l.new(root.outputs['Result'], shade.inputs[0]); l.new(gain, shade.inputs[1])
    gray = n.new('ShaderNodeCombineXYZ')
    for k in ('X', 'Y', 'Z'): l.new(shade.outputs[0], gray.inputs[k])
    lit = _rgb(n, l, 1., straw, gray.outputs[0], 'MULTIPLY')
    tip = n.new('ShaderNodeMapRange'); tip.inputs['From Min'].default_value = .9
    tip.inputs['To Max'].default_value = .45; l.new(along.outputs['Y'], tip.inputs['Value'])
    cut = _rgb(n, l, tip.outputs['Result'], lit, (.24, .22, .13, 1))
    paint = _paint_mask(n, l, geo.outputs['Position'])
    paint_cover = n.new('ShaderNodeMath'); paint_cover.operation = 'MULTIPLY'
    paint_cover.inputs[1].default_value = .9; l.new(paint, paint_cover.inputs[0])
    painted = _rgb(n, l, paint_cover.outputs[0], cut, (.78, .79, .76, 1))
    surface = n.new('ShaderNodeBsdfPrincipled')
    l.new(painted, surface.inputs['Base Color'])
    rough = n.new('ShaderNodeMapRange'); rough.inputs['To Min'].default_value = .46
    rough.inputs['To Max'].default_value = .78; l.new(paint, rough.inputs['Value'])
    l.new(rough.outputs['Result'], surface.inputs['Roughness'])
    surface.inputs['Specular IOR Level'].default_value = .5
    # Thin leaves pass light: a translucent lobe lets backlit blades glow.
    glow = _rgb(n, l, 1., painted, (1.5, 1.9, 1.1, 1), 'MULTIPLY')
    translucent = n.new('ShaderNodeBsdfTranslucent'); l.new(glow, translucent.inputs['Color'])
    share = n.new('ShaderNodeMapRange'); share.inputs['To Min'].default_value = .32
    share.inputs['To Max'].default_value = .05; l.new(paint, share.inputs['Value'])
    mix = n.new('ShaderNodeMixShader'); l.new(share.outputs['Result'], mix.inputs['Fac'])
    l.new(surface.outputs['BSDF'], mix.inputs[1]); l.new(translucent.outputs['BSDF'], mix.inputs[2])
    l.new(mix.outputs['Shader'], n.get('Material Output').inputs['Surface'])
    return mat


def thatch_material(bpy):
    """The layer under the canopy: scanned grass ground at its real 2.51 m size."""
    mat = bpy.data.materials.new('Thatch and soil under the sward'); mat.use_nodes = True
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = n.get('Principled BSDF')
    geo = n.new('ShaderNodeNewGeometry')
    scale = n.new('ShaderNodeVectorMath'); scale.operation = 'SCALE'
    scale.inputs['Scale'].default_value = 1 / 2.51
    l.new(geo.outputs['Position'], scale.inputs[0])
    images = {}
    for channel in ('diff', 'rough', 'nor_gl'):
        image = bpy.data.images.load(str(ASSETS / f'grass_ground_{channel}_2k.jpg'), check_existing=True)
        image.colorspace_settings.name = 'sRGB' if channel == 'diff' else 'Non-Color'
        tex = n.new('ShaderNodeTexImage'); tex.image = image
        l.new(scale.outputs['Vector'], tex.inputs['Vector']); images[channel] = tex
    tint = _rgb(n, l, 1., images['diff'].outputs['Color'], (.42, .62, .28, 1), 'MULTIPLY')
    paint = _paint_mask(n, l, geo.outputs['Position'])
    l.new(_rgb(n, l, paint, tint, (.62, .63, .60, 1)), bs.inputs['Base Color'])
    l.new(images['rough'].outputs['Color'], bs.inputs['Roughness'])
    normal = n.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value = .6
    l.new(images['nor_gl'].outputs['Color'], normal.inputs['Color'])
    l.new(normal.outputs['Normal'], bs.inputs['Normal'])
    return mat


def build_turf(bpy):
    import numpy as np
    rng = np.random.default_rng(TILE_SEED)
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, THATCH_Z))
    ground = bpy.context.object; ground.name = 'Pitch thatch and soil'
    ground.scale = (240, 240, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ground.data.materials.append(thatch_material(bpy))
    blades = blade_material(bpy)
    tiles = []
    for index in range(TILE_VARIANTS):
        mesh = _turf_tile(bpy, np, rng, index); mesh.materials.append(blades); tiles.append(mesh)
    collection = bpy.data.collections.new('Mown turf'); bpy.context.scene.collection.children.link(collection)
    x0 = STRIPE_EDGE_X - TILE * math.ceil((STRIPE_EDGE_X - TURF_X[0]) / TILE)
    nx = math.ceil((TURF_X[1] - x0) / TILE); ny = math.ceil((TURF_Y[1] - TURF_Y[0]) / TILE)
    for i in range(nx):
        x = x0 + (i + .5) * TILE
        towards_camera = math.floor((x - STRIPE_EDGE_X) / STRIPE_WIDTH) % 2
        for j in range(ny):
            y = TURF_Y[0] + (j + .5) * TILE
            obj = bpy.data.objects.new(f'Turf {i:02d}-{j:02d}', tiles[int(rng.integers(TILE_VARIANTS))])
            obj.location = (x, y, 0)
            obj.rotation_euler = (0, 0, math.pi * towards_camera)
            obj.scale = (-1 if rng.random() < .5 else 1, 1, 1)
            collection.objects.link(obj)
    print(f'[turf] {nx * ny} tiles x {BLADES_PER_TILE} blades, thatch at z={THATCH_Z}', flush=True)


def build_environment(bpy, scene):
    build_sky(bpy, scene)
    build_turf(bpy)


def ball_finish(bpy, mat):
    """PU match-ball skin: dielectric, satin, with a thin glossy film."""
    if not mat or not mat.use_nodes: return
    for shader in mat.node_tree.nodes:
        if shader.type != 'BSDF_PRINCIPLED': continue
        for name, value in [('Metallic', 0.), ('Roughness', .5)]:
            for link in list(shader.inputs[name].links): mat.node_tree.links.remove(link)
            shader.inputs[name].default_value = value
        shader.inputs['Coat Weight'].default_value = .3
        shader.inputs['Coat Roughness'].default_value = .22
        shader.inputs['Coat IOR'].default_value = 1.5


def make_balls(bpy):
    from mathutils import Vector
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(MODELS/'cheap_soccer_ball.glb'))
    imported = set(bpy.data.objects) - before
    meshes = [o for o in imported if o.type == 'MESH' and len(o.data.materials)]
    if len(meshes) != 1:
        raise RuntimeError('Expected one soccer ball mesh in supplied GLB')
    obj = meshes[0]
    # Evaluate the supplied rig once, then bake its world transform into the mesh.
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(deps), depsgraph=deps)
    mesh.transform(obj.matrix_world)
    lo = Vector(tuple(min(v.co[j] for v in mesh.vertices) for j in range(3)))
    hi = Vector(tuple(max(v.co[j] for v in mesh.vertices) for j in range(3)))
    center = (lo+hi)*.5
    radius = max((v.co-center).length for v in mesh.vertices)
    for v in mesh.vertices:
        v.co = (v.co-center) * (RADIUS/radius)
    mesh.update()
    for o in imported: bpy.data.objects.remove(o, do_unlink=True)
    for poly in mesh.polygons: poly.use_smooth = True
    for mat in mesh.materials: ball_finish(bpy, mat)
    result = {}
    for i, key in enumerate(KEYS):
        root = bpy.data.objects.new(key, None); bpy.context.collection.objects.link(root)
        visual = bpy.data.objects.new(f'{key}_scanned_leather', mesh)
        bpy.context.collection.objects.link(visual); visual.parent = root
        visual.rotation_euler = (.20+i*.55,.35+i*.8,-.18+i*.6)
        result[key] = root
    print(f'[assets] soccer radius={RADIUS} m; {len(mesh.vertices)} vertices', flush=True)
    return result
