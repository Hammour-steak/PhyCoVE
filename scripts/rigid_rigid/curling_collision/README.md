# curling_collision

Three identical granite curling stones stand in a line on indoor ice with red, blue and yellow handles, from left to right. The red stone slides to the right, strikes the blue stone, the blue stone slides across a clear gap and strikes the yellow stone, and every stone then slows under ice friction. All stones keep their orientation and translate only along the world X axis. This is a rigid–rigid scene of PhyCoVE, the benchmark for physical counterfactual video editing (PCVE). The source video is 4 s at 24 fps, 96 frames, 1280×720.

## Scene

- **Units and axes:** SI, Z up, gravity 9.81 m/s². All inputs are in `scene_config.py` (`BASELINE`), split into `physics`, `simulation_quality`, `appearance` and `render`.
- **Stones:** diameter 0.29 m (collision radius 0.145 m), 19.5 kg each. The complete visual stone is 0.184610 m high including the handle. R01, B01 and Y01 start at X = −1.28, −0.30 and +0.84 m on the common track Y = −0.55 m, leaving clear gaps of 0.69 m and 0.85 m. Only R01 moves at the start, at 1.25 m/s; all angular velocities are zero. The configuration also keeps a nominal granite height (0.14 m), centre-of-mass height (0.07 m) and running-band radius (0.065 m); they do not describe the visual mesh and do not affect the X trajectories.
- **Stone appearance:** handle and cap geometry come from the normalized stone asset (`sketchfab/curling_stone_filinmx`, normalized to a 0.29 m horizontal diameter, centred and grounded). `build_stone` in `appearance/look_curling_collision.py` replaces the asset's 24-sided granite body with a 192-segment lathe through the same measured profile; the striking band stays exactly at the 0.145 m collision radius, and cap and handle get two subdivision levels. The printed atlas of the asset is not used. Granite is procedural polished granite in stone-local metres: interlocking dark, matrix and pale mineral cells with an independent pattern per stone, mirror-polished shoulders (roughness 0.16–0.22) with handling scuffs, a ground striking band about 2.5–3.2 cm wide with chips, and running wear on the lower shoulder. Handles are plain moulded polymer (red, blue, yellow; yellow pigment linear (0.90, 0.60, 0.00)); the added stone of the ADD edit has a green handle, linear (0.018, 0.27, 0.05).
- **Ice:** an opaque optical approximation (`ice_material_debris`): a matte frosted base (linear (0.60, 0.64, 0.67)) under a full-strength glossy coat with roughness 0.035–0.09, so reflections follow the Fresnel response at grazing angles. Two droplet sizes form the pebble (5.5 mm spacing, 0.3 mm height, normal strength 0.12); slow undulation, decimetre-scale mottling (±5 %), sparse 1–3 mm broom debris and frost near the far boards (mix 0.40) complete it. A seeded 4096×3072 wear map generated at build time holds curved stone tracks, lane wear and sweep and slider scuffs; tracks also flatten the pebble. The physical support is a flat plane at Z = 0; none of this changes friction or collision geometry.
- **Club room:** a closed two-sheet curling club with 4.75 m sheets, house paint and centre, tee, back and hog lines. Behind the far side line runs a low charcoal foam bumper (152×152 mm section, 2.134 m lengths), then a 2.7 m rubber-matted walkway to the rear wall: painted concrete block with running-bond courses, a darker lower band and rubber skirting. Along the wall stand slatted benches on tube frames, a folded towel, a waste bin and resting brooms; the wall carries galvanized conduit with a switch box, two rows of framed team photographs (every third print monochrome), and a service door with kick plate, push bar, wired vision pane, a plain twin-head emergency light and an unlabelled fire extinguisher. The gallery window is a real opening with a deep reveal, clear glazing and half-lowered blinds; beyond it is a club bar interior clipped at the wall plane with 512 px textures, in which every label, menu board and packaging texture is flattened to its own mean linear colour (`flatten_labels`; the flattened image names are stored on the bar collection) and the till is removed. Nothing in the room carries lettering, logos or brand marks, no object resembles a stone, and no background photograph or projected image plane is used.
- **Lighting:** rows of ceiling battens over the sheets only (62 W each, slight output differences) and unevenly spaced warm walkway downlights that leave scallops on the wall, so the ice is the brightest surface in the shot; warm spill from the gallery.
- **Camera:** fixed, 0.78 m above the ice at (−2.5, −7.2, 0.78) m looking at (0.55, −0.1, 0.42) m, 66 mm lens on a 36 mm sensor, f/3.2 focused at 7.33 m. All stones and their complete travel stay inside the frame. `camera_finish` adds a compositor pass on the rendered image only: lateral colour dispersion 0.003 with zero distortion, bloom above scene-linear 1.2 at mix −0.9, and an 18 % elliptical corner vignette. It changes no geometry, pose or timing; handle centroids move by at most 0.7 px.
- **Rendering:** Blender 4.3.2 Cycles, 128 maximum adaptive samples (threshold 0.01), path bounces total 12 / diffuse 6 / glossy 6 / transmission 8, OIDN denoising, AgX High Contrast, exposure −0.05, a 0.25-frame shutter (1/96 s). Persistent data is off whenever motion blur is on, because Blender 4.3 can drop objects that have come to rest from later frames of the same session. With the fixed seed, static regions are identical from frame to frame. Encoding is H.264 (libx264, CRF 17, yuv420p).

