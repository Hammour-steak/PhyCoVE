# elastic_fluid_duck

A large rubber duck drops into an outdoor pool, deforms under the impact and the water pressure,
splashes and returns to an upright floating pose. This is an elastic–fluid scene with two-way
coupling between the elastic duck and the water. The source video is 4 s at 24 fps (96 frames),
1280×720.

## Scene

- Duck: a 0.6 m elastic body, density 200 kg/m³ (about 10 kg), Young's modulus 60 kPa, Poisson
  ratio 0.35, released above the pool centre (reference point at z = 1.1 m) at 2 m/s downward.
- Water: 1000 kg/m³, dynamic viscosity 1 mPa·s, in the outdoor pool.
- Rendering: every case uses the same look (`render_elastic_fluid_duck.LOOK`); cases with
  water add splash detail, spray, mist and foam, sun occluders, pool caustics and wet surfaces
  computed from the saved simulation.

## Physics

- Solver: Genesis 1.4.3 with a neo-Hookean MPM duck (64 grid cells per metre, 12.5 mm particles)
  and DFSPH water (34.7 mm particles).
- Time step: 10 steps of 1/240 s per video frame with 40 substeps each; frame i is the state at
  t = (i − 1)/24 s.
- Coupling: the duck acts on the water as a moving pressure boundary; pressure impulses are
  scattered back to the duck's material points through the transpose of the MPM transfer
  weights, so the coupling works both ways.
- Settings: the asset `assets/elastic_fluid/elastic_fluid_duck/scene_spec.json` holds the physics
  and numerical settings; each case directory records its own copy (`mpm_sph_experiment.json`)
  with the material assumptions, numerical settings and coupling checks.
- Water deletion: the edit uses refined MPM quadrature and explicit floor contact, so the duck
  does not fracture numerically on the empty pool floor.
- Timed edit and source: the published source is simulated together with the timed density edit.
  The simulator copies the complete solver state (every MPM and SPH field, Python-side counters
  and diagnostics) at frame 73 before the density switch, runs the unedited source to the end,
  restores the copy bit for bit and runs the edit on, so frames 1–73 are the same state in both
  cases. The other five edits are separate runs.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | the duck enters the pool, splashes and floats upright again |
| `edit_heavy_duck` | `SET duck.mass TIMES 5.5` | heavier duck with the same shape and volume; it sinks |
| `edit_viscous_liquid` | `SET water.viscosity TIMES 400000` | much more viscous liquid with the same density and look; splash and waves are suppressed |
| `edit_delete_duck` | `DELETE duck` | no duck from frame 1 (no MPM body, no pressure boundary) |
| `edit_delete_water_contact_fixed` | `DELETE water` | no water; the same elastic duck falls onto the empty pool floor |
| `edit_low_density_liquid_slow_sink_185` | `SET water.density TIMES 0.185` | liquid density 185 kg/m³; the duck sinks slowly with a smaller splash |
| `edit_low_density_liquid_after_float_185_f73` | `SET water.density TIMES 0.185 AT FRAME 73` | frames 1–72 as the source; at 3.00 s, once the duck floats steadily, the density drops to 185 kg/m³, the live state continues without reset and the duck descends |

The builder names the source `elastic_fluid_duck_baseline`; the published suite stores it as
`source`. The builder writes each edit's bilingual prompts with `pcve_edit_dsl.make_prompts` and
its own vocabulary (`vocabulary()` in the builder); the source prompts exist only in the
published suite.

## Assets

- `elastic_fluid/elastic_fluid_duck` (derived): the pool scene, duck geometry, initial water
  state, physics settings (`scene_spec.json`) and a selected source take
  (`selected_base_video.mp4`). It has no public download.

