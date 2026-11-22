# phone_sofa_drop

A 187 g phone is released from rest above the middle seat cushion of a living-room sofa, falls onto it, sinks into the
foam and bounces until it rests. The scene is rigid–elastic: a rigid phone in IPC contact with a viscoelastic FEM
cushion; recorded motion comes from the native solve and no pose or trajectory is authored. The source video is 4 s at
24 fps (96 frames, 1280×720): frame f shows physical time t = (f - 1)/24, the solver's 240 Hz state 10 (f - 1). The
case number 04 is kept in `entrypoints.json` (`case_number`).

## Scene

- Phone: 187 g, 70.6 x 146.6 x 8.25 mm, released with its centre at (0, -0.18, 0.7586) m, its lowest corner 0.258 m
  above the cushion top. Render model without logo or lock-screen picture (back-glass and screen-off materials), satin
  back glass with a light coat; the camera block is a plain dual-camera module (a vertical rounded capsule,
  19 x 46.5 mm, holding two lens assemblies in one column, with a small flash beside it). Size, mass and collision proxy
  are those of the solver.
- Middle cushion: 0.773 x 0.959 x 0.234 m foam block; the rendered cushion is a high-resolution sculpt carried by the
  solver's linear tetrahedra (about 2.2 cm) through a fixed tetrahedral embedding. The upholstery keeps the packed
  scene's woven-fabric PBR textures.
- Other objects: the sofa with its upholstered wooden deck, a mug in plain glazed ceramic.
- Room: closed with a ceiling (plain paint), a right wall and a front wall; walls in painted plaster
  (`painted_plaster_wall`, 2k, box-projected in world space, 2 m tile, warm tint).
- Light: daylight enters only through the left window: the `kloofendal_48d_partly_cloudy_puresky` sky (2k, strength 1)
  seen through the window and a sun lamp (4 W/m², 1.5 deg disc, slightly warm) shining in through it, so the window
  frame and the falling phone cast shadows on the sofa. A 3.1 x 1.9 m light portal fills the window opening (it adds no
  light).
- Added pillow (ADD case): `waffle_pique_cotton` (1k) on the pillow's own UVs, dyed a muted blue-grey, with the scanned
  weave normal, a fine irregular crumple bump on top (shading only, in UV space so it stays on the cloth while it
  deforms) and slight tonal mottling; the model's own seam and folds are kept.
- Cushion at the contact (render only, `appearance/cushion_smoothing.py`, `cushion_render_*` in
  `appearance/appearance.json`): every shape key gets (1) a Laplacian low-pass of its displacement from the settled
  state, only within 6 cm of the phone's outline (20 iterations, lambda 0.5, smooth falloff), and (2) a contact
  projection that keeps the render surface (a few millimetres above the solver surface) out of the phone body. Measured
  over all 961 states: largest crease angle near the phone 14.3 deg (`source`), 20.6 deg (`edit_soft_e_div2`); deepest
  dent 42.0 mm (`source`), 56.9 mm (`edit_soft_e_div2`), 175.6 mm (`edit_heavy_phone`); largest render-surface change
  2.7 / 3.6 / 6.7 mm; no render surface inside the phone. Per-case numbers are in each case's scene_report.json
  (`cushion_render_fix`). Solver caches and ground truth are not touched.
- Camera: the fixed camera of the packed scenes, 52 mm on a 36 mm sensor, shift 0, identical in all six cases.
- Render (`appearance/realism_look.py` with `appearance/appearance.json`; the look refuses to run if a simulated body or
  the camera would move): Cycles 256 samples (adaptive 0.01), OpenImageDenoise with albedo/normal (accurate
  prefilter), fixed seed 17, indirect clamp 10, filter glossy 0.5, caustics off, persistent data off, motion blur with a
  0.08-frame shutter (1/300 s), AgX Base Contrast, exposure +1, mild lens vignette (0.12) in the compositor, no
  per-frame grain; GPU frames render with OptiX.

## Physics

