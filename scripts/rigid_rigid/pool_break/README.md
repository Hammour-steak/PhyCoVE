# pool_break

A cue ball rolls down a pool table into a three-ball rack; the apex ball passes the impulse into the
two rear balls and the triangle opens up towards the side cushions. Rigid–rigid scene of PhyCoVE.
Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Table: `pool_table_animation.glb` scaled so its balls have the regulation radius 28.575 mm. Playing
  surface 1.81 × 0.93 m (half extents 0.904 × 0.467 m), cloth 0.74 m above the floor, cushions
  36.3 mm high. The table model is fitted to the solver's cloth and cushion planes
  (`appearance/table_model.py`); its frame has a satin clear coat. The model's own low-poly table,
  cue sticks and unused balls are hidden on import.
- Balls: cue ball, yellow 1, blue 2 and red 3 from the table model (2k textures), subdivided with every
  vertex on the 28.575 mm radius. The rack is an equilateral triangle pointing at the cue ball, apex on
  the foot spot (x = −0.452 m), rear pair one centre spacing behind it, 0.5 mm gaps. The cue ball starts
  at x = 0.60 m.
- Room: a basement billiard bar (`appearance/billiard_room.py`), far wall at x = −2.29 m, side walls at
  y = ±1.89 m, ceiling 2.30 m. Red brick walls (`brick_wall_001` tiled at 1.8 m for a 75 mm course),
  dark wood skirting and sill, `old_wooden_floor_02` floor, whitewashed ceiling; all boxes are
  UV-unwrapped in world metres.
- Light: a green caged fluorescent lamp on a chain 0.81 m above the cloth, lighting the table through an
  area light under its tubes; two wall sconces on the far wall and one over the barrel table, each a
  point light inside the shade. A window in the right wall lets in a sun lamp at 30° elevation and a
  Nishita sky (with a sky portal); camera rays through the glass see the `dusseldorf_bridge` photograph.
- Props (not simulated): a wine barrel used as a standing table with two bar stools in the far left
  corner and a wall clock on the far wall. The renderer checks every frame that no ball comes within
  2 cm of a prop's bounding box (`check_clearance`) and that no prop blocks the camera's view of a ball
  (`check_line_of_sight`); the closest piece over all cases is the lamp, 0.75 m from a ball.
- Camera (`--camera-mode break`, the default): location (1.90, −0.54, 0.88) looking at
  (−0.10, 0, −0.04), 21 mm lens, f/5.6, behind the cue ball and low at the head end; the whole table
  stays in frame. `--camera-mode survey` uses a higher rig at (1.90, −1.00, 1.52), 18 mm.
- Render: Cycles (48 samples by default), OptiX denoising when an OptiX device exists, otherwise
  OpenImageDenoise, AgX Base Contrast, exposure +0.3, motion
  blur with a 0.5-frame shutter, persistent data off.

## Physics

- Solver: PyBullet, 96 substeps per frame (2304 Hz at 24 fps), 200 solver iterations. Gravity
  −9.81 m/s².
- Four rigid spheres on a felt plane bounded by four cushion walls at the cushion noses; the pockets
  are visual only, so every ball stays on the table.
- Fixed parameters: ball mass 0.17 kg, ball friction 0.25, felt friction 0.12, ball restitution 0.93
  (ball–ball 0.93 × 0.93 = 0.86), felt restitution 0.10, cushion friction 0.30, cushion restitution
  0.72; rolling and spinning friction 0.
- Cloth drag is integrated outside Bullet as a constant rolling deceleration `BALL_ROLL_DECEL` =
  0.30 m/s². At frame 96 the cue ball and the apex ball have stopped and the other two are still
  rolling slowly.
- Editable: cue speed (3.6 m/s), signed lateral contact offset of the cue's line from the apex centre
  (0.003 m; ± one radius is a half-ball hit) and cue mass (0.17 kg).
