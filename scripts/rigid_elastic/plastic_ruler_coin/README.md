# plastic_ruler_coin

At the edge of a desk a hardcover book holds a clear plastic ruler down, with 140 mm of the ruler sticking out past
the edge. A coin is released from rest 50 mm above the overhanging part, hits it at frame 4, bounces and settles
while the ruler bends and rings down. This is a rigid–elastic scene: rigid coins against a thin elastic strip. The
source video is 4 s, 24 fps, 96 frames, 1280×720; video frame f is the native state at t = (f - 1)/24 s, with no
retiming or interpolation.

## Scene

- Ruler: clear cast acrylic, 317.5 × 31 × 1.6 mm, 177.5 mm clamped under a 1.6 kg book and 140 mm free, density
  1200 kg/m^3; IOR 1.49 with a faint cyan body tint, a 2 mm drawing bevel and a printed black millimetre scale
  0–30 cm with numerals only.
- Coin: plain cupro-nickel disc, radius 11.625 mm, thickness 2.33 mm, 7.5 g; centre 113 mm from the desk edge,
  bottom face 50 mm above the flat ruler, released from rest. Raised polished rim, toned field with fine scratches,
  reeded edge, no design.
- Book: 200 × 175 × 60 mm cloth-bound hardcover without a title, dark red dyed linen (`polyhaven/rough_linen` weave),
  boards with rubbed edges, an off-white text block with irregular sheet lines and a slightly concave fore-edge.
- Desk: lacquered oak veneer (`polyhaven/oak_veneer_01` at 8k over its real 1.83 m, 45 texels per cm, grain along the
  desk) with open pores as a fine bump (about 0.15 mm wide, 1–2 mm long) and light handling wear; 26 mm top with
  2.5 mm rounded edges, rails and legs.
- Floor: worn plank floor (`polyhaven/wood_floor_worn`, 4k over its real 2 m) 0.76 m below the desk top, defocused
  past the desk edge.
- Props: an unprinted yellow pencil and a speckled stoneware mug, both outside the swept volume of every case
  (`KEEPOUT` in `appearance/realism.py`).
- Light and background: only the HDR panorama `polyhaven/photo_studio_loft_hall` (4k, rotated -100 deg so its window
  wall is behind the desk on the camera's right, strength 1); no hidden lamps. No text other than the ruler's
  numerals and no external model.
- Camera: fixed, 0.70 m from the overhang at 23 deg elevation from the front right, 85 mm lens on a 36 mm sensor,
  f/22, focus on the ruler between the book and the coin. Each case records the camera it was rendered with in its
  camera.json.
- Render: Blender 4.3.2 Cycles, 512 samples, adaptive threshold 0.006, OpenImageDenoise (albedo + normal, accurate
  prefilter), indirect clamp 4, bounces 12 (diffuse 4, glossy 6, transmission 12), fixed seed, AgX Medium High
  Contrast at -0.4 EV, mild vignette, no motion blur.
- `appearance/realism.py` builds the whole scene and moves only the cached states: the ruler rest vertices are bent
  along the cached centreline (x' = X(x) - sin(theta(x)) z, z' = Z(x) + cos(theta(x)) z; the clamped part is only
  shifted by the mid-plane height), and the coins sit at the cached x, z and pitch.

## Physics

- Solver (`physics/physics.py`, CPU, NumPy + SciPy + Numba): a planar, geometrically exact, inextensible Kirchhoff
  strip with theta(s) = B(s) q, 8 Galerkin modes from an 80-element Euler–Bernoulli reference, 121 quadrature
  stations and a configuration-dependent mass matrix, clamped at the desk edge.
- Coins are rigid cylinders with translation and pitch; penalty face contact (13 samples per face) with damping and
  regularised Coulomb friction; coin–coin contact for the added coin.
- Velocity Verlet with the dissipative force at half velocity, dt = 1/96000 s; states are stored at exactly i/24 s
  (97 states, the 4 s endpoint is a diagnostic).
- Baseline (`physics/scene_spec.json`): ruler E = 2.4 GPa, effective modal damping ratio 0.07; contact stiffness
  1.28 MN/m, contact damping ratio 0.12, friction 0.30; gravity 9.81 m/s^2. The book's footprint length (0.19 m,
  `diagnostics`) enters only the reported hold-down moment, never the dynamics.

## Validation

- Every frame of every published case passes the replay check against its solve (ruler vertex hash of all 96 frames;
  coin matrices within 1.4e-7). The coin never enters the ruler and every prop stays clear of the motion.
- Temporal stability at 480×270: on the book, the far desk and the floor the frame-to-frame mean change is at most
  0.05/255 and the per-pixel standard deviation over frames 49–96 (99th percentile) at most 0.17/255 in every case;
  the near desk next to the ruler changes by up to 2.6/255 only while the ruler swings, and `edit_delete_coin` is
  constant to 0.0002/255.
