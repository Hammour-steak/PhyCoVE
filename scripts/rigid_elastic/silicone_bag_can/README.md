# silicone_bag_can

A silicone tote hangs by its two handles from two stainless hooks clamped to the front edge of a kitchen counter. A
metal can is released from rest above the bag, drops into it, pulls the bag down out of shape and the loaded bag sways.
This is a rigid–elastic scene: a rigid can against a thin elastic shell. The source video is 4 s, 24 fps, 96 frames,
1280×720; frame i shows native state i - 1 (t = (i - 1)/24 s).

## Scene

- Bag: 24 cm × 15 cm × 22 cm, about 273 g, 1.4 mm wall, 2.4 mm handles with a moulded transition, hanging from two
  hooks; the middle of each handle is fixed. No moulded lettering. Thin-sheet optics (transparency
  exp(-k h / |cos|) with the replayed local wall thickness h) with k = 200 /m, a neutral milky tint and a satin sheen,
  so the can shows through the wall as in a clear food-grade silicone bag.
- Can: 340 g, 6.8 cm across, 8 cm tall, a closed tin-can mesh released from rest with its bottom 18 cm above the bag's
  mouth (centre at (0.012, -0.145, 1.095) m). The printed label and its rules are hidden, leaving a plain bright,
  finely brushed tinplate can with beads, seams and an easy-open lid (no text or logo).
- Kitchen: the packed kitchen `source_scene.blend`, closed into a room (left wall with a 1.1 m × 1.35 m window, right
  and front walls, a ceiling slab overlapping the back wall), so daylight enters only through the two windows.
  Satin sage-green paint over the oak fronts (the packed `oak_veneer_01` grain faintly shows through, fine roller
  stipple, roughness 0.36–0.46); glossy hand-glazed off-white wall tiles with a per-tile tint, a slightly wavy glaze
  and each tile tilted by up to 0.2 degrees about its own centre; darker grout; mottled limewashed walls; a laminate
  floor (roughness 0.20–0.40); brushed stainless hooks and clamps.
- Light: daylight through the back-wall window and the left window (both out of frame): the `pretoria_gardens` HDRI
  (strength 4) through light portals, yawed 225 degrees so that the sun falls through the back window onto the left
  end of the worktop; only the sun disk of the HDRI (pixels above 100) is scaled to 0.4 (sun-patch maximum 242 of 255
  at frame 1). Plus a 12 W warm flush ceiling fitting with an opal body. AgX, look Medium High Contrast, +1.25 EV.
- Camera: the fixed camera of the packed kitchen, 28 mm lens on a 36 mm sensor, no shift, identical in all six cases.
- Render (`appearance/realism.py`, Blender 4.3.2): binds the native states as the base renderer does (96 shape keys,
  linear can keys, frame i = native state i - 1, the per-vertex wall-thickness skin), checks the dynamic signature of
  bag and cans before and after the restyle, asserts the camera unchanged and reruns the camera-coverage and
  native-replay audits; only static geometry, lights and materials change. Cycles, 256 samples (adaptive, threshold
  0.01, at least 64), OpenImageDenoise, indirect clamp 10, 0.25 shutter motion blur centred on the frame with
  persistent data off (the bag's shape-key values are keyed linearly, so the blur interpolates between consecutive
  native states), lens vignette 0.10 and dispersion 0.002. `--look accepted` renders with the base renderer
  (`appearance/render_counter.py`) at 64 samples by default.

## Physics

- Solver: libuipc 0.0.28 CUDA (`physics/solver.py`), IPC contact with friction 0.38.
- Bag: NeoHookean thin shell with discrete-shell bending, both from the same E = 1.05 MPa, nu = 0.46 and local
  thickness, density 1080 kg/m^3, Rayleigh mass damping C = 6 M s^-1. Nodal masses are the rest triangle area × mean
  local wall thickness × density / 3.
- Can: affine body. Counter and cabinet are static colliders; the floor uses a native sub-step Newton/Coulomb
  restitution impulse (e = 0.30, `physics/floor_contact.py`).
- dt = 1/1920 s, Newton velocity tolerance 0.02 m/s, 97 states at 24 Hz over 4 s.
- Every case except `delete_bag` starts from a bag state prepared under gravity (`prepared_empty.npz`;
  `add_second_can` from `prepared_preloaded.npz`, with the second can already at rest in the bag).
- Baseline values and simulation settings are in `physics/scene_spec.json`. The bag shell and the cans are the
  solver's own meshes in the render (shape keys and transforms).

## Measured motion

From the published ground truth (can position = centre of the can, bag position = centroid of its solver surface
vertices). The can's centre starts at z = 1.095 m; the bag centroid hangs at z = 0.762 m (0.757 m with the preloaded
second can). The loaded bag sways until the last frames in every case with a bag.

