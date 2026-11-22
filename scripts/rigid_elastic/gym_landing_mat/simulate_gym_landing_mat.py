"""Run the accepted native libuipc physics on a verified GPU worker."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END
from pathlib import Path
import sys

CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))

import argparse
from scene_inputs import ASSETS, CASES, SCENE
from scene_paths import OUTPUT, launch, output_path, worker_only

if __name__ == "__main__":
    worker_only()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id","--case",choices=CASES,default="source")
    parser.add_argument("--out",type=Path)
    parser.add_argument("--gpu-uuid",default="auto")
    parser.add_argument("--cpu-threads",type=int,default=6)
    args=parser.parse_args()
    out=output_path(args.out or OUTPUT/args.case_id/"simulation")
    if out.exists():raise FileExistsError(out)
    state=ASSETS/f"native/{args.case_id}/initial_state.npz"
    if not state.is_file():raise FileNotFoundError(state)
    launch([sys.executable,"-B",CASE/"physics/simulate.py","--scene",SCENE,"--case",args.case_id,
            "--out",out,"--duration","4","--dt",str(1/1200),
            "--velocity-tol",str(1e-4),"--preload","0","--initial-state",state],
           args.gpu_uuid,args.cpu_threads)
