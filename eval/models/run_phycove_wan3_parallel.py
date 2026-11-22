#!/usr/bin/env python3
"""Durable parallel PhyCoVE Wan3 queue with bounded concurrency and submission pacing."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

import requests

from baselines.wan3 import (
    Wan3Baseline, SubmissionRejected, atomic_json, exclusive_lock, sha256,
)
from run_phycove_wan3 import (
    parse_args as base_args, preflight, inside, publication_root,
    default_predictions_root, benchmark_metadata,
)


def rate_limited(exc):
    return bool(re.search(r'HTTP 429|throttl|rate.?limit|too many|concurren', str(exc), re.I))


def fatal_rejection(exc):
    return not rate_limited(exc) and bool(re.search(
        r'HTTP (401|402|403)|arrear|insufficient|balance|credit|InvalidApiKey|AccessDenied|FreeTierOnly',
        str(exc), re.I))


class SubmissionPaused(SubmissionRejected):
    pass


class Governor:
    def __init__(self, initial=16, maximum=32, submit_interval=0.25,
                 query_interval=0.1, cooldown=30):
        self.condition = threading.Condition()
        self.target, self.maximum = initial, maximum
        self.active = self.accepted = self.rate_events = 0
        self.submit_interval, self.query_interval = submit_interval, query_interval
        self.cooldown = cooldown
        self.next_submit = self.next_query = self.pause_until = self.last_rate = 0.0
        self.fatal = None
        self.uploads = {}
        self.upload_locks = {}
        self.upload_cache_path = None

    def acquire(self, known_task=False):
        with self.condition:
            while True:
                if self.fatal and not known_task:
                    raise SubmissionPaused(self.fatal)
                delay = self.pause_until - time.monotonic()
                if self.active < self.target and delay <= 0:
                    self.active += 1
                    return
                self.condition.wait(timeout=max(0.01, min(1, delay)) if delay > 0 else 1)

    def release(self):
        with self.condition:
            self.active -= 1
            self.condition.notify_all()

    def slot(self, kind):
        with self.condition:
            while True:
                if kind == 'submit' and self.fatal:
                    raise SubmissionPaused(self.fatal)
                now = time.monotonic()
                until = max(self.next_submit, self.pause_until) if kind == 'submit' else self.next_query
                if until <= now:
                    if kind == 'submit':
                        self.next_submit = now + self.submit_interval
                    else:
                        self.next_query = now + self.query_interval
                    return
                self.condition.wait(timeout=min(1, until - now))

    def accepted_task(self):
        with self.condition:
            self.accepted += 1
            if self.accepted % 8 == 0 and time.monotonic() - self.last_rate > 180:
                self.target = min(self.maximum, self.target + 8)
                self.condition.notify_all()

    def throttled(self, query=False):
        with self.condition:
            self.rate_events += 1
            self.last_rate = time.monotonic()
            if query:
                self.query_interval = min(6, max(0.1, self.query_interval * 1.5))
                self.next_query = max(self.next_query, self.last_rate + self.cooldown)
            else:
                self.target = max(2, self.target // 2)
                self.submit_interval = min(30, max(0.1, self.submit_interval * 1.5))
                self.pause_until = max(self.pause_until, self.last_rate + self.cooldown)
            self.condition.notify_all()

    def stop_new(self, reason):
        with self.condition:
            self.fatal = reason
            self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            return {'target_concurrency': self.target, 'max_concurrency': self.maximum,
                    'active_workers': self.active, 'new_tasks_accepted': self.accepted,
                    'rate_limit_events': self.rate_events,
                    'submit_interval_sec': round(self.submit_interval, 2),
                    'query_interval_sec': round(self.query_interval, 2),
                    'uploads_cached': len(self.uploads),
                    'provider_documented_running_limit': 5,
                    'submission_pause_reason': self.fatal}


class PacedSession(requests.Session):
    def __init__(self, governor):
        super().__init__()
        self.governor = governor

    def request(self, method, *args, **kwargs):
        if method.upper() == 'GET':
            self.governor.slot('query')
        response = super().request(method, *args, **kwargs)
        if method.upper() == 'GET' and response.status_code == 429:
            self.governor.throttled(query=True)
        return response


class GovernedBaseline(Wan3Baseline):
    def __init__(self, governor, **kwargs):
        self.governor = governor
        super().__init__(**kwargs)

    def setup(self):
        super().setup()
        original = self._session
        paced = PacedSession(self.governor)
        paced.headers.update(original.headers)
        paced.proxies.update(original.proxies)
        paced.trust_env = original.trust_env
        self._session = paced
        original.close()

    def upload_source(self, source):
        digest = sha256(source)
        with self.governor.condition:
            lock = self.governor.upload_locks.setdefault(digest, threading.Lock())
        with lock:
            cached = self.governor.uploads.get(digest)
            if cached and time.time() - cached['uploaded_at'] < 46 * 3600:
                return cached['url']
            url = super().upload_source(source)
            with self.governor.condition:
                self.governor.uploads[digest] = {'url': url, 'uploaded_at': time.time()}
                if self.governor.upload_cache_path:
                    atomic_json(self.governor.upload_cache_path, self.governor.uploads)
            return url

    def _create_task(self, body):
        self.governor.slot('submit')
        task_id = super()._create_task(body)
        self.governor.accepted_task()
        return task_id


def checkpoint_for(output):
    path = output.with_suffix('.task.json')
    return json.loads(path.read_text()) if path.exists() else {}


def execute_job(edit, job, root, governor, kwargs, factory=GovernedBaseline):
    output = root / job['output_relative']
    record = {'global_id': edit['global_id'], 'prompt': job['prompt'],
              'source_video': job['source_video']}
    client = factory(governor, **kwargs)
    client.setup()
    retries = 0
    try:
        while True:
            acquired = False
            try:
                state = checkpoint_for(output)
                if not (output.exists() and state.get('status') == 'completed'):
                    governor.acquire(known_task=bool(state.get('task_id')))
                    acquired = True
                # Only an explicit rate rejection with no task ID permits a new POST.
                client.retry_failed = (state.get('status') == 'rejected' and not state.get('task_id')
                                       and (rate_limited(state.get('error', '')) or fatal_rejection(state.get('error', ''))))
                result = client.edit_video(Path(job['source_video']), job['prompt'], output, edit_info=edit)
                record.update(status='completed', output_video=str(output),
                              elapsed_sec=round(result.elapsed_sec, 3), extra=result.extra)
                if result.extra.get('reused_existing'):
                    state = checkpoint_for(output)
                    record['elapsed_sec'] = round(max(0, state.get('completed_at', 0) - state.get('created_at', 0)), 3)
                return record
            except SubmissionPaused as exc:
                record.update(status='not_started', error=str(exc))
                return record
            except Exception as exc:
                state = checkpoint_for(output)
                if fatal_rejection(exc):
                    governor.stop_new(str(exc))
                elif rate_limited(exc) and retries < 8:
                    governor.throttled(query=bool(state.get('task_id')))
                    retries += 1
                    continue
                elif (state.get('task_id') and state.get('status') not in
                      ('FAILED', 'CANCELED', 'UNKNOWN', 'completed')
                      and isinstance(exc, (requests.RequestException, TimeoutError)) and retries < 4):
                    # Resume the known paid task; a download/poll failure never regenerates.
                    retries += 1
                    time.sleep(10)
                    continue
                record.update(status='needs_reconciliation' if state.get('status') in
                              ('submitting', 'submission_unknown') and not state.get('task_id') else 'failed',
                              error=f'{type(exc).__name__}: {str(exc)[:600]}', task_id=state.get('task_id'))
                return record
            finally:
                if acquired:
                    governor.release()
    finally:
        client.teardown()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--benchmark-root', type=Path, default=os.environ.get('PHYCOVE_ROOT'),
                   required=not os.environ.get('PHYCOVE_ROOT'),
                   help='Release folder with benchmark_manifest.json (default: $PHYCOVE_ROOT).')
    p.add_argument('--predictions-root', type=Path)
    p.add_argument('--job-directory', type=Path, required=True)
    p.add_argument('--workers', type=int, default=32)
    p.add_argument('--initial-concurrency', type=int, default=16)
    p.add_argument('--submit-interval', type=float, default=0.25)
    p.add_argument('--query-interval', type=float, default=0.1)
    p.add_argument('--poll-interval', type=float, default=20)
    p.add_argument('--prompt-flavor', choices=('quantitative', 'vague'), default='quantitative')
    p.add_argument('--prompt-lang', choices=('en', 'zh'), default='en')
    p.add_argument('--dry-run', action='store_true', help='Preflight all cases and verify skip list without API calls.')
    p.add_argument('--max-cost-cny', type=float, default=2200, help='Maximum estimated remaining Beijing list-price cost.')
    args = p.parse_args(argv)
    if not 1 <= args.initial_concurrency <= args.workers <= 64:
        p.error('Require 1 <= initial-concurrency <= workers <= 64')
    if min(args.submit_interval, args.query_interval, args.poll_interval) <= 0:
        p.error('Intervals must be positive')
    return args


def main(argv=None):
    args = parse_args(argv)
    base = base_args(['--benchmark-root', str(args.benchmark_root),
                      '--prompt-flavor', args.prompt_flavor, '--prompt-lang', args.prompt_lang,
                      '--poll-interval', str(args.poll_interval)])
    base.limit = None  # This entry point deliberately selects the full benchmark.
    if args.predictions_root:
        base.predictions_root = args.predictions_root
    predictions = (base.predictions_root or default_predictions_root(
        base.benchmark_root, base.prompt_flavor, base.prompt_lang)).resolve()
    publication = publication_root(base.benchmark_root)
    if inside(predictions, publication) or inside(args.job_directory, publication):
        raise ValueError('Keep predictions and job logs outside publication data')
    kwargs = {key: getattr(base, key) for key in ('model_id', 'api_base', 'resolution', 'duration',
              'ratio', 'poll_interval', 'poll_timeout', 'request_timeout', 'seed')}
    manifest_path, edits, plan, sources = preflight(base, Wan3Baseline(**kwargs))
    root = predictions / 'wan3_0_video'
    verified_completed = []
    for edit, job in zip(edits, plan):
        output = root / job['output_relative']
        state = checkpoint_for(output)
        if state.get('status') == 'completed' and output.is_file():
            if state['identity'] != Wan3Baseline(**kwargs).request_identity(Path(job['source_video']), job['prompt']):
                raise ValueError('Existing source/prompt/config mismatch: ' + edit['global_id'])
            if sha256(output) != state.get('output_sha256'):
                raise ValueError('Existing output hash mismatch: ' + edit['global_id'])
            verified_completed.append(edit['global_id'])
    remaining_cost = round(sum(job['estimated_list_cost_cny'] for job in plan
                               if job['global_id'] not in verified_completed), 6)
    context = benchmark_metadata(base.benchmark_root)
    plan_data = {**context, 'benchmark_root': str(base.benchmark_root.resolve()),
                 'predictions_root': str(predictions), 'baseline': 'wan3_0_video',
                 'manifest_sha256': sha256(manifest_path),
                 'total': len(edits), 'source_count': len(sources),
                 'edits_by_kind': dict(Counter(e['edit_kind'] for e in edits)),
                 'verified_completed': verified_completed,
                 'remaining': len(edits) - len(verified_completed),
                 'remaining_list_cost_cny': remaining_cost, 'workers': args.workers,
                 'initial_concurrency': args.initial_concurrency,
                 'provider_documented_running_limit': 5,
                 'provider_documented_queue_limit': 500,
                 'config': Wan3Baseline(**kwargs).config, 'tasks': plan}
    atomic_json(args.job_directory / 'plan.json', plan_data)
    print(json.dumps({k:v for k,v in plan_data.items() if k != 'tasks'}, indent=2), flush=True)
    if args.dry_run:
        return 0
    if not 0 <= remaining_cost <= args.max_cost_cny:
        raise ValueError('Estimated remaining list price exceeds --max-cost-cny')
    governor = Governor(args.initial_concurrency, args.workers, args.submit_interval, args.query_interval)
    governor.upload_cache_path = root / 'source_upload_cache.json'
    if governor.upload_cache_path.exists():
        governor.uploads = json.loads(governor.upload_cache_path.read_text())

    run_path = root / 'run_manifest.json'
    started = time.time()
    metadata = {**context, 'baseline': 'wan3_0_video', 'baseline_config': Wan3Baseline(**kwargs).config,
                'benchmark_root': str(base.benchmark_root.resolve()), 'predictions_root': str(predictions),
                'manifest_sha256': sha256(manifest_path), 'prompt_flavor': base.prompt_flavor,
                'prompt_lang': base.prompt_lang, 'num_shards': 1, 'shard_index': 0,
                'scene_count': len(sources), 'source_count': len(sources), 'edit_count': len(edits),
                'started_at': started, 'execution_host': os.uname().nodename,
                'job_directory': str(args.job_directory.resolve()),
                'remaining_list_cost_cny_at_start': remaining_cost,
                'verified_completed_at_start': len(verified_completed)}
    with exclusive_lock(run_path.with_suffix('.lock')):
        old = json.loads(run_path.read_text()) if run_path.exists() else {}
        for key in ('manifest_sha256', 'baseline_config', 'prompt_flavor', 'prompt_lang'):
            if old and old.get(key) != metadata[key]:
                raise ValueError(f'Run configuration changed: {key}')
        records = {r['global_id']: r for r in old.get('runs', [])}

        def flush(finished=False):
            state_counts = Counter()
            for job in plan:
                state = checkpoint_for(root / job['output_relative'])
                state_counts[state.get('status', 'pending')] += 1
            progress = {**metadata, **governor.snapshot(), 'state_counts': dict(state_counts),
                        'completed': state_counts['completed'], 'total': len(edits),
                        'remaining': len(edits) - state_counts['completed'],
                        'updated_at': time.time(), 'finished': finished}
            progress['status'] = ('completed' if state_counts['completed'] == len(edits)
                                  else 'blocked_account' if finished and governor.fatal else 'stopped_with_errors' if finished else 'draining_account_block' if governor.fatal else 'running')
            atomic_json(args.job_directory / 'progress.json', progress)
            atomic_json(root / 'full_run_progress.json', progress)
            atomic_json(run_path, {**metadata, 'runs': list(records.values()),
                                  'parallel_progress': progress, 'updated_at': time.time()})
            print(json.dumps({k: progress[k] for k in ('completed', 'total', 'state_counts',
                  'target_concurrency', 'active_workers', 'new_tasks_accepted', 'rate_limit_events', 'finished')}), flush=True)

        flush()
        with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix='wan3') as pool:
            futures = {pool.submit(execute_job, edit, job, root, governor, kwargs): edit['global_id']
                       for edit, job in zip(edits, plan)}
            while futures:
                done, _ = wait(futures, timeout=15, return_when=FIRST_COMPLETED)
                for future in done:
                    ident = futures.pop(future)
                    try:
                        record = future.result()
                    except Exception as exc:
                        record = {'global_id': ident, 'status': 'failed',
                                  'error': f'{type(exc).__name__}: {str(exc)[:600]}'}
                        if fatal_rejection(exc):
                            governor.stop_new(str(exc))
                    if record['status'] == 'completed' and record.get('extra', {}).get('reused_existing'):
                        record['elapsed_sec'] = records.get(ident, {}).get('elapsed_sec', record['elapsed_sec'])
                    records[ident] = record
                    print(json.dumps({'global_id': ident, 'status': record['status'],
                                      'reused_existing': record.get('extra', {}).get('reused_existing', False)}), flush=True)
                flush()
        flush(finished=True)
        failed = [r for r in records.values() if r['status'] != 'completed']
        atomic_json(args.job_directory / 'failed_cases.json', failed)
        return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
