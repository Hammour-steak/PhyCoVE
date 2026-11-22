"""Run and qualify the native CPU solve of one case (Linux, CPU only)."""

from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE=Path(__file__).resolve().parent
SCRIPTS=CASE.parents[1]
sys.path.insert(0,str(SCRIPTS))
if __name__=='__main__':
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__,'simulate')
# PCVE_UNIFIED_ENTRY_END

import argparse
import os
import subprocess
from scene_paths import output_path,worker_only

if __name__=='__main__':
    worker_only()
    sys.path.insert(0,str(CASE/'physics'))
    from common import CASES
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=tuple(CASES),required=True)
    parser.add_argument('--out',type=Path,required=True,help='Fresh directory under renders/tennis_net_hit/')
    parser.add_argument('--threads',type=int,default=2)
    args=parser.parse_args()
    out=output_path(args.out)
    if out.exists():
        parser.error('Choose a fresh output directory')
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS=str(args.threads),
             OPENBLAS_NUM_THREADS='1')
    for name in ('simulate.py','qualify.py'):
        cmd=[sys.executable,'-B',str(CASE/'physics'/name),'--case',args.case,'--out',str(out)]
        if name=='simulate.py':
            cmd+=['--threads',str(args.threads)]
        subprocess.run(cmd,check=True,env=env)