## Physics

- **Solver:** an exact event-driven, orientation-locked rigid-body impulse solver (`SOLVER_VERSION = "pcve-exact-1d-impulse/1.1"` in `simulate_curling_collision.py`), Python standard library only. Collision geometry is the equatorial radius of the identical stones. Contact times are roots of the relative gap equation computed from current positions, speeds and friction; they are not animation inputs.
- **Degrees of freedom:** world X translation only; Y, Z and all rotations are constrained. The model does not predict handle rotation, curl, tipping, running-band anisotropy or deformation.
- **Friction:** constant Coulomb kinetic friction μ = 0.018 with g = 9.81 m/s² gives a deceleration of 0.17658 m/s². Friction opposes the current velocity, so a light striker that rebounds also slows down; at zero speed friction stops acting and a static stone stays exactly at rest. The ice supports gravity and the ideal constraints do no work. There is no speed reset, air damping or animation easing.
- **Contacts:** stone-pair restitution e = 0.82. Each instantaneous contact applies J = (1+e)(v_left − v_right)/(1/m_left + 1/m_right); pair momentum is conserved and contact kinetic energy decreases. Segments between impacts are integrated analytically.
- **Sampling:** poses are stored at 480 Hz, including the exact collision and stop times (event time tolerance 1e-10 s, contact tolerance 1e-9 m, at most 100 events). Video frame f is the state at t = (f−1)/24 s; Blender replays the solved cache with fixed orientations.

## Measured motion

Source, default configuration: contacts at 0.575384 s and 1.453961 s. At the first contact red slows from 1.148399 to 0.103356 m/s and blue starts at 1.045043 m/s. Blue travels 0.85 m, then slows from 0.889904 to 0.080091 m/s; yellow starts at 0.809812 m/s and is at 0.360233 m/s at 4 s. Red and blue coast to rest through friction.

## Validation

- `physics/validate_curling_collision.py` checks one sequential contact per neighbouring pair, initially stationary targets, clear travel of each middle stone, striker speed loss, frictional slowdown of the last stone, momentum, restitution, decreasing energy, no penetration and constant orientation, height and track. The builder refuses a case that fails it.
- The renderer checks that every complete stone and every ground-contact location stays in frame in all 96 frames and records the result in `scenario_metadata.json`.
- `--stage verify` runs `scripts/pcve_verify_video.py` on each case video.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | Red strikes blue, blue strikes yellow |
| `edit_add_green_stone_midpoint` | `ADD green_stone BETWEEN blue_stone AND yellow_stone AT MIDPOINT` | A stationary fourth stone with a green handle, same mass and geometry, at X = +0.27 m (clear gaps of 0.28 m on both sides). Measured contacts at 0.575 s, 0.850 s and 1.168 s; blue stops at X = +0.003 m (source +0.568 m), green at +0.567 m, and yellow is struck 0.286 s sooner but is at +2.324 m at 4 s, within 5 mm of the source |
| `edit_delete_yellow_stone` | `DELETE yellow_stone` | No yellow stone is built; red strikes blue only |
| `edit_delete_blue_stone` | `DELETE blue_stone` | No blue stone; red crosses the larger gap and strikes yellow directly |
| `edit_blue_mass_x3` | `SET blue_stone.mass TIMES 3` | Blue mass 19.5 → 58.5 kg; blue gets too little speed to reach yellow and stops with a clear gap |
| `edit_red_mass_x1p1` | `SET red_stone.mass TIMES 1.1` | Red mass 19.5 → 21.45 kg; more momentum passes through blue and yellow moves visibly farther, still inside the frame |

All edits apply from frame 1. `edit_vocab.py` declares the DSL statements, binds them to the solver arrays (DELETE rebuilds the ordered arrays without the target stone; ADD inserts the green stone into the slot between blue and yellow) and derives the edit prompts with `pcve_edit_dsl.make_prompts`; the source prompts are written in `build_pcve_curling_collision.py`. Each edit's `prompts.json` also carries the solved outcome (`edit_summary`). No collision time or animation curve is authored for any edit.

## Assets

| Key | Type | Use |
|---|---|---|
| `sketchfab/curling_stone_filinmx` | manual + derived | Stone source GLB and the normalized `normalized_stone.blend` the renderer loads |
| `polyhaven/concrete_block_wall` | url | Painted rear and side block wall |
| `polyhaven/plywood` | url + derived | Benches, window sill and photo frames |
| `blenderkit/cafe_interior_loft_bar` | manual + derived | Club bar seen through the gallery window |
| `blenderkit/kitchen_towel` | manual + derived | Towel on a bench |

