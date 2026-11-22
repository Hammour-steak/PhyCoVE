#!/usr/bin/env python3
"""Run JoyAI-Video-Edit on PhyCoVE with one worker process per GPU (resume-safe).

Every GPU must be named explicitly via --gpus. Each worker is
`run_phycove_joyai_video_edit.py --num-shards N --shard-index i` pinned to one
card with CUDA_VISIBLE_DEVICES; arguments after `--` are passed to every worker.
Uses only the standard library, so any python3 can launch it.

The output mirrors the MiniMax H3 full run (predictions/.../minimax_h3/):
  joyai_video_edit/videos/<scene>/<case_id>.{mp4,task.json,lock}
  joyai_video_edit/run_manifest.shard<i>of<N>.json   per-worker records
  joyai_video_edit/run_manifest.json                 merged records + parallel_progress
  joyai_video_edit/full_run_progress.json            live queue state (also <job>/progress.json)
  joyai_video_edit/full_run_summary.json             written when the queue ends
  <job>/failed_cases.json, <job>/launch.json, <job>/shard<i>of<N>_gpu<g>.log

  python3 run_phycove_joyai_video_edit_parallel.py --gpus 2,5,6,7 \\
      --job-directory jobs/joyai_quant_en -- \\
      --benchmark-root $PHYCOVE_ROOT --prompt-flavor quantitative --prompt-lang en --continue-on-error

Rerunning the same command resumes: finished cases are verified by hash and skipped.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ENV_PYTHON = Path(os.environ.get('MODEL_ROOT', 'models')) / 'JoyAI-Video-Edit' / 'env' / 'bin' / 'python'
DEFAULT_BENCH = os.environ.get('PHYCOVE_ROOT')  # release folder; without it --benchmark-root is required
CONSISTENT = ('manifest_sha256', 'baseline_config', 'prompt_flavor', 'prompt_lang')


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def gpu_status():
    out = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,memory.total',
                          '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout
    rows = {}
    for line in out.strip().splitlines():
        index, used, total = (int(x.strip()) for x in line.split(','))
        rows[index] = {'used_mib': used, 'total_mib': total}
    return rows


def parse_args():
    argv = sys.argv[1:]
    passthrough = []
    if '--' in argv:
        cut = argv.index('--')
        argv, passthrough = argv[:cut], argv[cut + 1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--gpus', required=True, help='Comma-separated physical GPU indices, e.g. 2,5,6,7.')
    p.add_argument('--job-directory', type=Path, required=True, help='Logs, plans, launch.json and progress.json.')
    p.add_argument('--python', type=Path, default=ENV_PYTHON, help='Python of the JoyAI environment (default: $MODEL_ROOT/JoyAI-Video-Edit/env/bin/python).')
    p.add_argument('--min-free-gib', type=float, default=34.0,
                   help='Refuse a GPU with less free memory than this (720p low-VRAM peaks at ~31 GiB reserved).')
    p.add_argument('--claim-dir', type=Path,
                   help='Shared claim directory, e.g. /tmp/gpu_claims: mkdir <dir>/gpu<N> before use, '
                        'refuse a card someone else claimed, remove the claims when the queue ends.')
    p.add_argument('--merge-only', action='store_true', help='Only rebuild the merged manifest/progress/summary.')
    args = p.parse_args(argv)
    args.gpu_list = [int(g) for g in args.gpus.split(',') if g.strip()]
    if not args.gpu_list or len(set(args.gpu_list)) != len(args.gpu_list):
        p.error('--gpus must list distinct GPU indices')
    for flag in ('--num-shards', '--shard-index', '--dry-run', '--plan-path'):
        if any(a == flag or a.startswith(flag + '=') for a in passthrough):
            p.error(f'{flag} is set by this launcher')
    args.passthrough = passthrough
    return args


def predictions_dir(passthrough):
    """Resolve the worker's output directory the same way the worker does."""
    def value(flag, default):
        for i, a in enumerate(passthrough):
            if a == flag and i + 1 < len(passthrough):
                return passthrough[i + 1]
            if a.startswith(flag + '='):
                return a.split('=', 1)[1]
        return default
    bench = value('--benchmark-root', DEFAULT_BENCH)
    if bench is None:
        raise SystemExit('Pass --benchmark-root after -- or set PHYCOVE_ROOT')
    root = Path(bench).resolve()
    explicit = value('--predictions-root', None)
    flavor, lang = value('--prompt-flavor', 'quantitative'), value('--prompt-lang', 'en')
    base = Path(explicit) if explicit else root.parent.parent / 'predictions' / root.name / f'{flavor}_{lang}'
    return base.resolve() / 'joyai_video_edit'


