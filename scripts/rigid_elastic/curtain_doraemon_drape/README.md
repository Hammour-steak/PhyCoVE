# curtain_doraemon_drape

A short off-white cotton-linen curtain, already detached at the first frame, falls in front of a window onto a
blue-and-white porcelain vase standing on a desk, drapes over it (part of the fabric sinks into the open mouth) and
settles on the desktop. The scene is rigid–elastic: a thin cloth shell in frictional contact with a free rigid
vase and fixed furniture. The source video is 4 s at 24 fps (96 frames, 1280×720) at normal speed: frame k shows
the native state at t = (k-1)/24 s.

## Scene

- Curtain: 0.916 m x 0.50 m of fabric gathered into a 0.68 m pleated width, 0.25 mm thick, 90 g/m² (41 g),
  9 mm mesh pitch, 4,389 nodes. Its lower edge starts 0.55 m above the desk and moves down at 0.16 m/s after a
  0.25 s held preparation. There are no hooks or curtain rail.
- Vase (object id `figurine`): a porcelain vase scan uniformly scaled to 0.32 m tall, 19 cm at its widest, with a
  14 cm open mouth; 0.75 kg, standing free on the desk. Its collider revolves the scan's outer rings (96 segments
  enclosing the 49-gon) and its scanned inner wall, so the mouth is open.
- Fixed colliders: desk, window pane, window board, notebook and pen holder.
- Camera: fixed at (0.88, -1.52, 0.96) m looking at (-0.025, 0.015, 0.405) m, 41 mm lens, f/6.3 focused on the
  vase (`physics/baseline.py` LAYOUT); one camera for all cases.
- Room and light: a closed room; daylight enters only from the `residential_garden` HDRI through the window (Cycles
  light portal), white-balanced for overcast daylight, falling off into the room and the corners. There is no
  hidden fill light; the thin parallel glass panes cast no shadows.
- Walls: painted plaster (2 m tile, 80 % repainted) with ambient-occlusion grime in the corners and a plain double
  wall socket.
- Curtain material: the `rough_linen` scan on the curtain's rest coordinates (0.27 m tile), reduced to its luminance
  and dyed oatmeal off-white, with sheen, 40 % translucency (22 % in the double-fold hems and the 6 cm heading) and
  stitched hems.
- Vase material: a glossy glaze coat over the scanned maps.
- Window: insulated double glazing with faint smudges, rubber gaskets and a satin aluminium handle; faint interior
  reflections stay. A small potted succulent (18.5 x 16.8 x 26.8 cm) stands on the window board right of the
  mullion; every curtain node of the five whole-clip solves stays at least 7.5 cm from its bounding box.
- Desk: `wood_table` scan; a notebook with a plain unprinted cover board; a pen holder (its normal map is the wood
  normal map).
- Render (`appearance/render.py`, Blender 4.3 Cycles): replays the curtain mesh through an exact MDD vertex cache of
  the native positions (linearly interpolated only inside the 0.25-frame motion-blur shutter) and the vase by its
  native affine transforms; only light, materials and static dressing are authored. OptiX (`--device CUDA|CPU`
  possible), 256 samples with adaptive threshold 0.006, OpenImageDenoise with albedo and normal passes, AgX Base
  Contrast, exposure +3 EV, fixed seed, persistent data off, 1280×720, 24 fps, 96 frames.

## Physics

- Solver: libuipc 0.0.29 on CUDA (`physics/simulate.py`), IPC contact with d_hat 0.8 mm, dt 1/240 s, 10 substeps
  per frame.
- Curtain: strain-limiting Baraff-Witkin thin shell, E 2 MPa, nu 0.3, 0.25 mm, 360 kg/m³, friction 0.55, discrete
  shell bending D = E h³ / 12(1 - nu²).
- Dissipation (`physics/cloth_dissipation.py`): a momentum-preserving internal damping force (8 s⁻¹) and passive
  linear-plus-quadratic air drag (air density 1.225 kg/m³, drag coefficient 1.15), applied as external forces. No
  state is overwritten, filtered or hand-authored.
- Vase: dynamic 0.75 kg affine body on the fixed desk; friction 0.55 against the curtain, 0.45 otherwise. Its hollow
  collider is built from the scan by `tools/prepare_vase.py`.
- Parameters live in `physics/baseline.py` (PHYSICS, LAYOUT); `physics/vocab.py` binds the DSL to them and resolves
  every case. The baseline also defines an optional rigid ceramic tumbler (`cup_*`) that the solver and the renderer
  support; it is inactive in every case.
