---
pretty_name: PhyCoVE
license: mit
language:
- en
- zh
task_categories:
- video-to-video
size_categories:
- n<1K
tags:
- video
- physics
- video-editing
- counterfactual
- benchmark
- simulation
- blender
- datasets
- arxiv:2611.29184
configs:
- config_name: default
  default: true
  drop_labels: true
  metadata_filenames: [metadata_viewer.jsonl]
  data_files:
  - split: test
    path:
    - metadata_viewer.jsonl
    - scenes/*/cases/*/video.mp4
- config_name: real
  drop_labels: true
  metadata_filenames: [metadata_viewer.jsonl]
  data_files:
  - split: test
    path:
    - real/metadata_viewer.jsonl
    - real/scenes/*/cases/*/video.mp4
---

# PhyCoVE

[Paper (PDF)](https://arxiv.org/pdf/2611.29184) · [arXiv](https://arxiv.org/abs/2611.29184) · [Project Page](https://phycove.github.io/) · [Code](https://github.com/Hammour-steak/PhyCoVE)

**PhyCoVE is a simulation-based benchmark for physics-aware video editing, with 90 scenes, 90 source videos, and 508 editing tasks.** Given a source video and an instruction that changes physical properties or object presence, a model generates an edited video. Each task includes a reference edited video, instructions in English and Chinese, and simulation-derived ground-truth annotations.

The benchmark covers rigid, elastic, fluid, and mixed interactions. Examples include collisions, falling objects, cloth deformation, liquid pouring, and buoyancy. The videos of this main set are rendered from simulated scenes rather than captured from the real world.

The release also contains **PhyCoVE-Real**, a small real-recorded subset with 20 scenes, 20 source videos, and 25 editing tasks. It is stored under `real/` and is reported separately from the main set (see [PhyCoVE-Real](#phycove-real)).

| Release contents | Count / format |
| --- | --- |
| Scenes | 90 |
| Source videos | 90 |
| Editing tasks / reference edited videos | 508 |
| Unique videos | 598 |
| Ground-truth files | 598, one per source or edited case |
| Video format | MP4 / H.264, 1280 × 720, 24 fps |
| Clip length | 4 seconds / 96 frames |
| Instruction variants per task | English / Chinese × vague / quantitative |
| Evaluation split | `test` — 508 paired-video tasks |

## Latest update — 2026-11-13

- Added **70 `DELETE` editing tasks across 59 existing scenes**, bringing the benchmark to **508 editing tasks and 598 unique videos**. All new tasks remove an object from the start of the clip and include reference videos, bilingual prompts, and ground-truth annotations.
- Updated affected prompts to identify objects by visible appearance, such as the star-patterned toy ball, white toy chest, and purple toy sports car.
- Added the **PhyCoVE-Real** subset under `real/`: 20 real-recorded scenes and 25 editing tasks, loaded with the `real` configuration.
- Re-rendered the source and five reference edited videos for `metro_security_bag_curtain` to fix the flashing scanner hood. Use the current videos and their updated `video_sha256` values when refreshing a cached copy.

## Task

For each editing task:

1. Read the **source video** and select one of the four instruction variants.
2. Generate an edited video that follows the requested physical intervention.
3. Compare the prediction against the **reference edited video** and, where appropriate, the accompanying ground truth.

Reference edited videos and their ground-truth files are evaluation targets. They should not be supplied as inputs to the editing model.

Edits use three operations:

| Operation | Meaning | Tasks |
| --- | --- | ---: |
| `SET` | Change a physical parameter or initial condition | 333 |
| `DELETE` | Remove an object or material | 157 |
| `ADD` | Introduce an object | 18 |
| **Total** | | **508** |

There are **445 whole-clip edits** and **63 edits that begin partway through a clip**. The manifest records each intervention as an edit DSL statement, such as:

```text
SET apple.mass TIMES 1.5
SET water.viscosity TIMES 10000
DELETE water AT FRAME 49
```

`applies_from_frame` is **1-based**: frame 1 begins at 0 seconds; frame 49 begins at 2 seconds in a 24 fps clip. For an intervention starting at frame `f`, the intended application time is `(f - 1) / 24` seconds. Frames preceding the intervention are intended to retain the source behavior.

## Scene coverage

| Interaction category | Manifest value | Scenes | Editing tasks |
| --- | --- | ---: | ---: |
| Rigid–rigid | `rigid_rigid` | 40 | 236 |
| Rigid–elastic | `rigid_elastic` | 28 | 160 |
| Rigid–fluid | `rigid_fluid` | 16 | 80 |
| Elastic–fluid | `elastic_fluid` | 4 | 21 |
| Elastic–elastic | `elastic_elastic` | 2 | 11 |
| **Total** | | **90** | **508** |

Properties include mass, friction, restitution, initial velocity, gravity, density, viscosity, stiffness, and scene-specific physical parameters. The exact parameter names and counts are in `benchmark_manifest.json["counts"]["by_property"]`; use each task's `physics_diff` and `edit_dsl` to interpret its intervention.

## Download and use

### Download the complete release

```bash
pip install -U huggingface_hub
```

```python
from huggingface_hub import snapshot_download

root = snapshot_download(
    repo_id="ccmoony/PhyCoVE",
    repo_type="dataset",
    local_dir="PhyCoVE",
)
```

For a reproducible experiment, pass a specific Hub commit hash as `revision` and record it with the results.

### Read a task with the authoritative manifest

This route uses only Python's standard library after the files have been downloaded:

```python
import json
from pathlib import Path

root = Path("PhyCoVE")
benchmark = json.loads((root / "benchmark_manifest.json").read_text(encoding="utf-8"))
task = benchmark["edits"][0]

source_video = root / task["source_video"]
instruction = task["prompts"]["quantitative"]["en"]
reference_video = root / task["edited_video"]
ground_truth = json.loads((root / task["ground_truth"]).read_text(encoding="utf-8"))

print(task["global_id"])
print(instruction)
print(source_video, reference_video)
```

### Load paired videos with Hugging Face Datasets

Use `datasets>=4.0` for the paired-video metadata convention. The default configuration and Dataset Viewer read the 508 English-only editing-task rows in `metadata_viewer.jsonl`; shared source videos are referenced by those rows and do not create additional tasks.

```bash
pip install -U "datasets>=4.0"
```

```python
from datasets import Video, load_dataset

tasks = load_dataset("ccmoony/PhyCoVE", split="test")

# Inspect paths and metadata without requiring a video decoder.
tasks = tasks.cast_column("source", Video(decode=False))
tasks = tasks.cast_column("video", Video(decode=False))
example = tasks[0]

print(example["id"])
print(example["prompt_quantitative_en"])
print(example["source"])  # input source video
print(example["video"])   # reference edited video
```

Automatic video decoding requires the decoder dependencies supported by your installed `datasets` version. The manifest-based loading example above works independently of those dependencies.

For a local copy, select the metadata and videos explicitly. This also prevents scene names containing words such as `train` from affecting automatic split inference:

```python
tasks = load_dataset(
    "videofolder",
    data_files={"test": ["PhyCoVE/metadata.jsonl", "PhyCoVE/scenes/*/cases/*/video.mp4"]},
    split="test",
    drop_labels=True,
)
```

## File layout

```text
PhyCoVE/
├── README.md
├── benchmark_manifest.json
├── metadata.jsonl
├── metadata_viewer.jsonl        # English-only Dataset Viewer index
├── assets.json
├── real/                       # PhyCoVE-Real subset, same layout with its own indexes
├── scenes/
│   └── <scene>/cases/<case_id>/
│       ├── video.mp4
│       ├── prompts.json
│       └── ground_truth_transforms.json
└── splits/
    ├── all.txt
    ├── by_category/*.txt
    ├── by_kind/*.txt
    ├── by_property/*.txt
    └── by_timing/*.txt
```

All paths in the indexes are relative to the dataset root. Source videos are stored once per scene and reused by its editing tasks. Source case IDs are recorded in `sources[].case_id`; read them from the manifest rather than assuming a directory name.

### Manifest fields

`benchmark_manifest.json` is the authoritative index. Its `sources` list contains the 90 source records; `edits` contains the 508 evaluation tasks. `scene_metadata` provides scene titles and interaction categories, and `counts` summarizes the release.

| Editing-task field | Description |
| --- | --- |
| `global_id` | Unique task identifier, `<scene>/<case_id>` |
| `scene`, `case_id`, `interaction_category` | Scene, case, and physical interaction category |
| `source_case_id`, `source_video` | Input source case and its video path |
| `edited_video` | Reference edited video path |
| `ground_truth` | Reference case's ground-truth JSON path |
| `video_sha256` | SHA-256 of the reference edited video |
| `prompts` | Nested `vague` / `quantitative` × `zh` / `en` instruction strings |
| `edit_dsl`, `edit_kind`, `object_id`, `property` | Requested intervention; `property` may be null for presence edits |
| `physics_diff`, `edit_summary`, `outcome_type` | Existing parameter differences and descriptive metadata; inspect availability per task |
| `applies_from_frame`, `timing` | First affected frame and `whole_clip` / `partway` label |
| `original_validation_status` | Preserved authoring status for the original scene/case |

`metadata.jsonl` is the full bilingual flat index, with **one row per edit**. `metadata_viewer.jsonl` is its English-only projection used by the default Hub configuration and Dataset Viewer; it omits Chinese prompt fields and scene titles and translates the two Chinese DSL display hints into English. All bilingual prompts remain available in `metadata.jsonl`, the manifest, and the per-case prompt files. Its `id` corresponds to manifest `global_id`, `file_name` points to the reference video, and `source_file_name` points to the source. VideoFolder exposes the video paths as `video` and `source` video columns. Instructions are flattened into `prompt_vague_zh`, `prompt_vague_en`, `prompt_quantitative_zh`, and `prompt_quantitative_en`; `source_prompt_*` fields describe the source clip.

### Prompts

Source prompts describe the unedited scene. Editing prompts describe the intervention:

- **Quantitative:** names the requested numerical change and application frame.
- **Vague:** describes the requested change and its timing in qualitative terms.
- **English and Chinese:** both variants are included for every source and edit.

Prompt wording is preserved from the authoring suites. The release conversion does not rewrite the instructions.

### Ground truth

Every case includes a `ground_truth_transforms.json` with the `pcve_ground_truth/1` format and **96 frame records**. Annotations include scene/case identity, timing, camera information, and available object transforms and presence states. Additional physical quantities and provenance vary with the scene and solver; inspect the actual JSON before using a field in a metric. These annotations do not represent a universal per-particle fluid or deformable-body state.

### Selection indexes

`splits/all.txt` lists all 508 task IDs. The files in `by_category`, `by_kind`, `by_property`, and `by_timing` select tasks along different axes; they are **not independent train/validation/test partitions**. A task appears in one file within each axis and in selections across the other axes.


## PhyCoVE-Real

`real/` holds a real-recorded subset in the same layout as the main set, with its own `benchmark_manifest.json`, `metadata.jsonl`, `metadata_viewer.jsonl`, and `splits/`. It has 20 scenes, 20 source videos, and 25 editing tasks (21 `DELETE`, 3 `ADD`, 1 `SET`). The videos use the main set's format: MP4 / H.264, 1280 × 720, 24 fps, 96 frames.

- **Pairs.** Each source video and its reference edited video are separate recordings of the same setup, aligned on event timing. Trajectories, poses, and reflections differ between takes, so a pair is not a pixel-exact counterfactual. Trimming, cropping, frame sampling, and the exposure normalisation applied to 8 clips to remove camera auto-exposure jumps are recorded in `real/editing_provenance.json`.
- **Ground truth.** The files record frame timing, the mapping to original frames, object presence, and manually annotated events. 3D transforms, camera calibration, and physical parameters were not measured and are `null`, so trajectory-based physics metrics do not apply. Report video metrics for this subset separately from the main set.
- **Edit DSL.** Besides the main set's statements, three forms describe recorded edits: `DELETE a; DELETE b` removes several objects together (all are listed in `object_ids`), `ADD x` or `ADD x AT <region>` adds an object whose position is described only in the prompts, and `SET x.p INCREASE` / `DECREASE` gives the direction of an unmeasured change.

```python
real_tasks = load_dataset("ccmoony/PhyCoVE", "real", split="test")
```

## Evaluation and reproduction scope

This repository distributes **benchmark data for model evaluation**: source and reference videos, bilingual prompts, per-case annotations, indexes, and asset provenance. `assets.json` records asset sources, licenses, and checksums; it does not contain the 3D assets themselves.

Simulation caches, Blender scene files, solver environments, historical experiments, logs, intermediate render frames, and the scene-generation/evaluation code are not included. Rebuilding the simulated scenes requires the separate authoring code, its runtime dependencies, and the original or generated scene inputs. Downloading this dataset alone does not reproduce the simulations from scratch.

For experiments, report the dataset revision, task selection, prompt language/flavor, number of successfully generated videos, and any temporal or spatial preprocessing. Treat missing predictions and unavailable annotation fields explicitly. Perceptual similarity alone does not establish that a requested physical change was followed.

The authoring validation labels are preserved, including pending-review or unrecorded states. The main set is synthetic, and performance on it may not transfer directly to real-world footage.

## License and attribution

PhyCoVE is released under the [MIT License](LICENSE). Third-party asset attributions and their original license declarations are retained in `assets.json`; the MIT license does not replace those third-party terms.

## Citation

```bibtex
@article{yue2026phycove,
  title   = {PhyCoVE: Benchmarking Physical Counterfactual Video Editing across Diverse Material Dynamics},
  author  = {Yue, Conghan and Chen, Yuanjie and Xiao, Yunyan and Peng, Zeyu and Ye, Xingsong and
             Gao, Ya and Huang, Yanglin and Zhang, WeiYao and Han, Yue and Chen, Zhineng and Jiang, Yu-Gang},
  journal = {arXiv preprint arXiv:2611.29184},
  year    = {2026}
}
```

Dataset questions and reproducibility issues can be reported in the repository's [Community tab](https://huggingface.co/datasets/ccmoony/PhyCoVE/discussions).
