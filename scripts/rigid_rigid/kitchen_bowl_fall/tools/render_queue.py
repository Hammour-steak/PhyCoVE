"""Reproducible random sampling of bowl mass, tip-over spin, launch push and friction."""
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

from build_pcve_kitchen_bowl_fall import parser, run_case, write_json, outputs, SCENE
from pcve_scene_runtime import ROOT
from scene_config import defaults


def main():
    p = parser()
    p.set_defaults(out_root=ROOT / 'renders/batch_kitchen_bowl_fall')
    p.add_argument('--count', type=int, default=4)
    p.add_argument('--start-index', type=int, default=0)
    p.add_argument('--seed-base', type=int, default=20500)
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
        # Keep the kitchen and the drop height fixed; vary how the bowl leaves
        # the ledge and how heavy it is against the tableware it is about to hit.
        scenario['physics'].update(falling_bowl_mass=round(rng.uniform(.20, 1.4), 3),
                                   falling_bowl_spin=round(rng.uniform(-2.4, -.50), 3),
                                   falling_bowl_push=round(rng.uniform(.05, .55), 3),
                                   falling_bowl_friction=round(rng.uniform(.20, .60), 3),
                                   tableware_mass=round(rng.uniform(.60, 1.80), 3))
        scenario['render'].update(fps=args.fps, duration_sec=args.duration_sec, slow_motion=args.slow_motion,
                                  resolution=args.resolution, samples=args.samples)
        folder = args.out_root / f'sample_{index:04d}'
        result = run_case(folder, scenario, args)
        manifest['samples'].append(dict(sample_index=index, seed=seed, case_dir=str(folder),
                                        outputs=outputs(folder), **result))
        write_json(args.out_root / 'batch_manifest.json', manifest)


if __name__ == '__main__':
    main()
