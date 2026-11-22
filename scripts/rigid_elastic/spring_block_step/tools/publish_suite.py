"""Build and maintain a suite of spring_block_step in the current PCVE suite format.

    publish_suite.py encode        [--cases ...]   video.mp4 from the 96 PNG frames of each render output
    publish_suite.py build         --suite DIR     new suite from the native outputs: per case video.mp4,
                                                   prompts.json (pcve_prompts/1), provenance.json (pcve_provenance/1),
                                                   video_validation.json (pcve_video_validation/1), native_metadata/,
                                                   ground_truth_transforms.json; suite_manifest.json (pcve_suite/1),
                                                   inputs/, native_manifests/, README.txt
    publish_suite.py prompts       [--suite DIR]   bilingual prompts from the builder catalog (pcve_edit_catalog export)
    publish_suite.py ground-truth  --suite DIR [--blender BIN] [--cases ...]
                                                   cases/<case>/ground_truth_transforms.json from the native states
                                                   and the camera of the case's scene.blend (or the render record)

Native locations (states, solver audits, render outputs) come from
scene_manifest.json -> native_outputs.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, os, shutil, socket, subprocess, sys

HERE = Path(__file__).resolve().parent
SCENE_DIR = HERE.parent
SCRIPTS = SCENE_DIR.parents[1]
REPO = SCRIPTS.parent
sys.path[:0] = [str(SCENE_DIR), str(SCRIPTS)]
BUILDER = SCENE_DIR / 'build_pcve_spring_block_step.py'
SUITE_KEY = 'pcve_spring_block_step_suite'
CASE_ORDER = ('source', 'mass_half', 'young_quarter', 'friction_half', 'remove_spring', 'add_block')
LAYOUT = 'cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}'


def blender_runtime():
    pinned = REPO / 'tools/blender-4.3.2-linux-x64/blender'
    if pinned.is_file():
        return pinned
    from pcve_assets import blender
    return blender()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.writing')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scene_manifest():
    return read(SCENE_DIR / 'scene_manifest.json')


def default_suite():
    return REPO / scene_manifest()['canonical_suites'][SUITE_KEY]['target']


def repo_path(value):
    value = Path(value)
    return value if value.is_absolute() else REPO / value


def native():
    n = scene_manifest()['native_outputs']
    return {'states': repo_path(n['state_root']), 'audits': repo_path(n['audit_root']),
            'renders': repo_path(n['render_root']), 'case_dir': n.get('render_case_dir', '{case}'),
            'record': n.get('render_record', 'render_report.json'), 'camera': n.get('camera')}


def render_dir(case):
    n = native()
    return n['renders'] / n['case_dir'].format(case=case)


def catalog_ids():
    from pcve_edit_catalog import load_catalog
    catalog = load_catalog(BUILDER)
    ids = {'source': 'source'}
    ids.update({case: catalog['edits'][case]['catalog_case_id'] for case in CASE_ORDER[1:]})
    return catalog, ids


def prompts(suite):
    """Shared catalog export (pcve_edit_catalog.export_prompts) into the suite's pcve_prompts/1 files."""
    from pcve_edit_catalog import export_prompts
    result = export_prompts(BUILDER, suite)
    print(json.dumps({'prompts': [row['case_id'] for row in result['exported']],
                      'updated': [row['case_id'] for row in result['exported'] if row['status'] == 'updated']}))


def ground_truth(suite, blender, cases=None):
    """cases/<case>/ground_truth_transforms.json of a suite from the native states and the camera of each
    case's scene.blend (or the camera record of scene_manifest.json)."""
    n = native()
    _, ids = catalog_ids()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    for case, catalog_id in ids.items():
        if cases and case not in cases and catalog_id not in cases:
            continue
        out = suite / 'cases' / catalog_id / 'ground_truth_transforms.json'
        blend = render_dir(case) / 'scene.blend'
        command = [str(blender), '-b']
        if blend.is_file():
            command.append(str(blend))
        command += ['--factory-startup', '--disable-autoexec', '--python-exit-code', '1',
                    '--python', str(HERE / 'export_ground_truth.py'), '--',
                    '--case', case, '--case-id', catalog_id, '--native', str(n['states'] / case), '--out', str(out)]
        if not blend.is_file():
            cam = n['camera']
            if not cam:
                raise SystemExit(f'{case}: no scene.blend in {render_dir(case)} and no camera record in scene_manifest.json')
            command += ['--camera-location', *map(str, cam['location']), '--camera-target', *map(str, cam['target']),
                        '--lens', str(cam['lens_mm']), '--sensor-width', str(cam['sensor_width_mm'])]
        subprocess.run(command, check=True, env=env, stdout=subprocess.DEVNULL)
        gt = read(out)
        if len(gt['frames']) != 96 or gt['frame_end'] != 96 or gt['fps'] != 24:
            raise SystemExit(f'{case}: ground truth does not cover the 96-frame video')
        print('GROUND_TRUTH', case, sha(out))


