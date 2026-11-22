"""A sunlit school courtyard corner; every surface a ball touches is solver geometry.

The forecourt is interlocking concrete paving: the top of the solver's 'floor'
slab (z = 0). The step is a row of precast concrete kerb stones whose riser is the
solver platform's face at x = STEP_X and whose top, like the stone-slab terrace
behind it, is the platform top (z = step height). Kerb joints sit half a metre
either side of the ball lane, so the ball always meets an unbroken arris. The
yellow-brick school facades stand exactly where the solver's back and right
walls are; the solver's left wall (x = -3.8) lies behind the camera's field of
view, is never reached by either ball, and is not drawn, so it does not shade
the forecourt from the low western sun.

Light is Poly Haven's unclipped ``quadrangle_sunny`` HDRI (a university
quadrangle). Its sun is located in the pixels, cut out of the map and replaced
by a sun lamp with the same elevation, colour and irradiance, turned to the
bearing below, so shadows are crisp and the sun is not counted twice (the same
method as soccer_ball_collision). The camera never sees the sky: the facades
fill the top of the frame.

Props (utility cabinet, crate, broom, downpipe, window joinery) are not in the
simulation; check_props() refuses to render if any of them comes within
PROP_CLEARANCE_M of a ball or hides a ball centre from the camera.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
import bpy
from mathutils import Vector, Matrix
from pcve_assets import asset as _pcve_asset
from scene_geometry import ROOM_X, ROOM_Y, STEP_X, LANE_Y

ASSETS = _pcve_asset('') / 'polyhaven' / 'soccer_step_collision'

HDRI = ASSETS / 'quadrangle_sunny_2k.hdr'
# AgX - Medium High Contrast; exposure for a sunlit courtyard.
EXPOSURE = 0.
# Bearing (atan2(y, x), scene frame) the sky is turned to put its sun at:
# behind and left of the camera, so both facades and the balls are lit from the
# front-left and the ball shadows fall back and to the right along the lane.
SUN_AZIMUTH_DEG = 208.
SUN_ANGLE_DEG = .6
PROP_CLEARANCE_M = .02
# Visible extent of the paving beyond the solver slabs (same planes, z = 0 and
# z = step height); only reached by camera rays, never by the balls.
FAR = 14.
KERB_WIDTH = .25            # m, depth of the kerb stones behind the riser
KERB_LENGTH = 1.0           # m, along the step
KERB_JOINT = .008           # m, mortar joint between kerb stones
EDGE_RADIUS = .0015         # m, arris bevel on the stones (solver edge is sharp)
BRICK_SET_BACK = .03        # brick face behind the stone plinth face (= solver wall face)
PLINTH_TOP = .40
WINDOW_SILL_Z = 1.0
WINDOW_HEAD_Z = 2.7
# Window openings in the back facade (x ranges); the right 2.2 m is solid brick.
WINDOWS_X = ((-3.0, -1.6), (-1.0, .4), (1.0, 2.4))
FACADE_TOP = 7.
CLASSROOM_PANEL_W = 6.      # W per ceiling panel (8 panels) in the room behind the windows


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def _image(stem, channel):
    image = bpy.data.images.load(str(ASSETS / f'{stem}_{channel}_2k.jpg'), check_existing=True)
    image.colorspace_settings.name = 'sRGB' if channel == 'diff' else 'Non-Color'
    return image


def scanned_material(name, stem, size_m, tint=(1., 1., 1.), rough=(0., 1.), normal_strength=1.,
                     variation=.18, variation_scale=.35, per_object=False, saturation=1.):
    """Poly Haven texture set on world-projected UVs (see world_uv) at its real size.

    A metre-scale noise varies the albedo by +-variation so the tiling does not
    read; per_object shifts each object's texture by its random id; saturation
    scales the scan's colour saturation.
    """
    m = bpy.data.materials.new(name); m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    bs = n.get('Principled BSDF')
    uv = n.new('ShaderNodeUVMap'); uv.uv_map = 'WorldUV'
    scale = n.new('ShaderNodeVectorMath'); scale.operation = 'SCALE'
    scale.inputs['Scale'].default_value = 1 / size_m
    l.new(uv.outputs['UV'], scale.inputs[0])
    vector = scale.outputs['Vector']
    if per_object:
        info = n.new('ShaderNodeObjectInfo')
        shift = n.new('ShaderNodeCombineXYZ')
        mul = n.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = 17.31
        l.new(info.outputs['Random'], mul.inputs[0])
        l.new(mul.outputs[0], shift.inputs['X']); l.new(mul.outputs[0], shift.inputs['Y'])
        add = n.new('ShaderNodeVectorMath'); add.operation = 'ADD'
        l.new(vector, add.inputs[0]); l.new(shift.outputs[0], add.inputs[1]); vector = add.outputs['Vector']
    tex = {}
    for channel in ('diff', 'rough', 'nor_gl'):
        t = n.new('ShaderNodeTexImage'); t.image = _image(stem, channel)
        l.new(vector, t.inputs['Vector']); tex[channel] = t
    geo = n.new('ShaderNodeNewGeometry')
    noise = n.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = variation_scale
    noise.inputs['Detail'].default_value = 3.
    l.new(geo.outputs['Position'], noise.inputs['Vector'])
    gain = n.new('ShaderNodeMapRange'); gain.inputs['From Min'].default_value = .3
    gain.inputs['From Max'].default_value = .7
    gain.inputs['To Min'].default_value = 1 - variation; gain.inputs['To Max'].default_value = 1 + variation
    l.new(noise.outputs['Fac'], gain.inputs['Value'])
    tinted = n.new('ShaderNodeMixRGB'); tinted.blend_type = 'MULTIPLY'; tinted.inputs[0].default_value = 1.
    tinted.inputs[2].default_value = (*tint, 1)
    l.new(tex['diff'].outputs['Color'], tinted.inputs[1])
    varied = n.new('ShaderNodeVectorMath'); varied.operation = 'SCALE'
    hsv = n.new('ShaderNodeHueSaturation'); hsv.inputs['Saturation'].default_value = saturation
    l.new(tinted.outputs['Color'], hsv.inputs['Color'])
    l.new(hsv.outputs['Color'], varied.inputs[0]); l.new(gain.outputs['Result'], varied.inputs['Scale'])
    l.new(varied.outputs['Vector'], bs.inputs['Base Color'])
    remap = n.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = rough
    l.new(tex['rough'].outputs['Color'], remap.inputs['Value']); l.new(remap.outputs['Result'], bs.inputs['Roughness'])
    normal = n.new('ShaderNodeNormalMap'); normal.uv_map = 'WorldUV'
    normal.inputs['Strength'].default_value = normal_strength
    l.new(tex['nor_gl'].outputs['Color'], normal.inputs['Color']); l.new(normal.outputs['Normal'], bs.inputs['Normal'])
    return m


def plain_material(name, color, roughness, metallic=0., noise_bump=0.):
    m = bpy.data.materials.new(name); m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    bs = n.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['Metallic'].default_value = metallic
    if noise_bump:
        geo = n.new('ShaderNodeNewGeometry')
        noise = n.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 60.
        noise.inputs['Detail'].default_value = 8.
        l.new(geo.outputs['Position'], noise.inputs['Vector'])
        bump = n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = noise_bump
        bump.inputs['Distance'].default_value = .0005
        l.new(noise.outputs['Fac'], bump.inputs['Height']); l.new(bump.outputs['Normal'], bs.inputs['Normal'])
        rough = n.new('ShaderNodeMapRange'); rough.inputs['To Min'].default_value = roughness * .8
        rough.inputs['To Max'].default_value = min(1., roughness * 1.25)
        l.new(noise.outputs['Fac'], rough.inputs['Value']); l.new(rough.outputs['Result'], bs.inputs['Roughness'])
    return m


def window_glass():
    """Clear float glass. Shadow rays pass straight through it, so the sun lights
    the classroom without needing caustics; camera rays refract and reflect."""
    m = bpy.data.materials.new('Clear float glass'); m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    bs = n.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (.96, .98, .97, 1)
    bs.inputs['Roughness'].default_value = 0.
    bs.inputs['IOR'].default_value = 1.52
    bs.inputs['Transmission Weight'].default_value = 1.
    # Solar-control coating on the outer pane: about 10 % more specular reflection.
    bs.inputs['Coat Weight'].default_value = 1.
    bs.inputs['Coat Roughness'].default_value = 0.
    bs.inputs['Coat IOR'].default_value = 1.9
    path = n.new('ShaderNodeLightPath'); clear = n.new('ShaderNodeBsdfTransparent')
    mix = n.new('ShaderNodeMixShader')
    l.new(path.outputs['Is Shadow Ray'], mix.inputs['Fac'])
    l.new(bs.outputs['BSDF'], mix.inputs[1]); l.new(clear.outputs['BSDF'], mix.inputs[2])
    l.new(mix.outputs['Shader'], n.get('Material Output').inputs['Surface'])
    return m


def blind_fabric():
    """Beige roller-blind cloth: diffuse front, some light through from the lit room behind."""
    m = bpy.data.materials.new('Beige roller-blind fabric'); m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    bs = n.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (.66, .60, .49, 1); bs.inputs['Roughness'].default_value = .92
    through = n.new('ShaderNodeBsdfTranslucent'); through.inputs['Color'].default_value = (.66, .60, .49, 1)
    mix = n.new('ShaderNodeMixShader'); mix.inputs['Fac'].default_value = .3
    l.new(bs.outputs['BSDF'], mix.inputs[1]); l.new(through.outputs['BSDF'], mix.inputs[2])
    l.new(mix.outputs['Shader'], n.get('Material Output').inputs['Surface'])
    return m


def world_uv(obj):
    """UVs = world coordinates of each face's plane (metres), so textures keep their real size."""
    mesh = obj.data; mw = obj.matrix_world
    layer = mesh.uv_layers.get('WorldUV') or mesh.uv_layers.new(name='WorldUV')
    mesh.uv_layers.active = layer
    for poly in mesh.polygons:
        nrm = (mw.to_3x3() @ poly.normal)
        ax = max(range(3), key=lambda i: abs(nrm[i]))
        for li in poly.loop_indices:
            p = mw @ mesh.vertices[mesh.loops[li].vertex_index].co
            if ax == 2: u, v = p.x * (1 if nrm.z > 0 else -1), p.y
            elif ax == 1: u, v = p.x * (-1 if nrm.y > 0 else 1), p.z
            else: u, v = p.y * (1 if nrm.x > 0 else -1), p.z
            layer.data[li].uv = (u, v)


