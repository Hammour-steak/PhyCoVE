"""Fixed-camera Cycles rendering of unmodified, solver-produced SI poses."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == '__main__':
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    if _PcvePath(__file__).with_name('entrypoints.json').is_file():
        _pcve_sys.path.insert(0,str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__,'render')
# PCVE_UNIFIED_ENTRY_END
import argparse, copy, hashlib, json, os, subprocess, sys, time
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parent/'appearance'))
from simulate_domino_chain import signature
from look_domino_chain import material, look_at, resin_material, domino, desk_environment, setup_lighting

ROOT=Path(__file__).resolve().parents[3]


def dump(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


def setup_scene(cfg,physics):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc=bpy.context.scene;sc.unit_settings.system='METRIC';sc.unit_settings.scale_length=1
    # Persistent data stays off: with motion blur on, Blender 4.3 can drop
    # objects that have come to rest from later frames of the same session.
    sc.render.engine='CYCLES';sc.render.use_persistent_data=False;sc.cycles.samples=cfg['render']['samples'];sc.cycles.use_denoising=True
    sc.cycles.max_bounces=8;sc.cycles.diffuse_bounces=4;sc.cycles.glossy_bounces=4
    sc.render.resolution_x,sc.render.resolution_y=cfg['render']['resolution'];sc.render.resolution_percentage=100
    sc.render.fps=cfg['render']['fps'];sc.frame_start=1;sc.frame_end=physics['frame_end']
    sc.view_settings.view_transform='AgX';sc.view_settings.look='AgX - Medium High Contrast'
    sc.view_settings.exposure=0;sc.view_settings.gamma=1
    sc.render.film_transparent=False
    sc.render.use_motion_blur=True;sc.render.motion_blur_shutter=cfg['render']['motion_blur_shutter_frames']
    sc.render.image_settings.file_format='PNG';sc.render.image_settings.color_mode='RGB'
    ap=cfg['appearance'];formation=ap.get('image_formation',{})
    sc.cycles.pixel_filter_type=formation.get('pixel_filter_type','BLACKMAN_HARRIS')
    sc.cycles.filter_width=float(formation.get('pixel_filter_width_px',1.5))
    env=desk_environment(cfg)
    mats={'resin':resin_material(ap['domino']),'pip':material('Black inset pips',(.004,.0045,.004,1),.18),
          'ink':material('Subtle factory identity ink',(.035,.032,.026,1),.5),
          'wear':material('Faint resin handling scuffs',(.64,.62,.55,1),.46)}
    anchors=[]
    for index,active in enumerate(cfg['physics']['domino_active']):
        anchors.append(domino(index,cfg,mats) if active else None)
    for anchor in anchors:
        if anchor:anchor.rotation_mode='QUATERNION'
    # Dense solved samples, not designed tipping curves; physics owns every transform.
    for record in physics.get('trajectory_samples',physics['frames']):
        for obj,pose in zip(anchors,record['dominoes']):
            if obj is None:continue
            if not pose['present']:continue
            obj.location=pose['location'];x,y,z,w=pose['quaternion_xyzw'];obj.rotation_quaternion=(w,x,y,z)
            obj.keyframe_insert(data_path='location',frame=record['frame_index'])
            obj.keyframe_insert(data_path='rotation_quaternion',frame=record['frame_index'])
    for obj in anchors:
        if obj and obj.animation_data:
            for fc in obj.animation_data.action.fcurves:
                for k in fc.keyframe_points:k.interpolation='LINEAR'
    camcfg=ap['camera'];bpy.ops.object.camera_add(location=camcfg['location']);cam=bpy.context.object;cam.name='Fixed oblique side camera'
    look_at(cam,camcfg['target']);cam.data.lens=camcfg['lens_mm'];cam.data.sensor_width=camcfg['sensor_width_mm']
    cam.data.clip_start=.003;cam.data.clip_end=30;cam.data.dof.use_dof=True
    focus=bpy.data.objects.new('Focus on D03 contact region',None);bpy.context.collection.objects.link(focus);focus.location=camcfg['target']
    cam.data.dof.focus_object=focus;cam.data.dof.aperture_fstop=camcfg['f_stop'];sc.camera=cam
    setup_lighting(cfg)
    from sunlit_room_realism import apply_realism
    env=apply_realism(cfg,env)
    from photographic_finish import apply_finish
    env=apply_finish(cfg,env)
    for event in physics.get('interventions',[]):
        index=int(event['object_id'][1:])-1
        anchor=anchors[index]
        if anchor is None:continue
        for obj in [anchor,*anchor.children_recursive]:
            for attribute in ['hide_render','hide_viewport']:
                original=getattr(obj,attribute)
                setattr(obj,attribute,original);obj.keyframe_insert(data_path=attribute,frame=1)
                setattr(obj,attribute,True);obj.keyframe_insert(data_path=attribute,frame=event['frame_index'])
            if obj.animation_data:
                for curve in obj.animation_data.action.fcurves:
                    if curve.data_path in ['hide_render','hide_viewport']:
                        for key in curve.keyframe_points:key.interpolation='CONSTANT'
    sc.frame_set(1)
    return sc,anchors,env


def device(name):
    if name=='cpu':return 'CPU'
    prefs=bpy.context.preferences.addons['cycles'].preferences
    for backend in ['OPTIX','CUDA']:
        try:
            prefs.compute_device_type=backend;prefs.get_devices()
            gpu=[d for d in prefs.devices if d.type==backend]
            if not gpu:continue
            for d in prefs.devices:d.use=d in gpu
            bpy.context.scene.cycles.device='GPU'
            return backend+': '+', '.join(d.name for d in gpu)
        except Exception:continue
    bpy.context.scene.cycles.device='CPU';return 'CPU'


def ground_truth(physics,cfg):
    objects={f'D{i+1:02}':{'object_id':f'D{i+1:02}','mass_kg':m,'present':bool(cfg['physics']['domino_active'][i])} for i,m in enumerate(cfg['physics']['domino_masses'])}
    for event in physics.get('interventions',[]):
        objects[event['object_id']]['absent_from_frame']=event['frame_index']
        objects[event['object_id']]['removal_time_sec']=event['time_sec']
    frames=[]
    for f in physics['frames']:
        frames.append({'frame_index':f['frame_index'],'time_sec':f['time_sec'],
                       'objects':{v['object_id']:v for v in f['dominoes']},'dominoes':f['dominoes']})
    return {'schema_version':3,'units':{'length':'m','mass':'kg','time':'s'},
            'fps':physics['fps'],'frames':frames,'objects':objects,'camera':cfg['appearance']['camera'],
            'contact_events':physics['contact_events'],'tilt_threshold_times_sec':physics['tilt_threshold_times_sec'],
            'trajectory_source':physics.get('trajectory_provenance',{}).get('description','Direct PyBullet output; no hand-authored tipping animation'),
            'playback_rate':1.0,'time_mapping':'Video time equals solver time; gravity is recorded in configuration.physics.',
            'configuration_sha256':signature(cfg)}


def parse_args():
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['preview','animation','frames'],default='animation')
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path,required=True)
    p.add_argument('--appearance-json',type=Path);p.add_argument('--preview-frame',type=int,default=1);p.add_argument('--keyframes',nargs='*',type=int)
    p.add_argument('--resolution',nargs=2,type=int);p.add_argument('--fps',type=int);p.add_argument('--duration-sec',type=float)
    p.add_argument('--samples',type=int);p.add_argument('--device',choices=['auto','cpu'],default='auto')
    return p.parse_args(argv)


def main():
    args=parse_args();out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=json.loads(args.physics_json.read_text());cfg=copy.deepcopy(physics['configuration'])
    if args.appearance_json:
        override=json.loads(args.appearance_json.read_text())
        if set(override)!={'appearance'}:raise ValueError('An appearance override may only contain the appearance section.')
        cfg['appearance']=override['appearance']
    for key in ['resolution','samples','fps','duration_sec']:
        val=getattr(args,key)
        if val is not None and val!=cfg['render'][key]:
            raise ValueError(f'Render must match frozen physics configuration: {key} {val} != {cfg["render"][key]}')
    sc,anchors,env=setup_scene(cfg,physics);backend=device(args.device)
    metadata={'schema_version':3,**cfg,'physics_input':str(args.physics_json.resolve()),'physics_input_sha256':hashlib.sha256(args.physics_json.read_bytes()).hexdigest(),
              'configuration_sha256':signature(cfg),'blender_version':bpy.app.version_string,'render_backend':backend,
              'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES'),'dimension_ledger':env,
              'appearance_override_input':str(args.appearance_json.resolve()) if args.appearance_json else None,
              'invariant_appearance_sha256':signature(cfg['appearance']),'invariant_simulation_quality_sha256':signature(cfg['simulation_quality'])}
    dump(out/'scenario_metadata.json',metadata);dump(out/'ground_truth_transforms.json',ground_truth(physics,cfg))
    bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'domino_chain.blend'))
    start=time.perf_counter()
    if args.mode=='preview':
        sc.frame_set(args.preview_frame);sc.render.filepath=str(out/f'preview_{args.preview_frame:04}.png');bpy.ops.render.render(write_still=True)
    elif args.mode=='frames':
        for f in args.keyframes or [1,11,17,21,24,31,60,96]:
            sc.frame_set(f);sc.render.filepath=str(out/f'frame_{f:04}.png');bpy.ops.render.render(write_still=True)
    else:
        frames=out/'frames';frames.mkdir(exist_ok=True)
        sc.render.filepath=str(frames/'frame_');sc.render.use_file_extension=True
        bpy.ops.render.render(animation=True)
    render_sec=time.perf_counter()-start;encode_sec=0
    if args.mode=='animation':
        start=time.perf_counter()
        credit=[]
        if cfg['appearance']['domino'].get('asset_kind')=='sketchfab':
            credit=['-metadata','comment=Dominoes by Render at Night; https://sketchfab.com/3d-models/dominoes-6b89d69fe15748efa113e26354736507; CC BY 4.0 https://creativecommons.org/licenses/by/4.0/; adapted: rescaled to 50x25x8 mm, materials and D01-D05 IDs.']
        subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-framerate',str(cfg['render']['fps']),'-start_number','1','-i',str(out/'frames/frame_%04d.png'),
                        '-frames:v',str(physics['frame_end']),'-c:v','libx264','-preset','slow','-crf',str(cfg['appearance'].get('image_formation',{}).get('video_crf',17)),'-pix_fmt','yuv420p','-movflags','+faststart',*credit,str(out/'video.mp4')],check=True)
        encode_sec=time.perf_counter()-start
        subprocess.run([sys.executable,str(ROOT/'scripts/pcve_verify_video.py'),str(out/'video.mp4'),
                        '--out',str(out/'video_validation.json'),'--resolution',*[str(x) for x in cfg['render']['resolution']],
                        '--fps',str(cfg['render']['fps']),'--frames',str(physics['frame_end'])],check=True)
    dump(out/'render_report.json',{'render_sec':render_sec,'encode_sec':encode_sec,'mode':args.mode,'backend':backend,
                                   'frame_count':physics['frame_end'] if args.mode=='animation' else len(args.keyframes or [1]),
                                   'image_formation':{'pixel_filter_type':sc.cycles.pixel_filter_type,'pixel_filter_width_px':sc.cycles.filter_width,'video_crf':cfg['appearance'].get('image_formation',{}).get('video_crf',17)}})
    print(json.dumps({'render_sec':render_sec,'encode_sec':encode_sec,'output':str(out),'backend':backend}),flush=True)


if __name__=='__main__':main()
