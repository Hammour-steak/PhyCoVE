# metro_security_bag_curtain

A metro-station baggage X-ray scanner. A 4 kg backpack rides the scanner belt, pushes through the six-strip exit lead
curtain, crosses the last 70 cm of belt, drops over a fixed lip onto a stainless chute and stops on the pickup deck
while the strips swing back. The scene is rigid–elastic: a planar rigid backpack two-way coupled to elastic strip
shells. The source video is 4 s at 24 fps (96 frames, 1280×720) at normal speed: frame k shows the native state at
t = (k-1)/24 s (the 97th native state, t = 4 s, stays in the cache).

## Scene

- Conveyor: belt 0.40 m/s, belt top 75 cm above the floor; the belt ends at x = 0.70 m (curtain plane x = 0), a fixed
  lip leads onto a stainless chute (55 cm run, 18 cm drop) and a 65 cm pickup deck ending at x = 1.90 m.
- Backpack: a scanned backpack, 44 x 33 x 21 cm, 4 kg, starting 30 cm before the curtain at 0.2 m/s; belt-backpack
  friction 0.5. Its collider is a signed-distance field of the scan.
- Exit curtain: 6 lead strips, 29.5 cm long, 2.4 mm thick, 51 cm total width, E = 3 MPa. The strips have a satin
  sheen, hanging creases and a scuffed lower edge (shading only; the strip geometry is the native shell).
- Camera: fixed, 35 mm lens on a 36 mm sensor at (2.98, -3.36, 1.61) m looking along (-0.59, 0.80, -0.11), across the
  scanner exit toward the chute and the pickup deck.
- Look (`appearance/realism.py`, on top of the station, scanner and outfeed geometry):
  - No printed text, logos or labels: wall signs, train-direction sign, line directory, gate header text, tray-return
    plate, pickup notice, staff-door plate, scanner nameplate and warning label are removed; the hanging wayfinding
    box shows only pictograms (arrows, train, exit door) built as geometry.
  - Floor: polished sesame-white granite from the `ambientcg/Granite002A` scan, one random crop per 600 mm tile (about
    1 m of stone per texture repeat), base roughness 0.09-0.19 under a polish coat of roughness 0.06-0.12, polished
    walking lanes, stains, fine scratches and darker joint arrises; luminaires, gates and the scanner reflect in it.
  - Light comes only from luminaires in the room: every linear ceiling diffuser (and one run above the camera side)
    carries an area light of its own size (45 W per metre, 110 degree spread, about 5000 K, not visible to camera
    rays), and two ceiling slots wash the back and return walls from the top (12 W per metre, 50 degree spread), so
    the walls grade from bright tops to darker bases and the far corners stay darker.
  - Walls and columns: glazed panels from the `plaster_grey_04` scan with per-panel tone, a clear coat and a dirty kick
    band near the floor; brushed stainless (gates, posts, skirting) with anisotropic grain and fingerprints at hand
    height.
  - Scanner: rounded hood with anthracite end caps, cover seam, top service hatch with four captive screws, two
    recessed lifting handles on the exit end; slight yellowing, handprints and shoe-height scuffs on the powder coat.
    The belt carries the `ambientcg/Rubber002` micro-relief, a skived splice and wear tracks in belt coordinates, so
    they travel with the belt. The operator monitor shows an X-ray image.
  - Concourse props, all on the floor or wall and clear of the bag path: a slim backlit poster box (landscape crop,
    anodised bezel, glossy face), a recessed fire-hose cabinet (red steel frame, clear glass, hose reel, brass landing
    valve with handwheel, canvas hose roll), a brushed-steel litter bin and a yellow caution stand whose only marking
    is a warning triangle.
- Render (`appearance/render_scene.py`, Blender 4.3.2 Cycles): 384 samples, adaptive threshold 0.01, at most 8 bounces,
  OpenImageDenoise with albedo/normal passes, OptiX (CUDA or CPU selectable), no motion blur; AgX Medium High Contrast
  at -1.0 EV (the diffusers clip, the rest keeps its gradients); faint fog glow, mild lateral colour and vignette in the
  compositor. The renderer builds exactly the solver's support planes and hides the curtain from the timed-edit frame
  on.

## Physics

- Solver: `physics/shell_solver.py` solves six independent clamped strip shells (discrete-shell membrane and bending
  with Kelvin-Voigt viscosity, strip self-contact; `physics/constitutive.py`, `physics/self_contact.py`) two-way
  coupled (`physics/curtain_coupling.py`) to planar rigid backpacks with x, z and pitch (`physics/planar_rigid.py`), on
  the CPU in float64 with Numba, dt = 1/9600 s, 12 iterations.
