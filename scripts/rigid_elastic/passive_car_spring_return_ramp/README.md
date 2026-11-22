# passive_car_spring_return_ramp

An unpowered toy SUV rolls from rest down a wooden ramp on a children's-room floor, along a short flat
track and into a guided bumper plate backed by a metal coil spring; the spring compresses and pushes the
car back, the car separates, rolls backwards up the ramp and keeps moving freely. This is a rigid–elastic
scene: MuJoCo solves the motion and Blender replays the solved poses and rebuilds the coil shape from the
solved compression. The source video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Units and axes: SI, Z up.
- Track: a ramp with a 0.65 m horizontal run and slope 0.22, a 0.16 m radius arc into the flat section
  (top at 0.020 m). All track parts are fixed.
- Car: 0.143 m long, wheelbase 0.092 m, wheel radius 0.020 m; 0.18 kg in total (body 0.14 kg, four wheels
  0.01 kg each). The rear axle starts at x = −0.54 m with all wheels on the ramp and all velocities zero.
- Bumper plate: 0.012 kg on two fixed guide rods, travel 0 to 0.270 m; the coil behind it has 14 active
  and 2 end coils, mean diameter 28 mm, wire 0.78 mm, spaced from the solved compression (its own mass is
  ignored and its shape drives nothing).
- Room (`appearance/scene_geometry.py`, finished by `appearance/look_passive_car_spring_return_ramp.py`,
  the `look_module` of `appearance/appearance_overlay.json`): no text in frame (no print on the ramp cheek,
  door roundels or blocks, no face-out picture book); seven scanned shelf books keep their meshes, page
  blocks and wear with plain cloth and board covers (`book_assets.json` is the shelf recipe).
- Wall: scanned painted-plaster relief and roughness (`beige_wall_001`, 3 m × 3 m tile) under a sage paint
  colour.
- Props: a scanned potted succulent (`potted_plant_04`, true size 0.18 × 0.18 × 0.27 m) on the cabinet top
  and a plain double socket outlet above the skirting, both far from the car and plate corridor.
- Metal: the coil is bright zinc-plated spring steel so its 0.78 mm wire reads as a continuous helix in
  every frame; guide rods are plain bright steel.
- Light: window, sky HDRI (`residential_garden`) and sun only; no hidden fill lights.
- Camera: fixed at (0.58, −1.82, 0.505) m looking at (0.025, 0.055, 0.125) m, 46 mm lens, focus 1.95 m at
  f/11.
- Render: Cycles 384 samples, adaptive threshold 0.005 (minimum 64), OpenImageDenoise with albedo and
  normal passes, fixed seed, AgX. Motion blur with a 0.25-frame shutter centred on the frame: car, wheels
  and plate get linear keys on every solved frame and the coil gets keys on its solved length, so frame
  `f` still shows solver row `f − 1` exactly. Persistent data is off (with motion blur on, Blender 4.3 drops
  objects that have come to rest).

## Physics

- Solver: MuJoCo 3.17.0 on the CPU, `implicitfast` integrator, Newton solver, elliptic friction cones,
  dt = 1/12000 s; history saved at 1200 Hz.
- Car: a free six-degree-of-freedom body; each wheel turns freely on its own hinge with cylinder
  collision. No actuators, mocap, force callbacks, position or velocity overrides, and no constraint
  between car and plate.
