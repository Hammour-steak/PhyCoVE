"""Encode, verify and prepare review sheets for a suite rendered by tools/render_template_suite.py; record visual acceptance.

.venv-domino/bin/python scripts/rigid_rigid/ramp_car_ball_collision/tools/review_template_suite.py \
  --out-root renders/ramp_car_ball_collision/template_suite --cases source
# after actually looking at every sheet and the video:
.venv-domino/bin/python .../review_template_suite.py --out-root ... --accept source --evidence-json review.json

Encoding is libx264 slow, CRF 17, yuv420p, faststart.  This
script never grants visual acceptance by itself; --accept only records a review that was done.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageOps

FRAMES = range(1, 97)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def crop_box(item, width, height, padding=16):
    a, b, c, d = item['uv_bounds']
    return (max(0, int(a * width) - padding), max(0, int((1 - d) * height) - padding),
            min(width, int(c * width) + padding), min(height, int((1 - b) * height) + padding))


def sheet(folder, projected, frames, name, focus_crop=False, cell=(240, 155), columns=8):
    rows = (len(frames) + columns - 1) // columns
    output = Image.new('RGB', (columns * cell[0], rows * cell[1]), '#181818')
    draw = ImageDraw.Draw(output)
    for slot, index in enumerate(frames):
        with Image.open(folder / 'frames' / f'frame_{index:04d}.png') as image:
            if focus_crop:
                objects = projected[index - 1]['objects']
                focus = objects.get('car_body', objects.get('ball'))
                image = image.crop(crop_box(focus, 1280, 720, 18))
            tile = ImageOps.contain(image.convert('RGB'), (cell[0], cell[1] - 20), Image.Resampling.LANCZOS)
            x = (slot % columns) * cell[0]
            y = (slot // columns) * cell[1]
            output.paste(tile, (x + (cell[0] - tile.width) // 2, y))
            draw.text((x + 5, y + cell[1] - 18), f'F{index:02d}  {(index - 1) / 24:.3f}s', fill='white')
    output.save(folder / 'review' / name, quality=94)


def temporal_stability(folder, moving_boxes):
    """Frame-to-frame change at 480x270 outside every moving body's padded projection."""
    previous = None
    diffs = []
    for index in FRAMES:
        with Image.open(folder / 'frames' / f'frame_{index:04d}.png') as image:
            current = np.asarray(image.convert('RGB').resize((480, 270), Image.BILINEAR), dtype=np.float32)
        if previous is not None:
            mask = np.ones((270, 480), bool)
            for box in moving_boxes[index - 2] + moving_boxes[index - 1]:
                x0, y0, x1, y1 = [int(v * 480 / 1280) if i % 2 == 0 else int(v * 270 / 720) for i, v in enumerate(box)]
                mask[max(0, y0 - 12):y1 + 12, max(0, x0 - 12):x1 + 12] = False
            delta = np.abs(current - previous).max(axis=2)[mask]
            diffs.append({'pair': [index - 1, index], 'mean_abs_8bit': float(delta.mean()), 'p999_abs_8bit': float(np.percentile(delta, 99.9))})
        previous = current
    return {'method': '480x270 bilinear, static region = frame minus padded projections of all moving bodies in both frames',
            'max_mean_abs_8bit': max(d['mean_abs_8bit'] for d in diffs), 'max_p999_abs_8bit': max(d['p999_abs_8bit'] for d in diffs),
            'pairs': diffs}


