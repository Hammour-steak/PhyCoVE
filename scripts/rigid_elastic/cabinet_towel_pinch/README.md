# cabinet_towel_pinch

A cotton hand towel is draped over the top edge of a lower kitchen cabinet door that stands open at 45°,
with a small corner on the inside and most of the towel hanging outside. After 0.5 s the door is released
and a closing torque on its hinge swings it shut; the towel is carried along by contact and the part over
the top of the door is caught between the door and the cabinet frame. This is a rigid–elastic scene: a
cloth shell and an affine-body door coupled by IPC contact. The source video is 4 s, 24 fps, 96 frames,
1280×720; all cases start from the same pre-settled native state.

## Scene

- Towel: 28 cm × 60 cm, 0.8 mm thick, about 40 g; draped over the door top, no vertex pinned.
- Door: 0.47 × 0.018 × 0.65 m, 2.4 kg, on a revolute hinge, held open at 45° for the first 0.5 s (released
  at frame 13). The towel, door and cabinet collider are the same bodies in the solver and in the render.
- Room (`appearance/realism.py` opens each case's saved scene and restyles static room geometry, lights and
  materials only; towel shape keys, door transforms, camera and frame timing are those of the native
  solve): a closed plastered room 4.4 m wide with a 2.5 m ceiling.
- Light: daylight only through a 1.65 m × 1.35 m window in the left wall (out of frame), the
  `residential_garden` HDRI (strength 12) sampled through a light portal in the opening, plus a 10 W warm
  flush ceiling fitting with an opal body. No other lights.
- Materials (CC0 scans at real-world size, object-space mapping, offset per object): `silver_oak_veneer_01`
  (1 m tile) on every door, the face frame and end panels, grain vertical, leaf-to-leaf tone change, satin
  lacquer; `granular_concrete` (2.4 m) on 60 cm concrete-look porcelain floor tiles (roughness 0.05–0.16)
  over a grout bed for the 2 mm joints; `hangar_concrete_floor` (2 m) as a dark stone worktop;
  `gingham_check` (28.4 cm × 29.7 cm repeat) on the towel's UVs, green-and-white gingham in unbleached
  cotton with a folded 9 mm (long sides) / 12 mm (ends) hem and a stitch line 6 mm in from the edge; glossy
  hand-glazed white wall tiles with per-tile tint; white melamine carcass; brushed steel pulls.
- Fronts: the bar pulls of the other doors (static parts of the fixed collider that no case touches; the
  towel stays within x = 0.03–0.59 m) are not rendered, so the run reads as handleless. The towel door
  keeps its vertical bar pull at its top free corner: it is part of that door's simulated body, and the
  towel lies against it (within 3 mm) for all 96 frames of `source`, `edit_hinge_torque_x0_03` and
  `edit_young_modulus_x30`.
- Fitting details: a 16 cm oak filler closes the gap between the last door and the right end panel; the
  door hangs on concealed cup hinges; the towel bay has melamine gables and an adjustable shelf about
  0.44 m up with `pot_enamel_01` on it, all behind y = 0.02 m (the towel never passes y = 0.004 m); the two
  stacks of 12 mm discs of the native collider on the bottom shelf are oiled wooden coasters; the bay's
  bottom rail is face-frame oak. A cutting board and a black utensil pot stand on the worktop.
- Camera: fixed for all cases, 29.5 mm lens on a 36 mm sensor (`appearance/render_view.py`), aimed so that
  the top of the door and the floor landing are both in view; the look asserts it unchanged.
- Render: Blender 4.3.2 Cycles, 256 samples, OpenImageDenoise, indirect clamp 10, caustics off, motion blur
  with a 0.25-frame shutter (persistent data off), lens vignette 0.10 and dispersion 0.002, AgX Medium High
  Contrast, exposure +0.5 EV. Each published video is rendered on one device (the source on the CPU, the
  edits with OptiX). `--look accepted` renders with the base renderer at 128 samples by default.
- Encoding (`tools/publish_suite.py --encode`): H.264 High, CRF 17, yuv420p.

## Physics

- Solver: libuipc CUDA IPC (pyuipc 0.0.29); time step and mesh pitch as recorded in each case's simulation
  configuration (solver defaults dt = 1/240 s, pitch 8 mm).
- Towel: strain-limiting Baraff–Witkin shell with discrete-shell bending, frictional self-contact and
  quadratic air drag; 300 kg/m³, E = 1 MPa, Poisson ratio 0.3, friction 1.2.
- Door: affine body on a revolute joint driven by a 0.9 N·m closing torque with 1.2 N·m·s rotary damping,
  held open by a stiff torque spring (100 N·m/rad with a 2 N·m·s/rad dashpot) for the first 0.5 s. No motion
  is prescribed.
- `physics/edit_vocab.py` holds the baseline values and resolves each DSL edit into the native fields;
  `delete_door` does not create the door body and its hinge.
- `simulate_cabinet_towel_pinch.py` re-solves a case from the shared pre-settled seed with the recorded time
  step and pitch.

