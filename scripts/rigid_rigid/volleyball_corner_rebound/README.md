# volleyball_corner_rebound

A volleyball is thrown diagonally down into the corner of a school sports store: it lands, hits the
`x = 0` wall and then the `y = 0` wall, picks up spin from the contact friction and rolls back out
of the corner. Rigid–rigid scene of PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Room: 10 × 8 × 3 m; the ball plays in the near corner. A 1.4 m window opening in the `x = 0` wall
  spans y = 1.8–3.2 m and holds an aluminium sliding window with thin glass; outside is the
  `autumn_park` HDRI, visible to camera rays only.
- Ball: radius 0.105 m, 0.27 kg, released at (4.8, 4.5, 2.3) m at 5.85 m/s along
  (−4.8, −3.2, −0.96), about 9° below horizontal, without spin.
- Static colliders: a light grey sheet-steel cabinet (1.5 × 0.20 × 0.42 m, centre
  (3.8, 0.11, 0.21)) whose carcass and doors fill the collision box, two spare volleyballs at
  (4.75, 0.30) and (4.95, 0.80) m on the floor, and a wall-mounted split air-conditioning unit
  (the imported model scaled uniformly by 2.26 to 1.20 m wide) on the window wall at y = 4.70 m with
  its underside 2.40 m up.
- Props (render only, Poly Haven scans): two steel shelving racks with plastic crates and a
  cardboard box, a wall clock, a framed notice (0.59 × 0.84 m) on the `y = 0` wall above the
  cabinet, and a school chair by the window wall.
- Surfaces: terrazzo floor from the `mixed_stone_tiles` scan (1.8 m per scan, roughness remapped to
  0.16–0.42), white textured paint (`white_stucco`) above a 1.10 m green gloss dado with a 12 cm dark
  skirting; the collision walls have no protrusions.
- Light: no lamp in the room. A warm sun lamp (strength 3.4) at the HDRI's sun elevation of 34.1°,
  a Nishita sky and sky portals on the window and on two out-of-frame windows behind the camera.
  AgX Base Contrast, exposure 2.8.
- Camera (`--camera-preset comparison`, default): fixed at (8.6, 7.6, 2.25) m aimed at
  (3.4, 3.5, 1.20) m, 38 mm lens; the ceiling shows as a band about 6 % high along the top edge.
  `--camera-preset scene` uses a closer room camera at (5.8, 5.8, 2.75) m, 30 mm.
- Render: Cycles, 64 samples for the published suite, denoising, motion blur with a 0.5-frame
  shutter, persistent data off, caustics off, indirect light clamp 6.

## Physics

- Solver: PyBullet, 60 substeps per 24 fps frame (time step 1/1440 s), 120 solver iterations,
  deterministic overlapping pairs.
- Gravity −9.81 m/s². Ball restitution 0.78, friction 0.55, rolling friction 0.002, spinning
  friction 0.0001; floor restitution 0.85, friction 0.5, rolling friction 0.002; wall restitution
  1.0, friction 0.35; linear and angular damping 0.008. PyBullet multiplies the two bodies'
  restitution, so the effective values are 0.78 against a wall and about 0.66 against the floor.
- The ball penetrates the floor and walls by at most about 1 mm.
- A timed edit is written into the live solver at the top of its frame, before that frame's
  substeps; the builder checks that every earlier frame is bit-identical to the source and records
  the applied event in `simulation_metrics.json`.
- Ball mass is not editable: a free sphere under gravity follows the same trajectory at any mass.

## Measured motion

Source: the ball lands at 0.58 s, hits the `x = 0` wall at 1.33 s and the `y = 0` wall at 2.26 s, and
rolls out to about (2.25, 0.70) m. The only prop contact in the suite is the cabinet's top corner,
grazed once by `edit_speed_x15` at 1.69 s. Every edit moves the trajectory by at least 1.45 m.

| Case | Result |
| --- | --- |
| `edit_speed_x15` | First wall impact at 0.74 s, path length 10.81 → 12.38 m |
| `edit_restitution_x03` | The ball stops bouncing and comes to rest in the corner at (0.15, 0.11) m |
| `edit_friction_x05` | Peak spin 30.5 → 19.4 rad/s; the ball slides out to (3.97, 1.20) m |
| `edit_wall_restitution_x04` | The walls absorb the rebound; the ball slides down and stops at (0.50, 0.20) m |
| `edit_gravity_x25_at24` | Gravity −24.525 m/s² from 0.958 s while the ball is airborne |

## Validation

- `cases/<case>/room_layout_validation.json`: one framed artwork, two spare volleyballs in frame and
  stationary, no plant objects, the window fully in shot, one air-conditioning unit in frame with a
  back gap below 2 cm and a clearance above 0.4 m from the ball, and the smallest ball clearance to
  each prop in `render_prop_clearance_m`.
