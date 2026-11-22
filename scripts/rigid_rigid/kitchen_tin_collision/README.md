# kitchen_tin_collision

A rigid–rigid scene in PhyCoVE. On a bistro table at dusk, a round tuna tin lying flat slides
along a red-and-white checked tablecloth and strikes the long face of a sardine tin at rest,
off-centre, sending it sliding away with a twist. PyBullet solves the sliding and the impact;
Blender only replays the solved poses. The source video is 4 s at 24 fps (96 frames, 1280×720);
frame i is the solver state at t = (i−1)/24.

## Scene

- **Units and axes:** SI, Z up, gravity −9.81 m/s²; the table top is the world origin (z = 0)
  and the driving tin moves along +X. All editable inputs are in `scene_config.py`
  (`BASELINE_PHYSICS`); fixed geometry is in `physics/scene_geometry.py`.
- **Table:** a fixed box whose top is the flat top of the cloth, 1.077 × 0.660 m (half extents
  0.5385 × 0.330), at z = 0.
- **Room:** floor at z = −0.749 (a 0.7475 m table plus the cloth), walls at
  x = −2.60 / 1.25 and y = −2.60 / 1.30, ceiling 3.0 m above the floor. The solver builds floor
  and wall boxes from these numbers and `appearance/bistro_room.py` builds the visible room on
  the same planes.
- **Driving tin (tuna tin):** 0.20 kg, 0.080 m across, 0.0271 m tall, lying on its base (axis
  along Z), so its whole base is the contact face and it slides. Its collider is a convex hull
  of a rolled-rim profile revolved at 128 segments. It starts at (−0.42, −0.022) with 1.55 m/s
  along +X and no spin.
- **Struck tin (sardine tin):** 0.125 kg, a 0.129 × 0.075 × 0.036 m box, at rest at (0.018, 0),
  turned 90° about Z so its 129 mm long face meets the driving tin. The launch line is 22 mm off
  its centre line, so the hit lands on the flank of the long face and turns the tin.
- **Camera:** fixed at (−0.607, −0.747, 0.497) looking at (−0.17, 0.02, 0.028), 28 mm lens,
  f/5.6.
- **Room appearance:** `appearance/bistro_room.py` builds a bistro corner at dusk: a scanned
  wooden table scaled uniformly by 0.935 (0.7475 m high, inside the projection of the collision
  box) under a red-and-white checked cotton cloth (400 mm tile, real size) generated from the
  collision box: its flat top is the box top (a 15-point ray check at render time, deviation 0),
  it rolls over the edge with an 8 mm radius and hangs 23.5 cm with outward-bellying folds,
  conical corner drops and a turned hem; ironing creases are bump only. Mahogany wainscot
  (1.26 m high, with a capping moulding), warm lime-plaster walls and a terrazzo floor; the
  right-hand wall is a dark-green timber shop-front window (thin glass with a back-face IOR
  correction) with a white cotton half-curtain on a brass rod over its lower half. Four buttoned
  leather dining chairs and a lit wooden candlestick on the table.
- **Tins:** `appearance/look_kitchen_tin_collision.py` imports both tin models, keeps their
  geometry and normal maps (lid scoring, seams, ring pull) and replaces the printed colour with
  plain finishes: the tuna tin has bare tinplate ends and a body in one plain navy ink under
  clear lacquer, the sardine tin is bare aluminium. Each mesh is fitted with one uniform scale
  factor after restoring the world matrix the glTF node empties carry (a millimetre-to-metre
  conversion for the tuna tin, a non-uniform authored scale for the sardine tin); the gap to the
  solver's shape stays under 0.4 mm. No orientation is baked into the meshes: each tin's pose is
  the world matrix the solver reports.
- **Light and render:** only sources in the picture: two brass chandeliers whose bulbs emit
  (one over this table, one over the next table out of shot), the candle flame on the table, and
  the dusk sky through the window (a smooth sky dome with a portal in the window). A street
  photograph outside is visible to camera rays only. Cycles, OIDN denoising, AgX (Medium High
  Contrast) with exposure +0.75, indirect clamp 10, motion blur with a 0.25-frame shutter and
  persistent data off. The published videos use 256 samples.

## Physics

- PyBullet at 1440 Hz (60 substeps per 24 fps frame), 140 solver iterations, restitution
  velocity threshold 0.001 m/s, deterministic overlapping pairs, contact breaking threshold
  0.3 mm.
