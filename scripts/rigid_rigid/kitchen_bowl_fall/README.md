# kitchen_bowl_fall

A rigid–rigid scene in PhyCoVE. In a loft kitchen, a stoneware bowl standing askew in an open
wall cupboard tips out over the cupboard's front lip, falls about 0.7 m, strikes the rim of a
second bowl standing on the glass hob below and shoves it sideways, then comes to rest upside
down on the counter. PyBullet solves every contact; Blender only replays the solved poses. The
source video is 4 s at 24 fps (96 frames, 1280×720); frame i is the solver state at
t = (i−1)/24.

## Scene

- **Units and axes:** SI, Z up, gravity −9.81 m/s². All editable inputs are in
  `scene_config.py` (`BASELINE_PHYSICS`); the measured dimensions are in
  `physics/scene_geometry.py`.
- **Kitchen colliders:** `physics/room_colliders.py` loads
  `assets/scenes/kitchen_bowl_fall/room_colliders.json`: 10 boxes (floor, island, the counter
  beside the hob, hob glass, tiled upstand, the right-hand end wall of the kitchen and four outer
  walls) and 8 ray probes. `tools/export_room_colliders.py` measures them from
  `assets/models/modern_kitchen.glb` after the transform the scene uses (scale 0.5, a quarter
  turn about Z so the long island runs along physics X, then a translation of (−0.65, 0, 0));
  each box records its source node and the file records the GLB's sha256. The kitchen's
  right-hand end wall (x ∈ [1.496, 1.740], from the counter front edge y = 2.498 back to the
  upstand, floor to ceiling) is measured separately from the building shell (x = 3.261), which
  lies one room further out. The probes fail the export if the model moves.
- **Open wall cupboard:** the model's wall unit above the hob (`Cupboards_Cupboard_0`) is a door
  panel only (x ∈ [−0.494, 0.197], y ∈ [2.883, 2.939], z ∈ [1.828, 2.678]). The solver and the
  renderer both build a carcass in the volume of that panel:

  | Part | Size / position |
  | --- | --- |
  | carcass | x ∈ [−0.494, 0.197] (0.69 m wide), z ∈ [1.828, 2.678] (0.85 m tall) |
  | depth | front y = 2.939 to back panel y = 3.440 (against the tiles) |
  | board thickness | sides, top and bottom 0.018 m; shelf 0.016 m |
  | bottom board top face | z = 1.846 (the falling bowl stands here) |
  | inner shelf | top face z = 2.270 |
  | door | 0.020 m thick, open 104° about its right-hand vertical edge (x = 0.197), so it swings away from the camera |

- **Falling bowl:** a lathe-turned shallow stoneware serving bowl (celadon glaze), 0.160 m
  across, 0.070 m tall, 0.55 kg; its profile matches the solver's cylinder hull. At frame 1 it
  stands on the bottom board with its axis leaning forward 16°, centre at (x, y) = (−0.150,
  2.930), 1.5 mm above the board, with its rim at the front lip and its centre of mass already
  past the edge. Initial spin 0.06 rad/s about +x, initial linear velocity 0.
- **Bowl on the hob (tableware):** one stoneware rice bowl, 0.140 m across, 0.072 m tall,
  0.250 kg, at (x, y) = (−0.040, 2.750), standing on the hob glass at z = 0.957.
- **Camera:** fixed at (−2.15, 0.45, 2.05) looking at (−0.15, 3.00, 1.70), 28 mm lens, f/6.3
  focused on the target. It is about 38° to the left of the cupboard, above the cupboard's
  bottom board (1.846 m), and holds the cupboard top (z = 2.678) and the hob (z = 0.957) in one
  16:9 frame.
