# toy_boat_pool_glide

A 20 cm toy tug is pushed across a round three-ring inflatable kiddie pool in a sunlit back
garden and let go at 0.88 m/s. It glides 0.84 m, raising a bow wave and a wake, and slows almost
to rest without reaching the far wall. This is a rigid–fluid scene with two-way coupling: draft,
heave, pitch, drag, the bow wave and the wake come from one simulation. The source video is 4 s
at 24 fps (96 frames), 1280×720.

## Scene

- Pool: the inflatable pool model scaled to 1.80 m outer diameter; inner floor at z = 0.150 m,
  still water at z = 0.334 m (18.4 cm deep).
- Boat: mass 0.718 kg (the mass that displaces a 52 mm draft); released at (−0.428, −0.099) m
  with velocity (0.876, 0.125) m/s; rests at 31–38 mm draft; ends at (0.413, 0.028) m, 0.179 m
  from the wall at its closest.
- Water: 998 kg/m³, kinematic viscosity 1.0e-6 m²/s.
- Garden: lawn, wooden fence, a tree, a hose and the `sunny_rose_garden` HDRI.
- Camera `kneeling_rim`: 28 mm lens at (0.345, −1.95, 1.08) m looking at (0, 0.0825, 0.2775) m,
  f/4.
- Rendering: Cycles, 64 samples.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 5 mm particles (3.11 M), surface
  tension off; 16 steps × 4 substeps per frame.
- Coupling: the boat is a free rigid body coupled two-way with the water through Genesis
  `rigid_sph` with this scene's pressure-force patch.