- IPC cases: libuipc 0.0.28 on CUDA, BDF1, dt = 1/1200 s, gravity 5 m/s², fixed contact stiffness. The phone is an ABD
  rigid body (contact friction 0.5); the cushion is a Stable Neo-Hookean tetrahedral FEM solid with Newton-coupled
  Kelvin-Voigt viscosity (E = 1000 Pa, nu = 0.15, 35 kg/m³). Every case starts from its own settled equilibrium.
- Removed-cushion case: a PyBullet 6-DoF rigid solve of the phone on the upholstered wooden deck (4800 Hz, restitution
  0.4, friction 0.35).
- Added pillow: 0.32 kg FEM pillow, 0.38 x 0.34 x 0.16 m, E = 1800 Pa, nu = 0.1, 30 kg/m³, contact friction 0.8, lying on
  the cushion under the phone. The solver runs the native statement `ADD landing_pillow AT PRESET middle_seat`
  (`native_edit_dsl` of the catalog entry).
- Parameters: `scene_spec.json` holds the baseline, each case's override and its native DSL; `edit_vocab.py` maps the
  DSL onto them (`resolved_edit()` checks that the two agree).
- 0-4 s caches: every case was re-run from t = 0 to 4 s with its original solver producers, changing only the duration
  guard (3 s -> 4 s; for `remove_cushion` also the 30 Hz sample-count check 91 -> 121 and the length of the empty per-time
  template containers). Material, contact, integrator, step, initial state and every other setting are those of the
  0-3 s reference run. The producers and the inputs they read are not part of this repository; the registered 4 s
  caches are the reproduction inputs.
- Retiming to the video clock: `appearance/retime_packed_scene.py` rebuilds the packed scene's animation from the 4 s
  cache at its 240 Hz state rate (absolute linear shape keys driven by eval_time, linear phone location/quaternion keys).
  `tools/match_embedding_order.py` re-orders an embedding's rows to a packed scene's vertex order (no fitting; rows must
  match to 1e-6 m, then all 721 stored 0-3 s shape keys must agree).

## Validation

- Over the first 3 s the 4 s caches agree with the 0-3 s reference caches:

  | case | phone transform, max abs diff | cushion positions |
  |---|---|---|
  | `remove_cushion` | bit-identical | - |
  | `added_pillow` | 1.7e-8 | <= 1.2e-5 m |
  | `soft_e_div2` | 4.6e-6 | <= 1.2e-5 m |
  | `source` | 1.1e-5 | <= 1.2e-5 m |
  | `stiff_x100` | 3.2e-5 | <= 1.2e-5 m |
  | `heavy_phone` | 3.5e-5 | <= 1.2e-5 m |

- Scene build: before anything is changed, the cache states inside the 0-3 s window must agree with the shape keys and
  phone keys stored in the packed scene to 1e-4 m; after the rebuild every one of the 961 dense states is evaluated back
  from Blender and must match the cache to 5 um, and every frame f must sit on the native state t = (f - 1)/24.
- `--stage verify` of the builder checks every video against `scene_manifest.json`, the suite manifest and provenance
  (MP4 sample tables), the prompts against the builder catalog, the ground-truth frame count and clock, and the
  registered native cache behind the ground truth; `--require-standard` also demands 1280×720 / 24 FPS / 96 frames /
  4.000 s. `simulate_phone_sofa_drop.py --stage verify` checks a case's registered cache against assets.json and its
  exact sample clock; `render_phone_sofa_drop.py --stage verify` checks a case's published video.
- Flicker check (frames reduced to 480x270): on the still parts of the picture the largest
  frame-to-frame change is below 0.5 grey levels on average; larger per-pixel changes are where the cushion itself moves
  (its front face and seams while it bounces); after 2 s the whole picture changes by < 0.08 levels on average in every
  case except `edit_heavy_phone`, whose phone is still bouncing.

## Cases

The builder's native case ids drop the `edit_` prefix of the published case directories (`edit_heavy_phone` is native
case `heavy_phone`).

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | baseline: phone 187 g; cushion E = 1000 Pa |
| `edit_remove_cushion` | `DELETE cushion` | middle cushion removed, upholstered deck kept |
| `edit_added_pillow` | `ADD landing_pillow BETWEEN phone AND cushion_below_phone AT 1/4 FROM cushion_below_phone` | 0.32 kg FEM pillow lying on the cushion under the phone |
| `edit_stiff_x100` | `SET cushion.young_modulus TIMES 100` | cushion E 100 kPa |
| `edit_soft_e_div2` | `SET cushion.young_modulus TIMES 0.5` | cushion E 500 Pa |
| `edit_heavy_phone` | `SET phone.mass TIMES 10` | phone mass 1.87 kg |

