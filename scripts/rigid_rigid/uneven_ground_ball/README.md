# uneven_ground_ball

A rubber ball is launched along a gently sloping forest trail and rolls over its crests and hollows,
climbing, slowing, turning back and coming to rest on the uneven ground. Rigid–rigid scene of
PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Terrain: a height field over x ∈ [−8, 12] m, y ∈ [−8, 8] m on a 400 × 320 grid, base height
  0.08 m with a slope of −0.016 along x. A broad trough (amplitude −0.040 m, σ 2.40 × 0.50 m,
  centred at (−0.30, −0.30)) carries the ball along +x; four Gaussian mounds and hollows
  (amplitude ±0.040–0.045 m) inside and beside it make the path wander. The rendered ground is the
  PyBullet triangle mesh itself (`terrain_mesh.npz`); no vertex is moved or displaced.
- Ball: a four-panel blue-and-yellow rubber toy ball, radius 0.10 m, 0.45 kg, moment of inertia
  0.64 m r². It starts at (−1.8, −0.20) on the ground at 1.4 m/s along +x.
- Ground look: a packed-earth trail scan (`forest_ground_04`, 3.15 m per tile) along the trough
  and pine-needle litter (`forest_leaves_04`) elsewhere, with moss patches away from the path. The
  textures drive albedo, roughness, normal and about 4 mm of bump shading only; the curvature tint is
  baked from the same height field.
- Surroundings (not simulated): pine trunks with the `pine_bark` scan, stumps, a fallen trunk,
  ferns, pine saplings, mossy rocks and gravel, and dry branches, all Poly Haven scans. The solver's
  bench, planter and fence boxes lie at least 2.2 m from every trajectory and are not drawn.
- Light: the unclipped `forest_slope` HDRI (4k) with its small sun disc replaced by surrounding sky,
  a sun lamp at the HDRI's sun bearing and 41° elevation, and a shadow-only canopy plane 17 m
  overhead that dapples the ground. AgX Medium High Contrast, exposure −0.15.
- Camera (`TERRAIN_CAMERA`, the default `--view terrain`): location (−0.50, −2.20, 0.66) looking at
  (−0.50, −0.10, 0.10), 26 mm lens; a low three-quarter view in which every crest breaks the
  ball's silhouette.
- Render: Cycles, 48 samples for the published suite, denoising, motion blur with a 0.5-frame
  shutter, persistent data off, no caption bar (`--label` adds one).

## Physics

- Solver: PyBullet, time step 1/960 s (40 substeps per 24 fps frame), 100 solver iterations,
  deterministic overlapping pairs. The terrain is a concave triangle mesh split into collision
  chunks of 30,000 triangles; no triangle is removed or moved at chunk boundaries.
- Gravity −9.81 m/s². Ball friction 0.35, ground friction 1.0, rolling friction 0.0015 m, spinning
  friction 0.0015 m, ball restitution 0.05, ground restitution 0, no damping.
- The spinning-friction arm is (2/3)·μ·a for a contact patch of radius a ≈ 7 mm. With it a ball that
  has stopped does not turn on the spot (0.0° in `edit_high_rolling_resistance` and
  `edit_braking_timed`).
- A timed edit runs the baseline dynamics up to its frame and then writes the new coefficients into
  the live ball.
- The renderer checks the stored terrain mesh by exact hash and the current height function
  geometrically (largest deviation ≤ 1e-9 m).

## Measured motion

| Case | Path length | Note |
| --- | --- | --- |
| `source` | 3.348 m | |
| `edit_slow_ball` | 1.301 m | Stops in front of the mound at x ≈ −0.95 m and rolls back to −1.11 m |
| `edit_fast_ball` | 7.904 m | Jumps several crests and rolls out of frame on the right |
| `edit_low_friction` | 2.497 m | Fails to climb the mound, slips and rolls back |
| `edit_high_rolling_resistance` | 0.678 m | Stops at frame 35 |
| `edit_braking_timed` | 2.045 m | Brakes from frame 36, stops at frame 65 |

## Validation

