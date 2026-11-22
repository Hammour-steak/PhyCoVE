# spring_car_collision

A precompressed steel coil spring launches a toy car that rests against the spring's pusher plate; the car
rolls along the floor of a living room and runs into a free wooden block. The scene is a rigid–elastic
interaction (rigid car and blocks, elastic spring). Each source video is 4 s at 24 fps (96 frames,
1280×720), played at normal speed: video frame f shows the solver state at t = (f-1)/24 s.

## Scene

- Spring launcher: steel compression spring, free length 0.22 m, mean coil diameter 30 mm, wire 1.2 mm,
  E = 205.4 GPa (axial rate 47.4 N/m), initially compressed by 60 mm; it drives a 12 g pusher plate on a static
  launcher frame without engraved text.
- Toy car: a die-cast toy coupe modelled in `appearance/car_model.py` (no external asset), 0.230 × 0.110 ×
  0.0785 m, 0.3 kg, four wheels of radius 24.2 mm and width 16.6 mm. Smooth lofted body (Catmull-Clark level 3),
  smoked-plastic window openings, cut wheel arches, a black front intake, flush lamp lenses, blue enamel with
  clear coat, chromed five-hole rims, black tyres and steel axles; no badge, number, lettering or face. At rest
  its chassis origin is at x = -0.382 m (nose at x = -0.267 m), touching the plate at the middle of its rear
  bumper.
- Wooden block: 0.080 × 0.085 × 0.055 m, 0.14 kg, near face at x = 0.240 m, textured with a fine-grained wood
  scan.
- Room: the track lies on the oak strip floor (`wood_floor`, 1.7 m scan, satin lacquer) of a closed living room,
  4.4 × 6.0 × 2.6 m; the physical plane z = 0 is the floor. Warm white plaster walls and ceiling
  (`painted_plaster_wall`) with skirting boards. Along the far wall, 2.6 m behind the track: a walnut sideboard
  with rattan doors (`modern_wooden_cabinet`), a potted plant (`potted_plant_02`) and a wicker basket
  (`wicker_basket_02`) on the floor, a vase (`ceramic_vase_04`), a wooden bowl (`wooden_bowl_02`) and a succulent
  (`potted_plant_04`) on the sideboard. Every prop is real size, stands on its surface and stays outside the swept
  volume of all six cases plus 2 cm (`MOTION_KEEPOUT` in `appearance/look.py`).
- Light: daylight only, through two out-of-frame windows. A 1.9 × 1.95 m window in the left wall admits a
  0.53° afternoon sun lamp (energy 1.7) that throws a patch across the track, so launcher, car and block cast
  sharp shadows to the back right; a 1.8 × 1.4 m window behind the camera lets sky light onto the far wall and
  floor. Sky `kloofendal_48d_partly_cloudy_puresky`, strength 7. No hidden lights.
- Camera (`appearance/look.py` `CAMERA`, same for all cases): 50 mm lens on a 36 mm sensor, f/4, on a low tripod
  2.4 m in front of the track and 0.42 m above the floor, looking 5.2° down. It frames x = -0.77 to 0.96 m on the
  track, so the whole motion of every case (-0.71 to 0.90 m) stays in view.
- Rendering: Blender 4.3.2 Cycles, 384 samples, adaptive threshold 0.005, OpenImageDenoise (albedo + normal),
  indirect clamp 8, bounces 12 (diffuse 5, glossy 5, transmission 10), motion blur with a 0.25-frame shutter
  between consecutive solver samples, persistent data off, fixed seed 17. AgX view transform, Medium High
  Contrast look, exposure 0.85 EV (`look.EXPOSURE`). Appearance code changes no motion, size or keyed pose.

## Physics

- Solver: MuJoCo 3.3.7 rigid bodies on the CPU (`physics/physics_model.py`).
- Car: collides through the convex hull of its body and rolls on four separate wheel cylinders with bearing
  damping and rolling resistance. The body is symmetric, so the car keeps to the track centre line (y = 0).
- Spring: reduced axial model, k = G d^4 / (8 D^3 n) from wire geometry and Young's modulus, preload 60 mm,
  damping and guide friction, driving the 12 g pusher plate.
- Blocks: free boxes on the floor plane z = 0.
- Initial state: every case starts from the same frozen at-rest state
  (`assets/scenes/spring_car_collision/toy_car/source_initial_state.json`, recorded with its sha256 in every solve). The
  holding latch is removed at t = 0.
- Time step (`scene_spec.json` `production_dt_s_by_case`): 1/48000 s for `source`, `remove_block` and
  `stiffer_spring`; 1/12000 s for `remove_spring`, `heavier_block` and `add_block`. States are sampled at 24 Hz for
  4 s. The solves are deterministic on the CPU (two runs byte-identical).
- The ADD edit runs in the solver as `ADD obstacle_block AT PRESET approach` (`native_edit_dsl` in the builder
  catalog, `derived_interventions` in `scene_spec.json`); the 5/6 point of the DSL line is the added block's
  centre by construction.