The ADD line is the phone's drop line, from the phone's centre at release down to the anchor `cushion_below_phone`: the
point of the middle cushion's top surface on that line, (0, -0.18, 0.4727) m at t = 0 in the source (highest cache
surface vertex within 1 cm of the line). The anchor is a display name in `edit_vocab.PROMPT_OBJECTS`, not part of
`VOCAB` or `editable_objects`. The quarter point from the anchor, (0, -0.18, 0.5442) m, is 5.5 mm from the pillow centre
at frame 1 ((0.0016, -0.1810, 0.5390) m in the `edit_added_pillow` ground truth).

## Assets

- `scenes/phone_sofa_drop` (derived, 46 files): 0-4 s solver caches `solves_4s_240hz/<case>/` (`simulation_dense.npz`
  240 Hz, 961 states; `simulation.npz` 30 Hz, 121 states) the videos are rendered from, 0-3 s reference caches
  `solves_3s_30hz/<case>/`, packed Blender scenes `packed/<case>/` (objects, camera, cushion sculpt, materials), cushion
  embeddings `embedding/<case>/`.
- `polyhaven/painted_plaster_wall` (url): walls.
- `polyhaven/kloofendal_48d_partly_cloudy_puresky` (url): sky through the window.
- `polyhaven/waffle_pique_cotton` (url): added pillow fabric.

```bash
python3 scripts/download_assets.py --scene phone_sofa_drop
python3 scripts/download_assets.py --scene phone_sofa_drop --check
```

`PCVE_ASSETS_DIR` moves the asset root.

## Requirements

- `python3` (stdlib) for verify and package; `ffmpeg`/`ffprobe` on PATH.
- A numpy Python (`.venv-rigid-elastic/bin/python` when present) for ground truth.
- Blender 4.3.2 (`tools/blender-4.3.2-linux-x64/blender`, `$BLENDER` or `--blender-bin`).

## Commands

```bash
# verification and catalog
python3 scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py --stage verify --require-standard
python3 scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py --list-cases
python3 scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py --list-edits
python3 scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py --show-prompts added_pillow
python3 scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py --export-prompts \
    --out-root renders/pcve_suites/pcve_phone_sofa_drop_suite --dry-run

# native caches
python3 scripts/rigid_elastic/phone_sofa_drop/simulate_phone_sofa_drop.py --case heavy_phone --stage verify --window 4s \
    --out renders/phone_sofa_drop/<run>/cache/heavy_phone

# scene build and frames
python3 scripts/rigid_elastic/phone_sofa_drop/render_phone_sofa_drop.py --case source --stage scene \
    --out renders/phone_sofa_drop/<run>/render
python3 scripts/rigid_elastic/phone_sofa_drop/render_phone_sofa_drop.py --case source --stage frames --frames 1 2 3 \
    --out renders/phone_sofa_drop/<run>/render --gpu <GPU>
python3 scripts/rigid_elastic/phone_sofa_drop/render_phone_sofa_drop.py --case source --stage verify

# a new suite from rendered frames, and ground truth
python3 scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py --stage package \
    --render-root renders/phone_sofa_drop/<run>/render --out renders/phone_sofa_drop/<run>/pcve_phone_sofa_drop_suite
.venv-rigid-elastic/bin/python scripts/rigid_elastic/phone_sofa_drop/tools/export_ground_truth.py --case source \
    --out renders/phone_sofa_drop/<run>/source_ground_truth.json
```

`--window 3s` selects the 0-3 s reference cache.

## Outputs

- `render_phone_sofa_drop.py` writes `<out>/<case>/scene.blend`, scene_report.json, `frames/` and per-worker reports;
  without `--out` it writes to `renders/phone_sofa_drop/render/`, which is also the default `--render-root` of
  `--stage package`. The frames of the published videos are not kept.