At render time every prop is checked with a BVH against the ball centres of every frame of all six
cases (`appearance/ball_corridor.json`) plus the current case's frames: each prop must stay at least
2 cm from the ball surface and must not hide the ball from the camera, otherwise the render fails.
The closest prop is a gravel stone at 901 mm.

## Cases

The builder's native source case is `uneven_ground_ball_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Ball launched at 1.4 m/s along +x |
| `edit_slow_ball` | `SET ball.initial_velocity TIMES 0.5` | Initial speed 1.4 → 0.7 m/s |
| `edit_fast_ball` | `SET ball.initial_velocity TIMES 2.5` | Initial speed 1.4 → 3.5 m/s |
| `edit_low_friction` | `SET ball.friction TIMES 0.25` | Ball friction 0.35 → 0.0875 |
| `edit_high_rolling_resistance` | `SET ball.rolling_resistance TIMES 20` | Rolling resistance 0.0015 → 0.03 |
| `edit_braking_timed` | `SET ball.rolling_resistance TIMES 10 AT FRAME 36` | Rolling resistance 0.0015 → 0.015 from frame 36 |

## Assets

- `polyhaven/uneven_ground_ball` (url, plus two derived files): Poly Haven scans for the ground,
  bark, stumps, fallen trunk, ferns, saplings, rocks and branches, and the `forest_slope` HDRI.

Download and check them with `python3 scripts/download_assets.py --scene uneven_ground_ball`
(add `--check` to only report).

## Requirements

- Simulation: Python with `pybullet==3.2.7`, numpy and Pillow (`requirements.txt`; the repository's
  `.venv-domino` has them). CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU (CUDA or OptiX)
  for full-quality frames, CPU works for previews.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene uneven_ground_ball --check

# List the native case IDs
python3 scripts/rigid_rigid/uneven_ground_ball/build_pcve_uneven_ground_ball.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/uneven_ground_ball/build_pcve_uneven_ground_ball.py \
    --out-root renders/uneven_ground_ball/suite_build --simulate-only

# Render the simulated cases at the published settings
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/uneven_ground_ball/build_pcve_uneven_ground_ball.py \
    --out-root renders/uneven_ground_ball/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720 --samples 48
```

`tools/render_queue.py` (workflow `batch_render`) builds randomised variants from `--seed-base`
into `renders/batch_uneven_ground_ball`.

## Outputs

The commands above write to `renders/uneven_ground_ball/suite_build/`, one directory per case under
`cases/`; each case also keeps its `terrain_mesh.npz`. Without `--out-root` the builder writes to
`renders/uneven_ground_ball/suite_build/pcve_uneven_ground_ball_suite/`. The published suite is
`renders/pcve_suites/pcve_uneven_ground_ball_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_uneven_ground_ball.py`: suite builder; runs the simulation and render for each case.
- `simulate_uneven_ground_ball.py`: PyBullet solve; writes `physics_transforms.json` and
  `terrain_mesh.npz`.
- `render_uneven_ground_ball.py`: Blender replay and render; writes the video, ground truth and
  checks.
- `scene_config.py`: physics, terrain, render and camera defaults and scenario validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/terrain_geometry.py`: height field and terrain mesh shared by solver and renderer.
- `scripts/pcve_windows_dll_paths.py` (shared): adds the conda `Library/bin` to the DLL search path on Windows.
- `appearance/look_uneven_ground_ball.py`: trail, forest props and lighting.
- `appearance/video_presentation.py`: optional caption bar and display-only terrain contours.
- `appearance/ball_corridor.json`: ball centres of all six published cases, read by the prop check.
- `tools/render_queue.py`: randomised batch builder.

## Limitations

- Ball restitution 0.05 has no effect: PyBullet multiplies the two bodies' restitution and the
  ground's is 0, so contacts with the ground are perfectly inelastic.
- Another PyBullet or numpy build does not reproduce the trajectories bit for bit: terrain vertices
  differ by up to 3.3e-16 m and the contact dynamics then diverge (the end of `edit_fast_ball` differs
  by 1.3 m in y). Two runs with the same build are byte-identical.
- CPU renders of the same frame can differ by one or two intensity levels in a few hundred values
  between runs.
