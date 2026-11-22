"""Shared, deterministic appearance pass. Blender execution is remote-only.

Only shaders, polygon normals and light/render settings are changed. No object
transform, mesh vertex, modifier, camera or animation is changed by this pass.
Procedural coordinates are in object-space metres for hardware and material UVs
for the deforming membrane, so grain follows the native simulated surface.
"""
import bpy

REVISION = 'lab_materials'


def material(name, color, metallic, roughness):
    value = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    value.use_nodes = True
    value.diffuse_color = (*color, 1)
    nodes = value.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.name = 'Principled BSDF'
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    output = nodes.new('ShaderNodeOutputMaterial')
    value.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    return value, bsdf


def noise(mat, scale, stretch=None, uv=False, detail=2):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    vector = coord.outputs['UV' if uv else 'Object']
    if stretch:
        mapping = nodes.new('ShaderNodeVectorMath')
        mapping.operation = 'MULTIPLY'
        mapping.inputs[1].default_value = stretch
        links.new(vector, mapping.inputs[0])
        vector = mapping.outputs['Vector']
    texture = nodes.new('ShaderNodeTexNoise')
    texture.inputs['Scale'].default_value = scale
    texture.inputs['Detail'].default_value = detail
    texture.inputs['Roughness'].default_value = .63
    links.new(vector, texture.inputs['Vector'])
    return texture.outputs['Fac']


def ramp(mat, value, low, high):
    node = mat.node_tree.nodes.new('ShaderNodeValToRGB')
    node.color_ramp.elements[0].position = .18
    node.color_ramp.elements[0].color = (*low, 1)
    node.color_ramp.elements[1].position = .82
    node.color_ramp.elements[1].color = (*high, 1)
    mat.node_tree.links.new(value, node.inputs['Fac'])
    return node.outputs['Color']


def bump(mat, bsdf, value, strength, distance):
    node = mat.node_tree.nodes.new('ShaderNodeBump')
    node.inputs['Strength'].default_value = strength
    node.inputs['Distance'].default_value = distance
    mat.node_tree.links.new(value, node.inputs['Height'])
    mat.node_tree.links.new(node.outputs['Normal'], bsdf.inputs['Normal'])


