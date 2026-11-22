# apple_drop_kitchen_basin

A red apple is released above a round kitchen basin holding 10 cm of water. It falls, splashes
in, touches the basin floor, bobs back up and floats. This is a rigid–fluid scene with two-way
coupling: buoyancy, drag, bobbing and the splash come from one simulation. The source video is
4 s at 24 fps (96 frames), 1280×720.

## Scene

- Apple: 8 cm diameter, 850 kg/m³, released 37 cm above the basin. It floats about 85%
  submerged in theory.
- Water: 10 cm deep in an axisymmetric model of the round counter basin, 1000 kg/m³, kinematic
  viscosity 1e-6 m²/s. The counter is the floor of the simulation domain.
- Kitchen dressing: counter, cutting board, sink and objects standing on them, prepared as a
  ground map for the renderer.
- Start: the water first settles in the basin (`settle`); every case starts from that state.
- Rendering: water surface, spray, mist, foam, wetness maps and water beads are built from the
  particles, then rendered in Cycles with adaptive sampling (up to 1024 samples, noise threshold
  0.003), 180° shutter, exposure 0.7 and AgX Medium High Contrast.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 3 mm particles (about 658k), CUDA
  backend, 32-bit precision, fixed random seed.
- Time step: 1/240 s per step with 20 substeps (1/4800 s); 10 steps per video frame.
- Apple: a rigid sphere made of shells of boundary (ghost) particles, coupled two-way with the
  water through the pressure and viscous forces the solver computes on the ghosts. A smooth
  sphere gets no torque, so it does not rotate.
- Surface tension: Genesis cohesion 2.5e-3, calibrated so a free 2 × 2 × 4 cm water block
  oscillates at water's Rayleigh period (`physics/calibrate_surface_tension_apple_drop_kitchen_basin.py`).
- Water removal: the two deletion edits replay a finished source run and remove all water
  particles from the edit frame on (`physics/remove_water_edits.py`).

## Validation

In the source, free fall matches g·t (enters at frame 8, analytic 7.6), the apple touches the
floor about one frame after entry at about 2.2 m/s, the bobbing period is 0.625 s against about
0.6 s in theory, and it floats 87.6% submerged against 85.2% in theory. Particle count is
conserved (31 mL, 0.25%, splashes out) and the largest advective CFL number is 0.71, at entry.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | enters at frame 8, touches the floor, bobs (period 0.625 s) and floats 88% submerged |
| `edit_heavy_apple` | `SET apple.mass TIMES 1.5` | apple density 850 → 1275 kg/m³; it sinks and stays on the basin floor |
| `edit_high_density_liquid` | `SET water.density TIMES 2` | water density × 2 (cohesion halved to keep the same surface tension); floats 45% submerged (theory 43%) |
| `edit_viscous_liquid` | `SET water.viscosity TIMES 10000` | kinematic viscosity 0.01 m²/s with 50 substeps; no splash, the apple stops just under the surface and creeps back up |
| `edit_delete_water` | `DELETE water` | all water removed from frame 1; the apple falls onto the empty basin floor |
| `edit_delete_water_at_2s` | `DELETE water AT FRAME 49` | frames 1–48 as the source; all water removed from frame 49 and the apple continues with no liquid force |

The builder names the two deletion edits `delete_water` and `delete_water_at_2s`; the published
suite stores them as `edit_delete_water` and `edit_delete_water_at_2s`. `edit_vocab.py` holds the
edit vocabulary, each case's DSL and the published source prompts.

## Assets

- `blenderkit/red_apples` (manual): the apple.
- `blenderkit/round_counter_basin` (manual): the basin.
- `blenderkit/modern_living_kitchen` (manual): the kitchen room.
- `blenderkit/cutting_board` (manual): counter dressing.
- `blenderkit/bell_pepper` (manual): counter dressing.
- `elastic_fluid/elastic_fluid_duck` (derived): files of the `elastic_fluid_duck` scene, listed
  because the splash stage loads that scene's splash module.

```bash
python3 scripts/download_assets.py --scene apple_drop_kitchen_basin          # download and check sha256
python3 scripts/download_assets.py --scene apple_drop_kitchen_basin --check  # check only
```

