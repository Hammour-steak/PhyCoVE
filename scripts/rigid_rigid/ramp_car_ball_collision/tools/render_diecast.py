"""Render a prepared packed-template suite with measured exact-pose reuse only.

render_template_suite.py uses its scene setup and render-state signatures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import bpy

WORK=Path(__file__).resolve().parent
SCENE_CODE=WORK/'scene' if (WORK/'scene').is_dir() else WORK.parent
sys.path.insert(0,str(SCENE_CODE/'tools'))
from prepare_diecast import set_poses
from object_presence import CAR_ROOTS,remove_roots,keyframe_presence,active_roots,apply_frame_presence


def dump(path,value):
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    os.replace(temp,path)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def choose_backend(scene,backend):
    if backend=='CPU':scene.cycles.device='CPU';return 'CPU'
    preferences=bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type=backend
    preferences.get_devices()
    devices=[d for d in preferences.devices if d.type==backend]
    assert devices, 'Requested backend unavailable: '+backend
    for device in preferences.devices:device.use=device in devices
    scene.cycles.device='GPU'
    return backend+': '+', '.join(d.name for d in devices)


def state_signature(scene,roots,frame,configuration=None):
    if configuration is not None:roots=active_roots(roots,configuration,frame)
    states=[]
    for subframe in [-scene.render.motion_blur_shutter/2,0,scene.render.motion_blur_shutter/2]:
        value=frame+subframe
        whole=int(value)
        scene.frame_set(whole,subframe=value-whole)
        bpy.context.view_layer.update()
        states.append({name:[float(x) for row in root.matrix_world for x in row] for name,root in roots.items()})
    scene.frame_set(frame);bpy.context.view_layer.update()
    return hashlib.sha256(json.dumps({'frame':frame,'states':states},sort_keys=True).encode()).hexdigest()


def setup(folder,template,backend,threads):
    bpy.ops.wm.open_mainfile(filepath=str(template))
    result=json.loads((folder/'physics_transforms.json').read_text())
    roots={name:bpy.data.objects[name] for name in ['car_body','wheel_0','wheel_1','wheel_2','wheel_3']}
    if result['configuration']['physics']['ball']['present']:
        roots['ball']=bpy.data.objects['ball']
    else:
        obj=bpy.data.objects['ball']
        for child in list(obj.children_recursive):bpy.data.objects.remove(child,do_unlink=True)
        bpy.data.objects.remove(obj,do_unlink=True)
    if not result['configuration']['physics']['car'].get('present',True):remove_roots(roots,CAR_ROOTS)
    set_poses(roots,result)
    keyframe_presence(roots,result['configuration'])
    scene=bpy.context.scene
    scene.render.threads_mode='FIXED';scene.render.threads=threads
    scene.render.use_persistent_data=False
    scene.cycles.use_denoising=True;scene.cycles.denoising_use_gpu=False
    assert scene.cycles.samples==128 and scene.render.resolution_x==1280 and scene.render.resolution_y==720
    assert scene.render.fps==24 and scene.frame_end==96
    return scene,roots,choose_backend(scene,backend)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out-root',type=Path,required=True)
    parser.add_argument('--backend',choices=['CPU','METAL','CUDA','OPTIX'],default='METAL')
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--benchmark',type=int)
    parser.add_argument('--frame-start',type=int,default=1)
    parser.add_argument('--frame-end',type=int,default=96)
    parser.add_argument('--no-encode',action='store_true',help='Render frames on a node without ffmpeg; encode after collection')
    parser.add_argument('--cases',nargs='+',default=['source','edit_heavy_ball','edit_low_restitution','edit_remove_ball'])
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    out=args.out_root.resolve()
    template=out/'source_template.blend'
    manifest=json.loads((out/'suite_manifest.json').read_text())
    if args.benchmark:
        folder=out/'cases/source';scene,roots,backend=setup(folder,template,args.backend,args.threads)
        scene.frame_set(args.benchmark);bpy.context.view_layer.update()
        scene.render.filepath=str(out/('benchmark_'+args.backend.lower()+'.png'))
        start=time.monotonic();bpy.ops.render.render(write_still=True)
        dump(out/('benchmark_'+args.backend.lower()+'.json'),{'backend':backend,'render_sec':time.monotonic()-start,'samples':128,'resolution':[1280,720]})
        return
    bank={}
    template_hash=sha(template)
    record={'status':'rendering','requested_cases':args.cases,'requested_frame_range':[args.frame_start,args.frame_end],'backend':args.backend,'samples':128,'resolution':[1280,720],'fps':24,'total_frames_per_case':96,'cases':{}}
    records={r['case_id']:r for r in [manifest['source']]+manifest['edits']}
    for case_id in args.cases:
        folder=out/'cases'/case_id
        frames=folder/'frames';frames.mkdir(exist_ok=True)
        scene,roots,backend=setup(folder,template,args.backend,args.threads)
        record.update(current_case=case_id,current_frame=0,backend=backend)
        dump(out/'render_execution.json',record)
        timings={};reused=[]
        configuration=json.loads((folder/'settings.json').read_text())
        keys={str(frame):state_signature(scene,roots,frame,configuration) for frame in range(1,97)}
        signature_path=folder/'render_state_signatures.json'
        signatures={'template_sha256':template_hash,'frame_keys':keys}
        if signature_path.exists():assert json.loads(signature_path.read_text())==signatures
        else:dump(signature_path,signatures)
        for frame in range(args.frame_start,args.frame_end+1):
            path=frames/('frame_%04d.png'%frame)
            key=keys[str(frame)]
            apply_frame_presence(roots,configuration,frame)
            scene.frame_set(frame);bpy.context.view_layer.update()
            if not path.exists() and key in bank:
                original=bank[key]
                shutil.copy2(original['path'],path)
                reused.append({'frame':frame,'from_case':original['case_id'],'from_frame':original['frame'],'state_sha256':key,'png_sha256':sha(path)})
            elif not path.exists():
                scene.render.filepath=str(path)
                start=time.monotonic();bpy.ops.render.render(write_still=True)
                timings[str(frame)]=time.monotonic()-start
            bank.setdefault(key,{'path':path,'case_id':case_id,'frame':frame})
            record.update(current_frame=frame,current_frame_wall_sec=timings.get(str(frame),0.))
            dump(out/'render_execution.json',record)
        start=time.monotonic();complete=all((frames/('frame_%04d.png'%f)).is_file() for f in range(1,97))
        if complete and not args.no_encode:
            subprocess.run(['ffmpeg','-y','-v','error','-threads','2','-framerate','24','-i',str(frames/'frame_%04d.png'),
                '-frames:v','96','-an','-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'video.mp4')],check=True)
        case={'status':('frames_rendered_pending_encode' if args.no_encode else 'rendered_pending_review') if complete else 'requested_frames_complete_waiting_for_source_prefix','rendered_frame_count':len(timings),'reused_frame_count':len(reused),'frame_seconds':timings,
              'encode_sec':time.monotonic()-start,'video_sha256':sha(folder/'video.mp4') if complete and not args.no_encode else None,'backend':backend,
              'template_sha256':template_hash,'reused_frames':reused,'reuse_scope':'Exact root matrices at shutter start, center and end; same frame index, packed template and appearance; no approximately equal poses or image interpolation'}
        dump(folder/'render_execution.json',case)
        records[case_id]['status']=case['status']
        records[case_id]['video_sha256']=case['video_sha256']
        record['cases'][case_id]={k:v for k,v in case.items() if k not in ['frame_seconds','reused_frames']}
        dump(out/'suite_manifest.json',manifest);dump(out/'render_execution.json',record)
        print('CASE_COMPLETE',case_id,flush=True)
    assert sha(template)==template_hash
    record['status']='requested_cases_rendered_pending_review'
    dump(out/'render_execution.json',record)
    print('ALL_RENDERED',flush=True)


if __name__=='__main__':main()
