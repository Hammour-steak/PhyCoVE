#!/usr/bin/env python3
"""Run a fixed Kling 4.0 benchmark split with at most five concurrent jobs.

Each worker owns its client and HTTP sessions. Existing verified outputs are reused.
The split and batch ID are persistent: rerunning resumes the same selected cases.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from decimal import Decimal
import argparse
import json
from pathlib import Path
import re
import sys
import threading
import time

from baselines.kling4 import Kling4Baseline
from kling4_client import atomic_json, exclusive_lock, sha256
from run_phycove_kling4 import (parse_args as base_args, preflight, inside,
                               baseline_kwargs, default_predictions_root,
                               publication_root, dataset_metadata)


def load_state(output):
    path = Path(output).with_suffix('.task.json')
    return json.loads(path.read_text()) if path.exists() else {}


def run_job(edit, job, output, kwargs, stop_new, credit=None):
    """Resume accepted tasks after transient failures, without another paid POST."""
    record = dict(job)
    before = load_state(output)
    if stop_new.is_set() and not before.get('task_id'):
        return dict(record, status='deferred', error='New submissions paused after an unresolved task')
    baseline = Kling4Baseline(**kwargs)
    try:
        baseline.setup()
        if credit and before.get('phase') != 'completed' and not before.get('task_id'):
            credit.reserve(job['global_id'], job['estimated_units'], stop_new)
        for attempt in range(3):
            try:
                result = baseline.edit_video(Path(job['source_video']), job['prompt'], output, edit_info=edit)
                state = load_state(output)
                record.update(status='completed', output_video=str(output), extra=result.extra,
                              elapsed_sec=state.get('elapsed_sec', result.elapsed_sec),
                              newly_accepted=bool(state.get('task_id') and not before.get('task_id')))
                return record
            except Exception as exc:
                state = load_state(output)
                phase = state.get('phase')
                record.update(status='failed', error=f'{type(exc).__name__}: {exc}',
                              checkpoint_phase=phase, task_id=state.get('task_id'))
                if phase == 'rejected' and state.get('submit_response', {}).get('code') == 1102:
                    if credit:
                        credit.backend_not_ready()
                    else:
                        stop_new.set()
                # Rejected and terminal failed tasks are never automatically resubmitted.
                if phase in ('rejected', 'failed'):
                    break
                if attempt < 2:
                    print(f"[resume {attempt + 1}/2] {job['global_id']}: {record['error']}", flush=True)
                    time.sleep(10)
                    continue
                # Do not fill this slot with a fresh task while a provider task may still run.
                if phase in ('submitting', 'accepted'):
                    stop_new.set()
        return record
    finally:
        if credit:
            state = load_state(output)
            phase = state.get('phase')
            consumed = None
            if phase in ('prepared', 'rejected') or not state:
                consumed = 0
            elif phase in ('completed', 'failed'):
                charges = state.get('task', {}).get('billing')
                if charges:
                    consumed = sum((Decimal(str(item.get('amount', 0))) for item in charges), Decimal(0))
            credit.finish(job['global_id'], consumed)
        baseline.teardown()


def execute(jobs, worker, workers=5):
    """Bounded worker pool; every future stays associated with its original case."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, *item): item[1]['global_id'] for item in jobs}
        while futures:
            finished, _ = wait(futures, timeout=10, return_when=FIRST_COMPLETED)
            for future in finished:
                global_id = futures.pop(future)
                try:
                    record = future.result()
                except Exception as exc:
                    record = {'global_id': global_id, 'status': 'failed',
                              'error': f'{type(exc).__name__}: {exc}'}
                if record.get('global_id') != global_id:
                    raise RuntimeError('Worker returned a different case ID')
                yield record


def prioritize_existing_tasks(jobs):
    # Existing provider jobs already occupy slots even while this process is stopped.
    return sorted(jobs, key=lambda item: 0 if load_state(item[2]).get('phase')
                  in ('accepted', 'submitting') else 1)


