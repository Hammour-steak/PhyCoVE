# soccer_step_collision

A soccer ball rolls across the paving of a sunlit school courtyard, climbs a low kerb step onto a
stone terrace and strikes a basketball resting there, which rolls away. Rigid–rigid scene of
PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Balls: a soccer ball (`cheap_soccer_ball.glb`, PU cover with a thin clear coat), collision radius
  0.11 m, mass 0.43 kg, starting at x = −1.55 m with 1.95 m/s along +x; a basketball
  (`basketball.glb`, pebbled rubber), radius 0.12 m, mass 0.62 kg, at rest on the terrace at
  x = 0.82 m. Both are on the lane y = −0.18 m.
- Ground: interlocking concrete pavers (`concrete_pavers`, tiled at 1.92 m) on the top of the
  solver's `floor` slab (z = 0).
- Step: a row of precast concrete kerbstones (`brushed_concrete`, 1.0 × 0.25 m each). Their front
  face is the x = 0 face of the solver's `platform` and their top is the terrace at z = step height
  (0.045 m). The 8 mm joints sit 0.5 m to either side of the ball lane; the rendered edges have a
  1.5 mm bevel, the solver edge is square.
- Terrace: large grey stone slabs (`large_grey_tiles`), the top of `platform`.
- Background: yellow-brick school walls (`yellow_brick`) above a stone plinth whose front faces
  coincide with the solver's `back_wall` and `right_wall`; aluminium windows with coated clear glass
  and a lit classroom behind them; a downpipe in the inside corner. The solver's left wall
  (x = −3.8 m) is out of frame and is not drawn.
- Props (not simulated): a utility cabinet, a red plastic crate and a broom against the walls, about
  2.6 m from the nearest ball position in any case.
- Lighting: the Poly Haven HDRI `quadrangle_sunny`. Its sun is cut out of the map and replaced by a
  sun lamp with the same elevation (58.6°), colour and irradiance, turned to azimuth 208° (behind
  the camera on the left). The sky is visible to reflection rays only.
- Camera: location (−2.6, −5.5, 2.15) looking at (0.55, 0.1, 0.35), 48 mm lens.
- Render: Cycles, AgX Medium High Contrast, exposure 0, motion blur with a 0.5-frame shutter,
  persistent data off.

## Physics

- Solver: PyBullet, 1440 Hz fixed step, 100 solver iterations, restitution velocity threshold
  0.02 m/s, deterministic overlapping pairs. The builder runs the solve in-process.
- Ground, step and walls: boxes with lateral friction 0.65, restitution 0.22, rolling friction
  0.0015, collision margin 0.1 mm.
- Balls: spheres with thin-spherical-shell inertia (2/3 m r²), lateral friction 0.8, restitution
  0.72 (soccer ball) and 0.78 (basketball), no damping, swept-sphere CCD. The soccer ball starts
  rolling without slip.
- PyBullet multiplies the two restitution values of a contact, so the soccer ball meets the kerb
  with an effective restitution of about 0.16.
- Editable parameters (`scene_config.LIMITS`): both masses, launch speed, step height, terrace
  rolling friction, both ball restitutions, and the timed-edit schedule.
- The baseline must climb the step and then hit the basketball; the builder stops otherwise.
- Two simulation runs on the same machine are byte-identical. Largest penetration 1.2 mm, no
  energy gain.

## Measured motion

Effect of the ground/step restitution on the source and `edit_step_height_x2` (all six cases
re-run per value; the scene uses 0.22):

| Ground/step restitution | Source | `edit_step_height_x2` |
| --- | --- | --- |
| 0.22 | climbs the step, hits the basketball at frame 39 | stops against the kerb from frame 30 |
| 0.6 | climbs the step, hit at frame 50 | bounces back to x = −0.32 m |
| 0.8 | does not climb the step, no hit | bounces back to x = −0.74 m |
| 1.0 | climbs the step, hit at frame 65 | bounces back to x = −1.28 m |

## Validation

At render time `check_props()` requires every prop to stay at least 2 cm from both balls and off the
camera's line of sight to each ball centre on every frame, and stops with an error otherwise.

