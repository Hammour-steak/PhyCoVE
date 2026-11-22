# spring_block_step

A spring launcher pushes a wooden block off a raised board: a latched, precompressed steel compression spring drives a
push plate that shoves the block along the board, the block leaves the board, lands on the bench and slides to rest.
This is a rigid–elastic scene: a rigid block driven by an elastic spring. The source video is 4 s, 24 fps, 96 frames,
1280×720, real time; frame i shows the native state at t = (i - 1)/24 s.

## Scene

- Block: 74 × 64 × 50 mm, 145 g, oil-finished walnut (`walnut_veneer_02` scan with end grain), resting on a
  450 × 270 × 25 mm birch plywood board with a machined edge, raised on two 40 mm risers (top 65 mm above the bench),
  its front face 251 mm from the board's front edge.
- Spring: captured steel compression spring, wire 1.65 mm, mean coil 38 mm, 20 active turns plus two
  closed-and-ground ends, 158 mm free seat length, 75 mm precompression, on a telescopic guide with a 2 mm push plate;
  rendered as a ground-end coil with guide parts. A latch holds the plate until t = 0.375 s.
- Bench: butcher-block maple top 1.80 × 0.76 m, 45 mm thick, of eighteen 42 mm glued strips
  (`polyhaven/white_maple_veneer`, per-strip tone, darkened like oiled, used maple) with wear in world coordinates
  (oil blotches, pale and grime-filled scratches in three directions, nicks and dents, two overlapping coffee-cup
  rings, sawdust in the back-left corner, along the back edge and round the board's feet); end grain on the strip
  ends; pine legs and rails (`coated_pine`), OSB lower shelf (`oriented_strand_board`). The top surface is the
  solver's z = 0.
- Room: garage corner with painted concrete-block walls (390 × 190 mm blocks in running bond, 10 mm joints 3.5 mm
  behind the face, face relief from `granular_concrete`, off-white masonry paint with roller stipple), concrete floor
  (`hangar_concrete_floor`), a glazed timber window in the left wall with a light portal; steel-frame shelving
  (`steel_frame_shelves_02`) with a painted toolbox (`metal_toolbox`) and a wicker basket (`wicker_basket_02`), a
  potted plant.
- Bench props, all outside every case's motion corridor (`KEEPOUT`) and low in front of it: wooden bowl
  (`wooden_bowl_02`, desaturated to oiled natural wood) at plan position (0.37, 0.31) m and a modelled roll of 48 mm
  crepe masking tape at (0.25, -0.31) m, the two ADD endpoints; claw hammer (`wooden_hammer_01`), screwdriver
  (`flathead_screwdriver`), pliers, adjustable wrench, a modelled carpenter's pencil and sawdust. No text objects are
  allowed in the scene.
- Light: daylight through the window only (sky `kloofendal_48d_partly_cloudy_puresky`, strength 1; sun lamp 0.53 deg,
  strength 4.5) plus a modelled 1.2 m ceiling LED batten over the bench (opal diffuser, 3500 K, emission 28).
- Camera: fixed side-front camera at (0.58, -1.64, 0.38) m aimed at (0.17, 0, 0.085) m, 58 mm lens, 36 mm sensor,
  f/5.6, focus at (0.12, 0, 0.06) m (`CAMERA`, `FOCUS` in `appearance/realism.py`).
- Render: Blender 4.3.2 Cycles, 256 samples, adaptive threshold 0.01, OpenImageDenoise (accurate prefilter), bounces
  10 (diffuse 6, glossy 4, transmission 6), indirect clamp 6, motion blur shutter 0.25 frame with persistent data off,
  AgX Base Contrast, exposure +0.3, mild vignette (0.16), 1280×720, 24 fps. The look never moves a body, changes a
  collision shape or reads a solver parameter other than for placement checks; every keyed body is checked against
  the states at every rendered frame.

## Physics

- Native PyBullet rigid boxes on the CPU, dt = 1/192000 s, 160 solver iterations, cone friction; no launch velocity,
  keyframe, pose correction or terminal snap.
- Spring: E = 200 GPa, nu = 0.30, k = G d^4 / (8 D^3 n) = 64.9 N/m; guide friction 0.12 N·s/m viscous and 0.040 N dry.
- Friction: board–block 0.22, bench–block 0.24; PyBullet restitution input 0.22 (the landing is practically
  non-bouncing).
- States are saved at 240 Hz (961 samples) and at the 96 video instants t = i/24 s.
- In the source the block separates from the plate at 0.464 s, leaves the board at 0.703 s, lands on the bench at
  0.778 s (x = 0.230 m) and slides to rest at x = 0.309 m.

## Measured motion

From the registered states (the published ground truth agrees). The latch releases the plate at frame 10
(t = 0.375 s); the block first moves at frame 11 in every case with a spring.

| Case | Block at rest at x (m) | At rest from about frame | Note |
| --- | --- | --- | --- |
| `source` | 0.309 | 26 | lands on the bench at 0.778 s (x = 0.230 m) and slides about 8 cm |
| `edit_mass_half` | 0.592 | 30 | flies furthest |
| `edit_young_quarter` | -0.043 | 20 | stays on the board |
| `edit_friction_half` | 0.449 | 34 | slides further on the bench |
| `edit_remove_spring` | -0.158 | - | never moves |
| `edit_add_block` | 0.249 | 21 | strikes the second block, which slides 33 mm to x = 0.343 m |

## Validation

- A half-step run (1/384000 s) passes 5 mm / 5 deg gates in every case; `--stage validate-physics` passes all gates on
  the registered states.
- A re-solve of all six cases with pybullet 3.2.7 on Linux agrees with the registered states to <= 4.8 um in position
  and <= 1.3e-5 in quaternion components (`remove_spring` <= 6e-18 m); `resolved_physics.json` is identical.
- Every published video passes `pcve_media_contract.require_video` and a full ffprobe decode (1280×720, 24/1, 96
  frames, 4.000 s). Temporal stability at 480×270: once every body has stopped, the mean frame-to-frame change is
  0.002–0.011 grey levels of 255 (max 0.013) over the whole frame; the wall, toolbox, plant, bowl, tape roll and pliers
  regions are at most 0.011 on average.

## Cases

Native case ids are the case directory names without the `edit_` prefix.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | block 145 g, spring E = 200 GPa, bench friction 0.24 |
| `edit_mass_half` | `SET block.mass TIMES 0.5` | block 145 -> 72.5 g |
| `edit_young_quarter` | `SET spring.young_modulus TIMES 0.25` | spring E 200 -> 50 GPa (k = 16.2 N/m, same geometry and Poisson ratio) |
| `edit_friction_half` | `SET table.friction TIMES 0.5` | bench friction 0.24 -> 0.12 |
| `edit_remove_spring` | `DELETE spring` | spring, plate and moving guide absent (the backstop and fixed guide sleeve stay) |
| `edit_add_block` | `ADD obstacle BETWEEN bowl AND tape AT MIDPOINT` | a free 60 × 80 × 50 mm, 150 g block at rest at (0.31, 0, 0.025) m |

All edits apply from frame 1. The ADD endpoints `bowl` and `tape` are display-only anchors in `edit_vocab.py`
(`ADD_LINE_DSL`); their plan-view midpoint is the preset centre (0.31, 0) m, where the block comes to rest in the source
video. The solver runs the native statement `ADD obstacle AT PRESET landing`, kept in the catalog entry's
`native_edit_dsl`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `scenes/spring_block_step` | mixed (57 url, 5 manual, 3 derived) | look textures and models, scanned pliers, wrench and plant in `realism/` |
| `scenes/spring_block_step/native_states` | derived | registered native states per case |
| `polyhaven/white_maple_veneer` | url | bench top |
| `polyhaven/coated_pine` | mixed (5 url, 1 manual) | bench legs and rails |
| `polyhaven/oriented_strand_board` | url | lower shelf |
| `polyhaven/granular_concrete` | url | block-wall relief |
| `polyhaven/hangar_concrete_floor` | url | floor |
| `polyhaven/steel_frame_shelves_02` | url | shelving |
| `polyhaven/metal_toolbox` | url | toolbox |
| `polyhaven/wicker_basket_02` | mixed (5 url, 1 manual) | basket |
| `polyhaven/wooden_bowl_02` | url | bowl (ADD endpoint) |
| `polyhaven/wooden_hammer_01` | url | hammer |
| `polyhaven/flathead_screwdriver` | url | screwdriver |
| `polyhaven/kloofendal_48d_partly_cloudy_puresky` | url | sky |

```bash
python3 scripts/download_assets.py --scene spring_block_step
python3 scripts/download_assets.py --scene spring_block_step --check
```

## Requirements

- Solver: `.venv-rigid-elastic` (NumPy, pybullet), CPU. `.runtime/spring_block_step/pybullet/` keeps the pybullet
  3.2.5 build of the registered solves (same API).
- Rendering: Blender 4.3.2 (`tools/blender-4.3.2-linux-x64/blender` when present, else `pcve_assets.blender()`;
  `--blender-bin` overrides) on a GPU with OptiX or CUDA, or the CPU; every frame of a case must come from one device
  type with the same settings.
- FFmpeg from `PATH` or `PCVE_FFMPEG`. `--stage verify` needs no NumPy.

## Commands

```bash
S=scripts/rigid_elastic/spring_block_step

# native solve (+ half-step convergence run)
.venv-rigid-elastic/bin/python $S/simulate_spring_block_step.py --cases source --out renders/spring_block_step/resim --convergence

# compare a fresh solve with the registered states; numerical gates of the registered states
python3 $S/build_pcve_spring_block_step.py --stage compare-resim --rerun renders/spring_block_step/resim
python3 $S/build_pcve_spring_block_step.py --stage validate-physics

# render one case on a GPU, or two stills on the CPU
python3 $S/render_spring_block_step.py --case source --out renders/spring_block_step/<new folder>/render/source --gpu <GPU index or UUID>
python3 $S/render_spring_block_step.py --case source --out renders/spring_block_step/<new folder>/stills/source --device cpu --frames 1 20 --no-blend

# published suite: verify; prompts of a new suite (default renders/spring_block_step/suite_build/pcve_spring_block_step_suite)
python3 $S/build_pcve_spring_block_step.py --stage verify
python3 $S/build_pcve_spring_block_step.py --stage prompts
python3 $S/build_pcve_spring_block_step.py --export-prompts \
    --out-root renders/pcve_suites/pcve_spring_block_step_suite --dry-run

# encode new renders and build a new suite in a fresh folder
python3 $S/build_pcve_spring_block_step.py --stage encode
python3 $S/build_pcve_spring_block_step.py --stage publish --suite-root renders/spring_block_step/<new folder>/pcve_spring_block_step_suite
```

- All three entries accept the unified options (`--help`, `--describe`, `--dry-run`, `--out-root`, `--python`,
  `--blender`, `--gpu`, `--threads`). Nothing is written under `scripts/`.
- `--stage verify` checks, per case: video bytes = `scene_manifest.json` = `suite_manifest.json` = `provenance.json`,
  the media contract, `prompts.json` = the builder catalog (and the catalog = what `edit_vocab.py` derives), the
  registered states' hash and clock, `resolved_physics.json` = `scene_common.parameters(case)`, the ground truth
  (`pcve_ground_truth/1`, video length and clock), and that the render record of the video names the same states.
- `--stage prompts` checks the catalog and runs the shared prompt export. `--stage encode` writes each `video.mp4`
  from the 96 PNG frames (H.264, yuv420p, CRF 16, 24 fps, BT.709 tags). `--stage publish` builds a new suite
  (`tools/publish_suite.py build`, which never overwrites an existing suite) and verifies it; it does not copy the
  prompt history or the other provenance records of the published cases.

## Outputs

- Fresh solves: `renders/spring_block_step/resim/` (`<DIR>/cases/<case>/states.npz`); renders go to the `--out`
  folder under `renders/spring_block_step/` (96 PNG frames, `scene.blend` with relative texture paths, which holds the
  ground-truth camera, `render_report.json`, `video.mp4`).
- Solver reports (events, energy, penetration, half-step convergence):
  `renders/spring_block_step/physics_audit/pcve_spring_block_step_suite/cases/<case>/physics_audit.json`.
- Render records of the published videos: `renders/spring_block_step/accepted/render/<case>/render_report.json`.
  Neither the solver reports nor these render records are registered in `assets.json`.
- The published suite is `renders/pcve_suites/pcve_spring_block_step_suite/` (`scene_manifest.json` ->
  `canonical_suites`); `--stage verify` reads it by default and only `--export-prompts` with this path as `--out-root` writes it. `--stage prompts`
  and `--stage publish` write to `--suite-root`, by default
  `renders/spring_block_step/suite_build/pcve_spring_block_step_suite/`.
- Ground truth (`pcve_ground_truth/1`): block, push plate, obstacle and table as rigid bodies (recorded body centre and
  nearest rotation), the spring as a deformable body (centroid and bounding-box dimensions), from each case's
  registered states and the camera of its `scene.blend` (or the camera rebuilt from the render record), converted
  without resampling; static scenery that no edit names (board, risers) is left out.

## Code layout

- `build_pcve_spring_block_step.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`, equal to the published
  `prompts.json`; SET and DELETE prompts from the shared DSL renderer, ADD prompts from `edit_vocab.add_prompts()`);
  `--stage verify|prompts|validate-physics|compare-resim|encode|publish`.
