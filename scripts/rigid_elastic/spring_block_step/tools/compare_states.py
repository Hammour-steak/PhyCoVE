"""Compare a fresh solve with the registered native states, array by array.

    .venv-rigid-elastic/bin/python tools/compare_states.py --rerun <simulate --out DIR> [--cases ...] [--report FILE]

<DIR>/cases/<case>/ must hold the simulate entry's states.npz and motion_states.npz.
Prints, per case, whether every array is bitwise equal and otherwise the largest
absolute difference (positions in m, quaternion components, velocities in m/s, rad/s).
"""
from pathlib import Path
import argparse, json, sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scene_common import CASES, NATIVE, load_physics, save


def compare(a, b):
    out = {}
    for name in ('states.npz', 'motion_states.npz'):
        x, y = np.load(a / name), np.load(b / name)
        for key in sorted(set(x.files) | set(y.files)):
            if key not in x.files or key not in y.files:
                out[f'{name}:{key}'] = {'present_in_both': False}
                continue
            u, v = x[key], y[key]
            if u.dtype.kind in 'US':
                out[f'{name}:{key}'] = {'bitwise_equal': bool(np.array_equal(u, v))}
            elif u.shape != v.shape:
                out[f'{name}:{key}'] = {'bitwise_equal': False, 'shapes': [list(u.shape), list(v.shape)]}
            else:
                out[f'{name}:{key}'] = {'bitwise_equal': bool(np.array_equal(u, v)),
                                        'max_abs_diff': float(np.max(np.abs(u.astype(float) - v.astype(float)))) if u.size else 0.0}
    return {'arrays': out, 'resolved_physics_identical': load_physics(a / 'resolved_physics.json') == load_physics(b / 'resolved_physics.json')}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--rerun', type=Path, required=True)
    p.add_argument('--cases', nargs='+', default=list(CASES))
    p.add_argument('--native', type=Path, default=NATIVE)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    result = {case: compare(a.native / case, a.rerun / 'cases' / case) for case in a.cases}
    if a.report:
        save(a.report, result)
    summary = {}
    for case, r in result.items():
        arrays = r['arrays']
        summary[case] = {'all_bitwise_equal': all(v.get('bitwise_equal', False) for v in arrays.values()),
                         'resolved_physics_identical': r['resolved_physics_identical'],
                         'max_abs_diff': {k: v['max_abs_diff'] for k, v in arrays.items() if not v.get('bitwise_equal', True) and 'max_abs_diff' in v}}
    print(json.dumps(summary, indent=1))
