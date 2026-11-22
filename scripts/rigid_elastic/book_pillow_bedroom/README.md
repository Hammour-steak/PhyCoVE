# book_pillow_bedroom

A blue hardcover book is released from rest above a bed and drops onto a soft pillow lying on a quilted
duvet; the pillow and bedding deform under the impact and the book comes to rest on them. This is a
rigid–elastic scene: the book is an affine rigid body and the pillow, quilt and mattress are FEM volumes,
coupled by IPC contact in one solve. The source video is 4 s, 24 fps, 96 frames, 1280×720; frame i is the
native state at t = (i − 1)/24 s.

## Scene

- Falling book: 0.24 × 0.17 × 0.036 m, 0.5 kg, released from rest with its lowest corner 0.30 m above the
  pillow (centre at 0.980 m).
- Bed: pillow on a quilted duvet over a 1.02 × 1.02 × 0.074 m mattress; the bedding is settled at rest
  before the recorded 4 s.
- Room (`appearance/realism_look.py`, appearance only; geometry, motion and camera are those of the kit
  scene and the caches): the back wall (bed head, inner face y = 1.22 m) plus a left wall (a corner strip
  at the frame edge), right and front walls and a ceiling 2.70 m high close the room. A 1.8 × 1.5 m window
  opening with a painted frame and one vertical mullion sits in the left wall out of frame. Walls use the
  `plastered_wall_04` scan, its own hue removed and painted warm white; white skirting.
- Light: daylight through that window only: a 5200 K sun lamp (elevation 40°, strength 3, 0.6° disc) and a
  Nishita sky (strength 1.0, no sun disc), plus a sunlit paved courtyard outside for ground bounce. No
  hidden lights.
- Bedding look: the quilt is washed linen (the `rough_linen` weave at its true 0.271 m tile, oatmeal) with
  slubs of about 3 mm × 5 cm in warp and weft (up to +22 % albedo and a bump), dye mottling and millimetre
  heathering; sheet, pillowcase and piping are white cotton (`stretch_poplin` at its true 0.286 m tile)
  with weaker slubs. Both get three layers of soft elongated wrinkles (about 5 cm, 1.6 cm and 6 mm; bump
  only), roughness 0.86–0.98, specular 0.22 and cloth sheen 0.55. The pillowcase has topstitching 5 mm
  outside its welt (a 1.2 mm groove with 2 mm stitches and 2 mm gaps), shown only on the flat faces of the
  case. Everything reads the rest-position attribute of the frozen cloth finish, so nothing swims on the
  deforming cloth; the simulated meshes are untouched.
- Headboard: `poly_wool_herringbone` fabric with 16 covered buttons, one per visible tuft above the
  mattress; each 20 mm button rests in the funnel mouth of its tuft with its face 0.5 mm clear of the
  fabric.
- Props: scanned models `side_table_01` (oak side table, 0.45 × 0.55 × 0.55 m, 24 mm from the hanging duvet
  at frames 1 and 96; the look refuses less than 10 mm), with `potted_plant_04` (succulent) and
  `ceramic_vase_04` (jug) on it, in the left part of the frame, far from the book's path.
- Books: plain cloth covers in blue and brown book cloth, no title or printed border.
- Camera: the fixed camera of the kit scene (52 mm lens, 36 mm sensor), unchanged by the look (the renderer
  checks it); no compositor vignette.
- Render (`render_settings` in `appearance/realism_look.py`): Blender 4.3.2 Cycles on CUDA, 512 samples,
  adaptive threshold 0.008 (minimum 64), bounces 12 (diffuse 6, glossy 4, transmission 6), indirect clamp
  8, OpenImageDenoise with albedo and normal (accurate prefilter), fixed seed 29. Motion blur with a
  0.25-frame shutter centred on the frame (persistent data off); the books are keyed linearly between the
  cached frame poses. AgX Medium High Contrast, exposure +1.7 EV, camera white balance 9000 K with tint +22.
  In source frame 1 the shaded white duvet measures RGB (114, 111, 109) and the wall above the headboard
  (132, 121, 110). Every frame of a case is rendered on one GPU with one look fingerprint.
- Encoding (`tools/publish_suite.py`): H.264 High, CRF 16, yuv420p, BT.709 limited range.

## Physics

- Solver: coupled FEM / affine-body / IPC solve at 600 Hz (solver step 1/600 s), one native sample per video
  frame; IPC barrier distance 0.4 mm.
- Bodies (baseline in `edit_vocab.py`):

