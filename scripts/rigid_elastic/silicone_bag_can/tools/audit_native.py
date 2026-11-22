"""Independent native-state and delivery checks, with no Blender invocation."""
from pathlib import Path
import argparse,hashlib,json,re
import numpy as np

def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def audit_case(d):
    z=np.load(d/'simulation.npz');cfg=json.loads((d/'simulation_config.json').read_text(encoding='utf-8'));p=cfg['physics'];times=z['times'];x=z['bag_positions'];T=z['can_transforms']
    result=dict(case=cfg['case'],native_states=len(times),physical_duration_s=float(times[-1]),finite=bool(np.isfinite(x).all() and np.isfinite(T).all()),
        full_four_seconds=len(times)==97 and np.allclose(times,np.arange(97)/24,atol=1e-12),actual_host=cfg['actual_host'],gpu_uuid=cfg['gpu_uuid'])
    if x.shape[1]:
        fixed=z['bag_fixed_mask'];rv=z['bag_rest_positions'];f=z['bag_faces'];ref=rv[f]
        e1=ref[:,1]-ref[:,0];e2=ref[:,2]-ref[:,0]
        invref=np.linalg.inv(np.stack([np.stack([np.sum(e1*e1,1),np.sum(e1*e2,1)],1),np.stack([np.sum(e1*e2,1),np.sum(e2*e2,1)],1)],1))
        peaks=[];gaps=[]
        for state,bodies in zip(x,T):
            tri=state[f];a=tri[:,1]-tri[:,0];b=tri[:,2]-tri[:,0]
            gram=np.stack([np.stack([np.sum(a*a,1),np.sum(a*b,1)],1),np.stack([np.sum(a*b,1),np.sum(b*b,1)],1)],1)
            # Similarity of inv(reference metric)*current metric has positive
            # real eigenvalues: principal stretches squared.
            val=np.linalg.eigvals(invref@gram).real
            peaks.append(float(np.sqrt(np.maximum(val,0)).max()))
            # Sample vertices, edge midpoints and triangle centroids against the
            # conservative outer can cylinder. This is a sampled diagnostic,
            # not a certificate of continuous triangle/triangle nonintersection.
            points=np.concatenate([state,tri.mean(1),(tri[:,0]+tri[:,1])/2,(tri[:,1]+tri[:,2])/2,(tri[:,2]+tri[:,0])/2])
            for t in bodies:
                inv=np.linalg.inv(t);q=points@inv[:3,:3].T+inv[:3,3]
                dist=np.stack([np.linalg.norm(q[:,:2],axis=1)-p['can_radius_m'],np.abs(q[:,2])-p['can_height_m']/2],1)
                sd=np.linalg.norm(np.maximum(dist,0),axis=1)+np.minimum(np.max(dist,axis=1),0)
                gaps.append(float(sd.min()))
        anchor=np.linalg.norm(x[:,fixed]-rv[fixed],axis=2)
        result.update(anchor_max_error_m=float(anchor.max()),bag_lowest_z_m=float(x[:,:,2].min()),
            peak_depression_from_initial_m=float(x[0,:,2].min()-x[:,:,2].min()),max_principal_stretch=max(peaks),
            sampled_can_cylinder_min_signed_distance_m=min(gaps),sampled_penetration_gate=min(gaps)>-0.0005,
            contact_diagnostic_scope='Native vertices, edge midpoints and centroids vs conservative can cylinder; not continuous CCD proof',
            tail_max_shell_speed_m_s=float(np.linalg.norm(z['bag_velocities'][-12:],axis=2).max()))
    if T.shape[1]:
        singular=np.linalg.svd(T[:,:,:3,:3],compute_uv=False)
        result['can_max_singular_value_deviation']=float(np.max(np.abs(singular-1)))
        result['rigid_roundness_gate']=result['can_max_singular_value_deviation']<0.0002
        result['tail_primary_max_speed_m_s']=float(np.linalg.norm(z['can_velocities'][-24:,0,:3,3],axis=1).max())
        result['primary_initial_transform']=T[0,0].tolist()
        result['primary_end_center_m']=T[-1,0,:3,3].tolist()
    logs=list(d.glob('*.log'))
    warnings=[]
    for log in logs:
        for line in log.read_text(encoding='utf-8',errors='replace').splitlines():
            if re.search(r'\[(warning|error|critical)\]|\b(Traceback|RuntimeError|AssertionError|exits with max iteration|CCD failed|initial intersection)\b',line,re.I):warnings.append(line[:600])
    result['solver_logs_present']=bool(logs)
    result['solver_log_findings']=warnings[:120];result['solver_log_finding_count']=len(warnings) if logs else None
    result['cache_sha256']=hashlib.sha256((d/'simulation.npz').read_bytes()).hexdigest()
    save(d/'physics_audit.json',result)
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args()
    rows=[audit_case(p.parent) for p in sorted(a.root.glob('*/simulation.npz'))]
    common=all(np.array_equal(np.array(r['primary_initial_transform']),np.array(rows[0]['primary_initial_transform'])) for r in rows)
    result=dict(cases=rows,same_primary_initial_transform=common,material_calibrated=False,
        status='DEVELOPMENT_REVIEW_ONLY',note='Numerical diagnostics do not replace product calibration or a continuous independent contact audit')
    save(a.root/'audit.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
