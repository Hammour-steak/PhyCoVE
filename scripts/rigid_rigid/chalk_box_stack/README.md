# chalk_box_stack

A rigid–rigid scene in PhyCoVE. On a classroom bench a board eraser slides across the top and
swipes the bottom carton out from under a stack of two chalk boxes; the upper carton drops one
level and stops. PyBullet solves the contacts and Blender replays the solved poses. The source
video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- **Bodies:** two chalk cartons 0.12 × 0.085 × 0.08 m, 0.065 kg each, hand-stacked with a few
  millimetres of fixed offset and 1–2° of yaw per carton; a board eraser 0.13 × 0.075 × 0.032 m,
  2.5 kg, starting on the bench and launched at 2.8 m/s towards the bottom carton.
- **Bench:** a static 2.6 × 1.0 m slab with its top at z = 0.76 m on a static floor.
- **Recipe:** physics, render settings and camera come from
  `assets/scenes/chalk_box_stack/four_second.json`; `scene_config.py` reads it as the single
  source of the source video.
- **Camera:** a 40 mm perspective lens at f/8 from the front-left end of the bench (the `camera`
  entry of `assets/scenes/chalk_box_stack/four_second.json`), so the cartons' struck face is visible. `scene_config.validate`
  also accepts an orthographic camera with `ortho_scale`. The camera is stored with the physics
  cache, so moving it requires simulating again.
- **Room:** a closed classroom (both side walls, ceiling and the wall behind the camera). The bench
  is an oiled slab on an open black steel frame, topped with scanned oak veneer at real size; the
  floor is scanned grey checked tiles; a scanned blackboard hangs on the wall with its bottom rail
  10 cm below the bench top; a metre rule and a set square in varnished hardwood stand behind the
  contact lane; worksheets, a pen, loose chalk sticks, chalk crumbs and a water bottle dress the
  bench.
- **Cartons and eraser:** each carton is one dyed paperboard sheet (body, 1.3 mm groove and lid,
  0.35 mm crease edges, ink mottle, crushed fibre along the folds, matte knockout lettering). The
  eraser has a beech handle with grain in colour, roughness and relief and a charcoal felt sole.
- **Light:** six 1.2 × 0.3 m LED troffers in the ceiling whose diffusers emit, and overcast
  daylight through two windows in the left wall (Nishita sky, a portal in each window opening).
  There are no invisible fill lights.
- **Render:** Cycles with denoising and adaptive sampling (threshold 0.015), 180° shutter motion
  blur, AgX Base Contrast, 1280×720, 24 fps, 96 frames.

## Physics

- **Solver:** PyBullet at 2400 Hz (100 steps per frame), 100 solver iterations, contact breaking
  threshold 1 mm, collision margin 0.1 mm, gravity −9.81 m/s². 480 settling steps run before the
  eraser is launched. Frame i is the state at t = (i−1)/24 s; playback is real time.
- **Contact:** restitution 0.02 on every body. The cartons use a lateral friction of
  `sqrt(box_friction)` (box friction 0.3), so the box–box pair friction equals `box_friction`; the
  eraser friction is 0.42, the bench 0.65, the floor 0.8.
- **Timed edit:** a `timed_edits` schedule writes the new friction into the running bodies at the
  top of its frame through the same `sqrt` mapping; poses and velocities are read on both sides to
  show that only the coefficient changes.

## Measured motion

| Case | Measured outcome |
| --- | --- |
| `source` | the eraser reaches the bottom carton near frame 12 and pulls it out about 0.46 m; the upper carton drops one level and stops |
| `edit_fast_eraser` | contact near frame 6; the bottom carton and the eraser leave the bench and fall past the floor edge; the upper carton stays on the bench |
| `edit_slow_eraser` | bench friction stops the eraser before the stack; no contact, both cartons stay in place |
| `edit_slick_eraser` | the eraser barely slows, hits the bottom carton and pushes it more than 2.5 m |
| `edit_slippery_boxes` | the bottom carton slides about 0.93 m after extraction; the upper carton drops one level and settles |
| `edit_frictionless_midway` | frames 1–19 identical to the source; the bottom carton is pushed to the bench edge, falls off and ends 2.7 m away; the upper carton drops onto the bench in place |

## Validation

- `quality.hit_stack` requires a contact between eraser and bottom carton;
  `quality.upper_stack_preserved` requires the surviving carton to tilt less than 45°
  (`collapse_observed` is set above 60°). The builder rejects a source without both.
- Every edit must move a body more than 2 cm from its source path; for the timed edit, frames
  before the start frame must reproduce the source positions exactly.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source swipe |
| `edit_fast_eraser` | `SET eraser.initial_velocity TIMES 2` | Eraser speed 2.8 → 5.6 m/s |
| `edit_slow_eraser` | `SET eraser.initial_velocity TIMES 0.5` | Eraser speed 2.8 → 1.4 m/s |
| `edit_slick_eraser` | `SET eraser.friction TIMES 0.2` | Eraser friction 0.42 → 0.084 |
| `edit_slippery_boxes` | `SET chalk_boxes.friction TIMES 0.15` | Box friction 0.3 → 0.045 |
| `edit_frictionless_midway` | `SET chalk_boxes.friction TO 0 AT FRAME 20` | Box friction 0.3 → 0 from frame 20 (t = 0.792 s) |
| `edit_delete_eraser` | `DELETE eraser` | Board eraser removed from frame 1 |
| `edit_delete_bottom_box` | `DELETE bottom_box` | Bottom carton removed from frame 1 |

