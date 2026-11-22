"""OmniWeaving (Tencent Hunyuan, arXiv 2603.24458) as a local PhyCoVE baseline.

OmniWeaving is built on HunyuanVideo-1.5 (8.3B MMDiT) with a fine-tuned
Qwen2.5-VL-7B MLLM. Its `editing` task takes a source video plus a text
instruction. This wrapper loads the official pipeline once and runs, per case,
the same calls as the official `generate.py --task editing`:

    latents = generate.encode_video_to_latents(pipe, video, max_frames=video_length)
    pipe(prompt, aspect_ratio='16:9', num_inference_steps, video_length,
         negative_prompt='', seed, think=False, output_type='pt',
         only_give_text=False, deepstack=[8, 16, 24], setclip=True,
         task_type='editing', condition_video_latents=latents,
         condition_videos=[video])

Official defaults kept: pipeline_config `omniweaving` (guidance 6.0, flow
shift 7.0), 50 steps, bf16 transformer, empty negative prompt, no prompt
rewriting. Seed 0 follows the README example (the CLI default is 123).

Differences, all needed by the PhyCoVE harness ("frame i of a prediction is
frame i of the source"):

* Length. The official code keeps (n-1)//8*8+1 source frames, so the
  96-frame clips would lose their last 7 frames. The source is padded to
  `num_frames` (default 97) by repeating its last frame, and the output is cut
  back to the source length. Output frame i is aligned with source frame i
  because the source latents are concatenated channel-wise with the noise.
* Size. OmniWeaving only supports 480p: the official code resizes to the
  closest aspect bucket of generate_crop_size_list(base_size=640) and centre
  crops (1280x720 -> 853x480 -> 848x480). Here the full frame is resized
  directly to that bucket (848x480), so no border is cropped and the output maps
  back onto the whole source frame. The output is written at 848x480.
* Frame rate. The output keeps the source frame rate (24 fps), as the official
  code does for editing.
* Attention. transformer/config.json asks for FlashAttention-3 (Hopper only).
  On other GPUs the official fallback is the torch/flex path; this wrapper
  selects FlashAttention-2 instead, the same exact attention ('torch' remains
  available through attn_mode for checks).

The padded, resized clip the model sees is written as a lossless RGB H.264
file (libx264rgb, qp 0) and decoded back before use; the run stops if the
decoded frames differ from the intended ones by even one value.

A sidecar `<case>.task.json` records the request fingerprint and output hash,
so an interrupted run resumes and a finished case is reused only when prompt,
source and configuration all match.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from .base import BaselineModel, BaselineResult

MODEL_ROOT = Path(os.environ.get('MODEL_ROOT', 'models')) / 'OmniWeaving'  # MODEL_ROOT: folder of the model deployments
DEFAULT_SRC = MODEL_ROOT / 'src' / 'OmniWeaving'
DEFAULT_MODEL_PATH = MODEL_ROOT / 'checkpoints' / 'HY-OmniWeaving'
UPSTREAM_COMMIT = '70012d0a8ba4e6aabc3f5a694872e852afd42cfd'
# (enable_offloading, enable_group_offloading, overlap_group_offloading); placement only,
# results are unchanged. On a < 60 GB card generate.py turns group offloading on by
# itself, but that calls ModelMixin.enable_group_offload, which first appeared in
# diffusers 0.33.0, while requirements.txt pins 0.32.2. So the default here is
# 'model' (= generate.py --group_offloading false): each model is moved to the GPU
# for its own stage. 'group' needs diffusers >= 0.33.
OFFLOAD_PRESETS = {
    'model': (True, False, False),
    'group': (True, True, False),
    'none': (False, False, False),
}


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


def crop_size_list(base_size: int = 640, patch_size: int = 16, max_ratio: float = 4.0):
    """Copy of hyvideo.utils.data_utils.generate_crop_size_list (checked equal in the tests)."""
    num_patches = round((base_size / patch_size) ** 2)
    out, wp, hp = [], num_patches, 1
    while wp > 0:
        if max(wp, hp) / min(wp, hp) <= max_ratio:
            out.append((wp * patch_size, hp * patch_size))
        if (hp + 1) * wp <= num_patches:
            hp += 1
        else:
            wp -= 1
    return out


def bucket_hw(height: int, width: int) -> tuple[int, int]:
    """(h, w) bucket that generate.encode_video_to_latents picks for a height x width clip."""
    sizes = crop_size_list(640)
    ratios = [round(float(h) / float(w), 5) for h, w in sizes]
    aspect = float(height) / float(width)
    best = min(range(len(sizes)), key=lambda i: (abs(ratios[i] - aspect), i))
    return sizes[best]


def official_kept_frames(n: int) -> int:
    """Number of frames generate.encode_video_to_latents keeps from an n-frame clip."""
    if n < 33:
        raise ValueError(f'OmniWeaving needs at least 33 frames, got {n}')
    return 161 if n > 161 else (n - 1) // 8 * 8 + 1


class OmniWeavingBaseline(BaselineModel):
    name = 'omniweaving'

    def __init__(self, model_path: str | None = None, src_path: str | None = None,
                 num_frames: int = 97, num_inference_steps: int = 50, seed: int = 0,
                 pipeline_config: str = 'omniweaving', attn_mode: str = 'flash2',
                 offload: str = 'model', device: str = 'cuda', crf: int = 10,
                 tmp_root: str | None = None, **kwargs: Any) -> None:
        self.model_path = str(model_path or os.getenv('OMNIWEAVING_MODEL_PATH', DEFAULT_MODEL_PATH))
        self.src_path = str(src_path or os.getenv('OMNIWEAVING_SRC', DEFAULT_SRC))
        if official_kept_frames(num_frames) != num_frames:
            raise ValueError('num_frames must be 8n+1 in [33, 161] (97 covers the whole 96-frame clip)')
        if num_inference_steps < 1 or not 0 <= crf <= 51:
            raise ValueError('Invalid steps / crf')
        if pipeline_config not in ('omniweaving', 'omniweaving2'):
            raise ValueError('pipeline_config must be omniweaving or omniweaving2')
        if attn_mode not in ('flash2', 'torch'):
            raise ValueError('attn_mode must be flash2 or torch')
        if offload not in OFFLOAD_PRESETS:
            raise ValueError(f'offload must be one of {sorted(OFFLOAD_PRESETS)}')
        self.num_frames, self.num_inference_steps, self.seed = num_frames, num_inference_steps, seed
        self.pipeline_config, self.attn_mode, self.offload = pipeline_config, attn_mode, offload
        self.device, self.crf = device, crf
        self.tmp_root = Path(tmp_root or os.getenv('OMNIWEAVING_TMP', MODEL_ROOT / 'tmp'))
        self.pipe = self.ow = None
        self._dist_file = None
        # Placement (device, offload) is not part of the result identity.
        super().__init__(model=Path(self.model_path).name, upstream_commit=UPSTREAM_COMMIT,
                         task='editing', num_frames=num_frames, pad='repeat_last_frame',
                         source_resize='full_frame_to_480p_bucket', dtype='bf16',
                         num_inference_steps=num_inference_steps, seed=seed,
                         pipeline_config=pipeline_config, negative_prompt='', think=False,
                         only_give_text=False, deepstack=[8, 16, 24], setclip=True,
                         attn_mode=attn_mode, output_fps='source', output_size='model', crf=crf)

    # ------------------------------------------------------------------ #
    def check_files(self) -> None:
        root = Path(self.model_path)
        need = ['config.json', 'transformer/diffusion_pytorch_model.safetensors',
                'vae/diffusion_pytorch_model.safetensors', 'scheduler/scheduler_config.json',
                'text_encoder/ckpt/text_encoder_model.safetensors', 'text_encoder/llm/config.json',
                'text_encoder/byt5-small/config.json', 'text_encoder/Glyph-SDXL-v2/checkpoints/byt5_model.pt',
                'vision_encoder/siglip/image_encoder/model.safetensors',
                'vision_encoder/siglip/feature_extractor/preprocessor_config.json']
        missing = [p for p in need if not (root / p).is_file()]
        if missing:
            raise RuntimeError(f'OmniWeaving checkpoint incomplete under {root}: {missing}')
        if not (Path(self.src_path) / 'generate.py').is_file():
            raise RuntimeError(f'OmniWeaving source not found: {self.src_path}')

    def setup(self) -> None:
        self.check_files()
        os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')
        os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
        if os.environ.get('WORLD_SIZE', '1') != '1':
            raise RuntimeError('Run one process per GPU (no torchrun / sequence parallel)')
        import torch
        import torch.distributed as dist
        if self.device != 'cuda' or not torch.cuda.is_available():
            raise RuntimeError('OmniWeaving needs a CUDA GPU; set CUDA_VISIBLE_DEVICES to a free card')
        started = time.perf_counter()
        # generate.py builds a CUDA device mesh at import time; give it a private
        # one-process group (file rendezvous, so parallel shards need no ports).
        if not dist.is_initialized():
            self.tmp_root.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='dist_', dir=self.tmp_root)
            os.close(fd)
            os.unlink(name)
            self._dist_file = name
            dist.init_process_group('nccl', init_method=f'file://{name}', rank=0, world_size=1)
        if self.src_path not in sys.path:
            sys.path.insert(0, self.src_path)
        spec = importlib.util.spec_from_file_location('omniweaving_generate', Path(self.src_path) / 'generate.py')
        ow = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ow)  # initialize_parallel_state(sp=1) + cuda.set_device(0), as upstream
        from types import SimpleNamespace
        from hyvideo.commons.infer_state import initialize_infer_state
        from hyvideo.pipelines.hunyuan_video_pipeline import HunyuanVideo_1_5_Pipeline
        # generate.py's argparse defaults for the inference-state fields.
        infer_args = SimpleNamespace(use_sageattn=False, sage_blocks_range='0-53', enable_torch_compile=False,
                                     enable_cache=False, cache_type='deepcache', no_cache_block_id='53',
                                     cache_start_step=11, cache_end_step=45, total_steps=50,
                                     cache_step_interval=4, use_fp8_gemm=False,
                                     quant_type='fp8-per-token-sgl', include_patterns='double_blocks')
        infer_state = initialize_infer_state(infer_args)
        enable_offloading, enable_group_offloading, overlap = OFFLOAD_PRESETS[self.offload]
        from diffusers import ModelMixin
        if enable_group_offloading and not hasattr(ModelMixin, 'enable_group_offload'):
            raise RuntimeError("offload='group' needs diffusers >= 0.33 (enable_group_offload); "
                               "the official pin is 0.32.2, use offload='model'")
        device = torch.device('cpu') if enable_offloading else torch.device('cuda')
        transformer_init_device = torch.device('cpu') if enable_group_offloading else device
        pipe = HunyuanVideo_1_5_Pipeline.create_pipeline(
            pretrained_model_name_or_path=self.model_path, transformer_dtype=torch.bfloat16,
            device=device, transformer_init_device=transformer_init_device,
            pipeline_config=self.pipeline_config)
        pipe.apply_infer_optimization(infer_state=infer_state, enable_offloading=enable_offloading,
                                      enable_group_offloading=enable_group_offloading,
                                      overlap_group_offloading=overlap)
        pipe.transformer.set_attn_mode(self.attn_mode)
        modes = {pipe.transformer.attn_mode} | {b.attn_mode for b in pipe.transformer.double_blocks} \
            | {b.attn_mode for b in pipe.transformer.single_blocks}
        if modes != {self.attn_mode}:
            raise RuntimeError(f'Attention fell back to {modes} (wanted {self.attn_mode}); is flash-attn installed?')
        self.placement = {'offload': self.offload, 'enable_offloading': enable_offloading,
                          'enable_group_offloading': enable_group_offloading,
                          'overlap_group_offloading': overlap}
        self.pipe, self.ow = pipe, ow
        self.load_sec = time.perf_counter() - started

    def teardown(self) -> None:
        self.pipe = self.ow = None
        try:
            import torch
            import torch.distributed as dist
            torch.cuda.empty_cache()
            if self._dist_file and dist.is_initialized():
                dist.destroy_process_group()
        except Exception:  # noqa: BLE001
            pass
        if self._dist_file:
            Path(self._dist_file).unlink(missing_ok=True)
            self._dist_file = None

    # ------------------------------------------------------------------ #
    def model_input_frames(self, source_video: Path):
        """Frames the model sees: padded/cut to num_frames, full frame resized to the 480p bucket.

        Returns (uint8 array F x h x w x 3, source_len, padded, (h, w)).
        """
        import numpy as np
        import torch
        from decord import VideoReader
        from torchvision import transforms
        vr = VideoReader(str(source_video))
        source_len = len(vr)
        take = min(source_len, self.num_frames)
        frames = vr.get_batch(list(range(take))).asnumpy()
        del vr
        height, width = frames.shape[1:3]
        h, w = bucket_hw(height, width)
        x = torch.from_numpy(frames).permute(0, 3, 1, 2).float() / 255.0
        # Same filter as generate.encode_video_to_latents, without its centre crop.
        x = transforms.Resize((h, w), antialias=True)(x)
        out = (x * 255.0).round().clamp(0, 255).to(torch.uint8).permute(0, 2, 3, 1).numpy()
        padded = self.num_frames - take
        if padded:
            out = np.concatenate([out, np.repeat(out[-1:], padded, axis=0)], axis=0)
        return np.ascontiguousarray(out), source_len, padded, (h, w)

    @staticmethod
    def write_lossless(frames, path: Path, fps_fraction: str) -> None:
        """RGB-lossless H.264 (libx264rgb, qp 0), then verify by decoding with decord."""
        import numpy as np
        from decord import VideoReader
        n, h, w, _ = frames.shape
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}', '-r', fps_fraction, '-i', '-',
               '-an', '-c:v', 'libx264rgb', '-qp', '0', '-preset', 'veryfast', '-pix_fmt', 'rgb24', str(path)]
        proc = subprocess.run(cmd, input=frames.tobytes(), capture_output=True, timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f'ffmpeg failed: {proc.stderr.decode(errors="replace")[-800:]}')
        vr = VideoReader(str(path))
        back = vr.get_batch(list(range(len(vr)))).asnumpy()
        del vr
        if back.shape != frames.shape or not np.array_equal(back, frames):
            raise RuntimeError(f'Lossless round trip failed for {path}: {back.shape} vs {frames.shape}')

    @staticmethod
    def write_h264(frames, path: Path, fps_fraction: str, crf: int) -> None:
        n, h, w, _ = frames.shape
        tmp = path.with_name(path.stem + '.part.mp4')
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}', '-r', fps_fraction, '-i', '-',
               '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', str(crf),
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(tmp)]
        try:
            proc = subprocess.run(cmd, input=frames.tobytes(), capture_output=True, timeout=600)
            if proc.returncode != 0:
                raise RuntimeError(f'ffmpeg failed: {proc.stderr.decode(errors="replace")[-800:]}')
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)

    def request_identity(self, source_video: Path, prompt: str) -> dict[str, Any]:
        if not prompt.strip():
            raise ValueError('Empty prompt')
        return {**self.config, 'prompt': prompt, 'source_sha256': sha256(source_video)}

    def generate(self, model_video: Path, prompt: str, hw: tuple[int, int]):
        """The official generate_video() editing calls; returns uint8 frames F x H x W x 3 and latent shape."""
        import torch
        latents = self.ow.encode_video_to_latents(self.pipe, str(model_video), max_frames=self.num_frames)
        # 4x temporal / 16x spatial VAE: the whole padded clip must be encoded, uncropped.
        want = ((self.num_frames - 1) // 4 + 1, hw[0] // 16, hw[1] // 16)
        if latents.ndim != 5 or tuple(latents.shape[2:]) != want:
            raise RuntimeError(f'Condition latents {tuple(latents.shape)} do not cover {want} (T, H, W)')
        out = self.pipe(prompt=prompt, aspect_ratio='16:9', num_inference_steps=self.num_inference_steps,
                        video_length=self.num_frames, negative_prompt='', seed=self.seed, think=False,
                        output_type='pt', only_give_text=False, deepstack=[8, 16, 24], setclip=True,
                        task_type='editing', condition_video_latents=latents,
                        condition_videos=[str(model_video)])
        video = out.videos
        if video.ndim == 5:
            assert video.shape[0] == 1
            video = video[0]
        # generate.save_video's conversion.
        vid = (video * 255).clamp(0, 255).to(torch.uint8).permute(1, 2, 3, 0).contiguous().numpy()
        return vid, tuple(latents.shape)

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
            frames_in, source_len, padded, (h, w) = self.model_input_frames(source_video)
            keep = min(source_len, self.num_frames)
            state = {'schema_version': 1, 'global_id': edit_info.get('global_id'),
                     'request': identity, 'request_fingerprint': fingerprint,
                     'source_video': str(source_video.resolve()), 'status': 'running',
                     'started_at': time.time(), 'host': os.uname().nodename,
                     'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
                     'placement': getattr(self, 'placement', None)}
            atomic_json(checkpoint, state)
            self.tmp_root.mkdir(parents=True, exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix='case_', dir=self.tmp_root))
            torch.cuda.reset_peak_memory_stats()
            try:
                model_video = work / 'model_input.mkv'
                self.write_lossless(frames_in, model_video, source_media['fps_fraction'])
                t0 = time.perf_counter()
                video, latent_shape = self.generate(model_video, prompt, (h, w))
                inference_sec = time.perf_counter() - t0
                expected = (self.num_frames, h, w, 3)
                if video.shape != expected:
                    raise RuntimeError(f'Unexpected output shape {video.shape}, wanted {expected}')
                peak = {'peak_allocated_gib': round(torch.cuda.max_memory_allocated() / 2**30, 2),
                        'peak_reserved_gib': round(torch.cuda.max_memory_reserved() / 2**30, 2)}
                self.write_h264(video[:keep], output_path, source_media['fps_fraction'], self.crf)
            except BaseException as exc:
                state.update(status='failed', error=f'{type(exc).__name__}: {str(exc)[:600]}')
                atomic_json(checkpoint, state)
                raise
            finally:
                shutil.rmtree(work, ignore_errors=True)
            media = probe_video(output_path)
            if media['frames'] != keep or (media['width'], media['height']) != (w, h):
                raise RuntimeError(f'Written video has {media}, wanted {keep} frames at {w}x{h}')
            state.update(status='completed', output_sha256=sha256(output_path), output_media=media,
                         inference_sec=round(inference_sec, 2), completed_at=time.time(),
                         model_input_wh_frames=[w, h, self.num_frames], latent_shape=list(latent_shape),
                         generated_wh_frames=[w, h, int(video.shape[0])], frames_written=keep,
                         source_frames=source_len, padded_input_frames=padded, **peak)
            atomic_json(checkpoint, state)
        return BaselineResult(output_path, time.perf_counter() - started,
                              {**self.config, 'reused_existing': False, 'media': media,
                               'inference_sec': round(inference_sec, 2), **peak})
