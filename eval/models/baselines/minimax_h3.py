"""MiniMax H3 v2 reference-video baseline with persistent task recovery.

Uses the BaselineModel interface of base.py. A request contains only
the source video and the selected edit prompt. Task checkpoints live beside
predictions; an interrupted poll/download resumes the same paid task.
"""
from __future__ import annotations

import base64
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
import warnings

import requests

from .base import BaselineModel, BaselineResult

API_BASE = 'https://api.minimax.cn/v2'
MODEL_DEFAULT = 'MiniMax-H3'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


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
    proc = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=codec_name,width,height,avg_frame_rate,nb_frames:format=duration',
        '-of', 'json', str(path),
    ], capture_output=True, text=True, timeout=120, check=True)
    data = json.loads(proc.stdout)
    stream = data['streams'][0]
    numerator, denominator = stream['avg_frame_rate'].split('/')
    result = {
        'codec': stream['codec_name'], 'width': int(stream['width']),
        'height': int(stream['height']), 'fps': float(numerator) / float(denominator),
        'duration_sec': float(data['format']['duration']),
        'frames': int(stream['nb_frames']) if str(stream.get('nb_frames', '')).isdigit() else None,
    }
    if min(result['width'], result['height'], result['fps'], result['duration_sec']) <= 0:
        raise ValueError(f'Invalid video: {path}')
    return result


class TaskRejected(RuntimeError):
    """An explicit API rejection, with no accepted task ID."""


