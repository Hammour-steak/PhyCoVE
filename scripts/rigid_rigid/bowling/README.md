# bowling

A rigid–rigid scene in PhyCoVE. In an indoor bowling centre a 21.5 cm, 5 kg ball rolls down the
lane at 4 m/s and hits three 38 cm, 1.5 kg pins standing in a triangle; the front pin is knocked
into the back pins and all three fall. PyBullet solves every contact and Blender replays the solved
poses. The source video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- **Units and axes:** SI, Z up, +X down the lane, +Y to the left when facing the pins, gravity
  −9.81 m/s².
- **Pins:** P01 at the front centre, P02 back left, P03 back right, in an equilateral triangle
  with 30 cm spacing. Each pin has a flat base, belly, shoulder, thin neck and round head; the
  collision shape is 16 convex slices over the full height (largest radial error 0.8 mm).
  Integrating the profile gives a centre of mass 14.69 cm above the base and inertia
  `[0.01231, 0.01231, 0.00186]` kg·m² at 1.5 kg. Pins are free bodies; their bases are not fixed.
- **Ball:** sphere collider with uniform inertia; the visual mesh has two 20 mm finger holes and a
  25 mm thumb hole. Initial centre `[-2.5, 0.030, 0.1075]` m, velocity `[4, 0, 0]` m/s and the
  matching rolling spin `[0, 37.209, 0]` rad/s. Velocities are set once; there are no pushes,
  timed impulses or keyframed tipping.
- **Lane:** fixed, 1.054 m wide, with curved gutters and a pit 32 cm below the lane behind the pin
  deck (floor, back and side walls). Objects that reach the pit stay in the simulation.
- **Camera:** fixed, from the neighbouring lane's approach (three-quarter view, 50 mm lens), no
  depth of field. The neighbouring lanes are closed (sweep bars down, no pins).
- **Appearance:** preset `bowling_venue` (`appearance/appearance_venue.json`), built by
  `appearance/look_bowling.py`. It changes only what is seen; camera, contact geometry and physics
  do not depend on it.
  - No text or logos: the masking unit carries no lane numerals, and the printed maker logo and
    approval stamp on the pin coating are painted over at build time with unprinted wear from
    lower on the same pin; the marked texture is not packed into the saved scenes.
  - Masking unit: woven acoustic fabric panels at the real 27 cm weave repeat with a ±10 % tone
    spread between panels and an aluminium nosing on the bottom edge; it hides the parked
    pinsetters. Kickbacks are full height and the pit back is a black curtain on the pit-back
    contact face.
  - Gutters, capping, kickbacks and strike plates: scanned scuff and scratch maps (roughness and
    normal only, 2.5 m repeat); gutter roughness 0.46–0.70.
  - Lane: white maple grain at a 1 m tile, 39 flush boards with 0.16 mm seams and a board tone
    spread of 0.88–1.10, a full smooth top coat (coat weight 0.8, coat roughness 0.03,
    conditioner streak 0.04) that mirrors pins, ball and lamps; pin-deck wear 0.15.
  - Ball and pins: a blue-toned photographed resin pattern on the B01 mesh with its bores; scanned
    pins radially fitted to the 38 cm collision profile with their own UV atlas.
  - Lighting: every lamp is a visible fixture and there is no world fill. LED bars under the
    masking edge at the lane end, ceiling can spots on stems (30 W, 60° cone) washing the masking
    unit, a housed pit service lamp, a pin-deck emitter across the lane like its 1.30 m diffuser,
    and overhead rows on suspension rods. Static regions change by less than 0.04/255 between
    frames (30-frame test at 480×270).
- **Render:** Cycles 128 samples, OIDN denoising, AgX, 0.25-frame (1/96 s) motion blur with
  persistent data off, 1280×720, 24 fps, 96 frames; H.264 CRF 17.

## Physics

