# entryway_eva_slippers

On the stone floor of an entryway, an EVA slide (slipper) is released about 45 cm above the floor
with a horizontal speed of about 0.25 m/s; it falls, hits the floor and a second slide that rests
there, and both settle. This is an elastic–elastic scene: two deformable slides collide with each
other and the floor. The source video is 4 s at 24 fps (96 frames), 1280×720; frame k shows the
native state at t = (k−1)/24 s.

## Scene

- Slides: moulded EVA, density 200 kg/m³, Young's modulus 0.35 MPa, with a contoured heel cup,
  soft grip, smooth cuff borders, fine pores and a size mark (`tools/native/hero_materials.py`).
  The falling slide's centroid starts 0.456 m above the floor.
- Floor: scanned stone tile, friction 0.55.
- Room (`tools/native/room_scene.py`): sage grey front door, entryway bench, shoe cupboard with an
  oak top, coir door mat and scanned props (a wicker basket, rubber boots, a potted plant).
- Camera: the shared low entryway camera of the scene specification, 46 mm lens on a 36 mm sensor
  (as recorded in the ground truth), fixed for all cases. Camera, lights, room and every initial
  pose are shared by all cases.
- Rendering: Blender Cycles, 128 samples. The slides are rendered from their exact native FEM
  surface vertices, with no smoothing or subdivision. The published look
  (`tools/native/realism.py`, applied right after the room) adds a window opening (1.3 × 1.5 m)
  in the left wall with morning sun through it (strength 13, 0.8° disc, warm white), sets the
  room's area fills to 8% and the world background to 35%, uses AgX Medium High Contrast at
  exposure −0.25 EV, and adds lived-in wear (smudges, grime, scratches and shoe scuffs on the
  floor, grime on the door mat, mottling on the walls, light wear on door, skirting, cupboard and
  hardware, and fine grit of 0.5–1.8 mm grains). Every static addition stays outside the volume
  that both slides, the tray and their bounce occupy in every case.
- Materials are effective values, not calibrated.

## Physics

- Solver: libuipc 0.0.28 (CUDA, bdf2 integrator). Both slides are compressible volumetric FEM
  bodies (StableNeoHookean with a native objective-viscosity extension) with two-way IPC contact
  against the floor and each other, on the production tetrahedral geometry in
  `assets/scenes/entryway_eva_slippers/`. The shoe tray is a finite-mass affine body.
- Sampling: the solver samples exactly 24 Hz and stores 97 states (0–4 s, the last one the native
  endpoint at 4 s); the first 96 are the video frames.
- `tools/native/simulate.py` solves source, stiff_falling, remove_resting and add_shoe_tray with
  `tools/native/vocab_hero.py`; `tools/native/simulate_revision.py` runs the same solver for
  slippery_floor and light_falling with `tools/native/vocab_revised.py`. Both run with the
  production mesh and isotropic material (`--mesh production --isotropic`, set by
  `tools/launch.py`).
- ADD case: solved with its native preset (`native_edit_dsl` in the builder:
  `ADD shoe_tray AT PRESET beside_resting_slide`); the published DSL places the same tray on the
  line between two named display anchors in `edit_vocab.py` (the resting slide and an empty floor
  spot), whose midpoint lies 1.5 cm below the tray centre because the tray stands on the floor.

## Measured motion

From the published ground truth (surface-vertex centroids in m). The falling slide reaches the
resting slide at about frame 7.

| Case | Falling slide centroid height at frame 96 (m) | Resting slide moved (mm) |
|---|---|---|
| `source` | 0.049 | 0.7 |
| `edit_stiff_falling` | 0.036 | 3.3 |
| `edit_slippery_floor` | 0.025 (on the floor) | 5.8 |
| `edit_light_falling` | 0.059 (still settling at the end) | 0.7 |
| `edit_remove_resting` | 0.025 (on the floor) | – |
| `edit_add_shoe_tray` | 0.062 (on the tray; the tray stays in place) | 0.5 |

