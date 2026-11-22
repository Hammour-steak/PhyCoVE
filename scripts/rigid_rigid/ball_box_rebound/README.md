# ball_box_rebound

A rigid–rigid scene in PhyCoVE. In a daylit children's playroom, an 18 cm star-patterned hard toy
ball rolls at about 1.56 m/s into a white toy chest at about 45°, rebounds, and makes a
near-central head-on impact with a 22 cm football; both balls then slow down. PyBullet solves
every contact and Blender replays the solved poses. The source video is 4 s, 24 fps, 96 frames,
1280×720.

## Scene

- **Units and axes:** SI, Z up, gravity −9.81 m/s².
- **Star ball (B01):** sphere, radius 0.09 m, 0.32 kg, rigid thin-shell inertia (factor 2/3).
  Starts at (−0.95, −0.75, 0.09) m with velocity (1.10, 1.10, 0) m/s and the matching no-slip
  spin (−12.22, 12.22, 0) rad/s.
- **Toy chest (C01):** collision box 0.72 × 0.44 × 0.40 m, 8 kg (ballasted), centred at
  (−0.10, 0.45, 0.20) m. The rendered lid has a 2 mm decorative overhang.
- **Football (B02):** sphere, radius 0.11 m, 0.43 kg, thin-shell inertia, at rest at
  (0.565, −0.073, 0.11) m. It is a rigid approximation of an inflated ball.
- **Floor (F01):** fixed 8 × 8 × 0.12 m box with its top face at z = 0.
- **Camera:** fixed, location (1.45, −3.80, 1.45) m, target (−0.32, 0.27, 0.25) m, 48 mm lens on a
  36 mm sensor, f/5.6 focused at 4.35 m. Edits keep this camera; edited bodies may leave the frame.
- **Room:** 6.5 × 8.75 × 2.8 m playroom (appearance preset `documentary_playroom`) with directional
  window daylight, measured child-scale furniture, photographed wood, nonmetallic paint, linen
  curtains clear of the sill, a sewn cushion and a scale toy car on the cabinet.
- **Star ball finish:** 14 evenly spaced five-pointed stars in two sizes, cream (sRGB
  0.95/0.91/0.81) on coral-red vinyl (0.80/0.30/0.31), computed per texel into a 2048×1024
  equirectangular mask on a spherical UV layer; 0.22 satin coat, roughness 0.30–0.40, slightly
  matte ink with light rub-off and millimetre orange-peel relief, so the solved spin is visible.
- **Floor finish:** an oak plank scan mapped in world metres (1.7 m tile, saturation 0.88, value
  1.12, roughness 0.24–0.52, coat 0.10). The floor's contact parameters are those of F01, not of
  the look.
- **Text-free props:** books have plain bookcloth covers, the toy car's number plate is blank
  paint and its badge plain metal, and the one crayon-wrapper image that carries a word is not
  connected in its material.
- **Football finish:** the model's own scuff map darkens the white panels by at most 20 %.
- **Render:** Cycles, 1280×720, 256 samples, adaptive threshold 0.005, OIDN denoising, AgX,
  0.25-frame shutter, H.264 CRF 17 (yuv420p).

## Physics

- PyBullet, unconstrained six-DOF bodies, time step 1/1920 s (80 substeps per frame), 100 solver
  iterations, split impulse, contact ERP 0.08, restitution velocity threshold 0.04 m/s.
  Trajectories are stored at 480 Hz; frame i samples t = (i−1)/24 s.
- Contact parameters: star ball restitution 0.90, lateral friction 0.32, rolling 0.006,
  spinning 0.0002; chest restitution 0.95, friction 0.18; football restitution 0.62, friction
  0.50, rolling 0.002; floor restitution 0.04, friction 0.55.
- Bullet multiplies the restitutions of a contact pair: source ball/chest 0.855 and ball/football
  0.558; `edit_high_restitution` gives 0.950 and 0.620, `edit_low_restitution` 0.4275 and 0.279.
