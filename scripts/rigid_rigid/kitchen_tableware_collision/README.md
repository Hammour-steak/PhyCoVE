# kitchen_tableware_collision

A rigid–rigid scene in PhyCoVE. On a granite kitchen island at night, a celadon shallow bowl
slides along the counter into an ivory shallow bowl; after the collision both bowls slow down
and stop. PyBullet solves the sliding and the impact; Blender only replays the solved poses. The
source video is 4 s at 24 fps (96 frames, 1280×720); frame i is the solver state at
t = (i−1)/24.

## Scene

- **Units and axes:** SI, Z up, gravity −9.81 m/s²; the bowls move along +X on y = 0. All
  editable inputs are in `scene_config.py` (`BASELINE_PHYSICS`); fixed geometry is in
  `physics/scene_geometry.py`.
- **Counter:** a fixed box 3.04 × 0.98 m (x ±1.52, y ±0.49), top at z = 0.9458 m. There is no
  floor collider.
- **Bowls:** both 0.28 kg, 0.17 m across (rim radius 0.085 m) and 0.042 m tall, sharing one
  lathe profile (foot ring, underside, wall, rim and inner floor). The collider is the convex
  hull of that profile, so it fills the bowl's interior; nothing enters the interior. The left
  bowl (A, celadon) starts at x = −0.67 with +0.72 m/s; the right bowl (B, ivory) stands at rest
  at x = 0.
- **Camera:** fixed at (0.35, −1.85, 1.64) looking at (0.08, 0.18, 1.15), 38 mm lens, f/8.
- **Room:** `appearance/city_kitchen.py` builds a city apartment kitchen at night. The island is
  a single 30 mm slab of honed grey granite whose top is the counter box, so what the bowls
  touch on screen is the collision surface. The granite scan (a 0.9 m floor tile with grout) is
  cut into blocks of about 0.2 m taken from inside the tiles and reassembled without grout lines,
  with saturation lowered to 0.3. Joinery: handleless smoked-oak fronts with 3 mm gaps and a
  recessed aluminium pull rail; along the back wall a run of granite-topped base units with a
  black glass induction hob carrying a brass pot, and a floor-to-ceiling tall unit on the right;
  micro-cement walls. Two walnut shelves, each with a warm LED strip under it; the lower one
  carries 4 off-white plates, 3 stacked celadon bowls from the same lathe profile as the
  simulated bowl, and a round white vase.
- **Window:** a real opening in the back wall with a black aluminium frame and thin glass
  (back-face IOR correction). A gathered linen café curtain on a tension rod covers the lower
  half (top at about 1.55 m); above it a night city skyline HDR is visible to camera rays only
  and does not light the room; all other rays see a very dark night sky.
- **Light:** only fittings in the room: two opal-glass pendants over the island with glowing
  bulbs (2700 K), 6 recessed ceiling downlights (3000 K, 70°) and the LED strips under the
  shelves. No invisible fill panels.
- **Props:** `appearance/kitchen_props.py` places scanned props by their bounding boxes: on the
  back edge of the island a pear and a small wooden bowl with 3 lychees; on the back counter a
  blue-and-white jar, a teapot with cups and two wine bottles; the brass pot on the hob. Props on
  the island are confirmed by a downward ray to stand on the granite, and no two intersect.
- **Bowls:** `appearance/look_kitchen_tableware_collision.py` builds both bowls from the
  simulation's lathe profile: A in a celadon glaze, B in an off-white stoneware glaze with iron
  speckles; both have a clear glaze coat that darkens where the glaze pools and a slight
  orange-peel surface, and an unglazed foot ring (iron red for A, pale buff for B).
- **Render:** Cycles, AgX (Medium High Contrast) with exposure 1.0, motion blur with a
  0.5-frame shutter and persistent data off.

## Physics

- PyBullet at 1440 Hz (60 substeps per 24 fps frame), 120 solver iterations, restitution
  velocity threshold 0.001 m/s, deterministic overlapping pairs, contact breaking threshold
  0.5 mm.
