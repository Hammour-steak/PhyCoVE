# picnic_ground_blanket

A mandarin orange rolls across a cotton gingham picnic blanket that lies freely on a lawn; the orange, the blanket and
the grass layer under it are solved together, so the blanket and the lawn dip where the orange passes, and the orange
slows to rest. The scene is rigid–elastic: a rigid orange on a thin cloth shell over an FEM grass volume. The source
video is 4 s at 24 fps (96 frames, 1280×720): video frame i is the solver state at t = (i-1)/24. The case number 2 is
kept in `entrypoints.json` (`case_number`).

## Scene

- Orange: scanned closed mesh, radius 3.2 cm, 0.11 kg; its centre starts at (-0.290, -0.065, 0.086) m rolling at
  0.9 m/s to +x.
- Blanket: 0.84 m x 0.60 m, 0.45 mm thick, lying freely on the lawn. Woven gingham in unbleached cotton white, mid green
  where one dyed yarn crosses and deep green where both do; fibre speckle, millimetre yarn-slub bump and faint soiling in
  fabric (UV) coordinates, so they move with the cloth; cotton fuzz as a sheen tinted by the yarn colour; the
  photographed weave normal/roughness are kept. A 12 mm folded hem on all four sides: three layers thick (Solidify
  thickness 1.3 mm by a hem vertex group; the body stays 0.45 mm), a soft fold ridge, a running stitch 8.5 mm from the
  edge and a rounded edge. The native cloth vertices are not changed.
- Grass layer: 5 cm deep FEM volume rooted at the bottom. Grass blades near the cloth are render proxies that follow the
  solved FEM support surface (their full rotated footprint is capped under the cloth); individual blades are not
  simulated.
- Static props beside the blanket (not in the physics): a thermos (brushed stainless steel; its printed decal is not
  rendered), a mug and a plate with croissants and a second orange.
- Lawn: per-plant brightness/hue variation and metre-scale lush/yellowing patches on the scanned grass
  (grass_bermuda_01, grass_medium_01, shrub_sorrel_01) and ground; a fine rooted understory near the cloth; the same
  scanned turf continues through the camera footprint to the horizon (`appearance/far_meadow.py`, about 309,000
  instances).
- Blanket border: grass blades within 3.5 cm of the border are darker (crowded and shaded), and 126 short scanned grass
  tufts stand 6-20 mm outside the border with tips 10-30 mm above the hem. They are static and identical in every case.
  The layout is derived from the six stored native states of the asset store together (including
  `native/add_path_obstacle/`, an ADD solve that is not a published case; with five states the layout would have 129
  tufts), from the rest shape of the source, with every footprint at least 3 mm from the cloth in every frame of every
  state; each candidate draws the same random numbers whether or not it is kept (layout SHA-256 `02c293a8…`). The timed
  edit keeps this layout; its own cloth track is only checked for clearance and reported (nearest tuft root 10.28 mm
  from its cloth border; stored states 10.14 mm), so its frames before the edit show the same scene as the source.
- Daylight: the `kloofendal_48d_partly_cloudy_puresky` sky (2k HDR) lights the scene and appears in reflections. Its sun
  (47.9° elevation, measured from the map) is cut from the map and replaced by a sun lamp in the same direction with the
  same integrated irradiance and colour, so the photographed balance is kept: on level ground the sun gives 3.27 and the
  rest of the sky 1.52 (relative units), and shadows are crisp (0.6° disc). The sky is turned so the sun stands left of
  and a little behind the camera; shadows of the thermos, mug, plate and orange fall to the right. No fill light.
- Shade: crowns of three park trees outside the picture shade the lawn left of and behind the blanket (a shadow-only
  canopy layer 8 m up; the code checks that each tree is outside the field of view and that no shade comes within 3 m
  of the blanket centre).
- Camera: fixed (`scene_manifest.json` `camera`), 45 mm lens, 36 mm sensor, no shift, f/16 focused at 1.76 m. The
  renderer checks the packed camera against `scene_manifest.json` and checks every frame that it has not moved.
- Render (`appearance/render_replay.py` with `appearance/look.py`): Blender 4.3.2 Cycles, 512 samples, adaptive
  (threshold 0.006, minimum 64), OpenImageDenoise with albedo/normal and accurate prefilter, fixed seed, 12 bounces
  (48 transparent), glossy blur 0.5, indirect clamp 12, AgX Medium High Contrast, exposure 0, no motion blur, 24 fps.
  Every frame the native cloth vertices and rigid transforms are written into the packed scene, its stale shape-key
  animation is cleared, and Blender's evaluated cloth mid-surface is checked against the cache (2 µm, the cosmetic
  Solidify thickness excluded).