## Measured motion

From the solves of the published cases (the published ground truth agrees); frames are video frames.

| Case | Block first moves (frame) | Car speed at contact (m/s) | Block displacement (mm) | Car stops at x (m) |
|---|---|---|---|---|
| `source` | 23 | 0.519 | 64.7 | 0.190 |
| `edit_stiffer_spring` | 13 | 1.120 | 301.6 | 0.427 |
| `edit_heavier_block` | 23 | 0.520 | 14.7 | 0.140 |
| `edit_add_block` (added block hit at frame 18) | 20 | 0.318 | 18.8 (added block 49.3) | 0.064 |
| `edit_remove_block` | - | - | - | 0.764 (at rest from about frame 82) |
| `edit_remove_spring` | - | - | - | stays at rest at -0.382 |

Peak launch speed is 0.680 m/s (1.206 m/s with the stiffer spring). In the source video the car meets the
block at frame 23 and everything is at rest from about frame 30; without the block the car rolls on and stays
in frame.

## Validation

- Every rendered frame passes the replay check: keyed poses and coil vertices read back from the evaluated scene
  match the solver cache within 4.8e-7 m.
- Over the still second half (source frames 40-96, edits 85-96, at 480×270) the far wall, sideboard and floor
  show no frame-to-frame change (99th-percentile per-pixel standard deviation 0.0 grey levels); the launcher area
  shows at most 0.8.
- All six published videos are 1280×720, 24/1 fps, 96 frames, 4.000 s (ffprobe).
- `--stage verify` checks the published suite against the solves in
  `assets/scenes/spring_car_collision/native_cases/`.

## Cases

Builder case ids drop the `edit_` prefix of the published case directories (`edit_add_block` is `add_block`).
Camera, lights and every other initial pose are shared; each edit changes only its own field.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | spring E = 205.4 GPa, compression 60 mm; car 0.3 kg; block 0.14 kg |
| `edit_remove_spring` | `DELETE spring` | spring and pusher absent; the static launcher frame stays |
| `edit_stiffer_spring` | `SET spring.young_modulus TIMES 3` | E = 616.2 GPa; coil geometry and Poisson ratio unchanged, so the axial rate also triples |
| `edit_remove_block` | `DELETE block` | no block |
| `edit_heavier_block` | `SET block.mass TIMES 3` | block 0.42 kg |
| `edit_add_block` | `ADD obstacle_block BETWEEN car AND block AT 5/6 FROM car` | second block 80 × 85 × 59.2 mm, 0.14 kg, centred at 5/6 of the line from the car root to the block centre |

## Assets

- `scenes/spring_car_collision/toy_car` (derived, 5 files): solver geometry of the toy car and the shared at-rest
  pose, written by `tools/make_car_geometry.py`.
- `scenes/spring_car_collision/native_cases` (derived, 102 files): solves of the six cases (trajectory.npz,
  scene_params.json, audits), read by `--stage verify` and the renderer.
- `scenes/spring_car_collision` (manual, 3 files): fine-grained wood scan on the blocks.
- `polyhaven/wood_floor` (8 url, 1 manual, 2 derived): floor.
- `polyhaven/painted_plaster_wall` (url): walls and ceiling.
- `polyhaven/kloofendal_48d_partly_cloudy_puresky` (url): sky.
- `polyhaven/modern_wooden_cabinet`, `polyhaven/potted_plant_02`, `polyhaven/ceramic_vase_04`,
  `polyhaven/wooden_bowl_02` (url): far-wall props.
- `polyhaven/wicker_basket_02` (5 url, 1 manual) and `polyhaven/potted_plant_04` (8 url, 3 derived): far-wall
  props.

```bash
python3 scripts/download_assets.py --scene spring_car_collision
python3 scripts/download_assets.py --scene spring_car_collision --check
```

`PCVE_ASSETS_DIR` moves the asset root.

## Requirements

- Python: `.venv-genesis-mpm-sph` (NumPy, SciPy) for the builder and the entries.
- Solver: MuJoCo 3.3.7 exactly, CPU only. When the current interpreter has another MuJoCo version, the simulate
  entry re-runs itself with `.runtime/spring_car_collision/deps` (MuJoCo 3.3.7, cp310) on `PYTHONPATH`, under
  `.venv-rigid-elastic/bin/python` when that environment exists.
- Rendering: Blender 4.3.2 (`tools/blender-4.3.2-linux-x64`, else `$BLENDER` or `PATH`) on an NVIDIA GPU with
  OptiX or CUDA, or on the CPU (`--device cpu`).
- ffmpeg with libx264 for `tools/publish_suite.py`.

## Commands

Run from the repository root.

