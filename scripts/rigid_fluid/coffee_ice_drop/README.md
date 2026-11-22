# coffee_ice_drop

A 16 mm ice cube is released 4 cm above the coffee in a ceramic mug in a loft restaurant. It
splashes a few drops onto the saucer, reaches the cup floor and floats back up to rest at the
surface. This is a rigid–fluid scene with two-way coupling between the rigid ice and the coffee.
The source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Ice: a 16 mm cube, 920 kg/m³, released at (0, −3 mm, 0.8907 m) in the cup frame with Blender
  XYZ Euler angles (0.35, −0.24, 0.5) rad. Wet-ice-on-glaze friction 0.05.
- Coffee: 1030 kg/m³, kinematic viscosity 1.45e-6 m²/s, filled to 0.845 m and settled to
  0.841 m (13 mm below the rim).
- Cup: the mug, saucer, spoon and coffee beans of the restaurant stage, exported to `geometry/`.
  The ice collides with a hidden copy of the cavity whose floor is 2 mm above the mug floor, which
  keeps liquid under the ice so it does not stick to the bottom.
- Camera 30° down along the stage's view, 58 mm lens, 0.50 m from the cup, aimed at
  z = 0.862 m.
- Rendering: Cycles, 128 samples (adaptive sampling off), 180° motion blur from the surface
  velocity, in the restaurant stage `.blend`.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 1 mm particles, CUDA backend,
  32-bit precision, fixed random seed; the ice is a Genesis rigid box.
- Time step: 0.4 s of settling with the ice held, then 96 frames at 24 fps, 10 steps per frame
  of 16 substeps each.
- Coupling: the liquid sees the ice through three layers of ghost particles just inside its
  surface (Akinci-style boundary); every pressure impulse on the liquid is applied with the
  opposite sign to the ice.
- Surface tension: cohesion γ = 2e-4. Surface friction 1 on the saucer, table, spoon and beans,
  so landed drops stay where they land.
- Tolerances: density error 0.005% and divergence error 0.01%; looser values leave the resting
  surface jittering at about 11 mm/s.
- Gravity: Genesis 1.4.3's DFSPH applies gravity twice per substep (the liquid falls at 2 g);
  `physics/dfsph_coffee_ice_drop.py` removes the second call (`--keep-double-gravity` keeps it).
- High-viscosity edit: explicit SPH viscosity would need dt ≈ 1e-8 s, so the viscous term is one
  monolithic preconditioned conjugate-gradient solve per step over the liquid velocities and the
  ice's six degrees of freedom; liquid and ice exchange viscous momentum exactly.

## Validation

The fluid force balances the floating ice's weight within 0.3%, and the ice floats 88% submerged
(89.3% in theory). The manifest records each case's run checks.

Rendering-only treatments (the simulation data is untouched): isolated particles are not meshed;
slowly moving particles are meshed at a ±6-frame mean so the still surface does not shimmer;
drops that land on the saucer or table become thin films pinned where they landed; stretches
where everything stays within ±0.1 mm are drawn once from their mean state.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | ice 920 kg/m³, coffee 1030 kg/m³ and 1.45e-6 m²/s; splashes about 0.35 mL onto the saucer, reaches the floor, floats at 0.836 m |
| `edit_low_density_coffee` | `SET coffee.density TIMES 0.625` | coffee 643.75 kg/m³; same splash, the ice stays on the cup floor |
| `edit_high_viscosity_coffee` | `SET coffee.viscosity TIMES 1000000` | coffee 1.45 m²/s (implicit viscosity); the ice is caught at the surface, no splash, sinks about 1 mm in 4 s |
| `edit_delete_ice` | `DELETE ice` | `--no-ice`; the coffee stays at rest |
| `edit_delete_coffee` | `DELETE coffee` | `--no-coffee`, no hidden floor gap; the ice falls onto the dry cup floor |

The builder names the source `coffee_ice_drop_baseline`; the published suite stores it as
`source`. `edit_vocab.py` maps the DSL onto simulator flags (`sim_args`). The source description
is `SOURCE["description"]` in the builder; the four prompts of each edit are
`pcve_edit_dsl.make_prompts(parse(edit_dsl, edit_vocab.VOCAB), edit_vocab.VOCAB)`.

## Assets

- `scenes/coffee_ice_drop` (derived): the loft restaurant stage `.blend` (about 700 MB) that the
  cup set is exported from and every frame is rendered in. It has no public download.
- `blenderkit/realistic_ice_cube` (manual): the ice cube model.

