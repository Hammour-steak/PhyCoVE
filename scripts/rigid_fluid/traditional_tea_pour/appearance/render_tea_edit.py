"""Render native tea edits at the accepted 1280x720, 24fps, 128-sample quality."""
import argparse
import json
from pathlib import Path
import sys
import time
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tea_environment_state import protected_state, environment_state, digest, file_hash
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('case',type=Path)
p.add_argument('--device',choices=['GPU','CPU'],default='GPU')
p.add_argument('--frames',type=int,nargs='+')
p.add_argument('--report-tag')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
case=a.case.resolve();report=json.loads((case/'scene_revision.json').read_text())
scene=bpy.context.scene;scene.frame_set(72);bpy.context.view_layer.update()
assert digest(protected_state())==report['protected_sha256']
assert digest(environment_state())==report['environment_sha256']
assert (scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage,scene.render.fps,scene.cycles.samples)==(1280,720,100,24,128)
if report['native_cache_sha256']:
    cache=Path(bpy.path.abspath(bpy.data.cache_files[0].filepath)).resolve()
    assert cache==case/'genesis_liquid_cache.abc'
    assert file_hash(cache)==report['native_cache_sha256']
else:assert not len(bpy.data.cache_files)
if a.device=='GPU':
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    assert any(d.type=='OPTIX' for d in prefs.devices)
    for d in prefs.devices:d.use=d.type=='OPTIX'
scene.cycles.device=a.device;scene.render.threads_mode='FIXED';scene.render.threads=16
scene.render.use_persistent_data=True
out=case/'frames';out.mkdir(exist_ok=True)
times={};started=time.monotonic();skipped=[]
for f in a.frames or range(1,97):
    path=out/f'frame_{f:04d}.png'
    if path.exists():skipped.append(f);continue
    scene.frame_set(f);bpy.context.view_layer.update()
    actual=report['native_all96_checks'][str(f)]
    assert bpy.data.objects['GenesisTeaSurface'].hide_render==actual['hidden']
    scene.render.filepath=str(path);tick=time.monotonic();bpy.ops.render.render(write_still=True)
    times[str(f)]=time.monotonic()-tick
    print('TEA_EDIT_RENDER_FRAME',case.name,f,times[str(f)],flush=True)
assert file_hash(Path(report['source_blend']))==report['source_sha256']
if report['native_cache_sha256']:assert file_hash(cache)==report['native_cache_sha256']
result={'frames':times,'reused_same_quality_frames':skipped,'render_seconds':time.monotonic()-started,
        'samples':128,'width':1280,'height':720,'fps':24,'device':a.device,'source_and_cache_preserved':True}
(case/(f'render_{a.report_tag}.json' if a.report_tag else ('render_all.json' if not a.frames else 'render_probe.json'))).write_text(json.dumps(result,indent=2)+'\n')
print('TEA_EDIT_RENDER_DONE',case.name,len(times),flush=True)