class MinimaxH3Baseline(BaselineModel):
    name = 'minimax_h3'

    def __init__(self, model_id: str | None = None, resolution: str = '768P',
                 duration: int = 4, ratio: str = 'adaptive', api_base: str | None = None,
                 poll_interval: float = 10, poll_timeout: float = 1800,
                 request_timeout: float = 120, retry_failed: bool = False,
                 seed: int | None = None, **kwargs: Any) -> None:
        if seed is not None:
            warnings.warn('The verified H3 v2 request schema has no seed field; seed is not sent.')
        self.model_id = model_id or os.getenv('MINIMAX_MODEL', MODEL_DEFAULT)
        self.api_base = (api_base or os.getenv('MINIMAX_API_BASE', API_BASE)).rstrip('/')
        parsed = urlparse(self.api_base)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('--api-base must be an HTTPS API URL without credentials or query parameters')
        if not self.api_base.endswith('/v2'):
            raise ValueError('--api-base must include the /v2 suffix')
        if resolution not in ('768P', '2K') or not isinstance(duration, int) or not 4 <= duration <= 15:
            raise ValueError('H3 requires resolution 768P/2K and integer duration 4..15')
        if ratio not in ('adaptive', '21:9', '16:9', '4:3', '1:1', '3:4', '9:16'):
            raise ValueError(f'Unsupported aspect ratio: {ratio}')
        if min(poll_interval, poll_timeout, request_timeout) <= 0:
            raise ValueError('Timeouts and poll interval must be positive')
        self.resolution, self.duration, self.ratio = resolution, duration, ratio
        self.poll_interval, self.poll_timeout = poll_interval, poll_timeout
        self.request_timeout, self.retry_failed = request_timeout, retry_failed
        self._session: requests.Session | None = None
        self._download_session: requests.Session | None = None
        super().__init__(model_id=self.model_id, api_base=self.api_base,
                         resolution=resolution, duration=duration, ratio=ratio)

    def setup(self) -> None:
        key = os.environ.get('MINIMAX_API_KEY')
        if not key:
            raise RuntimeError('Set MINIMAX_API_KEY to a MiniMax pay-as-you-go API key.')
        self._session = requests.Session()
        self._session.headers.update({'Authorization': f'Bearer {key}'})
        # Never send the API bearer token to the result CDN.
        self._download_session = requests.Session()
        proxy = os.environ.get('MINIMAX_PROXY')
        if proxy:
            for session in (self._session, self._download_session):
                session.trust_env = False
                session.proxies.update({'https': proxy, 'http': proxy})

    def teardown(self) -> None:
        for session in (self._session, self._download_session):
            if session is not None:
                session.close()

    def request_identity(self, source_video: Path, prompt: str) -> dict[str, Any]:
        if not prompt.strip() or len(prompt) > 7000:
            raise ValueError('H3 prompt must contain 1..7000 characters')
        if not source_video.is_file() or not 0 < source_video.stat().st_size <= 50 * 1024 ** 2:
            raise ValueError(f'Source must be a nonempty video of at most 50 MiB: {source_video}')
        return {**self.config, 'prompt': prompt, 'source_sha256': sha256(source_video)}

    def build_payload(self, source_video: Path, prompt: str) -> dict[str, Any]:
        mime = 'video/quicktime' if source_video.suffix.lower() == '.mov' else 'video/mp4'
        uri = f'data:{mime};base64,' + base64.b64encode(source_video.read_bytes()).decode('ascii')
        body = {'model': self.model_id,
                'content': [{'type': 'text', 'text': prompt},
                            {'type': 'video_url', 'video_url': {'url': uri}, 'role': 'reference_video'}],
                'duration': self.duration, 'resolution': self.resolution, 'ratio': self.ratio}
        if len(json.dumps(body).encode('utf-8')) > 64 * 1024 ** 2:
            raise ValueError('Base64 request exceeds 64 MiB; use a smaller supported source file')
        return body

    @staticmethod
    def _check_api(data: dict[str, Any]) -> None:
        base = data.get('base_resp') or {}
        if str(base.get('status_code', 0)) != '0':
            raise TaskRejected(f"MiniMax API {base.get('status_code')}: {str(base.get('status_msg', ''))[:500]}")

    def _create_task(self, body: dict[str, Any]) -> str:
        assert self._session is not None
        # No automatic retries of a potentially accepted paid POST.
        with self._session.post(self.api_base + '/video_generation', json=body,
                                timeout=self.request_timeout) as response:
            if 400 <= response.status_code < 500 and response.status_code != 408:
                raise TaskRejected(f'MiniMax submission rejected: HTTP {response.status_code}')
            response.raise_for_status()
            data = response.json()
        task_id = data.get('task_id')
        if task_id:
            return str(task_id)
        self._check_api(data)
        raise RuntimeError('Submission response has no task_id; reconcile the request before retrying')

    def _poll_task(self, state: dict[str, Any], checkpoint: Path) -> str:
        assert self._session is not None
        deadline = time.monotonic() + self.poll_timeout
        errors = 0
        while time.monotonic() < deadline:
            try:
                with self._session.get(self.api_base + '/query/video_generation/' + quote(state['task_id'], safe=''),
                                       timeout=self.request_timeout) as response:
                    response.raise_for_status()
                    data = response.json()
                self._check_api(data)
                task = data.get('task')
                if not isinstance(task, dict):
                    raise ValueError('Query response has no task object')
                status = str(task.get('status', '')).lower()
                if status not in ('queued', 'pending', 'processing', 'running', 'preparing',
                                  'succeeded', 'failed', 'cancelled', 'canceled', 'expired'):
                    raise ValueError(f'Unrecognized H3 task status: {status!r}')
                errors = 0
            except (requests.RequestException, ValueError) as exc:
                # Status queries are safe to repeat; never regenerate on query failure.
                errors += 1
                if errors > 3 or (isinstance(exc, requests.HTTPError) and
                                  exc.response is not None and exc.response.status_code in (401, 402, 403, 404)):
                    raise
                time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))
                continue
            state.update(status=status, updated_at=time.time())
            if status == 'succeeded':
                url = (task.get('content') or {}).get('url')
                if not isinstance(url, str) or urlparse(url).scheme not in ('https', 'http'):
                    raise RuntimeError('Succeeded task has no HTTP video URL')
                state['result_url'] = url
            if status in ('failed', 'cancelled', 'canceled', 'expired'):
                state['task_error'] = task.get('error')
            atomic_json(checkpoint, state)
            if status == 'succeeded':
                return state['result_url']
            if status in ('failed', 'cancelled', 'canceled', 'expired'):
                raise RuntimeError(f"Task {state['task_id']} {status}: {state.get('task_error')}")
            time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))
        raise TimeoutError(f"Task {state['task_id']} is still pending; rerun to resume this task")

    def _download_video(self, url: str, output_path: Path) -> dict[str, Any]:
        assert self._download_session is not None
        tmp = output_path.with_name(output_path.stem + '.part.mp4')
        for attempt in range(3):
            try:
                with self._download_session.get(url, stream=True, timeout=self.request_timeout) as response:
                    response.raise_for_status()
                    with tmp.open('wb') as stream:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                stream.write(chunk)
                metadata = probe_video(tmp)
                tmp.replace(output_path)
                return metadata
            except (requests.RequestException, ValueError, KeyError, IndexError, subprocess.SubprocessError):
                if attempt == 2:
                    raise
                time.sleep(min(self.poll_interval, 10))
            finally:
                tmp.unlink(missing_ok=True)
        raise AssertionError('unreachable')

    def edit_video(self, source_video: Path, prompt: str, output_path: Path,
                   *, edit_info: dict[str, Any]) -> BaselineResult:
        started = time.perf_counter()
        identity = self.request_identity(source_video, prompt)
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        checkpoint = output_path.with_suffix('.task.json')
        with exclusive_lock(output_path.with_suffix('.lock')):
            state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
            if state and state.get('request_fingerprint') != fingerprint:
                raise RuntimeError(f'Prompt/source/config changed for {output_path}; use a new predictions root')
            if output_path.exists():
                # Recover a crash between the atomic video rename and checkpoint update.
                if state.get('status') == 'succeeded' and state.get('task_id'):
                    state.update(status='completed', output_media=probe_video(output_path),
                                 output_sha256=sha256(output_path), completed_at=time.time())
                    atomic_json(checkpoint, state)
                if not state or state.get('status') != 'completed':
                    raise RuntimeError(f'Output exists without a completed matching checkpoint: {output_path}')
                if sha256(output_path) != state['output_sha256']:
                    raise RuntimeError(f'Prediction checksum mismatch: {output_path}')
                return BaselineResult(output_path, 0, {**self.config, 'task_id': state['task_id'],
                                                       'reused_existing': True, 'media': state['output_media']})
            if state.get('status') in ('failed', 'cancelled', 'canceled', 'expired', 'rejected'):
                if not self.retry_failed:
                    raise RuntimeError(f"Previous task {state.get('task_id')} was {state['status']}; "
                                       'use --retry-failed to explicitly submit another task')
                history = state.get('previous_attempts', []) + [{k: v for k, v in state.items()
                                                              if k != 'previous_attempts'}]
                state = {'previous_attempts': history}
            if not state.get('task_id'):
                if state.get('status') in ('submitting', 'submission_unknown'):
                    raise RuntimeError(f'Unknown submission outcome in {checkpoint}; set the confirmed task_id '
                                       'in that checkpoint before resuming, or reconcile it with MiniMax first')
                body = self.build_payload(source_video, prompt)
                state.update(schema_version=1, global_id=edit_info.get('global_id'), request=identity,
                             request_fingerprint=fingerprint, source_video=str(source_video.resolve()),
                             status='submitting', created_at=time.time())
                atomic_json(checkpoint, state)
                try:
                    task_id = self._create_task(body)
                except TaskRejected as exc:
                    state.update(status='rejected', error=str(exc))
                    atomic_json(checkpoint, state)
                    raise
                except BaseException:
                    state['status'] = 'submission_unknown'
                    atomic_json(checkpoint, state)
                    raise
                state.update(task_id=task_id, status='submitted')
                atomic_json(checkpoint, state)
            # Requery even after a failed download: signed CDN links may have expired.
            url = self._poll_task(state, checkpoint)
            media = self._download_video(url, output_path)
            state.update(status='completed', output_sha256=sha256(output_path), output_media=media,
                         completed_at=time.time())
            atomic_json(checkpoint, state)
        return BaselineResult(output_path, time.perf_counter() - started,
                              {**self.config, 'task_id': state['task_id'], 'media': media,
                               'reused_existing': False})
