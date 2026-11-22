# stair_ball_bounce

A 14 cm, 40 g hollow toy ball with red, yellow and blue panels starts 15 cm above the top tread of a
home staircase, bounces down five wooden steps onto the lower landing, then bounces lower and rolls.
PyBullet solves every contact and trajectory; Blender replays the solved poses. Rigid–rigid scene of
PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Units and axes: SI, Z up, +X down the stairs, gravity −9.81 m/s².
- Stairs: treads S01–S05 at heights 0.80, 0.64, 0.48, 0.32 and 0.16 m, each 0.28 m deep and 0.90 m
  wide; upper landing at 0.96 m, lower landing at 0 m. Each tread has a 2.5 mm rounded nosing
  (eight-segment quarter circle) shared by the visual and collision shapes. Oak caps, noses and the
  landing match the collision meshes; the painted stair bodies sit 22 mm behind each nose.
- Ball: sphere collider, diameter 14 cm, mass 40 g, thin-shell inertia `I = 2/3 m r²`. Initial
  centre (0.038, 0, 1.02) m, initial velocity (1.35, 0, 0) m/s, no initial spin. Spin comes only from
  contact friction.
- Room (preset `home_oak_stairwell`): an enclosed stairwell with housed oak joinery, scanned painted
  plaster walls (3 m tile), satin-lacquered oak treads and landings, a radiator, a socket, a framed
  picture, a plant on the window sill and a 46 × 82 mm painted skirting along the open side of the
  stair. All furnishings stay outside the ball corridor (|Y| ≤ 0.07 m).
- Light: the `sunny_rose_garden` sky behind a real window (sun at 49° elevation), 12 diffuse and
  16 total bounces, no lamps.
- Camera: location (2.0, −4.4, 1.65) looking at (1.8, 0, 0.95), 30 mm lens; every case stays in
  frame.
- Render: Blender 4.3, Cycles, 64 samples, OpenImageDenoise, AgX Medium High Contrast, exposure
  +0.9 EV, white balance 5800 K with tint 14, no depth of field or motion blur. Videos are H.264,
  CRF 17.

All inputs live in `scene_config.py`, split into `physics`, `simulation_quality`, `appearance` and
`render`.

## Physics

- Solver: PyBullet 3.2.7, 9600 Hz (24 fps × 400 substeps), 100 contact iterations, split-impulse
  penetration recovery, `contactProcessingThreshold=0`. Video frame i is the solver state at
  t = (i−1)/24.
- Ball: restitution 0.55 (stairs 1.0; Bullet multiplies the two values), lateral friction 0.5,
  rolling friction 0.00115, spinning friction 0.0001. Stairs and landings: lateral friction 0.5, zero
  rolling and spinning friction. Restitution stops below 0.08 m/s; friction keeps acting. No air
  drag or damping.
- The initial velocity is set once; there are no constraints, pushes or corrections in flight.
- Contact events are continuous intervals of positive normal force, so one impact can span several
  events; `major_impact` lists only events with a clear approach speed and rebound.
- `--stage graybox` runs initial-condition and material scans, a drop test of the restitution rule
  and a timestep-halving comparison without rendering.

## Measured motion

From the solved 4 s trajectories:

| Case | Motion |
| --- | --- |
| `source` | One main bounce on each of S01–S05; first landing contact 1.80 s; rolls on the landing from 2.32 s |
| `edit_low_restitution` | Bounces of 0.4 cm; rolls on the landing from 1.87 s |
| `edit_high_restitution` | First rebound 6.3 cm; first landing contact 2.03 s |
| `edit_slow_initial_velocity` | Four bounces on S01; reaches the landing at 2.75 s |
| `edit_fast_initial_velocity` | Clears S01 and lands first on S02; landing contact 1.64 s |
| `edit_low_sliding_friction` | Lands on S01, S03 and S05 only; landing contact 1.40 s |
| `edit_low_rolling_friction` | Same contacts as the source; rolls farther on the landing |
| `edit_high_rolling_friction` | Repeated short contacts on S02, S04, S05; stops at x = 1.65 m at 2.93 s |
| `edit_high_friction` | Extra contacts on S03 and S05; nearly at rest on the landing at 4 s |