## Measured motion

From the published ground truth (frames of the 24 fps clock) and, where marked, the native caches.

| Case | Door | Towel |
|---|---|---|
| `source` | turns from frame 14, closed and at rest from about frame 42 | the part over the door top is caught; the door closes with a gap of about 2.5 mm at the handle side (native cache) |
| `edit_friction_x0_01` | as in the source | slides off the door by frame 5 (native cache) and lies on the floor (centroid 14 mm above it, at rest from about frame 32) |
| `edit_hinge_torque_x0_03` | starts to turn at frame 18 and only creeps (its centroid moves 18 mm in 4 s) | stays draped over the door top |
| `edit_young_modulus_x30` | as in the source | caught as in the source |
| `edit_delete_door` | absent | falls to the floor (centroid 29 mm above it, at rest from about frame 22) |

## Validation

- `--stage verify` checks all cases: the accepted delivery and native inputs (96 native samples, ground-truth
  clock) and the published suite (video SHA-256, 1280×720, 24 fps, 96 frames); `--out DIR` also writes the
  report to DIR.
- Temporal stability of the published videos at 480×270 grey in static regions (left and right fronts,
  floor, worktop): the 99th percentile of frame-to-frame change is at most 1 grey level and the largest step
  of a regional mean is 0.97 grey levels (the `edit_delete_door` floor as the towel lands).

## Cases

Native case ids are the published names without the `edit_` prefix (`source`, `friction_x0_01`,
`hinge_torque_x0_03`, `young_modulus_x30`, `delete_door`).

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | towel friction 1.2, E = 1 MPa; closing torque 0.9 N·m |
| `edit_friction_x0_01` | `SET towel.friction TIMES 0.01` | towel friction 0.012 |
| `edit_hinge_torque_x0_03` | `SET hinge.closing_torque TIMES 0.03` | closing torque 0.027 N·m |
| `edit_young_modulus_x30` | `SET towel.young_modulus TIMES 30` | towel E = 30 MPa |
| `edit_delete_door` | `DELETE door` | no door body and no hinge |

## Assets

| assets.json key | Type | Use |
|---|---|---|
| `scenes/cabinet_towel_pinch` | mixed (4 manual, 37 derived) | native output and saved scene of each case (`native/<case>/`), the shared pre-settled seed (`initial_state/`), and the oak, cotton, board and utensil models of the base renderer |
| `polyhaven/silver_oak_veneer_01` | url | doors, face frame, end panels |
| `polyhaven/granular_concrete` | url | floor tiles |
| `polyhaven/hangar_concrete_floor` | url | worktop |
| `polyhaven/gingham_check` | url | towel fabric |
| `polyhaven/pot_enamel_01` | url | pot on the shelf |

```bash
python3 scripts/download_assets.py --scene cabinet_towel_pinch          # download and check sha256
python3 scripts/download_assets.py --scene cabinet_towel_pinch --check  # check only
```

Files are stored under `assets/` (`PCVE_ASSETS_DIR` moves the root). The four manual models are royalty-free
(sources and authors in `assets.json`); their materials are packed in the saved scenes and the look replaces
their shading. The accepted native delivery (audits, ground truth, receipts, packaging records, reference
videos) is kept in `renders/cabinet_towel_pinch/accepted/pcve_cabinet_towel_pinch_suite/` and is not
registered in `assets.json`.

## Requirements

- Linux. The native solve needs an NVIDIA GPU (CUDA) and CPython 3.10 with pyuipc 0.0.29 staged in
  `.runtime/cabinet_towel_pinch/` on the machine that runs it.
- Rendering: Blender 4.3.2 on a GPU (OptiX or CUDA) or the CPU (`--device CPU --gpu-uuid cpu`).
- Python 3 with numpy for verify, ground truth and suite assembly.

## Commands

Run from the repository root.

```bash
# checks (no solve): accepted delivery, native inputs and published suite
python3 scripts/rigid_elastic/cabinet_towel_pinch/build_pcve_cabinet_towel_pinch.py --stage verify
python3 scripts/rigid_elastic/cabinet_towel_pinch/build_pcve_cabinet_towel_pinch.py --list-edits
python3 scripts/rigid_elastic/cabinet_towel_pinch/build_pcve_cabinet_towel_pinch.py --show-prompts delete_door
python3 scripts/rigid_elastic/cabinet_towel_pinch/build_pcve_cabinet_towel_pinch.py --export-prompts \
    --out-root renders/pcve_suites/pcve_cabinet_towel_pinch_suite --dry-run

# render one case with the published look on a claimed GPU (or --device CPU --gpu-uuid cpu)
python3 scripts/rigid_elastic/cabinet_towel_pinch/render_cabinet_towel_pinch.py --case source --gpu-uuid <GPU index or UUID> \
    --out renders/cabinet_towel_pinch/<new folder>

# encode the 96 frames of every case, then assemble a new suite
python3 scripts/rigid_elastic/cabinet_towel_pinch/tools/publish_suite.py --encode --renders renders/cabinet_towel_pinch/<render folder>
python3 scripts/rigid_elastic/cabinet_towel_pinch/tools/publish_suite.py --renders renders/cabinet_towel_pinch/<render folder> \
    --suite renders/cabinet_towel_pinch/<new folder>/pcve_cabinet_towel_pinch_suite

# ground truth of one case
python3 scripts/rigid_elastic/cabinet_towel_pinch/tools/export_ground_truth.py --case source \
    --out renders/cabinet_towel_pinch/<new folder>/source_ground_truth_transforms.json

# native solve (needs the staged runtime)
python3 scripts/rigid_elastic/cabinet_towel_pinch/simulate_cabinet_towel_pinch.py --case source
```

