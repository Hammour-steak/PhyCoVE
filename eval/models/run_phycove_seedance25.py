#!/usr/bin/env python3
"""Run one PhyCoVE video edit through Seedance 2.5 and resume saved tasks."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse

import requests

from baselines.minimax_h3 import atomic_json, exclusive_lock, probe_video, sha256

API = 'https://ark.cn-beijing.volces.com/api/v3'
MODEL = 'doubao-seedance-2-5-260628'
DEFAULT_ROOT = os.environ.get('PHYCOVE_ROOT')  # release folder; without it --benchmark-root is required


def publication_root(benchmark_root: Path) -> Path:
    """Resolve a nested real subset to the enclosing publication directory."""
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


def api_json(response):
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f'Ark returned HTTP {response.status_code}, not JSON') from None
    if not response.ok:
        error = data.get('error') or {}
        # Do not log headers, request bodies, or temporary download credentials.
        message = str(error.get('message', ''))
        if 'https://' in message or 'data:' in message:
            message = 'Details contain a media URL; omitted from the log.'
        raise RuntimeError(f'Ark HTTP {response.status_code}: {error.get("code")}: {message[:500]}')
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark-root', type=Path, default=DEFAULT_ROOT, required=DEFAULT_ROOT is None,
                        help='Release folder with benchmark_manifest.json (default: $PHYCOVE_ROOT).')
    parser.add_argument('--predictions-root', type=Path)
    parser.add_argument('--global-id', default='curling_collision/edit_delete_yellow_stone')
    parser.add_argument('--source-url', required=True, help='Verified public URL of this exact source video.')
    parser.add_argument('--source-url-sha256', required=True, help='SHA256 independently checked at the source URL.')
    parser.add_argument('--prompt-flavor', choices=('quantitative', 'vague'), default='quantitative')
    parser.add_argument('--prompt-lang', choices=('en', 'zh'), default='en')
    parser.add_argument('--resolution', choices=('480p', '720p', '1080p'), default='720p')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--poll-timeout', type=float, default=1800)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--retry-rate-rejected', action='store_true',
                        help='Retry only an explicit HTTP 429 rejection without an accepted task ID.')
    parser.add_argument('--retry-input-download-rejected', action='store_true',
                        help='Retry an explicit HTTP 400 resource-download rejection without a task ID.')
    args = parser.parse_args(argv)
    root = args.benchmark_root.resolve()
    manifest = json.loads((root / 'benchmark_manifest.json').read_text())
    edit = next(e for e in manifest['edits'] if e['global_id'] == args.global_id)
    source = (root / edit['source_video']).resolve()
    source.relative_to(root)
    source_hash = sha256(source)
    record = next(s for s in manifest['sources'] if s['video'] == edit['source_video'])
    if source_hash != record['video_sha256'] or source_hash != args.source_url_sha256:
        raise ValueError('Source URL, manifest and local video must have the same verified SHA256')
    media = probe_video(source)
    if not 4 <= media['duration_sec'] <= 30 or not 24 <= media['fps'] <= 60:
        raise ValueError('Seedance edit input must have 4..30 seconds and 24..60 FPS')
    url = urlparse(args.source_url)
    if url.scheme != 'https' or not url.hostname or url.username or url.query or url.fragment:
        raise ValueError('Provide a public HTTPS URL without credentials or query parameters')
    prompt = edit['prompts'][args.prompt_flavor][args.prompt_lang]
    body = {
        'model': MODEL,
        'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'video_url', 'video_url': {'url': args.source_url}, 'role': 'reference_video'},
        ],
        'omni_reference_task_type': 'edit', 'resolution': args.resolution,
        'ratio': 'adaptive', 'duration': -1, 'generate_audio': False,
        'seed': args.seed, 'watermark': False,
    }
    predictions = (args.predictions_root or default_predictions_root(
        root, args.prompt_flavor, args.prompt_lang)).resolve()
    publication = publication_root(root)
    if predictions == publication or publication in predictions.parents:
        raise ValueError('Predictions must be outside the publication directory')
    scene, case = edit['scene'], edit['case_id']
    if args.global_id != scene + '/' + case or any(c not in
            'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in scene + case):
        raise ValueError('Unsafe scene/case ID')
    output = predictions / 'seedance25' / 'videos' / scene / (case + '.mp4')
    checkpoint = output.with_suffix('.task.json')
    identity = {'global_id': args.global_id, 'source_sha256': source_hash,
                'prompt_flavor': args.prompt_flavor, 'prompt_lang': args.prompt_lang, 'request': body}
    print(json.dumps({'global_id': args.global_id, 'prompt': prompt, 'source': str(source),
                      'source_media': media, 'model': MODEL, 'output': str(output)}, ensure_ascii=False), flush=True)
    if args.dry_run:
        print('Preflight passed; no API task submitted.', flush=True)
        return 0
    key = os.environ.get('ARK_API_KEY')
    if not key:
        raise ValueError('ARK_API_KEY is not configured')
    session = requests.Session()
    session.headers['Authorization'] = 'Bearer ' + key
    started = time.time()
    try:
        with exclusive_lock(output.with_suffix('.lock')):
            state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
            if state and state.get('identity') != identity:
                raise ValueError('Saved task has a different request; use a different predictions directory')
            attempts = state.get('previous_attempts', [])
            error = str(state.get('error', ''))
            retry_rate = args.retry_rate_rejected and re.search(r'HTTP 429\b', error)
            retry_media = (args.retry_input_download_rejected and 'HTTP 400' in error
                           and 'resource download failed' in error.lower())
            if ((retry_rate or retry_media) and state.get('status') == 'submission_rejected'
                    and not state.get('task_id')):
                attempts = attempts + [{k: state[k] for k in ('status', 'error', 'started_at') if k in state}]
                state = {}
            if state.get('status') == 'completed':
                if not output.exists() or sha256(output) != state['output_sha256']:
                    raise ValueError('Completed output is missing or its hash changed')
                print('Reused verified output: ' + str(output), flush=True)
                return 0
            if state.get('status') in ('failed', 'cancelled', 'canceled', 'expired', 'submission_rejected'):
                raise RuntimeError('Saved task is terminal; inspect its error before submitting another task')
            if state and not state.get('task_id'):
                raise RuntimeError('Previous submission is ambiguous; check Ark task history before resubmitting')
            if not state:
                state = {'identity': identity, 'status': 'submitting', 'started_at': started,
                         'previous_attempts': attempts}
                atomic_json(checkpoint, state)
                response = session.post(API + '/contents/generations/tasks', json=body, timeout=(15, 120))
                if 400 <= response.status_code < 500 and response.status_code != 408:
                    state['status'] = 'submission_rejected'
                    try:
                        api_json(response)
                    except RuntimeError as exc:
                        state['error'] = str(exc)
                        atomic_json(checkpoint, state)
                        raise
                data = api_json(response)
                state.update(task_id=data['id'], status='submitted')
                atomic_json(checkpoint, state)
                print('Task submitted: ' + state['task_id'], flush=True)
            deadline = time.monotonic() + args.poll_timeout
            errors = 0
            while time.monotonic() < deadline:
                try:
                    data = api_json(session.get(API + '/contents/generations/tasks/' + state['task_id'], timeout=(15, 45)))
                    errors = 0
                except requests.RequestException:
                    errors += 1
                    if errors >= 3:
                        raise RuntimeError('Status query failed; rerun to resume the saved task') from None
                    time.sleep(10)
                    continue
                status = data.get('status', '')
                if status != state['status']:
                    print('Task status: ' + status, flush=True)
                state.update(status=status, updated_at=time.time())
                if status in ('failed', 'cancelled', 'canceled', 'expired'):
                    state['error'] = data.get('error')
                atomic_json(checkpoint, state)
                if status in ('failed', 'cancelled', 'canceled', 'expired'):
                    raise RuntimeError(f'Task {status}: {state.get("error")}')
                if status == 'succeeded':
                    result_url = data['content']['video_url']
                    if urlparse(result_url).scheme != 'https':
                        raise RuntimeError('Result URL is not HTTPS')
                    part = output.with_suffix('.part.mp4')
                    # The bearer credential is sent only to Ark, never to the CDN.
                    with requests.get(result_url, stream=True, timeout=(15, 120)) as result:
                        if not result.ok:
                            raise RuntimeError(f'Result download returned HTTP {result.status_code}; rerun to resume')
                        with part.open('wb') as stream:
                            for chunk in result.iter_content(1024 * 1024):
                                if chunk:
                                    stream.write(chunk)
                    metadata = probe_video(part)
                    part.replace(output)
                    state.update(status='completed', output_video=str(output), output_sha256=sha256(output),
                                 output_media=metadata, usage=data.get('usage'),
                                 elapsed_sec=round(time.time() - state['started_at'], 3))
                    atomic_json(checkpoint, state)
                    print(json.dumps({k: state[k] for k in ('status', 'task_id', 'output_video', 'output_media', 'elapsed_sec', 'usage')}, ensure_ascii=False), flush=True)
                    return 0
                time.sleep(10)
            raise TimeoutError('Polling timed out; rerun this command to resume the same task')
    finally:
        session.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except requests.RequestException as exc:
        print(f'{type(exc).__name__}: network request failed; consult the checkpoint to resume safely', file=sys.stderr)
        sys.exit(1)
    except (ValueError, RuntimeError, TimeoutError, OSError, KeyError, StopIteration) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