def metal(name, color, rough_range, stretch, anisotropy=.25, depth=3e-6):
    mat, bsdf = material(name, color, 1, sum(rough_range)/2)
    grain = noise(mat, 1, stretch, detail=2.3)
    rough = ramp(mat, grain, (rough_range[0],)*3, (rough_range[1],)*3)
    mat.node_tree.links.new(rough, bsdf.inputs['Roughness'])
    bsdf.inputs['Anisotropic'].default_value = anisotropy
    bump(mat, bsdf, grain, .15, depth)
    return mat


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def apply(scene, samples=256):
    """Apply the same finish to the source and all five counterfactual cases."""
    steel = metal('Precision brushed stainless steel', (.50,.53,.56),
                  (.23,.34), (6200,100,180), .32, 3e-6)
    aluminum = metal('Bead-blasted aluminum', (.56,.59,.62),
                     (.33,.43), (1350,1350,1350), .12, 5e-6)
    board = metal('Directional satin stainless breadboard', (.43,.45,.47),
                  (.40,.51), (9500,65,120), .40, 4e-6)
    bearing = metal('Precision polished bearing steel', (.60,.63,.66),
                    (.105,.145), (14500,14500,14500), .035, .8e-6)
    ring = metal('Circumferentially finished clamp steel', (.50,.53,.56),
                 (.22,.31), (3600,3600,140), .28, 2e-6)
    frame, bsdf = material('Black anodized laboratory frame', (.012,.016,.020), .72, .37)
    fine = noise(frame, 1950, detail=2)
    rough = ramp(frame, fine, (.32,)*3, (.42,)*3)
    frame.node_tree.links.new(rough, bsdf.inputs['Roughness'])
    bump(frame, bsdf, fine, .11, 5e-6)

    latex, bsdf = material('Charcoal latex with sparse DIC speckles', (.0045,.005,.0055), 0, .60)
    bsdf.inputs['IOR'].default_value = 1.49
    bsdf.inputs['Specular IOR Level'].default_value = .34
    bsdf.inputs['Coat Weight'].default_value = .018
    bsdf.inputs['Coat Roughness'].default_value = .48
    micro = noise(latex, 360, uv=True, detail=2.1)
    rough = ramp(latex, micro, (.55,)*3, (.65,)*3)
    latex.node_tree.links.new(rough, bsdf.inputs['Roughness'])
    bump(latex, bsdf, micro, .10, 35e-6)
    # Sparse painted DIC flecks remain material-bound, never extra geometry.
    speckles = noise(latex, 215, uv=True, detail=1.5)
    paint = latex.node_tree.nodes.new('ShaderNodeValToRGB')
    paint.color_ramp.interpolation = 'CONSTANT'
    paint.color_ramp.elements[0].position = .72
    paint.color_ramp.elements[0].color = (.0045,.005,.0055,1)
    paint.color_ramp.elements[1].position = .755
    paint.color_ramp.elements[1].color = (.18,.19,.19,1)
    latex.node_tree.links.new(speckles, paint.inputs['Fac'])
    latex.node_tree.links.new(paint.outputs['Color'], bsdf.inputs['Base Color'])

    glass, bsdf = material('Optical glass', (.012,.022,.027), 0, .055)
    bsdf.inputs['IOR'].default_value = 1.52
    bsdf.inputs['Transmission Weight'].default_value = .68
    bsdf.inputs['Coat Weight'].default_value = .35
    bsdf.inputs['Coat IOR'].default_value = 1.38
    # The guard uses a solid transparent dielectric, not alpha-faded plastic.
    guard, bsdf = material('Clear polycarbonate guard', (.93,.965,.98), 0, .065)
    bsdf.inputs['IOR'].default_value = 1.585
    bsdf.inputs['Transmission Weight'].default_value = 1
    bsdf.inputs['Alpha'].default_value = 1

    cables, bsdf = material('Flexible low-gloss cable jacket', (.004,.005,.006), 0, .56)
    fine = noise(cables, 1500)
    bump(cables, bsdf, fine, .12, 8e-6)
    # Select smooth normals only on analytically curved surfaces. Cylinder end
    # faces and six-sided socket recesses keep their manufactured sharp edges.
    smooth_count = 0
    for obj in scene.objects:
        if obj.type == 'CURVE' and 'cable' in obj.name.lower():
            assign(obj, cables)
        if obj.type != 'MESH':
            continue
        name = obj.name
        if name in ('304 stainless drop sphere', '304 stainless pre-positioned sphere'):
            assign(obj, bearing)
        elif name == 'Stainless breadboard skin':
            assign(obj, board)
        elif name.startswith('Upper precision clamp ring'):
            assign(obj, ring)
        if (name.startswith('Rubber membrane') or 'sphere' in name.lower()
                or any(term in name for term in ('clamp ring', 'clamp insert'))):
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
            smooth_count += 1
        elif len(obj.data.polygons) > 18 and any(m.type == 'BEVEL' for m in obj.modifiers):
            # Side quads are smooth; cap n-gons stay planar. No mesh subdivision.
            for polygon in obj.data.polygons:
                polygon.use_smooth = len(polygon.vertices) == 4
            smooth_count += 1

    for name, energy, color, size, size_y in (
        ('Large overhead softbox', 340, (1.0,.955,.88), 1.55, .92),
        ('Left shape strip', 195, (.84,.91,1.0), 1.05, .22),
        ('Warm instrument rim', 165, (1.0,.86,.69), .90, .32),
    ):
        light = bpy.data.objects.get(name)
        if light:
            light.data.energy = energy
            light.data.color = color
            light.data.size = size
            light.data.size_y = size_y
    if scene.world and scene.world.use_nodes:
        for node in scene.world.node_tree.nodes:
            if node.type == 'BACKGROUND':
                node.inputs['Strength'].default_value = .32

    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = .005
    scene.cycles.adaptive_min_samples = min(64, samples)
    scene.cycles.use_denoising = True
    scene.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    scene.cycles.denoising_prefilter = 'ACCURATE'
    scene.cycles.max_bounces = 12
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 8
    scene.cycles.transmission_bounces = 12
    scene.cycles.transparent_max_bounces = 12
    scene.cycles.sample_clamp_indirect = 8
    scene.cycles.seed = 3187
    scene.cycles.use_animated_seed = False
    scene.render.filter_size = 1.15
    scene.render.use_motion_blur = False
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = -.55
    scene['appearance_revision'] = REVISION
    return dict(revision=REVISION, samples=samples,
                smoothed_curved_objects=smooth_count,
                geometry_vertices_changed=False, object_transforms_changed=False,
                camera_changed=False, animation_changed=False,
                texture_method='deterministic physically scaled procedural microfinish',
                polished_spheres_share_material=True,
                materials=['polished bearing steel','directional satin breadboard',
                           'brushed steel','bead-blasted aluminum','black anodizing',
                           'UV-bound satin latex','solid dielectric polycarbonate'])
