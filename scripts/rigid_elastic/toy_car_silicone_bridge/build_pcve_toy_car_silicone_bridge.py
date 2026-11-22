"""Build independent source and physical edit cases with the public PCVE CLI."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == '__main__':
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    if _PcvePath(__file__).with_name('entrypoints.json').is_file():
        _pcve_sys.path.insert(0,str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__,'build_pcve')
# PCVE_UNIFIED_ENTRY_END
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from bridge_physics import CASES,baseline,config_for,save_json,digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
STEM='toy_car_silicone_bridge'

def run(command,log,env):
    log.parent.mkdir(parents=True,exist_ok=True);start=time.monotonic()
    print('RUN',json.dumps([str(x) for x in command]),flush=True)
    with log.open('w') as f:
        result=subprocess.run([str(x) for x in command],stdout=f,stderr=subprocess.STDOUT,env=env,cwd=ROOT)
    record={'command':list(map(str,command)),'log':str(log),'elapsed_s':time.monotonic()-start,'exit_code':result.returncode}
    save_json(log.with_suffix('.json'),record)
    if result.returncode:
        print(log.read_text()[-6000:],flush=True);raise RuntimeError('Stage failed: '+str(log))
    print('DONE',log.name,round(record['elapsed_s'],2),'seconds',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--stage',choices=['all','prepare','simulate','keyframes','render','verify','edits'],default='all')
    p.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES))
    p.add_argument('--python',type=Path,default=ROOT/'.venv-toy-car-bridge/bin/python')
    p.add_argument('--blender',type=Path,default=blender())
    p.add_argument('--gpu');p.add_argument('--threads',type=int,default=8)
    p.add_argument('--device',default='OPTIX',choices=['OPTIX','CUDA','METAL','CPU'])
    p.add_argument('--resume',action='store_true')
    p.add_argument('--reuse-physics-from',type=Path,help='prepare only: audited independent copies for an appearance-only revision')
    a=p.parse_args();out=a.output_dir.expanduser().resolve();out.mkdir(parents=True,exist_ok=True)
    if a.reuse_physics_from and a.stage!='prepare':raise ValueError('--reuse-physics-from requires --stage prepare')
    env={**os.environ,'OMP_NUM_THREADS':str(a.threads),'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    gpu=a.gpu or env.get('CUDA_VISIBLE_DEVICES')
    if a.stage in ['all','keyframes','render','edits'] and a.device in ['OPTIX','CUDA']:
        if gpu is None:
            rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used','--format=csv,noheader,nounits'],text=True)
            candidates=[tuple(map(int,row.split(','))) for row in rows.splitlines()]
            candidates=[x for x in candidates if x[1]<5 and x[2]<100]
            if not candidates:raise RuntimeError('No idle GPU under 100 MiB: select an available --gpu')
            gpu=str(min(candidates,key=lambda x:x[2])[0])
        env['CUDA_VISIBLE_DEVICES']=gpu
    native={'config_signature':digest(baseline()),'scene':STEM,'root':str(out),
        'cases':a.cases,'resources':{'gpu':gpu,'threads':a.threads,'python':str(a.python),'blender':str(a.blender)}}
    if (out/'pipeline_manifest.json').exists():
        previous=json.loads((out/'pipeline_manifest.json').read_text())
        if previous['config_signature']!=native['config_signature']:raise RuntimeError('Output root belongs to different baseline')
    save_json(out/'pipeline_manifest.json',native)
    if a.stage=='prepare':
        if a.reuse_physics_from:
            from reuse_cached_physics import prepare
            prepare(a.reuse_physics_from,out)
        for case in a.cases:
            folder=out/case;folder.mkdir(exist_ok=True);save_json(folder/'requested_config.json',config_for(case))
        return
    cases=[case for case in a.cases if a.stage!='edits' or case!='source']
    for case in cases:
        folder=out/case;folder.mkdir(exist_ok=True);logs=folder/'logs';sim=folder/'simulation';render=folder/'render'
        if a.stage in ['all','simulate','edits']:
            cmd=[a.python,'-u',HERE/f'simulate_{STEM}.py','--output-dir',sim,'--case',case]
            if a.resume:cmd+=['--reuse-cache']
            run(cmd,logs/'simulate.log',env)
        if a.stage in ['all','keyframes','render','edits']:
            # The source must pass physics before any edit is rendered.
            source_report=json.loads((out/'source/simulation/simulation_report.json').read_text())
            if source_report['status']!='accepted':raise RuntimeError('Source physics gate failed')
            if a.stage!='keyframes':
                acceptance=json.loads((out/'static_acceptance.json').read_text())
                if acceptance['status']!='accepted':raise RuntimeError('Static visual gate has not passed')
            cmd=[a.blender,'-b','-t',a.threads,'--python-exit-code','1','--python',HERE/f'render_{STEM}.py','--',
                '--simulation-dir',sim,'--output-dir',render,'--device',a.device]
            if a.stage=='keyframes':cmd+=['--frames','1','18','24','96']
            if a.resume:cmd+=['--resume']
            run(cmd,logs/('keyframes.log' if a.stage=='keyframes' else 'render.log'),env)
        if a.stage in ['all','render','verify','edits']:
            video=folder/'video.mp4'
            if a.stage!='verify':
                command=['ffmpeg','-y','-v','error','-framerate','24','-i',render/'frames/%04d.png','-frames:v','96',
                    '-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',video]
                run(command,logs/'encode.log',env)
            run([sys.executable,ROOT/'scripts/pcve_verify_video.py',video,'--out',folder/'video_verification.json'],logs/'verify_video.log',env)
    if a.stage in ['all','verify','edits'] and all((out/c/'video_verification.json').exists() for c in CASES):
        run([a.python,HERE/'physics/verify_suite.py','--root',out],out/'suite_verify.log',env)

if __name__=='__main__':main()