def block(name, lo, hi, mat, role, bevel=0.):
    """Axis-aligned box from corner lo to corner hi (metres), world-UV mapped."""
    lo, hi = Vector(lo), Vector(hi)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(lo + hi) / 2)
    o = bpy.context.object; o.name = name; o.dimensions = hi - lo
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    world_uv(o)
    if bevel:
        mod = o.modifiers.new('Arris', 'BEVEL'); mod.width = bevel; mod.segments = 2
        mod.limit_method = 'ANGLE'
        o.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    o['pcve_role'] = role
    return o


def _hdri_sun(np, image):
    """Sun of an equirectangular map: direction, irradiance (sky subtracted), surrounding sky, disc cone."""
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


def build_sky(scene):
    import numpy as np
    image = bpy.data.images.load(str(HDRI), check_existing=True)
    image.colorspace_settings.name = 'Linear Rec.709'
    sun = _hdri_sun(np, image)
    turn = sun['azimuth_deg'] - SUN_AZIMUTH_DEG
    azimuth, elevation = math.radians(SUN_AZIMUTH_DEG), math.radians(sun['elevation_deg'])
    toward_sun = Vector((math.cos(elevation) * math.cos(azimuth),
                         math.cos(elevation) * math.sin(azimuth), math.sin(elevation)))
    world = bpy.data.worlds.new('Quadrangle sunny sky'); world.use_nodes = True
    scene.world = world
    n, l = world.node_tree.nodes, world.node_tree.links
    coord = n.new('ShaderNodeTexCoord')
    mapping = n.new('ShaderNodeMapping'); mapping.inputs['Rotation'].default_value[2] = math.radians(turn)
    env = n.new('ShaderNodeTexEnvironment'); env.image = image
    l.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    l.new(mapping.outputs['Vector'], env.inputs['Vector'])
    # Inside the disc cone the map shows the surrounding sky; the lamp carries the disc.
    unit = n.new('ShaderNodeVectorMath'); unit.operation = 'NORMALIZE'
    l.new(coord.outputs['Generated'], unit.inputs[0])
    dot = n.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = toward_sun
    l.new(unit.outputs['Vector'], dot.inputs[0])
    inside = n.new('ShaderNodeMath'); inside.operation = 'GREATER_THAN'
    inside.inputs[1].default_value = math.cos(math.radians(sun['radius_deg']))
    l.new(dot.outputs['Value'], inside.inputs[0])
    cut = n.new('ShaderNodeMixRGB'); cut.blend_type = 'MIX'
    l.new(inside.outputs['Value'], cut.inputs[0]); l.new(env.outputs['Color'], cut.inputs[1])
    cut.inputs[2].default_value = (*map(float, sun['fill']), 1)
    background = n.get('Background')
    l.new(cut.outputs['Color'], background.inputs['Color'])
    background.inputs['Strength'].default_value = 1.
    # The sky lights the scene and shows in reflections (window glass, balls),
    # but camera rays never see it directly (the facades fill the frame anyway).
    world.cycles_visibility.camera = False
    world.cycles_visibility.glossy = True
    peak = float(sun['irradiance'].max())
    bpy.ops.object.light_add(type='SUN', location=(0, 0, 8))
    lamp = bpy.context.object; lamp.name = 'Afternoon sun (from HDRI)'
    lamp.rotation_euler = (-toward_sun).to_track_quat('-Z', 'Y').to_euler()
    lamp.data.energy = peak
    lamp.data.color = tuple(float(v) / peak for v in sun['irradiance'])
    lamp.data.angle = math.radians(SUN_ANGLE_DEG)
    print(f"[sky] HDRI sun azimuth {sun['azimuth_deg']:.2f} elevation {sun['elevation_deg']:.2f} deg, "
          f"disc {sun['radius_deg']:.2f} deg, irradiance {peak:.3f}; sky turned {turn:.2f} deg", flush=True)
    return dict(hdri_sun_elevation_deg=sun['elevation_deg'], sun_azimuth_deg=SUN_AZIMUTH_DEG, irradiance=peak)


