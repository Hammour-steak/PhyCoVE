"""Measure physical outcomes from native caches; never prescribe the result."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse,json
from pathlib import Path
import numpy as np
from rigid_geometry import geometry,body_surface_gaps,body_floor_gap,rotation_from_quaternion
from dough_config import CASES,write_json,digest,config

def differences(a,b,prefix=''):
 if isinstance(a,dict) and isinstance(b,dict):
  out={}
  for k in sorted(set(a)|set(b)):
   if not prefix and k=='case':continue
   out.update(differences(a.get(k),b.get(k),prefix+'.'+k if prefix else k))
  return out
 return {} if a==b else {prefix:{'before':a,'after':b}}

def closest_on_surface(p,v,faces):
 a,b,c=v[faces[:,0]],v[faces[:,1]],v[faces[:,2]];ab=b-a;ac=c-a;n=np.cross(ab,ac);den=(n*n).sum(1)
 proj=p-(((p-a)*n).sum(1)/den)[:,None]*n;ap=proj-a
 d00=(ab*ab).sum(1);d01=(ab*ac).sum(1);d11=(ac*ac).sum(1);d20=(ap*ab).sum(1);d21=(ap*ac).sum(1)
 u=(d11*d20-d01*d21)/(d00*d11-d01*d01);w=(d00*d21-d01*d20)/(d00*d11-d01*d01);inside=(u>=0)&(w>=0)&(u+w<=1)
 points=[]
 for x,y in ((a,b),(b,c),(c,a)):
  edge=y-x;t=np.clip(((p-x)*edge).sum(1)/(edge*edge).sum(1),0,1);points.append(x+t[:,None]*edge)
 points.append(np.where(inside[:,None],proj,points[0]));cp=np.concatenate(points);ds=((cp-p)**2).sum(1);i=ds.argmin()
 return float(np.sqrt(ds[i])),cp[i]

def audit_case(folder):
 folder=Path(folder);c=json.loads((folder/'actual_config.json').read_text());r=json.loads((folder/'simulation_receipt.json').read_text());eq=json.loads((folder/'equilibrium_report.json').read_text());d=np.load(folder/'simulation_cache.npz')
 present=bool(d['dough_present']);ball_present=bool(d['ball_present']) if 'ball_present' in d.files else True;case=r['case'];trace=d['trace'];time=trace[:,0];pos=trace[:,1:4];vel=trace[:,4:7];rad=c['physics']['ball']['radius_m'];T=d['ball_transforms'];p=T[:,:3,3]
 if not ball_present:
  floor=np.asarray(d['vertices'])[:,:,2].min(axis=1);fp=d['final_viscous_inverse'];detfp=np.linalg.det(fp)
  maxd=float(trace[:,15].max());maxedge=float(trace[:,16].max());maxcom=float(np.linalg.norm(trace[:,17:20],axis=1).max())
  checks={'finite_native_cache':bool(np.isfinite(d['vertices']).all() and np.isfinite(T).all()),
   'native_timeline_complete':len(T)==c['simulation_quality']['frames']+1 and abs(float(d['time_s'][-1])-c['simulation_quality']['frames']/24)<1e-12,
   'egg_deleted_from_physics':c['physics']['ball'].get('present') is False and r.get('egg_present') is False,
   'egg_has_no_motion_or_contact':bool(np.allclose(d['ball_velocities'],0) and np.allclose(d['ball_angular_velocities'],0) and r['first_ball_dough_contact_s']<0 and r['peak_ball_dough_force_N']==0),
   'dough_remains_present':present,'positive_tetrahedra':r['minimum_detF']>.4,
   'dough_vertices_above_table_within_0p3mm':float(floor.min())>-.0003,
   'table_penalty_error_below_0p5mm':r['maximum_table_quadrature_penetration_m']<.0005,
   'viscous_volume_preserved':float(np.abs(detfp-1).max())<1e-6,
   'linear_momentum_balance':float(np.linalg.norm(r['linear_momentum_balance_residual_kg_m_s']))<1e-6,
   'angular_momentum_balance':float(np.linalg.norm(r['angular_momentum_balance_residual_kg_m2_s']))<1e-7,
   'no_impact_deformation':maxd<.001}
  metrics={'egg_present':False,'maximum_local_deformation_m':maxd,'maximum_edge_displacement_m':maxedge,
   'dough_max_com_displacement_m':maxcom,'minimum_detF':r['minimum_detF'],
   'minimum_dough_vertex_table_gap_m':float(floor.min()),'first_contact_s':None,
   'deformation_definition':'Maximum nodal norm after mass-weighted best rigid fit to the common source state at t=0; no egg is present.'}
  if c.get('initialization',{}).get('mode')=='source_state_t0_edit':
   from source_initial_state import audit_shared_state
   shared=audit_shared_state(folder,c,r['mesh_sha256']);checks.update(shared)
   metrics.update(initial_state_semantics='Exact common source dough state at t=0; the egg is removed before the first simulated step.')
  checks={k:bool(v) for k,v in checks.items()};result={'case':case,'status':'accepted_numerical' if all(checks.values()) else 'requires_review','checks':checks,'metrics':metrics,'cache_sha256':digest(folder/'simulation_cache.npz')}
  write_json(folder/'acceptance.json',result);return result
 if present:
  first=r['first_ball_dough_contact_s'];contact_bracket=None;contact_method='Every-step solver contact-force onset'
 else:
  # The short table collision can occur entirely between 384 Hz trace samples.
  # First sampled penetration may only occur much later during final settling.
  # Detect actual impulse feedback in velocity, retaining its time bracket.
  free_velocity=np.array(c['physics']['ball']['initial_velocity_m_s'])+time[:,None]*np.array(c['physics']['gravity_m_s2'])
  affected=np.flatnonzero(np.linalg.norm(vel-free_velocity,axis=1)>1e-7)
  first=float(time[affected[0]]) if len(affected) else None
  contact_bracket=[float(time[max(0,affected[0]-1)]),first] if len(affected) else None
  contact_method='First sampled table-impulse velocity feedback; time is upper bracket bound, not a per-step timestamp'
 after=time>=(first or 0);up=np.flatnonzero(after&(vel[:,2]>.005));rebound=0.;apex=None
 if len(up):
  i=up[0];j=i+1
  while j<len(time)-1 and vel[j,2]>0:j+=1
  rebound=float(pos[j,2]-pos[after&(time<=time[i]),2].min());apex=float(time[j])
 pre=time<(first or 0)-.005;g=np.array(c['physics']['gravity_m_s2']);initial=np.array(c['physics']['ball']['initial_position_m']);analytic=initial+.5*(time[pre,None]**2+time[pre,None]*c['simulation_quality']['dt_s'])*g
 freeerr=float(np.linalg.norm(pos[pre]-analytic,axis=1).max()) if pre.any() else None
 angle=np.arccos(np.clip((np.einsum('nij,nji->n',T[:-1,:3,:3].transpose(0,2,1),T[1:,:3,:3])-1)/2,-1,1))
 # Frame geometry gives an independent closest-triangle audit, in addition to
 # the every-step quadrature penetration maximum recorded by the solver.
 gaps=[];floor=[]
 if present:
  geom=geometry(c)
  for xx,TT in zip(d['vertices'],T):gaps.append(float(body_surface_gaps(xx,d['dough_faces'],TT,geom).min()));floor.append(float(xx[:,2].min()))
 geom=geometry(c);body_floor=[body_floor_gap(TT,geom) for TT in T]
 R=T[:,:3,:3];rigid_error=float(np.abs(R.transpose(0,2,1)@R-np.eye(3)).max())
 checks={'finite_native_cache':bool(np.isfinite(d['vertices']).all() and np.isfinite(T).all()),
  'native_timeline_complete':len(T)==c['simulation_quality']['frames']+1 and abs(float(d['time_s'][-1])-c['simulation_quality']['frames']/24)<1e-12,
  'release_pose_and_zero_velocity':bool(np.allclose(p[0],initial,atol=1e-14) and np.linalg.norm(d['ball_velocities'][0])==0 and np.linalg.norm(d['ball_angular_velocities'][0])==0),
  'freefall_before_contact':freeerr is not None and freeerr<1e-8,
  'rigid_rotation_orthonormal':rigid_error<1e-10,
  'initial_orientation_matches_config':np.max(np.abs(R[0]-rotation_from_quaternion(c['physics']['ball']['initial_rotation_quaternion_wxyz'])))<1e-12,
  'rigid_mesh_above_board_within_0p5mm':min(body_floor)>-.0005,
  'rigid_geometry_matches_asset':np.array_equal(d['rigid_vertices'],geom['vertices']) and np.array_equal(d['rigid_faces'],geom['faces']),
  'linear_momentum_balance':float(np.linalg.norm(r['linear_momentum_balance_residual_kg_m_s']))<1e-6,
  'angular_momentum_balance':float(np.linalg.norm(r['angular_momentum_balance_residual_kg_m2_s']))<1e-7,
  'gravity_equilibrium':eq['maximum_nodal_speed_m_s']<c['simulation_quality']['settle_max_speed_m_s'],
  'table_penalty_error_below_0p5mm':r['maximum_table_quadrature_penetration_m']<.0005}
 metrics={'first_contact_s':first,'first_contact_method':contact_method,'first_contact_bracket_s':contact_bracket,'first_rebound_height_m':rebound,'first_rebound_apex_s':apex,'ball_final_position_m':p[-1].tolist(),
  'ball_final_speed_m_s':float(np.linalg.norm(d['ball_velocities'][-1])),'ball_final_angular_speed_rad_s':float(np.linalg.norm(d['ball_angular_velocities'][-1])),
  'ball_horizontal_path_after_contact_m':float(np.linalg.norm(np.diff(pos[after,:2],axis=0),axis=1).sum()),
  'ball_rotation_path_rad':float(angle.sum()),'freefall_max_error_m':freeerr,'rigid_rotation_error':rigid_error,
  'maximum_table_quadrature_penetration_m':r['maximum_table_quadrature_penetration_m'],
  'deformation_sampling_Hz':384,'notes':f'Rebound is the first upward center excursion. 24 fps surface clearance is independent of every-step quadrature maxima. Final values refer to the exact t={float(d["time_s"][-1]):g} s simulated endpoint.'}
 if present:
  maxd=int(trace[:,15].argmax());finalxy=p[-1,:2]-trace[-1,17:19];scale=c['physics']['dough'].get('geometry_xy_scale',1.);ondough=bool((finalxy[0]/(.055*scale))**2+(finalxy[1]/(.045*scale))**2<1 and p[-1,2]<.09 and abs(gaps[-1])<.0008 and body_floor[-1]>.002)
  metrics.update(maximum_local_deformation_m=float(trace[:,15].max()),maximum_local_deformation_time_s=float(time[maxd]),maximum_edge_displacement_m=float(trace[:,16].max()),
   dough_max_horizontal_displacement_m=float(np.linalg.norm(trace[:,17:19],axis=1).max()),dough_final_com_displacement_m=trace[-1,17:20].tolist(),
   maximum_accumulated_viscous_strain=r['max_accumulated_viscous_strain'],relaxed_volume_fraction=r['relaxed_volume_fraction'],relaxation_work_J=r['relaxation_work_J'],
   minimum_detF=r['minimum_detF'],maximum_quadrature_penetration_m=r['maximum_ball_dough_quadrature_penetration_m'],minimum_triangle_surface_gap_m=min(gaps),
   minimum_dough_vertex_table_gap_m=min(floor),precontact_local_motion_m=float(trace[pre,15].max()),ball_final_on_dough=ondough,final_triangle_surface_gap_m=gaps[-1],
   deformation_definition='Maximum nodal norm after mass-weighted best rigid fit to independently equilibrated state; sampled at 384 Hz.',
   edge_definition='Rest mesh elliptical radius >0.85; world displacement, sampled at 384 Hz.')
  fp=d['final_viscous_inverse'];detfp=np.linalg.det(fp);metrics['viscous_isochoric_determinant_error']=float(np.abs(detfp-1).max())
  checks.update(positive_tetrahedra=r['minimum_detF']>.4,no_precontact_jump=metrics['precontact_local_motion_m']<.0002,
   contact_and_relaxation=r['first_ball_dough_contact_s']>0 and r['relaxation_work_J']>1e-5 and r['relaxed_volume_fraction']>.005,
   viscous_volume_preserved=metrics['viscous_isochoric_determinant_error']<1e-6,
   quadrature_penetration_below_0p5mm=r['maximum_ball_dough_quadrature_penetration_m']<.0005,
   triangle_penetration_below_0p8mm=min(gaps)>-.0008,
   dough_vertices_above_table_within_0p3mm=min(floor)>-.0003,
   ball_final_above_board=body_floor[-1]>-.0005,actual_deformation_above_1mm=metrics['maximum_local_deformation_m']>.001)
 if c.get('initialization',{}).get('mode')=='source_state_t0_edit':
  from source_initial_state import audit_shared_state
  shared=audit_shared_state(folder,c,r['mesh_sha256'])
  checks.pop('gravity_equilibrium',None);checks.pop('no_precontact_jump',None)
  checks.update(shared)
  metrics.update(initial_state_semantics='Common source gravity-equilibrium state immediately before the t=0 material intervention; not equilibrium under edited E',precontact_motion_expected_from_t0_edit=True,deformation_definition='Maximum nodal norm after mass-weighted best rigid fit to the common source state at t=0; sampled at 384 Hz.')
 checks={k:bool(v) for k,v in checks.items()};result={'case':case,'status':'accepted_numerical' if all(checks.values()) else 'requires_review','checks':checks,'metrics':metrics,'cache_sha256':digest(folder/'simulation_cache.npz')}
 write_json(folder/'acceptance.json',result);return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--simulation-dir',type=Path);p.add_argument('--suite-root',type=Path);p.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES));a=p.parse_args()
 if a.simulation_dir:print(json.dumps(audit_case(a.simulation_dir),indent=2));return
 if not a.suite_root:p.error('Use --simulation-dir or --suite-root')
 reports=[];diffs={};source=None
 selected=list(dict.fromkeys(a.cases));source_path=a.suite_root/'cases/source/simulation/actual_config.json'
 if source_path.is_file():
  render=source_path.parent.parent/'render/actual_render_config.json';source=json.loads((render if render.is_file() else source_path).read_text())
 for case in selected:
  f=a.suite_root/'cases'/case/'simulation'
  if not (f/'simulation_receipt.json').is_file():continue
  reports.append(audit_case(f));render=f.parent/'render/actual_render_config.json';c=json.loads((render if render.is_file() else f/'actual_config.json').read_text())
  if case=='source':source=c
  elif source is not None:
   delta=differences(source,c);expected=differences(config('source',source.get('preset')),config(case,source.get('preset')))
   if c.get('initialization',{}).get('mode')=='source_state_t0_edit':
    assert reports[-1]['checks']['source_initialization_identity_verified'] and reports[-1]['checks']['shared_source_state_exact']
    expected.update({'simulation_quality.initial_equilibrium':{'before':source['simulation_quality']['initial_equilibrium'],'after':'source_state_t0_edit'},'initialization':{'before':source.get('initialization'),'after':c['initialization']}})
   assert delta==expected,(case,delta,expected)
   diffs[case]={'before':source,'after':c,'changed_fields':delta,'passed':True}
 paired=source is not None and all(case=='source' or case in diffs for case in selected)
 write_json(a.suite_root/'parameter_differences.json',diffs);write_json(a.suite_root/'acceptance_results.json',{'status':'numerical_passed' if paired and len(reports)==len(selected) and all(r['status']=='accepted_numerical' for r in reports) else 'requires_review','cases':reports,'requested_cases':selected,'paired_config_comparison_present':paired,'all_cases_present':len(reports)==len(selected),'visual_status':'pending_full_sequence_inspection'})
 print(json.dumps({r['case']:{'status':r['status'],'failed':[k for k,v in r['checks'].items() if not v],'metrics':r['metrics']} for r in reports},indent=2))
if __name__=='__main__':main()
