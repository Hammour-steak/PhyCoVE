"""Solve one case with the accepted native solver inside the restored worker kit."""

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
import json
import os
import subprocess
from scene_paths import output_path,prepare_worker,worker_only

if __name__=='__main__':
    worker_only()
    parser=argparse.ArgumentParser(description=__doc__)
    cases=json.loads((CASE/'entrypoints.json').read_bytes())['entrypoints']['simulate']['cases']
    parser.add_argument('case',nargs='?',default='source',choices=cases)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--tag',default='quilt')
    parser.add_argument('--rate',type=int,default=600)
    parser.add_argument('--material',default='cotton')
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--cpu-threads',type=int,default=3)
    args,native=parser.parse_known_args()
    out=output_path(args.out)
    if out.exists():
        parser.error('Choose a fresh simulation output')
    kit=prepare_worker()
    env=dict(os.environ,BOOK_PILLOW_ROOT=str(kit),PCVE_EXPLICIT_GPU=args.gpu_uuid,PCVE_CPU_THREADS=str(args.cpu_threads))
    subprocess.run([sys.executable,'-B',str(CASE/'tools/dispatch.py'),'simulate',args.case,
                    '--tag',args.tag,'--rate',str(args.rate),'--material',args.material,'--out',str(out),*native],
                   env=env,check=True)
