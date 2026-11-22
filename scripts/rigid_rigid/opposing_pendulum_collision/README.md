# opposing_pendulum_collision

Two balls hang on cords from an aluminium frame on a table. They are pulled out to mirror-image 35°
angles, released from rest at the same time, collide head-on near the bottom and swing back. A NumPy
rigid-body and cord solver that ships with the scene computes the motion; Blender replays the solved
poses. Rigid–rigid scene of PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Units and axes: SI, Z up, gravity −9.81 m/s².
- Balls: red `B_left` and blue `B_right`, 60 mm diameter, 120 g, uniform solid inertia
  `I = 0.4 m r²`, sphere colliders, glossy pigmented ABS (IOR 1.53, roughness 0.10–0.17), no printed
  numbers. Each ball is a free six-degree-of-freedom body released from rest.
- Cords: anchors at x = ±0.03 m, y = 0, z = 1.60 m; length 0.5635 m to an eyelet 0.0365 m above the
  ball centre, so the anchor-to-centre distance at release is 0.600 m. Rendered as 1 mm braided cord.
- Frame and table: 30 × 30 mm slot-8 anodized aluminium posts (x = ±0.70 m) and beam (centre at
  z = 1.640 m) whose visible size equals their collision boxes, a 1.54 × 0.35 × 0.025 m plywood base,
  and a table with a steel base and a five-board scanned timber top (collision box
  1.86 × 0.88 × 0.036 m, top at 0.76 m). A brass-and-glass hourglass, a notebook and a tape measure
  on the table are decoration and do not collide; the tape measure's printed label patch
  (`tape_label_uv_rect`) is painted plain black.
- Room (preset `furnished_daylight_room`): plaster walls, scanned wood floor (1.70 m tile), a
  steel-frame shelf cabinet with a wicker basket and a succulent on its shelves against the rear
  wall, and a floor plant in the rear-left corner, all more than 2 m behind the swing plane and placed
  by ray casting onto their supports. Light comes only from the overcast `suburban_field_01` sky
  through four window openings (one in frame at the rear, two in the left wall, one behind the
  camera), each with a Cycles portal; there are no lamps.
- Camera: location (0.62, −2.80, 2.05) looking at (0, 0.04, 1.20), 45 mm lens, 36 mm sensor, f/4
  focused at (0, 0, 1.10).
- Render: Blender 4.3, Cycles, 256 samples, adaptive threshold 0.01, OpenImageDenoise, AgX,
  +5.7 EV, 7000 K white balance, 0.5-frame shutter, vignette 0.18. Persistent data is
  off while motion blur is on.

All inputs live in `scene_config.py`, split into `physics`, `simulation_quality`, `appearance` and
`render`, together with the case overrides.

## Physics

- Solver: `physics/rigid_solver.py`, a NumPy rigid-body solver with tension-only cords. Step
  dt = 1/15360 s (24 fps × 640 substeps), up to 32 iterations per step, trajectories sampled at
  240 Hz. Video frame i is the solver state at t = (i−1)/24.
- Cords: massless, inextensible and tension-only (`|p + R a − A| ≤ L`, so they can go slack). A
  passive zero-stiffness bending damper at the eyelet (rate 30 s⁻¹, normalized by the effective
  inertia) acts only while the cord is taut, never adds energy and leaves spin about the cord axis
  free.
- Contact: ball–ball pair restitution 0.90 and friction 0.12; ball–base 0.22 / 0.35; ball–table
  0.28 / 0.32 (restitution / friction). Restitution is off below 0.015 m/s approach speed. Contact
  activates only at a non-positive sphere gap.
- Drag: linear 0.012 s⁻¹ and angular 0.008 s⁻¹ on each ball.
- `--stage graybox` runs the mass and restitution sweeps and a step-size comparison at half and
  double the formal substeps (1/7680 s and 1/30720 s).

## Validation

The build stops when a case fails `physics/validate_opposing_pendulum_collision.py`: cord extension
below 1 µm and penetration below 0.6 mm over the whole clip, total mechanical energy checked against
the passive damping at every substep, and a wobble limit relative to the cord (below 1.5° from 0.15 s
after each contact for the source, 2.5° for `edit_heavy_left`; measured by
`physics/motion_metrics.py`). `edit_heavy_left` must match the source before impact,
`edit_remove_right` must cross the middle and `edit_remove_left_rope` must land on the base or table.
The verify stage checks full decode, resolution, frame rate and frame count of every video.

## Cases

Every edit is applied before the simulation starts. `edit_vocab.py` holds the DSL vocabulary, the
statement of each case and the source prompts; `edit_vocab.edit_info` checks that each statement
produces exactly the case configuration in `scene_config.py`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Symmetric head-on collision near the bottom; each ball swings back about 8.7 cm |
| `edit_heavy_left` | `SET B_left.mass TIMES 3` | `B_left` mass 0.12 → 0.36 kg (inertia scaled with it) |
| `edit_low_restitution` | `SET B_left.restitution TIMES 0.27777777777777779` | Ball–ball pair restitution 0.90 → 0.25 |
| `edit_remove_right` | `DELETE B_right` | `B_right` and its cord absent from frame 1 |
| `edit_remove_left_rope` | `DELETE B_left_rope` | Left cord absent; the red ball falls freely from its release pose |

