"""Build isolated cases and matched controls on observed idle GPUs."""
import json,os,subprocess,time,traceback
from pathlib import Path
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO, asset
W=Path(__file__).resolve().parent.parent;P=json.loads((W/'edit_plan.json').read_text());R=Path(P['root'])
PY=str(REPO / '.venv-genesis-mpm-sph/bin/python')
G=asset('scenes/toy_car_ramp_pool_genesis/geometry_h105')
STATE=str(REPO / 'renders/toy_car_ramp_pool_genesis/reference_source/simulation/settle_final/water_state.npz')
def write(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
def status(stage,**kw):write(W/'physics_status.json',dict(stage=stage,updated_unix=time.time(),**kw))
jobs=[]
cases=P['cases']+[{'id':'viscosity_control_32','root':str(R/'controls/viscosity_control_32'),
        'physics':P['cases'][3]['physics']|{'water_kinematic_viscosity_m2_s':1.004e-6},'substeps':32,'event_time_s':None},
        {'id':'restart_control','root':str(R/'controls/restart_control'),'physics':P['cases'][4]['physics'],'substeps':4,'event_time_s':None}]
try:
    pending=cases.copy();batch=0
    while pending:
        raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True)
        snapshot=[list(map(int,l.split(','))) for l in raw.strip().splitlines()]
        available=sorted([g for g in snapshot if g[3]<10 and g[2]>14000],key=lambda g:g[1])
        if not available:status('waiting_for_idle_gpu');time.sleep(10);continue
        active=[]
        for c,gpu in zip(pending[:3],available):
            name=c['id'];run=Path(c['root'])/'simulation/run';run.parent.mkdir(parents=True,exist_ok=True)
            restart=name in ['mass_after_2s_x3','restart_control'];phys=c['physics']
            argv=[PY,str(W/'source'/('restart_at_2s.py' if restart else 'simulate_timed_mass.py')),'run','--out',str(run),
                '--water-state',STATE,'--frames','96','--dx','.010','--water-height','.105','--steps-per-frame','8',
                '--substeps',str(c['substeps']),'--settle-frames','72','--floor-projection','--wall-projection',
                '--basin-collider',str(G/'pool_visual_collider.obj'),'--initial-volume',str(G/'water_initial_basin.obj'),
                '--basin-profile',str(G/'basin_profile.npz'),'--car-mass',str(phys['car_mass_kg']),
                '--water-density',str(phys['water_density_kg_m3']),'--water-viscosity',str(phys['water_kinematic_viscosity_m2_s'])]
            if name=='no_car':argv+=['--no-car']
            if c['event_time_s'] is not None:argv+=['--mass-change-time','2.0','--mass-multiplier','3']
            env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES=str(gpu[0]),OMP_NUM_THREADS='8',OPENBLAS_NUM_THREADS='8',MKL_NUM_THREADS='8',
                    REBASE_SOURCE_RUN=P['baseline']+'/simulation/run')
            log=W/f'physics_{name}.log'
            with log.open('w') as f:process=subprocess.Popen(argv,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
            jobs.append(dict(id=name,pid=process.pid,gpu=gpu[0],argv=argv,log=str(log),time_unix=time.time()))
            active.append((c,process))
        del pending[:len(active)];batch+=1
        write(W/'physics_jobs.json',jobs);status('simulating',batch=batch,active=[c['id'] for c,p in active])
        for c,p in active:
            if p.wait()!=0:raise RuntimeError('Physics failed '+c['id'])
            assert (Path(c['root'])/'simulation/run/simulation_report.json').exists(),c['id']
    assert len(jobs)==len(cases),'Some cases were not launched due to GPU count'
    status('all_seven_runs_complete')
except Exception as exc:status('failed',error=str(exc),traceback=traceback.format_exc());raise