## Validation

`--stage verify` checks the accepted native delivery: the video and native cache against each
case's `artifact_manifest.json`, the renderer's binding to the native cache, the
media contract and the 97-sample 24 Hz native clock. It performs no new physical solve.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | slides 200 kg/m³, E = 0.35 MPa; floor friction 0.55 |
| `edit_stiff_falling` | `SET falling_slipper.young_modulus TIMES 4` | falling slide E 0.35 → 1.4 MPa |
| `edit_slippery_floor` | `SET stone_floor.friction TIMES 0.25` | floor friction 0.55 → 0.1375 |
| `edit_light_falling` | `SET falling_slipper.density TIMES 0.5` | falling slide density 200 → 100 kg/m³ |
| `edit_remove_resting` | `DELETE resting_slipper` | resting slide absent from frame 1 |
| `edit_add_shoe_tray` | `ADD shoe_tray BETWEEN resting_slipper AND left_floor_spot AT MIDPOINT` | wooden shoe tray with a raised rim on the floor from frame 1 |

The native case ids drop the `edit_` prefix. `PCVE_SOURCE` and `PCVE_EDITS` in the builder equal
the published prompts; edit prompts are the output of `pcve_edit_dsl.make_prompts` for
`edit_vocab.VOCAB`, the source prompts are written from the scene specification and the source
video, and the ADD prompts name the airborne slide's landing point on the floor.

## Assets

- `scenes/entryway_eva_slippers` (url and derived): production geometry, the native viscosity
  extension inputs, room assets and the scene specification. Files with a URL are downloaded from
  their provider; derived files are made by this project and have no public download.

```bash
python3 scripts/download_assets.py --scene entryway_eva_slippers          # download and check sha256
python3 scripts/download_assets.py --scene entryway_eva_slippers --check  # check only
```

## Requirements

- Linux. Solver runtime: libuipc 0.0.28 from `tools/ipc_probe_deps` and `tools/manifold3d_deps` in the
  repository root and the CUDA 12 runtime library of the viscosity extension in
  `.runtime/entryway_eva_slippers/lib/`, all put on the search paths by
  `tools/native/pool_worker.py`; a Python 3.10 staged in `.runtime/entryway_eva_slippers/python/`
  is used when present, else the current interpreter (it needs numpy and scipy).
- An NVIDIA GPU with CUDA for the solver and Cycles.
- Blender 4.3.2: `--blender-bin`, else `tools/blender-4.3.2-linux-x64` in the repository root, else
  `pcve_assets.blender()`.
- The accepted native delivery under `renders/entryway_eva_slippers/accepted_delivery/` (per-case
  `simulation.npz`, configs, videos, the edit suite manifest and the production specification of
  the edits): `--stage verify` and the default render caches read it. It is not registered in
  `assets.json`; `PCVE_ENTRYWAY_DATA` points the code at another copy.

## Commands

Run from the repository root.

```bash
python3 scripts/elastic_elastic/entryway_eva_slippers/build_pcve_entryway_eva_slippers.py --stage verify
python3 scripts/elastic_elastic/entryway_eva_slippers/build_pcve_entryway_eva_slippers.py --stage prepare
python3 scripts/elastic_elastic/entryway_eva_slippers/build_pcve_entryway_eva_slippers.py --list-edits
python3 scripts/elastic_elastic/entryway_eva_slippers/build_pcve_entryway_eva_slippers.py --show-prompts slippery_floor
python3 scripts/elastic_elastic/entryway_eva_slippers/simulate_entryway_eva_slippers.py --case stiff_falling \
  --out renders/entryway_eva_slippers/solves/stiff_falling
python3 scripts/elastic_elastic/entryway_eva_slippers/render_entryway_eva_slippers.py --case stiff_falling \
  --out renders/entryway_eva_slippers/solves/stiff_falling_render
blender -b --python-exit-code 1 --python scripts/elastic_elastic/entryway_eva_slippers/tools/native/realism.py -- \
  --case stiff_falling --cache renders/entryway_eva_slippers/solves/stiff_falling/simulation.npz \
  --out renders/entryway_eva_slippers/solves/stiff_falling_blender
```

