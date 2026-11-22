# rubber_band_wood_slider

A handmade rubber-band pull-back toy: a stretched rubber band pulls a wooden slider back along a wooden guide after it
is released, goes slack, and the slider stops on friction. This is a rigid–elastic scene: a rigid slider driven by a
finite-strain rubber shell. The source video is 4 s, 24 fps, 96 frames, 1280×720; frame i shows the physical state at
t = (i - 1)/24 s, with no retiming.

## Scene

- Toy: a 300 mm wooden guide (6 mm plywood base, two glued rails) holds a 36 g wooden slider (55 × 42 × 24 mm, no
  wheels). A closed rubber band (natural loop length 200 mm, 1.6 mm wide, 0.6 mm thick) is held at its left end by
  the clamp at the left end of the guide (around a peg under a screwed steel strap) and loops around the peg on the
  slider. The pegs are 117.5 mm apart, so the band is stretched by about 28 %. The slider is held still for 0.5 s and
  then released.
- `appearance/render_scene.py` rebuilds the toy (guide, rails, clamp, pegs, slider, band and the added stop), keys the
  slider from the solver trace and the band as one shape key per native state, and renders frame i at
  t = (i - 1)/24 s. `appearance/realism.py` (`apply()`, called once the toy, camera, render settings and ID-mask
  outputs exist) removes the base table, pencil, paper sketch, offcuts and lamps and builds a home-workshop bench
  around the toy; it never touches the toy, the camera or the replayed states.
- Bench: oriented strand board top (`polyhaven/oriented_strand_board`, 2.51 m per texture repeat, metre UVs), handling
  wear, five faint graphite layout lines away from the toy, saw dust (700 flecks, none inside the toy footprint).
- Toy materials: guide, rails, clamp, pegs and band use the base materials; the sanded oak faces keep their natural
  saturation, and the slider block is walnut (`polyhaven/walnut_veneer`, grain along the block, darker end grain):
  36 g over 55 × 42 × 24 mm is 650 kg/m^3, the density of walnut.
- Props, each resting on the bench with its footprint outside the toy keep-out (x = -0.165..0.165 m,
  y = -0.045..0.045 m): a No. 4 hand plane (`polyhaven/hand_plane_no4`) standing on its sole behind the toy at the
  right; pine plane shavings (0.12 mm ribbons with torn edges: three small rolls of 1.5–2 turns lying on their sides,
  two flat wavy pieces, seven flattened chips); two offcuts of the rail stock with sawn end grain; an unprinted red
  carpenter's pencil (175 × 12 × 6.5 mm) with a knife-cut tip.
- Light: the small-workshop HDRI (`polyhaven/small_workshop`, 4K, rotated 150 deg, strength 0.8) plus a late-afternoon
  sun through its window from the left (elevation 30 deg, from azimuth 160 deg, 1.2 deg disc, warm white, strength
  6). No other lamps.
- Camera: fixed, 58 mm on a 36 mm sensor, at (0.085, -0.365, 0.365) m aimed at (-0.002, 0.008, 0.012) m, depth of
  field at f/11 focused on the guide.
- Render: Blender 4.3.2 Cycles, 256 samples (adaptive threshold 0.003, at least 128), OpenImageDenoise with albedo and
  normal (accurate prefilter), indirect clamp 8, light tree, bounces 12 (diffuse 5, glossy 5), fixed seed 17; motion
  blur 1/72 s (1/3 frame) with 9 band deformation samples per shutter, persistent data off; AgX Medium High Contrast,
  exposure -0.6 EV, mild optical vignette (0.10) in the compositor. GPU renders use OptiX. ID masks of slider, band,
  stop and clamp are written beside the frames.

## Physics