- Support: belt, lip, chute and pickup deck are the solver's support profile.
- Driver: `physics/simulate_case.py` writes a case as `<out-root>/<case>/states.npz` (curtain vertices, backpack rigid
  state and root pose per 24 Hz sample) with simulation_config.json and simulation_report.json. The Numba cache under
  `.runtime/metro_security_bag_curtain/` is keyed by the sha256 of the five solver files; the solve refuses to finish
  if they change meanwhile.
- DSL forms: the solver reads the whole-clip edits in absolute SI form (`edit_vocab.CASE_DSL`, e.g.
  `SET exit_curtain.young_modulus TO 300000000`); `edit_vocab.PUBLIC_DSL` holds the equivalent multiplier form the
  builder catalog publishes; the timed edit is in `edit_vocab.TIMED_DSL`.
- Timed edit: the simulate entry loads the source states (`--source-cache`, default the stored source states in the
  assets), restores the exact float64 state of frame 12 (curtain vertex positions and velocities, backpack x, z, pitch
  and their velocities), removes the curtain there and keeps solving to t = 4 s. Frames 1-11 are the source states
  (asserted equal); the hand-off error is recorded in simulation_config.json (`continuation`) and
  simulation_report.json and is 0.0 for the published case. The merged states.npz carries `curtain_present_per_frame`
  and `timed_edit_frame`.
- The solver also accepts a second backpack (`second_bag_*` inputs of `edit_vocab.BASELINE`); it is off in every case.

## Measured motion

Recorded in the native states (backpack root x at t = 4 s):

| case | backpack x at 4 s | largest curtain vertex x | backpack pitch |
|---|---|---|---|
| `source` | 1.437 m (on the pickup deck) | 0.247 m | 0 to 18.8 degrees |
| `edit_young_modulus_x100` | 1.437 m | 0.245 m | 0 to 18.8 degrees |
| `edit_belt_speed_x2` | 1.489 m | 0.250 m | 0 to 18.1 degrees |
| `edit_friction_x0p02` | -0.265 m (ends before the curtain plane) | 0.117 m | 0 |
| `edit_delete_curtain` | 1.437 m | - | 0 to 18.8 degrees |
| `edit_delete_curtain_at_frame_12` | 1.437 m | 0.103 m (curtain removed at frame 12) | 0 to 18.8 degrees |

## Validation

- `--stage verify` checks the accepted delivery for the whole-clip cases (native states equal
  `edit_vocab.parameters(case)` on the 24 Hz clock, receipts tie each delivered video to its states, replay audit, media
  contract) and the published suite (video sha256 against suite_manifest.json, provenance.json, video_validation.json
  and `scene_manifest.json`, media contract, prompts equal to the builder catalog, native states and ground truth tied
  to the rendered video and its camera); with `--out-root DIR` it checks a rebuild instead. It re-runs itself with
  `.venv-rigid-elastic/bin/python` when NumPy is missing.
- Each published case was rendered whole on one GPU and passed the 96-frame replay audit (every frame of the reopened
  scene against the states, including the curtain's visibility), the grounding audit (`appearance/audit_grounding.py`)
  and the support-plane audit (`appearance/audit_scene_reuse.py`).
- Temporal stability (480x270, static regions including the hood front above the exit) of
  the published renders: mean change between neighbouring frames 0.004-0.015 8-bit levels and worst 8x8 block
  0.13-0.44 levels across the cases; the timed delete reaches 1.19 at the frame where the curtain disappears and the
  indirect light changes.
- Restarting the source from its frame-12 state reproduces frames 13-97 of the stored source bit for bit.

## Cases

The builder's native case ids drop the `edit_` prefix of the published case directories (`edit_belt_speed_x2` is native
case `belt_speed_x2`).

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | belt 0.4 m/s; backpack 4 kg, belt-backpack friction 0.5; strip E = 3 MPa |
| `edit_young_modulus_x100` | `SET exit_curtain.young_modulus TIMES 100` | strip Young's modulus 300 MPa |
| `edit_belt_speed_x2` | `SET conveyor.velocity TIMES 2` | belt 0.8 m/s |
| `edit_friction_x0p02` | `SET bag.friction TIMES 0.02` | belt-backpack friction 0.01 |
| `edit_delete_curtain` | `DELETE exit_curtain` | no curtain, solved and rendered without it |
| `edit_delete_curtain_at_frame_12` | `DELETE exit_curtain AT FRAME 12` | curtain removed at frame 12 (t = 11/24 s); frames 1-11 equal the source |
| `edit_delete_bag` | `DELETE bag` | no backpack: nothing pushes the curtain, which hangs still; solved and rendered by the drivers in the suite's `inputs/edit_delete_bag/` |

## Assets