def verify_case(out, case_id, manifest_rows):
    folder = out / 'cases' / case_id
    files = [folder / 'frames' / f'frame_{i:04d}.png' for i in FRAMES]
    assert all(p.is_file() for p in files), (case_id, 'incomplete frame set')
    hashes = {p.name: sha(p) for p in files}
    for p in files:
        with Image.open(p) as image:
            assert image.size == (1280, 720) and image.mode == 'RGB', p
            image.verify()
    video = folder / 'video.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-threads', '2', '-framerate', '24', '-i', str(folder / 'frames/frame_%04d.png'),
                    '-frames:v', '96', '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart', str(video)], check=True)
    info = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
                                      'stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration',
                                      '-of', 'json', str(video)], capture_output=True, text=True, check=True).stdout)
    stream = info['streams'][0]
    checks = {'resolution': (stream['width'], stream['height']) == (1280, 720), 'fps': stream['r_frame_rate'] == '24/1',
              'frames': stream['nb_read_frames'] == '96', 'duration': abs(float(info['format']['duration']) - 4.0) < 1 / 24}
    assert all(checks.values()), (case_id, checks, info)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '2', '-i', str(video), '-f', 'null', '-'], check=True)
    validation = {'accepted': True, 'sha256': sha(video), 'checks': checks, 'full_decode': True, 'png_sha256': hashes, 'probe': info}
    save(folder / 'video_validation.json', validation)
    # One execution summary from the per-process reports.
    reports = [json.loads(p.read_text()) for p in sorted(folder.glob('render_execution_*.json'))]
    rendered = {f: r['backend'] for r in reports for f in r['frame_seconds']}
    reused = {str(x['frame']): x for r in reports for x in r['reused_frames']}
    backends = sorted({r['backend'] for r in reports if r['frame_seconds']})
    assert len(backends) == 1, (case_id, 'one device per case', backends)
    assert set(rendered) | set(reused) == {str(f) for f in FRAMES}, (case_id, 'frames of unknown origin')
    save(folder / 'render_execution.json', {'status': 'rendered_pending_review', 'backend': backends[0], 'samples': 128,
        'rendered_frame_count': len(rendered), 'reused_frame_count': len(reused), 'process_reports': [r['tag'] for r in reports],
        'reused_frames': sorted(reused.values(), key=lambda x: x['frame']), 'video_sha256': validation['sha256'],
        'encode': 'ffmpeg libx264 -preset slow -crf 17 -pix_fmt yuv420p -movflags +faststart, 24 fps, 96 frames',
        'reuse_scope': 'Exact root matrices at shutter start, centre and end; same frame index and packed template; no approximately equal poses or image interpolation'})
    if reused:
        save(folder / 'exact_frame_reuse.json', {'accepted': True, 'frame_count': len(reused),
            'scope': 'Identical packed template, frame index and all root matrices at shutter start, centre and end (render_state_signatures.json).',
            'frames': sorted(reused.values(), key=lambda x: x['frame'])})
    pose = json.loads((folder / 'appearance_pose_validation.json').read_text())
    assert pose['accepted'] and json.loads((folder / 'physics_validation.json').read_text())['accepted']
    projected = pose['projected_bounds']
    (folder / 'review').mkdir(exist_ok=True)
    sheet(folder, projected, list(FRAMES), 'all_96_frames.jpg')
    sheet(folder, projected, list(FRAMES), 'focus_all_96_frames.jpg', True)
    sheet(folder, projected, list(range(23, 37)), 'collision_neighborhood.jpg', True, (400, 240), 4)
    sheet(folder, projected, list(range(85, 97)), 'stop_tail.jpg', True, (400, 240), 4)
    if case_id == 'edit_remove_car_at_2s':
        sheet(folder, projected, list(range(45, 54)), 'deletion_boundary_full.jpg', False, (640, 380), 3)
    boxes = [[crop_box(o, 1280, 720, 6) for o in p['objects'].values()] for p in projected]
    stability = temporal_stability(folder, boxes)
    save(folder / 'review' / 'temporal_stability.json', stability)
    row = manifest_rows[case_id]
    row['status'] = 'technically_verified_pending_visual_review'
    row['video_sha256'] = validation['sha256']
    return {'status': row['status'], 'video_sha256': validation['sha256'], 'frames': 96, 'resolution': [1280, 720], 'fps': 24,
            'duration_sec': 4.0, 'backend': backends[0], 'rendered_frames': len(rendered), 'reused_frames': len(reused),
            'static_region_max_mean_abs_8bit': stability['max_mean_abs_8bit']}


def accept(out, case_id, evidence, manifest_rows):
    folder = out / 'cases' / case_id
    validation = json.loads((folder / 'video_validation.json').read_text())
    assert validation['sha256'] == sha(folder / 'video.mp4')
    record = {'accepted': True, 'reviewer': 'automated_check', 'revision': 'room_finish',
              'reviewed_at_utc': datetime.now(timezone.utc).isoformat(), 'video_sha256': validation['sha256'],
              'physics_sha256': sha(folder / 'physics_transforms.json'),
              'evidence_files_sha256': {p.name: sha(p) for p in sorted((folder / 'review').glob('*.jpg'))}, **evidence}
    save(folder / 'case_acceptance.json', record)
    row = manifest_rows[case_id]
    row['status'] = 'accepted'
    row['case_acceptance'] = str(folder / 'case_acceptance.json')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-root', type=Path, required=True)
    parser.add_argument('--cases', nargs='*', default=[])
    parser.add_argument('--accept')
    parser.add_argument('--evidence-json', type=Path)
    args = parser.parse_args()
    out = args.out_root.resolve()
    manifest = json.loads((out / 'suite_manifest.json').read_text())
    rows = {r['case_id']: r for r in [manifest['source']] + manifest['edits']}
    summary_path = out / 'all_video_technical_validation.json'
    summary = json.loads(summary_path.read_text())['cases'] if summary_path.exists() else {}
    for case_id in args.cases:
        summary[case_id] = verify_case(out, case_id, rows)
        print(case_id, json.dumps(summary[case_id]), flush=True)
    if args.cases:
        save(summary_path, {'accepted': all(v['status'] != 'failed' for v in summary.values()), 'cases': summary})
    if args.accept:
        accept(out, args.accept, json.loads(args.evidence_json.read_text()), rows)
        print('ACCEPTED', args.accept)
    statuses = [r['status'] for r in rows.values()]
    manifest['status'] = 'accepted' if all(s == 'accepted' for s in statuses) else 'rendering_and_review_in_progress'
    if manifest['status'] == 'accepted':
        manifest['visual_review'] = {'reviewer': 'automated_check', 'all_cases_accepted': True, 'case_count': len(rows)}
    save(out / 'suite_manifest.json', manifest)


if __name__ == '__main__':
    main()