- Without `--gpu-uuid` (default `auto`) a GPU job goes through the scene's lease launcher `tools/worker.py`
  (shared GPU policy, cooperative leases, receipts under `renders/cabinet_towel_pinch/rebuild/provenance/`);
  with `--gpu-uuid <claimed GPU or cpu>` it runs directly on that GPU (`cpu` hides every GPU).
- `render_cabinet_towel_pinch.py --look realism` (default) restyles the case's saved scene with
  `appearance/realism.py`; `--look accepted` runs the base renderer `appearance/render_replay.py`.
- `tools/publish_suite.py --encode` turns each `<render>/<case>/frames/0001..0096.png` into video.mp4;
  without `--encode` it builds a suite folder that must not exist yet (videos, render provenance, ground
  truth, video validation with a full decode, prompts, provenance, suite manifest). It does not copy the
  published cases' `standardization` provenance records.
- `--export-prompts` writes the catalog prompts into a suite (by default `renders/cabinet_towel_pinch/suite_build/pcve_cabinet_towel_pinch_suite/`; the published suite only
  when its path is given with `--out-root`): it rewrites the declared fields of each prompts.json and the matching
  suite manifest record. Every replaced file is first copied to a backup folder
  (`renders/pcve_suites_archive/prompt_export/<scene>/` for the published suite). `--dry-run` only reports.

## Outputs

Reproduction outputs default to `renders/cabinet_towel_pinch/rebuild/`; outputs may not point into the
accepted delivery, the published suite or the asset store. The published suite is
`renders/pcve_suites/pcve_cabinet_towel_pinch_suite/` (pointer in `scene_manifest.json`); no command writes
into it unless that path is passed to `--export-prompts --out-root` (without `--dry-run`).

The published ground truth (`pcve_ground_truth/1`) holds the fixed camera (29.5 mm lens, 36 mm sensor), the
towel as a deformable body and the door as a rigid body. `tools/export_ground_truth.py` (`--case CASE --out
FILE` or `--suite DIR [--cases ...]`) writes it through `scripts/pcve_ground_truth.py` from each case's native
cache and the fixed camera of the saved scenes, without resampling: the door gets its recorded body centre and
the nearest rotation, the towel the centroid of its solver surface vertices and its bounding-box dimensions at
the first frame; the fixed cabinet carcass, which no edit names, is left out. `tools/publish_suite.py` calls it
for a new suite.

## Code layout

- `simulate_cabinet_towel_pinch.py`: native solve of one case (through the lease launcher `tools/worker.py`, or directly on a claimed GPU)
- `render_cabinet_towel_pinch.py`: renders one case with `--look realism` or `--look accepted`
- `build_pcve_cabinet_towel_pinch.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`, equal to the published prompts.json; edit prompts are `pcve_edit_dsl.make_prompts` output; the source prompts carry the measured values) and `--stage verify`
- `scene_paths.py`: data locations, launchers, output checks
- `scene_manifest.json`: published suite and accepted native delivery pointers
- `edit_vocab.py`: loads `physics/edit_vocab.py`
- `physics/simulate.py`: native solver
- `physics/geometry.py`: towel mesh, door, collider, frozen layout
- `physics/edit_vocab.py`: shared-DSL vocabulary, baseline values and edit resolution
- `physics/common.py`: shared paths and helpers of the physics code
- `appearance/realism.py`: the published look
- `appearance/render_replay.py`: base renderer; writes the saved scenes
- `appearance/surface_detail.py`: surface detail shaders
- `appearance/render_view.py`: camera
- `tools/worker.py`: lease launcher under the shared GPU policy
- `tools/retained_delivery.py`: checks behind `--stage verify`
- `tools/export_ground_truth.py`: ground truth in the `pcve_ground_truth/1` layout
- `tools/publish_suite.py`: encodes frames and assembles a suite
- `entrypoints.json`: entry-point options; the case number 21 (`case_number`)

## Limitations

- Towel and door materials are effective values, not fitted to a measured towel or hinge.
- `physics/simulate.py` only runs on hosts in a fixed list of machine names, so a native re-solve needs one of
  those machines or an edited host check.
- The published results were computed on another Linux GPU machine; bitwise reproduction elsewhere is not
  verified.
