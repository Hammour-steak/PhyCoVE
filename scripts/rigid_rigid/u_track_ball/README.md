# u_track_ball

A wooden ball is released from rest on the long, steep branch of an asymmetric U track on a display
table, rolls through the bottom of the U, climbs over the short exit branch and strikes a cardboard
carton standing on the table top. Rigid–rigid scene of PhyCoVE. Source video: 4 s, 24 fps,
96 frames, 1280×720.

## Scene

- Track: two parabolic branches meeting at the bottom of the U, z = 0.82 + h (x/L)² m. The drive
  branch is 0.90 m long and rises 0.56 m; the exit branch is 0.75 m long and rises 0.20 m. The
  channel is 0.18 m wide and 24 mm thick, discretised into 60 segments per branch. The visible
  channel floor is the collision mesh, topped with charcoal linoleum; 18 mm birch-plywood side boards
  coincide with the solver's side-board boxes. Ribs, a spine and a base board under the channel are
  visual only.
- Ball: radius 0.045 m, 0.25 kg, rendered as turned black walnut; it starts at rest at
  x = −0.84 m on the drive branch.
- Carton: 0.16 × 0.22 × 0.20 m, 0.08 kg, kraft corrugated board with label and tape, standing at
  (1.35, 0, 0.82) on the table top.
- Display table: 3.4 × 1.1 × 0.09 m top at 0.72 m, olive linoleum (`linoleum_brown`, recoloured)
  with a plywood edge and black square-tube legs; an exhibit label stands at the front left.
- Room: a science-museum gallery (environment theme `science_museum_gallery`) with board-formed
  concrete walls (`wood_textured_concrete`), terrazzo floor tiles (`terrazzo_tiles`), an exhibit
  panel on the back wall and a floor-to-ceiling window on the left showing the
  `golden_gate_hills` HDRI to camera rays only.
- Light: a sun lamp and a Nishita sky through the window (with a sky portal), ceiling track
  spotlights at about 3500 K and four recessed linear lights. AgX Base Contrast, exposure +0.35.
- Camera: location (2.45, −4.0, 2.45) looking at (0.35, 0, 1.02), 48 mm lens.
- Render: Cycles, 48 samples for the published suite, motion blur with a 0.5-frame shutter,
  persistent data off.

## Physics

- Solver: PyBullet, time step 1/960 s (40 substeps per 24 fps frame), 100 solver iterations,
  deterministic overlapping pairs.
- Gravity −9.81 m/s². Track friction 0.20, ball friction 0.50, ball rolling friction 0.002,
  spinning friction 0.0001, ball and carton restitution 0.05, track and table restitution 0,
  table friction 0.35, carton friction 0.45.
- The track is a concave triangle mesh built by `physics/track_geometry.py`, which also gives the
  renderer its geometry.
- Two consecutive Linux runs with PyBullet 3.2.7 give byte-identical output files.

## Validation

During rendering `visual_details.check_props` uses the ball and carton poses of all 96 frames to
check every visual-only prop: each must stay at least 2 cm from the ball and the carton and must not
hide either from the camera, otherwise the render fails. The results are written to `prop_clearance`
in `render_validation.json`.

## Cases

The builder's native source case is `u_track_ball_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Ball released from rest at x = −0.84 m |
| `edit_lower_release` | `SET ball.initial_position TO -0.7` | Release position −0.84 → −0.70 m |
| `edit_shallow_release` | `SET ball.initial_position TO -0.45` | Release position −0.84 → −0.45 m |
| `edit_fast_launch` | `SET ball.initial_velocity TO 1.8` | Initial speed 0 → 1.8 m/s along the track |
| `edit_heavy_ball` | `SET ball.mass TIMES 2.5` | Ball mass 0.25 → 0.625 kg |
| `edit_box_vanishes_before_impact` | `DELETE box AT FRAME 33` | Carton removed from frame 33 |
| `edit_delete_ball` | `DELETE ball` | Wooden ball removed from frame 1 |

## Assets

- `polyhaven/u_track_ball` (url, plus one derived file): Poly Haven scans for the gallery, table
  and track materials (`linoleum_brown`, `plywood`, `terrazzo_tiles`, `wood_textured_concrete`) and
  the `golden_gate_hills` HDRI; `assets/polyhaven/u_track_ball/sources.json` is the derived source record.

Download and check them with `python3 scripts/download_assets.py --scene u_track_ball`
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
python3 scripts/download_assets.py --scene u_track_ball --check

# List the native case IDs
python3 scripts/rigid_rigid/u_track_ball/build_pcve_u_track_ball.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/u_track_ball/build_pcve_u_track_ball.py \
    --out-root renders/u_track_ball/suite_build --simulate-only

# Render the simulated cases at the published settings
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/u_track_ball/build_pcve_u_track_ball.py \
    --out-root renders/u_track_ball/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720 --samples 48
```

`tools/render_queue.py` (workflow `batch_render`) builds randomised variants from `--seed-base`
into `renders/batch_u_track_ball`.

## Outputs

The commands above write to `renders/u_track_ball/suite_build/`, one directory per case under
`cases/`. Without `--out-root` the builder writes to
`renders/u_track_ball/suite_build/pcve_u_track_ball_suite/`. The published suite is
`renders/pcve_suites/pcve_u_track_ball_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_u_track_ball.py`: suite builder; runs the simulation and render for each case.
- `simulate_u_track_ball.py`: PyBullet solve; writes `physics_transforms.json`.
- `render_u_track_ball.py`: Blender replay and render; writes the video, ground truth and checks.
- `scene_config.py`: physics, render and camera defaults and scenario validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/track_geometry.py`: track, table and carton geometry shared by solver and renderer.
- `scripts/pcve_windows_dll_paths.py` (shared): adds the conda `Library/bin` to the DLL search path on Windows.
- `appearance/look_u_track_ball.py`: gallery, track, ball, carton and lighting.
- `appearance/visual_details.py`: visual-only props and the prop clearance check.
- `tools/render_queue.py`: randomised batch builder.

## Limitations

- On the steepest part of the drive branch the ball slides rather than rolling purely; the effective
  friction there is 0.5 × 0.2 = 0.1.
- The ball does not bounce when it lands on the table top (table restitution 0).
- In the source, `edit_fast_launch`, `edit_heavy_ball` and `edit_box_vanishes_before_impact` cases
  the ball finally rolls off the table top and leaves the frame.
- A Windows PyBullet build matches the Linux results to within 2e-10 in five cases; in
  `edit_shallow_release` it diverges from frame 74 by at most 0.56 mm in position.
- CPU renders of the same frame can differ by one intensity level in a few pixels between runs.
