"""Exact recorded complete-state restore, independent of other outputs."""
import ctypes,json
import numpy as np

def restore(lib,net,strip,endpoint,canonical_context=None):
 """Configure at the frozen installation, then restore all dynamic slots."""
 import coupled_abi as abi
 context=abi.configure(lib,net,strip,True) if canonical_context is None else dict(canonical_context)
 context['positions']=context['positions'].copy();context['velocities']=context['velocities'].copy()
 with np.load(endpoint) as z:
  net['positions'][:]=z['net_positions_f64'];net['velocities'][:]=z['net_velocities_f64']
  strip['positions'][:]=z['strip_positions'];strip['velocities'][:]=z['strip_velocities']
  net['_ball_state']=tuple(z[k].copy() for k in ('ball_position','ball_velocity','ball_angular_velocity','ball_quaternion'))
 ns=context['strip_node_count'];first=context['net_pool_first'];virtual=context['virtual_first'];ids=context['net_pool_indices']
 context['positions'][:ns]=strip['positions'];context['velocities'][:ns]=strip['velocities']
 context['positions'][first:virtual]=net['positions'][ids];context['velocities'][first:virtual]=net['velocities'][ids]
 binding=net['_band_binding'];bi=context['native_band_vertex_ids'];parents=binding['band_binding_indices'][bi];weights=binding['band_binding_weights'][bi]
 context['positions'][virtual:]=(net['positions'][parents]*weights[...,None]).sum(axis=1)+binding['band_binding_offsets'][bi]
 context['velocities'][virtual:]=(net['velocities'][parents]*weights[...,None]).sum(axis=1)
 keys=['positions','velocities','mass','fixed','edges','rest','ea','unilateral','mechanical_bend_triplets','mechanical_bend_rest_lengths','mechanical_bend_ei']
 arrays=[context[k] for k in keys]+[strip['faces']]
 arrays+=[context[k] for k in ['contact_pairs','contact_radii','forces','net_pool_indices','virtual_binding_indices','virtual_binding_weights','virtual_binding_offsets','node_floor_clearance_m','full_net_floor_clearance_m','excluded_net_edge_indices','native_band_vertex_ids']]
 arrays=[np.ascontiguousarray(x) for x in arrays];ptr=lambda x:x.ctypes.data_as(ctypes.c_void_p)
 status=lib.configure_finite_strap(len(context['positions']),ns,len(context['edges']),len(context['mechanical_bend_triplets']),len(strip['faces']),len(context['contact_pairs']),
  first,virtual,len(context['virtual_binding_indices']),len(ids),len(context['excluded_net_edge_indices']),len(net['positions']),*map(ptr,arrays),
  context['fixture_geometry_sha256'].encode(),json.dumps(context['fixture_active_component_ids']).encode(),1)
 assert status==0
 lib._finite_state=context;lib._finite_present=True
 return context
