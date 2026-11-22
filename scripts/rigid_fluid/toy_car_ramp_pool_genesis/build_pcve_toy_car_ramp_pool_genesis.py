"""Public pipeline entry point for toy_car_ramp_pool_genesis."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'build_pcve')
# PCVE_UNIFIED_ENTRY_END
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from pcve_scene_pipeline import ROOT, Step, blender, cli_args, execute, parser


def main():
    p=parser(__doc__)
    p.add_argument('--input-blend',type=Path,required=True,help='The existing sunny ramp/pool appearance scene')
    a=p.parse_args(cli_args())
    a.out_root=a.out_root.expanduser().resolve()
    settle=a.out_root/'settle'
    run=a.out_root/'run'
    steps=[Step('settle','simulate',[a.python,HERE/'simulate_toy_car_ramp_pool_genesis.py','settle','--out',settle],(settle/'water_state.npz',)),
           Step('simulate','simulate',[a.python,HERE/'simulate_toy_car_ramp_pool_genesis.py','run','--out',run,
                '--water-state',settle/'water_state.npz'],(run/'simulation_report.json',)),
           Step('surface','surface',[a.python,HERE/'surface_toy_car_ramp_pool_genesis.py','--run',run],(run/'meshes',)),
           Step('render','render',blender(a,HERE/'render_toy_car_ramp_pool_genesis.py','--input-blend',a.input_blend,
                '--run',run,'--out-dir',a.out_root/'render','--resolution','1280','720','--samples','32'),(a.out_root/'render/video.mp4',)),
           Step('verify','verify',[a.python,ROOT/'scripts/pcve_verify_video.py',a.out_root/'render/video.mp4',
                '--out',a.out_root/'video_verification.json'])]
    execute(HERE.name,a,steps,[a.input_blend])

if __name__=='__main__':main()
