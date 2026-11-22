"""Public pipeline entry point for traditional_tea_pour."""
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


PHYSICS,APPEARANCE,TOOLS=HERE/'physics',HERE/'appearance',HERE/'tools'
# the accepted contact inputs, source run (table caps) and environment scene, kept in the published suite's inputs
ACCEPTED=ROOT/'renders/pcve_suites/pcve_traditional_tea_pour_suite/inputs/source/cases'

def main():
    p=parser(__doc__)
    p.add_argument('--inputs',type=Path,default=ACCEPTED/'contact_inputs',help='Existing contact reproduction inputs; never modified')
    p.add_argument('--input-blend',type=Path,default=ACCEPTED/'environment_render/scene_environment_refined.blend',help='Existing environment/delivered scene, read-only')
    p.add_argument('--baseline-caps',type=Path,default=ACCEPTED/'source_run/table_cap_geometry_all.json')
    a=p.parse_args(cli_args())
    a.out_root=a.out_root.expanduser().resolve()
    a.inputs=a.inputs.expanduser().resolve()
    a.input_blend=a.input_blend.expanduser().resolve()
    case=a.out_root/'source'
    caps=a.baseline_caps.expanduser().resolve()
    steps=[Step('prepare','prepare',[a.python,PHYSICS/'prepare_tea_dynamic_case.py',a.inputs,case,
                '--coaster',a.inputs/'coaster_world.obj'],(case/'input_provenance.json',)),
           Step('simulate','simulate',[a.python,HERE/'simulate_traditional_tea_pour.py',case],(case/'simulation_result.json',)),
           Step('surface','surface',[a.python,PHYSICS/'surface_tea_dynamics.py',case],(case/'surfaces',)),
           Step('actual_cup','verify',[a.python,TOOLS/'audit_genesis_actual_cup.py',case]),
           Step('numerical_checks','verify',[a.python,TOOLS/'validate_genesis_tea.py',case,'--plan',case/'acceptance_plan.json']),
           Step('motion','verify',[a.python,PHYSICS/'measure_tea_dynamics.py',case,'--all-frames']),
           Step('table_caps','verify',[a.python,PHYSICS/'measure_tea_table_caps.py',case,caps,case,'--all-frames']),
           Step('contact_acceptance','verify',[a.python,TOOLS/'accept_tea_contact.py',case,'--baseline-caps',caps]),
           Step('native_prepare','render',blender(a,APPEARANCE/'prepare_tea_contact_native.py',case,scene=a.input_blend),
                (case/'scene_tea_fixed.blend',)),
           Step('render','render',[a.python,APPEARANCE/'launch_tea_render.py','-b',case/'scene_tea_fixed.blend',
                '--python-exit-code','1','--python',HERE/'render_traditional_tea_pour.py','--',case,'--samples','128','--save-quality'],
                (case/'render_all.json',)),
           Step('video_qa','verify',[a.python,TOOLS/'qa_tea_contact.py',case],(case/'video_contact_fixed.mp4',)),
           Step('video_verify','verify',[a.python,ROOT/'scripts/pcve_verify_video.py',case/'video_contact_fixed.mp4',
                '--out',a.out_root/'video_verification.json'])]
    execute(HERE.name,a,steps,[a.inputs,a.input_blend,caps,a.inputs/'coaster_world.obj'])

if __name__=='__main__':main()
