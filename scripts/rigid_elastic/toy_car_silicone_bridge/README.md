# toy_car_silicone_bridge

A toy car with four separate rigid wheels gets one push on a wooden road on a children's-room floor and
rolls freely across a silicone bridge clamped at both ends; the bridge sags under the car and springs
back. This is a rigid–elastic scene: the bridge's weight and elasticity, the wheel–bridge friction
contact, the car body and the wheel axles are solved together in MuJoCo, and Blender only reads the solved
cache. The source video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Units and axes: SI, Z up, gravity −9.81 m/s².
- Car: 0.110 m long, 0.078 m wide, wheel radius 14 mm and width 9 mm, wheelbase 0.075 m, track 0.068 m;
  0.150 kg in total (body 0.11471 kg, each wheel 0.00882 kg). Collisions use simple boxes and cylinders;
  the detailed car body, wheel arches and windows are visual only.
- Bridge: a silicone strip 0.320 m long (0.280 m free span) × 0.120 m wide × 6 mm thick, flat top at
  0.065 m. The last 2 cm at each end are embedded in the wooden road; the middle and both side edges move
  freely in 3D. No hidden supports.
- Start: the car's rear axle starts at x = −0.290 m. The scene first settles under gravity for 4 s (not
  shown). At video time 0.25 s the car gets one push: body vx = 0.65 m/s and each wheel ω = 0.65 / 0.014
  rad/s. After that nothing drives or overrides the car.
- Silicone look: deep teal pigmented silicone, Principled BSDF (IOR 1.41, roughness 0.20–0.30) mixed with
  a 20 % diffuse translucent lobe, so light passes through the closed 6 mm solid. Pigment variation,
  handling smudges and a 4 mm moulding waviness (20 µm, shading normal only) are on the rest-pose UVs and
  move with the solved shell. The shell is subdivided (render level 2) before the 6 mm solidify. No
  subsurface scattering.
- Clamped ends: each fixed 20 mm end band lies flush in a 6.2 mm deep, 121 mm wide rebate routed into the
  road deck and is held by two brushed aluminium plates (18 × 28 × 2.5 mm) with two pan-head screws each,
  at |y| ≥ 46 mm. In every cached frame of every case the car body stays within |y| ≤ 40.6 mm, so the
  hardware never touches it. `edit_delete_bridge` has solid road ends without rebates or plates, as in its
  physics model.
- Room: a pine cube shelf (its white bins tinted linen grey), a potted plant, a carved wooden elephant and a
  baseball at native scanned size; a wicker basket with a settled linen throw, a cushion, plaster wall,
  skirting and oak floor. All props stand behind the road (y ≥ 0.45 m) and do not overlap the car at its
  final positions. No readable text in frame.
- Light: daylight through a 1.8 × 1.4 m window opening in the left wall only: a sun lamp (strength 3.5,
  0.53°, 30° elevation, 12° towards the back wall) that lights the whole visible road, the bridge and both
  clamped ends in every frame, and an HDRI sky (strength 1, its own sun clamped at 40) sampled through a
  Cycles portal that emits nothing. No hidden key or fill lights.
- Camera: fixed at (0.60, −1.40, 0.42) m looking at (0.30, 0.03, 0.08) m, 40 mm lens, focus 1.55 m at
  f/4.5.
- Render: Cycles 256 samples without adaptive sampling, OpenImageDenoise with albedo and normal passes
  (accurate prefilter), fixed seed, AgX Medium High Contrast, +2.6 EV. Motion blur with a 0.25-frame
  shutter: cached car and wheel poses are linear keyframes (frame f = cache index f − 1); the bridge has
  no deformation blur (under 2 mm per frame). Persistent data is off, as Blender 4.3 needs with motion
  blur.

## Physics

- Solver: MuJoCo 3.17.0 on the CPU, discrete integrator, Newton solver, sparse Jacobian, elliptic friction
  cones, dt = 1/4800 s (200 steps per video frame), up to 600 inner iterations, tolerance 1e-8. No IPC.
