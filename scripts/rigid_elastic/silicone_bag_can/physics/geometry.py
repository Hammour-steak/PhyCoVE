"""Metric mid-surface, continuous handles and exact closed can proxy. No bpy."""
import numpy as np
import trimesh
from scipy.spatial import Delaunay

def bag_mesh(p, nt=80, nz=36):
    if nt % 8: raise ValueError('Angular resolution must be divisible by eight')
    w=p['bag_width_m']/2;d=p['bag_depth_m']/2;cy=p['bag_center_y_m'];zb=p['bag_bottom_z_m'];zt=p['bag_mouth_z_m']
    verts=[[0.,cy,zb]];faces=[];rings=[]
    # Flat rounded bottom: staggered rings keep the centre fan well conditioned.
    for r in np.linspace(.12,.88,8):
        ring=[]
        count=nt if r==.88 else max(8,round(nt*r/.88))
        for k in range(count):
            th=2*np.pi*k/count
            ring.append(len(verts));verts.append([w*r*np.cos(th),cy+d*r*np.sin(th),zb])
        rings.append(ring)
    bottom=np.array(verts)
    for face in Delaunay(bottom[:,:2]/np.array([w,d])).simplices:
        if np.cross(bottom[face[1]]-bottom[face[0]],bottom[face[2]]-bottom[face[0]])[2]>0:face=face[::-1]
        faces.append(face.tolist())
    rings=[rings[-1]]
    for j in range(nz+1):
        t=j/nz
        rr=.88+.12*np.sin(min(1,t*7)*np.pi/2)
        z=zb+.008+(zt-zb-.008)*t
        ring=[]
        for k in range(nt):
            th=2*np.pi*k/nt
            # Shallow, molded gussets are rest geometry, common to all variants.
            gusset=.0015*np.sin(6*th)*np.sin(np.pi*t)
            ring.append(len(verts));verts.append([(w*rr+gusset)*np.cos(th),cy+(d*rr+gusset)*np.sin(th),z])
        rings.append(ring)
    for a,b in zip(rings[:-1],rings[1:]):
        for k in range(nt):
            kk=(k+1)%nt
            faces.extend([[a[k],a[kk],b[kk]],[a[k],b[kk],b[k]]])
    rim=rings[-1];fixed=[];handle_ids=[]
    # Two U straps on opposite side walls; their four-vertex ends share actual
    # boundary vertices with the bag, not a disconnected decorative loop.
    half=nt//8;sections=24;width_nodes=4
    for side in (0,nt//2):
        aa=np.array([verts[rim[(side-half+j)%nt]] for j in range(width_nodes)])
        bb=np.array([verts[rim[(side+half-j)%nt]] for j in range(width_nodes)])
        strips=[]
        for i in range(sections+1):
            t=i/sections
            if i==0:ids=[rim[(side-half+j)%nt] for j in range(width_nodes)]
            elif i==sections:ids=[rim[(side+half-j)%nt] for j in range(width_nodes)]
            else:
                q=(1-t)*aa+t*bb
                q[:,2]+=.148*np.sin(np.pi*t)
                # Smooth outward bow clears the mouth and canned-food path.
                q[:,0]+=np.cos(2*np.pi*side/nt)*.012*np.sin(np.pi*t)
                ids=list(range(len(verts),len(verts)+width_nodes));verts.extend(q.tolist())
            strips.append(ids);handle_ids.extend(ids)
            if abs(t-.5)<=1/sections+.00001:fixed.extend(ids)
        for a,b in zip(strips[:-1],strips[1:]):
            for j in range(width_nodes-1):faces.extend([[a[j],a[j+1],b[j+1]],[a[j],b[j+1],b[j]]])
    v=np.array(verts,float);f=np.array(faces,np.int32)
    m=trimesh.Trimesh(v,f,process=False)
    # Consistent winding across the welded straps, retaining vertex identity.
    trimesh.repair.fix_winding(m)
    fixed_mask=np.zeros(len(v),bool);fixed_mask[np.unique(fixed)]=True
    return v,np.array(m.faces,np.int32),fixed_mask,np.array(sorted(set(handle_ids)),np.int32)

def can_mesh(radius,height,sections=64):
    # Vertically closed, circular, bevelled cylinder; metal stiffness is ABD.
    v=[];f=[]
    profiles=[(radius-.0011,-height/2),(radius,-height/2+.0011),(radius,height/2-.0011),(radius-.0011,height/2)]
    for r,z in profiles:
        for k in range(sections):
            th=2*np.pi*k/sections;v.append([r*np.cos(th),r*np.sin(th),z])
    for j in range(3):
        for k in range(sections):
            a=j*sections+k;b=j*sections+(k+1)%sections;c=b+sections;dd=a+sections
            f.extend([[a,b,c],[a,c,dd]])
    for j,z,reverse in [(0,-height/2,True),(3,height/2,False)]:
        c=len(v);v.append([0,0,z])
        for k in range(sections):
            a=j*sections+k;b=j*sections+(k+1)%sections
            f.append([c,b,a] if reverse else [c,a,b])
    mesh=trimesh.Trimesh(np.array(v),np.array(f,np.int32),process=False)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0
    return mesh

if __name__=='__main__':
    import json
    from pathlib import Path
    p=json.loads((Path(__file__).resolve().parent/'scene_spec.json').read_text(encoding='utf-8'))['baseline']
    v,f,fixed,h=bag_mesh(p)
    m=trimesh.Trimesh(v,f,process=False);edges=m.edges_unique
    print(json.dumps(dict(vertices=len(v),triangles=len(f),fixed_vertices=int(fixed.sum()),winding=m.is_winding_consistent,
        min_edge_m=float(np.linalg.norm(v[edges[:,0]]-v[edges[:,1]],axis=1).min()),area_m2=m.area,
        mass_kg=m.area*p['bag_thickness_m']*p['bag_density_kg_m3'],can_volume_m3=can_mesh(.034,.080).volume),indent=2))
