"""Build the source take and every independent edit of it."""
from __future__ import annotations

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
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))

import argparse
import math
from pathlib import Path
import subprocess

from scene_config import BASELINE_METRICS_PATH, load_scenario, write_json
from pcve_scene_runtime import render_prefix, python_for

HERE = Path(__file__).resolve().parent

from simulate_basketball_rim_roll_in import simulate
from edit_vocab import DESCRIPTION, EDIT_CASES, VOCAB, dsl

SOURCE_CASE_ID = 'basketball_rim_baseline'
# An edit has to move the ball far enough that a viewer can see it; the ball is
# about 30 px across at this framing, so 2 cm is a third of its own diameter.
MIN_VISIBLE_SHIFT_M = 0.02
MAX_PENETRATION_M = 0.01


def physics_diff(edit):
    """The before/after block the manifest and prompts.json carry."""
    if isinstance(edit, dsl.DeleteEdit):
        diff = {f'presence ({edit.object_id})': {'from': 'present', 'to': 'absent'}}
    elif isinstance(edit, dsl.AddEdit):
        diff = {'presence': {'from': 'absent', 'to': 'present'},
                'position': dsl.add_position_diff(edit, VOCAB)}
    else:
        diff = {f'{edit.property_name} ({edit.object_id})': {
            'from': dsl.baseline_value_for(edit, VOCAB),
            'to': dsl.resolved_to_value(edit, VOCAB)}}
        if edit.factor is not None:
            diff[f'{edit.property_name} ({edit.object_id})']['factor'] = edit.factor
    diff['timing'] = dsl.timing_diff(edit, VOCAB)
    return diff


def build_edit_record(case):
    """Parse the case's DSL once and derive everything the suite publishes."""
    edit = dsl.parse(case.dsl, VOCAB)
    return {
        'case_id': case.case_id,
        'source_case_id': SOURCE_CASE_ID,
        'edit_dsl': case.dsl,
        'edit_summary': case.summary,
        'applies_from_frame': dsl.starts_at_frame(edit),
        'physics_diff': physics_diff(edit),
        'prompts': dsl.make_prompts(edit, VOCAB),
        'overrides': {'physics': dsl.to_scenario_override(edit, VOCAB)},
    }


def rim_summary(metrics):
    """The handful of numbers that say whether the shot did its trick."""
    return {
        'board_impact_frame': (metrics['board_impact'] or {}).get('frame_index'),
        'rim_contacts': metrics['rim_contact_count'],
        'rim_orbit_revolutions': metrics['rim_orbit_revolutions'],
        'passed_through_rim': metrics['passed_through_rim'],
        'through_rim_frame': (metrics['through_rim'] or {}).get('frame_index'),
        'landing_frame': (metrics['landing'] or {}).get('frame_index'),
        'surface_sequence': metrics['surface_sequence'][:12],
        'path_length_m': round(metrics['path_length_m'], 3),
    }


def check_run(case_id, edit, data, baseline):
    """Reject a take that is not a finite, visible simulation of the edit it claims."""
    for frame in data['frames']:
        values = [*frame['ball_location'], *frame['ball_quaternion_xyzw'],
                  *frame['ball_linear_velocity'], *frame['ball_angular_velocity']]
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError(f'{case_id}: non-finite state at frame {frame["frame_index"]}')
    metrics = data['metrics']
    if (metrics['min_floor_gap_m'] < -MAX_PENETRATION_M
            or metrics['min_board_gap_m'] < -MAX_PENETRATION_M):
        raise RuntimeError(f'{case_id}: the ball penetrates the floor or the board')
    shift = max(math.dist(a['ball_location'], b['ball_location'])
                for a, b in zip(data['frames'], baseline['frames']))
    if shift < MIN_VISIBLE_SHIFT_M:
        raise RuntimeError(f'{case_id}: edited ball never moves more than {shift:.3f} m away '
                           f'from the source')
    start = dsl.starts_at_frame(edit)
    if dsl.is_timed(edit):
        # A timed edit is only worth shipping if the run-up is the source video
        # frame for frame; that is what makes the two halves comparable.
        early = [frame['ball_location'] for frame in data['frames'][:start - 1]]
        source = [frame['ball_location'] for frame in baseline['frames'][:start - 1]]
        if early != source:
            raise RuntimeError(f'{case_id}: frames before {start} must reproduce the source exactly')
    return {'max_shift_m': round(shift, 4), **rim_summary(metrics),
            'timed_events': metrics.get('timed_events', [])}


