# scarf_chair_slip

A fringed cotton scarf hangs over the top rail of a wooden chair's backrest, is released from rest at t = 0, slides off
the backrest and lands in a heap on the seat, settled after about 1.2 s; the chair moves by less than 1 mm. This is a
rigid–elastic scene: a cloth shell against a free rigid chair. The source video is 4 s, 24 fps, 96 frames, 1280×720,
one native sample per frame.

## Scene

- Scarf: 27 cm × 94.5 cm including 3.5 cm of native ribbon fringe at each end, 0.35 mm thick, about 36 g. It is
  built over the top rail with the long end (60 cm) towards the seat and the short end (18 cm) behind the backrest,
  both ends about 8 cm clear of the seat, at rest at t = 0. Frame 1 shows it as a fairly straight ribbon leaning out
  from the backrest: that is the constructed pose at release. Look: the scene's hanging-scarf textile plus a
  plain-weave relief at the real thread pitch (0.9 mm), a 6 mm rolled selvedge along both long edges and native
  fringe ribbons.
- Chair: 6.72 kg, 1.081 m tall, seat at 0.456 m, free on the floor; the render uses the solver's chair model with a
  honey-stained beech finish (`polyhaven/white_maple_veneer`, satin coat).
- Book (`edit_add_landing_book`): a free 0.65 kg, 24.5 × 19 × 3.7 cm box as dark green cloth boards
  (`polyhaven/rough_linen`) around an off-white page block.
- Room: a closed 4.6 m × 4.8 m bedroom-study, 2.7 m high, plastered walls in warm white emulsion
  (`polyhaven/painted_plaster_wall`, 2.4 m tile, slight roller mottling), oak strip floor (the scene's `wood_floor`
  scan, 2 m tile, oiled), painted skirting, a double socket without lettering, a painted timber casement window with
  float glass and a deep sill in the left wall, and two gathered sheer voile panels on a steel rod.
- Furniture and props: the scene's desk re-surfaced in ash veneer (`polyhaven/ash_veneer`, satin lacquer) carrying
  `polyhaven/potted_plant_04`, `polyhaven/ceramic_vase_04`, `polyhaven/wooden_bowl_02`, a closed notebook, a pencil
  and a speckled stoneware mug; `polyhaven/wooden_display_shelves_01` against the back wall with plain clothbound
  books, `polyhaven/antique_ceramic_vase_01`, a bowl and a plant. All props stay outside the swept volume of every
  case (`KEEPOUT` in `appearance/realism.py`).
- Light: daylight only through the window: an afternoon sun about 44 degrees above the horizon (it lights the seat
  above the desk and draws the window bars on the floor) and the `residential_garden` sky through the opening, with a
  sky portal for sampling. No hidden lamps. AgX, look Medium High Contrast, +2.3 EV (interior exposure; the window
  burns out).
- Camera (`appearance/view.py`, also read by the ground-truth exporter): a tripod at (1.4, -2.3, 1.2) m aimed at
  (-0.3, 0.1, 0.55) m, 30 mm on a 36 mm sensor fitted horizontally, no shift. The chair, the scarf in every case and
  the floor where it lands without the chair stay inside the frame.
