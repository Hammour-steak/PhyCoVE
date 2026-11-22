#!/usr/bin/env python3
"""Run Kiwi-Edit on PhyCoVE across several GPUs: one shard process per card.

Each shard is a plain run_phycove_kiwi_edit.py process pinned with an explicit
CUDA_VISIBLE_DEVICES, so shards share nothing but the predictions directory
(each case has its own lock + checkpoint, each shard its own run manifest).
Rerunning the same command resumes: finished cases are verified and skipped.

Example (GPUs 4-7, quantitative English prompts):
    python run_phycove_kiwi_edit_parallel.py --gpus 4 5 6 7 \
        --job-directory jobs/kiwi_edit/quantitative_en \
        -- --benchmark-root $PHYCOVE_ROOT --prompt-flavor quantitative --prompt-lang en --continue-on-error
Everything after `--` is passed to every shard unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BUSY_MIB = 1024  # a card with more memory in use than this is someone else's


def gpu_usage() -> dict[int, int]:
    out = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used', '--format=csv,noheader,nounits'],
                         capture_output=True, text=True, check=True, timeout=60).stdout
    return {int(i): int(m) for i, m in (line.split(',') for line in out.strip().splitlines())}


def main() -> int:
    argv = sys.argv[1:]
    passthrough = []
    if '--' in argv:
        cut = argv.index('--')
        argv, passthrough = argv[:cut], argv[cut + 1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--gpus', type=int, nargs='+', required=True, help='Physical GPU indices, one shard each.')
    p.add_argument('--job-directory', type=Path, required=True, help='Logs + launch record (outside the release).')
    p.add_argument('--allow-busy-gpu', action='store_true',
                   help=f'Launch even if a listed card already uses more than {BUSY_MIB} MiB.')
    p.add_argument('--python', default=sys.executable)
    args = p.parse_args(argv)
    if len(set(args.gpus)) != len(args.gpus):
        p.error('--gpus must be distinct')
    for flag in ('--num-shards', '--shard-index', '--device'):
        if any(a == flag or a.startswith(flag + '=') for a in passthrough):
            p.error(f'{flag} is set by this launcher')
    usage = gpu_usage()
    busy = [g for g in args.gpus if usage.get(g, 10**9) > BUSY_MIB]
    if busy and not args.allow_busy_gpu:
        raise SystemExit(f'GPUs {busy} are in use ({ {g: usage.get(g) for g in busy} } MiB); pick free cards')
    args.job_directory.mkdir(parents=True, exist_ok=True)
    # Validate the selection once before occupying any GPU.
    subprocess.run([args.python, str(HERE / 'run_phycove_kiwi_edit.py'), *passthrough, '--dry-run',
                    '--plan-path', str(args.job_directory / 'plan.json')],
                   cwd=HERE, check=True, stdout=subprocess.DEVNULL)
    n = len(args.gpus)
    procs = []
    for shard, gpu in enumerate(args.gpus):
        env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(gpu), 'PYTHONUNBUFFERED': '1'}
        log = (args.job_directory / f'shard{shard}of{n}_gpu{gpu}.log').open('a')
        cmd = [args.python, str(HERE / 'run_phycove_kiwi_edit.py'), *passthrough,
               '--num-shards', str(n), '--shard-index', str(shard)]
        procs.append((shard, gpu, subprocess.Popen(cmd, cwd=HERE, env=env, stdout=log,
                                                   stderr=subprocess.STDOUT), log, cmd))
    launch = {'started_at': time.time(), 'host': os.uname().nodename, 'launcher_pid': os.getpid(),
              'processes': [{'shard': s, 'gpu': g, 'pid': pr.pid, 'cmd': c} for s, g, pr, _, c in procs]}
    (args.job_directory / 'launch.json').write_text(json.dumps(launch, indent=2))
    print(json.dumps(launch['processes'], indent=2), flush=True)

    def stop(signum, _frame):
        for _, _, pr, _, _ in procs:
            if pr.poll() is None:
                pr.send_signal(signal.SIGINT)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    codes = {}
    for shard, gpu, pr, log, _ in procs:
        codes[shard] = pr.wait()
        log.close()
        print(f'shard {shard} (GPU {gpu}) exited {codes[shard]}', flush=True)
    launch.update(finished_at=time.time(), exit_codes=codes)
    (args.job_directory / 'launch.json').write_text(json.dumps(launch, indent=2))
    return 0 if all(c == 0 for c in codes.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