- Car: a free six-degree-of-freedom body; each wheel turns on its own axle with 0.00009 N·m Coulomb
  bearing friction and no motor.
- Bridge: a 2D StVK elastic shell whose bending and stretching both follow from E, ν and thickness
  (33 × 13 vertices, 768 triangles, 3 mm collision radius); E = 0.9 MPa, ν = 0.47, 1100 kg/m³ (0.253 kg),
  stiffness-proportional Rayleigh damping 0.020 s. Three vertex columns per end are fixed.
- Contact: sliding friction 0.75, torsional 0.002, rolling 0.00001.
- `physics/bridge_physics.py` holds the physical and numerical inputs, the edits (`config_for`) and the
  MuJoCo model; `appearance/appearance.json` holds the appearance inputs, which are part of every solved
  configuration.

## Measured motion

Sag is the peak bridge deflection from the flat mid-surface; "extra" is the part beyond the bridge's own
gravity sag. Crossing means the last wheel has left the span and is at road height on the right.

| Case | Sag / extra | Top speed | Crosses at | Outcome at 4 s |
|---|---|---|---|---|
| `source` | 26.85 / 7.78 mm | 0.813 m/s | 1.046 s | across |
| `edit_soft_bridge` | 41.11 / 12.95 mm | 0.862 m/s | — | stuck on the bridge |
| `edit_stiff_bridge` | 17.90 / 5.05 mm | 0.745 m/s | 1.033 s | across |
| `edit_heavy_car` | 31.77 / 12.84 mm | 0.836 m/s | 1.079 s | across, still rolling slowly |
| `edit_delete_bridge` | — | 0.808 m/s | — | falls to the floor at 0.546 s and overturns |

## Validation

- Each case must have finite values, no solver warnings, less than 0.1 mm drift over the last half second
  of the settling, fixed ends that do not move, bounded contact penetration (about 0.04 mm for the source;
  the largest negative gap in any case is 0.23 mm and is reported, not clamped) and bounded material strain
  (about 3.1 % peak for the source). The source must cross and the bridge must recover its gravity shape
  after the car leaves.
- The video check covers every PNG, resolution, frame rate, 96 frames, 4 s and full decode.
- Static regions (wall, shelf, plant pot, front floor, block faces) change by at most 0.1 of 255 grey levels
  between consecutive frames at 480×270.
- Convergence of the source:

| Check | Peak sag | Crossing time | vs. source |
|---|---|---|---|
| source | 26.846 mm | 1.04583 s | — |
| half timestep | 26.839 mm | 1.05000 s | sag −0.026 %, crossing 4.2 ms later |
| 49 × 19 mesh | 26.908 mm | 1.07500 s | sag +0.232 %, crossing 29.2 ms later |

## Cases

Native case ids are the published names without the `edit_` prefix (`source`, `soft_bridge`,
`stiff_bridge`, `heavy_car`, `delete_bridge`). Each edit is built independently, before the gravity
settling, and changes one input (with the values derived from it); camera, materials, lighting, the car's
start and push, contact and solver settings match the source.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | bridge E = 0.9 MPa, car 150 g |
| `edit_soft_bridge` | `SET bridge.young_modulus TO 0.3` | bridge E = 0.3 MPa (÷ 3) |
| `edit_stiff_bridge` | `SET bridge.young_modulus TIMES 3` | bridge E = 2.7 MPa |
| `edit_heavy_car` | `SET car.mass TIMES 2` | car 300 g (masses and inertias scaled); the same initial velocities, so the push carries twice the impulse and kinetic energy |
| `edit_delete_bridge` | `DELETE bridge` | bridge removed |

## Assets

| assets.json key | Type | Use |
|---|---|---|
| `scenes/toy_car_silicone_bridge` | mixed (50 url, 34 derived) | road, furniture, wall and fabric textures, HDRI, basket and books; generated asset libraries and settled linen |
| `polyhaven/wood_floor` | mixed (8 url, 1 manual, 2 derived) | floor |
| `polyhaven/wooden_display_shelves_01` | mixed (5 url, 1 manual) | pine cube shelf |
| `polyhaven/carved_wooden_elephant` | url | wooden elephant on the floor |
| `polyhaven/baseball_01` | url | ball on the floor |
| `polyhaven_models/potted_plant_02` | url | potted plant |