- **Solver:** PyBullet 3.2.7 at 9600 Hz (24 fps × 400 substeps), 160 solver iterations,
  split-impulse penetration recovery, zero collision margin on the convex slices. Frame i is the
  solver state at t = (i−1)/24 s; nothing is resampled, interpolated or retimed.
- **Coefficients:** ball friction 0.22, restitution 0.42, rolling friction 0.00035; pins
  friction 0.36, restitution 0.25; lane friction 0.32, restitution 0.35; pit friction 0.65,
  restitution 0.12. Restitution uses Bullet's product rule.
- **Knock-down:** a pin counts as down once it tilts past 45°; 1°, 10°, 30° and 80° crossings are
  recorded too. A removed pin is not counted.
- **Mass edits** scale the inertia with the mass and keep the shape and centre of mass. A removed
  pin is absent from frame 1.
- All inputs are in `scene_config.py`, split into `physics`, `simulation_quality`, `appearance`
  and `render`; the `appearance` section is read from `appearance/appearance_venue.json`.

## Measured motion

| Case | Measured outcome |
| --- | --- |
| `source` | ball hits P01 at 0.584 s; P01 hits P03, the ball hits P02; all three pins fall (P01, P02, P03 pass 45° at 0.654, 0.788 and 1.044 s); maximum penetration 0.215 mm |
| `edit_light_ball` | no pin falls; P01 tilts at most 0.75°; the ball bounces off and rolls into the pit |
| `edit_heavy_P01` | no pin falls; same motion as `edit_light_ball` (same ball-to-pin mass ratio) |
| `edit_remove_P01` | the ball knocks down both remaining pins (P02 at 0.756 s, P03 at 1.054 s) |
| `edit_grippy_P01` | all three fall (P01 0.712 s, P02 0.910 s, P03 1.157 s); P01 slides much less and stays on the lane |

The light-ball and heavy-pin values lie well past the thresholds found by a mass sweep (ball
0.07–0.1 kg, P01 75–100 kg).

## Validation

- The build stops if a case fails a check in `physics/validate_bowling.py`: pins start grounded
  and at rest; mass, centre of mass and inertia read back from the solver; the first contact is
  the expected one; impacts pass from the front pin to the back pins; tipping times; knock-down
  count; maximum penetration (at most 0.315 mm over the five cases); no energy gain; ballistic free
  flight; continuous poses. The source is simulated and checked first; edits run only if it
  passes.
- The video check covers full decode, resolution, frame rate and frame count.
- Runs at 4800, 9600 and 19200 Hz agree on the knock-down count and the chain of impacts; later
  secondary contacts do not converge frame by frame.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source roll |
| `edit_light_ball` | `SET B01.mass TIMES 0.01` | Ball mass 5 → 0.05 kg |
| `edit_heavy_P01` | `SET P01.mass TIMES 100` | Front pin mass 1.5 → 150 kg |
| `edit_remove_P01` | `DELETE P01` | Front pin removed from frame 1 |
| `edit_grippy_P01` | `SET P01.friction TIMES 6.944444444444445` | Front pin friction 0.36 → 2.5 |

Prompts are generated from the edit DSL by `pcve_edit_dsl.make_prompts` with the vocabulary in
`edit_vocab.py`; the source prompts are written in `build_pcve_bowling.py`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `bowling_documentary/ball_ramprasath` | manual | ball resin texture |
| `bowling_documentary/retired_pin` | manual | pin model and paint (printed marks painted out at build time) |
| `bowling_documentary/white_maple_veneer` | url | lane boards |
| `polyhaven/poly_wool_herringbone` | url | masking-unit fabric |
| `polyhaven/blue_metal_plate` | url | scuffs on gutters, capping, kickbacks and strike plates (roughness and normal only) |
| `bowling_documentary/fonts` | manual | font read by the venue layer for lane numerals that the final look deletes; nothing of it is rendered |

Assets live in `assets/` at the repository root (`PCVE_ASSETS_DIR` selects another location).
Manual files need a provider account; `download_assets.py` prints each asset page and the file
names to save.

