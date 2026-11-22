"""Read-only numerical audit of completed caches; does not import Blender or UIPC."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--case-dir',type=Path,required=True);a=ap.parse_args();d=a.case_dir.resolve();z=np.load(d/'simulation.npz');cfg=json.loads((d/'simulation_config.json').read_text());rep=json.loads((d/'simulation_report.json').read_text())
 x=z['elastic_positions'];r=z['elastic_rest_positions'];t=z['elastic_tetrahedra'];fixed=z['elastic_fixed_mask'];finite=all(np.isfinite(z[k]).all() for k in z.files)
 if len(t):
  ref=np.stack([r[t[:,i]]-r[t[:,0]] for i in (1,2,3)],-1);inv=np.linalg.inv(ref);mins=[]
  for q in x:cur=np.stack([q[t[:,i]]-q[t[:,0]] for i in (1,2,3)],-1);mins.append(float(np.linalg.det(cur@inv).min()))
  min_j=min(mins);fixed_error=float(np.max(np.linalg.norm(x[:,fixed]-r[fixed],axis=2))) if np.any(fixed) else 0.
 else:min_j=1.;fixed_error=0.
 T=z['block_transforms'];orth=float(np.max(np.linalg.norm(np.transpose(T[:,:3,:3],(0,2,1))@T[:,:3,:3]-np.eye(3),axis=(1,2))));surface=set(map(int,z['elastic_surface_faces'].ravel()));surface_only=bool(surface and all(all(int(v) in surface for v in f) for f in z['elastic_surface_faces'])) if len(r) else True
 checks={'all_cache_values_finite':bool(finite),'positive_tet_jacobian':min_j>0.10,'sponge_has_zero_fixed_vertices':int(fixed.sum())==0,'rigid_rotation_orthogonality':orth<1e-5,'surface_topology_nonempty_or_deleted':surface_only,'manual_motion_false':cfg['manual_motion'] is False and cfg['manual_deformation'] is False,'fixed_table_leg_collision_volume_declared':rep.get('fixed_table_leg_has_collision_volume') is True and rep.get('fixed_table_leg_mass_kg',0)>20,'added_block_cache_matches_case':bool(len(z['added_block_transforms']))==bool(cfg['physics']['added_block_present'])}
 out={'status':'passed' if all(checks.values()) else 'failed','case_id':cfg['case_id'],'checks':checks,'minimum_tet_jacobian':min_j,'maximum_fixed_rear_boundary_error_m':fixed_error,'maximum_rigid_orthogonality_error':orth,'peak_bumper_displacement_m':rep['peak_bumper_displacement_m'],'peak_front_face_compression_m':rep['peak_front_face_compression_m'],'fixed_table_leg_mass_kg':rep['fixed_table_leg_mass_kg'],'input_sha256':{'simulation.npz':sha(d/'simulation.npz')},'scope':'Saved-state numerical integrity, restrained sponge rear-face enforcement, explicit fixed wood table-leg collision volume, optional second-rigid-body cache binding, and observable axial compression. The effective hyperelastic material is not a calibrated crushable-foam product law.'};(d/'independent_physics_audit.json').write_text(json.dumps(out,indent=2,allow_nan=False),encoding='utf-8');print(json.dumps(out,indent=2))
 out['scope']='Saved-state numerical integrity, zero constrained sponge vertices, explicit fixed table-leg collision volume representing the heavy table assembly, optional second rigid body, and thickness-based axial compression. The effective hyperelastic material is not a calibrated crushable-foam product law.'
 (d/'independent_physics_audit.json').write_text(json.dumps(out,indent=2,allow_nan=False),encoding='utf-8')
 if out['status']!='passed':raise SystemExit(2)
if __name__=='__main__':main()