- Band (`physics/physics.py`): an incompressible plane-stress neo-Hookean shell (160 segments × 2 rows) with geometric
  dihedral bending, E = 1.2 MPa, Poisson ratio 0.49, two objective Maxwell branches (fractions 0.15 / 0.05, times
  0.030 / 0.35 s) in membrane and bending response, and Kelvin viscosity (20 / 40 Pa s). E scales membrane force and
  bending moment together.
- Coupling: a finite material arc of the band is fixed to the world at the left clamp and another is bound rigidly to
  the slider, whose prismatic joint receives the material forces through the exact rigid Jacobian.
- MuJoCo 3.17.0 on the CPU resolves contact, friction (slider–guide 0.20, band–wood 0.65) and self-contact.
- dt = 1/384000 s, states at 480 Hz over 4.0 s (1921 samples per case). All six cases start from one shared prepared
  state (`reproduction/prepared_initial.npz` of the stored increment) with zero velocity.

## Measured motion

From the stored native states (the published ground truth agrees). The slider is held until t = 0.50 s (frame 13),
first moves at frame 14 and in every case is at rest again by about frame 20 (t = 0.79 s).

| Case | Slider return (mm) |
| --- | --- |
| `source` | 62.3 |
| `edit_young_x0p5` | 32.9 |
| `edit_mass_x3` | 23.1 |
| `edit_friction_x2` | 32.0 |
| `edit_add_stop` | 44.2 (against the stop) |
| `edit_delete_band` | 0 (does not move) |

## Validation

- The stored audit (kept in the increment): finiteness, contact/energy, material invariants and the fixed material
  ends pass; halving dt moves material points by about 0.114 mm (threshold 0.20 mm). The strict mesh-refinement test
  (160 -> 192 segments, 6.74 mm against 0.5 mm) and the residual-speed test of `mass_x3` after it stops do not pass
  and are recorded as such.
- Every published video: 1280×720, 24/1 fps, 96 frames, 4.000 s, full decode clean.
- Temporal stability (static regions: bench, offcuts, shavings, plane, clamp, guide front):
  mean frame-to-frame change 0.021–0.026 grey levels, worst 8×8 block 0.14–0.50 levels, 99th percentile 0.08–0.11
  levels in all six cases.

## Cases

Native case ids are the case directory names without the `edit_` prefix.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | band E = 1.2 MPa, slider 0.036 kg, slider–guide friction 0.20 |
| `edit_young_x0p5` | `SET band.young_modulus TIMES 0.5` | band E 1.2 -> 0.6 MPa |
| `edit_mass_x3` | `SET slider.mass TIMES 3` | slider 0.036 -> 0.108 kg |
| `edit_friction_x2` | `SET guide.friction TIMES 2` | slider–guide friction 0.20 -> 0.40 |
| `edit_delete_band` | `DELETE band` | band and its forces absent; pegs and slider stay |
| `edit_add_stop` | `ADD stopper BETWEEN slider_peg AND left_clamp AT 1/4 FROM slider_peg` | two fixed 6 × 10 × 20 mm wooden blocks centred at x = 15 mm, 22 mm clear between them |

All edits apply from frame 1. The ADD endpoints `slider_peg` (x = 47.5 mm) and `left_clamp` (centre of the left clamp,
x = -84 mm) are display-only anchors in `edit_vocab.py` (`PROMPT_OBJECTS`, not part of `VOCAB`); the quarter point
from the peg is x = 14.6 mm, 0.4 mm from the added stop. The solver runs the native statement
`ADD stopper AT PRESET return_path` (`edit_vocab.EDITS`), kept in the catalog entry's `native_edit_dsl`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `scenes/rubber_band_wood_slider` | mixed (6 derived, 4 manual, 3 url) | stored physics increment `native/accepted_increment.zip` (native states, shared prepared state, solver, audits) and scene models and textures |
| `polyhaven/oriented_strand_board` | url | bench top |
| `polyhaven/walnut_veneer` | url | slider block |
| `polyhaven/hand_plane_no4` | url | hand plane prop |
| `polyhaven/small_workshop` | url | HDRI |