The builder names the source case `chalk_box_stack_baseline`; the edit IDs are the same as the
published case names. `edit_vocab.py` declares the vocabulary, the cases and the source prompts.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `models` (`realistic_blackboard.glb`, `the_pen.glb`, `chalk.glb`, `water_bottle__plastic_bottle.glb`) | manual | blackboard, pen, chalk sticks and water bottle |
| `polyhaven/chalk_box_stack` | url | oak veneer for the bench and drawing tools, grey floor tiles |
| `scenes/chalk_box_stack` | derived | `assets/scenes/chalk_box_stack/four_second.json`, the physics, render and camera recipe of the source video |

```bash
python3 scripts/download_assets.py --scene chalk_box_stack
python3 scripts/download_assets.py --scene chalk_box_stack --check
```

## Requirements

- Python with `pybullet==3.2.7` (`requirements.txt`); the repository's `.venv-domino/`
  environment has it.
- Blender 4.3.2 for rendering (`--blender`, or `--render-python` with the `bpy` module; otherwise
  `$BLENDER`, `blender` on `PATH` or `~/.local/opt/blender-*`).
- A GPU is optional (`--device auto` or `cpu`).

## Commands

Run from the repository root.

```bash
# case list
python3 scripts/rigid_rigid/chalk_box_stack/build_pcve_chalk_box_stack.py --list-cases

# physics for the source
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/chalk_box_stack/build_pcve_chalk_box_stack.py \
  --out-root renders/chalk_box_stack/new_run --simulate-only --cases chalk_box_stack_baseline

# physics and video for all six cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/chalk_box_stack/build_pcve_chalk_box_stack.py \
  --out-root renders/chalk_box_stack/new_run --mode animation \
  --blender tools/blender-4.3.2-linux-x64/blender

# one case solved on its own
.venv-domino/bin/python scripts/rigid_rigid/chalk_box_stack/simulate_chalk_box_stack.py \
  --out renders/chalk_box_stack/single/physics_transforms.json

# preview of one solved case
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
  --python scripts/rigid_rigid/chalk_box_stack/render_chalk_box_stack.py -- \
  --physics-json renders/chalk_box_stack/single/physics_transforms.json \
  --out-dir renders/chalk_box_stack/single --mode preview --device cpu
```

- Builder `--mode` is `animation` (default, writes `video.mp4`) or `preview`; `--cases` builds a
  subset; `--render-only` renders from existing caches; `--clean-stale-cases` removes case
  folders that are not in the current case list; `--dry-run` prints each case's commands.
- `tools/render_queue.py` (workflow `batch_render`) samples randomised scenarios on top of the
  builder (`--count`, `--start-index`, `--seed-base`).
- `--physics-python` and `--render-python` (or `PCVE_PHYSICS_PYTHON`, `PCVE_RENDER_PYTHON`) select
  the interpreters.

## Outputs

- A build writes `cases/<case>/` under `--out-root` (default
  `renders/chalk_box_stack/suite_build/pcve_chalk_box_stack_suite`) with `physics_transforms.json`,
  metrics and, after rendering, `video.mp4` and the render records, plus the suite manifest.
  `tools/render_queue.py` writes to `renders/batch_chalk_box_stack` by default.
- The published suite is `renders/pcve_suites/pcve_chalk_box_stack_suite/`; do not use it as an
  output root.

## Code layout

- `simulate_chalk_box_stack.py` — PyBullet solve of one case, including timed edits (public entry).
- `render_chalk_box_stack.py` — Blender replay and render (public entry).
- `build_pcve_chalk_box_stack.py` — source and edit suite builder with per-case checks (public entry).
- `scene_config.py` — scenario from `assets/scenes/chalk_box_stack/four_second.json`, merging and validation.
- `edit_vocab.py` — edit DSL vocabulary, case list and source prompts.
- `physics/scene_geometry.py` — carton, eraser and bench dimensions, masses and stacking layout.
- `physics/motion_analysis.py` — settling metrics of a solved case, including bodies that have left the view.
- `physics/validate_chalk_box_stack.py` — simulation signature and cache validation (rejects trajectories from different geometry, dynamics or timing).
- `scripts/pcve_windows_dll_paths.py` (shared) — on Windows, puts the conda `Library/bin` on the DLL search path before PyBullet loads (no effect elsewhere).
- `appearance/look_chalk_box_stack.py` — classroom, bench dressing, cartons, eraser and lighting.
- `appearance/render_quality.py` — Cycles and colour-management settings.
- `tools/render_queue.py` — randomised batch scenarios (workflow `batch_render`).
- `requirements.txt`, `entrypoints.json`, `scene_manifest.json` — dependencies and entry metadata.

## Limitations

- Cartons and eraser are rigid boxes; the cartons do not deform and the felt sole does not
  compress.
- One contact restitution (0.02) is used for every body.
- The bench is a single static box; the wall base under the bench edge is outside the frame.
