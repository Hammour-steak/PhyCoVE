"""Create benchmark sidecars and hash manifest without invoking Blender."""

from pathlib import Path
import argparse,hashlib,json,sys
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from pcve_assets import asset
SPEC=json.loads(asset('scenes/steel_ball_tensioned_membrane/scene_spec.json').read_text(encoding='utf-8'))

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case-dir',type=Path,required=True);ap.add_argument('--case',required=True);a=ap.parse_args();d=a.case_dir.resolve();z=np.load(d/'simulation.npz');cfg=json.loads((d/'simulation_config.json').read_text())
    if cfg.get('case')!=a.case:raise ValueError(f'config case {cfg.get("case")} != CLI case {a.case}')
    times=np.asarray(z['times'],float);fps=round(1/float(np.median(np.diff(times)))) if len(times)>1 else SPEC['fps']
    if len(times)>1 and not np.allclose(np.diff(times),1/fps,rtol=0,atol=1e-10):raise ValueError('nonuniform or inconsistent simulation times')
    second_present=bool(z['second_ball_present'][0])
    gt={'schema_version':2,'scene_id':cfg['scene_id'],'case_id':a.case,'fps':fps,'quaternion_order':'wxyz','object_ids':['ball','second_ball'],'object_presence':{'ball':bool(cfg['physics']['ball_present']),'second_ball':second_present},'frames':[]}
    video_frame_count=len(times)-1
    gt['simulation_endpoint_s']=float(times[-1]);gt['video_frame_count']=video_frame_count
    for i,(t,T) in enumerate(zip(z['times'][:video_frame_count],z['ball_transforms'][:video_frame_count])):
        # Sphere orientation is retained as the full native affine matrix.
        second_T=z['second_ball_transforms'][i]
        gt['frames'].append({'frame_index':i+1,'time_s':float(t),'ball_transform_4x4':T.tolist(),'objects':{'ball':{'present':True,'transform_4x4':T.tolist()},'second_ball':{'present':second_present,'transform_4x4':second_T.tolist() if second_present else None}}})
    (d/'ground_truth_transforms.json').write_text(json.dumps(gt,indent=2),encoding='utf-8')
    deform={'schema_version':1,'object_id':'membrane','object_present':bool(cfg['physics']['membrane_present']),'topology':'fixed indexed triangle surface','positions_file':'simulation.npz','positions_key':'membrane_positions','faces_key':'membrane_faces','units':'m','native_solver':True,'hand_authored':False,'frame_count':len(z['times']),'vertex_count':len(z['membrane_rest_positions']),'face_count':len(z['membrane_faces'])}
    deform.update(frame_count=video_frame_count,cache_state_count=len(times),video_state_indices=list(range(video_frame_count)),simulation_endpoint_s=float(times[-1]))
    (d/'deformation_manifest.json').write_text(json.dumps(deform,indent=2),encoding='utf-8')
    environment={'shared_environment_id':'steel_ball_tensioned_membrane_university_mechanics_lab','camera_shared_across_cases':True,'lighting_shared_across_cases':True,'render_seed_shared':True,'assets':[{'name':'University Workshop 4K HDRI','source':'https://polyhaven.com/a/university_workshop','author':'Savva Zakharov','license':'CC0','use':'university laboratory background, reflections and ambient illumination'},{'name':'Professional controlled-impact workcell','source':'procedural metric construction informed by laboratory equipment references','license':'project authored','use':'optical breadboard, T-slot release gantry with centred cantilever electromagnet, bolted clamp ring with flanged posts, rigid-post high-speed camera, split photogates, LED panel, DAQ rack and routed cabling'},{'name':'Rigid sphere(s) and elastic membrane','source':'native simulation cache plus procedural render geometry','license':'project authored','use':'visible geometry; physical states are replayed without pose or deformation edits'}],'product_references_not_copied':[{'name':'Newport M-IG optical table','source':'https://www.newport.com/p/M-IG-46-2'},{'name':'Instron drop tower systems','source':'https://www.instron.com/en/resources/test-types/tensile-impact-test-drop-tower/'},{'name':'Photron FASTCAM Mini AX','source':'https://photron.com/fastcam-mini-ax/'},{'name':'NI CompactDAQ','source':'https://www.ni.com/en-us/shop/compactdaq.html'}]}
    (d/'environment_manifest.json').write_text(json.dumps(environment,indent=2),encoding='utf-8')
    files=['video.mp4','prompts.json','ground_truth_transforms.json','simulation.npz','simulation_config.json','simulation_report.json','render_report.json','deformation_manifest.json','environment_manifest.json','scene.blend']
    manifest={'schema_version':1,'scene_id':cfg['scene_id'],'case_id':a.case,'release_class':'development_candidate','material_calibrated':False,'accepted_benchmark_gt':False,'artifacts':[]}
    for name in files:
        path=d/name
        if not path.exists():raise FileNotFoundError(path)
        # Data files carry their hash; JSON records are listed by name only.
        manifest['artifacts'].append({'path':name} if name.endswith('.json') else {'path':name,'bytes':path.stat().st_size,'sha256':sha(path)})
    (d/'artifact_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('FINALIZED',a.case,len(manifest['artifacts']))
if __name__=='__main__':main()