## Cases

The builder's native source case is `soccer_step_collision_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Soccer ball at 1.95 m/s climbs the 0.045 m step and hits the basketball |
| `edit_soccer_mass_x3` | `SET soccer.mass TIMES 3` | Soccer ball mass 0.43 → 1.29 kg |
| `edit_basketball_mass_x3` | `SET basketball.mass TIMES 3` | Basketball mass 0.62 → 1.86 kg |
| `edit_soccer_speed_x05` | `SET soccer.initial_velocity TIMES 0.5` | Soccer ball launch speed 1.95 → 0.975 m/s |
| `edit_step_height_x2` | `SET platform.height TIMES 2` | Step height 0.045 → 0.09 m |
| `edit_soccer_speed_halved_midrun` | `SET soccer.speed TIMES 0.5 AT FRAME 18` | Soccer ball speed 1.95 → 0.975 m/s from frame 18; it rolls on from that state |
| `edit_delete_basketball` | `DELETE basketball` | Basketball removed from frame 1 |
| `edit_delete_soccer` | `DELETE soccer` | Soccer ball removed from frame 1 |

## Assets

- `models` (manual): `cheap_soccer_ball.glb` and `basketball.glb`.
- `polyhaven/soccer_step_collision` (url): the HDRI, the paving, kerb, terrace and brick scans and
  the prop models.
- `polyhaven/large_grey_tiles` (manual): the terrace slab textures.
- `scenes/soccer_step_collision` (derived): `assets/scenes/soccer_step_collision/ASSET_SOURCES.json` (asset sources) and
  `assets/scenes/soccer_step_collision/scenario.json`.

Download and check them with `python3 scripts/download_assets.py --scene soccer_step_collision`
(add `--check` to only report).

## Requirements

- Simulation: Python with `pybullet` (`requirements.txt`; the repository's `.venv-domino` has it).
  CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`). The builder renders on the CPU by
  default (`--device cpu`, 4 threads); `--device auto` uses a GPU when Blender finds one.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene soccer_step_collision --check

# List the native case IDs
python3 scripts/rigid_rigid/soccer_step_collision/build_pcve_soccer_step_collision.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/soccer_step_collision/build_pcve_soccer_step_collision.py \
    --out-root renders/soccer_step_collision/suite_build --simulate-only

# Render the simulated cases at the published resolution
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/soccer_step_collision/build_pcve_soccer_step_collision.py \
    --out-root renders/soccer_step_collision/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720 --samples 48
```

## Outputs

The commands above write to `renders/soccer_step_collision/suite_build/`, one directory per case
under `cases/`. Without `--out-root` the builder writes to
`renders/soccer_step_collision/suite_build/pcve_soccer_step_collision_suite/`. The published suite
is `renders/pcve_suites/pcve_soccer_step_collision_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_soccer_step_collision.py`: suite builder; simulates each case in-process and calls the
  renderer.
- `simulate_soccer_step_collision.py`: PyBullet solve; writes `physics_transforms.json`.
- `render_soccer_step_collision.py`: Blender replay and render; writes the video, ground truth and
  render checks.
- `scene_config.py`: physics, render and camera defaults, limits and scenario validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/scene_geometry.py`: ball radii, start positions, room and step boxes shared by solver and
  renderer.
- `physics/validate_soccer_step_collision.py`: checks on the cached simulation.
- `appearance/look_soccer_step_collision.py`: courtyard, sky, materials and props.

## Limitations

- `simulation_signature` hashes the scene's `.py` files, including `appearance/`, so any code change
  invalidates cached simulations.
- Whether the soccer ball climbs the step and when it hits the basketball depend strongly on the
  ground/step restitution (see Measured motion).
- After repeated bounces off the kerb, the half-speed cases are sensitive to the floating-point
  behaviour of the PyBullet build; a Windows build differs from Linux by up to 1.0e-2 in
  `edit_soccer_speed_x05` and 3.6e-3 in `edit_soccer_speed_halved_midrun`, with the same order of
  events.
