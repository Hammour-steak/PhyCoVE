"""Choose currently empty GPU immediately before this scoped Blender render.

If every GPU is occupied, use CPU; never evict or stop another user's work.
Blender arguments are passed literally, without a shell. The target script must
support --device at the end of its own arguments.
"""
import json
import os
import subprocess
import sys
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import blender

query=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
gpus=[dict(zip(('index','memory_mib','utilization_percent'),map(int,line.split(',')))) for line in query.strip().splitlines()]
available=[g for g in gpus if g['memory_mib']<200 and g['utilization_percent']==0]
env=os.environ.copy()
device='GPU' if available else 'CPU'
if available: env['CUDA_VISIBLE_DEVICES']=str(available[0]['index'])
print('TEA_RENDER_RESOURCE_SELECTION='+json.dumps({'snapshot':gpus,'selected_gpu':available[0] if available else None,'render_device':device}),flush=True)
blender=str(blender())
raise SystemExit(subprocess.run([blender,*sys.argv[1:],'--device',device],env=env).returncode)