- All six videos decode fully: 1280×720, 24/1 fps, 96 frames, 4.000 s.
- Re-solved cases are compared array by array with the stored solves. On Linux
  (Python 3.10.19, NumPy 1.26.4, Numba 0.65.1) the mode basis from `scipy.linalg.eigh` differs from the stored solves
  (Python 3.10, NumPy 1.26.1, SciPy 1.15.3, Numba 0.68.0) by 2.3e-6, so the contact branch drifts:

| Native case | Largest centreline difference (m) | Largest coin-state difference (m) |
| --- | --- | --- |
| `delete_coin` | 7.8e-9 | 0 |
| `source` | 8.4e-5 | 8.3e-5 |
| `ruler_modulus_x025` | 3.3e-5 | 2.4e-5 |
| `ruler_modulus_x8` | 8.5e-4 | 5.5e-4 |
| `coin_mass_x02` | 3.0e-5 | 2.3e-3 |
| `add_second_coin` | 2.6e-3 | 6.3e-3 |

## Cases

Native case ids are the case directory names without the `edit_` prefix (`coin_mass_x02`, ..., `add_second_coin`).

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | coin 7.5 g, ruler E = 2.4 GPa |
| `edit_coin_mass_x02` | `SET coin.mass TIMES 0.2` | coin mass 7.5 -> 1.5 g |
| `edit_ruler_modulus_x025` | `SET ruler.young_modulus TIMES 0.25` | ruler E 2.4 -> 0.6 GPa |
| `edit_ruler_modulus_x8` | `SET ruler.young_modulus TIMES 8` | ruler E 2.4 -> 19.2 GPa |
| `edit_delete_coin` | `DELETE coin` | no coin |
| `edit_add_second_coin` | `ADD second_coin BETWEEN book_edge AND ruler_end AT MIDPOINT` | an identical 7.5 g coin lying on the ruler, centre (0.068, 0, 0.762765) m |

All edits apply from frame 1. The ADD endpoints `book_edge` (the book's front edge where the ruler comes out,
(0, 0, 0.7616) m) and `ruler_end` (the free end of the ruler, (0.140, 0, 0.7608) m) are display-only anchors in
`edit_vocab.py`; their midpoint is 0.25 cm from the added coin's centre. The solver runs the native statement
`ADD second_coin AT PRESET resting_on_ruler`, kept in the edit's `native_edit_dsl` field and in
`physics/scene_spec.json`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `scenes/plastic_ruler_coin` | mixed (19 derived, 4 url, 5 manual) | stored native solves `accepted/physics/<case>/` and the look textures |
| `polyhaven/photo_studio_loft_hall` | url | HDR panorama, the only light |
| `polyhaven/oak_veneer_01` | mixed (5 url, 1 derived) | desk veneer |
| `polyhaven/wood_floor_worn` | url | floor |
| `polyhaven/rough_linen` | mixed (10 url, 1 manual, 4 derived) | book cloth weave |

```bash
python3 scripts/download_assets.py --scene plastic_ruler_coin
python3 scripts/download_assets.py --scene plastic_ruler_coin --check
```

## Requirements

- Python: `.venv-rigid-elastic` (NumPy, SciPy, Numba) for solves, renders and the tools; the solver runs on the CPU.
  The Numba kernel cache is created in `.runtime/plastic_ruler_coin/numba_cache` on the first solve.
- Blender 4.3.2 (`tools/blender-4.3.2-linux-x64/blender`, else the shared Blender lookup; `--blender-bin` overrides).
- Rendering: one NVIDIA GPU (`--device gpu`, Cycles OptiX/CUDA) or the CPU (`--device cpu`); all frames of one case
  use the same device and settings.
- ffmpeg and ffprobe on PATH for encoding and publishing.

## Commands

```bash
PY=.venv-rigid-elastic/bin/python
S=scripts/rigid_elastic/plastic_ruler_coin

# verify the stored solves, the stored delivery and the published suite
$PY $S/build_pcve_plastic_ruler_coin.py --stage verify
$PY $S/build_pcve_plastic_ruler_coin.py --list-edits
$PY $S/build_pcve_plastic_ruler_coin.py --show-prompts add_second_coin

# solve one case (default output renders/plastic_ruler_coin/rebuild/physics/<case>)
$PY $S/simulate_plastic_ruler_coin.py --case source

# render one case on a GPU, or a few frames on the CPU (default output renders/plastic_ruler_coin/rebuild/realism/<case>)
$PY $S/render_plastic_ruler_coin.py --case source --device gpu --gpu-uuid <GPU UUID>
$PY $S/render_plastic_ruler_coin.py --case source --device cpu --cpu-threads 48 --frames 1 4
$PY $S/render_plastic_ruler_coin.py --case source --cache-dir renders/plastic_ruler_coin/rebuild/physics/source

# assemble a new suite from finished renders, then write its ground truth
$PY $S/tools/publish_suite.py --native renders/plastic_ruler_coin/rebuild
$PY $S/tools/export_ground_truth.py --suite renders/plastic_ruler_coin/rebuild/suite_staging
```