- The two launch-speed edits scale the initial angular velocity by the same factor, so the ball
  still rolls without slipping; their scalar speeds are about 1.8668 and 1.2445 m/s against
  1.5556 m/s in the source. No later force, velocity maintenance, trajectory constraint or pose
  correction is applied.
- Friction edits change only the selected body's lateral friction; rolling and spinning friction
  stay unchanged.
- Initial deletion: B02 is never created in the physics world and its visual hierarchy is removed
  before the scene is prepared. Timed deletion: the unchanged world integrates to solver step 3840
  (t = 2.000 s); B02 is removed before the sample at that time and every remaining body keeps its
  position, orientation and velocities. The event records the states before and after and the
  energy removed with B02.
- All football render children carry constant visibility keys (present at frame 48, absent at
  frame 49) for render and viewport, so shadows and reflections disappear too. Ground truth marks
  a deleted body `present: false`; a body that is outside the frame but still simulated keeps
  `present: true` with `visible_in_frame: false`.

## Validation

- `physics/validate_ball_box_rebound.py` checks the source: the 45° oblique approach, contact
  order (chest, then football), clear free travel between contacts, the oblique rebound toward the
  right foreground, a near-central head-on second contact without visible heading change, chest
  stability (drift < 4 mm), masses and inertia, the initial no-slip roll, no interpenetration
  (gap > −1.5 mm), energy dissipation and the absence of prescribed motion or forcing.
- `physics/validate_edits.py` checks each edit: only the declared change is present, appearance,
  camera, render and solver quality are unchanged, mass/inertia/friction readback, time sampling,
  finite states, contact gaps, energy and the presence schedule; the timed deletion matches the
  source before removal and leaves the surviving states unchanged across it.
- PyBullet's `getDynamicsInfo` does not return restitution for these bodies, so the readback is
  recorded as null and the restitution edits are checked through the measured normal impact
  response against the configured pair restitution.
- Blender preparation checks every present pose, child visibility, mesh bounds and contact
  visibility; the source keeps a 2.5 % framing margin and edits record partial or full exits.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Star ball 0.32 kg at (1.10, 1.10, 0) m/s, restitution 0.90, friction 0.32 |
| `edit_high_restitution` | `SET B01.restitution TO 1` | Star-ball restitution 0.90 → 1.00 |
| `edit_low_restitution` | `SET B01.restitution TIMES 0.5` | Star-ball restitution 0.90 → 0.45 |
| `edit_fast_initial_velocity` | `SET B01.initial_velocity TIMES 1.2` | Velocity (1.10, 1.10, 0) → (1.32, 1.32, 0) m/s, spin scaled |
| `edit_slow_initial_velocity` | `SET B01.initial_velocity TIMES 0.8` | Velocity (1.10, 1.10, 0) → (0.88, 0.88, 0) m/s, spin scaled |
| `edit_high_ball_friction` | `SET B01.lateral_friction TIMES 2.5` | Star-ball lateral friction 0.32 → 0.80 |
| `edit_high_football_friction` | `SET B02.lateral_friction TIMES 2` | Football lateral friction 0.50 → 1.00 |
| `edit_remove_football` | `DELETE B02` | Football absent from physics and rendering from frame 1 |
| `edit_remove_football_at_2s` | `DELETE B02 AT FRAME 49` | Football removed from frame 49 (t = 2.000 s) in the running world |