- **Appearance:** `appearance/loft_kitchen.py` builds an industrial loft kitchen on the solver's
  own colliders, so every visible surface a bowl can touch is the collision surface: a cast
  concrete wall-run counter with a black glass hob 11 mm proud, a brick back wall and a brick
  pier closing the run on the right (the solver's `wall_kitchen_end`), and the open cupboard in
  oak joinery with dishes on its shelf. Around them: red brick, a board-formed concrete soffit,
  a maple strip floor, black steel windows, oak base units and scanned props (a drawer cabinet,
  a wooden spoon in a utensil crock, a cutting board, avocados in a fruit bowl, a potted
  anthurium on the sill). `check_props` keeps every prop at least 2 cm from both bowls and out
  of their line of sight in every solved frame. `appearance/look_kitchen_bowl_fall.py` holds the
  shared materials and the lathe-turned ceramics: the falling bowl in a pale celadon glaze, the
  bowl on the hob in an oatmeal speckled glaze.
- **Light and render:** light comes only through the windows: a late-afternoon sun (18°
  elevation, strength 3.6) through a steel window in the left wall just out of frame, and sky
  through it, through the back-wall window and through a window behind the camera. Cycles,
  384 samples, OIDN denoising, AgX with exposure 0.30, motion blur with a 0.25-frame shutter and
  persistent data off.

## Physics

- PyBullet at 1440 Hz (60 substeps per 24 fps frame), 150 solver iterations, restitution
  velocity threshold 0.001 m/s, deterministic overlapping pairs, contact breaking threshold
  0.5 mm.
- Falling bowl: cylinder collider (closed convex hull of the bowl profile), lateral friction
  0.32, restitution 0.05, rolling friction 0.020, spinning friction 0.002, linear damping 0.02,
  angular damping 0.30, swept-sphere CCD (radius 0.05 m).
- Bowl on the hob: box collider 0.14 × 0.14 × 0.072 m with the bowl's footprint, lateral
  friction 0.50, restitution 0.05, rolling friction 0.005, spinning friction 0.006, angular
  damping 0.08, swept-sphere CCD. A box gives a stable contact manifold when the heavy-bowl edit
  pins this light body against the hob; a cylinder-on-cylinder contact in that case is resolved
  with a correction large enough to throw the bowl out of the kitchen.
- Static surfaces: kitchen boxes have lateral friction 0.55; the counter and floor boxes use the
  counter restitution (0.12) and every other kitchen box (hob glass, upstand, walls) uses the
  cupboard restitution (0.10). Cupboard boards and the door have friction 0.50 and restitution
  0.10.
- No push, force or keyed motion is applied: the falling bowl starts with its centre of mass past
  the lip and gravity does the rest.
- Timed edits change gravity at a frame boundary inside the running simulation; every frame
  before that is identical to the source.

## Measured motion

Source: frame 1 shows the bowl tilted in the open cupboard and an empty bowl on the hob. From 0
to 0.60 s the bowl tips out over its rim, slides off the lip and falls about 0.70 m, turning. At
0.596 s it hits the rim of the bowl below, which is pushed sideways by about 0.11 m (0.8 bowl
diameters) without tipping. At 0.82 s the falling bowl grazes the front edge of the hob and comes
to rest upside down on the counter; both bowls are at rest well before 4 s.

Measured per case (`quality` in each case's physics cache):

| Case | First hit on the bowl | First landing | Max bowl tilt | Bowl displacement | Max penetration |
| --- | --- | --- | --- | --- | --- |
| `source` | 0.596 s | 0.822 s (counter) | 0.0° | 0.11 m | 1.5 mm |
| `edit_heavy_bowl` | 0.596 s | 0.781 s (counter) | 2.4° | 1.47 m (against the end wall) | 1.5 mm |
| `edit_strong_gravity` | 0.343 s | 0.465 s (counter) | 0.0° | 0.13 m | 2.8 mm |
| `edit_remove_tableware` | — | 0.760 s (counter) | 0.0° | 0.00 m | 1.2 mm |
| `edit_bouncier_kitchen` | 0.595 s | 0.812 s (counter) | 0.0° | 0.12 m | 0.6 mm |
| `edit_gravity_off_after_impact` | 0.596 s | 0.846 s (grazes the counter) | 5.1° | 1.21 m | 1.5 mm |

## Validation

- `quality.valid` in each physics cache requires a maximum penetration below 12 mm and no body
  leaving the kitchen bounds at any time; `settled_by_end` and `final_speed_m_s` record whether
  everything is at rest on the last frame.
- On the source case the builder also requires that the falling bowl reaches the bowl below
  (`first_tableware_impact_sec`), that this bowl starts moving (`transmission_observed`), and
  that it is tilted at least 15° or displaced at least 0.08 m (`tableware_tilt_max_deg`,
  `tableware_displacement_m`). A shallow bowl struck on the rim slides rather than tips, so the
  displacement criterion is the one the source meets.
- The event log is grouped by moving body (`actor` = `falling_bowl` or `tableware`, `object` =
  the body touched) and records the first impact on the bowl, the counter and the floor, the
  maximum tilt, both displacements and the maximum penetration.
- `physics/validate_kitchen_bowl_fall.py` rejects a cache whose simulation signature, frame
  clock, frame count or presence schedule does not match its scenario.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source motion |
| `edit_heavy_bowl` | `SET falling_bowl.mass TIMES 10` | Falling bowl 0.55 → 5.5 kg; the bowl below is pushed along the whole counter (1.47 m) and stops against the kitchen's end wall |
| `edit_strong_gravity` | `SET world.gravity TIMES 3` | Gravity −9.81 → −29.43 m/s²; the bowl is hit at 0.34 s and the falling bowl is on the counter at 0.47 s |
| `edit_remove_tableware` | `DELETE tableware` | The bowl on the hob is absent from frame 1; the falling bowl hits the hob glass directly (0.76 s) and ends upside down on the counter |
| `edit_bouncier_kitchen` | `SET world.restitution TIMES 2` | All four restitutions doubled (falling bowl 0.05 → 0.10, bowl on the hob 0.05 → 0.10, counter 0.12 → 0.24, cupboard 0.10 → 0.20); the falling bowl bounces once more and settles at 1.42 s |
| `edit_gravity_off_after_impact` | `SET world.gravity TIMES 0 AT FRAME 19` | From frame 19 (t = 0.75 s), after the first impact at 0.596 s, gravity is zero; the falling bowl drifts away turning 5 cm above the hob (2.84 m), the bowl below keeps sliding at 0.35 m/s (1.21 m), and neither lands again |
| `edit_remove_falling_bowl` | `DELETE falling_bowl` | White cupboard bowl removed from frame 1 |

The builder names the source case `kitchen_bowl_fall_baseline`; the edit IDs are the published
case IDs (`--list-cases` prints them). `DELETE tableware` removes the single rigid body
`tableware_bowl`; `scene_geometry.present()` decides presence for the solver and the renderer.
`world.restitution` is one compound binding over the four restitution fields.

The gravity cut is at frame 19 rather than frame 16 (the first whole frame after the impact):
the rim-on-rim impact has an almost horizontal normal and gives the falling bowl about 0.9 m/s
along −x. Without gravity there is no normal force and no friction, so a cut at frame 16 lets the
bowl slide 2.9 m into the gap between the floor edge and the left wall. At frame 19 the bowl has
tumbled to 5 cm above the counter at 0.75 m/s and stops at x = −2.44, still over the floor.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `models` (`modern_kitchen.glb`) | manual | Kitchen model measured by `tools/export_room_colliders.py`; the render does not load it |
| `polyhaven/kitchen_bowl_fall` | manual | Scanned surfaces, props and the window view of the loft kitchen |
| `scenes/kitchen_bowl_fall` (`assets/scenes/kitchen_bowl_fall/room_colliders.json`) | derived | Kitchen collider boxes and probes shared by the solver and the renderer |

```bash
python3 scripts/download_assets.py --scene kitchen_bowl_fall           # fetch what can be fetched
python3 scripts/download_assets.py --scene kitchen_bowl_fall --check   # report only
```

Manual files need a provider login; the script prints where to get each one. `PCVE_ASSETS_DIR`
replaces the asset root.

## Requirements

- Python with PyBullet (`requirements.txt`: `pybullet>=3.2.5`); the repository's
  `.venv-domino/` environment (PyBullet 3.2.7) works. The entries run in the interpreter that
  invokes them; `--physics-python` / `PCVE_PHYSICS_PYTHON` select the solver interpreter.
- Blender 4.3 (tested with 4.3.2 at `tools/blender-4.3.2-linux-x64/`), passed with `--blender`
  or found from `$BLENDER`, `PATH` or `~/.local/opt/blender-*`. Alternatively `--render-python`
  / `PCVE_RENDER_PYTHON` names a Python with the `bpy` module.
- The physics runs on the CPU. Rendering uses Cycles on a GPU when available (`--device auto`)
  or on the CPU (`--device cpu`).

## Commands

Run from the repository root.

```bash
# List the cases and the native interface
.venv-domino/bin/python scripts/rigid_rigid/kitchen_bowl_fall/build_pcve_kitchen_bowl_fall.py --list-cases
.venv-domino/bin/python scripts/rigid_rigid/kitchen_bowl_fall/build_pcve_kitchen_bowl_fall.py --describe

# Physics for all six cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_bowl_fall/build_pcve_kitchen_bowl_fall.py \
    --out-root renders/kitchen_bowl_fall/new_run --simulate-only

# Physics and the full 96-frame video of one case (--cases selects a subset)
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_bowl_fall/build_pcve_kitchen_bowl_fall.py \
    --out-root renders/kitchen_bowl_fall/new_run --mode animation \
    --blender tools/blender-4.3.2-linux-x64/blender --cases kitchen_bowl_fall_baseline

# One case by hand: solve, then render keyframes from the cache
.venv-domino/bin/python scripts/rigid_rigid/kitchen_bowl_fall/simulate_kitchen_bowl_fall.py \
    --out renders/kitchen_bowl_fall/manual/physics_transforms.json
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/kitchen_bowl_fall/render_kitchen_bowl_fall.py -- \
    --physics-json renders/kitchen_bowl_fall/manual/physics_transforms.json \
    --out-dir renders/kitchen_bowl_fall/manual --mode keyframes --device cpu \
    --resolution 640 360 --samples 32

# Randomised batch on top of the same builder
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_bowl_fall/tools/render_queue.py \
    --out-root renders/kitchen_bowl_fall/batch --count 4 --simulate-only

# Re-measure the kitchen colliders (writes assets/scenes/kitchen_bowl_fall/room_colliders.json)
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/kitchen_bowl_fall/tools/export_room_colliders.py
```

The builder's `--mode` is `keyframes` by default (`preview` renders one frame, `animation` all
96 frames plus `video.mp4`); `--simulate-only` and `--render-only` split the two stages and
`--skip-existing` reuses a case whose asset and scenario fingerprint is unchanged. The
simulate entry also accepts `--scenario-json`, `--scenario-overrides-json`, one flag per
editable parameter (for example `--falling-bowl-mass`) and `--remove-tableware`.

## Outputs

A run writes `suite_manifest.json` and `cases/<case>/` under `--out-root` (default
`renders/kitchen_bowl_fall/suite_build/pcve_kitchen_bowl_fall_suite/`). Each case gets
`scenario_input.json`, `physics_transforms.json`, `simulation_metrics.json`, `prompts.json`,
`run_status.json` and, for edits, `scenario_overrides.json`; rendering adds `preview.png`,
`cases/<case>/keyframes.json` or `video.mp4`, `ground_truth_transforms.json`, `scenario_metadata.json`,
`render_validation.json` and the saved `kitchen_bowl_fall.blend`. The batch tool writes
`sample_<n>/` and `<out-root>/batch_manifest.json`. The published suite is
`renders/pcve_suites/pcve_kitchen_bowl_fall_suite/`; do not use it as an output root.

## Code layout

- `build_pcve_kitchen_bowl_fall.py`: suite builder (source and edits, prompts, acceptance checks).
- `simulate_kitchen_bowl_fall.py`: PyBullet solve of one scenario.
- `render_kitchen_bowl_fall.py`: Blender scene build, pose replay and render.
- `scene_config.py`: editable physics, render and camera defaults, limits and validation.
- `edit_vocab.py`: edit DSL vocabulary, bindings and the edit case list.
- `physics/scene_geometry.py`: measured dimensions, materials and solver constants.
- `physics/room_colliders.py`: loads and checks the kitchen collider file.
- `physics/validate_kitchen_bowl_fall.py`: cache validation and the simulation signature.
- `physics/input_hashes.py`: asset hashes used by the `--skip-existing` fingerprint.
- `appearance/loft_kitchen.py`: the loft kitchen, cupboard, props, windows and lighting.
- `appearance/look_kitchen_bowl_fall.py`: materials and lathe-turned ceramics.
- `tools/export_room_colliders.py`: Blender tool that measures the collider file from the model.
- `tools/render_queue.py`: randomised batch sampler.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry metadata, scene manifest
  and Python requirements.

## Limitations

- The bowl on the hob collides as a box with the bowl's footprint, not as a bowl.
- The falling bowl collides as a closed cylinder; its hollow interior has no collision.
- The cupboard carcass is built by the scene in the volume of the model's door panel; the model
  itself has no cupboard interior.
- Contact losses of ceramic on glass and stone are modelled with damping and rolling friction
  constants.
