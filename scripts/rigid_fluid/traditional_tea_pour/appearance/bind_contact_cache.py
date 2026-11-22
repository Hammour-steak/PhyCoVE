"""Bind only the new contact scene (scene_tea_fixed.blend) to its own exported ABC after first save."""
import json
import sys
from pathlib import Path
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tea_environment_state import file_hash,protected_state,digest
case=Path(sys.argv[sys.argv.index('--')+1]).resolve()
assert Path(bpy.data.filepath).resolve()==case/'scene_tea_fixed.blend'
report=json.loads((case/'scene_revision.json').read_text())
assert len(bpy.data.cache_files)==1
cache=bpy.data.cache_files[0]
assert file_hash(case/'genesis_liquid_cache.abc')==report['native_cache_sha256']
cache.filepath=str(case/'genesis_liquid_cache.abc')
bpy.context.scene.frame_set(72); bpy.context.view_layer.update()
mesh=bpy.data.objects['GenesisTeaSurface'].evaluated_get(bpy.context.evaluated_depsgraph_get()).data
with np.load(case/'surfaces/frame_0072.npz') as z: expected=z['vertices']
assert len(mesh.vertices)==len(expected)
actual=np.empty(len(expected)*3,dtype=np.float32); mesh.vertices.foreach_get('co',actual)
assert float(np.max(np.abs(actual.reshape(-1,3)-expected)))<1e-6
assert digest(protected_state())==report['protected_sha256']
cache.filepath='//genesis_liquid_cache.abc'
bpy.ops.wm.save_as_mainfile(filepath=str(case/'scene_tea_fixed.blend'),check_existing=False,relative_remap=False)
print('NEW_CONTACT_CACHE_BIND_PASS',flush=True)
