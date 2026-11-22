#!/usr/bin/env python3
"""Durable parallel PhyCoVE H3 queue with bounded concurrency and submission pacing."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

import requests

from baselines.minimax_h3 import (
    MinimaxH3Baseline, TaskRejected, atomic_json, exclusive_lock, sha256,
)
from run_phycove_minimax_h3 import (
    parse_args as base_args, preflight, inside, publication_root, default_predictions_root,
)


def rate_limited(exc):
    return bool(re.search(r'\b1002\b|HTTP 429|rate.?limit|too many|concurren', str(exc), re.I))


def fatal_rejection(exc):
    return bool(re.search(r'HTTP (401|402|403)|\b(1004|1008|2013|2049)\b|insufficient.{0,20}(balance|credit)', str(exc), re.I))


class SubmissionPaused(TaskRejected):
    pass


class Governor:
    def __init__(self, initial=16, maximum=32, submit_interval=3.2,
                 query_interval=0.7, cooldown=60):
        self.condition = threading.Condition()
        self.target, self.maximum = initial, maximum
        self.active = self.accepted = self.rate_events = 0
        self.submit_interval, self.query_interval = submit_interval, query_interval
        self.cooldown = cooldown
        self.next_submit = self.next_query = self.pause_until = self.last_rate = 0.0
        self.fatal = None

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


class GovernedBaseline(MinimaxH3Baseline):
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

    def _create_task(self, body):
        self.governor.slot('submit')
        task_id = super()._create_task(body)
        self.governor.accepted_task()
        return task_id


def checkpoint_for(output):
    path = output.with_suffix('.task.json')
    return json.loads(path.read_text()) if path.exists() else {}


def reconcile_manifest(old, metadata, plan, root, job_directory, incremental=False, archive=True):
    """Accept a new manifest only after validating every cached input and video."""
    for key in ('baseline_config', 'prompt_flavor', 'prompt_lang'):
        if old and old.get(key) != metadata[key]:
            raise ValueError(f'Run configuration changed: {key}')
    changed = bool(old and old.get('manifest_sha256') != metadata['manifest_sha256'])
    if changed and not incremental:
        raise ValueError('Run configuration changed: manifest_sha256; use --incremental to verify and reuse matching cases')
    if not changed:
        return {r['global_id']: r for r in old.get('runs', [])}
    for job in plan:
        output = root / job['output_relative']
        state = checkpoint_for(output)
        if not state:
            if output.exists():
                raise ValueError('Output has no checkpoint: ' + job['global_id'])
            continue
        identity = {**metadata['baseline_config'], 'prompt': job['prompt'],
                    'source_sha256': job['source_sha256']}
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if state.get('request') != identity or state.get('request_fingerprint') != fingerprint:
            raise ValueError('Cached prompt/source/config changed: ' + job['global_id'])
        if state.get('status') == 'completed' and (not output.exists() or sha256(output) != state.get('output_sha256')):
            raise ValueError('Cached video missing or hash mismatch: ' + job['global_id'])
    if archive:
        history = job_directory / 'previous_run_manifest.json'
        if history.exists() and json.loads(history.read_text()) != old:
            raise ValueError('This job already archived another manifest; use a new job directory')
        atomic_json(history, old)
        for filename in ('full_run_progress.json', 'full_run_summary.json'):
            source = root / filename
            target = job_directory / ('previous_' + filename)
            if source.exists() and not target.exists():
                atomic_json(target, json.loads(source.read_text()))
    current = {job['global_id'] for job in plan}
    return {r['global_id']: r for r in old.get('runs', []) if r['global_id'] in current}


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
                if job.get('source_sha256') and sha256(Path(job['source_video'])) != job['source_sha256']:
                    raise ValueError('Source video changed after preflight: ' + job['global_id'])
                if not (output.exists() and state.get('status') == 'completed'):
                    governor.acquire(known_task=bool(state.get('task_id')))
                    acquired = True
                # Terminal failures need --retry-failed; only explicit rate rejections retry automatically.
                client.retry_failed = bool(kwargs.get('retry_failed', False) or (
                    state.get('status') == 'rejected' and not state.get('task_id')
                    and rate_limited(state.get('error', ''))))
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
                      ('failed', 'cancelled', 'canceled', 'expired', 'completed')
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
    p.add_argument('--submit-interval', type=float, default=3.2)
    p.add_argument('--query-interval', type=float, default=0.7)
    p.add_argument('--poll-interval', type=float, default=20)
    p.add_argument('--prompt-flavor', choices=('quantitative', 'vague'), default='quantitative')
    p.add_argument('--prompt-lang', choices=('en', 'zh'), default='en')
    p.add_argument('--wait-for-pilot', type=Path)
    p.add_argument('--dry-run', action='store_true', help='Validate selected sources and write a plan without API calls.')
    p.add_argument('--incremental', action='store_true',
                   help='Allow a new manifest after checking cached source, prompt, configuration and video hashes.')
    p.add_argument('--retry-failed', action='store_true',
                   help='Explicitly resubmit terminal failed cases; matching completed videos are still skipped.')
    args = p.parse_args(argv)
    if not 1 <= args.initial_concurrency <= args.workers <= 64:
        p.error('Require 1 <= initial-concurrency <= workers <= 64')
    if min(args.submit_interval, args.query_interval, args.poll_interval) <= 0:
        p.error('Intervals must be positive')
    return args


def main(argv=None):
    args = parse_args(argv)
    args.job_directory.mkdir(parents=True, exist_ok=True)
    if args.wait_for_pilot:
        launch = json.loads(args.wait_for_pilot.read_text())
        # Pilot shards must release their files before the full queue resumes them.
        while True:
            live = []
            for row in launch['processes']:
                proc = Path('/proc') / str(row['pid'])
                try:
                    cmd = (proc / 'cmdline').read_bytes()
                    if b'run_phycove_minimax_h3.py' in cmd:
                        live.append(row['pid'])
                except (FileNotFoundError, PermissionError):
                    pass
            if not live:
                break
            print(f'Waiting for {len(live)} pilot workers to finish', flush=True)
            time.sleep(5)
    base = base_args(['--benchmark-root', str(args.benchmark_root),
                      '--prompt-flavor', args.prompt_flavor, '--prompt-lang', args.prompt_lang,
                      '--poll-interval', str(args.poll_interval)])
    if args.predictions_root:
        base.predictions_root = args.predictions_root
    base.retry_failed = args.retry_failed
    benchmark = base.benchmark_root.resolve()
    publication = publication_root(benchmark)
    predictions = (base.predictions_root or default_predictions_root(
        benchmark, base.prompt_flavor, base.prompt_lang)).resolve()
    if inside(predictions, publication) or inside(args.job_directory, publication):
        raise ValueError('Keep predictions and job logs outside publication data')
    kwargs = {key: getattr(base, key) for key in ('model_id', 'api_base', 'resolution', 'duration',
              'ratio', 'poll_interval', 'poll_timeout', 'request_timeout', 'retry_failed')}
    manifest_path, edits, plan, sources = preflight(base, MinimaxH3Baseline(**kwargs))
    root = predictions / 'minimax_h3'
    governor = Governor(args.initial_concurrency, args.workers, args.submit_interval, args.query_interval)
    run_path = root / 'run_manifest.json'
    started = time.time()
    metadata = {'baseline': 'minimax_h3', 'baseline_config': MinimaxH3Baseline(**kwargs).config,
                'benchmark_root': str(base.benchmark_root.resolve()), 'predictions_root': str(predictions),
                'benchmark_name': json.loads(manifest_path.read_text()).get('benchmark_name'),
                'data_subset': benchmark.relative_to(publication).as_posix() if benchmark != publication else 'root',
                'manifest_sha256': sha256(manifest_path), 'prompt_flavor': base.prompt_flavor,
                'prompt_lang': base.prompt_lang, 'num_shards': 1, 'shard_index': 0,
                'scene_count': len(sources), 'source_count': len(sources), 'edit_count': len(edits),
                'started_at': started, 'execution_host': os.uname().nodename,
                'job_directory': str(args.job_directory.resolve())}
    if args.dry_run:
        old = json.loads(run_path.read_text()) if run_path.exists() else {}
        if old and old.get('manifest_sha256') != metadata['manifest_sha256'] and args.incremental:
            reconcile_manifest(old, metadata, plan, root, args.job_directory, incremental=True, archive=False)
        atomic_json(args.job_directory / 'plan.json', {**metadata, 'tasks': plan})
        print(json.dumps({**metadata, 'offline_preflight_passed': True}, ensure_ascii=False, indent=2))
        return 0
    with exclusive_lock(run_path.with_suffix('.lock')):
        old = json.loads(run_path.read_text()) if run_path.exists() else {}
        records = reconcile_manifest(old, metadata, plan, root, args.job_directory, args.incremental)

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
                                  else 'stopped_with_errors' if finished else 'running')
            atomic_json(args.job_directory / 'progress.json', progress)
            atomic_json(root / 'full_run_progress.json', progress)
            atomic_json(run_path, {**metadata, 'runs': list(records.values()),
                                  'parallel_progress': progress, 'updated_at': time.time()})
            print(json.dumps({k: progress[k] for k in ('completed', 'total', 'state_counts',
                  'target_concurrency', 'active_workers', 'new_tasks_accepted', 'rate_limit_events', 'finished')}), flush=True)

        flush()
        with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix='h3') as pool:
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
