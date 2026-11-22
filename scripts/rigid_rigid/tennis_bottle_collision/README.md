# tennis_bottle_collision

A tennis ball rolls across the parquet floor of a living room into two empty plastic bottles
standing side by side and knocks them over. Rigid–rigid scene of PhyCoVE. Source video: 4 s,
24 fps, 96 frames, 1280×720.

## Scene

- Tennis ball: radius 33.5 mm, mass 0.057 kg, starting at x = −0.52 m and rolling along +x at
  0.85 m/s.
- Bottles: two empty, capped PET bottles (radius 41 mm, height 0.23 m, mass 0.026 kg: 24 g body and
  2 g cap) standing upright at x = 0, y = ±0.0415 m (83 mm apart). The rendered mesh has an empty air
  cavity and a PET wall whose mass matches the physics (`physics/empty_bottle_geometry.py`,
  `physics/empty_bottle_validation.py`); the centre-of-mass height comes from
  `assets/scenes/tennis_bottle_collision/empty_bottle_properties.json`. A third slot, `bottle_added`, is absent unless an ADD edit
  enables it.
- Room: inner wall faces at x −2.6…4.6 m and y −2.4…3.8 m, ceiling 2.6 m (`room` in
  `scene_config.py`). The simulator places walls on these planes and `appearance/room_box.py`
  builds the room on them: the skirting face is the collision plane and the plaster sits one board
  thickness behind it. Neither the ball nor the bottles reach a wall in any case.
- Furnishing (not simulated): a small grey sofa with orange cushions, a coffee table on a checked wool
  rug, a side table, a rattan basket, a dark glass-fronted hutch, a leather armchair and a potted
  plant; herringbone parquet floor (texture at its real size of 3.4 m, roughness floor 0.38). The rug
  is more than 1.5 m from the moving bodies, which only touch the wooden floor.
- Lighting: daylight only. A wide south window behind the camera lets low sun cross the floor onto the
  ball and bottles, and a west window adds fill; a sun lamp and a Nishita sky, with a garden photo
  outside the window visible to camera rays only. The PET bottles pass 70 % of shadow rays.
- Camera: location (−0.9, −0.7, 0.40) looking at (0.15, 0.06, 0.1), 25 mm lens.
- Render: Cycles, AgX Base Contrast, exposure +1 EV, motion blur with a 0.5-frame shutter,
  persistent data off.

## Physics

- Solver: PyBullet DIRECT, 1440 Hz fixed step, 120 solver iterations, restitution velocity threshold
  0.015 m/s, contact breaking threshold 0.2 mm, deterministic overlapping pairs, gravity −9.81 m/s².
  The builder runs the solve in-process.
- Floor: box, lateral friction 1.0, restitution 0.25. Walls: boxes, friction 0.5, restitution 0.15.
- Ball: sphere, friction 0.42, restitution 0.65, rolling friction 0.0014. Bottles: convex hull of the
  bottle profile (80 segments), friction 0.32, restitution 0.55, rolling friction 0.0008. Both have
  spinning friction 0.001, angular damping 0.005 and collision margin 0.05 mm.
- Timed edits may change only `bottle_mass` and `bottle_restitution`, from frame 2 to 96.

## Validation

`room_box.check_clearance` checks the bounding spheres of the ball and bottles against every piece of
furniture on every frame and stops the render below 2 cm.

## Cases

The builder's native source case is `tennis_bottle_collision_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Ball at 0.85 m/s knocks over both bottles |
| `edit_fast_ball` | `SET tennis_ball.initial_velocity TIMES 3` | Ball speed 0.85 → 2.55 m/s |
| `edit_heavy_bottles` | `SET bottles.mass TIMES 10` | Bottle mass 0.026 → 0.26 kg |
| `edit_remove_far_bottle` | `DELETE bottle_right` | Right bottle absent from frame 1 |
| `edit_add_lane_bottle` | `ADD bottle_added BETWEEN tennis_ball AND bottle_left AT MIDPOINT` | A third bottle stands halfway between the ball and the left bottle |
| `edit_heavy_bottles_midfall` | `SET bottles.mass TIMES 10 AT FRAME 16` | Bottle mass 0.026 → 0.26 kg from frame 16 |
| `edit_remove_tennis_ball` | `DELETE tennis_ball` | Tennis ball removed from frame 1 |