## Physics

- Solver: libuipc CUDA IPC (`physics/simulate.py`), one solve per case.
- Orange: affine rigid body on its scanned closed mesh, friction 0.55, initial roll matching its speed.
- Blanket: free Baraff-Witkin thin shell with discrete shell bending, 420 kg/m³, E 3 MPa, bending 6e-6 N·m.
- Grass layer: StableNeoHookean FEM volume, 80 kg/m³, E 900 Pa, ν 0.16.
- Viscosity: the native metric/dihedral viscosity extension (`scripts/pcve_native_viscosity.cu`, `physics/viscosity.py`;
  prebuilt module `tools/viscosity_plugin` at the repository root, `PCVE_NATIVE_RUNTIME` overrides it) is solved in
  the same Newton/IPC system.
- Integration: every case starts from one common warm start (`initial_state.npz`), runs dt 1/2400 s with velocity
  tolerance 1e-5 and no preload for 4 s, and records the states at i/24 s, i = 0..95.
- Parameters: `physics/scene_specs.json`; `physics/simulate.py` and `physics/scene_specs.json` also carry the parameters
  of the related gym_landing_mat setup (`--scene gym_landing_mat`) and of a picnic-cup obstacle that no published case
  uses (`picnic_cup_active` 0).
- Timed edit: `physics/simulate.py --source-cache <source cache.npz>` builds the world with the edited mass, restores the
  complete libuipc state of source frame 12 (grass FEM and cloth vertex positions and velocities, the orange's affine
  transform and velocity), reads it back and checks it against the cache (hand-off error 0 for all six arrays, limit
  1e-8), checks that the solver configuration equals the stored source solve and that the parameters differ only in
  `body_mass`, and solves on to 4 s with the same settings. In the merged `cache.npz` frames 1-11 are the stored source
  cache (checked bit for bit) and frames 12-96 the continuation (`continuation.npz`).

## Measured motion

From the native states (orange centre, frame 1 at (-0.290, -0.065, 0.086) m):

| Case | Orange at 4 s (x, y, z) m | Horizontal travel |
| --- | --- | --- |
| `source` | (-0.051, 0.025, 0.068) | 0.256 m, at rest from about frame 31 |
| `edit_mass_double` | (-0.101, -0.012, 0.061) | 0.197 m |
| `edit_faster` | (0.298, 0.044, 0.065) | 0.598 m |
| `edit_stiffer` | (-0.084, 0.000, 0.075) | 0.216 m |
| `edit_delete_actor` | - (no orange) | - |
| `edit_mass_double_at_frame_12` | (-0.052, 0.022, 0.062) | 0.254 m |

At frame 12 the orange has nearly stopped; with the doubled mass it presses a little deeper and stays almost where it
is.

## Validation

- `--stage verify` (default) checks the published suite: videos, prompts, ground truth (re-exported and compared for every
  case), native inputs and the timed-edit records (`tools/verify.py`).
- Temporal stability: frame-to-frame change in the static parts of the picture (far lawn, props) at 480 × 270 is below
  0.1/255 on average; frame 1 of the source and of `edit_stiffer` (identical physics at that instant) differ by 0 pixels
  above 20/255.

## Cases

The builder's native case ids drop the `edit_` prefix of the published case directories (`edit_faster` is native case
`faster`).

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | orange 0.11 kg at 0.9 m/s; grass E 900 Pa |
| `edit_mass_double` | `SET mandarin_orange.mass TIMES 2` | `body_mass` 0.11 -> 0.22 kg |
| `edit_faster` | `SET mandarin_orange.initial_velocity TIMES 2` | `body_initial_speed` 0.9 -> 1.8 m/s |
| `edit_stiffer` | `SET grass_thatch.young_modulus TIMES 10` | `solid_young_modulus` 900 -> 9000 Pa |
| `edit_delete_actor` | `DELETE mandarin_orange` | `active` [1, 1] -> [0, 1] |
| `edit_mass_double_at_frame_12` | `SET mandarin_orange.mass TIMES 2 AT FRAME 12` | `body_mass` 0.11 -> 0.22 kg from frame 12 (t = 11/24 s) |

## Assets

