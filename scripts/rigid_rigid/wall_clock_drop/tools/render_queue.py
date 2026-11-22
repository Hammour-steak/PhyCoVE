"""Reproducible random sampling of clock mass, tip-over spin, launch push and friction."""
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
from build_pcve_wall_clock_drop import parser, run_case, write_json, outputs, SCENE
from scene_config import defaults


def main():
    p = parser()
    p.set_defaults(out_root=ROOT / 'renders/batch_wall_clock_drop')
    p.add_argument('--count', type=int, default=4)
    p.add_argument('--start-index', type=int, default=0)
    p.add_argument('--seed-base', type=int, default=20400)
    args = p.parse_args()
    args.out_root = args.out_root.resolve()
    if args.count < 1 or args.start_index < 0 or args.cases or (args.simulate_only and args.render_only):
        raise ValueError('Invalid batch options')
    manifest = dict(schema_version=1, scene=SCENE, seed_base=args.seed_base,
                    start_index=args.start_index, samples=[])
    for offset in range(args.count):
        index = args.start_index + offset
        seed = args.seed_base + index
        rng = random.Random(seed)
        scenario = defaults()
        scenario['seed'] = seed
        # Keep the room and the drop height fixed; vary how the clock leaves the
        # hook and how heavy it is against the crate it is about to hit.
        scenario['physics'].update(clock_mass=round(rng.uniform(.35, 2.4), 3),
                                   clock_tip_spin=round(rng.uniform(-2.6, -.55), 3),
                                   clock_push=round(rng.uniform(.05, .60), 3),
                                   clock_friction=round(rng.uniform(.25, .65), 3),
                                   crate_mass=round(rng.uniform(.35, 1.30), 3))
        scenario['render'].update(fps=args.fps, duration_sec=args.duration_sec, slow_motion=args.slow_motion,
                                  resolution=args.resolution, samples=args.samples)
        folder = args.out_root / f'sample_{index:04d}'
        result = run_case(folder, scenario, args)
        manifest['samples'].append(dict(sample_index=index, seed=seed, case_dir=str(folder),
                                        outputs=outputs(folder), **result))
        write_json(args.out_root / 'batch_manifest.json', manifest)


if __name__ == '__main__':
    main()
