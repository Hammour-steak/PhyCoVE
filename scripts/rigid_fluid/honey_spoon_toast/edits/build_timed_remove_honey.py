"""Build the timed edit DELETE honey AT FRAME k from an accepted source run of the honey thread model.

The fixed spoon, toast and plate have no state that the honey changes, so the edit is exact: frames 1..k-1 are the
source run's own cache files (hard links) and from frame k on every honey component (reservoir, meniscus buffer,
thread and puddle) is empty and nothing more is fed. All 96 frames are then rendered from the source scene template
by render_honey_spoon_toast.py --remove-honey-from-frame k (the honey object is removed at frame k) and encoded.
"""
import argparse,copy,hashlib,json,math,re,shutil,subprocess,sys,time
from pathlib import Path
import numpy as np
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO, asset, blender

ROOT=REPO
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import edit_vocab  # noqa: E402
import pcve_edit_dsl as dsl  # noqa: E402
FPS,FRAMES=edit_vocab.FPS,edit_vocab.FRAMES
SOURCE_RUN=ROOT/'renders/pcve_suites/pcve_honey_spoon_toast_suite/inputs/04_realtime_runs/rope_source'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.new')
    temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False))
    temporary.replace(path)

def link(origin,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    try:target.hardlink_to(origin)
    except OSError:shutil.copy2(origin,target)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-root',type=Path,required=True)
    p.add_argument('--source-run',type=Path,default=SOURCE_RUN,
                   help='accepted source run of the thread model (particles, rope_states, meshes_smooth, filament_meshes)')
    p.add_argument('--source-template',type=Path,default=asset('scenes/honey_spoon_toast/scene_template.blend'))
    p.add_argument('--blender',type=Path,default=blender())
    p.add_argument('--threads',type=int,default=16,help='Blender threads')
    p.add_argument('--edit-dsl',default=edit_vocab.EDIT_DSL['remove_honey_at_frame_51'])
    a=p.parse_args()
    match=re.fullmatch(r'DELETE\s+honey\s+AT\s+FRAME\s+(\d+)',a.edit_dsl.strip())
    if not match:p.error('This entry implements DELETE honey AT FRAME <n> only')
    event=int(match[1]);assert 2<=event<=FRAMES
    out=a.out_root.expanduser().resolve();assert not out.exists(),f'Use a fresh output directory: {out}'
    source=a.source_run.resolve()
    source_template=a.source_template.resolve()
    source_report=load(source/'simulation_report.json')
    assert source_report['status']=='complete' and source_report['numerics']['frames']==FRAMES
    assert all(row['spoon_tilt_deg']==15 for row in source_report['frames'])
    out.mkdir(parents=True)
    start=time.perf_counter();run=out/'simulation';run.mkdir()
    components=[('particles','frame_'),('rope_states','rope_'),('meshes_smooth','honey_'),('filament_meshes','honey_')]
    for directory,_ in components:(run/directory).mkdir()
    event_state=source_report['frames'][event-1]
    pv=source_report['hybrid_model']['particle_volume_m3']
    volume=(event_state['reservoir_particles']*pv*1e6 + sum(event_state[k] for k in ['meniscus_buffer_volume_ml','thread_volume_ml','deposited_volume_ml']))
    with np.load(source/'particles/frame_0001.npz') as initial_state:
        initial=len(initial_state['honey_pos'])*pv*1e6
    assert math.isclose(volume,initial,rel_tol=1e-9)
    with np.load(source/'rope_states'/f'rope_{event:04d}.npz') as original:
        rope={k:original[k].copy() for k in original.files}
    with np.load(source/'particles'/f'frame_{event:04d}.npz') as bulk:
        actual_volume=(len(bulk['honey_pos'])*pv + rope['vol'].sum() + float(rope['pending'])
                       + float(rope['buffer']) + rope['film_h'].sum()*float(rope['film_cell'])**2)*1e6
    assert math.isclose(actual_volume,volume,rel_tol=1e-9)
    for key in ['x','v']:rope[key]=np.empty((0,3),np.float64)
    for key in ['vol','radius']:rope[key]=np.empty(0,np.float64)
    rope['on']=np.empty(0,bool);rope['film_h']=np.zeros_like(rope['film_h'])
    rope['pending']=np.asarray(0.);rope['buffer']=np.asarray(0.)
    empty_mesh={'vertices':np.empty((0,3),np.float32),'triangles':np.empty((0,3),np.int32)}
    edited=copy.deepcopy(source_report)
    edited.pop('source_frames',None)
    source_contact_diagnostics={key:edited['physics'].pop(key) for key in
        ['contact_projection_count','maximum_contact_projection_m'] if key in edited['physics']}
    first_contact=source_report.get('first_contact_frame')
    if first_contact is not None and first_contact>=event:first_contact=None
    prefix_breakups=[item for item in source_report.get('breakup_events',[])
                    if item['physics_time_s']<event_state['physics_time_s']]
    edited.update(case_id=out.name,solver=source_report['solver']+'; exact empty-state continuation after timed deletion',
        initial_particles=source_report['particles'],particle_count_semantics='Initial count; active reservoir counts are in frames.',
        source_provenance={'run':str(source),'simulation_report_sha256':sha(source/'simulation_report.json'),
                           'original_simulation_seconds':source_report['simulation_seconds'],
                           'original_full_run_contact_diagnostics':source_contact_diagnostics},
        first_contact_frame=first_contact,breakup_events=prefix_breakups,build_seconds=0.,simulation_seconds=0.,thread_simulation_seconds=0.)
    rows=[];cache_identity=0
    for f in range(1,FRAMES+1):
        row=copy.deepcopy(source_report['frames'][f-1])
        if f<event:
            for directory,prefix in components:
                origin=source/directory/f'{prefix}{f:04d}.npz';target=run/directory/origin.name
                link(origin,target);assert sha(origin)==sha(target);cache_identity+=1
        else:
            np.savez(run/'particles'/f'frame_{f:04d}.npz',honey_pos=np.empty((0,3),np.float32),honey_vel=np.empty((0,3),np.float16))
            np.savez(run/'rope_states'/f'rope_{f:04d}.npz',**rope)
            for directory in ['meshes_smooth','filament_meshes']:np.savez(run/directory/f'honey_{f:04d}.npz',**empty_mesh)
            for key,value in row.items():
                if key not in ['frame','playback_time_s','physics_time_s','spoon_tilt_deg']:
                    row[key]=None if value is None else 0
            row['lowest_thread_z_above_toast_m']=None
        row.update(honey_present=f<event,feed_enabled=f<event,removed_honey_volume_ml=volume if f>=event else 0.)
        rows.append(row)
    edited['frames']=rows
    edited['event']={'dsl':a.edit_dsl,'frame':event,'video_time_s':(event-1)/FPS,
        'physics_time_s':event_state['physics_time_s'],'before':event_state,'removed_volume_ml':volume,
        'removed_mass_kg':volume*1e-6*source_report['physics']['honey_density_kg_m3'],
        'after':{'reservoir_particles':0,'rope_nodes':0,'meniscus_buffer_volume_ml':0.,'thread_volume_ml':0.,'deposited_volume_ml':0.,'feed_enabled':False},
        'semantics':'Delete all honey, including reservoir, hanging thread, buffer and any deposit; no further feed.'}
    edited['state_edit_seconds']=time.perf_counter()-start
    write(run/'simulation_report.json',edited)
    for f in range(event,FRAMES+1):
        with np.load(run/'particles'/f'frame_{f:04d}.npz') as d:assert d['honey_pos'].shape==d['honey_vel'].shape==(0,3)
        with np.load(run/'rope_states'/f'rope_{f:04d}.npz') as d:
            assert d['x'].size==d['vol'].size==0 and not np.any(d['film_h']) and float(d['buffer'])==float(d['pending'])==0
        for directory in ['meshes_smooth','filament_meshes']:
            with np.load(run/directory/f'honey_{f:04d}.npz') as d:assert d['vertices'].shape==d['triangles'].shape==(0,3)
    before={'physics':{'honey_delete_frame':None,'initial_honey_volume_ml':initial,'density_kg_m3':1420.,'kinematic_viscosity_m2_s':.008,'spoon_tilt_deg':15.},
            'simulation_quality':source_report['numerics'],'appearance':{'template_sha256':sha(source_template)},
            'render':{'resolution':[1280,720],'samples':32,'fps':FPS,'frames':FRAMES,'duration_s':4.,'crf':18}}
    after=copy.deepcopy(before);after['physics']['honey_delete_frame']=event
    write(out/'configuration_diff.json',{'before':before,'after':after})
    write(out/'prompts.json',{'case_id':out.name,'edit_dsl':a.edit_dsl,
        'prompts':dsl.make_prompts(dsl.parse(a.edit_dsl,edit_vocab.VOCAB),edit_vocab.VOCAB),
        'applies_from_frame':event,'application_time_sec':(event-1)/FPS,'unedited_frames':[1,event-1],
        'cache_prefix_files_byte_identical':cache_identity})
    render=out/'render';start=time.perf_counter()
    with (out/'render.log').open('w') as log:
        subprocess.run([str(a.blender),'-b','-t',str(a.threads),'--python-exit-code','1','--python',str(HERE.parent/'render_honey_spoon_toast.py'),
                        '--','--input-blend',str(source_template),'--run',str(run),'--out-dir',str(render),'--samples','32',
                        '--mesh-subdir','meshes_smooth','--extra-mesh-subdir','filament_meshes',
                        '--frames',*map(str,range(1,FRAMES+1)),'--remove-honey-from-frame',str(event),'--encode'],
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    render_seconds=time.perf_counter()-start
    video=render/'honey_spoon_toast.mp4'
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries',
        'stream=width,height,avg_frame_rate,nb_read_frames:format=duration','-of','json',str(video)],text=True))
    st=probe['streams'][0];assert (st['width'],st['height'],st['avg_frame_rate'],int(st['nb_read_frames']))==(1280,720,'24/1',FRAMES)
    assert float(probe['format']['duration'])==FRAMES/FPS
    subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],check=True)
    report=load(render/'render_report.json')
    assert [row['frame'] for row in report['frames']]==list(range(1,FRAMES+1))
    assert [row['honey_present'] for row in report['frames']]==[f<event for f in range(1,FRAMES+1)]
    validation={'status':'technical_passed_visual_pending','video_sha256':sha(video),'media':probe,
                'source_prefix_cache_files_byte_identical':cache_identity,'all_post_event_honey_state_empty':True,
                'all_post_event_meshes_empty':True,'all_frames_rendered':FRAMES,'removed_honey_volume_ml':volume,
                'first_contact_frame':first_contact,'render_seconds':render_seconds}
    write(out/'validation.json',validation)
    print(json.dumps({'case':str(out),'video_sha256':sha(video),'event_frame':event,'video_time_s':(event-1)/FPS,'status':validation['status']},indent=2))

if __name__=='__main__':main()
