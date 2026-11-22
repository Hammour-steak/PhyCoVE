"""Render one case's native state with the current gym look (appearance/realism.py) on a claimed GPU."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END
from pathlib import Path
import sys

CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))

import argparse
import json
from scene_inputs import ASSETS, CASES, SCENE, accepted_case, reference_main
from scene_paths import OUTPUT, blender_runtime, launch, output_path, worker_only

LOOKS = {"realism": "appearance/realism.py",          # current appearance
         "accepted": "appearance/render_replay.py"}   # frozen renderer of the accepted delivery

if __name__ == "__main__":
    worker_only()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id","--case",choices=CASES,default="source")
    parser.add_argument("--out",type=Path)
    parser.add_argument("--simulation",type=Path)
    parser.add_argument("--scene",type=Path)
    parser.add_argument("--reference-main",type=Path)
    parser.add_argument("--look",choices=tuple(LOOKS),default="realism")
    parser.add_argument("--samples",type=int,default=192)
    parser.add_argument("--still-frame",type=int)
    parser.add_argument("--frame-start",type=int)
    parser.add_argument("--frame-end",type=int)
    parser.add_argument("--blender-bin",type=Path)
    parser.add_argument("--gpu-uuid",default="auto")
    parser.add_argument("--cpu-threads",type=int,default=6)
    args=parser.parse_args()
    out=output_path(args.out or OUTPUT/args.case_id/"render")
    if out.exists() and not (args.still_frame or args.frame_start or args.frame_end):raise FileExistsError(out)
    source=accepted_case(args.case_id)/"simulation"
    inputs=args.simulation or source
    config=json.loads((inputs/"simulation_config.json").read_bytes())
    if (config["scene_id"],config["case"],config["simulation"]["duration"],config["simulation"]["fps"])!=(SCENE,args.case_id,4.,24):
        parser.error("Unexpected native scene, case or clock")
    packed=args.scene or ASSETS/f"packed/{args.case_id}.blend"
    if not packed.is_file():raise FileNotFoundError(packed)
    extra=["--reference-main",args.reference_main or reference_main(args.case_id)]
    for flag,value in (("--still-frame",args.still_frame),("--frame-start",args.frame_start),("--frame-end",args.frame_end)):
        if value is not None:extra.extend([flag,value])
    launch([blender_runtime(args.blender_bin),"--background","--factory-startup","--disable-autoexec","-t",args.cpu_threads,
            "--python-exit-code","1","--python",CASE/LOOKS[args.look],"--","--simulation",inputs,
            "--scene",packed,"--out",out,"--samples",args.samples,*extra],args.gpu_uuid,args.cpu_threads)
