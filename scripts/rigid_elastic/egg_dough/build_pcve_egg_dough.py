"""Build the source and its four physical edits (simulate, render, verify)."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=='__main__':
 import sys
 from pathlib import Path
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
 from pcve_scene_entry import prepare_entry
 prepare_entry(__file__,'build_pcve')
# PCVE_UNIFIED_ENTRY_END
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pcve_scene_pipeline import Step,parser,execute
from dough_config import HERE,CASES,preset_names,config,asset_directory

def main():
 p=parser(__doc__,python_env='.venv-taichi-mpm');p.add_argument('--preset',choices=preset_names());p.add_argument('--cases',nargs='+',choices=CASES);p.add_argument('--asset-dir',type=Path);p.add_argument('--steps-per-frame',type=int);p.add_argument('--initial-state-mode',choices=['own_equilibrium','source_shared']);p.add_argument('--source-initial-state',type=Path)
 a=p.parse_args();a.cases=a.cases or list(CASES);resolved=config('source',a.preset);a.preset=resolved['preset'];a.asset_dir=a.asset_dir or asset_directory(resolved);root=a.out_root.resolve();steps=[]
 # Edits start from the source's settled state at t=0; 4096 solver steps per video frame.
 mode=a.initial_state_mode or 'source_shared'
 if a.steps_per_frame is None:a.steps_per_frame=4096
 if a.source_initial_state and mode!='source_shared':p.error('--source-initial-state requires --initial-state-mode source_shared')
 shared=a.source_initial_state or root/'cases/source/simulation/initial_state.npz'
 if mode=='source_shared':
  if 'source' in a.cases:a.cases=['source']+[x for x in a.cases if x!='source']
  elif not shared.is_file():p.error('A source case or existing --source-initial-state is required')
 for case in a.cases:
  sim=root/'cases'/case/'simulation';render=root/'cases'/case/'render'
  preset_args=['--preset',a.preset] if a.preset else []
  if mode=='source_shared' and case!='source':preset_args+=['--initial-state-from',shared]
  steps.append(Step(case+'_simulate','simulate',[a.python,HERE/'simulate_egg_dough.py','--out-dir',sim,'--case',case,'--asset-dir',a.asset_dir,'--gpu',a.gpu or 'auto','--steps-per-frame',str(a.steps_per_frame)]+preset_args,outputs=(sim/'simulation_cache.npz',)))
  steps.append(Step(case+'_render','render',[a.python,HERE/'render_egg_dough.py','--simulation-dir',sim,'--out-dir',render,'--blender',a.blender,'--gpu',a.gpu or 'auto','--threads',str(a.threads),'--save-blend'],outputs=(render/'video.mp4',)))
 steps.append(Step('measure_and_compare','verify',[a.python,HERE/'physics/validate_egg_dough.py','--suite-root',root,'--cases',*a.cases],outputs=(root/'acceptance_results.json',root/'parameter_differences.json')))
 execute('egg_dough',a,steps,inputs=(a.asset_dir/'geometry.npz',))
if __name__=='__main__':main()