from pcve_project_paths import suite_output_root
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-root', type=Path, default=suite_output_root("basketball_rim_roll_in"))
    parser.add_argument('--simulate-only', action='store_true')
    parser.add_argument('--mode', choices=('build', 'preview', 'keyframes', 'animation'),
                        default='keyframes')
    parser.add_argument('--only', help='Comma-separated edit IDs; the source is always included')
    parser.add_argument('--resolution', nargs=2, type=int, default=(1280, 720))
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    parser.add_argument('--device', choices=('auto', 'cpu', 'gpu'), default='auto')
    parser.add_argument('--gpu-backend', choices=('optix', 'cuda'), default='optix')
    parser.add_argument('--render-python', type=Path, default=python_for('render'))
    parser.add_argument('--blender', type=Path,
                        help='Blender executable; otherwise the render Python with bpy')
    parser.add_argument('--keyframes', default=None,
                        help='Shared comparison frames; default follows the run')
    args = parser.parse_args()
    selected = set(args.only.split(',')) if args.only else {c.case_id for c in EDIT_CASES}
    unknown = selected - {c.case_id for c in EDIT_CASES}
    if unknown:
        parser.error(f'Unknown case IDs: {sorted(unknown)}')
    root = args.out_root.resolve()
    cases = [c for c in EDIT_CASES if c.case_id in selected]
    records = [dict(case_id=SOURCE_CASE_ID, kind='source', source_case_id=None, edit_dsl=None,
                    overrides={}, applies_from_frame=1, physics_diff={},
                    description=DESCRIPTION, prompts=DESCRIPTION)]
    records += [dict(build_edit_record(case), kind='edit') for case in cases]
    physics = VOCAB.baseline_physics
    manifest = {'schema_version': 3, 'suite_name': 'pcve_basketball_rim_roll_in_suite',
                'scene': 'basketball_rim_roll_in', 'source_case_id': SOURCE_CASE_ID,
                'baseline_physics': physics,
                'fps': physics['fps'], 'duration_sec': physics['duration_sec'],
                'total_frames': VOCAB.total_frames, 'frame_count': VOCAB.total_frames,
                'edit_count': len(cases),
                'render_mode': 'simulate-only' if args.simulate_only else args.mode,
                'source': None, 'edits': [], 'cases': []}
    baseline_data = None
    for index, record in enumerate(records):
        case_dir = root / 'cases' / record['case_id']
        case_dir.mkdir(parents=True, exist_ok=True)
        overrides = record.pop('overrides')
        edit = dsl.parse(record['edit_dsl'], VOCAB) if record['edit_dsl'] else None
        write_json(case_dir / 'scenario_overrides.json', overrides)
        if edit is None:
            write_json(case_dir / 'prompts.json', dict(schema_version=1, case_id=record['case_id'],
                                                      kind='source', prompts=record['description']))
        else:
            write_json(case_dir / 'prompts.json', dict(schema_version=2, **{
                key: record[key] for key in ('case_id', 'kind', 'source_case_id', 'edit_dsl',
                                             'edit_summary', 'applies_from_frame',
                                             'physics_diff', 'prompts')}))
        scenario = load_scenario(overrides if overrides else None)
        write_json(case_dir / 'scenario_input.json', scenario)
        data = simulate(scenario)
        if edit is None:
            baseline_data = data
            check = {'max_shift_m': 0.0, **rim_summary(data['metrics']), 'timed_events': []}
            # The vocabulary quotes this run's frame numbers; keep them honest.
            write_json(BASELINE_METRICS_PATH, rim_summary(data['metrics']))
        else:
            check = check_run(record['case_id'], edit, data, baseline_data)
        write_json(case_dir / 'physics_transforms.json', data)
        write_json(case_dir / 'simulation_metrics.json', data['metrics'])
        write_json(case_dir / 'run_status.json', {'simulation': 'complete',
                                                 'render': 'pending' if not args.simulate_only
                                                 else 'not_requested'})
        if not args.simulate_only:
            keyframes = args.keyframes or ','.join(str(f) for f in [
                1, *(e for e in [check.get('board_impact_frame'), check.get('through_rim_frame')] if e),
                *(event['frame'] for event in data['metrics']['timed_events']), data['frame_end']])
            command = render_prefix(args, HERE / 'render_basketball_rim_roll_in.py') + [
                       '--out-dir', str(case_dir),
                       '--scenario-overrides-json', str(case_dir / 'scenario_overrides.json'),
                       '--mode', args.mode, '--resolution', *map(str, args.resolution),
                       '--samples', str(args.samples), '--engine', args.engine,
                       '--device', args.device, '--gpu-backend', args.gpu_backend,
                       '--keyframes', keyframes]
            with (case_dir / 'render.log').open('w', encoding='utf-8') as log:
                completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
            if completed.returncode:
                write_json(case_dir / 'run_status.json', {'simulation': 'complete',
                                                         'render': 'failed'})
                raise RuntimeError(f'Render failed, see {case_dir / "render.log"}')
            write_json(case_dir / 'run_status.json', {'simulation': 'complete', 'render': 'complete'})
        manifest['cases'].append({**record, 'seed': 8100 + index, 'check': check,
            'directory': str(case_dir),
            'physics_transforms': str(case_dir / 'physics_transforms.json'),
            'scenario_overrides_json': str(case_dir / 'scenario_overrides.json'),
            'prompts_json': str(case_dir / 'prompts.json'),
            'ground_truth': str(case_dir / 'ground_truth_transforms.json')
            if not args.simulate_only else None,
            'video': str(case_dir / 'video.mp4')
            if args.mode == 'animation' and not args.simulate_only else None})
        write_json(root / 'suite_manifest.json', manifest)
        print(f'{record["case_id"]}: shift={check["max_shift_m"]} m, '
              f'rev={check["rim_orbit_revolutions"]}, '
              f'through={check["passed_through_rim"]}@{check["through_rim_frame"]}, '
              f'events={[e["frame"] for e in check["timed_events"]]}', flush=True)
    manifest['source'] = manifest['cases'][0]
    manifest['edits'] = manifest['cases'][1:]
    write_json(root / 'suite_manifest.json', manifest)


if __name__ == '__main__':
    main()