## Assets

- `models` (manual): `tennis_ball.glb` and `plastic_water_bottle.glb`.
- `polyhaven/tennis_bottle_collision` (url): parquet, rug and wall scans and the furniture models.
- `polyhaven/door_basketball_collision` (url): the garden photo outside the window, shared with
  door_basketball_collision.
- `scenes/tennis_bottle_collision` (derived): `assets/scenes/tennis_bottle_collision/empty_bottle_properties.json` (bottle mass and
  centre of mass, read by the solver), `assets/scenes/tennis_bottle_collision/empty_bottle_mesh_audit.json`, `assets/scenes/tennis_bottle_collision/asset_sources.json`,
  `assets/scenes/tennis_bottle_collision/ASSET_CREDITS.md` and `assets/scenes/tennis_bottle_collision/scenario.json`.

Download and check them with `python3 scripts/download_assets.py --scene tennis_bottle_collision`
(add `--check` to only report).

## Requirements

- Simulation: Python with `pybullet` (`requirements.txt`; the repository's `.venv-domino` has it).
  CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU for
  full-quality frames (`--device auto`), `--device cpu` for previews.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene tennis_bottle_collision --check

# List the native case IDs
python3 scripts/rigid_rigid/tennis_bottle_collision/build_pcve_tennis_bottle_collision.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/tennis_bottle_collision/build_pcve_tennis_bottle_collision.py \
    --out-root renders/tennis_bottle_collision/suite_build --simulate-only

# Render the simulated cases at the published resolution
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/tennis_bottle_collision/build_pcve_tennis_bottle_collision.py \
    --out-root renders/tennis_bottle_collision/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720
```

`tools/render_queue.py` (workflow `batch_render`) samples the ball speed from `--seed` and builds
`--count` variants into `renders/tennis_bottle_batch`.

## Outputs

The commands above write to `renders/tennis_bottle_collision/suite_build/`, one directory per case
under `cases/`. Without `--out-root` the builder writes to
`renders/tennis_bottle_collision/suite_build/pcve_tennis_bottle_collision_suite/`. The published
suite is `renders/pcve_suites/pcve_tennis_bottle_collision_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_tennis_bottle_collision.py`: suite builder; simulates each case in-process and calls the
  renderer.
- `simulate_tennis_bottle_collision.py`: PyBullet solve; writes `physics_transforms.json`.
- `render_tennis_bottle_collision.py`: Blender replay and render; writes the video, ground truth and
  render checks.
- `scene_config.py`: physics, render, camera and room defaults and scenario validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/scene_geometry.py`: ball and bottle dimensions, bottle profile and layout.
- `physics/empty_bottle_geometry.py`: hollow PET bottle mesh and its mass.
- `physics/empty_bottle_validation.py`: checks the Blender bottle mesh (air cavity, wall mass).
- `physics/validate_tennis_bottle_collision.py`: checks on the cached simulation.
- `appearance/look_tennis_bottle_collision.py`: materials, light grade and motion blur.
- `appearance/room_box.py`: room, furniture, windows and the clearance check.
- `tools/render_queue.py`: randomised batch builder.

## Limitations

- The bottles are rigid convex hulls; they do not dent or flex.
- The furniture and rug are not part of the simulation; only the clearance check keeps the moving
  bodies away from them.
- PyBullet builds on other platforms differ in floating point; with the same code a Windows build
  topples the bottles differently, by up to about 0.6 m.
- The sample count of the published render is not recorded in the published data.
