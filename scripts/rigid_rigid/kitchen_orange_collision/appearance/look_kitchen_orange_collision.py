"""The two scanned oranges, and the sunlit breakfast room they roll in.

The room itself is built in ``sunlit_dining_room``; this module imports the
fruit scans, fits them to the simulator's 7.7 cm sphere, and gives them peel
and flesh materials that light passes into, as it does in a real orange.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from scene_geometry import RADIUS, CUT_TOP
import sunlit_dining_room

MODELS = _pcve_asset('models')
FRUIT_MODELS = ('fresh_orange.glb', 'orange_fruit.glb')


def used_assets():
    """Every asset file a render reads, relative to the assets directory."""
    return ([f'models/{n}' for n in FRUIT_MODELS]
            + [f'polyhaven/kitchen_orange_collision/{f}' for f in sunlit_dining_room.used_files()])


def _bsdf(mat):
    return mat.node_tree.nodes.get('Principled BSDF')


def _bbox(o):
    """World bounds from real vertices: ``bound_box`` reads as all zeros until the
    dependency graph has evaluated the freshly imported objects."""
    from mathutils import Vector
    mw = o.matrix_world
    pts = [mw @ v.co for v in o.data.vertices]
    return (Vector([min(p[i] for p in pts) for i in range(3)]),
            Vector([max(p[i] for p in pts) for i in range(3)]))


def _fit_sphere(points):
    import numpy as np
    from mathutils import Vector
    P = np.asarray(points, dtype=np.float64)
    zmin, zmax = P[:, 2].min(), P[:, 2].max()
    Q = P[P[:, 2] > zmin + 0.08 * (zmax - zmin)]
    A = np.hstack([2 * Q, np.ones((len(Q), 1))])
    sol, *_ = np.linalg.lstsq(A, (Q ** 2).sum(axis=1), rcond=None)
    c = Vector(sol[:3].tolist())
    return c, float(np.sqrt(sol[3] + c.dot(c))), zmin, zmax


def _import_mesh(bpy, name):
    from mathutils import Matrix
    path = MODELS / f'{name}.glb'
    if not path.is_file():
        raise FileNotFoundError(f'Missing local asset: {path}')
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [o for o in bpy.data.objects if o not in previous and o.type == 'MESH']
    bpy.context.view_layer.update()
    for o in meshes:
        o.data = o.data.copy()
        o.data.transform(o.matrix_world)
        o.parent = None
        o.matrix_world = Matrix.Identity(4)
        for poly in o.data.polygons:
            poly.use_smooth = True
    for o in [o for o in bpy.data.objects if o not in previous and o.type != 'MESH']:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    return bpy.context.object


def _peel(mat):
    """Orange peel: the scan's colour, a waxy low sheen, and light scattering a
    few millimetres into the rind so the fruit glows red-orange where the sun
    grazes it instead of reading as painted plastic."""
    bs = _bsdf(mat)
    bs.inputs['Roughness'].default_value = .46
    bs.inputs['Specular IOR Level'].default_value = .45
    bs.inputs['Coat Weight'].default_value = .10
    bs.inputs['Coat Roughness'].default_value = .32
    bs.inputs['Subsurface Weight'].default_value = .30
    bs.inputs['Subsurface Radius'].default_value = (1., .42, .14)
    bs.inputs['Subsurface Scale'].default_value = .004
    mat.name = 'Orange peel'


def _flesh(mat):
    """The cut face: juice-wet segments that let light deep into the fruit."""
    bs = _bsdf(mat)
    bs.inputs['Roughness'].default_value = .30
    bs.inputs['Specular IOR Level'].default_value = .55
    bs.inputs['Coat Weight'].default_value = .35
    bs.inputs['Coat Roughness'].default_value = .12
    bs.inputs['Subsurface Weight'].default_value = .65
    bs.inputs['Subsurface Radius'].default_value = (1., .62, .26)
    bs.inputs['Subsurface Scale'].default_value = .008
    mat.name = 'Orange flesh'


def make_driver(bpy, name='Driver orange'):
    """Whole orange: the scan was cut flat where it sat, so the base is re-inflated.

    A photogrammetry orange stops at the table it was scanned on, leaving a flat
    disc on its underside; on a body that rolls, that disc would leave the fruit
    hanging a centimetre above the cloth. The base vertices are pushed out onto
    the fitted sphere, which is the only edit made to the asset.
    """
    from mathutils import Matrix
    o = _import_mesh(bpy, 'fresh_orange')
    centre, radius, zmin, zmax = _fit_sphere([v.co.copy() for v in o.data.vertices])
    s = RADIUS / radius
    flat = [i for i, v in enumerate(o.data.vertices) if v.co.z < zmin + .06 * (zmax - zmin)]
    o.data.transform(Matrix.Scale(s, 4) @ Matrix.Translation(-centre))
    for i in flat:
        v = o.data.vertices[i]
        if v.co.length > 1e-6:
            v.co = v.co.normalized() * RADIUS
    o.data.update()
    o.name, o.data.name = name, name + ' mesh'
    for m in o.data.materials:
        if m is not None and m.use_nodes and _bsdf(m) is not None:
            _peel(m)
    return o


def make_struck(bpy, name='Sliced orange'):
    """The sliced orange: origin is the sphere centre, flat face at +z.

    The scan is one mesh with one material; the faces of the cut get their own
    copy of it (same texture) shaded as flesh, the rest is peel.
    """
    from mathutils import Matrix, Vector
    o = _import_mesh(bpy, 'orange_fruit')
    lo, hi = _bbox(o)
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0.))
    s = RADIUS / max(hi.x - lo.x, hi.y - lo.y) * 2
    o.data.transform(Matrix.Scale(s, 4) @ Matrix.Translation(-centre))
    o.data.update()
    o.name, o.data.name = name, name + ' mesh'
    peel = o.data.materials[0]
    flesh = peel.copy()
    _peel(peel)
    _flesh(flesh)
    o.data.materials.append(flesh)
    cut = 0
    for poly in o.data.polygons:
        if poly.normal.z > .96 and poly.center.z > CUT_TOP - .003:
            poly.material_index = 1
            cut += 1
    if not cut:
        raise RuntimeError('No cut face found on the sliced orange')
    return o


def make_oranges(bpy, rear_count=0):
    """The two named fruit plus, for the queue edit, whole oranges behind the struck one.

    The queued oranges are the same scan as the driver, duplicated so they can be
    placed independently; they share its mesh and material.
    """
    driver = make_driver(bpy)
    objects = {'driver_orange': driver, 'cut_orange': make_struck(bpy)}
    for index in range(int(rear_count)):
        twin = driver.copy()
        twin.name = f'Queued orange {index + 1}'
        bpy.context.collection.objects.link(twin)
        objects[f'rear_orange_{index + 1}'] = twin
    return objects


def build_environment(bpy, scene):
    return sunlit_dining_room.build_room(scene)
