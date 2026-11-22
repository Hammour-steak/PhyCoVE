"""CPU-only verification of a native cache against the finite table-leg and floor volumes.

The initial speed and pose are compared with the case's own solver configuration.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case-dir',required=True,type=Path);a=p.parse_args();d=a.case_dir
 cfg=json.loads((d/'simulation_config.json').read_text());params=cfg['physics']
 z=np.load(d/'simulation.npz');x=z['elastic_positions'];t=z['block_transforms'];v=z['block_velocities']
 center=np.array(params['backstop_center_m']);half=np.array(params['backstop_dimensions_m'])/2
 # Only points INSIDE all six planes penetrate the finite leg. Rear-face
 # overhang outside the leg's 120 mm width is not a collision penetration.
 if x.size:
  depths=np.min(np.minimum(x-(center-half),(center+half)-x),axis=-1)
  max_leg_penetration=float(max(0,depths.max()));floor_depth=float(max(0,-x[:,:,2].min()))
 else:max_leg_penetration=0.;floor_depth=0.
 blocks=[(z['block_vertices'],t)]
 if len(z['added_block_transforms']):blocks.append((z['added_block_vertices'],z['added_block_transforms']))
 block_floor_depth=0.
 for vertices,transforms in blocks:
  world=vertices@np.transpose(transforms[:,:3,:3],(0,2,1))+transforms[:,None,:3,3]
  block_floor_depth=max(block_floor_depth,float(max(0,-world[:,:,2].min())))
 initial_velocity=v[0,:3,3].tolist()
 checks={'initial_velocity_matches_case':bool(np.allclose(initial_velocity,params['block_initial_velocity_m_s'],atol=1e-10)),
  'baseline_initial_center_unchanged':bool(np.allclose(t[0,:3,3],params['block_initial_center_m'],atol=1e-10)),
  'no_sponge_vertices_in_leg_volume':max_leg_penetration<=1e-5,
  'sponge_floor_no_penetration':floor_depth<=1e-5,
  'block_floor_no_penetration':block_floor_depth<=1e-5,
  'sponge_is_unrestrained':not np.any(z['elastic_fixed_mask'])}
 report={'status':'passed' if all(checks.values()) else 'failed','case_id':cfg['case_id'],'checks':checks,
  'initial_velocity_m_s':initial_velocity,
  'maximum_sponge_vertex_penetration_into_leg_m':max_leg_penetration,
  'maximum_sponge_floor_penetration_m':floor_depth,'maximum_block_floor_penetration_m':block_floor_depth,
  'cache_sha256':hashlib.sha256((d/'simulation.npz').read_bytes()).hexdigest(),
  'scope':'Native sampled vertex versus finite collision-volume checks; independent tetrahedral/rigid audit and IPC continuous contact are recorded separately.'}
 (d/'contact_volume_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 if report['status']!='passed':raise SystemExit(2)

if __name__=='__main__':main()
