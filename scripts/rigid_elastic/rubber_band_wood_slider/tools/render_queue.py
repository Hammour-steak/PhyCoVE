"""Server-side render queue: all 96 frames of each case on one free GPU of this host, then encode.

    nohup python3 scripts/rigid_elastic/rubber_band_wood_slider/tools/render_queue.py \
        --root renders/rubber_band_wood_slider/<run> --gpus <GPU indices> --max-jobs 2 &

A GPU is taken only when it has no compute process of any user, utilization <= 10 % and < 1 GiB in use, and its
claim directory (--claims/gpu<N>, default .runtime/rubber_band_wood_slider/gpu_claims) could be created. While a case renders, a process of another user appearing on
that GPU stops the case (by PID), releases the claim and puts the case back in the queue; its finished frames are
kept and the rest is rendered later on another GPU of the same model (render_scene.py skips existing frames).
Each case is encoded (tools/publish_suite.py encode) when its 96 frames exist. State: <root>/queue_state.json.
"""
from pathlib import Path
import argparse
import datetime
import json
import os
import signal
import socket
import subprocess
import sys
import time

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]
from scene_paths import CASES, RUNTIME, blender_runtime, native_case, output_path  # noqa: E402

LOOK = CASE_DIR / 'appearance/realism.py'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def gpus():
    rows = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,name,utilization.gpu,memory.used',
                                    '--format=csv,noheader,nounits'], text=True, timeout=60)
    apps = subprocess.check_output(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader'],
                                   text=True, timeout=60)
    users = {}
    for line in apps.strip().splitlines():
        uuid, pid = [v.strip() for v in line.split(',')]
        try:
            user = subprocess.check_output(['ps', '-o', 'user=', '-p', pid], text=True).strip()
        except subprocess.CalledProcessError:
            user = '?'
        users.setdefault(uuid, []).append((int(pid), user))
    result = {}
    for row in rows.strip().splitlines():
        index, uuid, name, util, used = [v.strip() for v in row.split(',')]
        result[index] = {'uuid': uuid, 'name': name, 'util': int(util), 'used': int(used), 'procs': users.get(uuid, [])}
    return result


def frames_done(out):
    return sum((out / f'{i:04d}.png').is_file() for i in range(1, 97))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--cases', nargs='+', choices=CASES, default=CASES)
    ap.add_argument('--gpus', nargs='+', required=True, help='GPU indices this queue may use')
    ap.add_argument('--max-jobs', type=int, default=2)
    ap.add_argument('--claims', type=Path, default=RUNTIME / 'gpu_claims')
    ap.add_argument('--samples', type=int, default=256)
    ap.add_argument('--threads', type=int, default=8)
    ap.add_argument('--revision', default='look_review')
    ap.add_argument('--blender-bin', type=Path)
    a = ap.parse_args()
    root = output_path(a.root)
    root.mkdir(parents=True, exist_ok=True)
    logs = RUNTIME / 'queue' / root.name
    logs.mkdir(parents=True, exist_ok=True)
    me = subprocess.check_output(['id', '-un'], text=True).strip()
    pending = [c for c in a.cases if not (root / c / 'video.mp4').is_file()]
    running, done, events = {}, [c for c in a.cases if c not in pending], []
    state = root / 'queue_state.json'

    def save():
        state.write_text(json.dumps({'updated': now(), 'pending': pending, 'running': {c: {k: v for k, v in j.items() if k != 'proc'} for c, j in running.items()},
                                     'done': done, 'events': events[-50:]}, indent=1) + '\n')

    def release(job):
        try:
            (a.claims / f"gpu{job['gpu']}").rmdir()
        except OSError:
            pass

    def stop(case, reason):
        job = running.pop(case)
        if job['proc'].poll() is None:
            os.kill(job['proc'].pid, signal.SIGTERM)
            try:
                job['proc'].wait(60)
            except subprocess.TimeoutExpired:
                os.kill(job['proc'].pid, signal.SIGKILL)
        release(job)
        events.append({'utc': now(), 'case': case, 'gpu': job['gpu'], 'event': reason, 'frames': frames_done(root / case)})
        pending.insert(0, case)

    try:
        while pending or running:
            table = gpus()
            for case, job in list(running.items()):
                code = job['proc'].poll()
                out = root / case
                foreign = [p for p in table[job['gpu']]['procs'] if p[1] != me]
                if code is None and foreign:
                    stop(case, f'stopped: other user process on GPU {job["gpu"]}: {foreign}')
                    continue
                if code is None:
                    continue
                running.pop(case)
                release(job)
                if code == 0 and frames_done(out) == 96:
                    enc = subprocess.run([sys.executable, str(CASE_DIR / 'tools/publish_suite.py'), 'encode', str(out)],
                                         capture_output=True, text=True)
                    events.append({'utc': now(), 'case': case, 'gpu': job['gpu'], 'event': f'rendered, encode exit {enc.returncode}',
                                   'detail': (enc.stdout + enc.stderr)[-400:]})
                    done.append(case)
                else:
                    events.append({'utc': now(), 'case': case, 'gpu': job['gpu'], 'event': f'blender exit {code}', 'frames': frames_done(out)})
                    job['tries'] = job.get('tries', 0) + 1
                    if job['tries'] < 3:
                        pending.insert(0, case)
            while pending and len(running) < a.max_jobs:
                free = [i for i in a.gpus if i in table and not table[i]['procs'] and table[i]['util'] <= 10 and table[i]['used'] < 1024]
                chosen = None
                for i in free:
                    a.claims.mkdir(parents=True, exist_ok=True)
                    try:
                        (a.claims / f'gpu{i}').mkdir()
                        chosen = i
                        break
                    except FileExistsError:
                        continue
                if chosen is None:
                    break
                case = pending.pop(0)
                native = native_case(case)
                out = root / case
                out.mkdir(parents=True, exist_ok=True)
                cmd = [str(blender_runtime(a.blender_bin)), '-b', '-t', str(a.threads), '--python-exit-code', '1', '--python', str(LOOK),
                       '--', '--case', case, '--input', str(native), '--audit', str(native / 'capture_start_audit.json'), '--out', str(out),
                       '--samples', str(a.samples), '--review-candidate', '--revision', a.revision]
                env = dict(os.environ, CUDA_VISIBLE_DEVICES=table[chosen]['uuid'], PCVE_GPU_POLICY_PASSED='1',
                           PCVE_WORKER_IP=socket.gethostname(), OMP_NUM_THREADS=str(a.threads), PYTHONDONTWRITEBYTECODE='1')
                log = open(logs / f'{case}_{datetime.datetime.now().strftime("%H%M%S")}.log', 'w')
                proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, cwd=str(CASE_DIR.parents[2]))
                running[case] = {'proc': proc, 'pid': proc.pid, 'gpu': chosen, 'uuid': table[chosen]['uuid'], 'name': table[chosen]['name'],
                                 'started': now(), 'tries': 0, 'log': log.name, 'command': cmd}
                events.append({'utc': now(), 'case': case, 'gpu': chosen, 'event': f'started pid {proc.pid}', 'frames_present': frames_done(out)})
            save()
            time.sleep(30)
    finally:
        for case in list(running):
            stop(case, 'queue exiting')
        save()


if __name__ == '__main__':
    main()
