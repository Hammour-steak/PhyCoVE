"""Read-only CPU audit of actual native surfaces; never imports Blender."""
from pathlib import Path
import argparse,json
import numpy as np
import trimesh
from baseline import save,sha,LAYOUT
from vocab import resolve

def audit(simulation,complete=True,contact=True):
    path=simulation/'cache.npz'
    if not path.exists():path=simulation/'checkpoint.npz'
    z=np.load(path);x=z['positions'];f=z['faces'];times=z['times'];cfg=json.loads((simulation/'simulation_config.json').read_text(encoding='utf8'))
    p,edit=resolve(cfg['case_id']);checks={}
    checks['physics_matches_dsl']=p==cfg['physics'];checks['shared_layout']=LAYOUT==cfg['layout']
    checks['finite_native_vertices']=bool(np.all(np.isfinite(x)))
    checks['correct_output_times']=bool(np.allclose(times,np.arange(len(x))/24,atol=1e-12))
    checks['correct_frame_count']=len(x)==96 if complete else True
    report=dict(cache_sha256=sha(path),config_sha256=sha(simulation/'simulation_config.json'),case_id=cfg['case_id'],
        checks=checks,frames=len(x),cloth_nodes=x.shape[1],material_calibrated=False,
        audit_scope='Actual exported native vertices and affine states at output sampling; not a product material fit or a proof of temporal convergence.')
    T=z['rigid_transforms'];names=list(z['rigid_names']);metrics={}
    for name in ['desk','window','window_sill','notebook','pen_holder']:
        i=names.index(name);err=float(abs(T[:,i]-T[0,i]).max());metrics[name+'_static_transform_error']=err
        checks[name+'_static']=err<1e-10
    if 'figurine'in names:
        body=T[:,names.index('figurine')];axis=body[:,:3,2].copy();axis/=np.linalg.norm(axis,axis=1)[:,None]
        tilt=np.rad2deg(np.arccos(np.clip(axis[:,2],-1,1)))
        metrics['max_figurine_tilt_deg']=float(tilt.max());metrics['max_base_xy_motion_m']=float(np.linalg.norm(body[:,:2,3]-body[0,:2,3],axis=1).max())
        checks['figurine_remains_standing']=metrics['max_figurine_tilt_deg']<5.
        geom=np.load(simulation/'figurine_geometry.npz');worldv=np.einsum('tij,vj->tvi',body[:,:3,:3],geom['vertices'])+body[:,None,:3,3]
        metrics['min_figurine_base_z_m']=float(worldv[:,:,2].min())
        checks['base_above_table']=metrics['min_figurine_base_z_m']>=-.00015
    triangles=x[:,f];cross=np.cross(triangles[:,:,1]-triangles[:,:,0],triangles[:,:,2]-triangles[:,:,0]);areas=np.linalg.norm(cross,axis=-1)/2
    metrics['minimum_triangle_area_m2']=float(areas.min());checks['noncollapsed_surface_triangles']=metrics['minimum_triangle_area_m2']>1e-12
    if 'rest_positions'in z:
        R=z['rest_positions'][f][:,:,[0,2]]
        D=np.stack([R[:,1]-R[:,0],R[:,2]-R[:,0]],axis=-1)
        inv=np.linalg.inv(D);Ds=np.stack([triangles[:,:,1]-triangles[:,:,0],triangles[:,:,2]-triangles[:,:,0]],axis=-1)
        F=np.einsum('tfij,fjk->tfik',Ds,inv);singular=np.linalg.svd(F,compute_uv=False)
        metrics['max_principal_stretch']=float(singular.max());metrics['min_principal_stretch']=float(singular.min())
        metrics['principal_stretch_p99']=float(np.percentile(singular,99))
        yarn_lengths=np.linalg.norm(F,axis=-2)
        metrics['max_warp_weft_stretch']=float(yarn_lengths.max())
        metrics['min_warp_weft_stretch']=float(yarn_lengths.min())
        cos=(F[:,:,:,0]*F[:,:,:,1]).sum(-1)/(yarn_lengths[:,:,0]*yarn_lengths[:,:,1])
        metrics['max_bias_shear_angle_deg']=float(np.rad2deg(np.arcsin(np.clip(abs(cos),0,1))).max())
        checks['warp_weft_stretch_below_8_percent']=metrics['max_warp_weft_stretch']<1.08
        checks['bias_shear_below_55_degrees']=metrics['max_bias_shear_angle_deg']<55.
        report['woven_strain_interpretation']='Warp/weft yarn extension and bias shear are checked separately. Principal stretch alone conflates yarn extension with the intended easy shear of woven cloth.'
    if 'velocities'in z:
        v=z['velocities'];late=times>=3.5
        if late.any():
            metrics['late_rms_cloth_velocity_m_s']=float(np.sqrt(np.mean(np.sum(v[late]**2,axis=-1))))
            if cfg['case_id']=='source':checks['late_motion_below_6cm_s']=metrics['late_rms_cloth_velocity_m_s']<.06
    metrics['final_cloth_height_range_m']=[float(x[-1,:,2].min()),float(x[-1,:,2].max())]
    metrics['final_cloth_xy_bounds_m']=[x[-1,:,:2].min(0).tolist(),x[-1,:,:2].max(0).tolist()]
    if contact:
        contacts={}
        for name in ['figurine','desk','window_sill','ceramic_cup']:
            if name not in names:continue
            geom=np.load(simulation/(name+'_geometry.npz'));mesh=trimesh.Trimesh(geom['vertices'],geom['faces'],process=False)
            hull_planes=None
            if name=='figurine':
                from scipy.spatial import ConvexHull
                hull_planes=np.unique(np.round(ConvexHull(mesh.vertices).equations,11),axis=0)
                assert np.max(mesh.vertices@hull_planes[:,:3].T+hull_planes[:,3])<1e-7
            def convex_candidates(points):
                if hull_planes is None:return np.ones(len(points),bool)
                keep=np.ones(len(points),bool)
                for start in range(0,len(hull_planes),96):
                    ids=np.flatnonzero(keep)
                    if not len(ids):break
                    planes=hull_planes[start:start+96]
                    keep[ids]=np.all(points[ids]@planes[:,:3].T+planes[:,3]<=2e-7,axis=1)
                return keep
            values=[]
            for frame in range(len(x)):
                transform=T[frame,names.index(name)];local=(x[frame]-transform[:3,3])@np.linalg.inv(transform[:3,:3]).T
                lo=mesh.bounds[0]-.004;hi=mesh.bounds[1]+.004;near=np.all((local>=lo)&(local<=hi),axis=1)
                points=local[near]
                if name=='desk':
                    # The exact closed native collider is an axis-aligned box.
                    q=abs(points-mesh.bounds.mean(0))-np.diff(mesh.bounds,axis=0)[0]/2
                    distance=np.linalg.norm(np.maximum(q,0),axis=1)+np.minimum(q.max(1),0)
                    penetration=max(0.,-float(distance.min()))if len(points)else 0.
                else:
                    if hull_planes is not None:points=points[convex_candidates(points)]
                    inside=mesh.contains(points)if len(points)else np.zeros(0,bool)
                    if inside.any():
                        unused,distance,unused_ids=trimesh.proximity.closest_point(mesh,points[inside])
                        penetration=float(distance.max())
                    else:penetration=0.
                values.append(penetration)
            contacts[name]=dict(max_node_penetration_m=max(values),per_frame_node_penetration_m=values)
            checks[name+'_no_output_vertex_penetration']=max(values)<.00010
        report['sampled_contact_audit']=contacts
        report['contact_audit_limit']='Inside classification and exact distance of actual cloth nodes to closed native rigid surfaces; exact desk cuboid SDF; actual figure-mesh AABB and a conservatively expanded convex hull (validated to contain every native vertex) reject only points that cannot be inside. All output frames are checked. Edge/edge and triangle crossing guarantees additionally depend on native CCD/contact; output-node sampling alone is not an all-primitive certificate.'
    report['metrics']=metrics;report['passed']=all(checks.values());save(simulation/'physics_audit.json',report)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('simulation',type=Path);ap.add_argument('--probe',action='store_true');ap.add_argument('--no-contact',action='store_true');a=ap.parse_args()
    report=audit(a.simulation,not a.probe,not a.no_contact)
    print(json.dumps({'passed':report['passed'],'checks':report['checks'],'metrics':report['metrics']},indent=2))

if __name__=='__main__':main()