```bash
python3 scripts/download_assets.py --scene rubber_band_wood_slider
python3 scripts/download_assets.py --scene rubber_band_wood_slider --check
```

## Requirements

- Python 3 for the entries; `.venv-rigid-elastic` (NumPy) for the ground truth.
- Solves: a Python with NumPy and Numba (`.venv-rigid-elastic` by default, `--python-runtime`) and MuJoCo 3.17.0;
  `.runtime/rubber_band_wood_slider/mujoco/` holds MuJoCo 3.17.0 built for CPython 3.10, `--mujoco-runtime` selects
  another unpacked package. CPU only.
- Blender 4.3.2 (`tools/blender-4.3.2-linux-x64/blender` when present, else `pcve_assets.blender()`; `--blender-bin`
  overrides). One NVIDIA GPU (OptiX) for full renders; `--device cpu` for stills.
- FFmpeg from `PATH` or `PCVE_FFMPEG`.

## Commands

```bash
S=scripts/rigid_elastic/rubber_band_wood_slider

# verify the stored increment and the published suite
python3 $S/build_pcve_rubber_band_wood_slider.py --stage verify
python3 $S/build_pcve_rubber_band_wood_slider.py --list-edits
python3 $S/build_pcve_rubber_band_wood_slider.py --export-prompts \
    --out-root renders/pcve_suites/pcve_rubber_band_wood_slider_suite --dry-run

# native re-solve of one case (CPU)
python3 $S/simulate_rubber_band_wood_slider.py --case source --out renders/rubber_band_wood_slider/<new folder>/simulation/source

# render one case on an idle GPU, or three stills on the CPU
python3 $S/render_rubber_band_wood_slider.py --case source --gpu-uuid <GPU UUID or index> --out renders/rubber_band_wood_slider/<new folder>/source
python3 $S/render_rubber_band_wood_slider.py --case source --device cpu --render-threads 48 --frames 1,31,96 --out renders/rubber_band_wood_slider/<new folder>/stills

# all six cases, each whole on one idle GPU
python3 $S/tools/render_queue.py --root renders/rubber_band_wood_slider/<new folder> --gpus <GPU indices> --max-jobs 2

# encode frames rendered without ffmpeg, then publish a new suite
python3 $S/build_pcve_rubber_band_wood_slider.py --stage encode --native renders/rubber_band_wood_slider/<new folder>
python3 $S/build_pcve_rubber_band_wood_slider.py --stage publish --native renders/rubber_band_wood_slider/<new folder> --revision <label> --archive-as pcve_rubber_band_wood_slider_suite_before_<label>

# rewrite or check the ground truth of a suite
.venv-rigid-elastic/bin/python $S/tools/export_ground_truth.py --suite <suite folder> --check
```

- All three entries accept the unified options (`--help`, `--describe`, `--dry-run`, `--out-root`, `--python`,
  `--blender`, `--gpu`, `--threads`); outputs may not be written under `scripts/`.
- `--stage verify` checks the increment (edit policy, native states and the videos it was delivered
  with, `tools/retained_delivery.py`) and the published suite: video hashes against `scene_manifest.json`,
  `suite_manifest.json` and `provenance.json`, the media contract, prompts equal to the builder catalog, the render
  provenance tied to the stored states, and the ground truth (96 frames on the video clock, camera equal to the
  render camera). `--stage package --out DIR` copies the verified increment.
