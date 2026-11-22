"""Render fixed reconstruction with the same loader used by the coffee scene."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,json,subprocess,os,time
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import blender
p=argparse.ArgumentParser();p.add_argument('case',type=Path);p.add_argument('--source',type=Path,required=True)
p.add_argument('--scene-name',default='scene.blend')
a=p.parse_args();case=a.case.resolve();source=a.source.resolve();HERE=Path(__file__).resolve().parent
q=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
gpus=[dict(zip(('index','memory','util'),map(int,l.split(',')))) for l in q.strip().splitlines()]
free=[g['index'] for g in gpus if g['memory']<200 and g['util']==0][:3]
workers=free if free else [None]*6
missing=[f for f in range(1,97) if not (case/f'frames/frame_{f:04d}.png').exists()]
chunks=[missing[i::len(workers)] for i in range(len(workers))];start=time.monotonic()
def run(i,gpu,frames):
 if not frames:return
 if gpu is not None:
  check=subprocess.check_output(['nvidia-smi',f'--id={gpu}','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
  memory,util=map(int,check.strip().split(','))
  assert memory<200 and util==0,f'GPU {gpu} became occupied'
 env=os.environ.copy();env.update(OMP_NUM_THREADS='16')
 if gpu is not None:env['CUDA_VISIBLE_DEVICES']=str(gpu)
 command=[str(blender()),'-b',str(source/a.scene_name),'-t','16','--python-exit-code','1','--python',str(HERE/'render_tea_direct.py'),'--',str(case),'--frames',*map(str,frames),'--output','frames','--report-tag',f'direct_chunk{i}','--device','GPU' if gpu is not None else 'CPU']
 print('DIRECT_CHUNK_STARTED',i,gpu,len(frames),flush=True)
 with open(case/f'render_direct_chunk{i}.log','w') as log:
  result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT)
 if result.returncode:
  print((case/f'render_direct_chunk{i}.log').read_text()[-3000:],flush=True)
  raise RuntimeError(f'Chunk {i} render failed')
 (case/f'render_direct_chunk{i}_execution.json').write_text(json.dumps({'command':command,'gpu':gpu,'snapshot':gpus},indent=2)+'\n')
 print('DIRECT_CHUNK_DONE',i,flush=True)
with ThreadPoolExecutor(max_workers=len(workers)) as executor:
 for job in as_completed([executor.submit(run,i,gpu,chunk) for i,(gpu,chunk) in enumerate(zip(workers,chunks))]):job.result()
frames={}
for i,chunk in enumerate(chunks):
 if chunk:frames.update(json.loads((case/f'render_direct_chunk{i}.json').read_text())['frames'])
assert all((case/f'frames/frame_{f:04d}.png').exists() for f in range(1,97))
report={'frames':frames,'render_seconds':time.monotonic()-start,'samples':128,'width':1280,'height':720,'fps':24,
        'mode':'Direct per-frame mesh with per-vertex velocity attributes','source_and_cache_preserved':True,
        'parallel_chunks':len(workers),'backend':'OptiX' if free else 'CPU','gpu_snapshot':gpus}
(case/'render_all.json').write_text(json.dumps(report,indent=2)+'\n')
subprocess.run(['ffmpeg','-y','-v','error','-framerate','24','-start_number','1','-i',str(case/'frames/frame_%04d.png'),'-frames:v','96','-c:v','libx264','-threads','8','-preset','slow','-crf','14','-pix_fmt','yuv420p','-movflags','+faststart',str(case/'video.mp4')],check=True)
print('DIRECT_VIDEO_READY',time.monotonic()-start,flush=True)