`edit_vocab.py` declares the statements; the builder derives each edit's prompts with
`pcve_edit_dsl.make_prompts` and writes the source prompts from `build_pcve_ball_box_rebound.py`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `sketchfab/hayley_toy_box` | manual, derived | White toy chest (UVs, colours) and the star-ball mesh |
| `blenderkit/stitched_soccer_ball` | manual, derived | Football model and scuff map |
| `blenderkit/vintage_fiat_500` | manual, derived | Scale toy car on the cabinet |
| `blenderkit/rally_toy_car` | manual, derived | Toy car in the play area |
| `blenderkit/cosmic_kids_bedroom` | manual, derived | Curtains and a plush toy |
| `blenderkit/cozy_living_room` | manual, derived | Floor cushion and textile props |
| `blenderkit/stuffed_penguin` | manual, derived | Plush toy |
| `blenderkit/kids_table_chairs` | manual, derived | Child-scale furniture |
| `blenderkit/noos_kids_table` | manual, derived | Wooden play table and chairs |
| `blenderkit/playroom` | manual, derived | Pinned drawing and room props |
| `blenderkit/small_storage_cabinet` | manual, derived | Low storage cabinet |
| `blenderkit/childrens_bookshelf` | manual, derived | Child bookcase |
| `blenderkit/wicker_basket` | manual, derived | Woven toy basket |
| `blenderkit/woven_rug` | manual, derived | Bound rug |
| `blenderkit/wood_train_set` | manual, derived | Wooden toy train |
| `blenderkit/rocking_horse` | manual, derived | Wooden rocking horse |
| `blenderkit/plastic_container` | manual, derived | Listed in `asset_manifest.json` |
| `blenderkit/dovetail_toy_chest` | manual, derived | Listed in `asset_manifest.json` |
| `polyhaven/wood_floor` | url, manual, derived | Oak plank floor scan |
| `polyhaven/wood_floor_worn` | url | Listed in `asset_manifest.json` |
| `scenes/ball_box_rebound/material_textures/plywood` | url | Plywood finishes |
| `scenes/ball_box_rebound/material_textures/rough_linen` | url | Canvas, linen and rug textiles |
| `scenes/ball_box_rebound/room_surfaces/linoleum_brown` | url | Floor layer under the oak finish |
| `scenes/ball_box_rebound/room_surfaces/white_plaster_02` | url | Wall paint |
| `scenes/ball_box_rebound/room_surfaces/kloofendal_overcast_puresky` | url | Sky environment |
| `scenes/ball_box_rebound/window_sky/kloofendal_48d_partly_cloudy_puresky` | url | Window sky environment |
| `scenes/ball_box_rebound` | derived | Collision meshes and a download record |

```bash
python3 scripts/download_assets.py --scene ball_box_rebound
python3 scripts/download_assets.py --scene ball_box_rebound --check
```

Manual files need a provider account; `download_assets.py` prints the page and file name to save.
`tools/download_blenderkit_assets.py` fetches a free asset through the provider's public API
(`--base-id`, `--name`, `--asset-dir`). `asset_manifest.json` records sources, licenses and
versions.

## Requirements

- Python environment `.venv-domino/` at the repository root (`numpy>=1.26,<2`,
  `pybullet==3.2.7`, see `requirements.txt`).
- Blender 4.3.2 (`tools/blender-4.3.2-linux-x64/blender`; otherwise `$BLENDER`, `blender` on
  `PATH` or `~/.local/opt/blender-*`).
- Physics runs on a CPU. Rendering uses `--device cpu` by default; `gpu` and `metal` are
  accepted. `ffmpeg` is needed for encoding.

## Commands

Run from the repository root. Each new run needs a fresh output root.

