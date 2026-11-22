"""Public pipeline entry point for faucet_sink."""
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import asset
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
    p.add_argument('--cases',nargs='+',choices=('source','edit_low_flow','edit_high_flow','edit_high_viscosity','edit_stop_flow_at_2s'),default=['source'])
    p.add_argument('--template',type=Path,default=asset('scenes/faucet_sink/scene_template.blend'))
    a=p.parse_args(cli_args())
    a.out_root=a.out_root.expanduser().resolve()
    steps=[]
    for case in dict.fromkeys(a.cases):
        work=a.out_root/'cases'/case/'work'
        output=a.out_root/'cases'/case/'output'
        steps += [Step(case+'_prepare','prepare',blender(a,HERE/'appearance/prepare_faucet_sink.py','--case-id',case,
                        '--template',a.template,'--work-dir',work),(work/'scene.blend',)),
                  Step(case+'_simulate','simulate',blender(a,HERE/'simulate_faucet_sink.py','--case-id',case,
                        '--work-dir',work,'--scene',work/'scene.blend'),(work/'scene_baked.blend',)),
                  Step(case+'_render','render',blender(a,HERE/'render_faucet_sink.py','--case-id',case,
                        '--scene',work/'scene_baked.blend','--output-dir',output),(output/'video.mp4',)),
                  Step(case+'_verify','verify',[sys.executable,ROOT/'scripts/pcve_verify_video.py',output/'video.mp4',
                        '--out',a.out_root/(case+'_video_verification.json')])]
    execute(HERE.name,a,steps,[a.template])

if __name__=='__main__':main()