| Case | Can centre lowest (z, frame) | Can centre at frame 96 (z) | Bag centroid deepest dip |
| --- | --- | --- | --- |
| `source` | 0.609 m, frame 9 | 0.657 m | 43 mm at frame 9 |
| `edit_can_mass_x2` | 0.565 m, frame 10 | 0.642 m | 72 mm at frame 10 |
| `edit_bag_young_x0_25` | 0.510 m, frame 11 | 0.614 m | 108 mm at frame 10 |
| `edit_bag_young_x5` | 0.661 m, frame 9 | 0.676 m (still rolling on the bag bottom) | 8 mm at frame 18 |
| `edit_delete_bag` | lands on the floor and rests at 0.080 m from about frame 21 | 0.080 m | - |
| `edit_add_second_can` | 0.645 m, frame 19 (the second can is pushed down to 0.613 m at frame 9) | 0.655 m | 27 mm at frame 9 |

## Validation

- `--stage verify` checks all six cases: each native cache against the replay audit of its accepted render,
  the strict edit policy, 97 native samples with the 4 s endpoint, the published video SHA-256, prompts and the
  96-frame ground truth, and 1280×720 / 24 fps / 96 frames.
- Temporal stability of the published videos at 480×270 grey: in the static regions (wall tiles, right worktop, left
  and right fronts, floor, sun patch) the 99th percentile of the frame-to-frame change is at most 1 grey level in
  every case and the largest step of a regional mean is 0.29 grey levels; on the bag in frames 80–96 the regional
  mean moves by at most 0.25 grey levels, except `edit_bag_young_x5` (1.28), where the can is still rolling on the bag
  bottom.

## Cases

Native case ids are the case directory names without the `edit_` prefix.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | can 340 g, bag E = 1.05 MPa |
| `edit_can_mass_x2` | `SET can.mass TIMES 2` | can 340 -> 680 g |
| `edit_bag_young_x0_25` | `SET bag.young_modulus TIMES 0.25` | bag E 1.05 -> 0.2625 MPa |
| `edit_bag_young_x5` | `SET bag.young_modulus TIMES 5` | bag E 1.05 -> 5.25 MPa |
| `edit_delete_bag` | `DELETE bag` | no bag; the hooks stay and the can drops from the same place onto the floor |
| `edit_add_second_can` | `ADD second_can BETWEEN can AND bag_bottom AT 9/10 FROM can` | a second 340 g can of the same size already at rest in the bag |

All edits apply from frame 1. The solver runs the ADD as the native statement
`ADD second_can AT PRESET preloaded_inside_bag`, kept in `native_edit_dsl` and in `physics/vocab.py` (`CASE_DSL`).
`bag_bottom` is a display-only anchor in `edit_vocab.py`: the bottom of the bag straight under the second can at frame
1, (0.0020, -0.1488, 0.6236) m; the can end of the line is the falling can's release centre (0.012, -0.145, 1.095) m,
and the 9/10 point lies 0.92 cm from the second can's frame-1 centre.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `scenes/silicone_bag_can` | mixed (15 derived, 1 manual) | packed kitchen `source_scene.blend` (credits in `assets/scenes/silicone_bag_can/asset_sources.json`), prepared bag states `prepared_empty.npz` and `prepared_preloaded.npz`, stored native output per case `native/<case>/` |
| `polyhaven/pretoria_gardens` | url | HDRI of the published look |

```bash
python3 scripts/download_assets.py --scene silicone_bag_can
python3 scripts/download_assets.py --scene silicone_bag_can --check
```

## Requirements

- Linux; Python 3 for the entries and checks, NumPy for the ground truth.
- Solves: an NVIDIA GPU and a libuipc 0.0.28 runtime staged on the machine that solves; none is kept in the
  repository.
- Rendering: Blender 4.3.2 (`--blender-bin` overrides) on one GPU with OptiX, CUDA or the CPU (`--device`).
- ffmpeg for encoding.

## Commands

```bash
S=scripts/rigid_elastic/silicone_bag_can

# checks (no solve): stored delivery, native inputs and published suite
python3 $S/build_pcve_silicone_bag_can.py --stage verify
python3 $S/build_pcve_silicone_bag_can.py --list-edits
python3 $S/build_pcve_silicone_bag_can.py --show-prompts add_second_can
python3 $S/build_pcve_silicone_bag_can.py --export-prompts \
    --out-root renders/pcve_suites/pcve_silicone_bag_can_suite --dry-run

# render one case with the published look on a claimed GPU, or stills on the CPU
python3 $S/render_silicone_bag_can.py --case source --gpu-uuid <GPU UUID> --out renders/silicone_bag_can/rebuild/realism/source
python3 $S/render_silicone_bag_can.py --case source --device CPU --gpu-uuid cpu --frames 1,48,96 --out renders/silicone_bag_can/rebuild/stills/source

# native solve of one case (staged runtime, GPU)
python3 $S/simulate_silicone_bag_can.py --case source

# base pipeline: native solve, base-look render and audit into renders/silicone_bag_can/rebuild
python3 $S/build_pcve_silicone_bag_can.py --stage all --cases source

# encode the 96 frames of every case and assemble a new suite
python3 $S/tools/publish_suite.py --encode --renders renders/silicone_bag_can/<render folder>
python3 $S/tools/publish_suite.py --renders renders/silicone_bag_can/<render folder> --suite renders/silicone_bag_can/<new folder>/pcve_silicone_bag_can_suite

# ground truth of one case
python3 $S/tools/export_ground_truth.py --case source --out renders/silicone_bag_can/<new folder>/source_ground_truth.json
```

