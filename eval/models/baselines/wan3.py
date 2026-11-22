"""Wan 3.0 source-video editing, with persistent recovery of paid API tasks.

Only the source clip and selected benchmark prompt are sent to the provider.
Official schemas: https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference
Uploads: https://help.aliyun.com/zh/model-studio/get-temporary-file-url
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any
from urllib.parse import quote, urlparse

import requests

from .base import BaselineModel, BaselineResult


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


@contextmanager
def exclusive_lock(path: Path):
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


def probe_video(path: Path) -> dict[str, Any]:
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


class SubmissionRejected(RuntimeError):
    """Provider explicitly rejected submission, rather than losing its reply."""


class Wan3Baseline(BaselineModel):
    name = 'wan3_0_video'

    def __init__(self, model_id: str | None = None, api_base: str | None = None,
                 resolution: str = '720P', duration: int = 4,
                 ratio: str = 'adaptive', seed: int = 42,
                 poll_interval: float = 15, poll_timeout: float = 1800,
                 request_timeout: float = 120, retry_failed: bool = False,
                 **kwargs: Any) -> None:
        self.model_id = model_id or 'wan3.0-video'
        workspace = os.getenv('DASHSCOPE_WORKSPACE_ID')
        default_base = (f'https://{workspace}.cn-beijing.maas.aliyuncs.com/api/v1'
                        if workspace else 'https://dashscope.aliyuncs.com/api/v1')
        self.api_base = (api_base or os.getenv('DASHSCOPE_API_BASE', default_base)).rstrip('/')
        url = urlparse(self.api_base)
        if (url.scheme != 'https' or not url.hostname or not url.hostname.endswith('.aliyuncs.com')
                or url.username or url.password or url.query or url.fragment
                or not self.api_base.endswith('/api/v1')):
            raise ValueError('Use an Alibaba Cloud HTTPS API base ending in /api/v1')
        if self.model_id not in ('wan3.0-video', 'wan3.0-video-prime'):
            raise ValueError('This adapter supports wan3.0-video / wan3.0-video-prime')
        if resolution not in ('480P', '720P', '1080P') or not 2 <= duration <= 30:
            raise ValueError('Wan3 requires 480P/720P/1080P and duration 2..30 seconds')
        if ratio not in ('adaptive', '21:9', '16:9', '4:3', '1:1', '3:4', '9:16'):
            raise ValueError('Invalid ratio')
        if not 0 <= seed <= 2147483647 or min(poll_interval, poll_timeout, request_timeout) <= 0:
            raise ValueError('Invalid seed or timeout')
        self.resolution, self.duration, self.ratio, self.seed = resolution, duration, ratio, seed
        self.poll_interval, self.poll_timeout = poll_interval, poll_timeout
        self.request_timeout, self.retry_failed = request_timeout, retry_failed
        self._session = self._media_session = None
        super().__init__(model_id=self.model_id, api_base=self.api_base,
                         resolution=resolution, duration=duration, ratio=ratio,
                         seed=seed, audio=False, prompt_extend=False, **kwargs)

    def setup(self) -> None:
        key = os.environ.get('DASHSCOPE_API_KEY')
        if not key:
            raise RuntimeError('DASHSCOPE_API_KEY is not set')
        self._session = requests.Session()
        self._session.headers.update({'Authorization': f'Bearer {key}'})
        # CDN downloads and signed OSS uploads must not receive the API bearer.
        self._media_session = requests.Session()

    def teardown(self) -> None:
        for session in (self._session, self._media_session):
            if session is not None:
                session.close()

    def request_identity(self, source_video: Path, prompt: str) -> dict[str, Any]:
        if not prompt.strip() or len(prompt) > 20000:
            raise ValueError('Prompt must contain 1..20000 characters')
        if source_video.suffix.lower() not in ('.mp4', '.mov') or not 0 < source_video.stat().st_size <= 100 * 1024**2:
            raise ValueError('Source must be a nonempty MP4/MOV of at most 100 MiB')
        media = probe_video(source_video)
        if not 1 <= media['duration_sec'] <= 15 or media['duration_sec'] + self.duration > 30.01:
            raise ValueError('Source must be 1..15 seconds; input + output must be at most 30 seconds')
        if (media['fps'] < 16 or min(media['width'], media['height']) < 240
                or max(media['width'], media['height']) > 4096
                or max(media['width'], media['height']) / min(media['width'], media['height']) > 8):
            raise ValueError('Source dimensions or FPS exceed Wan3 reference-video limits')
        return {**self.config, 'source_sha256': sha256(source_video),
                'prompt': prompt, 'source_metadata': media}

    def estimate_cost(self, source_duration: float) -> float:
        # Beijing list price; no assumed free quota or promotional discount.
        rate = {'480P': 0.3, '720P': 0.6, '1080P': 1.2}[self.resolution]
        if self.model_id.endswith('-prime'):
            rate *= 1.5
        return round((source_duration + self.duration) * rate, 6)

    def build_payload(self, source_url: str, prompt: str) -> dict[str, Any]:
        return {'model': self.model_id,
                'input': {'prompt': prompt, 'media': [{'type': 'reference_video', 'url': source_url}]},
                'parameters': {'resolution': self.resolution, 'duration': self.duration,
                               'ratio': self.ratio, 'seed': self.seed, 'audio': False,
                               'prompt_extend': False, 'watermark': False}}

    def upload_source(self, source: Path) -> str:
        response = self._session.get(self.api_base + '/uploads',
            params={'action': 'getPolicy', 'model': self.model_id}, timeout=self.request_timeout)
        response.raise_for_status()
        policy = response.json()['data']
        host = policy['upload_host']
        if urlparse(host).scheme != 'https':
            raise ValueError('Upload policy must specify HTTPS')
        name = sha256(source)[:16] + '-' + source.name
        object_key = policy['upload_dir'] + '/' + name
        fields = {'OSSAccessKeyId': policy['oss_access_key_id'], 'Signature': policy['signature'],
                  'policy': policy['policy'], 'x-oss-object-acl': policy['x_oss_object_acl'],
                  'x-oss-forbid-overwrite': policy['x_oss_forbid_overwrite'],
                  'key': object_key, 'success_action_status': '200'}
        with source.open('rb') as stream:
            uploaded = self._media_session.post(host, data=fields,
                files={'file': (name, stream, 'video/mp4')}, timeout=self.request_timeout)
        uploaded.raise_for_status()
        return 'oss://' + object_key

    def _create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Do not retry this paid POST: a lost response can still mean an accepted job.
        response = self._session.post(self.api_base + '/services/aigc/video-generation/video-synthesis',
            json=payload, headers={'X-DashScope-Async': 'enable',
                                  'X-DashScope-OssResourceResolve': 'enable'},
            timeout=self.request_timeout)
        data = response.json()
        if 400 <= response.status_code < 500 and response.status_code != 408:
            raise SubmissionRejected(f"HTTP {response.status_code} {data.get('code')}: {data.get('message')}")
        response.raise_for_status()
        if not (data.get('output') or {}).get('task_id'):
            raise RuntimeError('Submission reply has no task ID; reconcile before resubmitting')
        return data

    def _poll_task(self, state: dict[str, Any], checkpoint: Path) -> str:
        deadline = time.monotonic() + self.poll_timeout
        errors = 0
        last_status = None
        while time.monotonic() < deadline:
            try:
                response = self._session.get(self.api_base + '/tasks/' + quote(state['task_id'], safe=''),
                                             timeout=self.request_timeout)
                response.raise_for_status()
                data = response.json()
                output = data['output']
                status = output['task_status']
                if status not in ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELED', 'UNKNOWN'):
                    raise ValueError('Unknown provider status: ' + str(status))
                errors = 0
            except (requests.RequestException, ValueError, KeyError):
                errors += 1
                if errors > 3:
                    raise
                time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))
                continue
            state.update(status=status, provider_response=data, updated_at=time.time())
            if status == 'SUCCEEDED':
                state['result_url'] = output['video_url']
            atomic_json(checkpoint, state)
            if status != last_status:
                print(f"[wan3] task={state['task_id']} status={status}", flush=True)
                last_status = status
            if status == 'SUCCEEDED':
                return state['result_url']
            if status in ('FAILED', 'CANCELED', 'UNKNOWN'):
                raise RuntimeError(f"Task {status}: {output.get('code')}: {output.get('message')}")
            time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))
        raise TimeoutError('Polling timed out; rerun to resume the saved task without resubmitting')

    def _download(self, url: str, path: Path) -> dict[str, Any]:
        if urlparse(url).scheme != 'https':
            raise ValueError('Result must be an HTTPS URL')
        temporary = path.with_name(path.stem + '.part.mp4')
        for attempt in range(3):
            try:
                with self._media_session.get(url, stream=True, timeout=self.request_timeout) as response:
                    response.raise_for_status()
                    with temporary.open('wb') as stream:
                        for chunk in response.iter_content(1024 * 1024):
                            stream.write(chunk)
                media = probe_video(temporary)
                temporary.replace(path)
                return media
            except (requests.RequestException, OSError, ValueError, subprocess.SubprocessError):
                if attempt == 2:
                    raise
                time.sleep(2)

    def edit_video(self, source_video: Path, prompt: str, output_path: Path, *,
                   edit_info: dict[str, Any]) -> BaselineResult:
        started = time.monotonic()
        identity = self.request_identity(source_video, prompt)
        checkpoint = output_path.with_suffix('.task.json')
        with exclusive_lock(output_path.with_suffix('.task.lock')):
            state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
            if state and state['identity'] != identity:
                raise ValueError('Checkpoint input/config differs; use a different output directory')
            if state.get('status') == 'completed' and output_path.is_file():
                if sha256(output_path) != state.get('output_sha256'):
                    raise ValueError('Existing output hash differs from checkpoint')
                return BaselineResult(output_path, 0, {**state['summary'], 'reused_existing': True})
            if state.get('status') in ('submitting', 'submission_unknown') and not state.get('task_id'):
                raise RuntimeError('Previous submission outcome is unknown; reconcile it before another paid POST')
            if state.get('status') in ('rejected', 'FAILED', 'CANCELED', 'UNKNOWN'):
                if not self.retry_failed:
                    raise RuntimeError('Previous request failed; explicit --retry-failed is required to resubmit')
                state = {}
            if not state.get('task_id'):
                if output_path.exists():
                    raise ValueError('Output exists without a matching completed checkpoint')
                source_url = self.upload_source(source_video)
                payload = self.build_payload(source_url, prompt)
                state = {'identity': identity, 'status': 'submitting', 'created_at': time.time(),
                         'source_path': str(source_video), 'request': payload}
                atomic_json(checkpoint, state)
                try:
                    reply = self._create_task(payload)
                except SubmissionRejected as exc:
                    state.update(status='rejected', error=str(exc))
                    atomic_json(checkpoint, state)
                    raise
                except BaseException:
                    state['status'] = 'submission_unknown'
                    atomic_json(checkpoint, state)
                    raise
                state.update(task_id=str(reply['output']['task_id']), status=reply['output']['task_status'],
                             submission_response=reply)
                atomic_json(checkpoint, state)
            url = self._poll_task(state, checkpoint)
            media = self._download(url, output_path)
            summary = {'model_id': self.model_id, 'task_id': state['task_id'],
                       'source_sha256': identity['source_sha256'], 'raw_video': media,
                       'usage': state['provider_response'].get('usage', {}),
                       'estimated_list_cost_cny': self.estimate_cost(identity['source_metadata']['duration_sec'])}
            state.update(status='completed', output_sha256=sha256(output_path),
                         output_video=str(output_path), summary=summary, updated_at=time.time())
            atomic_json(checkpoint, state)
            return BaselineResult(output_path, time.monotonic() - started, summary)
