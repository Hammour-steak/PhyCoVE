# toy_car_collision

A small die-cast toy car slides across the oak floor of a children's room and rear-ends a larger
cartoon toy car standing in its lane, pushing it forward. Rigid–rigid scene of PhyCoVE. Source
video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Driver car (`car_a`): length 0.145 m, mass 0.065 kg, starting at x = −0.42 m with 0.95 m/s
  along +x. Receiver car (`car_b`): length 0.18 m, mass 0.110 kg, at rest at x = 0. Each physics box
  has the length/width/height proportions of its rendered model; the rendered wheels roll by the
  travelled arc length.
- Room (`appearance/kids_room.py`, layout in `ROOM` / `LOOK` of
  `appearance/look_toy_car_collision.py`): the floor top is the solver's ground plane z = 0. The
  skirting faces are at x = −1.60 / 2.30 m and y = −2.30 / 1.25 m, ceiling 2.60 m. The car lane is
  y ≈ 0, x from −0.49 m to at most 1.56 m (the receiver in `edit_driver_speed_x3`), at least 0.7 m
  from any wall.
- Materials: oak floor scan `wood_floor` (tiled at its real 1.7 m, boards along the direction of
  travel, roughness floor 0.32); light blue-grey painted walls with a few percent of tone and sheen
  variation; white skirting, ceiling and two double sockets.
- Furnishing (not simulated): a white painted cabinet, a wicker basket, a school desk with a white
  wooden chair, a low stool, a baseball and a ukulele leaning on the east wall, placed by
  bounding-box anchors.
- Lighting: daylight only. A sun lamp (elevation 30°, heading 12° off +x) and a Nishita sky with a
  sky portal in each of two windows. The west window (sill 0.60 m) is out of frame and casts a sun
  patch with window-bar shadows on the floor; both cars are in the patch from frame 1. The north
  window (sill 1.05 m) is above the frame and adds sky light.
- Camera: location (−0.25, −1.60, 0.70) looking at (0.60, 0, 0.04), 23 mm lens.
- Render: Cycles, AgX Medium High Contrast, exposure +0.2, motion blur with a 0.5-frame shutter,
  persistent data off.

## Physics

- Solver: PyBullet, 1440 Hz fixed step, 100 solver iterations, restitution velocity threshold
  0.005 m/s, contact breaking threshold 0.1 mm, deterministic overlapping pairs, gravity
  −9.81 m/s².
- Ground: a static plane, friction 0.5, restitution 0.
- Cars: free 6-DOF rigid boxes with no damping and collision margin 0.1 mm. Friction 0.12 (driver)
  and 0.14 (receiver) acts as the effective rolling drag at the floor. Car-to-car restitution 0.32
  (each body gets the square root, Bullet multiplies the two).
- Timed edits may change either car's friction or rescale the receiver's current velocity in place
  (`receiver_speed_multiplier`, 0.05–50); the run continues from the state reached.

## Validation

Before rendering, `check_clearance` replays the whole trajectory: each car's bounding sphere must stay
at least 2 cm from every furniture bounding box and from the four walls, and the furniture boxes must
not overlap each other; otherwise the render fails. The result is written as `prop_clearance_m` in
`render_validation.json`; over the six cases the closest piece is the stool, 0.25 m.

## Cases

The builder's native source case is `toy_car_collision_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Driver at 0.95 m/s rear-ends the resting receiver |
| `edit_driver_mass_x3` | `SET car_a.mass TIMES 3` | Driver mass 0.065 → 0.195 kg |
| `edit_driver_speed_x3` | `SET car_a.initial_velocity TIMES 3` | Driver launch speed 0.95 → 2.85 m/s |
| `edit_driver_friction_quarter` | `SET car_a.friction TIMES 0.25` | Driver friction 0.12 → 0.03 |
| `edit_delete_receiver` | `DELETE car_b` | Receiver absent from frame 1 |
| `edit_receiver_speed_boost_timed` | `SET car_b.speed TIMES 5 AT FRAME 16` | Receiver's current speed multiplied by 5 at frame 16 |
| `edit_delete_car_a` | `DELETE car_a` | Purple toy sports car removed from frame 1 |

## Assets

- `models` (manual): the two toy car models.
- `polyhaven/toy_car_collision` (url): the floor scan and the furniture models.
- `scenes/toy_car_collision` (derived): `assets/scenes/toy_car_collision/ASSET_SOURCES.json` (asset sources) and `assets/scenes/toy_car_collision/scenario.json`.

Download and check them with `python3 scripts/download_assets.py --scene toy_car_collision`
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
python3 scripts/download_assets.py --scene toy_car_collision --check

# List the native case IDs
python3 scripts/rigid_rigid/toy_car_collision/build_pcve_toy_car_collision.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/toy_car_collision/build_pcve_toy_car_collision.py \
    --out-root renders/toy_car_collision/suite_build --simulate-only

# Render the simulated cases at the published resolution
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/toy_car_collision/build_pcve_toy_car_collision.py \
    --out-root renders/toy_car_collision/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720
```

## Outputs

The commands above write to `renders/toy_car_collision/suite_build/`, one directory per case under
`cases/`. Without `--out-root` the builder writes to
`renders/toy_car_collision/suite_build/pcve_toy_car_collision_suite/`. The published suite is
`renders/pcve_suites/pcve_toy_car_collision_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_toy_car_collision.py`: suite builder; runs the simulation and render for each case.
- `simulate_toy_car_collision.py`: PyBullet solve; writes `physics_transforms.json`.
- `render_toy_car_collision.py`: Blender replay and render; writes the video, ground truth and
  render checks.
- `scene_config.py`: physics, render and camera defaults, limits and scenario validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/scene_geometry.py`: car dimensions, start positions, physics clock and fixed constants.
- `physics/validate_toy_car_collision.py`: checks on the cached simulation.
- `physics/input_hashes.py`: asset hashes used by the `--skip-existing` fingerprint.
  compares.
- `appearance/look_toy_car_collision.py`: room layout, car models and light grade.
- `appearance/kids_room.py`: room, windows, materials, furniture and the clearance check.
- `appearance/asset_import.py`: glTF import and wheel detection for the car models.

## Limitations

- The cars are boxes sliding on the floor; wheel rolling is approximated by a constant friction
  coefficient, and the rendered wheels turn by the travelled distance.
- The furniture is not part of the simulation; only the clearance check keeps the cars away from it.
- The sample count of the published render is not recorded in the published data.
