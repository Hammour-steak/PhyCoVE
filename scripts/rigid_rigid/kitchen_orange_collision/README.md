# kitchen_orange_collision

A rigid–rigid scene in PhyCoVE. A whole orange rolls across a breakfast table in a sunlit
Mediterranean dining room and strikes a second orange whose top has been sliced off, knocking it
into a roll. Nothing is keyframed: PyBullet solves every contact and Blender replays the solved
poses. The source video is 4 s at 24 fps (96 frames, 1280×720); frame i is the solver state at
t = (i−1)/24.

## Scene

- **Units and axes:** SI, Z up, gravity −9.81 m/s²; the driving orange rolls along +X. All
  editable inputs are in `scene_config.py` (`BASELINE_PHYSICS`); fixed geometry is in
  `physics/scene_geometry.py`.
- **Table:** a fixed box 1.81 × 1.10 m, top at z = 0.742 m, 40 mm thick, centred at
  (−0.005, −0.0025). The floor is a fixed slab whose top is the ground z = 0.
- **Driving orange:** 0.17 kg, 7.7 cm across (radius 0.0385 m), sphere collider with solid-sphere
  inertia, starting at x = −0.55 with 0.90 m/s along +X and the matching rolling spin.
- **Sliced orange:** 0.14 kg, the same radius with the cap above 0.020 m (0.52 R) sliced off,
  leaving a 5.3 cm cut face. It stands on its dome with the cut face up, centre at (0.12, 0.010)
  and the face turned 24° away from the driving orange. Standing dome-down puts both centres at
  the same height (38.5 mm above the cloth), so the contact normal is horizontal; it is also the
  only pose in which the sliced orange rests still. Its collider is a convex hull with the dome
  sampled at 48 rings (bumps of 0.08 mm); its centre of mass (1.7 mm below the sphere centre) and
  inertia come from a closed-form integration of the sliced solid.
- **Queued oranges (edit only):** with `rear_oranges = 2`, two whole oranges with the driving
  orange's mass stand behind the sliced one, 0.6 mm apart.
- **Camera:** fixed at (−1.34, −1.40, 1.42) looking at (0.02, 0.08, 0.80), 27 mm lens on a
  36 mm sensor, f/4 focused on the target. The frame holds the whole table, the chairs on its
  far side, the back wall, the window and the open terrace doors, with the fruit at the centre.
  The framing margin is reported in `render_validation.json`; an edit that throws fruit out of
  frame is flagged there.
- **Room:** `appearance/sunlit_dining_room.py` builds a dining room at real size: whitewashed
  walls, a cream marble floor, blue-grey painted joinery. In the wall at the far end of the
  table a pair of full-height glazed doors folds inwards onto a stone-paved terrace at the same
  level, bounded by a 0.70 m white parapet, with a ridge across a hazy valley beyond. The room
  floor, the threshold and the terrace paving all lie on the simulated ground z = 0, so fruit
  that leaves the table over the far end (+x) rolls out of the door and across the terrace with
  nothing in its way. Door and window frames are built to size and painted blue-grey satin; the
  glass is thin glass with a back-face IOR correction.
- **Table and cloth:** the table is built on the collision box: one top board (the box itself,
  under the cloth thickness), wooden trestles at both ends and a stretcher. Trestles keep the
  floor where oranges land past the end of the table visible from the camera. The linen cloth's
  top is generated on the box top and stays flat; its edge rolls over the rim with an 8 mm
  radius and the drop stays within the box's 40 mm thickness (deviation at most 6 mm, checked
  when the cloth is built). Weave, yarn stripes, two ironing creases and slight wrinkles are in
  the shading only. The near end (−x) and the back side (+y) hang 20 cm with soft folds and a
  cone at their shared corner; the far end (+x) and the front side (−y) hang only 36 mm, so no
  drop sits in the path of an orange leaving the table or hides the floor below the front edge.
