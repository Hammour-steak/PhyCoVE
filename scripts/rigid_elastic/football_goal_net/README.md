# football_goal_net

In a football stadium a ball is struck from 0.6 m in front of the goal line, flies into the goal, hits the back of
the goal net, is thrown back out by the net and bounces and rolls back onto the pitch while the net swings and
settles. The scene is rigid–elastic: a rigid ball against a viscoelastic strand network. The source video is 4 s at
24 fps (96 frames, 1280×720) at normal speed: frame k shows the native state at t = (k-1)/24 s (native 120 Hz
sample 5(k-1)); there is no retiming, interpolation or frozen tail.

## Scene

- Coordinates: metres, x along the goal line (inner posts at x = ±3.66 m), y into the goal (goal line y = 0, rear
  ground rail y = 2.55 m, perimeter boards y = 5.05 m), z up. Camera, scene and every initial pose are shared by all
  cases.
- Ball: 0.43 kg, radius 0.11 m (22 cm), start (0.58, -0.6, 1.14) m, 16 m/s horizontal plus 1 m/s up, spin
  (-8, 0.5, 1.5) rad/s. Clean off-white PU panels with light scuffs and satin black pentagons.
- Goal net: 4 mm hexagonal-mesh strands and 6 mm support cords, fixed at the frame clips and ground rails; drawn from
  the solver's own strand centrelines (one shape key per 120 Hz state, round cords through geometry nodes).
- Goal frame, stanchions, support wires and perimeter boards: a frozen collision world. Behind the goal the perimeter
  surfaces are drawn as switched-off LED boards (black satin modules, joints every 0.96 m, grass-side dust) in front
  of a dark painted concrete wall with a scanned concrete coping.
- Pitch: turf shaders recoloured towards the photographed pitch (hue 0.476, saturation x0.70, value x1.55), with 5.5 m
  mowing bands parallel to the goal line (value x0.86-x1.10), metre-scale drift, decimetre clumping, 3-10 cm
  tussocks, single-blade variation (also as a slight bump), sparse bright blade tips and a worn goalmouth; all
  aperiodic world-space noise, so there is no moire against the tuft lattice. Static grass tiles are placed on the
  turf, which is bound to the solver's compression samples.
- Background: a goal-free stadium photograph re-projected behind the goal (gamma 1.28, contrast +0.13, saturation
  x1.15 before emission).
- Light: a sun lamp with the direction derived from the photograph (hazy bright day, sun high behind the goal and to
  the left), 2 deg disc, energy 10; the panorama lights the scene at strength 1.3.
- Camera (`appearance/camera.py`): one fixed pitchside telephoto view, eye (18, -34, 2.5) m, target (-1, -2, 1) m,
  90 mm lens on a 36 mm sensor, focus on (0.3, 0.8, 1.0) m (39.1 m), aperture f/4 (set by the look); it never moves.
- Render (`appearance/render.py` with the look `appearance/realism.py`): opens the packed stadium/goal scene
  (`prepared_scene.blend`, sha256 pinned) and moves goal rails, stanchions and mounts to the physical anchors. Blender
  4.3.2 Cycles, 1280×720, 256 samples with adaptive threshold 0.012, OpenImageDenoise, seed 260026, 10 bounces
  (8 transparent), motion blur with a 0.5 shutter on the 120 Hz timeline (1/240 s), persistent data off (with motion
  blur on, Blender 4.3 drops objects that come to rest when it is on), AgX Medium High Contrast, exposure +0.35,
  vignette 0.12, lateral colour 0.002, 8-bit PNG frames, H.264 High crf 16 yuv420p at 24 fps.

## Physics

- Solver: a float64 explicit integrator at 192 kHz on one CPU core (numba), output at 120 Hz (481 states, 0-4 s).
- Net: strand axial stiffness k = E pi (2 mm)² / L0 with E = 84.4 MPa, bending from the same E, Kelvin-Voigt axial
  viscosity 4000 Pa s.
