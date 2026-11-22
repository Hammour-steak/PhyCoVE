# toy_car_ramp_pool_genesis

A toy car slides down an 18° ramp in a sunny courtyard into a rounded inflatable pool, plunges in,
splashes and floats or sinks. This is a rigid–fluid scene with two-way coupling between the free
car and the water; the ramp, pool floor and walls are fixed. The source video is 4 s at 24 fps
(96 frames), 1280×720.

## Scene

- Car: a free rigid cuboid 0.16 × 0.071 × 0.055 m, 0.42 kg, friction 0.1; the visual car is a
  separate mesh.
- Ramp: 18°, friction 0.07.
- Water: 998 kg/m³, kinematic viscosity 1.004e-6 m²/s, filled to 0.105 m in a rounded basin.
- Courtyard: the scene file `scene_pool_corrected.blend` (asset `scenes/toy_car_ramp_pool_genesis`)
  with ground, walls, plants and lighting.
- Rendering: Cycles, 32 samples. Liquid outside the measured rounded basin is removed at render
  time only.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 1 cm particles, settled for 72 frames
  before the clip.
- Time step: 8 steps × 4 substeps per frame (dt = 1/192 s per step).
- Coupling: Genesis `rigid_sph` with this scene's pressure-force patch, two-way between the car
  and the water.
- Basin: a signed-distance field (4 mm cells) with an extra fixed-container non-penetration
  projection.
- High-viscosity edit: 32 substeps per step.
- The source is a recorded physical take: among several runs of the same, unchanged physics it is
  the one with the smallest car yaw (`normal_b`, at most 2.6°). Re-running the solver does not
  reproduce it frame for frame (`recipes/source_plan.json`).

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | the car slides down from rest, plunges at about 1.8 m/s about 1 s in, splashes, then floats and drifts forward at under 0.2 m/s |
| `edit_no_car` | `DELETE car` | the car is removed |
| `edit_heavy_car_x3` | `SET car.mass TIMES 3` | car mass × 3 = 1.26 kg |
| `edit_low_density_div4` | `SET water.density TIMES 0.25` | water density ÷ 4 = 249.5 kg/m³ |
| `edit_high_viscosity_x20000` | `SET water.viscosity TIMES 20000` | kinematic viscosity × 20000 = 0.02008 m²/s; the car barely moves forward after entering |
| `edit_mass_after_2s_x3` | `SET car.mass TIMES 3 AT FRAME 49` | frames 1–48 as the source; car mass × 3 from 2.00 s |

The workflows name the edits without the `edit_` prefix (`no_car`, `heavy_car_x3`, …). The case
definitions are in `recipes/edit_plan.json`; `edit_vocab.py` holds the edit DSL vocabulary and
the published prompts.

## Assets

- `scenes/toy_car_ramp_pool_genesis` (derived): the courtyard scene file read by `recipes/*.json`
  and the pool geometry (collider, initial water volume, basin profile) read by
  `edits/launch_physics.py`. It has no public download.
- `rigid_fluid/toy_car_ramp_pool_genesis` (url and derived): courtyard textures and plants, and
  the animation geometry.
- `elastic_fluid/elastic_fluid_duck` (derived): files of the `elastic_fluid_duck` scene, listed
  because the splash step uses that scene's splash module.

