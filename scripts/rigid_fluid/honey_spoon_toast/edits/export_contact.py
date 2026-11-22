from pathlib import Path
import json
import argparse
import sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO, asset

root = REPO
parser = argparse.ArgumentParser()
parser.add_argument('--work-dir', type=Path, required=True)
parser.add_argument('--source-template', type=Path, default=asset('scenes/honey_spoon_toast/scene_template.blend'))
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
stage = args.work_dir.resolve()
bpy.ops.wm.open_mainfile(filepath=str(args.source_template.resolve()))
tree = BVHTree.FromObject(bpy.data.objects['PCVE_Plate'], bpy.context.evaluated_depsgraph_get())
radii, heights = [], []
for i in range(241):
    radius = i * .0005
    hit, _, _, _ = tree.ray_cast(Vector((.095 + radius, 0, .85)), Vector((0, 0, -1)))
    if hit is not None:
        radii.append(radius)
        heights.append(hit.z)
record = {'plate_center_xy_m': [.095, 0.], 'radius_m': radii, 'height_m': heights,
          'toast_center_xy_m': [.095, 0.], 'toast_half_size_xy_m': [.065, .0525],
          'toast_top_m': .797, 'table_top_m': .7587666511535645,
          'source': 'vertical ray intersections with the evaluated rendered ceramic plate'}
(stage / 'receiving_contact.json').write_text(json.dumps(record, indent=2) + '\n')
print('EXPORTED_CONTACT', len(radii), flush=True)
