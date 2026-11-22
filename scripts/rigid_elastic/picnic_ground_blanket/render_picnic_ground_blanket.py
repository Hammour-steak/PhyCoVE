"""Render one case: replay its native state into the packed scene with the current look."""
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
import os
import subprocess
from scene_inputs import ASSETS, CASES, SCENE, TIMED_CASES, native
from scene_paths import OUTPUT, blender_runtime, output_path

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id","--case",choices=CASES+TIMED_CASES,default="source")
    parser.add_argument("--out",type=Path)
    parser.add_argument("--simulation",type=Path,help="Native state directory (default: the accepted state in the asset store)")
    parser.add_argument("--scene",type=Path,help="Packed scene (default: assets/scenes/picnic_ground_blanket/packed_scene.blend)")
    parser.add_argument("--samples",type=int,default=512)
    parser.add_argument("--blender-bin",type=Path)
    parser.add_argument("--gpu-uuid",default="auto",help="GPU index or UUID (sets CUDA_VISIBLE_DEVICES); 'auto' inherits it")
    parser.add_argument("--cpu-threads",type=int,default=6)
    parser.add_argument("--device",choices=("GPU","CPU"),default="GPU")
    parser.add_argument("--cycles-backend",choices=("OPTIX","CUDA"),default="OPTIX")
    parser.add_argument("--frame-start",type=int,default=1)
    parser.add_argument("--frame-end",type=int,default=96)
    parser.add_argument("--still-frame",type=int,nargs="+",help="Render only these frames (look development)")
    args=parser.parse_args()
    out=output_path(args.out or OUTPUT/args.case_id/"render")
    if out.exists() and any(out.iterdir()) and not args.still_frame and (args.frame_start,args.frame_end)==(1,96):raise FileExistsError(out)
    if args.case_id in TIMED_CASES and args.simulation is None:
        parser.error("A timed edit renders its solved state: pass --simulation (e.g. the suite case's native_metadata)")
    inputs=args.simulation or native(args.case_id)
    config=json.loads((inputs/"simulation_config.json").read_bytes())
    if (config["scene_id"],config["case"],config["simulation"]["duration"],config["simulation"]["fps"])!=(SCENE,args.case_id,4.,24):
        parser.error("Unexpected native scene, case or clock")
    packed=args.scene or ASSETS/"packed_scene.blend"
    if not packed.is_file():raise FileNotFoundError(packed)
    env=dict(os.environ,OMP_NUM_THREADS=str(args.cpu_threads))
    if args.gpu_uuid!="auto":env["CUDA_VISIBLE_DEVICES"]=args.gpu_uuid
    frames=["--still-frame",*map(str,args.still_frame)] if args.still_frame else ["--frame-start",str(args.frame_start),"--frame-end",str(args.frame_end)]
    command=[blender_runtime(args.blender_bin),"--background","--factory-startup","--disable-autoexec","-t",args.cpu_threads,
             "--python-exit-code","1","--python",CASE/"appearance/render_replay.py","--","--simulation",inputs,
             "--scene",packed,"--out",out,"--samples",args.samples,"--device",args.device,"--cycles-backend",args.cycles_backend,*frames]
    subprocess.run(list(map(str,command)),env=env,check=True)
