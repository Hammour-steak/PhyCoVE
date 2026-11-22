# thomas_dual_spring_train

An unpowered blue toy train on a straight wooden track is released from a preloaded steel compression spring at
the left end, runs to a second spring at the right end and shuttles back and forth between the two springs while
rolling resistance slowly takes its energy. The scene is a rigid–elastic interaction (rigid train, elastic
springs). Each source video is 4 s at 24 fps (96 frames, 1280×720), played at normal speed: frame k shows the
solver state at t = (k-1)/24 s.

## Scene

- Train: unpowered blue wooden toy train, 150 g, body box 0.130 × 0.046 × 0.066 m, six wheels; centre starts at
  x = -0.300 m.
- Springs: two guided steel compression springs, E = 200 GPa, wire 1.1 mm, mean coil 24 mm, 12 active turns, rest
  length 120 mm, fixed ends at x = -0.44 m and +0.44 m, each with a finite-mass pusher plate; the left spring is
  preloaded by 45 mm.
- Track and hardware: fine-sanded maple veneer (`white_maple_veneer`, 1 m repeat) with a subtle amber clear finish
  and separate cut end grain; milled rail cross-section with spare grooves and interlocking circular sockets
  (running beds and gauge as in the solver); countersunk screws and bored guide sleeves on the fixed mounting
  hardware; brushed aluminium. The render lifts the solver frame by 0.569 m so the track sits on the table (table
  top 0.560 m).
- Table: a wooden table model that keeps its wood and plywood with a spatially varying satin finish. The train
  keeps its model geometry and paint, with a 0.1 mm shader edge radius and a non-uniform clear coat; the added
  block is worn painted wood with edge wear.
- Room: back wall in scanned painted plaster (`beige_wall_001`, 3 m repeat) with profiled skirting and a chair
  rail; a window opening in the left wall with jambs, transom and sill and an unbleached linen curtain with folds;
  a scanned oak floor (`wood_floor`, 1.7 m repeat) and a matte ceiling for room bounce.
- Published look (`appearance/realism.py`, run by the render entry through `tools/worker.py`): runs
  `appearance/render.py` with its `overlay` hook (`render.OVERLAY`) applied after the scene setup. The table is
  dressed with railway accessories in rough sawn timber (a tunnel, three trees, a signal), a carved wooden elephant
  and a wicker basket (`assets/scenes/thomas_dual_spring_train/realism/`), handling wear and dust on the table and
  a lens finish.
- Light: a sun (strength 15, 0.03 rad) turned to enter the window aperture, curtains casting no shadow, world
  strength 1.5, a window area light of 28 W; AgX Medium High Contrast, exposure +0.55, indirect clamp 8.
- Camera: at (0.78, -1.74, 0.92) m aimed at (0, 0.015, 0.595) m, 58 mm lens on a 36 mm sensor, f/5.6, focused on
  the track. The published videos use this camera; the published ground truth records the base-scene camera
  (see Limitations).
- Rendering (`appearance/render.py`): Blender 5.1 Cycles with OptiX, 192 samples (`--samples`), adaptive threshold
  0.008, denoising, bounces 10 (diffuse 5, glossy 5, transmission 5), fixed seed, no motion blur, AgX view
  transform. The appearance code changes no physical model, initial condition or pose; every static object is
  recorded in the render metadata with its transform and materials.

## Physics

- Solver: MuJoCo 3.3.7 on the CPU (`physics/native.py`), dt = 1/38400 s, 4 s.
- The track grooves reduce the chassis to longitudinal translation. Six revolute wheels exchange bounded
  maximum-dissipation Coulomb traction impulses with the running surface (slip allowed); dry bearing and rolling
  torque act at the hinges (rolling resistance coefficient 0.012).
- The two guided springs with finite-mass pusher plates touch the train only unilaterally. No actuator,
  prescribed trajectory or retiming.
- Wheel geometry is read from `assets/scenes/thomas_dual_spring_train/canonical/geometry.json`.
- Each solve writes states.npz (96 frame states plus the 4 s endpoint, 1200 Hz dense states, contact forces),
  config.json, physics_report.json and the MuJoCo model.xml.
