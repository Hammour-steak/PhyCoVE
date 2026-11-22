"""Reproducible random sampling of kettle and pen-cup masses on top of the scene builder."""
# PCVE_UNIFIED_ENTRY_BEGIN

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parents[1]
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
# PCVE_UNIFIED_ENTRY_END

import random

from pcve_scene_runtime import ROOT
from build_pcve_office_desk_kettle_tip import parser, run_case, write_json, outputs
from scene_config import defaults


def main():
    p = parser()
    p.set_defaults(out_root=ROOT / 'renders/office_desk_kettle_tip_batch')
    p.add_argument('--count', type=int, default=3)
    p.add_argument('--seed', type=int, default=0)
    args = p.parse_args()
    args.out_root = args.out_root.resolve()
    if args.count < 1 or args.cases or (args.simulate_only and args.render_only):
        raise ValueError('Invalid batch options')
    rng = random.Random(args.seed)
    manifest = dict(schema_version=1, scene='office_desk_kettle_tip', seed=args.seed, samples=[])
    for i in range(args.count):
        scenario = defaults()
        scenario['seed'] = args.seed + i
        scenario['physics'].update(kettle_mass=round(rng.uniform(.7, 1.4), 3),
                                   pen_holder_mass=round(rng.uniform(.18, .3), 3))
        scenario['render'].update(fps=args.fps, duration_sec=args.duration_sec, slow_motion=args.slow_motion,
                                  resolution=args.resolution, samples=args.samples)
        folder = args.out_root / f'sample_{i:03d}'
        result = run_case(folder, scenario, args)
        manifest['samples'].append(dict(sample_index=i, seed=scenario['seed'], case_dir=str(folder),
                                        outputs=outputs(folder), **result))
        if not args.dry_run:
            write_json(args.out_root / 'batch_manifest.json', manifest)


if __name__ == '__main__':
    main()