- Render (`appearance/realism.py`): the scarf plays the 96 native shell states through a Mesh Cache of the exact
  solver positions (so motion blur sees the solver's own frame-to-frame motion); chair and book follow the native
  transforms, keyed per frame. Cycles, 256 samples (adaptive threshold 0.006), OpenImageDenoise, indirect clamp 8,
  bounces 10 (diffuse 5, glossy 4, transmission 8), 0.30-frame shutter motion blur with persistent data off, fixed
  seed, 1280×720, 24 fps, 96 frames. `--look accepted` renders with the base renderer
  (`appearance/render_replay.py`) at 192 samples by default.

## Physics

- Solver: libuipc CUDA IPC (pyuipc 0.0.29).
- Scarf: strain-limiting Baraff–Witkin shell with discrete-shell bending, 420 kg/m^3, effective E = 4 MPa, Poisson
  ratio 0.3, 4 uN·m reference bending, frictional self-contact (0.55), quadratic air drag (air density 1.225 kg/m^3,
  drag coefficient 1.15 on the normal component plus 3 % tangential drag, no direct state damping).
- Friction: cloth–chair 0.32, cloth–floor and cloth–book 0.45.
- Chair and book are free affine bodies; no vertex is pinned and no motion is prescribed.
- The scarf, chair and book are the same bodies in the solver and in the render.
- `simulate_scarf_chair_slip.py` re-solves a case with the time step and mesh pitch recorded in its stored simulation
  configuration; every edit starts from the positions and velocities of frame 1 of the stored source solve.

## Measured motion

From the published ground truth (scarf position = centroid of its solver surface vertices) and the published videos.

| Case | Scarf | Other bodies |
| --- | --- | --- |
| `source` | slides off the backrest and settles in a heap on the back of the seat by about 1.2 s, then stays still | chair moves by less than 1 mm |
| `edit_young_modulus_x10` | the stiffer scarf lands on the seat and is still creeping after frame 40 | chair as in the source |
| `edit_density_x2` | lands in a heap on the seat as in the source | chair as in the source |
| `edit_friction_x0_2` | ends at the front edge of the seat with its fringe over the edge | chair as in the source |
| `edit_add_landing_book` | lands on the seat where the book lies (its centroid ends about 1.5 cm higher than in the source) | the book starts about 1.4 cm above where it comes to rest and settles within the first frames |
| `edit_delete_chair` | falls and ends lying flat on the floor | - |

## Validation

Temporal stability of the published videos at 480×270 grey over frames 40–96 (every case settled): the 99th
percentile of the frame-to-frame change is at most 1 grey level, and the largest step of a regional mean is at most
0.24 grey levels (`edit_young_modulus_x10`, whose scarf is still creeping; source 0.06); the curtain and window regions
change by at most 0.04.

## Cases

Native case ids are the case directory names without the `edit_` prefix.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | scarf E = 4 MPa, 420 kg/m^3, scarf–chair friction 0.32 |
| `edit_young_modulus_x10` | `SET scarf.young_modulus TIMES 10` | stretch, shear and bending stiffness ×10 together |
| `edit_density_x2` | `SET scarf.density TIMES 2` | scarf 420 -> 840 kg/m^3 |
| `edit_friction_x0_2` | `SET scarf.friction TIMES 0.2` | scarf–chair friction 0.32 -> 0.064; floor, book and self friction unchanged |
| `edit_add_landing_book` | `ADD landing_book BETWEEN scarf AND seat_middle AT 1/10 FROM seat_middle` | a free 0.65 kg book over the seat centre, centre (0.025, 0.015, 0.496) m at frame 1 |
| `edit_delete_chair` | `DELETE chair` | no chair |

All edits apply from frame 1. The solver runs the ADD as the native statement `ADD landing_book AT PRESET seat_center`
(`native_edit_dsl` in the builder). `seat_middle` is a display-only anchor in `edit_vocab.py` at the middle of the seat
top, (0.025, 0.015, 0.4662) m; the scarf end of the line is the scarf's frame-1 surface centroid
(0, 0.0501, 0.8539) m, so the 1/10 point lies 1.0 cm from the book's frame-1 centre.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `scenes/scarf_chair_slip` | mixed (26 derived, 5 manual) | stored native output per case (`native/<case>/`), chair model and solver collision mesh, scarf fabric, desk and room assets |
| `polyhaven/painted_plaster_wall` | url | walls |
| `polyhaven/white_maple_veneer` | url | chair finish |
| `polyhaven/ash_veneer` | url | desk finish |
| `polyhaven/rough_linen` | mixed (10 url, 1 manual, 4 derived) | book cloth |
| `polyhaven/potted_plant_04` | mixed (8 url, 3 derived) | plant on the desk |
| `polyhaven/ceramic_vase_04` | url | vase on the desk |
| `polyhaven/wooden_bowl_02` | url | bowl on the desk |
| `polyhaven/wooden_display_shelves_01` | mixed (5 url, 1 manual) | shelves on the back wall |
| `polyhaven/antique_ceramic_vase_01` | url | vase on the shelves |

The look also reads the `polyhaven/residential_garden` sky, which is registered for other scenes.

```bash
python3 scripts/download_assets.py --scene scarf_chair_slip
python3 scripts/download_assets.py --scene scarf_chair_slip --check
```

## Requirements

- Linux; Python 3 for the entries and the checks, NumPy for the ground truth.
- Solves: an NVIDIA GPU (the solver needs a GPU UUID in `CUDA_VISIBLE_DEVICES`), CPython 3.10 and the pyuipc 0.0.29
  wheel kept in `.runtime/scarf_chair_slip/solver/`; the solver must be staged on the machine that solves, and
  `tools/worker.py` puts the solver named by solver/active_solver_path.txt first on the path.
- Rendering: Blender 5.1.0 (`tools/blender-5.1.0-linux-x64`, else 4.3.2, else the shared lookup; `--blender-bin`
  overrides) on one GPU with OptiX, CUDA or the CPU (`--device`). Any Cycles build from 4.x runs the look.
- ffmpeg for encoding.

## Commands

```bash
S=scripts/rigid_elastic/scarf_chair_slip

# checks (no solve): stored delivery, native inputs and published suite
python3 $S/build_pcve_scarf_chair_slip.py --stage verify
python3 $S/build_pcve_scarf_chair_slip.py --list-edits
python3 $S/build_pcve_scarf_chair_slip.py --show-prompts add_landing_book
python3 $S/build_pcve_scarf_chair_slip.py --export-prompts \
    --out-root renders/pcve_suites/pcve_scarf_chair_slip_suite --dry-run

# render one case with the published look on a claimed GPU, or stills on the CPU
python3 $S/render_scarf_chair_slip.py --case source --gpu-uuid <GPU UUID> --out renders/scarf_chair_slip/rebuild/source/realism
python3 $S/render_scarf_chair_slip.py --case source --device CPU --gpu-uuid cpu --frames 1,48,96 --out renders/scarf_chair_slip/rebuild/source/stills

# encode the 96 frames of every case and assemble a new suite
python3 $S/tools/publish_suite.py --encode --renders renders/scarf_chair_slip/<render folder>
python3 $S/tools/publish_suite.py --renders renders/scarf_chair_slip/<render folder> --suite renders/scarf_chair_slip/<new folder>/pcve_scarf_chair_slip_suite

# ground truth of one case
python3 $S/tools/export_ground_truth.py --case source --out renders/scarf_chair_slip/<new folder>/source_ground_truth.json

# native solve (needs the staged runtime and a GPU)
python3 $S/simulate_scarf_chair_slip.py --case source
```

- The entries only require Linux. Without `--gpu-uuid` (default `auto`) a GPU job goes through the lease launcher
  `tools/worker.py` (shared GPU policy, file leases, receipts under `renders/scarf_chair_slip/rebuild/`); with
  `--gpu-uuid <claimed GPU or cpu>` it runs directly on that GPU (`cpu` hides every GPU).
- `--stage verify --out DIR` also writes the report to DIR/verify_report.json.
- `tools/publish_suite.py --encode` turns each `<render>/<case>/frames/0001..0096.png` into `video.mp4` (H.264 High,
  CRF 17, yuv420p, 24 fps, 96 frames). Without `--encode` it builds a suite folder that must not exist yet (videos,
  render provenance, ground truth in `pcve_ground_truth/1`, video validation with a full decode, prompts, provenance,
  suite manifest). It never replaces the published suite and does not copy the prompt history or the other provenance
  records of the published cases.
- `--export-prompts [--dry-run]` writes the builder's prompts into a suite (by default `renders/scarf_chair_slip/suite_build/pcve_scarf_chair_slip_suite/`; the published suite only
  when its path is given with `--out-root`): it rewrites the declared fields of each prompts.json and the matching
  suite manifest record. Every replaced file is first copied to a backup folder
  (`renders/pcve_suites_archive/prompt_export/<scene>/` for the published suite). `--dry-run` only reports.

