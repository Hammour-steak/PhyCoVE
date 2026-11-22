# bowling_ball_pool_drop

A 15 cm miniature bowling ball falls into a mountain pool at sunset. The splash, the air cavity,
the Worthington jet, buoyancy, drag and the ball's landing on the pool floor all come from one
two-way coupled simulation. This is a rigid–fluid scene. The source video is 4 s at 24 fps
(96 frames), 1280×720.

## Scene

- Ball: radius 0.075 m, 2.0687 kg (mean density 1170.65 kg/m³, so it sinks), three finger holes;
  its centre starts at z = 0.70 m moving down at 4.0 m/s.
- Pool: the visible opening of the mountain-pool deck, a parallelogram with sides 3.03 m and
  2.17 m (corners 77.3° / 102.7°), floor at z = −1.25 m, still water level at z = −0.250 m
  (11 cm below the coping).
- Water: 1000 kg/m³, kinematic viscosity 1e-6 m²/s.
- Start: the water first settles in the pool (`settle`); every case starts from that state.
- Camera at (1.25, −2.00, 0.45) m aimed at (0, 0, 0.25) m, 26 mm lens. A sun lamp at 10°
  elevation lights the water, ball and spray; the tiled tank receives that sunlight traced
  through the simulated water surface.
- Rendering: Cycles, 64 samples with denoising, exposure −0.75, AgX Medium High Contrast.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 2 cm particles (about 1.05 M), CUDA
  backend, 32-bit precision, fixed random seed.
- Time step: 1/240 s per step with 10 substeps; 10 steps per video frame (100 substeps per frame).
  Divergence and density error targets 0.1 and 0.05%.
- Domain: the pool walls are four planes clamped in the advection step; the domain reaches
  z = 4.25 m for the jet (tip at about 4.1 m).
- Ball: concentric shells of boundary particles; pressure and viscous impulses act on it inside
  every pressure iteration (two-way coupling). It only translates (a smooth sphere under pressure
  gets no torque) and rests half a particle above the floor.
- Surface tension is neglected (Weber number about 3.5e4).
- Timed edit: continues from the source's frame-49 particle state. From the edit onward it keeps
  the pressure reaction of fluid within one particle of the floor
  (`--conservative-floor-pressure`), which otherwise pins a light ball to the floor; a control
  with the original mass and the same setting stays on the floor. Timed edits support positive
  ball-mass changes only.
- `physics/physics_bowling_ball_pool_drop.py` holds the baseline physics; `edit_vocab.py`
  defines the edit DSL on it.

## Validation

The builder checks every video (decode, resolution, frame rate, frame count). The simulation
report records particle count, solver errors and, for the timed edit, the rounding bound of the
float16 velocities stored in the source checkpoint (promoted to float32 on loading; new frames
are float32).

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | splash, cavity and a jet up to about 4.1 m; the ball lands on the pool floor |
| `edit_light_ball` | `SET ball.mass TIMES 0.25626870931880164` | 0.530 kg (about 300 kg/m³); rises back and floats about 30% submerged |
| `edit_high_density_liquid` | `SET water.density TIMES 2` | water denser than the ball; it floats about 59% submerged |
| `edit_viscous_liquid` | `SET water.viscosity TIMES 100000` | 0.1 m²/s (entry Reynolds number about 9); splash, cavity and waves are damped and the ball creeps down |
| `edit_delete_ball` | `DELETE ball` | no ball from frame 1; the water is simulated afresh |
| `edit_light_ball_after_2s` | `SET ball.mass TO 0.5301437603 AT FRAME 49` | frames 1–48 as the source; from frame 49 the lightened ball rises from the floor |

The builder names the source `bowling_ball_pool_drop_baseline`; the published suite stores it
as `source`.

## Assets

- `blenderkit/bowling_ball` (manual, plus derived prepared files): the ball.
- `sketchfab/pool_in_the_mountains_baked` (manual): the pool deck and surroundings.
- `polyhaven/qwantani_patio` (url): the HDR sky.
- `elastic_fluid/elastic_fluid_duck` (derived): files of the `elastic_fluid_duck` scene, listed
  because the splash and caustics stages load that scene's modules.

```bash
python3 scripts/download_assets.py --scene bowling_ball_pool_drop          # download and check sha256
python3 scripts/download_assets.py --scene bowling_ball_pool_drop --check  # check only
```

