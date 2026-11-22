"""Render native real-time samples in the published look (appearance/realism_overlay.py over
appearance/render_scene.py) on a leased GPU, then encode."""
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
import os
import subprocess
import time
from pcve_assets import asset, blender
from tools.retained_delivery import DELIVERY, WORK

if __name__ == "__main__":
    if os.name=="nt":
        raise SystemExit("Blender rendering runs on a Linux GPU host.")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",default="source",choices=("source","soft_bands","heavy_ball","heavy_domino","delete_domino"))
    parser.add_argument("--simulation",type=Path)
    parser.add_argument("--out",type=Path,default=WORK/"render")
    parser.add_argument("--samples",type=int,default=128)
    parser.add_argument("--slow",action="store_true")
    parser.add_argument("--blender-bin",type=Path)
    parser.add_argument("--gpu-uuid",default="auto")
    parser.add_argument("--threads",type=int,default=8)
    args=parser.parse_args()
    simulation=args.simulation or DELIVERY/"cases"/args.case
    out=args.out.resolve()
    if WORK.resolve() not in out.parents or out.exists():
        parser.error(f"Choose a fresh output directory under {WORK}")
    path=args.blender_bin
    if path is None:
        pinned=CASE.parents[2]/"tools/blender-4.3.2-linux-x64/blender"
        path=pinned if pinned.is_file() else blender()
    render=[path,"-b","-t",args.threads,"--factory-startup","--disable-autoexec","--python-exit-code","1",
            "--python",CASE/"appearance/realism_overlay.py","--","--assets",asset("scenes/slingshot_domino"),
            "--simulation",simulation,"--out",out,"--samples",args.samples]
    if args.slow:render.append("--slow")
    env=dict(os.environ,OMP_NUM_THREADS=str(args.threads))
    subprocess.run([sys.executable,"-B",str(CASE/"tools/worker_run.py"),"--gpu",args.gpu_uuid,
                    "--name",f"slingshot_{time.time_ns()}","--wait","--",*map(str,render)],env=env,check=True)
    subprocess.run([sys.executable,"-B",str(CASE/"tools/encode_on_worker.py"),"--render",str(out),
                    "--simulation",str(simulation)],check=True)
