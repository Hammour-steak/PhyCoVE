"""Replay a qualified native cache in the current bedroom look (appearance/realism_look.py)."""

from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE=Path(__file__).resolve().parent
SCRIPTS=CASE.parents[1]
sys.path.insert(0,str(SCRIPTS))
if __name__=='__main__':
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__,'render')
# PCVE_UNIFIED_ENTRY_END

import argparse
import json
import os
import subprocess
from scene_paths import output_path,prepare_worker,worker_only

if __name__=='__main__':
    worker_only('render')
    parser=argparse.ArgumentParser(description=__doc__)
    cases=json.loads((CASE/'entrypoints.json').read_bytes())['entrypoints']['render']['cases']
    parser.add_argument('case',nargs='?',default='source',choices=cases)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--input',type=Path,required=True,help='Native case directory (simulation.npz, motion_audit.json)')
    parser.add_argument('--tag',default='quilt')
    parser.add_argument('--samples',type=int,help='Cycles samples (default: appearance/realism_look.py SAMPLES)')
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--cpu-threads',type=int,default=3)
    parser.add_argument('--blender-bin',type=Path)
    args,native=parser.parse_known_args()
    out=output_path(args.output)
    if out.exists():
        parser.error('Choose a fresh render output')
    if not all((args.input/n).is_file() for n in ('simulation.npz','motion_audit.json')):
        parser.error('A matching native cache and motion audit are required')
    kit=prepare_worker('render')
    env=dict(os.environ,BOOK_PILLOW_ROOT=str(kit),PCVE_EXPLICIT_GPU=args.gpu_uuid,PCVE_CPU_THREADS=str(args.cpu_threads))
    if args.blender_bin:
        env['PCVE_BLENDER_BIN']=str(args.blender_bin)
    if args.samples:
        native+=['--samples',str(args.samples)]
    subprocess.run([sys.executable,'-B',str(CASE/'tools/dispatch.py'),'render',args.case,
                    '--tag',args.tag,'--input',str(args.input.resolve()),
                    '--output',str(out),*native],env=env,check=True)
