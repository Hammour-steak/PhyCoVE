"""Public pipeline entry point for beach_ball_hammock_mpm."""
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


BUILDER_VALUE_FLAGS=('--out-root','--stage','--python','--blender','--threads','--gpu','--work-dir','--output-dir',
                     '--source-blend','--appearance-json')


def split_simulation_args(argv):
    """--simulation-args swallows everything after it; the shared entry adapter appends --stage,
    --out-root, --threads, ... after the native arguments, so move builder options back in front."""
    if '--simulation-args' not in argv:
        return argv
    i=argv.index('--simulation-args')
    head,tail,rest=list(argv[:i]),argv[i+1:],[]
    j=0
    while j<len(tail):
        if tail[j] in BUILDER_VALUE_FLAGS and j+1<len(tail):
            head+=tail[j:j+2];j+=2
        elif tail[j]=='--dry-run':
            head.append(tail[j]);j+=1
        else:
            rest.append(tail[j]);j+=1
    return head+['--simulation-args',*rest]


def main():
    p=parser(__doc__,'.venv-taichi-mpm')
    p.add_argument('--source-blend',type=Path,required=True)
    p.add_argument('--work-dir',type=Path)
    p.add_argument('--output-dir',type=Path)
    p.add_argument('--appearance-json',help='Appearance JSON for the render stage (default: appearance/appearance.json)')
    p.add_argument('--simulation-args',nargs=__import__('argparse').REMAINDER,default=[],help='Existing native simulator flags; this option must be last')
    a=p.parse_args(split_simulation_args(cli_args()))
    if any(value.split('=')[0] in ('--work-dir','--reuse-cache') for value in a.simulation_args):
        p.error('--simulation-args cannot redirect or reuse a runtime cache')
    a.out_root=a.out_root.expanduser().resolve()
    work=(a.work_dir or a.out_root/'work').resolve()
    output=(a.output_dir or a.out_root/'output').resolve()
    if a.stage in ('all','prepare'):
        for folder in (work,output):
            if folder.exists() and any(folder.iterdir()):
                p.error('Choose fresh work/output directories: '+str(folder))
    steps=[Step('prepare','prepare',blender(a,HERE/'appearance/prepare_beach_ball_hammock_mpm.py','--source-blend',a.source_blend,
                '--work-dir',work),(work/'scene.blend',work/'mpm_hammock_surface.npz')),
           # A str keeps the virtualenv entry point: the runner resolves Path commands, and resolving the venv's
           # symlinked interpreter would start the system Python, which has no Taichi.
           Step('simulate','simulate',[str(a.python.expanduser().absolute()),HERE/'simulate_beach_ball_hammock_mpm.py',
                '--work-dir',work,*a.simulation_args]),
           Step('render','render',blender(a,HERE/'render_beach_ball_hammock_mpm.py','--work-dir',work,
                '--output-dir',output,*(['--appearance-json',a.appearance_json] if a.appearance_json else [])),
                (output/'video.mp4',)),
           Step('verify','verify',[sys.executable,ROOT/'scripts/pcve_verify_video.py',output/'video.mp4',
                '--out',a.out_root/'video_verification.json'])]
    execute(HERE.name,a,steps,[a.source_blend])

if __name__=='__main__':main()