- The entries only require Linux. Without `--gpu-uuid` (default `auto`) a GPU job goes through the lease launcher
  `tools/worker_run.py` (shared GPU policy, GPU lease, job records under `renders/silicone_bag_can/rebuild/`); with
  `--gpu-uuid <claimed GPU or cpu>` it runs directly on that GPU (`cpu` hides every GPU).
- `tools/publish_suite.py --encode` turns each `<render>/<case>/frames/0001..0096.png` into `video.mp4` (H.264 High,
  CRF 17, yuv420p, 24 fps, 96 frames). Without `--encode` it builds a suite folder that must not exist yet (videos,
  render provenance, ground truth in `pcve_ground_truth/1`, video validation with a full decode, prompts, provenance,
  suite manifest). It never replaces the published suite and does not copy the prompt history or the other provenance
  records of the published cases.
- `--export-prompts [--dry-run]` writes the builder's prompts into a suite (by default `renders/silicone_bag_can/suite_build/pcve_silicone_bag_can_suite/`; the published suite only
  when its path is given with `--out-root`): it rewrites the declared fields of each prompts.json and the matching
  suite manifest record. Every replaced file is first copied to a backup folder
  (`renders/pcve_suites_archive/prompt_export/<scene>/` for the published suite). `--dry-run` only reports.

## Outputs

- Reproduction outputs default to `renders/silicone_bag_can/rebuild/` (`native/<case>`, `<look>/<case>`); outputs may
  not point into the stored delivery, the published suite or the asset store.
- Stored delivery (audits, ground truth, receipts, reference videos): `renders/silicone_bag_can/accepted/`.
- The published suite is `renders/pcve_suites/pcve_silicone_bag_can_suite/` (pointer in `scene_manifest.json`);
  nothing writes it by default.
- Ground truth (`pcve_ground_truth/1`): the fixed camera of the stored render reports (28 mm lens, 36 mm sensor), the
  bag as a deformable body (centroid of its solver surface vertices, bounding-box dimensions at the first frame), the
  can and the second can as rigid bodies (recorded body centre and nearest rotation), converted from each case's
  native cache without resampling.

## Code layout

- `build_pcve_silicone_bag_can.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`, equal to the published `prompts.json`;
  edit prompts are `pcve_edit_dsl.make_prompts` output); `--stage verify` and the base pipeline
  `--stage simulate|render|audit|all`.
- `simulate_silicone_bag_can.py`: native solve of one case through `tools/worker_run.py` or directly on a claimed GPU.
- `render_silicone_bag_can.py`: `--look realism` (default) renders the published look; `--look accepted` runs the
  base renderer.
- `scene_paths.py`: data locations, launchers, published suite and stored delivery; `scene_manifest.json`: suite
  pointer and video hashes.
- `edit_vocab.py`: loads `physics/vocab.py` and adds the display-only ADD anchor.
- `physics/solver.py`: native libuipc solver.
- `physics/geometry.py`: bag and can meshes.
- `physics/floor_contact.py`: floor restitution impulses.
- `physics/vocab.py`: shared-DSL vocabulary and native edit statements.
- `physics/scene_spec.json`: baseline and simulation settings.
- `appearance/realism.py`: published look.
- `appearance/render_counter.py`: base renderer; its native binding, skin and replay audit are reused by the
  published look.
- `appearance/optics_native.py`: native cache binding, signatures, camera coverage.
- `appearance/build_details.py`: template build and surface helpers.
- `tools/worker_run.py`: lease launcher with `scripts/pcve_gpu_reservations.py` under the shared GPU policy.
- `tools/audit_native.py`: audit of native outputs.
- `tools/retained_delivery.py`: checks behind `--stage verify`.
- `tools/export_ground_truth.py`: ground truth through `scripts/pcve_ground_truth.py` (`--case CASE --out FILE` or
  `--suite DIR [--cases ...]`).
- `tools/publish_suite.py`: encode frames and assemble a suite.

## Limitations

- Materials are effective values, not fitted to a measured bag.
- The published results were computed on other Linux GPU machines (all six cases on one GPU with OptiX, 11–12 s per
  frame); bitwise reproduction elsewhere is not verified.
- The stored delivery under `renders/silicone_bag_can/accepted/` is not registered in `assets.json`.
