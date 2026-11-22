"""Export the tub alcove as a concave collider mesh.

Why this exists: the room shell is modelled as four flat planes
(`static_boxes`: wall_north at y=4.47, wall_east at x=11.10), but the GLB
actually cuts the north-east corner at 45 degrees - a chamfered wall running
from about (6.8, 4.49) to (10.4, 1.06), with a marble shelf (top z=2.49) in the
triangle behind it. Without a collider for it, a stool that flies into the
corner passes 0.5-1.2 m into the visible wall and is swallowed by it, with
only leg tips poking out.

The chamfer is diagonal, so axis-aligned boxes would either leak (a 0.4 m air
wall along the whole run) or leave a stair-stepped edge. This exports the GLB's
own triangles for that corner instead - the same contract the bathtub uses:
the collider *is* the geometry.

Selection is "triangle AABB overlaps the crop box", not "triangle centre is
inside", because the room shell's walls are large quads whose centres sit far
outside the crop; a centre test would silently drop them and leave the chamfer
uncollided.

Run with a Python that has the bpy module (the interpreter --render-python points at):

  <render-python> scripts/rigid_rigid/bathroom_stool_rebound/tools/export_alcove_collider.py
"""
from __future__ import annotations

# PCVE_UNIFIED_ENTRY_BEGIN
import sys as _export_sys
from pathlib import Path as _ExportPath
_SCENE_DIR = _ExportPath(__file__).resolve().parents[1]
for _sub in (_SCENE_DIR.parents[1], _SCENE_DIR, _SCENE_DIR / "physics", _SCENE_DIR / "appearance"):
    if _sub.is_dir() and str(_sub) not in _export_sys.path:
        _export_sys.path.insert(1, str(_sub))
# PCVE_UNIFIED_ENTRY_END

import argparse

import bpy
from pcve_project_paths import project_root as _project_root
from pcve_assets import asset as _pcve_asset
from scene_geometry import ALCOVE_CROP, ALCOVE_MESH, ALCOVE_SOURCES

FLOOR_BAND_Z = 0.06


def crop_bounds():
    x0, x1, y0, y1, z0, z1 = ALCOVE_CROP
    return x0, x1, y0, y1, z0, z1


def overlaps(bounds, aabb):
    return all(bounds[k * 2] <= aabb[k * 2 + 1] and bounds[k * 2 + 1] >= aabb[k * 2]
               for k in range(3))


def collect():
    """World-space triangles of the alcove, minus the floor it sits on."""
    bounds = crop_bounds()
    verts, faces = [], []
    stats = {}
    for name in ALCOVE_SOURCES:
        obj = bpy.context.scene.objects.get(name)
        if obj is None:
            raise RuntimeError('GLB is missing %r - did the asset change?' % name)
        mw = obj.matrix_world
        normal_mw = mw.to_3x3()
        world = [mw @ v.co for v in obj.data.vertices]
        kept = dropped = floorish = 0
        for poly in obj.data.polygons:
            idx = list(poly.vertices)
            pts = [world[i] for i in idx]
            aabb = []
            for axis in range(3):
                aabb.extend((min(p[axis] for p in pts), max(p[axis] for p in pts)))
            if not overlaps(bounds, aabb):
                dropped += 1
                continue
            normal = (normal_mw @ poly.normal).normalized()
            if normal.z > 0.9 and max(p.z for p in pts) < FLOOR_BAND_Z:
                floorish += 1      # the room's own floor: `floor` box already covers it
                continue
            base = len(verts)
            verts.extend(tuple(p) for p in pts)
            faces.append([base + i for i in range(len(pts))])
            kept += 1
        stats[name] = (len(obj.data.polygons), kept, dropped, floorish)
    return verts, faces, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--glb', type=_ExportPath, default=None)
    parser.add_argument('--out', type=_ExportPath, default=None)
    args = parser.parse_args()

    root = _project_root(__file__)
    glb = args.glb or _pcve_asset('models/big_project.glb')
    out = args.out or _pcve_asset(ALCOVE_MESH)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    bpy.context.view_layer.update()

    verts, faces, stats = collect()
    for name, (total, kept, dropped, floorish) in stats.items():
        print('%-30s total=%5d kept=%4d outside=%4d floor=%3d'
              % (name, total, kept, dropped, floorish))
    if not faces:
        raise RuntimeError('crop box selected no triangles - ALCOVE_CROP is wrong')

    mesh = bpy.data.meshes.new('alcove collider')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('alcove collider', mesh)
    bpy.context.scene.collection.objects.link(obj)

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.obj_export(
        filepath=str(out), export_selected_objects=True, apply_modifiers=True,
        export_materials=False, forward_axis='Y', up_axis='Z',
        export_normals=False, export_uv=False, export_triangulated_mesh=True,
    )
    mesh.calc_loop_triangles()
    print('crop %s' % (list(ALCOVE_CROP),))
    print('wrote %s  verts=%d tris=%d  %.2f MB'
          % (out, len(mesh.vertices), len(mesh.loop_triangles), out.stat().st_size / 1e6))


if __name__ == '__main__':
    main()