- Timed edit: `--source-cache` names the stored source run (cache.npz and simulation_config.json, solved with the
  baseline parameters, dt and pitch). The scene is built with the edited friction, the exact source state of frame 8
  (curtain vertex positions and velocities, every rigid transform) is written into the solver, and solving resumes at
  t = 7/24 s; the restored state must match the cache to < 1e-8 (state_handoff.json). The cache does not record
  rigid-body velocities; the vase rests on the desk (recorded motion below 3e-4 m/s), so its affine velocity restarts
  at zero. The output cache.npz holds source frames 1-7 followed by the continuation (continuation.npz keeps the
  solved part).

## Measured motion

From the solves behind the published videos (one solver run per case, `sim/<case>/run1` beside the accepted
delivery):

| case | highest curtain point at 4 s | RMS curtain speed after 3.5 s | what happens |
|---|---|---|---|
| `source` | 0.407 m | 0.037 m/s | about 100 of the 4,389 nodes sink into the open mouth and a fold stands above the rim; around frames 73-89 a side flap slides a little (at most 2 cm per frame at a single node, centroid almost unchanged), then rests |
| `edit_young_modulus_x10` | 0.335 m | 0.0002 m/s | the stiff sheet stays on the vase |
| `edit_density_x0_5` | 0.451 m | 0.0006 m/s | the lighter curtain rests higher on the vase |
| `edit_friction_x0_1` | 0.119 m | 0.0003 m/s | the curtain slides off the vase |
| `edit_delete_figurine` | 0.156 m | 0.032 m/s | no vase; the curtain falls onto the desk |

Temporal stability, measured on static pixels far from the moving bodies at 480x270: the median frame-to-frame
luminance change after frame 31 is at most 0.05 of 255 in every whole-clip case; the maxima (0.06-0.13, up to 1.9
in `edit_young_modulus_x10` and `edit_delete_figurine` while their curtain still moves) come from moving shadows, as
do the larger changes in frames 6-10 when the falling curtain passes the window.

## Validation

- `physics/audit.py SIM_DIR` writes physics_audit.json: DSL binding, static bodies, vase upright, warp/weft stretch
  < 8 %, bias shear < 55 deg, sampled cloth-node penetration of every rigid collider. All published solves pass:
  vase tilt at most 0.012 deg, base above the desk, no curtain node inside any rigid collider. Fold trajectories carry
  no convergence certificate (`accepted_benchmark_gt` false).
- `--stage verify` checks the cases of `physics/vocab.py` CASES in the accepted delivery: DSL binding and edit policy,
  solver configuration against the resolved physics and layout, cache/render/video binding, media contract and the
  ground-truth clock. Cases in a delivery that are not in CASES are ignored.

## Cases

The builder's native case ids drop the `edit_` prefix of the published case directories (`edit_friction_x0_1` is
native case `friction_x0_1`). Every case shares the camera, lights, desk and initial poses.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | curtain E = 2 MPa, 360 kg/m³ (90 g/m² at 0.25 mm), friction 0.55; vase 0.75 kg |
| `edit_young_modulus_x10` | `SET curtain.young_modulus TIMES 10` | curtain E 2 -> 20 MPa (bending follows from E) |
| `edit_density_x0_5` | `SET curtain.density TIMES 0.5` | 360 -> 180 kg/m³ (90 -> 45 g/m²) |
| `edit_friction_x0_1` | `SET curtain.friction TIMES 0.1` | curtain contact friction 0.55 -> 0.055 |
| `edit_delete_figurine` | `DELETE figurine` | the vase is absent |
| `edit_friction_x0_1_at_frame_8` | `SET curtain.friction TIMES 0.1 AT FRAME 8` | frames 1-7 are the source; from frame 8 (t = 7/24 s) the curtain friction is 0.055 |

## Assets

- `scenes/curtain_doraemon_drape` (mixed: 1 url, 6 manual, 7 derived): vase collider and preparation record, desk
  scan, notebook, pen holder, linen material, window HDRI and the asset manifests.
- `polyhaven/antique_ceramic_vase_01` (url): vase scan.
- `polyhaven/rough_linen` (mixed: 10 url, 1 manual, 4 derived): curtain fabric maps.
- `polyhaven/painted_plaster_wall` (url): wall material.
- `polyhaven/potted_plant_04` (mixed: 8 url, 3 derived): succulent on the window board.

```bash
python3 scripts/download_assets.py --scene curtain_doraemon_drape
python3 scripts/download_assets.py --scene curtain_doraemon_drape --check
```

Licences are recorded per file in `assets.json`.

## Requirements

- Linux with a CUDA GPU for solves and renders (renders can also run with `--device CPU`).
- Solver Python 3.10 with numpy, scipy and trimesh plus pyuipc 0.0.29 in `.runtime/curtain_doraemon_drape/uipc_029/`;
  the simulate entry uses `.runtime/curtain_doraemon_drape/python` if present, else `.venv-rigid-elastic/bin/python`,
  or the interpreter given by `--python-runtime`.
