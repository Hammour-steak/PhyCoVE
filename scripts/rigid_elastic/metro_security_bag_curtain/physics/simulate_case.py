"""Native float64 CPU simulation, exact 24 Hz output; never invokes Blender."""
from pathlib import Path
import argparse,json,hashlib,time,platform,os,sys
from scene_paths import NATIVE, RUNTIME, output_path
H=Path(__file__).resolve().parent
MATH_FILES=('constitutive.py','self_contact.py','planar_rigid.py','curtain_coupling.py','shell_solver.py')
FINGERPRINT=hashlib.sha256(b''.join((H/n).read_bytes() for n in MATH_FILES)).hexdigest()
cache=RUNTIME/'numba_cache'/FINGERPRINT[:16];cache.mkdir(parents=True,exist_ok=True)
os.environ.update(NUMBA_CACHE_DIR=str(cache),CUDA_VISIBLE_DEVICES='-1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',NUMBA_NUM_THREADS='1')
if platform.system()=='Linux':sys.path.insert(0,str(RUNTIME/'linux_python'))
from shell_solver import simulate,np
from edit_vocab import CASE_DSL,LABELS,TIMED_DSL,parameters,timed_schedule
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def arrays(p,m,r,meta):
    """The states.npz arrays of one solve (24 Hz samples plus the static model)."""
    y=r[2];u=r[3];h=p['bag_dimensions_m'][2]/2
    roots=np.zeros_like(y);roots[:,:,0]=y[:,:,0]-np.sin(y[:,:,2])*h;roots[:,:,2]=y[:,:,1]-np.cos(y[:,:,2])*h
    rv=np.zeros_like(u);rv[:,:,0]=u[:,:,0]-u[:,:,2]*np.cos(y[:,:,2])*h;rv[:,:,2]=u[:,:,1]+u[:,:,2]*np.sin(y[:,:,2])*h
    euler=np.zeros_like(y);euler[:,:,1]=y[:,:,2]
    extra={k:meta.pop(k) for k in ('membrane_stiffness','bending_stiffness','collider','support_hull','support_profile','bag_mass','bag_pitch_inertia')}
    return dict(positions=r[0],velocities=r[1],bag_rigid=y,bag_rigid_velocity=u,bag_positions=roots,bag_linear_velocity=rv,bag_euler=euler,bag_q=roots[:,:,0],bag_v=rv[:,:,0],telemetry=r[4],rest_positions=m['rest'],triangles=m['tris'],uv=m['uv'],mass=m['mass'],invmass=m['invmass'],coefficients=m['coeff'],hinges=m['hinges'],strip_ids=m['strip_ids'],times=np.arange(len(r[0]))/24,**extra)
def write(dest,start,states,config):
    np.savez_compressed(dest/'states.npz',**states)
    save(dest/'simulation_config.json',config)
    y=states['bag_rigid'];roots=states['bag_positions'];rv=states['bag_linear_velocity']
    bags=y.shape[1]>0   # False only for DELETE bag (bag_present 0)
    report={'case_id':config['case_id'],'execution_host':platform.node(),'execution_platform':platform.platform(),'compute':'CPU float64 Numba; no Blender or GPU','wall_s':time.monotonic()-start,'state_sha256':hashlib.sha256((dest/'states.npz').read_bytes()).hexdigest(),'max_deflection_m':float(states['positions'][:,:,0].max()),'bag_final_q_m':roots[-1,:,0].tolist(),'bag_final_root_positions_m':roots[-1].tolist(),'bag_pitch_range_deg':[float(np.rad2deg(y[:,:,2].min())),float(np.rad2deg(y[:,:,2].max()))] if bags else None,'min_bag_speed_m_s':float(rv[:,:,0].min()) if bags else None,'not_experimental_calibration':True}
    if 'continuation' in config:report['state_handoff_max_abs_error']=config['continuation']['handoff_max_abs_error']
    save(dest/'simulation_report.json',report);print(json.dumps(report),flush=True)
def solve_named(case,tag,dt,iterations,duration,p,edit_dsl,label,diagnostic=False,out_root=None):
    dest=output_path(out_root)/case
    if dest.exists():raise FileExistsError('Preserve previous native states: '+str(dest))
    start=time.monotonic();m,r,meta=simulate(p,dt=dt,iterations=iterations,duration=duration)
    dest.mkdir(parents=True,exist_ok=False);states=arrays(p,m,r,meta)
    write(dest,start,states,{'scene_id':'metro_security_bag_curtain','case_id':case,'physics':p,'edit_dsl':edit_dsl,'label_zh':label,'diagnostic_only':diagnostic,'solver':meta,'fps':24,'frames_for_video':round(duration*24),'native_caches_recomputed':True})
