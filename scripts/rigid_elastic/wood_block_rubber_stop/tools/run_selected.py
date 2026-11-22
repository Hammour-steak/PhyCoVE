"""Guarded worker execution into a fresh directory; stored artifacts are never rewritten."""
import argparse,json,os,platform,runpy,shutil,socket,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
CASES=('source','fast_block','heavy_block','soft_010','remove_bumper','add_mid_block')
# Cases outside the published catalog, run by the driver in the staged suite's inputs/edit_<case>/.
STAGED_CASES=('remove_wood_block',)

def run_selected(kind):
 if platform.system()!='Linux':raise SystemExit('GPU simulation and Blender replay must run on a Linux CUDA host, never local Windows/WSL.')
 worker=os.environ.get('PCVE_WORKER_HOST') or socket.gethostname().split('.')[0]
 addresses=subprocess.check_output(['hostname','-I'],text=True).split()
 gpu=os.environ.get('CUDA_VISIBLE_DEVICES')
 argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
 cpu_render=kind=='render' and '--device' in argv and argv[argv.index('--device')+1:argv.index('--device')+2]==['cpu']
 if not cpu_render and (not gpu or gpu.count(',')):raise SystemExit('Bind one checked-idle GPU with CUDA_VISIBLE_DEVICES before launching.')
 ap=argparse.ArgumentParser(add_help=False);ap.add_argument('--case',choices=CASES+STAGED_CASES,required=True);ap.add_argument('--out',type=Path,required=True)
 args,_=ap.parse_known_args(argv);out=args.out.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh output directory; accepted results are immutable.')
 if kind=='render':
  encoder=os.environ.get('PCVE_FFMPEG') or shutil.which('ffmpeg')
  if not encoder or not Path(encoder).is_file():raise SystemExit('Set PCVE_FFMPEG to an existing encoder before rendering; the encoder is checked before Blender constructs the scene.')
  runtime=REPO/'.runtime/wood_block_rubber_stop/encoder';runtime.mkdir(parents=True,exist_ok=True)
  owned_encoder=runtime/'ffmpeg'
  if not owned_encoder.exists():shutil.copy2(encoder,owned_encoder)
  os.environ['PATH']=str(runtime)+':'+os.environ['PATH']
 # The two stiffest cases keep their accepted finer step and Newton budget.
 if kind=='simulate' and args.case in {'soft_010','fast_block'}:
  if not any(x=='--dt' or x.startswith('--dt=') for x in argv):argv+=['--dt',str(1/2400)]
  if not any(x=='--newton-max-iterations' or x.startswith('--newton-max-iterations=') for x in argv):argv+=['--newton-max-iterations','600']
 folder=HERE.parent/('appearance' if kind=='render' else 'physics')
 script=folder/f'{kind}.py'
 sys.path.insert(0,str(folder));sys.argv=[str(script),*argv]
 runpy.run_path(str(script),run_name='__main__')
 report_path=out/('simulation_config.json' if kind=='simulate' else 'render_report.json')
 report=json.loads(report_path.read_text(encoding='utf-8'))
 report.update(execution_host=worker,execution_hostname=socket.gethostname(),execution_ip=addresses[0] if addresses else None,cuda_visible_devices=gpu)
 report['gpu_inventory']=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,index','--format=csv,noheader'],text=True).strip() if gpu else None
 report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
 argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
 role,*options=argv
 if role not in {'simulate','render'}:raise ValueError(role)
 sys.argv=[sys.argv[0],*options]
 run_selected(role)