```bash
python3 scripts/download_assets.py --scene toy_car_silicone_bridge          # download and check sha256
python3 scripts/download_assets.py --scene toy_car_silicone_bridge --check  # check only
```

Files are stored under `assets/` (`PCVE_ASSETS_DIR` moves the root); scene-only files are in
`assets/scenes/toy_car_silicone_bridge/`. Derived files have no public download, so `--check` reports them
missing. `asset_sources.json` pins the download URLs and sha256 of the textures and models;
`tools/fetch_assets.py` downloads and checks them. The renderer reads the settled basket cloth in every
frame from `assets/scenes/toy_car_silicone_bridge/generated/` (settled_linen_envelope.npz and
linen_settlement_envelope.json).

## Requirements

- Linux; MuJoCo runs on the CPU; an NVIDIA GPU renders (OptiX by default; `--device CUDA` or `--device CPU`
  also work).
- Python environment `.venv-toy-car-bridge/` at the repository root (MuJoCo 3.3.7 and older cannot fix the
  bridge ends as needed):
  ```bash
  python3 -m venv .venv-toy-car-bridge
  .venv-toy-car-bridge/bin/pip install -r scripts/rigid_elastic/toy_car_silicone_bridge/requirements.txt
  ```
  (mujoco 3.17.0, numpy 2.2.6, Pillow 11.3.0)
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then `~/.local/opt/blender-*/blender`;
  `--blender` overrides it.
- `ffmpeg` and `ffprobe`.

## Commands

Run from the repository root.

```bash
python3 scripts/rigid_elastic/toy_car_silicone_bridge/build_pcve_toy_car_silicone_bridge.py --list-cases
python3 scripts/rigid_elastic/toy_car_silicone_bridge/build_pcve_toy_car_silicone_bridge.py \
    --out-root renders/toy_car_silicone_bridge/<new folder> --stage simulate --cases source --dry-run

# 1. simulate the source (no rendering); it must pass its physics checks
python3 scripts/rigid_elastic/toy_car_silicone_bridge/build_pcve_toy_car_silicone_bridge.py \
    --out-root renders/toy_car_silicone_bridge/<new folder> --stage simulate --cases source
# 2. render frames 1, 18, 24 and 96 at full quality and look at them
python3 scripts/rigid_elastic/toy_car_silicone_bridge/build_pcve_toy_car_silicone_bridge.py \
    --out-root renders/toy_car_silicone_bridge/<new folder> --stage keyframes --cases source --gpu <GPU index or UUID>
```

Full renders start only after the keyframe review is recorded: write static_acceptance.json with
`{"status": "accepted"}` (and notes) in the output root. Then:

```bash
# 3. the full source video, reusing the keyframes
python3 scripts/rigid_elastic/toy_car_silicone_bridge/build_pcve_toy_car_silicone_bridge.py \
    --out-root renders/toy_car_silicone_bridge/<new folder> --stage render --cases source --gpu <GPU index or UUID> --resume
# 4. the four edits (simulate and render each)
python3 scripts/rigid_elastic/toy_car_silicone_bridge/build_pcve_toy_car_silicone_bridge.py \
    --out-root renders/toy_car_silicone_bridge/<new folder> --stage edits \
    --cases soft_bridge stiff_bridge heavy_car delete_bridge --gpu <GPU index or UUID>
# 5. check physics differences, quality and full decode; write the summary table
python3 scripts/rigid_elastic/toy_car_silicone_bridge/build_pcve_toy_car_silicone_bridge.py \
    --out-root renders/toy_car_silicone_bridge/<new folder> --stage verify

# convergence checks, each in its own folder
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/toy_car_silicone_bridge/simulate_toy_car_silicone_bridge.py \
    --output-dir renders/toy_car_silicone_bridge/<new folder>/half_dt --timestep 0.00010416666666666667
.venv-toy-car-bridge/bin/python scripts/rigid_elastic/toy_car_silicone_bridge/simulate_toy_car_silicone_bridge.py \
    --output-dir renders/toy_car_silicone_bridge/<new folder>/grid_49x19 --grid 49 19

# basket cloth solve (inside Blender 4.3.2)
blender -b --python-exit-code 1 --python scripts/rigid_elastic/toy_car_silicone_bridge/tools/generate_basket_linen.py -- [--out <dir>] [--force]
```