- Blender 4.3 (`tools/blender-4.3.2-linux-x64/blender` if present, else `scripts/pcve_assets.blender()`; override with
  `--blender-bin`).
- `physics/audit.py` needs a Python with numpy, scipy and trimesh.
- `--gpu-uuid` takes a claimed GPU (UUID or index); without it `tools/worker_run.py` picks an idle GPU (preflight,
  per-GPU lease, UUID binding).

## Commands

```bash
# check the accepted delivery and the registered assets
python3 scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py --stage verify [--accepted-root <delivery>]
python3 scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py --stage prepare

# edit catalog and prompts
python3 scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py --list-cases
python3 scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py --list-edits
python3 scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py --show-prompts friction_x0_1_at_frame_8

# solve, audit, render and finalize one case
python3 scripts/rigid_elastic/curtain_doraemon_drape/simulate_curtain_doraemon_drape.py --case source \
    --out renders/curtain_doraemon_drape/<run>/sim/source --gpu-uuid <GPU>
python3 scripts/rigid_elastic/curtain_doraemon_drape/physics/audit.py renders/curtain_doraemon_drape/<run>/sim/source
python3 scripts/rigid_elastic/curtain_doraemon_drape/render_curtain_doraemon_drape.py \
    --simulation renders/curtain_doraemon_drape/<run>/sim/source \
    --out renders/curtain_doraemon_drape/<run>/render/source --gpu-uuid <GPU> --device OPTIX --samples 256
blender -b --factory-startup --python-exit-code 1 \
    --python scripts/rigid_elastic/curtain_doraemon_drape/tools/finalize_remote.py -- --case source \
    --simulation renders/curtain_doraemon_drape/<run>/sim/source \
    --render renders/curtain_doraemon_drape/<run>/render/source \
    --out renders/curtain_doraemon_drape/<run>/delivery/cases/source

# timed edit: continue the stored source run from frame 8
python3 scripts/rigid_elastic/curtain_doraemon_drape/simulate_curtain_doraemon_drape.py --case friction_x0_1_at_frame_8 \
    --source-cache renders/curtain_doraemon_drape/accepted/sim/source/run1 \
    --out renders/curtain_doraemon_drape/<run>/sim/friction_x0_1_at_frame_8 --gpu-uuid <GPU>

# package five finalized cases into a native delivery
python3 scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py --stage package \
    --root renders/curtain_doraemon_drape/<run>/delivery --simulation-root renders/curtain_doraemon_drape/<run>/sim

# new suite and its ground truth
python3 scripts/rigid_elastic/curtain_doraemon_drape/tools/publish_suite.py \
    --delivery renders/curtain_doraemon_drape/<run>/delivery \
    --camera renders/curtain_doraemon_drape/<run>/render/source/scene_manifest.json \
    --suite renders/curtain_doraemon_drape/<run>/suite
python3 scripts/rigid_elastic/curtain_doraemon_drape/tools/export_ground_truth.py \
    --delivery renders/curtain_doraemon_drape/<run>/delivery --suite renders/curtain_doraemon_drape/<run>/suite \
    --camera renders/curtain_doraemon_drape/<run>/render/source/scene_manifest.json

# vase collider from the scan
blender -b --factory-startup --python-exit-code 1 \
    --python scripts/rigid_elastic/curtain_doraemon_drape/tools/prepare_vase.py -- \
    --out renders/curtain_doraemon_drape/<run>/porcelain_vase
```

The simulate entry forwards `--case` and `--source-cache` to `physics/simulate.py`; the render entry forwards
`--stills 1,24,48,96` or `--frame-start A --frame-end B` to `appearance/render.py`. `--stage package` accepts
`--simulation-run run1` when each solver case folder holds run subfolders.

## Outputs

- New solves, renders and deliveries go to `renders/curtain_doraemon_drape/<run>/`. `scene_paths.output_path`
  refuses outputs inside `scripts/`, the accepted delivery, the published suite and the asset store.
- Render folder: RGB PNGs, an object-index EXR per frame, a scene_manifest.json with the fixed camera,
  render_completion.json and the packed scene.blend. The renderer refuses a native state of another baseline or vase
  collider (`--allow-other-baseline` only for look development).
- Accepted native delivery of the five whole-clip cases (solver states, audits, masks, MDD, portable scenes,
  ground-truth sidecars, videos): `renders/curtain_doraemon_drape/accepted/delivery/` (scene_manifest.json
  `data.accepted_delivery`); solver states in `renders/curtain_doraemon_drape/accepted/sim/<case>/run1/`.