- Pool walls: the water is held by the domain floor and a vertical cylinder of radius 0.723 m
  (the rings' inner radius at the waterline) imposed in the advection step; a ring of 48 fixed
  boxes gives the boat a wall to bump. Clamping to the rings' undulating profile pumps energy
  into the water and blows up within a frame.
- Boat collider: the convex hull of the lower 40% of the ship (59 mm). A hidden 8-frame push
  ramps the horizontal velocity to the set speed (heave, pitch and roll free) and releases the
  boat at frame 1.
- Start: the water first settles around the boat held at its floating pose (`settle`).
- Sinking edits keep the lower-hull collider (a ballasted rigid hull; water filling cabins is
  not simulated).
- Timed edit: the new mass and inertia are applied to the live body (`RigidEntity.set_mass`),
  keeping pose and velocity. The builder passes `--resume-from <accepted source run>
  --resume-frame 24`, so the run copies the source's frames 1–23, restores its saved frame-24
  state (water positions bit for bit; water velocities as saved, in float16; boat pose and
  velocity) and applies the mass there. `resume_handoff.json` in the run records the handoff
  errors.
- Viscous edit: a compound, reduced-order model, not a viscosity-only counterfactual. Besides
  viscosity 0.003514 m²/s it uses a stationary-medium drag `a = −γ v` on the water with
  γ = 6 s⁻¹ (`--fluid-drag-rate 6`, recorded in the case metadata), no-slip pool walls,
  hydrostatic hull pressure, an equivalent-sphere horizontal drag on the boat instead of
  horizontal two-way feedback (Schiller–Naumann), a single force integration, its own settled
  start, and 88 steps × 4 substeps per frame. Horizontal reaction pairs are therefore not
  momentum-conserving. `tools/run_viscous_glide.sh <out-dir>` runs this preset; the builder uses
  it too.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | glides 0.84 m with a bow wave and wake and slows almost to rest |
| `edit_heavy_boat` | `SET toy_tug.mass TIMES 3` | the ballasted boat sinks to the pool floor |
| `edit_slow_push` | `SET toy_tug.initial_velocity TIMES 0.5` | weaker wave, shorter glide |
| `edit_fast_push` | `SET toy_tug.initial_velocity TIMES 1.5` | stronger wave; reaches the opposite wall |
| `edit_light_water` | `SET water.density TIMES 0.25` | less buoyancy; the boat sinks |
| `edit_viscous_water` | `SET water.viscosity TIMES 3500` | much stronger resistance and a glide of about 9.3 cm |
| `edit_remove_boat` | `DELETE toy_tug` | no boat from frame 1 |
| `edit_heavy_boat_mid_glide` | `SET toy_tug.mass TIMES 3 AT FRAME 24` | frames 1–23 as the source; mass and inertia triple at 0.958 s during the glide, then the boat sinks |

The builder names the source `toy_boat_pool_glide_baseline`; the published suite stores it as
`source`.

## Assets

- `sketchfab/toy_ship` (manual, plus derived prepared colliders): the toy tug.
- `sketchfab/inflatable_swimming_pool` (manual, plus derived pool profiles): the pool.
- `blenderkit/summer_garden`, `blenderkit/wood_board_cc0`, `blenderkit/garden_hose_spray_nozzle`
  (manual): garden, fence boards and hose.
- `polyhaven/sunny_rose_garden` (url, plus derived files): the HDRI.
- `polyhaven/residential_garden`, `polyhaven/leafy_grass` (url): background HDRI and lawn
  texture.
- `polyhaven_models/grass_bermuda_01`, `polyhaven_models/grass_medium_01`,
  `polyhaven_models/dandelion_01`, `polyhaven_models/potted_plant_01`,
  `polyhaven_models/potted_plant_02` (url): lawn and garden plants.
- `elastic_fluid/elastic_fluid_duck` (derived): files of the `elastic_fluid_duck` scene, listed
  because the splash stage loads that scene's splash module.

```bash
python3 scripts/download_assets.py --scene toy_boat_pool_glide          # download and check sha256
python3 scripts/download_assets.py --scene toy_boat_pool_glide --check  # check only
```

Manual files need a free BlenderKit or Sketchfab account; the script prints each asset page and
the file names to save. Derived files are made by this project and have no public download.
`tools/download_lawn_assets.py` fetches the Poly Haven garden assets.

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`).
- An NVIDIA GPU for Genesis and for Cycles. A case takes about 11 minutes of simulation on a
  shared RTX 4090, 13 minutes of surfaces and 10 minutes of rendering.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/toy_boat_pool_glide/build_pcve_toy_boat_pool_glide.py \
  --out-root renders/toy_boat_pool_glide/suite --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/toy_boat_pool_glide/build_pcve_toy_boat_pool_glide.py \
  --out-root renders/toy_boat_pool_glide/suite --keep-intermediates --parallel 2
bash scripts/rigid_fluid/toy_boat_pool_glide/tools/pipeline_toy_boat_pool_glide.sh renders/toy_boat_pool_glide/run_source
blender -b --python-exit-code 1 --python scripts/rigid_fluid/toy_boat_pool_glide/render_toy_boat_pool_glide.py -- \
  --run renders/toy_boat_pool_glide/run_source --out-dir renders/toy_boat_pool_glide/rerender --camera kneeling_rim
```

- The builder does not simulate the source again. It adopts the published source video
  (`renders/pcve_suites/pcve_toy_boat_pool_glide_suite/cases/source/video.mp4`, checked against
  the sha256 in `scene_manifest.json`) and the accepted source run (`--source-run`, default
  `renders/toy_boat_pool_glide/source/run`), and builds every edit. The timed edit continues that
  run's frame-24 state.
- `tools/pipeline_toy_boat_pool_glide.sh <out-dir> [simulate args]` runs one case: settle, run, a
  wall check that fails if the hull comes within 2 cm of the wall
  (`physics/check_wall_toy_boat_pool_glide.py`), the surface step over seven processes
  (`tools/run_splash_parallel.sh`), then rendering over the four least busy GPUs and H.264.
- `render_toy_boat_pool_glide.py` re-renders a finished simulation.
- `appearance/prepare_assets_toy_boat_pool_glide.py` (in Blender) rebuilds the boat collider and
  pool profile.

## Outputs

- `renders/toy_boat_pool_glide/suite/cases/<case>/`: `video.mp4`, prompts, particle cache (with
  `--keep-intermediates`), surfaces and `simulation_report.json`.
- `renders/toy_boat_pool_glide/suite/suite_manifest.json`: the measured sinking, glide and stop
  frames of every case.
- Without `--out-root` the builder writes to `renders/toy_boat_pool_glide/suite_build/`. The
  published suite is `renders/pcve_suites/pcve_toy_boat_pool_glide_suite/`; the builder only reads
  its source video.

## Code layout

- `build_pcve_toy_boat_pool_glide.py`: adopts the source and builds the edits (entry point).
- `simulate_toy_boat_pool_glide.py`: Genesis simulation, modes `settle` and `run` (entry point).
- `render_toy_boat_pool_glide.py`: Blender rendering (entry point).
- `physics/physics_toy_boat_pool_glide.py`: baseline physics.
- `physics/splash_toy_boat_pool_glide.py`: water surface, spray and foam.
- `physics/check_wall_toy_boat_pool_glide.py`: wall-distance check.
- `physics/viscous_hull_toy_boat.py`: reduced-order hull model of the viscous edit.
- `appearance/garden_environment_toy_boat.py`, `appearance/realism_environment_toy_boat.py`: garden environment and its detail layer.
- `appearance/prepare_assets_toy_boat_pool_glide.py`: boat collider and pool profile (runs in Blender).
- `tools/pipeline_toy_boat_pool_glide.sh`: one case end to end.
- `tools/run_splash_parallel.sh`: parallel surface step.
- `tools/run_viscous_glide.sh`: viscous edit preset.
- `tools/sweep_edits.sh`: runs all edits; `--reuse-sweep` lets the builder reuse its runs.
- `tools/download_lawn_assets.py`: Poly Haven garden downloads.
- `edit_vocab.py`: edit DSL vocabulary.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: supported cases, accepted source physics and the published suite with its video hashes.

## Limitations

- The coupler floats hulls high (a mass for a 20 mm draft rests at 14.8 mm); the boat is placed
  at the measured rest draft so it does not pop up on release.
- 0.72 kg is heavy for a plastic tug of this size; it is what a 20 × 11 cm hull needs to sit deep
  enough to show a waterline and push a visible wave.
- Waves of a few millimetres are below the 5 mm particle size, which is why the source runs at
  0.9 m/s.
- `edit_viscous_water` is a reduced-order hybrid; γ is chosen for the motion, not fitted to a real
  material.
