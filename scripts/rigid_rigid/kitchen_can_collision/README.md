# kitchen_can_collision

A rigid–rigid scene in PhyCoVE. A beverage can lying on its side rolls along a kitchen island
worktop and strikes a second can standing upright; the struck can slides forward and both come
to rest. PyBullet solves the rolling, the impact and the sliding; Blender only replays the
solved poses. The source video is 4 s at 24 fps (96 frames, 1280×720); frame i is the solver
state at t = (i−1)/24.

## Scene

- **Units and axes:** SI, Z up, gravity −9.81 m/s². The cans travel along +X on y = 0. All
  editable inputs are in `scene_config.py` (`BASELINE_PHYSICS`); fixed geometry is in
  `physics/scene_geometry.py`.
- **Worktop:** a fixed box 3.04 × 0.98 m (x ±1.52, y ±0.49), top face at z = 0.9458
  (`COUNTER_Z`).
- **Cans:** both 0.24 kg, 0.066 m across (radius 0.033 m) and 0.128 m tall. The collider is a
  convex hull of the measured can profile (rim, shoulder and body, 128 segments). The rolling
  can lies on its side at x = −0.48 and starts with 0.62 m/s along +X and the matching rolling
  spin 0.62/0.033 rad/s; the upright can stands at rest at x = 0.05.
- **Camera:** fixed at (−1.40, −1.15, 1.75) looking at (0.16, 0.05, 1.015), 44 mm lens, f/8.
- **Appearance:** `appearance/kitchen_room.py` builds a farmhouse kitchen to real dimensions.
  The island top is a 40 mm oiled white-oak butcher block of 24 staves, each sampling a
  different region of the scanned texture with a slightly different tone; its outline and top
  face are the simulator's worktop box, so the surface the cans touch on screen is the collision
  surface. Under the island are sage-green shaker cabinets (drawers, doors, brass pulls,
  recessed toe kick); along the back wall runs a row of off-white cabinets with an oak worktop
  and a stack-bond glazed tile splashback; the floor is terracotta tile and the walls painted
  plaster, all scanned materials mapped at their measured size. The side wall and the back wall
  each have a real window (opening, wooden frame, thin glass with a back-face IOR correction and
  a sky portal). A low late-afternoon sun (17° elevation, strength 3.6) comes through the side
  window and casts the window-frame shadow on the worktop; there is no lamp in the room. The
  view outside the back window is an HDR landscape (grass and a tree line) visible to camera
  rays only and rotated to the sun's azimuth.
- **Props:** `appearance/tabletop_props.py` places scanned models seated by their bounding
  boxes; fruit finds its support surface with downward rays. On the island: a chopping board
  with lemons, limes and an onion, three apples in a wooden bowl, and a croissant on a carved
  wooden plate; on the back worktop an electric kettle, an enamel pot and a milk jug; three bar
  stools on the far side of the island. The cans are printed beverage cans scaled to the
  collider's diameter and height.
- **Render:** Cycles, AgX with exposure 1.2, motion blur with a 0.5-frame shutter and
  persistent data off.

## Physics

- PyBullet at 1440 Hz (60 substeps per 24 fps frame), 120 solver iterations, restitution
  velocity threshold 0.001 m/s, deterministic overlapping pairs, contact breaking threshold
  0.3 mm.
- Cans: rolling friction 0.00065, spinning friction 0.0001, no damping, collision margin
  0.1 mm. The worktop has restitution 0.
- **Restitution:** each can carries √0.45; Bullet multiplies the two values, so the can–can
  pair restitution is 0.45.
- **Friction:** Bullet keeps one `lateralFriction` per body and multiplies the two at a
  contact, so there is no per-pair friction. The scene declares two body-level coefficients:
  `can_friction` (0.065, on both cans) and `table_friction` (1.0, on the worktop). The can–can
  contact is set by the cans' value, the can–worktop contact by the product. The simulation
  reports the body values it set (`effective_can_lateral_friction`,
  `effective_table_lateral_friction`) next to the requested ones.