- `scenes/picnic_ground_blanket` (derived, 26 files): packed render scene (`packed_scene.blend`: camera, props, scanned
  plants, blanket mesh), the closed orange contact mesh (`mandarin_geometry.npz`) and the stored native state of each
  whole-clip case and of `add_path_obstacle` (`native/<case>/`: `cache.npz`, `initial_state.npz`,
  simulation_config.json, simulation_report.json).
- `polyhaven/kloofendal_48d_partly_cloudy_puresky` (url): sky of the look.

```bash
python3 scripts/download_assets.py --scene picnic_ground_blanket
python3 scripts/download_assets.py --scene picnic_ground_blanket --check
```

## Requirements

- Solves: Linux and a CUDA GPU (`scene_paths.require_linux`; `tools/worker_run.py` leases a GPU through
  `scripts/pcve_gpu_policy.py`), libuipc and the native viscosity module.
- Rendering: Blender 4.3.2 on any CUDA/OptiX GPU or on the CPU.
- Verify, ground-truth export, packaging and publishing need numpy and Pillow; the builder runs them with
  `.venv-rigid-elastic/bin/python` when the calling Python lacks them.

## Commands

```bash
# verification and catalog
python3 scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py --stage verify
python3 scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py --list-cases
python3 scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py --list-edits
python3 scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py --show-prompts mass_double_at_frame_12
python3 scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py --export-prompts \
    --out-root renders/pcve_suites/pcve_picnic_ground_blanket_suite --dry-run

# re-render and package the stored native states of the whole-clip cases
python3 scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py --stage replay \
    --gpu-uuid <GPU UUID> --out renders/picnic_ground_blanket/rebuild/<run>
# selected frames of one case (look development)
python3 scripts/rigid_elastic/picnic_ground_blanket/render_picnic_ground_blanket.py --case-id source --still-frame 1 40 \
    --out renders/picnic_ground_blanket/rebuild/<run>/look_check
# new native solve, then render and package
python3 scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py --stage all --cases faster \
    --out renders/picnic_ground_blanket/rebuild/<run>
# timed edit: continue from the source state of frame 12, then render that solve
python3 scripts/rigid_elastic/picnic_ground_blanket/simulate_picnic_ground_blanket.py --case mass_double_at_frame_12 \
    --out renders/picnic_ground_blanket/rebuild/<run>/mass_double_at_frame_12/simulation
python3 scripts/rigid_elastic/picnic_ground_blanket/render_picnic_ground_blanket.py --case mass_double_at_frame_12 \
    --simulation renders/picnic_ground_blanket/rebuild/<run>/mass_double_at_frame_12/simulation \
    --out renders/picnic_ground_blanket/rebuild/<run>/mass_double_at_frame_12/render
.venv-rigid-elastic/bin/python scripts/rigid_elastic/picnic_ground_blanket/tools/finalize.py \
    --render renders/picnic_ground_blanket/rebuild/<run>/mass_double_at_frame_12/render --case mass_double_at_frame_12 \
    --simulation renders/picnic_ground_blanket/rebuild/<run>/mass_double_at_frame_12/simulation

# ground truth of one case compared with the published suite; a new suite from finished renders
.venv-rigid-elastic/bin/python scripts/rigid_elastic/picnic_ground_blanket/tools/export_ground_truth.py --case source \
    --compare renders/pcve_suites/pcve_picnic_ground_blanket_suite
.venv-rigid-elastic/bin/python scripts/rigid_elastic/picnic_ground_blanket/tools/publish_suite.py \
    --delivery renders/picnic_ground_blanket/rebuild/<run> --suite renders/picnic_ground_blanket/rebuild/<run>/pcve_picnic_ground_blanket_suite
```

`--stage replay` and `--reuse-native` apply to the whole-clip cases only; the timed edit has no stored state to replay.
The render entry also takes `--device GPU|CPU`, `--cycles-backend OPTIX|CUDA`, `--samples` and `--frame-start A
--frame-end B`. `tools/publish_suite.py --publish` (instead of `--suite`) builds in `<delivery>/suite_staging`, checks,
then replaces the published suite; it is the only command that writes there.

## Outputs

- New solves and renders go under `renders/picnic_ground_blanket/` (for example `rebuild/<run>/<case>/simulation` and
  `<case>/render`); outputs may not be written into the published suite, the accepted delivery or the asset store.
