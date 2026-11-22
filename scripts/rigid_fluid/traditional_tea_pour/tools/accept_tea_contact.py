"""Gate contact repair using actual liquid mass, cap geometry and cup audits."""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

p=argparse.ArgumentParser()
p.add_argument('case',type=Path)
p.add_argument('--baseline-caps',type=Path,required=True)
a=p.parse_args(); case=a.case.resolve()
caps_path=case/('table_cap_geometry_all.json' if (case/'table_cap_geometry_all.json').exists() else 'table_cap_geometry.json')
caps=json.loads(caps_path.read_text())
old=json.loads(a.baseline_caps.read_text())
numeric=json.loads((case/'numeric_acceptance_genesis.json').read_text())
cup=json.loads((case/'actual_cup_audit.json').read_text())
settings=json.loads((case/'experiment.json').read_text())['after']
simulation=json.loads((case/'simulation_result.json').read_text())
rows={}
for f,components in caps['frames'].items():
    if not components: continue
    frac=np.array([r['mesh_above_table_volume_fraction'] for r in components])
    volume=np.array([r['mesh_volume_ul'] for r in components])
    rows[f]={'components':len(components),'median_above_table_fraction':float(np.median(frac)),
             'min_above_table_fraction':float(frac.min()),
             'weighted_above_table_fraction':float(np.dot(frac,volume)/volume.sum()),
             'median_visible_convex_hull_area_px2':float(np.median([r['unoccluded_above_table_convex_hull_area_px2'] for r in components])),
             'median_bottom_z_mm':float(np.median([r['bounds_z_mm'][0] for r in components]))}
coverage={}
ids_after_landing=set()
for f in range(21,97):
    with np.load(case/f'particles/frame_{f:04d}.npz') as z:
        pos=z['pos'].astype(float); ids=z['particle_ids']
    with np.load(case/f'surfaces/frame_{f:04d}.npz') as z: v=z['vertices'].astype(float)
    landed=(np.linalg.norm(pos[:,:2],axis=1)>.06)&(pos[:,2]<.004)
    missing_ids=ids_after_landing-set(int(i) for i in ids)
    assert not missing_ids
    ids_after_landing.update(int(i) for i in ids[landed])
    distance=cKDTree(v).query(pos[landed])[0] if landed.any() else np.array([])
    coverage[str(f)]={'landed_particles':int(landed.sum()),'missing_mesh_over2spacing':int((distance>2*settings['particle_size_m']).sum()),
                     'previously_landed_ids_deleted':len(missing_ids)}
final=rows['96']
checks={
    'all96_mass_and_fill_gates_pass':numeric['passed_numeric_gate'],
    'no_solver_iteration_cap_hits':simulation['density_solver']['iteration_cap_hits']==simulation['divergence_solver']['iteration_cap_hits']==0,
    'no_sampled_ceramic_particle_penetration':cup['max_particles_inside_ceramic_over0_1mm']==0,
    'no_below_rim_inside_outside_mesh_paths':all(r['below_rim_inside_to_exterior_connected_components']==0 for r in cup['surface_frames'].values()),
    'final_median_visible_fraction_ge99percent':final['median_above_table_fraction']>=.99,
    'final_weighted_visible_fraction_ge98percent':final['weighted_above_table_fraction']>=.98,
    'no_cohort_mesh_coverage_loss':all(r['missing_mesh_over2spacing']==0 for r in coverage.values()),
    'no_landed_particle_deletion':all(r['previously_landed_ids_deleted']==0 for r in coverage.values()),
    'resting_median_clearance_le0p2mm':-.02<=final['median_bottom_z_mm']<=.2,
    'all_saved_tail_frames_checked':all(str(f) in rows for f in range(32,97)),
    'settled_tail_median_visible_fraction_ge99percent':all(r['median_above_table_fraction']>=.99 for f,r in rows.items() if int(f)>=32),
}
old_final=old['frames']['96']
result={'case':str(case),'checks':checks,'passed':all(checks.values()),'cap_frames':rows,'particle_coverage':coverage,
        'before':{'median_visible_fraction':float(np.median([r['mesh_above_table_volume_fraction'] for r in old_final])),
                  'median_visible_area_px2':float(np.median([r['unoccluded_above_table_convex_hull_area_px2'] for r in old_final]))},
        'after':final,'support_contact_skin_m':settings['support_contact_skin_m'],
        'causal_scope':'Independent re-solve, only table/coaster finite-particle contact skin changed. Optical and encoding refinements must be reported separately.',
        'limits':'Mesh-above-plane measures a contact error, not a calibrated contact angle. Individual airborne/merging/occluded droplets need not remain fixed on screen.'}
(case/'contact_acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
print('CONTACT_ACCEPTANCE='+json.dumps({k:v for k,v in result.items() if k not in ('cap_frames','particle_coverage')}),flush=True)
if not result['passed']: raise SystemExit(2)
