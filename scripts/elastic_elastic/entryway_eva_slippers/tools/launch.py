"""Delegate a simulate or render run to the GPU launcher (tools/native/pool_worker.py)."""
import argparse,datetime,subprocess,sys
from pathlib import Path
from tools.retained import CASE,CASES,SUITE,out_path

# Sample count of the published renders (render_config.json of every published case).
PUBLISHED_SAMPLES=128

def run(tool):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",choices=CASES,default="source")
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--pool-audit",type=Path,help="Optional GPU inventory JSON (time_utc, workers); rejected when older than 5 minutes")
    parser.add_argument("--gpu-uuid",default="auto")
    parser.add_argument("--threads-count",type=int,choices=range(1,17),default=6)
    if tool=="blender":
        parser.add_argument("--cache",type=Path)
        parser.add_argument("--blender-bin",type=Path)
    args=parser.parse_args()
    if sys.platform!="linux":
        parser.error("The native solver and renderer run on Linux")
    out=out_path(args.out)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("repro_%Y%m%dT%H%M%S%fZ")
    revised=args.case in {"light_falling","slippery_floor"}
    command=[sys.executable,"-B",CASE/"tools/native/pool_worker.py","--name",stamp,"--tool",tool,
             "--gpu",args.gpu_uuid,"--threads",args.threads_count]
    if args.pool_audit:
        command.extend(["--pool-audit",args.pool_audit.resolve()])
    if tool=="blender":
        if args.blender_bin:command.extend(["--blender-bin",args.blender_bin.resolve(strict=True)])
        cache=args.cache or SUITE/"cases"/args.case/"simulation.npz"
        # The published look: realism.py runs render_hero.py (with the production-edit vocabulary for the
        # two revised cases) and adds the hallway light and wear.
        command.extend(["--","realism.py",
                        "--case",args.case,"--cache",cache.resolve(strict=True),"--out",out,"--samples",PUBLISHED_SAMPLES])
    else:
        command.extend(["--","simulate_revision.py" if revised else "simulate.py",
                        "--case",args.case,"--out",out,"--mesh","production","--isotropic"])
    subprocess.run(list(map(str,command)),check=True)
