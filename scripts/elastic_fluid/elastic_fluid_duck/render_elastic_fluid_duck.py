"""Render and verify PCVE elastic-duck cases with the hotel-pool look.

Render (inside Blender):   blender -b --python render_elastic_fluid_duck.py -- --case-dir <case> [--out-dir <dir>] [--frames ...]
Sun occluders (Blender):   blender -b --python render_elastic_fluid_duck.py -- --case-dir <case> --occluders
Verify an existing video:  python render_elastic_fluid_duck.py --case-dir <case> --verify-only [--evidence-manifest <suite_manifest.json>]

The frozen scene.blend (checked against asset_manifest.json on load) is rendered with one look,
LOOK: the scene's sun lamp under a physical clear sky; sunlight on the pool floor and walls
(caustics, shadows) traced through the simulated water by caustics_elastic_fluid_duck.py; the
anisotropic water surface with spray, mist and foam of splash_elastic_fluid_duck.py; wet pool walls and
duck from wetness_elastic_fluid_duck.py; clear water with depth absorption; square pool mosaic;
velocity motion blur; depth of field, mild lens effects and light film grain in the video. Without
water the sun lights the empty pool directly; without the duck it is left out.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import optics_elastic_fluid_duck as optics

LOOK = 'hotel_pool_clear_sky_traced_caustics'
# The frozen scene lights everything from an HDRI shot under a covered veranda (roof overhead, sky only
# as an overexposed band at the horizon) and keeps its sun lamp disabled; that environment gives
# 10.3 W/m2 on a horizontal surface.
SUN_STRENGTH = 37.        # direct sun 3x that irradiance on a horizontal surface (sun at 57 deg)
SUN_ANGLE_DEGREES = .6
SUN_COLOR = (1., .95, .88)
REAL_EXPOSURE = -2.65     # with VIEW_LOOK: sunlit stone as bright as in the frozen look at -1.35
VIEW_LOOK = 'AgX - Base Contrast'                   # the frozen 'Medium High Contrast' crushes the shade
REAL_SAMPLES, REAL_NOISE_THRESHOLD = 256, .005      # frozen 128, .01: denoiser blotches in the darker shade
# Physical clear sky (Nishita) instead of the veranda HDRI, aligned with the sun lamp, its own sun disc
# off. With a light summer haze (dust 4) Nishita's sun gives 115 W/m2 normal to it and its sky 16 W/m2
# on a horizontal surface (measured); scaled to the 37 W/m2 lamp the sky would give 5 W/m2. 3x that
# stands in for the light the courtyard's missing surroundings would bounce into the shade.
SKY_DUST = 4.
SKY_STRENGTH = 3.*SUN_STRENGTH/115.
PAVING_SATURATION = .6    # the frozen look's .78 reads pink in sunlight
# Wet look (wetness_elastic_fluid_duck.py says where): the mosaic darkens (its grout most) and deepens in
# colour, the vinyl duck darkens little; both get smoother under a clear coat of water.
WET_TILE = {'darken': .25, 'saturate': .2, 'roughness': .08, 'coat': .9, 'coat_roughness': .03}
WET_DUCK = {'darken': .1, 'saturate': 0., 'roughness_scale': .4, 'coat': 1., 'coat_roughness': .02}
FOCUS_DISTANCE, FSTOP = 7., 5.6           # camera to duck is 7.0 m
POOL_SHELL = ('PoolFloor', 'PoolBack', 'PoolFront', 'PoolLeft', 'PoolRight')
SHELL_OVERLAP = .05       # water mesh pushed this far into the pool shell, so the shell sits inside the water
FILM_GRAIN = 'format=yuv420p,noise=c0s=3:c0f=t+u'  # ffmpeg filter: light luma grain, new every frame
WATER_NAMES = ('LiquidDomain', 'InitialLiquid', 'StaticWaterPreview', 'SPHWater')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf8')
    temporary.replace(path)


def import_blender():
    global bpy, np, Matrix, Vector
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector


def capture_appearance():
    return {'lighting':lighting(), 'render':render_settings(),
            'static_geometry_sha256':static_signature(), 'materials':material_records()}


def load_specification(case):
    spec = json.loads((case/'mpm_sph_experiment.json').read_text())
    assets = Path(spec['runtime_assets']['path'])
    path = assets/'asset_manifest.json'
    assert digest(path) == spec['runtime_assets']['manifest_sha256']
    manifest = json.loads(path.read_text())
    assert digest(assets/'scene.blend') == manifest['files']['scene.blend']['sha256']
    return spec, assets, manifest


def set_velocity(mesh, velocity):
    """Per-vertex velocity in m/s; Cycles uses it for motion blur, also when topology changes per frame."""
    attribute = mesh.attributes.get('velocity') or mesh.attributes.new('velocity','FLOAT_VECTOR','POINT')
    attribute.data.foreach_set('vector', np.ascontiguousarray(velocity, dtype=np.float32).ravel())


def aniso_material():
    """WaterAniso: the clear Water BSDF, blended to the clear spray BSDF by the 'spray' vertex weight."""
    source = next(n for n in bpy.data.materials['Water'].node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
    material = bpy.data.materials.new('WaterAniso')
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    deep = nodes['Principled BSDF']
    deep.distribution, deep.subsurface_method = source.distribution, source.subsurface_method
    for target, socket in zip(deep.inputs, source.inputs):
        if hasattr(socket, 'default_value'):
            target.default_value = socket.default_value
    clear = nodes.new('ShaderNodeBsdfPrincipled')
    for name, value in (('Base Color',(1.,1.,1.,1.)), ('Transmission Weight',1.), ('Roughness',.02), ('IOR',1.333)):
        clear.inputs[name].default_value = value
    weight = nodes.new('ShaderNodeAttribute')
    weight.attribute_name = 'spray'
    mix = nodes.new('ShaderNodeMixShader')
    links.new(weight.outputs['Fac'], mix.inputs['Fac'])
    links.new(deep.outputs['BSDF'], mix.inputs[1])
    links.new(clear.outputs['BSDF'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return material


def particle_material(name, base, transmission, roughness, opacity=None):
    """Principled material for secondary particles; opacity scales the per-point 'fade' attribute."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes['Principled BSDF']
    for socket, value in (('Base Color',(*base, 1.)), ('Transmission Weight',transmission),
                          ('Roughness',roughness), ('IOR',1.333)):
        bsdf.inputs[socket].default_value = value
    if opacity is not None:
        fade = nodes.new('ShaderNodeAttribute')
        fade.attribute_name = 'fade'
        scale = nodes.new('ShaderNodeMath')
        scale.operation = 'MULTIPLY'
        scale.inputs[1].default_value = opacity
        links.new(fade.outputs['Fac'], scale.inputs[0])
        links.new(scale.outputs['Value'], bsdf.inputs['Alpha'])
    return material


