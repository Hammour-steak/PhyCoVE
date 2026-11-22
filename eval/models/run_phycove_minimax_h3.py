#!/usr/bin/env python3
"""Run MiniMax H3 on PhyCoVE source videos and edit prompts (or preflight offline)."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

from baselines.minimax_h3 import (
    MinimaxH3Baseline, atomic_json, exclusive_lock, probe_video, sha256,
)

DEFAULT_BENCH = os.environ.get('PHYCOVE_ROOT')  # release folder; without it --benchmark-root is required


def publication_root(benchmark_root: Path) -> Path:
    root = benchmark_root.resolve()
    if root.name == 'real' and (root.parent / 'benchmark_manifest.json').is_file():
        return root.parent
    return root


def default_predictions_root(benchmark_root: Path, flavor='quantitative', lang='en') -> Path:
    root = benchmark_root.resolve()
    publication = publication_root(root)
    predictions = publication.parent.parent / 'predictions' / publication.name
    if root != publication:
        predictions /= root.relative_to(publication)
    return predictions / f'{flavor}_{lang}'


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--benchmark-root', type=Path, default=DEFAULT_BENCH, required=DEFAULT_BENCH is None,
                   help='Release folder with benchmark_manifest.json (default: $PHYCOVE_ROOT).')
    p.add_argument('--predictions-root', type=Path,
                   help='Parent of minimax_h3/. Default: predictions/PhyCoVE/[real/]<flavor>_<lang>.')
    p.add_argument('--prompt-flavor', choices=('vague', 'quantitative'), default='quantitative')
    p.add_argument('--prompt-lang', choices=('en', 'zh'), default='en')
    p.add_argument('--filter-scene')
    p.add_argument('--filter-property')
    p.add_argument('--filter-category')
    p.add_argument('--filter-kind', choices=('SET', 'DELETE', 'ADD'))
    p.add_argument('--filter-timing', choices=('whole_clip', 'partway'))
    p.add_argument('--split-file', type=Path, help='Relative to the benchmark root, e.g. splits/by_kind/ADD.txt.')
    p.add_argument('--limit', type=int)
    p.add_argument('--num-shards', type=int, default=1)
    p.add_argument('--shard-index', type=int, default=0)
    p.add_argument('--model-id', default=None)
    p.add_argument('--api-base', default=None, help='MiniMax HTTPS base including /v2; also MINIMAX_API_BASE.')
    p.add_argument('--resolution', choices=('768P', '2K'), default='768P')
    p.add_argument('--duration', type=int, choices=range(4, 16), default=4)
    p.add_argument('--ratio', choices=('adaptive', '21:9', '16:9', '4:3', '1:1', '3:4', '9:16'), default='adaptive')
    p.add_argument('--poll-interval', type=float, default=10)
    p.add_argument('--poll-timeout', type=float, default=1800)
    p.add_argument('--request-timeout', type=float, default=120)
    p.add_argument('--retry-failed', action='store_true', help='Explicitly resubmit previously rejected/terminal failed tasks.')
    p.add_argument('--skip-existing', action='store_true', default=True,
                   help='Accepted for compatibility. Matching completed results are always reused after hash verification.')
    p.add_argument('--continue-on-error', action='store_true', help='Continue to later edits if one fails; default stops.')
    p.add_argument('--dry-run', action='store_true', help='Validate all selected inputs without credentials or network calls.')
    p.add_argument('--plan-path', type=Path, help='Optionally write the offline preflight plan as JSON.')
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


def preflight(args, baseline):
    root = args.benchmark_root.resolve()
    manifest_path = root / 'benchmark_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    edits = manifest['edits']
    if len({e['global_id'] for e in edits}) != len(edits):
        raise ValueError('Duplicate edit IDs in benchmark manifest')
    if args.split_file:
        split = args.split_file if args.split_file.is_absolute() else root / args.split_file
        selected = set(split.read_text().splitlines())
        unknown = selected - {e['global_id'] for e in edits}
        if unknown:
            raise ValueError(f'Unknown IDs in split: {sorted(unknown)[:5]}')
        edits = [e for e in edits if e['global_id'] in selected]
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
    source_map = {r['global_id']: r for r in manifest['sources']}
    verified_sources = {}
    plan = []
    for edit in edits:
        for component in (edit['scene'], edit['case_id']):
            if not component or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in component):
                raise ValueError(f'Unsafe scene/case name: {component!r}')
        if edit['global_id'] != edit['scene'] + '/' + edit['case_id']:
            raise ValueError(f'Inconsistent global_id: {edit["global_id"]}')
        source = source_map[edit['scene'] + '/' + edit['source_case_id']]
        if edit['source_video'] != source['video']:
            raise ValueError(f'Source link mismatch: {edit["global_id"]}')
        path = local_file(root, edit['source_video'])
        prompt = edit['prompts'][args.prompt_flavor][args.prompt_lang]
        if path not in verified_sources:
            media = probe_video(path)
            if media['codec'] not in ('h264', 'hevc') or not 2 <= media['duration_sec'] <= 15:
                raise ValueError(f'H3 requires H.264/H.265, 2..15 seconds: {path}')
            if not 23.97 <= media['fps'] <= 60:
                raise ValueError(f'H3 reference video requires 23.976..60 FPS: {path}')
            if sha256(path) != source['video_sha256']:
                raise ValueError(f'Source video SHA256 mismatch: {path}')
            verified_sources[path] = media
        identity = baseline.request_identity(path, prompt)
        # Validate payload size exactly, but never persist the source's Base64 bytes.
        baseline.build_payload(path, prompt)
        plan.append({'global_id': edit['global_id'], 'source_video': str(path),
                     'source_sha256': identity['source_sha256'], 'prompt': prompt,
                     'output_relative': f"videos/{edit['scene']}/{edit['case_id']}.mp4"})
    return manifest_path, edits, plan, verified_sources


def main(argv=None) -> int:
    args = parse_args(argv)
    root = args.benchmark_root.resolve()
    predictions = (args.predictions_root or default_predictions_root(
        root, args.prompt_flavor, args.prompt_lang)).resolve()
    publication = publication_root(root)
    if inside(predictions, publication) or (args.plan_path and inside(args.plan_path, publication)):
        raise ValueError('Keep predictions and preflight plans outside the publication directory')
    baseline = MinimaxH3Baseline(**{k: getattr(args, k) for k in (
        'model_id', 'api_base', 'resolution', 'duration', 'ratio', 'poll_interval',
        'poll_timeout', 'request_timeout', 'retry_failed')})
    manifest_path, edits, plan, sources = preflight(args, baseline)
    plan_data = {
        'benchmark_root': str(root), 'manifest_sha256': sha256(manifest_path),
        'benchmark_name': json.loads(manifest_path.read_text()).get('benchmark_name'),
        'data_subset': root.relative_to(publication).as_posix() if root != publication else 'root',
        'baseline': baseline.name, 'baseline_config': baseline.config,
        'prompt_flavor': args.prompt_flavor, 'prompt_lang': args.prompt_lang,
        'shard_index': args.shard_index, 'num_shards': args.num_shards,
        'edit_count': len(edits), 'scene_count': len({e['scene'] for e in edits}),
        'source_count': len(sources), 'predictions_root': str(predictions),
        'edits_by_kind': dict(Counter(e['edit_kind'] for e in edits)), 'tasks': plan,
    }
    if args.plan_path:
        atomic_json(args.plan_path, plan_data)
    print(json.dumps({k: v for k, v in plan_data.items() if k != 'tasks'}, ensure_ascii=False, indent=2))
    if args.dry_run:
        print('Offline preflight passed; no API calls or generation tasks submitted.')
        return 0
    baseline.setup()
    baseline_root = predictions / baseline.name
    suffix = f'.shard{args.shard_index}of{args.num_shards}' if args.num_shards > 1 else ''
    run_path = baseline_root / f'run_manifest{suffix}.json'
    failures = 0
    try:
        with exclusive_lock(run_path.with_suffix('.lock')):
            old = json.loads(run_path.read_text()) if run_path.exists() else {}
            for key in ('manifest_sha256', 'baseline_config', 'prompt_flavor', 'prompt_lang'):
                if old and old.get(key) != plan_data[key]:
                    raise ValueError(f'Run configuration changed ({key}); use another predictions root')
            records = {r['global_id']: r for r in old.get('runs', [])}

            def flush():
                atomic_json(run_path, {**{k: v for k, v in plan_data.items() if k != 'tasks'},
                                       'runs': list(records.values()), 'updated_at': time.time()})

            for index, (edit, job) in enumerate(zip(edits, plan), 1):
                print(f"[{index}/{len(edits)}] {edit['global_id']}", flush=True)
                record = {'global_id': edit['global_id'], 'prompt': job['prompt'],
                          'source_video': job['source_video']}
                try:
                    result = baseline.edit_video(Path(job['source_video']), job['prompt'],
                                                 baseline_root / job['output_relative'], edit_info=edit)
                    if result.extra.get('reused_existing'):
                        print(f"[skip existing] {edit['global_id']} (verified prompt, source, config and output hash)", flush=True)
                    record.update(status='completed', output_video=str(result.output_video),
                                  elapsed_sec=records.get(edit['global_id'], {}).get('elapsed_sec', 0)
                                  if result.extra.get('reused_existing') else round(result.elapsed_sec, 3),
                                  extra=result.extra)
                except KeyboardInterrupt:
                    record.update(status='interrupted', error='Interrupted; rerun to resume saved task')
                    records[edit['global_id']] = record
                    flush()
                    return 130
                except Exception as exc:
                    record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
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
