"""Archive the verified contact fix and a small local preview bundle."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('root',type=Path)
p.add_argument('--server-scripts',type=Path,help='package the server case (the scripts folder itself is not archived)')
a=p.parse_args(); root=a.root.resolve()
server=a.server_scripts is not None
diag=root if server else root/'diagnostics'
def read(name): return json.loads((diag/name).read_text())
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while data:=f.read(8*1024*1024): h.update(data)
    return h.hexdigest()
contact=read('contact_acceptance.json'); native=read('saved_animation_validation.json')
scene=read('protected_scene_validation.json'); video=read('video_validation.json'); visual=read('visual_review.json')
assert contact['passed'] and native['passed'] and scene['passed'] and video['passed'] and visual['passed']
assert len(native['all96frames'])==96
simulation=read('simulation_result.json'); render=read('render_all.json'); revision=read('scene_revision.json')
assert render['samples']==128 and len(render['frames'])==96
video_path=root/('video_contact_fixed.mp4' if server else 'video.mp4')
assert sha(video_path)==video['video_sha256']
if server:
    assert root.name=='source_run'
    assert sha(root/'genesis_liquid_cache.abc')==scene['native_cache_sha256']
    assert sha(Path(revision['source_blend']))==revision['source_sha256']
    for f,h in revision['source_caches_preserved'].items(): assert sha(Path(f))==h
    chosen=[root/f for f in ['video_contact_fixed.mp4','scene_tea_fixed.blend','genesis_liquid_cache.abc','contact_acceptance.json','protected_scene_validation.json','saved_animation_validation.json','visual_review.json','video_validation.json','scene_revision.json','delivery_notes.txt']]
else:
    chosen=[f for f in root.rglob('*') if f.is_file() and f.name!='delivery_manifest.json']
manifest={'status':'complete','case':'source_run',
    'scope':'Correct finite-particle table/coaster contact and improve small-droplet rendering. Hero assets/camera/environment unchanged.',
    'server_case':str(root),
    'native_cache_sha256':scene['native_cache_sha256'],'video_sha256':video['video_sha256'],
    'quality':{'width':1280,'height':720,'fps':24,'frames':96,'duration_s':4,'samples':128,'h264_crf':14},
    'contact_before':contact['before'],'contact_after':contact['after'],
    'contact_skin_m':contact['support_contact_skin_m'],
    'checks':{'contact':contact['checks'],'native_all96':True,'protected_scene':scene['passed'],'video':video['checks'],'visual':visual['passed']},
    'timing_seconds':{'simulation':simulation['simulation_seconds'],'render':render['render_seconds'],'encode':video['encode_seconds']},
    'method':'pcve-scene-workflow independent physical correction with source preservation, keyframe comparison and all-frame regression.',
    'files':{str(f.relative_to(root)):{'sha256':sha(f),'bytes':f.stat().st_size} for f in chosen}}
(root/'delivery_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('TEA_CONTACT_PACKAGE_COMPLETE '+json.dumps({'server':server,'files':len(chosen),'video_sha256':video['video_sha256'],'timing_seconds':manifest['timing_seconds']}),flush=True)