- An existing output is never overwritten; `--resume` reuses it only when the configuration is identical.
- `--stage prepare --reuse-physics-from <finished output root>` copies the solved physics of another output
  root for an appearance-only render (`physics/reuse_cached_physics.py`); it refuses if any physics or solver
  setting or the render timing (size, frame rate, frame count, duration) differs. Samples and motion blur may
  change.
- `tools/generate_basket_linen.py` writes both cloth files to `renders/toy_car_silicone_bridge/rebuild/<UTC
  time>/` unless `--out` is given. With `--out` set to the registered folder it refuses to replace a file
  whose new sha256 differs from `assets.json` unless `--force` is added. The cloth solve repeats bit for bit
  (Blender 4.3.2, CPU), but its report records the run time, so its sha256 always differs.

## Outputs

New runs write to the chosen output root under `renders/toy_car_silicone_bridge/`; each case goes to
`<out-root>/<case>/`. The published suite is `renders/pcve_suites/pcve_toy_car_silicone_bridge_suite/`; no
command writes into it by default.

| Path in a case folder | Content |
|---|---|
| video.mp4 | rendered video |
| simulation/simulation.npz | 97 solved states (t = 0 to 4 s; the video uses the first 96) |
| simulation/model.xml, simulation/config.json, simulation/edit_manifest.json | MuJoCo model and exact inputs |
| simulation/preroll_state.npz, simulation/initial_push.json | settled state and the push |
| simulation/simulation_report.json, simulation/metrics_240hz.json, simulation/contact_forces_240hz.json | physics checks, 240 Hz metrics and contact forces |
| render/frames/, render/scene.blend, keyframes/ | frames, a first-frame scene for inspection, keyframes |
| video_verification.json, frame_integrity.json | video and frame checks |
| prompts.json | the case's edit DSL and prompts (from `edit_vocab.py`) with the measured outcome |

The output root also holds metrics.csv (all cases), pipeline_manifest.json, suite_acceptance.json,
camera_envelope.json and validation/.

## Code layout

- `simulate_toy_car_silicone_bridge.py`: MuJoCo simulation entry
- `render_toy_car_silicone_bridge.py`: Blender rendering from the cache; builds the scene with `appearance/scene_geometry.py` and checks the shared models against `assets.json`
- `build_pcve_toy_car_silicone_bridge.py`: prepare, simulate, keyframes, render, edits and verify stages
- `edit_vocab.py`: edit DSL vocabulary and prompts
- `physics/bridge_physics.py`: bridge model, edits and solver inputs
- `physics/reuse_cached_physics.py`: reuse of solved caches for an appearance-only render
- `physics/verify_suite.py`: suite verification
- `appearance/appearance.json`: appearance inputs (camera, optics, materials, room, light), part of every solved configuration
- `appearance/scene_geometry.py`: the scene in metres: silicone, clamped ends, scanned room props, window light, motion-blur keyframes
- `asset_sources.json`: pinned download URLs and checksums of the textures and models
- `tools/fetch_assets.py`: asset download and check
- `tools/generate_basket_linen.py`: basket cloth solve (Blender)
- `requirements.txt`: Python packages of `.venv-toy-car-bridge`
- `entrypoints.json`, `scene_manifest.json`: entry-point options, runtimes, cases and the published suite

## Limitations

- With the finer mesh the car's final stopping point moves about 0.092 m along the road; the crossing
  outcome and peak sag are robust, the stopping point is not a converged prediction.
- The bridge is a constant-thickness shell with small material strain, not a 3D nearly incompressible
  solid, and its damping is not calibrated against real silicone.
- The detailed car body, wheel arches and windows are visual; collisions use simplified shapes.
