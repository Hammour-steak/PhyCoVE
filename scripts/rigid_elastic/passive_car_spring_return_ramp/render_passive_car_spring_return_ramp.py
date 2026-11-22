"""Formal Cycles images from solved rigid poses and spring compression."""
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
import hashlib
import json
import os
import sys
import time
from pathlib import Path
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scene_config import digest,save_json
from scene_geometry import build_scene,apply_frame
from appearance_config import effective_configuration,asset_signature

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--simulation-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--frames',nargs='+',type=int);p.add_argument('--device',choices=['OPTIX','CUDA','CPU'],default='OPTIX');p.add_argument('--resume',action='store_true');p.add_argument('--graybox',action='store_true')
    p.add_argument('--appearance-config',type=Path,help='Appearance-only overlay, defaults to the canonical current preset')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]);out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    solved_cfg=json.loads((a.simulation_dir/'config.json').read_text());cfg=effective_configuration(solved_cfg,a.appearance_config);report=json.loads((a.simulation_dir/'simulation_report.json').read_text())
    if report['status']!='accepted':raise RuntimeError('Physics gate failed')
    inputs={'config_sha256':digest(solved_cfg),'effective_config_sha256':digest(cfg),'cache':str((a.simulation_dir/'simulation.npz').resolve()),'cache_sha256':hashlib.sha256((a.simulation_dir/'simulation.npz').read_bytes()).hexdigest(),
            'asset_dependency_sha256':asset_signature(),'graybox':a.graybox,'appearance':cfg['appearance'],'render':cfg['render'],'blender':bpy.app.version_string}
    if (out/'render_input.json').is_file() and json.loads((out/'render_input.json').read_text())!=inputs:raise RuntimeError('Render output contains different inputs')
    save_json(out/'render_input.json',inputs);save_json(out/'render_config.json',cfg)
    from scene_config import differences
    save_json(out/'appearance_diff.json',{'before':solved_cfg,'after':cfg,'differences':differences(solved_cfg,cfg)})
    start=time.monotonic();data=np.load(a.simulation_dir/'simulation.npz');objects=build_scene(cfg,data,a.graybox);sc=bpy.context.scene
    devices=['CPU']
    if a.device!='CPU':
        pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type=a.device;pref.get_devices();devices=[]
        for dev in pref.devices:
            dev.use=dev.type==a.device
            if dev.use:devices.append(dev.name)
        if not devices:raise RuntimeError('Requested GPU backend unavailable')
        sc.cycles.device='GPU'
    else:sc.cycles.device='CPU'
    apply_frame(cfg,data,0,objects);bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
    if not a.graybox:
        assets=scene_asset(Path(__file__).resolve().parent, 'assets');assets.mkdir(parents=True,exist_ok=True)
        recipe=digest({'appearance':cfg['appearance'],'assets':inputs['asset_dependency_sha256']})
        library=assets/f'gravity_track_{recipe[:12]}.blend'
        if not library.exists():bpy.data.libraries.write(str(library),set(bpy.data.objects),fake_user=True)
        save_json(assets/f'provenance_{recipe[:12]}.json',{'source':'Original toy/room geometry; CC0 PBR/HDRI/duck and detailed book meshes; retained original watercolor book print',
            'license':'Original geometry follows project code; individual asset provenance per assets/realism/manifest.json','units':'metres',
            'appearance':cfg['appearance'],'asset_dependency_sha256':inputs['asset_dependency_sha256'],
            'recipe_sha256':recipe,'library':str(library),'reproduction':'Render one source frame with the canonical render entry'})
    frames=a.frames or list(range(1,cfg['render']['frames']+1));(out/'frames').mkdir(exist_ok=True);times=[]
    for frame in frames:
        if not 1<=frame<=cfg['render']['frames']:raise ValueError(frame)
        path=out/'frames'/f'{frame:04d}.png'
        if path.exists():
            if a.resume:continue
            raise RuntimeError('Frame exists; use --resume: '+str(path))
        apply_frame(cfg,data,frame-1,objects);sc.frame_set(frame);sc.render.filepath=str(path);t=time.monotonic();bpy.ops.render.render(write_still=True)
        times.append({'frame':frame,'elapsed_s':time.monotonic()-t});save_json(out/'render_progress.json',{'completed':times,'devices':devices,'samples':sc.cycles.samples})
    stamp='keyframes_'+'_'.join(map(str,frames)) if a.frames else 'full'
    save_json(out/f'timing_{stamp}.json',{'elapsed_s':time.monotonic()-start,'frames':times,'devices':devices,'quality':cfg['render'],'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES')})

if __name__=='__main__':main()
