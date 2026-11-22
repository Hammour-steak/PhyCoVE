"""Prepare the published-look suite from an accepted packed-template suite: new look, same solved motion.

Opens the accepted packed template (its SHA-256 is checked), applies the room finish (refine_template in
appearance/look_ramp_car_ball_collision.py), packs it as the new
shared template and lays out all seven cases.  No solver runs: every case's physics configuration,
dense trajectory samples, contacts, per-frame poses and ground truth are copied from the accepted
suite and proven equal (physics_freeze_validation.json).  Only the configuration's appearance
group changes.

blender -b --factory-startup -t 32 --python-exit-code 1 \
  --python scripts/rigid_rigid/ramp_car_ball_collision/tools/prepare_template_suite.py -- \
  --accepted-suite <accepted suite with source_template.blend> \
  --out-root renders/ramp_car_ball_collision/template_suite
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import bpy

HERE = Path(__file__).resolve().parents[1]
for parent in HERE.parents:
    if (parent / 'scripts/pcve_assets.py').is_file():
        sys.path.insert(0, str(parent / 'scripts'))
        break
for directory in [HERE, HERE / 'appearance', HERE / 'tools']:
    sys.path.insert(0, str(directory))
from scene_config import differences, save_json, signature
from scene_config import BASELINE
from look_ramp_car_ball_collision import refine_template
from prepare_diecast import audit_scene
from render_diecast import setup, state_signature

CASES = ['source', 'edit_heavy_ball', 'edit_low_restitution', 'edit_remove_ball',
         'edit_light_ball', 'edit_remove_car', 'edit_remove_car_at_2s']
TEMPLATE_SHA256 = '4c949e5b6e36f77d5aa0ac3c2328ad81ff32a86093b9f859736a37c147cbb698'
# Solver outputs and annotations that stay byte-identical to the accepted suite.
COPIED = ['ground_truth_transforms.json', 'prompts.json', 'physics_validation.json', 'contacts.json', 'trajectory.csv',
          'native_physics_transforms.json', 'native_trajectory.csv', 'native_contacts.json',
          'native_physics_validation.json', 'native_prompts.json']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def with_appearance(result, appearance):
    out = copy.deepcopy(result)
    out['configuration']['appearance'] = copy.deepcopy(appearance)
    out['configuration_sha256'] = signature(out['configuration'])
    for key in ['trajectory_samples', 'contact_events', 'frames', 'outcome', 'dt_sec']:
        assert out.get(key) == result.get(key), key
    assert out['configuration']['physics'] == result['configuration']['physics']
    assert out['configuration']['simulation_quality'] == result['configuration']['simulation_quality']
    assert out['configuration']['render'] == result['configuration']['render']
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--accepted-suite', type=Path, required=True, help='Accepted packed-template suite (source + six edits)')
    parser.add_argument('--appearance-json', type=Path, help='appearance group; default: the appearance in scene_config.py')
    parser.add_argument('--out-root', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=32)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    accepted = args.accepted_suite.resolve()
    out = args.out_root.resolve()
    assert not (out / 'suite_manifest.json').exists(), 'Choose a fresh output root'
    out.mkdir(parents=True, exist_ok=True)
    appearance = json.loads(args.appearance_json.read_text()) if args.appearance_json else copy.deepcopy(BASELINE["appearance"])
    parent_manifest = json.loads((accepted / 'suite_manifest.json').read_text())
    template_blend = accepted / 'source_template.blend'
    assert sha(template_blend) == TEMPLATE_SHA256, 'Accepted template changed'

    # 1. Shared packed template: accepted scene + room finish.
    bpy.ops.wm.open_mainfile(filepath=str(template_blend))
    cfg = copy.deepcopy(parent_manifest['configuration'])
    cfg['appearance'] = copy.deepcopy(appearance)
    ledger = refine_template(cfg)
    scene = bpy.context.scene
    assert scene.cycles.samples == 128 and not scene.render.use_persistent_data and scene.render.use_motion_blur
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    bpy.ops.file.pack_all()
    template = out / 'source_template.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(template))
    template_hash = sha(template)
    save_json(out / 'appearance_ledger.json', ledger)

    # 2. Cases: copied solver outputs, new settings, pose audit, state signatures, packed scene.
    freeze = {}
    records = {}
    parent_rows = {r['case_id']: r for r in [parent_manifest['source']] + parent_manifest['edits']}
    for case_id in CASES:
        old = accepted / 'cases' / case_id
        folder = out / 'cases' / case_id
        folder.mkdir(parents=True)
        for name in COPIED:
            if (old / name).exists():
                shutil.copy2(old / name, folder / name)
        before = json.loads((old / 'physics_transforms.json').read_text())
        result = with_appearance(before, appearance)
        save_json(folder / 'physics_transforms.json', result)
        old_settings = json.loads((old / 'settings.json').read_text())
        settings = copy.deepcopy(old_settings)
        settings['appearance'] = copy.deepcopy(appearance)
        assert settings == result['configuration']
        save_json(folder / 'settings.json', settings)
        save_json(folder / 'configuration_diff.json', {'before': old_settings, 'after': settings,
            'differences': differences(old_settings, settings), 'changed_group': 'appearance',
            'actual_physics_unchanged': True, 'dense_trajectory_unchanged': True, 'contacts_unchanged': True,
            'frame_poses_unchanged': True, 'reference_case': str(old)})
        scene, roots, backend = setup(folder, template, 'CPU', args.threads)
        report = audit_scene(scene, roots, result, sha(old / 'physics_transforms.json'), ledger)
        report['pose_samples_checked'] = sum(len(f['objects']) for f in result['frames'])
        report['presence'] = {'initial_car_present': result['configuration']['physics']['car'].get('present', True),
                              'remove_car_at_sec': result['configuration']['physics']['car'].get('remove_at_sec')}
        save_json(folder / 'appearance_pose_validation.json', report)
        keys = {str(f): state_signature(scene, roots, f, settings) for f in range(1, 97)}
        save_json(folder / 'render_state_signatures.json', {'template_sha256': template_hash, 'frame_keys': keys})
        scene.frame_set(1)
        bpy.context.view_layer.update()
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(folder / 'ramp_car_ball_collision.blend'))
        copied = {name: {'accepted_sha256': sha(old / name), 'finished_sha256': sha(folder / name)}
                  for name in COPIED if (old / name).exists()}
        freeze[case_id] = {'accepted_physics_sha256': sha(old / 'physics_transforms.json'),
            'finished_physics_sha256': sha(folder / 'physics_transforms.json'),
            'physics_equal': result['configuration']['physics'] == before['configuration']['physics'],
            'simulation_quality_equal': result['configuration']['simulation_quality'] == before['configuration']['simulation_quality'],
            'trajectory_samples_equal': result['trajectory_samples'] == before['trajectory_samples'],
            'contacts_equal': result['contact_events'] == before['contact_events'],
            'frames_equal': result['frames'] == before['frames'],
            'copied_files_identical': all(v['accepted_sha256'] == v['finished_sha256'] for v in copied.values()),
            'copied_files': copied, 'trajectory_sample_count': len(result['trajectory_samples'])}
        row = copy.deepcopy(parent_rows[case_id])
        for key in ['video_sha256', 'case_acceptance']:
            row.pop(key, None)
        row.update(status='prepared_pending_render', case_dir=str(folder), accepted_case_dir=str(old),
                   outputs={k: str(folder / n) for k, n in [('video', 'video.mp4'), ('scene', 'ramp_car_ball_collision.blend'),
                            ('physics', 'physics_transforms.json'), ('settings', 'settings.json'),
                            ('ground_truth', 'ground_truth_transforms.json'), ('prompts', 'prompts.json')]})
        records[case_id] = row
        print('PREPARED', case_id, flush=True)
    assert all(all(v[k] for k in ['physics_equal', 'simulation_quality_equal', 'trajectory_samples_equal', 'contacts_equal',
                                  'frames_equal', 'copied_files_identical']) for v in freeze.values())
    save_json(out / 'physics_freeze_validation.json', {'accepted': True, 'no_solver_rerun': True,
        'accepted_suite': str(accepted), 'changed_configuration_group': 'appearance', 'cases': freeze})
    manifest = {'schema_version': 4, 'scene': 'ramp_car_ball_collision', 'suite_name': 'pcve_ramp_car_ball_collision_suite',
        'interaction_category': 'rigid_rigid', 'configuration': cfg, 'source': records['source'],
        'edits': [records[c] for c in CASES[1:]], 'fps': 24, 'resolution': [1280, 720], 'total_frames': 96,
        'duration_sec': 4.0, 'samples': 128, 'status': 'prepared_pending_render', 'source_template': str(template),
        'source_template_sha256': template_hash, 'appearance_revision': appearance['preset'],
        'render_revision': appearance['room_finish']['revision'], 'parent_suite_path': str(accepted),
        'parent_template_sha256': TEMPLATE_SHA256, 'native_suite': parent_manifest.get('native_suite'),
        'asset_credit': parent_manifest.get('asset_credit', '') + ' Poly Haven beige_wall_001 and rough_linen CC0.',
        'source_count': 1, 'edit_count': len(CASES) - 1}
    save_json(out / 'suite_manifest.json', manifest)
    print('PREPARED_ALL', str(out), template_hash, flush=True)


if __name__ == '__main__':
    main()
