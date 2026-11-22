"""Read-only audit of basketball_rim_roll_in: the recipe, the vocabulary, and any built suite."""
from __future__ import annotations

# PCVE_UNIFIED_ENTRY_BEGIN
import sys as _audit_sys
from pathlib import Path as _AuditPath
_SCENE_DIR = _AuditPath(__file__).resolve().parents[1]
for _sub in (_SCENE_DIR.parents[1], _SCENE_DIR, _SCENE_DIR / "physics",
             _SCENE_DIR / "appearance", _SCENE_DIR / "tools"):
    if _sub.is_dir() and str(_sub) not in _audit_sys.path:
        _audit_sys.path.insert(1, str(_sub))
# PCVE_UNIFIED_ENTRY_END

import argparse
import json
import math
from pathlib import Path

SCENE = 'basketball_rim_roll_in'


def scene_report():
    """Everything that can be checked without running a simulation."""
    import scene_config as sc
    from edit_vocab import (BOUNCE_FACTOR, DESCRIPTION, EDIT_CASES, GRAVITY_FRAME,
                            RESTITUTION_PARTS, TOTAL_FRAMES, VOCAB, dsl)
    report = {'passed': True, 'errors': [], 'notes': [], 'cases': {}}
    scenario = sc.load_scenario()
    # Round-trip through JSON before comparing: the disk copy has lists where
    # the code writes tuples, and that is not drift.
    defaults = json.loads(json.dumps(sc.defaults()))
    if scenario != defaults:
        # The on-disk recipe is what every entry point reads; if it has drifted
        # from the code the suite is silently running a different shot.
        drift = [key for key in defaults if defaults[key] != scenario.get(key)]
        report['notes'].append(f'scenario.json differs from defaults in: {drift}')
    report['fps'] = scenario['physics']['fps']
    report['duration_sec'] = scenario['physics']['duration_sec']
    report['total_frames'] = TOTAL_FRAMES
    if abs(TOTAL_FRAMES - 4 * scenario['physics']['fps']) > 0:
        report['errors'].append(f'clip is {TOTAL_FRAMES} frames, not the 4 s the brief asks for')
    # Every restitution must stay inside [0, 1] after the bounce edit.
    for part in RESTITUTION_PARTS:
        value = scenario['physics'][part] * BOUNCE_FACTOR
        if not 0.0 <= value <= 1.0:
            report['errors'].append(f'{part} would leave [0, 1] after the bounce edit '
                                    f'({value:.2f})')
    report['bounce_factor'] = BOUNCE_FACTOR
    for case in EDIT_CASES:
        entry = {'dsl': case.dsl}
        try:
            edit = dsl.parse(case.dsl, VOCAB)
        except Exception as exc:
            report['errors'].append(f'{case.case_id}: {exc}')
            report['cases'][case.case_id] = {**entry, 'parsed': False}
            continue
        override = dsl.to_scenario_override(edit, VOCAB)
        entry['parsed'] = True
        entry['applies_from_frame'] = dsl.starts_at_frame(edit)
        entry['override_keys'] = sorted(override)
        if dsl.is_timed(edit) and not 2 <= entry['applies_from_frame'] <= TOTAL_FRAMES:
            report['errors'].append(f'{case.case_id}: edit lands outside the clip')
        try:
            patched = sc.merge(sc.defaults(), {'physics': override})
            sc.validate(patched, check_assets=True)
        except Exception as exc:
            report['errors'].append(f'{case.case_id}: override does not validate ({exc})')
        report['cases'][case.case_id] = entry
    report['physics_diff_sample'] = {
        'gravity_midway': dsl.to_physics_override(
            dsl.parse(f'SET world.gravity TIMES 3 AT FRAME {GRAVITY_FRAME}', VOCAB), VOCAB)}
    report['description'] = DESCRIPTION['vague']['zh']
    report['passed'] = not report['errors']
    return report


