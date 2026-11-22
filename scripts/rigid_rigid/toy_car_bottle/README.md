# toy_car_bottle

A die-cast toy car rolls across the tatami floor of a Japanese-style room and hits an empty plastic
bottle standing in its lane; the bottle trips over and slides away while the car stops. Rigid–rigid
scene of PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Car: mass 0.35 kg, starting at x = −0.48 m with 1.3 m/s along +x. The physics body is a box sized
  to the rendered car model; the wheel rotation exists only in the render.
- Bottle: an empty PET bottle (radius 41 mm), mass 0.02 kg, upright at (0, 0.012). A second bottle
  slot, `bottle_2`, is absent unless an ADD edit enables it. The baseline values live in
  `assets/scenes/toy_car_bottle/scenario.json`; `scene_config.py` adds the derived anchors shared by
  solver, renderer and edit vocabulary.
- Room (`appearance/washitsu.py`, layout in `ROOM` / `LOOK` of `appearance/look_toy_car_bottle.py`):
  ten 0.9 × 1.8 m tatami mats laid in the traditional pattern form a 3.6 × 4.5 m floor whose top is
  the solver's ground plane z = 0. Walls at x = −1.55 / 2.05 m and y = −1.85 / 2.65 m, ceiling
  2.40 m, hinoki posts in the corners. The back wall is four barred shoji with washi paper and a
  veranda behind it; the side walls are juraku clay (`clay_plaster`); the west wall (out of frame)
  has two glass sliding doors.
- Furnishing (not simulated): a lacquered low table, two indigo floor cushions and a white ceramic
  vase (`ceramic_vase_04`).
- Bottle look: thin-walled PET with Fresnel reflection, a matt HDPE cap and a printed shrink label
  with a blue wave pattern; the bottle's shadow uses a transmission of 0.75.
- Lighting: daylight only. A sun lamp (elevation 30°, light travelling 15° off +x) and a Nishita sky
  enter through the west glass doors, with a sky portal in the door opening.
- Camera: the ground-truth camera from the scenario (28 mm lens) at tatami height.
- Render: Cycles, 32 samples with denoising, AgX Base Contrast, exposure 0, motion blur with a
  0.5-frame shutter, persistent data off.

## Physics

- Solver: PyBullet, 24 fps × 80 substeps (1920 Hz), 100 solver iterations, gravity −9.81 m/s².
  The builder runs `simulate_toy_car_bottle.py` with the physics interpreter.
- Floor: a static plane, friction 0.5, restitution 0.6.
- Car: box collider, friction 0.40, restitution 0.1. Bottle: convex hull of the bottle profile,
  friction 0.5, restitution 0.8, linear damping 0.02, angular damping 0.04. Restitution velocity
  threshold 0.015 m/s.
- Timed events are checked against the simulated frame range and the allowed physics fields, and their
  before/after values are written to `physics_transforms.json`. The timed speed edit changes the car's
  velocity without moving it.
- Two simulation runs on the same machine are byte-identical.

## Measured motion

Car friction sweep, 0.14 to 0.50 in steps of 0.02 (restitution 0.1, everything else fixed).
Displacements in m; "edge" is the first frame a body's bounding box crosses the frame edge, "out" the
first frame more than half of a body is outside the frame, "—" never.

| car_friction | Source bottle | `edit_heavy_bottle` bottle | `edit_slippery_bottle` bottle | Earliest edge | Earliest out |
| --- | --- | --- | --- | --- | --- |
| 0.14 | 0.709, topples | 0.451 | 1.102 | 17 | 19 |
| 0.16–0.24 | 0.615–0.423, topples | 0.424–0.336 | 1.028–0.738 | 17–18 | 19–20 |
| 0.26–0.36 | 0.395–0.277, topples | 0.318–0.239 | 0.665–0.373 | 16–20 | 19–26 |
| 0.38 | 0.255, topples | 0.221, topples | 0.320 | 21 | — |
| 0.40 | 0.234, topples | 0.058, stays upright | 0.268, slides upright | 22 | — |
| 0.42–0.46 | 0.068–0.039, stays upright | 0.047–0.028 | 0.213–0.129 | 22–24 | — |
| 0.48–0.50 | 0.030–0.015, stays upright | 0.021–0.011 | 0.084–0.040 | — | — |

The scene uses 0.40. Key numbers at 0.40 (a body counts as stopped once its speed stays below
5 mm/s):

| Case | First contact frame | Bottle displacement | Bottle topples | Bottle stop frame | Car stops at x / frame |
| --- | --- | --- | --- | --- | --- |
| `source` | 10 | 0.234 m | yes | 54 | −0.076 / 16 |
| `edit_heavy_bottle` | 10 | 0.058 m | no | 38 | −0.102 / 23 |
| `edit_fast_car` | 6 | 0.700 m | yes | 49 | 0.356 / 23 |
| `edit_slippery_bottle` | 10 | 0.268 m | no (slides upright) | 32 | −0.074 / 17 |
| `edit_add_midpoint_bottle` | car hits bottle 2 at 3, bottle 2 hits bottle 1 at 7 | bottle 1 0.122 m, bottle 2 0.280 m | no | 21 / 24 | −0.118 / 16 |
| `edit_fast_car_midflight` | 7 | 0.879 m | yes | 31 | 0.523 / 27 |

