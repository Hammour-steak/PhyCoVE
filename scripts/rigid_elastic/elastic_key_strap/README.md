# elastic_key_strap

A wooden key rack hangs on the wall above an entryway cabinet. A thin silicone strap hangs from its middle hook and a
steel keyring at its lower end carries two keys. The keys start slightly lifted with the strap slack and bowed;
released, they drop, stretch the strap, snap it taut and bounce with internal damping and a small three-dimensional
sway before settling. Without the strap they fall onto the cabinet top. The scene is rigid–elastic (rigid keys and
ring on a viscoelastic membrane strap). The source video is 4 s at 24 fps (96 frames, 1280×720) at normal speed:
video frame f is the native state at t = (f-1)/24 s; the 97th native state at t = 4 s stays in the cache.

## Scene

- Strap: silicone, 216 x 10 x 0.8 mm, density 1070 kg/m³, pinned at its top edge to the middle hook (y 0.090 m,
  z 1.283 m) and welded at its bottom edge to the ring; the moulded eyelet is sized so its hole rests on the hook rod.
- Keyring: steel, 24 mm across, 3.5 g, free body; two keys (5.9 cm and 5.4 cm long, 27 g together) hang from it on
  ball joints and collide through convex hulls of their meshes.
- Start pose: the ring at rest 35 mm above the straight-strap position and 9 mm to the side; hook anchor 1.28 m above
  the floor, cabinet top 0.86 m. Camera, light and start pose are the same in every case.
- Camera: fixed, 40 mm lens, f/8 (`appearance/render_scene.py`).
- Room and light: a closed room (floor, ceiling, side and front walls, a 140 mm thick window wall), so daylight enters
  only through a 1.45 x 1.35 m side window with a fixed narrow pane. The light is the
  `kloofendal_48d_partly_cloudy_puresky` sky panorama seen through the window (its own sun turned behind a solid wall,
  a light portal in the opening) and a late-afternoon sun lamp (0.55 degrees) that throws a window patch with the
  mullion shadow, the plant and the hanging keys onto the wall; brightness falls off away from the window. There are
  no hidden area lights or fill lamps.
- Wall: warm white emulsion over the scanned plaster relief with a faint roller-lap tone drift.
- Dressing (real size unless noted): a potted plant and a framed photograph (half size, a 38 x 25 cm print behind a
  clear glass pane) on the left, a wooden bowl as a catch-all on the right, steel rosettes where the hooks leave the
  rack and two mounting screws at the rack's ends. Every prop stands on the cabinet top and stays outside the swept
  volume of all cases (checked by the look).
- Rack hooks: 5 mm satin steel with a ball tip, leaving the oak board through an 18 mm base plate with two screws; the
  bottom of the J is where the strap's top edge is pinned. The hooks are not part of the solve. The dark arcs on the
  board are the hooks' shadows, cast in the same direction as the plant's and the keys' shadows.
- Materials: a sage silicone strap; nickel and brass finishes on the keys and the ring.
- Render (`appearance/realism.py`, Blender 4.3.2 Cycles): 384 samples, adaptive threshold 0.005, OpenImageDenoise
  (albedo + normal), indirect clamp 6, fixed seed, motion blur with a 0.25-frame shutter between consecutive native
  states (persistent data off), AgX Medium High Contrast at +0.3 EV, mild vignette and lateral colour from
  `pcve_realism_kit.lens_finish`, 1280×720, 24 fps, 96 frames.
- realism.py bakes the 96 native states into linear keyframes and per-frame strap shape keys (so motion blur sees the
  real motion between frames) and checks every frame of the scene against the solve before rendering (positions and
  strap mid-surface within 2e-6 m).

## Physics

- Solver: `physics/physics_model.py` couples a 25 x 2-node silicone ribbon to native MuJoCo 3.3.7 rigid bodies on the
  CPU: a finite-strain plane-stress Neo-Hookean membrane (E = 450 kPa), native MuJoCo discrete bending and an
  objective Kelvin-Voigt reference-strain viscosity (2200 Pa s), applied through a numba passive-force callback.
- Constraints and contact: the strap's top edge is pinned to the hook and its bottom edge welded to the ring; the keys
  hang on ball joints; contact with the cabinet top and the wall.
- Integration: explicit Euler at dt = 1/768000 s, sampled at 24 Hz (97 states) plus a 240 Hz trace.
- Parameters: `physics/scene_spec.json` holds the baseline; `edit_vocab.py` holds the shared-DSL vocabulary (`CASE_DSL`
  for the whole-clip edits, `TIMED_DSL` for the timed one); each case is the baseline plus
  `edit_vocab.override_for(case)`.
- Timed edit: for `keys_mass_5x_at_frame_24` the solver loads the source solve given by `--source-cache` (default: the
  stored source solve), restores its MuJoCo state (qpos, qvel, float64) at frame 24, sets the key mass there and keeps
  solving. The Newton warm start (solver tolerance 1e-10) and the 240 Hz dissipation accumulator restart at the edit
  frame. The merged solve takes frames 1-23 from the source (checked to be identical) and the continuation from frame
  24 on; its physics_audit.json records the edit frame, the source cache and its SHA-256, the parameters after the edit
  and the hand-off error.