## Validation

The build stops when a case fails a check.

- Physics, after each simulation (`physics/validate_stair_ball_bounce.py`): one initial velocity
  and no constraints or external forces, ballistic free flight, no energy gain, no penetration or
  contact gap at rebounds, no pose jumps, spin generated only by contact, and the ball reaches and
  stays on the lower landing. The source must hit S01–S05 in order with five clear rebounds, then
  bounce and roll on the landing. An edit may differ from the source only in its declared
  parameters. `edit_high_friction` comes to rest at 4.16 s, so it must instead be nearly at rest on
  the lower landing (speed below 0.1 m/s) and decelerating through the last 0.5 s.
- Video, in the `render` and `verify` stages (`scripts/pcve_verify_video.py`): full decode,
  resolution, frame rate and frame count.

The source is simulated first; edits are simulated only after it passes.

## Cases

Every edit changes only the listed ball parameters from the start of the simulation. `edit_vocab.py`
maps the DSL properties to the config fields and generates the edit prompts with
`pcve_edit_dsl.make_prompts`; the source prompts are in `build_pcve_stair_ball_bounce.py`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Ball thrown at 1.35 m/s down the stairs |
| `edit_low_restitution` | `SET B01.restitution TIMES 0.3` | Restitution 0.55 → 0.165 |
| `edit_high_restitution` | `SET B01.restitution TIMES 1.18` | Restitution 0.55 → 0.649 |
| `edit_slow_initial_velocity` | `SET B01.initial_velocity TIMES 0.48148148148148145` | vx 1.35 → 0.65 m/s |
| `edit_fast_initial_velocity` | `SET B01.initial_velocity TIMES 1.1703703703703703` | vx 1.35 → 1.58 m/s |
| `edit_low_sliding_friction` | `SET B01.lateral_friction TO 0.05` | Lateral friction 0.5 → 0.05 |
| `edit_low_rolling_friction` | `SET B01.rolling_friction TO 0.0002` | Rolling friction 0.00115 → 0.0002 |
| `edit_high_rolling_friction` | `SET B01.rolling_friction TO 0.012` | Rolling friction 0.00115 → 0.012 |
| `edit_high_friction` | `SET B01.friction TIMES 5` | Lateral friction 0.5 → 2.5 and rolling friction 0.00115 → 0.00575 together |

## Assets

- `polyhaven/beige_wall_001` (url): painted-plaster relief and roughness on the walls and the
  painted stair.
- `polyhaven/wood_floor` (url): treads and landings.
- `polyhaven/sunny_rose_garden` (url): sky and sunlight behind the window.
- `polyhaven/hanging_picture_frame_02` (url): framed picture on the wall.
- `polyhaven/potted_plant_04` (url): plant on the window sill.

Download and check them with `python3 scripts/download_assets.py --scene stair_ball_bounce` (add
`--check` to only report). `tools/fetch_assets.py` fetches the two props and the sky directly from
the Poly Haven API with per-asset manifests.

## Requirements

- Python: `.venv-domino` in the repository root, or any environment with `requirements.txt`
  (`pybullet==3.2.7`). The simulation runs on the CPU.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU, CPU works but
  is slow. `ffmpeg`/`ffprobe` for encoding and the video check.

## Commands

Run from the repository root. Without `--cases` the builder runs only `source`,
`edit_low_restitution` and `edit_high_restitution`, so the commands list all nine cases.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene stair_ball_bounce --check

# List the cases and print the plan
.venv-domino/bin/python scripts/rigid_rigid/stair_ball_bounce/build_pcve_stair_ball_bounce.py --list-cases
.venv-domino/bin/python scripts/rigid_rigid/stair_ball_bounce/build_pcve_stair_ball_bounce.py \
    --out-root renders/stair_ball_bounce/suite_build --dry-run

# Simulate and validate all nine cases on the CPU
.venv-domino/bin/python scripts/rigid_rigid/stair_ball_bounce/build_pcve_stair_ball_bounce.py \
    --out-root renders/stair_ball_bounce/suite_build --stage simulate \
    --cases source edit_low_restitution edit_high_restitution edit_slow_initial_velocity \
    edit_fast_initial_velocity edit_low_sliding_friction edit_low_rolling_friction \
    edit_high_rolling_friction edit_high_friction