- **Settling:** both cans are placed 0.2 mm above the worktop and run 240 settle steps with the
  source coefficients (0.065 and 1.0) before frame 1; the declared friction values are written
  afterwards and then the rolling can receives its velocity. Every friction edit therefore
  starts from the source's settled poses.
- **Timed edits:** `simulate_kitchen_can_collision.py` parses the schedule before the first
  step and, at the frame boundary named by `AT FRAME`, writes the new value into the running
  simulation (`changeDynamics` on the worktop for `table_friction`, on both cans for
  `can_friction`, `resetBaseVelocity` with matching spin for a speed). Each write is logged in
  `timed_events` (physics cache and `run_status.json`) with the value before and after and the
  body states. Timed values are checked against `TIMED_FIELDS`, a wider band than the
  start-of-run limits.

## Measured motion

Read back from each case's `simulation_metrics.json`.

Source (`kitchen_can_collision_baseline`): first impact at 0.843 s (about frame 21); the rolling
can travels 0.611 m and the upright can 0.147 m; peak speed of the struck can 0.276 m/s; maximum
tilt 3.12°; contact impulse 0.154 N·s; everything settled by 1.84 s.

The rolling can rolls rather than skids. The simulator records
`max_preimpact_slip_ratio` = |v_x − ω_y·R| / |v_x| with R = 0.033 m before the first impact
(0 = pure rolling, 1 = sliding without turning):

| Case | Pre-impact max | Pre-impact median |
| --- | --- | --- |
| `source` | 0.52 % | 0.40 % |
| `edit_rough_cans` | 0.42 % | 0.34 % |
| `edit_slippery_table` | 0.52 % | 0.40 % |

After the impact the source ratio peaks at 97 % on frame 22 (the collision reverses the linear
velocity in one substep while the spin lags), then 57 %, 54 %, 20 % and 4.3 % by frame 26, after
which the median is 0.28 %. In `edit_rough_cans` the peak on the same frame is 55 %.

First frame on which each edit differs from the source (all recorded body poses compared frame
by frame):

| Case | First differing frame | Reason |
| --- | --- | --- |
| `edit_heavy_driver` | 22 | mass matters only once the contact exists; frame 21 is still the approach |
| `edit_heavy_receiver` | 22 | same |
| `edit_remove_receiver` | 1 | the upright can is absent from the first frame |
| `edit_rough_cans` | 2 | the rougher contact acts on the first rolling step |
| `edit_slippery_table` | 31 | the write lands at frame 30 and acts in that frame's substeps |

## Validation

- `quality.valid` requires a maximum penetration below 2 mm, both cans staying on the worktop
  (positive edge clearance) and the struck can tilting less than 25°.
- On the source case the builder requires `transmission_observed` (the struck can reaches more
  than 0.02 m/s).
- `physics/validate_kitchen_can_collision.py` rejects a cache whose simulation signature, frame
  count, frame clock or presence schedule does not match its scenario.
- The render fails if any prop rule is broken: every island prop stands on the oak at least
  2 cm from the edge; props on the same worktop do not overlap; on every frame each can's
  bounding box stays at least 2 cm (horizontally) from every prop; on every frame 4 sight lines
  from the camera to each can are blocked only by cans. Across the six cases the closest a can
  comes to a prop is 8.8 cm (`edit_remove_receiver`, frame 96, the chopping board).

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source motion |
| `edit_heavy_driver` | `SET rolling_can.mass TIMES 3` | Rolling can 0.24 → 0.72 kg: impulse 0.154 → 0.402 N·s, rolling can travels 0.858 m, struck can 0.394 m, tilt 6.10° |
| `edit_heavy_receiver` | `SET upright_can.mass TIMES 3` | Upright can 0.24 → 0.72 kg: impulse 0.229 N·s, the struck can moves 0.023 m (tilt 0.94°), the rolling can stops at 0.487 m |
| `edit_remove_receiver` | `DELETE upright_can` | No contact: the rolling can travels 1.306 m and still creeps at 0.085 m/s on the last frame |
| `edit_rough_cans` | `SET can.friction TIMES 3` | Can surface 0.065 → 0.195: contact at 0.8465 s instead of 0.8431 s, rolling can stops at 0.520 m, struck can at 0.056 m although it leaves the contact slightly faster (0.292 vs 0.276 m/s) |
| `edit_slippery_table` | `SET table.friction TIMES 0.25 AT FRAME 30` | From frame 30 (t = 1.208 s), after the impact, the worktop friction drops 1.0 → 0.25: the struck can slides 0.335 m and the rolling can 0.799 m |