- `tools/finalize.py` encodes the 96 PNG frames with libx264 CRF 17, preset slow, yuv420p, and writes instance masks
  (orange, blanket), the ground truth and the media audits. A case rendered in frame ranges (render report parts) is
  merged after checking that inputs, settings, appearance and device type are identical.
- Accepted delivery of the whole-clip videos (`scene_manifest.json` `data.accepted_delivery`):
  `renders/picnic_ground_blanket/accepted/<case>/render/`; per case the repository keeps render/video.mp4 and
  render/render_report.json (read by `--stage verify`); the frames are not kept.
- Published suite: `renders/pcve_suites/pcve_picnic_ground_blanket_suite/` (`scene_manifest.json` `canonical_suites`).
  The timed edit has no state in the asset store: its solver and render records are in the suite case's
  `native_metadata/`, and the merged cache is recorded (path and SHA-256) in its provenance.json.
- Ground truth (`tools/export_ground_truth.py`, `pcve_ground_truth/1`): per frame i (t = (i-1)/24) the orange with its
  native affine world transform (`present: false` in `edit_delete_actor`), and the blanket and the grass layer as
  deformable bodies whose location is the centroid of their vertices in that frame (blanket mid-surface; top surface of
  the FEM grass layer); the camera is `scene_manifest.json` `camera`. In the timed edit frames 1-11 equal the source.
  Full vertex data stays in the native cache.
- GPU launches record their job under `.runtime/picnic_ground_blanket/jobs`.

## Code layout

```
simulate_picnic_ground_blanket.py     native libuipc solve of one case through the GPU launcher
render_picnic_ground_blanket.py       replay of one case into the packed scene with the look
build_pcve_picnic_ground_blanket.py   edit catalog (PCVE_SOURCE / PCVE_EDITS); --stage verify | validate | simulate | render | finalize | all | replay
edit_vocab.py                         public edit vocabulary (loads physics/edit_vocab.py)
scene_inputs.py                       native inputs of every case
scene_paths.py                        paths, output guard, Linux requirement
scene_manifest.json                   camera, published suite pointer, data locations
entrypoints.json                      unified entry declaration
physics/simulate.py                   libuipc solve, including the timed continuation
physics/geometry.py, scripts/pcve_fem_geometry.py  blanket, grass and body geometry
physics/scene_specs.json              scene specification
physics/edit_vocab.py                 objects, properties, DSL bindings, timed cases
physics/viscosity.py                  loader of the native viscosity module
scripts/pcve_native_viscosity.cu, scripts/pcve_native_viscosity_frontend.cpp  native viscosity sources
appearance/render_replay.py           replays a native state into the packed scene and renders it
appearance/look.py                    light and materials
appearance/far_meadow.py              scanned turf continued over the far lawn
tools/finalize.py                     video, instance masks, ground truth and audits of one rendered case
tools/export_ground_truth.py          ground_truth_transforms.json (pcve_ground_truth/1) from a native state
tools/publish_suite.py                suite assembly
tools/verify.py                       suite verification
tools/worker_run.py                   GPU launcher of a native solve (lease, UUID binding; scripts/pcve_gpu_reservations.py)
```

`PCVE_SOURCE` and `PCVE_EDITS` in the builder declare the source description and the five edits (DSL, physics override
and diff, native case id, bilingual vague and quantitative prompts); `--export-prompts` writes them into the suite's
prompts.json (`pcve_prompts/1`). The edit prompts are the `pcve_edit_dsl.make_prompts` output for
`physics/edit_vocab.py`; the quantitative source prompt gives the blanket size, grass depth, orange size, mass and
speed, and the rolling distance. `look.enamel_cup` and the cup branch of `appearance/render_replay.py` render a
picnic-cup obstacle only when a native state contains one; `tools/finalize.py` rejects a visible cup.

## Limitations

- Material values are effective, not calibrated against a measured blanket or lawn.
- The whole-clip native states were solved through the GPU launcher on other Linux GPU machines (their reports do not
  record the machine). The timed continuation ran on an RTX 3090 with the CUDA-12 build of the same viscosity sources
  (`.runtime/gym_landing_mat/native_cuda12` via `PCVE_NATIVE_RUNTIME`; the source used the CUDA-13 build).
- Renders: `edit_mass_double` on RTX 3090 cards, the other four whole-clip cases on RTX 4090 cards, each case split into
  frames 1-48 and 49-96 on two cards of one model with OptiX; the timed edit on an RTX 3090 with OptiX, all 96 frames in
  one run. Bitwise reproduction on other machines is not verified.
