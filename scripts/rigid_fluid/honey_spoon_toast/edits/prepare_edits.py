"""Create independent object edits from the packed source, retaining its look."""
from pathlib import Path
import array
import argparse
import hashlib
import json
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO, asset

ROOT = REPO
parser = argparse.ArgumentParser()
parser.add_argument('--work-dir', type=Path, required=True)
parser.add_argument('--source-template', type=Path, default=asset('scenes/honey_spoon_toast/scene_template.blend'))
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
STAGE, SOURCE = args.work_dir.resolve(), args.source_template.resolve()
STAGE.mkdir(parents=True, exist_ok=True)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def objects_snapshot(exclude=()):
    result = {}
    for obj in bpy.context.scene.objects:
        if obj.name in exclude:
            continue
        row = {'type': obj.type, 'matrix': [list(v) for v in obj.matrix_world],
               'parent': obj.parent.name if obj.parent else None,
               'visibility': [obj.hide_render, obj.hide_viewport]}
        if obj.type == 'MESH':
            coords = array.array('f', [0.]) * (len(obj.data.vertices) * 3)
            obj.data.vertices.foreach_get('co', coords)
            row.update(vertices=sha(coords.tobytes()), materials=[m.name for m in obj.data.materials if m],
                       modifiers=[(m.name, m.type) for m in obj.modifiers])
        elif obj.type == 'CAMERA':
            row['optics'] = [obj.data.lens, obj.data.dof.aperture_fstop, obj.data.dof.focus_distance,
                             obj.data.dof.focus_object.name if obj.data.dof.focus_object else None]
        elif obj.type == 'LIGHT':
            row['light'] = [obj.data.type, obj.data.energy, list(obj.data.color), obj.data.size]
        result[obj.name] = row
    return result


assert sha(SOURCE.read_bytes()) == 'c3ff20fcb29deeba0bb1ec8d41095f67928285f2ee211aff08ea73d41fe94841'
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
plate = bpy.data.objects['PCVE_Plate']
tree = BVHTree.FromObject(plate, bpy.context.evaluated_depsgraph_get())
heights = []
for x in [.074, .086, .09782639865233517, .110, .122]:
    for y in [-.024, -.012, 0., .012, .024]:
        hit, _, _, _ = tree.ray_cast(Vector((x, y, .85)), Vector((0, 0, -1)))
        assert hit is not None
        heights.append(hit.z)
print('PLATE_HEIGHTS', json.dumps(heights), flush=True)
assert max(heights) - min(heights) < 5e-5, 'Landing grid must lie in the flat plate well.'
hit, _, _, _ = tree.ray_cast(Vector((.09782639865233517, 0, .85)), Vector((0, 0, -1)))
landing = hit.z

# The un-subdivided closed plate is a collision proxy with the same profile.
plate.data.calc_loop_triangles()
collision = STAGE / 'plate_collision.obj'
with collision.open('w') as stream:
    for vertex in plate.data.vertices:
        p = plate.matrix_world @ vertex.co
        stream.write(f'v {p.x:.10g} {p.y:.10g} {p.z:.10g}\n')
    for tri in plate.data.loop_triangles:
        stream.write('f ' + ' '.join(str(v + 1) for v in tri.vertices) + '\n')

records = {}
for case, remove in [('remove_bread', ['PCVE_ToastTextured']),
                     ('remove_honey', ['PCVE_Honey']), ('lower_viscosity', [])]:
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    before = objects_snapshot(remove)
    assert not [o.name for o in bpy.data.objects if o.name.startswith('PCVE_BreadCrumb_')]
    for name in remove:
        assert name in bpy.data.objects, name
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    assert objects_snapshot(remove) == before, 'Non-target object changed'
    assert not [o.name for o in bpy.data.objects if o.name in remove]
    out = STAGE / case
    out.mkdir(exist_ok=False)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'scene.blend'))
    records[case] = {'removed_objects': remove, 'non_target_objects_unchanged': True,
                     'template_sha256': sha((out / 'scene.blend').read_bytes()),
                     'source_template_sha256': sha(SOURCE.read_bytes()),
                     'non_target_snapshot_sha256': sha(json.dumps(before, sort_keys=True).encode())}
record = {'cases': records, 'plate_landing_z_m': landing,
          'plate_landing_patch_height_range_m': [min(heights), max(heights)],
          'plate_collision_sha256': sha(collision.read_bytes())}
(STAGE / 'preparation_report.json').write_text(json.dumps(record, indent=2) + '\n')
print('EDITS_PREPARED', json.dumps(record), flush=True)
