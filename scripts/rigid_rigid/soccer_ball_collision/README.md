# soccer_ball_collision

Two size-five footballs roll towards each other across a mown grass pitch, collide almost head-on and
roll apart. Rigid–rigid scene of PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Balls: `cheap_soccer_ball.glb` (file unchanged) with a scene material close to a PU cover
  (non-metallic, roughness 0.5, coat 0.3). Radius 0.11 m, 0.43 kg. `ball_a` starts at
  (−0.85, −0.04) rolling along +x at 0.69 m/s, `ball_b` at (0.85, 0.04) rolling along −x at 0.63 m/s;
  both start rolling without slip. A third ball `ball_c` exists only in the ADD case, at the midpoint
  (0, 0).
- Pitch: procedural ryegrass, about 24,000 blades per m² (18–34 mm long, 1.8–3.6 mm wide, bent,
  twisted, creased, mown tips, translucent), instanced from ten 0.25 m turf tiles over
  x −5.25…3.5 m, y −3…6.5 m. Under the blades lies a soil layer from the Poly Haven Grass Ground scan
  (2.51 m repeat). The physics ground z = 0 is the grass tips; the soil is at z = −0.014 m. Mowing
  stripes are 5.5 m wide along y; a 12 cm white touchline is painted onto the blades at y = 3.5 m.
- Light: the `orlando_stadium` HDR (2k). At render time the sun (elevation 51.8°) is located in the
  image, a 2.45° cone around it is filled with the surrounding sky, and a sun lamp with the same
  direction, colour and irradiance (0.6° disc) is added; the sky is rotated so the sun stands at
  azimuth 200°, behind the camera on the left.
- Camera: location (0.45, −3.05, 1.12) looking at (0, 0.07, 0.06), 53 mm lens, depth of field focused
  on the target, f/7.1. The scene has no props.
- Render: Cycles, AgX Medium High Contrast, exposure −0.25, motion blur with a 0.5-frame shutter,
  persistent data off. Neighbouring keyframe quaternions are kept in the same hemisphere so motion blur
  interpolates rotations along the short path.

## Physics

- Solver: PyBullet, 1440 Hz, 100 solver iterations, restitution velocity threshold 0.01, deterministic
  overlapping pairs. Gravity −9.81 m/s².
- Ground: plane, friction 0.8, restitution 0.
- Balls: friction 0.65, rolling friction 0.0015, spinning friction 0.0002, restitution √0.78 =
  0.8832 per ball (Bullet multiplies the two), no damping, inertia 2/3·m·r² (thin inflated shell).
- Timed edits are written into the live bodies at the top of their frame; earlier frames match the
  source bit for bit.

## Measured motion

On Linux with PyBullet 3.2.7 repeated runs are byte-identical. A Windows PyBullet 3.2.7 build gives
the same source (largest difference 1.7e-17) while the five edit cases diverge after the collision
(from frames 23–93), by at most 1.2e-2.

## Cases

The builder's native source case is `soccer_ball_collision_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Balls at 0.69 and 0.63 m/s collide and roll apart |
| `edit_fast_driver` | `SET ball_a.initial_velocity TIMES 2` | `ball_a` initial speed 0.69 → 1.38 m/s |
| `edit_heavy_receiver` | `SET ball_b.mass TIMES 3` | `ball_b` mass 0.43 → 1.29 kg |
| `edit_dead_receiver` | `SET ball_b.restitution TIMES 0.1` | `ball_b` restitution 0.8832 → 0.0883 |
| `edit_add_midpoint_ball` | `ADD ball_c BETWEEN ball_a AND ball_b AT MIDPOINT` | Third ball present at the midpoint from frame 1 |
| `edit_overspin_receiver_timed` | `SET ball_b.spin TIMES 10 AT FRAME 32` | `ball_b` spin −5.73 → −57.27 rad/s from frame 32 |
| `edit_delete_ball_a` | `DELETE ball_a` | Left soccer ball removed from frame 1 |
| `edit_delete_ball_b` | `DELETE ball_b` | Right soccer ball removed from frame 1 |

## Assets

- `models` (manual): `cheap_soccer_ball.glb`.
- `polyhaven/soccer_ball_collision` (url): the Grass Ground textures and `orlando_stadium_2k.hdr`.
- `scenes/soccer_ball_collision` (derived): `assets/scenes/soccer_ball_collision/scenario.json`, the ball texture source record and the
  asset credits.

Download and check them with `python3 scripts/download_assets.py --scene soccer_ball_collision`
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
python3 scripts/download_assets.py --scene soccer_ball_collision --check

# List the native case IDs
python3 scripts/rigid_rigid/soccer_ball_collision/build_pcve_soccer_ball_collision.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/soccer_ball_collision/build_pcve_soccer_ball_collision.py \
    --out-root renders/soccer_ball_collision/suite_build --simulate-only

# Render the simulated cases at the published resolution
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/soccer_ball_collision/build_pcve_soccer_ball_collision.py \
    --out-root renders/soccer_ball_collision/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720 --samples 48
```

`tools/render_queue.py` (workflow `batch_render`) builds randomised variants from `--seed-base`.

## Outputs

The commands above write to `renders/soccer_ball_collision/suite_build/`, one directory per case under
`cases/`. Without `--out-root` the builder writes to
`renders/soccer_ball_collision/suite_build/pcve_soccer_ball_collision_suite/`. The published suite is
`renders/pcve_suites/pcve_soccer_ball_collision_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_soccer_ball_collision.py`: suite builder; runs the simulation and render for each case.
- `simulate_soccer_ball_collision.py`: PyBullet solve; writes `physics_transforms.json`.
- `render_soccer_ball_collision.py`: Blender replay and render; writes the video, ground truth and
  checks.
- `scene_config.py`: editable physics, limits, render and camera defaults and validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/scene_geometry.py`: ball radius, start positions and fixed constants.
- `physics/validate_soccer_ball_collision.py`: acceptance checks on a solved case.
- `physics/input_hashes.py`: asset hashes used by the `--skip-existing` fingerprint.
- `appearance/look_soccer_ball_collision.py`: pitch, grass, touchline, stadium light and ball
  material.
- `tools/render_queue.py`: randomised batch builder.

## Limitations

- The ground is a flat plane at the grass tips; grass blades do not interact with the balls.
- Ball spin and rolling resistance are PyBullet's sphere friction model with constant coefficients.
- The sample count used for the published videos is not recorded in the suite.
