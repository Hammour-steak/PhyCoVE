"""The bistro corner, its checked tablecloth, and the two real tins.

Everything here is appearance only: the solver never sees this module, and the
table surface it assumes (``z = 0``, centred on the origin) is exactly the flat
top of the cloth built in bistro_room.py.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from pathlib import Path
from scene_geometry import DRIVER_RADIUS, DRIVER_HEIGHT, RECEIVER_HALF
import bistro_room

MODELS = _pcve_asset('models')
TUNA = MODELS / 'tuna_can.glb'
SARDINE = MODELS / 'sardine_can.glb'
CLOTH_OBJECTS = ('Tablecloth',)

# The two tin scans come with printed labels: a brand, a barcode and a
# nutrition panel on the sardine tin's lid and sides, a brand band and a
# nutrition panel round the tuna tin.  The render keeps their geometry and
# their normal maps (the lid scoring, the seams, the ring pull, all text-free)
# and replaces the printed colour with what an unlabelled tin is made of:
# * tuna tin: bare tinplate ends and a body lithographed in one plain navy ink
#   under clear lacquer;
# * sardine tins: bare drawn aluminium, lid and body alike.
TUNA_INK = (.030, .072, .205)
TINPLATE = (.80, .80, .78)
ALUMINIUM = (.86, .86, .85)
# The printed band stops this far short of each end of the tuna tin: the
# double seams at the rims are bare metal on a real can.
TUNA_SEAM_M = .0030


def _import(bpy, path):
    if not Path(path).is_file():
        raise FileNotFoundError(f'Missing local asset: {path}')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before]


def _vertex_bbox(objects):
    """World-space AABB built from real vertices.

    ``bound_box`` is only refreshed when the depsgraph re-evaluates, and a
    freshly imported glTF object has not done that yet: it still reports the
    authored local extents.  Feeding those through ``matrix_world`` mixes two
    different spaces and quietly mis-sizes the object -- that is what stretched
    the sardine tin 4.5% past its authored proportions.  Vertices are always
    current, so anything that measures an import must use this."""
    points = [o.matrix_world @ v.co for o in objects for v in o.data.vertices]
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    return lo, hi


# -------------------------------------------------------------------- tins

def _fit_tin(bpy, path, target, reference_name=None):
    """Import a tin and rewrite its vertices so the body is ``target`` metres
    across and centred on its own geometric centre, which is the point the
    solver reports.  The pull tab keeps its offset relative to the body.

    Two traps, either of which would silently stretch the tins:

    1. glTF nests the mesh under empties that carry the node transform -- the
       millimetre-to-metre conversion for the tuna tin, and the authored
       non-uniform scale on the sardine tin.  Deleting those empties before
       detaching the mesh drops the transform with them, so every mesh parks its
       world matrix first and gets it back afterwards.
    2. The fit must be one uniform factor.  Fitting x/y/z to their own targets
       would stretch the mesh, and a stretched can reads wrong the moment it
       catches a highlight.  With a single factor the authored proportions
       survive exactly and the gap to the solver's box stays under 0.4 mm.

    No orientation is baked in here on purpose.  The solver reports each tin's
    full world matrix and the renderer applies it verbatim.  Both tins are
    spawned on their bases, so the authored pose is already the pose the solver
    will report -- the driver carries an identity rotation and the receiver only
    a yaw about Z.  Baking a turn into the mesh would compose with the solver's
    matrix instead of replacing it and would lift the can off the cloth."""
    from mathutils import Matrix, Vector
    imported = _import(bpy, path)
    meshes = [o for o in imported if o.type == 'MESH']
    world = {o.name: o.matrix_world.copy() for o in meshes}
    for o in imported:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    for o in meshes:
        o.parent = None
        o.matrix_world = world[o.name]
    reference = next((o for o in meshes if o.name == reference_name), meshes[0])
    bpy.context.view_layer.update()
    lo, hi = _vertex_bbox([reference])
    size = [hi[i] - lo[i] for i in range(3)]
    centre = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2))
    factors = [target[i] / size[i] for i in range(3)]
    uniform = (factors[0] * factors[1] * factors[2]) ** (1. / 3.)
    transform = Matrix.Scale(uniform, 4) @ Matrix.Translation(-centre)
    for o in meshes:
        matrix = o.matrix_world.copy()
        o.parent = None
        o.data = o.data.copy()
        o.data.transform(transform @ matrix)
        o.matrix_world = Matrix.Identity(4)
        for poly in o.data.polygons:
            poly.use_smooth = True
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    return bpy.context.object


def _strip_print(m):
    """Unlink the scan's printed colour and metal/roughness maps from the
    material, keep its normal map, and return (nodes, links, bsdf)."""
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    for socket in ('Base Color', 'Metallic', 'Roughness', 'Alpha'):
        for link in list(bsdf.inputs[socket].links):
            links.remove(link)
    for node in [n for n in nodes if n.type == 'TEX_IMAGE']:
        if not any(l.to_node.type == 'NORMAL_MAP' for out in node.outputs for l in out.links):
            nodes.remove(node)
    bsdf.inputs['Alpha'].default_value = 1.
    m.blend_method = 'OPAQUE'
    return nodes, links, bsdf


def _wear(nodes, links, low, high, scale=900.):
    """Roughness that wanders between ``low`` and ``high``: the handling marks
    and faint rolling lines of a tin that has been on a shelf."""
    coords = nodes.new('ShaderNodeTexCoord')
    stretch = nodes.new('ShaderNodeMapping')
    stretch.inputs['Scale'].default_value = (scale, scale, scale * .12)
    links.new(coords.outputs['Object'], stretch.inputs['Vector'])
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 1.
    noise.inputs['Detail'].default_value = 5.
    links.new(stretch.outputs['Vector'], noise.inputs['Vector'])
    span = nodes.new('ShaderNodeMapRange')
    span.inputs['To Min'].default_value = low
    span.inputs['To Max'].default_value = high
    links.new(noise.outputs['Fac'], span.inputs['Value'])
    return coords, span.outputs['Result']


def bare_metal(m, colour, low, high):
    nodes, links, bsdf = _strip_print(m)
    bsdf.inputs['Base Color'].default_value = (*colour, 1.)
    bsdf.inputs['Metallic'].default_value = 1.
    _, rough = _wear(nodes, links, low, high)
    links.new(rough, bsdf.inputs['Roughness'])


def printed_tuna_body(m):
    """Tinplate with a plain navy band round the body, under clear lacquer.

    The mask comes from the tin's own geometry in object space (the fit leaves
    the tin centred on its origin, axis along z): side walls (|n_z| < 0.6)
    away from the two seams are printed, everything else is bare tinplate."""
    nodes, links, bsdf = _strip_print(m)
    coords, rough_metal = _wear(nodes, links, .16, .26)
    split_n = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coords.outputs['Normal'], split_n.inputs['Vector'])
    flat = nodes.new('ShaderNodeMath'); flat.operation = 'ABSOLUTE'
    links.new(split_n.outputs['Z'], flat.inputs[0])
    side = nodes.new('ShaderNodeMath'); side.operation = 'LESS_THAN'
    side.inputs[1].default_value = .6
    links.new(flat.outputs['Value'], side.inputs[0])
    split_p = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coords.outputs['Object'], split_p.inputs['Vector'])
    height = nodes.new('ShaderNodeMath'); height.operation = 'ABSOLUTE'
    links.new(split_p.outputs['Z'], height.inputs[0])
    inside = nodes.new('ShaderNodeMath'); inside.operation = 'LESS_THAN'
    inside.inputs[1].default_value = DRIVER_HEIGHT / 2 - TUNA_SEAM_M
    links.new(height.outputs['Value'], inside.inputs[0])
    band = nodes.new('ShaderNodeMath'); band.operation = 'MULTIPLY'
    links.new(side.outputs['Value'], band.inputs[0])
    links.new(inside.outputs['Value'], band.inputs[1])
    colour = nodes.new('ShaderNodeMix'); colour.data_type = 'RGBA'
    colour.inputs['A'].default_value = (*TINPLATE, 1.)
    colour.inputs['B'].default_value = (*TUNA_INK, 1.)
    links.new(band.outputs['Value'], colour.inputs['Factor'])
    links.new(colour.outputs['Result'], bsdf.inputs['Base Color'])
    metal = nodes.new('ShaderNodeMath'); metal.operation = 'SUBTRACT'
    metal.inputs[0].default_value = 1.
    links.new(band.outputs['Value'], metal.inputs[1])
    links.new(metal.outputs['Value'], bsdf.inputs['Metallic'])
    rough = nodes.new('ShaderNodeMix'); rough.data_type = 'FLOAT'
    rough.inputs['B'].default_value = .30
    links.new(rough_metal, rough.inputs['A'])
    links.new(band.outputs['Value'], rough.inputs['Factor'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    # Litho print is varnished: a thin clear coat over the ink only.
    links.new(band.outputs['Value'], bsdf.inputs['Coat Weight'])
    bsdf.inputs['Coat Roughness'].default_value = .12


def make_tins(bpy):
    driver = _fit_tin(bpy, TUNA, (2 * DRIVER_RADIUS, 2 * DRIVER_RADIUS, DRIVER_HEIGHT),
                      reference_name='tuna_can_tuna_can_0')
    driver.name = 'Tuna tin (driver, sliding)'
    receiver = _fit_tin(bpy, SARDINE, (2 * RECEIVER_HALF[0], 2 * RECEIVER_HALF[1], 2 * RECEIVER_HALF[2]))
    receiver.name = 'Sardine tin (receiver, at rest)'
    done = set()
    for o in (driver, receiver):
        for m in o.data.materials:
            if not m or not m.use_nodes or m.name in done:
                continue
            done.add(m.name)
            if o is driver and m.name == 'tuna_can':
                printed_tuna_body(m)
                m.name = 'Tuna tin: tinplate, plain navy litho'
            elif o is driver:
                bare_metal(m, ALUMINIUM, .18, .30)          # the ring-pull tab
                m.name = 'Tuna tin: aluminium tab'
            else:
                bare_metal(m, ALUMINIUM, .20, .32)
                m.name = 'Sardine tin: bare aluminium'
    return {'driver_can': driver, 'receiver_can': receiver}


def build_environment(bpy, scene):
    return bistro_room.build(bpy, scene)


def used_files():
    """Every asset file the render reads, for the run metadata."""
    return [TUNA, SARDINE, *bistro_room.used_files()]
