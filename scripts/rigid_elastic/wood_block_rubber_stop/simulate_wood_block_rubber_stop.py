"""Run the native libuipc FEM/ABD solve of one case on one bound GPU (4.000 s window by default)."""

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

from edit_vocab import SELECTED_CASES
from scene_paths import REPO,launch,output_path,python_runtime,require_linux

if __name__=='__main__':
    require_linux()
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--case',choices=SELECTED_CASES,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--cpu-threads',type=int,default=8)
    parser.add_argument('--python-runtime',type=Path)
    args,native=parser.parse_known_args()
    python=python_runtime(args.python_runtime)
    if python is None or not python.is_file():
        parser.error('Select a Python 3.10 runtime with numpy, scipy and trimesh (--python-runtime)')
    deps=REPO/'tools/ipc_probe_deps'
    env_args=['PYTHONPATH='+os.pathsep.join(map(str,[SCRIPTS,CASE,deps])),
              'LD_LIBRARY_PATH='+str(deps/'uipc/_native')]
    launch(['/usr/bin/env',*env_args,python,'-B',CASE/'tools/run_selected.py','simulate',
            '--case',args.case,'--out',output_path(args.out),*native],args.gpu_uuid,args.cpu_threads)
