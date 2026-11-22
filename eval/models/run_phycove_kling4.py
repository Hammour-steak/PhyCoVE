#!/usr/bin/env python3
"""Run official Kling 4.0 on PhyCoVE source videos and selected edit prompts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import quote

from baselines.kling4 import Kling4Baseline
from kling4_client import atomic_json, exclusive_lock, sha256

DEFAULT_BENCH = os.environ.get('PHYCOVE_ROOT')  # release folder; without it --benchmark-root is required
DEFAULT_SOURCE_URL_TEMPLATE = 'https://hf-mirror.com/datasets/ccmoony/PhyCoVE/resolve/main/{source_video}'


def publication_root(benchmark_root: Path) -> Path:
    """Locate the enclosing release when selecting its nested real subset."""
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


def source_url_template(benchmark_root: Path, template=None) -> str:
    """Default URLs are relative to the HF release, not the subset manifest."""
    if template is not None:
        return template
    root = benchmark_root.resolve()
    publication = publication_root(root)
    if root == publication:
        return DEFAULT_SOURCE_URL_TEMPLATE
    prefix = quote(root.relative_to(publication).as_posix(), safe='/')
    return DEFAULT_SOURCE_URL_TEMPLATE.replace('{source_video}', prefix + '/{source_video}')


def baseline_kwargs(args):
    kwargs = {key: getattr(args, key) for key in (
        'api_base', 'resolution', 'duration', 'audio', 'poll_interval', 'poll_timeout')}
    kwargs['source_url_template'] = source_url_template(args.benchmark_root, args.source_url_template)
    return kwargs


def dataset_metadata(root, predictions):
    publication = publication_root(root)
    manifest = json.loads((root / 'benchmark_manifest.json').read_text())
    return {'benchmark_name': manifest.get('benchmark_name', publication.name),
            'data_subset': root.relative_to(publication).as_posix() if root != publication else 'root',
            'predictions_root': str(predictions)}


def inside(path, root):
    return path.resolve().is_relative_to(root.resolve())


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark-root', type=Path, default=DEFAULT_BENCH, required=DEFAULT_BENCH is None,
                   help='Release folder with benchmark_manifest.json (default: $PHYCOVE_ROOT).')
    parser.add_argument('--predictions-root', type=Path)
    parser.add_argument('--filter-scene')
    parser.add_argument('--case-id')
    parser.add_argument('--split-file', type=Path)
    parser.add_argument('--limit', type=int, default=1, help='At most this many cases; default 1')
    parser.add_argument('--prompt-flavor', choices=('quantitative', 'vague'), default='quantitative')
    parser.add_argument('--prompt-lang', choices=('en', 'zh'), default='en')
    parser.add_argument('--source-url-template',
                        help='Custom HTTPS template containing {source_video}; the default automatically includes real/ for the real subset')
    parser.add_argument('--resolution', choices=('720p', '1080p'), default='720p')
    parser.add_argument('--duration', type=int, default=4)
    parser.add_argument('--audio', choices=('native', 'original'), default='native')
    parser.add_argument('--api-base')
    parser.add_argument('--poll-interval', type=float, default=10)
    parser.add_argument('--poll-timeout', type=float, default=1800)
    parser.add_argument('--max-units', type=float, default=6, help='Upper bound on selected tasks at published unit rates')
    parser.add_argument('--dry-run', action='store_true', help='Offline validation; no key or API calls')
    parser.add_argument('--plan-path', type=Path)
    args = parser.parse_args(argv)
    if args.limit < 1 or args.max_units <= 0:
        parser.error('--limit and --max-units must be positive')
    return args


def preflight(args, baseline):
    root = args.benchmark_root.resolve()
    manifest_path = root / 'benchmark_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    all_edits = manifest['edits']
    if len({row['global_id'] for row in all_edits}) != len(all_edits):
        raise ValueError('Duplicate edit IDs')
    edits = all_edits
    if args.split_file:
        path = args.split_file if args.split_file.is_absolute() else root / args.split_file
        selected = set(path.read_text().splitlines())
        if selected - {row['global_id'] for row in all_edits}:
            raise ValueError('Split contains unknown edit IDs')
        edits = [row for row in edits if row['global_id'] in selected]
    if args.filter_scene:
        edits = [row for row in edits if row['scene'] == args.filter_scene]
    if args.case_id:
        edits = [row for row in edits if row['case_id'] == args.case_id]
    edits = edits[:args.limit]
    if not edits:
        raise ValueError('No edits selected')
    sources = {row['global_id']: row for row in manifest['sources']}
    tasks = []
    for edit in edits:
        if edit['global_id'] != edit['scene'] + '/' + edit['case_id']:
            raise ValueError('Inconsistent edit ID')
        for component in (edit['scene'], edit['case_id']):
            if not component or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in component):
                raise ValueError('Unsafe scene or case name')
        source = sources[edit['scene'] + '/' + edit['source_case_id']]
        path = root / edit['source_video']
        if (Path(edit['source_video']).is_absolute() or not inside(path, root)
                or not path.is_file() or edit['source_video'] != source['video']):
            raise ValueError('Invalid source path')
        prompt = edit['prompts'][args.prompt_flavor][args.prompt_lang]
        identity = baseline.client.identity(path, prompt)
        if identity['source_sha256'] != source['video_sha256']:
            raise ValueError(f'Source SHA256 differs from benchmark: {edit["global_id"]}')
        tasks.append({'global_id': edit['global_id'], 'source_video': str(path),
                      'source_sha256': identity['source_sha256'], 'prompt': prompt,
                      'estimated_units': baseline.client.estimate_units(identity['source_metadata']['duration_sec']),
                      'output_relative': f"videos/{edit['scene']}/{edit['case_id']}.mp4"})
    return manifest_path, edits, tasks


def main(argv=None):
    args = parse_args(argv)
    root = args.benchmark_root.resolve()
    predictions = (args.predictions_root or default_predictions_root(
        root, args.prompt_flavor, args.prompt_lang)).resolve()
    publication = publication_root(root)
    if inside(predictions, publication) or (args.plan_path and inside(args.plan_path, publication)):
        raise ValueError('Keep predictions and plans outside the publication directory')
    baseline = Kling4Baseline(**baseline_kwargs(args))
    manifest_path, edits, tasks = preflight(args, baseline)
    plan = {**dataset_metadata(root, predictions),
            'benchmark_root': str(root), 'manifest_sha256': sha256(manifest_path),
            'baseline': baseline.name, 'baseline_config': baseline.config,
            'prompt_flavor': args.prompt_flavor, 'prompt_lang': args.prompt_lang,
            'estimated_units': round(sum(task['estimated_units'] for task in tasks), 6),
            'edit_count': len(tasks), 'pricing_source': 'https://kling.ai/dev/pricing', 'tasks': tasks}
    if args.plan_path:
        atomic_json(args.plan_path, plan)
    print(json.dumps({k: v for k, v in plan.items() if k != 'tasks'}, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        print('Offline preflight passed; no API calls or paid tasks submitted.')
        return 0
    if plan['estimated_units'] > args.max_units:
        raise ValueError('Selected cases exceed --max-units; reduce selection or explicitly increase the limit')
    out_root = predictions / baseline.name
    run_path = out_root / 'run_manifest.json'
    failures = 0
    with exclusive_lock(run_path.with_suffix('.lock')):
        old = json.loads(run_path.read_text()) if run_path.exists() else {}
        for key in ('manifest_sha256', 'baseline_config', 'prompt_flavor', 'prompt_lang'):
            if old and old.get(key) != plan[key]:
                raise ValueError(f'Run configuration changed ({key}); use another predictions root')
        records = {row['global_id']: row for row in old.get('runs', [])}
        baseline.setup()
        try:
            for index, (edit, job) in enumerate(zip(edits, tasks), 1):
                print(f"[{index}/{len(tasks)}] {edit['global_id']}", flush=True)
                record = dict(job)
                try:
                    result = baseline.edit_video(Path(job['source_video']), job['prompt'],
                                                 out_root / job['output_relative'], edit_info=edit)
                    record.update(status='completed', output_video=str(result.output_video), extra=result.extra,
                                  elapsed_sec=records.get(edit['global_id'], {}).get('elapsed_sec', 0)
                                  if result.extra['reused_existing'] else result.elapsed_sec)
                except KeyboardInterrupt:
                    record.update(status='interrupted', error='Rerun the same command to resume')
                    raise
                except Exception as exc:
                    record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                    print(record['error'], file=sys.stderr, flush=True)
                    failures += 1
                finally:
                    records[edit['global_id']] = record
                    atomic_json(run_path, {**{k: v for k, v in plan.items() if k != 'tasks'},
                                           'runs': list(records.values()), 'updated_at': time.time()})
                if failures:
                    break
        finally:
            baseline.teardown()
    print(f'Run manifest: {run_path}; failures: {failures}')
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