- Output of one solve: simulation.npz (times, qpos, qvel, body poses, strap vertices), trace_240hz.npz,
  resolved_config.json, scenario_overrides.json, physics_audit.json (solver, machine, platform, steps, warnings,
  extrema) and model.xml.

## Validation

- `--stage verify` checks the accepted delivery of the whole-clip cases (edit policy of the published edits, resolved
  parameters against the vocabulary, cache and video SHA-256 against accepted_case.json, the 24 Hz clock, no retiming
  or smoothing in the replay) and the published suite for all six cases (video hashes pinned in
  `scene_manifest.json`, 1280×720 / 24 fps / 96 frames, prompts equal to the builder, ground truth on the 96-frame
  clock and written from the case's solve, every absolute path in the suite manifest present).
- Temporal stability of the five whole-clip videos at 480x270 over frames 49-96: on the wall, rack, switch, photograph
  and plant pot the mean frame-to-frame change is at most 0.04/255 and the 99th-percentile per-pixel standard deviation
  at most 0.5/255 in every case; on the cabinet top it is at most 1.3/255 except where the keys land
  (`edit_keys_mass_5x`, `edit_strap_soft`).

## Cases

The builder's native case ids drop the `edit_` prefix of the published case directories (`edit_strap_soft` is native
case `strap_soft`).

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | strap E = 450 kPa, viscosity 2200 Pa s; keys 27 g; bowed start, drop, snap taut, rebound, settling |
| `edit_keys_mass_5x` | `SET keys.mass TIMES 5` | keys 27 -> 135 g; the heavier keys stretch the strap until they reach the cabinet top |
| `edit_strap_soft` | `SET strap.young_modulus TIMES 0.1` | strap 450 -> 45 kPa; the keys reach the cabinet top |
| `edit_strap_stiff` | `SET strap.young_modulus TIMES 10` | strap 450 kPa -> 4.5 MPa; the strap barely stretches |
| `edit_remove_strap` | `DELETE strap` | no strap; the keys fall onto the cabinet |
| `edit_keys_mass_5x_at_frame_24` | `SET keys.mass TIMES 5 AT FRAME 24` | frames 1-23 equal the source; from frame 24 (t = 23/24 s) the keys weigh 135 g |

## Assets

- `scenes/elastic_key_strap` (mixed: 7 url, 3 manual, 41 derived): key, cabinet and tray models, wall plaster and oak
  veneer maps, prepared key geometry (`prepared/key{1,2}.npz`), receipt artwork and the stored whole-clip solves
  (`native_solves/cases/<case>/`).
- `polyhaven/potted_plant_04` (mixed: 8 url, 3 derived): plant on the cabinet.
- `polyhaven/hanging_picture_frame_02` (mixed: 15 url, 3 derived): framed photograph.
- `polyhaven/wooden_bowl_02` (url): catch-all bowl.
- `polyhaven/kloofendal_48d_partly_cloudy_puresky` (url): sky panorama behind the window.

```bash
python3 scripts/download_assets.py --scene elastic_key_strap
python3 scripts/download_assets.py --scene elastic_key_strap --check
```

## Requirements

- Solver: Python 3.10 with numpy, numba, scipy and mujoco==3.3.7 (`.venv-rigid-elastic` is the declared runtime);
  MuJoCo 3.15 rejects the model (`flex/contact internal`). CPU only.
- Renderer: Blender 4.3.2 (`tools/blender-4.3.2-linux-x64` when present, else `pcve_assets.blender()`); a GPU for
  `--device optix|cuda`, or `--device cpu`.

## Commands

```bash
# catalog, prompts, verification
python3 scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py --list-cases
python3 scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py --list-edits
python3 scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py --show-prompts keys_mass_5x_at_frame_24
python3 scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py --export-prompts \
    --out-root renders/pcve_suites/pcve_elastic_key_strap_suite --dry-run
python3 scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py --stage verify

# rebuild into a new folder
OUT=renders/elastic_key_strap/rebuild/<run>
python3 scripts/rigid_elastic/elastic_key_strap/simulate_elastic_key_strap.py --case source --out-root $OUT
python3 scripts/rigid_elastic/elastic_key_strap/simulate_elastic_key_strap.py --case keys_mass_5x_at_frame_24 \
    --out-root $OUT --source-cache $OUT/physics/source
python3 scripts/rigid_elastic/elastic_key_strap/render_elastic_key_strap.py --case source --out-root $OUT \
    --device optix --gpu-uuid <GPU UUID>
python3 scripts/rigid_elastic/elastic_key_strap/render_elastic_key_strap.py --case keys_mass_5x_at_frame_24 \
    --out-root $OUT --cache-dir $OUT/physics/keys_mass_5x_at_frame_24
python3 scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py --stage all --out $OUT
python3 scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py --stage publish --out $OUT

# new suite and ground truth
python3 scripts/rigid_elastic/elastic_key_strap/tools/publish_suite.py --native $OUT --suite $OUT/pcve_elastic_key_strap_suite
python3 scripts/rigid_elastic/elastic_key_strap/tools/export_ground_truth.py --out $OUT/ground_truth
```

