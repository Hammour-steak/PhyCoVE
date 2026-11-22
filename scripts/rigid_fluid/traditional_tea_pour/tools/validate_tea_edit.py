"""Validate requested speed/mass-flux edits, time-local deletion, and cache lineage."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('case',type=Path)
p.add_argument('--baseline',type=Path,required=True)
a=p.parse_args();case=a.case.resolve();base=a.baseline.resolve()
e=json.loads((case/'experiment.json').read_text());settings=e['after']
b=json.loads((base/'experiment.json').read_text());bs=b['after']
rows=json.loads((case/'particle_audit.json').read_text())['frames']
surface=json.loads((case/'surface_audit.json').read_text())['frames']
result=json.loads((case/'simulation_result.json').read_text())
scale=settings['speed_scale'];delete=settings['deletion_frame'];perframe=int(2208*scale)
stop=settings.get('stop_flow_frame')
emission_end=min(84,delete-1 if delete is not None else 84,stop-1 if stop is not None else 84)
checks={
    'source_speed_ratio':np.isclose(settings['source_speed_m_s']/bs['source_speed_m_s'],scale,rtol=0,atol=1e-12),
    'source_mass_flux_ratio':np.isclose(settings['constant_mass_flux_kg_s']/bs['constant_mass_flux_kg_s'],scale,rtol=0,atol=1e-12),
    'particle_spacing_fixed':settings['particle_size_m']==bs['particle_size_m'],
    'particle_mass_fixed':settings['particle_mass_kg']==bs['particle_mass_kg'],
    'aperture_fixed':settings['source_diameter_m']==bs['source_diameter_m'],
    'time_steps_fixed':settings['step_dt_s']==bs['step_dt_s'] and settings['substeps']==bs['substeps'],
    'material_fixed':settings['water_mu_m2_s']==bs['water_mu_m2_s'] and settings['gamma']==bs['gamma'],
    'gravity_density_geometry_inputs_fixed':e['before']==b['before'],
    'solver_completed':result['completed'],
    'no_iteration_cap_hits':result['density_solver']['iteration_cap_hits']==0 and result['divergence_solver']['iteration_cap_hits']==0,
    'no_recycling':result['no_recycling'],
    'all96_particle_and_surface_frames':set(rows)==set(surface)==set(map(str,range(1,97))),
}
framechecks={};near_boundary=0;bounds=np.array(settings['domain_bounds_m'])
for f in range(1,97):
    row=rows[str(f)]
    activeframes=max(0,min(f,emission_end)-12)
    expected_active=0 if delete is not None and f>=delete else activeframes*perframe
    expected_new=perframe if 13<=f<=emission_end else 0
    expected_deleted=perframe*max(0,min(84,delete-1)-12) if f==delete else 0
    data=np.load(case/f'particles/frame_{f:04d}.npz')
    surf=np.load(case/f'surfaces/frame_{f:04d}.npz')
    pos,vel,ids=data['pos'],data['vel'],data['particle_ids']
    checks_f={
        'expected_active_count':len(pos)==row['active_particles']==expected_active,
        'expected_emission':row['new_particles']==expected_new,
        'expected_deletion':row.get('deleted_this_frame',0)==expected_deleted,
        'finite_state':np.isfinite(pos).all() and np.isfinite(vel).all(),
        'stable_particle_identity':np.array_equal(ids,np.arange(len(ids),dtype=ids.dtype)),
        'finite_surface':np.isfinite(surf['vertices']).all(),
        'no_surface_without_particles':bool(len(surf['vertices']))==bool(len(pos)),
    }
    if stop is not None:
        checks_f['no_deletion']=row['deleted_this_frame']==0 and row['cumulative_deleted_particles']==0
        checks_f['inlet_command_matches_schedule']=np.array_equal(row['inlet_command_velocity_m_s'],[0.,0.,0.] if f>=stop else np.array(e['before']['physics']['velocity_m_s'])*scale)
        checks_f['inlet_flux_matches_schedule']=row['inlet_volume_flux_ml_s']==(settings['constant_rest_volume_flux_ml_s'] if 13<=f<=emission_end else 0.)
        if f>=stop:
            checks_f['existing_liquid_retained']=len(pos)==perframe*max(0,emission_end-12)>0
        if f==stop:
            previous=np.load(case/f'particles/frame_{f-1:04d}.npz')
            checks_f['existing_liquid_keeps_moving']=bool(np.linalg.norm(vel,axis=1).max()>.01 and np.max(np.linalg.norm(pos-previous['pos'],axis=1))>1e-6)
    if len(pos):
        side_distance=np.minimum(pos[:,:2]-bounds[0,:2],bounds[1,:2]-pos[:,:2])
        near_boundary+=int((side_distance.min(1)<2*settings['particle_size_m']).sum())
    if e.get('cache_branch') and f<49:
        checks_f['exact_source_particle_prefix']=hashlib.sha256((case/f'particles/frame_{f:04d}.npz').read_bytes()).digest()==hashlib.sha256((base/f'particles/frame_{f:04d}.npz').read_bytes()).digest()
        checks_f['exact_source_surface_prefix']=hashlib.sha256((case/f'surfaces/frame_{f:04d}.npz').read_bytes()).digest()==hashlib.sha256((base/f'surfaces/frame_{f:04d}.npz').read_bytes()).digest()
    framechecks[str(f)]={k:bool(v) for k,v in checks_f.items()}
checks['all_frame_checks_pass']=all(all(c.values()) for c in framechecks.values())
checks['no_artificial_side_boundary_contact']=near_boundary==0
before={'physics':{'velocity_m_s':e['before']['physics']['velocity_m_s'],
                   'tea_exists_until_sec':None,'rest_volume_flux_ml_s':bs['constant_rest_volume_flux_ml_s'],
                   'inlet_velocity_schedule':[{'from_sec':0.,'velocity_m_s':e['before']['physics']['velocity_m_s']}],
                   'inlet_flux_schedule':[{'from_sec':0.,'rest_volume_flux_ml_s':bs['constant_rest_volume_flux_ml_s']}]},
        'simulation_quality':{k:bs[k] for k in ('particle_size_m','step_dt_s','substeps','source_diameter_m','gamma','domain_bounds_m')},
        'appearance':{'source':'environment_render','camera_lighting_and_objects':'preserved'},
        'render':{'width':1280,'height':720,'fps':24,'frames':96,'samples':128}}
after=copy.deepcopy(before)
after['physics'].update(velocity_m_s=(np.array(before['physics']['velocity_m_s'])*scale).tolist(),
                         tea_exists_until_sec=settings['deletion_sec'],rest_volume_flux_ml_s=settings['constant_rest_volume_flux_ml_s'])
after['simulation_quality']['domain_bounds_m']=settings['domain_bounds_m']
changes=[]
if scale!=1:
    after['physics']['inlet_velocity_schedule'][0]['velocity_m_s']=after['physics']['velocity_m_s']
    after['physics']['inlet_flux_schedule'][0]['rest_volume_flux_ml_s']=settings['constant_rest_volume_flux_ml_s']
    changes+=['physics.velocity_m_s','physics.rest_volume_flux_ml_s','physics.inlet_velocity_schedule','physics.inlet_flux_schedule']
if delete is not None:changes+=['physics.tea_exists_until_sec']
if stop is not None:
    assert scale==1. and delete is None
    after['physics']['inlet_velocity_schedule'].append({'from_sec':settings['stop_flow_sec'],'velocity_m_s':[0.,0.,0.]})
    after['physics']['inlet_flux_schedule'].append({'from_sec':settings['stop_flow_sec'],'rest_volume_flux_ml_s':0.})
    changes+=['physics.inlet_velocity_schedule','physics.inlet_flux_schedule']
if settings['domain_bounds_m']!=bs['domain_bounds_m']:changes+=['simulation_quality.domain_bounds_m']
diff={'before':before,'after':after,'declared_changed_paths':changes,
      'derived_flux_note':'Fixed physical nozzle and particle mass. Native emitted volume and mass per second scale with inlet speed.',
      'numerical_domain_note':'Only the double-speed case expands x/y bounds to avoid truncating physically farther splashes; spacing, step and solver tolerances remain fixed.'}
(case/'edit_diff.json').write_text(json.dumps(diff,indent=2)+'\n')
checks={k:bool(v) for k,v in checks.items()}
report={'case':str(case),'checks':checks,'frames':framechecks,'accepted_numerical_and_semantic':all(checks.values()),
        'near_artificial_boundary_particle_frame_observations':near_boundary,
        'source_coupling_limit':'Fixed/prescribed rigid geometry; no two-way liquid-dependent rigid state.',
        'pre_deletion_method':e.get('cache_branch'),'final_rest_volume_ml':rows['96']['total_rest_volume_ml'],
        'deletion_includes':('Entire liquid jet, liquid in the cup, and all splashed droplets; dry decorative tea leaves remain scenery.' if delete is not None else None),
        'flow_stop_semantics':('Only inlet velocity/flux become zero. Existing liquid remains active and simulated.' if stop is not None else None),
        'flow_stop_sec':settings.get('stop_flow_sec'),'flow_stop_frame':stop}
(case/'edit_validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('frames','pre_deletion_method')},indent=2))
assert all(checks.values()),checks