def ffmpeg():
    return os.environ.get('PCVE_FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg'


def encode(cases=None):
    """H.264 yuv420p, CRF 16, 24 FPS, BT.709 tags, from frames/0001.png..0096.png of each render output."""
    for case in CASE_ORDER:
        if cases and case not in cases:
            continue
        out = render_dir(case)
        frames = sorted((out / 'frames').glob('*.png'))
        if [f.name for f in frames] != [f'{i:04d}.png' for i in range(1, 97)]:
            raise SystemExit(f'{case}: {len(frames)} frames, expected 0001..0096.png')
        subprocess.run([ffmpeg(), '-y', '-v', 'error', '-framerate', '24', '-start_number', '1', '-i', str(out / 'frames/%04d.png'),
                        '-frames:v', '96', '-c:v', 'libx264', '-crf', '16', '-preset', 'slow', '-pix_fmt', 'yuv420p',
                        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv',
                        '-movflags', '+faststart', str(out / 'video.mp4')], check=True)
        report = read(out / 'render_report.json')
        report.update(status='complete', encoded_on=socket.gethostname().split('.')[0], video_sha256=sha(out / 'video.mp4'))
        write(out / 'render_report.json', report)
        print('ENCODED', case, report['video_sha256'])


def validate(video, case_id):
    """pcve_video_validation/1 record: full decode with ffprobe plus the shared media contract."""
    from pcve_media_contract import require_video
    media = require_video(video)
    probe = json.loads(subprocess.run([shutil.which('ffprobe') or 'ffprobe', '-v', 'error', '-count_frames', '-show_entries',
                                       'stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration',
                                       '-of', 'json', str(video)], check=True, capture_output=True, text=True).stdout)
    stream = probe['streams'][0]
    if (stream['width'], stream['height'], stream['r_frame_rate'], stream['nb_read_frames']) != (1280, 720, '24/1', '96'):
        raise SystemExit(f'{video}: {stream}')
    decode = subprocess.run([ffmpeg(), '-v', 'error', '-i', str(video), '-f', 'null', '-'], capture_output=True, text=True)
    return {'schema_version': 1, 'format_version': 'pcve_video_validation/1', 'scene': 'spring_block_step',
            'case_id': case_id, 'video': 'video.mp4', 'resolution': [1280, 720], 'fps': '24/1',
            'duration_sec': media['duration_s'], 'frames': 96, 'sha256': sha(video), 'technical_probe_verified': True,
            'full_decode_verified': decode.returncode == 0 and not decode.stderr.strip(), 'content_unchanged': False,
            'visual_or_physics_acceptance': 'replays the accepted native states; visual review pending',
            'native_validation': {'contract_probe': media, 'probe': {'streams': probe['streams'], 'format': probe['format']}}}


def prompt_record(record, fps):
    """The pcve_prompts/1 file that `--export-prompts` keeps unchanged for this catalog record."""
    from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame
    item = {'schema_version': 1, 'format_version': FORMAT_VERSION, 'scene': 'spring_block_step',
            'case_id': record['catalog_case_id'], 'kind': record['kind'], 'source_case_id': 'source',
            'availability': 'available', 'prompts': record['prompts'], 'edit_dsl': None, 'object_id': None,
            'applies_from_frame': None, 'application_time_sec': None, 'physics_override': {}, 'physics_diff': {},
            'prompt_provenance': {'origin': 'generated:' + rel(BUILDER), 'text_modified': False}}
    if record['kind'] == 'edit':
        frame = _applies_from_frame(record)
        item.update(edit_dsl=record['edit_dsl'], applies_from_frame=frame, application_time_sec=(frame - 1) / fps,
                    physics_override=record['physics_override'], physics_diff=record['physics_diff'])
    return item


def rel(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def build(suite, blender):
    """A new suite at `suite` (which must not exist) from the native outputs named in scene_manifest.json."""
    from pcve_edit_catalog import _fps
    if suite.exists():
        raise SystemExit(f'{suite} exists; move the published suite to archive/ first')
    sm = scene_manifest()
    n = native()
    catalog, ids = catalog_ids()
    declared = {'source': catalog['source'], **catalog['edits']}
    fps = _fps()
    now = datetime.datetime.now().astimezone().isoformat()
    rows = []
    for case, cid in ids.items():
        cdir = suite / 'cases' / cid
        (cdir / 'native_metadata').mkdir(parents=True)
        rdir = render_dir(case)
        video = cdir / 'video.mp4'
        shutil.copy2(rdir / 'video.mp4', video)
        val = validate(video, cid)
        write(cdir / 'video_validation.json', val)
        if val['sha256'] != sm['canonical_suites'][SUITE_KEY]['case_video_sha256'][case]:
            raise SystemExit(f'{case}: video differs from scene_manifest.json')
        metadata = []
        for folder, names in ((rdir, (n['record'],)),
                              (n['states'] / case, ('resolved_physics.json', 'scenario_overrides.json')),
                              (n['audits'] / case, ('physics_audit.json',))):
            for name in names:
                if not (folder / name).is_file():
                    continue
                shutil.copy2(folder / name, cdir / 'native_metadata' / name)
                metadata.append({'source': rel(folder / name), 'relative': f'native_metadata/{name}',
                                 'sha256': sha(folder / name), 'bytes': (folder / name).stat().st_size})
        shutil.copy2(n['states'] / case / 'scenario_overrides.json', cdir / 'scenario_overrides.json')
        render = read(rdir / n['record'])
        prompts_record = prompt_record(declared[case], fps)
        write(cdir / 'prompts.json', prompts_record)
        write(cdir / 'provenance.json', {
            'schema_version': 1, 'format_version': 'pcve_provenance/1', 'scene': 'spring_block_step', 'case_id': cid,
            'kind': prompts_record['kind'], 'native_case_id': case, 'video_sha256': val['sha256'], 'created_at': now,
            'render_dir': rel(rdir), 'native_states': rel(n['states'] / case),
            'native_states_sha256': sha(n['states'] / case / 'states.npz'),
            'physics_audit': rel(n['audits'] / case / 'physics_audit.json'), 'native_case_metadata': metadata,
            'render': {k: render.get(k) for k in ('look', 'samples', 'device', 'host', 'motion_blur_shutter_frames', 'blender')},
            'native_acceptance': 'Native states are the accepted PyBullet solves (physics_audit.json, tools/validate_physics.py); '
                                 'the video replays them unchanged.'})
        rows.append({'case_id': cid, 'native_case_id': case, 'kind': prompts_record['kind'], 'source_case_id': 'source',
                     'case_dir': f'cases/{cid}', 'status': 'rendered_and_verified', 'availability': 'video_present',
                     'video': f'cases/{cid}/video.mp4', 'video_sha256': val['sha256'],
                     'media': {k: val[k] for k in ('resolution', 'fps', 'duration_sec', 'frames', 'sha256')},
                     **{k: prompts_record[k] for k in ('prompts', 'edit_dsl', 'object_id', 'applies_from_frame',
                                                       'application_time_sec', 'physics_override', 'physics_diff')}})
    for name in ('inputs', 'native_manifests'):
        (suite / name).mkdir()
    write(suite / 'inputs/native_input_locations.json', {
        'scene': 'spring_block_step', 'kind': 'native_input_locations',
        'native_state_root': rel(n['states']), 'physics_audit_root': rel(n['audits']), 'native_render_root': rel(n['renders']),
        'scene_code': rel(SCENE_DIR),
        'metadata_policy': 'Per-case render record, resolved physics, scenario overrides and solver audit are copied into cases/<case>/native_metadata; states, frames and scene.blend files stay at the native locations.'})
    snapshots = []
    for name, target in (('entrypoints.json', 'scene_entrypoints.json'), ('scene_manifest.json', 'scene_scene_manifest.json')):
        shutil.copy2(SCENE_DIR / name, suite / 'native_manifests' / target)
        snapshots.append({'path': f'native_manifests/{target}', 'sha256': sha(suite / 'native_manifests' / target)})
    (suite / 'README.txt').write_text(
        'PCVE suite: spring_block_step (a compressed spring launches a wooden block off a raised board onto a workbench)\n'
        f'Source: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(rows) - 1}).\n'
        'Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, ground_truth_transforms.json.\n'
        'Index: suite_manifest.json. Scene code: scripts/rigid_elastic/spring_block_step.\n', encoding='utf-8')
    write(suite / 'suite_manifest.json', {
        'schema_version': 5, 'format_version': 'pcve_suite/1', 'layout': LAYOUT, 'scene': 'spring_block_step',
        'title': 'spring_block_step', 'suite_name': SUITE_KEY, 'interaction_category': 'rigid_elastic',
        'suite_path': rel(suite), 'source_count': 1, 'edit_count': len(rows) - 1, 'status': 'rendered_and_verified',
        'source': rows[0], 'edits': rows[1:],
        'metadata': {'scene_id': 'spring_block_step', 'created_at': now, 'storage_type': 'physical_files',
                     'inputs': [{'role': 'native_input_locations', 'path': 'inputs/native_input_locations.json'}],
                     'native_manifests': snapshots}})
    ground_truth(suite, blender)
    print('BUILT', suite, [r['case_id'] for r in rows])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('encode', 'build', 'prompts', 'ground-truth'))
    parser.add_argument('--suite', type=Path)
    parser.add_argument('--blender', type=Path, default=blender_runtime())
    parser.add_argument('--cases', nargs='+')
    args = parser.parse_args()
    if args.command == 'ground-truth' and args.suite is None:
        parser.error('ground-truth writes into the suite given by --suite (a new suite; the published ground truth '
                     'is in the pcve_ground_truth/1 layout)')
    suite = (args.suite or REPO / 'renders' / SCENE_DIR.name / 'suite_build' / SUITE_KEY).resolve()
    scripts = SCRIPTS.resolve()
    if suite == scripts or scripts in suite.parents:
        parser.error('the suite lives under renders/, not scripts/')
    if args.command == 'encode':
        encode(args.cases)
    elif args.command == 'build':
        build(suite, args.blender)
    elif args.command == 'prompts':
        prompts(suite)
    else:
        ground_truth(suite, args.blender, args.cases)
