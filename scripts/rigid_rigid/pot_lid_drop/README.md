# pot_lid_drop

A stainless steel pot lid slips off a pot on a kitchen worktop, falls 1.1 m edge-first onto the tiled
floor, rebounds, tips over its rim and curls flat. Rigid–rigid scene of PhyCoVE. Source video: 4 s,
24 fps, 96 frames, 1280×720.

## Scene

- Lid: cut from the pot model `a_pot.glb` by the renderer, 24 cm across (radius 0.12 m, rim 14 mm
  thick), 0.45 kg, ring-brushed stainless steel with a black bakelite knob. The pot body is polished
  stainless steel and stands on a flush induction hob on the worktop.
- Kitchen (`appearance/coastal_kitchen.py`): a galley kitchen. Dark grey granite floor tiles
  (`granite_tile`, 2.3 m repeat) whose top face is the solver's floor plane; `painted_plaster_wall`
  walls. Left: warm-white matt lacquered base units with recessed aluminium pulls, a 30 mm white quartz
  worktop at 1.036 m, a gooseneck tap and a 3000 K under-cabinet light strip. Right: charcoal tall units
  (fridge, oven, storage). The end wall has a black steel-framed floor-to-ceiling window showing the
  `dalkey_view` HDR (an overcast bay).
- Light: overcast skylight from the `dalkey_view` HDR through a window portal, three recessed
  downlights and the under-cabinet strip; no sun patch.
- Props (`appearance/kitchen_props.py`, not simulated): a wine bottle, two white ceramic jars and a bar
  stool, placed by bounding box on the worktop or floor. Every frame is checked: no static object other
  than the floor may come within 2 cm of the lid (or the added bowl) or block the camera's view of it.
  The closest distance over all cases is 2.42 cm (lid and pot handle in frame 1).
- Added bowl (`edit_add_bowl_at_landing`): oatmeal-glazed stoneware with an unglazed foot ring, radius
  0.11 m, 0.08 kg; its lathe profile is `edit_vocab.BOWL_PROFILE`, read by both the solver (collision
  hull) and the renderer (mesh).
- Camera: fixed, defined by the `layout` block of `assets/scenes/pot_lid_drop/scenario.json`.
- Render: Cycles, AgX Base Contrast, exposure +1.9 EV, motion blur with a 0.5-frame shutter,
  persistent data off.

## Physics

- Solver: PyBullet, 60 substeps per frame (1440 Hz at 24 fps), 150 solver iterations. Gravity
  −9.81 m/s².
- The scenario (`assets/scenes/pot_lid_drop/scenario.json`, blocks `assets`, `physics`, `layout`) is the
  single parameter source; case override files have the same shape and are merged key by key
  (`scene_config.py`).
- Lid: friction 0.5, rolling friction 0.0025, spinning friction 0.02, restitution 0.22, linear damping
  0.02, angular damping 0.03, collision margin 0.2 mm. Floor: friction 0.55, rolling and spinning
  friction 0.002. Bowl: restitution 0.2, friction 0.4.
- Collision shape: the renderer measures the lid mesh and writes its convex hull (`assets/scenes/pot_lid_drop/lid_hull.json`); the
  simulator loads it with `--lid-hull-json`. The registered copy is
  `assets/scenes/pot_lid_drop/lid_hull.json`. Without a hull the simulator falls back to an analytic
  disc and prints a warning.
- `ADD bowl BETWEEN rest_left AND rest_right AT MIDPOINT`: the endpoints are floor anchors one lid
  width either side of where the source lid comes to rest; the bowl stands at their midpoint.

## Measured motion

- Source: first touchdown on frame 13, rebound 0.066 m, the lid tips over its rim, curls 0.37 m across
  the floor and is at rest from frame 32.
- Two independent solves on Linux with PyBullet 3.2.7 are bit-identical. The simulate command below
  with the registered hull reproduces the published slide distance (0.2988 m).

## Cases

