"""Numerical gates of the accepted native states (the gates of the delivery finalizer's validate()).

    .venv-rigid-elastic/bin/python tools/validate_physics.py [--native DIR] [--audits DIR] [--report FILE]

Reads states.npz, motion_states.npz, model.xml and resolved_physics.json from
<native>/<case>/ (default: the registered assets/scenes/spring_block_step/native_states)
and physics_audit.json, with its half-step convergence block, from
<audits>/<case>/ (default: renders/spring_block_step/physics_audit/pcve_spring_block_step_suite/cases).
Also checks that each resolved_physics.json equals scene_common.parameters(case).
"""
from pathlib import Path
import argparse, hashlib, json, sys
import xml.etree.ElementTree as ET
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scene_common import CASES, DELIVERY, FRAMES, NATIVE, load_physics, parameters, save, spring_properties
from pcve_media_contract import require_times


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(native, audits):
    report = {'schema_version': 1, 'position_gate_m': .005, 'rotation_gate_deg': 5.0,
              'penetration_gate_m': .0003, 'tail_speed_gate_m_s': .002, 'material_calibrated': False, 'cases': []}
    source = np.load(native / 'source/states.npz')
    initial = {n: (source['positions'][0, i], source['quaternions'][0, i]) for i, n in enumerate(source['body_names'])}
    for case in CASES:
        path, apath = native / case, audits / case
        a = json.loads((apath / 'physics_audit.json').read_text(encoding='utf8'))
        states = np.load(path / 'states.npz'); require_times(states['time'])
        c = load_physics(path / 'resolved_physics.json')
        expected, _ = parameters(case)
        assert c == dict(expected, spring_derived=spring_properties(expected)), (case, 'resolved physics differ from scene_common')
        model = ET.parse(path / 'model.xml').getroot()
        assert model.find(".//geom[@name='lower']") is None
        assert model.find(".//geom[@name='table']") is not None
        assert not any('lower' in pair for pair in a['native_contact_pairs'])
        for i, n in enumerate(states['body_names']):
            if n in initial:
                assert np.array_equal(states['positions'][0, i], initial[n][0]), (case, n, 'initial position')
                assert np.array_equal(states['quaternions'][0, i], initial[n][1]), (case, n, 'initial quaternion')
        assert np.all(states['initial_qvel'] == 0), case
        assert a['min_contact_distance_m'] >= -.0003, (case, 'penetration')
        assert a['max_total_energy_j'] <= a['initial_total_energy_j'] + 1e-6, (case, 'energy creation')
        assert a['end_speed_m_s'] < .002, (case, 'tail speed')
        conv = a['convergence']
        assert conv['max_position_error_m'] < .005, (case, conv)
        assert conv['max_rotation_error_deg'] < 5, (case, conv)
        assert conv['dense_motion_position_error_m'] < .005, (case, conv)
        assert conv['dense_motion_rotation_error_deg'] < 5, (case, conv)
        assert a['guide_upper_stop_not_hit']
        motion = np.load(path / 'motion_states.npz'); assert len(motion['time']) == 961
        assert np.array_equal(motion['positions'][::10][:FRAMES], states['positions'])
        assert np.array_equal(motion['quaternions'][::10][:FRAMES], states['quaternions'])
        if case == 'source':
            e = a['events']; assert e['natural_length_separation_s'] < e['leave_upper_s'] < e['first_table_contact_s']
        if case == 'add_block': assert 'first_obstacle_geom_contact_s' in a['events']
        if case == 'young_quarter': assert 'leave_upper_s' not in a['events']
        max_difference = float(np.linalg.norm(states['positions'][:, 0] - source['positions'][:, 0], axis=1).max())
        if case != 'source': assert max_difference > .02, (case, 'not a visible trajectory difference')
        report['cases'].append({'case_id': case, 'all_checks_passed': True, 'maximum_source_difference_m': max_difference,
                                'initial_existing_poses_identical': True, 'convergence': conv,
                                'states_sha256': sha(path / 'states.npz')})
    report['all_checks_passed'] = True
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--native', type=Path, default=NATIVE)
    p.add_argument('--audits', type=Path, default=DELIVERY / 'cases')
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    result = validate(a.native, a.audits)
    if a.report:
        save(a.report, result)
    print(json.dumps({'all_checks_passed': result['all_checks_passed'],
                      'cases': {r['case_id']: round(r['maximum_source_difference_m'], 4) for r in result['cases']}}))
