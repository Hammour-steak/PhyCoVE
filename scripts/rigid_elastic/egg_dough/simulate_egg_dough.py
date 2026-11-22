#!/usr/bin/env python3
"""Simulate one independent, gravity-equilibrated rigid/viscoelastic-dough case."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=='__main__':
 import sys
 from pathlib import Path
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
 from pcve_scene_entry import prepare_entry
 prepare_entry(__file__,'simulate')
# PCVE_UNIFIED_ENTRY_END
import argparse,os,time,json
from pathlib import Path
import numpy as np
from dough_config import config,CASES,write_json,digest,choose_gpu,preset_names,asset_directory

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=CASES,default='source');p.add_argument('--preset',choices=preset_names());p.add_argument('--out-dir',type=Path,required=True)
 p.add_argument('--initial-state-from',type=Path,help='Copy the verified source initial state; apply this case material at t=0 and allow its precontact gravity response');p.add_argument('--asset-dir',type=Path);p.add_argument('--frames',type=int,default=96);p.add_argument('--steps-per-frame',type=int,default=2048);p.add_argument('--gpu',default='auto');p.add_argument('--initial-equilibrium',choices=['relaxed_static','explicit_warmup'],default='relaxed_static');p.add_argument('--unload-after',type=float,default=-1.,help='Diagnostic only: delete sphere after this time; never used in formal cases')
 a=p.parse_args();out=a.out_dir.resolve()
 if a.initial_state_from and (a.case=='source' or a.initial_equilibrium!='relaxed_static'):p.error('--initial-state-from is for edited cases and cannot be combined with explicit warmup')
 if out.exists() and any(out.iterdir()):raise FileExistsError(out)
 out.mkdir(parents=True,exist_ok=True);gpu=choose_gpu(a.gpu);os.environ['CUDA_VISIBLE_DEVICES']=gpu
 import taichi as ti
 from fem_viscoelastic import DoughBall,pose
 c=config(a.case,a.preset);c['case']=a.case
 # A shared physical initial state may have been rendered later with a newer
 # look. Preserve the source simulation's appearance record here so the paired
 # simulation diff remains physical-only; render_egg_dough applies the current
 # appearance file independently.
 if a.initial_state_from:
  source_sim_config=json.loads((a.initial_state_from.parent/'actual_config.json').read_text())
  c['appearance']=source_sim_config['appearance']
 ball_present=bool(c['physics']['ball'].get('present',True));q=c['simulation_quality'];q['initial_equilibrium']='source_state_t0_edit' if a.initial_state_from else a.initial_equilibrium;q['frames']=a.frames;q['steps_per_frame']=a.steps_per_frame;q['dt_s']=1/(24*a.steps_per_frame)
 if a.unload_after>=0:c['diagnostic_unload_after_s']=a.unload_after
 a.asset_dir=a.asset_dir or asset_directory(c)
 meta=json.loads((a.asset_dir/'asset_manifest.json').read_text());assert abs(meta.get('xy_scale',1.)-c['physics']['dough']['geometry_xy_scale'])<1e-12;assert meta.get('profile','domed_pad')==c['physics']['dough'].get('geometry_profile','domed_pad');q['mesh_spacing_m']=meta['spacing_m'];q['vertical_layers']=meta['layers']
 d=dict(np.load(a.asset_dir/'geometry.npz'));source_state=None;source_metadata={}
 if a.initial_state_from:
  from source_initial_state import load_source_state
  source_state,c['initialization'],source_metadata=load_source_state(a.initial_state_from,c,digest(a.asset_dir/'geometry.npz'))
 write_json(out/'actual_config.json',c);start=time.monotonic()
 ti.init(arch=ti.cpu if gpu=='cpu' else ti.cuda,default_fp=ti.f64,offline_cache=True,device_memory_GB=2,cpu_max_num_threads=8)
 solid=DoughBall(c,d);dt=solid.dt;sub=a.steps_per_frame;fps=24
 equilibrium_metadata={}
 if source_state is not None:
  from source_initial_state import apply_source_state
  apply_source_state(solid,source_state);equilibrium_metadata=source_metadata;elapsed=0.;speed=float(np.linalg.norm(source_state['velocities'],axis=1).max())
  print(json.dumps({'phase':'source_state_t0_edit',**source_metadata}),flush=True)
 elif solid.present and a.initial_equilibrium=='relaxed_static':
  from equilibrate_dough import equilibrate
  equilibrium_metadata=equilibrate(solid,c,d);elapsed=0.;speed=0.
  print(json.dumps({'phase':'static_equilibrium',**equilibrium_metadata}),flush=True)
 elif solid.present:
  elapsed=0.;speed=1.
  while elapsed<q['settle_max_s']-dt:
   for _ in range(round(.1/dt)):solid.step(0,-1.)
   elapsed+=round(.1/dt)*dt;speed=float(np.linalg.norm(solid.v.to_numpy(),axis=1).max())
   print(json.dumps({'phase':'settle','case':a.case,'time_s':elapsed,'max_speed_m_s':speed,'minJ':float(solid.minJ[None]),'wall_s':time.monotonic()-start}),flush=True)
   if elapsed>=q['settle_min_s']-.5*dt and speed<q['settle_max_speed_m_s']:break
  if speed>q['settle_max_speed_m_s']:raise RuntimeError('No acceptable gravity equilibrium')
 else:elapsed=0.;speed=0.
 settled=solid.x.to_numpy();initial_v=solid.v.to_numpy();initial_fv=solid.fvi.to_numpy();initial_ev=solid.ev.to_numpy()
 np.savez_compressed(out/'initial_state.npz',vertices=settled,velocities=initial_v,viscous_inverse=initial_fv,accumulated_viscous_strain=initial_ev)
 write_json(out/'equilibrium_report.json',{'duration_s':elapsed,'maximum_nodal_speed_m_s':speed,'max_viscous_strain':float(initial_ev.max()),'ball_held_at_release_pose':ball_present,'egg_present':ball_present,'fixed_nodes':0,'same_world_continuation':True,**equilibrium_metadata})
 solid.reset_accounting();mass=solid.mass.to_numpy();totmass=mass.sum() if solid.present else 0.
 def momenta(x,v,bp,bv,bw):
  P=(mass[:,None]*v).sum(0) if solid.present else np.zeros(3);L=np.cross(x,mass[:,None]*v).sum(0) if solid.present else np.zeros(3)
  if ball_present:return P+solid.M*bv,L+np.cross(bp,solid.M*bv)+solid.rigid_angular_momentum()
  return P,L
 initial=solid.state();P0,L0=momenta(*initial[:5]);com0=(settled*mass[:,None]).sum(0)/mass.sum();restc=settled-com0;edge=np.sqrt((d['rest_vertices'][:,0]/(.060*c['physics']['dough']['geometry_xy_scale']))**2+(d['rest_vertices'][:,1]/(.050*c['physics']['dough']['geometry_xy_scale']))**2)>.85
 def shape_metrics(xx):
  com=(xx*mass[:,None]).sum(0)/mass.sum();xc=xx-com;U,sv,Vt=np.linalg.svd((restc*mass[:,None]).T@xc);RR=U@np.diag([1,1,np.linalg.det(U@Vt)])@Vt;residual=xc-restc@RR
  return float(np.linalg.norm(residual,axis=1).max()),float(np.linalg.norm(xx[edge]-settled[edge],axis=1).max()),com-com0
 records=[];vertices=[];velocities=[];transforms=[];ballv=[];ballw=[];epframes=[];trace=[];contact_snapshot_saved=False
 # 97 simulation samples include the exact t=4 endpoint; video uses first 96.
 for frame in range(a.frames+1):
  x,v,bp,bv,bw,bq=solid.state();vertices.append(x.astype(np.float32));velocities.append(v.astype(np.float32));transforms.append(pose(bp,bq));ballv.append(bv);ballw.append(bw);epframes.append(solid.ev.to_numpy().astype(np.float32))
  if not all(np.isfinite(z).all() for z in (x,v,bp,bv,bw)):raise RuntimeError('Non-finite state')
  if float(solid.minJ[None])<.25:raise RuntimeError('Unsafe element compression/inversion')
  com=(x*mass[:,None]).sum(0)/mass.sum();disp=x-settled;local=disp-(com-(settled*mass[:,None]).sum(0)/mass.sum())
  records.append({'time_s':frame/fps,'ball_position_m':bp.tolist(),'ball_velocity_m_s':bv.tolist(),'ball_angular_velocity_rad_s':bw.tolist(),
   'maximum_local_deformation_m':float(np.linalg.norm(local,axis=1).max()) if solid.present else None,
   'dough_com_displacement_m':(com-(settled*mass[:,None]).sum(0)/mass.sum()).tolist() if solid.present else None,'max_accumulated_viscous_strain':float(solid.ev.to_numpy().max()) if solid.present else None})
  if frame==a.frames:break
  for step in range(sub):
   t=(frame*sub+step+1)*dt;use=not(a.unload_after>=0 and t>a.unload_after)
   solid.step(int(use and ball_present),t)
   if step%max(1,sub//16)==0:
    if source_state is not None and not contact_snapshot_saved and float(solid.first_contact[None])>=0:
     np.savez_compressed(out/'first_contact_state.npz',vertices=solid.x.to_numpy(),time_s=t,first_actual_contact_time_s=float(solid.first_contact[None]));contact_snapshot_saved=True
    md,ed,cd=shape_metrics(solid.x.to_numpy()) if solid.present else (0.,0.,np.zeros(3))
    trace.append([t,*np.array(solid.bp[None]),*np.array(solid.bv[None]),*np.array(solid.bw[None]),float(solid.contactN[None]),float(solid.instant_gap[None]),float(solid.current_energy[None]),float(solid.relaxation_work[None]),float(solid.visc_work[None]),md,ed,*cd])
  if frame%4==0:print(json.dumps({'case':a.case,'frame':frame+1,'ball_z_m':float(solid.bp[None][2]),'max_pen_m':float(solid.max_pen[None]),'minJ':float(solid.minJ[None]),'relaxation_work_J':float(solid.relaxation_work[None]),'wall_s':time.monotonic()-start}),flush=True)
 final=solid.state();P,L=momenta(*final[:5]);rp=P-P0-np.array(solid.extP[None]);rl=L-L0-np.array(solid.extL[None]);ep=solid.ev.to_numpy()
 np.savez_compressed(out/'simulation_cache.npz',vertices=np.array(vertices),velocities=np.array(velocities),rest_vertices=d['rest_vertices'],settled_vertices=settled,
  rigid_vertices=solid.rigid_vertices,rigid_faces=solid.rigid_faces,rigid_inertia_body_kg_m2=solid.I,tetrahedra=d['tetrahedra'],dough_faces=d['surface_triangles'],dough_present=solid.present,ball_present=ball_present,ball_transforms=np.array(transforms),ball_velocities=np.array(ballv),ball_angular_velocities=np.array(ballw),
  accumulated_viscous_strain=np.array(epframes),final_viscous_inverse=solid.fvi.to_numpy(),time_s=np.arange(a.frames+1)/fps,trace=np.array(trace))
 receipt={'case':a.case,'egg_present':ball_present,'simulation_wall_seconds':time.monotonic()-start,'gpu':gpu,'software':{'taichi':ti.__version__,'numpy':np.__version__},'mesh_sha256':digest(a.asset_dir/'geometry.npz'),
  'cache_sha256':digest(out/'simulation_cache.npz'),'rigid_geometry_sha256':c['physics']['ball']['rigid_geometry_sha256'],'rigid_geometry_kind':'mesh signed-distance contact with matching visual boundary','rigid_angular_integrator':'World angular momentum, full body inertia rotated each step; quaternion orientation','nodes':solid.n,'tetrahedra':solid.ne,'dough_mass_kg':float(totmass),
  'minimum_detF':float(solid.minJ[None]) if solid.present else None,'maximum_ball_dough_quadrature_penetration_m':float(solid.max_pen[None]),'maximum_table_quadrature_penetration_m':float(solid.max_table_pen[None]),
  'relaxation_work_J':float(solid.relaxation_work[None]),'viscous_work_J':float(solid.visc_work[None]),'contact_dissipation_work_J':float(solid.contact_work[None]),'rolling_resistance_work_J':float(solid.rolling_work[None]),'max_accumulated_viscous_strain':float(ep.max()) if solid.present else None,
  'relaxed_volume_fraction':float(d['volumes'][ep>1e-6].sum()/d['volumes'].sum()) if solid.present else None,'first_ball_dough_contact_s':float(solid.first_contact[None]),'peak_ball_dough_force_N':float(solid.peak_force[None]),
  'linear_momentum_balance_residual_kg_m_s':rp.tolist(),'angular_momentum_balance_residual_kg_m2_s':rl.tolist(),
  'frames':records,'trace_columns':['t_s','ball_x','ball_y','ball_z','vx','vy','vz','wx','wy','wz','normal_contact_N','minimum_quadrature_gap_m','stored_energy_J','relaxation_work_J','viscous_work_J','maximum_rigid_fit_removed_deformation_m','maximum_edge_world_displacement_m','dough_com_dx_m','dough_com_dy_m','dough_com_dz_m']}
 write_json(out/'simulation_receipt.json',receipt);print(json.dumps({k:v for k,v in receipt.items() if k not in ('frames','trace_columns')},indent=2),flush=True)
if __name__=='__main__':main()