| Body | Values |
|---|---|
| falling book | 0.24 × 0.17 × 0.036 m, 0.5 kg, affine body, contact friction 0.55 |
| pillow | Young's modulus 400 Pa, Poisson ratio 0.22, density 18 kg/m³, shear / bulk viscosity 18 / 36 Pa·s |
| quilt (duvet) | Young's modulus 1800 Pa, Poisson ratio 0.40, density 24 kg/m³, shear / bulk viscosity 24 / 125 Pa·s |
| mattress | 1.02 × 1.02 × 0.074 m, Young's modulus 120 kPa, Poisson ratio 0.2, density 60 kg/m³, shear / bulk viscosity 50 / 100 Pa·s |
| added book (ADD case) | 0.26 × 0.19 × 0.030 m, 0.65 kg, pre-settled on the landing point |

- Pillow, quilt and mattress are effective neo-Hookean volumes with Kelvin–Voigt viscosity.
- Pre-roll: before the recorded 4 s every case runs until the bedding is at rest; in the ADD case the
  pre-roll lasts at least 3 s and ends only after a 9-sample window in which the quilt and pillow surfaces
  move less than 0.25 mm (`physics/simulate.py`).
- The ADD solve uses the native statement `ADD extra_book AT PRESET landing_point` (`native_edit_dsl` in the
  builder).

## Measured motion

From the published ground truth (book centre height in m, frames of the 24 fps clock). The book reaches the
pillow at about frame 8.

| Case | Book centre at frame 1 | Lowest (frame) | At frame 96 |
|---|---|---|---|
| `source` | 0.980 | 0.613 (9) | 0.629 |
| `edit_heavy_book` | 0.980 | 0.581 (9) | 0.605 |
| `edit_soft_pillow` | 0.980 | 0.603 (settles slowly, lowest at the end) | 0.603 |
| `edit_firm_pillow` | 0.980 | 0.627 (8) | 0.656 |
| `edit_remove_pillow` | 0.980 | 0.489 (9), on the quilt | 0.499 |
| `edit_add_bedside_book` | 0.980 | 0.624 (9), on the added book | 0.633 |

In `edit_add_bedside_book` the impact pushes the added book 20 mm down into the pillow.

## Validation

- `--stage verify` (`tools/verify_delivery.py`, options `--delivery` and `--suite`) is read-only. It checks
  the accepted delivery (every file and alias of its delivery manifest with sha256 and size, each native
  cache against the acceptance record, the motion audits and the strict edit policy of its packaged suite)
  and the published suite (videos against the suite manifest, the provenance files and the
  `scene_manifest.json` pointer, the media contract with a full decode, prompts equal to the builder
  catalog, `pcve_ground_truth/1` ground truth with 96 frames at (i − 1)/24 s, and each video rendered from
  the accepted cache of its case).
- `tools/audit.py` applies motion, volume and time gates to a native output and writes
  motion_audit.json. With `BOOK_PILLOW_REVIEW_AT_720P=1` it applies the 720p half-pixel
  quilt-stationarity gate once the source render report exists; without the gate the ADD audit keeps the
  0.5 mm all-volume result (failed at 0.507 mm) and the render refuses it. The ADD case passes the
  half-pixel criterion (0.257 px at 720p); the 0.5 mm diagnostic is recorded as failed in the acceptance
  records.
- `appearance/render.py` refuses any change of an existing object transform or of the camera, compares the
  book pose with the cache every frame, and checks the quilt binding and visible book–bedding gaps at frames
  1–19, 25, 37, 49, 73 and 96.
- Published renders: every frame carries provenance whose PNG sha256 matches; the binding audit passes in
  all six cases (book pose against the cache at most 9e-8 per matrix entry; sampled visible book–bedding
  gap between −1.2 mm and +1.7 mm). Temporal stability (mean absolute frame-to-frame luma change, 0–255, at
  480×270 in static regions): wall 0.004–0.007 on average (largest pair 0.18), side table 0.002–0.007
  (0.10), headboard 0.007–0.021 (0.89); the largest values fall on frame pairs 5–8, where the falling book
  changes the light in the room.

## Cases

