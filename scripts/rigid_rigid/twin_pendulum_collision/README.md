# twin_pendulum_collision

Two pendulums hang side by side on a lab bench apparatus; the left (driver) bob is released from
32° and strikes the resting right (receiver) bob, which swings out, and the two keep exchanging
motion while air drag slowly damps them. Rigid–rigid scene of PhyCoVE. Source video: 4 s, 24 fps,
96 frames, 1280×720.

## Scene

- Pendulums: two bobs of radius 32 mm on 0.32 m rods, pivots 1.25 m above the floor and 86 mm apart
  (22 mm surface gap at rest). Driver bob 0.26 kg, released from rest at 32°; receiver bob 0.26 kg,
  hanging at rest. The bobs are red phenolic resin balls; rods and connectors are idealised as
  massless.
- Bench: top at 0.76 m, a 25 mm black epoxy worktop with a 100 mm upstand at the back running up to
  the wall. The apparatus (base, posts, bearings, scale, nameplate) has a grey hammer-finish base and
  a black anodised nameplate.
- Room: a university physics teaching lab. The wall is a concrete block wall in eggshell latex paint
  (normal and roughness of the `concrete_block_wall` scan tiled at their real 2 m size), with a
  metal-cased double socket.
- Props (not simulated): a laptop for logging data (scaled to 310 mm wide), a pocket watch lying face
  up, and a sheet of record paper with a ruled table (procedural).
- Lighting: two opal-diffuser fluorescent fittings on the ceiling (the diffusers emit), and low morning
  sun plus a Nishita sky through a window in the left wall, out of frame, with a portal in the window
  opening. AgX, exposure −0.5.
- Camera: location (0.68, −1.90, 1.36) looking at (−0.015, 0, 1.04), 55 mm lens.
- Render: Cycles, motion blur with a 0.5-frame shutter, persistent data off.

## Physics

- Solver: pure-Python constrained rigid-body dynamics, no PyBullet. Two generalized angles keep the
  rods planar and inextensible; RK4 integrates gravity (9.81 m/s²) and linear drag F = −c·v at
  4800 Hz (200 substeps per frame at 24 fps).
- Impacts: the contact time is bracketed by bisection and a frictionless normal impulse using both
  pivot inertias resolves the collision, including oblique contact and the pivot reaction. Pair
  restitution 0.92. Each body's inertia about its pivot is m(L² + 0.4 r²).
- Editable parameters: driver mass (0.08–0.80 kg), driver release angle (12–55°), drag coefficient
  (0–0.08) and receiver presence. The receiver mass is fixed. A timed DELETE removes the receiver at
  the top of the given frame and books its energy as removed.
- Re-running the solver reproduces the published ground truth of all six cases to a largest
  field-by-field difference of 4.4e-15; two runs agree.

## Validation

At render time `verify_props` requires the props to stand on the bench without overlapping each other
or the apparatus base, to stay at least 2 cm from the bobs and rods along the case's trajectory (all
six cases are at least 0.24 m), to lie outside the whole swing range the parameter limits allow, and
not to block the camera's rays to any bob or rod; otherwise the render fails.

## Cases

The builder's native source case is `twin_pendulum_collision_baseline`; it is published as
`source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Driver released from 32° strikes the resting receiver |
| `edit_heavy_driver` | `SET driver.mass TIMES 2` | Driver mass 0.26 → 0.52 kg |
| `edit_large_amplitude` | `SET driver.initial_angle_deg TIMES 1.5` | Driver release angle 32° → 48° |
| `edit_high_drag` | `SET pendulums.drag_coefficient TIMES 8` | Drag coefficient 0.006 → 0.048 |
| `edit_remove_receiver` | `DELETE receiver` | Receiver absent from frame 1 |
| `edit_remove_receiver_after_impact` | `DELETE receiver AT FRAME 18` | Receiver removed from frame 18 |
| `edit_remove_driver` | `DELETE driver` | Left red bob removed from frame 1 |

## Assets

- `models` (manual): registered for this scene in `assets.json`; the scene code reads no file from it.
- `polyhaven/twin_pendulum_collision` (url): the concrete block wall scan, the laptop and the pocket
  watch.

Download and check them with `python3 scripts/download_assets.py --scene twin_pendulum_collision`
(add `--check` to only report).

## Requirements

- Simulation: Python 3 standard library only (`requirements.txt` lists no packages). CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU for
  full-quality frames (`--device auto`), `--device cpu` for previews.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene twin_pendulum_collision --check

# List the native case IDs
python3 scripts/rigid_rigid/twin_pendulum_collision/build_pcve_twin_pendulum_collision.py --list-cases

# Simulate all six cases on the CPU
python3 scripts/rigid_rigid/twin_pendulum_collision/build_pcve_twin_pendulum_collision.py \
    --out-root renders/twin_pendulum_collision/suite_build --simulate-only

# Render the simulated cases at the published resolution
python3 scripts/rigid_rigid/twin_pendulum_collision/build_pcve_twin_pendulum_collision.py \
    --out-root renders/twin_pendulum_collision/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720
```

`tools/render_queue.py` (workflow `batch_render`) builds randomised variants from `--seed-base` into
`renders/batch_twin_pendulum_collision`.

## Outputs

The commands above write to `renders/twin_pendulum_collision/suite_build/`, one directory per case
under `cases/`. Without `--out-root` the builder writes to
`renders/twin_pendulum_collision/suite_build/pcve_twin_pendulum_collision_suite/`. The published
suite is `renders/pcve_suites/pcve_twin_pendulum_collision_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_twin_pendulum_collision.py`: suite builder; runs the simulation and render for each case.
- `simulate_twin_pendulum_collision.py`: constrained RK4 solve; writes `physics_transforms.json`.
- `render_twin_pendulum_collision.py`: Blender replay and render; writes the video, ground truth and
  render checks.
- `scene_config.py`: physics, render and camera defaults, limits and scenario validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/scene_geometry.py`: bob, rod, pivot and bench dimensions, restitution and physics clock.
- `physics/validate_twin_pendulum_collision.py`: checks on the cached simulation.
- `physics/input_hashes.py`: asset hashes used by the `--skip-existing` fingerprint.
  files, compared by `--skip-existing`.
- `appearance/look_twin_pendulum_collision.py`: lab room, apparatus, materials, lights, props and
  `verify_props`.
- `tools/render_queue.py`: randomised batch builder.

## Limitations

- Rods and connectors are massless, the bobs are frictionless at contact, and drag is linear in
  velocity.
- `simulation_signature` hashes every scene `.py`, including `appearance/`, so any code change
  invalidates cached simulations.
- CPU renders of the same frame differ between runs (up to 11 intensity levels in about a thousand
  channel values).
- The sample count of the published render is not recorded in the published data.