- Bowls: lateral friction 0.018 (`tableware_friction`), restitution √0.68 each so the bowl–bowl
  pair restitution is 0.68, spinning friction 0.001, rolling friction 0.0001, no damping,
  collision margin 0.1 mm. The counter has lateral friction 1.0 and restitution 0, so the
  bowl–counter friction is 0.018.
- The bowls are placed 0.15 mm above the counter and run 180 settle steps before the initial
  velocities are applied; the settle is not part of the clip.
- **Timed edit:** at the frame boundary named by `AT FRAME`, the new `tableware_friction` is
  written into every live bowl and the run continues from the state it reached; the write is
  logged in `timed_events` with the value before and after.
- The two bowls' collision is logged with pre- and post-impact velocities, the axial
  separation/approach speed ratio and the change of X momentum.

## Measured motion

In the source the struck bowl, hit on its rim, rocks by about 6° and hops by about 4 mm, then
both bowls slide to rest. The collision starts about frame 19. In `edit_fast_driver` both bowls
slide off the right end of the island and fall out of frame; with no floor they keep falling.

## Validation

- `quality.valid` requires a maximum penetration below 2 mm and a maximum tilt below 25° while a
  bowl rests on the counter (inside the footprint and at surface height). A bowl that slides off
  the counter is listed in `bowls_left_counter` and is not checked further.
- On the source case the builder requires `transmission_observed` (the struck bowl reaches more
  than 0.02 m/s).
- `physics/validate_kitchen_tableware_collision.py` rejects a cache whose simulation signature,
  frame count, frame clock or presence schedule does not match its scenario.
- The render fails unless, on every frame, every prop's bounding box keeps at least 2 cm from
  each bowl's bounding box; while a bowl is on the counter and in frame, the 4 sight lines from
  the camera to it hit only bowls; and the replayed matrices differ from the physics matrices by
  at most 2e-6. Results go to `render_validation.json`. All six cases pass; the smallest
  prop-to-bowl distance is 0.20 m.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source motion |
| `edit_heavy_driver` | `SET bowl_a.mass TIMES 5` | Left bowl 0.28 → 1.40 kg |
| `edit_fast_driver` | `SET bowl_a.initial_velocity TIMES 5` | Left bowl launch 0.72 → 3.6 m/s; both bowls slide off the right end of the island |
| `edit_no_restitution` | `SET pair.restitution TO 0` | Bowl–bowl restitution 0.68 → 0 (perfectly plastic) |
| `edit_remove_receiver` | `DELETE bowl_b` | The right bowl is absent from frame 1 |
| `edit_frictionless_counter_timed` | `SET bowls.friction TIMES 0 AT FRAME 21` | From frame 21 (t = 0.833 s), just after the collision, both bowls have zero friction on the counter and coast on without stopping |
| `edit_remove_bowl_a` | `DELETE bowl_a` | Left celadon bowl removed from frame 1 |

The builder names the source case `kitchen_tableware_collision_baseline`; the edit IDs are the
published case IDs (`--list-cases` prints them). `DELETE bowl_b` sets `receiver_active` to 0, so
the body is never created, carries no transforms and is not rendered.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `polyhaven/kitchen_tableware_collision` | url | Scanned surfaces, props, pendants and the window HDR |
| `scenes/kitchen_tableware_collision` (`assets/scenes/kitchen_tableware_collision/asset_sources.json`, `assets/scenes/kitchen_tableware_collision/scenario.json`) | derived | Provenance records of the scene's assets; not read by the code |

`assets.json` also lists this scene under the shared `models` key; the scene reads none of its
files.

```bash
python3 scripts/download_assets.py --scene kitchen_tableware_collision           # fetch what can be fetched
python3 scripts/download_assets.py --scene kitchen_tableware_collision --check   # report only
```

`PCVE_ASSETS_DIR` replaces the asset root.

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
.venv-domino/bin/python scripts/rigid_rigid/kitchen_tableware_collision/build_pcve_kitchen_tableware_collision.py --list-cases
.venv-domino/bin/python scripts/rigid_rigid/kitchen_tableware_collision/build_pcve_kitchen_tableware_collision.py --describe