```bash
python3 scripts/download_assets.py --scene toy_car_ramp_pool_genesis          # download and check sha256
python3 scripts/download_assets.py --scene toy_car_ramp_pool_genesis --check  # check only
```

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`) and this scene's `rigid_sph` pressure-force patch to Genesis.
- An NVIDIA GPU for Genesis and for Cycles.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.
- The recorded source take: the `current-source` and `current-edits` workflows read simulation
  results under `renders/toy_car_ramp_pool_genesis/`, which are not assets: `reference_source/`
  (the reference source run; its settled pool water `simulation/settle_final/water_state.npz`
  is the initial water of every edit), `reference_configuration/` (the configuration and file
  inventory the selected take is checked against), `yaw_audit/` (the instrumented runs;
  `runs/normal_b` is the selected take) and `retained_edit_suite/` (the retained edit suite manifest).

## Commands

Run from the repository root.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/toy_car_ramp_pool_genesis/build_pcve_toy_car_ramp_pool_genesis.py \
  --workflow current-source --out-root renders/toy_car_ramp_pool_genesis/current_source --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/toy_car_ramp_pool_genesis/build_pcve_toy_car_ramp_pool_genesis.py \
  --workflow current-source --out-root renders/toy_car_ramp_pool_genesis/current_source
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/toy_car_ramp_pool_genesis/build_pcve_toy_car_ramp_pool_genesis.py \
  --workflow current-edits --out-root renders/toy_car_ramp_pool_genesis/current_edits
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/toy_car_ramp_pool_genesis/build_pcve_toy_car_ramp_pool_genesis.py \
  --input-blend assets/scenes/toy_car_ramp_pool_genesis/scene_pool_corrected.blend \
  --out-root renders/toy_car_ramp_pool_genesis/plain --gpu 0 --dry-run
```

- The published videos come from the `current-source` and `current-edits` workflows
  (`reproduce_current.py`, with the solver code in `source/` and `edits/`). They relocate the
  recorded plans in `recipes/` into the new workspace and keep the review gates; check the
  `<workspace>/status.json` and the review markers between stages. `--stage` runs `prepare`,
  `simulate`, `surface`, `render` or `verify`; the default (`all`) prepares the workspace and runs
  only the simulate stage, so run `surface`, `render` and `verify` afterwards.
- Without `--workflow` the builder runs a plain settle → simulate → surface → render → verify
  pipeline from a scene file with `physics/simulate_genesis_toy_car_pool.py`. It does not carry
  the published runs' settings; use it for new runs, not to reproduce the published suite.

## Outputs

- `renders/toy_car_ramp_pool_genesis/current_source/`, `.../current_edits/`: workflow workspaces
  with `<workspace>/status.json`, review markers and the stage outputs.
- `renders/toy_car_ramp_pool_genesis/plain/`: `settle/`, `run/` (particles and `meshes/`),
  `render/video.mp4`, `video_verification.json` and `pipeline_manifest.json`.
- The published suite is `renders/pcve_suites/pcve_toy_car_ramp_pool_genesis_suite/`; the
  workflows do not write there.

## Code layout

- `build_pcve_toy_car_ramp_pool_genesis.py`: plain pipeline and the recorded workflows (entry point).
- `simulate_toy_car_ramp_pool_genesis.py`: Genesis simulation, modes `settle` and `run` (entry point).
- `surface_toy_car_ramp_pool_genesis.py`: particle-to-mesh reconstruction.
- `render_toy_car_ramp_pool_genesis.py`: Blender rendering (entry point).
- `reproduce_current.py`: relocates the recorded source and edit plans into a fresh workspace.
- `recipes/source_plan.json`, `recipes/edit_plan.json`: recorded plans of the source and the edits.
- `source/`: source pipeline (scene refinement, water repair, surfaces, rendering, checks).
- `edits/`: edit pipeline (physics launch, timed mass change, surfaces, rendering and checks).
- `physics/simulate_genesis_toy_car_pool.py`, `physics/surface_genesis_toy_car_pool.py`: simulation and surface of the plain pipeline.
- `appearance/render_genesis_toy_car_pool.py`: rendering of the plain pipeline.
- `edit_vocab.py`: edit DSL vocabulary, case DSL and the published prompts.
- `entrypoints.json`: entry-point options, runtimes and workflows for the shared CLI.
- `scene_manifest.json`: cases and video hashes of the published suite.

## Limitations

- The car is a cuboid collider; the visual car is a separate mesh.
- The source is a selected take, not a repeatable run.
- The recorded workflows read simulation results under `renders/toy_car_ramp_pool_genesis/` that
  are not part of the asset registry.