- **Furnishings:** two painted wooden chairs (scaled by 0.79 to a 0.46 m seat), a painted
  dresser, a landscape painting in a frame (no text or signature), a ceramic pot by the window,
  and on the near end of the table three pomegranates, three buns and a brass jug, all at least
  0.2 m from the oranges' path.
- **Oranges:** `appearance/look_kitchen_orange_collision.py` imports the two scanned oranges and
  changes only their materials: subsurface scattering at a 4 mm scale and a light waxy clear
  coat on the peel; the cut face, separated by its normal, uses the same texture with deeper
  subsurface scattering and a wet highlight. The whole-orange scan is flat where it was
  photographed; those base vertices are pushed out onto the fitted sphere so the visible fruit
  matches the sphere collider.
- **Light and render:** sun and sky only, no lamps or fill cards: a sun lamp at 25° elevation
  and −8° azimuth (from +x, slightly towards −y), strength 4.2, through the glazed doors and the
  window, and a Nishita sky at strength 0.6 with one portal each in the doors and the window. An
  HDR photograph outside is visible to camera rays only, rotated so its sun matches the lamp's
  azimuth; a light-blocking ground plane far beyond the terrace, invisible to the camera, stops
  sky below the horizon from lighting the room. Cycles, OpenImageDenoise (albedo and normal),
  AgX with exposure +0.75, motion blur with a 0.25-frame shutter and persistent data off.

## Physics

- PyBullet at 1440 Hz (60 substeps per 24 fps frame), 120 solver iterations, restitution
  velocity threshold 0.001 m/s, deterministic overlapping pairs, contact breaking threshold
  0.3 mm.
- Oranges: rolling friction 0.0004, spinning friction 0.0002, no damping, collision margin
  0.2 mm. Table and floor have restitution 0.
- **Restitution:** each orange carries √0.40, so the orange–orange pair restitution is 0.40.
- **Friction:** Bullet keeps one `lateralFriction` per body and multiplies the two at a contact,
  so the scene declares two body-level coefficients: `orange_friction` (0.72, all oranges) and
  `table_friction` (1.0, the table). The floor keeps friction 1.0.
- **Settling:** all oranges run 240 settle steps with the source coefficients before frame 1;
  the declared friction values are then written and the driving orange receives its velocity.
- **Timed edits:** at the frame boundary named by `AT FRAME`, the simulator writes the new value
  into the running simulation (a speed write sets the matching rolling spin) and logs the value
  before and after with the body states in `timed_events`. Timed values are checked against
  `TIMED_FIELDS`, a wider band than the launch limits (speed up to 9 m/s).

## Measured motion

Source (24 fps, 4 s, 96 frames):

| Quantity | Value |
| --- | --- |
| first contact | frame 18, 0.679 s |
| driving orange travel | 0.913 m |
| sliced orange travel | 0.147 m |
| sliced orange roll | 173° |
| peak speed of the sliced orange | 0.576 m/s |
| normal impulse | 0.110 N·s |
| pre-impact slip ratio | 7.7e-16 (pure rolling) |
| worst penetration | 0.37 mm |

Sliced-orange travel along X per case: source 0.147 m, `edit_heavy_driver` −0.035 m,
`edit_heavy_cut` −0.007 m, `edit_fast_driver` 1.099 m, `edit_rear_queue` 0.002 m,
`edit_midframe_surge` 9.035 m. Two runs of all six cases with PyBullet 3.2.7 on Linux are
byte-identical.

Where fruit leaves the table it drops off the far end (+x) onto the ground: in
`edit_heavy_driver` and `edit_fast_driver` it lands 0.2–0.5 m past the end of the table; in
`edit_midframe_surge` the sliced orange flies 1.6 m, lands and rolls to x = 9.2 m, in frame up
to frame 87 (about 8.5 m). In `edit_fast_driver` the sliced orange lands behind the table and is
hidden by the table top from frame 33.

