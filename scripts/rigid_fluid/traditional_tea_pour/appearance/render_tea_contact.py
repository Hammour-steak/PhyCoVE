"""Render native repaired contact; same camera/environment, explicit quality."""
import argparse
import json
import sys
import time
from pathlib import Path
import bpy

sys.path.insert(0,str(Path(__file__).resolve().parent))
from tea_environment_state import protected_state,environment_state,digest,file_hash
p=argparse.ArgumentParser()
p.add_argument('case',type=Path)
p.add_argument('--device',choices=['CPU','GPU'],default='GPU')
p.add_argument('--frames',type=int,nargs='+')
p.add_argument('--samples',type=int,default=32)
p.add_argument('--output',default=None)
p.add_argument('--save-quality',action='store_true')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
assert a.samples>=32
case=a.case.resolve(); report=json.loads((case/'scene_revision.json').read_text())
scene=bpy.context.scene; scene.frame_set(72); bpy.context.view_layer.update()
actual=protected_state(); expected=report['protected_after']
# An accepted quality increase is allowed explicitly; all hero/appearance state stays fixed.
actual['render'][6]=expected['render'][6]
assert digest(actual)==digest(expected)
assert digest(environment_state())==report['environment_sha256_after']
cache_path=Path(bpy.path.abspath(bpy.data.cache_files[0].filepath)).resolve()
assert file_hash(cache_path)==report['native_cache_sha256']
if a.device=='GPU':
    prefs=bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type='OPTIX'; prefs.get_devices()
    assert any(d.type=='OPTIX' for d in prefs.devices)
    for d in prefs.devices: d.use=d.type=='OPTIX'
scene.cycles.device=a.device; scene.cycles.samples=a.samples
scene.render.threads_mode='FIXED'; scene.render.threads=32
scene.render.use_persistent_data=True
out=case/(a.output or ('stills_32spp' if a.frames else 'frames')); out.mkdir(exist_ok=True)
times={}; start=time.monotonic()
for f in a.frames or range(1,97):
    path=out/f'frame_{f:04d}.png'; assert not path.exists()
    scene.frame_set(f); bpy.context.view_layer.update()
    scene.render.filepath=str(path)
    tick=time.monotonic(); bpy.ops.render.render(write_still=True)
    times[str(f)]=time.monotonic()-tick
    print('TEA_CONTACT_RENDER_FRAME',f,times[str(f)],flush=True)
if a.save_quality:
    scene.frame_set(72)
    bpy.ops.wm.save_as_mainfile(filepath=str(case/'scene_tea_fixed.blend'),check_existing=False,relative_remap=False)
assert file_hash(cache_path)==report['native_cache_sha256']
assert file_hash(Path(report['source_blend']))==report['source_sha256']
result={'frames':times,'render_seconds':time.monotonic()-start,'samples':a.samples,'device':a.device,
        'width':scene.render.resolution_x,'height':scene.render.resolution_y,'fps':scene.render.fps,
        'source_and_cache_preserved':True}
(case/('render_all.json' if not a.frames else f'render_probe_{out.name}.json')).write_text(json.dumps(result,indent=2)+'\n')
print('TEA_CONTACT_RENDER_COMPLETE',len(times),flush=True)