Manual files need a free BlenderKit or Sketchfab account; the script prints each asset page and
the file names to save. Derived files are made by this project and have no public download.

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`).
- An NVIDIA GPU for Genesis and for Cycles; `PCVE_GPU=available` accepts an idle shared GPU with
  at least 16 GiB free. One case takes about 15 minutes of simulation and 25 minutes of splash,
  caustics and rendering.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root. GPU steps wait for an idle GPU (`tools/run_on_idle_gpu.sh`: no
compute process, under 256 MiB in use, 0% utilisation).

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/bowling_ball_pool_drop/build_pcve_bowling_ball_pool_drop.py \
  --out-root renders/bowling_ball_pool_drop --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/bowling_ball_pool_drop/build_pcve_bowling_ball_pool_drop.py \
  --out-root renders/bowling_ball_pool_drop --keep-intermediates \
  --cases edit_light_ball edit_high_density_liquid edit_viscous_liquid
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/bowling_ball_pool_drop/build_pcve_bowling_ball_pool_drop.py \
  --out-root renders/bowling_ball_pool_drop --skip-existing --keep-intermediates --resume-source \
  --cases edit_delete_ball edit_light_ball_after_2s
```

- The first build settles the water and builds the source and three edits; the second appends
  the deletion and the timed edit to the same root and needs the source's particles.
- `--cases` selects edit cases (all five by default; the source is always built);
  `--skip-existing` keeps finished cases. `--keep-intermediates` keeps the source particles so it
  can be re-rendered or continued without re-simulating.
- `--gpu <index>` uses a chosen GPU. `PCVE_THREADS` sets Blender threads (default 8);
  `NUMBA_NUM_THREADS` caps the six surface workers.
- The render chain of one run is `tools/pipeline_bowling_ball_pool_drop.sh <run dir> <video.mp4>`:
  anisotropic water surface plus spray, mist and foam (`physics/splash_bowling_ball_pool_drop.py`),
  sun visibility (`appearance/sun_visibility_bowling_ball_pool_drop.py`, in Blender), caustics
  traced through the simulated surface (`physics/caustics_bowling_ball_pool_drop.py`), then
  Cycles and H.264.

## Outputs

- `renders/bowling_ball_pool_drop/settle/`: the settled water.
- `renders/bowling_ball_pool_drop/cases/<case>/video.mp4`: the rendered video.
- `renders/bowling_ball_pool_drop/cases/<case>/prompts.json`: edit DSL and prompts.
- `renders/bowling_ball_pool_drop/cases/<case>/simulation_report.json`: simulation settings and checks.
- `renders/bowling_ball_pool_drop/suite_manifest.json`: all cases and their status.
- Without `--out-root` the builder writes to `renders/bowling_ball_pool_drop/suite_build/`.
- The published suite is `renders/pcve_suites/pcve_bowling_ball_pool_drop_suite/`; the builder
  does not write there.

## Code layout

- `build_pcve_bowling_ball_pool_drop.py`: builds the source and the edits, checks videos (entry point).
- `simulate_bowling_ball_pool_drop.py`: Genesis simulation, modes `settle` and `run` (entry point).
- `render_bowling_ball_pool_drop.py`: Blender rendering (entry point).
- `physics/physics_bowling_ball_pool_drop.py`: baseline physics.
- `physics/optics_bowling_ball_pool_drop.py`: pool optics.
- `physics/splash_bowling_ball_pool_drop.py`: splash and water-surface reconstruction.
- `physics/caustics_bowling_ball_pool_drop.py`: sunlight caustics on the tank.
- `appearance/scene_bowling_ball_pool_drop.py`: environment, ball, lights and asset checks.
- `appearance/sun_visibility_bowling_ball_pool_drop.py`: sun visibility map (runs in Blender).
- `tools/pipeline_bowling_ball_pool_drop.sh`: render chain of one run.
- `tools/run_on_idle_gpu.sh`: idle-GPU launcher, also used by `apple_drop_kitchen_basin`.
- `edit_vocab.py`: edit DSL vocabulary.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases, video hashes of the published suite, render and simulation settings.

## Limitations

- The pool interior is light-baked, so it is shown as emission; the tank below the coping is a
  rendered tiled tank.
- Surface tension is neglected.
- The source checkpoint stores water velocity as float16, so the timed continuation cannot
  recover precision lost there.
