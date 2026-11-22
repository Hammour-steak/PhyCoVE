#!/usr/bin/env python3
"""Durable parallel Seedance queue; reuse trial checkpoints and accepted tasks."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from baselines.minimax_h3 import atomic_json, exclusive_lock, probe_video, sha256
from run_phycove_minimax_h3_parallel import Governor, SubmissionPaused
from run_phycove_seedance25 import MODEL, default_predictions_root, publication_root

TERMINAL = {'failed', 'cancelled', 'canceled', 'expired', 'submission_rejected'}


def read_state(output):
    checkpoint = output.with_suffix('.task.json')
    return json.loads(checkpoint.read_text()) if checkpoint.exists() else {}


def case_busy(output):
    lock = output.with_suffix('.lock')
    if not lock.exists():
        return False
    with lock.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
    return False


def media_rejection(state):
    error = str(state.get('error', ''))
    previous = sum('resource download failed' in str(a.get('error', '')).lower()
                   for a in state.get('previous_attempts', []))
    return (not state.get('task_id') and state.get('status') == 'submission_rejected'
            and 'HTTP 400' in error and 'resource download failed' in error.lower() and previous < 3)


def expected_body(prompt, url):
    return {'model': MODEL, 'content': [
        {'type': 'text', 'text': prompt},
        {'type': 'video_url', 'video_url': {'url': url}, 'role': 'reference_video'}],
        'omni_reference_task_type': 'edit', 'resolution': '720p', 'ratio': 'adaptive',
        'duration': -1, 'generate_audio': False, 'seed': 42, 'watermark': False}


def published_url_matches(url, relative, prefix=''):
    base = 'https://huggingface.co/datasets/ccmoony/PhyCoVE/resolve/'
    if not isinstance(url, str) or not url.startswith(base):
        return False
    revision, separator, path = url[len(base):].partition('/')
    expected = '/'.join(part for part in (prefix.strip('/'), relative) if part)
    return bool(separator and re.fullmatch(r'[A-Za-z0-9_-]+', revision) and path == expected)


def verified_identity(edit, source_hash, default_url, state, path_prefix=''):
    # Older trials used earlier immutable HF revisions. Reuse their exact URL
    # when the source SHA, prompt and all inference settings still match.
    if not published_url_matches(default_url, edit['source_video'], path_prefix):
        raise ValueError('Published source URL has the wrong subset or video path: ' + edit['global_id'])
    ident = {'global_id': edit['global_id'], 'source_sha256': source_hash,
             'prompt_flavor': 'quantitative', 'prompt_lang': 'en',
             'request': expected_body(edit['prompts']['quantitative']['en'], default_url)}
    if state:
        old = state.get('identity') or {}
        old_url = old['request']['content'][1]['video_url']['url']
        if not published_url_matches(old_url, edit['source_video'], path_prefix):
            raise ValueError('Saved source URL is not this published PhyCoVE video')
        ident['request']['content'][1]['video_url']['url'] = old_url
        if old != ident:
            raise ValueError('Saved prompt, input or generation settings changed: ' + edit['global_id'])
    return ident


def fatal_error(message):
    return bool(re.search(r'HTTP (401|402|403)\b|insufficient.{0,30}(balance|credit)|'
                          r'AccountOverdue|SetLimitExceeded|BalanceNotEnough', str(message), re.I))


def execute(job, root, script, governor, logs, runner=subprocess.run, sleeper=time.sleep):
    output = root / job['output_relative']
    log = logs / (job['global_id'].replace('/', '__') + '.log')
    result = {'global_id': job['global_id'], 'source_video': job['source_video'],
              'prompt': job['identity']['request']['content'][0]['text'], 'output_video': str(output)}
    resumes = 0
    while True:
        # A restarted controller can adopt children left running by the previous
        # controller. Wait for their case lock instead of launching a duplicate.
        if case_busy(output):
            sleeper(3)
            continue
        state = read_state(output)
        if state and state.get('identity') != job['identity']:
            return {**result, 'status': 'failed', 'error': 'Checkpoint identity changed'}
        if state.get('status') == 'completed':
            if not output.exists() or sha256(output) != state.get('output_sha256'):
                return {**result, 'status': 'failed', 'error': 'Completed video is missing or its SHA256 changed'}
            return {**result, 'status': 'completed', 'task_id': state['task_id'],
                    'elapsed_sec': state.get('elapsed_sec'), 'media': state.get('output_media'),
                    'output_sha256': state.get('output_sha256'), 'resumes': resumes}
        known = bool(state.get('task_id'))
        rate_rejection = (not known and state.get('status') == 'submission_rejected'
                          and re.search(r'HTTP 429\b', str(state.get('error', ''))))
        if state and not known and state.get('status') in ('submitting', 'submission_unknown'):
            return {**result, 'status': 'needs_reconciliation', 'error': 'Submission response was lost; no automatic second POST'}
        if state.get('status') in TERMINAL and not rate_rejection and not media_rejection(state):
            error = state.get('error', '')
            if fatal_error(error):
                governor.stop_new(str(error))
            return {**result, 'status': 'failed', 'error': error, 'task_id': state.get('task_id')}
        acquired = False
        try:
            governor.acquire(known_task=known)
            acquired = True
            if not known:
                governor.slot('submit')
            command = [sys.executable, '-u', str(script), '--benchmark-root', job['benchmark_root'],
                       '--predictions-root', str(root.parent), '--global-id', job['global_id'],
                       '--source-url', job['identity']['request']['content'][1]['video_url']['url'],
                       '--source-url-sha256', job['identity']['source_sha256'],
                       '--poll-timeout', '300', '--retry-rate-rejected', '--retry-input-download-rejected']
            with log.open('ab') as stream:
                process = runner(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
            current = read_state(output)
            if not known and current.get('task_id'):
                governor.accepted_task()
            if current.get('status') == 'completed':
                continue
            if (current.get('status') == 'submission_rejected' and not current.get('task_id')
                    and re.search(r'HTTP 429\b', str(current.get('error', '')))):
                governor.throttled()
                continue
            if media_rejection(current):
                sleeper(min(30, 5 * 2 ** len(current.get('previous_attempts', []))))
                continue
            if current.get('task_id') and current.get('status') not in TERMINAL:
                # Retry status queries/downloads for this same accepted task only.
                resumes += 1
                sleeper(5)
                continue
            if not current:
                return {**result, 'status': 'failed', 'error': f'Worker exited before saving a checkpoint ({process.returncode}); see {log}'}
        except SubmissionPaused as exc:
            return {**result, 'status': 'not_started', 'error': str(exc)}
        finally:
            if acquired:
                governor.release()


def preflight(args):
    benchmark = args.benchmark_root.resolve()
    manifest_path = benchmark / 'benchmark_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    published = json.loads(args.sources_map.read_text())
    by_video = {s['video']: s for s in published['sources']}
    publication = publication_root(benchmark)
    path_prefix = published.get('path_prefix', benchmark.relative_to(publication).as_posix()
                                if benchmark != publication else '')
    root = (args.predictions_root or default_predictions_root(benchmark)).resolve() / 'seedance25'
    job_directory = args.job_directory.resolve()
    if publication == root or publication in root.parents or publication == job_directory or publication in job_directory.parents:
        raise ValueError('Keep all predictions and job logs outside publication data')
    sources = {}
    for source in manifest['sources']:
        path = (benchmark / source['video']).resolve()
        path.relative_to(benchmark)
        digest = sha256(path)
        remote = by_video[source['video']]
        if digest != source['video_sha256'] or digest != remote['published_sha256']:
            raise ValueError('Published and local source video differ: ' + source['video'])
        media = probe_video(path)
        if not (4 <= media['duration_sec'] <= 30 and 24 <= media['fps'] <= 60
                and media['codec'] in ('h264', 'hevc') and 407696 <= media['width'] * media['height'] <= 8295044):
            raise ValueError('Unsupported Seedance source: ' + source['video'])
        sources[source['video']] = {**remote, 'local_path': str(path), 'media': media}
    jobs, existing = [], []
    existing_task_count = 0
    ids = set()
    for edit in manifest['edits']:
        gid = edit['global_id']
        if gid in ids or gid != edit['scene'] + '/' + edit['case_id'] or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', gid):
            raise ValueError('Duplicate or unsafe edit ID: ' + gid)
        ids.add(gid)
        source = sources[edit['source_video']]
        relative = 'videos/' + gid + '.mp4'
        output = root / relative
        state = read_state(output)
        existing_task_count += bool(state.get('task_id'))
        identity = verified_identity(edit, source['published_sha256'], source['url'], state, path_prefix)
        if state.get('status') == 'completed':
            if not output.exists() or sha256(output) != state.get('output_sha256'):
                raise ValueError('Previously completed output hash does not match: ' + gid)
            existing.append(gid)
        jobs.append({'global_id': gid, 'benchmark_root': str(benchmark), 'source_video': source['local_path'],
                     'source_media': source['media'], 'identity': identity, 'output_relative': relative})
    return root, jobs, {'benchmark_root': str(benchmark), 'benchmark_name': manifest.get('benchmark_name'),
                       'data_subset': path_prefix or 'root', 'manifest_sha256': sha256(manifest_path),
                       'baseline': 'seedance25', 'model': MODEL, 'resolution': '720p', 'seed': 42,
                       'prompt_flavor': 'quantitative', 'prompt_lang': 'en', 'source_count': len(sources),
                       'total': len(jobs), 'existing_verified': existing,
                       'existing_task_count': existing_task_count,
                       'new_case_count': len(jobs) - existing_task_count, 'hf_revision': published['revision'],
                       'hf_path_prefix': path_prefix}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--benchmark-root', type=Path, default=os.environ.get('PHYCOVE_ROOT'),
                   required=not os.environ.get('PHYCOVE_ROOT'),
                   help='Release folder with benchmark_manifest.json (default: $PHYCOVE_ROOT).')
    p.add_argument('--predictions-root', type=Path)
    p.add_argument('--sources-map', type=Path, required=True)
    p.add_argument('--job-directory', type=Path, required=True)
    p.add_argument('--workers', type=int, default=64)
    p.add_argument('--submit-interval', type=float, default=0.5)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    if not 1 <= args.workers <= 128 or args.submit_interval < 0.4:
        p.error('Use 1..128 workers and at least 0.4 seconds between submissions (150 RPM)')
    root, jobs, metadata = preflight(args)
    args.job_directory.mkdir(parents=True, exist_ok=True)
    atomic_json(args.job_directory / 'plan.json', {**metadata, 'jobs': jobs})
    print(json.dumps({**metadata, 'workers': args.workers, 'new_cases': metadata['new_case_count']}), flush=True)
    if args.dry_run:
        return 0
    if not os.environ.get('ARK_API_KEY'):
        raise RuntimeError('ARK_API_KEY is missing')
    logs = args.job_directory / 'cases'
    logs.mkdir(exist_ok=True)
    script = Path(__file__).with_name('run_phycove_seedance25.py')
    governor = Governor(initial=args.workers, maximum=args.workers,
                        submit_interval=args.submit_interval, query_interval=0.1, cooldown=30)
    records = {}
    started = time.time()
    metadata.update(started_at=started, execution_host=os.uname().nodename,
                    job_directory=str(args.job_directory.resolve()))
    def flush(finished=False):
        states = [read_state(root / job['output_relative']) for job in jobs]
        counts = Counter(s.get('status', 'pending') for s in states)
        progress = {**metadata, **governor.snapshot(), 'state_counts': dict(counts),
                    'completed': counts['completed'], 'remaining': len(jobs) - counts['completed'],
                    'known_tasks': sum(bool(s.get('task_id')) for s in states),
                    'new_tasks_accepted': sum(bool(s.get('task_id')) for s in states) - metadata['existing_task_count'],
                    'elapsed_sec': round(time.time() - started, 1), 'updated_at': time.time(),
                    'finished': finished, 'status': 'completed' if counts['completed'] == len(jobs)
                    else 'stopped_with_errors' if finished else 'running'}
        for path in [args.job_directory / 'progress.json', root / 'full_run_progress.json']:
            atomic_json(path, progress)
        atomic_json(root / 'run_manifest.json', {**metadata, 'runs': list(records.values()), 'parallel_progress': progress})
        print(json.dumps({k: progress[k] for k in ['completed', 'total', 'state_counts', 'target_concurrency',
                          'new_tasks_accepted', 'rate_limit_events', 'elapsed_sec', 'finished']}), flush=True)
        return progress
    with exclusive_lock(root / 'run_manifest.lock'):
        flush()
        with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix='seedance') as pool:
            futures = {pool.submit(execute, job, root, script, governor, logs): job for job in jobs}
            while futures:
                done, _ = wait(futures, timeout=15, return_when=FIRST_COMPLETED)
                for future in done:
                    job = futures.pop(future)
                    try:
                        records[job['global_id']] = future.result()
                    except Exception as exc:
                        records[job['global_id']] = {'global_id': job['global_id'], 'status': 'failed',
                                                     'error': f'{type(exc).__name__}: {exc}'}
                flush()
        progress = flush(finished=True)
        atomic_json(args.job_directory / 'failed_cases.json', [r for r in records.values() if r['status'] != 'completed'])
        return 0 if progress['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
