"""Encode rendered cases and publish them as a suite in the current PCVE suite format.

    python3 .../tools/publish_suite.py encode <case render dir>
    python3 .../tools/publish_suite.py build --native renders/rubber_band_wood_slider/<rev> --revision <rev> \
        [--suite DIR] [--archive-as pcve_rubber_band_wood_slider_suite_before_<rev>]

encode   writes video.mp4 (libx264 CRF 16, yuv420p, 24 fps, 96 frames) and encoding_receipt.json from 0001.png...0096.png.
build    writes the suite in a staging folder beside it (.<suite>.staging): cases/<case>/{video.mp4, prompts.json
         (pcve_prompts/1, from the builder catalog), provenance.json (pcve_provenance/1), video_validation.json
         (pcve_video_validation/1), native_metadata/, ground_truth_transforms.json (tools/export_ground_truth.py,
         pcve_ground_truth/1)}, suite_manifest.json (pcve_suite/1), inputs/, native_manifests/, README.txt.
         Once the staging folder is checked (every JSON readable, every case's ground truth
         pcve_ground_truth/1), an existing suite moves (never deleted) to archive/pcve_suites/<archive-as>, the
         staging folder takes its place, and the scene_manifest.json pointer is set with every case video sha256.
Prompts of a published suite are updated with `build_pcve_rubber_band_wood_slider.py --export-prompts`.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR / 'tools'), str(CASE_DIR), str(CASE_DIR.parents[1])]
from scene_paths import (CATALOG, REPO, SCENE, SCENE_MANIFEST, SUITE, SUITE_KEY, ffmpeg_binary,  # noqa: E402
                         sha256, state_sha256)

BUILDER = CASE_DIR / f'build_pcve_{SCENE}.py'
ORDER = ['source', 'add_stop', 'delete_band', 'friction_x2', 'mass_x3', 'young_x0p5']
METADATA = ('render_provenance.json', 'realism_provenance.json', 'scene_snapshot.json', 'encoding_receipt.json')
LAYOUT = 'cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}'


def write(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path = Path(path)
    if not path.is_file() or path.read_text(encoding='utf-8') != text:
        tmp = path.with_name('.' + path.name + '.writing')
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(path)


def encode(folder):
    folder = Path(folder).resolve()
    frames = [folder / f'{i:04d}.png' for i in range(1, 97)]
    missing = [f.name for f in frames if not f.is_file()]
    if missing:
        raise SystemExit(f'{folder}: missing frames {missing[:5]}')
    prov = json.loads((folder / 'render_provenance.json').read_text())
    ff = ffmpeg_binary()
    subprocess.run([str(ff), '-hide_banner', '-loglevel', 'error', '-y', '-framerate', '24', '-start_number', '1',
                    '-i', str(folder / '%04d.png'), '-frames:v', '96', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(folder / 'video.mp4')], check=True)
    receipt = {'video_sha256': sha256(folder / 'video.mp4'), 'encoder': 'ffmpeg libx264 CRF 16 preset slow, yuv420p',
               'ffmpeg_binary_sha256': sha256(ff), 'frames': 96, 'fps': 24, 'first_frame_time_s': 0.0,
               'frame_times': 'frame i (1-based) shows t = (i - 1) / 24 s', 'case': prov['case'],
               'input_state_sha256': prov['simulation_cache_sha256'],
               'frame_sha256': {f.name: sha256(f) for f in frames}}
    write(folder / 'encoding_receipt.json', receipt)
    print(json.dumps({k: receipt[k] for k in ('case', 'video_sha256')}))
    return receipt


def validate(video):
    probe = json.loads(subprocess.run(
        ['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
         'stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration',
         '-of', 'json', str(video)], check=True, capture_output=True, text=True).stdout)
    decode = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-f', 'null', '-'], capture_output=True, text=True)
    s = probe['streams'][0]
    clean = decode.returncode == 0 and not decode.stderr.strip()
    ok = (s['width'], s['height'], s['r_frame_rate'], s['nb_read_frames']) == (1280, 720, '24/1', '96') \
        and abs(float(probe['format']['duration']) - 4.0) < 1e-6 and clean
    return {'technical_decode_verified': clean, 'pcve_spec_compliant': ok, 'resolution': [s['width'], s['height']],
            'fps': s['r_frame_rate'], 'duration_sec': float(probe['format']['duration']), 'frames': int(s['nb_read_frames']),
            'full_decode': decode.returncode == 0, 'sha256': sha256(video), 'probe': probe}


def rel(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def prompt_record(record, fps):
    """The pcve_prompts/1 file that `--export-prompts` keeps unchanged for this catalog record."""
    from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame
    item = {'schema_version': 1, 'format_version': FORMAT_VERSION, 'scene': SCENE, 'case_id': record['catalog_case_id'],
            'kind': record['kind'], 'source_case_id': 'source', 'availability': 'available', 'prompts': record['prompts'],
            'edit_dsl': None, 'object_id': None, 'applies_from_frame': None, 'application_time_sec': None,
            'physics_override': {}, 'physics_diff': {},
            'prompt_provenance': {'origin': 'generated:' + rel(BUILDER), 'text_modified': False}}
    if record['kind'] == 'edit':
        frame = _applies_from_frame(record)
        item.update(edit_dsl=record['edit_dsl'], applies_from_frame=frame, application_time_sec=(frame - 1) / fps,
                    physics_override=record['physics_override'], physics_diff=record['physics_diff'])
    return item


def build(native, revision, suite, archive_as):
    from pcve_edit_catalog import _fps, load_catalog
    from pcve_ground_truth import check_suite, write as write_ground_truth
    import export_ground_truth as gt
    native, suite = Path(native).resolve(), Path(suite).resolve()
    for case in ORDER:
        prov = json.loads((native / case / 'render_provenance.json').read_text())
        receipt = json.loads((native / case / 'encoding_receipt.json').read_text())
        if prov['simulation_cache_sha256'] != state_sha256(case):
            raise SystemExit(f'{case}: render is not tied to the accepted native states')
        if receipt['video_sha256'] != sha256(native / case / 'video.mp4'):
            raise SystemExit(f'{case}: video differs from its encoding receipt')
        if sorted(receipt['frame_sha256']) != [f'{i:04d}.png' for i in range(1, 97)]:
            raise SystemExit(f'{case}: incomplete frame list')
    archive = None
    if suite.exists():
        if not archive_as:
            raise SystemExit('The suite exists; pass --archive-as to move it into archive/pcve_suites/')
        archive = REPO / 'archive/pcve_suites' / archive_as
        if archive.exists():
            raise SystemExit(f'{archive} exists')
    published = suite
    suite = suite.with_name('.' + suite.name + '.staging')
    if suite.exists():
        raise SystemExit(f'{suite} exists (an earlier build stopped); move it away first')
    (suite / 'cases').mkdir(parents=True)
    catalog = load_catalog(BUILDER)
    declared = {'source': catalog['source'], **catalog['edits']}
    fps = _fps()
    now = datetime.now(timezone.utc).astimezone().isoformat()
    records = []
    for case in ORDER:
        catalog_id = CATALOG[case]
        folder = suite / 'cases' / catalog_id
        (folder / 'native_metadata').mkdir(parents=True)
        shutil.copy2(native / case / 'video.mp4', folder / 'video.mp4')
        meta = []
        for name in METADATA:
            if (native / case / name).is_file():
                shutil.copy2(native / case / name, folder / 'native_metadata' / name)
                meta.append({'source': rel(native / case / name), 'relative': f'native_metadata/{name}'})
        check = validate(folder / 'video.mp4')
        if not check['pcve_spec_compliant']:
            raise SystemExit(f'{case}: video is not 1280x720 / 24 fps / 96 frames / 4 s or does not decode')
        write(folder / 'video_validation.json', {
            'schema_version': 1, 'format_version': 'pcve_video_validation/1', 'scene': SCENE, 'case_id': catalog_id,
            'video': 'video.mp4', 'resolution': check['resolution'], 'fps': check['fps'],
            'duration_sec': check['duration_sec'], 'frames': check['frames'], 'sha256': check['sha256'],
            'technical_probe_verified': check['pcve_spec_compliant'], 'full_decode_verified': check['technical_decode_verified'],
            'content_unchanged': False, 'visual_or_physics_acceptance': 'new render; visual review pending',
            'native_validation': {'probe': check['probe']}})
        prompts = prompt_record(declared[case], fps)
        write(folder / 'prompts.json', prompts)
        write(folder / 'provenance.json', {
            'schema_version': 1, 'format_version': 'pcve_provenance/1', 'scene': SCENE, 'case_id': catalog_id,
            'kind': prompts['kind'], 'native_case_id': case, 'video_sha256': check['sha256'], 'created_at': now,
            'look_revision': revision, 'native_render_dir': rel(native / case), 'native_case_metadata': meta,
            'native_states': f'assets/scenes/{SCENE}/native/accepted_increment.zip#cases/{case}/simulation.npz',
            'native_states_sha256': state_sha256(case)})
        prov = json.loads((folder / 'native_metadata/render_provenance.json').read_text())
        write_ground_truth(folder / 'ground_truth_transforms.json', gt.convert(case, gt.build(case, prov)))
        records.append({'case_id': catalog_id, 'native_case_id': case, 'kind': prompts['kind'], 'source_case_id': 'source',
                        'case_dir': f'cases/{catalog_id}', 'status': 'video_verified', 'availability': 'video_present',
                        'video': f'cases/{catalog_id}/video.mp4', 'video_sha256': check['sha256'],
                        'media': {k: check[k] for k in ('resolution', 'fps', 'duration_sec', 'frames', 'sha256')},
                        **{k: prompts[k] for k in ('prompts', 'edit_dsl', 'object_id', 'applies_from_frame',
                                                   'application_time_sec', 'physics_override', 'physics_diff')}})
    (suite / 'inputs').mkdir()
    write(suite / 'inputs/native_input_locations.json', {
        'scene': SCENE, 'kind': 'native_input_locations',
        'native_states': f'assets/scenes/{SCENE}/native/accepted_increment.zip (cases/<case>/simulation.npz)',
        'native_render_folders': [rel(native / c) for c in ORDER], 'scene_code': rel(CASE_DIR),
        'metadata_policy': 'Case-local evidence is in cases/<case>/native_metadata; the 96 PNG frames, ID masks and '
                           'per-frame provenance of every case stay in the native render folder.'})
    (suite / 'native_manifests').mkdir()
    shutil.copy2(CASE_DIR / 'entrypoints.json', suite / 'native_manifests/scene_entrypoints.json')
    (suite / 'README.txt').write_text(
        f'PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(records) - 1}).\n'
        'Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, '
        'ground_truth_transforms.json.\nIndex: suite_manifest.json. Scene code: scripts/rigid_elastic/rubber_band_wood_slider.\n',
        encoding='utf-8')
    write(suite / 'suite_manifest.json', {
        'schema_version': 5, 'format_version': 'pcve_suite/1', 'layout': LAYOUT, 'scene': SCENE, 'title': SCENE,
        'suite_name': SUITE_KEY, 'interaction_category': 'rigid_elastic', 'suite_path': rel(published), 'source_count': 1,
        'edit_count': len(records) - 1, 'status': 'video_verified', 'source': records[0], 'edits': records[1:],
        'metadata': {'scene_id': SCENE, 'created_at': now, 'look_revision': revision, 'storage_type': 'physical_files',
                     'render_outputs': rel(native),
                     'inputs': [{'role': 'native_input_locations', 'path': 'inputs/native_input_locations.json'}],
                     'native_manifests': [{'path': 'native_manifests/scene_entrypoints.json'}]}})
    for p in suite.rglob('*.json'):
        json.loads(p.read_text(encoding='utf-8'))
    check_suite(suite)
    if archive is not None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(published), str(archive))
        print(json.dumps({'archived_previous_suite': str(archive)}))
    os.rename(suite, published)
    suite = published
    scene = json.loads(SCENE_MANIFEST.read_text(encoding='utf-8'))
    scene['canonical_suites'] = {SUITE_KEY: {
        'target': rel(suite),
        'case_video_sha256': {r['native_case_id']: r['video_sha256'] for r in records},
        'case_video_path': {r['native_case_id']: r['video'] for r in records}}}
    write(SCENE_MANIFEST, scene)
    print(json.dumps({'suite': str(suite), 'cases': [r['case_id'] for r in records]}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    e = sub.add_parser('encode')
    e.add_argument('folder', type=Path)
    b = sub.add_parser('build')
    b.add_argument('--native', type=Path, required=True, help='folder with one rendered sub-folder per native case')
    b.add_argument('--revision', required=True)
    b.add_argument('--suite', type=Path, default=SUITE)
    b.add_argument('--archive-as')
    a = ap.parse_args()
    if a.command == 'encode':
        encode(a.folder)
    else:
        build(a.native, a.revision, a.suite, a.archive_as)


if __name__ == '__main__':
    main()