# Render, then verify the videos
.venv-domino/bin/python scripts/rigid_rigid/stair_ball_bounce/build_pcve_stair_ball_bounce.py \
    --out-root renders/stair_ball_bounce/suite_build --stage render \
    --blender tools/blender-4.3.2-linux-x64/blender \
    --cases source edit_low_restitution edit_high_restitution edit_slow_initial_velocity \
    edit_fast_initial_velocity edit_low_sliding_friction edit_low_rolling_friction \
    edit_high_rolling_friction edit_high_friction
.venv-domino/bin/python scripts/rigid_rigid/stair_ball_bounce/build_pcve_stair_ball_bounce.py \
    --out-root renders/stair_ball_bounce/suite_build --stage verify \
    --cases source edit_low_restitution edit_high_restitution edit_slow_initial_velocity \
    edit_fast_initial_velocity edit_low_sliding_friction edit_low_rolling_friction \
    edit_high_rolling_friction edit_high_friction
```

`--stage all` (the default) runs simulate, render and verify in order; `--skip-existing` reuses
finished cases; `--appearance-json` applies an appearance-only override to every selected case.
`tools/prepare_appearance_stair_ball_bounce.py --source-root <suite> --out-root <new root>` copies
each case's accepted solver payload, replaces only `appearance` and checks that poses, 240 Hz
samples, contacts and metrics are unchanged.

## Outputs

The commands above write to `renders/stair_ball_bounce/suite_build/`, one directory per case under
`cases/` with `video.mp4`, `physics_transforms.json`, `trajectory.csv` (240 Hz),
`contacts.json`, `ground_truth_transforms.json`, `prompts.json`, `scenario_metadata.json`,
`settings.json`, `physics_validation.json`, `video_validation.json` and `stair_ball_bounce.blend`.
The published suite is `renders/pcve_suites/pcve_stair_ball_bounce_suite/`; do not pass it as
`--out-root`.

## Code layout

- `build_pcve_stair_ball_bounce.py`: suite builder with stages `simulate`, `render`, `verify`,
  `all` and `graybox`; holds the source prompts.
- `simulate_stair_ball_bounce.py`: PyBullet simulation; writes `physics_transforms.json` and
  `trajectory.csv`.
- `render_stair_ball_bounce.py`: Blender replay and render.
- `scene_config.py`: all physical, numerical, appearance and render inputs and the cases.
- `edit_vocab.py`: edit DSL vocabulary and edit records.
- `physics/validate_stair_ball_bounce.py`: physics acceptance checks.
- `physics/graybox_stair_ball_bounce.py`: scans, drop test and timestep comparison.
- `appearance/look_stair_ball_bounce.py`: Blender look, built in five successive layers (real-scale
  stairwell, domestic finish, enclosed daylit room, sunlit stairwell with furnishings, final
  photographic pass).
- `tools/prepare_appearance_stair_ball_bounce.py`: appearance-only rebuild from an accepted suite.
- `tools/fetch_assets.py`: fetches the props and sky from the Poly Haven API.

## Limitations

- Rigid-body approximation: shell deformation, the air inside the ball and rate-dependent material
  behaviour are not modelled.
- Restitution and friction are effective solver parameters, not calibrated against a real toy ball.
- `edit_high_friction` changes two coefficients at once, so its effect cannot be attributed to
  either alone.
- Glass uses a thin-window approximation (0.965 transmission per surface for direct light). Sky
  strength, exposure, white balance and paint brightness are set by visual review; about 0.2 % of
  pixels clip (window and sun patch).
- The visible floor ends at the wall (Y = 0.5 m) while its collision box extends behind it; the
  ball stays near Y = 0.
- `tools/fetch_assets.py` writes to `assets/` and ignores `PCVE_ASSETS_DIR`.
- CPU renders of the same frame differ between runs by up to about 12 intensity levels in isolated
  pixels (mean difference below 0.003 levels).