`--stage all` runs prepare, simulate and render (`--accepted-physics` renders the stored solves instead of
`$OUT/physics`); `--stage publish` writes `$OUT/pcve_elastic_key_strap_suite`. A render without `--cache-dir` replays
the stored solve of its case; `--frames` renders a subset of video frames. `tools/publish_suite.py --native $OUT
--publish` builds and checks a new suite in `$OUT/suite_staging/`, then moves the published suite into
`renders/pcve_suites_archive/`, puts the checked copy in its place and updates the video hashes in
`scene_manifest.json`; it is the only command that replaces the published suite.

## Outputs

- Solves: `<root>/physics/<case>/`; renders: `<root>/realism/<case>/frame_0001..0096.png` with
  native_replay_audit.json, appearance_scene_audit.json and realism_provenance.json (one per frame range when
  `--frames` splits a case). The default root is `renders/elastic_key_strap/rebuild/<UTC stamp>`; `scene_paths`
  refuses outputs in `scripts/`, the assets, the accepted delivery and `renders/pcve_suites/`.
- Stored whole-clip solves: `assets/scenes/elastic_key_strap/native_solves/cases/<case>/`; `--stage verify`, the default
  source cache, the default render cache and the ground truth of the whole-clip cases read them.
- Accepted delivery of the whole-clip cases: `renders/elastic_key_strap/accepted_physics/` (accepted_case.json,
  suite_manifest.json, per-case audits, `cases/<case>/video.mp4`); renders of the published whole-clip videos:
  `renders/elastic_key_strap/accepted_media/realism/<case>/`.
- Published suite: `renders/pcve_suites/pcve_elastic_key_strap_suite/` (pointer in `scene_manifest.json`); the merged
  native solve of the timed edit is in its `inputs/native_timed/keys_mass_5x_at_frame_24/`.
- `tools/publish_suite.py` builds into `--suite` (default
  `renders/elastic_key_strap/suite_build/pcve_elastic_key_strap_suite/`) and pairs each render with the solve it replayed (checked by the render record's
  native_cache_sha256), writes prompts from the builder and `pcve_ground_truth/1` ground truth, carries the
  `standardization` records of the published case provenance and never writes into an existing
  suite.
- Ground truth (`tools/export_ground_truth.py --out DIR`, writes `DIR/<case>/ground_truth_transforms.json`; the
  published suite is only read): the fixed camera with its intrinsics as recorded by the renderer
  (native_replay_audit.json in the case's native_metadata/), and per frame the world matrix, location, quaternion,
  linear and angular velocity of the keyring and both keys (MuJoCo body frames: the ring centre and the ball-joint
  pivots; joint velocities mapped through the kinematic tree; poses rebuilt from qpos are checked against the stored
  body poses and the ring velocity against the 240 Hz trace), and the strap's presence, mid-surface centroid, bounds,
  centreline length and end points (`present: false` without the strap).

## Code layout

```
build_pcve_elastic_key_strap.py   edit catalog (PCVE_SOURCE / PCVE_EDITS); --stage verify | prepare | simulate | render | publish | all
simulate_elastic_key_strap.py     one native solve: DIR/physics/<case> (--source-cache for the timed case)
render_elastic_key_strap.py       one case with the published look: DIR/realism/<case> (--cache-dir to replay another solve)
edit_vocab.py                     DSL vocabulary, CASE_DSL, TIMED_DSL, override_for()
scene_paths.py                    solve, delivery, suite and output locations; output guard; Blender runtime
scene_manifest.json               published suite pointer (canonical_suites) and data locations
entrypoints.json                  unified entry declaration
physics/physics_model.py          MuJoCo 3.3.7 + membrane solver (also the timed continuation)
physics/scene_spec.json           baseline parameters and clip contract
appearance/render_scene.py        base scene: moving parts, rack, cabinet, camera; its main() renders the base scene alone
appearance/realism.py             published look, keyframe baking, per-frame replay check, rendering
tools/publish_suite.py            assembles a suite from finished renders (--publish replaces the published suite)
tools/export_ground_truth.py      ground truth of each suite case from its native solve
```

The prompts of every case are declared in `PCVE_SOURCE` / `PCVE_EDITS` of the builder and equal the published
prompts.json files; `--export-prompts` writes them to a suite.

## Limitations

- Material values are nominal values for silicone, not a calibration against a product; the keys collide through
  convex hulls of their meshes.
- The five whole-clip solves were computed on a Windows workstation with MuJoCo 3.3.7 on the CPU and the timed
  continuation on a Linux machine with the same MuJoCo (recorded in each case's physics_audit.json). The timed case
  continues the Windows source solve; an unchanged-parameter continuation on Linux differs from that source by at most
  5e-10 in qpos, the same as a full Linux re-run, so a re-solve on another platform is close to but not bitwise equal
  to the published solves.
- The published videos were rendered on a Linux machine with an RTX 3090 (OptiX, 384 samples, about 14 s per frame);
  the parts of one case share the device type, settings and code hashes (checked when the parts are merged).