- The catalog ADD uses the display-only point `right_track_reference` (the track top under the right spring,
  `edit_vocab.py`); the solver places the block with `native_edit_dsl = ADD wood_block AT PRESET
  track_interceptor`, and the midpoint of the DSL line is 0.35 cm from the block centre.

## Measured motion

From the published ground truth (render coordinates, video frames). The train centre starts at x = -0.300 m and
starts to move at frame 2.

| Case | Train reaches the right spring (frame) | Train at frame 96 |
|---|---|---|
| `source` | 16 | x = -0.113 m, still shuttling |
| `edit_mass_x3` | 27 | x = -0.036 m, still moving |
| `edit_rolling_x4` | 18 | at rest at x = -0.182 m from about frame 74 |
| `edit_right_young_x025` | 16 | x = -0.265 m, still moving |
| `edit_delete_right_spring` | - | rolls on to x = 0.359 m, at rest from about frame 41 |
| `edit_add_wood_block` | - (hits the block at frame 8) | block slides to x = 0.196 m; train and block at rest from about frame 20, train at x = 0.108 m |

## Validation

`--stage verify` checks each published video and native state against the hashes in its `render_provenance.json`
and the 96 solver time points of the stored states.

## Cases

Builder case ids drop the `edit_` prefix of the published case directories (`edit_mass_x3` is `mass_x3`). Camera,
lights, table and every other initial pose are shared; an edit changes only its own field.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | train 150 g, rolling resistance coefficient 0.012; springs E = 200 GPa; left spring preloaded by 45 mm |
| `edit_mass_x3` | `SET train.mass TIMES 3` | train 450 g |
| `edit_rolling_x4` | `SET train.rolling_resistance TIMES 4` | rolling resistance coefficient 0.048 |
| `edit_right_young_x025` | `SET right_spring.young_modulus TIMES 0.25` | right spring E = 50 GPa |
| `edit_delete_right_spring` | `DELETE right_spring` | right spring and its pusher plate absent |
| `edit_add_wood_block` | `ADD wood_block BETWEEN train AND right_track_reference AT MIDPOINT` | 85 g wooden block, friction 0.32, on the track at x = 0.025 m |

## Assets

- `scenes/thomas_dual_spring_train` (8 derived, 20 manual, 3 url): train and table models, wall, floor and track
  textures, wheel geometry (`assets/scenes/thomas_dual_spring_train/canonical/geometry.json`) and the props of the published look (`realism/`).
  Licences are recorded per file in `assets.json`: the train model is CC BY 4.0 and needs attribution, the table
  model is royalty-free, the scanned textures are CC0.

```bash
python3 scripts/download_assets.py --scene thomas_dual_spring_train
python3 scripts/download_assets.py --scene thomas_dual_spring_train --check
```

`PCVE_ASSETS_DIR` moves the asset root.

## Requirements

- Solve: a CPython 3.10 with NumPy and SciPy and MuJoCo 3.3.7 exactly (`physics/native.py` refuses any other
  version); use `PYTHONPATH=.runtime/spring_car_collision/deps`, the MuJoCo 3.3.7 cp310 build kept with
  spring_car_collision. `.venv-genesis-mpm-sph` has another MuJoCo version.
- Render: Linux, Blender 5.1 (`tools/blender-5.1.0-linux-x64`, or `--blender-bin`), an idle NVIDIA GPU with OptiX
  (`tools/worker.py` leases it), ffmpeg.

## Commands

Run from the repository root.