def main(argv=None):
    parallel = argparse.ArgumentParser(add_help=False)
    parallel.add_argument('--workers', type=int, choices=range(1, 6), default=5)
    parallel.add_argument('--batch-id', required=True)
    parallel.add_argument('--watch-credit', action='store_true', help='Wait for sufficient resource-pack balance before new submissions')
    settings, remaining = parallel.parse_known_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', settings.batch_id):
        raise ValueError('Use a simple alphanumeric batch ID')
    args = base_args(remaining)
    if not args.split_file:
        raise ValueError('Provide a fixed --split-file; do not resample on resume')
    root = args.benchmark_root.resolve()
    predictions = (args.predictions_root or default_predictions_root(
        root, args.prompt_flavor, args.prompt_lang)).resolve()
    publication = publication_root(root)
    if inside(predictions, publication) or (args.plan_path and inside(args.plan_path, publication)):
        raise ValueError('Keep predictions and plans outside the publication directory')
    kwargs = baseline_kwargs(args)
    baseline = Kling4Baseline(**kwargs)
    manifest_path, edits, tasks = preflight(args, baseline)
    out_root = predictions / baseline.name
    run_path = out_root / 'run_manifest.json'
    batch_path = out_root / 'batches' / settings.batch_id / 'batch_manifest.json'
    plan = {**dataset_metadata(root, predictions),
            'benchmark_root': str(root), 'manifest_sha256': sha256(manifest_path),
            'baseline': baseline.name, 'baseline_config': baseline.config,
            'prompt_flavor': args.prompt_flavor, 'prompt_lang': args.prompt_lang,
            'batch_id': settings.batch_id, 'workers': settings.workers,
            'watch_credit': settings.watch_credit,
            'estimated_units': round(sum(job['estimated_units'] for job in tasks), 6),
            'edit_count': len(tasks), 'tasks': tasks,
            'pricing_source': 'https://kling.ai/dev/pricing'}
    if args.plan_path:
        atomic_json(args.plan_path, plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        print('Offline preflight passed; no API calls or paid tasks submitted.')
        return 0
    if not 0 < plan['estimated_units'] <= args.max_units:
        raise ValueError('Selected cases exceed --max-units')
    with exclusive_lock(run_path.with_suffix('.lock')):
        old = json.loads(run_path.read_text()) if run_path.exists() else {}
        old_batch = json.loads(batch_path.read_text()) if batch_path.exists() else {}
        for key in ('manifest_sha256', 'baseline_config', 'prompt_flavor', 'prompt_lang'):
            if old and old.get(key) != plan[key]:
                raise ValueError(f'Run configuration changed ({key}); use another predictions root')
        for key in ('manifest_sha256', 'baseline_config', 'prompt_flavor', 'prompt_lang', 'tasks'):
            if old_batch and old_batch.get(key) != plan[key]:
                raise ValueError(f'Batch selection/configuration changed ({key}); preserve its fixed split')
        records = {row['global_id']: row for row in old.get('runs', [])}
        batch_records = {row['global_id']: row for row in old_batch.get('runs', [])}
        stop_new = threading.Event()
        credit = None
        if settings.watch_credit:
            from kling4_credit import CreditGuard
            holds = {}
            for task in tasks:
                saved = load_state(out_root / task['output_relative'])
                if (saved.get('phase') in ('accepted', 'submitting')
                        and saved.get('task', {}).get('status') not in ('succeeded', 'failed')):
                    holds[task['global_id']] = task['estimated_units']
            credit = CreditGuard(baseline.client.api_base, batch_path.parent / 'credit_state.json',
                                 existing_holds=holds)

        def flush():
            atomic_json(batch_path, {**plan, 'runs': list(batch_records.values()),
                                    'new_submissions_paused': stop_new.is_set(), 'updated_at': time.time()})
            total = sum(row.get('estimated_units', 0) for row in records.values())
            atomic_json(run_path, {
                **{key: plan[key] for key in ('benchmark_root', 'benchmark_name', 'data_subset',
                   'predictions_root', 'manifest_sha256', 'baseline',
                   'baseline_config', 'prompt_flavor', 'prompt_lang', 'pricing_source')},
                'edit_count': len(records), 'estimated_units': round(total, 6),
                'runs': list(records.values()), 'updated_at': time.time()})

        flush()  # Persist the fixed batch before any paid submission.
        jobs = [(edit, job, out_root / job['output_relative'], kwargs, stop_new, credit)
                for edit, job in zip(edits, tasks)]
        jobs = prioritize_existing_tasks(jobs)
        try:
            for result in execute(jobs, run_job, workers=settings.workers):
                global_id = result['global_id']
                batch_records[global_id] = records[global_id] = result
                flush()
                print(f"[{len(batch_records)}/{len(tasks)}] {global_id}: {result['status']}", flush=True)
        finally:
            if credit:
                credit.close()
        failed = sum(row.get('status') != 'completed' for row in batch_records.values())
        print(f'Batch manifest: {batch_path}; failures/deferred: {failed}', flush=True)
        return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
