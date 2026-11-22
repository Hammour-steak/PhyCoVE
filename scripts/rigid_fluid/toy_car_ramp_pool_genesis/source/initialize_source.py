"""Isolate and verify the exact 96-frame physical take, then start surface processing."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
import numpy as np
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO
W=Path(__file__).resolve().parent.parent
P=json.loads((W/'source_plan.json').read_text()); R=Path(P['root']); C=Path(P['candidate_run'])
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(8*1024*1024),b''):h.update(c)
    return h.hexdigest()
R.mkdir(exist_ok=True);run=R/'simulation/run';(run/'particles').mkdir(parents=True,exist_ok=True)
assert len(list((C/'particles').glob('frame_*.npz')))==96
files={};rows=[];last=None;max_step=0.;max_speed=0.
sim=json.loads((C/'simulation_report.json').read_text())
assert sim['physics']['car_mass_kg']==.42
for f in range(1,97):
    src=C/'particles'/f'frame_{f:04d}.npz';dst=run/'particles'/src.name
    if not dst.exists():os.link(src,dst)
    digest=sha(src);assert sha(dst)==digest;files[str(src.relative_to(C))]=digest
    with np.load(dst) as d:
        x=d['water_pos'];v=d['water_vel'];pos=d['car_pos'];q=d['car_quat_wxyz']
        assert x.shape==(95277,3) and v.shape==x.shape and np.isfinite(x).all() and np.isfinite(v).all()
        assert np.allclose(pos,sim['frames'][f-1]['car_pos'],atol=1e-7)
        assert np.allclose(q,sim['frames'][f-1]['car_quat_wxyz'],atol=1e-7)
        if last is not None:max_step=max(max_step,float(np.median(np.linalg.norm(x-last,axis=1))))
        last=x.copy();max_speed=max(max_speed,float(np.max(np.linalg.norm(v,axis=1))))
        assert abs(float(np.linalg.norm(q))-1)<1e-5
        rows.append({'frame':f,'time_s':(f-1)/24,'water_particles':len(x),'water_z_max_m':float(x[:,2].max()),'pose_matches_report':True})
for name in ['simulation_report.json','actual_configuration.json','force_runtime.json']:
    shutil.copy2(C/name,run/name);files[name]=sha(C/name)
write(R/'selected_cache_inventory.json',{'candidate':str(C),'isolated_run':str(run),'files':files,'immutable_particle_hardlinks':True})
write(R/'physical_acceptance.json',{'status':'all_96_frozen_physical_frames_verified','frames':rows,
      'selection':P['selection'],'maximum_median_particle_step_m':max_step,'maximum_water_particle_speed_m_s':max_speed,
      'manual_pose_changes':False,'physics_recomputed':False})
shutil.copy2(W/'source_plan.json',R/'source_plan.json')
env=os.environ.copy();env.update(OMP_NUM_THREADS='16',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
with (W/'surface.log').open('w') as f:
    surface=subprocess.Popen(P['commands']['surface'],env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
with (W/'pipeline.log').open('w') as f:
    pipeline=subprocess.Popen([str(REPO / '.venv-genesis-mpm-sph/bin/python'),str(W/'source/pipeline_source.py')],env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
write(W/'launch_jobs.json',{'time_unix':time.time(),'surface_pid':surface.pid,'pipeline_pid':pipeline.pid,'candidate':str(C)})
print(json.dumps({'status':'selected_source_surface_and_pipeline_launched','surface_pid':surface.pid,'pipeline_pid':pipeline.pid}),flush=True)