## Validation

- `quality.valid` requires a maximum penetration below 5 mm (a body landing on the floor at
  3.8 m/s with a 1/1440 s step) and no body centre below the floor. Leaving the table is
  reported as `left_table`, not rejected.
- On the source case the builder requires `transmission_observed` (the sliced orange reaches more
  than 0.02 m/s).
- `physics/validate_kitchen_orange_collision.py` rejects a cache whose simulation signature,
  frame count, frame clock or presence schedule does not match its scenario. The signature
  includes the appearance modules, so editing them invalidates cached physics.
- The render fails unless, in every case and frame (with 8 extra steps between frames), each
  orange stays at least 2 cm from the set (closest: the stretcher under the table at 33 mm, the
  door frame at 15 cm in the surge case), and the ray from the camera to every orange in frame is
  not blocked by furniture or by cloth below the table box. Results go to each case's
  `render_validation.json`.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source motion |
| `edit_heavy_driver` | `SET driver_orange.mass TIMES 5` | Driving orange 0.17 → 0.85 kg; it ploughs through and runs off the end of the table (2.10 m) |
| `edit_heavy_cut` | `SET cut_orange.mass TIMES 10` | Sliced orange 0.14 → 1.4 kg; it barely moves (−0.007 m) and stops the driving orange at 0.46 m |
| `edit_fast_driver` | `SET driver_orange.initial_velocity TIMES 3` | Launch speed 0.90 → 2.7 m/s; contact at 0.22 s, the sliced orange travels 1.10 m |
| `edit_rear_queue` | `SET cut_orange.rear_oranges TO 2` | Two whole oranges queued tight behind the sliced one; the impact is carried through four bodies |
| `edit_midframe_surge` | `SET driver_orange.speed TIMES 8 AT FRAME 10` | From frame 10 (t = 0.375 s), halfway along the 0.60 m run-up, the driving orange's speed is multiplied by 8; it arrives at 7.2 m/s and the sliced orange is thrown 9.0 m |
| `edit_delete_cut_orange` | `DELETE cut_orange` | Sliced orange removed from frame 1 |
| `edit_delete_driver_orange` | `DELETE driver_orange` | Whole orange removed from frame 1 |

The builder names the source case `kitchen_orange_collision_baseline`; the edit IDs are the
published case IDs (`--list-cases` prints them). `rear_oranges` is a count whose source value is
0, so its edit is written `TO 2`. `edit_vocab.py` also declares
`pair.restitution`, `orange.friction` and `table.friction`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `models` (`fresh_orange.glb`, `orange_fruit.glb`) | manual | Scanned whole orange and sliced orange |
| `polyhaven/kitchen_orange_collision` | url | Scanned surfaces, furniture, props and the window HDR of the dining room |

```bash
python3 scripts/download_assets.py --scene kitchen_orange_collision           # fetch what can be fetched
python3 scripts/download_assets.py --scene kitchen_orange_collision --check   # report only
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
- The physics runs on the CPU in a few minutes for all six cases. Rendering uses Cycles on a GPU
  when available (`--device auto`) or on the CPU (`--device cpu`).

## Commands

Run from the repository root. The builder and renderer default to 960×540 and a low sample
count; pass `--resolution 1280 720` and a `--samples` value for full-size videos.

```bash
# List the cases and the native interface
.venv-domino/bin/python scripts/rigid_rigid/kitchen_orange_collision/build_pcve_kitchen_orange_collision.py --list-cases
.venv-domino/bin/python scripts/rigid_rigid/kitchen_orange_collision/build_pcve_kitchen_orange_collision.py --describe

# Physics for all six cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_orange_collision/build_pcve_kitchen_orange_collision.py \
    --out-root renders/kitchen_orange_collision/new_run --simulate-only