- The visible ball spin is reconstructed as rolling without slip from each ball's path
  (`rolling_quaternions`).

## Measured motion

On Linux with the pip build of PyBullet 3.2.7 the six cases reproduce bit for bit. A Windows build
diverges from frame 11–20 depending on the case; the largest ball position differences are 0.03 mm in
the source, at most 0.07 mm in `edit_cut_left`, `edit_cut_right`, `edit_light_cue` and
`edit_dead_rack_timed`, and 7.2 cm in `edit_power_break` (end-of-clip spread 0.700 vs 0.738 m). The
first-impact frame and which ball hits which stay the same.

## Cases

The builder's native source case is `pool_break_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Cue ball at 3.6 m/s, contact offset 3 mm |
| `edit_power_break` | `SET cue_ball.initial_velocity TIMES 2.5` | Cue speed 3.6 → 9.0 m/s |
| `edit_cut_left` | `SET cue_ball.contact_offset TO -0.0143 HINT "向左偏"` | Contact offset 0.003 → −0.0143 m |
| `edit_cut_right` | `SET cue_ball.contact_offset TO 0.0143 HINT "向右偏"` | Contact offset 0.003 → 0.0143 m |
| `edit_light_cue` | `SET cue_ball.mass TIMES 0.3` | Cue mass 0.17 → 0.051 kg |
| `edit_dead_rack_timed` | `SET rack.restitution TIMES 0.1 AT FRAME 13` | Rack ball restitution 0.93 → 0.093 from frame 13 |
| `edit_delete_apex_ball` | `DELETE apex_ball` | Yellow ball removed from frame 1 |
| `edit_delete_cue_ball` | `DELETE cue_ball` | White cue ball removed from frame 1 |

## Assets

- `models` (manual): `pool_table_animation.glb`, the table and numbered balls.
- `polyhaven/pool_break` (url): the lamp, sconces, barrel, stools and wall clock models, the room
  textures and the window photograph.

Download and check them with `python3 scripts/download_assets.py --scene pool_break`
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
python3 scripts/download_assets.py --scene pool_break --check

# List the native case IDs
python3 scripts/rigid_rigid/pool_break/build_pcve_pool_break.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/pool_break/build_pcve_pool_break.py \
    --out-root renders/pool_break/suite_build --simulate-only

# Render the simulated cases at the published resolution
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/pool_break/build_pcve_pool_break.py \
    --out-root renders/pool_break/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720 --samples 48
```

`tools/render_queue.py` (workflow `batch_render`) samples cue speed, contact offset and cue mass from
`--seed-base` into `renders/batch_pool_break`.

## Outputs

The commands above write to `renders/pool_break/suite_build/`, one directory per case under
`cases/`. Without `--out-root` the builder writes to
`renders/pool_break/suite_build/pcve_pool_break_suite/`. The published suite is
`renders/pcve_suites/pcve_pool_break_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_pool_break.py`: suite builder; runs the simulation and render for each case.
- `simulate_pool_break.py`: PyBullet solve with cloth drag and rolling orientations; writes
  `physics_transforms.json`.
- `render_pool_break.py`: Blender replay and render, camera rigs; writes the video, ground truth and
  checks.
- `scene_config.py`: table geometry, rack layout, editable and fixed physics, render defaults and
  validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/validate_pool_break.py`: acceptance checks on a solved case.
- `appearance/billiard_room.py`: room, lamp, sconces, window, props and the clearance and
  line-of-sight checks.
- `appearance/table_model.py`: table model import, fit to the solver planes, materials and numbered
  ball meshes.
- `tools/render_queue.py`: randomised batch builder.

## Limitations

- Pockets are not modelled; the cushions are flat walls at the cushion noses.
- Cloth rolling resistance is a constant deceleration applied outside the solver, and the rendered
  spin is reconstructed from the path rather than taken from Bullet.
- The sample count used for the published videos is not recorded in the suite.
