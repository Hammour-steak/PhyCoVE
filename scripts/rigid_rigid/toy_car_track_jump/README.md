# toy_car_track_jump

A 150 mm red toy car runs along an orange plastic toy track, climbs a straight 38° incline and
leaves an open launch lip front axle first; it flies a parabola, lands near level on the floor with
a slight rebound and rolls on until it stops. Rigid–rigid scene of PhyCoVE. Source video: 4 s,
24 fps, 96 frames, 1280×720.

## Scene

- Track: orange molded plastic toy track, 468 mm level, then a 300 mm horizontal blend into a
  straight 38° incline up to a 270 mm lip, on two molded risers; a stationary launcher at the start.
- Car: 150 mm red toy car with four wheels on two axles; the roof race number is painted out with a
  plain white disc (UV centre (0.752, 0.4365), radius 0.071).
- Room: a daylit, furnished activity room with a pale grey floor, storage shelves with plain
  cloth-bound books, a vase, a jug, a framed photo and a small potted plant, a sofa with woven
  cushions, a side table with a corded lamp, pictures, tied-back curtains and a woven wool rug
  behind the track. Nothing touches the car's path and no furniture stands between camera and car.
  The scene shows no text or numbers.
- Light: daylight through real window openings only (one in shot behind the track, one in the left
  wall, one behind the camera). The sun through the left-wall window is 10 W/m², 0.6° disc, colour
  (1, 0.84, 0.64), 30° elevation; the lit table lamp is 1.8 W with shade emission 0.25; exposure
  0.7 EV; no hidden fill light.
- Materials: semi-gloss molded plastics (roughness track 0.13–0.24, risers 0.15–0.27, launcher and
  button 0.20–0.32), track subsurface 0.12 (radius 3.0/1.0/0.24 mm), rug normal strength 1.4 and
  sheen 0.3.
- Camera: one fixed side camera 0.26 m above the floor, about 1.5 m from the track and 36° off its
  perpendicular toward its start, 25.2 mm lens, f/8.
- Render: Cycles, 128 samples, denoising, rendered at 1920×1080 (150 %) and downscaled when
  encoding, AgX High Contrast, 0.15-frame shutter, persistent data off. A compositor pass adds faint
  lens glow and colour fringing; the encoder adds a slight vignette and fine temporal sensor noise
  (not in the saved frames). All cases share appearance, camera, sampling, motion blur and encoding
  filter.

## Physics

- Solver: MuJoCo 3.17.0, timestep 1/4800 s; poses, wheel spins and contacts are sampled at 240 Hz
  and Blender replays them with quaternion-sign continuity only. Frame n is at t = (n−1)/24.
- Bodies: a free six-degree-of-freedom rigid chassis (90 g) with its centre of mass 30 mm behind
  the body centre, and two unpowered hinge axles, each carrying two rigid 4 g wheels. No motors,
  steering, planar locks, centering forces, velocity resets or authored poses.
- Start: an initial 2.76 m/s velocity with matching wheel spin stands for the launcher push, which
  ends before frame 1; a 6 mm/s sideways component, a small yaw rate and a 0.3 mm lateral
  centre-of-mass offset make the launch slightly imperfect.
- Contacts: tyres collide as capsules of the tyre radius along each axle stub; deck and rails are
  240 box segments following the track profile. The floor uses a damped-spring contact (stiffness
  1e6 s⁻², damping ratio 0.95) that stands in for tyre compliance. The launcher base, housing,
  button and entry throat have collision proxies.
- Track friction: sliding 0.65, torsional 0.00001 m, rolling 0.00002 m. MuJoCo's torsional and
  rolling coefficients are lengths; the DSL names the dimensionless sliding coefficient. Both
  friction edits raise sliding friction and rolling resistance; torsional friction is unchanged.
- The timed edit changes the track and rail `geom_friction` arrays at t = 7/24 s (frame 8); the
  next integration step uses the new coefficients and no position or velocity is reset.
- All inputs are in `scene_config.py`; `counterfactual_cases.py` holds the overrides of the edits.
  Repeating the solve in the same environment gives identical states.

## Measured motion

| Quantity | Value |
| --- | --- |
| Exit speed (last rear-wheel contact) | 1.49 m/s |
| Free flight | 0.34 s, chassis origin peaks at 350 mm |
| First floor contact | 0.73 s, near level |
| Rebound | 6.8 mm chassis rise |
| Rollout | stops at about 1.93 s, 1.65 m along +X, heading within 1.1° |

