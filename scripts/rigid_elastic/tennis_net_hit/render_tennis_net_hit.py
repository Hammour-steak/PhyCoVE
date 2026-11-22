"""Render one case: replay its qualified render cache in the packed court scene with the
current look (appearance/realism.py over appearance/render.py), then encode 1280x720/24 fps/96 frames."""

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
import shutil
import subprocess
from pcve_assets import asset
from pcve_media_contract import require_video
from scene_paths import blender_runtime,launch,output_path

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--case-id','--case',required=True)
    parser.add_argument('--cache',type=Path,required=True,help='render_cache.npz with its qualification.json beside it')
    parser.add_argument('--out',type=Path,required=True,help='Fresh directory under renders/tennis_net_hit/')
    parser.add_argument('--gpu-uuid',help='CUDA_VISIBLE_DEVICES for Blender; inherited when omitted')
    parser.add_argument('--render-threads',type=int,default=6)
    parser.add_argument('--blender-bin',type=Path)
    parser.add_argument('--ffmpeg',type=Path)
    parser.add_argument('--start-frame',type=int,default=1)
    parser.add_argument('--end-frame',type=int,default=96)
    parser.add_argument('--samples',type=int,help='Cycles samples; the look sets the default')
    parser.add_argument('--device',choices=('OPTIX','CUDA','CPU'),default='OPTIX')
    parser.add_argument('--audit-only',action='store_true',help='Replay checks on the CPU without rendering frames')
    parser.add_argument('--pool',action='store_true',help='Launch through tools/worker_run.py (GPU preflight, lease and UUID binding)')
    args=parser.parse_args()
    out=output_path(args.out)
    if out.exists():
        parser.error('Choose a fresh render output')
    if not 1<=args.start_frame<=args.end_frame<=96:
        parser.error('Frames must be within 1-96')
    full=not args.audit_only and args.start_frame==1 and args.end_frame==96
    encoder=args.ffmpeg or shutil.which('ffmpeg')
    if full and not encoder:
        parser.error('Set --ffmpeg to an existing encoder')
    sys.path.insert(0,str(CASE/'physics'))
    from common import CASES,sha
    if args.case_id not in CASES:
        parser.error('Unknown native case ID')
    qual=json.loads(args.cache.with_name('qualification.json').read_bytes())
    if not qual['passed'] or qual['case_id']!=args.case_id or qual['render_cache_sha256']!=sha(args.cache):
        parser.error('The cache is not a qualified match for this branch')
    scene=asset('scenes/tennis_net_hit/inputs/scene.blend')
    if not scene.is_file():
        parser.error('Restore the pinned packed court scene (download_assets.py --scene rigid_elastic/tennis_net_hit)')
    cmd=[blender_runtime(args.blender_bin),'--disable-autoexec','-b',scene,'-t',args.render_threads,
         '--python-exit-code','1','--python',CASE/'appearance/realism.py','--',
         '--case',args.case_id,'--cache',args.cache.resolve(),'--out',out,
         '--frames',f'{args.start_frame}-{args.end_frame}','--device','CPU' if args.audit_only else args.device,
         '--threads',args.render_threads]
    if args.samples:
        cmd+=['--samples',args.samples]
    if args.audit_only:
        cmd.append('--audit-only')
    cmd=[str(x) for x in cmd]
    env=dict(os.environ)
    if args.audit_only:
        env['CUDA_VISIBLE_DEVICES']=''
    elif args.gpu_uuid:
        env['CUDA_VISIBLE_DEVICES']=args.gpu_uuid
    if args.pool:
        launch(cmd,args.gpu_uuid or 'auto',args.render_threads,env)
    else:
        subprocess.run(cmd,env=env,check=True)
    if full:
        frames=sorted((out/'frames').glob('*.png'))
        if [p.name for p in frames]!=[f'{i:04d}.png' for i in range(1,97)]:
            raise RuntimeError('The 96 native render frames are required')
        video=out/'video.mp4'
        subprocess.run([str(encoder),'-v','error','-framerate','24','-start_number','1','-i',str(out/'frames/%04d.png'),
                        '-frames:v','96','-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p',
                        '-movflags','+faststart','-threads','4',str(video)],check=True)
        media=require_video(video)
        print(json.dumps({'video':str(video),'sha256':sha(video),'media':media}))