Manual files need a free BlenderKit account; the script prints each asset page and the file
names to save. Derived files are made by this project and have no public download.

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`).
- An NVIDIA GPU for Genesis and for Cycles. The base simulation takes about 16 minutes on an
  RTX 4090.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it. Blender 4.3.2 with OptiX crashes
  under NVIDIA driver 550, so the render chain uses CUDA there; elsewhere `CYCLES_BACKEND=CUDA`
  selects it.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root. GPU steps wait for an idle GPU
(`scripts/rigid_fluid/bowling_ball_pool_drop/tools/run_on_idle_gpu.sh`).

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/apple_drop_kitchen_basin/build_pcve_apple_drop_kitchen_basin.py \
  --out-root renders/apple_drop_kitchen_basin \
  --cases source edit_heavy_apple edit_high_density_liquid edit_viscous_liquid --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/apple_drop_kitchen_basin/build_pcve_apple_drop_kitchen_basin.py \
  --out-root renders/apple_drop_kitchen_basin \
  --cases source edit_heavy_apple edit_high_density_liquid edit_viscous_liquid --render-gpus 2
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/apple_drop_kitchen_basin/build_pcve_apple_drop_kitchen_basin.py \
  --out-root renders/apple_drop_kitchen_basin/water_removal --cases delete_water delete_water_at_2s \
  --source-run renders/apple_drop_kitchen_basin/runs/source
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/apple_drop_kitchen_basin/build_pcve_apple_drop_kitchen_basin.py \
  --out-root renders/apple_drop_kitchen_basin --stage verify --cases source
```

- Only `source` runs when `--cases` is not given. `--stage simulate`, `render` or `verify` runs
  one step; finished products are never overwritten.
- `--render-gpus n` renders every n-th frame on each of n idle GPUs.
- The deletion edits read a finished source run given by `--source-run`; the default is the
  published source run in
  `renders/pcve_suites/pcve_apple_drop_kitchen_basin_suite/inputs/01_apple_drop_kitchen_basin/base`,
  which is only read.

## Outputs

- `renders/apple_drop_kitchen_basin/settle/water_state.npz`: the settled water.
- `renders/apple_drop_kitchen_basin/runs/<case>/`: particles, splash outputs, `ground.npz`,
  `render/` frames and `simulation_report.json`.
- `renders/apple_drop_kitchen_basin/<case>.mp4`: the rendered video, with
  `<case>_video_verification.json` (decode and format check).
- `renders/apple_drop_kitchen_basin/pipeline_manifest.json`: the plan and per-stage logs.
- The published suite is `renders/pcve_suites/pcve_apple_drop_kitchen_basin_suite/`; the builder
  does not write there.

## Code layout

- `build_pcve_apple_drop_kitchen_basin.py`: settle, simulate, render and verify the selected cases (entry point).
- `simulate_apple_drop_kitchen_basin.py`: Genesis simulation, modes `settle` and `run` (entry point).
- `render_apple_drop_kitchen_basin.py`: Blender rendering (entry point).
- `scene_apple_drop_kitchen_basin.py`: kitchen, basin, apple, camera and lights.
- `physics/splash_apple_drop_kitchen_basin.py`: splash and water-surface reconstruction.
- `physics/calibrate_surface_tension_apple_drop_kitchen_basin.py`: surface-tension calibration.
- `physics/remove_water_edits.py`, `physics/encode_water_removal.py`: the water-removal edits and their encoding.
- `appearance/ground_apple_drop_kitchen_basin.py`: kitchen ground map.
- `tools/pipeline_apple_drop_kitchen_basin.sh`: the render chain of one case.
- `tools/render_gpus_apple_drop_kitchen_basin.sh`, `tools/render_cpu_apple_drop_kitchen_basin.sh`: multi-GPU and CPU render launchers.
- `tools/package_native.py`: packaging of native outputs.
- `edit_vocab.py`: edit vocabulary, case DSL and the published source prompts.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases and video hashes of the published suite.

## Limitations

- The apple is a smooth sphere; its stem, shape and rotation are not simulated.
- The viscous edit uses ×1e4 rather than a stronger factor, which would need about 20× more
  substeps at 3 mm.
- Water beads, puddles and wet films are rendered from the particle data, not simulated as thin
  films.
