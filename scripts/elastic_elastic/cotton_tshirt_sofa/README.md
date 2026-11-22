# cotton_tshirt_sofa

An ivory cotton T-shirt is let go above a sage-grey sofa in a living room and falls onto the right
seat cushion, where it folds and settles while the foam cushion deforms under it. This is an
elastic–elastic scene: a thin cloth shell lands on a deformable foam volume. The source video is
4 s at 24 fps (96 frames), 1280×720; frame k shows the native state at t = (k−1)/24 s.

## Scene

- Shirt: about 103 g, 400 kg/m³ × 0.45 mm = 180 g/m², effective Young's modulus 0.3 MPa,
  friction 0.6 against the sofa; its lowest point starts 0.82 m above the floor. A sewn shell with
  four garment openings (24,150 vertices, 47,982 triangles).
- Seat cushion: upholstery foam, Young's modulus 12 kPa, 35 kg/m³, Poisson ratio 0.25; its
  bottom 18 mm is attached to the sofa deck. The rest of the sofa and the left cushion are fixed;
  a rigid rug support plane sits at 12.5 mm.
- Material values are effective parameters of a cotton jersey and an upholstery foam, not fitted
  to a measured product.
- Room (`tools/native/room.py`, `tools/native/photographic.py`): an enclosed living room with oak
  flooring, chalk plaster, a looped wool rug, a side table, a public-domain botanical wall print,
  and daylight through clear glazing and linen curtains that hide the outdoors.
- Textiles (`tools/native/textiles.py`): cotton jersey with microfiber sheen on the exact physical
  shell (symmetric 0.45 mm thickness, stitches, cuffs, hem and a rib collar); sage-grey upholstery
  on the sofa and the deforming seat cushion.
- Camera (`assets/scenes/cotton_tshirt_sofa/presentation.json`): fixed at (2.05, −3.30, 1.85) m
  looking at (0.12, −0.02, 0.78) m, 46 mm lens, f/5.6 focused at (0.45, −0.06, 0.58) m, AgX Medium
  High Contrast, exposure +0.15. The calibration is written into every render report and ground
  truth.
- Rendering: Blender 4.3.2 Cycles, 128 samples, adaptive threshold 0.006, 8 bounces (diffuse 4,
  glossy 4, transparency 8), OpenImageDenoise; deformation motion blur over a 1/60 s shutter that
  opens at each frame time, built from three solver states per frame. The published look
  (`tools/native/realism.py`) runs `tools/native/render.py` and, once the room is built, adds a low warm
  afternoon sun from the left window (energy 9, 3.5° disc), scales the area fill lights by 0.45
  and adds surface wear to the floor, plaster, rug and window timber (`REALISM_*` environment
  variables override these defaults).

## Physics

- Solver: libuipc 0.0.28 (CUDA, IPC contact with ACCD) in `tools/native/simulate.py`.
- Shirt: a strain-limiting Baraff–Witkin membrane plus discrete shell bending; the effective
  modulus scales membrane, shear and bending together at fixed thickness and Poisson ratio 0.3.
  Self-contact is on. The resolved SI values are stored in each native `simulation_config.json`.
- Seat cushion: a Stable Neo-Hookean tetrahedral volume.
- Air: passive quadratic normal drag plus 2% tangential skin drag on the shirt, applied as an
  external force; no motion filtering or state damping.
