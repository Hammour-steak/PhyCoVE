# newtons_cradle

The leftmost ball of a five-ball steel Newton's cradle is released from rest; the impulse passes
through the three resting middle balls and swings the rightmost ball out, and the exchange repeats
for the rest of the clip. Rigid–rigid scene of PhyCoVE. Source video: 4 s, 24 fps, 96 frames,
1280×720.

## Scene

- Cradle: five chrome steel balls, radius 19 mm, density 7800 kg/m³, on 0.18 m pendulums whose
  pivots are 1.00 m above the floor. Ball gap 0.1 mm. The leftmost ball starts at rest 0.045 m above
  its lowest centre position. The frame is two 10 mm chrome tubes bent into an inverted U (uprights
  at x = ±0.265 m, cross-bars at the pivot height, y = ±0.065 m) on a piano-black base; 0.5 mm nylon
  lines run from the cross-bars to an eye screw on each ball and are parented to the balls.
- Desk: 1.70 × 0.80 m, top at 0.72 m, 28 mm rosewood-veneer top on tapered legs; the cradle stands
  on it.
- Room: a mid-century study (environment theme `mid_century_study`) with slate-blue-grey plaster
  walls (`plastered_wall_04`) and parquet (`rectangular_parquet`). Daylight only: a sun lamp at 25°
  elevation through a window in the left wall, a Nishita sky and two window portals; no window is in
  frame. AgX, exposure +1 EV.
- Props (not simulated): a rosewood cabinet with a ceramic jar, a small brass vase and a porcelain
  horse behind the desk; on the desk a picture frame (thin glass), a yellow notepad, a magnifying
  glass and a stapler. All are Poly Haven scans placed by bounding box on their supporting surface.
- Camera: location (0.78, −1.58, 1.29) looking at (−0.01, 0, 0.89), 58 mm lens, depth of field
  focused at 1.86 m, f/16. `render_newtons_cradle.py` uses this camera whenever the scenario keeps
  the default camera from `scene_config.py`.
- Render: Cycles, 384 samples for the published suite, OpenImageDenoise, motion blur with a
  0.25-frame shutter, persistent data off, caustics off.

## Physics

- Solver: PyBullet, 4800 Hz fixed step, 160 solver iterations, restitution velocity threshold 0,
  contact slop 0, deterministic overlapping pairs.
- Gravity −9.81 m/s², ball-to-ball restitution 0.99, joint damping 2e-6. Only `initial_height`,
  `restitution`, the ball presence mask and the timed-edit schedule are editable; `scene_config.py`
  rejects changes to any other parameter.
- The sampling rate must divide the 4800 Hz physics clock (24 fps × slow motion 1, 2, 4 or 8).
- Middle-ball drift and end-ball rebound height with restitution 0.99: source 10.2 mm / 42.6 mm,
  `edit_low_release` 7.3 mm / 21.3 mm, `edit_high_release` 12.9 mm / 86.4 mm.

## Validation

Every rendered frame is checked and the results are written to `render_validation.json`: each ball
stays inside the cradle keep-out box (x ±0.31 m, y ±0.125 m, z ≤ 1.02 m), every prop is at least
2 cm from that box, desk props stand on the desk without overlapping, and no prop lies on the line of
sight from the camera to any ball.

## Cases

The builder's native source case is `newtons_cradle_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Leftmost ball released 0.045 m above its lowest position |
| `edit_low_release` | `SET first_ball.initial_height TIMES 0.5` | Release height 0.045 → 0.0225 m |
| `edit_high_release` | `SET first_ball.initial_height TIMES 2` | Release height 0.045 → 0.09 m |
| `edit_delete_middle_ball` | `DELETE ball_02` | Middle ball absent from frame 1 |
| `edit_delete_inner_right_ball` | `DELETE ball_03` | Second ball from the right absent from frame 1 |
| `edit_dead_bounce_timed` | `SET balls.restitution TIMES 0.3 AT FRAME 15` | Ball restitution 0.99 → 0.297 from frame 15 |

## Assets

- `polyhaven/newtons_cradle` (url, plus one derived file): Poly Haven scans for the room materials
  and the desk and cabinet props.
- `scenes/newtons_cradle` (derived): `assets/scenes/newtons_cradle/sources.json`, the source record for the scene's assets.

Download and check them with `python3 scripts/download_assets.py --scene newtons_cradle`
(add `--check` to only report).

## Requirements

- Simulation: Python with `pybullet==3.2.7` (`requirements.txt`; the repository's `.venv-domino`
  has it). CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU (CUDA or OptiX)
  for full-quality frames, CPU works for previews.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene newtons_cradle --check

# List the native case IDs
python3 scripts/rigid_rigid/newtons_cradle/build_pcve_newtons_cradle.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/newtons_cradle/build_pcve_newtons_cradle.py \
    --out-root renders/newtons_cradle/suite_build --simulate-only

# Render the simulated cases at the published settings
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/newtons_cradle/build_pcve_newtons_cradle.py \
    --out-root renders/newtons_cradle/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720 --samples 384
```

`tools/render_queue.py` (workflow `batch_render`) builds randomised variants from `--seed-base`
into `renders/batch_newtons_cradle`.

## Outputs

The commands above write to `renders/newtons_cradle/suite_build/`, one directory per case under
`cases/`. Without `--out-root` the builder writes to
`renders/newtons_cradle/suite_build/pcve_newtons_cradle_suite/`. The published suite is
`renders/pcve_suites/pcve_newtons_cradle_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_newtons_cradle.py`: suite builder; runs the simulation and render for each case.
- `simulate_newtons_cradle.py`: PyBullet solve; writes `physics_transforms.json`.
- `render_newtons_cradle.py`: Blender replay and render; writes the video, ground truth and checks.
- `scene_config.py`: physics, render and camera defaults and scenario validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/scene_geometry.py`: pendulum pivot positions shared by solver and renderer.
- `scripts/pcve_windows_dll_paths.py` (shared): adds the conda `Library/bin` to the DLL search path on Windows.
- `appearance/look_newtons_cradle.py`: assembles the look.
- `appearance/study_room.py`: room, desk and daylight.
- `appearance/cradle_model.py`: cradle frame, balls and lines at simulation size.
- `appearance/desk_props.py`: prop placement on the desk and cabinet.
- `appearance/render_quality.py`: Cycles, denoiser and motion-blur settings.
- `tools/render_queue.py`: randomised batch builder.

## Limitations

- Each pendulum is a PyBullet revolute joint carrying a sphere at the end of a massless link; the
  nylon lines are visual only. Ball-to-ball friction is zero and one restitution value applies to
  every ball pair (each body gets the square root, Bullet multiplies the two).
- CPU renders of the same frame can differ by one intensity level in a few pixels between runs.
- When an end ball passes its lowest point, the window and sun reflected in the chrome are smeared by
  the 1/96 s shutter into a bright streak.
