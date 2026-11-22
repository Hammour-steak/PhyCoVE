"""Render one native case with the current look (appearance/render.py) in Blender 4.3 Cycles."""

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
import subprocess
from scene_paths import blender_runtime,launch,output_path,require_linux

if __name__=='__main__':
    require_linux()
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--simulation',type=Path,required=True,help='native solver output with cache.npz and simulation_config.json')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--gpu-uuid',default='auto',help='claimed GPU (UUID or index); not needed with --device CPU')
    parser.add_argument('--render-threads',type=int,default=8)
    parser.add_argument('--blender-bin',type=Path)
    parser.add_argument('--device',choices=('OPTIX','CUDA','CPU'),default='OPTIX')
    parser.add_argument('--width',type=int,default=1280)
    parser.add_argument('--samples',type=int,default=256)
    args,native=parser.parse_known_args()
    out=output_path(args.out)
    cache=args.simulation.resolve()
    if not (cache/'cache.npz').is_file() or not (cache/'simulation_config.json').is_file():
        parser.error('The matched native simulation directory is required')
    command=[blender_runtime(args.blender_bin),'-b','-t',args.render_threads,
             '--factory-startup','--disable-autoexec','--python-exit-code','1',
             '--python',CASE/'appearance/render.py','--','--simulation',cache,
             '--out',out,'--width',args.width,'--samples',args.samples,'--device',args.device,*native]
    if args.device=='CPU':
        env=dict(os.environ,OMP_NUM_THREADS=str(args.render_threads),CUDA_VISIBLE_DEVICES='')
        subprocess.run([str(c) for c in command],env=env,check=True)
    else:
        launch(command,args.gpu_uuid,args.render_threads)