FRAME_FIELDS=('positions','velocities','bag_rigid','bag_rigid_velocity','bag_positions','bag_linear_velocity','bag_euler','bag_q','bag_v')
def solve_timed(case,dt,iterations,source_dir,out_root=None,schedule=None):
    """Timed edit AT FRAME k: restore the source state of frame k (t=(k-1)/24) exactly, apply the edit
    there and continue the same solver to t=4 s; frames 1..k-1 are the source states unchanged."""
    dest=output_path(out_root)/case
    if dest.exists():raise FileExistsError('Preserve previous native states: '+str(dest))
    schedule=schedule if schedule is not None else timed_schedule(case);assert len(schedule)==1,'One timed change per case'
    k=int(schedule[0]['frame']);t0=(k-1)/24;base=parameters('source')
    source_dir=Path(source_dir)
    source_cfg=json.loads((source_dir/'simulation_config.json').read_text(encoding='utf-8'))
    assert source_cfg['case_id']=='source' and source_cfg['physics']==base,'The source cache was not solved with the baseline parameters'
    assert source_cfg['solver']['dt_s']==dt and source_cfg['solver']['iterations']==iterations,'Continue with the source dt and iteration count'
    with np.load(source_dir/'states.npz',allow_pickle=False) as data:src={key:data[key] for key in data.files}
    assert len(src['times'])==97 and abs(src['times'][k-1]-t0)<1e-12
    p=dict(base);p.update(schedule[0]['params'])
    start=time.monotonic();seed={key:src[key][k-1] for key in ('positions','velocities','bag_rigid','bag_rigid_velocity')}
    m,r,meta=simulate(p,dt=dt,iterations=iterations,duration=(97-k)/24,initial_state=seed)
    cont=arrays(p,m,r,meta)
    handoff={key:float(np.max(np.abs(cont[key][0]-src[key][k-1]))) for key in FRAME_FIELDS}
    assert max(handoff.values())<1e-8,('Source state was not restored exactly',handoff)
    merged=dict(cont)
    for key in FRAME_FIELDS:merged[key]=np.concatenate([src[key][:k-1],cont[key]])
    merged['times']=np.arange(97)/24
    assert np.allclose(np.concatenate([src['times'][:k-1],t0+cont['times']]),merged['times'],atol=1e-12,rtol=0)
    for key in FRAME_FIELDS:assert merged[key].shape==src[key].shape and np.array_equal(merged[key][:k-1],src[key][:k-1])
    rows=int(round(t0*240));tele=cont['telemetry'].copy();tele[:,0]+=t0
    merged['telemetry']=np.concatenate([src['telemetry'][:rows],tele])
    merged['curtain_present_per_frame']=np.array([1]*(k-1)+[int(p['curtain_present'][0])]*(98-k),dtype=np.int8)
    merged['timed_edit_frame']=np.array(k)
    dest.mkdir(parents=True,exist_ok=False)
    source_sha=hashlib.sha256((source_dir/'states.npz').read_bytes()).hexdigest()
    write(dest,start,merged,{'scene_id':'metro_security_bag_curtain','case_id':case,'physics':base,'timed_edits':schedule,'edit_dsl':TIMED_DSL.get(case),'label_zh':LABELS.get(case,case),'diagnostic_only':case not in TIMED_DSL,'solver':meta,'fps':24,'frames_for_video':96,'native_caches_recomputed':True,
        'continuation':{'method':'restore the exact float64 source state of frame k (curtain vertex positions/velocities, bag COM x/z/pitch and their velocities) and keep solving with the edited parameters',
            'source_states':str(source_dir/'states.npz'),'source_states_sha256':source_sha,'edit_frame':k,'start_time_s':t0,'frames_from_source':[1,k-1],'frames_solved':[k,96],
            'physics_after_edit':p,'handoff_max_abs_error':handoff,'telemetry_note':'work and dissipation columns restart from zero at the edit frame'}})
def main():
    a=argparse.ArgumentParser();a.add_argument('--case',default='source',help='a case of edit_vocab.CASE_DSL or TIMED_DSL, or all');a.add_argument('--tag',required=True);a.add_argument('--out-root',type=Path,required=True);a.add_argument('--dt',type=float,default=1/9600);a.add_argument('--iterations',type=int,default=12);a.add_argument('--duration',type=float,default=4)
    a.add_argument('--source-cache',type=Path,default=NATIVE/'source',help='timed edits: folder with the source states.npz and simulation_config.json to continue from');args=a.parse_args()
    out_root=output_path(args.out_root)
    for case in (CASE_DSL if args.case=='all' else [args.case]):
        if case in TIMED_DSL:solve_timed(case,args.dt,args.iterations,args.source_cache,out_root=out_root)
        else:solve_named(case,args.tag,args.dt,args.iterations,args.duration,parameters(case),CASE_DSL[case],LABELS[case],out_root=out_root)
if __name__=='__main__':main()