The bottle's peak speed is 0.98 m/s in the source and 1.47 m/s in `edit_fast_car`. In
`edit_fast_car_midflight` the toppled bottle has a corner past the right frame edge from frame 22
on and stays at least 76 % in frame. Every moving body stays at least 0.36 m from the props and walls.

## Validation

Before rendering, `check_props` replays the whole trajectory: the bounding sphere of every moving body
must stay at least 2 cm from every piece of furniture, the corner posts and the wall plaster, and the
camera's lines of sight to each body's centre and eight corners must not be blocked by the room or a
prop; otherwise the render fails. The result is stored under `appearance` in
`scenario_metadata.json`.

## Cases

The builder's native source case is `toy_car_bottle_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Car at 1.3 m/s hits the single bottle |
| `edit_heavy_bottle` | `SET bottle.mass TIMES 4` | Bottle mass 0.02 → 0.08 kg |
| `edit_fast_car` | `SET car.initial_velocity TIMES 1.5` | Car launch speed 1.3 → 1.95 m/s |
| `edit_slippery_bottle` | `SET bottle.friction TIMES 0.25` | Bottle friction 0.5 → 0.125 |
| `edit_add_midpoint_bottle` | `ADD bottle_2 BETWEEN car AND bottle AT MIDPOINT` | A second bottle stands upright halfway between car and bottle |
| `edit_fast_car_midflight` | `SET car.speed TIMES 1.5 AT FRAME 5` | Car speed 1.3 → 1.95 m/s from frame 5 |
| `edit_delete_car` | `DELETE car` | Toy car removed from frame 1 |
| `edit_delete_bottle` | `DELETE bottle` | Plastic water bottle removed from frame 1 |

## Assets

- `models` (manual): the toy car model and `plastic_water_bottle.glb`; `--models-dir` points the
  renderer to another directory holding these two files.
- `polyhaven/toy_car_bottle` (url): tatami, clay plaster, wood and fabric scans and the vase model
  used by `appearance/washitsu.py`.
- `scenes/toy_car_bottle` (derived): `assets/scenes/toy_car_bottle/scenario.json` (the baseline physics and layout, read by all
  three entries) and `assets/scenes/toy_car_bottle/ASSET_SOURCES.json`.

Download and check them with `python3 scripts/download_assets.py --scene toy_car_bottle`
(add `--check` to only report).

## Requirements

- Simulation: Python with `pybullet` (`requirements.txt`; the repository's `.venv-domino` has it).
  CPU only.
- Rendering: Blender 4.3.2. The builder takes `--blender` or `BLENDER_BIN`; without them it uses
  `tools/blender-4.3.2-linux-x64/blender` of the repository, else `blender` on PATH. Cycles on an
  NVIDIA GPU (`--device auto`, the default); `--device cpu` works for previews.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene toy_car_bottle --check

# List the native case IDs
python3 scripts/rigid_rigid/toy_car_bottle/build_pcve_toy_car_bottle.py --list-cases

# Simulate all six cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/toy_car_bottle/build_pcve_toy_car_bottle.py \
    --out-root renders/toy_car_bottle/suite_build --simulate-only

# Simulate and render all six cases at the published settings (1280x720, 32 samples, animation)
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/toy_car_bottle/build_pcve_toy_car_bottle.py \
    --out-root renders/toy_car_bottle/suite_build --blender tools/blender-4.3.2-linux-x64/blender
```

The builder has no render-only switch; a full run simulates and renders every selected case.
`tools/render_queue.py` (workflow `batch_render`) calls the builder's `batch_main`, which scales every
simulated parameter by a seeded factor in 0.8–1.2 per sample and writes to
`renders/batch_toy_car_bottle`.

## Outputs

The commands above write to `renders/toy_car_bottle/suite_build/`, one directory per case under
`cases/`. Without `--out-root` the builder writes to
`renders/toy_car_bottle/suite_build/pcve_toy_car_bottle_suite/`. The published suite is
`renders/pcve_suites/pcve_toy_car_bottle_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_toy_car_bottle.py`: suite builder; carries its own copy of the runtime helpers
  (interpreter and Blender lookup, build arguments) and the batch entry
  `batch_main`.
- `simulate_toy_car_bottle.py`: PyBullet solve; writes `physics_transforms.json`.
- `render_toy_car_bottle.py`: Blender replay and render, with its own copy of the runtime helpers.
- `scene_config.py`: loads `assets/scenes/toy_car_bottle/scenario.json` and adds the shared derived anchors.
- `edit_vocab.py`: edit DSL vocabulary and case list; `prepare_config` is imported by the simulate
  and render entries.
- `appearance/look_toy_car_bottle.py`: room layout, bottle and car materials, light grade and the
  `check_props` clearance check.
- `appearance/washitsu.py`: tatami room, shoji, walls, glass doors and furniture.
- `tools/render_queue.py`: thin wrapper around `batch_main`.

## Limitations

- The car is a box collider; the wheels do not roll in the simulation and the car slides with
  friction 0.40.
- The bottle is a rigid convex hull; it does not dent.
- In `edit_fast_car_midflight` the toppled bottle is partly cut off by the right frame edge from
  frame 22.
- The embedded runtime helpers in the builder and renderer are separate copies of the shared
  `scripts/pcve_scene_runtime.py` and differ from it (Blender lookup, hash scope).