- Start: all cases start from the same gravity-prepared release state
  (`geometry/prepared_release.npz` in the scene's assets, shoulder pinches released) and the same
  prepared seat equilibrium.
- Time step: dt = 1/240 s, Newton velocity tolerance 0.5 mm/s, linear residual tolerance 1e-4,
  d_hat 0.4 mm. A 1e-4 versus 1e-6 linear-residual comparison over the first 1.458 s differs by
  45.9 mm RMS (200.2 mm at the worst node) in the final garment pose: fine folds are numerically
  sensitive.
- Outputs of a solve: `simulation.npz` (96 shirt/seat position and velocity samples at
  (k−1)/24 s, float32), `shutter_positions.npz` (three solver states per frame at +0, +1/120 and
  +1/60 s, bound to the cache by its sha256), `simulation_config.json`, `telemetry.json` and
  `completion.json`.
- Timed edit: continues the accepted source solve. `--source-cache` names the source
  `deformation.npz` (with its `shutter_positions.npz` beside it); the solver is built with the
  edited friction, the shirt and seat vertex positions and velocities of frame 10 (t = 9/24 s, as
  stored in float32) are written into it, the hand-off error is asserted below 1e-8
  (`state_handoff.json`), and solving resumes. The merged caches hold the source samples of
  frames 1–9 followed by the continuation; frames 1–9 are asserted equal to the source.
- The libuipc CUDA solve is not checked for bitwise reproducibility across GPUs.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | shirt 180 g/m², E = 0.3 MPa, friction 0.6; seat foam E = 12 kPa |
| `edit_stiff_shirt` | `SET shirt.young_modulus TIMES 10` | E = 3 MPa (membrane, shear and bending scale together) |
| `edit_heavy_shirt` | `SET shirt.density TIMES 3` | 1200 kg/m³ at the same thickness and geometry |
| `edit_low_friction` | `SET shirt.friction TIMES 0.25` | friction 0.15 |
| `edit_remove_seat` | `DELETE seat` | the right seat cushion is absent |
| `edit_low_friction_at_frame_10` | `SET shirt.friction TIMES 0.25 AT FRAME 10` | frames 1–9 as the source; friction 0.15 from t = 9/24 s |

The native case ids drop the `edit_` prefix (`stiff_shirt`, `heavy_shirt`, `low_friction`,
`remove_seat`, `low_friction_at_frame_10`). The builder declares `PCVE_SOURCE` and `PCVE_EDITS`
(DSL, parameter change, native and published case id, Chinese and English prompts); the edit
prompts are `pcve_edit_dsl.make_prompts` of the DSL with `edit_vocab.VOCAB`.

## Assets

- `scenes/cotton_tshirt_sofa` (derived and manual): camera, prepared FEM inputs (`geometry/`),
  sofa and shirt models and textures; texture sources, licenses and hashes are in the asset
  manifests of `assets/scenes/cotton_tshirt_sofa/`.

```bash
python3 scripts/download_assets.py --scene cotton_tshirt_sofa          # download and check sha256
python3 scripts/download_assets.py --scene cotton_tshirt_sofa --check  # check only
```

## Requirements

- Solver runtime: Python 3.10 with libuipc 0.0.28, numpy and scipy. `tools/native/pool_job.py`
  uses `.runtime/cotton_tshirt_sofa/python/bin/python3.10` when one is staged there (else the
  calling interpreter) and adds `tools/ipc_probe_deps` (libuipc 0.0.28) and `tools/manifold3d_deps` of the
  repository root to `PYTHONPATH`.
- An NVIDIA GPU with CUDA for libuipc and Cycles. A full-clip solve takes 30–55 minutes.
- Blender 4.3.2: `tools/blender-4.3.2-linux-x64` in the repository root, else
  `pcve_assets.blender()`.
- `ffmpeg` for encoding.
- The accepted delivery under `renders/cotton_tshirt_sofa/`: `accepted_delivery/` (videos, per-case
  `deformation.npz`, `shutter_positions.npz` and native metadata) and `accepted_renders/<case>/`
  (render reports). `--stage verify`, the default render caches and the default `--source-cache`
  of the timed edit read it. It is not registered in `assets.json`.

## Commands

Run from the repository root.

```bash
python3 scripts/elastic_elastic/cotton_tshirt_sofa/build_pcve_cotton_tshirt_sofa.py --stage verify
python3 scripts/elastic_elastic/cotton_tshirt_sofa/build_pcve_cotton_tshirt_sofa.py --list-edits
python3 scripts/elastic_elastic/cotton_tshirt_sofa/build_pcve_cotton_tshirt_sofa.py --show-prompts low_friction_at_frame_10
python3 scripts/elastic_elastic/cotton_tshirt_sofa/build_pcve_cotton_tshirt_sofa.py --export-prompts \
    --out-root renders/pcve_suites/pcve_cotton_tshirt_sofa_suite --dry-run
python3 scripts/elastic_elastic/cotton_tshirt_sofa/simulate_cotton_tshirt_sofa.py --case stiff_shirt \
  --out renders/cotton_tshirt_sofa/solve_stiff_shirt
python3 scripts/elastic_elastic/cotton_tshirt_sofa/simulate_cotton_tshirt_sofa.py --case low_friction_at_frame_10 \
  --out renders/cotton_tshirt_sofa/solve_low_friction_at_frame_10
python3 scripts/elastic_elastic/cotton_tshirt_sofa/render_cotton_tshirt_sofa.py --case stiff_shirt \
  --out renders/cotton_tshirt_sofa/render_stiff_shirt
blender -b --python-exit-code 1 --python scripts/elastic_elastic/cotton_tshirt_sofa/tools/native/realism.py -- \
  --case low_friction_at_frame_10 \
  --cache renders/pcve_suites/pcve_cotton_tshirt_sofa_suite/inputs/native_timed/low_friction_at_frame_10/simulation.npz \
  --out renders/cotton_tshirt_sofa/render_low_friction_at_frame_10 --samples 128
```

- `--stage verify` checks that the accepted native states and exposure sidecars are the ones their
  render reports name, the clocks, the media contract and the timed cache. `--export-prompts` writes the prompts into a suite's
  `cases/<case>/prompts.json` (`pcve_prompts/1`).
- Solves and renders run through the GPU launcher (`tools/native/pool_job.py`: process query, GPU
  ranking, lease, UUID binding, receipt); `--gpu-uuid` picks a GPU. Outputs must
  be fresh folders beneath `renders/cotton_tshirt_sofa/`. The timed edit takes `--source-cache`
  (the source `deformation.npz`); the render entry takes `--cache` (a `simulation.npz` or
  `deformation.npz`).
- The render entry renders the published look (`tools/native/realism.py`, 128 samples). The Blender command
  renders the same look directly; the exposure sidecar `shutter_positions.npz` must sit beside the
  cache. Both `tools/native/render.py` and `tools/native/realism.py` run on any Linux GPU machine.
- Rendering writes `frame_0000.png` … `frame_0095.png`; the videos are those frames encoded with
  `ffmpeg -framerate 24 -i frame_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 16 -movflags +faststart video.mp4`
  and must pass `pcve_media_contract.require_video`.
- `tools/export_ground_truth.py --suite renders/pcve_suites/pcve_cotton_tshirt_sofa_suite --native
  renders/cotton_tshirt_sofa/accepted_delivery/benchmark_increment/scenes/cotton_tshirt_sofa/cases
  --out renders/cotton_tshirt_sofa/ground_truth` writes
  `<out>/<case>/ground_truth_transforms.json`
  (`pcve_ground_truth/1`; the published suite is only read): for frame i the centroid of the shirt
  shell vertices and of the seat cushion's surface vertices of native sample i−1 (both deformable,
  translation-only `matrix_world`) and the render camera; the timed edit is read from the suite's `inputs/native_timed/`.