## Outputs

- Reproduction outputs default to `renders/scarf_chair_slip/rebuild/` (`<case>/simulation`, `<case>/<look>`); outputs
  may not point into the stored delivery, the published suite or the asset store.
- Stored delivery (audits, ground truth, portable scenes, receipts, reference videos): `renders/scarf_chair_slip/accepted/`.
- The published suite is `renders/pcve_suites/pcve_scarf_chair_slip_suite/` (pointer in `scene_manifest.json`);
  nothing writes it by default.
- Ground truth (`pcve_ground_truth/1`): the fixed camera of `appearance/view.py`, the scarf as a deformable body
  (centroid of its solver surface vertices, bounding-box dimensions at the first frame), chair and book as rigid
  bodies (recorded body centre and nearest rotation, with the chair's solver collision mesh and the configured book
  box as rest shapes), converted from each case's native cache without resampling; the static floor is left out.

## Code layout

- `build_pcve_scarf_chair_slip.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`, equal to the published `prompts.json`;
  edit prompts are `pcve_edit_dsl.make_prompts` output) and `--stage verify`.
- `simulate_scarf_chair_slip.py`: native solve of one case through `tools/worker.py` or directly on a claimed GPU.
- `render_scarf_chair_slip.py`: `--look realism` (default) renders the published look from the case's native cache;
  `--look accepted` runs the base renderer.
- `scene_paths.py`: data locations, launchers, published suite and stored delivery; `scene_manifest.json`: suite
  pointer and video hashes.
- `edit_vocab.py`: loads `physics/edit_vocab.py` and adds the display-only ADD anchor.
- `physics/simulate.py`: native libuipc solver.
- `physics/common.py`: fixed layout, physics, scarf mesh and data paths.
- `physics/edit_vocab.py`: shared-DSL vocabulary.
- `appearance/realism.py`: published look.
- `appearance/view.py`: camera, shared with the ground-truth exporter.
- `appearance/render_replay.py`: base renderer, with `appearance/room.py`, `appearance/optics.py`,
  `appearance/scarf_material.py`.
- `tools/worker.py`: lease launcher under the shared GPU policy.
- `tools/finalize.py`: encoder and portable scene of the base renderer.
- `tools/retained_delivery.py`: checks behind `--stage verify`.
- `tools/export_ground_truth.py`: ground truth through `scripts/pcve_ground_truth.py` (`--case CASE --out FILE` or
  `--suite DIR [--cases ...]`).
- `tools/publish_suite.py`: encode frames and assemble a suite.

## Limitations

- Materials and friction are engineering values, not fitted to a measured scarf.
- The published results were computed on other Linux GPU machines (each published case rendered whole on one GPU with
  OptiX at 256 samples, about 9 s per frame); bitwise reproduction elsewhere is not verified.
- The stored delivery under `renders/scarf_chair_slip/accepted/` is not registered in `assets.json`.
