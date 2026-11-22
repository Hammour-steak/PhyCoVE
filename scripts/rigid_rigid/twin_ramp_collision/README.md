# twin_ramp_collision

A symmetric double ramp stands on a table, with a red ball at the top of the left slope and a blue
ball at the top of the right slope. Both are released from rest at the same time, roll down, collide
on the flat middle section and roll back up the slopes. PyBullet solves the motion; Blender replays
the solved poses. Rigid–rigid scene of PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Units and axes: SI, Z up, the ramp runs along X, gravity −9.81 m/s².
- Ramp: each slope is 0.50 m long horizontally and rises 0.12 m; the flat middle section is 0.20 m;
  the running surface is 0.25 m wide. Each slope meets the flat section through a 35 mm
  C1-continuous parabolic blend (48 segments). The ramp is fixed and built from full-width plywood
  plank segments whose top edges meet exactly; visible top surface and collision shape share one
  profile. It stands on a 1.72 × 0.86 m table, top at 0.76 m.
- Balls: `B_left` (red) and `B_right` (blue), radius 25 mm, 75 g, uniform solid inertia
  `I = 0.4 m r²`, opaque cast resin with two antipodal ivory spots so rolling stays visible. Their
  contact points start at x = ±0.53165 m with zero linear and angular velocity; the release height
  is 10.23 cm above the resting height on the flat section.
- Room (preset `natural_home_realism`): painted walls and ceiling (3 m real repeat), a rounded
  25 mm laminate tabletop on coated steel legs, 600 mm matte porcelain floor tiles with skirting, a
  double-glazed rear window with linen curtains and a plant on its ledge, a second casement in the
  left wall outside the frame, and a worn alarm clock and a tape measure at the rear of the table.
- Light: the overcast `residential_garden` sky (strength 6.0, rotation 0.6 rad) is the only light
  and enters only through the two glazed openings, each with a Cycles portal; there are no lamps.
- Camera: location (0.29, −1.99, 1.57), 50 mm lens, f/8. Each ball is about 40 px across.
- Render: Blender 4.3, Cycles, 64 samples, OpenImageDenoise, AgX Medium High Contrast at +1.8 stops,
  0.25-frame shutter (1/96 s), persistent data off.

All inputs live in `scene_config.py`, split into `physics`, `simulation_quality`, `appearance` and
`render`. The appearance changes only what is seen; the running surface, camera and physics do not
depend on it.

## Physics

- Solver: PyBullet 3.2.7, dt = 1/15360 s (24 fps × 640 substeps), 100 iterations, `contactERP = 0`,
  zero collision margin, 0.5 µm contact slop, restitution threshold 0.01 m/s. Trajectories are
  sampled at 240 Hz. Video frame i is the solver state at t = (i−1)/24.
- Contact: Bullet multiplies restitution and sliding friction of the two bodies. Ball and ramp
  sliding friction 0.3 each (effective 0.09), rolling friction 0.00002 each (effective 0.000012),
  spinning friction 0.00001. Ball restitution 0.98 (ball–ball effective 0.9604); ramp restitution 0,
  so the balls never bounce off the ramp.
- No pushers, constraints, keyframes or velocity resets after the collision.
- `--stage graybox` runs the parameter and substep sweeps without rendering. Doubling the step rate
  changes the first climb height by less than 0.017 mm.

## Measured motion

Climb height is the ball centre's height above its resting height on the flat section.

| Case | Motion |
| --- | --- |
| `source` | First ball–ball contact at 0.7833 s (between frames 19 and 20); both climb about 4.15 cm, turn at about 1.19 s and roll back |
| `edit_heavy_left` | Same collision time; red climbs about 1.1 cm, blue about 8.8 cm (velocities after impact −0.68 and +1.62 m/s) |
| `edit_low_restitution` | Weak rebound; both balls stay near the middle |
| `edit_remove_right` | No collision; red crosses the middle, climbs 10.15 cm up the right slope and turns at about 1.61 s |

## Validation

The build stops when a case fails `physics/validate_twin_ramp_collision.py`: initial state and
symmetry, climb heights, smooth passage over the ramp joints (no position jump above 2.1 m/s ÷ fps
between frames), penetration, no energy gain, the edit changes only its declared field, the first
collision lies on a 240 Hz sample, and the downhill motion before the collision matches the source.
The largest ball–ball penetration is 0.08 mm and ramp penetration stays below 0.001 mm. The
`realism` workflow also finds each ball in every rendered frame by colour and requires the centroid
within 6 px of the solved projection (`physics/audit_twin_ramp_collision.py`), checks the
contact-frame silhouette gap, and reads all solved poses back from the saved scenes
(`appearance/audit_saved_scenes.py`).

## Cases

Every edit changes one property; everything else matches the source. `edit_vocab.py` holds the DSL
vocabulary, the statements and the source prompts; the edit prompts come from
`pcve_edit_dsl.make_prompts`. `B_left.restitution` means the effective ball–ball restitution against
the blue ball; the compiler sets its square root on both balls.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Both balls released from rest at the top of their slopes |
| `edit_heavy_left` | `SET B_left.mass TIMES 1.5` | Left ball mass 0.075 → 0.1125 kg |
| `edit_low_restitution` | `SET B_left.restitution TIMES 0.31497292794668885` | Ball–ball effective restitution 0.9604 → 0.3025 (each ball 0.98 → 0.55) |
| `edit_remove_right` | `DELETE B_right` | Blue ball absent from frame 1 |

## Assets

- `polyhaven/plywood` (url): ramp boards.
- `scenes/twin_ramp_collision/wall_textures/beige_wall_001` (url): painted walls and ceiling (2K scan).
- `ambientcg/SurfaceImperfections018` (url): roughness and tone variation on the tabletop and floor
  tiles.
