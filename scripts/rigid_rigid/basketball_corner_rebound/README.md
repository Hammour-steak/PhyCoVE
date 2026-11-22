# basketball_corner_rebound

A rigid–rigid scene in PhyCoVE. A basketball rolls diagonally into the right-angled corner of a
daylit room, rebounds off one wall and then the other, and rolls back out into the room. PyBullet
solves the rolling and the wall contacts and Blender renders the solved poses. The source video
is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- **Units and axes:** SI, Z up, gravity −9.81 m/s². The room is 8 × 8 × 3 m; the corner the ball
  rolls into is at x = 0, y = 0.
- **Ball:** sphere, radius 0.121 m, mass 0.62 kg, starting at (1.48, 1.24) m on the floor, rolling
  at 2.0 m/s along the direction (−0.87, −0.493) with the matching pure-rolling spin.
- **Walls and floor:** four static wall boxes and a static floor box.
- **Camera:** fixed and level (no pitch) so the room's verticals stay vertical; the framing comes
  from a vertical lens shift (`shift_y`). Location, target and lens are in the scene's
  `assets/scenes/basketball_corner_rebound/scenario.json` asset.
- **Light:** no lamps inside. A sun lamp at 38° elevation and −35° heading and a physical sky
  with its own sun disc off light the room through the windows; every window opening has a Cycles
  portal. The room is closed, with a ceiling and a fill window in each of the two walls behind the
  camera.
- **View outside:** a garden HDRI seen through the glass, visible to camera rays only and rotated
  to the sun azimuth; the lighting comes from the physical sky.
- **Floor:** worn wood-floor scan (diffuse, roughness and normal maps at 2k), tiled at 2 m.
- **Props:** a framed picture on the wall and a fiddle-leaf fig under the window, both visual
  only.
- **Render:** Cycles, AgX Base Contrast, exposure +3, 180° shutter (0.5-frame) motion blur,
  24 samples plus denoising by default.

## Physics

- PyBullet in DIRECT mode, time step 1/1440 s (60 substeps per frame), 120 solver iterations,
  restitution velocity threshold 0.02 m/s, contact breaking threshold 1 mm, swept-sphere CCD with
  radius 0.8 r.
- Ball: restitution 0.82, lateral friction 0.65, rolling friction 0.002, spinning friction 0.0001,
  linear and angular damping 0.008. Floor: restitution 0.65, friction 0.5, rolling friction 0.002.
  Walls: restitution 1.0, friction 0.12.
- Frame i is the solver state at t = (i−1)/24 s.
- A timed edit is written into the live ball at the top of its start frame: frames 1 to k−1 are
  stepped on the source physics, and the steps that lead to frame k run on the edited value. A
  spin edit multiplies the ball's current angular velocity about its current axis; pose and linear
  velocity are left unchanged (the simulator refuses an edit that moves the ball).

## Measured motion

| Case | Outcome |
| --- | --- |
| `source` | First wall contact at frame 21, second at frame 32; path length 3.40 m |
| `edit_fast_ball` | 4 m/s launch; wall contacts move to about frames 11 and 16; the ball ends about 3 m further than in the source |
| `edit_slow_ball` | 0.6 m/s launch; rolling friction stops the ball before the corner, no wall contact; path 1.21 m; final position about 1.27 m from the source |
| `edit_slick_ball` | Smaller tangential wall impulse, the ball slips at both walls; path 4.3 m |
| `edit_low_gravity` | Gravity −3.924 m/s²; lower normal force and rolling resistance; second contact at frame 31; path 3.83 m; final position 0.46 m further out |
| `edit_spin_midway` | Spin 8.8 → 44.2 rad/s at frame 28; friction turns the extra spin into forward speed; second contact at frame 31; final position 1.9 m further; frames 1–27 equal the source |

## Validation

- The builder rejects a case with non-finite states, floor or wall penetration above 1 cm, or an
  edit that never moves the ball more than 2 cm from the source; for the timed edit it requires
  frames before the start frame to equal the source exactly.
- The renderer checks every frame's Blender pose against the physical sphere, whether the ball is
  in frame, and its clearance from the plant pot (`clear_of_plant`, `min_plant_clearance_m` in
  `render_validation.json`).

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Ball 0.62 kg at 2.0 m/s, friction 0.65, gravity −9.81 m/s² |
| `edit_fast_ball` | `SET ball.initial_velocity TIMES 2` | Launch speed 2.0 → 4.0 m/s |
| `edit_low_gravity` | `SET world.gravity TIMES 0.4` | Gravity −9.81 → −3.924 m/s² |
| `edit_slick_ball` | `SET ball.friction TIMES 0.15` | Ball friction 0.65 → 0.0975 |
| `edit_slow_ball` | `SET ball.initial_velocity TIMES 0.3` | Launch speed 2.0 → 0.6 m/s |
| `edit_spin_midway` | `SET ball.spin TIMES 5 AT FRAME 28` | Spin multiplied by 5 from frame 28 (t = 1.125 s) |