- `--stage package` (`tools/suite.py`) needs all six cases and a suite folder that does not exist yet (default
  `--out`: `renders/phone_sofa_drop/suite_build/pcve_phone_sofa_drop_suite/`). It refuses a case whose frames
  come from more than one device, machine or sample setting or differ from their worker report, encodes (libx264, preset
  slow, crf 16, yuv420p, 24 fps, faststart), checks each video is 1280×720 / 24 FPS / 96 frames / 4.000 s, writes the
  suite formats (prompts, provenance, video validation, suite manifest) and ground truth (`pcve_ground_truth/1`) and
  points `scene_manifest.json` at the new suite. It does not copy the published cases'
  `standardization` provenance records.
- Published suite: `renders/pcve_suites/pcve_phone_sofa_drop_suite/`; `scene_manifest.json` (`canonical_suites`)
  records every video's sha256.
- Ground truth (`tools/export_ground_truth.py --case CASE --out FILE`, `pcve_ground_truth/1`, through the shared module
  `scripts/pcve_ground_truth.py`): fixed camera (52 mm on a 36 mm sensor, shift 0), per frame the phone pose from the
  solver (the recorded body centre and the nearest rotation; the same matrix Blender plays back, with its velocities)
  and, for the deformable cushion and pillow, the centroid and bounding-box dimensions of their solver surface vertices
  with the state index into the cache. Nothing is fitted or resampled; static scenery that no edit names is left out;
  the ground truth describes the solver surface. `--clock 4s` (default) is the published clock; `--clock 3s` writes the
  native 30 FPS record (frames 1-91) of the 0-3 s reference caches, a clock the `pcve_ground_truth/1` layout cannot
  represent.

## Code layout

```
simulate_phone_sofa_drop.py          --stage verify checks/exports a registered cache
render_phone_sofa_drop.py            --stage scene | frames | all builds and renders a case; --stage verify checks its published video
build_pcve_phone_sofa_drop.py        edit catalog (PCVE_SOURCE / PCVE_EDITS); --stage verify | package
edit_vocab.py                        DSL vocabulary, display anchors (PROMPT_OBJECTS), resolved_edit()
scene_spec.json                      baseline parameters, per-case overrides and native DSL
scene_manifest.json                  published suite pointer (canonical_suites) and video hashes
entrypoints.json                     unified entry declaration
appearance/retime_packed_scene.py    Blender: rebuilds a packed scene's animation on the 24 FPS clock, applies the look, saves
appearance/realism_look.py           look (materials, closed room, daylight through the window, render settings)
appearance/appearance.json           numbers of the look
appearance/cushion_smoothing.py      render-only cushion smoothing near the phone and contact projection
appearance/render_frames.py          Blender: renders frames of a saved scene and writes a per-worker report
tools/export_ground_truth.py         pcve_ground_truth/1 from the solver cache
tools/suite.py                       package / verify of the suite
tools/scene_common.py                paths, registered inputs, cache clock checks
tools/match_embedding_order.py       Blender: re-orders the cushion embedding to a packed scene's vertex order
```

`PCVE_SOURCE` / `PCVE_EDITS` in the builder equal the published `cases/<case>/prompts.json`; the edit texts are the
output of `pcve_edit_dsl.make_prompts` for `edit_vocab.py`. Objects are named as they look ("the phone", "the middle sofa
cushion", "a small blue-grey pillow"); the source quantitative prompt states gravity 5 m/s² because that is the solver's
setting. `--export-prompts` writes them into a suite (by default `renders/phone_sofa_drop/suite_build/pcve_phone_sofa_drop_suite/`; the published suite only
  when its path is given with `--out-root`).

## Limitations

- Gravity in the solves is 5 m/s².
- The 4 s caches cannot be re-solved from this repository: the original solver producers and the inputs they read are
  not included; the registered 4 s caches are the reproduction inputs.
- All 96 frames of a published case were rendered on one machine and one GPU model with the settings stored in the
  scene, on other Linux GPU machines; determinism elsewhere has not been verified.
- The cushion surface in the video is smoothed near the phone for rendering; the ground truth follows the solver
  surface.