The ball–ball restitution is a pair value; the DSL binds it to the left ball.

## Assets

- `blenderkit/pendulum_wood_metal_table` (manual): steel table base.
- `blenderkit/pendulum_sliding_window` (manual): the four windows.
- `architecture_pbr/white_stucco` (derived): wall plaster.
- `polyhaven/wood_table_001` (url): table top.
- `polyhaven/plywood` (url): frame base.
- `polyhaven/measuring_tape_01` (url): tape measure on the table.
- `polyhaven/suburban_field_01` (url): sky seen through the windows, the only light source.
- `polyhaven/wood_floor` (url): room floor.
- `polyhaven/drawer_cabinet` (url): shelf cabinet at the rear wall.
- `polyhaven/wicker_basket_01` (url): basket on a cabinet shelf.
- `polyhaven/potted_plant_04` (url): succulent on a cabinet shelf.
- `polyhaven_models/potted_plant_01` (url): floor plant.

The `asset_manifest.json` files of these entries are hashed into the build's
`implementation_manifest.json`. Download and check them with
`python3 scripts/download_assets.py --scene opposing_pendulum_collision` (add `--check` to only
report). Manual files need a provider account; the script prints the page and file name to save.

## Requirements

- Python: `.venv-domino` in the repository root, or any environment with `requirements.txt`
  (`numpy==1.26.4`, `Pillow==11.3.0`). The simulation runs on the CPU.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU, CPU works but
  is slow. `ffmpeg`/`ffprobe` for encoding and the video check.

## Commands

Run from the repository root. The builder needs an empty or matching `--out-root`; use a new one
whenever a physics input changes.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene opposing_pendulum_collision --check

# List the cases and print the plan
.venv-domino/bin/python scripts/rigid_rigid/opposing_pendulum_collision/build_pcve_opposing_pendulum_collision.py --list-cases
.venv-domino/bin/python scripts/rigid_rigid/opposing_pendulum_collision/build_pcve_opposing_pendulum_collision.py \
    --out-root renders/opposing_pendulum_collision/suite_build --dry-run

# Simulate and validate all five cases on the CPU
.venv-domino/bin/python scripts/rigid_rigid/opposing_pendulum_collision/build_pcve_opposing_pendulum_collision.py \
    --out-root renders/opposing_pendulum_collision/suite_build --stage simulate

# Render, then verify the videos
.venv-domino/bin/python scripts/rigid_rigid/opposing_pendulum_collision/build_pcve_opposing_pendulum_collision.py \
    --out-root renders/opposing_pendulum_collision/suite_build --stage render \
    --blender tools/blender-4.3.2-linux-x64/blender
.venv-domino/bin/python scripts/rigid_rigid/opposing_pendulum_collision/build_pcve_opposing_pendulum_collision.py \
    --out-root renders/opposing_pendulum_collision/suite_build --stage verify

# Sweeps and step-size comparison, no rendering
.venv-domino/bin/python scripts/rigid_rigid/opposing_pendulum_collision/build_pcve_opposing_pendulum_collision.py \
    --out-root renders/opposing_pendulum_collision/suite_build --stage graybox
```

`--stage all` (the default) runs simulate, render and verify in order; `--cases` selects cases and
`--skip-existing` reuses finished cases. The graybox stage writes to `<out-root>/graybox/`.

## Outputs

The commands above write to `renders/opposing_pendulum_collision/suite_build/`: `suite_manifest.json`,
`implementation_manifest.json` and one directory per case under `cases/` with `video.mp4`,
`physics_transforms.json`, `trajectory.csv`, `physics_validation.json`, `config_diff.json`,
`prompts.json`, `settings.json`, `contacts.json`, `ground_truth_transforms.json`, the saved `.blend`
and the rendered frames. The published suite is
`renders/pcve_suites/pcve_opposing_pendulum_collision_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_opposing_pendulum_collision.py`: suite builder with stages `simulate`, `render`,
  `verify`, `all` and `graybox`.
- `simulate_opposing_pendulum_collision.py`: runs the solver for one scenario; writes
  `physics_transforms.json` and `trajectory.csv`.
- `render_opposing_pendulum_collision.py`: Blender replay and render.
- `scene_config.py`: all physical, numerical, appearance and render inputs and the cases.
- `edit_vocab.py`: edit DSL vocabulary, statements and prompts.
- `physics/rigid_solver.py`: rigid-body, cord and contact solver.
- `physics/motion_metrics.py`: wobble and motion measurements.
- `physics/validate_opposing_pendulum_collision.py`: physics acceptance checks.
- `physics/graybox_opposing_pendulum_collision.py`: mass and restitution sweeps and step-size
  comparison.
- `appearance/look_opposing_pendulum_collision.py`: Blender look (preset
  `furnished_daylight_room`).

## Limitations

- The cords have no mass, bending stiffness or self-contact; the bending damper is a
  phenomenological loss, not calibrated against a real cord.
- Restitution and friction are effective parameters, not measured for real ABS balls.
- Window glass is a thin Fresnel approximation.
- The solver reports `minimum_tension_N` but never updates it, so it stays 0 and the
  `nonnegative_tension` check always passes; cord slack is tracked separately (`slack_substeps`).
- CPU renders of the same frame can differ by up to two intensity levels in a few hundred pixels
  between runs.
