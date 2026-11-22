"""Render one independent edit at the source's complete delivery quality."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from PIL import Image, ImageChops
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO, blender

parser = argparse.ArgumentParser()
parser.add_argument('--case', required=True, choices=['remove_bread', 'remove_honey', 'lower_viscosity'])
parser.add_argument('--work-dir', type=Path, required=True)
args = parser.parse_args()
ROOT = REPO
STAGE = args.work_dir.resolve()
CASE = STAGE / args.case
OUT = CASE / 'render'
RUN = CASE / 'simulation'
RENDERER = STAGE / 'code/edits/render_edit.py'
BLENDER = blender()
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()

assert not OUT.exists(), OUT
prep = json.loads((STAGE / 'preparation_report.json').read_text())['cases'][args.case]
assert digest(CASE / 'scene.blend') == prep['template_sha256']
OUT.mkdir()
shutil.copy2(CASE / 'scene.blend', OUT / 'scene.blend')
preview = CASE / 'preview'
rows = []
for row in json.loads((preview / 'render_report.json').read_text())['frames']:
    source = preview / row['file']
    os.link(source, OUT / source.name)
    rows.append(dict(row, device='CPU preview', sha256=digest(source)))
assert rows
tick = time.monotonic()
if args.case == 'remove_honey':
    with Image.open(preview / 'frame_0001.png') as first, Image.open(preview / 'frame_0096.png') as last:
        assert ImageChops.difference(first.convert('RGB'), last.convert('RGB')).getbbox() is None
    for frame in range(1, 97):
        target = OUT / f'frame_{frame:04d}.png'
        if not target.exists():
            os.link(OUT / 'frame_0001.png', target)
            rows.append({'frame': frame, 'seconds': 0., 'file': target.name,
                         'reused_static_frame': 1, 'sha256': digest(target)})
    workers = []
else:
    completed = {row['frame'] for row in rows}
    remaining = [f for f in range(1, 97) if f not in completed]
    workers = []
    for index in range(4):
        frames = remaining[index::4]
        directory = OUT / f'worker_cpu_{index}'
        log = (OUT / f'render_cpu_{index}.log').open('w')
        command = [str(BLENDER), '-b', '-t', '32', '--python-exit-code', '1',
                   '--python', str(RENDERER), '--', '--input-blend', str(OUT / 'scene.blend'),
                   '--run', str(RUN), '--out-dir', str(directory), '--samples', '32',
                   '--mesh-subdir', 'meshes_smooth', '--frames', *map(str, frames)]
        if args.case == 'remove_bread':
            command.extend(['--extra-mesh-subdir', 'filament_meshes'])
        process = subprocess.Popen(command, env=dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='32'),
                                   stdout=log, stderr=subprocess.STDOUT)
        workers.append((process, log, index, directory, frames))
    print('RENDERING', args.case, len(remaining), flush=True)
    for process, log, index, directory, frames in workers:
        code = process.wait()
        log.close()
        assert code == 0, (index, code)
        report = json.loads((directory / 'render_report.json').read_text())
        assert [row['frame'] for row in report['frames']] == frames
        for row in report['frames']:
            source = directory / row['file']
            os.link(source, OUT / source.name)
            rows.append(dict(row, device=f'CPU worker {index}', sha256=digest(source)))
render_wall = time.monotonic() - tick
rows.sort(key=lambda row: row['frame'])
assert [row['frame'] for row in rows] == list(range(1, 97))
tick = time.monotonic()
video = OUT / 'honey_spoon_toast.mp4'
subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-framerate', '24', '-i',
                str(OUT / 'frame_%04d.png'), '-c:v', 'libx264', '-crf', '18',
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)], check=True)
encoding = time.monotonic() - tick
probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
    '-count_frames', '-show_entries', 'stream=codec_name,width,height,r_frame_rate,nb_read_frames:format=duration',
    '-of', 'json', str(video)], text=True))
stream = probe['streams'][0]
assert (stream['width'], stream['height'], stream['r_frame_rate'], int(stream['nb_read_frames'])) == (1280,720,'24/1',96)
assert float(probe['format']['duration']) == 4.
subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-f', 'null', '-'], check=True)
record = {'case': args.case, 'status': 'media_checks_passed_visual_review_pending',
          'scene_sha256': prep['template_sha256'], 'video_sha256': digest(video),
          'frames': rows, 'media': probe,
          'render': {'engine': 'Cycles CPU', 'samples': 32, 'resolution': [1280,720],
                     'fps': 24, 'frames': 96, 'duration_s': 4., 'crf': 18},
          'timings_seconds': {'render_wall': render_wall, 'render_compute_sum': sum(r['seconds'] for r in rows),
                              'encode': encoding},
          'static_shot_reused': args.case == 'remove_honey'}
(OUT / 'render_report.json').write_text(json.dumps(record, indent=2) + '\n')
print('ENCODED', args.case, record['video_sha256'], flush=True)
