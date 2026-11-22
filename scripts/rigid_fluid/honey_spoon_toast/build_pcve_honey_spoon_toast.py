"""Public pipeline entry point for honey_spoon_toast.

From an accepted spoon-reservoir run: the thread model (simulate_honey_spoon_toast.py), the bulk surface of the
reservoir run, the thread mesh, the render and the technical checks; --with-edits also rebuilds the four edits
(edits/reproduce.py)."""
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
    p = parser(__doc__)
    p.add_argument('--reservoir-run',type=Path,default=ROOT/'renders/pcve_suites/pcve_honey_spoon_toast_suite/inputs/04_realtime_runs/reservoir_ts1')
    p.add_argument('--bulk-run',type=Path,default=ROOT/'renders/pcve_suites/pcve_honey_spoon_toast_suite/inputs/04_realtime_runs/rope_source')
    p.add_argument('--input-blend',type=Path,default=asset('scenes/honey_spoon_toast/scene_template.blend'))
    p.add_argument('--with-edits',action='store_true',help='Also rebuild the four edits, including the honey removal at frame 51')
    a = p.parse_args(cli_args())
    a.out_root=a.out_root.expanduser().resolve()
    a.reservoir_run=a.reservoir_run.expanduser().resolve()
    a.bulk_run=a.bulk_run.expanduser().resolve()
    a.input_blend=a.input_blend.expanduser().resolve()
    run=a.out_root/'runs/source'
    output=a.out_root/'source'
    steps=[Step('source_simulate','simulate',[a.python,HERE/'simulate_honey_spoon_toast.py',
                '--source',a.reservoir_run,'--out',run],(run/'simulation_report.json',)),
           Step('source_bulk','surface',[a.python,HERE/'physics/prepare_honey_bulk.py','--run',run,'--bulk-run',a.bulk_run],(run/'meshes_smooth',)),
           Step('source_surface','surface',[a.python,HERE/'mesh_viscous_rope.py','--run',run,'--workers',str(a.threads)],(run/'filament_meshes',)),
           Step('source_render','render',blender(a,HERE/'render_honey_spoon_toast.py','--input-blend',a.input_blend,
                '--run',run,'--out-dir',output,'--samples','32','--mesh-subdir','meshes_smooth',
                '--extra-mesh-subdir','filament_meshes','--encode'),(output/'honey_spoon_toast.mp4',)),
           Step('source_verify','verify',[a.python,HERE/'physics/validate_viscous_rope.py','--run',run,'--source',a.reservoir_run,
                '--video',output/'honey_spoon_toast.mp4','--out',a.out_root/'technical_acceptance.json'])]
    if a.with_edits:
        if not a.gpu:
            p.error('--with-edits requires --gpu identifying an available simulation GPU')
        steps.append(Step('independent_edits','edits',[a.python,HERE/'edits/reproduce.py','--work-dir',a.out_root/'edits','--gpu',a.gpu],
                          (a.out_root/'edits/lower_viscosity',a.out_root/'edits/remove_honey_at_frame_51/render/honey_spoon_toast.mp4')))
    execute(HERE.name,a,steps,[a.reservoir_run,a.bulk_run,a.input_blend])

if __name__ == '__main__':
    main()
