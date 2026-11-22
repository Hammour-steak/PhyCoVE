"""Export the solver's physical strip surface as indexed XYZ deformation GT.

This is a direct Kirchhoff cross-section reconstruction. Printed markings,
bevels and the hanging hole remain in the separate remote render binding.
"""
from pathlib import Path
import json
import numpy as np

def export(d):
    cfg=json.loads((d/'simulation_config.json').read_text())['physics']
    cache=np.load(d/'simulation.npz');sfree=cache['arc_length']
    s=np.r_[np.linspace(-cfg['ruler_clamped_length_m'],0,81)[:-1],sfree]
    ny=7;ns=len(s);ys=np.linspace(-cfg['ruler_width_m']/2,cfg['ruler_width_m']/2,ny)
    positions=np.empty((len(cache['times']),2*ns*ny,3),np.float32)
    for frame,curve in enumerate(cache['beam_curves']):
        free=s>=0;x=s.copy();z=np.full(ns,cfg['ruler_midplane_z_m']);theta=np.zeros(ns)
        x[free]=np.interp(s[free],sfree,curve[:,0]);z[free]=np.interp(s[free],sfree,curve[:,1]);theta[free]=np.interp(s[free],sfree,curve[:,2])
        for layer,sign in enumerate((-1,1)):
            off=sign*cfg['ruler_thickness_m']/2
            block=np.empty((ns,ny,3),float)
            block[:,:,0]=(x-np.sin(theta)*off)[:,None];block[:,:,1]=ys[None,:];block[:,:,2]=(z+np.cos(theta)*off)[:,None]
            positions[frame,layer*ns*ny:(layer+1)*ns*ny]=block.reshape(-1,3)
    triangles=[]
    for layer in range(2):
        for i in range(ns-1):
            for j in range(ny-1):
                a=layer*ns*ny+i*ny+j;b=a+ny;c=b+1;dd=a+1
                triangles.extend([(a,c,b),(a,dd,c)] if layer==0 else [(a,b,c),(a,c,dd)])
    # Closed thickness faces along both long edges and both ends.
    boundary=[i*ny for i in range(ns)]+[(ns-1)*ny+j for j in range(1,ny)]+[i*ny+ny-1 for i in range(ns-2,-1,-1)]+[j for j in range(ny-2,0,-1)]
    for k,a in enumerate(boundary):
        b=boundary[(k+1)%len(boundary)];c=b+ns*ny;dd=a+ns*ny;triangles.extend([(a,b,c),(a,c,dd)])
    triangles=np.array(triangles,np.int32)
    np.savez_compressed(d/'ruler_surface.npz',times=cache['times'],positions=positions,triangles=triangles,material_s_m=s)
    return {'vertex_count':positions.shape[1],'triangle_count':len(triangles),'cache_state_count':len(cache['times'])}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('case_dir',type=Path);a=p.parse_args();print(export(a.case_dir))
