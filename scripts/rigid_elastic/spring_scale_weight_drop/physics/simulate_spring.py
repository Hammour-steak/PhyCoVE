"""CPU native dynamics. All visible motion derives from this cache, in real time.

Downward displacements are positive. Each turn has its own mass and axial
force. The closed-turn branch includes initial tension and coil contact;
the open branch follows the helical spring E -> G -> k relation. Contacts
have equal and opposite forces and compression-only passive damping.
"""
import argparse,json,math,os,platform,time
from pathlib import Path
from physics.scene import BASELINE,OUT,WORK,spring_constants,write_spec,sha
WORK.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('NUMBA_CACHE_DIR',str(WORK/'numba_cache'))
import numpy as np
from numba import njit
from edit_vocab import CASE_DSL,TIMED_DSL,LABELS,parameters,override_for,case_dsl

@njit(cache=True)
def rhs(y,ms,ei0,ks,kclosed,F0,cs,cguide,kc,cc,mweight,g,gap,present,stop,travel,kstop,cstop,spring):
 # spring False (DELETE spring): no turn exists, so no segment force acts and only the carriage node (the last
 # one) moves; the other turn nodes keep a zero state.
 N=len(ms);dy=np.zeros_like(y);u=y[:N];v=y[N:2*N];w=y[2*N];vw=y[2*N+1]
 T=np.empty(N);diss=0.
 for i in range(N):
  up=0. if i==0 else u[i-1];vp=0. if i==0 else v[i-1]
  e=ei0[i]+u[i]-up;dv=v[i]-vp
  if spring:
   T[i]=F0+(ks if e>=0. else kclosed)*e+cs*dv
   diss+=cs*dv*dv
  else:T[i]=0.
 delta=w-u[-1]-gap;dv=vw-v[-1];normal=0.
 if present and delta>0.:
  normal=kc*delta+cc*max(dv,0.);diss+=cc*max(dv,0.)**2
 penetration=max(u[-1]-travel,0.) if stop else 0.;reaction=0.
 if penetration>0.:
  reaction=kstop*penetration+cstop*max(v[-1],0.);diss+=cstop*max(v[-1],0.)**2
 for i in range(N):
  if not spring and i+1<N:continue
  dy[i]=v[i]
  below=T[i+1] if i+1<N else normal-cguide*v[i]-reaction
  dy[N+i]=g+(below-T[i])/ms[i]
 dy[2*N]=vw if present else 0.
 dy[2*N+1]=g-normal/mweight if present else 0.
 dy[2*N+2]=diss+cguide*v[-1]**2
 return dy