# Two keyframes of the source: mid run-up and just after the strike
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_orange_collision/build_pcve_kitchen_orange_collision.py \
    --out-root renders/kitchen_orange_collision/new_run --cases kitchen_orange_collision_baseline \
    --mode keyframes --keyframes 12 44 --resolution 640 360 --samples 64 \
    --blender tools/blender-4.3.2-linux-x64/blender

# Physics and full 96-frame videos for all cases (video.mp4 per case)
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_orange_collision/build_pcve_kitchen_orange_collision.py \
    --out-root renders/kitchen_orange_collision/new_run --mode animation --resolution 1280 720 \
    --samples 256 --blender tools/blender-4.3.2-linux-x64/blender

# One case by hand: solve, then render keyframes from the cache
.venv-domino/bin/python scripts/rigid_rigid/kitchen_orange_collision/simulate_kitchen_orange_collision.py \
    --out renders/kitchen_orange_collision/manual/physics_transforms.json
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/kitchen_orange_collision/render_kitchen_orange_collision.py -- \
    --physics-json renders/kitchen_orange_collision/manual/physics_transforms.json \
    --out-dir renders/kitchen_orange_collision/manual --mode keyframes --device cpu

# Randomised batch (masses, speed, restitution) on top of the same builder
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_orange_collision/tools/render_queue.py \
    --out-root renders/kitchen_orange_collision/batch --count 4 --simulate-only
```

The builder's `--mode` is `keyframes` by default (`preview` renders one frame, `animation` all
96 frames plus `video.mp4`); `--cases` builds a subset (the source case ID is accepted too),
`--simulate-only` and `--render-only` split the two stages and `--skip-existing` reuses a case
whose fingerprint is unchanged. The renderer re-simulates unless `--physics-json` is given and
refuses a cache whose scenario or simulation signature differs.

## Outputs

A run writes `suite_manifest.json` and `cases/<case>/` under `--out-root` (default
`renders/kitchen_orange_collision/suite_build/pcve_kitchen_orange_collision_suite/`). Each case
gets `scenario_input.json`, `physics_transforms.json`, `simulation_metrics.json`,
`prompts.json`, `run_status.json` and, for edits, `scenario_overrides.json`; rendering adds the
preview, keyframes or `video.mp4`, `ground_truth_transforms.json`, `scenario_metadata.json`,
`render_validation.json` and the saved `.blend`. The batch tool writes `sample_<n>/` and
`<out-root>/batch_manifest.json`. The published suite is
`renders/pcve_suites/pcve_kitchen_orange_collision_suite/`; do not use it as an output root.

## Code layout

- `build_pcve_kitchen_orange_collision.py`: suite builder (source and edits, prompts, acceptance check).
- `simulate_kitchen_orange_collision.py`: PyBullet solve of one scenario, including timed writes.
- `render_kitchen_orange_collision.py`: Blender scene build, pose replay, checks and render.
- `scene_config.py`: editable physics, render and camera defaults, limits and validation.
- `edit_vocab.py`: edit DSL vocabulary, bindings, the edit case list and the source prompts.
- `physics/scene_geometry.py`: table box, orange geometry, sliced-orange hull and mass properties.
- `physics/validate_kitchen_orange_collision.py`: cache validation and the simulation signature.
- `physics/input_hashes.py`: asset hashes used by the `--skip-existing` fingerprint.
- `appearance/look_kitchen_orange_collision.py`: orange import, base re-inflation and materials.
- `appearance/sunlit_dining_room.py`: the dining room, terrace, table, cloth, furniture, light and
  clearance checks.
- `tools/render_queue.py`: randomised batch sampler.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry metadata, scene manifest
  and Python requirements.

## Limitations

- The sliced orange is a rigid convex hull; the soft flesh and juice of a real cut orange are
  not modelled.
- Friction is set per body, so `orange.friction` also changes the orange–cloth contact.
- The tablecloth folds and creases are shading and geometry around a rigid box; the cloth is not
  simulated.
- The floor is a 120 m square slab standing in for unbounded ground.
