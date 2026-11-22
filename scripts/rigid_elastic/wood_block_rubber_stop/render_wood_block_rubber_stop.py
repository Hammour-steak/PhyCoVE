"""Replay a native cache in the dining-room look (Blender/Cycles) on one bound GPU, or on the CPU with --device cpu."""

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
import os
import shutil
import subprocess

from edit_vocab import SELECTED_CASES
from scene_paths import CACHES,blender_runtime,launch,output_path,require_linux

if __name__=='__main__':
    require_linux()
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--case',choices=SELECTED_CASES,required=True)
    parser.add_argument('--cache',type=Path,help='simulation.npz with simulation_config.json beside it; default: the registered native cache of --case')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--render-threads',type=int,default=8)
    parser.add_argument('--blender-bin',type=Path)
    args,native=parser.parse_known_args()
    cache=(args.cache or CACHES/args.case/'simulation.npz').expanduser().resolve()
    if not cache.is_file() or not cache.with_name('simulation_config.json').is_file():
        parser.error('A matching native cache and configuration are required')
    encoder=os.environ.get('PCVE_FFMPEG') or shutil.which('ffmpeg')
    if not encoder or not Path(encoder).is_file():
        parser.error('Set PCVE_FFMPEG to an existing encoder')
    out=output_path(args.out)
    cmd=['/usr/bin/env','PCVE_FFMPEG='+str(encoder),
         blender_runtime(args.blender_bin),'-b','-t',args.render_threads,'--factory-startup',
         '--disable-autoexec','--python-exit-code','1','--python',CASE/'tools/run_selected.py','--','render',
         '--case',args.case,'--cache',cache,'--out',out,*native]
    cpu='--device' in native and native[native.index('--device')+1:native.index('--device')+2]==['cpu']
    if cpu:  # CPU render: no GPU binding
        subprocess.run([str(c) for c in cmd],env=dict(os.environ,OMP_NUM_THREADS=str(args.render_threads)),check=True)
    else:
        launch(cmd,args.gpu_uuid,args.render_threads)