- Published suite: `renders/pcve_suites/pcve_curtain_doraemon_drape_suite/` (pointer in scene_manifest.json); the
  merged native cache of the timed case is in its `inputs/native_timed/friction_x0_1_at_frame_8/`.
- `tools/publish_suite.py` only builds a new folder: it refuses an existing one, never modifies the published suite,
  refuses ground truth that is not `pcve_ground_truth/1` and carries over the `standardization`
  provenance records of the published suite (`--previous`). Its delivery holds one finalized folder per builder case,
  including the timed case (continuation run rendered and finalized the same way, with geometry/ from the solver
  output); the timed case's native solver files are copied to `inputs/native_timed/` of the new suite. Check a new
  folder (`--export-prompts --dry-run --out-root <suite>`, ground-truth overlays) before replacing the published one
  by hand.
- Ground truth (`pcve_ground_truth/1`, `tools/export_ground_truth.py`): frame i is native sample i-1; the vase is its
  native affine transform (collider frame, base centre) with its centre of mass; the curtain is the centroid of its
  shell vertices with an identity rotation, its rest bounding box and mass-weighted velocity. The camera is the fixed
  LAYOUT camera recorded by a render (`--camera`); an identity camera matrix is refused. In `edit_delete_figurine`
  the vase is absent in every frame.

## Code layout

```
simulate_curtain_doraemon_drape.py      native solve of one case (physics/simulate.py under the case-isolated runtime)
render_curtain_doraemon_drape.py        Blender replay of one solved case (appearance/render.py)
build_pcve_curtain_doraemon_drape.py    edit catalog (PCVE_SOURCE / PCVE_EDITS); --stage verify | prepare | metadata | validate | package
edit_vocab.py                           re-exports VOCAB, CASES, resolve from physics/vocab.py
scene_paths.py                          delivery, suite, runtime and output paths; Blender runtime; GPU launch
scene_manifest.json                     published suite pointer (canonical_suites) and data locations
entrypoints.json                        unified entry declaration
physics/baseline.py                     SI parameters, layout and meshes
physics/vocab.py                        DSL vocabulary and case resolution
physics/simulate.py                     libuipc solve, including the timed continuation (--source-cache)
physics/cloth_dissipation.py            internal damping and air drag forces
physics/audit.py                        CPU audit of a solver output
appearance/render.py                    look and Cycles replay
tools/prepare_vase.py                   vase install transform and IPC collider from the scan (inside Blender)
tools/finalize_remote.py                video encoding, masks, camera calibration, gt.json, cloth.mdd, portable scene (inside Blender)
tools/standardize_case.py               native delivery metadata of one case
tools/build_suite.py                    native delivery packaging (metadata, validate, package)
tools/export_ground_truth.py            pcve_ground_truth/1 of a delivery case
tools/publish_suite.py                  assembles a new suite from finalized case folders
tools/worker_run.py                     idle-GPU launch with preflight, lease and UUID binding (scripts/pcve_gpu_reservations.py)
```

The builder declares `PCVE_SOURCE` and `PCVE_EDITS`; edit prompts are the output of the shared `pcve_edit_dsl`
renderer with `physics/vocab.py`, and the source prompts describe the scene with the values above.
`--export-prompts [--dry-run]` writes them into a suite.

## Limitations

- Material values are effective values, not fitted to a measured fabric.
- The CUDA solver is not bit-reproducible, also on one machine. A repeat solve with the same inputs differs from
  frame 1-3 on where the cloth folds: maximum node distance 0.14 m (`source`), 0.015 m (`young_modulus_x10`),
  < 0.0001 m (`density_x0_5`), 0.020 m (`friction_x0_1`), 0.22 m (`delete_figurine`); curtain centroid at most 0.010,
  0.003, 0.000, 0.0005 and 0.044 m; vase transforms within 2e-4. Final highest points of the two runs: 0.407/0.390,
  0.335/0.336, 0.451/0.451, 0.119/0.119, 0.156/0.117 m; the late slide of the source does not occur in the repeat
  run. The records are in determinism.json beside the solver states; the repeat runs are not kept.
- A timed case can therefore only be continued from the stored source cache, not from a fresh source solve, and a new
  solve is not expected to match the published states bit for bit.
- The published cases were solved and rendered on Linux machines with RTX 4090 and RTX 3090 GPUs (OptiX, 256 samples,
  one device type per case; render_manifest.json and completion.json of each case record the machine and GPU).
- No case-isolated CPython is staged in `.runtime/curtain_doraemon_drape/python`, so solves run with
  `.venv-rigid-elastic/bin/python` unless `--python-runtime` names another Python 3.10.
