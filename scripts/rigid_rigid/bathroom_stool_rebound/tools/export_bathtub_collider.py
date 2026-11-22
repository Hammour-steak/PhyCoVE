"""Regenerate assets/scenes/bathroom_stool_rebound/bathtub_collision.obj from the GLB's marble.

The bathtub collider is the model's own triangles, so this script is the one
place that decides what "the bathtub" means geometrically: every mesh under the
'bathtub' empty, with its world transform baked in and exported Z-up (no axis
swap), because the solver loads it directly into Bullet's coordinates.

Run with a Python that has the bpy module (the interpreter --render-python points at):

  <render-python> scripts/rigid_rigid/bathroom_stool_rebound/tools/export_bathtub_collider.py

Re-run it whenever the GLB is replaced; the OBJ is a build product, but it is
committed so the physics runtime never needs Blender.
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
from scene_geometry import BATHTUB_MESH

ROOT_PREFIX = 'bathtub'


def subtree(root):
    out, stack = [], [root]
    while stack:
        obj = stack.pop()
        out.append(obj)
        stack.extend(obj.children)
    return out


def collect_meshes():
    roots = [o for o in bpy.context.scene.objects
             if o.name.startswith(ROOT_PREFIX)
             and (o.parent is None or not o.parent.name.startswith(ROOT_PREFIX))]
    if not roots:
        raise RuntimeError('No bathtub empty found in the GLB')
    return [o for r in roots for o in subtree(r) if o.type == 'MESH']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--glb', type=_ExportPath, default=None)
    parser.add_argument('--out', type=_ExportPath, default=None)
    args = parser.parse_args()

    root = _project_root(__file__)
    glb = args.glb or _pcve_asset('models/big_project.glb')
    out = args.out or _pcve_asset(BATHTUB_MESH)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    bpy.context.view_layer.update()

    members = collect_meshes()
    print('bathtub meshes:', [m.name for m in members])

    # Flatten to one world-space mesh so the export needs no transform tricks.
    verts, faces = [], []
    for obj in members:
        base = len(verts)
        mw = obj.matrix_world
        verts.extend([mw @ v.co for v in obj.data.vertices])
        faces.extend([[base + i for i in poly.vertices] for poly in obj.data.polygons])

    mesh = bpy.data.meshes.new('tub collider')
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    obj = bpy.data.objects.new('tub collider', mesh)
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
    print('wrote %s  verts=%d tris=%d  %.2f MB'
          % (out, len(mesh.vertices), len(mesh.loop_triangles), out.stat().st_size / 1e6))


if __name__ == '__main__':
    main()
