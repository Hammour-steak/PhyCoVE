# ramp_car_ball_collision

An unpowered four-wheel toy car rolls from rest down a toy ramp with a short flat run-out, crosses a
wooden living-room floor and hits a 6 cm toy ball with its front bumper; the ball rolls away and the
car rolls on behind it. Rigid–rigid scene of PhyCoVE. Source video: 4 s, 24 fps, 96 frames,
1280×720.

## Scene

- Units and axes: SI, Z up, +X is the direction of travel.
- Ramp: free-standing toy ramp, 0.55 m long horizontally, 0.18 m wide, 0.12 m high at the top. An
  8 cm curve joins the slope to a 16 cm flat deck 3.2 mm above the floor, which ends in a 3.5 cm lip
  down to the floor (74.5 cm footprint). The collision shape follows the visible deck.
- Car: about 12.2 × 6 × 5.1 cm; 200 g body and four 12.5 g wheels (250 g total), wheelbase 76 mm,
  wheel radius 14 mm. The visible body is a copper diecast toy car whose four wheels sit on the
  solver axles with round wheel openings and 0.8 mm clearance.
- Ball: radius 3 cm, 30 g, starting at (0.445, 0, 0.03) m, 25 cm past the end of the ramp.
- Start: all bodies at rest with the four wheels on the ramp.
- Room: full-scale living room with a recessed double-glazed casement window, linen drapes, a sofa
  with two pillows, a wicker basket and a plush toy; beyond the open window a 3D courtyard with
  paving, planted containers, grasses and a limewashed boundary wall. Walls and ceiling use the
  `beige_wall_001` plaster scan (tiled at 3 m) on warm white paint of linear albedo 0.72; sofa and
  pillows use the `rough_linen` scan at a 0.271 m tile.
- Light: only the sky (`residential_garden` HDRI, strength 1.0) and a sun lamp (strength 3.0, 2°
  disc), both entering through the open casement; a Cycles light portal over the window opening
  (1.97 × 1.70 m); eight diffuse bounces; exposure +2.2 EV. The sun patch on the floor covers the
  ramp exit and the collision area.
- Camera: fixed at (1.95, −2.18, 0.65) looking at (0.68, 0.1, 0.26), 40.5 mm lens on a 36 mm
  sensor, depth of field focused at 2.6 m, f/6.3.
- Render: Cycles, 128 samples, OpenImageDenoise, AgX Medium High Contrast, 0.15-frame shutter,
  persistent data off.

## Physics

- Solver: PyBullet 3.2.7, dt = 1/15360 s (24 fps × 640 substeps), 120 solver iterations, contact
  ERP 0, split impulse on. Trajectories are sampled at 240 Hz; video frame i is the solver state at
  t = (i−1)/24.
- Car: the body is a free six-degree-of-freedom body; each wheel is a separate rigid body on a
  passive revolute axle (motor force 0, axle damping 2e-6 N·m·s). Tyre friction 0.85, rolling
  friction 0.0007, restitution 0.03; bumper restitution 0.8. The bumper collision proxy is 30 mm
  above the floor, ahead of the wheels, so the first car–ball contact is bumper against the middle
  of the ball.
- Ball: thin-shell inertia I = 2/3 m r², restitution 0.8, friction 0.45, rolling friction 0.003.
- Ramp and floor: lateral friction 0.65, restitution 0.12. Gravity −9.81 m/s².
- No motors, set velocities, path following or velocity resets; resistance comes only from Bullet's
  friction, rolling and spinning contact constraints and the axle damping.
- Bullet multiplies the restitution of the two bodies in a contact, so the low-restitution edit
  changes car–ball restitution 0.64 → 0.08 and ball–floor 0.096 → 0.012. Mass edits recompute the
  ball inertia with the same hollow-sphere formula.
- `edit_remove_car` builds neither the chassis nor its wheels. `edit_remove_car_at_2s` removes the
  whole articulated multibody with one `removeBody` at native tick 30720 (t = 2.0 s), without
  resetting any other state; frame 49 is the first frame without the car, and the renderer hides the
  complete car hierarchy, with its shadows and reflections, over the whole shutter interval of that
  frame.
- The configuration is `BASELINE` in `scene_config.py` (groups `physics`, `simulation_quality`,
  `appearance`, `render`); `CASES` holds the solver override of each edit.

## Measured motion

The car leaves the ramp at 0.99 s at 1.05 m/s and reaches the ball at 1.09 s in every case that has
both bodies.

| Case | Outcome |
| --- | --- |
| `source` | The ball rolls 1.09 m; the car carries on 0.96 m and stops at x = 1.31 m |
| `edit_heavy_ball` | The ball moves 8 cm; the car bounces back 4.7 cm and stops at x = 0.31 m |
| `edit_low_restitution` | The car pushes the ball through two more contacts; the ball travels 0.95 m |
| `edit_remove_ball` | No collision; the car rolls on to x = 1.66 m |
| `edit_light_ball` | The ball rolls 1.26 m; the car carries on 1.18 m and stops at x = 1.53 m |
| `edit_remove_car` | Nothing strikes the ball; it stays at rest |
| `edit_remove_car_at_2s` | Identical to the source before 2 s; the ball keeps rolling from its solver state |

