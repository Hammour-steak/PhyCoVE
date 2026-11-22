#!/usr/bin/env python3
"""Official Kling 4.0 video editing; resumable tasks, no automatic paid retries.

Schema: https://kling.ai/document-api/api/video/4-0/video-omni
Pricing: https://kling.ai/dev/pricing
Requires requests and ffprobe. Credentials come only from KLING_API_KEY.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlparse
import uuid

import requests


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@contextmanager
def exclusive_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f'Another process is using {path}') from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def probe_video(path):
    result = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=codec_name,width,height,avg_frame_rate,nb_frames:format=duration',
        '-of', 'json', str(path),
    ], check=True, capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    stream = data['streams'][0]
    numerator, denominator = stream['avg_frame_rate'].split('/')
    return {'codec': stream['codec_name'], 'width': int(stream['width']),
            'height': int(stream['height']), 'fps': float(numerator) / float(denominator),
            'duration_sec': float(data['format']['duration']),
            'frames': int(stream['nb_frames']) if str(stream.get('nb_frames', '')).isdigit() else None}


def https_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Provide an HTTPS URL without embedded credentials or a fragment')
    return url


class Kling4Client:
    model = 'kling-4.0'

    def __init__(self, api_base=None, resolution='720p', duration=4,
                 aspect_ratio='adaptive', audio='native', poll_interval=10,
                 poll_timeout=1800, request_timeout=90):
        self.api_base = (api_base or os.getenv('KLING_API_BASE', 'https://api-beijing.klingai.com')).rstrip('/')
        if self.api_base not in ('https://api-beijing.klingai.com', 'https://api-singapore.klingai.com'):
            raise ValueError('Use an official Beijing or Singapore Kling API base')
        if resolution not in ('720p', '1080p') or not isinstance(duration, int) or not 3 <= duration <= 30:
            raise ValueError('Kling 4.0 requires 720p/1080p and an integer duration of 3..30 seconds')
        if aspect_ratio not in ('adaptive', '21:9', '16:9', '9:16', '1:1'):
            raise ValueError('Invalid aspect ratio')
        if audio not in ('native', 'original') or min(poll_interval, poll_timeout, request_timeout) <= 0:
            raise ValueError('Invalid audio mode or timeout')
        self.settings = dict(resolution=resolution, duration=duration, aspect_ratio=aspect_ratio, audio=audio)
        self.poll_interval, self.poll_timeout, self.request_timeout = poll_interval, poll_timeout, request_timeout
        self.config = dict(model=self.model, api_base=self.api_base, settings=self.settings,
                           prompt_prefix='Edit @Video1. ')
        self.api = self.media = None
        self._verified_urls = set()

    def setup(self):
        key = os.environ.get('KLING_API_KEY', '').strip()
        if not key:
            raise RuntimeError('KLING_API_KEY is not set')
        self.api = requests.Session()
        self.api.headers.update({'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
        # Source URLs and output CDNs must never receive the API credential.
        self.media = requests.Session()

    def close(self):
        for session in (self.api, self.media):
            if session is not None:
                session.close()

    def identity(self, source_video, prompt):
        path = Path(source_video)
        if not prompt.strip() or len('Edit @Video1. ' + prompt.strip()) > 26000:
            raise ValueError('Prompt must contain 1..25987 characters')
        if path.suffix.lower() not in ('.mp4', '.mov') or not 0 < path.stat().st_size <= 300 * 1024**2:
            raise ValueError('Source must be a nonempty MP4/MOV of at most 300 MiB')
        info = probe_video(path)
        width, height = info['width'], info['height']
        if not (3 <= info['duration_sec'] <= 30 and 24 <= info['fps'] <= 60
                and 700 <= min(width, height) and max(width, height) <= 4553
                and width * height <= 8294400 and 0.4 <= width / height <= 2.5):
            raise ValueError(f'Source exceeds official Kling 4.0 video limits: {info}')
        return {**self.config, 'source_sha256': sha256(path), 'source_metadata': info,
                'benchmark_prompt': prompt, 'api_prompt': 'Edit @Video1. ' + prompt.strip()}

    def estimate_units(self, source_duration):
        # With video input: rate * (output + max(input, output)).
        rate = {'720p': 0.6, '1080p': 0.9}[self.settings['resolution']]
        return round(rate * (self.settings['duration'] + max(source_duration, self.settings['duration'])), 6)

    def payload(self, source_url, prompt, external_id):
        return {'contents': [{'type': 'prompt', 'text': 'Edit @Video1. ' + prompt.strip()},
                             {'type': 'base_video', 'url': https_url(source_url), 'id': 'Video1'}],
                'settings': dict(self.settings),
                'options': {'external_task_id': external_id, 'watermark_info': {'enabled': False}}}

    def verify_source_url(self, url, expected_sha):
        https_url(url)
        if (url, expected_sha) in self._verified_urls:
            return
        digest, size = hashlib.sha256(), 0
        with self.media.get(url, stream=True, timeout=(10, self.request_timeout)) as response:
            response.raise_for_status()
            for block in response.iter_content(1024 * 1024):
                size += len(block)
                if size > 300 * 1024**2:
                    raise ValueError('Remote source exceeds 300 MiB')
                digest.update(block)
        if digest.hexdigest() != expected_sha:
            raise ValueError('Source URL does not match the local benchmark source SHA256')
        self._verified_urls.add((url, expected_sha))

    def query(self, *, task_id=None, external_id=None):
        if bool(task_id) == bool(external_id):
            raise ValueError('Query by exactly one task ID or external ID')
        params = {'task_ids': task_id} if task_id else {'external_task_ids': external_id}
        for attempt in range(3):
            try:
                response = self.api.get(self.api_base + '/tasks', params=params,
                                        timeout=self.request_timeout, allow_redirects=False)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                body = response.json()
                if response.status_code != 200 or body.get('code') != 0:
                    raise RuntimeError(f'Kling query HTTP {response.status_code}: {body}')
                rows = body.get('data', [])
                if not isinstance(rows, list):
                    raise RuntimeError('Unexpected Kling task query schema')
                matches = [r for r in rows if (r.get('id') == task_id if task_id else r.get('external_id') == external_id)]
                if len(matches) > 1:
                    raise RuntimeError('Multiple tasks returned for a unique ID')
                return matches[0] if matches else None
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def _download(self, url, output):
        https_url(url)
        temporary = output.with_name(output.name + '.part')
        with self.media.get(url, stream=True, timeout=self.request_timeout) as response:
            response.raise_for_status()
            with temporary.open('wb') as stream:
                for block in response.iter_content(1024 * 1024):
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
        info = probe_video(temporary)
        if info['duration_sec'] <= 0:
            raise RuntimeError('Downloaded output is not a valid video')
        temporary.replace(output)
        return info

    def edit_video(self, source_video, source_url, prompt, output):
        if self.api is None:
            raise RuntimeError('Call setup() first')
        started = time.monotonic()
        output = Path(output).resolve()
        state_path = output.with_suffix('.task.json')
        identity = self.identity(source_video, prompt)
        with exclusive_lock(output.with_suffix('.lock')):
            state = json.loads(state_path.read_text()) if state_path.exists() else None
            if state and state.get('identity') != identity:
                raise ValueError('Existing task uses another source/prompt/config; use another output path')
            if state and state.get('phase') == 'completed' and output.is_file():
                if sha256(output) != state['output_sha256']:
                    raise ValueError('Completed output SHA256 changed')
                return dict(state, reused_existing=True, elapsed_sec=0)
            if output.exists() and not state:
                raise ValueError('Output exists without a matching task checkpoint')
            if not state:
                state = {'identity': identity, 'external_id': 'pcve-kling4-' + uuid.uuid4().hex,
                         'phase': 'prepared', 'created_at': time.time()}
                atomic_json(state_path, state)
            if state['phase'] in ('rejected', 'failed'):
                raise RuntimeError(f"Saved task {state['phase']}: {state.get('error')}; no automatic resubmission")
            if not state.get('task_id') and state['phase'] != 'prepared':
                found = self.query(external_id=state['external_id'])
                if not found:
                    raise RuntimeError('Previous submission outcome is unknown; no second POST was sent. '
                                       f"Query external_task_ids={state['external_id']} later.")
                state.update(task_id=found['id'], phase='accepted')
                atomic_json(state_path, state)
            if not state.get('task_id'):
                self.verify_source_url(source_url, identity['source_sha256'])
                payload = self.payload(source_url, prompt, state['external_id'])
                # Persist before the paid POST. A timeout/crash must not create a duplicate.
                state.update(phase='submitting', payload=payload)
                atomic_json(state_path, state)
                response = self.api.post(self.api_base + '/omni-video/kling-4.0', json=payload,
                                         timeout=self.request_timeout, allow_redirects=False)
                body = response.json()
                state['submit_response'] = body
                if response.status_code != 200 or body.get('code') != 0:
                    state.update(phase='rejected' if response.status_code < 500 else 'submitting',
                                 error=f'HTTP {response.status_code}: {body}')
                    atomic_json(state_path, state)
                    raise RuntimeError(state['error'])
                task_id = body.get('data', {}).get('id')
                if not task_id:
                    atomic_json(state_path, state)
                    raise RuntimeError('Submission reply has no task ID; rerun to reconcile by external ID')
                state.update(task_id=task_id, phase='accepted')
                atomic_json(state_path, state)
                print(f'Kling 4.0 submitted: {task_id}', flush=True)
            deadline, previous = time.monotonic() + self.poll_timeout, None
            while time.monotonic() < deadline:
                task = self.query(task_id=state['task_id'])
                if task:
                    status = task.get('status')
                    state.update(task=task, updated_at=time.time())
                    atomic_json(state_path, state)
                    if status != previous:
                        print(f"Kling task {state['task_id']}: {status}", flush=True)
                        previous = status
                    if status == 'failed':
                        state.update(phase='failed', error=task.get('status_msg') or task.get('message') or task)
                        atomic_json(state_path, state)
                        raise RuntimeError(f'Kling task failed: {state["error"]}')
                    if status == 'succeeded':
                        videos = [item for item in task.get('outputs', []) if item.get('type') == 'video' and item.get('url')]
                        if len(videos) != 1:
                            raise RuntimeError('Expected exactly one video in task.outputs')
                        info = self._download(videos[0]['url'], output)
                        state.update(phase='completed', output=str(output), output_metadata=info,
                                     output_sha256=sha256(output), elapsed_sec=time.monotonic() - started,
                                     completed_at=time.time())
                        atomic_json(state_path, state)
                        return dict(state, reused_existing=False)
                time.sleep(min(self.poll_interval, 60))
            raise RuntimeError('Polling timed out; rerun the same command to resume this task')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-video', required=True, type=Path)
    parser.add_argument('--source-url', required=True, help='Provider-readable HTTPS URL; bytes must match --source-video')
    parser.add_argument('--prompt', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--api-base')
    parser.add_argument('--resolution', choices=('720p', '1080p'), default='720p')
    parser.add_argument('--duration', type=int, default=4)
    parser.add_argument('--max-units', type=float, default=6)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    client = Kling4Client(api_base=args.api_base, resolution=args.resolution, duration=args.duration)
    identity = client.identity(args.source_video, args.prompt)
    units = client.estimate_units(identity['source_metadata']['duration_sec'])
    print(json.dumps({'identity': identity, 'estimated_units': units}, ensure_ascii=False, indent=2))
    if args.dry_run:
        return
    if not 0 < units <= args.max_units:
        parser.error('Estimated consumption exceeds --max-units')
    client.setup()
    try:
        result = client.edit_video(args.source_video, args.source_url, args.prompt, args.output)
        print(json.dumps({k: result.get(k) for k in ('task_id', 'output', 'output_metadata', 'reused_existing')}, indent=2))
    finally:
        client.close()


if __name__ == '__main__':
    main()