`asset_manifest.json` records the sources, licences, hashes and modifications. Assets live in `assets/` at the repository root (or `$PCVE_ASSETS_DIR`; the renderer also accepts `--asset-root`). The stone licence is non-commercial (CC BY-NC 4.0) and the manual interior assets are licensed for rendered output only, so saved `.blend` files are not redistributed. Use the registered `normalized_stone.blend` to keep its registered hash; `tools/prepare_sketchfab_asset.py` documents how it is made from the source GLB.

```bash
python3 scripts/download_assets.py --scene curling_collision          # download url files, list manual ones
python3 scripts/download_assets.py --scene curling_collision --check  # check only
```

## Requirements

- Simulation and orchestration: Python 3 standard library only (`python3`).
- Rendering: Blender 4.3.2 with Cycles, found by `pcve_assets.blender` (`$BLENDER`, then `blender` on `PATH`, then the newest `~/.local/opt/blender-*/blender`), or pass `--blender tools/blender-4.3.2-linux-x64/blender`.
- `ffmpeg` and `ffprobe` for encoding and video checks.
- CPU rendering is the default. GPU rendering uses OptiX and needs an explicitly selected idle GPU (`--device gpu` together with `--gpu <index>`).

## Commands

Run from the repository root. The builder renders only `source` unless `--cases` names more cases.

```bash
S=scripts/rigid_rigid/curling_collision
python3 $S/build_pcve_curling_collision.py --list-cases
python3 $S/build_pcve_curling_collision.py --describe
python3 $S/build_pcve_curling_collision.py --out-root renders/curling_collision/new_run --dry-run

# solve and validate physics for all cases
python3 $S/build_pcve_curling_collision.py --out-root renders/curling_collision/new_run --stage simulate \
  --cases source edit_add_green_stone_midpoint edit_delete_yellow_stone edit_delete_blue_stone edit_blue_mass_x3 edit_red_mass_x1p1
# eight preview frames (1 14 15 24 35 36 60 96) at full quality
python3 $S/build_pcve_curling_collision.py --out-root renders/curling_collision/new_run --stage preview \
  --cases source --device cpu --threads 64
# all 96 frames, encode, then check the video (reuses identical preview frames)
python3 $S/build_pcve_curling_collision.py --out-root renders/curling_collision/new_run --stage render \
  --cases source --device cpu --threads 64 --skip-existing
python3 $S/build_pcve_curling_collision.py --out-root renders/curling_collision/new_run --stage verify --cases source

# rebuild the normalized stone from the source GLB
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 --python $S/tools/prepare_sketchfab_asset.py -- \
  --input assets/sketchfab/curling_stone_filinmx/source.glb --out renders/curling_collision/asset_check/normalized_stone.blend
```

`--stage all` solves, renders, encodes and verifies in one run. `--config-json <file>` merges named fields into the four configuration groups; changed inputs require a fresh output root. The standalone entries take `--out <file>` (`simulate_curling_collision.py`) and `--physics-json`, `--out-dir`, `--mode prepare|frames|animation`, `--keyframes`, `--device`, `--threads-native`, `--skip-existing`, `--asset-root` (`render_curling_collision.py`); `--describe` prints the full interface.

## Outputs

A run writes `<out-root>/suite_manifest.json`, `<out-root>/implementation_manifest.json` (effective configuration and solver cache hash) and, per case, `<out-root>/cases/<case>/` with `physics_transforms.json`, `trajectory.csv` (480 Hz), `contacts.json`, `physics_validation.json`, `settings.json`, `prompts.json`, `scenario_metadata.json`, `ground_truth_transforms.json`, `curling_collision.blend`, `frames/frame_0001.png`…, `video.mp4`, `video_validation.json` and timing logs; edits add `scenario_overrides.json`. Use a fresh root under `renders/curling_collision/`. The published suite is `renders/pcve_suites/pcve_curling_collision_suite/`; `scene_manifest.json` pins its video hashes. Do not write new runs into it.

## Code layout

- `build_pcve_curling_collision.py`: suite builder (stages, cases, source prompts, manifests).
- `simulate_curling_collision.py`: event-driven solver, CSV and JSON export.
- `render_curling_collision.py`: Blender scene build, pose replay, frame rendering and encoding.
- `scene_config.py`: all physical, appearance and render inputs and their validation.
- `edit_vocab.py`: edit vocabulary, DSL statements, solver bindings and outcome summaries.
- `physics/validate_curling_collision.py`: trajectory acceptance checks.
- `appearance/look_curling_collision.py`: stones, ice, club room, lighting and camera finish.
- `tools/prepare_sketchfab_asset.py`: normalization of the stone source GLB (Blender).
- `asset_manifest.json`: asset sources, licences, hashes and modifications.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry-point description, scene manifest, dependency note.

## Limitations

- The motion is a constrained one-dimensional model: no handle rotation, curl, tipping or deformation.
- Granite–ice friction and stone restitution are constants, not calibrated against measurements.
- The ice is an opaque optical approximation over a flat collision plane; its pebble, wear and debris are visual only.
