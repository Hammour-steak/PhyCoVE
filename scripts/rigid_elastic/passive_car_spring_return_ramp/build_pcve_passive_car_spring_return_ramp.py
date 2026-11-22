"""Public PCVE staged pipeline with independent cache roots and acceptance gates."""
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender
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
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from scene_config import SCENE,CASES,baseline,config_for,save_json,digest
from appearance_config import effective_configuration,asset_signature

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def run(cmd,log,env):
    log.parent.mkdir(parents=True,exist_ok=True);started=time.monotonic();cmd=list(map(str,cmd));print('RUN',json.dumps(cmd),flush=True)
    with log.open('w') as f:result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
    save_json(log.with_suffix('.json'),{'command':cmd,'elapsed_s':time.monotonic()-started,'exit_code':result.returncode})
    if result.returncode:raise RuntimeError(log.read_text()[-5000:])
    print('DONE',log.name,round(time.monotonic()-started,2),'s',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--stage',choices=['all','prepare','simulate','keyframes','render','verify','edits'],default='all')
    p.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES));p.add_argument('--resume',action='store_true')
    p.add_argument('--simulation-root',type=Path,help='Reuse accepted case caches from this root; never run the solver')
    p.add_argument('--appearance-config',type=Path,help='Appearance-only overlay, defaults to current scene preset')
    p.add_argument('--python',type=Path,default=ROOT/'.venv-toy-car-bridge/bin/python')
    p.add_argument('--blender',type=Path,default=blender())
    p.add_argument('--gpu');p.add_argument('--threads',type=int,default=8);p.add_argument('--device',choices=['OPTIX','CUDA','CPU'],default='OPTIX')
    a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.simulation_root and a.stage in ['all','simulate','edits']:raise RuntimeError('Use prepare/keyframes/render/verify for appearance-only cache reuse')
    reference=a.simulation_root.resolve() if a.simulation_root else None
    effective=effective_configuration(baseline(),a.appearance_config)
    env={**os.environ,'OMP_NUM_THREADS':str(a.threads),'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    if a.gpu is not None:env['CUDA_VISIBLE_DEVICES']=a.gpu
    if a.stage in ['all','render','keyframes','edits'] and a.device!='CPU' and 'CUDA_VISIBLE_DEVICES' not in env:
        raise RuntimeError('Inspect current resources and select --gpu explicitly, or use --device CPU')
    manifest={'scene':SCENE,'config_sha256':digest(baseline()),'effective_appearance_sha256':digest(effective['appearance']),
              'simulation_reference_root':str(reference) if reference else None,'cases':list(CASES),'root':str(out),
              'resources':{'gpu':env.get('CUDA_VISIBLE_DEVICES'),'threads':a.threads,'python':str(a.python),'blender':str(a.blender)}}
    if (out/'pipeline_manifest.json').is_file():
        previous=json.loads((out/'pipeline_manifest.json').read_text())
        if any(previous.get(k)!=manifest[k] for k in ['config_sha256','effective_appearance_sha256','simulation_reference_root']):raise RuntimeError('Output root belongs to a different baseline or appearance')
    save_json(out/'pipeline_manifest.json',manifest)
    snapshot=out/'reproduction';snapshot.mkdir(exist_ok=True)
    for f in [*HERE.iterdir(), *(_p for _s in ('physics', 'appearance', 'tools', 'docs') if (HERE / _s).is_dir() for _p in sorted((HERE / _s).iterdir()))]:
        if f.is_file() and f.suffix in ['.py','.md','.json','.txt']:
            target=snapshot/f.relative_to(HERE);target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() and target.read_bytes()!=f.read_bytes():
                # Immutable source snapshot by content; never erase previous evidence.
                target=target.with_name(f.stem+'_'+hashlib.sha256(f.read_bytes()).hexdigest()[:12]+f.suffix)
            if not target.exists():shutil.copy2(f,target)
    save_json(out/'source_file_hashes.json',{str(f.relative_to(snapshot)):hashlib.sha256(f.read_bytes()).hexdigest() for f in snapshot.rglob('*') if f.is_file()})
    if reference:
        for case in a.cases:
            src=reference/case/'simulation';dst=out/case/'simulation'
            if src.resolve()==dst.resolve():raise RuntimeError('Use a fresh output root for appearance revisions')
            if json.loads((src/'simulation_report.json').read_text())['status']!='accepted':raise RuntimeError('Reference physics gate failed: '+case)
            if not dst.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(src,dst)
            for f in src.iterdir():
                if f.is_file() and (not(dst/f.name).is_file() or hashlib.sha256(f.read_bytes()).digest()!=hashlib.sha256((dst/f.name).read_bytes()).digest()):raise RuntimeError('Copied cache differs from accepted reference: '+str(f))
    if a.stage=='prepare':
        run([a.python,HERE/'tools/prepare_assets.py'],out/'prepare_assets.log',env)
        for case in a.cases:
            folder=out/case;folder.mkdir(exist_ok=True);save_json(folder/'requested_config.json',config_for(case))
            save_json(folder/'requested_render_config.json',effective_configuration(config_for(case),a.appearance_config))
        return
    selected=[c for c in a.cases if c!='source' or a.stage!='edits']
    for case in selected:
        folder=out/case;folder.mkdir(exist_ok=True);logs=folder/'logs';sim=folder/'simulation';render=folder/'render'
        if a.stage in ['all','simulate','edits']:
            cmd=[a.python,HERE/f'simulate_{SCENE}.py','--output-dir',sim,'--case',case]
            if a.resume:cmd+=['--reuse-cache']
            run(cmd,logs/'simulate.log',env)
        if a.stage in ['all','keyframes','render','edits']:
            source=json.loads((out/'source/simulation/simulation_report.json').read_text())
            if source['status']!='accepted':raise RuntimeError('Source physics gate failed')
            if a.stage!='keyframes':
                gate=json.loads((out/'static_acceptance.json').read_text())
                if gate['status']!='accepted':raise RuntimeError('Formal static image review has not passed')
                if gate['appearance_sha256']!=digest(effective['appearance']):raise RuntimeError('Static acceptance has a different camera/appearance')
                if gate['asset_dependency_sha256']!=asset_signature():raise RuntimeError('Texture dependencies changed after static review')
            cmd=[a.blender,'-b','-t',a.threads,'--python-exit-code','1','--python',HERE/f'render_{SCENE}.py','--',
                 '--simulation-dir',sim,'--output-dir',render,'--device',a.device]
            if a.appearance_config:cmd+=['--appearance-config',a.appearance_config]
            if a.stage=='keyframes':cmd+=['--frames','1','24','29','34','39','53','96']
            if a.resume:cmd+=['--resume']
            run(cmd,logs/('keyframes.log' if a.stage=='keyframes' else 'render.log'),env)
        if a.stage in ['all','render','verify','edits']:
            video=folder/'video.mp4'
            if a.stage!='verify':
                cmd=['ffmpeg','-n','-v','error','-framerate','24','-i',render/'frames/%04d.png','-frames:v','96','-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',video]
                if not(video.exists() and a.resume):run(cmd,logs/'encode.log',env)
            run([a.python,HERE/'physics/verify_suite.py','--root',out,'--cases',case,'--video'],logs/'verify.log',env)
    if a.stage in ['all','verify','edits'] and all((out/c/'video.mp4').exists() for c in CASES):
        run([a.python,HERE/'physics/verify_suite.py','--root',out,'--video'],out/'suite_verify.log',env)

if __name__=='__main__':main()
