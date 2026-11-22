"""Replay an audited native cache in Blender on a leased GPU and encode the 24 fps video."""

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
import shutil
import subprocess

from scene_paths import blender_runtime,launch,output_path,require_linux

if __name__=='__main__':
    require_linux()
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--render-threads',type=int,default=4)
    parser.add_argument('--blender-bin',type=Path)
    parser.add_argument('--ffmpeg',type=Path)
    parser.add_argument('--samples',type=int,default=96)
    parser.add_argument('--width',type=int,default=1280,help='1280 renders the 1280x720 benchmark frame')
    parser.add_argument('--look',choices=('realism','review'),default='realism',
                        help='realism: appearance/realism.py, the published look; review: the base replay scene of appearance/render_source_review.py')
    parser.add_argument('--single-frame-index',type=int)
    args,native=parser.parse_known_args()
    out=output_path(args.out)
    if out.exists():
        parser.error('Choose a fresh replay output')
    audit=json.loads(args.cache.with_name('source_audit.json').read_bytes())
    if audit['status']!='passed':
        parser.error('The native collision audit must pass')
    encoder=args.ffmpeg or shutil.which('ffmpeg')
    if args.single_frame_index is None and not (encoder and Path(encoder).is_file()):
        parser.error('Select an existing FFmpeg executable')
    native += ['--all-contact-frames'] if '--all-contact-frames' not in native else []
    if args.single_frame_index is not None:
        native += ['--single-frame-index',str(args.single_frame_index)]
    renderer=CASE/('appearance/realism.py' if args.look=='realism' else 'appearance/render_source_review.py')
    command=[blender_runtime(args.blender_bin),'-b','-t',args.render_threads,'--factory-startup',
             '--disable-autoexec','--python-exit-code','1','--python',renderer,
             '--','--cache',args.cache.resolve(),'--out',out,'--width',args.width,'--samples',args.samples,*native]
    launch(command,args.gpu_uuid,args.render_threads)
    if args.single_frame_index is None:
        import numpy as np
        with np.load(args.cache,allow_pickle=False) as cache:
            fps=round(1/float(cache['times'][1]-cache['times'][0]))
        subprocess.run([str(encoder),'-hide_banner','-loglevel','error','-framerate',str(fps),
                        '-i',str(out/'contact_frame_%04d.png'),'-c:v','libx264','-crf','17',
                        '-pix_fmt','yuv420p','-movflags','+faststart',str(out/'review.mp4')],check=True)
