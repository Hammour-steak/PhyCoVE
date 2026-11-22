"""Recompute the native cloth/foam states of one case (libuipc) through the GPU launcher tools/native/pool_job.py."""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END

import argparse
from scene_driver import CASES,SUITE,TIMED_CASES,WORK,output,require_linux,worker
if __name__=="__main__":
    require_linux()
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case",choices=CASES+TIMED_CASES,default="source")
    p.add_argument("--source-cache",type=Path,help="timed cases: source deformation.npz to continue from (default: the accepted delivery's source)")
    p.add_argument("--out",type=Path,help="fresh folder beneath renders/cotton_tshirt_sofa/")
    p.add_argument("--gpu-uuid",default="auto")
    p.add_argument("--cpu-threads",type=int,default=6)
    p.add_argument("--pool-audit",type=Path,help="optional GPU inventory JSON (time_utc); rejected when older than 5 minutes")
    a=p.parse_args()
    out=output(a.out or WORK/"simulate"/a.case)
    resume=["--source-cache",(a.source_cache or SUITE/"cases/source/deformation.npz").resolve()] if a.case in TIMED_CASES else []
    worker("python","simulate.py",["--case",a.case,"--name",a.case,"--out",out,"--duration","4","--dt",str(1/240),*resume],
           a.gpu_uuid,a.cpu_threads,a.pool_audit)
