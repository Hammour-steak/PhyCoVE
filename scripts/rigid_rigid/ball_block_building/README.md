# ball_block_building

A rigid–rigid scene in PhyCoVE. A wooden ball rolls without slipping across a workbench into a
two-block pile; the impact pushes the base block aside and the upper block loses its support and
falls onto the bench top. PyBullet solves every contact and Blender replays the solved poses. The
source video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- **Units and axes:** SI, Z up, gravity −9.81 m/s². The ball and blocks move along y = 0.
- **Workbench:** a fixed 2.65 × 1.25 × 0.09 m top whose upper face is at z = 0.72, on four
  0.30 × 0.05 m legs (`building_geometry.table_parts`). The rendered top and legs are drawn from
  the same boxes, so the surface the ball rolls on is the collision surface. A ground box with its
  top face at z = 0 lies under the bench.
- **Ball:** sphere, radius 0.06 m, mass 0.4 kg, released at (−0.60, 0, 0.7802) m, already rolling
  at 2.2 m/s along +X with the matching no-slip spin ω_y = v/r.
- **Blocks:** two separate free bodies, density 650 kg/m³. `block_00` (base) is 7 × 7 × 16 cm,
  standing upright at x = 0.35 m; `block_01` (top) is a 9 cm cube centred on it. There are no
  hidden supports, bonds or scripted collapse.
- **Camera:** location (2.35, −3.45, 1.72) m looking at (0.05, 0.45, 1.05) m, 48 mm lens, f/8
  depth of field focused on the base block.
- **Room:** a joinery workshop. Inner wall faces at x = −3.00 / 2.95 m and y = −3.95 / 1.30 m,
  2.75 m ceiling, concrete floor on z = 0, whitewashed brick walls. The back wall has a 4 × 4
  steel-framed window onto a farmland HDRI (camera rays only, rotated to the sun direction).
- **Light:** daylight only. A sun lamp at 24° elevation and 160° heading enters through an east
  window outside the right edge of the frame, so the whole run of the ball is sunlit; a physical
  sky is sampled through area-light portals in both windows.
- **Bench top:** laminated ash, a veneer scan sampled at a different place for every 4.5 cm strip,
  with glue lines, oil stains and worn roughness; an OSB shelf under the top holds a toolbox.
- **Ball and block finish:** oiled teak ball, cherry base block, walnut top block, 1.2 mm chamfers.
  The grain maps veneer scans by distance along the grain and distance from the pith, so long-grain
  faces show longitudinal grain and end faces show growth rings; the ball's poles are end grain.
  The ball and base block are graded from the scan's mean colour to oiled timber (teak about sRGB
  105/70/48, cherry about 130/88/72).
- **Props (not simulated):** on an OSB tool board on the back wall, a handsaw, claw hammer, hand
  drill, screwdrivers, dowels and a rack; in the back-left corner a wooden rack with spray cans, a
  cleaner tin, an oil can, a wooden box, a lubricant spray, a rusty can and a stack of hardwood
  offcuts; on the bench a vice at the front-left corner and a plane, pencil and tape measure at
  the back. glTF 1k models are placed by bounding-box anchors; rigged models are baked from their
  evaluated meshes.
- **Render:** Cycles, 32 samples by default, denoising, AgX Medium High Contrast, exposure −0.35,
  0.5-frame motion blur with persistent data off, Cycles seed 19.

## Physics

- PyBullet in DIRECT mode, time step 1/960 s (40 substeps per 24 fps frame), 120 solver
  iterations, deterministic overlapping pairs.
- Friction / restitution: ball 0.40 / 0.10 with rolling friction 0.0002, blocks 0.55 / 0.05 with
  linear and angular damping 0.01, bench 0.70 / 0, ground 0.6 / 0.
- The blocks settle for 0.8 s before the ball is created; the run fails if the pile drifts more
  than 5 mm or moves faster than 0.03 m/s during settling.
- Frame i is the solver state at t = (i−1)/24 s; nothing is resampled or retimed.
- The timed gravity edit changes the gravity magnitude inside the running world before the
  substeps that lead to its start frame; the direction stays −Z.

## Validation

- The builder requires the source case to hit the pile and to show a visible collapse: the base
  block slides more than 3 cm along +X and the top block drops more than 10 cm.
- Every case records first contact time, impacted blocks, settle drift, top-block drop and tilt,
  base-block slide, the number of blocks displaced by more than 3 cm and per-frame presence in
  `simulation_metrics.json`.
- The renderer checks that the Blender replay matches the solved poses to 1e-5, that every moving
  body's bounding sphere keeps at least 2 cm from every prop's bounding box in every frame
  (`check_clearance`), and that rays from the camera to each body's centre and top face are not
  blocked by props (`check_sightlines`). Results go to `render_validation.json` and to
  `scenario.room` in the ground truth.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Ball 0.4 kg at 2.2 m/s, blocks friction 0.55, gravity 9.81 m/s² |