The builder names the source case `kitchen_can_collision_baseline`; the edit IDs are the
published case IDs (`--list-cases` prints them). `DELETE upright_can` sets `receiver_active` to
0, so the body is never created, carries no transforms in the ground truth and is not rendered.
In `edit_slippery_table` the friction write does not move either can (`state_before` equals
`state_after`); physics frames 1–30 match the source.

`edit_vocab.py` also declares `rolling_can.initial_velocity`, `rolling_can.speed` (the same key
written into a moving body, usable with `AT FRAME`), `upright_can.initial_velocity` and
`pair.restitution`:

| DSL object.property | Unit | Source value | Simulated key |
| --- | --- | --- | --- |
| `rolling_can.mass` | kg | 0.24 | `driver_mass` |
| `upright_can.mass` | kg | 0.24 | `receiver_mass` |
| `rolling_can.initial_velocity` | m/s | 0.62 | `initial_velocity` |
| `rolling_can.speed` | m/s | 0.62 | `initial_velocity` (written mid-run) |
| `upright_can.initial_velocity` | m/s | 0.0 | `receiver_initial_velocity` |
| `pair.restitution` | – | 0.45 | `restitution` |
| `can.friction` | – | 0.065 | `can_friction` |
| `table.friction` | – | 1.0 | `table_friction` |
| `edit_remove_rolling_can` | `DELETE rolling_can` | Horizontal blue can removed from frame 1 |

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `models` | manual | Can model used for both cans (file chosen in `appearance/look_kitchen_can_collision.py`) |
| `polyhaven/kitchen_can_collision` | url | Scanned surfaces, props and the window HDR of the kitchen |
| `scenes/kitchen_can_collision` (`assets/scenes/kitchen_can_collision/asset_sources.json`, `assets/scenes/kitchen_can_collision/scenario.json`) | derived | Provenance records of the scene's assets; not read by the code |

```bash
python3 scripts/download_assets.py --scene kitchen_can_collision           # fetch what can be fetched
python3 scripts/download_assets.py --scene kitchen_can_collision --check   # report only
```

Manual files need a provider login; the script prints where to get each one. `PCVE_ASSETS_DIR`
replaces the asset root.

## Requirements

- Python with PyBullet 3.2.7 (`requirements.txt`); the repository's `.venv-domino/` environment
  provides it. The entries run in the interpreter that invokes them; `--physics-python` /
  `PCVE_PHYSICS_PYTHON` select the solver interpreter.
- Blender 4.3 (tested with 4.3.2 at `tools/blender-4.3.2-linux-x64/`), passed with `--blender`
  or found from `$BLENDER`, `PATH` or `~/.local/opt/blender-*`. Alternatively `--render-python`
  / `PCVE_RENDER_PYTHON` names a Python with the `bpy` module.
- The physics runs on the CPU. Rendering uses Cycles on a GPU when available (`--device auto`)
  or on the CPU (`--device cpu`).

## Commands

Run from the repository root. The builder and renderer default to 960×540; pass
`--resolution 1280 720` for the published video size.

