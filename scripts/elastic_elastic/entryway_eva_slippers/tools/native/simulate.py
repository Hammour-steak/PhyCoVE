"""Native compressible volumetric FEM, objective viscosity and two-way IPC."""
from pathlib import Path
import argparse,os,socket,subprocess,sys,time
from common import CASE,FORMAL,INPUTS,save,read,sha
sys.path[:0]=[str(FORMAL),str(INPUTS/'runtime/native')]
import numpy as np
from scipy.spatial import cKDTree
import uipc
from uipc import view,builtin
from uipc.core import Scene,Engine,World,FiniteElementStateAccessorFeature,AffineBodyStateAccessorFeature
from uipc.geometry import tetmesh,trimesh,ground,label_surface,label_triangle_orient,flip_inward_triangles
from uipc.constitution import StableNeoHookean,ElasticModuli,AffineBodyConstitution
from vocab_hero import SPEC, CASE_DSL, SPEC_PATH, parameters
from geometry import placed, lumped_mass
from shoe_tray import tray_mesh,affine_energy
from material_model import mapped_moduli,elastic_energy

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--case',choices=CASE_DSL,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--duration',type=float,default=4.);ap.add_argument('--dt',type=float);ap.add_argument('--mesh',choices=['pilot','production','refined'],default='production');ap.add_argument('--boundary-steiner',action='store_true');ap.add_argument('--isotropic',action='store_true');ap.add_argument('--linear-tol',type=float);ap.add_argument('--velocity-tol',type=float);ap.add_argument('--max-newton',type=int);a=ap.parse_args()
 host=socket.gethostname().split('.')[0];uuid=os.environ.get('CUDA_VISIBLE_DEVICES','')
 if not uuid.startswith('GPU-') or ',' in uuid:raise RuntimeError('Bind exactly one GPU by UUID (CUDA_VISIBLE_DEVICES=GPU-...)')
 p=parameters(a.case);dt=a.dt or SPEC['simulation']['dt_s'];stride=round(1/SPEC['fps']/dt)
 if abs(stride*dt-1/SPEC['fps'])>1e-12:raise ValueError('Time step must sample exact24Hz times')
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 if (out/'simulation.npz').exists():raise FileExistsError('Preserve prior simulation')
 meshfile=(INPUTS/'accepted_delivery/geometry_d'/Path(SPEC['simulation']['geometry']).name).resolve()
 if a.mesh!='production' or not meshfile.is_relative_to((INPUTS/'accepted_delivery').resolve()):raise ValueError('Use the production geometry; refinement controls require a separately meshed specification')
 z=np.load(meshfile);cfg=Scene.default_config();cfg['dt']=dt;cfg['gravity']=[[0.],[0.],[-p['gravity_m_s2']]];cfg['integrator']['type']='bdf2';cfg['contact']['d_hat']=SPEC['simulation']['contact_d_hat_m'];cfg['contact']['eps_velocity']=1e-4;cfg['contact']['adaptive']['min_kappa']=1e6;cfg['contact']['adaptive']['max_kappa']=1e12;cfg['contact']['adaptive']['kappa_eval_scale']=1.;cfg['newton']['max_iter']=a.max_newton or SPEC['simulation']['newton_max_iterations'];cfg['newton']['velocity_tol']=a.velocity_tol or SPEC['simulation'].get('velocity_tolerance_m_s',2e-4);cfg['newton']['semi_implicit']['enable']=0;cfg['linear_system']['fem_preconditioner']='mas';cfg['linear_system']['tol_rate']=a.linear_tol or SPEC['simulation'].get('linear_relative_tolerance',1e-7);cfg['line_search']['max_iter']=48
 scene=Scene(cfg);contact=scene.contact_tabular();contact.default_model(p['shoe_shoe_friction'],1e8);floor=contact.create('fixed_environment');contact.insert(floor,contact.default_element(),p['floor_friction'],1e8);contact.insert(floor,floor,0.,1e8,enable=False);g=ground(0.,np.array([0.,0.,1.]));floor.apply_to(g);scene.objects().create('fixed_floor').geometries().create(g)
 tray_data=None;tray_local=np.empty((0,3));tray_faces=np.empty((0,3),np.int32);tray_initial=np.eye(4)
 if p['tray_present'][0]:
  if p['tray_is_fixed']:raise ValueError('The shoe tray must be a finite-mass dynamic body')
  v,tray_faces=tray_mesh(p);tray_local=v-np.array(p['tray_center_m']);tray_initial[:3,3]=p['tray_center_m'];m=trimesh(tray_local,tray_faces);label_surface(m);AffineBodyConstitution().apply_to(m,SPEC['simulation']['tray_affine_orthogonality_kappa_pa'],p['tray_density_kg_m3']);view(m.transforms())[:]=tray_initial
  tray_contact=contact.create('dynamic_wooden_shoe_tray');contact.insert(tray_contact,contact.default_element(),p['shoe_shoe_friction'],1e8);contact.insert(tray_contact,floor,p['tray_floor_friction'],1e8);tray_contact.apply_to(m);scene.objects().create('dynamic_wooden_shoe_tray').geometries().create(m)
  def meta(name):return np.asarray(m.meta().find(name).view())
  if int(meta('constitution_uid').ravel()[0])!=1:raise RuntimeError('Expected the pinned affine OrthoPotential constitution')
  tray_data=dict(mass_kg=float(meta('abd_mass').ravel()[0]),first_mass_moment_kg_m=meta('abd_mass_x_bar').reshape(3).tolist(),second_mass_moment_kg_m2=meta('abd_mass_x_bar_x_bar').reshape(3,3).tolist(),volume_m3=float(meta('volume').ravel()[0]),kappa_pa=float(SPEC['simulation']['tray_affine_orthogonality_kappa_pa']),is_fixed=False,energy_mapping='Native dyadic mass moments and kappa*rest_volume*||A^T A-I||_F^2; no rigid projection')
 import pcve_viscosity as native_viscosity
 manifest=read(INPUTS/'runtime/native/build_manifest.json');binary=INPUTS/'runtime/native/pcve_viscosity.cpython-310-x86_64-linux-gnu.so'
 if sha(binary)!=manifest['sha256']:raise RuntimeError('Native dissipation binary hash mismatch')
 materials=[];rest=[];tets=[];faces=[];ids=[];masses=[];restvol=[];offset=0
 for part_id,name in [(0,'falling'),(1,'resting')]:
  if name=='resting' and not p['resting_present'][0]:continue
  v,t,f=placed(z,p,name);m=tetmesh(v,t);label_surface(m);label_triangle_orient(m);flip_inward_triangles(m);mat=mapped_moduli(p[name+'_young_modulus_pa'],p[name+'_poisson_ratio']);StableNeoHookean().apply_to(m,ElasticModuli.youngs_poisson(mat['input_E_pa'],mat['input_nu']),p[name+'_density_kg_m3']);eta=p[name+'_shear_viscosity_pa_s'];bulk=p[name+'_bulk_viscosity_pa_s'];native_viscosity.apply_to(m,eta,bulk,0.)
  mu=np.asarray(m.tetrahedra().find('mu').view());lam=np.asarray(m.tetrahedra().find('lambda').view())
  if not np.allclose(mu,mat['kernel_mu_pa'],rtol=1e-10) or not np.allclose(lam,mat['kernel_lambda_pa'],rtol=1e-10):raise RuntimeError('Installed constitutive mapping changed')
  scene.objects().create(name+'_slipper').geometries().create(m);mass,vol=lumped_mass(v,t,p[name+'_density_kg_m3']);mat.update(name=name,part_id=part_id,density_kg_m3=p[name+'_density_kg_m3'],mass_kg=float(mass.sum()),shear_viscosity_pa_s=eta,bulk_viscosity_pa_s=bulk,observed_native_mu_pa=float(mu[0]),observed_native_lambda_pa=float(lam[0]));materials.append(mat);rest.append(v);tets.append(t+offset);faces.append(f+offset);ids.append(np.full(len(v),part_id,np.int8));masses.append(mass);restvol.append(vol);offset+=len(v)
 rest=np.concatenate(rest);tt=np.concatenate(tets);ff=np.concatenate(faces);ids=np.concatenate(ids);mass=np.concatenate(masses);vol=np.concatenate(restvol);tetids=ids[tt[:,0]];dm=np.stack([rest[tt[:,i]]-rest[tt[:,0]] for i in [1,2,3]],axis=-1);inv=np.linalg.inv(dm)
 provenance=dict(host=host,job_name=os.environ.get('PCVE_JOB_NAME'),gpu_uuid=uuid,gpu=subprocess.check_output(['nvidia-smi','-i',uuid,'--query-gpu=uuid,name,driver_version','--format=csv,noheader'],text=True).strip(),python=sys.version,numpy=np.__version__,uipc_file=uipc.__file__,backend_sha256=sha(Path(uipc.__file__).parent/'_native/libuipc_backend_cuda.so'),native_viscosity_sha256=sha(binary),native_viscosity_original_build=manifest,local_blender_used=False)
 save(out/'simulation_config.json',dict(scene_id=CASE,case=a.case,edit_dsl=CASE_DSL[a.case],physics=p,dt_s=dt,duration_s=a.duration,fps=24,mesh_level=a.mesh,geometry_file=SPEC['simulation']['geometry'],mesh_sha256=sha(meshfile),materials=materials,tray_mass_properties=tray_data,solver_config=cfg,material_calibrated=False,accepted_benchmark_gt=False,provenance=provenance))
 uipc.Logger.set_level(uipc.Logger.Warn);start=time.monotonic();engine=Engine('cuda',str(out/'solver'));world=World(engine);world.init(scene)
 if not world.is_valid():raise RuntimeError('Invalid initial collision scene')
 accessor=world.features().find(FiniteElementStateAccessorFeature);state=accessor.create_geometry()
 for key in [builtin.position,builtin.velocity]:
  if state.vertices().find(key) is None:state.vertices().create(key,np.zeros(3))
 accessor.copy_to(state);initial=np.asarray(state.positions().view()).reshape(-1,3);distance,mapping=cKDTree(initial).query(rest)
 if distance.max()>1e-8 or len(np.unique(mapping))!=len(rest):raise RuntimeError('Native vertex order mapping failed')
 velocity = view(state.vertices().find(builtin.velocity)).reshape(-1,3)
 velocity[mapping[ids == 0]] = p['falling_initial_velocity_m_s']
 accessor.copy_from(state)
 abd=None;ag=None;tray_index=None
 if tray_data:
  abd=world.features().find(AffineBodyStateAccessorFeature);ag=abd.create_geometry()
  for key,value in [(builtin.transform,np.eye(4)),(builtin.velocity,np.zeros((4,4)))]:
   if ag.instances().find(key) is None:ag.instances().create(key,value)
  abd.copy_to(ag);transforms=np.asarray(ag.instances().find(builtin.transform).view()).reshape(-1,4,4);distance=np.linalg.norm(transforms[:,:3,3]-tray_initial[:3,3],axis=1);tray_index=int(np.argmin(distance))
  if distance[tray_index]>1e-8:raise RuntimeError('Native dynamic tray ID mapping failed')
 XP=[];XV=[];BT=[];BV=[];rows=[];high=[];steps=round(a.duration/dt);previousF=None;viscous_work=0.;minJ=1.;maxJ=1.;maxenergy=0.;maxcompfraction=0.;minimum_tray_floor_gap=None;maximum_tray_orthogonal_error=0.
 def cache_payload():return dict(positions=np.asarray(XP),velocities=np.asarray(XV),rest=rest,tetrahedra=tt,faces=ff,part_ids=ids,masses=mass,times=np.arange(len(XP))/24,tray_transforms=np.asarray(BT).reshape(-1,4,4),tray_velocities=np.asarray(BV).reshape(-1,4,4),tray_vertices_local=tray_local,tray_faces=tray_faces)
 for step in range(steps+1):
  accessor.copy_to(state);x=np.asarray(state.positions().view()).reshape(-1,3)[mapping].copy();vel=np.asarray(state.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
  if not np.isfinite(x).all():raise FloatingPointError('Nonfinite native positions')
  F=np.stack([x[tt[:,i]]-x[tt[:,0]] for i in [1,2,3]],axis=-1)@inv;J=np.linalg.det(F);elastic=0.
  for mat in materials:
   mask=tetids==mat['part_id'];elastic+=float(np.sum(elastic_energy(F[mask],mat)*vol[mask]))
  if previousF is not None:
   D=.5*(np.swapaxes(F,-1,-2)@F-np.swapaxes(previousF,-1,-2)@previousF);trace=np.trace(D,axis1=-2,axis2=-1);dev=D-trace[:,None,None]*np.eye(3)/3
   for mat in materials:
    mask=tetids==mat['part_id'];viscous_work+=float(np.sum(vol[mask]*(2*mat['shear_viscosity_pa_s']*np.sum(dev[mask]**2,axis=(1,2))+mat['bulk_viscosity_pa_s']*trace[mask]**2)/dt))
  previousF=F;kinetic=float(.5*np.sum(mass[:,None]*vel*vel));potential=float(np.sum(mass*x[:,2])*p['gravity_m_s2']);tray_row=None
  if abd:
   abd.copy_to(ag);tray_T=np.asarray(ag.instances().find(builtin.transform).view()).reshape(-1,4,4)[tray_index].copy();tray_V=np.asarray(ag.instances().find(builtin.velocity).view()).reshape(-1,4,4)[tray_index].copy()
   if not np.isfinite(tray_T).all() or not np.isfinite(tray_V).all() or np.linalg.det(tray_T[:3,:3])<=0:raise FloatingPointError('Invalid native affine tray state')
   tray_k,tray_p,tray_e,tray_center,tray_orth=affine_energy(tray_T,tray_V,tray_data,p['gravity_m_s2']);tray_world=tray_local@tray_T[:3,:3].T+tray_T[:3,3];tray_gap=float(tray_world[:,2].min());minimum_tray_floor_gap=tray_gap if minimum_tray_floor_gap is None else min(minimum_tray_floor_gap,tray_gap);maximum_tray_orthogonal_error=max(maximum_tray_orthogonal_error,tray_orth);kinetic+=tray_k;potential+=tray_p;elastic+=tray_e
   tray_row=dict(center_m=tray_center.tolist(),mass_kg=tray_data['mass_kg'],floor_gap_m=tray_gap,orthogonality_error=tray_orth,kinetic_energy_j=tray_k,gravity_energy_j=tray_p,affine_shape_energy_j=tray_e)
  total=elastic+kinetic+potential;minJ=min(minJ,float(J.min()));maxJ=max(maxJ,float(J.max()));maxenergy=max(maxenergy,total)
  row=dict(time_s=step*dt,min_J=float(J.min()),max_J=float(J.max()),kinetic_energy_j=kinetic,elastic_energy_j=elastic,gravity_energy_j=potential,total_mechanical_energy_j=total,accumulated_native_viscous_work_j=viscous_work,parts={})
  row['tray']=tray_row;full=step%stride==0
  for mat in materials:
   part=mat['part_id'];mask=ids==part;tm=tetids==part;com=np.average(x[mask],weights=mass[mask],axis=0);partrow=dict(center_m=com.tolist(),velocity_m_s=np.average(vel[mask],weights=mass[mask],axis=0).tolist(),floor_gap_m=float(x[mask,2].min()),volume_ratio=float(np.sum(vol[tm]*J[tm])/vol[tm].sum()))
   if full:
    a0=rest[mask]-np.average(rest[mask],weights=mass[mask],axis=0);b=x[mask]-com;U,_,VT=np.linalg.svd((a0*mass[mask,None]).T@b);R=VT.T@U.T
    if np.linalg.det(R)<0:VT[-1]*=-1;R=VT.T@U.T
    deform=np.linalg.norm(b-a0@R.T,axis=1);partrow.update(nonrigid_rms_m=float(np.sqrt(np.average(deform**2,weights=mass[mask]))),nonrigid_max_m=float(deform.max()),rotation_matrix=R.tolist());sing=np.linalg.svd(F[tm],compute_uv=False);fraction=float(np.sum(vol[tm][sing.min(1)<.65])/vol[tm].sum());partrow['rest_volume_fraction_with_compression_over_35pct']=fraction;maxcompfraction=max(maxcompfraction,fraction)
   row['parts'][mat['name']]=partrow
  high.append(row)
  if full:
   XP.append(x.astype(np.float32));XV.append(vel.astype(np.float32));rows.append(row)
   if abd:BT.append(tray_T);BV.append(tray_V)
   if step>0 and step%(stride*24)==0 and step<steps:
    # A real native prefix for diagnostics while a longer run continues.
    # It is never packaged as a completed four-second simulation.
    checkpoint=out/f'checkpoint_{round(step*dt):02d}s.npz';np.savez_compressed(checkpoint,**cache_payload())
    save(checkpoint.with_suffix('.json'),dict(actual_native_endpoint_s=step*dt,states=len(XP),complete_run=False,sha256=sha(checkpoint)))
   if step%(stride*3)==0:save(out/'progress.json',dict(step=step,total_steps=steps,time_s=step*dt,wall_s=time.monotonic()-start,last=row));print('STATE',step,'/',steps,'t',round(step*dt,3),'J',round(float(J.min()),5),'fall_z',round(row['parts']['falling']['center_m'][2],5),'elapsed',round(time.monotonic()-start,1),flush=True)
  if float(J.min())<=0:
   worst=int(np.argmin(J));save(out/'failure.json',dict(reason='Inverted volume element',step=step,time_s=step*dt,min_J=float(J.min()),tet_index=worst,part_id=int(tetids[worst]),rest_volume_m3=float(vol[worst])));np.savez_compressed(out/'failure_snapshot.npz',positions=x,velocities=vel,rest=rest,tetrahedra=tt,faces=ff,part_ids=ids,masses=mass,J=J);np.savez_compressed(out/'partial_native.npz',positions=np.asarray(XP),velocities=np.asarray(XV),rest=rest,tetrahedra=tt,faces=ff,part_ids=ids,masses=mass,times=np.arange(len(XP))/24);save(out/'high_rate_failure.json',high);raise RuntimeError('Inverted volume element')
  if step<steps:
   world.advance();world.retrieve()
   if not world.is_valid():raise RuntimeError('Solver invalid during integration')
 np.savez_compressed(out/'simulation.npz',**cache_payload())
 save(out/'simulation_report.json',dict(case=a.case,rows=rows,min_J=minJ,max_J=maxJ,max_total_mechanical_energy_j=maxenergy,max_rest_volume_fraction_with_compression_over_35pct=maxcompfraction,minimum_dynamic_tray_floor_gap_m=minimum_tray_floor_gap,maximum_dynamic_tray_orthogonality_error=maximum_tray_orthogonal_error,wall_s=time.monotonic()-start,physical_duration_s=steps*dt,cache_states=len(XP),material_calibrated=False,scope='Native compressible FEM and optional finite-mass affine rigid tray with two-way frictional IPC. Energy includes the native affine dyadic kinetic and orthogonal shape terms. Full substep history and24Hz states are retained.'))
 save(out/'high_rate_metrics.json',high);print('SIMULATION_COMPLETE',a.case,time.monotonic()-start,flush=True)

if __name__=='__main__':main()
