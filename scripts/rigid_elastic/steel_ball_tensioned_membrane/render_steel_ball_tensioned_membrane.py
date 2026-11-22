"""Render one case in the published look (appearance/realism_overlay.py on the accepted saved scene of --case,
default source; output under renders/steel_ball_tensioned_membrane/.work/), or with --cache the Blender replay of a
native cache (appearance/render_native.py), or with --input the appearance upgrade of an existing saved four-second
scene (appearance/upgrade_visuals.py)."""

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
from pcve_assets import asset
from scene_paths import blender_runtime,launch,output_path,worker_only

if __name__=='__main__':
    worker_only()
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    source=parser.add_mutually_exclusive_group()
    source.add_argument('--cache',type=Path)
    source.add_argument('--input',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--blender-bin',type=Path)
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--render-threads',type=int,default=6)
    args,native=parser.parse_known_args()
    out=output_path(args.out)
    if args.input:
        entry=CASE/'appearance/upgrade_visuals.py'
        hdri=asset('scenes/steel_ball_tensioned_membrane/university_workshop_4k.hdr')
        payload=['--input',args.input.resolve(),'--hdri',hdri]
        if not (args.input/'scene.blend').is_file():
            parser.error('The packed four-second scene given by --input is required')
    elif args.cache:
        entry=CASE/'appearance/render_native.py'
        if not args.cache.is_file() or not args.cache.with_name('simulation_config.json').is_file():
            parser.error('A matched native cache and configuration are required')
        payload=['--cache',args.cache.resolve()]
    else:
        # The published look: the overlay renders the accepted saved scene of the case (--case, default source).
        entry=CASE/'appearance/realism_overlay.py'
        payload=[] if any(x=='--case' or x.startswith('--case=') for x in native) else ['--case','source']
    if (out/'video.mp4').is_file() or (out/'render_report.json').is_file():
        parser.error('Choose a fresh render output')
    cmd=[blender_runtime(args.blender_bin),'-b','-t',args.render_threads,'--factory-startup',
         '--disable-autoexec','--python-exit-code','1','--python',entry,'--','--out',out,*payload,*native]
    launch(cmd,args.gpu_uuid,args.render_threads)
