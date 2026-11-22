# cup_water_drop

A 72 mm ceramic mug holding 240 mL of water is released with its base 0.284 m above a wooden
kitchen table. It lands upright with a small hop; the water inside erupts into a crown and a
short central jet, falls back and settles, and a few small drops land on the table. This is a
rigid–fluid scene with two-way coupling between the free mug and the water. The source video is
4 s at 24 fps (96 frames), 1280×720.

## Scene

- Mug: the coffee-cup-set mug (`MUG.004`) scaled to 72 mm, a free rigid body of 0.32 kg released
  at rest with its centre at (0, 0, 0.320) m and a 12° yaw.
- Water: 240 mL, 998.2 kg/m³, kinematic viscosity 1.0e-6 m²/s, surface tension 0.072 N/m. It
  settles in the held mug to 19.7 mm above the cup frame's origin with a meniscus.
- Table and props: table top at z = 0; the table, plate and napkin are fixed colliders.
- Camera at (0.48, −0.74, 0.66) m aimed at (0, 0, 0.17) m, 45 mm lens
  (`physics/layout_cup_water_drop.py`).
- Rendering: Cycles, 64 samples with denoising, fixed seed, motion blur over 0.38 frame, AgX
  Medium High Contrast, exposure −1, no depth of field. Water: IOR 1.333, roughness 0.025, slight
  blue absorption.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 1 mm particles (300,348 for the
  water), Akinci surface tension calibrated so a free 6 mm drop oscillates at water's Rayleigh
  frequency; the ceramic counts as fully wetted.
- Time step: mug and water fall together exactly (analytic free fall) up to frame 6, then the
  coupled simulation runs frames 6–96 at 10 steps per frame of 64 substeps (1/240 s steps), which
  keeps the 2.4 m/s impact within the CFL limit of 1 mm particles.
- Mug: collides with the table through the convex hull of its body (handle excluded), friction
  0.42, contact time constant 2 ms. The ceramic's outer three lattice layers are ghost particles
  with their own pressure; every pressure impulse they give the water is applied to the mug in
  reverse (force and torque).
- Density solve: split, so new compression is removed through the velocities (with the impulses
  on the mug) and existing compression only through the positions; a density error never turns
  into kinetic energy. Tolerances: average density error 0.005%, divergence 0.02% per step.
- Gravity: Genesis 1.4.3's DFSPH applies gravity twice per substep; the patch in
  `physics/dfsph_cup_water_drop.py` removes the second call.
- Props have fluid friction 1, so landed drops stay where they land.
- Modes: `relax` settles the water in the held mug; `drop` releases it.

## Validation

The source lands 0.24 s after release at 2.4 m/s, rebounds at about 0.2 m/s and comes to rest;
about 0.05 mL of water ends up on the table. The manifest records each case's run checks
(density and divergence errors).

Rendering-only treatments (the simulation data is untouched): isolated particles are not meshed;
slowly moving particles are meshed at a ±6-frame mean so the still surface does not shimmer;
drops that land become thin films pinned where they landed; stretches where everything stays
within ±0.1 mm are drawn once from their mean state.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | mug 0.32 kg, 240 mL of water; lands, hops and settles, a few drops on the table |
| `edit_heavy_cup` | `SET cup.mass TIMES 2.5` | mug 0.32 → 0.80 kg; it hits harder and the water splashes up more violently |
| `edit_high_viscosity_water` | `SET water.viscosity TIMES 100` | 1.0e-6 → 1.0e-4 m²/s, like a light syrup; splashing is damped and no fine drops leave the mug |
| `edit_low_density_water` | `SET water.density TIMES 0.6` | 998.2 → 598.92 kg/m³; the splash erupts more sharply on impact |
| `edit_delete_water` | `DELETE water` | no water; the empty mug falls, bounces slightly and rests upright, the table stays dry |