- Ball: thin-shell rigid body (I = 2 m R² / 3) with spin.
- Turf: a viscoelastic foundation sampled at 14,458 points.
- Parameters: the baseline and every override are in `physics/strict_edit_plan.json`; `edit_vocab.py` maps the DSL
  onto its fields.
- Whole-clip cases: the five accepted 120 Hz caches are registered assets and are not re-solved.
- Timed edit (`physics/solve_timed.py`, same solver snapshot, inputs and runtime as the source and mass_double jobs,
  whose code, frozen inputs and receipt stay in the accepted physics delivery, located through `tools/retained.py`):
  1. prefix: the source parameters from t = 0 to t = 7/24 s; its samples must reproduce the stored source cache to
     < 1e-8; the stage writes the solver's lossless checkpoint at tick 56000 of 192 kHz (net positions and velocities,
     ball position, velocity, spin and orientation, turf memory, contact ledgers);
  2. edit: the mass_double variant restored from that checkpoint with the solver's own `--resume`; a lineage check
     allows exactly the scheduled `ball_mass_kg` change and nothing else; it solves on to 4 s;
  3. merge: native samples 0-34 are the source samples, samples 35-480 the edit run's; the hand-off error and the
     parameters are recorded in the timed_edit.json receipt.
  The published timed solve took about 2.6 h on one core; its prefix matches the source to 7.5e-15 m (ball position),
  7.6e-13 m/s (ball velocity) and 0 (net nodes), and the hand-off error is below 2e-12.

## Validation

- Every rendered frame re-checks the bindings against the cache: ball position < 2e-5 m, net nodes < 2e-6 m, grass
  height < 2e-7 m. For the timed case `appearance/render.py` binds the merged cache through its receipt and checks that
  every turf control the solver activated lies inside the common soil field. `appearance/render.py --audit-only`
  builds the scene and runs the per-frame binding checks without rendering.
- `--stage verify` checks the accepted media delivery and the published suite (`tools/retained.py`).
- Static regions change by less than 0.03/255 between consecutive frames. In the source video the ball enters, is
  caught by the back net (frames 6-12), drops, bounces and rolls out, with no penetration or floating.

## Cases

The builder's native case ids drop the `edit_` prefix of the published case directories (`edit_young_tenth` is native
case `young_tenth`).

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | ball 0.43 kg, r = 0.11 m, 16 m/s horizontal + 1 m/s up; net strand E = 84.4 MPa |
| `edit_young_tenth` | `SET net.young_modulus TIMES 0.1` | strand E = 8.44 MPa |
| `edit_mass_double` | `SET ball.mass TIMES 2` | ball 0.86 kg |
| `edit_speed_half` | `SET ball.horizontal_velocity TIMES 0.5` | horizontal speed 8 m/s |
| `edit_remove_net` | `DELETE net` | net absent from frame 1 |
| `edit_mass_double_at_frame_8` | `SET ball.mass TIMES 2 AT FRAME 8` | source physics up to t = 7/24 s, ball 0.86 kg from frame 8 on |

## Assets

- `scenes/football_goal_net` (derived, 31 files): packed stadium/goal scene, net model, collision world, grass tiles,
  goal-free stadium panorama and the native 120 Hz caches of the five whole-clip cases (`native/<case>/` with render
  gate, physics report and sampled geometry audit).

```bash
python3 scripts/download_assets.py --scene football_goal_net
python3 scripts/download_assets.py --scene football_goal_net --check
```

## Requirements

- Python 3 for the entries and the verify stage.
- Timed solve: a Python 3.10 environment with numba like the one the solver jobs ran in; it is not part of the
  repository. CPU only.
- Rendering: Blender 4.3.2 (`pcve_assets.blender()` unless `--blender-bin`), OptiX, CUDA or CPU.

## Commands