```bash
python3 scripts/download_assets.py --scene coffee_ice_drop          # download and check sha256
python3 scripts/download_assets.py --scene coffee_ice_drop --check  # check only
```

The exported cup geometry in `geometry/` is enough for the simulation; rendering needs the stage.

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`) and pysplashsurf for the surface step.
- An NVIDIA GPU for Genesis and for Cycles. Simulation takes about 2.6 s per frame on an
  RTX 3090, 23 s per frame with implicit viscosity.
- Blender 4.3.2 (`--blender`, or `$BLENDER`).
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/coffee_ice_drop/build_pcve_coffee_ice_drop.py \
  --out-root renders/coffee_ice_drop --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/coffee_ice_drop/build_pcve_coffee_ice_drop.py \
  --suite-root renders/coffee_ice_drop
```

- For each case the builder simulates, reconstructs the coffee surface, renders and encodes; all
  five cases run by default (`--cases` selects some, by the builder names).
- `--input-blend` is the restaurant stage (default
  `assets/scenes/coffee_ice_drop/loft_restaurant_stage.blend`); `--ice-asset` and `--geometry`
  point at the ice model and the exported cup geometry.
- Every step resumes from what exists in `runs/<case>/`, and rendering only renders missing
  frames. To redo a look change, delete `runs/<case>/frames` and `video.mp4` (and `surfaces/`
  and `runs/<case>/surface_log.json` if the surface step changed).

The steps of one case can also be run one at a time (edit flags such as `--no-ice` go to the
simulator):

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/coffee_ice_drop/simulate_coffee_ice_drop.py \
  --geom scripts/rigid_fluid/coffee_ice_drop/geometry --out renders/coffee_ice_drop/runs/source
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/coffee_ice_drop/surface_coffee_ice_drop.py \
  renders/coffee_ice_drop/runs/source
blender -b assets/scenes/coffee_ice_drop/loft_restaurant_stage.blend --python-exit-code 1 \
  --python scripts/rigid_fluid/coffee_ice_drop/render_coffee_ice_drop.py -- \
  renders/coffee_ice_drop/runs/source assets/blenderkit/realistic_ice_cube/realistic_ice_cube.blend \
  renders/coffee_ice_drop/runs/source/frames
```

`--help` after `--` lists the renderer's optional positional arguments (samples, frame list,
camera distance and target, blur, ice look).

## Outputs

- `renders/coffee_ice_drop/cases/<case>/video.mp4`: the rendered video.
- `renders/coffee_ice_drop/cases/<case>/prompts.json`: bilingual prompts (a description for the
  source, the instruction for an edit).
- `renders/coffee_ice_drop/runs/<case>/`: fp16 particle positions and velocities, ice poses,
  `sim_log.json`, `surfaces/` and frames.
- `renders/coffee_ice_drop/suite_manifest.json`: physics, numerical settings, run checks and
  video hash of every case.
- The published suite is `renders/pcve_suites/pcve_coffee_ice_drop_suite/`; the builder does not
  write there. It keeps the runs of the four cases with an ice cube in
  `inputs/02_ground_truth_resimulation/` (`sim_log.json` with the per-frame ice pose, the fp16
  coffee particles and the surface hold plan). Each case's `ground_truth_transforms.json`
  follows the cup and the ice pose that the renderer keys; the coffee is not tracked.

## Code layout

- `build_pcve_coffee_ice_drop.py`: full suite: geometry export, simulate, surface, render, manifest (entry point).
- `simulate_coffee_ice_drop.py`: coupled rigid/DFSPH simulation (entry point).
- `surface_coffee_ice_drop.py`: per-frame coffee surface and drop films.
- `render_coffee_ice_drop.py`: Blender rendering in the restaurant stage (entry point).
- `physics/dfsph_coffee_ice_drop.py`: Genesis DFSPH patches (single gravity, optional rigid-response variants).
- `physics/ice_coupling_coffee_ice_drop.py`: ice ghost-particle coupling and the implicit viscosity solve.
- `physics/cavity_coffee_ice_drop.py`: measures the cup cavity and builds the solid saucer collider.
- `appearance/geometry_coffee_ice_drop.py`: exports the cup set from the stage.
- `geometry/`: exported cup, saucer, spoon, beans and cavity profile, read by the simulator.
- `edit_vocab.py`: edit DSL vocabulary and simulator flag mapping.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases, configuration, data locations and published video hashes.

## Limitations

- 1 mm particles cannot resolve surface tension, so the splash breaks into particle-sized drops.
- In `edit_delete_coffee` the cup wall hides the ice on the cup floor from the 30° camera.
- Liquid meshed against the rising ice leaves a few small brown specks on it.
