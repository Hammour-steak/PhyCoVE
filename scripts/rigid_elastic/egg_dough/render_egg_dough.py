#!/usr/bin/env python3
"""Formal 720p Cycles rendering and complete encode/decode verification."""
from __future__ import annotations
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import scene_asset
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=='__main__':
    import sys as _s
    from pathlib import Path as _P
    if (_P(__file__).parent/'entrypoints.json').is_file():
        _s.path.insert(0,str(_P(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,'render')
# PCVE_UNIFIED_ENTRY_END
import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from dough_config import HERE,choose_gpu,blender_path,write_json,digest,LOOK_FILE

def verify_video(path):
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames',
        '-show_entries','stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration','-of','json',str(path)],text=True))
    s=probe['streams'][0]
    assert (s['width'],s['height'],s['r_frame_rate'],s['avg_frame_rate'],int(s['nb_read_frames']))==(1280,720,'24/1','24/1',96),probe
    assert abs(float(probe['format']['duration'])-4)<.001,probe
    subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True)
    return probe

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--simulation-dir',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--blender',default=blender_path())
    p.add_argument('--gpu',default='auto');p.add_argument('--threads',type=int,default=6)
    p.add_argument('--frames',default='all');p.add_argument('--save-blend',action='store_true')
    p.add_argument('--appearance-file',type=Path,default=LOOK_FILE)
    p.add_argument('--resume',action='store_true',help='Render missing frames only after validating matching cache and look identity')
    a=p.parse_args();cache=a.simulation_dir.resolve()/'simulation_cache.npz';out=a.out_dir.resolve()
    signature={'cache_sha256':digest(cache),
        'config_sha256':digest(a.simulation_dir/'actual_config.json'),'appearance_sha256':digest(a.appearance_file) if a.appearance_file.is_file() else None,'frames':a.frames,'quality':'Cycles64_1280x720'}
    manifest=scene_asset(HERE, 'assets/look_assets/asset_manifest.json')
    for item in json.loads(manifest.read_text())['assets']:
        asset=manifest.parent/item['path']
        if digest(asset)!=item['sha256']:raise RuntimeError('Pinned visual asset changed: '+item['path'])
    signature.update(visual_assets_sha256=digest(manifest))
    new_manifest=scene_asset(HERE, 'assets/worktop_textures/asset_manifest.json')
    for item in json.loads(new_manifest.read_text())['assets']:
        if digest(new_manifest.parent/item['path'])!=item['sha256']:
            raise RuntimeError('Pinned realism asset changed: '+item['path'])
    signature['realism_assets_sha256']=digest(new_manifest)
    rigid_manifest=scene_asset(HERE, 'assets/rigid_egg/asset_manifest.json')
    for item in json.loads(rigid_manifest.read_text())['assets']:
        if digest(rigid_manifest.parent/item['path'])!=item['sha256']:raise RuntimeError('Rigid egg asset changed: '+item['path'])
    signature['rigid_asset_manifest_sha256']=digest(rigid_manifest)
    look=json.loads(a.appearance_file.read_text())
    # Every scanned map the look reads is part of the render identity.
    _pcve_assets_sys.path.insert(0,str(HERE/'appearance'))
    from realism_look_assets import files
    signature['look_assets_sha256']={name:digest(path) for name,path in sorted(files(HERE).items())}
    r=look.get('render',{})
    signature['quality']=f"Cycles{r.get('samples',256)}_1280x720_shutter{r.get('shutter_frames',.25) if r.get('motion_blur') else 0}"
    if out.exists() and any(out.iterdir()):
        if not a.resume or not (out/'render_identity.json').is_file():raise FileExistsError(out)
        if json.loads((out/'render_identity.json').read_text())!=signature:raise RuntimeError('Resume inputs differ')
    out.mkdir(parents=True,exist_ok=True);write_json(out/'render_identity.json',signature)
    frame_ids=list(range(1,97)) if a.frames=='all' else list(map(int,a.frames.split(',')))
    missing=[i for i in frame_ids if not (out/'frames'/f'frame_{i:04d}.png').is_file()]
    gpu=choose_gpu(a.gpu);render_start=time.monotonic()
    if missing:
        cmd=[a.blender,'-b','--disable-autoexec','-t',str(a.threads),'--python-exit-code','1','--python',str(HERE/'appearance/scene_egg_dough.py'),
            '--','--appearance-file',str(a.appearance_file.resolve()),'--cache',str(cache),'--out-dir',str(out),'--frames',','.join(map(str,missing))]
        if a.save_blend:cmd.append('--save-blend')
        with (out/f'render_{int(time.time())}.log').open('w') as log:
            subprocess.run(cmd,env=dict(os.environ,CUDA_VISIBLE_DEVICES='' if gpu=='cpu' else gpu,PCVE_CYCLES_CPU='1' if gpu=='cpu' else '0'),stdout=log,stderr=subprocess.STDOUT,check=True)
    render_seconds=time.monotonic()-render_start
    receipt={**signature,'gpu':gpu,'new_frames':missing,'render_wall_seconds_this_invocation':render_seconds}
    if a.frames=='all':
        for i in frame_ids:assert (out/'frames'/f'frame_{i:04d}.png').is_file()
        t=time.monotonic()
        if not (out/'video.mp4').exists():
            subprocess.run(['ffmpeg','-v','error','-framerate','24','-start_number','1','-i',str(out/'frames/frame_%04d.png'),
                '-frames:v','96','-c:v','libx264','-threads','4','-preset','slow','-crf','17','-pix_fmt','yuv420p',
                '-movflags','+faststart',str(out/'video.mp4')],check=True)
        receipt.update(encode_wall_seconds=time.monotonic()-t,probe=verify_video(out/'video.mp4'),
            video_sha256=digest(out/'video.mp4'),status='video_spec_and_decode_passed')
    else:receipt['status']='static_frames_only'
    write_json(out/'render_receipt.json',receipt);print(json.dumps(receipt),flush=True)

if __name__=='__main__':main()