```bash
PY=.venv-genesis-mpm-sph/bin/python
S=scripts/rigid_elastic/spring_car_collision

# Verify the published suite against the solves (verify is also the default stage)
$PY $S/build_pcve_spring_car_collision.py --stage verify

# Cases, edit catalog and prompts
$PY $S/build_pcve_spring_car_collision.py --list-cases
$PY $S/build_pcve_spring_car_collision.py --list-edits
$PY $S/build_pcve_spring_car_collision.py --show-prompts add_block

# Check physical definitions and inputs without integrating or writing
$PY $S/simulate_spring_car_collision.py --native-dry-run

# Solve cases into <out-root>/cases/<case>/
$PY $S/simulate_spring_car_collision.py --out-root renders/spring_car_collision/<run> --cases source add_block

# Render one case from its solve into <out-root>/<case>/
$PY $S/render_spring_car_collision.py --case source --out-root renders/spring_car_collision/<run> --device optix --gpu-index <GPU>
$PY $S/render_spring_car_collision.py --case source --out-root renders/spring_car_collision/<run> --device cpu --render-threads <N> --frames 1 48 96

# Encode a render root and assemble a suite in <native>/suite_staging
$PY $S/tools/publish_suite.py --native renders/spring_car_collision/<run>

# Ground truth of a suite folder (pcve_ground_truth/1)
$PY $S/tools/export_ground_truth.py --suite renders/spring_car_collision/<run>/suite_staging
```

`render_spring_car_collision.py --cache <trajectory.npz>` renders another solve (its scene_params.json beside it);
`--native-dry-run` on the render entry prints the Blender command. `tools/make_car_geometry.py` rewrites the toy
car's solver geometry and the shared at-rest pose in `assets/scenes/spring_car_collision/toy_car/`.

## Outputs

- The simulate entry writes `<out-root>/cases/<case>/` (trajectory.npz, scene_params.json, audits); default
  out-root `renders/spring_car_collision/simulate`.
- The render entry writes `<out-root>/<case>/frame_0001..0096.png`, `render_metadata.json` (camera, settings,
  asset and code hashes) and replay_audit.json; default out-root `renders/spring_car_collision/render`.
- `tools/publish_suite.py` encodes `frame_0001..0096.png` to `video.mp4` when it is missing (libx264, crf 16,
  yuv420p, bt709, 24 fps), checks that all render parts of a case share one device type, setting, code and
  solver cache, writes ground truth and assembles the suite in `<native>/suite_staging` (or `--staging DIR`).
- The published suite is `renders/pcve_suites/pcve_spring_car_collision_suite/` (pointer in
  `scene_manifest.json`). Only `tools/publish_suite.py --publish` (or `--stage publish --publish`) replaces it: it
  requires `pcve_ground_truth/1` ground truth for every case, moves the current suite to `archive/pcve_suites/`,
  repoints `scene_manifest.json` and carries each case's prompt history and other carried provenance records over.

## Code layout

- `build_pcve_spring_car_collision.py`: edit catalog (`PCVE_SOURCE` / `PCVE_EDITS`, equal to the published
  prompts.json); stages verify, simulate, render, publish.
- `simulate_spring_car_collision.py`: solves the selected cases.
- `render_spring_car_collision.py`: renders one case in Blender 4.3.2.
- `scene_config.py`: paths and runtimes (asset store, MuJoCo runtime, renders, suite, Blender).
- `edit_vocab.py`: edit DSL vocabulary; the edit prompts are `pcve_edit_dsl.make_prompts` output for it.
- `scene_spec.json`: baseline physics, the six cases and their time steps.
- `scene_manifest.json`: published suite pointer, solve hashes, data locations.
- `physics/physics_model.py`: MuJoCo model, release from the frozen at-rest state, 24 Hz sampling, audits.
- `appearance/render_native.py`: keys the 96 solver samples, checks every frame against the cache, renders.
- `appearance/assets_scene.py`: spring assembly, blocks and coil helix at solver size.
- `appearance/car_model.py`: toy car body, wheel pivots and solver geometry.
- `appearance/look.py`: room, daylight, camera and materials.
- `tools/make_car_geometry.py`: writes the toy car's solver geometry and the shared at-rest pose.
- `tools/export_ground_truth.py`: per-frame ground truth through `scripts/pcve_ground_truth.py`: car chassis,
  block and added block as rigid bodies (recorded body centre, nearest rotation), the spring as a deformable body
  (centre and dimensions of its coil bounding box), camera from render_metadata.json, no resampling; the static
  launcher frame is left out.
- `tools/publish_suite.py`: encodes a render root and assembles it as a suite.

## Limitations

- Contact, damping and rolling parameters are nominal values, not calibrated on a real toy.
- At close range a thin dark seam shows where the windscreen base meets the front wing and a faint highlight
  streak runs along the door; neither is visible from the fixed camera.
- The published cases were rendered with OptiX on NVIDIA RTX 3090 cards in three 32-frame parts (about 12.5 s
  per frame) on another Linux GPU machine; bitwise reproduction of the frames elsewhere is not verified.
