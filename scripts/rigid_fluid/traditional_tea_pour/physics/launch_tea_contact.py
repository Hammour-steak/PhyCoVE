"""Use a verified empty GPU for an isolated 96-frame contact repair solve."""
import argparse
import json
import os
import subprocess
from pathlib import Path
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO

p=argparse.ArgumentParser()
p.add_argument('case',type=Path)
p.add_argument('--skin',type=float,required=True)
a=p.parse_args()
q=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
gpus=[dict(zip(('index','memory_mib','utilization_percent'),map(int,r.split(',')))) for r in q.strip().splitlines()]
free=[g for g in gpus if g['memory_mib']<200 and g['utilization_percent']==0]
if not free: raise RuntimeError('No empty GPU; preserve all existing jobs and retry later')
env=os.environ.copy()
env.update(CUDA_VISIBLE_DEVICES=str(free[0]['index']),OMP_NUM_THREADS='8',RAYON_NUM_THREADS='8')
print('CONTACT_REPAIR_RESOURCES='+json.dumps({'gpus':gpus,'selected':free[0]}),flush=True)
script=Path(__file__).resolve().parent/'simulate_tea_contact.py'
python=str(REPO / '.venv-genesis-mpm-sph/bin/python')
command=[python,str(script),str(a.case),'--max-density-error','.005','--max-divergence-error','.05',
         '--domain-half','.24','--surface-friction','1','--gamma','.0002','--coaster',
         '--support-contact-skin',str(a.skin)]
raise SystemExit(subprocess.run(command,env=env).returncode)
