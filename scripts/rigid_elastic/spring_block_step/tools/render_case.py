"""Render one case of the current look (appearance/realism.py) in Blender 4.3.2.

    render_case.py --case source --out renders/spring_block_step/<rev>/render/source [--frames 1 20 ...]
                   [--samples N] [--device optix|cuda|cpu] [--gpu INDEX|UUID] [--threads N] [--blender-bin BIN]
                   [--no-blend] [--native DIR]

Any Linux host. --gpu binds CUDA_VISIBLE_DEVICES for this one Blender process
(check the card is free first); --device cpu renders on the CPU with --threads.
Every frame of a case must come from one device type with the same settings.
Outputs may not be written under scripts/.
"""
from pathlib import Path
import argparse, os, subprocess

HERE = Path(__file__).resolve().parent
SCENE = HERE.parent
REPO = SCENE.parents[2]
CASES = ('source', 'mass_half', 'young_quarter', 'friction_half', 'remove_spring', 'add_block')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--case', required=True, choices=CASES)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--frames', nargs='+', type=int)
    p.add_argument('--samples', type=int)
    p.add_argument('--device', choices=('optix', 'cuda', 'cpu'), default='optix')
    p.add_argument('--gpu', help='GPU index or UUID for CUDA_VISIBLE_DEVICES')
    p.add_argument('--threads', type=int, default=16)
    p.add_argument('--blender-bin', type=Path, default=REPO / 'tools/blender-4.3.2-linux-x64/blender')
    p.add_argument('--native', type=Path)
    p.add_argument('--no-blend', action='store_true', help='do not save scene.blend (preview renders)')
    a = p.parse_args()
    out = a.out.expanduser().resolve()
    scripts = (REPO / 'scripts').resolve()
    if out == scripts or scripts in out.parents:
        p.error('outputs may not be written under scripts/')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    if a.gpu is not None:
        env['CUDA_VISIBLE_DEVICES'] = str(a.gpu)
    elif a.device == 'cpu':
        env['CUDA_VISIBLE_DEVICES'] = ''
    command = [str(a.blender_bin), '-b', '--factory-startup', '-t', str(a.threads), '--python-exit-code', '1',
               '--python', str(SCENE / 'appearance/realism.py'), '--', '--case', a.case, '--out', str(out), '--device', a.device]
    if a.frames:
        command += ['--frames', *map(str, a.frames)]
    if a.samples:
        command += ['--samples', str(a.samples)]
    if a.native:
        command += ['--native', str(a.native)]
    if a.no_blend:
        command.append('--no-blend')
    print(' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command, env=env, cwd=REPO).returncode)


if __name__ == '__main__':
    main()