```bash
python3 scripts/download_assets.py --scene bowling
python3 scripts/download_assets.py --scene bowling --check
```

## Requirements

- Python environment `.venv-domino/` at the repository root with `pybullet==3.2.7`;
  `entrypoints.json` points the entry scripts at it.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- An NVIDIA GPU for rendering at a practical speed (CPU rendering works but is slow).
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
B=scripts/rigid_rigid/bowling/build_pcve_bowling.py
.venv-domino/bin/python $B --list-cases
.venv-domino/bin/python $B --out-root renders/bowling/new_run --dry-run      # print the plan only
.venv-domino/bin/python $B --out-root renders/bowling/new_run --stage simulate --cases source
.venv-domino/bin/python $B --out-root renders/bowling/new_run --stage all     # simulate, render, verify
.venv-domino/bin/python $B --out-root renders/bowling/new_run --stage verify
```

- All five cases run by default; `--cases` selects some of them. `--stage` runs one step
  (`simulate`, `render` or `verify`); `all` runs them in order. `--skip-existing` reuses finished
  cases in the same output root. `--stage graybox` runs the physics sweeps without rendering.
- Run the build on an idle GPU; the shared `--gpu` option selects the device. `--device cpu`
  renders on the CPU.
- To render the cases in parallel on idle GPUs, run `--stage simulate` first, then
  `.venv-domino/bin/python scripts/rigid_rigid/bowling/tools/render_queue.py --out-root renders/bowling/new_run --max-jobs 2`.
- `--reuse-physics-root <finished suite>` renders with the solved trajectories of another suite
  after checking that its physics, solver and render settings match.

## Outputs

Each case is written to `<out-root>/cases/<case>/` (`--out-root` is required):

| File | Content |
| --- | --- |
| `video.mp4` | the rendered video (H.264, CRF 17) |
| `physics_transforms.json` | full simulation result: per-frame poses, contacts, tilt thresholds, quality metrics |
| `trajectory.csv` | 240 Hz poses and velocities of the ball and pins |
| `contacts.json` | sub-frame contact events with normal force and impulse |
| `ground_truth_transforms.json` | per-frame poses as replayed in Blender |
| `prompts.json` | edit DSL and natural-language prompts |
| `scenario_metadata.json`, `settings.json` | the exact inputs of the case |
| `video_validation.json` | decode and format check of the video |
| `bowling.blend` | the rendered scene with textures packed |

The suite root also holds `suite_manifest.json` and `implementation_manifest.json`. The published
suite is `renders/pcve_suites/pcve_bowling_suite/`; do not use it as an output root.

## Code layout

- `simulate_bowling.py` — PyBullet simulation (public entry).
- `render_bowling.py` — Blender replay and rendering (public entry).
- `build_pcve_bowling.py` — suite builder: simulate, render, verify (public entry).
- `scene_config.py` — all physical, numerical, appearance and render inputs and the case overrides.
- `edit_vocab.py` — edit DSL vocabulary and prompts.
- `physics/validate_bowling.py` — physics validation of each case.
- `physics/graybox_bowling.py` — gray-box physics sweeps (`--stage graybox`).
- `appearance/look_bowling.py` — Blender look of the venue, pins and ball, built in layers.
- `appearance/appearance_venue.json` — appearance configuration.
- `tools/render_queue.py` — renders cases on idle GPUs.
- `entrypoints.json`, `scene_manifest.json` — entry options and runtimes for the shared CLI; published suite.

## Limitations

- The ball has uniform-sphere inertia and the pins uniform solid inertia: no core, coating
  elasticity or wear.
- Friction and restitution are effective solver parameters, not calibrated against real bowling
  equipment.
- The pinsetter, masking unit and venue are static approximations built for appearance.
- Pins that fall into the pit can be hidden by the lane end and the kickbacks; in the source, P02
  lies in the pit behind the pin deck from about frame 48 on.
