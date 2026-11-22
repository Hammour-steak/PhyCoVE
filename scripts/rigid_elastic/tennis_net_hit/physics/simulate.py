"""Remote CPU source replay and genuine 3–4 s edit continuation."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import numpy as np
from common import INPUTS, HERE, CASES, KINEMATICS, SOURCE_SHA, LIB_SHA, PACKET_SHA, sha, write
import owner_adapter as owner
from checkpoint_io import restore
from band_geometry import evaluate_band, evaluate_band_velocity


def digest(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def endpoint(net,strip):
 return {'net_positions_f64':net['positions'].copy(),'net_velocities_f64':net['velocities'].copy(),
   'strip_positions':strip['positions'].copy(),'strip_velocities':strip['velocities'].copy(),
   **dict(zip(('ball_position','ball_velocity','ball_angular_velocity','ball_quaternion'),net['_ball_state']))}


def checkpoint_postcheck(inputs,out,speed,ratio):
 net,config,hinges,strip,_=owner.load_initial()
 steel=net['kind']==1;net['ea'][~steel]*=ratio;net['bend_ei']*=ratio
 bp,bv,bw,bq=net['_ball_state'];bv=bv.copy();bv[1]=speed;net['_ball_state']=(bp,bv,bw,bq)
 config['simulation_dt_s']=1/153600;config['speed_m_s']=speed;config['net_present']=True
 lib=owner.library(True);canonical=owner.coupled_abi.configure(lib,net,strip,True)
 restore(lib,net,strip,inputs/'endpoint_0058.npz',canonical)
 result=owner.integrate(lib,net,config,hinges,strip,.05,3840,True)
 proof={}
 with np.load(inputs/'0059.npz') as z:
  rows=np.rint((z['times']-2.95)*3840).astype(int)
  for key in KINEMATICS:
   x,y=result[key][rows],z[key]
   proof[key]={'bit_identical':np.array_equal(x,y),'maximum_absolute_error':float(np.max(np.abs(x-y)))}
 with np.load(inputs/'endpoint_0059.npz') as z:
  for key,x in endpoint(net,strip).items():
   y=z[key];proof['endpoint_'+key]={'bit_identical':np.array_equal(x,y),'maximum_absolute_error':float(np.max(np.abs(x-y)))}
 # Cross-host replay is independently bounded; native physics gates remain
 # 1 nm / 1e-5 N. Bit identity is reported separately, never assumed.
 passed=max(x['maximum_absolute_error'] for x in proof.values())<1e-9
 write(out/'checkpoint_replay.json',{'passed':passed,'checks':proof,'all_bit_identical':all(x['bit_identical'] for x in proof.values()),'scope':'accepted 2.95–3.00 s replay plus full-f64 endpoint'})
 assert passed,proof
 restore(lib,net,strip,inputs/'endpoint_0059.npz',canonical)
 with np.load(inputs/'0059.npz') as z:
  expected={k:z[k][-1] for k in KINEMATICS}
 # Restore stores real f64 fields. Record the exact rendered-state boundary.
 first={'net_positions':net['positions'].astype(np.float32),'net_velocities':net['velocities'].astype(np.float32),
  'strap_positions':strip['positions'],'strap_velocities':strip['velocities'],
  'strap_surface_positions':owner.coupled_abi.thicken(strip['positions'][None],strip['faces'],strip['config']['thickness_m'])[0],
  **dict(zip(('ball_positions','ball_velocities','ball_angular_velocities','ball_quaternions'),net['_ball_state']))}
 continuity={k:np.array_equal(first[k],expected[k]) for k in KINEMATICS}
 write(out/'restart_continuity.json',{'passed':all(continuity.values()),'physical_time_s':3,'bit_identical':continuity});assert all(continuity.values())

 with np.load(out/'restart_rendered_sample.npz') as z:
  actual={k:z[k] for k in KINEMATICS}
 with np.load(inputs/'0059.npz') as z:
  checks={k:np.array_equal(actual[k],z[k][-1]) for k in KINEMATICS}
 write(out/'actual_restart_continuity.json',{'passed':all(checks.values()),'bit_identical':checks,'physical_time_s':3})
 assert all(checks.values()),checks


def main():
 p=argparse.ArgumentParser();p.add_argument('--case',choices=CASES,required=True);p.add_argument('--threads',type=int,default=2);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 assert os.name=='posix'
 assert os.environ.get('CUDA_VISIBLE_DEVICES','')==''
 ident=a.case;present=ident!='remove_entire_net';start=0. if ident in ('source','remove_entire_net') else 3.
 out=a.out;out.mkdir(parents=True,exist_ok=False)
 snapshots=out/'execution_code';snapshots.mkdir()
 for name in ('simulate.py','owner_adapter.py','checkpoint_io.py','common.py'):shutil.copy2(HERE/name,snapshots/name)
 write(snapshots/'sha256.json',{p.name:sha(p) for p in snapshots.iterdir()})
 inputs=INPUTS/'inputs'/ident;receipt=json.loads((inputs/'input_receipt.json').read_text())
 for name,row in receipt['files'].items():
  if name in ('prefix_samples.npz','0059.npz','endpoint_0058.npz'):continue
  if name=='endpoint_0059.npz' and not start:continue
  assert sha(inputs/name)==row['sha256']
 assert sha(INPUTS/'frozen/webbing_revision.so')==LIB_SHA
 net,config,hinges,strip,loss=owner.load_initial();reference=net['positions'].copy()
 _,dsl,speed,ratio=CASES[ident]
 before={k:digest(net[k]) for k in ('positions','velocities','mass','rest','eta','fixed')}
 original_ball=tuple(x.copy() for x in net['_ball_state'])
 original_strip={k:digest(strip[k]) for k in ('positions','velocities','mass','rest')}
 steel=net['kind']==1;original_ea=net['ea'].copy();original_ei=net['bend_ei'].copy()
 net['ea'][~steel]*=ratio;net['bend_ei']*=ratio
 bp,bv,bw,bq=net['_ball_state'];bv=bv.copy();bv[1]=speed;net['_ball_state']=(bp,bv,bw,bq)
 config['speed_m_s']=speed;config['net_present']=present;config['simulation_dt_s']=1/153600
 checks={k:digest(net[k])==h for k,h in before.items()}
 checks.update({f'strip_{k}':digest(strip[k])==h for k,h in original_strip.items()})
 checks.update(steel_EA=np.array_equal(net['ea'][steel],original_ea[steel]),
   material_EA=np.array_equal(net['ea'][~steel],original_ea[~steel]*ratio),
   material_EI=np.array_equal(net['bend_ei'],original_ei*ratio),
   ball_position=np.array_equal(bp,original_ball[0]),ball_quaternion=np.array_equal(bq,original_ball[3]),
   ball_spin=np.array_equal(bw,original_ball[2]),ball_velocity_xz=np.array_equal(bv[[0,2]],original_ball[1][[0,2]]))
 assert all(checks.values()),checks
 sys.path.insert(0,str(INPUTS/'frozen'))
 import pcve_edit_dsl,current_edit_vocab
 assert current_edit_vocab.TOTAL_FRAMES==96
 if dsl:
  parsed=pcve_edit_dsl.parse(dsl,current_edit_vocab.VOCAB)
  actual=current_edit_vocab.solver_overrides(parsed)
  assert actual==({'net_present':False} if not present else {'ball_initial_velocity_y_m_s':speed} if ident.startswith('ball_') else {'net_young_modulus_pa':25e6*ratio})
 lib=owner.library(present)
 setup={'revision':'standard_net_solve','case_id':ident,'edit_dsl':dsl,'speed_m_s':speed,'net_young_modulus_pa':25e6*ratio,
  'net_present':present,'initial_inputs_audit':checks,'source_ancestor_cache_sha256':SOURCE_SHA,'common_initial_packet_sha256':PACKET_SHA,
  'parent_cache_sha256':receipt['parent_physical_cache_sha256'],'executed_library_sha256':sha(Path(lib._name)),
  'physical_start_s':start,'requested_physical_stop_s':4.,'fps':24,'frames':96,'resolution':[1280,720],
  'simulation_dt_s':config['simulation_dt_s'],'native_record_hz':3840,'worker_host':os.uname().nodename,
  'execution':'remote_CPU_only','gpu_allocated':False,'pid':os.getpid(),'threads':a.threads,'start_unix':time.time(),
  'common_stretch_time_s':.0005,'common_bending_time_s':.025,'common_contact_mu':0.,
  'material_calibrated':False,'accepted_benchmark_gt':False}
 write(out/'setup.json',setup)
 canonical=owner.coupled_abi.configure(lib,net,strip,True) if present else None
 if start:
  restore(lib,net,strip,inputs/'endpoint_0059.npz',canonical)
  restored=endpoint(net,strip)
  with np.load(inputs/'endpoint_0059.npz') as z:checks={k:np.array_equal(v,z[k]) for k,v in restored.items()}
  write(out/'restart_f64_input.json',{'passed':all(checks.values()),'bit_identical':checks})
  assert all(checks.values())
 old_hashes=json.loads((inputs/'original_chunk_kinematics.json').read_text()) if ident=='source' else None
 chunks=out/'chunks';chunks.mkdir();paths=[];clock=start;wall=time.monotonic();peak=0.
 source_maximum_difference=None
 while clock<4-1e-9:
  index=round(clock/.05);duration=.05
  try:
   result=(owner.integrate(lib,net,config,hinges,strip,duration,3840,True) if present else owner.rigid_integrate(lib,net,config,hinges,duration,3840))
  except Exception as error:
   write(out/'failure.json',{'error':str(error),'physical_time_s':clock,'completed':False});raise
  if old_hashes is not None and index<60:
   row={'chunk':index,'arrays':{k:digest(result[k][::8])==old_hashes[index]['arrays'][k]['sha256'] for k in KINEMATICS}}
   with (out/'source_replay_hashes.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
  result['times']+=clock
  if start and abs(clock-start)<1e-10:
   np.savez_compressed(out/'restart_rendered_sample.npz',**{k:result[k][0].copy() for k in KINEMATICS})
  nt=len(result['times']);ticks=np.rint(result['times']*3840).astype(np.int64)
  keep=(ticks%160<=4)|(ticks%160>=156)
  arrays={k:result[k][keep] for k in ('times',*KINEMATICS)}
  if present:
   arrays['band_positions']=evaluate_band(arrays['net_positions'],net['_band_binding']).astype(np.float32)
   arrays['band_velocities']=evaluate_band_velocity(arrays['net_velocities'],net['_band_binding']).astype(np.float32)
   length=np.linalg.norm(arrays['net_positions'][:,net['edges'][~steel,1]]-arrays['net_positions'][:,net['edges'][~steel,0]],axis=2)
   peak=max(peak,float(np.maximum(length/net['rest'][~steel]-1,0).max()))
  else:
   for key in ('net_positions','net_velocities','strap_positions','strap_velocities','strap_surface_positions','band_positions','band_velocities'):arrays[key]=np.empty((int(keep.sum()),0,3))
  path=chunks/f'{index:04d}.npz';np.savez_compressed(path,**arrays);paths.append(path)
  np.savez_compressed(chunks/f'endpoint_{index:04d}.npz',**endpoint(net,strip))
  clock+=duration
  write(out/'progress.json',{'case_id':ident,'physical_time_s':clock,'runtime_s':time.monotonic()-wall,'source_replay_maximum_visible_difference_m':source_maximum_difference,'native_gates_unchanged':True})
  print(json.dumps({'case_id':ident,'physical_time_s':clock,'runtime_s':time.monotonic()-wall}),flush=True)
 # Native calculation is complete even if the slower reference/copy phase
 # is still recovering from SSH interruptions. Nothing is published until
 # every required immutable reference has arrived and validation has passed.
 write(out/'native_interval_complete.json',{'physical_start_s':start,'physical_stop_s':4,'native_gates_passed':True})
 if not present:
  statistics=np.zeros(12,np.float64);lib.pcve_court_stats(statistics.ctypes.data_as(ctypes.c_void_p))
  write(out/'court_contact_response.json',{'passed':bool(statistics[0]>0 and statistics[2]>=-1e-8),
    'contact_corrections':int(statistics[0]),'maximum_predictor_overlap_m':float(statistics[1]),'energy_dissipated_j':float(statistics[2]),
    'total_normal_impulse_ns':statistics[3:6].tolist(),'first_contact_s':float(statistics[6]),'position_projection_gravity_work_j':float(statistics[7]),
    'maximum_native_step_travel_m':float(statistics[8]),'native_final_overlap_gate_m':1e-9,'restitution':.35,'friction':0.,'actual_render_asset_triangles':True,'material_calibrated':False})
  assert statistics[0]>0 and statistics[2]>=-1e-8
 required=['prefix_samples.npz']+(['endpoint_0058.npz','0059.npz'] if start else [])
 deadline=time.monotonic()+86400
 while not all((inputs/name).is_file() for name in required):
  write(out/'progress.json',{'case_id':ident,'physical_time_s':4,'stage':'waiting_for_verified_reference_inputs','missing':[n for n in required if not (inputs/n).is_file()]})
  if time.monotonic()>deadline:raise RuntimeError('Reference-input wait limit; native chunks retained')
  time.sleep(20)
 for name in required:assert sha(inputs/name)==receipt['files'][name]['sha256']
 with np.load(inputs/'prefix_samples.npz') as z:old={k:z[k] for k in z.files}
 if start:checkpoint_postcheck(inputs,out,speed,ratio)
 # Actual prefix values and new native continuation meet at the verified f64
 # endpoint. No temporal stretching, frozen tail or positional correction.
 dynamic=('times',*KINEMATICS,'band_positions','band_velocities')
 offsets=[];previous_time=float(old['times'][-1]) if start else None
 for path in paths:
  with np.load(path) as z:
   duplicate=previous_time is not None and abs(float(z['times'][0])-previous_time)<1e-10
   offsets.append(1 if duplicate else 0);previous_time=float(z['times'][-1])
 cache={}
 for key in dynamic:
  rows=[]
  if start:rows.append(old[key])
  for offset,path in zip(offsets,paths):
   with np.load(path) as z:rows.append(z[key][offset:])
  cache[key]=np.concatenate(rows)
 cache.update(net_edges=net['edges'],net_edge_kind=net['kind'],net_present=np.array(present),center_strap_present=np.array(present),
  strap_surface_faces=strip['surface_faces'] if present else np.empty((0,3),np.int32),
  strap_width_m=np.array(.045),strap_thickness_m=np.array(.0007),ball_mass=np.array(.0576),ball_radius=np.array(config['ball_radius_m']),
  net_edge_axial_rigidity=net['ea'],net_bend_ei=net['bend_ei'],net_node_masses=net['mass'],net_edge_radii=net['radii'],band_faces=net['_band_binding']['band_faces'],
  parent_source_cache_sha256=np.array(SOURCE_SHA),native_physical_stop_s=np.array(4.))
 if ident in ('source','remove_entire_net'):
  source_maximum_difference=0.
  for t in np.arange(73)/24:
   i=np.argmin(abs(cache['times']-t));j=np.argmin(abs(old['times']-t))
   assert abs(cache['times'][i]-t)<1e-10 and abs(old['times'][j]-t)<1e-10
   for key in (('net_positions','strap_surface_positions','ball_positions') if present else ('ball_positions',)):
    source_maximum_difference=max(source_maximum_difference,float(np.max(np.abs(cache[key][i]-old[key][j]))))
  assert source_maximum_difference<1e-5,source_maximum_difference
 assert cache['times'][0]==0 and cache['times'][-1]>4-1e-10 and np.all(np.diff(cache['times'])>0)
 centers=np.arange(96)/24;indices=np.asarray([np.argmin(abs(cache['times']-t)) for t in centers])
 assert np.max(abs(cache['times'][indices]-centers))<1e-10
 # All 96 center poses are genuine recorded native states; shutter poses are
 # evaluated on the exact same piecewise-linear deformation used by Cycles.
 np.savez_compressed(out/'simulation.npz',**cache)
 gt={'times':centers,**{k:cache[k][indices] for k in ('ball_positions','ball_velocities','ball_quaternions','net_positions','strap_surface_positions')}}
 np.savez_compressed(out/'ground_truth_24fps.npz',**gt)
 ball=cache['ball_positions'];velocity=cache['ball_velocities']
 completion={**setup,'completed':True,'physical_duration_s':4.,'physical_cache_sha256':sha(out/'simulation.npz'),
  'ground_truth_sha256':sha(out/'ground_truth_24fps.npz'),'all_native_solver_gates_passed':True,
  'new_interval_maximum_pe_strain':peak,'source_replay_maximum_visible_difference_m':source_maximum_difference,
  'ball_rebounded_to_near_side':bool(np.any(velocity[:,1]<-.1)) if present else None,
  'ball_final_position_m':ball[-1].tolist(),'runtime_s':time.monotonic()-wall,'genuine_4s_physics':True}
 if ident=='ball_speed_x2':assert completion['ball_rebounded_to_near_side'] and ball[-1,1]<0
 if not present:assert np.any(ball[:,1]>=0)
 write(out/'completion.json',completion);print('COMPLETE',flush=True)


if __name__=='__main__':main()
