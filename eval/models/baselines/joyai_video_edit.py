"""JoyAI-Video-Edit (jd-opensource, Apache-2.0) as a local PhyCoVE baseline.

Runs the official streaming runtime (`deploy/xvideo`, JoyOmniRuntime) in this
process, the same way the official server handles an uploaded mp4
(`source == "file"`): lossless output frames, no face/person gating, no static
KV freezing, no prompt enhancement, 2 denoising steps, seed 42. The model sees
only the source video and the selected edit prompt, verbatim.

Low-VRAM layout (FP8 DiT staged block by block, MiMo-VL text encoder offloaded
to CPU) is the official setting for cards with <= 48 GB, which includes the
48 GB RTX 4090s. Must run in the JoyAI Python environment (see
eval/README.md).
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from .base import BaselineModel, BaselineResult

MODEL_ROOT = Path(os.environ.get('MODEL_ROOT', 'models')) / 'JoyAI-Video-Edit'  # MODEL_ROOT: folder of the model deployments
DIT_DEFAULT = 'joyai_video_edit_dit_1101_face++.pth'
UPSTREAM_COMMIT = 'd5d459996b9db56ebbec611ae5d23e3d174c1a73'
# Official session sizes (deploy/run_server.sh): 480p = 840x480, 720p = 1248x720.
RESOLUTIONS = {'480p': (480, 840), '720p': (720, 1248)}


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
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
        'stream=codec_name,width,height,avg_frame_rate,nb_read_frames:format=duration',
        '-of', 'json', str(path),
    ], capture_output=True, text=True, timeout=120, check=True)
    data = json.loads(proc.stdout)
    stream = data['streams'][0]
    numerator, denominator = stream['avg_frame_rate'].split('/')
    result = {
        'codec': stream['codec_name'], 'width': int(stream['width']),
        'height': int(stream['height']), 'fps': float(numerator) / float(denominator),
        'duration_sec': float(data['format']['duration']),
        'frames': int(stream['nb_read_frames']),
    }
    if min(result['width'], result['height'], result['fps'], result['frames']) <= 0:
        raise ValueError(f'Invalid video: {path}')
    return result


def read_frames(path: Path):
    """All frames of the first video stream as RGB PIL images, plus the stream FPS."""
    import av
    frames = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate)
        for frame in container.decode(stream):
            frames.append(frame.to_image())
    if not frames:
        raise ValueError(f'No frames decoded: {path}')
    return frames, fps


def write_h264(frames, fps: float, path: Path, crf: int) -> None:
    """Encode uint8 HxWx3 RGB frames as H.264 yuv420p at the given constant frame rate."""
    height, width = frames[0].shape[:2]
    proc = subprocess.Popen([
        'ffmpeg', '-nostdin', '-y', '-loglevel', 'error',
        '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', f'{fps:g}', '-i', '-',
        '-c:v', 'libx264', '-preset', 'medium', '-crf', str(crf), '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart', str(path),
    ], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in frames:
            if frame.shape[:2] != (height, width):
                raise ValueError('Output frames changed size mid-video')
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    err = proc.stderr.read().decode(errors='replace')
    if proc.wait() != 0:
        raise RuntimeError(f'ffmpeg failed for {path}: {err[-800:]}')


class JoyAIVideoEditBaseline(BaselineModel):
    name = 'joyai_video_edit'

    def __init__(self, model_root: Path | str = MODEL_ROOT, dit_ckpt: str | None = None,
                 resolution: str = '720p', num_inference_steps: int = 2, seed: int = 42,
                 max_temporal_ids: int = 8, max_inflight_chunks: int = 2, low_vram: bool = True,
                 crf: int = 10, chunk_timeout: float = 600, **kwargs: Any) -> None:
        if resolution not in RESOLUTIONS:
            raise ValueError(f'resolution must be one of {sorted(RESOLUTIONS)}')
        if num_inference_steps < 1 or max_temporal_ids < 1 or max_inflight_chunks < 1:
            raise ValueError('steps, max_temporal_ids and max_inflight_chunks must be positive')
        if not 0 <= crf <= 51:
            raise ValueError('crf must be in 0..51')
        self.model_root = Path(model_root)
        self.dit_ckpt = Path(dit_ckpt) if dit_ckpt else (
            self.model_root / 'checkpoints/JoyAI-Video-Edit/dit' / DIT_DEFAULT)
        self.vae_ckpt = self.model_root / 'checkpoints/JoyAI-Video-Edit/vae'
        self.text_encoder_ckpt = self.model_root / 'checkpoints/MiMo-VL-7B-RL-2508'
        self.deploy_dir = self.model_root / 'src/JoyAI-Video-Edit/deploy'
        self.height, self.width = RESOLUTIONS[resolution]
        self.num_inference_steps, self.seed = num_inference_steps, seed
        self.max_temporal_ids, self.max_inflight_chunks = max_temporal_ids, max_inflight_chunks
        self.low_vram, self.crf, self.chunk_timeout = low_vram, crf, chunk_timeout
        self.runtime = None
        self.load_sec: float | None = None
        # Everything that changes the generated pixels is in the config, so a
        # changed setting is caught by the run-manifest / checkpoint fingerprint.
        super().__init__(model='JoyAI-Video-Edit', upstream_commit=UPSTREAM_COMMIT,
                         dit_ckpt=self.dit_ckpt.name, resolution=resolution,
                         height=self.height, width=self.width,
                         num_inference_steps=num_inference_steps, seed=seed,
                         max_temporal_ids=max_temporal_ids, low_vram_fp8=low_vram,
                         freeze_kv_on_static=False, prompt_enhancement=False,
                         output='lossless frames -> H.264 yuv420p', crf=crf)

    # ------------------------------------------------------------------ setup
    def check_files(self) -> None:
        for path in (self.dit_ckpt, self.vae_ckpt / 'diffusion_pytorch_model.safetensors',
                     self.text_encoder_ckpt / 'model.safetensors.index.json',
                     self.deploy_dir / 'xvideo/serving/joyomni_streaming.py'):
            if not path.exists():
                raise FileNotFoundError(f'JoyAI-Video-Edit file missing: {path}')

    def setup(self) -> None:
        self.check_files()
        cache = self.model_root / 'cache_rtx4090'
        defaults = {
            # RTX 4090 (Ada, sm_89): no FA4 (Blackwell only); PyTorch SDPA attention.
            'JOYOMNI_FA4_ATTN': '0', 'JOYOMNI_SAGE_ATTN': '0',
            'JOYOMNI_FP8_IMG': '1', 'JOYOMNI_FP8_TXT': '1', 'JOYOMNI_FP8_FAST_ACCUM': '0',
            'JOYOMNI_CUDA_GRAPH': '1', 'JOYOMNI_LOW_VRAM': '1' if self.low_vram else '0',
            'TORCHINDUCTOR_CACHE_DIR': str(cache / 'torchinductor'),
            'TRITON_CACHE_DIR': str(cache / 'triton'),
            'CUDA_CACHE_PATH': str(cache / 'nv_compute'),
            'TORCHINDUCTOR_FX_GRAPH_CACHE': '1',
            'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True',
            'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
        }
        for key, value in defaults.items():
            os.environ.setdefault(key, value)
        os.environ['JOYOMNI_LOW_VRAM'] = '1' if self.low_vram else '0'
        for key in ('TORCHINDUCTOR_CACHE_DIR', 'TRITON_CACHE_DIR', 'CUDA_CACHE_PATH'):
            Path(os.environ[key]).mkdir(parents=True, exist_ok=True)
        if str(self.deploy_dir) not in sys.path:
            sys.path.insert(0, str(self.deploy_dir))

        import logging
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('JoyAI-Video-Edit needs a CUDA GPU; set CUDA_VISIBLE_DEVICES to one free card')
        logging.getLogger('torch.utils._sympy.interp').setLevel(logging.ERROR)
        from xvideo.inductor_autotune_fix import install as install_autotune_fix
        install_autotune_fix()
        from xvideo.serving.joyomni_streaming import JoyOmniRuntime
        started = time.perf_counter()
        self.runtime = JoyOmniRuntime.load(
            str(self.dit_ckpt), vae_ckpt=str(self.vae_ckpt),
            text_encoder_ckpt=str(self.text_encoder_ckpt),
            device='cuda:0', vae_encode_device='cuda:0', vae_decode_device='cuda:0',
            vae_pseudo_device='cuda:0', postprocess_device='cuda:0', seed=self.seed,
            warmup_height=self.height, warmup_width=self.width)
        # Uploaded-file mode of the official server: return raw uint8 frames, not JPEG.
        self.runtime.lossless_output = True
        self.load_sec = time.perf_counter() - started

    def teardown(self) -> None:
        self.runtime = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    # ------------------------------------------------------------- inference
    def request_identity(self, source_video: Path, prompt: str) -> dict[str, Any]:
        if not prompt.strip():
            raise ValueError('Empty edit prompt')
        if not source_video.is_file():
            raise ValueError(f'Missing source video: {source_video}')
        return {**self.config, 'prompt': prompt, 'source_sha256': sha256(source_video)}

    def _generate(self, frames, fps: float, prompt: str):
        import torch
        from xvideo.serving.joyomni_streaming import StreamingSettings
        settings = StreamingSettings(
            height=self.height, width=self.width, num_inference_steps=self.num_inference_steps,
            seed=self.seed, max_temporal_ids=self.max_temporal_ids,
            freeze_kv_on_static=False, static_diff_thresh=0.5, profile_timings=False,
            output_codec='mjpeg')
        session = self.runtime.create_v2v_session(prompt, settings=settings)
        results = []
        try:
            for index, frame in enumerate(frames):
                results += session.push_frame(
                    frame, frame_meta={'seq': index + 1, 't_capture_ms': index * 1000.0 / fps})
                # File input waits for capacity instead of dropping frames.
                deadline = time.monotonic() + self.chunk_timeout
                while session.inflight_chunks() >= self.max_inflight_chunks:
                    if time.monotonic() > deadline:
                        raise TimeoutError('JoyAI chunk did not finish in time')
                    result = session.wait_async_result(timeout=0.05)
                    if result is not None:
                        results.append(result)
            session.flush_pending()
            deadline = time.monotonic() + self.chunk_timeout
            while len(results) < session.chunk_idx:
                if time.monotonic() > deadline:
                    raise TimeoutError(f'Only {len(results)}/{session.chunk_idx} chunks returned')
                result = session.wait_async_result(timeout=0.5)
                if result is not None:
                    results.append(result)
        finally:
            session.close(timeout=60)
        results.sort(key=lambda r: r.profile.get('chunk_idx', 0))
        out = []
        for result in results:
            chunk = list(result.jpegs)
            if result.valid_count is not None:
                chunk = chunk[:result.valid_count]
            out.extend(chunk)
        for frame in out:
            if not hasattr(frame, 'shape'):
                raise RuntimeError('Expected lossless uint8 frames from the runtime')
        torch.cuda.synchronize()
        return out

    def edit_video(self, source_video: Path, prompt: str, output_path: Path,
                   *, edit_info: dict[str, Any]) -> BaselineResult:
        identity = self.request_identity(source_video, prompt)
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        record_path = output_path.with_suffix('.task.json')
        with exclusive_lock(output_path.with_suffix('.lock')):
            state = json.loads(record_path.read_text()) if record_path.exists() else {}
            if state and state.get('request_fingerprint') != fingerprint:
                raise RuntimeError(f'Prompt/source/config changed for {output_path}; use a new predictions root')
            if output_path.exists():
                if state.get('status') != 'completed':
                    raise RuntimeError(f'Output exists without a completed matching record: {output_path}')
                if sha256(output_path) != state['output_sha256']:
                    raise RuntimeError(f'Prediction checksum mismatch: {output_path}')
                return BaselineResult(output_path, 0, {**self.config, 'reused_existing': True,
                                                       'media': state['output_media']})
            if self.runtime is None:
                raise RuntimeError('Call setup() before edit_video()')
            import torch
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            frames, fps = read_frames(source_video)
            edited = self._generate(frames, fps, prompt)
            if len(edited) != len(frames):
                raise RuntimeError(f'Frame count changed: {len(frames)} in, {len(edited)} out')
            infer_sec = time.perf_counter() - started
            output_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = output_path.with_name(output_path.stem + '.part.mp4')
            try:
                write_h264(edited, fps, tmp, self.crf)
                media = probe_video(tmp)
                tmp.replace(output_path)
            finally:
                tmp.unlink(missing_ok=True)
            elapsed = time.perf_counter() - started
            gpu = {'peak_allocated_gib': round(torch.cuda.max_memory_allocated() / 2**30, 2),
                   'peak_reserved_gib': round(torch.cuda.max_memory_reserved() / 2**30, 2),
                   'device_name': torch.cuda.get_device_name(0)}
            state = {'schema_version': 1, 'global_id': edit_info.get('global_id'), 'request': identity,
                     'request_fingerprint': fingerprint, 'source_video': str(source_video.resolve()),
                     'status': 'completed', 'input_frames': len(frames), 'input_fps': fps,
                     'output_sha256': sha256(output_path), 'output_media': media,
                     'inference_sec': round(infer_sec, 3), 'elapsed_sec': round(elapsed, 3),
                     'gpu_memory': gpu, 'host': os.uname().nodename,
                     'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
                     'completed_at': time.time()}
            atomic_json(record_path, state)
        return BaselineResult(output_path, elapsed, {**self.config, 'reused_existing': False,
                                                     'media': media, 'inference_sec': round(infer_sec, 3),
                                                     'gpu_memory': gpu})