- Tins: restitution √0.35 each, so the tin–tin pair restitution is 0.35; rolling friction
  0.0016 (tuna) and 0.0004 (sardine), spinning friction 0.0001, no damping, collision margin
  0.1 mm.
- **Friction:** Bullet keeps one `lateralFriction` per body and multiplies the two at a
  contact, so friction is declared per body: `driver_friction` 0.20, `receiver_friction` 0.20,
  `table_friction` 1.0. The table and the tins have restitution 0 and √0.35; the floor has
  friction 0.62 and restitution 0.10, the walls 0.55 and 0.18.
- **Settling:** the tins run 240 settle steps with the source coefficients (0.20 and 1.0)
  before frame 1; the declared friction values are written afterwards and then the driving tin
  receives its velocity.
- **Timed edits:** at the frame boundary named by `AT FRAME`, the simulator writes the new value
  into the running simulation and logs it in `timed_events` with the value before and after and
  the body states. Timed values are checked against `TIMED_FIELDS`.

## Measured motion

Source: first contact at 0.285 s, 22 mm off the struck tin's centre along Y (34 % of its
64.5 mm half-length). The struck tin is pushed 0.155 m, turns 79.1° about Z with at most 2.8° of
tilt, and stops at 0.70 s; the driving tin moves 0.433 m and turns −3.0°. In every case both
tins stay on the cloth (closest 7.85 cm to the table edge), so the only static surface they
touch is the cloth top. The driving tin slides flat, so `max_preimpact_slip_ratio` is about 1
(pure sliding). Two runs of all cases with PyBullet 3.2.7 on Linux are byte-identical.

## Validation

- `quality.valid` requires a maximum penetration below 2 mm, no body below the floor (5 mm
  tolerance) and a struck-tin tilt below 60°. The tilt is counted only while
  a tin is within 2 cm above the table. `stayed_on_table` is recorded separately.
- On the source case the builder requires `transmission_observed` (the struck tin reaches more
  than 0.02 m/s).
- `physics/validate_kitchen_tin_collision.py` rejects a cache whose simulation signature, frame
  count, frame clock or presence schedule does not match its scenario.
- The render fails unless every tin still on the cloth keeps a screen margin of at least 0.015,
  every prop on the table and in the room stays at least 2 cm from each tin's bounding sphere
  (closest: the candlestick, 12.7 cm), and the sight lines from the camera to each tin's centre
  and 8 inset corners are not blocked by another object.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source motion |
| `edit_heavy_driver` | `SET driver_can.mass TIMES 5` | Driving tin 0.20 → 1.00 kg; the struck tin slides 0.337 m and turns −250.6° |
| `edit_heavy_receiver` | `SET receiver_can.mass TIMES 10` | Struck tin 0.125 → 1.25 kg; it moves about 1 mm and turns less than 1° |
| `edit_remove_receiver` | `DELETE receiver_can` | The struck tin is absent from frame 1; the driving tin slides through the empty spot and stops on the table at 0.788 s after 0.612 m |
| `edit_receiver_friction_drop` | `SET receiver_can.friction TIMES 0.25 AT FRAME 11` | From frame 11 (t = 0.417 s), 0.13 s after the hit, the struck tin's friction drops 0.20 → 0.05; it slides until 1.50 s and covers 0.364 m |
| `edit_remove_driver_can` | `DELETE driver_can` | Round dark blue tin removed from frame 1 |

The builder names the source case `kitchen_tin_collision_baseline`; the edit IDs are the
published case IDs (`--list-cases` prints them). `DELETE receiver_can` sets `receiver_active` to
0, so the body is never created, carries no transforms and is not rendered. `edit_vocab.py` also
declares `driver_can.initial_velocity`, `receiver_can.initial_velocity`, `driver_can.friction`,
`table.friction` and `pair.restitution`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `models` (`tuna_can.glb`, `sardine_can.glb`) | manual | Tin models for the driving and struck tins |
| `polyhaven/kitchen_tin_collision` | manual | Scanned surfaces, furniture, chandeliers, candlestick and the window photograph of the bistro |