- `ambientcg/Fabric034` (url): curtain fabric detail.
- `polyhaven/residential_garden` (url): sky outside the windows, the only light source.
- `polyhaven/alarm_clock_01` (url): alarm clock on the table.
- `polyhaven/measuring_tape_01` (url): tape measure on the table.
- `polyhaven_models/potted_plant_02` (url): plant on the window ledge.

`realism_assets.json` lists the assets of the look with files and hashes; it is hashed into the
build provenance and no code reads its values. Download and check the assets with
`python3 scripts/download_assets.py --scene twin_ramp_collision` (add `--check` to only report).

## Requirements

- Python: `.venv-domino` in the repository root, or any environment with `pybullet==3.2.7`. The
  simulation runs on the CPU.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU, CPU works but
  is slow. `ffmpeg`/`ffprobe` for encoding and the video check.

## Commands

Run from the repository root. The builder needs an empty or matching `--out-root`.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene twin_ramp_collision --check

# List the cases and print the plan
.venv-domino/bin/python scripts/rigid_rigid/twin_ramp_collision/build_pcve_twin_ramp_collision.py --list-cases
.venv-domino/bin/python scripts/rigid_rigid/twin_ramp_collision/build_pcve_twin_ramp_collision.py \
    --out-root renders/twin_ramp_collision/suite_build --dry-run

# Simulate and validate all four cases on the CPU
.venv-domino/bin/python scripts/rigid_rigid/twin_ramp_collision/build_pcve_twin_ramp_collision.py \
    --out-root renders/twin_ramp_collision/suite_build --stage simulate

# Render, then verify the videos
.venv-domino/bin/python scripts/rigid_rigid/twin_ramp_collision/build_pcve_twin_ramp_collision.py \
    --out-root renders/twin_ramp_collision/suite_build --stage render \
    --blender tools/blender-4.3.2-linux-x64/blender
.venv-domino/bin/python scripts/rigid_rigid/twin_ramp_collision/build_pcve_twin_ramp_collision.py \
    --out-root renders/twin_ramp_collision/suite_build --stage verify

# Workflow realism: re-render a simulated suite on idle GPUs and audit every frame
.venv-domino/bin/python scripts/rigid_rigid/twin_ramp_collision/build_pcve_twin_ramp_collision.py \
    --workflow realism --out-root renders/twin_ramp_collision/realism_build \
    --physics-source-root renders/twin_ramp_collision/suite_build --stage all
```

`--stage all` (the default) runs simulate, render and verify in order; `--cases` selects cases and
`--skip-existing` reuses finished cases. The `realism` workflow copies the solved trajectories byte
for byte, renders with `physics/render_queue.py` (a case starts only on an idle GPU from `--gpus`, default all eight device indices)
and verifies the frames and saved scenes; its stages are `prepare`, `render`, `verify` and `all`.
`--appearance-json` gives it a visual-only override (appearance, shutter and persistent data); it
refuses changes to resolution, samples, frame rate or duration. Its `--physics-source-root` defaults
to `renders/twin_ramp_collision/native`, so pass the simulated suite explicitly.

## Outputs

The commands above write to `renders/twin_ramp_collision/suite_build/` (`suite_manifest.json`,
`implementation_manifest.json` and one directory per case under `cases/` with `video.mp4`,
`physics_transforms.json`, `trajectory.csv`, `contacts.json`, `physics_validation.json`,
`config_diff.json`, `ground_truth_transforms.json`, `prompts.json`, `scenario_metadata.json`,
`settings.json`, `render_report.json`, `video_validation.json` and `twin_ramp_collision.blend`). The
`realism` workflow writes to its own `--out-root` and adds `appearance_override.json`,
`appearance_diff.json`, `render_audit.json`, `saved_scene_audit.json` and `realism_validation.json`.
The published suite is `renders/pcve_suites/pcve_twin_ramp_collision_suite/`; do not pass it as
`--out-root`.

## Code layout

- `build_pcve_twin_ramp_collision.py`: suite builder with stages `simulate`, `render`, `verify`,
  `all` and `graybox`.
- `build_realism_twin_ramp_collision.py`: workflow `realism`, re-renders an existing physics suite.
- `simulate_twin_ramp_collision.py`: PyBullet simulation for one case.
- `render_twin_ramp_collision.py`: Blender replay and render.
- `scene_config.py`: all physical, numerical, appearance and render inputs and the cases.
- `edit_vocab.py`: edit DSL vocabulary, statements and prompts.
- `realism_assets.json`: assets of the look with files and hashes, hashed into the provenance.
- `physics/validate_twin_ramp_collision.py`: physics acceptance checks.
- `physics/graybox_twin_ramp_collision.py`: parameter and substep sweeps.
- `physics/audit_twin_ramp_collision.py`: per-frame render audit for the `realism` workflow.
- `physics/render_queue.py`: idle-GPU render queue for the `realism` workflow.
- `appearance/look_twin_ramp_collision.py`: Blender look, built in successive layers that the final
  functions build on.
- `appearance/audit_saved_scenes.py`: reads the solved poses back from the saved scenes.

## Limitations

- Rigid balls with effective friction and restitution; nothing is calibrated against real resin
  balls on plywood.
- In `edit_heavy_left` a second, oblique ball–ball impact on the right slope lifts the blue ball by
  less than 0.91 mm.
- Window light, exposure and materials are set by visual review; the sky seen through the rear
  window is overexposed.
- CPU renders of the same frame differ between runs by up to three intensity levels in a few
  thousand pixels.