```bash
S=scripts/rigid_elastic/thomas_dual_spring_train

# Verify the published videos and solver states
python3 $S/build_pcve_thomas_dual_spring_train.py --stage verify
python3 $S/build_pcve_thomas_dual_spring_train.py --list-cases
python3 $S/build_pcve_thomas_dual_spring_train.py --list-edits
python3 $S/build_pcve_thomas_dual_spring_train.py --show-prompts add_wood_block

# Solve one case, or the selected cases into <out>/simulation/<case>/
PYTHONPATH=.runtime/spring_car_collision/deps python3 $S/simulate_thomas_dual_spring_train.py --case mass_x3 \
    --out renders/thomas_dual_spring_train/<run>/simulation
PYTHONPATH=.runtime/spring_car_collision/deps python3 $S/build_pcve_thomas_dual_spring_train.py --stage simulate \
    --cases mass_x3 --out renders/thomas_dual_spring_train/<run>

# Render one case in the published look (192 samples) from a folder holding <case>/states.npz
python3 $S/render_thomas_dual_spring_train.py --case <case> \
    --state-root renders/thomas_dual_spring_train/<run>/simulation \
    --out renders/thomas_dual_spring_train/<run>/renders --blender-bin <blender 5.1> --gpu <GPU UUID>

# A single still instead of the 96-frame video
python3 $S/render_thomas_dual_spring_train.py --case <case> --mode preview --frame <N> \
    --out renders/thomas_dual_spring_train/<run>/preview
```

Without `--state-root` the render reads the published solver states; without `--out` it writes to
`renders/thomas_dual_spring_train/renders`.

## Outputs

- New solves, renders, GPU leases and Blender caches go to `renders/thomas_dual_spring_train/`;
  `--stage simulate` writes `<out>/simulation/<case>/`, a render writes frames, `video.mp4` and render metadata to
  `<out>/<case>/`.
- The published solver states are in `renders/thomas_dual_spring_train/simulation/accepted/<case>/` and the
  published videos in `renders/thomas_dual_spring_train/delivery/accepted/<case>/`; `--stage verify` and the
  default render input read them (or `--accepted-root DIR` / `--state-root DIR`).
- The published suite is `renders/pcve_suites/pcve_thomas_dual_spring_train_suite/` (pointer in
  `scene_manifest.json`). Only `--export-prompts` with this path as `--out-root` writes into it.
- The published ground truth (`pcve_ground_truth/1`) was generated from the published `states.npz` in render
  coordinates (solver z + 0.569 m): the train body box and the added block as rigid bodies, the springs as
  deformable bodies given by their coil centres, and the base-scene camera at (0.78, -1.72, 1.12) m. The scene has no
  ground-truth exporter of its own.

## Code layout

- `build_pcve_thomas_dual_spring_train.py`: edit catalog (`PCVE_SOURCE` / `PCVE_EDITS`, equal to the published
  prompts.json; edit prompts are `pcve_edit_dsl.make_prompts` output for `edit_vocab.py`); stages verify and
  simulate.
- `simulate_thomas_dual_spring_train.py`: CPU solve of one case or all cases.
- `render_thomas_dual_spring_train.py`: renders one case from its solver states through `tools/worker.py`.
- `edit_vocab.py`: DSL vocabulary and the display-only ADD anchors.
- `scene_manifest.json`: published suite pointer; keeps the case number 23 (`case_number`).
- `physics/native.py`: MuJoCo model, solver and baseline.
- `appearance/render.py`: solver-state replay and base look (Blender 5.1, Cycles OptiX).
- `appearance/base_scene.py`, `appearance/details.py`: scene construction used by `appearance/render.py`.
- `appearance/realism.py`: overlay of the published look on `appearance/render.py` (window sun, camera, dressed table).
- `appearance/toy_railway_props.py`: railway props of the published look.
- `tools/worker.py`: leases an idle GPU, then runs Blender and ffmpeg.
- `tools/retained_delivery.py`: checks behind `--stage verify`.

## Limitations

- Contact, bearing and material parameters are plausible values, not calibrated on the toy.
- The published ground truth and the render metadata (`camera_matrix`) record the base-scene camera at
  (0.78, -1.72, 1.12) m, taken before the overlay moves the camera to (0.78, -1.74, 0.92) m. Ground-truth positions
  projected with this camera are offset from the objects in the video by up to about 22 px.
- The published results were computed on another Linux GPU machine; bitwise reproduction elsewhere is not
  verified.
