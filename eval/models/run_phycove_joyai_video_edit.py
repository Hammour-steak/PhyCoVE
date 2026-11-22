#!/usr/bin/env python3
"""Run JoyAI-Video-Edit locally on PhyCoVE source videos and edit prompts (one GPU per process).

Run with the JoyAI environment's Python, e.g.
  CUDA_VISIBLE_DEVICES=4 $MODEL_ROOT/JoyAI-Video-Edit/env/bin/python \\
      run_phycove_joyai_video_edit.py --limit 2
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # keep eval/ free of __pycache__

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

from baselines.joyai_video_edit import (
    MODEL_ROOT, RESOLUTIONS, JoyAIVideoEditBaseline, atomic_json, exclusive_lock, probe_video, sha256,
)

DEFAULT_BENCH = os.environ.get('PHYCOVE_ROOT')  # release folder; without it --benchmark-root is required
SAFE = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--benchmark-root', type=Path, default=DEFAULT_BENCH, required=DEFAULT_BENCH is None,
                   help='Release folder with benchmark_manifest.json (default: $PHYCOVE_ROOT).')
    p.add_argument('--predictions-root', type=Path,
                   help='Parent of joyai_video_edit/. Default: <release-parent>/../predictions/PhyCoVE/<flavor>_<lang>.')
    p.add_argument('--prompt-flavor', choices=('vague', 'quantitative'), default='quantitative')
    p.add_argument('--prompt-lang', choices=('en', 'zh'), default='en')
    p.add_argument('--filter-scene')
    p.add_argument('--filter-property')
    p.add_argument('--filter-category')
    p.add_argument('--filter-kind', choices=('SET', 'DELETE', 'ADD'))
    p.add_argument('--filter-timing', choices=('whole_clip', 'partway'))
    p.add_argument('--global-id', action='append', default=[],
                   help='Select one edit by <scene>/<case_id>; repeatable.')
    p.add_argument('--split-file', type=Path, help='Relative to the benchmark root, e.g. splits/by_kind/ADD.txt.')
    p.add_argument('--limit', type=int)
    p.add_argument('--num-shards', type=int, default=1)
    p.add_argument('--shard-index', type=int, default=0)
    p.add_argument('--model-root', type=Path, default=MODEL_ROOT, help='Default: $MODEL_ROOT/JoyAI-Video-Edit.')
    p.add_argument('--dit-ckpt', help='Default: <model-root>/checkpoints/JoyAI-Video-Edit/dit/joyai_video_edit_dit_1101_face++.pth')
    p.add_argument('--resolution', choices=sorted(RESOLUTIONS), default='720p')
    p.add_argument('--num-inference-steps', type=int, default=2)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--max-temporal-ids', type=int, default=8)
    p.add_argument('--no-low-vram', dest='low_vram', action='store_false',
                   help='Keep the bf16 DiT and text encoder resident (needs more than 48 GB at 720p).')
    p.add_argument('--crf', type=int, default=10, help='libx264 CRF of the written prediction (lower = closer to lossless).')
    p.add_argument('--continue-on-error', action='store_true', help='Continue to later edits if one fails; default stops.')
    p.add_argument('--dry-run', action='store_true', help='Validate the selection and inputs without loading the model.')
    p.add_argument('--plan-path', type=Path, help='Optionally write the preflight plan as JSON.')
    args = p.parse_args(argv)
    if args.num_shards < 1 or not 0 <= args.shard_index < args.num_shards:
        p.error('--num-shards must be positive and --shard-index must be in [0, num-shards)')
    if args.limit is not None and args.limit < 1:
        p.error('--limit must be positive')
    return args


def inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def local_file(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or not inside(path, root) or not path.is_file():
        raise ValueError(f'Invalid benchmark file: {relative}')
    return path


def select_edits(args, manifest):
    edits = manifest['edits']
    ids = {e['global_id'] for e in edits}
    if len(ids) != len(edits):
        raise ValueError('Duplicate edit IDs in benchmark manifest')
    root = args.benchmark_root.resolve()
    if args.split_file:
        split = args.split_file if args.split_file.is_absolute() else root / args.split_file
        selected = {line.strip() for line in split.read_text().splitlines() if line.strip()}
        unknown = selected - ids
        if unknown:
            raise ValueError(f'Unknown IDs in split: {sorted(unknown)[:5]}')
        edits = [e for e in edits if e['global_id'] in selected]
    if args.global_id:
        unknown = set(args.global_id) - ids
        if unknown:
            raise ValueError(f'Unknown --global-id: {sorted(unknown)}')
        edits = [e for e in edits if e['global_id'] in set(args.global_id)]
    for arg, key in (('filter_scene', 'scene'), ('filter_property', 'property'),
                     ('filter_category', 'interaction_category'), ('filter_kind', 'edit_kind'),
                     ('filter_timing', 'timing')):
        value = getattr(args, arg)
        if value:
            edits = [e for e in edits if (e.get(key) or ('presence' if key == 'property' else None)) == value]
    if args.limit is not None:
        edits = edits[:args.limit]
    edits = edits[args.shard_index::args.num_shards]
    if not edits:
        raise ValueError('No edits selected; check filters, split or shard')
    return edits


def preflight(args, baseline):
    root = args.benchmark_root.resolve()
    manifest_path = root / 'benchmark_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    edits = select_edits(args, manifest)
    source_map = {r['global_id']: r for r in manifest['sources']}
    verified_sources, plan = {}, []
    for edit in edits:
        for component in (edit['scene'], edit['case_id']):
            if not component or any(c not in SAFE for c in component):
                raise ValueError(f'Unsafe scene/case name: {component!r}')
        if edit['global_id'] != edit['scene'] + '/' + edit['case_id']:
            raise ValueError(f'Inconsistent global_id: {edit["global_id"]}')
        source = source_map[edit['scene'] + '/' + edit['source_case_id']]
        if edit['source_video'] != source['video']:
            raise ValueError(f'Source link mismatch: {edit["global_id"]}')
        path = local_file(root, edit['source_video'])
        prompt = edit['prompts'][args.prompt_flavor][args.prompt_lang]
        if path not in verified_sources:
            if sha256(path) != source['video_sha256']:
                raise ValueError(f'Source video SHA256 mismatch: {path}')
            verified_sources[path] = probe_video(path)
        identity = baseline.request_identity(path, prompt)
        plan.append({'global_id': edit['global_id'], 'source_video': str(path),
                     'source_sha256': identity['source_sha256'], 'prompt': prompt,
                     'source_media': verified_sources[path],
                     'output_relative': f"videos/{edit['scene']}/{edit['case_id']}.mp4"})
    return manifest_path, edits, plan, verified_sources


def main(argv=None) -> int:
    args = parse_args(argv)
    root = args.benchmark_root.resolve()
    predictions = (args.predictions_root or (root.parent.parent / 'predictions' / root.name /
                   f'{args.prompt_flavor}_{args.prompt_lang}')).resolve()
    if inside(predictions, root) or (args.plan_path and inside(args.plan_path, root)):
        raise ValueError('Keep predictions and preflight plans outside the publication directory')
    baseline = JoyAIVideoEditBaseline(
        model_root=args.model_root, dit_ckpt=args.dit_ckpt, resolution=args.resolution,
        num_inference_steps=args.num_inference_steps, seed=args.seed,
        max_temporal_ids=args.max_temporal_ids, low_vram=args.low_vram, crf=args.crf)
    manifest_path, edits, plan, sources = preflight(args, baseline)
    plan_data = {
        'benchmark_root': str(root), 'manifest_sha256': sha256(manifest_path),
        'baseline': baseline.name, 'baseline_config': baseline.config,
        'prompt_flavor': args.prompt_flavor, 'prompt_lang': args.prompt_lang,
        'shard_index': args.shard_index, 'num_shards': args.num_shards,
        'edit_count': len(edits), 'scene_count': len({e['scene'] for e in edits}),
        'source_count': len(sources), 'predictions_root': str(predictions),
        'edits_by_kind': dict(Counter(e['edit_kind'] for e in edits)), 'tasks': plan,
    }
    if args.plan_path:
        atomic_json(args.plan_path, plan_data)
    print(json.dumps({k: v for k, v in plan_data.items() if k != 'tasks'}, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        baseline.check_files()
        print('Preflight passed; model not loaded.')
        return 0
    baseline_root = predictions / baseline.name
    suffix = f'.shard{args.shard_index}of{args.num_shards}' if args.num_shards > 1 else ''
    run_path = baseline_root / f'run_manifest{suffix}.json'
    failures = 0
    with exclusive_lock(run_path.with_suffix('.lock')):
        old = json.loads(run_path.read_text()) if run_path.exists() else {}
        for key in ('manifest_sha256', 'baseline_config', 'prompt_flavor', 'prompt_lang'):
            if old and old.get(key) != plan_data[key]:
                raise ValueError(f'Run configuration changed ({key}); use another predictions root')
        records = {r['global_id']: r for r in old.get('runs', [])}
        meta = {k: v for k, v in plan_data.items() if k != 'tasks'}
        meta.update(execution_host=os.uname().nodename,
                    cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'))

        def flush(**extra):
            atomic_json(run_path, {**meta, **extra, 'runs': list(records.values()), 'updated_at': time.time()})

        todo = [(e, j) for e, j in zip(edits, plan)
                if not ((baseline_root / j['output_relative']).exists()
                        and (baseline_root / j['output_relative']).with_suffix('.task.json').exists())]
        try:
            if todo:
                print(f'Loading JoyAI-Video-Edit ({len(todo)} of {len(edits)} edits need generation)...', flush=True)
                baseline.setup()
                meta['model_load_sec'] = round(baseline.load_sec, 1)
                print(f'Model loaded in {baseline.load_sec:.0f}s', flush=True)
            for index, (edit, job) in enumerate(zip(edits, plan), 1):
                print(f"[{index}/{len(edits)}] {edit['global_id']}", flush=True)
                record = {'global_id': edit['global_id'], 'prompt': job['prompt'],
                          'source_video': job['source_video']}
                try:
                    result = baseline.edit_video(Path(job['source_video']), job['prompt'],
                                                 baseline_root / job['output_relative'], edit_info=edit)
                    reused = result.extra.get('reused_existing')
                    if reused:
                        print(f"[skip existing] {edit['global_id']} (verified prompt, source, config and output hash)", flush=True)
                    else:
                        print(f"  done in {result.elapsed_sec:.1f}s, peak reserved "
                              f"{result.extra['gpu_memory']['peak_reserved_gib']} GiB", flush=True)
                    record.update(status='completed', output_video=str(result.output_video),
                                  elapsed_sec=records.get(edit['global_id'], {}).get('elapsed_sec', 0)
                                  if reused else round(result.elapsed_sec, 3), extra=result.extra)
                except KeyboardInterrupt:
                    record.update(status='interrupted', error='Interrupted; rerun to resume')
                    records[edit['global_id']] = record
                    flush()
                    return 130
                except Exception as exc:
                    record.update(status='failed', error=f'{type(exc).__name__}: {str(exc)[:800]}')
                    failures += 1
                    print(record['error'], file=sys.stderr, flush=True)
                records[edit['global_id']] = record
                flush()
                if failures and not args.continue_on_error:
                    break
        finally:
            baseline.teardown()
    print(f'Run manifest: {run_path}; failures in this invocation: {failures}')
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
