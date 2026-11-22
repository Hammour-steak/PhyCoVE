"""Public CPU solver CLI with the audited per-case numerical resolution."""
import argparse
from pathlib import Path
from config import EDITS
from physics import simulate
WORK=Path(__file__).resolve().parents[4]/'renders/slingshot_domino/physics'
a=argparse.ArgumentParser();a.add_argument('--case',default='source',choices=['source',*EDITS]);a.add_argument('--all',action='store_true');a.add_argument('--segments',type=int,default=40);a.add_argument('--steps-per-frame',type=int);a.add_argument('--out',type=Path);a.add_argument('--stop-time',type=float);args=a.parse_args()
for case in ['source',*EDITS]if args.all else[args.case]:
    target=(args.out/case if args.all else args.out)if args.out else WORK/case
    if target.exists():raise FileExistsError(target)
    simulate(case,target,args.segments,args.steps_per_frame or(19200 if case=='heavy_ball'else 4800),stop_time=args.stop_time)