def points_object(name, material):
    """A vertex-only mesh that geometry nodes turn into Cycles points (radius attribute) with this material."""
    group = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    group.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = group.nodes, group.links
    source, target = nodes.new('NodeGroupInput'), nodes.new('NodeGroupOutput')
    points = nodes.new('GeometryNodeMeshToPoints')
    radius = nodes.new('GeometryNodeInputNamedAttribute')
    radius.data_type = 'FLOAT'
    radius.inputs['Name'].default_value = 'radius'
    assign = nodes.new('GeometryNodeSetMaterial')
    assign.inputs['Material'].default_value = material
    links.new(source.outputs[0], points.inputs['Mesh'])
    links.new(radius.outputs['Attribute'], points.inputs['Radius'])
    links.new(points.outputs['Points'], assign.inputs['Geometry'])
    links.new(assign.outputs['Geometry'], target.inputs[0])
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    obj.modifiers.new('Points', 'NODES').node_group = group
    return obj


def particle_objects():
    """Clear spray droplets that sparkle in the sun, fine whitish mist and surface foam; name -> object."""
    return {'spray': points_object('SPHSpray', particle_material('SprayDrops', (1., 1., 1.), 1., .02)),
            'mist': points_object('SPHMist', particle_material('SprayMist', (1., 1., 1.), .3, .4, opacity=.7)),
            'foam': points_object('SPHFoam', particle_material('SurfaceFoam', (.85, .88, .9), .2, .5, opacity=.6))}


def add_absorption(material):
    """Colour from depth: Volume Absorption inside the closed water mesh."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    absorption = nodes.new('ShaderNodeVolumeAbsorption')
    absorption.inputs['Color'].default_value = (*optics.WATER_ABSORPTION[0], 1.)
    absorption.inputs['Density'].default_value = optics.WATER_ABSORPTION[1]
    output = next(n for n in nodes if n.bl_idname == 'ShaderNodeOutputMaterial')
    links.new(absorption.outputs['Volume'], output.inputs['Volume'])


def shadow_transparent(material):
    """Let shadow rays pass the water surface, so the sun lights the duck under water (still attenuated
    by the volume absorption) instead of leaving it in the surface's shadow."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    output = next(n for n in nodes if n.bl_idname == 'ShaderNodeOutputMaterial')
    surface = output.inputs['Surface'].links[0].from_socket
    path = nodes.new('ShaderNodeLightPath')
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Shadow Ray'], mix.inputs['Fac'])
    links.new(surface, mix.inputs[1])
    links.new(transparent.outputs['BSDF'], mix.inputs[2])
    links.new(mix.outputs['Shader'], output.inputs['Surface'])


def ripple_normal(material):
    """The optional ripples of optics_elastic_fluid_duck.py on the water's shading normal, n + n_z * tilt
    (caustics_elastic_fluid_duck.py refracts the sunlight through the same ripples). The 'RippleTime'
    value node holds the frame's time."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    clock = nodes.new('ShaderNodeValue')
    clock.name = 'RippleTime'
    if not optics.ripple_terms():
        return
    geometry = nodes.new('ShaderNodeNewGeometry')
    position, normal = nodes.new('ShaderNodeSeparateXYZ'), nodes.new('ShaderNodeSeparateXYZ')
    links.new(geometry.outputs['Position'], position.inputs['Vector'])
    links.new(geometry.outputs['Normal'], normal.inputs['Vector'])

    def operation(name, *inputs):
        node = nodes.new('ShaderNodeMath')
        node.operation = name
        for socket, value in zip(node.inputs, inputs):
            if isinstance(value, float):
                socket.default_value = value
            else:
                links.new(value, socket)
        return node.outputs['Value']

    tilt = [None, None]
    for kx, ky, omega, phase, coefficients in optics.ripple_terms():
        shift = operation('MULTIPLY_ADD', clock.outputs['Value'], -omega, phase)
        wave = operation('COSINE', operation('MULTIPLY_ADD', position.outputs['X'], kx,
                                             operation('MULTIPLY_ADD', position.outputs['Y'], ky, shift)))
        for axis, coefficient in enumerate(coefficients):
            term = operation('MULTIPLY', wave, coefficient)
            tilt[axis] = term if tilt[axis] is None else operation('ADD', tilt[axis], term)
    combine = nodes.new('ShaderNodeCombineXYZ')
    links.new(tilt[0], combine.inputs['X'])
    links.new(tilt[1], combine.inputs['Y'])
    scale, add, unit = (nodes.new('ShaderNodeVectorMath') for _ in range(3))
    scale.operation, add.operation, unit.operation = 'SCALE', 'ADD', 'NORMALIZE'
    links.new(combine.outputs['Vector'], scale.inputs[0])
    links.new(normal.outputs['Z'], scale.inputs['Scale'])
    links.new(geometry.outputs['Normal'], add.inputs[0])
    links.new(scale.outputs['Vector'], add.inputs[1])
    links.new(add.outputs['Vector'], unit.inputs[0])
    for bsdf in [n for n in nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled']:
        links.new(unit.outputs['Vector'], bsdf.inputs['Normal'])


def wet_layer(material, wet, colour, darken, saturate, coat, coat_roughness, roughness=None, roughness_scale=None):
    """Blend the material's Principled BSDF towards wet by the wetness socket: darker, more saturated
    colour, smoother (a wet roughness value, or the roughness map scaled), under a clear coat of water.
    Returns the wet colour for other users of the colour."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = next(n for n in nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')

    def operation(name, *inputs):
        node = nodes.new('ShaderNodeMath')
        node.operation = name
        for socket, value in zip(node.inputs, inputs):
            if isinstance(value, float):
                socket.default_value = value
            else:
                links.new(value, socket)
        return node.outputs['Value']

    deeper = nodes.new('ShaderNodeHueSaturation')
    links.new(colour, deeper.inputs['Color'])
    links.new(operation('MULTIPLY_ADD', wet, saturate, 1.), deeper.inputs['Saturation'])
    darker = nodes.new('ShaderNodeVectorMath')
    darker.operation = 'SCALE'
    links.new(deeper.outputs['Color'], darker.inputs[0])
    links.new(operation('MULTIPLY_ADD', wet, -darken, 1.), darker.inputs['Scale'])
    links.new(darker.outputs['Vector'], bsdf.inputs['Base Color'])
    surface = bsdf.inputs['Roughness']
    if surface.is_linked:
        links.new(operation('MULTIPLY', surface.links[0].from_socket, operation('MULTIPLY_ADD', wet, roughness_scale-1., 1.)), surface)
    else:
        links.new(operation('MULTIPLY_ADD', wet, roughness-surface.default_value, surface.default_value), surface)
    for socket, value in (('Coat Weight', coat), ('Coat Roughness', coat_roughness)):
        dry = bsdf.inputs[socket].default_value
        links.new(operation('MULTIPLY_ADD', wet, value-dry, dry), bsdf.inputs[socket])
    return darker.outputs['Vector']


