"""NumPy queries of the pinned mesh SDF and dense FEM boundary samples."""
import numpy as np
from pathlib import Path
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import scene_asset
def geometry(c):
 return dict(np.load(scene_asset(Path(__file__).parents[1],c['physics']['ball']['rigid_geometry_asset'])))
def signed_gap(points,g):
 p=np.asarray(points);q=(p-g['sdf_min'])/g['sdf_spacing'];shape=np.array(g['sdf'].shape);inside=((q>=0)&(q<shape-1)).all(1)
 base=np.clip(np.floor(q).astype(int),0,shape-2);f=np.clip(q-base,0,1);out=np.zeros(len(p))
 for i in (0,1):
  for j in (0,1):
   for k in (0,1):
    w=(f[:,0] if i else 1-f[:,0])*(f[:,1] if j else 1-f[:,1])*(f[:,2] if k else 1-f[:,2])
    out+=w*g['sdf'][base[:,0]+i,base[:,1]+j,base[:,2]+k]
 out[~inside]=.003
 return out
def boundary_probe_weights(n=4):
 return np.array([[i/n,j/n,1-(i+j)/n] for i in range(n+1) for j in range(n-i+1)])
def body_surface_gaps(vertices,faces,T,g):
 points=np.einsum('ij,fjk->fik',boundary_probe_weights(),vertices[faces]).reshape(-1,3)
 local=(points-T[:3,3])@T[:3,:3]
 return signed_gap(local,g)
def body_floor_gap(T,g):
 return float((g['vertices']@T[:3,:3].T+T[:3,3])[:,2].min())


def rotation_from_quaternion(q):
 w,x,y,z=q
 return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