In a 30–1200 g ball-mass sweep the car stops dead at about 400 g and bounces back clearly from
800 g. Halving the solver step moves the first impact by 0.46 ms, the ball's final position by
1.7 cm and the car's by 2.5 mm.

## Validation

- `physics/validate_ramp_car_ball_collision.py` runs after every solve and stops the build on
  failure; edits are simulated only after the source passes. It reads back the inputs the solver
  used (body inertia, tyre friction, restitution, each set and asserted per link), checks that all
  bodies start at rest without penetration, that the first car–ball contact is bumper against ball
  with all four wheels off the ramp, the expected outcome of each edit, and for the timed deletion
  that every sample before the deletion matches the source.
- The render stage of an edit requires a recorded visual review of the source video
  (`cases/source/case_acceptance.json`, written by `tools/record_visual_review.py` after
  `tools/audit_rendered_frames.py` and `tools/audit_saved_scene.py`; the review JSON sets
  `all_frames_reviewed`, `event_frames_reviewed` and `visual_accepted`).
- The verify stage checks every case video with `scripts/pcve_verify_video.py` (resolution, fps,
  frame count) and marks a case accepted when its review matches the current physics and video
  hashes.
- `tools/audit_rendered_frames.py` decodes every frame, checks that the ball is visible at its
  solved position and writes contact sheets; `tools/audit_saved_scene.py` (inside Blender) reopens
  the saved scene and compares every frame's poses, the camera, the render settings and texture
  packing.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Car rolls down the ramp and hits the ball |
| `edit_heavy_ball` | `SET ball.mass TO 0.8` | Ball mass 0.03 → 0.8 kg, inertia scaled with mass |
| `edit_low_restitution` | `SET ball.restitution TIMES 0.125` | Ball restitution 0.8 → 0.1 |
| `edit_remove_ball` | `DELETE ball` | Ball absent from frame 1 |
| `edit_light_ball` | `SET ball.mass TO 0.01` | Ball mass 0.03 → 0.01 kg, inertia scaled with mass |
| `edit_remove_car` | `DELETE car` | Car body and four wheels absent from frame 1 |
| `edit_remove_car_at_2s` | `DELETE car AT FRAME 49` | Car body and four wheels removed at frame 49 (t = 2.0 s) |

## Assets

- `khronos_models/car_concept` (url): source model of the toy car body and wheels.
- `blenderkit/cozy_living_room` (manual): sofa and cushion.
- `blenderkit/rattan_basket` (manual): wicker basket.
- `blenderkit/stuffed_penguin` (manual): plush toy.
- `polyhaven/residential_garden` (url): sky seen through the window.
- `polyhaven/beige_wall_001` (url): wall and ceiling plaster.
- `polyhaven/rough_linen` (url, with derived metadata): curtains, sofa and pillows.
- `polyhaven/wood_floor` (url, with derived metadata): floor.
- `polyhaven_models/potted_plant_02` (url): courtyard planters.
- `polyhaven_models/grass_medium_01` (url): courtyard grasses.

Manual files need a free provider account; the download script prints each asset page and the file
names to save. Download and check them with
`python3 scripts/download_assets.py --scene ramp_car_ball_collision` (add `--check` to only
report). Set `PCVE_ASSETS_DIR` to use another asset directory.

## Requirements

- Simulation: `.venv-domino` at the repository root, which has `pybullet==3.2.7`;
  `entrypoints.json` points the entry scripts at it. CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`), found from `--blender`, `$BLENDER`,
  `blender` on `PATH`, then `~/.local/opt/blender-*`; Cycles on an NVIDIA GPU (CPU works, slowly).
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene ramp_car_ball_collision --check

# List the cases
python3 scripts/rigid_rigid/ramp_car_ball_collision/build_pcve_ramp_car_ball_collision.py --list-cases

# Simulate and validate all seven cases on the CPU
.venv-domino/bin/python scripts/rigid_rigid/ramp_car_ball_collision/build_pcve_ramp_car_ball_collision.py \
    --out-root renders/ramp_car_ball_collision/suite_build --stage simulate

# Render the source video
.venv-domino/bin/python scripts/rigid_rigid/ramp_car_ball_collision/build_pcve_ramp_car_ball_collision.py \
    --out-root renders/ramp_car_ball_collision/suite_build --stage render --cases source \
    --blender tools/blender-4.3.2-linux-x64/blender --synchronized-cache

# Audit the source frames and record the visual review
.venv-domino/bin/python scripts/rigid_rigid/ramp_car_ball_collision/tools/audit_rendered_frames.py \
    --case-dir renders/ramp_car_ball_collision/suite_build/cases/source
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/ramp_car_ball_collision/tools/audit_saved_scene.py -- \
    --case-dir renders/ramp_car_ball_collision/suite_build/cases/source
.venv-domino/bin/python scripts/rigid_rigid/ramp_car_ball_collision/tools/record_visual_review.py \
    --case-dir renders/ramp_car_ball_collision/suite_build/cases/source --review-json review.json

# Render the edits, then verify every video
.venv-domino/bin/python scripts/rigid_rigid/ramp_car_ball_collision/build_pcve_ramp_car_ball_collision.py \
    --out-root renders/ramp_car_ball_collision/suite_build --stage render \
    --cases edit_heavy_ball edit_low_restitution edit_remove_ball edit_light_ball edit_remove_car edit_remove_car_at_2s \
    --blender tools/blender-4.3.2-linux-x64/blender --synchronized-cache
.venv-domino/bin/python scripts/rigid_rigid/ramp_car_ball_collision/build_pcve_ramp_car_ball_collision.py \
    --out-root renders/ramp_car_ball_collision/suite_build --stage verify

# Mass and restitution sweeps without rendering
.venv-domino/bin/python scripts/rigid_rigid/ramp_car_ball_collision/build_pcve_ramp_car_ball_collision.py \
    --out-root renders/ramp_car_ball_collision/graybox_build --stage graybox
```

