"""Solve one case with the native libuipc physics through the GPU launcher (tools/worker_run.py)."""
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
from scene_inputs import CASES, SCENE, TIMED_CASES, native
from scene_paths import OUTPUT, launch, output_path, require_linux

if __name__ == "__main__":
    require_linux()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id","--case",choices=CASES+TIMED_CASES,default="source")
    parser.add_argument("--out",type=Path)
    parser.add_argument("--source-cache",type=Path,help="timed edits: accepted source cache.npz (default: the asset store's source state)")
    parser.add_argument("--gpu-uuid",default="auto")
    parser.add_argument("--cpu-threads",type=int,default=6)
    args=parser.parse_args()
    out=output_path(args.out or OUTPUT/args.case_id/"simulation")
    if out.exists():raise FileExistsError(out)
    if args.case_id in TIMED_CASES:
        # Timed edit: restore the source state of the edit frame and continue (physics/simulate.py --source-cache).
        start=["--source-cache",args.source_cache or native("source")/"cache.npz"]
    else:
        start=["--initial-state",native(args.case_id)/"initial_state.npz"]
    if not Path(start[1]).is_file():raise FileNotFoundError(start[1])
    # dt 1/2400 s, velocity tolerance 1e-5 and no preload: the settings of the accepted solves.
    launch([sys.executable,"-B",CASE/"physics/simulate.py","--scene",SCENE,"--case",args.case_id,
            "--out",out,"--duration","4","--dt",str(1/2400),
            "--velocity-tol",str(1e-5),"--preload","0",*start],
           args.gpu_uuid,args.cpu_threads)