```bash
python3 scripts/download_assets.py --scene kitchen_tin_collision           # fetch what can be fetched
python3 scripts/download_assets.py --scene kitchen_tin_collision --check   # report only
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
.venv-domino/bin/python scripts/rigid_rigid/kitchen_tin_collision/build_pcve_kitchen_tin_collision.py --list-cases
.venv-domino/bin/python scripts/rigid_rigid/kitchen_tin_collision/build_pcve_kitchen_tin_collision.py --describe

# Physics for all five cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_tin_collision/build_pcve_kitchen_tin_collision.py \
    --out-root renders/kitchen_tin_collision/new_run --simulate-only

# Physics and keyframes for all cases at preview quality
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_tin_collision/build_pcve_kitchen_tin_collision.py \
    --out-root renders/kitchen_tin_collision/new_run --resolution 640 360 --samples 64 \
    --blender tools/blender-4.3.2-linux-x64/blender

# Physics and full 96-frame videos at the published settings (video.mp4 per case)
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_tin_collision/build_pcve_kitchen_tin_collision.py \
    --out-root renders/kitchen_tin_collision/new_run --mode animation --samples 256 \
    --blender tools/blender-4.3.2-linux-x64/blender

# One case by hand: solve, then render keyframes from the cache
.venv-domino/bin/python scripts/rigid_rigid/kitchen_tin_collision/simulate_kitchen_tin_collision.py \
    --out renders/kitchen_tin_collision/manual/physics_transforms.json
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/kitchen_tin_collision/render_kitchen_tin_collision.py -- \
    --physics-json renders/kitchen_tin_collision/manual/physics_transforms.json \
    --out-dir renders/kitchen_tin_collision/manual --mode keyframes --device cpu \
    --resolution 640 360 --samples 16

# Randomised batch (masses, speed, restitution, frictions) on top of the same builder
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/kitchen_tin_collision/tools/render_queue.py \
    --out-root renders/kitchen_tin_collision/batch --count 4 --simulate-only
```

In `keyframes` mode (the default) each case renders frame 1, the frames just before and at
first contact, contact + 6, frame 49 and frame 96 (frames 1, 7, 8, 14, 49 and 96 in the
source), plus `preview.png`; `--keyframes` selects other frames. `--mode animation` renders all
96 frames and writes `video.mp4`. `--cases` builds a subset, `--simulate-only` and
`--render-only` split the two stages and `--skip-existing` reuses a case whose fingerprint is
unchanged.

## Outputs

A run writes `suite_manifest.json` and `cases/<case>/` under `--out-root` (default
`renders/kitchen_tin_collision/suite_build/pcve_kitchen_tin_collision_suite/`). Each case gets
`scenario_input.json`, `physics_transforms.json`, `simulation_metrics.json`, `prompts.json`,
`run_status.json` and, for edits, `scenario_overrides.json`; rendering adds `preview.png`,
keyframes or `video.mp4`, `ground_truth_transforms.json`, `scenario_metadata.json`,
`render_validation.json` and the saved `.blend`. The batch tool writes `sample_<n>/` and
`<out-root>/batch_manifest.json`. The published suite is
`renders/pcve_suites/pcve_kitchen_tin_collision_suite/`; do not use it as an output root.

## Code layout

- `build_pcve_kitchen_tin_collision.py`: suite builder (source and edits, prompts, acceptance check).
- `simulate_kitchen_tin_collision.py`: PyBullet solve of one scenario, including timed writes.
- `render_kitchen_tin_collision.py`: Blender scene build, pose replay, checks and render.
- `scene_config.py`: editable physics, render and camera defaults, limits and validation.
- `edit_vocab.py`: edit DSL vocabulary, bindings, the edit case list and the source prompts.
- `physics/scene_geometry.py`: table, room and tin geometry and solver constants.
- `physics/validate_kitchen_tin_collision.py`: cache validation and the simulation signature.
- `physics/input_hashes.py`: asset hashes used by the `--skip-existing` fingerprint.
- `appearance/look_kitchen_tin_collision.py`: tin import, uniform fit and tin finishes.
- `appearance/bistro_room.py`: the bistro room, table, cloth, furniture and lighting.
- `tools/render_queue.py`: randomised batch sampler.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry metadata, scene manifest
  and Python requirements.

## Limitations

- The sardine tin collides as a box and the tuna tin as a convex hull; the ring pull and lid
  recesses have no collision.
- The cloth is shading and geometry around a rigid box; it is not simulated and does not deform
  under the tins.
- Friction is set per body; a tin–table contact uses the product of the tin and table values.