- `--synchronized-cache` keeps textures cached between frames and refreshes all meshes every frame;
  it differs from an uncached render by at most one 8-bit level.
- `--device cpu` forces CPU rendering. `--reuse-physics-from <finished suite>` re-renders with the
  solved trajectories of another suite.
- The render entry renders selected frames with `--mode frames --keyframes ...` (default frames 1,
  13, 21, 25, 31, 41, 57, 77 and 96).

## Outputs

`--out-root` is required; the commands above write to `renders/ramp_car_ball_collision/suite_build/`.
Each case is written to `<out-root>/cases/<case>/`: `video.mp4`, `physics_transforms.json` (poses,
contacts, outcome, quality metrics), `trajectory.csv` (240 Hz poses and velocities),
`contacts.json`, `ground_truth_transforms.json`, `prompts.json`, `config_diff.json`,
`settings.json`, `video_validation.json`, the packed `ramp_car_ball_collision.blend` and `frames/`.
The builder refuses a non-empty output root it did not create and a root whose stored configuration
differs from the current one. The published suite is
`renders/pcve_suites/pcve_ramp_car_ball_collision_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_ramp_car_ball_collision.py`: suite builder with the stages simulate, render, verify
  and graybox.
- `simulate_ramp_car_ball_collision.py`: PyBullet solve of one case.
- `render_ramp_car_ball_collision.py`: Blender replay and render of one case.
- `scene_config.py`: configuration and case overrides; the appearance preset, lighting and model
  names in it are configuration keys recorded in the published data.
- `edit_vocab.py`: edit vocabulary, DSL statement of every edit and source prompts;
  `pcve_edit_dsl.make_prompts` turns each statement into the published prompts.
- `physics/validate_ramp_car_ball_collision.py`: physics checks for every case.
- `physics/graybox_scan.py`: mass and restitution sweeps.
- `appearance/look_ramp_car_ball_collision.py`: room, ramp, window, car, courtyard and room finish.
- `tools/audit_rendered_frames.py`: per-frame visibility audit and contact sheets.
- `tools/audit_saved_scene.py`: Blender-side comparison of saved poses, camera and render settings.
- `tools/record_visual_review.py`: records a completed visual review of a case.
- `tools/object_presence.py`: per-frame presence of the car for the deletion edits.
- `tools/prepare_template_suite.py`: lays out a suite from a packed template with the room finish applied,
  copying the solved physics unchanged.
- `tools/render_template_suite.py`: renders cases and frame ranges of a suite prepared by
  `tools/prepare_template_suite.py`, on any backend.
- `tools/review_template_suite.py`: encodes (libx264 slow, CRF 17, yuv420p), verifies and writes review
  sheets for such a suite.
- `tools/prepare_diecast.py`, `tools/render_diecast.py`: pose setting, scene audit and render
  functions shared by the packed-template tools.
- `asset_manifest.json`, `ASSET_CREDITS.md`: car model provenance, modifications and attribution.

## Limitations

- The ball is a rigid shell; PVC deformation is not modelled.
- Rolling and spinning resistance are Bullet's load-limited contact approximations; nothing is
  calibrated against a measured toy car.
- Glass uses a thin approximation for shadow rays.
- The published videos are rendered from one packed template with `tools/prepare_template_suite.py` and
  `tools/render_template_suite.py`; a fresh build with the render entry applies the same layers to a new
  scene and matches the published frames closely but not bit for bit. `tools/prepare_template_suite.py`
  checks the SHA-256 of a fixed packed template and needs the suite that holds it, which is not part
  of the repository.
- CPU renders of the same frame differ by up to a few 8-bit levels between runs.
