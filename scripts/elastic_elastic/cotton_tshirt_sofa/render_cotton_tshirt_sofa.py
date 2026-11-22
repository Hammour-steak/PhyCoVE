"""Replay the native states and their exposure samples of one case in the published look (tools/native/realism.py,
the overlay on tools/native/render.py) through the GPU launcher."""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

import argparse
from scene_driver import CASES,PUBLISHED,SUITE,TIMED_CASES,WORK,output,require_linux,worker
if __name__=="__main__":
    require_linux()
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case",choices=CASES+TIMED_CASES,default="source")
    p.add_argument("--cache",type=Path,help="native cache (default: the accepted delivery's deformation.npz; for a timed edit the "
                   "published suite's inputs/native_timed/<case>/simulation.npz)")
    p.add_argument("--out",type=Path,help="fresh folder beneath renders/cotton_tshirt_sofa/")
    p.add_argument("--gpu-uuid",default="auto")
    p.add_argument("--cpu-threads",type=int,default=6)
    p.add_argument("--pool-audit",type=Path,help="optional GPU inventory JSON (time_utc); rejected when older than 5 minutes")
    p.add_argument("--blender-bin",type=Path)
    a=p.parse_args()
    out=output(a.out or WORK/"render"/a.case)
    default=PUBLISHED/"inputs/native_timed"/a.case/"simulation.npz" if a.case in TIMED_CASES else SUITE/"cases"/a.case/"deformation.npz"
    cache=(a.cache or default).resolve()
    if not cache.is_file():raise FileNotFoundError(cache)
    worker("blender","realism.py",["--case",a.case,"--cache",cache,"--out",out,"--save-scene"],
           a.gpu_uuid,a.cpu_threads,a.pool_audit,a.blender_bin)
