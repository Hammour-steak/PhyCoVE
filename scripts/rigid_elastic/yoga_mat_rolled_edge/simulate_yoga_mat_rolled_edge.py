"""Solve one case on a leased GPU (libuipc shell + ABD ball; delete_mat is the CPU rigid-floor branch) and audit it."""

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
import subprocess

from edit_vocab import BASELINE,CASE_DSL,TIMED_DSL,override_for,timed_override
from pcve_assets import asset
from scene_paths import OUTPUT,launch,output_path,require_linux,suite_dir

if __name__=='__main__':
    require_linux()
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--out',type=Path,help='new case directory (default: renders/yoga_mat_rolled_edge/physics/<case>)')
    parser.add_argument('--case',choices=tuple(CASE_DSL)+tuple(TIMED_DSL),default='source')
    parser.add_argument('--source-cache',type=Path,help='timed edits: the 24 fps source simulation.npz whose edit-frame state is continued '
                        '(default: the published source cache, cases/source/native_metadata/simulation.npz of the suite)')
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--cpu-threads',type=int,default=2)
    args,native=parser.parse_known_args()
    out=output_path(args.out or OUTPUT/'physics'/args.case)
    if out.exists():
        parser.error('Choose a fresh simulation output')
    physics=dict(BASELINE)
    timed_frame=None
    if args.case in TIMED_DSL:
        change,timed_frame=timed_override(args.case)
        physics.update(change)
    else:
        physics.update(override_for(args.case))
    # Samples t=(i-1)/24, i=1..96 (a 4 s clip), with the accepted solver settings.
    defaults={'--ball-mass':physics['ball_mass_kg'],'--ball-speed':physics['ball_initial_speed_m_s'],
              '--young':physics['mat_young_modulus_pa'],'--ball-radius':physics['ball_radius_m'],
              '--dt':1/960,'--duration':4.0,'--fps':24,'--frames':96,'--grid-x':97,'--grid-y':25,'--velocity-tol':.001,'--newton-max':700}
    for flag,value in defaults.items():
        if not any(item==flag or item.startswith(flag+'=') for item in native):
            native += [flag,str(value)]
    seed=asset('scenes/yoga_mat_rolled_edge/settled_state.npz')
    if args.case=='delete_mat':
        native += ['--delete-mat','--rigid-initial-cache',str(seed)]
    elif timed_frame is not None:
        source_cache=args.source_cache or suite_dir()/'cases/source/native_metadata/simulation.npz'
        native += ['--source-cache',str(source_cache),'--edit-frame',str(timed_frame)]
    else:
        native += ['--settled-cache',str(seed)]
    runtime=SCRIPTS.parent/'.runtime/gym_landing_mat'
    native_runtime=SCRIPTS.parent/'tools/ipc_probe_deps'
    paths=[runtime/'python_deps',native_runtime,SCRIPTS]
    plugin=asset('scenes/yoga_mat_rolled_edge/native')
    env_args=['PYTHONPATH='+os.pathsep.join(map(str,paths)),
              'LD_LIBRARY_PATH='+os.pathsep.join(map(str,[runtime/'lib',native_runtime/'uipc/_native'])),
              'PCVE_VISCOSITY_PLUGIN='+str(plugin)]
    command=['/usr/bin/env',*env_args,sys.executable,'-B',str(CASE/'physics/simulate_source.py'),
             '--out',str(out),*native]
    if args.case=='delete_mat':
        subprocess.run(command,env=dict(os.environ,CUDA_VISIBLE_DEVICES=''),check=True)
    else:
        launch(command,args.gpu_uuid,args.cpu_threads)
    subprocess.run(['/usr/bin/env',*env_args,sys.executable,'-B',str(CASE/'physics/audit_source.py'),
                    str(out)],check=True)