| `edit_heavy_ball` | `SET ball.mass TIMES 2` | Ball mass 0.4 → 0.8 kg |
| `edit_fast_ball` | `SET ball.initial_velocity TIMES 1.5` | Ball speed 2.2 → 3.3 m/s (spin scaled to stay no-slip) |
| `edit_low_block_friction` | `SET blocks.friction TIMES 0.4` | Block friction 0.55 → 0.22 |
| `edit_delete_block_01` | `DELETE block_01` | Top block absent from simulation and rendering from frame 1 |
| `edit_stronger_gravity_timed` | `SET world.gravity TIMES 1.5 AT FRAME 12` | Gravity 9.81 → 14.715 m/s² from frame 12 (t = 0.458 s) |
| `edit_delete_ball` | `DELETE ball` | Wooden ball removed from frame 1 |

The builder calls the source case `ball_block_building_baseline`; the edit IDs are the same as
the published case names. `edit_vocab.py` declares the DSL statements and the builder writes the
prompts with `pcve_edit_dsl.make_prompts`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `polyhaven/ball_block_building` | url (one derived `assets/polyhaven/ball_block_building/sources.json`) | Veneer, brick, concrete and OSB scans, the farmland HDRI and the workshop prop models |

```bash
python3 scripts/download_assets.py --scene ball_block_building
python3 scripts/download_assets.py --scene ball_block_building --check
```

The scene reads no file from `assets/models`.

## Requirements

- Python environment `.venv-domino/` at the repository root with `pybullet==3.2.7`
  (`requirements.txt`).
- Blender 4.3.2 for rendering (`tools/blender-4.3.2-linux-x64/blender`, or `$BLENDER`, `blender`
  on `PATH`, `~/.local/opt/blender-*`).
- The physics needs only a CPU. Rendering runs on CPU or a CUDA GPU (`--device auto`).

## Commands

Run from the repository root.

```bash
# case list
.venv-domino/bin/python scripts/rigid_rigid/ball_block_building/build_pcve_ball_block_building.py --list-cases

# physics for all six cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/ball_block_building/build_pcve_ball_block_building.py \
  --out-root renders/ball_block_building/run --simulate-only

# physics and video for every case at the published resolution
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/ball_block_building/build_pcve_ball_block_building.py \
  --out-root renders/ball_block_building/run --resolution 1280 720 --samples 32 --mode animation \
  --blender tools/blender-4.3.2-linux-x64/blender

# one case without the builder
.venv-domino/bin/python scripts/rigid_rigid/ball_block_building/simulate_ball_block_building.py \
  --out renders/ball_block_building/single/physics_transforms.json
```

`--cases` selects a subset, `--mode preview` renders one still per case, `--skip-existing` reuses
cases whose fingerprint matches, `--dry-run` prints the commands and `--clean-stale-cases` removes
case folders that are not in the case list. `tools/render_queue.py` (workflow `batch_render`)
samples random ball masses and speeds on top of the same builder (`--count`, `--start-index`,
`--seed-base`).

## Outputs

Without `--out-root` the builder writes to
`renders/ball_block_building/suite_build/pcve_ball_block_building_suite/`. Each case folder
`cases/<case>/` receives `scenario_input.json`, `physics_transforms.json`,
`simulation_metrics.json`, `prompts.json`, and after rendering `video.mp4`, `preview.png`,
`ground_truth_transforms.json`, `scenario_metadata.json`, `render_validation.json` and the packed
`ball_block_building.blend`; edits also get `scenario_overrides.json`. The suite root holds
`suite_manifest.json`. The published suite is
`renders/pcve_suites/pcve_ball_block_building_suite/`; do not use it as an output root.

## Code layout

- `build_pcve_ball_block_building.py`: suite builder (source plus five edits, prompts, manifest).
- `simulate_ball_block_building.py`: PyBullet solve of one scenario.
- `render_ball_block_building.py`: Blender replay, checks and render of one case.
- `scene_config.py`: physics, camera and render defaults, override merge and validation.
- `edit_vocab.py`: edit DSL vocabulary and the case list.
- `physics/building_geometry.py`: bench and block boxes shared by physics and rendering.
- `scripts/pcve_windows_dll_paths.py` (shared): on Windows, adds the conda `Library/bin` to the DLL path before
  PyBullet loads.
- `appearance/look_ball_block_building.py`: room layout, daylight and wood looks.
- `appearance/workshop.py`: workshop room, props, clearance and sightline checks.
- `appearance/render_quality.py`: Cycles/EEVEE settings and colour management.
- `tools/render_queue.py`: random batch sampling of ball mass and speed.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry-point description, scene
  manifest and Python requirements.

## Limitations

- The props are visual only; they are kept clear of the moving bodies by the clearance check
  rather than by collision.
- Collision shapes are boxes and a sphere; the 1.2 mm chamfers are visual only.
- The builder's default render resolution is 960×540; pass `--resolution 1280 720` to match the
  published videos.