- The render entry reads the stored solve of the case unless `--cache-dir` names a new one. `--out-root DIR` moves
  outputs under `DIR`; outputs may not be written into `scripts/`, the assets, the stored delivery or the published
  suite.
- `--stage verify` re-hashes the files pinned by the six `artifact_manifest.json` files of the stored delivery,
  audits its edit policy, checks the six stored solves against `physics/scene_spec.json`, and checks the published
  suite (video hashes against `scene_manifest.json`, `suite_manifest.json` and `provenance.json`, 1280×720/24/96
  decode, prompts equal to the builder, ground-truth format and clock). `--stage package --out DIR` copies the
  verified published suite.
- `tools/publish_suite.py --native DIR` replay-checks every case (`tools/verify_replay.py`), encodes missing videos
  (libx264 crf 16 yuv420p, 24 fps) and assembles `DIR/suite_staging`. `--publish` checks that every case's ground
  truth is `pcve_ground_truth/1`, moves the published suite to `archive/pcve_suites/<suite>_before_<native folder
  name>/` and puts the staging folder in its place, keeping each case's `standardization`
  provenance records; `--update-scene-manifest` then records its videos in `scene_manifest.json`.
- `--export-prompts [--dry-run]` writes the builder's prompts into a suite (by default `renders/plastic_ruler_coin/suite_build/pcve_plastic_ruler_coin_suite/`; the published suite only
  when its path is given with `--out-root`).

## Outputs

- Solves: `renders/plastic_ruler_coin/rebuild/physics/<case>/` (`simulation.npz`, `simulation_config.json`,
  `simulation_report.json`).
- Renders: `renders/plastic_ruler_coin/rebuild/realism/<case>/` (frames, video, camera, replay receipts and audit,
  ruler render binding, provenance, render log).
- New suites: `<native folder>/suite_staging/`.
- The published suite is `renders/pcve_suites/pcve_plastic_ruler_coin_suite/` (pointer in `scene_manifest.json`
  `canonical_suites`); nothing writes it by default.
- Ground truth (`pcve_ground_truth/1`): the coins are rigid bodies with the recorded body centre and the nearest
  rotation; the ruler is a deformable body with its strip-surface centroid and bounding-box dimensions. The record
  comes from the stored solve (97 states at t = i/24 s, video frame f = state f - 1) and the camera the video was
  rendered with, converted without resampling; static scenery that no edit names is left out.

## Code layout

- `build_pcve_plastic_ruler_coin.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`, equal to the published
  `prompts.json`; edit texts are `pcve_edit_dsl.make_prompts` output for `edit_vocab.py`); `--stage verify|package`.
- `simulate_plastic_ruler_coin.py`: solves one case with `physics/physics.py`.
- `render_plastic_ruler_coin.py`: renders one case with `appearance/realism.py` in Blender.
- `edit_vocab.py`: DSL vocabulary and the display anchors of the ADD.
- `scene_paths.py`: every location (stored solves, stored delivery, runtime, outputs, Blender and Python runtimes).
- `physics/physics.py`: strip–coin solver.
- `physics/vocabulary.py`: resolves the five edits with the shared DSL and policy.
- `physics/export_surface.py`: reconstructs the strip surface from a solve.
- `physics/scene_spec.json`: baseline, solver settings and cases.
- `appearance/realism.py`: Blender scene, look and replay of the cached states.
- `tools/verify_replay.py`: checks rendered frames against the cache.
- `tools/export_ground_truth.py`: writes per-case ground truth through `scripts/pcve_ground_truth.py`.
- `tools/publish_suite.py`: encodes renders and assembles a suite.
- Stored data read by the code: solves in `assets/scenes/plastic_ruler_coin/accepted/physics/<case>/`, delivery records
  in `renders/plastic_ruler_coin/accepted/`.

## Limitations

- Material, contact and damping values are nominal, not calibrated against a physical ruler.
- Re-solving on another platform changes the contact branch (table in Validation), so the stored solves are the
  reproduction inputs.
- The ruler shape is stored at 24 Hz only, so the renders have no motion blur.
- The stored solves were computed on Windows and the published videos were rendered on another Linux GPU machine
  (one GPU per case, OptiX); bitwise reproduction elsewhere is not verified.
- The frames of the published videos are not kept; the published suite holds the videos.