- Rolling resistance (source): rolling friction length ρ = 1e-5 m (MuJoCo's minimum), axle dry friction
  2e-5 N·m and viscous friction 3e-7 N·m·s per axle; sliding friction 0.65, torsional friction length
  0.001 m.
- Plate and spring: the plate is on a horizontal slide joint standing in for the two guide rods (dry
  friction 0.004 N, viscous damping 0.002 N·s/m) with travel limits q ∈ [0, 0.270] m. A lumped spring
  k = 12 N/m with damping c = 0.12 N·s/m acts on the plate (natural length 0.32 m, no preload,
  F = −kq − c q̇). Car and plate touch only through one-sided contact.

## Measured motion

Climb is the rear axle's first rise up the ramp after the rebound.

| Case | Max compression | Climb | Outcome |
|---|---|---|---|
| `source` | 164 mm | 73.5 mm | hits the plate at 0.943 s and 1.40 m/s; back on the ramp at 1.15 m/s |
| `edit_soft_spring` | 270 mm (travel limit) | 33.1 mm | weaker, later push back |
| `edit_stiff_spring` | 75 mm | 74.8 mm | short, sharp push back |
| `edit_high_friction` | 99 mm | 4.0 mm | arrives later and slower (1.163 s, 0.92 m/s); barely climbs |
| `edit_heavy_car` | 242 mm | 86.1 mm | compresses further and climbs higher |
| `edit_delete_spring` | 270 mm (limit) | — | pushes the plate to its end stop; nothing pushes the car back |

Before reaching the plate, the spring edits move exactly like the source.

## Validation

- Events are detected at every integration step: first contact time and speed, maximum compression and
  stored energy, first reversal, sustained separation (gap above 0.1 mm for at least 5 ms), speed back at
  the ramp foot, first climb height, final state.
- The energy budget tracks gravitational, kinetic and spring energy and integrates the spring, guide and
  axle losses; the remainder is reported as contact, rolling and numerical loss.
- Checks: zero initial velocity, no preload, no actuation, contact penetration below 0.5 mm, travel limits,
  no energy gain, wheels on the track, sideways drift, solver warnings, isolated edit differences and coil
  clearance.
- `physics/verify_suite.py --video` adds the video check: resolution, frame rate, 96 frames, 4 s, full
  decode, every PNG, and that the render changed only the appearance.
- Full renders start only after a keyframe review is recorded in static_acceptance.json, tied to the
  appearance, geometry and texture signatures written by the keyframe render.

## Cases

Native case ids are the published names without the `edit_` prefix (`source`, `soft_spring`,
`stiff_spring`, `high_friction`, `heavy_car`, `delete_spring`). Each case is integrated independently from
the same resting start and changes one declared input.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | k = 12 N/m, c = 0.12 N·s/m, car 0.18 kg |
| `edit_soft_spring` | `SET spring.stiffness TIMES 0.2` | k = 2.4 N/m |
| `edit_stiff_spring` | `SET spring.stiffness TIMES 5` | k = 60 N/m |
| `edit_high_friction` | `SET car.rolling_resistance TIMES 20` | `physics.car.travel_resistance_multiplier = 20`: rolling friction length 1e-5 → 2e-4 m, axle dry friction 2e-5 → 4e-4 N·m, axle viscous friction 3e-7 → 6e-6 N·m·s |
| `edit_heavy_car` | `SET car.mass TIMES 2` | car 0.36 kg (mass split and inertias × 2) |
| `edit_delete_spring` | `DELETE spring` | spring removed (k = 0, c = 0); plate, guides and limits stay |

At rest the axle dry friction is a reaction force up to its limit, so in `edit_high_friction` it is not
itself 20 times larger.

## Assets

| assets.json key | Type | Use |
|---|---|---|
| `scenes/passive_car_spring_return_ramp` | mixed (47 url, 7 derived) | cabinet, books, toys and texture library |
| `scenes/toy_car_silicone_bridge` | mixed (50 url, 34 derived) | shared wood and fabric textures |
| `rigid_fluid/tilted_cup_environment` | mixed (4 url, 7 derived) | shared room textures |
| `polyhaven/beige_wall_001` | url | painted-plaster wall relief and roughness |
| `polyhaven/potted_plant_04` | mixed (8 url, 3 derived) | potted succulent on the cabinet |
| `polyhaven/residential_garden` | url | HDRI outside the window |
| `polyhaven/wood_floor` | mixed (8 url, 1 manual, 2 derived) | floor |

```bash
python3 scripts/download_assets.py --scene passive_car_spring_return_ramp          # download and check sha256
python3 scripts/download_assets.py --scene passive_car_spring_return_ramp --check  # check only
```

Files are stored under `assets/` (`PCVE_ASSETS_DIR` moves the root); scene-only files are in
`assets/scenes/passive_car_spring_return_ramp/`. Derived files have no public download, so `--check`
reports them missing. `tools/prepare_assets.py` (run by `--stage prepare`) downloads the CC0 textures,
HDRI and book meshes, checks the retained book artwork and writes their file-level URLs, licences and
sha256 to assets/realism/manifest.json in the scene's asset folder. The render entry writes a library
`.blend` of the built scene (`gravity_track_<recipe>.blend`) and its provenance next to the scene's assets
the first time a geometry and appearance recipe is rendered.

## Requirements

- Linux; MuJoCo runs on the CPU; an NVIDIA GPU renders (OptiX by default; `--device CUDA` or `--device CPU`
  also work).
- Python environment `.venv-toy-car-bridge/` at the repository root (shared with `toy_car_silicone_bridge`)
  with `requirements.txt` (mujoco 3.17.0, numpy 2.2.6, Pillow 11.3.0).
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then `~/.local/opt/blender-*/blender`;
  `--blender` overrides it.
- `ffmpeg` and `ffprobe`.

## Commands

Run from the repository root.

```bash
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/passive_car_spring_return_ramp/build_pcve_passive_car_spring_return_ramp.py --list-cases
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/passive_car_spring_return_ramp/build_pcve_passive_car_spring_return_ramp.py \
    --out-root renders/passive_car_spring_return_ramp/<new folder> --dry-run

# 1. simulate the source, then the edits, and check them
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/passive_car_spring_return_ramp/build_pcve_passive_car_spring_return_ramp.py \
    --out-root renders/passive_car_spring_return_ramp/<new folder> --stage simulate --cases source
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/passive_car_spring_return_ramp/build_pcve_passive_car_spring_return_ramp.py \
    --out-root renders/passive_car_spring_return_ramp/<new folder> --stage simulate \
    --cases soft_spring stiff_spring high_friction heavy_car delete_spring
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/passive_car_spring_return_ramp/physics/verify_suite.py \
    --root renders/passive_car_spring_return_ramp/<new folder>

# 2. render full-quality keyframes of the source and look at them
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/passive_car_spring_return_ramp/build_pcve_passive_car_spring_return_ramp.py \
    --out-root renders/passive_car_spring_return_ramp/<new folder> --stage keyframes --cases source --gpu <GPU index or UUID>
```

Record the review in static_acceptance.json, then render all cases and verify:

```bash
OUT=renders/passive_car_spring_return_ramp/<new folder> python3 - <<'EOF'
import hashlib, json, os
out = os.environ['OUT']
r = json.load(open(f'{out}/source/render/render_input.json'))
digest = lambda v: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()
json.dump({'status': 'accepted', 'appearance_sha256': digest(r['appearance']),
           'geometry_sha256': r['geometry_sha256'], 'asset_dependency_sha256': r['asset_dependency_sha256']},
          open(f'{out}/static_acceptance.json', 'w'), indent=1)
EOF
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/passive_car_spring_return_ramp/build_pcve_passive_car_spring_return_ramp.py \
    --out-root renders/passive_car_spring_return_ramp/<new folder> --stage render --gpu <GPU index or UUID> --resume
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/passive_car_spring_return_ramp/physics/verify_suite.py \
    --root renders/passive_car_spring_return_ramp/<new folder> --video
```

- A non-empty simulation cache or an existing video is never overwritten; `--resume` reuses only frames
  and caches with identical inputs.
- `--simulation-root <finished suite> --stage prepare` copies the solved physics of another output root for
  an appearance-only render; `--appearance-config <overlay.json>` renders with another appearance overlay
  (it may change only `appearance`).

## Outputs

New runs write to the chosen output root under `renders/passive_car_spring_return_ramp/`; each case goes
to `<out-root>/<case>/`. The published suite is
`renders/pcve_suites/pcve_passive_car_spring_return_ramp_suite/`; no command writes into it by default.

| Path in a case folder | Content |
|---|---|
| `video.mp4` | rendered video |
| `simulation/simulation.npz` | solved states |
| `simulation/history.csv` | 1200 Hz history: positions, contact, compression, energy terms |
| `simulation/model.xml`, simulation/config.json, simulation/edit_manifest.json | MuJoCo model, exact inputs, and the before and after of the edit (with mass and inertia ledger) |
| simulation/simulation_report.json | events and physics checks |
| `render/` | frames, render inputs, appearance diff, signatures and timing |
| verification.json, `logs/` | per-case physics and video checks; command logs |

The output root also holds pipeline_manifest.json, a snapshot of the scene code (`reproduction/`,
source_file_hashes.json) and, after a full verify, suite_verification.json.

## Code layout

- `simulate_passive_car_spring_return_ramp.py`: MuJoCo simulation entry
- `render_passive_car_spring_return_ramp.py`: Blender rendering entry
- `build_pcve_passive_car_spring_return_ramp.py`: prepare, simulate, keyframes, render, edits and verify stages
- `scene_config.py`: physical and numerical inputs and the edits (`config_for`); its `render.samples` reads 128 because appearance overlays may not change `render`, and the look sets 384, recorded in `appearance.finish.render_quality` and in each case's render progress record
- `edit_vocab.py`: edit DSL vocabulary and prompts
- `appearance_config.py`: applies the appearance overlay and computes the geometry and texture signatures (textures hashed against `assets.json`)
- `appearance/appearance_overlay.json`: the appearance overlay (`appearance_config.CURRENT_OVERLAY`); its `appearance.finish` block holds the inputs of the look module
- `appearance/scene_geometry.py`: room, track, car, guides, coil and camera in metres
- `appearance/look_passive_car_spring_return_ramp.py`: photographic pass
- `book_assets.json`: shelf-book recipe
- `physics/verify_suite.py`: physics, edit and video verification
- `tools/prepare_assets.py`: asset download and checks
- `requirements.txt`: Python packages of `.venv-toy-car-bridge`
- `entrypoints.json`, `scene_manifest.json`: entry-point options, runtimes, cases and the published suite

## Limitations

- The spring is a lumped k and c, not a continuum coil; the coil geometry is rebuilt from the solved
  compression.
- In `edit_soft_spring` and `edit_delete_spring` the plate reaches its 270 mm travel limit, so the return
  is also shaped by the end stop.
- Rolling resistance values are solver parameters, not calibrated against a real toy tyre.