The builder's native source case is `pot_lid_drop_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Lid falls 1.1 m, tips over and lies flat from frame 32 |
| `edit_light_gravity` | `SET world.gravity TIMES 0.3` | Gravity −9.81 → −2.943 m/s² |
| `edit_add_bowl_at_landing` | `ADD bowl BETWEEN rest_left AND rest_right AT MIDPOINT` | Bowl present on the floor where the lid lands |
| `edit_slick_rim` | `SET lid.rolling_friction TIMES 0.1` | Lid rolling friction 0.0025 → 0.00025 |
| `edit_bouncy_lid` | `SET lid.restitution TO 0.45` | Lid restitution 0.22 → 0.45 |
| `edit_zero_gravity_timed` | `SET world.gravity TO 0 AT FRAME 14` | Gravity −9.81 → 0 from frame 14 |

## Assets

- `models` (manual): `a_pot.glb`, the pot and lid.
- `polyhaven/pot_lid_drop` (url): kitchen props, floor and wall textures and the window HDR.
- `scenes/pot_lid_drop` (derived): `assets/scenes/pot_lid_drop/scenario.json` (physics, layout and camera) and `assets/scenes/pot_lid_drop/lid_hull.json`
  (the measured lid hull).

Download and check them with `python3 scripts/download_assets.py --scene pot_lid_drop`
(add `--check` to only report).

## Requirements

- Simulation: Python with `pybullet==3.2.7` and `numpy` (`requirements.txt`; the repository's
  `.venv-domino` has them). CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU (CUDA or OptiX)
  for full-quality frames, CPU works for previews. The builder renders every case through Blender,
  which also runs the PyBullet solve.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene pot_lid_drop --check

# List the native case IDs
python3 scripts/rigid_rigid/pot_lid_drop/build_pcve_pot_lid_drop.py --list-cases

# Solve the source case on the CPU with the registered lid hull
.venv-domino/bin/python scripts/rigid_rigid/pot_lid_drop/simulate_pot_lid_drop.py \
    --out renders/pot_lid_drop/sim/physics_transforms.json \
    --lid-hull-json assets/scenes/pot_lid_drop/lid_hull.json --fps 24 --duration-sec 4

# Build the scene, solve and export ground truth for the source case without rendering frames
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/pot_lid_drop/render_pot_lid_drop.py -- \
    --mode build --out-dir renders/pot_lid_drop/source_build --device cpu \
    --physics-python .venv-domino/bin/python

# Build and render all six cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/pot_lid_drop/build_pcve_pot_lid_drop.py \
    --out-root renders/pot_lid_drop/suite_build \
    --blender tools/blender-4.3.2-linux-x64/blender --resolution 1280 720 --samples 48
```

`tools/render_queue.py` (workflow `batch_render`) samples cases through the shared
`pcve_batch_queue.batch_main`.

## Outputs

The commands above write to `renders/pot_lid_drop/`; the suite build goes to
`renders/pot_lid_drop/suite_build/`, one directory per case under `cases/`. Without `--out-root` the
builder writes to `renders/pot_lid_drop/suite_build/pcve_pot_lid_drop_suite/`. The published suite is
`renders/pcve_suites/pcve_pot_lid_drop_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_pot_lid_drop.py`: suite builder; renders every case through the render script.
- `simulate_pot_lid_drop.py`: PyBullet solve of the lid (and the added bowl); writes
  `physics_transforms.json`.
- `render_pot_lid_drop.py`: builds the scene in Blender, measures the lid hull, calls the simulator,
  renders and exports ground truth.
- `scene_config.py`: loads `assets/scenes/pot_lid_drop/scenario.json` and merges case overrides.
- `edit_vocab.py`: edit DSL vocabulary, case list and the bowl profile.
- `appearance/coastal_kitchen.py`: kitchen room, cabinetry, window and lighting.
- `appearance/cookware.py`: pot, lid and bowl materials.
- `appearance/kitchen_props.py`: prop placement and the clearance and occlusion checks.
- `tools/render_queue.py`: batch sampler.

## Limitations

- The lid's collider is its convex hull, which fills the hollow underside.
- The builder has no simulate-only stage; trajectories without rendering come from the simulate entry
  or the render script's `--mode build`.
- A Windows PyBullet build differs by about 1e-7 m in position and up to 5.2e-5 m/s in velocity in some
  cases.