```bash
.venv-domino/bin/python scripts/rigid_rigid/ball_box_rebound/build_pcve_ball_box_rebound.py --list-cases

# physics for all nine cases (validators run for each case)
.venv-domino/bin/python scripts/rigid_rigid/ball_box_rebound/build_pcve_ball_box_rebound.py \
  --out-root renders/ball_box_rebound/run --stage simulate

# build and save each case's packed .blend, then render and verify the videos
.venv-domino/bin/python scripts/rigid_rigid/ball_box_rebound/build_pcve_ball_box_rebound.py \
  --out-root renders/ball_box_rebound/run --stage prepare --device cpu --threads-native 8 \
  --blender tools/blender-4.3.2-linux-x64/blender --skip-existing
.venv-domino/bin/python scripts/rigid_rigid/ball_box_rebound/build_pcve_ball_box_rebound.py \
  --out-root renders/ball_box_rebound/run --stage render --device cpu \
  --blender tools/blender-4.3.2-linux-x64/blender --skip-existing
.venv-domino/bin/python scripts/rigid_rigid/ball_box_rebound/build_pcve_ball_box_rebound.py \
  --out-root renders/ball_box_rebound/run --stage verify

# selected stills of one case from its physics cache
tools/blender-4.3.2-linux-x64/blender --factory-startup -b --python-exit-code 1 \
  --python scripts/rigid_rigid/ball_box_rebound/render_ball_box_rebound.py -- \
  --physics-json renders/ball_box_rebound/run/cases/edit_remove_football_at_2s/physics_transforms.json \
  --out-dir renders/ball_box_rebound/run/cases/edit_remove_football_at_2s \
  --mode frames --keyframes 48 49 --device cpu

# all 96 frames of a prepared case with a pool of CPU workers, then encode and verify
.venv-domino/bin/python scripts/rigid_rigid/ball_box_rebound/tools/render_parallel_cpu.py \
  --out-dir renders/ball_box_rebound/run/cases/source --blender tools/blender-4.3.2-linux-x64/blender

# one case without the builder
.venv-domino/bin/python scripts/rigid_rigid/ball_box_rebound/simulate_ball_box_rebound.py \
  --out renders/ball_box_rebound/single/physics_transforms.json --case-id edit_low_restitution
```

Stages are `simulate`, `prepare`, `preview` (selected frames), `render`, `verify` and `all`.
`--cases` selects a subset; the source is always included. `--reuse-physics-json` replays only a
source cache with identical physical inputs, numerical quality and timing; edits are still solved.
`tools/render_frozen_frames.py` renders a disjoint frame range from a prepared project (run inside
Blender with the case's `.blend`, `--device cpu|optix|cuda`, one device per case). Both frame
renderers refuse a project whose configuration differs from the case settings and turn off
persistent data while motion blur is on.

## Outputs

Each case folder `<out-root>/cases/<case>/` receives `settings.json`, `physics_transforms.json`,
`trajectory.csv`, `contacts.json`, `interventions.json`, `physics_validation.json` and
`prompts.json`; edits also get `scenario_overrides.json` and `configuration_diff.json`. Rendering
adds the packed `ball_box_rebound.blend`, `video.mp4`, `ground_truth_transforms.json`,
`scenario_metadata.json` and `video_validation.json`. The root holds `suite_manifest.json` and
`implementation_manifest.json`. The published suite is
`renders/pcve_suites/pcve_ball_box_rebound_suite/`; do not use it as an output root.

## Code layout

- `build_pcve_ball_box_rebound.py`: suite builder with stages, source prompts and manifest.
- `simulate_ball_box_rebound.py`: PyBullet solve of one case, CSV export.
- `render_ball_box_rebound.py`: Blender preparation, frame and animation rendering of one case.
- `scene_config.py`: physics, simulation quality, appearance and render configuration.
- `edit_vocab.py`: the eight edit statements and their DSL vocabulary.
- `physics/validate_ball_box_rebound.py`: source acceptance checks.
- `physics/validate_edits.py`: edit acceptance checks.
- `appearance/look_ball_box_rebound.py`: playroom, toys, lighting and finishes, built in layers;
  helpers suffixed with a layer name are the lower layers the final `room()`, `toys()` and
  `lighting()` build on.
- `asset_manifest.json`: asset sources, licenses and versions.
- `tools/render_frozen_frames.py`, `tools/render_parallel_cpu.py`: frame-range and pooled CPU
  rendering of prepared projects.
- `tools/download_blenderkit_assets.py`: provider API download of free assets.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry-point description, scene
  manifest and Python requirements.

## Limitations

- The football is a rigid sphere; shell deformation is not solved.
- The chest is a box collider; its rendered lid overhangs the collider by 2 mm.
- Edited bodies leave the fixed view: the star ball fully exits from frame 72 in
  `edit_low_restitution` and from frame 75 in `edit_remove_football`, and the football is partly
  cut by the frame edge late in `edit_fast_initial_velocity`.
- Rendering with persistent data and motion blur together drops resting objects in Blender 4.3,
  so persistent data is off whenever motion blur is on.
