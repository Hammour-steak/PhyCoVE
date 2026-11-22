"""Explicit t=0 intervention from a verified source gravity-equilibrium state."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
from pathlib import Path
import json
import numpy as np
from dough_config import config,digest
FIELDS=('vertices','velocities','viscous_inverse','accumulated_viscous_strain')
def load_source_state(path,c,mesh_sha256):
 path=Path(path).resolve();folder=path.parent
 src=json.loads((folder/'actual_config.json').read_text());eq=json.loads((folder/'equilibrium_report.json').read_text());receipt=json.loads((folder/'simulation_receipt.json').read_text())
 assert src['case']=='source' and src['preset']==c['preset']
 assert src['physics']==config('source',src['preset'])['physics']
 assert src['appearance']==c['appearance'] and receipt['mesh_sha256']==mesh_sha256
 assert eq['method']=='fully_relaxed_static_force_balance' and eq['fixed_nodes']==0
 assert eq['maximum_residual_acceleration_m_s2']<.01 and eq['net_force_residual_N']<1e-5
 assert 'diagnostic_unload_after_s' not in src and c['physics']['dough']['present']
 assert src['physics']['ball']['initial_position_m']==c['physics']['ball']['initial_position_m']
 assert src['physics']['ball']['initial_velocity_m_s']==c['physics']['ball']['initial_velocity_m_s']
 assert src['physics']['ball']['initial_angular_velocity_rad_s']==c['physics']['ball']['initial_angular_velocity_rad_s']
 with np.load(path,allow_pickle=False) as d:state={k:d[k].copy() for k in FIELDS}
 assert all(np.isfinite(v).all() for v in state.values())
 assert np.linalg.norm(state['velocities'],axis=1).max()<1e-12
 assert np.abs(np.linalg.det(state['viscous_inverse'])-1).max()<1e-8
 identity={'mode':'source_state_t0_edit','edit_time_s':0.,'source_case':'source','source_initial_state_sha256':digest(path),'source_config_sha256':digest(folder/'actual_config.json'),'source_equilibrium_report_sha256':digest(folder/'equilibrium_report.json'),'source_mesh_sha256':mesh_sha256,'copied_state_fields':list(FIELDS),'allow_precontact_gravity_response':True}
 metadata={'method':'copied_source_equilibrium_then_material_edit_at_t0','is_equilibrium_for_edited_material':False,'source_initial_state_path':str(path),'source_equilibrium':eq,'initial_history':'Copy source positions, zero velocities, fully relaxed Maxwell metric and accumulated viscous strain exactly, then change only the declared material property at t=0; no edited-material prewarmup.','initialization_identity':identity}
 return state,identity,metadata

def apply_source_state(solid,state):
 assert state['vertices'].shape==(solid.n,3) and state['viscous_inverse'].shape==(solid.ne,3,3)
 solid.x.from_numpy(state['vertices']);solid.v.from_numpy(state['velocities']);solid.fvi.from_numpy(state['viscous_inverse']);solid.ev.from_numpy(state['accumulated_viscous_strain'])

def audit_shared_state(folder,c,mesh_sha256):
 folder=Path(folder);eq=json.loads((folder/'equilibrium_report.json').read_text());path=Path(eq['source_initial_state_path'])
 if not path.is_file():
  candidates=[folder.parent.parent/'source/simulation/initial_state.npz',folder.parent/'source/initial_state.npz']
  path=next((p for p in candidates if p.is_file()),path)
 source,identity,meta=load_source_state(path,c,mesh_sha256)
 with np.load(folder/'initial_state.npz',allow_pickle=False) as own:exact=all(np.array_equal(own[k],source[k]) for k in FIELDS)
 return {'shared_source_state_exact':exact,'source_initialization_identity_verified':identity==c.get('initialization'),'source_gravity_equilibrium_before_t0_edit':meta['source_equilibrium']['maximum_residual_acceleration_m_s2']<.01,'edited_initial_state_declared_nonequilibrium':eq.get('is_equilibrium_for_edited_material') is False}