## Outputs

- `renders/cotton_tshirt_sofa/<new folder>/`: new solves (`simulation.npz`,
  `shutter_positions.npz`, configuration and telemetry), renders and launch records.
- `renders/cotton_tshirt_sofa/`: also holds the accepted delivery that verify and the default
  caches read.
- The published suite is `renders/pcve_suites/pcve_cotton_tshirt_sofa_suite/` (videos, prompts,
  ground truth and the timed merged cache in `inputs/native_timed/low_friction_at_frame_10/`);
  `scene_manifest.json` points to it. Solves and renders do not write there.

## Code layout

- `build_pcve_cotton_tshirt_sofa.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`) and `--stage verify` (entry point).
- `simulate_cotton_tshirt_sofa.py`: one native solve through the GPU launcher (entry point).
- `render_cotton_tshirt_sofa.py`: one replay in the published look through the GPU launcher (entry point).
- `edit_vocab.py`: exposes `tools/native/edit_vocab.VOCAB` at the scene root.
- `scene_driver.py`: case lists, data locations, output rule and launcher call.
- `tools/native/simulate.py`: libuipc shell and volume solve, timed continuation.
- `tools/native/edit_vocab.py`: baseline (`scene_spec.json`), vocabulary, case DSL and solver parameters.
- `tools/native/scene_spec.json`: baseline scene parameters.
- `tools/native/pool_job.py`: GPU launcher.
- `tools/native/render.py`: Blender replay of a native cache.
- `tools/native/room.py`, `tools/native/photographic.py`, `tools/native/textiles.py`: room, photographic materials and textiles.
- `tools/native/realism.py`: the published look over `tools/native/render.py`.
- `tools/native/common.py`: paths and helpers.
- `tools/retained_delivery.py`: accepted-delivery and timed-cache check.
- `tools/export_ground_truth.py`: ground truth of the suite from the native caches.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: published suite pointer (`canonical_suites`) and data locations.

## Limitations

- Shirt and foam parameters are effective values, not measured from a product.
- Fine folds are sensitive to the linear-solver tolerance (see Physics).
- The libuipc CUDA solve is not checked for bitwise reproducibility across GPUs; the accepted
  solves and renders were made on several machines (RTX 4090 and RTX 3090 among them).
