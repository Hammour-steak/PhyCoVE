"""Portable path/packet adapter around unchanged recorded solver modules."""
import ctypes
import json
import sys
import numpy as np
from common import INPUTS, PACKET_SHA, sha

FROZEN=INPUTS/'frozen'
sys.path.insert(0,str(FROZEN))
import frozen_physics_model as BASE
CONTRACT=json.loads((FROZEN/'backend_contract.json').read_text())
BASE.DIAGNOSTIC_NAMES=CONTRACT['ancestor_diagnostic_names']
DIAGNOSTIC_NAMES=CONTRACT['diagnostic_names']
sys.modules['coupled_solver']=sys.modules[__name__]
import contact_geometry,coupled_geometry,coupled_abi
contact_geometry.FIXTURE=FROZEN/'anchor_fixture_geometry.json'
coupled_geometry.FIXTURE=contact_geometry.FIXTURE
# Python binds default arguments when a module is imported. Updating FIXTURE
# alone leaves this original function's path pointing at the original checkout.
# Rebind only the asset path; preserve the frozen geometry implementation.
assert len(contact_geometry.add_canonical_hardware.__defaults__)==1
contact_geometry.add_canonical_hardware.__defaults__=(contact_geometry.FIXTURE,)
assert coupled_geometry.add_canonical_hardware is contact_geometry.add_canonical_hardware
integrate=coupled_abi.integrate


def load_initial():
 packet=FROZEN/'initial_packet.npz';assert sha(packet)==PACKET_SHA
 def decode(v,z):
  if 'array' in v:return np.ascontiguousarray(z[v['array']])
  if 'dict' in v:return {k:decode(x,z) for k,x in v['dict'].items()}
  if 'tuple' in v:return tuple(decode(x,z) for x in v['tuple'])
  if 'list' in v:return [decode(x,z) for x in v['list']]
  return v['literal']
 with np.load(packet) as z:return decode(json.loads(str(z['packet_schema_json']))['tree'],z)


def library(present=True):
 path=FROZEN/'webbing_revision.so' if present else INPUTS/'court_collision/rigid_with_court.so'
 lib=ctypes.CDLL(str(path))
 if present:
  coupled_abi.bind(lib)
  lib.set_webbing_dissipation.argtypes=[ctypes.c_double]*3
  lib.set_webbing_dissipation(.0005,.025,0.)
  lib.get_webbing_dissipation.argtypes=[ctypes.c_void_p]
 else:
  I,P,D=ctypes.c_int,ctypes.c_void_p,ctypes.c_double
  lib.solve.argtypes=[I,I]+[P]*10+[I]+[P]*3+[I,I]+[P]*5+[I]+[P]*3+[I]+[P]*2+[I,D,I,I,I]+[P]*13
  lib.solve.restype=I
  build=json.loads((INPUTS/'court_collision/build.json').read_text())
  assert sha(path)==build['derived_library_sha256']
  mesh=INPUTS/'court_collision/fence_triangles.npz';assert sha(mesh)==build['fence_geometry_sha256']
  with np.load(mesh) as z:triangles=np.ascontiguousarray(z['triangles'],np.float64)
  lib.pcve_set_court_mesh.argtypes=[I,P];lib.pcve_set_court_mesh.restype=I
  assert lib.pcve_set_court_mesh(len(triangles),triangles.ctypes.data_as(P))==len(triangles)
  lib.pcve_court_stats.argtypes=[P]
 return lib


def rigid_integrate(lib,net,config,hinges,duration,fps):
 # Same recorded standalone ABI, parameters and initial dynamic slots. This
 # code does not import output directories on the worker.
 dt=config['simulation_dt_s'];sample=round(1/(fps*dt));steps=round(duration/dt)
 assert steps%sample==0 and abs(sample*dt-1/fps)<1e-12
 count=steps//sample+1;n=len(net['positions'])
 outx=np.empty((count,n,3),np.float32);outv=np.empty_like(outx)
 balls=[np.empty((count,k)) for k in (3,3,3,4)]
 bp,bv,bw,bq=[np.ascontiguousarray(a,np.float64).copy() for a in net['_ball_state']]
 par=np.r_[BASE._params(config,False),0.,0.]
 par[18]=net['top_indices'][len(net['top_indices'])//2]
 band=net['_band_binding'];p=coupled_abi.ptr
 args=[net[k] for k in ('positions','velocities','mass','edges','rest','ea','eta','kind','radii','fixed')]
 bend=[net[k] for k in ('bend_triplets','bend_rest_lengths','bend_ei')]
 b=[band[k] for k in ('band_binding_indices','band_binding_weights','band_binding_offsets','band_faces','band_face_ranges')]
 h=[hinges[k] for k in ('hinge_nodes','hinge_viscosity_nms','hinge_yield_moment_nm')]
 color=[hinges[k] for k in ('hinge_color_offsets','hinge_color_order')]
 diag=np.empty((count,32));summary=np.zeros(18)
 status=lib.solve(n,len(net['edges']),*map(p,args),len(bend[0]),*map(p,bend),len(b[0]),len(band['band_faces']),*map(p,b),len(h[0]),*map(p,h),len(color[0])-1,*map(p,color),steps,dt,sample,0,1,*map(p,[bp,bv,bw,bq,par,outx,outv,*balls,diag,summary]))
 assert status==0,('Rigid native status',status)
 net['_ball_state']=(bp,bv,bw,bq)
 return {'times':np.arange(count)*sample*dt,'net_positions':outx,'net_velocities':outv,
   **dict(zip(('ball_positions','ball_velocities','ball_angular_velocities','ball_quaternions'),balls)),
   'strap_positions':np.empty((count,0,3)),'strap_velocities':np.empty((count,0,3)),
   'strap_surface_positions':np.empty((count,0,3))}