def wet_duck():
    """The duck's material blended towards wet by the 'wet' vertex attribute that load_wetness sets."""
    duck = bpy.data.objects['duck_visual']
    material = duck.material_slots[0].material.copy()
    material.name = 'Duck wet'
    slot = duck.material_slots[0]
    slot.link = 'OBJECT'
    slot.material = material
    bsdf = next(n for n in material.node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
    wet = material.node_tree.nodes.new('ShaderNodeAttribute')
    wet.attribute_name = 'wet'
    wet_layer(material, wet.outputs['Fac'], bsdf.inputs['Base Color'].links[0].from_socket, **WET_DUCK)
    duck.data.attributes.new('wet', 'FLOAT', 'POINT')


def sunlit_shell(shell):
    """Sunlight on the pool floor and walls from caustics_elastic_fluid_duck.py instead of the sun lamp:
    the lamp leaves the shell out (light linking), and each shell object gets its own tile material that
    emits the tile colour times the frame's sun irradiance texture over pi, as a diffuse surface lit by
    that sun would. The walls also get the wet band of wetness_elastic_fluid_duck.py."""
    sun = bpy.data.objects['Afternoon Sun']
    excluded = bpy.data.collections.new('NoDirectSun')
    for name in POOL_SHELL:
        excluded.objects.link(bpy.data.objects[name])
    for item in excluded.collection_objects:
        item.light_linking.link_state = 'EXCLUDE'
    sun.light_linking.receiver_collection = excluded
    layout = optics.shell_textures(*shell)
    for name in POOL_SHELL:
        material = bpy.data.materials['Pool blue mosaic'].copy()
        material.name = f'Pool blue mosaic {name}'
        material.cycles.emission_sampling = 'NONE'  # sunlit tiles, not a lamp: other surfaces see them through bounces
        slot = bpy.data.objects[name].material_slots[0]
        slot.link = 'OBJECT'
        slot.material = material
        nodes, links = material.node_tree.nodes, material.node_tree.links
        bsdf = next(n for n in nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
        tile = bsdf.inputs['Base Color'].links[0].from_socket
        u, v, (u0, _), (v0, _), (rows, cols) = layout[name]
        image = bpy.data.images.new(f'Sunlight {name}', cols, rows, alpha=False, float_buffer=True)
        image.colorspace_settings.name = 'Non-Color'
        uv = nodes.new('ShaderNodeUVMap')
        uv.uv_map = 'TileUV'
        place = nodes.new('ShaderNodeMapping')
        width, height = cols*optics.SHELL_PIXEL, rows*optics.SHELL_PIXEL
        place.inputs['Location'].default_value = (-u0/width, -v0/height, 0.)
        place.inputs['Scale'].default_value = (1/width, 1/height, 1.)
        texture = nodes.new('ShaderNodeTexImage')
        texture.image, texture.extension, texture.interpolation = image, 'CLIP', 'Linear'
        lit, sunlit, facing = (nodes.new('ShaderNodeVectorMath') for _ in range(3))
        lit.operation, sunlit.operation, facing.operation = 'MULTIPLY', 'MULTIPLY', 'DOT_PRODUCT'
        sunlit.inputs[1].default_value = [SUN_STRENGTH*c/math.pi for c in SUN_COLOR]
        facing.inputs[1].default_value = optics.SHELL_INWARD[name]
        geometry = nodes.new('ShaderNodeNewGeometry')
        inner = nodes.new('ShaderNodeMath')
        inner.operation = 'GREATER_THAN'
        inner.inputs[1].default_value = .5
        links.new(uv.outputs['UV'], place.inputs['Vector'])
        links.new(place.outputs['Vector'], texture.inputs['Vector'])
        if name != 'PoolFloor':  # walls: wet tiles above the water line, grey texture R = G = B
            wet = bpy.data.images.new(f'Wet {name}', cols, rows, alpha=False, float_buffer=True)
            wet.colorspace_settings.name = 'Non-Color'
            band = nodes.new('ShaderNodeTexImage')
            band.image, band.extension, band.interpolation = wet, 'CLIP', 'Linear'
            links.new(place.outputs['Vector'], band.inputs['Vector'])
            tile = wet_layer(material, band.outputs['Color'], tile, **WET_TILE)
        links.new(tile, lit.inputs[0])
        links.new(texture.outputs['Color'], lit.inputs[1])
        links.new(lit.outputs['Vector'], sunlit.inputs[0])
        links.new(sunlit.outputs['Vector'], bsdf.inputs['Emission Color'])
        links.new(geometry.outputs['True Normal'], facing.inputs[0])
        links.new(facing.outputs['Value'], inner.inputs[0])
        links.new(inner.outputs['Value'], bsdf.inputs['Emission Strength'])  # inner faces only


def load_sunlight(case, frame, fps):
    """Frame's sun irradiance on the pool shell (caustics_elastic_fluid_duck.py) and the ripples' time."""
    with np.load(case/'runs/source/aniso'/f'caustics_{frame:04d}.npz') as data:
        for name in POOL_SHELL:
            image = bpy.data.images[f'Sunlight {name}']
            rgb = data[name]
            assert rgb.shape == (image.size[1], image.size[0], 3) and np.isfinite(rgb).all()
            rgba = np.concatenate([rgb, np.ones((*rgb.shape[:2], 1), rgb.dtype)], axis=-1)
            image.pixels.foreach_set(np.ascontiguousarray(rgba, dtype=np.float32).ravel())
            image.update()
    bpy.data.materials['WaterAniso'].node_tree.nodes['RippleTime'].outputs['Value'].default_value = (frame-1)/fps


def load_wetness(case, frame, visual):
    """Frame's wet band on the pool walls and wet duck vertices (wetness_elastic_fluid_duck.py)."""
    with np.load(case/'runs/source/aniso'/f'wet_{frame:04d}.npz') as data:
        for name in POOL_SHELL[1:]:
            image = bpy.data.images[f'Wet {name}']
            grey = data[name]
            assert grey.shape == (image.size[1], image.size[0]) and np.isfinite(grey).all()
            rgba = np.repeat(grey[..., None], 4, axis=-1)
            rgba[..., 3] = 1.
            image.pixels.foreach_set(np.ascontiguousarray(rgba, dtype=np.float32).ravel())
            image.update()
        wet = data['duck']
    if visual is not None:
        assert wet.shape == (len(visual.data.vertices),)
        visual.data.attributes['wet'].data.foreach_set('value', np.ascontiguousarray(wet, dtype=np.float32))
        visual.data.update()


def export_occluders(case):
    """Sun occluders for caustics_elastic_fluid_duck.py: the duck's triangles (indices into
    visual_deformation.npz) and the other objects inside the pool (the ladder) as world-space triangles."""
    import_blender()
    spec, assets, manifest = load_specification(case)
    bpy.ops.wm.open_mainfile(filepath=str(assets/'scene.blend'))
    assert capture_appearance() == manifest['packed_appearance'], 'Frozen appearance changed.'
    lower = np.asarray(spec['simulation_quality']['sph_lower_bound_m'])
    upper = np.asarray(spec['simulation_quality']['sph_upper_bound_m'])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    triangles, owners, names = [], [], []
    for obj in sorted(bpy.context.scene.objects, key=lambda o: o.name):
        if obj.type != 'MESH' or obj.hide_render or obj.name in POOL_SHELL or obj.name.startswith(('ball', 'Duck', 'duck_')) \
                or obj.name in WATER_NAMES:
            continue
        corners = np.array([obj.matrix_world @ Vector(c) for c in obj.bound_box])
        if (corners.max(axis=0)[:2] <= lower[:2]).any() or (corners.min(axis=0)[:2] >= upper[:2]).any():
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        points = np.array([evaluated.matrix_world @ vertex.co for vertex in mesh.vertices])
        faces = np.array([triangle.vertices[:] for triangle in mesh.loop_triangles])
        triangles.append(points[faces])
        owners.append(np.full(len(faces), len(names)))
        names.append(obj.name)
        evaluated.to_mesh_clear()
    duck = bpy.data.objects['duck_visual'].data
    duck.calc_loop_triangles()
    duck_triangles = np.array([triangle.vertices[:] for triangle in duck.loop_triangles], np.int32)
    if spec['physics'].get('duck_presence', [1]) == [1]:
        assert len(duck.vertices) == len(np.load(case/'runs/source/visual_deformation.npz')['positions'][0])
    path = case/'runs/source/aniso/occluders.npz'
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, static_triangles=np.concatenate(triangles) if triangles else np.zeros((0, 3, 3)),
                        static_owner=np.concatenate(owners) if owners else np.zeros(0, int), static_names=np.array(names),
                        duck_triangles=duck_triangles)
    print('OCCLUDERS', path, names, 'duck triangles', len(duck_triangles), flush=True)


def tile_uv(obj):
    """World-metre UVs projected along each face's dominant axis (the tiles used world X/Y on every face,
    so the pool walls showed long vertical stripes instead of square mosaic)."""
    mesh = obj.data
    layer = mesh.uv_layers.get('TileUV') or mesh.uv_layers.new(name='TileUV')
    rotation = obj.matrix_world.to_3x3()
    for polygon in mesh.polygons:
        normal = rotation @ polygon.normal
        axis = max(range(3), key=lambda k: abs(normal[k]))
        keep = [k for k in range(3) if k != axis]
        for loop in polygon.loop_indices:
            point = obj.matrix_world @ mesh.vertices[mesh.loops[loop].vertex_index].co
            layer.data[loop].uv = (point[keep[0]], point[keep[1]])


def lens_effects(scene):
    """Mild camera optics in the compositor: highlight glow, lateral colour fringing and a vignette."""
    scene.use_nodes = True
    tree = scene.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    layers = tree.nodes.new('CompositorNodeRLayers')
    glare = tree.nodes.new('CompositorNodeGlare')
    glare.glare_type, glare.quality, glare.mix, glare.size = 'FOG_GLOW', 'HIGH', -.85, 7
    glare.threshold = 1.5*2**(-REAL_EXPOSURE)  # only highlights brighter than 1.5 after exposure glow
    lens = tree.nodes.new('CompositorNodeLensdist')
    lens.inputs['Dispersion'].default_value = .006
    mask = tree.nodes.new('CompositorNodeEllipseMask')
    mask.width = mask.height = 1.15
    blur = tree.nodes.new('CompositorNodeBlur')
    blur.use_relative, blur.factor_x, blur.factor_y = True, 30., 30.
    vignette = tree.nodes.new('CompositorNodeMapRange')
    vignette.inputs['To Min'].default_value = .8
    mix = tree.nodes.new('CompositorNodeMixRGB')
    mix.blend_type = 'MULTIPLY'
    composite = tree.nodes.new('CompositorNodeComposite')
    links = tree.links
    links.new(layers.outputs['Image'], glare.inputs['Image'])
    links.new(glare.outputs['Image'], lens.inputs['Image'])
    links.new(mask.outputs['Mask'], blur.inputs['Image'])
    links.new(blur.outputs['Image'], vignette.inputs['Value'])
    links.new(lens.outputs['Image'], mix.inputs[1])
    links.new(vignette.outputs['Value'], mix.inputs[2])
    links.new(mix.outputs['Image'], composite.inputs['Image'])


def clear_sky(scene):
    """Physical clear sky aligned with the sun lamp in place of the frozen veranda environment, whose
    overexposed horizon band showed in the pool as white blobs and whose roof let the sky light in only
    from the sides, so shade looked flat and grey."""
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    sky = next(n for n in nodes if n.bl_idname == 'ShaderNodeTexSky')
    to_sun = Vector(optics.SUN_TO).normalized()
    sky.sky_type, sky.sun_disc = 'NISHITA', False
    sky.sun_elevation = math.asin(to_sun.z)
    sky.sun_rotation = math.atan2(to_sun.x, to_sun.y) % (2*math.pi)  # Nishita: to-sun = (cos e sin r, cos e cos r, sin e)
    sky.altitude, sky.air_density, sky.dust_density, sky.ozone_density = 0., 1., SKY_DUST, 1.
    background = next(n for n in nodes if n.bl_idname == 'ShaderNodeBackground')
    background.inputs['Strength'].default_value = SKY_STRENGTH
    links.new(sky.outputs['Color'], background.inputs['Color'])


def apply_look(scene, shell, water, duck):
    """LOOK on the frozen scene; water and duck say whether they are in the case. Returns the
    water material and the spray, mist and foam objects (none without water)."""
    sun = bpy.data.objects['Afternoon Sun']
    assert (sun.matrix_world.to_3x3() @ Vector((0., 0., 1.))).normalized().dot(Vector(optics.SUN_TO).normalized()) > .99999
    sun.hide_render = False
    sun.data.energy, sun.data.angle, sun.data.color = SUN_STRENGTH, math.radians(SUN_ANGLE_DEGREES), SUN_COLOR
    clear_sky(scene)
    scene.view_settings.exposure, scene.view_settings.look = REAL_EXPOSURE, VIEW_LOOK
    scene.cycles.samples, scene.cycles.adaptive_threshold = REAL_SAMPLES, REAL_NOISE_THRESHOLD
    scene.render.use_motion_blur, scene.render.motion_blur_shutter = True, .5
    scene.render.use_persistent_data = False  # the shell's sunlight textures change every frame
    paving = bpy.data.materials['Poly Haven patio tiles'].node_tree.nodes['PreservePreviousPatioColourTreatment']
    paving.inputs['Saturation'].default_value = PAVING_SATURATION
    tiles = bpy.data.materials['Pool blue mosaic'].node_tree
    uv = tiles.nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'TileUV'
    tiles.links.new(uv.outputs['UV'], next(n for n in tiles.nodes if n.bl_idname == 'ShaderNodeTexBrick').inputs['Vector'])
    for name in POOL_SHELL:
        tile_uv(bpy.data.objects[name])
    camera = scene.camera.data
    camera.dof.use_dof, camera.dof.focus_distance, camera.dof.aperture_fstop = True, FOCUS_DISTANCE, FSTOP
    lens_effects(scene)
    if not water:
        return None, {}
    bsdf = next(n for n in bpy.data.materials['Water'].node_tree.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
    for name, value in (('Base Color',(1.,1.,1.,1.)), ('Transmission Weight',1.), ('Roughness',.02)):
        bsdf.inputs[name].default_value = value
    sunlit_shell(shell)
    if duck:
        wet_duck()
    material = aniso_material()
    particles = particle_objects()
    add_absorption(material)
    shadow_transparent(material)
    ripple_normal(material)
    return material, particles


def load_water(case, frame, shell):
    """Frame's anisotropic water surface (splash_elastic_fluid_duck.py), pushed 5 cm into the pool shell at
    its contact so the tiles sit inside the absorbing water."""
    with np.load(case/'runs/source/aniso'/f'water_{frame:04d}.npz') as data:
        vertices, triangles, normals = data['vertices'], data['triangles'], data['normals']
        velocity, spray = data['velocity'], data['spray']
    assert np.isfinite(vertices).all() and normals.shape == vertices.shape and np.isfinite(normals).all()
    lower, upper = shell
    vertices = vertices.copy()
    for axis in range(3):
        vertices[vertices[:, axis] < lower[axis]+.03, axis] -= SHELL_OVERLAP
        if axis < 2:
            vertices[vertices[:, axis] > upper[axis]-.03, axis] += SHELL_OVERLAP
    mesh = bpy.data.meshes.new(f'SPHWaterFrame{frame:04d}')
    mesh.vertices.add(len(vertices))
    mesh.vertices.foreach_set('co', vertices.ravel())
    mesh.loops.add(triangles.size)
    mesh.loops.foreach_set('vertex_index', triangles.ravel())
    mesh.polygons.add(len(triangles))
    mesh.polygons.foreach_set('loop_start', np.arange(0, triangles.size, 3, dtype=np.int32))
    mesh.polygons.foreach_set('loop_total', np.full(len(triangles), 3, dtype=np.int32))
    mesh.polygons.foreach_set('use_smooth', np.ones(len(triangles), dtype=np.bool_))
    mesh.update(calc_edges=True)
    mesh.normals_split_custom_set_from_vertices(normals.tolist())
    set_velocity(mesh, velocity)
    mesh.attributes.new('spray', 'FLOAT', 'POINT').data.foreach_set('value', spray)
    water = bpy.data.objects.get('SPHWater')
    if water is None:
        water = bpy.data.objects.new('SPHWater', mesh)
        bpy.context.scene.collection.objects.link(water)
    else:
        old = water.data
        water.data = mesh
        if old.users == 0:
            bpy.data.meshes.remove(old)
    mesh.materials.append(bpy.data.materials['WaterAniso'])
    water.matrix_world = Matrix.Identity(4)


def load_particles(case, frame, kind, obj):
    """Frame's spray, mist or foam points (position, radius, velocity and fade) onto their points object."""
    with np.load(case/'runs/source/aniso'/f'{kind}_{frame:04d}.npz') as data:
        position, radius, velocity = data['position'], data['radius'], data['velocity']
        fade = data['fade'] if 'fade' in data else np.ones(len(radius), np.float32)
    mesh = bpy.data.meshes.new(f'{obj.name}{frame:04d}')
    mesh.vertices.add(len(position))
    mesh.vertices.foreach_set('co', np.ascontiguousarray(position, dtype=np.float32).ravel())
    mesh.attributes.new('radius','FLOAT','POINT').data.foreach_set('value', np.ascontiguousarray(radius, dtype=np.float32))
    mesh.attributes.new('fade','FLOAT','POINT').data.foreach_set('value', np.ascontiguousarray(fade, dtype=np.float32))
    set_velocity(mesh, velocity)
    mesh.update()
    old = obj.data
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def look_inputs(case):
    """Settings of the per-case look inputs a render depends on (none without water)."""
    aniso = case/'runs/source/aniso'
    return {name: json.loads((aniso/report).read_text())['settings'] for name, report in
            (('splash', 'report.json'), ('caustics', 'caustics_report.json'), ('wetness', 'wet_report.json'))
            if (aniso/report).exists()}


def verify_video(case, out, evidence_manifest=None):
    spec, assets, manifest = load_specification(case)
    video = out/'video.mp4'
    if (out/'render_report.json').exists():
        rendering = json.loads((out/'render_report.json').read_text())
        assert rendering['status'] == 'all_96_frames_complete'
        assert rendering['look'] == LOOK and rendering['appearance_unchanged']
        assert rendering['simulation_report_sha256'] == digest(case/'runs/source/simulation_report.json')
        for frame,record in rendering['frames'].items():
            assert digest(out/'frames'/f'frame_{int(frame):04d}.png') == record['sha256']
        render_seconds = rendering['render_seconds']
        origin = 'rendered_from_actual_case_particles'
    elif not spec['counterfactual']['changes'] and (out/'selected_base_provenance.json').exists():
        provenance = json.loads((out/'selected_base_provenance.json').read_text())
        assert digest(video) == provenance['video_sha256'] == manifest['selected_base_video_sha256']
        assert provenance['base_video_recomputed'] is False
        assert provenance['raw_physics_reaudit_available'] is False
        assert provenance['original_simulation_report_sha256'] == manifest['selected_base_simulation_sha256']
        assert manifest['selected_base_look'] == LOOK
        render_seconds = None
        origin = 'exact_user_selected_base_video_imported_without_raw_cache'
    else:
        assert evidence_manifest is not None, 'No render report, base provenance or retained evidence for this video.'
        suite = json.loads(Path(evidence_manifest).read_text())
        retained = suite['retained_case_evidence'][spec['counterfactual']['id']]
        assert retained['configuration'] == spec, 'Retained clip configuration differs from the requested case.'
        original = retained['technical_verification']
        assert digest(video) == original['video_sha256']
        assert original['all_96_frames_decoded'] and original['look'] == LOOK
        render_seconds = original['render_seconds']
        origin = 'retained_video_identity_checked_no_raw_physics_reaudit'
    data = json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-count_frames','-show_entries','stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration',
        '-of','json',str(video)],text=True))
    stream = data['streams'][0]
    assert (stream['width'],stream['height']) == (1280,720)
    assert stream['r_frame_rate'] == stream['avg_frame_rate'] == '24/1'
    assert int(stream['nb_read_frames']) == 96 and abs(float(data['format']['duration'])-4)<.001
    subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
    result = {'status':'complete_video_technical_checks_passed_visual_review_pending',
        'case_id':spec['counterfactual']['id'], 'video_sha256':digest(video),
        'video':data, 'origin':origin, 'all_96_frames_decoded':True,
        'look':LOOK, 'samples':REAL_SAMPLES, 'render_seconds':render_seconds,
        'physics_changes':spec['counterfactual']['changes'],
        'raw_physics_reaudit_available':(case/'runs/source/simulation_report.json').exists(),
        'simulation_recomputed_for_this_video':origin == 'rendered_from_actual_case_particles',
        'water_deleted_from_simulation_and_render':spec['physics'].get('water_presence',[1]) == [0],
        'accepted_as_calibrated_ground_truth':False}
    save(out/'video_verification.json',result)
    print('VIDEO_VERIFIED',spec['counterfactual']['id'],result['video_sha256'],flush=True)


