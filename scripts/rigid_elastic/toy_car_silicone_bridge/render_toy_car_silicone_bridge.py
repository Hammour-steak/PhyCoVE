"""Cycles render of cached solved geometry; never changes physical trajectories."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import scene_asset
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
        _pcve_prepare_entry(__file__,'render')
# PCVE_UNIFIED_ENTRY_END
import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
from pathlib import Path
import importlib
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from bridge_physics import save_json,digest
from pcve_assets import asset as shared_asset

def geometry_module(cfg):
    """The scene builder (appearance/scene_geometry.py)."""
    return importlib.import_module('scene_geometry')

def shared_model_files(cfg):
    """sha256 of every registry file of the shared CC0 models, checked against assets.json."""
    names=list(cfg['appearance'].get('shared_models',{}))
    if not names:return {},{}
    registry=json.loads((Path(__file__).resolve().parents[3]/'assets.json').read_text())['assets']
    found,expected={},{}
    for name in names:
        for rel,info in registry[name]['files'].items():
            found[f'shared/{name}/{rel}']=hashlib.sha256((shared_asset(name)/rel).read_bytes()).hexdigest()
            expected[f'shared/{name}/{rel}']=info['sha256']
    return found,expected

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simulation-dir',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--frames',nargs='+',type=int,help='1-based keyframes at full formal quality')
    p.add_argument('--device',choices=['OPTIX','CUDA','METAL','CPU'],default='OPTIX')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--allow-diagnostic-input',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])
    a.simulation_dir=a.simulation_dir.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    render_lock=(out/'render.lock').open('a+')
    fcntl.flock(render_lock,fcntl.LOCK_EX)
    cfg=json.loads((a.simulation_dir/'config.json').read_text());report=json.loads((a.simulation_dir/'simulation_report.json').read_text())
    if report['status']!='accepted' and not a.allow_diagnostic_input:raise RuntimeError('Physics gate failed: '+str(a.simulation_dir))
    geometry=geometry_module(cfg);build_scene,apply_frame=geometry.build_scene,geometry.apply_frame
    signature=digest(cfg)
    cache_hash=hashlib.sha256((a.simulation_dir/'simulation.npz').read_bytes()).hexdigest()
    pbr_root=scene_asset(Path(__file__).resolve().parent, 'assets/pbr')
    material_files={str(p.relative_to(pbr_root)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(pbr_root.rglob('*')) if p.suffix.lower() in ['.jpg','.hdr','.gltf','.bin','.png','.exr','.blend']}
    pinned=json.loads(Path(__file__).with_name('asset_sources.json').read_text())
    expected={str(Path(entry['id'])/f.get('relative_path',f['name'])):f['sha256']
              for entry in pinned['assets'] for f in entry['provenance']['files']}
    generated_root=scene_asset(Path(__file__).resolve().parent, 'assets/generated')
    drape=cfg['appearance']['basket_drape']
    generated_provenance=json.loads((generated_root/drape['provenance']).read_text())
    generated_name='generated/'+generated_provenance['files'][0]
    material_files[generated_name]=hashlib.sha256((generated_root/generated_provenance['files'][0]).read_bytes()).hexdigest()
    expected[generated_name]=generated_provenance['sha256']
    shared_found,shared_expected=shared_model_files(cfg)
    material_files.update(shared_found);expected.update(shared_expected)
    if material_files!=expected:raise RuntimeError('Pinned material/model dependencies differ: run fetch_assets.py / download_assets.py')
    material_hash=digest(material_files)
    if (out/'render_input.json').exists():
        old=json.loads((out/'render_input.json').read_text())
        if old['config_sha256']!=signature:raise RuntimeError('Existing render root has different inputs')
        if old.get('material_sha256')!=material_hash:raise RuntimeError('Existing render root has different texture maps')
        if old['cache_sha256']!=cache_hash and list((out/'frames').glob('*.png')):raise RuntimeError('Existing frames belong to a different solved cache')
    save_json(out/'render_input.json',{'config_sha256':signature,'cache':str(a.simulation_dir/'simulation.npz'),
        'cache_sha256':cache_hash,
        'appearance':cfg['appearance'],'render':cfg['render'],'blender':bpy.app.version_string,
        'material_sha256':material_hash,'material_files_sha256':material_files})
    start=time.monotonic();data=np.load(a.simulation_dir/'simulation.npz');objects=build_scene(cfg,data);sc=bpy.context.scene
    if a.device!='CPU':
        pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type=a.device;pref.get_devices()
        devices=[]
        for device in pref.devices:
            device.use=device.type==a.device
            if device.use:devices.append(device.name)
        if not devices:raise RuntimeError('Requested render device not available: '+a.device)
        sc.cycles.device='GPU'
    else:devices=['CPU'];sc.cycles.device='CPU'
    apply_frame(data,0,*objects)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
    frames=a.frames or list(range(1,cfg['render']['frames']+1));times=[];(out/'frames').mkdir(exist_ok=True)
    for frame in frames:
        if not 1<=frame<=cfg['render']['frames']:raise ValueError(frame)
        target=out/'frames'/f'{frame:04d}.png'
        if target.exists() and a.resume:continue
        if target.exists():raise RuntimeError('Frame exists; use --resume: '+str(target))
        apply_frame(data,frame-1,*objects);sc.frame_set(frame);sc.render.filepath=str(target)
        t=time.monotonic();bpy.ops.render.render(write_still=True);times.append({'frame':frame,'seconds':time.monotonic()-t})
        save_json(out/'render_progress.json',{'rendered':times,'device':devices,'samples':sc.cycles.samples,'resolution':[sc.render.resolution_x,sc.render.resolution_y]})
    stamp=f'keyframes_{"_".join(map(str,frames))}' if a.frames else 'full'
    save_json(out/f'timing_{stamp}.json',{'elapsed_s':time.monotonic()-start,'frames':times,'devices':devices,
        'quality':cfg['render'],'mode':'formal quality keyframes' if a.frames else 'formal full render',
        'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES')})

if __name__=='__main__':main()
