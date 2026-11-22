"""Build ``assets/models/wooden_crate.glb``: a slatted pine crate, 0.400 x 0.300 x 0.620 m.

Run inside Blender from the repository root:

    blender -b --python scripts/rigid_rigid/wall_clock_drop/tools/make_crate_asset.py

The scene needs an object that is unmistakably a rigid body standing in the fall
line of the clock. Corrugated board was the wrong answer: a carton dents, and
this benchmark is about rigid collisions. A nailed pine crate is the honest
equivalent -- the same box of air, but the material really does behave the way
the solver assumes -- so the asset is generated here rather than borrowed: four
corner posts, eight rails, three boards per side, a boarded lid and bottom, and
a 2 mm bevel so the edges catch the room's key light.

The crate is modelled with its base on z = 0 and centred on x = y = 0, at the
exact dimensions the collision box uses, so ``make_crate`` only has to import it.
"""
# PCVE_UNIFIED_ENTRY_BEGIN
import sys as _crate_sys
from pathlib import Path as _CratePath
_SCENE_DIR = _CratePath(__file__).resolve().parents[1]
for _sub in (_SCENE_DIR.parents[1], _SCENE_DIR, _SCENE_DIR / "physics"):
    if _sub.is_dir() and str(_sub) not in _crate_sys.path:
        _crate_sys.path.insert(1, str(_sub))
# PCVE_UNIFIED_ENTRY_END

from pathlib import Path

WIDTH, DEPTH, HEIGHT = 0.400, 0.300, 0.620
POST = 0.030
BOARD = 0.014          # slat thickness
RAIL = 0.030           # top and bottom rails
LID = 0.012            # lid and bottom boards
BEVEL = 0.002


def boxes():
    """Every plank of the crate as (x0, x1, y0, y1, z0, z1, material).

    The boards sit 4 mm behind the outer faces of the posts and rails, so the
    frame stands proud the way a nailed crate does and the sides cast a thin
    shadow line instead of reading as one flat panel.
    """
    hx, hy = WIDTH / 2, DEPTH / 2
    ix, iy = hx - POST, hy - POST           # inside the corner posts
    recess = 0.004
    out = []
    # Four corner posts.
    for x0, x1 in ((-hx, -hx + POST), (hx - POST, hx)):
        for y0, y1 in ((-hy, -hy + POST), (hy - POST, hy)):
            out.append((x0, x1, y0, y1, 0.0, HEIGHT, 0))
    # Top and bottom rails, front/back and left/right.
    for z0, z1 in ((0.0, RAIL), (HEIGHT - RAIL, HEIGHT)):
        for y0, y1 in ((-hy, -hy + BOARD), (hy - BOARD, hy)):
            out.append((-ix, ix, y0, y1, z0, z1, 0))
        for x0, x1 in ((-hx, -hx + BOARD), (hx - BOARD, hx)):
            out.append((x0, x1, -iy, iy, z0, z1, 0))
    # Three boards per side, in the same three bands all the way round.
    bands = ((RAIL, RAIL + 0.120), (RAIL + 0.220, RAIL + 0.340), (HEIGHT - RAIL - 0.120, HEIGHT - RAIL))
    board = 0
    for z0, z1 in bands:
        for y0, y1 in ((-hy + recess, -hy + recess + BOARD), (hy - recess - BOARD, hy - recess)):
            out.append((-ix, ix, y0, y1, z0, z1, 1 + board % 2))
            board += 1
        for x0, x1 in ((-hx + recess, -hx + recess + BOARD), (hx - recess - BOARD, hx - recess)):
            out.append((x0, x1, -iy, iy, z0, z1, 1 + board % 2))
            board += 1
    # Lid and floor: boards across, laid along y.
    n = 6
    span = 2 * ix
    gap = 0.0055
    pitch = (span - gap * (n - 1)) / n
    for index in range(n):
        x0 = -ix + index * (pitch + gap)
        out.append((x0, x0 + pitch, -hy + BOARD, hy - BOARD, HEIGHT - LID, HEIGHT, 1 + index % 2))
    for index in range(3):
        width = (span - gap * 2) / 3
        x0 = -ix + index * (width + gap)
        out.append((x0, x0 + width, -iy, iy, 0.0, LID, 1 + index % 2))
    return out


def materials(bpy):
    """Three tints of the same pine, so neighbouring boards do not read as one slab."""
    spec = [('crate_wood_frame', (.170, .104, .060)),
            ('crate_wood_a', (.220, .140, .082)),
            ('crate_wood_b', (.196, .120, .068))]
    made = []
    for name, colour in spec:
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = (*colour, 1)
        bsdf.inputs['Roughness'].default_value = .62
        bsdf.inputs['Metallic'].default_value = 0.
        made.append(material)
    return made


def main():
    import bpy
    import bmesh

    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new('wooden_crate')
    bm = bmesh.new()
    slots = []
    for x0, x1, y0, y1, z0, z1, slot in boxes():
        corners = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        verts = [bm.verts.new(corner) for corner in corners]
        # Index order matches the corner loop above: x slowest, z fastest.
        for a, b, c, d in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                           (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
            bm.faces.new((verts[a], verts[b], verts[c], verts[d]))
        slots.extend([slot] * 6)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    crate = bpy.data.objects.new('wooden_crate', mesh)
    bpy.context.collection.objects.link(crate)

    for material in materials(bpy):
        mesh.materials.append(material)
    for polygon, slot in zip(mesh.polygons, slots):
        polygon.material_index = slot

    bevel = crate.modifiers.new('bevel', 'BEVEL')
    bevel.width = BEVEL
    bevel.segments = 2
    bevel.limit_method = 'ANGLE'
    bevel.angle_limit = 0.5
    bpy.context.view_layer.objects.active = crate
    bpy.ops.object.modifier_apply(modifier=bevel.name)

    root = next(p for p in Path(__file__).resolve().parents if (p / 'assets').is_dir())
    out = root / 'assets' / 'models' / 'wooden_crate.glb'
    bpy.ops.object.select_all(action='DESELECT')
    crate.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(out), export_format='GLB', use_selection=True,
                              export_apply=True, export_yup=True)
    print('wrote', out, 'boxes', len(boxes()), 'verts', len(mesh.vertices))


if __name__ == '__main__':
    main()
