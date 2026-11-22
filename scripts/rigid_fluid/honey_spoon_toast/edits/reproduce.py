"""Rebuild the four independent edits in a fresh isolated directory."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO, blender

parser = argparse.ArgumentParser()
parser.add_argument('--work-dir', type=Path, required=True)
parser.add_argument('--gpu', required=True, help='Available simulation GPU selected after checking server load')
args = parser.parse_args()
root = REPO
code = Path(__file__).resolve().parent
stage = args.work_dir.resolve()
assert not stage.exists(), 'A fresh work directory is required; source caches are read-only.'
stage.mkdir(parents=True)
shutil.copytree(code.parent, stage / 'code', ignore=shutil.ignore_patterns('__pycache__'))
py = str(root / '.venv-genesis-mpm-sph/bin/python')
blender = str(blender())
source = root / 'renders/pcve_suites/pcve_honey_spoon_toast_suite/inputs/04_realtime_runs/reservoir_ts1'
baseline = root / 'renders/pcve_suites/pcve_honey_spoon_toast_suite/inputs/04_realtime_runs/rope_source'


def run(command, gpu=None):
    env = dict(os.environ, OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4', RAYON_NUM_THREADS='16')
    env['CUDA_VISIBLE_DEVICES'] = '' if gpu is None else str(gpu)
    subprocess.run(list(map(str, command)), env=env, check=True)


for script in ['prepare_edits.py', 'export_contact.py']:
    run([blender, '-b', '-t', '8', '--python-exit-code', '1', '--python', code / script,
         '--', '--work-dir', stage])
prep = json.loads((stage / 'preparation_report.json').read_text())
run([blender, '-b', '-t', '8', '--python-exit-code', '1', '--python', code / 'export_bread_contact.py',
     '--', '--input-blend', stage / 'lower_viscosity/scene.blend',
     '--out-dir', stage / 'receiving_surface'])
plate_run = stage / 'remove_bread/simulation'
run([py, code.parent / 'simulate_viscous_rope.py', '--source', source, '--out', plate_run,
     '--landing-height', prep['plate_landing_z_m']])
for frame in range(1, 97):
    with np.load(plate_run / 'particles' / f'frame_{frame:04d}.npz') as a, np.load(baseline / 'particles' / f'frame_{frame:04d}.npz') as b:
        assert np.array_equal(a['honey_pos'], b['honey_pos'])
(plate_run / 'meshes_smooth').mkdir()
for path in (baseline / 'meshes_smooth').glob('*.npz'):
    os.link(path, plate_run / 'meshes_smooth' / path.name)
run([py, code.parent / 'mesh_viscous_rope.py', '--run', plate_run, '--workers', '12'])
low_run = stage / 'lower_viscosity/simulation'
run([py, code / 'simulate_honey_reservoir.py', '--out', low_run, '--viscosity', '.0001', '--dx', '.001', '--steps-per-frame', '32', '--substeps', '137',
     '--plate-collision', stage / 'plate_collision.obj', '--receiving-contact', stage / 'receiving_contact.json',
     '--toast-collision', stage / 'receiving_surface/toast_collision.obj',
     '--toast-contact', stage / 'receiving_surface/toast_surface.npz',
     '--table-top', '.7587666511535645', '--table-center', '0', '0', '--table-size', '2', '1.4',
     '--domain-lower', '-.9', '-.6', '.73', '--domain-upper', '.95', '.6', '1.04'], gpu=args.gpu)
run([py, code / 'surface_honey_spoon_toast.py', '--run', low_run, '--smoothing-iters', '24',
     '--iso-threshold', '.4', '--mesh-subdir', 'meshes_smooth', '--calibrate-isolated-volume',
     '--toast-contact', stage / 'receiving_surface/toast_surface.npz', '--boundary-mirror'])
for case, frames in [('remove_bread', [1, 60, 96]), ('remove_honey', [1, 96]),
                     ('lower_viscosity', [1, 8, 12, 24, 48, 72, 96])]:
    command = [blender, '-b', '-t', '32', '--python-exit-code', '1', '--python', code / 'render_edit.py',
               '--', '--input-blend', stage / case / 'scene.blend', '--run',
               baseline if case == 'remove_honey' else stage / case / 'simulation',
               '--out-dir', stage / case / 'preview', '--samples', '32', '--mesh-subdir', 'meshes_smooth',
               '--frames', *frames]
    if case == 'remove_bread':
        command += ['--extra-mesh-subdir', 'filament_meshes']
    if case == 'remove_honey':
        command += ['--no-honey']
    run(command)
    run([py, code / 'render_sequence.py', '--work-dir', stage, '--case', case])
    run([py, code / 'make_review.py', '--work-dir', stage, '--case', case])
run([py, code / 'build_timed_remove_honey.py', '--out-root', stage / 'remove_honey_at_frame_51',
     '--source-run', baseline])
print('REPRODUCTION_COMPLETE_VISUAL_REVIEW_REQUIRED', stage)