- `--stage prepare` checks that the registered assets are present. `--out` with `--stage verify`
  also writes `<out>/verify_report.json` (a fresh folder under `renders/entryway_eva_slippers/`).
  `--native-help` prints the scene-specific options of an entry.
- Without `--gpu-uuid` (default `auto`) a GPU job goes through the lease launcher
  `tools/native/pool_worker.py` (fresh hardware query, shared GPU policy ranking, lease, UUID
  binding and a launch receipt); `--pool-audit` optionally passes
  a GPU inventory JSON, rejected when older than five minutes. With `--gpu-uuid <UUID>` the
  launcher uses that GPU; `--threads-count` sets CPU threads.
- The render entry renders the look of the published videos (`tools/native/realism.py` over
  `tools/native/render_hero.py`, with the production-edit vocabulary for slippery_floor and
  light_falling) at 128 samples. Without `--cache` it uses the case's cache in the accepted
  delivery; otherwise it needs a matching cache of the same production geometry. Raw render output
  is a frame sequence. The Blender command renders the same look directly (`--samples N` sets the
  samples).

## Outputs

- `renders/entryway_eva_slippers/<new folder>/`: new solves, renders, verify reports.
- `renders/entryway_eva_slippers/launches/`: launch receipts and logs.
- The published suite is `renders/pcve_suites/pcve_entryway_eva_slippers_suite/` (videos,
  prompts, ground truth); `scene_manifest.json` points to it. Its ground-truth files give the
  render camera and, per frame, the surface-vertex centroid of each slide (deformable, with the
  bounding box of its rest surface as dimensions) and the centre of the tray, taken from each
  case's native `simulation.npz`. `--export-prompts [--dry-run]` of the builder writes prompts into
  a suite.

## Code layout

- `build_pcve_entryway_eva_slippers.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`), `--stage verify` and `--stage prepare` (entry point).
- `simulate_entryway_eva_slippers.py`: solve one case through `tools/launch.py` (entry point).
- `render_entryway_eva_slippers.py`: replay one native cache in the published look through `tools/launch.py` (entry point).
- `edit_vocab.py`: DSL vocabulary of the published cases (`vocab_revised` plus display-only ADD anchors).
- `tools/launch.py`: argument front end of the two entries.
- `tools/retained.py`: accepted native delivery checks.
- `tools/native/pool_worker.py`: GPU launcher.
- `tools/native/simulate.py`, `tools/native/simulate_revision.py`: native FEM/IPC solver for the two case groups.
- `tools/native/geometry.py`, `tools/native/material_model.py`, `tools/native/shoe_tray.py`: geometry, material model and the shoe tray.
- `tools/native/render.py`, `tools/native/render_hero.py`, `tools/native/render_replay.py`: Blender replay of the exact FEM surfaces.
- `tools/native/room_scene.py`, `tools/native/hero_materials.py`: room and slide materials.
- `tools/native/realism.py`: look of the published videos (overlay on `tools/native/render_hero.py`).
- `tools/native/common.py`: paths and helpers.
- `tools/native/vocab_hero.py`, `tools/native/vocab_revised.py`, `tools/native/vocab_replay.py`, `tools/native/edit_vocab.py`, `tools/native/scene_spec_replay.json`: vocabularies and specification of the solver and renderers.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: published suite pointer and data locations.

## Limitations

- Materials are effective values; there is no material calibration.
- The ADD case is solved from a native preset placement; the published DSL describes the same
  tray through display anchors.
- Determinism of the GPU solve on other machines is not verified.