```bash
# catalog, prompts, verification
python3 scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py --stage verify
python3 scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py --stage prepare
python3 scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py --list-cases
python3 scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py --list-edits
python3 scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py --show-prompts source
python3 scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py --export-prompts \
    --out-root renders/pcve_suites/pcve_football_goal_net_suite --dry-run

# export stored states and the published video
python3 scripts/rigid_elastic/football_goal_net/simulate_football_goal_net.py --case source --mode native \
    --out renders/football_goal_net/<run>/source_native.npz
python3 scripts/rigid_elastic/football_goal_net/simulate_football_goal_net.py --case source --mode canonical \
    --out renders/football_goal_net/<run>/source_24hz.npz
python3 scripts/rigid_elastic/football_goal_net/render_football_goal_net.py --case source \
    --out renders/football_goal_net/<run>/source.mp4

# timed solve (Python 3.10 + numba runtime)
python3 scripts/rigid_elastic/football_goal_net/simulate_football_goal_net.py --case mass_double_at_frame_8 --mode solve \
    --out renders/football_goal_net/<run>/timed
python3 scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py --stage simulate \
    --cases mass_double_at_frame_8 --out renders/football_goal_net/<run>/simulate
python3 scripts/rigid_elastic/football_goal_net/physics/solve_timed.py --case mass_double_at_frame_8 \
    --out renders/football_goal_net/<run>/timed --stage prefix

# render one case with the published look
python3 scripts/rigid_elastic/football_goal_net/render_football_goal_net.py --render --case source \
    --out renders/football_goal_net/<run>/source --device OPTIX --gpu <GPU> --parallel 2 --samples 256 --frames 1-96
python3 scripts/rigid_elastic/football_goal_net/render_football_goal_net.py --render --case mass_double_at_frame_8 \
    --cache-dir renders/pcve_suites/pcve_football_goal_net_suite/inputs/native_timed/mass_double_at_frame_8 \
    --out renders/football_goal_net/<run>/mass_double_at_frame_8
python3 scripts/rigid_elastic/football_goal_net/render_football_goal_net.py --encode-only --case source \
    --out renders/football_goal_net/<run>/source

# new suite and ground truth
python3 scripts/rigid_elastic/football_goal_net/tools/publish_suite.py --renders renders/football_goal_net/<run> \
    --timed-solves renders/football_goal_net/<run>/timed_solves --suite renders/football_goal_net/<run>/suite
<blender> -b --factory-startup --python-exit-code 1 \
    --python scripts/rigid_elastic/football_goal_net/tools/export_ground_truth.py -- \
    --suite renders/football_goal_net/<run>/suite
```

`physics/solve_timed.py --stage` takes prefix, compare, edit, merge or all (default). `--parallel N` renders N frame
ranges at once on the same device with the same settings; with all 96 frames present the render entry encodes
video.mp4 and writes render_setup.json. `tools/publish_suite.py --publish` (instead of `--suite`) builds and checks a
staging folder next to the published suite, then moves the published suite to `renders/pcve_suites_archive/` and the
staging folder into its place, updating `case_video_sha256` in `scene_manifest.json`; it is the only command that
replaces the published suite.

## Outputs

- New exports, solves and renders go to `renders/football_goal_net/<run>/`. A render folder holds the PNG frames,
  range reports, render_setup.json (every frame, its range report and the code and inputs it was made with) and
  video.mp4.
- Accepted physics delivery (the source and mass_double solver jobs with executed code, frozen inputs and receipts):
  `renders/football_goal_net/accepted_physics/`; the timed solve reads it. Accepted media delivery (per-case render
  reports, 24 Hz states, one reference video per case): `renders/football_goal_net/accepted_media/`; `--stage verify`
  and `--mode canonical` read it.