- `scenes/metro_security_bag_curtain/backpack` (derived): backpack scan and colliders.
- `scenes/metro_security_bag_curtain/granite_tile` (url): granite tile maps.
- `scenes/metro_security_bag_curtain/signage_labels` (derived): project-authored signage and label art.
- `scenes/metro_security_bag_curtain/xray_monitor` (mixed: 1 url, 1 manual): X-ray image on the operator monitor
  (CC BY 2.5; attribution in assets.json and next to the image).
- `scenes/metro_security_bag_curtain/station_art` (derived): project-authored station art.
- `scenes/metro_security_bag_curtain/station_look` (derived): poster lightbox photo read by `appearance/realism.py`.
- `scenes/metro_security_bag_curtain/native` (derived): stored native states of the source and the whole-clip edits.
- `ambientcg/Granite002A` (manual): floor granite.
- `ambientcg/Rubber002` (manual): belt micro-relief.
- `polyhaven/plaster_grey_04` (url): wall panels.

```bash
python3 scripts/download_assets.py --scene metro_security_bag_curtain
python3 scripts/download_assets.py --scene metro_security_bag_curtain --check
```

## Requirements

- Solver: Python with NumPy and Numba (`.venv-rigid-elastic`), CPU only; 25-32 min per case with a curtain.
- Renderer: Blender 4.3.2 (`tools/blender-4.3.2-linux-x64`, or `--blender-bin`) on a Linux machine with an NVIDIA GPU
  (or `--device CPU`); ffmpeg for encoding (`tools/encode_case.py` encodes frames rendered on a machine without
  ffmpeg).
- GPU renders go through `tools/worker_guard.py` (checked idle GPU with a lease, `scripts/pcve_gpu_reservations.py`)
  unless `--gpu-uuid` names a claimed GPU.

## Commands

```bash
# verification, catalog, ground truth check
python3 scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py --stage verify
python3 scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py --stage prepare
python3 scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py --list-cases
python3 scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py --list-edits
python3 scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py --show-prompts delete_curtain_at_frame_12
python3 scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py --export-prompts \
    --out-root renders/pcve_suites/pcve_metro_security_bag_curtain_suite --dry-run
python3 scripts/rigid_elastic/metro_security_bag_curtain/tools/export_ground_truth.py --check
python3 scripts/rigid_elastic/metro_security_bag_curtain/tools/export_ground_truth.py --out renders/metro_security_bag_curtain/<run>/ground_truth

# rebuild (simulation on CPU, rendering on a GPU)
python3 scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py --stage all \
    --cases source delete_curtain_at_frame_12 --out-root renders/metro_security_bag_curtain/<run> --gpu-uuid <GPU UUID>
python3 scripts/rigid_elastic/metro_security_bag_curtain/simulate_metro_security_bag_curtain.py \
    --case delete_curtain_at_frame_12 --source-cache renders/metro_security_bag_curtain/<run>/simulation/source \
    --out-root renders/metro_security_bag_curtain/<run>/simulation
python3 scripts/rigid_elastic/metro_security_bag_curtain/render_metro_security_bag_curtain.py \
    --case delete_curtain_at_frame_12 --cache-root renders/metro_security_bag_curtain/<run>/simulation \
    --out-root renders/metro_security_bag_curtain/<run>/render --save-blend --grounding-audit --gpu-uuid <GPU UUID>
python3 scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py --stage verify \
    --out-root renders/metro_security_bag_curtain/<run>

# a new suite from render outputs (one folder per native case)
python3 scripts/rigid_elastic/metro_security_bag_curtain/tools/publish_suite.py \
    --renders renders/metro_security_bag_curtain/<run>/render \
    --timed-native renders/metro_security_bag_curtain/<run>/simulation \
    --suite renders/metro_security_bag_curtain/<run>/pcve_metro_security_bag_curtain_suite
```

In `--stage all` a timed case continues from the source states of the same rebuild when `source` is among the cases,
otherwise from the stored source states. Simulate options: `--case` (a case or `all`), `--tag`, `--out-root`, `--dt`,
`--iterations`, `--duration`, `--source-cache`. Render options: `--case`, `--tag`, `--cache-root`, `--out-root`,
`--frames all|i,j,k`, `--samples` (384), `--width`, `--device GPU|CPU`, `--backend OPTIX|CUDA`, `--save-blend`,
`--grounding-audit`, `--assemble-only`, `--blender-bin`, `--gpu-uuid`, `--render-threads`.

## Outputs

- New solves, renders and launch records go to `renders/metro_security_bag_curtain/` (default `rebuild_<UTC stamp>/`);
  outputs never go into `scripts/`.
- A render writes frames, video.mp4 (libx264 CRF 16, yuv420p, 24 fps), render_report.json, encoding_receipt.json,
  replay_audit.json and the support audits.