| Case | Outcome |
| --- | --- |
| `edit_initial_speed_half` | Climbs partway, reverses and stops against the launcher |
| `edit_initial_speed_double` | Flies higher and farther, pitches in flight and leaves the right of the frame at frame 18 |
| `edit_high_friction_uphill` | Stops partway up the ramp |
| `edit_remove_car` | Static empty track |
| `edit_high_friction_near_lip` | Stops near the lip, supported by all four wheels |

## Validation

- `physics/validate_toy_car_track_jump.py` checks frame count, gravity, axle order at the lip,
  parabolic flight, wheel-first landing, no chassis contact with the floor, axle attachment, zero
  motor torque, penetration, heading, lateral drift, rebound and rollout.
- `physics/validate_counterfactuals.py` checks rigidity, gravity, attachment, penetration and zero
  motor torque, then each case's intended outcome; for the timed edit the states before frame 8
  must match the source.
- The renderer refuses a camera that does not keep the whole track, all risers and every car pose
  of the source in frame (the launcher body may run off the left edge). `camera_validation.json`
  records the first frame in which a car fully leaves the frame.
- The verify stage checks resolution, frame rate, frame count, duration and full decode of every
  video.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Initial speed 2.76 m/s |
| `edit_initial_speed_half` | `SET car.initial_speed TIMES 0.5` | Initial speed 2.76 → 1.38 m/s, wheel spin matched |
| `edit_initial_speed_double` | `SET car.initial_speed TIMES 2` | Initial speed 2.76 → 5.52 m/s, wheel spin matched |
| `edit_high_friction_uphill` | `SET track.friction TO 2` | Track sliding friction 0.65 → 2.0, rolling 0.00002 → 0.006 m, from frame 1 |
| `edit_remove_car` | `DELETE car` | Chassis, axles and wheels absent from frame 1 |
| `edit_high_friction_near_lip` | `SET track.friction TO 3 AT FRAME 8` | Track sliding friction 0.65 → 3.0, rolling 0.00002 → 0.04 m, from frame 8 |

## Assets

- `scenes/toy_car_track_jump/room` (url): Poly Haven furniture, props and surface scans of the room.
- `scenes/toy_car_track_jump/room_dressing` (url, with derived files): source mesh of the toy car and
  further room props.
- `scenes/toy_car_track_jump/car_150mm` (derived): the 150 mm car library made by
  `tools/prepare_real_car.py`, and its dimensions.
- `polyhaven/wood_floor` (url): floor.
- `polyhaven/rough_linen` (url): curtains, ties, cushions and lamp shade.
- `polyhaven/book_encyclopedia_set_01` (url): shelf books.
- `polyhaven/hanging_picture_frame_02` (url): wall picture.
- `polyhaven/potted_plant_04` (url): shelf plant.
- `polyhaven/sunny_rose_garden` (url): sky seen through the windows.
- `pcve/domino_chain_curtain_drape` (derived): settled curtain cloth shape.

Download and check them with `python3 scripts/download_assets.py --scene toy_car_track_jump`
(add `--check` to only report).

## Requirements

- Simulation: `.venv-toy-car-bridge` at the repository root with `requirements.txt`
  (`mujoco==3.17.0`, `numpy==2.2.6`). CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`), found from `--blender`, `$BLENDER`,
  `blender` on `PATH`, then `~/.local/opt/blender-*`. Cycles on an NVIDIA GPU with about 5 GB of
  free memory; with `--device auto` Cycles uses every visible GPU, so limit it with
  `CUDA_VISIBLE_DEVICES`.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
# Download and check the registered assets
python3 scripts/download_assets.py --scene toy_car_track_jump --check

# Rebuild the 150 mm car library from the source mesh into renders/toy_car_track_jump/prepared/car_150mm.
# --replace-registered-asset overwrites assets/scenes/toy_car_track_jump/car_150mm instead; the rebuilt
# red_toy_car_library.blend does not match its registered sha256, so keep the registered copy.
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/toy_car_track_jump/tools/prepare_real_car.py -- --help
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
    --python scripts/rigid_rigid/toy_car_track_jump/tools/prepare_real_car.py

# List the cases
python3 scripts/rigid_rigid/toy_car_track_jump/build_pcve_toy_car_track_jump.py --list-cases

# Simulate and validate all six cases on the CPU
.venv-toy-car-bridge/bin/python scripts/rigid_rigid/toy_car_track_jump/build_pcve_toy_car_track_jump.py \
    --out-root renders/toy_car_track_jump/suite_build --stage simulate

# Prepare the scenes, render and encode the videos, then verify them
.venv-toy-car-bridge/bin/python scripts/rigid_rigid/toy_car_track_jump/build_pcve_toy_car_track_jump.py \
    --out-root renders/toy_car_track_jump/suite_build --stage prepare \
    --blender tools/blender-4.3.2-linux-x64/blender --device cpu
.venv-toy-car-bridge/bin/python scripts/rigid_rigid/toy_car_track_jump/build_pcve_toy_car_track_jump.py \
    --out-root renders/toy_car_track_jump/suite_build --stage render \
    --blender tools/blender-4.3.2-linux-x64/blender --device auto --render-workers 3
.venv-toy-car-bridge/bin/python scripts/rigid_rigid/toy_car_track_jump/build_pcve_toy_car_track_jump.py \
    --out-root renders/toy_car_track_jump/suite_build --stage verify
```