The builder names the source `cup_water_drop_baseline`; the published suite stores it as
`source`. `edit_vocab.py` maps the DSL onto simulator flags.

## Assets

- `blenderkit/coffee_cup_set` (manual): the mug.
- `blenderkit/modern_living_kitchen` (manual): the kitchen room.
- `blenderkit/cutting_board`, `blenderkit/kitchen_towel`, `blenderkit/red_apples` (manual): table
  dressing.
- `polyhaven/wood_table` (url, plus one derived file): the table wood texture.
- `rigid_fluid/tilted_cup_environment` (url and derived): the shared table environment, also used
  by `tilted_cup_table_pour`.

```bash
python3 scripts/download_assets.py --scene cup_water_drop          # download and check sha256
python3 scripts/download_assets.py --scene cup_water_drop --check  # check only
```

Manual files need a free BlenderKit account; the script prints each asset page and the file
names to save. Derived files are made by this project and have no public download.

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`) and pysplashsurf.
- An NVIDIA GPU for Genesis and for Cycles. Simulation takes about 1 minute per frame on an
  RTX 3090.
- Blender 4.3.2 (`--blender`, or `$BLENDER`, else `blender` on `PATH`).
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root with an idle GPU.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/cup_water_drop/build_pcve_cup_water_drop.py \
  --out-root renders/cup_water_drop --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/cup_water_drop/build_pcve_cup_water_drop.py \
  --suite-root renders/cup_water_drop
```

- For each case the builder settles the water in the held mug, simulates the drop, reconstructs
  the water surface, renders and encodes; all five cases run by default (`--cases` selects some,
  by the builder names). It exports the mug geometry and the plate and napkin colliders when
  `geometry/` is incomplete.
- Every step resumes from what exists in `renders/cup_water_drop/runs/<case>/`, and rendering
  only renders missing frames. To redo a look change, delete `frames/` and `video.mp4` in that
  directory (and `surfaces/` and `runs/<case>/surface_log.json` if the surface step changed).

## Outputs

- `renders/cup_water_drop/cases/<case>/video.mp4`: the rendered video.
- `renders/cup_water_drop/cases/<case>/prompts.json`: bilingual prompts.
- `renders/cup_water_drop/runs/<case>/`: particle positions (float32) and velocities (float16),
  mug pose per frame, `sim_log.json`, `surfaces/` and frames.
- `renders/cup_water_drop/suite_manifest.json`: physics, numerical settings, run checks and video
  hash of every case.
- The published suite is `renders/pcve_suites/pcve_cup_water_drop_suite/`; the builder does not
  write there.

## Code layout

- `build_pcve_cup_water_drop.py`: full suite: geometry, relax, drop, surface, render, manifest (entry point).
- `simulate_cup_water_drop.py`: `relax` and `drop` simulation (entry point).
- `surface_cup_water_drop.py`: per-frame water surface and drop films.
- `render_cup_water_drop.py`: Blender rendering (entry point).
- `physics/dfsph_cup_water_drop.py`: Genesis DFSPH patches.
- `physics/coupling_cup_water_drop.py`: mug ghost-particle coupling and split density solve.
- `physics/cavity_cup_water_drop.py`: mug cavity profile and the plate and napkin colliders.
- `physics/layout_cup_water_drop.py`: metric layout of the table scene and camera, shared by the collider builders and the renderer.
- `physics/droplets_cup_water_drop.py`: volume-preserving geometry of small and landed drops for the surface step.
- `appearance/geometry_cup_water_drop.py`: exports the mug mesh (runs in Blender).
- `geometry/`: mug mesh, cavity profile, plate and napkin colliders, read by the simulator.
- `edit_vocab.py`: edit DSL vocabulary and simulator flag mapping.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases and video hashes of the published suite.

## Limitations

- At 1 mm a surface particle's Weber number in the splash is of order one; the small drops are
  particle-sized.
- The mug collides with the table through its convex hull without the handle.