- Stored native states of the source and the whole-clip edits: `assets/scenes/metro_security_bag_curtain/native/accepted_states/<case>/`
  (the default `--tag` of the render entry). Accepted physics delivery read by `--stage verify`:
  `renders/metro_security_bag_curtain/accepted/` (per-case receipts and audits, `cases/<case>/video.mp4`). The frames of the
  published renders are not kept; the suite holds the videos.
- `.runtime/metro_security_bag_curtain/` holds the Numba cache, solver checkpoints and optional pinned ffmpeg and
  Python packages.
- Published suite: `renders/pcve_suites/pcve_metro_security_bag_curtain_suite/` (pointer in `scene_manifest.json`); the
  timed edit's merged native states are in its `inputs/native_timed/delete_curtain_at_frame_12/`.
- `tools/publish_suite.py` writes a new suite folder (it must not exist; default `--suite`:
  `renders/metro_security_bag_curtain/suite_build/pcve_metro_security_bag_curtain_suite/`) in the formats `pcve_suite/1`,
  `pcve_prompts/1`, `pcve_provenance/1`, `pcve_video_validation/1` and `pcve_ground_truth/1`; the `canonical_suites`
  entry of `scene_manifest.json` is updated by hand from the printed video hashes.
- Ground truth (`tools/export_ground_truth.py --out DIR`, writes `DIR/<case>/ground_truth_transforms.json` in the
  `pcve_ground_truth/1` layout): the backpack is the Blender root `bag` (bottom-centre contact root, pitch about +y;
  velocity and centre of mass included); the curtain is tracked by its vertex centroid with its bounds, strip centroids
  and largest displacement (deformable; absent from frame 12 on in the timed edit); the conveyor is kinematic and not
  tracked; the fixed camera comes from the case's `native_metadata/render_report.json`. `--check` recomputes and
  compares with the published files.

## Code layout

```
simulate_metro_security_bag_curtain.py   native solve of one case or all (runs physics/simulate_case.py)
render_metro_security_bag_curtain.py     Blender 4.3.2 replay of native states (runs appearance/render_scene.py)
build_pcve_metro_security_bag_curtain.py edit catalog (PCVE_SOURCE / PCVE_EDITS); --stage verify | prepare | simulate | render | all
edit_vocab.py                            baseline physics, case DSL, public DSL, timed DSL, DSL vocabulary
scene_paths.py                           repository locations (assets, native states, runtime, renders, suite)
scene_manifest.json                      published suite pointer (canonical_suites) and data locations
entrypoints.json                         unified entry declaration
physics/shell_solver.py                  strip shells coupled to planar rigid bodies and the outfeed
physics/constitutive.py                  membrane, bending and viscosity forces
physics/self_contact.py                  strip self-contact
physics/curtain_coupling.py              two-way curtain-backpack coupling
physics/planar_rigid.py                  planar rigid backpack (x, z, pitch)
physics/simulate_case.py                 case driver, timed continuation
appearance/render_scene.py               scene assembly, state replay, render, encoding, replay audit
appearance/scene_environment.py          scanner, belt and station geometry
appearance/checkpoint_details.py, detail_refinement.py, monitor_upgrade.py, concourse_return.py, outfeed.py, station_details.py
                                         station, scanner, monitor and outfeed detail modules used by scene_environment.py
appearance/realism.py                    look (materials, luminaires, compositor)
appearance/audit_grounding.py            saved-scene support check (--grounding-audit)
appearance/audit_scene_reuse.py          outfeed planes against the native support profile
tools/export_ground_truth.py             per-frame ground truth of the suite cases (--check recomputes)
tools/publish_suite.py                   assembles a new suite from render outputs
tools/encode_case.py                     encodes frames rendered on a machine without ffmpeg
tools/worker_guard.py                    Blender launch on a checked idle GPU with a lease
```

`PCVE_SOURCE` / `PCVE_EDITS` in the builder hold each case's DSL, parameter change, native case id and the bilingual
vague/quantitative prompts; the edit prompts are the output of the shared `make_prompts` with `edit_vocab.VOCAB`.
`--export-prompts` writes them into a suite. The friction edit is phrased as a property of the backpack (display name
"friction coefficient" in `edit_vocab.py`); the physics sets the belt-backpack coefficient `belt_bag_friction`. The
quantitative source prompt carries the scene numbers (belt speed and height, backpack size, mass, start offset and
speed, curtain strips and modulus, chute and deck lengths). `accepted_states` is the name of the stored native-state
set, a configuration key recorded in the published data.

## Limitations

- Material and friction values are effective, uncalibrated parameters.
- The native states were solved on the CPU of other Linux machines and rendered on RTX 3090 and RTX A6000 GPUs; a solve
  on another Linux machine is not proven bit-identical to the published states.
