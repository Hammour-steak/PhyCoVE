"""Public pipeline entry point for apple_drop_kitchen_basin."""
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
from pcve_scene_pipeline import ROOT, Step, cli_args, execute, parser


def main():
    p = parser(__doc__)
    p.add_argument('--cases', nargs='+', choices=('source','edit_heavy_apple','edit_high_density_liquid','edit_viscous_liquid','delete_water','delete_water_at_2s'), default=['source'])
    p.add_argument('--source-run',type=Path,default=ROOT/'renders/pcve_suites/pcve_apple_drop_kitchen_basin_suite/inputs/01_apple_drop_kitchen_basin/base',help='Accepted source cache used by the water-removal edits; read-only')
    p.add_argument('--render-gpus', type=int, default=1)
    a = p.parse_args(cli_args())
    a.out_root = a.out_root.expanduser().resolve()
    if a.render_gpus < 1:
        p.error('--render-gpus must be positive')
    water = a.out_root / 'settle/water_state.npz'
    sim = HERE / 'simulate_apple_drop_kitchen_basin.py'
    idle = HERE.parent / 'bowling_ball_pool_drop/tools/run_on_idle_gpu.sh'
    removal={'delete_water','delete_water_at_2s'}
    steps = [] if set(a.cases)<=removal else [Step('settle','simulate',['bash',idle,a.python,'-u',sim,'settle','--extra-layers','2',
             '--surface-tension','2.5e-3','--domain-top','3.5','--out',water.parent],(water,))]
    extra = {'source': [], 'edit_heavy_apple':['--ball-mass',str(850 * 4/3 * __import__('math').pi * .04**3 * 1.5)],
             'edit_high_density_liquid':['--liquid-density','1996.4'],
             'edit_viscous_liquid':['--liquid-nu','1.004e-2','--substeps','50']}
    for case in dict.fromkeys(a.cases):
        run = a.out_root / 'runs' / case
        video = a.out_root / (case + '.mp4')
        if case in removal:
            first=1 if case=='delete_water' else 49
            steps += [Step(case+'_simulate','simulate',['bash',idle,a.python,HERE/'physics/remove_water_edits.py',
                       '--source',a.source_run,'--out',run,'--case',case],(run/'simulation_report.json',)),
                      Step(case+'_render','render',['bash',idle,a.blender,'--factory-startup','-b','-t',str(a.threads),
                       '--python-exit-code','1','--python',HERE/'render_apple_drop_kitchen_basin.py','--',
                       '--run',run,'--out',run/'render','--frame-list',','.join(map(str,range(first,97))),
                       '--samples','1024','--resolution','1280','720','--gpu-backend','CUDA'],(run/'render/render_report.json',)),
                      Step(case+'_encode','render',[a.python,HERE/'physics/encode_water_removal.py','--run',run,'--video',video],(video,)),
                      Step(case+'_verify','verify',[a.python,ROOT/'scripts/pcve_verify_video.py',video,
                       '--out',a.out_root/(case+'_video_verification.json')])]
            continue
        gamma = '1.25e-3' if case == 'edit_high_density_liquid' else '2.5e-3'
        steps += [Step(case+'_simulate','simulate',['bash',idle,a.python,'-u',sim,'run','--water-state',water,
                  '--domain-top','3.5','--surface-tension',gamma,*extra[case],'--out',run],(run/'simulation_report.json',)),
                  Step(case+'_render','render',['bash',HERE/'tools/pipeline_apple_drop_kitchen_basin.sh',run,video],(video,),
                       {'RENDER_GPUS':str(a.render_gpus),'BLENDER':str(a.blender),'PCVE_GENESIS_PYTHON':str(a.python)}),
                  Step(case+'_verify','verify',[a.python,ROOT/'scripts/pcve_verify_video.py',video,
                       '--out',a.out_root/(case+'_video_verification.json')])]
    execute(HERE.name,a,steps,[a.source_run] if set(a.cases)&removal else [])

if __name__ == '__main__':
    main()