class Queue:
    def __init__(self, args, baseline_root: Path, started_at: float):
        self.args, self.root, self.started_at = args, baseline_root, started_at
        self.n = len(args.gpu_list)
        self.job = args.job_directory.resolve()
        self.initial_completed = None

    def plans(self):
        plans = [read_json(self.job / f'plan_shard{i}of{self.n}.json') for i in range(self.n)]
        return [p for p in plans if p]

    def shard_runs(self):
        runs = {}
        for i in range(self.n):
            data = read_json(self.root / f'run_manifest.shard{i}of{self.n}.json', {})
            for record in data.get('runs', []):
                runs[record['global_id']] = record
        return runs

    def update(self, finished=False, workers_alive=0):
        plans = self.plans()
        if not plans:
            return None
        for other in plans[1:]:
            for key in CONSISTENT:
                if other.get(key) != plans[0].get(key):
                    raise ValueError(f'Shard plans disagree on {key}')
        tasks = [t for p in plans for t in p['tasks']]
        shard_runs = self.shard_runs()
        counts = Counter()
        for task in tasks:
            output = self.root / task['output_relative']
            state = read_json(output.with_suffix('.task.json'), {})
            if output.exists() and state.get('status') == 'completed':
                counts['completed'] += 1
            else:
                counts[shard_runs.get(task['global_id'], {}).get('status', 'pending')] += 1
        total = len(tasks) if len(plans) == self.n else None
        completed = counts['completed']
        if self.initial_completed is None:
            self.initial_completed = completed
        now = time.time()
        new = completed - self.initial_completed
        rate = new / (now - self.started_at) if new > 0 else None
        remaining = None if total is None else total - completed
        p0 = plans[0]
        meta = {
            'baseline': p0['baseline'], 'baseline_config': p0['baseline_config'],
            'benchmark_root': p0['benchmark_root'], 'predictions_root': p0['predictions_root'],
            'manifest_sha256': p0['manifest_sha256'], 'prompt_flavor': p0['prompt_flavor'],
            'prompt_lang': p0['prompt_lang'], 'num_shards': self.n, 'shard_index': None,
            'scene_count': len({t['global_id'].split('/')[0] for t in tasks}),
            'source_count': len({t['source_video'] for t in tasks}), 'edit_count': len(tasks),
            'started_at': self.started_at, 'execution_host': os.uname().nodename,
            'job_directory': str(self.job), 'gpus': self.args.gpu_list,
        }
        progress = {**meta, 'workers_alive': workers_alive, 'state_counts': dict(counts),
                    'completed': completed, 'total': total, 'remaining': remaining,
                    'completed_this_queue': new,
                    'cases_per_hour': round(rate * 3600, 1) if rate else None,
                    'eta_minutes': round(remaining / rate / 60, 1) if rate and remaining is not None else None,
                    'updated_at': now, 'finished': finished}
        progress['status'] = ('completed' if total is not None and completed == total
                              else 'stopped_with_errors' if finished else 'running')
        atomic_json(self.job / 'progress.json', progress)
        atomic_json(self.root / 'full_run_progress.json', progress)
        with (self.root / 'run_manifest.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                old = read_json(self.root / 'run_manifest.json', {})
                for key in CONSISTENT:
                    if old and old.get(key) != meta[key]:
                        raise ValueError(f'Existing run_manifest.json has a different {key}; not merging')
                runs = {r['global_id']: r for r in old.get('runs', [])}
                runs.update(shard_runs)
                atomic_json(self.root / 'run_manifest.json', {
                    **meta, 'merged_from': [f'run_manifest.shard{i}of{self.n}.json' for i in range(self.n)],
                    'runs': list(runs.values()), 'parallel_progress': progress, 'updated_at': now})
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        if finished:
            self.summarize(tasks, shard_runs, progress)
        return progress

    def summarize(self, tasks, shard_runs, progress):
        verified, media, size, errors = 0, Counter(), 0, []
        for task in tasks:
            output = self.root / task['output_relative']
            state = read_json(output.with_suffix('.task.json'), {})
            if output.exists() and state.get('status') == 'completed':
                size += output.stat().st_size
                if sha256(output) == state.get('output_sha256'):
                    verified += 1
                else:
                    errors.append({'global_id': task['global_id'], 'error': 'output hash mismatch'})
                m = state.get('output_media', {})
                media[str((m.get('width'), m.get('height'), m.get('fps'), m.get('frames')))] += 1
            else:
                record = shard_runs.get(task['global_id'], {})
                errors.append({'global_id': task['global_id'], 'status': record.get('status', 'pending'),
                               'error': record.get('error')})
        bench_manifest = Path(progress['benchmark_root']) / 'benchmark_manifest.json'
        summary = {
            'total_edit_cases': progress['total'], 'completed_videos': progress['completed'],
            'hashes_verified': verified, 'errors': errors, 'queue_status': progress['status'],
            'queue_finished': True, 'max_concurrency': self.n, 'gpus': self.args.gpu_list,
            'queue_runtime_minutes': round((time.time() - self.started_at) / 60, 1),
            'finished_at_beijing': datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'prediction_root': str(self.root), 'prediction_video_bytes': size,
            'media_groups': dict(media),
            'benchmark_manifest_hash_matches': sha256(bench_manifest) == progress['manifest_sha256'],
        }
        atomic_json(self.root / 'full_run_summary.json', summary)
        atomic_json(self.job / 'failed_cases.json', errors)


def claim_gpus(claim_dir: Path, gpus, job: Path):
    claimed = []
    try:
        for g in gpus:
            path = claim_dir / f'gpu{g}'
            try:
                path.mkdir(parents=False)
            except FileExistsError:
                raise SystemExit(f'GPU {g} is claimed by someone else ({path}); pick another card') from None
            claimed.append(path)
            atomic_json(path / 'owner.json', {'owner': 'joyai_video_edit full run', 'user': os.environ.get('USER'),
                                              'launcher_pid': os.getpid(), 'job_directory': str(job),
                                              'claimed_at': time.time()})
    except BaseException:
        release(claimed)
        raise
    return claimed


def release(claimed):
    for path in claimed:
        owner = read_json(path / 'owner.json', {})
        if owner.get('launcher_pid') == os.getpid():
            (path / 'owner.json').unlink(missing_ok=True)
            try:
                path.rmdir()
            except OSError:
                pass


def main() -> int:
    args = parse_args()
    args.job_directory.mkdir(parents=True, exist_ok=True)
    baseline_root = predictions_dir(args.passthrough)
    baseline_root.mkdir(parents=True, exist_ok=True)
    n = len(args.gpu_list)
    if args.merge_only:
        launch = read_json(args.job_directory / 'launch.json', {})
        queue = Queue(args, baseline_root, launch.get('started_at', time.time()))
        print(json.dumps(queue.update(finished=True), indent=2))
        return 0
    if not args.python.exists():
        raise SystemExit(f'JoyAI Python not found: {args.python}')
    claimed = claim_gpus(args.claim_dir, args.gpu_list, args.job_directory) if args.claim_dir else []
    try:
        status = gpu_status()
        for g in args.gpu_list:
            if g not in status:
                raise SystemExit(f'GPU {g} does not exist')
            free = (status[g]['total_mib'] - status[g]['used_mib']) / 1024
            if free < args.min_free_gib:
                raise SystemExit(f'GPU {g} has only {free:.1f} GiB free (< {args.min_free_gib}); pick another card')
        started = time.time()
        queue = Queue(args, baseline_root, started)
        procs = []
        for i, g in enumerate(args.gpu_list):
            plan = args.job_directory.resolve() / f'plan_shard{i}of{n}.json'
            cmd = [str(args.python), '-u', str(HERE / 'run_phycove_joyai_video_edit.py'),
                   '--num-shards', str(n), '--shard-index', str(i), '--plan-path', str(plan), *args.passthrough]
            env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(g), 'PYTHONDONTWRITEBYTECODE': '1'}
            log = (args.job_directory / f'shard{i}of{n}_gpu{g}.log').open('a')
            procs.append((i, g, subprocess.Popen(cmd, cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT,
                                                 stdin=subprocess.DEVNULL), log, cmd))
        atomic_json(args.job_directory / 'launch.json', {
            'launcher_pid': os.getpid(), 'started_at': started, 'host': os.uname().nodename,
            'predictions': str(baseline_root), 'claims': [str(c) for c in claimed],
            'processes': [{'shard': i, 'gpu': g, 'pid': p.pid, 'cmd': cmd} for i, g, p, _, cmd in procs]})
        print(f'Launched {n} workers; logs in {args.job_directory}', flush=True)
        while True:
            alive = sum(p.poll() is None for _, _, p, _, _ in procs)
            if not alive:
                break
            time.sleep(30)
            try:
                progress = queue.update(workers_alive=alive)
                if progress:
                    print(json.dumps({k: progress[k] for k in ('completed', 'total', 'state_counts',
                                      'cases_per_hour', 'eta_minutes')}), flush=True)
            except (ValueError, OSError) as exc:
                print(f'progress update skipped: {exc}', flush=True)
        for _, _, _, log, _ in procs:
            log.close()
        codes = {f'shard{i}_gpu{g}': p.returncode for i, g, p, _, _ in procs}
        progress = queue.update(finished=True)
        print(json.dumps({'exit_codes': codes, 'status': progress and progress['status'],
                          'completed': progress and progress['completed'],
                          'total': progress and progress['total']}, indent=2), flush=True)
        return 0 if all(c == 0 for c in codes.values()) else 1
    finally:
        release(claimed)


if __name__ == '__main__':
    sys.exit(main())
