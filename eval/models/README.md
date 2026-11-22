# PhyCoVE model runners

This folder holds the code that produced the edited videos of the models in the
paper.

| Path | Content |
| --- | --- |
| `run_phycove_<model>.py` | Runner for one model (one process, one GPU or one API client). |
| `run_phycove_<model>_parallel.py` | Resumable queue around it: one shard per GPU for local models, bounded concurrent requests for API models. |
| `run_baseline.py` | Generic runner over the `BASELINES` registry, used for VOID and the `no_edit` control. |
| `baselines/` | One adapter per model behind the `BaselineModel` interface of `base.py`. VOID additionally takes per-case click points (from Gemini 3.1 Flash-Lite + SAM 2 on the source video) and one-sentence background prompts supplied locally via `baselines/void_points.json` and `baselines/void_bg_prompts.json`. |
| `kling4_client.py`, `kling4_credit.py` | Kling 4.0 API client, and the resource-pack guard used by `run_phycove_kling4_parallel.py --watch-credit`. |
| `phycove_seedance25_sources.json`, `phycove_seedance25_real_sources.json` | Public URL and SHA256 of every source video (simulated and real-video subsets), passed to the Seedance queue with `--sources-map`. |
| `requirements.txt` | Packages of the API runners. |

## Inputs and outputs

Every runner reads a release folder (`--benchmark-root`, the folder with
`benchmark_manifest.json`; pass its `real/` folder for the real-video subset)
and sends the model only the source video and the selected edit instruction,
unchanged (`--prompt-flavor quantitative --prompt-lang en` by default). The
edited ground truth, trajectories and simulation parameters never reach the
model. Predictions are written outside the release, by default to
`predictions/<release>/<flavor>_<lang>/<model>/` next to `releases/`
(`predictions/<release>/real/<flavor>_<lang>/<model>/` for the real-video
subset):

```text
<model>/
  run_manifest.json                    # run records (one file per shard when sharded)
  videos/<scene>/<case_id>.mp4         # prediction
  videos/<scene>/<case_id>.task.json   # request fingerprint, source and output SHA256, provider task state
```