@njit(cache=True)
def integrate(y0,t0,dt,steps,ms,ei0,ks,kclosed,F0,cs,cguide,kc,cc,mweight,g,gap,present,stop,travel,kstop,cstop,spring):
 # y0/t0: the state the run starts from (zeros at t=0 for a whole clip; the restored source state for a timed edit).
 N=len(ms);y=y0.copy();stride=int(round(1/24/dt));dense_stride=int(round(.001/dt))
 frames=np.zeros((steps//stride+1,len(y)));frames[0]=y;dense=np.zeros((steps//dense_stride+1,8));dense[0,0]=t0
 frame_i=1;dense_i=1;minimum_e=0.;peak_T=0.;peak_contact=0.;peak_stop=0.;peak_pitch=0.
 for step in range(1,steps+1):
  a=rhs(y,ms,ei0,ks,kclosed,F0,cs,cguide,kc,cc,mweight,g,gap,present,stop,travel,kstop,cstop,spring)
  b=rhs(y+dt*.5*a,ms,ei0,ks,kclosed,F0,cs,cguide,kc,cc,mweight,g,gap,present,stop,travel,kstop,cstop,spring)
  c=rhs(y+dt*.5*b,ms,ei0,ks,kclosed,F0,cs,cguide,kc,cc,mweight,g,gap,present,stop,travel,kstop,cstop,spring)
  d=rhs(y+dt*c,ms,ei0,ks,kclosed,F0,cs,cguide,kc,cc,mweight,g,gap,present,stop,travel,kstop,cstop,spring)
  y+=dt/6*(a+2*b+2*c+d)
  if step%stride==0:frames[frame_i]=y;frame_i+=1
  if step%dense_stride==0:
   T=np.empty(N);Us=0.;dmin=0.;emax=0.
   for i in range(N):
    if not spring:
     T[i]=0.;continue
    e=ei0[i]+y[i]-(y[i-1] if i else 0.);stiff=ks if e>=0. else kclosed
    T[i]=F0+stiff*e
    initial_stiff=ks if ei0[i]>=0. else kclosed
    Us+=F0*e+.5*stiff*e*e-(F0*ei0[i]+.5*initial_stiff*ei0[i]**2)
    dmin=min(dmin,e);emax=max(emax,e)
   delta=max(y[2*N]-y[N-1]-gap,0.) if present else 0.
   dv=y[2*N+1]-y[2*N-1]
   normal=kc*delta+cc*max(dv,0.) if delta>0 else 0.
   sp=max(y[N-1]-travel,0.) if stop else 0.
   fr=kstop*sp+cstop*max(y[2*N-1],0.) if sp>0 else 0.
   energy=.5*np.sum(ms*y[N:2*N]**2)-np.sum(ms*g*y[:N])+Us+.5*kc*delta**2+.5*kstop*sp**2
   if present:energy+=.5*mweight*y[2*N+1]**2-mweight*g*y[2*N]
   dense[dense_i]=np.array([t0+step*dt,y[N-1],y[2*N],normal,fr,energy,y[-1],delta]);dense_i+=1
   minimum_e=min(minimum_e,dmin);peak_T=max(peak_T,np.max(T));peak_contact=max(peak_contact,normal);peak_stop=max(peak_stop,fr);peak_pitch=max(peak_pitch,emax)
 return frames,dense,np.array([minimum_e,peak_T,peak_contact,peak_stop,peak_pitch])

def equilibrium_segments(p,load_n=0.):
 dc=spring_constants(p);N=p['spring_active_turns'];Ms=dc['active_spring_mass_kg'];g=p['gravity_m_s2']
 T=(p['carriage_mass_kg']+Ms*(N-np.arange(1,N+1)+.5)/N)*g+load_n
 e=np.where(T>=p['spring_initial_tension_n'],(T-p['spring_initial_tension_n'])/(N*dc['axial_rate_n_m']),
            (T-p['spring_initial_tension_n'])/p['closed_turn_contact_stiffness_n_m'])
 return e

# DELETE spring: nothing holds the carriage, so it slides down the guide rods until its two guide bushings
# (8.5 mm below the crosshead centre) land on the lower guide shoes, whose tops are at z = 0.288 m
# (appearance/render_spring.py). That landing uses the solver's travel-stop contact law with the declared stop
# contact stiffness and compression damping.
GUIDE_SHOE_TOP_Z_M=.288
GUIDE_BUSHING_HALF_LENGTH_M=.0085

def guide_shoe_travel(p,ei0):
 """Carriage travel at which the guide bushings touch the lower guide shoes (initial crosshead centre as in the renderer)."""
 end=p['coil_top_z_m']-float(np.sum(p['spring_wire_diameter_m']+ei0))
 cross=end-p['lower_hook_length_m']-p['crosshead_height_m']/2
 return cross-GUIDE_BUSHING_HALF_LENGTH_M-GUIDE_SHOE_TOP_Z_M

def solve(case,dt=1/48000,write=True,source_cache=None):
 p=parameters(case)
 if 'timed_edits' in p:return solve_timed(case,p,dt,write,source_cache)
 dc=spring_constants(p);N=p['spring_active_turns'];Ms=dc['active_spring_mass_kg']
 # Source pan self-weight pre-extends the spring. The E edit retains that
 # exact initial pose and is allowed to relax physically; it is not retared.
 ei0=equilibrium_segments(BASELINE);ms=np.full(N,Ms/N);ms[-1]=p['carriage_mass_kg']+Ms/(2*N)
 spring=bool(p.get('spring_present',True));stop=p['stop_present'];travel=p['stop_travel_m']
 if not spring:ms[-1]=p['carriage_mass_kg'];stop=True;travel=guide_shoe_travel(p,ei0)
 gap=p['weight_initial_bottom_z_m']-p['pan_pad_top_z_m'];steps=round(4/dt)
 start=time.time()
 states,dense,extrema=integrate(np.zeros(2*N+3),0.,dt,steps,ms,ei0,dc['axial_rate_n_m']*N,p['closed_turn_contact_stiffness_n_m'],
 p['spring_initial_tension_n'],p['spring_internal_segment_damping_ns_m'],p['guide_damping_ns_m'],
 p['pad_contact_stiffness_n_m'],p['pad_compression_damping_ns_m'],p['weight_mass_kg'],p['gravity_m_s2'],gap,
 p['weight_present'],stop,travel,p['stop_contact_stiffness_n_m'],p['stop_compression_damping_ns_m'],spring)
 coil_z0=p['coil_top_z_m']-np.r_[0,np.cumsum(p['spring_wire_diameter_m']+ei0)]
 coil_z=np.empty((97,N+1));coil_z[:,0]=p['coil_top_z_m'];coil_z[:,1:]=coil_z0[1:]-states[:,:N]
 pan_z=p['pan_pad_top_z_m']-states[:,N-1]
 weight_bottom=p['weight_initial_bottom_z_m']-states[:,2*N]
 C=p['spring_mean_diameter_m']/p['spring_wire_diameter_m'];wahl=(4*C-1)/(4*C-4)+.615/C
 peak_stress=wahl*8*extrema[1]*p['spring_mean_diameter_m']/(math.pi*p['spring_wire_diameter_m']**3)
 energy_error=np.max(np.abs(dense[:,5]+dense[:,6]));initial_energy=p['weight_mass_kg']*p['gravity_m_s2']*gap if p['weight_present'] else 1.
 contact_i=np.flatnonzero(dense[:,3]>0.)
 report={'case':case,'physics':p,'derived':dc,'dt_s':dt,'steps':steps,'solver':'Numba CPU fixed-step RK4, 28 massive axial spring segments, passive contacts',
 'seconds':time.time()-start,'cpu_environment':{'platform':platform.platform(),'python':platform.python_version(),'numpy':np.__version__},
 'max_travel_m':float(dense[:,1].max()),'final_travel_m':float(states[-1,N-1]),'max_pad_compression_m':float(dense[:,7].max()),
 'first_contact_s':float(dense[contact_i[0],0]) if len(contact_i) else None,
 'stationary_pan_freefall_contact_s':math.sqrt(2*gap/p['gravity_m_s2']) if p['weight_present'] else None,
 'max_spring_tension_n':float(extrema[1]),'max_contact_n':float(extrema[2]),'max_stop_reaction_n':float(extrema[3]),
 'max_wire_shear_stress_pa_wahl':float(peak_stress),'max_helix_angle_deg':math.degrees(math.atan((p['spring_wire_diameter_m']+extrema[4])/(math.pi*p['spring_mean_diameter_m']))),
 'max_closed_turn_compression_m':float(-extrema[0]),'max_energy_balance_error_j':float(energy_error),'energy_error_fraction_of_drop_energy':float(energy_error/initial_energy),
 'initial_pose_sha256':__import__('hashlib').sha256(np.r_[coil_z0,p['pan_pad_top_z_m'],p['weight_initial_bottom_z_m']].tobytes()).hexdigest(),
 'frame_times_s':(np.arange(97)/24).tolist(),'first96_frames_are_video':True,'endpoint4s_is_validation_only':True,
 'static_loaded_travel_m':float(np.sum(equilibrium_segments(p,p['weight_mass_kg']*p['gravity_m_s2'] if p['weight_present'] else 0.)-ei0)),
 'trajectory_is_native_solver_output':True,'experimental_material_calibration':False}
 if not spring:
  for key in ('max_wire_shear_stress_pa_wahl','max_helix_angle_deg','max_closed_turn_compression_m','static_loaded_travel_m'):report[key]=None
  report['solver']='Numba CPU fixed-step RK4; no spring: guided rigid carriage and freely falling rigid mass, passive contacts'
  report['spring_absent']={'carriage_node_mass_kg':float(ms[-1]),'guide_shoe_travel_m':travel,'guide_shoe_top_z_m':GUIDE_SHOE_TOP_Z_M,
   'guide_bushing_half_length_m':GUIDE_BUSHING_HALF_LENGTH_M,'landing_contact':'travel-stop contact law with stop_contact_stiffness_n_m and stop_compression_damping_ns_m',
   'turn_nodes':'no spring turns: turn nodes 1-27 keep a zero state; node 28 is the carriage'}
 if write:
  folder=OUT/'cases'/case;folder.mkdir(parents=True,exist_ok=True)
  np.savez_compressed(folder/'native_dynamics.npz',frame_times_s=np.arange(97)/24,states=states,coil_node_z_m=coil_z,pan_pad_top_z_m=pan_z,weight_bottom_z_m=weight_bottom,
   node_masses_kg=ms,initial_segment_extension_m=ei0,dense_columns=np.array(['time_s','travel_m','weight_drop_m','normal_n','stop_n','mechanical_energy_j','dissipation_j','pad_compression_m']),dense=dense)
  report['native_cache_sha256']=sha(folder/'native_dynamics.npz')
  (folder/'physics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  (folder/'scenario_override.json').write_text(json.dumps(override_for(case),indent=2),encoding='utf-8')
  (folder/'edit.json').write_text(json.dumps({'case':case,'label_zh':LABELS[case],'dsl':case_dsl(case)},ensure_ascii=False,indent=2),encoding='utf-8')
 return report,states,dense

def solve_timed(case,p,dt,write,source_cache):
 """Timed edit (AT FRAME k): frames 1..k-1 are the accepted source cache itself. The complete RK4 state of
 source frame k (t=(k-1)/24: every turn displacement and velocity, the falling weight and the dissipation
 integral) is restored from that cache, the edited parameters apply from there on and the same integrator
 continues to 4 s. The cache stores the full state vector y of every frame, so the hand-off is exact."""
 import hashlib
 schedule=p.pop('timed_edits')
 assert len(schedule)==1,'One timed edit per case'
 frame=int(schedule[0]['frame']);change=dict(schedule[0]['params']);j=frame-1
 assert set(change)<={'weight_mass_kg','spring_young_modulus_pa','guide_damping_ns_m'},'Only the scalar material edits can be timed'
 if source_cache is None:raise ValueError('A timed edit needs the accepted source cache (--source-cache .../cases/source/native_dynamics.npz)')
 source_cache=Path(source_cache);src=dict(np.load(source_cache,allow_pickle=False))
 src_report=json.loads((source_cache.parent/'physics.json').read_text(encoding='utf-8'))
 assert src_report['case']=='source' and src_report['dt_s']==dt and src_report['physics']==parameters('source'),'Source cache and current source parameters differ'
 stride=round(1/24/dt);assert src['states'].shape[0]==97 and abs(src['frame_times_s'][j]-j/24)<1e-12
 after=dict(p,**change);dc=spring_constants(after);N=after['spring_active_turns'];Ms=dc['active_spring_mass_kg']
 ei0=equilibrium_segments(BASELINE);ms=np.full(N,Ms/N);ms[-1]=after['carriage_mass_kg']+Ms/(2*N)
 gap=after['weight_initial_bottom_z_m']-after['pan_pad_top_z_m'];steps=(96-j)*stride
 start=time.time()
 cont,dense,extrema=integrate(np.array(src['states'][j],dtype=np.float64),j/24,dt,steps,ms,ei0,dc['axial_rate_n_m']*N,after['closed_turn_contact_stiffness_n_m'],
 after['spring_initial_tension_n'],after['spring_internal_segment_damping_ns_m'],after['guide_damping_ns_m'],
 after['pad_contact_stiffness_n_m'],after['pad_compression_damping_ns_m'],after['weight_mass_kg'],after['gravity_m_s2'],gap,
 after['weight_present'],after['stop_present'],after['stop_travel_m'],after['stop_contact_stiffness_n_m'],after['stop_compression_damping_ns_m'],True)
 handoff=float(np.max(np.abs(cont[0]-src['states'][j])));assert handoff<1e-12,('Source state was not restored exactly',handoff)
 states=np.concatenate([src['states'][:j],cont]);assert states.shape==src['states'].shape and np.array_equal(states[:j],src['states'][:j])
 coil_z0=p['coil_top_z_m']-np.r_[0,np.cumsum(p['spring_wire_diameter_m']+ei0)]
 coil_z=np.empty((97,N+1));coil_z[:,0]=p['coil_top_z_m'];coil_z[:,1:]=coil_z0[1:]-states[:,:N]
 pan_z=p['pan_pad_top_z_m']-states[:,N-1];weight_bottom=p['weight_initial_bottom_z_m']-states[:,2*N]
 for key,value in (('coil_node_z_m',coil_z),('pan_pad_top_z_m',pan_z),('weight_bottom_z_m',weight_bottom)):
  assert np.array_equal(value[:j],src[key][:j]),key
 merged_dense=np.concatenate([src['dense'][src['dense'][:,0]<=j/24+1e-12],dense[1:]])
 energy_after=dense[1:,5]+dense[1:,6]
 report={'case':case,'physics':p,'timed_edits':schedule,'physics_after_edit':after,'derived':spring_constants(p),'derived_after_edit':dc,'dt_s':dt,'steps':96*stride,
 'solver':'Numba CPU fixed-step RK4, 28 massive axial spring segments, passive contacts; timed edit continued from the restored source state',
 'seconds':time.time()-start,'cpu_environment':{'platform':platform.platform(),'python':platform.python_version(),'numpy':np.__version__},
 'timed_edit':{'frame':frame,'time_s':j/24,'step':j*stride,'params_before':{k:p[k] for k in change},'params_after':change,
  'source_cache':str(source_cache),'source_cache_sha256':hashlib.sha256(source_cache.read_bytes()).hexdigest(),
  'source_frames_kept':[1,j],'continued_frames':[frame,96],'state_handoff_max_abs':handoff,
  'continuation':'The state vector y of source frame %d (all 28 turn displacements and velocities, the falling weight, the dissipation integral) is the initial value; RK4 with the edited parameters from step %d on.'%(frame,j*stride)},
 'max_travel_m':float(merged_dense[:,1].max()),'final_travel_m':float(states[-1,N-1]),'max_pad_compression_m':float(merged_dense[:,7].max()),
 'continuation_max_spring_tension_n':float(extrema[1]),'continuation_max_contact_n':float(extrema[2]),
 'continuation_energy_balance_drift_j':float(np.max(np.abs(energy_after-energy_after[0]))) if len(energy_after) else 0.,
 'energy_note':'The mass change at the edit frame changes the mechanical energy of the falling weight; the energy balance is checked within the continuation.',
 'frame_times_s':(np.arange(97)/24).tolist(),'first96_frames_are_video':True,'endpoint4s_is_validation_only':True,
 'trajectory_is_native_solver_output':True,'experimental_material_calibration':False}
 if write:
  folder=OUT/'cases'/case;folder.mkdir(parents=True,exist_ok=True)
  np.savez_compressed(folder/'native_dynamics.npz',frame_times_s=np.arange(97)/24,states=states,coil_node_z_m=coil_z,pan_pad_top_z_m=pan_z,weight_bottom_z_m=weight_bottom,
   node_masses_kg=ms,initial_segment_extension_m=ei0,dense_columns=np.array(['time_s','travel_m','weight_drop_m','normal_n','stop_n','mechanical_energy_j','dissipation_j','pad_compression_m']),dense=merged_dense)
  report['native_cache_sha256']=sha(folder/'native_dynamics.npz')
  (folder/'physics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  (folder/'scenario_override.json').write_text(json.dumps(override_for(case),indent=2),encoding='utf-8')
  (folder/'state_handoff.json').write_text(json.dumps(report['timed_edit'],indent=2),encoding='utf-8')
  (folder/'edit.json').write_text(json.dumps({'case':case,'label_zh':LABELS[case],'dsl':TIMED_DSL[case]},ensure_ascii=False,indent=2),encoding='utf-8')
 return report,states,merged_dense

def main():
 global OUT
 ap=argparse.ArgumentParser();ap.add_argument('--case',choices=list(CASE_DSL)+list(TIMED_DSL)+['all'],default='all');ap.add_argument('--convergence',action='store_true')
 ap.add_argument('--out',type=Path,required=True,help='New output root: cases/<case>/, scene_spec.json and physics_suite.json are written there')
 ap.add_argument('--source-cache',type=Path,help='Timed edits: the accepted source native_dynamics.npz whose frame k state is continued');a=ap.parse_args()
 OUT=a.out;write_spec(OUT)
 reports=[]
 for case in CASE_DSL if a.case=='all' else [a.case]:
  report,states,dense=solve(case,source_cache=a.source_cache);reports.append(report)
  print(json.dumps({k:report[k] for k in ['case','seconds','max_travel_m','max_pad_compression_m','max_energy_balance_error_j','max_wire_shear_stress_pa_wahl']}),flush=True)
  if a.convergence:
   fine,fstates,fdense=solve(case,dt=1/96000,write=False)
   check={'case':case,'coarse_dt_s':1/48000,'fine_dt_s':1/96000,'max_sampled_pan_error_m':float(np.max(np.abs(states[:,27]-fstates[:,27]))),
    'max_sampled_weight_error_m':float(np.max(np.abs(states[:,56]-fstates[:,56]))),'max_travel_difference_m':abs(report['max_travel_m']-fine['max_travel_m']),
    'fine_energy_balance_error_j':fine['max_energy_balance_error_j']}
   check['passed']=check['max_sampled_pan_error_m']<.0003 and check['max_sampled_weight_error_m']<.0003
   (OUT/'cases'/case/'convergence.json').write_text(json.dumps(check,indent=2),encoding='utf-8');print('CONVERGENCE',json.dumps(check),flush=True)
 (OUT/'physics_suite.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')

if __name__=='__main__':main()