def render_case(case, out, selected=None, samples=REAL_SAMPLES):
    import_blender()
    spec, assets, manifest = load_specification(case)
    assert samples == REAL_SAMPLES
    validation = json.loads((case/'benchmark_validation.json').read_text())
    water_presence = spec['physics'].get('water_presence',[1])
    assert water_presence in ([0],[1])
    water_deleted = water_presence == [0]
    assert validation['all_96_frames_checked']
    if water_deleted:
        assert validation['water_deleted_from_simulation'] and validation['no_hidden_water_or_pressure_boundary']
        assert validation['pressure_solver_present'] is False and validation['pressure_converged'] is None
        assert spec['counterfactual']['deleted_objects'] == ['water']
        assert validation['empty_pool_skinned_surface_checked']
        if 'numerical_repair' in spec:
            assert validation['material_continuity_checked_all_frames']
            assert validation['same_duck_mass_material_pose_and_initial_velocity']
            assert validation['same_grid_spacing_and_time_step']
            assert validation['no_rotation_lock_or_prescribed_pose']
    else:
        assert validation['pressure_converged']
    report_path = case/'runs/source/simulation_report.json'
    assert validation['simulation_report_sha256'] == digest(report_path)
    presence = spec['physics'].get('duck_presence',[1])
    assert presence in ([0],[1])
    deleted = presence == [0]
    if deleted:
        assert validation['duck_deleted_from_simulation'] and validation['no_hidden_duck_or_ghost_collision_boundary']
        assert spec['counterfactual']['deleted_objects'] == ['duck']
        poses = None
    else:
        with np.load(case/'runs/source/visual_deformation.npz') as data:
            poses = data['positions']
            assert list(map(int,data['frame_numbers'])) == list(range(1,97))
        assert len(poses) == 96 and np.isfinite(poses).all()
        duck_velocity = np.gradient(poses, 1/spec['render']['fps'], axis=0)
    bpy.ops.wm.open_mainfile(filepath=str(assets/'scene.blend'))
    frozen = capture_appearance()
    assert frozen == manifest['packed_appearance'], 'Frozen appearance changed.'
    configure_gpu()
    scene = bpy.context.scene
    removed_water = []
    if water_deleted:
        floor_object = bpy.data.objects['PoolFloor']
        top = max((floor_object.matrix_world @ Vector(p))[2]
                  for p in floor_object.bound_box)
        assert abs(top-validation['pool_floor_top_z_m']) < 1e-6
        removed_water = [o.name for o in bpy.data.objects if o.name in WATER_NAMES]
        for name in removed_water:
            bpy.data.objects.remove(bpy.data.objects[name],do_unlink=True)
        assert not any(o.name in WATER_NAMES for o in bpy.data.objects)
        assert capture_appearance() == frozen, 'Water deletion changed the environment or optical materials.'
        print('WATER_ABSENT_FROM_BLENDER',removed_water,'floor',top,flush=True)
    visual = None
    if deleted:
        removed = [obj.name for obj in bpy.data.objects if obj.name.startswith(('Duck','duck_'))]
        assert 'duck_visual' in removed
        for name in removed:
            bpy.data.objects.remove(bpy.data.objects[name],do_unlink=True)
        assert not any(obj.name.startswith(('Duck','duck_')) for obj in bpy.data.objects)
        assert capture_appearance() == frozen, 'Deletion changed the environment or optical materials.'
        print('DUCK_REMOVED_FROM_BLENDER',removed,flush=True)
    else:
        visual = bpy.data.objects['duck_visual']
        visual.parent = None
        visual.matrix_world = Matrix.Identity(4)
        visual.animation_data_clear()
        for modifier in list(visual.modifiers):
            if modifier.type == 'MESH_CACHE':
                visual.modifiers.remove(modifier)
        if visual.data.has_custom_normals:
            visual.data.normals_split_custom_set([(0.,0.,0.)]*len(visual.data.loops))
        assert len(visual.data.vertices) == poses.shape[1]
    shell = (np.asarray(spec['simulation_quality']['sph_lower_bound_m']),
             np.asarray(spec['simulation_quality']['sph_upper_bound_m']))
    water_material, particles = apply_look(scene, shell, water=not water_deleted, duck=not deleted)
    look = capture_appearance()
    out.mkdir(parents=True,exist_ok=True)
    (out/'frames').mkdir(exist_ok=True)
    path = out/'render_report.json'
    previous = json.loads(path.read_text()) if path.exists() else None
    identity = {'look':LOOK,
        'simulation_report_sha256':digest(report_path),
        'visual_deformation_sha256':None if deleted else digest(case/'runs/source/visual_deformation.npz'),
        'asset_manifest_sha256':digest(assets/'asset_manifest.json'), 'look_inputs':look_inputs(case)}
    if previous:
        assert previous['input_identity'] == identity, 'Cannot resume changed rendering inputs.'
    report = {'status':'rendering', 'input_identity':identity, 'look':LOOK,
        'simulation_report_sha256':identity['simulation_report_sha256'],
        'frames':previous['frames'] if previous else {}, 'appearance_unchanged':False,
        'duck_deleted_from_blender_scene':deleted,
        'water_deleted_from_blender_scene':water_deleted,
        'removed_water_object_names':removed_water}
    selected = selected or list(range(1,97))
    assert all(1 <= frame <= 96 for frame in selected)
    for frame in selected:
        png = out/'frames'/f'frame_{frame:04d}.png'
        if png.exists() and str(frame) in report['frames']:
            assert digest(png) == report['frames'][str(frame)]['sha256']
            continue
        assert not png.exists(), 'Unverified PNG exists in the output.'
        tick = time.monotonic()
        scene.frame_set(frame)
        if not deleted:
            visual.data.vertices.foreach_set('co',poses[frame-1].ravel())
            set_velocity(visual.data,duck_velocity[frame-1])
            visual.data.update()
            actual = np.empty_like(poses[frame-1])
            visual.data.vertices.foreach_get('co',actual.ravel())
            assert np.max(np.abs(actual-poses[frame-1])) < 2e-5
        if water_deleted:
            assert not any(o.name in WATER_NAMES for o in bpy.data.objects)
        else:
            load_water(case,frame,shell)
            for kind, obj in particles.items():
                load_particles(case,frame,kind,obj)
            load_sunlight(case,frame,spec['render']['fps'])
            load_wetness(case,frame,visual)
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = str(png)
        bpy.ops.render.render(write_still=True)
        report['frames'][str(frame)] = {'sha256':digest(png),'seconds':time.monotonic()-tick}
        save(path,report)
        print('RENDER_FRAME',frame,flush=True)
    if water_material is not None:
        water_material.node_tree.nodes['RippleTime'].outputs['Value'].default_value = 0.
    assert capture_appearance() == look, 'The look changed between frames.'
    report['appearance_unchanged'] = True
    report['render_seconds'] = sum(row['seconds'] for row in report['frames'].values())
    report['status'] = 'all_96_frames_complete' if len(report['frames']) == 96 else 'keyframe_preview'
    save(path,report)
    if len(report['frames']) == 96:
        video = out/'video.mp4'
        assert not video.exists(), 'Refuse to replace an existing video.'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-n','-framerate','24','-start_number','1',
            '-i',str(out/'frames/frame_%04d.png'),'-vf',FILM_GRAIN,'-frames:v','96','-c:v','libx264','-crf','18',
            '-pix_fmt','yuv420p','-movflags','+faststart','-threads','4',str(video)],check=True)
        verify_video(case,out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-dir',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path)
    parser.add_argument('--frames',type=int,nargs='+')
    parser.add_argument('--samples',type=int,default=REAL_SAMPLES)
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--skip-existing',action='store_true')
    parser.add_argument('--occluders',action='store_true',help='Only write runs/source/aniso/occluders.npz.')
    parser.add_argument('--evidence-manifest',type=Path,
                        help='Central retained evidence used to verify an existing video-only edit.')
    arguments = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None
    args = parser.parse_args(arguments)
    case = args.case_dir.resolve()
    out = args.out_dir.resolve() if args.out_dir else case
    if args.occluders:
        export_occluders(case)
    elif args.verify_only or (args.skip_existing and (out/'video.mp4').exists()):
        verify_video(case,out,args.evidence_manifest)
    else:
        render_case(case,out,args.frames,args.samples)


def digest(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda : stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def scalar(v):
    if isinstance(v, (str, bool, int, float)):
        return v
    try:
        return list(v)
    except TypeError:
        return str(v)

def tree_record(tree):
    if tree is None:
        return None
    record = {'nodes': [{'name': n.name, 'type': n.bl_idname, 'inputs': [(s.identifier, scalar(s.default_value)) for s in n.inputs if hasattr(s, 'default_value')], 'outputs': [(s.identifier, scalar(s.default_value)) for s in n.outputs if hasattr(s, 'default_value')], 'properties': {k: scalar(getattr(n, k)) for k in ('operation', 'blend_type', 'distribution', 'noise_dimensions', 'sky_type', 'sun_elevation', 'sun_rotation', 'sun_disc', 'sun_size', 'sun_intensity', 'altitude', 'air_density', 'dust_density', 'ozone_density', 'vector_type', 'space', 'data_type', 'interpolation_type', 'clamp', 'uv_map', 'projection', 'extension') if hasattr(n, k)}, 'image': (n.image.name if n.image else None) if hasattr(n, 'image') else None, 'color_ramp': {'interpolation': n.color_ramp.interpolation, 'elements': [(e.position, list(e.color)) for e in n.color_ramp.elements]} if hasattr(n, 'color_ramp') else None} for n in sorted(tree.nodes, key=lambda n: n.name)], 'links': sorted(((l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier) for l in tree.links))}
    return json.loads(json.dumps(record))

def material_records():
    result = {}
    for m in bpy.data.materials:
        r = {'diffuse_color': list(m.diffuse_color), 'nodes': tree_record(m.node_tree)}
        result[m.name] = {'sha256': hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest(), 'configuration': r}
    return result

def lighting():
    s = bpy.context.scene
    return {'world': tree_record(s.world.node_tree), 'lights': [{'name': o.name, 'type': o.data.type, 'location': list(o.location), 'rotation': list(o.rotation_euler), 'energy': o.data.energy, 'color': list(o.data.color), 'angle': getattr(o.data, 'angle', None), 'size': getattr(o.data, 'size', None), 'hide_render': o.hide_render} for o in sorted(s.objects, key=lambda o: o.name) if o.type == 'LIGHT']}

def uv_records(obj):
    result = {}
    for layer in obj.data.uv_layers:
        values = np.empty((len(layer.data), 2), np.float32)
        layer.data.foreach_get('uv', values.ravel())
        result[layer.name] = hashlib.sha256(values.tobytes()).hexdigest()
    return {'active': obj.data.uv_layers.active.name if obj.data.uv_layers.active else None, 'layers': result}

def modifier_records(obj):
    return [{'name': mod.name, 'type': mod.type, 'settings': {name: scalar(getattr(mod, name)) for name in ('show_render', 'show_viewport', 'width', 'segments', 'limit_method', 'angle_limit', 'keep_sharp', 'weight', 'affect', 'mode', 'levels', 'render_levels', 'subdivision_type', 'use_clamp_overlap', 'harden_normals', 'offset', 'thickness') if hasattr(mod, name)}} for mod in obj.modifiers]

def static_signature(ignore_architecture=False, ignored_names=()):
    records = []
    for o in sorted(bpy.context.scene.objects, key=lambda o: o.name):
        if o.name in ignored_names:
            continue
        if ignore_architecture and o.name == 'Hotel side wing':
            continue
        if o.type == 'LIGHT' or o.name.startswith(('ball', 'Duck', 'duck_')) or o.name in ('LiquidDomain', 'InitialLiquid', 'StaticWaterPreview', 'SPHWater', 'SPHSpray', 'SPHMist', 'SPHFoam'):
            continue
        record = {'name': o.name, 'type': o.type, 'matrix': [list(row) for row in o.matrix_world], 'hide_render': o.hide_render, 'modifiers': modifier_records(o), 'materials': [s.material.name if s.material else None for s in o.material_slots]}
        if o.type == 'MESH':
            vertices = np.empty((len(o.data.vertices), 3), np.float32)
            o.data.vertices.foreach_get('co', vertices.ravel())
            record['vertices_sha256'] = hashlib.sha256(vertices.tobytes()).hexdigest()
            record['polygons'] = len(o.data.polygons)
            record['uv'] = uv_records(o)
        if o.type == 'CAMERA':
            record['camera'] = [o.data.lens, o.data.dof.use_dof]
        records.append(record)
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()

def render_settings():
    s = bpy.context.scene
    return {'resolution': [s.render.resolution_x, s.render.resolution_y], 'resolution_percentage': s.render.resolution_percentage, 'fps': s.render.fps, 'fps_base': s.render.fps_base, 'frame_range': [s.frame_start, s.frame_end], 'engine': s.render.engine, 'samples': s.cycles.samples, 'denoising': s.cycles.use_denoising, 'motion_blur': s.render.use_motion_blur, 'bounces': {k: getattr(s.cycles, k) for k in ('max_bounces', 'diffuse_bounces', 'glossy_bounces', 'transmission_bounces', 'transparent_max_bounces', 'volume_bounces', 'sample_clamp_direct', 'sample_clamp_indirect')}, 'color_management': {k: getattr(s.view_settings, k) for k in ('view_transform', 'look', 'exposure', 'gamma')}}

def configure_gpu():
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for backend in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            selected = [d for d in prefs.devices if d.type == backend]
            if not selected:
                continue
            for d in prefs.devices:
                d.use = d in selected
            bpy.context.scene.cycles.device = 'GPU'
            bpy.context.scene.render.use_persistent_data = True
            print('LIGHTING_GPU', backend, [d.name for d in selected], flush=True)
            return {'backend': backend, 'devices': [d.name for d in selected]}
        except Exception as exc:
            print('LIGHTING_GPU_RETRY', str(exc), flush=True)
    raise RuntimeError('No GPU: refusing a silent CPU fallback.')


if __name__ == '__main__':
    main()