Native case ids are the published names without the `edit_` prefix (`source`, `heavy_book`,
`soft_pillow`, `firm_pillow`, `remove_pillow`, `add_bedside_book`).

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | book 0.5 kg, pillow E = 400 Pa |
| `edit_heavy_book` | `SET book.mass TIMES 2` | book 1.0 kg |
| `edit_soft_pillow` | `SET pillow.young_modulus TIMES 0.5` | pillow E = 200 Pa |
| `edit_firm_pillow` | `SET pillow.young_modulus TIMES 5` | pillow E = 2000 Pa |
| `edit_remove_pillow` | `DELETE pillow` | no pillow; the book lands on the quilt |
| `edit_add_bedside_book` | `ADD extra_book BETWEEN book AND bed_below_book AT 1/3 FROM bed_below_book` | a pre-settled 0.26 × 0.19 × 0.030 m, 0.65 kg brown book on the pillow under the falling book |

## Assets

| assets.json key | Type | Use |
|---|---|---|
| `scenes/book_pillow_bedroom` | mixed (7 url, 1 manual, 48 derived) | worker-kit inputs and byte-frozen kit modules (index kit/files.json, layout kit/kit_layout.json), bed model and prepared meshes |
| `polyhaven/side_table_01` | url | side table |
| `polyhaven/potted_plant_04` | mixed (8 url, 3 derived) | succulent on the side table |
| `polyhaven/ceramic_vase_04` | url | jug on the side table |
| `polyhaven/plastered_wall_04` | url | walls |
| `polyhaven/poly_wool_herringbone` | url | headboard fabric |
| `polyhaven/stretch_poplin` | url | sheet, pillowcase and piping |

```bash
python3 scripts/download_assets.py --scene book_pillow_bedroom          # download and check sha256
python3 scripts/download_assets.py --scene book_pillow_bedroom --check  # check only
```

Files are stored under `assets/` (`PCVE_ASSETS_DIR` moves the root). The licensed bed model and prepared
meshes are private reproduction inputs. The accepted physics delivery (`renders/book_pillow_bedroom/accepted/`) is
kept under `renders/` and is not registered in `assets.json`.

## Requirements

- Linux with an NVIDIA GPU (CUDA); there is no CPU mode for simulation or delivered renders.
- A restored worker kit: the minimum-inputs tarball in `renders/book_pillow_bedroom/accepted/inputs/` extracted
  into a fresh directory under `.runtime/book_pillow_bedroom/` (it contains `book_kit/`, Python 3.10 and
  the CUDA runtime), with `BOOK_PILLOW_ROOT` set to its `book_kit` directory. The entries hash-check every
  registered input of `assets/scenes/book_pillow_bedroom` and every frozen module listed in kit/files.json
  and hard-link missing ones into the kit.
- Blender 4.3.2: `tools/blender-4.3.2-linux-x64/blender` of the checkout unless `--blender-bin` is given.
- Python 3 with numpy for the builder, verify and ground-truth tools.

## Commands

Run from the repository root.

```bash
# verify the accepted delivery and the published suite (read-only)
python3 scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py --stage verify
python3 scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py --stage prepare   # download_assets.py --check
python3 scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py --list-edits
python3 scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py --show-prompts add_bedside_book

# solve one case, audit it, render it
python3 scripts/rigid_elastic/book_pillow_bedroom/simulate_book_pillow_bedroom.py source \
    --out renders/book_pillow_bedroom/<new folder>/source --rate 600 --material cotton
BOOK_PILLOW_REVIEW_AT_720P=1 <kit python3.10> scripts/rigid_elastic/book_pillow_bedroom/tools/audit.py \
    renders/book_pillow_bedroom/<new folder>/source
python3 scripts/rigid_elastic/book_pillow_bedroom/render_book_pillow_bedroom.py source \
    --input renders/book_pillow_bedroom/accepted/cases/source --output renders/book_pillow_bedroom/<new folder>/source/render \
    --gpu-uuid <GPU UUID> --frames 1 7 96 --samples <N>

# build a new suite from a finished six-case render, then add its ground truth
python3 scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py --stage package \
    --renders-root <render root> --out-root renders/book_pillow_bedroom/<new folder>
python3 scripts/rigid_elastic/book_pillow_bedroom/tools/publish_suite.py --renders <render root with one folder per case> \
    --out renders/book_pillow_bedroom/<new folder>/pcve_book_pillow_bedroom_suite
python3 scripts/rigid_elastic/book_pillow_bedroom/tools/export_ground_truth.py \
    --suite renders/book_pillow_bedroom/<new folder>/pcve_book_pillow_bedroom_suite \
    --native-root renders/book_pillow_bedroom/accepted/cases --render-root <render root>
```

- The entries also provide `--help`, `--describe` and a read-only `--dry-run`.
- Without `--gpu-uuid` (default `auto`) a job goes through the scene's lease launcher: `tools/dispatch.py`
  starts `tools/launch.py`, which picks an idle GPU under the shared GPU policy, holds a lease and retries
  for up to four hours while no GPU is idle. With `--gpu-uuid GPU-...` the launcher uses that card (still
  checked idle and leased).
