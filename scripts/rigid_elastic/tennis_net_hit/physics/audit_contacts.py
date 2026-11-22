"""Check exact native finite contact pairs on the rendered interpolation clock."""
from pathlib import Path
import argparse,ctypes,json,os,subprocess,time
import numpy as np
from playback_math import hermite
from common import INPUTS
import owner_adapter as backend
from coupled_geometry import build_context

CODE=r'''
API double audit_recorded_pairs(int nk,const int *pairs,const double *radius,const double *xx,int *worst){
 const V *x=(const V*)xx;double minimum=.0005;*worst=-1;
 for(int k=0;k<nk;k++){
  const int *row=pairs+6*k;V a=x[row[1]],b=x[row[2]],p=x[row[3]],q=x[row[4]],s=row[0]?q:x[row[5]];
  double r=radius[k]+.0005;
  if(std::min(a.x,b.x)-r>std::max({p.x,q.x,s.x})||std::max(a.x,b.x)+r<std::min({p.x,q.x,s.x})||
     std::min(a.y,b.y)-r>std::max({p.y,q.y,s.y})||std::max(a.y,b.y)+r<std::min({p.y,q.y,s.y})||
     std::min(a.z,b.z)-r>std::max({p.z,q.z,s.z})||std::max(a.z,b.z)+r<std::min({p.z,q.z,s.z}))continue;
  double distance;
  if(row[0]){double u,v;V pa,pb;segment_closest(a,b,p,q,u,v,pa,pb);distance=norm(sub(pa,pb));}
  else distance=segment_triangle(a,b,p,q,s).distance;
  double gap=distance-radius[k];if(gap<minimum){minimum=gap;*worst=k;}
 }
 return minimum;
}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--record-fps',type=int,default=960)
 p.add_argument('--interpolation',choices=('linear','hermite'),default='linear')
 p.add_argument('--shutter-only',action='store_true')
 p.add_argument('--shutter-hz',type=int,choices=(3840,7680,15360),default=7680);a=p.parse_args()
 if os.name!='posix':raise RuntimeError('Remote audit only')
 a.out.mkdir(parents=True,exist_ok=True)
 text=(INPUTS/'frozen/finite_strip_prototype.cpp').read_text();prefix=text[:text.index('// Inputs contain strip nodes')]
 source=a.out/'recorded_contact_audit.cpp';source.write_text(prefix+'\n'+CODE)
 libpath=a.out/'recorded_contact_audit.so'
 subprocess.run(['g++','-O3','-std=c++17','-shared','-fPIC',str(source),'-o',str(libpath)],check=True)
 lib=ctypes.CDLL(str(libpath));lib.audit_recorded_pairs.argtypes=[ctypes.c_int]+[ctypes.c_void_p]*4+[ctypes.POINTER(ctypes.c_int)]
 # nk, pairs, radius, positions, worst (four arguments after nk)
 lib.audit_recorded_pairs.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)]
 lib.audit_recorded_pairs.restype=ctypes.c_double
 net,config,hinges,strip,d=backend.load_initial()
 context=build_context(net,strip,True);vertices=context['positions'].copy()
 pairs=np.ascontiguousarray(context['contact_pairs'],np.int32);radii=np.ascontiguousarray(context['contact_radii'],np.float64)
 with np.load(a.cache) as z:
  times=z['times'];sx=z['strap_positions'];skin=z['strap_surface_positions'];nx=z['net_positions'];band=z['band_positions']
  faces=z['strap_surface_faces'];vel=z['strap_velocities']
  if a.interpolation=='hermite':nv=z['net_velocities'];bv=z['band_velocities']
 if a.shutter_only:
  half=a.shutter_hz//960
  clocks=np.unique(np.clip((np.arange(96)[:,None]/24+np.arange(-half,half+1)/a.shutter_hz).ravel(),0.,float(times[-1])))
 else:clocks=np.arange(round(float(times[-1])*a.record_fps)+1)/a.record_fps
 count=len(clocks)
 samples=[];started=time.monotonic();ns=context['strip_node_count'];first=context['net_pool_first'];virtual=context['virtual_first']
 ptr=lambda x:x.ctypes.data_as(ctypes.c_void_p)
 for k in range(count):
  t=float(clocks[k]);i=max(0,min(len(times)-2,int(np.searchsorted(times,t,side='right')-1)));alpha=(t-times[i])/(times[i+1]-times[i])
  if a.interpolation=='hermite':
   h=times[i+1]-times[i];ids=context['net_pool_indices'];bi=context['native_band_vertex_ids']
   vertices[:ns]=hermite(sx[i],vel[i],sx[i+1],vel[i+1],alpha,h)
   vertices[first:first+len(ids)]=hermite(nx[i,ids],nv[i,ids],nx[i+1,ids],nv[i+1,ids],alpha,h)
   vertices[virtual:]=hermite(band[i,bi],bv[i,bi],band[i+1,bi],bv[i+1,bi],alpha,h)
  else:
   vertices[:ns]=(1-alpha)*sx[i]+alpha*sx[i+1]
   vertices[first:first+len(context['net_pool_indices'])]=(1-alpha)*nx[i,context['net_pool_indices']]+alpha*nx[i+1,context['net_pool_indices']]
   vertices[virtual:]=(1-alpha)*band[i,context['native_band_vertex_ids']]+alpha*band[i+1,context['native_band_vertex_ids']]
  worst=ctypes.c_int(-1)
  gap=lib.audit_recorded_pairs(len(pairs),ptr(pairs),ptr(radii),ptr(vertices),ctypes.byref(worst))
  samples.append({'time_s':t,'minimum_gap_m':gap,'worst_declared_pair':worst.value})
  if k%240==0:print(json.dumps({'audit_time_s':t,'min_gap_m':min(x['minimum_gap_m'] for x in samples)}),flush=True)
 minimum=min(samples,key=lambda x:x['minimum_gap_m'])
 tail=times>=2.;speed=np.linalg.norm(vel,axis=2)
 displacement=skin[tail]-skin[tail].mean(axis=0,keepdims=True) if np.any(tail) else skin-skin.mean(axis=0,keepdims=True)
 report={'scope':(f'Actual 24 FPS shutter intervals, 1/480 s exposure, sampled on a {a.shutter_hz} Hz clock; includes midpoints between the 3840 Hz replay deformation keys; all movie frame centers are genuine native states' if a.shutter_only else 'All declared physical contacts on a uniform observation clock'),
  'shutter_only':a.shutter_only,'observation_clock_hz':a.shutter_hz if a.shutter_only else a.record_fps,
  'interpolation':a.interpolation,
  'samples':samples,'minimum':minimum,'render_penetration_tolerance_m':20e-6,
  'passed':minimum['minimum_gap_m']>=-20e-6,'physical_native_overlap_gate_m':1e-9,
  'physical_native_stationarity_gate_n':1e-5,'physical_native_gates_not_relaxed':True,
  'tail_rms_surface_displacement_about_per_vertex_time_mean_m':float(np.sqrt(np.mean(displacement*displacement))),
  'tail_max_speed_m_s':float(speed[tail].max()) if np.any(tail) else None,
  'tail_rms_speed_m_s':float(np.sqrt(np.mean(speed[tail]**2))) if np.any(tail) else None,
  'contact_pair_count':len(pairs),'runtime_s':time.monotonic()-started,'blender_invoked':False,
  'uncalibrated_material':True,'accepted_benchmark_gt':False}
 (a.out/'render_contact_audit.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k!='samples'}),flush=True)
 if not report['passed']:raise SystemExit(2)

if __name__=='__main__':main()
