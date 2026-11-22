"""Provenance-preserving rendering helpers."""
import os,re,subprocess,sys
import bpy
import numpy as np
from mathutils import Matrix,Vector
from physics.scene import REPO,ASSET_DIR,sha

def material(name, color, rough=0.55, metal=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    return m

def wood_material(name, folder, prefix, width):
    m = material(name, (0.35, 0.22, 0.12))
    n = m.node_tree.nodes
    l = m.node_tree.links
    b = n.get('Principled BSDF')
    coord = n.new('ShaderNodeTexCoord')
    scale = n.new('ShaderNodeVectorMath')
    scale.operation = 'SCALE'
    scale.inputs[3].default_value = 1 / width
    l.new(coord.outputs['Object'], scale.inputs[0])
    for (suffix, socket_name) in [('diff', 'Base Color'), ('rough', 'Roughness'), ('nor_gl', 'Normal')]:
        matches = list(folder.glob(prefix + '_' + suffix + '*.jpg'))
        assert len(matches) == 1, (folder, prefix, suffix)
        tex = n.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(matches[0]))
        tex.extension = 'REPEAT'
        tex.projection = 'BOX'
        tex.projection_blend = .12
        l.new(scale.outputs[0], tex.inputs['Vector'])
        if suffix != 'diff':
            tex.image.colorspace_settings.name = 'Non-Color'
        if suffix == 'nor_gl':
            normal = n.new('ShaderNodeNormalMap')
            normal.inputs['Strength'].default_value = 0.45
            l.new(tex.outputs['Color'], normal.inputs['Color'])
            l.new(normal.outputs[0], b.inputs['Normal'])
        elif suffix == 'diff':
            tone=n.new('ShaderNodeHueSaturation')
            tone.inputs['Saturation'].default_value=.58
            tone.inputs['Value'].default_value=.85
            l.new(tex.outputs['Color'],tone.inputs['Color'])
            l.new(tone.outputs['Color'],b.inputs[socket_name])
        else:
            l.new(tex.outputs['Color'], b.inputs[socket_name])
    return m

def cube(name, center, size, mat, bevel=0.0006, identity=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    o = bpy.context.object
    o.name = name
    o.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    o.pass_index = identity
    if bevel:
        mod = o.modifiers.new('Physical-looking edge fillet outside contact region', 'BEVEL')
        mod.width = bevel
        mod.segments = 3
        o.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return o

def cylinder(name, center, radius, depth, mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=radius, depth=depth, location=center)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    bevel = o.modifiers.new('Small manufactured edge', 'BEVEL')
    bevel.width = 0.0005
    bevel.segments = 3
    o.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return o

def imported_prop(key, center, length, yaw, ground):
    file = ASSET_DIR / 'props' / {'pencil': 'pencil.blend', 'ruler_reference': 'ruler_reference.blend'}[key]
    with bpy.data.libraries.load(str(file), link=False) as (src, dst):
        dst.objects = list(src.objects)
    objects = [o for o in dst.objects if o and o.type == 'MESH']
    for o in objects:
        matrix = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = matrix
        if o.name not in bpy.context.collection.objects:
            bpy.context.collection.objects.link(o)
    bpy.context.view_layer.update()
    points = np.array([tuple(o.matrix_world @ Vector(v)) for o in objects for v in o.bound_box])
    lo = points.min(0)
    hi = points.max(0)
    span = hi - lo
    longest = int(np.argmax(span))
    thin = int(np.argmin(span))
    middle = next((i for i in range(3) if i not in [longest, thin]))
    R = np.zeros((3, 3))
    R[0, longest] = 1
    R[2, thin] = 1
    R[1, middle] = 1
    if np.linalg.det(R) < 0:
        R[1, middle] = -1
    basis = Matrix(R.tolist()).to_4x4()
    scale = Matrix.Scale(length / span[longest], 4)
    angle = Matrix.Rotation(yaw, 4, 'Z')
    transform = angle @ basis @ scale @ Matrix.Translation(Vector((-(lo + hi) / 2).tolist()))
    for o in objects:
        o.matrix_world = transform @ o.matrix_world
    bpy.context.view_layer.update()
    points = np.array([tuple(o.matrix_world @ Vector(v)) for o in objects for v in o.bound_box])
    shift = Vector((center[0], center[1], ground - float(points[:, 2].min())))
    for o in objects:
        o.location += shift
        o.pass_index = 0
    bpy.context.view_layer.update()
    placed = np.array([tuple(o.matrix_world @ Vector(v)) for o in objects for v in o.bound_box])
    return {'key': key, 'asset_sha256': sha(file), 'mesh_object_count': len(objects), 'placed_bounds': [placed.min(0).tolist(), placed.max(0).tolist()]}

# appearance/realism.py sets this to its recorded GPU approval instead of the delivered policy check.
GPU_POLICY_OVERRIDE = None


def choose_gpu(scene):
    uuid = os.environ.get('CUDA_VISIBLE_DEVICES', '')
    if not uuid.startswith('GPU-') or ',' in uuid:
        raise RuntimeError('One leased GPU UUID required')
    sys.path.insert(0, str(REPO / 'scripts'))
    from pcve_gpu_policy import require_gpu
    decision = GPU_POLICY_OVERRIDE or require_gpu(uuid, case_id='steel_ball_silicone_cup')
    pci = subprocess.check_output(['nvidia-smi', '-i', uuid, '--query-gpu=pci.bus_id', '--format=csv,noheader'], text=True).strip()

    def key(v):
        match = re.search('([0-9a-fA-F]{4,8}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})(?:\\.([0-7]))?', v)
        return tuple((int(x or '0', 16) for x in match.groups())) if match else None
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = bool(d.type == 'OPTIX' and (uuid in d.id or (key(d.id) is not None and key(d.id) == key(pci))))
    rows = [{'id': d.id, 'name': d.name, 'type': d.type, 'use': d.use} for d in prefs.devices]
    assert sum((d['use'] for d in rows)) == 1, 'Cannot bind one verified OptiX device'
    scene.cycles.device = 'GPU'
    return (uuid, pci, decision, rows)

def area(name, pos, target, power, size, color):
    lamp = bpy.data.lights.new(name, 'AREA')
    lamp.energy = power
    lamp.shape = 'DISK'
    lamp.size = size
    lamp.color = color
    o = bpy.data.objects.new(name, lamp)
    bpy.context.collection.objects.link(o)
    o.location = pos
    o.rotation_euler = (Vector(target) - o.location).to_track_quat('-Z', 'Y').to_euler()