Running a command again resumes it: a finished case is skipped only when its
source, prompt, configuration and output hash all match, and a changed
configuration is refused (use another `--predictions-root`). `--dry-run` checks
the selection, source hashes and prompts without loading a model or calling an
API. Cases are selected with `--split-file`, `--filter-scene`, `--filter-kind`
and similar options (see each runner's `--help`).

## Locations

Paths are passed on the command line or through environment variables; use
absolute paths, since the GPU launchers start their workers in this folder.

| Variable | Used by | Content |
| --- | --- | --- |
| `PHYCOVE_ROOT` | every `run_phycove_*` runner | Default of `--benchmark-root`; without it the option is required (`run_baseline.py` always requires it). |
| `MODEL_ROOT` | JoyAI-Video-Edit, Kiwi-Edit, OmniWeaving, VOID | Folder of the model deployments (default `models`): `JoyAI-Video-Edit/` (with its `env/`), `Kiwi-Edit/checkpoints/kiwi-edit-5b-instruct-only-diffusers/`, `OmniWeaving/{src,checkpoints,env}/`, and for VOID `CogVideoX-Fun-V1.5-5b-InP/`, `void/void_pass1.safetensors`, `sam2_hiera_large.pt`. |
| `KIWI_EDIT_MODEL_PATH`, `OMNIWEAVING_MODEL_PATH`, `OMNIWEAVING_SRC`, `OMNIWEAVING_TMP` | Kiwi-Edit, OmniWeaving | Override single locations under `MODEL_ROOT`; JoyAI-Video-Edit takes `--model-root`. |
| `VOID_ROOT`, `VOID_ENV` | VOID | Checkout of the official `void-model` repository (default `void-model`) and the conda environment VOID runs in (default `envs/void`). |
| `KLING_API_KEY`, `MINIMAX_API_KEY`, `ARK_API_KEY`, `DASHSCOPE_API_KEY`, `GEMINI_API_KEY` | API models, VOID | Provider keys; `MINIMAX_API_BASE` and `MINIMAX_PROXY` are optional. |

## Models

| Model (key) | Runner | Access | Setting |
| --- | --- | --- | --- |
| JoyAI-Video-Edit (`joyai_video_edit`) | `run_phycove_joyai_video_edit[_parallel].py` | local GPU | official streaming runtime, 2 denoising steps, seed 42, 1248x720, `max_temporal_ids` 8, low-VRAM FP8 layout |
| Kiwi-Edit (`kiwi_edit`) | `run_phycove_kiwi_edit[_parallel].py` | local GPU | instruction-only 5B weights, first 81 frames (the trained length), 50 steps, seed 0, tiled VAE decoding, written at 1280x720 and 24 fps |
| OmniWeaving (`omniweaving`) | `run_phycove_omniweaving[_parallel].py` | local GPU | `editing` task with the official defaults (guidance 6.0, flow shift 7.0, 50 steps), seed 0, 848x480, source padded to 97 frames and cut back to 96, FlashAttention-2 |
| Kling 4.0 (`kling4_0_video`) | `run_phycove_kling4[_parallel].py` | API, `KLING_API_KEY` | omni-video endpoint, `Edit @Video1. ` followed by the instruction, 720p, 4 s; the source is passed by public URL (`--source-url-template`) and checked against its SHA256 |
| MiniMax H3 (`minimax_h3`) | `run_phycove_minimax_h3[_parallel].py` | API, `MINIMAX_API_KEY` | 768P, 4 s, adaptive aspect ratio |
| Seedance 2.5 (`seedance25`) | `run_phycove_seedance25[_parallel].py` | API, `ARK_API_KEY` | `doubao-seedance-2-5-260628`, 720p, seed 42; the source is passed by the public URL in `--sources-map` |
| Wan 3.0 (`wan3_0_video`) | `run_phycove_wan3[_parallel].py` | API, `DASHSCOPE_API_KEY` | 720P, 4 s, adaptive aspect ratio, seed 42, no prompt rewriting, no audio; the source is uploaded through the provider's temporary file upload |
| VOID (`void`) | `run_baseline.py --baseline void --filter-kind DELETE` | local GPU, `GEMINI_API_KEY` | official VOID pipeline (SAM 2 mask from the click points, Gemini reasoning about affected regions, quadmask, CogVideoX-Fun inpainting); Remove edits only |

The local models run in environments built from their official repositories
(JoyAI-Video-Edit, Kiwi-Edit, OmniWeaving, VOID). The API runners need
`pip install -r requirements.txt` and FFmpeg (`ffprobe`, `ffmpeg`) on the path.
The single-case Kling and Wan runners select one case unless `--limit` is given
and refuse selections above an estimated cost (`--max-units`,
`--max-cost-cny`).

```bash
cd eval/models
export PHYCOVE_ROOT=/path/to/releases/PhyCoVE MODEL_ROOT=/path/to/models

# check the inputs only
python run_phycove_wan3.py --limit 1 --dry-run

# local model, one shard per GPU (arguments after -- go to every shard)
$MODEL_ROOT/OmniWeaving/env/bin/python run_phycove_omniweaving_parallel.py --gpus 0 1 2 3 \
  --job-directory jobs/omniweaving -- --continue-on-error

# API models, bounded concurrency
python run_phycove_wan3_parallel.py --job-directory jobs/wan3
python run_phycove_seedance25_parallel.py --sources-map phycove_seedance25_sources.json \
  --job-directory jobs/seedance25
python run_phycove_wan3_parallel.py --benchmark-root $PHYCOVE_ROOT/real --job-directory jobs/wan3_real

# VOID on the Remove edits
python run_baseline.py --baseline void --benchmark-root $PHYCOVE_ROOT --filter-kind DELETE \
  --predictions-root /path/to/predictions/PhyCoVE/quantitative_en --skip-existing
```

To add a model, subclass `BaselineModel` (see `baselines/no_edit.py`),
implement `edit_video`, and register it in `BASELINES` in `run_baseline.py`.