```bash
# List the cases and the native interface
.venv-domino/bin/python scripts/rigid_rigid/kitchen_can_collision/build_pcve_kitchen_can_collision.py --list-cases
.venv-domino/bin/python scripts/rigid_rigid/kitchen_can_collision/build_pcve_kitchen_can_collision.py --describe

# Physics for all six cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_can_collision/build_pcve_kitchen_can_collision.py \
    --out-root renders/kitchen_can_collision/new_run --simulate-only

# Physics and full 96-frame videos (video.mp4 per case)
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_can_collision/build_pcve_kitchen_can_collision.py \
    --out-root renders/kitchen_can_collision/new_run --mode animation --resolution 1280 720 \
    --blender tools/blender-4.3.2-linux-x64/blender

# Keyframes of the timed case only
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_can_collision/build_pcve_kitchen_can_collision.py \
    --out-root renders/kitchen_can_collision/new_run --cases edit_slippery_table \
    --mode keyframes --keyframes 1 30 96 --blender tools/blender-4.3.2-linux-x64/blender

# One case by hand: solve, then render keyframes from the cache
.venv-domino/bin/python scripts/rigid_rigid/kitchen_can_collision/simulate_kitchen_can_collision.py \
    --out renders/kitchen_can_collision/manual/physics_transforms.json
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/kitchen_can_collision/render_kitchen_can_collision.py -- \
    --physics-json renders/kitchen_can_collision/manual/physics_transforms.json \
    --out-dir renders/kitchen_can_collision/manual --mode keyframes --device cpu

# Randomised batch (masses, launch speed, restitution) on top of the same builder
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_can_collision/tools/render_queue.py \
    --out-root renders/kitchen_can_collision/batch --count 4 --simulate-only
```

The builder's `--mode` is `keyframes` by default (`preview` renders one frame, `animation` all
96 frames plus `video.mp4`); `--cases` builds a subset (the source case ID is accepted too),
`--simulate-only` and `--render-only` split the two stages and `--skip-existing` reuses a case
whose fingerprint is unchanged. The simulate entry also accepts `--scenario-json`,
`--scenario-overrides-json` and one flag per editable parameter.

## Outputs

A run writes `suite_manifest.json` and `cases/<case>/` under `--out-root` (default
`renders/kitchen_can_collision/suite_build/pcve_kitchen_can_collision_suite/`). Each case gets
`scenario_input.json`, `physics_transforms.json`, `simulation_metrics.json`, `prompts.json`,
`run_status.json` and, for edits, `scenario_overrides.json`; rendering adds the preview,
keyframes or `video.mp4`, `ground_truth_transforms.json`, `scenario_metadata.json`,
`render_validation.json` and the saved `.blend`. The batch tool writes `sample_<n>/` and
`<out-root>/batch_manifest.json`. The published suite is
`renders/pcve_suites/pcve_kitchen_can_collision_suite/`; do not use it as an output root.

## Code layout

- `build_pcve_kitchen_can_collision.py`: suite builder (source and edits, prompts, acceptance check).
- `simulate_kitchen_can_collision.py`: PyBullet solve of one scenario, including timed writes.
- `render_kitchen_can_collision.py`: Blender scene build, pose replay, prop checks and render.
- `scene_config.py`: editable physics, render and camera defaults, limits and validation.
- `edit_vocab.py`: edit DSL vocabulary, bindings, the edit case list and the source prompts.
- `physics/scene_geometry.py`: can profile, worktop height and solver constants.
- `physics/validate_kitchen_can_collision.py`: cache validation and the simulation signature.
- `physics/input_hashes.py`: asset hashes used by the `--skip-existing` fingerprint.
- `appearance/look_kitchen_can_collision.py`: can import and scaling, environment assembly.
- `appearance/kitchen_room.py`: the farmhouse kitchen, windows and sun.
- `appearance/tabletop_props.py`: props, their placement and clearance checks.
- `tools/render_queue.py`: randomised batch sampler.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry metadata, scene manifest
  and Python requirements.

## Limitations

- Friction is set per body, so `can.friction` also changes the can–worktop contact (through the
  product with the worktop value).
- The cans collide as convex hulls of the can profile; the recessed base and the lid well are
  filled.
- The props are visual only and do not take part in the simulation.
