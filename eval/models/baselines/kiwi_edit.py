"""Kiwi-Edit (showlab, arXiv 2603.02175) local GPU baseline.

Wraps the official diffusers checkpoint `linyq/kiwi-edit-5b-instruct-only-diffusers`
(Wan2.2-TI2V-5B DiT + Qwen2.5-VL-3B MLLM encoder, custom remote-code pipeline).
Inference follows the official `diffusers_demo.py`:

* frames are decoded with torchvision `read_video`; sources above 1280x720
  pixels are shrunk to fit and floored to multiples of 16 (PhyCoVE is exactly
  1280x720, so nothing is resized here);
* `pipe(prompt, source_video=frames, height, width, num_frames, 50 steps,
  guidance_scale=5.0, seed=0, tiled=True)`. The released pipeline has no CFG
  branch, so guidance_scale has no effect; it is kept only for parity.

VAE decoding runs spatially tiled: the diffusers port drops tiling and then
needs a single 24 GiB conv3d at 1280x736x81, which does not fit on a 48 GB RTX
4090 (see install_tiled_vae). The default preset `fast` encodes untiled (as the
diffusers port does) and decodes in 4 tiles of 30x44 latents (stride 16x36);
`diffsynth` uses the native DiffSynth pipeline's 30x52 / 15x26 tiles for both
directions (9 tiles, ~60 s slower per case, used for outputs before 2026-11-12).

Two further differences from the demo, both needed by the PhyCoVE harness
("frame i of a prediction is frame i of the source"):

* the result is written at the source clip's own frame rate (24 fps), not at
  the demo's hard-coded 15 fps, so playback time matches the source;
* the pipeline rounds 720 up to 736 rows (multiple of 32) and stretches the
  source to it; the output is resized back to the source size.

`num_frames` defaults to 81, the length the model was trained on (the first
81 of 96 source frames, 3.375 s). `num_frames=97` covers the whole 4 s clip by
repeating the last source frame once and dropping that frame from the output.

A sidecar `<case>.task.json` records the request fingerprint and output hash,
so an interrupted run resumes and a finished case is only reused when prompt,
source and configuration all match.
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

from .base import BaselineModel, BaselineResult

# MODEL_ROOT: folder of the model deployments.
DEFAULT_MODEL_PATH = str(Path(os.environ.get('MODEL_ROOT', 'models')) / 'Kiwi-Edit' / 'checkpoints'
                         / 'kiwi-edit-5b-instruct-only-diffusers')
MAX_PIXELS_DEFAULT = 720 * 1280


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
        'fps_fraction': stream['avg_frame_rate'],
        'duration_sec': float(data['format']['duration']),
        'frames': int(stream['nb_read_frames']) if str(stream.get('nb_read_frames', '')).isdigit() else None,
    }
    if min(result['width'], result['height'], result['fps'], result['duration_sec']) <= 0:
        raise ValueError(f'Invalid video: {path}')
    return result


def _blend_mask(shape_hw, is_bound, border, torch):
    """DiffSynth WanVideoVAE.build_mask: linear ramps on interior tile edges."""
    def ramp(length, left_bound, right_bound, width):
        x = torch.ones((length,))
        if width > 0 and not left_bound:
            x[:width] = (torch.arange(width) + 1) / width
        if width > 0 and not right_bound:
            x[-width:] = torch.flip((torch.arange(width) + 1) / width, dims=(0,))
        return x
    h = ramp(shape_hw[0], is_bound[0], is_bound[1], border[0])[:, None].expand(*shape_hw)
    w = ramp(shape_hw[1], is_bound[2], is_bound[3], border[1])[None, :].expand(*shape_hw)
    return torch.minimum(h, w)[None, None, None]


def install_tiled_vae(vae, encode_tiles=((30, 52), (15, 26)), decode_tiles=((30, 52), (15, 26))):
    """Spatially tiled VAE encode/decode, as in Kiwi-Edit's native DiffSynth pipeline.

    The diffusers port (`pipeline_kiwi_edit.py`) accepts `tiled/tile_size/tile_stride`
    but never forwards them, so it decodes 81 frames of 1280x736 in one piece; that
    single conv3d asks for 24 GiB and does not fit on a 48 GB card next to the
    20 GB of weights. This reproduces DiffSynth's `WanVideoVAE.tiled_encode/decode`
    (same linear blending) around the wrapper's own untiled `encode/decode`.
    `encode_tiles` / `decode_tiles` are ((tile_h, tile_w), (stride_h, stride_w)) in
    latent units, or None to leave that direction untiled (the diffusers default).
    """
    import torch
    from types import SimpleNamespace
    f = vae.upsampling_factor
    untiled_encode, untiled_decode = vae.encode, vae.decode

    def tasks(H, W, size, stride):
        out = []
        for h in range(0, H, stride[0]):
            if h - stride[0] >= 0 and h - stride[0] + size[0] >= H:
                continue
            for w in range(0, W, stride[1]):
                if w - stride[1] >= 0 and w - stride[1] + size[1] >= W:
                    continue
                out.append((h, h + size[0], w, w + size[1]))
        return out

    def run(x, size, stride, scale_up, call):
        H, W = x.shape[-2:]
        values = weight = None
        for h, h_, w, w_ in tasks(H, W, size, stride):
            # Blend in float32 on the GPU (DiffSynth blends on CPU; same math, ~1 GB extra VRAM).
            y = call(x[:, :, :, h:h_, w:w_]).float()
            if values is None:
                oh, ow = (H * f, W * f) if scale_up else (H // f, W // f)
                values = torch.zeros((1, y.shape[1], y.shape[2], oh, ow), device=y.device)
                weight = torch.zeros((1, 1, y.shape[2], oh, ow), device=y.device)
            border = ((size[0] - stride[0]) * f, (size[1] - stride[1]) * f) if scale_up else \
                     ((size[0] - stride[0]) // f, (size[1] - stride[1]) // f)
            mask = _blend_mask(y.shape[-2:], (h == 0, h_ >= H, w == 0, w_ >= W), border, torch).to(y.device)
            th, tw = (h * f, w * f) if scale_up else (h // f, w // f)
            values[..., th:th + y.shape[3], tw:tw + y.shape[4]] += y * mask
            weight[..., th:th + y.shape[3], tw:tw + y.shape[4]] += mask
            del y
        return values.div_(weight)

    def encode(x):
        (th, tw), (sh, sw) = encode_tiles
        mu = run(x, (th * f, tw * f), (sh * f, sw * f), False,
                 lambda t: untiled_encode(t).latent_dist.sample())
        return SimpleNamespace(latent_dist=SimpleNamespace(sample=lambda: mu))

    def decode(z):
        out = run(z, *decode_tiles, True, lambda t: untiled_decode(t).sample)
        return SimpleNamespace(sample=out.clamp_(-1, 1))

    if encode_tiles is not None:
        vae.encode = encode
    if decode_tiles is not None:
        vae.decode = decode


# name -> (encode_tiles, decode_tiles, fingerprint label); see install_tiled_vae.
VAE_TILING_PRESETS = {
    # Native DiffSynth defaults; outputs made before 2026-11-12 used this.
    'diffsynth': (((30, 52), (15, 26)), ((30, 52), (15, 26)), 'diffsynth_30x52_stride15x26'),
    # Faster: untiled encode (as the diffusers port does) + fewer, larger decode tiles.
    'fast': (None, ((30, 44), (16, 36)), 'encode_untiled+decode_30x44_stride16x36'),
}


class KiwiEditBaseline(BaselineModel):
    name = 'kiwi_edit'

    def __init__(self, model_path: str | None = None, num_frames: int = 81,
                 num_inference_steps: int = 50, seed: int = 0,
                 max_pixels: int = MAX_PIXELS_DEFAULT, guidance_scale: float = 5.0,
                 device: str = 'cuda', crf: int = 17, vae_tiling: str = 'fast',
                 **kwargs: Any) -> None:
        self.model_path = str(model_path or os.getenv('KIWI_EDIT_MODEL_PATH', DEFAULT_MODEL_PATH))
        if num_frames < 5 or num_frames % 4 != 1:
            raise ValueError('Kiwi-Edit needs num_frames = 4n+1 (81 = trained length, 97 = full 96-frame clip)')
        if num_inference_steps < 1 or max_pixels < 256 * 256 or not 0 <= crf <= 51:
            raise ValueError('Invalid steps / max_pixels / crf')
        self.num_frames, self.num_inference_steps = num_frames, num_inference_steps
        self.seed, self.max_pixels, self.guidance_scale = seed, max_pixels, guidance_scale
        if vae_tiling not in VAE_TILING_PRESETS:
            raise ValueError(f'vae_tiling must be one of {sorted(VAE_TILING_PRESETS)}')
        self.device, self.crf, self.vae_tiling = device, crf, vae_tiling
        self.pipe = None
        # `device` is a placement detail, not part of the result identity.
        super().__init__(model=Path(self.model_path).name, num_frames=num_frames,
                         num_inference_steps=num_inference_steps, seed=seed,
                         max_pixels=max_pixels, guidance_scale=guidance_scale,
                         output_fps='source', crf=crf,
                         vae_tiling=VAE_TILING_PRESETS[vae_tiling][2])

    # ------------------------------------------------------------------ #
    def setup(self) -> None:
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
        os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
        # Keep diffusers' copy of the remote pipeline code beside the model, not in ~/.cache.
        os.environ.setdefault('HF_MODULES_CACHE', str(Path(self.model_path).parent.parent / 'cache' / 'hf_modules'))
        import torch
        from diffusers import DiffusionPipeline
        if not (Path(self.model_path) / 'model_index.json').is_file():
            raise RuntimeError(f'Kiwi-Edit checkpoint not found: {self.model_path}')
        if self.device.startswith('cuda') and not torch.cuda.is_available():
            raise RuntimeError('CUDA is not available; set CUDA_VISIBLE_DEVICES to a free GPU')
        started = time.perf_counter()
        pipe = DiffusionPipeline.from_pretrained(self.model_path, trust_remote_code=True)
        pipe.to(self.device, dtype=torch.bfloat16)
        encode_tiles, decode_tiles, _ = VAE_TILING_PRESETS[self.vae_tiling]
        install_tiled_vae(pipe.vae, encode_tiles, decode_tiles)
        self.pipe = pipe
        self.load_sec = time.perf_counter() - started

    def teardown(self) -> None:
        self.pipe = None
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    def load_frames(self, source_video: Path):
        """Official demo loader, with last-frame padding when num_frames > clip length."""
        from PIL import Image
        from torchvision.io import read_video
        vframes, _, _ = read_video(str(source_video), pts_unit='sec')
        if len(vframes) == 0:
            raise ValueError(f'No frames decoded: {source_video}')
        source_len = len(vframes)
        frames = []
        for i in range(min(source_len, self.num_frames)):
            img = Image.fromarray(vframes[i].numpy())
            w, h = img.size
            scale = min(1.0, (self.max_pixels / (w * h)) ** 0.5)
            if scale < 1.0:
                img = img.resize((int(w * scale) // 16 * 16, int(h * scale) // 16 * 16), Image.LANCZOS)
            frames.append(img)
        padded = 0
        # The pipeline needs 4n+1 frames; repeat the last frame rather than letting
        # the VAE source latent and the noise latent disagree in length.
        while len(frames) < self.num_frames and len(frames) % 4 != 1:
            frames.append(frames[-1].copy())
            padded += 1
        return frames, source_len, padded

    def write_video(self, frames, output_path: Path, size: tuple[int, int], fps_fraction: str) -> None:
        from PIL import Image
        width, height = size
        tmp = output_path.with_name(output_path.stem + '.part.mp4')
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', fps_fraction,
               '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', str(self.crf),
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(tmp)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for frame in frames:
                if frame.size != (width, height):
                    frame = frame.resize((width, height), Image.LANCZOS)
                proc.stdin.write(frame.convert('RGB').tobytes())
            proc.stdin.close()
            err = proc.stderr.read().decode(errors='replace')
            if proc.wait(timeout=600) != 0:
                raise RuntimeError(f'ffmpeg failed: {err[-800:]}')
            tmp.replace(output_path)
        finally:
            if proc.poll() is None:
                proc.kill()
            tmp.unlink(missing_ok=True)

    def request_identity(self, source_video: Path, prompt: str) -> dict[str, Any]:
        if not prompt.strip():
            raise ValueError('Empty prompt')
        return {**self.config, 'prompt': prompt, 'source_sha256': sha256(source_video)}

    # ------------------------------------------------------------------ #
    def edit_video(self, source_video: Path, prompt: str, output_path: Path,
                   *, edit_info: dict[str, Any], overwrite: bool = False) -> BaselineResult:
        started = time.perf_counter()
        identity = self.request_identity(source_video, prompt)
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        checkpoint = output_path.with_suffix('.task.json')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with exclusive_lock(output_path.with_suffix('.lock')):
            state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
            if state and state.get('request_fingerprint') != fingerprint and not overwrite:
                raise RuntimeError(f'Prompt/source/config changed for {output_path}; '
                                   'use another predictions root or --overwrite')
            if output_path.exists() and not overwrite:
                if state.get('status') == 'completed' and state.get('request_fingerprint') == fingerprint \
                        and sha256(output_path) == state.get('output_sha256'):
                    return BaselineResult(output_path, 0, {**self.config, 'reused_existing': True,
                                                           'media': state.get('output_media'),
                                                           'inference_sec': state.get('inference_sec')})
                raise RuntimeError(f'Output exists without a matching completed checkpoint: {output_path}')
            if self.pipe is None:
                raise RuntimeError('Call setup() before edit_video()')
            import torch
            source_media = probe_video(source_video)
            frames, source_len, padded = self.load_frames(source_video)
            w, h = frames[0].size
            state = {'schema_version': 1, 'global_id': edit_info.get('global_id'),
                     'request': identity, 'request_fingerprint': fingerprint,
                     'source_video': str(source_video.resolve()), 'status': 'running',
                     'started_at': time.time(), 'host': os.uname().nodename,
                     'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES')}
            atomic_json(checkpoint, state)
            if self.device.startswith('cuda'):
                torch.cuda.reset_peak_memory_stats()
            t0 = time.perf_counter()
            try:
                video = self.pipe(prompt=prompt, source_video=frames, ref_image=None,
                                  height=h, width=w, num_frames=len(frames),
                                  num_inference_steps=self.num_inference_steps,
                                  guidance_scale=self.guidance_scale, seed=self.seed, tiled=True,
                                  progress_bar=lambda x: x)
            except BaseException as exc:
                state.update(status='failed', error=f'{type(exc).__name__}: {str(exc)[:600]}')
                atomic_json(checkpoint, state)
                raise
            inference_sec = time.perf_counter() - t0
            peak = {}
            if self.device.startswith('cuda'):
                peak = {'peak_allocated_gib': round(torch.cuda.max_memory_allocated() / 2**30, 2),
                        'peak_reserved_gib': round(torch.cuda.max_memory_reserved() / 2**30, 2)}
            keep = min(len(video), source_len, self.num_frames)
            generated = (video[0].size[0], video[0].size[1], len(video))
            self.write_video(video[:keep], output_path,
                             (source_media['width'], source_media['height']), source_media['fps_fraction'])
            media = probe_video(output_path)
            state.update(status='completed', output_sha256=sha256(output_path), output_media=media,
                         inference_sec=round(inference_sec, 2), completed_at=time.time(),
                         generated_wh_frames=generated, frames_written=keep,
                         source_frames=source_len, padded_input_frames=padded, **peak)
            atomic_json(checkpoint, state)
        return BaselineResult(output_path, time.perf_counter() - started,
                              {**self.config, 'reused_existing': False, 'media': media,
                               'inference_sec': round(inference_sec, 2), **peak})
