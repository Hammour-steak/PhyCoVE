"""Exact cached prefix followed by an empty-fluid state in a prescribed rigid scene.

This segmented existence model is valid here because all rigid bodies are fixed
or prescribed and carry no liquid reaction state. It is not an FSI restart.
A separate solver-kernel deactivation run verifies the all-inactive operation.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import time
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('source',type=Path)
p.add_argument('case',type=Path)
p.add_argument('deactivation_evidence',type=Path)
a=p.parse_args(); source=a.source.resolve();case=a.case.resolve();evidence=a.deactivation_evidence.resolve()
assert not (case/'particles').exists() and not (case/'surfaces').exists()
started=time.monotonic()
for sub in ('particles','surfaces'):
    (case/sub).mkdir()
    for f in range(1,97):
        src=(source if f<49 else evidence)/sub/f'frame_{f:04d}.npz'
        shutil.copy2(src,case/sub/src.name)
experiment=json.loads((evidence/'experiment.json').read_text())
experiment['cache_branch']={'method':'Exact accepted particle/surface prefix for frames 1..48, then all tea absent and emission disabled from frame49 (2s). Static/prescribed rigid state has no fluid-dependent continuation.',
    'source':str(source),'source_last_frame':48,'delete_frame':49,'delete_display_time_sec':2.,
    'solver_kernel_deactivation_evidence':str(evidence/'simulation_result.json'),
    'resimulation_before_deletion_reused':False,'reason':'CUDA reductions are not bitwise deterministic; use the accepted cached prefix to isolate the time-local intervention.'}
(case/'experiment.json').write_text(json.dumps(experiment,indent=2)+'\n')
baseline_rows=json.loads((source/'particle_audit.json').read_text())['frames']
empty_rows=json.loads((evidence/'particle_audit.json').read_text())['frames']
rows={}
for f in range(1,97):
    row=copy.deepcopy((baseline_rows if f<49 else empty_rows)[str(f)])
    row.update(time_s=(f-1)/24,solver_snapshot_time_s=f/24,
               deleted_this_frame=79488 if f==49 else 0,
               cumulative_deleted_particles=0 if f<49 else 79488)
    rows[str(f)]=row
(case/'particle_audit.json').write_text(json.dumps({'frames':rows,'experiment':str(case/'experiment.json')},indent=2)+'\n')
surface_before=json.loads((source/'surface_audit.json').read_text())
surface_after=json.loads((evidence/'surface_audit.json').read_text())
surface_before['case']=str(case)
surface_before['frames']={str(f):copy.deepcopy((surface_before if f<49 else surface_after)['frames'][str(f)]) for f in range(1,97)}
(case/'surface_audit.json').write_text(json.dumps(surface_before,indent=2)+'\n')
result=json.loads((evidence/'simulation_result.json').read_text())
result.update(simulation_recomputed=False,method='Validated segmented cached-state existence intervention',
              solver_deactivation_evidence=str(evidence/'simulation_result.json'),
              branch_seconds=time.monotonic()-started)
(case/'simulation_result.json').write_text(json.dumps(result,indent=2)+'\n')
print('EXACT_PREFIX_BRANCH_DONE',flush=True)