- Outputs must be fresh directories outside `scripts/`, `assets/` and the two kept deliveries. Render the
  source first, then audit the other cases (the quilt gate needs the source render report).
- The render input is a native cache with a passed motion audit (simulation.npz, motion_audit.json),
  normally the accepted ones. Extra render options (`--frames`, `--range`, `--preview`, `--cpu-stills`) pass
  through to `appearance/render.py`; `--cpu-stills` renders at most four `--frames` on the CPU for look
  development. `BOOK_PILLOW_LOOKDEV` (constant overrides for look development) is recorded in the render
  report when set and is never set for published renders.
- `tools/publish_suite.py` checks per case 96 frames with provenance, a passed binding audit and a render
  report on one backend and one look fingerprint, encodes the video, measures temporal stability and writes
  a fresh suite (`--out` must not exist); `--update-pointer` repoints `canonical_suites` in
  `scene_manifest.json`. It does not copy the published cases' `standardization`
  provenance records.

## Outputs

New solves, renders and suites go to fresh folders under `renders/book_pillow_bedroom/`; restored kits and
job scratch go to `.runtime/book_pillow_bedroom/`. The published suite is
`renders/pcve_suites/pcve_book_pillow_bedroom_suite/` (pointer in `scene_manifest.json`
`canonical_suites`); no command writes into it by default.

- A native solve writes simulation.npz and the solver configuration; `tools/audit.py` adds
  motion_audit.json.
- A render writes frames, per-frame provenance, a render report and a binding audit.
- The published ground truth (`pcve_ground_truth/1`) holds the fixed camera, the falling book and the added
  book as rigid bodies, and the pillow and quilt as deformable bodies. `tools/export_ground_truth.py` writes
  it through `scripts/pcve_ground_truth.py` from the native caches (book poses and solver velocities;
  added-book velocity by central difference; pillow and quilt presence, centroid and bounds of the cached
  vertices) and the camera of the render that produced each video, without resampling: rigid bodies get the
  recorded body centre and the nearest rotation, deformable bodies the centroid of their native vertices and
  the bounding-box dimensions at the first frame they are present; static scenery that no edit names is
  left out.

## Code layout

- `simulate_book_pillow_bedroom.py`: solves one case inside the restored worker kit (`tools/dispatch.py` → `tools/launch.py`)
- `render_book_pillow_bedroom.py`: replays a native cache in Blender with the bedroom look (`--tag` names the render job)
- `build_pcve_book_pillow_bedroom.py`: edit catalog (`PCVE_SOURCE` / `PCVE_EDITS`, equal to the published prompts.json; edit prompts are `pcve_edit_dsl.make_prompts` output for `edit_vocab.py`); `--stage verify | prepare | package`
- `edit_vocab.py`: DSL vocabulary, display-only anchors of the ADD endpoints, and the baseline physics
- `scene_paths.py`: repository locations, worker-kit restore, output checks
- `physics/physics.py`: solver model
- `physics/simulate.py`: pre-roll and 24 Hz sampler (run with the kit's Python 3.10)
- `appearance/render.py`: Blender replay with per-frame pose checks and contact audits
- `appearance/realism_look.py`: the bedroom look and render settings
- `tools/launch.py`, `tools/dispatch.py`: idle-GPU launcher with lease
- `tools/audit.py`: motion, volume and time gates of a native output
- `tools/verify_delivery.py`: read-only checks behind `--stage verify`
- `tools/publish_suite.py`: encodes a finished six-case render and builds a new suite
- `tools/export_ground_truth.py`: per-case ground truth from the native caches and the render camera
- `entrypoints.json`: entry-point options; the case number 9 (`case_number`)
- `scene_manifest.json`: published-suite pointer and accepted-delivery pointer (`native_delivery`)

Prompts name objects as they look on screen (blue book, pillow, brown book), state when the edit applies,
never describe the outcome, and leave out pillow and bedding colours.

## Limitations

- Pillow, quilt and mattress materials are effective values, not calibrated measurements.
- The ADD case fails the stricter 0.5 mm all-volume quilt-stationarity diagnostic (0.507 mm) and passes
  only the half-pixel criterion.
- Paths and model ids inside the restored kit keep the kit's own names.
- The published results were computed on another Linux GPU machine; bitwise reproduction elsewhere is not
  verified.