- `--stage all` runs simulate, prepare, render and verify in one go; `graybox` is an alias of
  simulate. `--cases` selects cases (the source is always included).
- `--keyframes 8 13 24 48` renders review frames only. `--skip-existing` resumes when the solver
  implementation and configuration hashes match; a changed configuration needs a fresh output root.
- `--source-scene PATH` copies a packed `source_template.blend` into the suite and prepares every
  case from it instead of building the scene from code.
- Rendered frames are reused only between exposures whose float32 root matrices at shutter start,
  centre and end are identical (moving exposures also need the same frame index); the encoder noise
  is drawn independently for every output frame.

## Outputs

`--out-root` is required; the commands above write to `renders/toy_car_track_jump/suite_build/`.
Each case writes to `<out-root>/cases/<case>/`: `video.mp4`, `toy_car_track_jump.blend` (images
packed), `physics_transforms.json`, `ground_truth_transforms.json`, `trajectory.csv`,
`contacts.json`, `prompts.json`, `settings.json`, `parameter_diff.json`, `physics_validation.json`,
`camera_validation.json` and `video_validation.json`. The suite root holds `suite_manifest.json`,
`frame_reuse.json`, `implementation_manifest.json` and a copy of `asset_manifest.json`. The
published suite is `renders/pcve_suites/pcve_toy_car_track_jump_suite/`; do not pass it as
`--out-root`.

## Code layout

- `build_pcve_toy_car_track_jump.py`: builder entry point; runs `counterfactual_suite.py`.
- `counterfactual_suite.py`: simulate, prepare, render, encode and verify the suite.
- `counterfactual_cases.py`: case IDs, parameter overrides and per-case prompt records.
- `edit_vocab.py`: edit vocabulary, DSL statements and source prompts; `counterfactual_cases.prompts`
  turns each statement into the published prompts with `pcve_edit_dsl.make_prompts`.
- `scene_config.py`: all SI inputs, the track profile, appearance and render settings; the
  appearance block names in it are configuration keys recorded in the published data.
- `simulate_toy_car_track_jump.py`: MuJoCo solve.
- `render_toy_car_track_jump.py`: Cycles replay of the solved poses; applies the three appearance
  modules below in the order listed.
- `appearance/look_toy_car_track_jump.py`: room, track, risers, car and lighting.
- `appearance/refine_toy_car_track_jump.py`: window opening, metric UVs for normal maps, glass
  panes, plastic wear and bevels.
- `appearance/finish_toy_car_track_jump.py`: daylight, molded-plastic finish, rug pile and removal of
  printed text.
- `physics/validate_toy_car_track_jump.py`: source physics checks.
- `physics/validate_counterfactuals.py`: per-case physics checks.
- `tools/prepare_real_car.py`: builds the 150 mm car library from the source mesh (Blender).
- `asset_manifest.json`, `ASSET_CREDITS.md`: asset sources, licenses, hashes and modifications.

## Limitations

- Friction, rolling resistance, mass distribution and contact parameters are generic values; they
  are not measured on a particular toy or floor.
- Wheels and body are rigid; tyre compliance exists only in the floor contact and the car has no
  suspension. The track is a rigid sampled mesh that does not flex on its risers; module joints are
  cosmetic.
- Rolling resistance is constant, so deceleration is close to linear; the car stands still for the
  last 2.1 s of the source.
- The landing is sensitive to launch speed, ramp shape, centre of mass and start position; other
  MuJoCo versions or platforms may land differently.
- In `edit_high_friction_uphill` the parked car rests mainly on three wheels: at frame 96 the
  far-side front wheel sits 0.23 mm above the deck (below one pixel, hidden by the body), and a
  native creep of 1.6e-5 m/s remains.
- In `edit_initial_speed_double` the car lands off screen with chassis–floor contact (up to 1.0 mm
  penetration); the full trajectory stays in the ground truth.
