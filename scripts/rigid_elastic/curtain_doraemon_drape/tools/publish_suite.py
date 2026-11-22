"""Assemble a suite from finalized native case folders in the current PCVE suite format.

    python3 scripts/rigid_elastic/curtain_doraemon_drape/tools/publish_suite.py --delivery DIR \
        --camera RENDER/scene_manifest.json --suite NEW_DIR [--previous SUITE]

<delivery>/cases/<native case>/ holds one finalized case per builder case: tools/finalize_remote.py output
packaged by `build_pcve_curtain_doraemon_drape.py --stage package` (tools/standardize_case.py), i.e. video.mp4,
cache.npz, simulation_config.json, geometry/<body>_native.npz and the JSON sidecars. The timed case
(friction_x0_1_at_frame_8) is its continuation run (physics/simulate.py --source-cache) rendered and finalized the
same way; its native solver files are also copied to inputs/native_timed/<case>/. --camera is a render
scene_manifest.json that records the fixed camera (tools/export_ground_truth.py).

Per case the suite gets video.mp4, native_metadata/ (the case's small JSON sidecars), prompts.json (pcve_prompts/1,
from PCVE_SOURCE / PCVE_EDITS of the builder), provenance.json (pcve_provenance/1), video_validation.json
(pcve_video_validation/1) and ground_truth_transforms.json (pcve_ground_truth/1); the suite gets suite_manifest.json
(pcve_suite/1), README.txt and inputs/native_input_locations.json. The standardization records of
each case's provenance.json in the previous suite (--previous, default: the published suite) are carried over. Ground
truth that is not pcve_ground_truth/1 is refused.

The tool only builds a new folder: an existing suite is never overwritten, moved or modified. Check the new folder
(scripts/pcve_media_contract, `--export-prompts --dry-run --out-root NEW`, the ground-truth overlays) before swapping it
with the published suite by hand. Prompts of a published suite are updated with
`build_pcve_curtain_doraemon_drape.py --export-prompts`.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENE_DIR = HERE.parent
SCRIPTS = SCENE_DIR.parents[1]
REPO = SCRIPTS.parent
sys.path[:0] = [str(HERE), str(SCRIPTS)]
from export_ground_truth import ground_truth, save  # noqa: E402
from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog  # noqa: E402
from pcve_media_contract import require_video  # noqa: E402
from pcve_case_metadata import carried_provenance  # noqa: E402

SCENE = 'curtain_doraemon_drape'
BUILDER = SCENE_DIR / f'build_pcve_{SCENE}.py'
SUITE = REPO / f'renders/pcve_suites/pcve_{SCENE}_suite'
LAYOUT = 'cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json,ground_truth_transforms.json}'
METADATA = ('simulation_config.json', 'completion.json', 'state_handoff.json', 'physics_audit.json', 'render_manifest.json',
            'render_completion.json', 'encoding_verification.json', 'camera_calibration.json', 'gt.json',
            'deformation_manifest.json', 'canonical_coordinate_audit.json', 'asset_credits.json', 'scenario_overrides.json',
            'edit.json', 'source_scene_readability.json', 'artifact_manifest.json')
# Native solver files of a timed case published with the suite (its merged cache is the input of video and GT).
TIMED_INPUTS = ('cache.npz', 'continuation.npz', 'simulation_config.json', 'completion.json', 'state_handoff.json',
                'telemetry.npz')
GROUND_TRUTH_FORMAT = 'pcve_ground_truth/1'

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def relative(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def prompt_record(record, fps):
    """The pcve_prompts/1 file that `--export-prompts` keeps unchanged for this catalog record."""
    item = {'schema_version': 1, 'format_version': FORMAT_VERSION, 'scene': SCENE, 'case_id': record['catalog_case_id'],
            'kind': record['kind'], 'source_case_id': 'source', 'availability': 'available',
            'prompts': record['prompts'], 'edit_dsl': None, 'object_id': None, 'applies_from_frame': None,
            'application_time_sec': None, 'physics_override': {}, 'physics_diff': {},
            'prompt_provenance': {'origin': 'generated:' + relative(BUILDER), 'text_modified': False}}
    if record['kind'] == 'edit':
        frame = _applies_from_frame(record)
        item.update(edit_dsl=record['edit_dsl'], applies_from_frame=frame, application_time_sec=(frame - 1) / fps,
                    physics_override=record['physics_override'], physics_diff=record['physics_diff'])
    return item


def video_validation(video, case):
    contract = require_video(video)
    probe = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                            'stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration',
                            '-of', 'json', str(video)], capture_output=True, text=True, check=True,
                           stdin=subprocess.DEVNULL)
    probe = json.loads(probe.stdout)
    stream = probe['streams'][0]
    decode = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(video), '-f', 'null', '-'], capture_output=True, text=True)
    frames = int(stream['nb_read_frames'])
    return {'schema_version': 1, 'format_version': 'pcve_video_validation/1', 'scene': SCENE, 'case_id': case,
            'video': 'video.mp4', 'resolution': [int(stream['width']), int(stream['height'])], 'fps': stream['r_frame_rate'],
            'duration_sec': float(probe['format']['duration']), 'frames': frames, 'sha256': sha(video),
            'technical_probe_verified': frames == 96 and stream['r_frame_rate'] == '24/1',
            'full_decode_verified': decode.returncode == 0 and not decode.stderr.strip(),
            'content_unchanged': False, 'visual_or_physics_acceptance': 'new render; visual review pending',
            'native_validation': {'contract_probe': contract, 'probe': probe}}


def build(delivery, suite, camera, previous=None):
    if suite.exists():
        raise RuntimeError(f'{suite} exists; choose a new suite folder')
    catalog = load_catalog(BUILDER)
    records = [catalog['source'], *catalog['edits'].values()]
    fps = _fps()
    now = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    entries = []
    for record in records:
        native, case = record['case_id'], record['catalog_case_id']
        source_dir = delivery / 'cases' / native
        folder = suite / 'cases' / case
        (folder / 'native_metadata').mkdir(parents=True)
        shutil.copy2(source_dir / 'video.mp4', folder / 'video.mp4')
        for name in METADATA:
            if (source_dir / name).is_file():
                shutil.copy2(source_dir / name, folder / 'native_metadata' / name)
        digest = sha(folder / 'video.mp4')
        if digest != sha(source_dir / 'video.mp4'):
            raise RuntimeError(f'{case}: copy differs')
        check = video_validation(folder / 'video.mp4', case)
        if not (check['technical_probe_verified'] and check['full_decode_verified']):
            raise RuntimeError(f'{case}: video fails the media contract')
        save(folder / 'video_validation.json', check)
        prompts = prompt_record(record, fps)
        save(folder / 'prompts.json', prompts)
        truth = ground_truth(source_dir, camera)
        if truth.get('format_version') != GROUND_TRUTH_FORMAT:
            raise RuntimeError(f'{case}: ground truth is not {GROUND_TRUTH_FORMAT}')
        save(folder / 'ground_truth_transforms.json', truth)
        config = read(source_dir / 'simulation_config.json')
        provenance = {
            'schema_version': 1, 'format_version': 'pcve_provenance/1', 'scene': SCENE, 'case_id': case,
            'kind': record['kind'], 'native_case_id': native, 'video_sha256': digest, 'created_at': now,
            'native_case_dir': relative(source_dir), 'native_metadata': f'cases/{case}/native_metadata',
            'native_cache_sha256': sha(source_dir / 'cache.npz'), 'scene_code': relative(SCENE_DIR),
            'ground_truth': {'file': f'cases/{case}/ground_truth_transforms.json', 'camera': relative(camera),
                             'generator': relative(HERE / 'export_ground_truth.py')}}
        status = 'rendered_pending_review'
        if config.get('timed_continuation'):
            inputs = suite / 'inputs' / 'native_timed' / native
            inputs.mkdir(parents=True)
            for name in TIMED_INPUTS:
                if (source_dir / name).is_file():
                    shutil.copy2(source_dir / name, inputs / name)
            shutil.copytree(source_dir / 'geometry', inputs / 'geometry')
            handoff = read(source_dir / 'state_handoff.json')
            if not handoff.get('verified'):
                raise RuntimeError(f'{case}: the timed continuation has no verified state handoff')
            status = 'native_timed_physics_verified_and_rendered'
            provenance.update(status=status, native_timed_inputs=f'inputs/native_timed/{native}',
                              timed_continuation=config['timed_continuation'], state_handoff=handoff)
        old = previous / 'cases' / case / 'provenance.json' if previous is not None else None
        if old is not None and old.is_file():
            carried = carried_provenance(old)
            if carried:
                provenance.update(carried, carried_from=relative(old))
        save(folder / 'provenance.json', provenance)
        entries.append({
            'case_id': case, 'native_case_id': native, 'kind': record['kind'], 'source_case_id': 'source',
            'case_dir': f'cases/{case}', 'status': status, 'availability': 'video_present',
            'video': f'cases/{case}/video.mp4', 'video_sha256': digest,
            'media': {k: check[k] for k in ('resolution', 'fps', 'duration_sec', 'frames', 'sha256')},
            **{k: prompts[k] for k in ('prompts', 'edit_dsl', 'object_id', 'applies_from_frame', 'application_time_sec',
                                       'physics_override', 'physics_diff')}})
    save(suite / 'inputs' / 'native_input_locations.json', {
        'scene': SCENE, 'kind': 'native_input_locations', 'native_delivery': relative(delivery),
        'native_case_directories': {e['native_case_id']: relative(delivery / 'cases' / e['native_case_id']) for e in entries},
        'camera_record': relative(camera), 'scene_code': relative(SCENE_DIR),
        'metadata_policy': 'Small case sidecars are copied to cases/<case>/native_metadata; native caches, masks, MDD and '
                           'packed scenes stay in the native delivery, except the solver files of timed cases '
                           '(inputs/native_timed/<case>/).'})
    (suite / 'README.txt').write_text(
        f'PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(entries) - 1}).\n'
        'Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, '
        'ground_truth_transforms.json.\nIndex: suite_manifest.json. Scene code: scripts/rigid_elastic/curtain_doraemon_drape.\n',
        encoding='utf-8')
    save(suite / 'suite_manifest.json', {
        'schema_version': 5, 'format_version': 'pcve_suite/1', 'layout': LAYOUT, 'scene': SCENE, 'title': SCENE,
        'suite_name': suite.name, 'interaction_category': 'rigid_elastic', 'suite_path': relative(suite),
        'source_count': 1, 'edit_count': len(entries) - 1, 'status': 'rendered_pending_review',
        'source': entries[0], 'edits': entries[1:],
        'metadata': {'scene_id': SCENE, 'created_at': now, 'storage_type': 'physical_files',
                     'native_delivery': relative(delivery),
                     'inputs': [{'role': 'native_input_locations', 'path': 'inputs/native_input_locations.json'}]}})
    return {'suite': str(suite), 'cases': {e['case_id']: e['video_sha256'] for e in entries}}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--delivery', type=Path, required=True, help='finalized native case folders <delivery>/cases/<native case>/')
    p.add_argument('--camera', type=Path, required=True, help='render scene_manifest.json with the fixed camera')
    p.add_argument('--suite', type=Path, required=True, help='new suite folder (must not exist)')
    p.add_argument('--previous', type=Path, default=SUITE,
                   help='suite whose provenance standardization records are carried over (default: the published suite)')
    args = p.parse_args()
    previous = args.previous.resolve() if args.previous.is_dir() else None
    print(json.dumps(build(args.delivery.resolve(), args.suite.resolve(), args.camera.resolve(), previous),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
