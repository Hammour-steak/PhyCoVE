"""Audit the actual piecewise-linear ball path against common court triangles."""
import ctypes
import json
from pathlib import Path
import numpy as np
from common import INPUTS,sha,write


def audit(path,out,present):
 root=INPUTS/'court_collision';record=json.loads((root/'build.json').read_text())
 assert sha(root/'rigid_with_court.so')==record['derived_library_sha256']
 assert sha(root/'fence_triangles.npz')==record['fence_geometry_sha256']
 with np.load(root/'fence_triangles.npz') as z:mesh=np.ascontiguousarray(z['triangles'],np.float64)
 lib=ctypes.CDLL(str(root/'rigid_with_court.so'));lib.pcve_set_court_mesh.argtypes=[ctypes.c_int,ctypes.c_void_p]
 lib.pcve_set_court_mesh(len(mesh),mesh.ctypes.data_as(ctypes.c_void_p))
 lib.pcve_court_gap.argtypes=[ctypes.c_void_p,ctypes.c_double];lib.pcve_court_gap.restype=ctypes.c_double
 with np.load(path) as z:times=z['times'];positions=z['ball_positions'];radius=float(z['ball_radius'])
 minimum=[1.,0.];samples=0;leaves=0
 def gap(p,t):
  nonlocal samples
  p=np.ascontiguousarray(p,np.float64);v=lib.pcve_court_gap(p.ctypes.data_as(ctypes.c_void_p),1.)-radius;samples+=1
  if v<minimum[0]:minimum[:]=[v,float(t)]
  return v
 def interval(a,b,ta,tb,ga,gb,depth=0):
  nonlocal leaves
  length=float(np.linalg.norm(b-a))
  # Distance to a closed triangle set is 1-Lipschitz. This lower bound covers
  # the entire straight segment, not just its sampled endpoints.
  if min(ga,gb)-length/2>=-1e-8:leaves+=1;return
  mid=(a+b)*.5;t=(ta+tb)*.5;gm=gap(mid,t)
  if gm< -20e-6:raise RuntimeError('Rendered ball path enters background court geometry '+str((gm,t)))
  if depth>=18 or length<1e-8:leaves+=1;return
  interval(a,mid,ta,t,ga,gm,depth+1);interval(mid,b,t,tb,gm,gb,depth+1)
 values=[gap(p,t) for p,t in zip(positions,times)]
 for i in range(len(times)-1):interval(positions[i],positions[i+1],times[i],times[i+1],values[i],values[i+1])
 response=Path(out)/'court_contact_response.json'
 native=json.loads(response.read_text()) if response.exists() else None
 if not present:assert native and native['passed'] and native['contact_corrections']>0
 report={'passed':minimum[0]>=-20e-6,'scope':'Recorded native ball states and their exact piecewise-linear 3D replay against fixed evaluated asset triangles',
  'minimum_observed_gap_m':minimum[0],'minimum_time_s':minimum[1],'samples':samples,'certified_linear_segments':leaves,
  'triangle_count':len(mesh),'geometry_sha256':record['fence_geometry_sha256'],'native_response':native,
  'no_background_contact_observed':native is None,'common_fence_restitution':.35,'common_fence_friction':0.,'material_calibrated':False}
 write(Path(out)/'court_contact_audit.json',report);assert report['passed'];return report