- The renderer measures the ball against every render-only prop's bounding box on every frame
  (plus 12 points between frames) and refuses the take below 2 cm. The closest approach over the six
  cases is 0.64 m (the framed notice in `edit_speed_x15`); in the other five cases it is 0.82 m (the
  chair).
- `cases/<case>/camera_frame_validation.json` ray-casts the finished frame on a 64 × 36 grid and reports the
  ceiling sample fraction (0.058 against a limit of 0.12), whether the camera is inside the room and
  the highest visible surface.

## Cases

The builder's native source case is `volleyball_corner_rebound_baseline`; it is published as
`source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Ball thrown at 5.85 m/s into the corner |
| `edit_speed_x15` | `SET ball.initial_velocity TIMES 1.5` | Initial speed 5.85 → 8.775 m/s, same direction |
| `edit_restitution_x03` | `SET ball.restitution TIMES 0.3` | Ball restitution 0.78 → 0.234 |
| `edit_friction_x05` | `SET ball.friction TIMES 0.5` | Ball friction 0.55 → 0.275 |
| `edit_wall_restitution_x04` | `SET wall.restitution TIMES 0.4` | Wall restitution 1.0 → 0.4 |
| `edit_gravity_x25_at24` | `SET world.gravity TIMES 2.5 AT FRAME 24` | Gravity −9.81 → −24.525 m/s² from frame 24 |

## Assets

- `scenes/volleyball_corner_rebound` (derived): `assets/scenes/volleyball_corner_rebound/scenario.json` (room, ball and physics
  parameters), `assets/scenes/volleyball_corner_rebound/comparison_camera.json` and `assets/scenes/volleyball_corner_rebound/detail_camera.json` (camera and render settings) and
  `assets/scenes/volleyball_corner_rebound/ASSET_SOURCES.json` (source record).
- `polyhaven/volleyball_corner_rebound` (url): Poly Haven scans for the floor, walls, props and the
  `autumn_park` HDRI.
- `models` (manual): `indoor_air_conditioner_unit.glb`, the split air-conditioning unit.

Download and check them with `python3 scripts/download_assets.py --scene volleyball_corner_rebound`
(add `--check` to only report).

## Requirements

- Simulation: Python with `pybullet==3.2.7` (`requirements.txt`; the repository's `.venv-domino`
  has it). The builder simulates in its own process. CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU (`--device auto`)
  for full-quality frames; the default `--device cpu` works for previews.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene volleyball_corner_rebound --check

# List the native case IDs
python3 scripts/rigid_rigid/volleyball_corner_rebound/build_pcve_volleyball_corner_rebound.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/volleyball_corner_rebound/build_pcve_volleyball_corner_rebound.py \
    --out-root renders/volleyball_corner_rebound/suite_build --simulate-only

# Render the simulated cases at the published settings, reusing the cached physics
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/volleyball_corner_rebound/build_pcve_volleyball_corner_rebound.py \
    --out-root renders/volleyball_corner_rebound/suite_build --reuse-physics \
    --blender tools/blender-4.3.2-linux-x64/blender --device auto --mode animation \
    --resolution 1280 720 --samples 64
```

`--only` selects edits (the source is always built).

## Outputs

The commands above write to `renders/volleyball_corner_rebound/suite_build/`, one directory per case
under `cases/`. Without `--out-root` the builder writes to
`renders/volleyball_corner_rebound/suite_build/pcve_volleyball_corner_rebound_suite/`. The published
suite is `renders/pcve_suites/pcve_volleyball_corner_rebound_suite/`; do not pass it as
`--out-root`.

## Code layout

- `build_pcve_volleyball_corner_rebound.py`: suite builder; simulates each case in process, checks
  timed edits against the source and runs the render.
- `simulate_volleyball_corner_rebound.py`: PyBullet solve; writes `physics_transforms.json`.
- `render_volleyball_corner_rebound.py`: Blender replay and render; writes the video, ground truth
  and layout checks. Without `--physics-json` it simulates first with the interpreter from
  `pcve_scene_runtime.python_for`.
- `scene_config.py`: loads `assets/scenes/volleyball_corner_rebound/scenario.json`, applies overrides and validates them.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/scene_geometry.py`: cabinet, spare-ball and air-conditioning unit colliders shared by
  solver and renderer.
- `appearance/look_volleyball_corner_rebound.py`: room, window, props and lighting.
- `appearance/camera_rig.py`: places the fixed camera from the case's render settings.

## Limitations

- The render-only props are absent from the solver; the clearance check guarantees the ball never
  comes within 2 cm of them.
- The ceiling is visible as a thin band along the top edge of the frame.
- The ball is about 18 px across at its farthest point at 960 × 540.