The builder calls the source case `basketball_corner_baseline`; the edit IDs are the same as the
published case names. `edit_vocab.py` declares the DSL vocabulary, the edits and the source
prompts; the builder writes edit prompts with `pcve_edit_dsl.make_prompts`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `scenes/basketball_corner_rebound` | derived | `assets/scenes/basketball_corner_rebound/scenario.json` (physics, camera, render and asset settings), camera and source records |
| `polyhaven/basketball_corner_rebound` | url | Worn wood-floor maps and the garden HDRI |
| `models` (`cafe_wall_pictures.glb`, `fiddle_leaf_fig.glb`) | manual | Wall picture and plant |

```bash
python3 scripts/download_assets.py --scene basketball_corner_rebound
python3 scripts/download_assets.py --scene basketball_corner_rebound --check
```

## Requirements

- Python environment `.venv-domino/` at the repository root with `pybullet==3.2.7`
  (`requirements.txt`); the builder simulates in its own process, so run it with this
  interpreter.
- Blender 4.3.2 for rendering (`tools/blender-4.3.2-linux-x64/blender`, or `$BLENDER`, `blender`
  on `PATH`, `~/.local/opt/blender-*`).
- Physics runs on a CPU; rendering defaults to `--device cpu`.

## Commands

Run from the repository root.

```bash
.venv-domino/bin/python scripts/rigid_rigid/basketball_corner_rebound/build_pcve_basketball_corner_rebound.py --list-cases

# physics for all six cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/basketball_corner_rebound/build_pcve_basketball_corner_rebound.py \
  --out-root renders/basketball_corner_rebound/run --simulate-only

# all 96 frames of every case at the published resolution
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/basketball_corner_rebound/build_pcve_basketball_corner_rebound.py \
  --out-root renders/basketball_corner_rebound/run --mode animation --resolution 1280 720 \
  --blender tools/blender-4.3.2-linux-x64/blender

# one case without the builder
.venv-domino/bin/python scripts/rigid_rigid/basketball_corner_rebound/simulate_basketball_corner_rebound.py \
  --out renders/basketball_corner_rebound/single/physics_transforms.json
```

The builder always builds the source plus the edits named by `--only` (comma-separated edit IDs,
all edits by default); it has no `--cases` option. `--mode` is `keyframes` (default; frame 1, the
two wall contacts, the timed-edit frame and the last frame, or `--keyframes` with comma-separated
frame numbers), `preview`, `build` or `animation` (all 96 frames and `video.mp4`). The render
entry re-simulates each case from its scenario with the physics interpreter found by
`scene_config.runtime()` (`PCVE_PHYSICS_PYTHON`, then `.runtime/sim`, then a Python on `PATH`).
The unified simulate entry with `--out-root` writes `<out-root>/simulation.json` in that directory.

## Outputs

Without `--out-root` the builder writes to
`renders/basketball_corner_rebound/suite_build/pcve_basketball_corner_rebound_suite/`. Each case
folder `cases/<case>/` receives `scenario_overrides.json`, `scenario_input.json`, `prompts.json`,
`physics_transforms.json`, `simulation_metrics.json` and `run_status.json`, and after rendering the
frames or `video.mp4`, `ground_truth_transforms.json`, `scenario_metadata.json`,
`render_validation.json` and `render.log`. The suite root holds `suite_manifest.json`. The
published suite is `renders/pcve_suites/pcve_basketball_corner_rebound_suite/`; do not use it as
an output root.

## Code layout

- `build_pcve_basketball_corner_rebound.py`: suite builder (simulation, checks, render calls,
  manifest).
- `simulate_basketball_corner_rebound.py`: PyBullet solve, timed-edit schedule and wall-contact
  events.
- `render_basketball_corner_rebound.py`: Blender replay, camera, validation and rendering of one
  case.
- `scene_config.py`: loads and validates `assets/scenes/basketball_corner_rebound/scenario.json`, finds the runtimes.
- `edit_vocab.py`: DSL vocabulary, the five edits with their on-screen summaries, source prompts.
- `appearance/look_basketball_corner_rebound.py`: room, daylight, floor, picture and plant.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry-point description, scene
  manifest and Python requirements.

## Limitations

- The ball is a rigid sphere and the walls are static boxes; ball deformation is not solved.
- The picture and the plant are visual only; contact with the pot is reported, not simulated.
- The builder's default render resolution is 960×540 with 24 samples; pass
  `--resolution 1280 720` to match the published videos.
