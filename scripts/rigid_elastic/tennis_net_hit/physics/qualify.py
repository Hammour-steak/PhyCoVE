"""Validate exact native frame centers, material bindings and actual replay."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from common import INPUTS,HERE,CASES,LIB_SHA,sha,write
import owner_adapter as owner


def main():
 p=argparse.ArgumentParser();p.add_argument('--case',choices=CASES,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 out=a.out;c=json.loads((out/'completion.json').read_text())
 assert c['completed'] and c['genuine_4s_physics'] and c['all_native_solver_gates_passed']
 raw=out/'simulation.npz';assert sha(raw)==c['physical_cache_sha256']
 _,dsl,speed,ratio=CASES[a.case]
 if a.case=='ball_speed_x2':
  old=json.loads((INPUTS/'inputs'/a.case/'completion.json').read_text())
  assert max(old['peak_observed_pe_strain'],c['new_interval_maximum_pe_strain'])<.2
  assert c['ball_rebounded_to_near_side'] and c['ball_final_position_m'][1]<0
 net,config,hinges,strip,_=owner.load_initial();present=a.case!='remove_entire_net'
 with np.load(raw) as z:
  times=z['times'];assert times[0]==0 and abs(times[-1]-4)<1e-9 and np.all(np.diff(times)>0)
  center=np.arange(96)/24;ii=np.asarray([np.argmin(abs(times-t)) for t in center])
  assert max(abs(times[ii]-center))<1e-10
  assert bool(z['net_present'])==present and bool(z['center_strap_present'])==present
  assert float(z['ball_mass'])==.0576 and np.array_equal(z['net_node_masses'],net['mass'])
  steel=net['kind']==1
  assert np.array_equal(z['net_edge_axial_rigidity'][steel],net['ea'][steel])
  assert np.array_equal(z['net_edge_axial_rigidity'][~steel],net['ea'][~steel]*ratio)
  assert np.array_equal(z['net_bend_ei'],net['bend_ei']*ratio)
  ball=z['ball_positions'];velocity=z['ball_velocities'];q=z['ball_quaternions']
  assert np.array_equal(ball[0],net['_ball_state'][0]) and np.array_equal(q[0],net['_ball_state'][3])
  assert velocity[0,1]==speed and np.array_equal(velocity[0,[0,2]],net['_ball_state'][1][[0,2]])
  assert np.isfinite(ball).all() and np.isfinite(velocity).all()
  assert np.max(abs(np.linalg.norm(q,axis=1)-1))<1e-8
  assert ball[:,2].min()>=config['ball_radius_m']-1e-6
  if present:
   assert np.array_equal(z['net_positions'][0],net['positions'].astype(np.float32))
   assert c['executed_library_sha256']==LIB_SHA
  else:
   assert z['net_positions'].shape[1]==0 and z['strap_surface_positions'].shape[1]==0
   assert ball[:,1].max()>0
  keys=('times','net_positions','net_edges','net_edge_kind','band_positions','strap_positions','strap_velocities','strap_surface_positions','ball_positions','ball_quaternions','net_present','strap_surface_faces')
  renderer={k:z[k] for k in keys}
  positions=ball[ii].copy()
 with np.load(out/'ground_truth_24fps.npz') as z:
  assert np.array_equal(z['times'],center) and np.array_equal(z['ball_positions'],positions)
 if present:
  subprocess.run([sys.executable,'-B',str(HERE/'audit_contacts.py'),'--cache',str(raw),'--out',str(out/'contact_audit'),'--shutter-only'],check=True)
  contacts=json.loads((out/'contact_audit/render_contact_audit.json').read_text());assert contacts['passed']
 else:contacts={'passed':True,'scope':'Whole net assembly absent; these contacts do not exist','contact_pair_count':0}
 from audit_court import audit
 court=audit(raw,out,present)
 # Strip inactive fields and unnecessary velocities for the GPU renderer;
 # every remaining motion sample still comes from the physical cache.
 np.savez_compressed(out/'render_cache.npz',**renderer)
 qualification={'passed':True,'case_id':a.case,'edit_dsl':dsl,'parent_source_cache_sha256':c['source_ancestor_cache_sha256'],
  'physical_cache_sha256':c['physical_cache_sha256'],'render_cache_sha256':sha(out/'render_cache.npz'),
  'ground_truth_sha256':c['ground_truth_sha256'],'native_frame_times_s':center.tolist(),
  'native_ball_positions_m':positions.tolist(),'physical_stop_s':4.,'fps':24,'frames':96,'width':1280,'height':720,
  'all_protected_inputs_passed':all(c['initial_inputs_audit'].values()),'native_gates_unchanged':True,
  'contact_audit_passed':contacts['passed'],'ball_rebounded_to_near_side':c['ball_rebounded_to_near_side'],
  'court_contact_audit_passed':court['passed'],'court_contact_audit':court,
  'source_replay_maximum_visible_difference_m':c['source_replay_maximum_visible_difference_m'],
  'ball_final_position_m':c['ball_final_position_m'],'normal_speed':True,
  'material_calibrated':False,'accepted_benchmark_gt':False}
 write(out/'qualification.json',qualification);print(json.dumps({'case_id':a.case,'passed':True,'render_cache_sha256':qualification['render_cache_sha256']}),flush=True)


if __name__=='__main__':main()
