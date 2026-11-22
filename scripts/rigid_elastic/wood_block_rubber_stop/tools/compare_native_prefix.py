"""Compare the shared time window of two native caches of the same case (no solver, no Blender).

Used by the determinism stage (two independent solves of the same case) and to compare a longer solve
with the first part of a shorter one.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np

TIMED=('block_transforms','block_velocities','added_block_transforms','added_block_velocities','elastic_positions','elastic_velocities','times')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def compare(new_dir,old_dir):
 a=np.load(new_dir/'simulation.npz');b=np.load(old_dir/'simulation.npz')
 na=json.loads((new_dir/'simulation_config.json').read_text());nb=json.loads((old_dir/'simulation_config.json').read_text())
 n=min(len(a['times']),len(b['times']));rows={}
 for key in sorted(set(a.files)&set(b.files)):
  x=a[key];y=b[key]
  if key in TIMED:x=x[:n];y=y[:n]
  if x.shape!=y.shape:rows[key]={'shape_new':list(x.shape),'shape_old':list(y.shape),'comparable':False};continue
  diff=float(np.abs(x.astype(float)-y.astype(float)).max()) if x.size else 0.
  rows[key]={'shape':list(x.shape),'max_abs_diff':diff,'bitwise_equal':bool(np.array_equal(x,y))}
 return {'case_id':na['case_id'],'shared_frames':int(n),'shared_window_s':float(a['times'][n-1]),
  'physics_identical':na['physics']==nb['physics'],'simulation_settings_identical':na['simulation']==nb['simulation'],
  'solver_config_identical':na['solver_config']==nb['solver_config'],
  'new_cache':str(new_dir/'simulation.npz'),'new_cache_sha256':sha(new_dir/'simulation.npz'),
  'old_cache':str(old_dir/'simulation.npz'),'old_cache_sha256':sha(old_dir/'simulation.npz'),'arrays':rows}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--new',type=Path,required=True,help='folder with simulation.npz + simulation_config.json')
 ap.add_argument('--old',type=Path,required=True);ap.add_argument('--out',type=Path);a=ap.parse_args()
 report=compare(a.new.resolve(),a.old.resolve());text=json.dumps(report,indent=2)
 if a.out:a.out.write_text(text+'\n',encoding='utf-8')
 print(text)

if __name__=='__main__':main()