# Physics for all six cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_tableware_collision/build_pcve_kitchen_tableware_collision.py \
    --out-root renders/kitchen_tableware_collision/new_run --simulate-only

# Physics and full 96-frame videos (video.mp4 per case)
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_tableware_collision/build_pcve_kitchen_tableware_collision.py \
    --out-root renders/kitchen_tableware_collision/new_run --mode animation --resolution 1280 720 \
    --blender tools/blender-4.3.2-linux-x64/blender

# One case by hand: solve, then render keyframes from the cache
.venv-domino/bin/python scripts/rigid_rigid/kitchen_tableware_collision/simulate_kitchen_tableware_collision.py \
    --out renders/kitchen_tableware_collision/manual/physics_transforms.json
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/kitchen_tableware_collision/render_kitchen_tableware_collision.py -- \
    --physics-json renders/kitchen_tableware_collision/manual/physics_transforms.json \
    --out-dir renders/kitchen_tableware_collision/manual --mode keyframes --device cpu

# Randomised batch (masses, speeds, restitution) on top of the same builder
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_tableware_collision/tools/render_queue.py \
    --out-root renders/kitchen_tableware_collision/batch --count 4 --simulate-only
```

The builder's `--mode` is `keyframes` by default (`preview` renders one frame, `animation` all
96 frames plus `video.mp4`); `--cases` builds a subset, `--simulate-only` and `--render-only`
split the two stages and `--skip-existing` reuses a case whose fingerprint is unchanged.

## Outputs

A run writes `suite_manifest.json` and `cases/<case>/` under `--out-root` (default
`renders/kitchen_tableware_collision/suite_build/pcve_kitchen_tableware_collision_suite/`). Each
case gets `scenario_input.json`, `physics_transforms.json`, `simulation_metrics.json`,
`prompts.json`, `run_status.json` and, for edits, `scenario_overrides.json`; rendering adds the
preview, keyframes or `video.mp4`, `ground_truth_transforms.json`, `scenario_metadata.json`,
`render_validation.json` and the saved `.blend`. The batch tool writes `sample_<n>/` and
`<out-root>/batch_manifest.json`. The published suite is
`renders/pcve_suites/pcve_kitchen_tableware_collision_suite/`; do not use it as an output root.

## Code layout

- `build_pcve_kitchen_tableware_collision.py`: suite builder (source and edits, prompts, acceptance check).
- `simulate_kitchen_tableware_collision.py`: PyBullet solve of one scenario, including the timed friction write.
- `render_kitchen_tableware_collision.py`: Blender scene build, pose replay, checks and render.
- `scene_config.py`: editable physics, render and camera defaults, limits and validation.
- `edit_vocab.py`: edit DSL vocabulary, bindings and the edit case list.
- `physics/scene_geometry.py`: shared lathe profile, collision hull and solver constants.
- `physics/validate_kitchen_tableware_collision.py`: cache validation and the simulation signature.
- `physics/input_hashes.py`: asset hashes used by the `--skip-existing` fingerprint.
- `appearance/look_kitchen_tableware_collision.py`: the two bowls, glazes and shelf tableware.
- `appearance/city_kitchen.py`: room, island, joinery, window and lights.
- `appearance/kitchen_props.py`: scanned props and their placement.
- `tools/render_queue.py`: randomised batch sampler.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry metadata, scene manifest
  and Python requirements.

## Limitations

- The bowl–counter friction is 0.018, far below glazed stoneware on stone (about 0.2–0.4); with
  such a value the left bowl stops within 10 cm and does not reach the right bowl.
- The bowls collide as convex hulls that fill their interiors.
- There is no floor: bowls that leave the counter fall indefinitely (out of frame).
- Results depend on the PyBullet build. With PyBullet 3.2.7 on Linux two runs are
  byte-identical; a Windows build of the same version differs after the impact (largest
  per-frame position difference between 9.3e-6 m and 5.1e-2 m across the cases), with the same
  contact order and the same effect of each edit.