def import_gltf(folder, name):
    """Import a Poly Haven glTF, bake its hierarchy into one mesh object at the origin of its bbox floor."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(ASSETS / folder / f'{folder}_1k.gltf'))
    imported = set(bpy.data.objects) - before
    bpy.context.view_layer.update(); deps = bpy.context.evaluated_depsgraph_get(); parts = []
    for o in imported:
        if o.type != 'MESH': continue
        mesh = bpy.data.meshes.new_from_object(o.evaluated_get(deps), depsgraph=deps)
        mesh.transform(o.matrix_world)
        obj = bpy.data.objects.new(name, mesh); bpy.context.collection.objects.link(obj); parts.append(obj)
    for o in imported: bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts: o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1: bpy.ops.object.join()
    obj = bpy.context.object; obj.name = name
    lo = Vector(tuple(min(v.co[i] for v in obj.data.vertices) for i in range(3)))
    hi = Vector(tuple(max(v.co[i] for v in obj.data.vertices) for i in range(3)))
    # Origin at the centre of the footprint, on the lowest vertex.
    shift = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    obj.data.transform(Matrix.Translation(-shift))
    obj['pcve_role'] = 'prop'; obj['source_asset'] = f'polyhaven/soccer_step_collision/{folder}'
    return obj, hi - lo


def build_ground(h):
    pavers = scanned_material('Interlocking concrete pavers', 'concrete_pavers', 1.92,
                              tint=(.95, .95, .97), rough=(.55, .95), normal_strength=.9, variation=.16,
                              saturation=.55)
    slabs = scanned_material('Grey stone terrace slabs', 'large_grey_tiles', 3.0,
                             tint=(1.02, 1.0, .97), rough=(.45, .9), normal_strength=.8, variation=.12)
    kerb = scanned_material('Precast concrete kerb stones', 'brushed_concrete', 2.5,
                            tint=(.92, .92, .93), rough=(.5, .85), normal_strength=.7,
                            variation=.07, per_object=True, saturation=.6)
    # Forecourt: the solver floor slab (top z = 0) carried on to the frame edge.
    block('floor', (-FAR, -FAR, -.16), (STEP_X, ROOM_Y[1], 0.), pavers, 'collision')
    # Kerb stones: riser = platform face at x = STEP_X, top = platform top. Joints
    # at LANE_Y +- KERB_LENGTH/2 + k*KERB_LENGTH keep the lane's arris continuous.
    y = LANE_Y - KERB_LENGTH / 2
    while y > -FAR: y -= KERB_LENGTH
    i = 0
    while y < ROOM_Y[1]:
        y1 = min(ROOM_Y[1], y + KERB_LENGTH)
        lo_y = y + KERB_JOINT / 2 if y > -FAR else y
        hi_y = y1 - KERB_JOINT / 2 if y1 < ROOM_Y[1] else y1
        block(f'platform kerb stone {i:02d}', (STEP_X, lo_y, -.12), (STEP_X + KERB_WIDTH, hi_y, h),
              kerb, 'collision', EDGE_RADIUS)
        y = y1; i += 1
    # Mortar bed visible in the joints, well below the kerb top.
    block('kerb joint bedding', (STEP_X + .002, -FAR, -.12), (STEP_X + KERB_WIDTH - .002, ROOM_Y[1], h - .012),
          plain_material('Dark mortar bedding', (.10, .095, .09), .9), 'collision')
    # Terrace slabs behind the kerb: the rest of the platform top.
    block('platform terrace slabs', (STEP_X + KERB_WIDTH, -FAR, -.12), (ROOM_X[1], ROOM_Y[1], h), slabs, 'collision')


def build_facades(h):
    brick = scanned_material('Yellow school brick', 'yellow_brick', 2.0, tint=(.93, .90, .86),
                             rough=(.7, 1.), normal_strength=1., variation=.10, saturation=.82)
    plinth = scanned_material('Stone plinth', 'large_grey_tiles', 1.6, tint=(.80, .80, .82),
                              rough=(.5, .85), normal_strength=.6, variation=.08)
    sill = scanned_material('Stone window sills', 'large_grey_tiles', 1.1, tint=(.95, .95, .95),
                            rough=(.35, .7), normal_strength=.5, variation=.05, per_object=True)
    frame = plain_material('Anodised aluminium window frames', (.11, .115, .12), .38, .8, .05)
    glass = window_glass()
    blind = blind_fabric()
    interior_wall = plain_material('Classroom emulsion paint', (.74, .73, .70), .9, 0., .05)
    interior_floor = plain_material('Classroom vinyl floor', (.20, .19, .17), .55, 0., .05)
    y0, y1 = ROOM_Y[1], ROOM_Y[1] + .45
    x0, x1 = -FAR, ROOM_X[1]
    yb = y0 + BRICK_SET_BACK
    # Back facade: plinth on the solver wall face, brick set back above it.
    block('back_wall plinth', (x0, y0, -.1), (x1, y1, PLINTH_TOP), plinth, 'collision')
    edges = sorted(WINDOWS_X)
    xs = [x0] + [v for w in edges for v in w] + [x1]
    for k in range(0, len(xs), 2):
        block('back_wall brick pier', (xs[k], yb, PLINTH_TOP), (xs[k + 1], y1, FACADE_TOP), brick, 'collision')
    for i, (a, b) in enumerate(edges):
        block('back_wall brick under window', (a, yb, PLINTH_TOP), (b, y1, WINDOW_SILL_Z), brick, 'collision')
        block('back_wall brick over window', (a, yb, WINDOW_HEAD_Z), (b, y1, FACADE_TOP), brick, 'collision')
        # Joinery sits in the reveal, behind the brick face; only the sill nose is proud of it.
        block(f'window sill {i}', (a - .04, y0 - .02, WINDOW_SILL_Z - .05), (b + .04, yb + .14, WINDOW_SILL_Z),
              sill, 'prop', .004)
        fy0, fy1 = yb + .12, yb + .18
        for xa, xb in ((a, a + .06), (b - .06, b), ((a + b) / 2 - .03, (a + b) / 2 + .03)):
            block(f'window frame {i} jamb', (xa, fy0, WINDOW_SILL_Z), (xb, fy1, WINDOW_HEAD_Z), frame, 'prop', .003)
        for za, zb in ((WINDOW_SILL_Z, WINDOW_SILL_Z + .07), (WINDOW_HEAD_Z - .06, WINDOW_HEAD_Z)):
            block(f'window frame {i} rail', (a, fy0, za), (b, fy1, zb), frame, 'prop', .003)
        block(f'window glass {i}', (a + .05, fy0 + .025, WINDOW_SILL_Z + .06), (b - .05, fy0 + .031, WINDOW_HEAD_Z - .05),
              glass, 'prop')
        # Roller blinds inside, each pulled down to a different height.
        drop = (.70, .45, .58)[i % 3]
        block(f'window blind {i}', (a + .04, y1 - .03, WINDOW_HEAD_Z - drop * (WINDOW_HEAD_Z - WINDOW_SILL_Z)),
              (b - .04, y1 - .025, WINDOW_HEAD_Z - .02), blind, 'prop')
    # The classroom behind the back facade, seen (dimly) through the glass.
    iy0, iy1, ih = y1, y1 + 6., 3.2
    for name, lo, hi, mat in (('floor', (x0, iy0, -.1), (x1, iy1, .3), interior_floor),
                              ('ceiling', (x0, iy0, ih), (x1, iy1, ih + .2), interior_wall),
                              ('back wall', (x0, iy1, -.1), (x1, iy1 + .2, ih + .2), interior_wall),
                              ('end wall', (x1, iy0, -.1), (x1 + .2, iy1, ih + .2), interior_wall),
                              ('far end wall', (x0 - .2, iy0, -.1), (x0, iy1, ih + .2), interior_wall)):
        block(f'Classroom {name}', lo, hi, mat, 'prop')
    # The classroom's ceiling panels are on, as in a school during the day, so the
    # room shows faintly behind the reflections instead of reading as a black hole.
    for lx in (-2.6, -.6, 1.4, 3.4):
        for ly in (iy0 + 1.4, iy0 + 3.6):
            d = bpy.data.lights.new('Classroom ceiling panel', 'AREA'); d.shape = 'RECTANGLE'
            d.size, d.size_y = 1.2, .3; d.energy = CLASSROOM_PANEL_W; d.color = (1., .96, .90)
            o = bpy.data.objects.new('Classroom ceiling panel', d); bpy.context.collection.objects.link(o)
            o.location = (lx, ly, ih - .02)
    # Right facade: plinth face on the solver's right wall face.
    rx0 = ROOM_X[1]
    block('right_wall plinth', (rx0, -FAR, -.1), (rx0 + .45, y1, PLINTH_TOP), plinth, 'collision')
    block('right_wall brick', (rx0 + BRICK_SET_BACK, -FAR, PLINTH_TOP), (rx0 + .45, y1, FACADE_TOP), brick, 'collision')
    # Downpipe in the internal corner, with brackets and a shoe onto the terrace.
    metal = plain_material('Grey powder-coated downpipe', (.32, .33, .34), .42, .3, .08)
    px, py, r = rx0 - .075, y0 - .075, .04
    bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=r, depth=FACADE_TOP - h - .2,
                                        location=(px, py, h + .2 + (FACADE_TOP - h - .2) / 2))
    pipe = bpy.context.object; pipe.name = 'Downpipe'; pipe.data.materials.append(metal); pipe['pcve_role'] = 'prop'
    for f in pipe.data.polygons: f.use_smooth = True
    bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=r, depth=.26, location=(px - .07, py - .07, h + .12),
                                        rotation=(math.radians(50), 0, math.radians(-45)))
    shoe = bpy.context.object; shoe.name = 'Downpipe shoe'; shoe.data.materials.append(metal); shoe['pcve_role'] = 'prop'
    for f in shoe.data.polygons: f.use_smooth = True
    for z in (.9, 2.1):
        block('Downpipe bracket', (px - .05, py + r - .002, h + z), (px + .05, y0 + .03, h + z + .025), metal, 'prop')
        block('Downpipe bracket', (px + r - .002, py - .05, h + z), (rx0 + .03, py + .05, h + z + .025), metal, 'prop')


def place_props(h):
    """Scanned courtyard props against the facades, far from the ball lane."""
    props = []
    box, size = import_gltf('utility_box_02', 'Electrical utility cabinet')
    # Model front faces -y; stand it on the terrace against the back plinth.
    box.location = (3.95, ROOM_Y[1] - size.y / 2 - .01, h)
    props.append(box)
    crate, csize = import_gltf('plastic_crate_03', 'Red plastic crate')
    crate.rotation_euler.z = math.radians(-8)
    crate.location = (2.25, ROOM_Y[1] - csize.y / 2 - .05, h)
    props.append(crate)
    broom, bsize = import_gltf('plastic_broom', 'Yard broom leaning on the facade')
    props.append(broom)
    return props, bsize


def lean_broom(broom, size, h):
    """Head on the terrace, handle resting against the brick: tilt about x until the top touches."""
    broom.rotation_mode = 'ZXY'  # turn the head parallel to the wall first, then tilt towards it
    broom.rotation_euler = (math.radians(-11), 0, math.radians(90))
    broom.location = (3.0, 0., h)
    bpy.context.view_layer.update()
    pts = [broom.matrix_world @ v.co for v in broom.data.vertices]
    max_y = max(p.y for p in pts); min_z = min(p.z for p in pts)
    broom.location.y += (ROOM_Y[1] + BRICK_SET_BACK - .003) - max_y
    broom.location.z += h - min_z
    bpy.context.view_layer.update()


def build_scene(s):
    h = s['physics']['step_height']
    scene = bpy.context.scene
    sky = build_sky(scene)
    build_ground(h)
    build_facades(h)
    props, bsize = place_props(h)
    lean_broom(props[-1], bsize, h)
    return sky


def ball_finish(mat, key):
    """Soccer: PU skin with a thin glossy film. Basketball: pebbled composite leather."""
    if not mat or not mat.use_nodes: return
    n, l = mat.node_tree.nodes, mat.node_tree.links
    for shader in [x for x in n if x.type == 'BSDF_PRINCIPLED']:
        for name, value in [('Metallic', 0.), ('Roughness', .5 if key == 'soccer' else .62), ('Emission Strength', 0.)]:
            for link in list(shader.inputs[name].links): l.remove(link)
            shader.inputs[name].default_value = value
        if key == 'soccer':
            shader.inputs['Coat Weight'].default_value = .3
            shader.inputs['Coat Roughness'].default_value = .22
            shader.inputs['Coat IOR'].default_value = 1.5
        else:
            coord = n.new('ShaderNodeTexCoord')
            pebbles = n.new('ShaderNodeTexVoronoi'); pebbles.feature = 'SMOOTH_F1'
            pebbles.inputs['Scale'].default_value = 420.
            l.new(coord.outputs['Object'], pebbles.inputs['Vector'])
            bump = n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = .35
            bump.inputs['Distance'].default_value = .0004; bump.invert = True
            l.new(pebbles.outputs['Distance'], bump.inputs['Height'])
            old = shader.inputs['Normal'].links[0].from_socket if shader.inputs['Normal'].is_linked else None
            if old is not None: l.new(old, bump.inputs['Normal'])
            l.new(bump.outputs['Normal'], shader.inputs['Normal'])
            shader.inputs['Specular IOR Level'].default_value = .45


def make_ball(path, key, radius):
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=str(path))
    imported = set(bpy.data.objects) - before
    bpy.context.view_layer.update(); deps = bpy.context.evaluated_depsgraph_get(); parts = []
    for o in imported:
        if o.type != 'MESH': continue
        mesh = bpy.data.meshes.new_from_object(o.evaluated_get(deps), depsgraph=deps)
        mesh.transform(o.matrix_world)
        obj = bpy.data.objects.new(key, mesh); bpy.context.collection.objects.link(obj); parts.append(obj)
    for o in imported: bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts: o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1: bpy.ops.object.join()
    o = bpy.context.object
    lo = Vector(tuple(min(v.co[i] for v in o.data.vertices) for i in range(3)))
    hi = Vector(tuple(max(v.co[i] for v in o.data.vertices) for i in range(3)))
    c = (lo + hi) / 2
    outer = max((v.co - c).length for v in o.data.vertices)
    for v in o.data.vertices: v.co = (v.co - c) * (radius / outer)
    o.data.update(); o.name = key
    for f in o.data.polygons: f.use_smooth = True
    for m in o.data.materials: ball_finish(m, key)
    # Fixed mesh-space orientation, independent of physical centre and quaternion.
    o.data.transform(Matrix.Rotation(.36 if key == 'soccer' else .55, 4, 'X') @ Matrix.Rotation(.38, 4, 'Z'))
    o['pcve_role'] = 'ball'
    return o


def check_props(scene, cam, balls, radii, frames):
    """Raise if any prop comes within PROP_CLEARANCE_M of a ball or hides a ball centre."""
    from mathutils.bvhtree import BVHTree
    deps = bpy.context.evaluated_depsgraph_get()
    props = [o for o in scene.objects if o.type == 'MESH' and o.get('pcve_role') == 'prop']
    trees = []
    for o in props:
        ev = o.evaluated_get(deps); mesh = ev.to_mesh()
        verts = [o.matrix_world @ v.co for v in mesh.vertices]
        trees.append((o.name, BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in mesh.polygons])))
        ev.to_mesh_clear()
    worst = (math.inf, None)
    for row in frames:
        for key, ball in balls.items():
            centre = Vector(row[key]['location'])
            for name, tree in trees:
                hit = tree.find_nearest(centre)
                if hit[0] is None: continue
                gap = hit[3] - radii[key]
                if gap < worst[0]: worst = (gap, f'{name} / {key} frame {row["frame_index"]}')
                if gap < PROP_CLEARANCE_M:
                    raise RuntimeError(f'Prop {name} is {gap * 1000:.1f} mm from {key} at frame {row["frame_index"]}')
            direction = centre - cam.location
            for name, tree in trees:
                hit = tree.ray_cast(cam.location, direction.normalized(), direction.length)
                if hit[0] is not None:
                    raise RuntimeError(f'Prop {name} hides the {key} centre at frame {row["frame_index"]}')
    print(f'[props] {len(props)} props; nearest prop-ball gap {worst[0] * 1000:.0f} mm ({worst[1]})', flush=True)
    return worst[0]