- `simulate_spring_block_step.py`: runs `physics/simulate.py`.
- `render_spring_block_step.py`: renders one case through `tools/render_case.py`.
- `scene_common.py`: constants, baseline physics, cases, repository locations, `load_physics()`.
- `edit_vocab.py`: edit DSL vocabulary, ADD preset and its two on-screen endpoints, prompt wording.
- `scene_manifest.json`: published suite pointer, native locations, state and video hashes.
- `physics/simulate.py`: PyBullet solve of one or more cases (+ half-step convergence run).
- `appearance/base_scene.py`: metric helpers, board, guide parts, camera, render defaults.
- `appearance/render.py`: mechanism (ground-end coil, guides, walnut block, plywood board), keyed from the 240 Hz states.
- `appearance/realism.py`: published look and render entry of one case.
- `tools/render_case.py`: Blender launcher used by the render entry.
- `tools/export_ground_truth.py`: per-frame ground truth of one case (inside Blender) through
  `scripts/pcve_ground_truth.py`; `tools/publish_suite.py ground-truth --suite DIR` runs it for a suite.
- `tools/publish_suite.py`: `encode`, `build`, `prompts`, `ground-truth`.
- `tools/validate_physics.py`: numerical gates of the registered states and solver audits.
- `tools/compare_states.py`: array-by-array comparison of a fresh solve with the registered states.

## Limitations

- The landing is almost non-bouncing because of PyBullet's restitution model with input 0.22.
- The registered states were solved with pybullet 3.2.5; other builds agree to micrometres, not bitwise.
- The published results were computed on other Linux GPU machines (each case rendered wholly on one GPU with OptiX,
  15–17 min per case); bitwise reproduction elsewhere is not verified.