```bash
python3 scripts/download_assets.py --scene elastic_fluid_duck          # download and check sha256
python3 scripts/download_assets.py --scene elastic_fluid_duck --check  # check only
```

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`).
- An NVIDIA GPU with a driver for CUDA 12.3 or newer for Genesis, and for Cycles.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root. The three steps after the dry run prepare all seven case
directories (the source is simulated, not copied), simulate the timed edit and, from its
frame-73 state, the source in one GPU run, then simulate the other edits and run the remaining
stages of every case.

```bash
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/elastic_fluid_duck/build_pcve_elastic_fluid_duck.py \
  --out-root renders/elastic_fluid_duck --dry-run
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/elastic_fluid_duck/build_pcve_elastic_fluid_duck.py \
  --out-root renders/elastic_fluid_duck --stage prepare --resimulate-base --keep-intermediates
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/elastic_fluid_duck/simulate_elastic_fluid_duck.py \
  --case-dir renders/elastic_fluid_duck/cases/edit_low_density_liquid_after_float_185_f73 --stage simulate \
  --source-branch-case renders/elastic_fluid_duck/cases/elastic_fluid_duck_baseline
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/elastic_fluid_duck/build_pcve_elastic_fluid_duck.py \
  --out-root renders/elastic_fluid_duck --resimulate-base --keep-intermediates
```

- Per case the builder runs `simulate` (GPU), `surface` (water surface, duck skinning and the
  scene's numerical audit), for cases with water the CPU look inputs `splash`, `occluders`,
  `caustics` and `wetness`, then `render` (GPU, which also checks the video: 1280×720, 24 fps, 96
  decodable frames); finally it writes `suite_manifest.json`. A case whose simulation report
  already exists continues with `surface`; finished videos are refused unless `--skip-existing`
  keeps them. `run_pipeline()` in the builder lists the command of each stage; each stage writes
  `<case>/<stage>.log`.
- It starts a stage on any GPU without processes and memory use (`nvidia-smi`), up to `--jobs`
  (default 6) stages at once; `--max-wall-seconds` limits one simulation (default 7200 s).
- `--cases` selects edits, `--edits-only` skips the source, `--stage finish` collects explicit
  `--cases` whose simulation is complete.
- `--case-storage-root DIR` keeps new case directories on another volume and links them from the
  output root (a case with `--keep-intermediates` holds about 1.5 GB of particle caches).
- Without `--resimulate-base` the builder does not simulate the source: it copies the selected
  take from the asset (`selected_base_video.mp4`), which has no particle cache and is not the
  published source.

## Outputs

- `renders/elastic_fluid_duck/cases/<case>/video.mp4` and, for an edit, its bilingual
  `prompts.json`.
- `renders/elastic_fluid_duck/suite_manifest.json`: every case's physics, numerical settings,
  coupling checks and video hash.
- With `--keep-intermediates` each case also keeps its configuration, the particle caches and
  reports under `runs/source/`, the surfaces, the rendered frames and the stage logs; without it
  the builder moves the configuration and checks of each case into `suite_manifest.json`.
- Without `--out-root` the builder writes to `renders/elastic_fluid_duck/suite_build/pcve_elastic_fluid_duck_suite/`.
- The published suite is `renders/pcve_suites/pcve_elastic_fluid_duck_suite/`; the builder does
  not write there.

## Code layout

- `build_pcve_elastic_fluid_duck.py`: case plans and prompts, the stage scheduler and the suite manifest (entry point).
- `simulate_elastic_fluid_duck.py`: coupled MPM/DFSPH solver with the pressure-boundary operator, the same-run branch, the numerical audit, the water-surface reconstruction and duck skinning (entry point).
- `render_elastic_fluid_duck.py`: rendering, sun occluders and video checks of a case (entry point).
- `physics/splash_elastic_fluid_duck.py`: splash detail computed from the saved simulation (render-side, CPU).
- `physics/optics_elastic_fluid_duck.py`, `physics/caustics_elastic_fluid_duck.py`: sunlight optics and pool caustics (render-side, CPU).
- `physics/wetness_elastic_fluid_duck.py`: wet surfaces (render-side, CPU).
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases and published videos.

Other scenes reuse these files: `bathroom_sink_duck_neospace` loads `simulate_elastic_fluid_duck.py`
for the pressure-boundary operator, and `apple_drop_kitchen_basin`, `bowling_ball_pool_drop` and
`toy_boat_pool_glide` import the splash module (and `bowling_ball_pool_drop` the caustics and
optics modules) from `physics/`, so a change here can change those scenes too.

## Limitations

- The duck is a homogeneous elastic solid, not a hollow rubber shell with air inside.
- Splash detail, caustics and wetness are render-side stages computed from the simulation; they
  do not feed back into it.
- Genesis runs on the GPU and its float atomics are not bit-reproducible: two runs of one case
  differ slightly, which is why the source and the timed edit come from one run.
