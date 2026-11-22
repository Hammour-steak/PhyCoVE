"""Build the source and five edited scene variants."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__, "build_pcve")
# PCVE_UNIFIED_ENTRY_END

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from pcve_scene_runtime import python_for, render_prefix, append_render_options
from input_hashes import input_hashes
from scene_config import defaults, merge, validate
from validate_office_desk_kettle_tip import validate_cache
from edit_vocab import VOCAB, EDIT_CASES
from pcve_project_paths import suite_output_root
import pcve_edit_dsl as dsl

SOURCE_CASE_ID = 'office_desk_kettle_tip_baseline'


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def run_logged(command, path, args):
    if args.verbose_render:
        subprocess.run(command, check=True)
    else:
        with path.open('w', encoding='utf-8') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def run_case(folder, scenario, args):
    validate(scenario)
    folder.mkdir(parents=True, exist_ok=True)
    signature = dict(scenario=scenario, inputs=input_hashes(),
                     engine=args.engine, device=args.device, preview_frame=args.preview_frame,
                     mode=args.mode, simulate_only=args.simulate_only)
    fp = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    status_path = folder / 'run_status.json'
    required = ['physics_transforms.json', 'simulation_metrics.json']
    if not args.simulate_only:
        required += ['preview.png', 'ground_truth_transforms.json', 'scenario_metadata.json',
                     'render_validation.json', 'office_desk_kettle_tip.blend']
        if args.mode == 'animation':
            required += ['video.mp4', 'office_desk_kettle_tip.mp4']
        elif args.mode == 'keyframes':
            required += ['keyframes.json']
    if args.skip_existing and status_path.exists():
        status = json.loads(status_path.read_text(encoding='utf-8'))
        if status.get('fingerprint') == fp and status.get('valid') and all((folder / name).exists() for name in required):
            return dict(status, status='skipped_existing')
    sim = [str(args.physics_python), str(Path(__file__).with_name('simulate_office_desk_kettle_tip.py')),
           '--out', str(folder / 'physics_transforms.json'), '--scenario-json', str(folder / 'scenario_input.json')]
    render = render_prefix(args, Path(__file__).with_name('render_office_desk_kettle_tip.py'))
    render += ['--physics-json', str(folder / 'physics_transforms.json'), '--out-dir', str(folder),
               '--engine', args.engine, '--device', args.device, '--samples', str(args.samples),
               '--resolution', *map(str, args.resolution), '--mode', args.mode]
    render = append_render_options(render, args)
    if args.dry_run:
        for command in ([] if args.render_only else [sim]) + ([] if args.simulate_only else [render]):
            print(subprocess.list2cmdline(command))
        return dict(status='dry_run', valid=False, quality=dict(valid=False))
    write_json(folder / 'scenario_input.json', scenario)
    if not args.render_only:
        run_logged(sim, folder / 'simulation.log', args)
    data = json.loads((folder / 'physics_transforms.json').read_text(encoding='utf-8'))
    validate_cache(data)
    if data['scenario']['physics'] != scenario['physics'] or any(
            data['scenario']['render'][key] != scenario['render'][key] for key in ('fps', 'slow_motion', 'duration_sec')):
        raise ValueError('Cached physics/timing differs; resimulate before --render-only')
    if not args.simulate_only:
        run_logged(render, folder / 'render.log', args)
    if not all((folder / name).exists() for name in required):
        raise RuntimeError('Incomplete case outputs')
    if not args.simulate_only and args.mode == 'keyframes':
        selected = json.loads((folder / 'keyframes.json').read_text(encoding='utf-8'))
        if not selected or not all((folder / f['file']).is_file() for f in selected): raise RuntimeError('Incomplete keyframe outputs')
    status = dict(status='completed', valid=True, fingerprint=fp, simulation_only=args.simulate_only,
                  render_mode=args.mode, quality=data['quality'])
    write_json(status_path, status)
    return status


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-root', type=Path, default=suite_output_root("office_desk_kettle_tip"))
    p.add_argument('--physics-python', type=Path, default=python_for('physics'))
    p.add_argument('--render-python', type=Path, default=python_for('render'))
    p.add_argument('--blender', type=Path)
    p.add_argument('--duration-sec', type=float, default=4.)
    p.add_argument('--fps', type=int, default=24)
    p.add_argument('--slow-motion', type=int, choices=(1, 2, 4, 8), default=1)
    p.add_argument('--samples', type=int, default=32)
    p.add_argument('--resolution', type=int, nargs=2, default=[960, 540])
    p.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    p.add_argument('--mode', choices=('preview', 'keyframes', 'animation'), default='keyframes')
    p.add_argument('--preview-frame', type=int)
    p.add_argument('--simulate-only', action='store_true')
    p.add_argument('--render-only', action='store_true')
    p.add_argument('--skip-existing', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--verbose-render', action='store_true')
    p.add_argument('--cases', nargs='+')
    return p


def outputs(folder):
    names = dict(video='video.mp4', physics='physics_transforms.json', ground_truth='ground_truth_transforms.json',
                 scenario_input='scenario_input.json', scenario_metadata='scenario_metadata.json', preview='preview.png',
                 scenario_overrides='scenario_overrides.json', prompts='prompts.json')
    return {key: str((folder / name).resolve()) for key, name in names.items() if (folder / name).exists()}


def main():
    args = parser().parse_args()
    args.out_root = args.out_root.resolve()
    if args.render_only and args.simulate_only:
        raise ValueError('Conflicting execution modes')
    cases = EDIT_CASES
    if args.cases:
        if set(args.cases) - {SOURCE_CASE_ID, *[name for name, _ in cases]}:
            raise ValueError('Unknown case')
        cases = [(name, instruction) for name, instruction in cases if name in args.cases]
    source = defaults()
    source['render'].update(fps=args.fps, duration_sec=args.duration_sec, slow_motion=args.slow_motion,
                            resolution=args.resolution, samples=args.samples)
    description = {
        'vague': {'zh': '办公室内，桌子上水壶因为重心不稳而倒下，碰倒了笔筒，里面的一支笔也被连带摔了出来。',
                  'en': 'In an office, a kettle on the desk loses its balance and topples, knocking over the pen cup and flinging the ballpoint pen inside out of it.'},
        'quantitative': {'zh': '水壶 0.90 kg，笔筒 0.080 kg，笔 0.012 kg；水壶以 16° 前倾（小于 18.6° 平衡角）加 5.35 rad/s 的绕底缘转动起步，随后完全靠重力原地翻倒，0.129 s 撞上笔筒外壁并把它掀翻 90°，笔在 0.34 s 被撬出筒外；壶与桌面摩擦 0.15，筒/桌面摩擦 0.90。',
                         'en': 'Kettle 0.90 kg, pen cup 0.080 kg, pen 0.012 kg; the kettle starts at a 16 degree lean (short of its 18.6 degree balance angle) with a 5.35 rad/s rotation about its base rim, then topples in place under gravity alone, striking the cup\'s outer wall at 0.129 s and tipping it 90 degrees while the pen is levered out at 0.34 s; kettle/desk friction 0.15, cup/desk friction 0.90.'}}
    manifest = dict(schema_version=3, suite_name='pcve_office_desk_kettle_tip_suite',
                    description='One source and four edits: kettle mass, pen-cup mass, pen deletion, and the pen cup vanishing 0.3 s into the clip.',
                    baseline_physics=source['physics'], total_frames=round(args.fps * args.duration_sec * args.slow_motion),
                    resolution=args.resolution, fps=args.fps, duration_sec=args.duration_sec * args.slow_motion,
                    samples=args.samples, physical_duration_sec=args.duration_sec,
                    playback_duration_sec=args.duration_sec * args.slow_motion,
                    sample_fps=args.fps * args.slow_motion, slow_motion=args.slow_motion, source=None, edits=[])
    path = args.out_root / 'suite_manifest.json'
    for case_id, instruction in [(SOURCE_CASE_ID, None), *cases]:
        folder = args.out_root / 'cases' / case_id
        scenario = source
        record = dict(case_id=case_id, kind='edit' if instruction else 'source', case_dir=str(folder), status='pending')
        if instruction:
            edit = dsl.parse(instruction, VOCAB)
            override = {'physics': dsl.to_scenario_override(edit, VOCAB)}
            scenario = merge(source, override)
            if isinstance(edit, dsl.SetEdit):
                diff = {f'{edit.property_name} ({edit.object_id})':
                        {'from': dsl.baseline_value_for(edit, VOCAB), 'to': dsl.resolved_to_value(edit, VOCAB)}}
            elif edit.at_frame is not None:
                # A delete that lands partway through is not the same statement
                # as one that never builds the body, so the diff carries the
                # frame the body leaves the world on.
                diff = {edit.object_id: {'from': 'present', 'to': 'removed',
                                         'removal_frame': edit.at_frame}}
            else:
                diff = {edit.object_id: {'from': 'present', 'to': 'removed'}}
            diff['timing'] = dsl.timing_diff(edit, VOCAB)
            if isinstance(edit, dsl.DeleteEdit) and edit.at_frame is not None:
                summary = (f'At frame {edit.at_frame} the pen cup is removed from the running '
                           f'simulation: it stops colliding and stops being rendered from that '
                           f'frame on, while the kettle and the pen carry on from the state they '
                           f'had reached. Frames 1-{edit.at_frame - 1} are identical to the source clip.')
            elif isinstance(edit, dsl.DeleteEdit):
                summary = 'Remove the ballpoint pen from simulation, rendering and GT from frame 1.'
            else:
                summary = 'Change exactly one physical parameter; geometry, camera and materials stay fixed.'
            if dsl.is_timed(edit) and isinstance(edit, dsl.SetEdit):
                summary = (f'{summary} The edit is applied inside the running simulation at frame '
                           f'{edit.at_frame}, then the simulation continues from that state.')
            record.update(source_case_id=SOURCE_CASE_ID, edit_dsl=instruction,
                          applies_from_frame=dsl.starts_at_frame(edit),
                          edit_summary=summary,
                          physics_diff=diff, prompts=dsl.make_prompts(edit, VOCAB),
                          scenario_overrides_json=str(folder / 'scenario_overrides.json'), prompts_json=str(folder / 'prompts.json'))
            write_json(folder / 'scenario_overrides.json', override)
            write_json(folder / 'prompts.json', dict(schema_version=2, **{key: record[key] for key in (
                'case_id', 'source_case_id', 'edit_dsl', 'applies_from_frame', 'edit_summary', 'physics_diff', 'prompts')}))
            manifest['edits'].append(record)
        else:
            record['description'] = description
            manifest['source'] = record
            write_json(folder / 'prompts.json', dict(schema_version=1, case_id=case_id, kind='source', prompts=description))
        write_json(path, manifest)
        print(f'[suite] {case_id}', flush=True)
        start = time.perf_counter()
        try:
            record.update(run_case(folder, scenario, args))
            if not args.dry_run and not instruction and args.duration_sec >= 1 and not record['quality']['transmission_observed']:
                raise RuntimeError('Baseline did not transfer motion to the pen cup')
            record['outputs'] = outputs(folder)
        except Exception:
            record['status'] = 'failed'
            write_json(path, manifest)
            raise
        record['elapsed_sec'] = round(time.perf_counter() - start, 3)
        write_json(path, manifest)


if __name__ == '__main__':
    main()
