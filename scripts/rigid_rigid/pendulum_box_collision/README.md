# pendulum_box_collision

A pine block slides along a lab bench and meets a swinging steel pendulum bob head-on just as the bob
returns to the bottom of its arc; the two bounce apart and the block slides on. Rigid–rigid scene of
PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Bench: slab 2.6 × 1.0 × 0.08 m, top face at z = 0.76 m, varnished sapele (`sapele_veneer_02`).
  The back wall is painted worn brick (`painted_worn_brick`) with a 7 cm sapele upstand.
- Block: lab slider, 12 × 7 × 8.5 cm, 0.40 kg, `coated_pine` scan lightened to natural pine, 2.5 mm
  bevelled edges. It starts outside the frame, 0.70 m (`APPROACH_DISTANCE`) before the contact
  position, moving along +x at 1.30 m/s.
- Pendulum: polished steel ball of radius 24 mm, 0.40 kg, on a 0.36 m dark braided thread; the bob
  hangs 10 mm above the bench and starts at the lowest point moving at 0.55 m/s. A retort stand holds
  the thread: the cross-bar runs along x to above the pendulum, then a right-angle double clamp and a
  short rod along −y reach the suspension point `scene_geometry.PIVOT`. The stand base is at
  y = 0.19 m, about 8 cm from the block's track.
- Props (not simulated): a twin-bell alarm clock (dial cover replaced by thin glass), a brass compass
  and a ring binder at the back of the bench, all Poly Haven scans. A prop check
  (`verify_dressing`) keeps every prop at least 2 cm from the block, bob and thread and off every
  body's line of sight to the camera.
- Light: ceiling LED troffers and low afternoon sun at 17° elevation through two windows in the left
  wall (sun lamp, Nishita sky, window portals); the windows are out of frame. Environment theme
  `physics_teaching_lab_painted_brick`.
- Camera: orthographic, location (0.68, −2.28, 1.20) looking at (−0.02, 0.03, 0.925),
  `ortho_scale` 1.06.
- Render: Cycles (128 samples by default), AgX Base Contrast, exposure 0, motion blur with a
  0.5-frame shutter, persistent data off.

## Physics

- Solver: PyBullet, 4800 Hz, 100 solver iterations. Gravity −9.81 m/s².
- The bob is a free rigid sphere held by a `JOINT_POINT2POINT` constraint to a massless anchor at the
  pivot; rod stretch stays below 1 mm.
- Friction: block 0.30 × bench 0.16 = 0.048 effective (deceleration 0.47 m/s²); bob 0.25.
  Block–bench restitution 0.02. Pair restitution between bob and block 0.55 (each body gets the
  square root).
- The start position makes the block reach the bob after half a pendulum period (0.605 s).
- Editable: bob mass and speed, block mass and speed (limits 0.05–5.0 kg, 0–0.90 m/s, 0.05–5.0 kg,
  1.12–3.5 m/s) and the pair restitution (0.05–0.92, used by the timed edit).

## Measured motion

- Source: first contact at 0.603 s, measured restitution 0.540.
- Two consecutive runs on Linux with PyBullet 3.2.7 give byte-identical `physics_transforms.json` and
  `simulation_metrics.json`.

## Cases

The builder's native source case is `pendulum_box_collision_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Block at 1.3 m/s meets the bob swinging at 0.55 m/s |
| `edit_heavy_bob` | `SET bob.mass TIMES 10` | Bob mass 0.4 → 4.0 kg |
| `edit_still_bob` | `SET bob.initial_velocity TO 0` | Bob initial speed 0.55 → 0 m/s |
| `edit_heavy_block` | `SET wooden_block.mass TIMES 5` | Block mass 0.4 → 2.0 kg |
| `edit_fast_block` | `SET wooden_block.initial_velocity TIMES 2.5` | Block initial speed 1.3 → 3.25 m/s |
| `edit_soft_bounce_timed` | `SET pair.restitution TIMES 0.1 AT FRAME 18` | Pair restitution 0.55 → 0.055 from frame 18 |
| `edit_delete_bob` | `DELETE bob` | Pendulum bob removed from frame 1 |
| `edit_delete_wooden_block` | `DELETE wooden_block` | Wooden block removed from frame 1 |

## Assets

- `polyhaven/pendulum_box_collision` (url): the alarm clock, compass and binder models and the bench,
  wall and block textures.

Download and check them with `python3 scripts/download_assets.py --scene pendulum_box_collision`
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
python3 scripts/download_assets.py --scene pendulum_box_collision --check

# List the native case IDs
python3 scripts/rigid_rigid/pendulum_box_collision/build_pcve_pendulum_box_collision.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/pendulum_box_collision/build_pcve_pendulum_box_collision.py \
    --out-root renders/pendulum_box_collision/suite_build --simulate-only

# Render the simulated cases (1280×720, 128 samples by default)
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/pendulum_box_collision/build_pcve_pendulum_box_collision.py \
    --out-root renders/pendulum_box_collision/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation
```

`tools/render_queue.py` (workflow `batch_render`) builds randomised variants from `--seed-base`.

## Outputs

The commands above write to `renders/pendulum_box_collision/suite_build/`, one directory per case
under `cases/`. Without `--out-root` the builder writes to
`renders/pendulum_box_collision/suite_build/pcve_pendulum_box_collision_suite/`. The published suite
is `renders/pcve_suites/pcve_pendulum_box_collision_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_pendulum_box_collision.py`: suite builder; runs the simulation and render for each case.
- `simulate_pendulum_box_collision.py`: PyBullet solve; writes `physics_transforms.json`.
- `render_pendulum_box_collision.py`: Blender replay and render; writes the video, ground truth and
  checks.
- `scene_config.py`: editable physics parameters, limits, render and camera defaults, validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/scene_geometry.py`: bench, block, bob and pivot dimensions shared by solver and renderer.
- `physics/validate_pendulum_box_collision.py`: acceptance checks on a solved case.
- `scripts/pcve_windows_dll_paths.py` (shared): adds the conda `Library/bin` to the DLL search path on Windows.
- `appearance/look_pendulum_box_collision.py`: lab room, stand, bodies, props, lighting and the prop
  checks.
- `appearance/render_quality.py`: Cycles, denoiser and motion-blur settings.
- `tools/render_queue.py`: randomised batch builder.

## Limitations

- The effective block–bench friction (0.048) is lower than pine on wood (about 0.2–0.4).
- The thread is a rigid point-to-point constraint; it does not go slack.
- PyBullet builds differ slightly across platforms in the block's sliding and tumbling: against a
  Windows build three cases match to ≤ 6e-11, the source and `edit_still_bob` differ by at most
  2.0e-5 m, and `edit_heavy_bob` differs by up to 1.7e-3 m after the block has slid off the bench end,
  out of frame.
- The sample count used for the published videos is not recorded in the suite.
- CPU renders of the same frame can differ by one intensity level in a few pixels between runs.
