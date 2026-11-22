"""Encode a finished render of all six cases and build a fresh pcve_book_pillow_bedroom_suite from it.

    python3 tools/publish_suite.py --renders renders/book_pillow_bedroom/<render>         --out <new suite folder>/pcve_book_pillow_bedroom_suite [--update-pointer]

Per case (<renders>/<native case>/ from render_book_pillow_bedroom.py):
1. checks 96 frames with provenance, a passed binding audit and render_report.json, all on one backend
   and one look fingerprint;
2. encodes frames/frame_%04d.png to video.mp4 (H.264 High, CRF 16, 24 fps, 96 frames, yuv420p,
   BT.709 limited range tags) and writes encode_report.json (media contract, full decode with exact
   i/24 s timestamps);
3. measures temporal stability: on the video scaled to 480x270, the mean absolute frame-to-frame
   luma change inside static regions (wall, headboard, side table) for every frame pair.
Then it writes the suite in the current PCVE formats (the --out directory must not exist):
cases/<case>/ with a hard link of video.mp4, video_validation.json (pcve_video_validation/1),
prompts.json (pcve_prompts/1, from the builder catalog), provenance.json (pcve_provenance/1) and
native_metadata/ (physics config, motion audit, scenario overrides, metrics; the render and encode
reports), suite_manifest.json (pcve_suite/1), inputs/native_input_locations.json and README.txt.
Ground truth is added afterwards by tools/export_ground_truth.py. --update-pointer rewrites
scene_manifest.json canonical_suites. Prompts of a published suite are updated with
`build_pcve_book_pillow_bedroom.py --export-prompts`.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

CASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE.parents[1]), str(CASE)]
from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog
from pcve_media_contract import require_times, require_video
from scene_paths import REPO, SCENE, SUITE, manifest, native_delivery

BUILDER = CASE / f'build_pcve_{SCENE}.py'

CASES = ('source', 'heavy_book', 'firm_pillow', 'add_bedside_book', 'soft_pillow', 'remove_pillow')
CRF = 16
# Static image regions (x0, y0, x1, y1 at 480x270): wall above the headboard, upper headboard, side table.
STATIC = {'wall': (180, 4, 470, 30), 'headboard': (300, 45, 470, 95), 'side_table': (0, 120, 100, 175)}


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def catalog_id(case):
    return 'source' if case == 'source' else 'edit_' + case


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def rel(path):
    path = Path(path).resolve()
    return path.relative_to(REPO.resolve()).as_posix() if path.is_relative_to(REPO.resolve()) else path.as_posix()


def check_render(folder):
    report = read(folder / 'render_report.json')
    audit = read(folder / 'binding_audit.json')
    frames = sorted((folder / 'frames').glob('frame_*.png'))
    if [p.name for p in frames] != [f'frame_{i:04d}.png' for i in range(1, 97)]:
        raise RuntimeError(f'{folder}: expected exactly 96 frames')
    if not audit['passed'] or report['rendered_frames'] != list(range(1, 97)):
        raise RuntimeError(f'{folder}: binding audit or rendered frame list is incomplete')
    records = [read(folder / 'frame_provenance' / f'frame_{i:04d}.json') for i in range(1, 97)]
    for record, frame in zip(records, frames):
        if record['png_sha256'] != sha(frame):
            raise RuntimeError(f'{frame}: PNG differs from its provenance')
    if len({(r['backend'], r['look'], r['samples']) for r in records}) != 1:
        raise RuntimeError(f'{folder}: frames were rendered with different backends, looks or samples')
    require_times(report['physical_times_s'])
    return report, records[0]


def encode(folder):
    video = folder / 'video.mp4'
    cmd = ['ffmpeg', '-v', 'error', '-y', '-framerate', '24', '-i', str(folder / 'frames/frame_%04d.png'),
           '-frames:v', '96', '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
           '-c:v', 'libx264', '-profile:v', 'high', '-preset', 'slow', '-crf', str(CRF), '-pix_fmt', 'yuv420p',
           '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv',
           '-movflags', '+faststart', str(video)]
    subprocess.run(cmd, check=True)
    media = require_video(video)
    decoded = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(video), '-vf', 'showinfo', '-f', 'null', '-'],
                             text=True, capture_output=True, check=True)
    rows = [(int(n), float(t)) for n, t in re.findall(r'\bn:\s*(\d+).*?\bpts_time:([\d.eE+-]+)', decoded.stderr)]
    if len(rows) != 96 or any(n != i or abs(t - i / 24) > 1e-5 for i, (n, t) in enumerate(rows)):
        raise RuntimeError(f'{video}: decoded frames or timestamps are not 96 at i/24 s')
    report = {'actual_media': media, 'full_decode_frames': len(rows), 'decoded_pts_s': [t for _, t in rows],
              'source': '96 Cycles sRGB PNG frames (AgX view)', 'command': [Path(c).name if os.sep in c else c for c in cmd],
              'no_retiming': True, 'video_sha256': sha(video)}
    write(folder / 'encode_report.json', report)
    return video, report


def stability(video):
    """Mean absolute luma change between consecutive frames in static regions (0-255 scale)."""
    out = {}
    for name, (x0, y0, x1, y1) in STATIC.items():
        vf = f'scale=480:270,crop={x1 - x0}:{y1 - y0}:{x0}:{y0},format=gray,tblend=all_mode=difference,signalstats'
        log = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(video), '-vf', vf + ',metadata=print:key=lavfi.signalstats.YAVG',
                              '-f', 'null', '-'], text=True, capture_output=True, check=True).stderr
        values = [float(v) for v in re.findall(r'lavfi\.signalstats\.YAVG=([\d.]+)', log)]
        out[name] = {'pairs': len(values), 'max_mean_abs_luma_change': round(max(values), 3),
                     'mean_mean_abs_luma_change': round(sum(values) / len(values), 3)}
    return out


def validation(video, report, case):
    """pcve_video_validation/1 of a freshly encoded video (encode() decoded all 96 frames at i/24 s)."""
    m = report['actual_media']
    probe = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_entries',
                                       'stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration',
                                       '-of', 'json', str(video)], text=True, capture_output=True, check=True).stdout)
    decode = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-f', 'null', '-'], capture_output=True, text=True)
    return {'schema_version': 1, 'format_version': 'pcve_video_validation/1', 'scene': SCENE, 'case_id': case,
            'video': 'video.mp4', 'resolution': [m['width'], m['height']],
            'fps': f"{m['fps_numerator']}/{m['fps_denominator']}", 'duration_sec': m['duration_s'], 'frames': m['frames'],
            'sha256': report['video_sha256'], 'technical_probe_verified': True,
            'full_decode_verified': report['full_decode_frames'] == 96 and decode.returncode == 0 and not decode.stderr.strip(),
            'content_unchanged': False, 'visual_or_physics_acceptance': 'new render; visual review pending',
            'native_validation': {'contract_probe': m, 'probe': probe}}


def prompt_record(record, fps):
    """The pcve_prompts/1 file that `--export-prompts` keeps unchanged for this catalog record."""
    item = {'schema_version': 1, 'format_version': FORMAT_VERSION, 'scene': SCENE, 'case_id': record['catalog_case_id'],
            'kind': record['kind'], 'source_case_id': 'source', 'availability': 'available',
            'prompts': record['prompts'], 'edit_dsl': None, 'object_id': None, 'applies_from_frame': None,
            'application_time_sec': None, 'physics_override': {}, 'physics_diff': {},
            'prompt_provenance': {'origin': 'generated:' + rel(BUILDER), 'text_modified': False}}
    if record['kind'] == 'edit':
        frame = _applies_from_frame(record)
        item.update(edit_dsl=record['edit_dsl'], applies_from_frame=frame, application_time_sec=(frame - 1) / fps,
                    physics_override=record['physics_override'], physics_diff=record['physics_diff'])
    return item


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--renders', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--update-pointer', action='store_true')
    a = p.parse_args()
    renders, out = a.renders.resolve(), a.out.resolve()
    if out.exists():
        raise SystemExit(f'{out} exists; choose a new suite folder')
    catalog = load_catalog(BUILDER)
    declared = {r['case_id']: r for r in [catalog['source'], *catalog['edits'].values()]}
    fps = _fps()
    native_root = native_delivery() / 'cases'
    rows = {}
    for case in CASES:
        folder = renders / case
        report, frame = check_render(folder)
        video, enc = encode(folder)
        rows[case] = dict(folder=folder, report=report, frame=frame, video=video, encode=enc, stable=stability(video))
        print('ENCODED', case, enc['video_sha256'], json.dumps(rows[case]['stable']), flush=True)
    (out / 'cases').mkdir(parents=True)
    now = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    records = {}
    for case, row in rows.items():
        cid = catalog_id(case)
        folder = out / 'cases' / cid
        (folder / 'native_metadata').mkdir(parents=True)
        os.link(row['video'], folder / 'video.mp4')
        check = validation(folder / 'video.mp4', row['encode'], cid)
        if not check['full_decode_verified']:
            raise RuntimeError(f'{cid}: full decode failed')
        write(folder / 'video_validation.json', check)
        native = native_root / case
        for src in [native / n for n in ('physics_config.json', 'motion_audit.json', 'scenario_overrides.json', 'metrics.json')] + \
                   [row['folder'] / n for n in ('render_report.json', 'binding_audit.json', 'encode_report.json')]:
            shutil.copyfile(src, folder / 'native_metadata' / src.name)
        prompts = prompt_record(declared[case], fps)
        write(folder / 'prompts.json', prompts)
        rep = row['report']
        write(folder / 'provenance.json', {
            'schema_version': 1, 'format_version': 'pcve_provenance/1', 'scene': SCENE, 'case_id': cid,
            'kind': prompts['kind'], 'native_case_id': case, 'video_sha256': check['sha256'], 'created_at': now,
            'native_cache': {'file': rel(native / 'simulation.npz'), 'sha256': rep['input_cache_sha256']},
            'render': {'render_dir': rel(row['folder']), 'look': rep['look'], 'samples': rep['samples'], 'backend': rep['backend'],
                       'blender': rep['blender']},
            'native_metadata': f'cases/{cid}/native_metadata', 'temporal_stability_480x270': row['stable']})
        records[case] = {
            'case_id': cid, 'native_case_id': case, 'kind': prompts['kind'], 'source_case_id': 'source',
            'case_dir': f'cases/{cid}', 'status': 'rendered_pending_review', 'availability': 'video_present',
            'video': f'cases/{cid}/video.mp4', 'video_sha256': check['sha256'],
            'media': {k: check[k] for k in ('resolution', 'fps', 'duration_sec', 'frames', 'sha256')},
            **{k: prompts[k] for k in ('prompts', 'edit_dsl', 'object_id', 'applies_from_frame', 'application_time_sec',
                                       'physics_override', 'physics_diff')}}
    (out / 'inputs').mkdir()
    write(out / 'inputs/native_input_locations.json', {
        'native_caches': {c: {'file': rel(native_root / c / 'simulation.npz'), 'sha256': rows[c]['report']['input_cache_sha256']} for c in CASES},
        'render_root': rel(renders), 'worker_kit_inputs': rel(native_delivery() / 'inputs'),
        'assets': ['assets/scenes/book_pillow_bedroom', 'assets/polyhaven/plastered_wall_04', 'assets/polyhaven/poly_wool_herringbone',
                   'assets/polyhaven/stretch_poplin', 'assets/polyhaven/side_table_01', 'assets/polyhaven/potted_plant_04',
                   'assets/polyhaven/ceramic_vase_04']})
    write(out / 'suite_manifest.json', {
        'schema_version': 5, 'format_version': 'pcve_suite/1',
        'layout': 'cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}',
        'scene': SCENE, 'title': SCENE, 'suite_name': SUITE, 'interaction_category': 'rigid_elastic',
        'suite_path': rel(out), 'source_count': 1, 'edit_count': len(CASES) - 1, 'status': 'rendered_pending_review',
        'source': records['source'], 'edits': [records[c] for c in CASES if c != 'source'],
        'metadata': {'scene_id': SCENE, 'created_at': now, 'look': 'appearance/realism_look.py',
                     'render_outputs': rel(renders), 'physics': 'accepted native caches (scene_manifest.json native_delivery), replayed unchanged',
                     'inputs': [{'role': 'native_input_locations', 'path': 'inputs/native_input_locations.json'}]}})
    (out / 'README.txt').write_text('\n'.join([
        f'PCVE suite: {SCENE}', f'Source: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(CASES) - 1}).',
        'Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, '
        'ground_truth_transforms.json (tools/export_ground_truth.py).',
        'Index: suite_manifest.json. Scene code: scripts/rigid_elastic/book_pillow_bedroom.', '']), encoding='utf-8')
    if a.update_pointer:
        scene = manifest()
        scene['canonical_suites'][SUITE] = {'target': rel(out), 'look': 'daylight bedroom',
                                            'case_video_sha256': {c: records[c]['video_sha256'] for c in CASES},
                                            'render_root': rel(renders)}
        write(CASE / 'scene_manifest.json', scene)
    print(json.dumps({c: {'video_sha256': records[c]['video_sha256'], 'stability': row_stab}
                      for c, row_stab in ((c, rows[c]['stable']) for c in CASES)}, indent=2))


if __name__ == '__main__':
    main()