def suite_report(root):
    """What a built suite actually contains, case by case."""
    report = {'out_root': str(root), 'passed': True, 'errors': [], 'cases': {},
              'notes': []}
    manifest_path = root / 'suite_manifest.json'
    if not manifest_path.is_file():
        report['passed'] = False
        report['errors'].append('missing suite_manifest.json')
        return report
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    total = manifest.get('total_frames')
    records = [manifest.get('source') or {}] + list(manifest.get('edits') or [])
    baseline = None
    for record in records:
        case_id = record.get('case_id')
        if not case_id:
            continue
        folder = root / 'cases' / case_id
        entry = {'case_dir': str(folder), 'frames': 0,
                 'video': (folder / 'video.mp4').is_file()}
        cache = folder / 'physics_transforms.json'
        if not cache.is_file():
            report['errors'].append(f'{case_id}: missing physics_transforms.json')
            report['cases'][case_id] = entry
            continue
        data = json.loads(cache.read_text(encoding='utf-8'))
        entry['frames'] = len(data.get('frames') or [])
        entry['frame_end'] = data.get('frame_end')
        entry['timed_edits'] = data.get('timed_edits') or []
        if total and entry['frames'] != total:
            report['errors'].append(f'{case_id}: {entry["frames"]} frames, expected {total}')
        for frame in data.get('frames') or []:
            values = [*frame['ball_location'], *frame['ball_linear_velocity'],
                      *frame['ball_angular_velocity']]
            if not all(math.isfinite(v) for v in values):
                report['errors'].append(f'{case_id}: non-finite state at '
                                        f'frame {frame["frame_index"]}')
                break
        metrics = data.get('metrics') or {}
        entry['rim_orbit_revolutions'] = metrics.get('rim_orbit_revolutions')
        entry['passed_through_rim'] = metrics.get('passed_through_rim')
        entry['surface_sequence'] = (metrics.get('surface_sequence') or [])[:8]
        if case_id == manifest.get('source_case_id'):
            baseline = data
            if (metrics.get('surface_sequence') or [''])[0] != 'backboard':
                report['errors'].append('the source take does not start on the backboard')
            if not metrics.get('passed_through_rim'):
                report['errors'].append('the source take never passes through the rim')
        elif baseline is not None:
            shift = max(math.dist(a['ball_location'], b['ball_location'])
                        for a, b in zip(data['frames'], baseline['frames']))
            entry['max_shift_m'] = round(shift, 4)
            if shift < 0.02:
                report['errors'].append(f'{case_id}: edit moves the ball less than 2 cm')
            edits = data.get('timed_edits') or []
            for event in edits:
                frame = event.get('frame')
                if not frame:
                    continue
                early = [f['ball_location'] for f in data['frames'][:frame - 1]]
                source = [f['ball_location'] for f in baseline['frames'][:frame - 1]]
                entry['source_frames_identical'] = early == source
                if early != source:
                    report['errors'].append(f'{case_id}: frames before {frame} differ '
                                            f'from the source')
        report['cases'][case_id] = entry
    if not report['cases']:
        report['errors'].append('suite_manifest.json lists no cases')
    report['passed'] = not report['errors']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-root', type=Path, help='Suite root from build_pcve_%s.py' % SCENE)
    parser.add_argument('--json', type=Path, help='Write the full report here')
    args = parser.parse_args()
    report = {'scene': SCENE, 'recipe': scene_report()}
    if args.out_root:
        report['suite'] = suite_report(args.out_root.resolve())
    report['passed'] = all(part['passed'] for part in report.values()
                           if isinstance(part, dict) and 'passed' in part)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                             encoding='utf-8')
    print(json.dumps({'passed': report['passed'],
                      'recipe_errors': report['recipe']['errors'],
                      'suite_errors': (report.get('suite') or {}).get('errors', []),
                      'cases': len(((report.get('suite') or {}).get('cases') or {}))},
                     indent=2, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