- Published suite: `renders/pcve_suites/pcve_football_goal_net_suite/` (pointer in `scene_manifest.json`). The merged
  timed solve is in its `inputs/native_timed/mass_double_at_frame_8/` (simulation.npz, timed_edit.json,
  prefix_vs_accepted_source.json and the edit run's physics_report.json, run_identity.json and prefix_lineage.json).
- `tools/publish_suite.py` assembles videos, prompts, provenance, media checks and the ground truth (written in
  Blender, required to be `pcve_ground_truth/1`) and carries over the `standardization` records
  of the published provenance.json files.
- Ground truth (`tools/export_ground_truth.py`, `pcve_ground_truth/1`): frame i is native sample 5(i-1). The ball is a
  rigid body (location, quaternion, matrix_world, linear and angular velocity); the net is deformable and tracked by
  its node centroid (identity rotation, node count, bounding box, maximum node displacement from frame 1); the turf is
  not tracked (frames carry the minimum relative height of its solver samples). The camera record (matrix_world, pixel
  intrinsics, lens, sensor, shift, clip range, depth of field) is rebuilt with `appearance/camera.py` and checked
  against the render setup of the published video, from which it takes aperture and focus. Full net node arrays stay
  in the native caches named in `source`. For the timed edit the tool reads the merged solve in the suite's
  `inputs/native_timed/<case>/`; its frames 1-7 equal the source.

## Code layout

```
simulate_football_goal_net.py        export the 120 Hz native state or the 24 Hz subset; --mode solve runs the timed edit
render_football_goal_net.py          export the published video; --render replays a case with the look and encodes it
build_pcve_football_goal_net.py      edit catalog (PCVE_SOURCE / PCVE_EDITS); --stage verify | prepare | simulate | all
edit_vocab.py                        DSL vocabulary, solver_overrides(), timed edits (TIMED_DSL)
scene_manifest.json                  published suite pointer (canonical_suites) and data locations
entrypoints.json                     unified entry declaration
physics/solve_timed.py               timed edit: prefix to the edit frame, checkpoint, edited continuation, merge
physics/strict_edit_plan.json        baseline physics and the overrides of every case (SI)
appearance/render.py                 Blender replay: scene build, per-frame binding checks, render settings, report
appearance/realism.py                look applied by render.py after the build
appearance/camera.py                 fixed camera
appearance/look_base.py, surfaces.py net, ball, turf and surface shaders of the packed scene
appearance/turf.py, grass_binding.py turf binding to the solver samples
appearance/grass_patches.py          static grass tiles
appearance/backdrop.py, stadium_backdrop.py  stadium photograph re-projection and frozen collision surfaces
appearance/visual_profile.py, visual_layout.json  layout corrections and visual profile of the packed scene
appearance/rebound_board.py, training_rebound_board.preset.json  board geometry and look, drawn only when a native cache contains the board
tools/retained.py                    data locations and the verify checks
tools/export_ground_truth.py         suite ground truth from the native states (runs in Blender)
tools/publish_suite.py               assembles a suite from render outputs (ground truth included)
```

`PCVE_SOURCE` / `PCVE_EDITS` in the builder match the published prompts.json files (`--export-prompts --dry-run`
reports every case unchanged). The SET and DELETE prompts, including the timed one, are `pcve_edit_dsl.make_prompts`
output for `edit_vocab.py`; the source prompts are written from `physics/strict_edit_plan.json`, the net model and the
source video (`description_basis` in the builder). No published case contains the rebound board
(`training_rebound_board_present`).

## Limitations

- Materials are effective values, not calibrated on a real net (`material_calibrated: false` in the ground truth).
- The stored caches were computed as single-core CPU jobs on another Linux machine. Four of the five whole-clip jobs
  continued earlier runs from their checkpoints, which are not kept, so only the timed edit can be solved again.
- The published videos were rendered with OptiX on RTX 4090 and RTX 3090 cards, every frame of a case on one card model
  with the same settings; the render report records the machine of every frame range.
- `appearance/grass_patches.py` and `appearance/visual_profile.py` keep no-op host-check functions (`_remote_only`,
  `_assert_remote`); the render path does not check the machine.
