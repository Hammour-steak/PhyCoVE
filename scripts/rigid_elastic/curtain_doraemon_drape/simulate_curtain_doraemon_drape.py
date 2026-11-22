"""Run the native libuipc 0.0.29 solve of one case on a claimed GPU (or an idle one picked by tools/worker_run.py)."""

from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE=Path(__file__).resolve().parent
SCRIPTS=CASE.parents[1]
sys.path.insert(0,str(SCRIPTS))
if __name__=='__main__':
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__,'simulate')
# PCVE_UNIFIED_ENTRY_END

import argparse
import os
from scene_paths import REPO,RUNTIME,launch,output_path,require_linux

if __name__=='__main__':
    require_linux()
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--cpu-threads',type=int,default=8)
    parser.add_argument('--python-runtime',type=Path,
                        help='Python 3.10 with numpy/scipy/trimesh (default: .runtime/<scene>/python, else .venv-rigid-elastic)')
    args,native=parser.parse_known_args()
    target=output_path(args.out)
    isolated=RUNTIME/'python/bin/python3.10'
    executable=args.python_runtime or (isolated if isolated.is_file() else REPO/'.venv-rigid-elastic/bin/python')
    # pyuipc 0.0.29 is installed case-isolated in .runtime/<scene>/uipc_029 (wheel unpacked, see README).
    paths=[SCRIPTS,CASE/'physics',RUNTIME/'uipc_029',RUNTIME/'deps']
    env_args=['PYTHONPATH='+os.pathsep.join(map(str,paths))]
    if executable.resolve()==isolated.resolve() and isolated.is_file():
        env_args += ['PYTHONHOME='+str(RUNTIME/'python'),
                     'LD_LIBRARY_PATH='+os.pathsep.join([str(RUNTIME/'python/lib'),os.environ.get('LD_LIBRARY_PATH','')])]
    if not Path(executable).is_file() or not (RUNTIME/'uipc_029/uipc').is_dir():
        parser.error('Install the case-isolated pyuipc 0.0.29 runtime under '+str(RUNTIME/'uipc_029'))
    launch(['/usr/bin/env',*env_args,executable,'-B',CASE/'physics/simulate.py',
            '--out',target,*native],args.gpu_uuid,args.cpu_threads)
