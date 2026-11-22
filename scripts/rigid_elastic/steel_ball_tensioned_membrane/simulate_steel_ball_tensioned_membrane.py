"""Run the native four-second shell/rigid solve through tools/worker_run.py (GPU preflight and lease)."""

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
from scene_paths import launch,output_path,worker_only

if __name__=='__main__':
    worker_only()
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--cpu-threads',type=int,default=6)
    args,native=parser.parse_known_args()
    out=output_path(args.out)
    if out.is_dir() and any(out.iterdir()):
        parser.error('Choose a fresh simulation output')
    launch([sys.executable,'-B',CASE/'physics/simulate_native.py','--out',out,*native],
           args.gpu_uuid,args.cpu_threads)