- `--stage publish` runs `tools/publish_suite.py build`, which writes the suite in the current PCVE formats with its
  ground truth from `tools/export_ground_truth.py` and points `scene_manifest.json` at it (with every case video's
  sha256). With `--archive-as` it builds the new suite in a staging folder next to the target, checks it (every
  case's ground truth must be `pcve_ground_truth/1`), and only then moves the published suite into
  `archive/pcve_suites/<name>` and the staging folder into place; each case's provenance keeps the prompt history
  and the other carried provenance records of the suite it replaces.
- `tools/render_queue.py` renders all 96 frames of a case on one GPU and then encodes it. A GPU is taken only when it
  has no compute process of any user, utilization <= 10 % and < 1 GiB in use, and its claim directory could be
  created; if another user's process appears on that GPU, the case is stopped, its claim released and its remaining
  frames rendered later on another GPU of the same model (finished frames are kept). State:
  `<root>/queue_state.json`.
- `tools/publish_suite.py encode` writes `video.mp4` (libx264 CRF 16, yuv420p, 24 fps, 96 frames) and an encoding
  receipt.

## Outputs

- New solves and renders: fresh folders under `renders/rubber_band_wood_slider/` (render default
  `rebuild_<UTC>/render/<case>`, solve default `rebuild_<UTC>/simulation/<case>`): 96 PNG frames, ID masks, per-frame
  provenance, render and look provenance, scene snapshot, encoding receipt, video.
- The published suite is `renders/pcve_suites/pcve_rubber_band_wood_slider_suite/` (`scene_manifest.json` ->
  `canonical_suites`); only `--stage publish` writes it.
- Ground truth (`pcve_ground_truth/1`): slider, guide and stopper are rigid bodies with the recorded body centre and
  the nearest rotation; the band is a deformable body with the centroid of its vertices and bounding-box dimensions.
  It comes from the stored 480 Hz states (every 20th state, no interpolation) and the render camera of each case,
  converted without resampling; static scenery that no edit names is left out.

## Code layout

- `build_pcve_rubber_band_wood_slider.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`, equal to the published
  `prompts.json`; edit texts are `pcve_edit_dsl.make_prompts` output for `edit_vocab.py`); `--stage
  verify|encode|publish|package`.
- `simulate_rubber_band_wood_slider.py`: native solve of one case with `physics/physics.py`.
- `render_rubber_band_wood_slider.py`: Blender replay of one case's stored states with the published look.
- `scene_paths.py`: all locations, the output rule, increment extraction, GPU binding.
- `edit_vocab.py`: DSL vocabulary, display anchors of the ADD, native edit statements.
- `scene_spec.json`: baseline parameters and cases.
- `physics/physics.py`: rubber shell and MuJoCo coupling.
- `appearance/render_scene.py`: replay of the toy, camera, render settings, masks, provenance.
- `appearance/render_base.py`: Blender helpers (materials, primitives, scanned assets).
- `appearance/realism.py`: workshop bench, light and props of the published look.
- `tools/retained_delivery.py`: checks of the stored increment behind `--stage verify`.
- `tools/export_ground_truth.py`: ground truth through `scripts/pcve_ground_truth.py`; `--check` recomputes every file
  and fails on a difference, and a comparison option (see `--help`) checks the slider track and camera against the
  ground truth delivered inside the increment.
- `tools/publish_suite.py`: `encode` and `build` of a suite.
- `tools/render_queue.py`: GPU render queue for all cases.
- Runtime state in `.runtime/rubber_band_wood_slider/`: `native/<case>/` extraction cache of the increment
  (byte-checked against the increment members), `launches/`, `gpu_claims/`, `queue/`, `mujoco/`.

## Limitations

- Materials are not calibrated against a real band (`accepted_benchmark_gt = false` in the native records and
  `scene_manifest.json`).
- The stored solves ran under Python 3.12 with NumPy 1.26.4, Numba 0.60.0 and MuJoCo 3.17.0 (cp312 wheel listed in
  the increment's reproduction/wheel_manifest.json); a new solve with another Python or on another platform is not
  guaranteed to be bitwise equal to the stored states. Nothing in the published suite depends on a re-solve.
- The published results were computed on other Linux GPU machines (each case rendered whole on one GPU with OptiX);
  bitwise reproduction elsewhere is not verified.
