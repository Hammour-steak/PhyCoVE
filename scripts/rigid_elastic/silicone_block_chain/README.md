# silicone_block_chain

A small wooden press rig on a workbench: a 32 mm steel ball rolls down a sloping wooden track and drops into the
shallow cup of a platen that slides on four guide rods; the platen compresses a foam block and its edge tips up a
hinged wooden flag. This is a rigid–elastic scene: rigid ball, platen and flag against a viscoelastic foam block (the
scene ID names a silicone block; the deformable body is a polyurethane foam block). The source video is 4 s, 24 fps,
96 frames, 1280×720.

## Scene

| Part | Values |
| --- | --- |
| Track | 18.0 cm run, 3.6 cm rise (18.4 cm long); the ball starts at rest at the top |
| Steel ball | 32 mm, 134.7 g (solid) |
| Platen with cup and sleeves | 18 g, bottom at 48.7 mm, lower stop at 25.7 mm |
| Foam block | 32 × 32 × 40 mm, bottom at 8.3 mm |
| Flag | 70 mm, 3 g, hinged at x = 52 mm, z = 45.7 mm |

- Look (`appearance/realism.py`): an overlay on the packed scene of a case (the stored packed scene, or the bake of
  `appearance/bake_native.py`).
- Light and environment: only the HDR panorama `polyhaven/small_workshop` (4k, rotated 270° about +z so the windows
  are behind the camera, strength 1) lights, reflects and backs the scene; the defocused background is the photograph.
  The packed scene's hidden area lights and low backdrop wall are removed.
- Wood: a different stock per part: birch-faced ply base with visible plies on its cut edges
  (`polyhaven/white_maple_veneer`), an aged cross-grain ply platen, ash posts and flag (`polyhaven/ash_veneer`), and
  the saved okoume ply scan for the track, rails, cup and small sticks; each part has its own grain offset, grain turn
  and tone; the two ramp risers have 0.6 mm sanded edges.
- Gauge: a short brushed stainless rule with fine etched graduations (static scenery).
- Foam: three thin felt-tip deformation marks (about 1 mm, soft edges, faint bleed, faded blue-black) and open-cell
  mottling (about 15 mm and 1 mm noise) in the foam's rest coordinates, so marks and shading move with the material.
  The packed scene's ruler, pencil and sketch sheet are removed.
- Camera: fixed, 50 mm lens on a 36 mm sensor (`scene_manifest.json` `camera`); motion blur with a 0.25-frame shutter
  (persistent data off), AgX Medium High Contrast at +0.8 EV, mild vignette and lateral colour from
  `pcve_realism_kit.lens_finish`.
- Render: Blender 4.3.2 Cycles, 384 samples, adaptive threshold 0.005, OpenImageDenoise with albedo and normal,
  indirect clamp 4, fixed seed, 1280×720, 24 fps, 96 frames.

## Physics

- `physics/physics.py` solves the rig on the CPU (NumPy + SciPy): an implicit finite-strain viscoelastic foam block
  (tetrahedral mesh of 6 × 6 × 8 cells) coupled to a guided platen with penalty cup contacts, Coulomb friction and
  rolling resistance, an analytic ramp roll for the ball until it leaves the track, and a passive hinged flag lifted
  by the platen edge.
- Foam: Young's modulus 3 kPa, Poisson's ratio 0.08, 48 kg/m^3, shear viscosity 35 Pa·s, bulk viscosity 70 Pa·s.
- Cup contact: friction 0.2, normal stiffness 160 kN/m, damping 55 N·s/m; rolling resistance length 0.15 mm.
- Every 1/1920 s step is an L-BFGS-B minimisation; the cache stores 96 samples per second and video frame f is
  native sample 4(f - 1) (t = (f - 1)/24 s).
- Geometry is in `physics/rig.py`, the baseline, edits and timed schedule in `physics/config.py`.
- Timed edit: the source parameters run in the same solve until step 560 (t = 7/24 s, frame 8, the ball still on the
  track), where `PressRig.set_ball_mass` sets the ball's mass to 67.35 g with the same outer diameter and a concentric
  hollow core; the ball keeps its position, velocity and spin, and its rolling law continues from the current distance
  and speed with the new acceleration (exit 0.522 s instead of 0.517 s, first cup contact 0.573 s instead of 0.567 s).
  Samples 0–28 (frames 1–8) are bit-identical to the source solve of the same machine.

## Validation

- Before anything changes, `appearance/realism.py` checks every requested frame against the native cache (2e-6 m,
  1e-5 rad, the limits of the float32 keyframes); right before each render it checks the frame again and requires
  every original object, the foam surfaces, the foam optical densities and the camera to equal the saved scene. On
  the published renders the largest scene-vs-cache error is 8.3e-7 rad (ball spin), positions below 1e-8 m.
- The bake of a re-solve into the workshop template passes the bake and saved-scene audit of `appearance/scene.py`
  (cup 1.8e-9 m, ball 5.4e-9 m, flag 3.7e-8 rad, foam 1.9e-9 m).
- Temporal stability of the whole-clip renders at 480×270 over frames 49–96: on the guide rods, steel rule, bench and
  background the frame-to-frame mean change is at most 0.16/255, the per-pixel standard deviation (99th percentile)
  at most 1.0/255 on the rule, bench and background and 0.3/255 on the rear rods; larger values (up to 3.3/255) occur
  only where moving parts pass.
- GPU (OptiX) and CPU renders of the same frame differ only by sampling noise (PSNR about 41 dB).

## Cases

Native case ids are the case directory names without the `edit_` prefix.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | ball 134.70 g, foam E = 3 kPa |
| `edit_stiff_foam` | `SET foam_block.young_modulus TIMES 4` | foam E 3 -> 12 kPa |
| `edit_light_ball` | `SET steel_ball.mass TIMES 0.5` | ball 134.70 -> 67.35 g (same 32 mm outer diameter, concentric hollow core) |
| `edit_viscous_foam` | `SET foam_block.viscosity TIMES 4` | shear viscosity 35 -> 140 Pa·s, bulk viscosity 70 -> 280 Pa·s |
| `edit_remove_foam` | `DELETE foam_block` | no foam block |
| `edit_light_ball_at_frame_8` | `SET steel_ball.mass TIMES 0.5 AT FRAME 8` | ball 134.70 -> 67.35 g from frame 8 (t = 7/24 s) |

Which solve each published video replays:

- `edit_stiff_foam`, `edit_light_ball`, `edit_viscous_foam`, `edit_remove_foam`: the stored caches in
  `assets/scenes/silicone_block_chain/accepted_solves/physics/<case>/`, rendered from the stored packed scenes
  `accepted_solves/packed/<case>.blend` into which they are baked.
- `source` and `edit_light_ball_at_frame_8`: a re-solve of the same code (NumPy 1.26.4, SciPy 1.15.3, single-thread
  BLAS) kept with the suite cases in `cases/<case>/native_metadata/` (`simulation.npz`, `config.json`,
  `bake_report.json`), baked into the workshop template `workshop_template/packed/source.blend`. The stored caches do not hold the
  foam node velocities and the L-BFGS-B solve is not bit-reproducible across machines, so the timed edit branches from
  a source solved in the same run. The re-solved source differs from the stored source cache by at most 1.04 mm in the
  rigid states and 1.2e-5 m in the foam nodes.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `scenes/silicone_block_chain` | mixed (18 derived, 1 manual) | stored caches and solver reports `accepted_solves/physics/<case>/`, stored packed scenes `accepted_solves/packed/<case>.blend`, workshop template `workshop_template/packed/source.blend` |
| `polyhaven/small_workshop` | url | HDR panorama, the only light and background |
| `polyhaven/white_maple_veneer` | url | ply base |
| `polyhaven/ash_veneer` | url | posts and flag |

```bash
python3 scripts/download_assets.py --scene silicone_block_chain
python3 scripts/download_assets.py --scene silicone_block_chain --check
```

`PCVE_ASSETS_DIR` selects another asset root.

## Requirements

- Solver: `.venv-rigid-elastic` (NumPy 1.26.4, SciPy 1.15.3), CPU, single-thread BLAS (`OPENBLAS_NUM_THREADS=1`).
- Rendering: Blender 4.3.2 (`--blender-bin` overrides) on a GPU with OptiX or CUDA, or on the CPU (`--device CPU`);
  the delivered look (`--look delivered`) needs a leased GPU through `tools/worker.py`.
- ffmpeg for encoding.

## Commands

```bash
PY=.venv-rigid-elastic/bin/python
S=scripts/rigid_elastic/silicone_block_chain

# verify the published suite, the solves it replays and the stored delivery
$PY $S/build_pcve_silicone_block_chain.py --stage verify
python3 $S/build_pcve_silicone_block_chain.py --list-edits
python3 $S/build_pcve_silicone_block_chain.py --show-prompts light_ball_at_frame_8

# solve one case (writes renders/silicone_block_chain/rebuild/physics/<case>/{simulation.npz,config.json})
OPENBLAS_NUM_THREADS=1 $PY $S/simulate_silicone_block_chain.py --case source
OPENBLAS_NUM_THREADS=1 $PY $S/simulate_silicone_block_chain.py --case light_ball_at_frame_8

# render a stored case with the published look (writes rebuild/realism/<case>/)
python3 $S/render_silicone_block_chain.py --case stiff_foam --gpu-uuid <GPU UUID> --device OPTIX

# render a solve of its own: bake, then render (timed edit, re-solved source)
python3 $S/render_silicone_block_chain.py --case light_ball_at_frame_8 --native-dir renders/silicone_block_chain/rebuild/physics/light_ball_at_frame_8 --device CPU --cpu-threads 48
python3 $S/render_silicone_block_chain.py --case source --native-dir renders/pcve_suites/pcve_silicone_block_chain_suite/cases/source/native_metadata --device CPU

# assemble a new suite from the six renders (a folder that must not exist yet)
python3 $S/tools/publish_suite.py --native renders/silicone_block_chain/rebuild --suite renders/silicone_block_chain/<new folder>/pcve_silicone_block_chain_suite
```

- All three entries accept the unified `--help`, `--describe`, `--dry-run`, `--out-root` (simulate and render: the
  output root; build: `--out`, a copy of the verify report), `--python`, `--blender`, `--gpu` and `--threads`. Outputs
  may not be written into `scripts/`, the assets, the stored delivery or the published suite.
- `--stage verify` re-hashes the data files (videos, caches, packed scenes) listed with a sha256 in the stored delivery
  manifest at their current locations (code and record files are listed without hashes and only counted), checks the stored caches and the two re-solves
  against `physics/config.py` (and the timed edit's samples before the edit against the source re-solve, bit for bit),
  and checks the published suite: video hashes against `suite_manifest.json` and `scene_manifest.json`, the media
  contract, `prompts.json` equal to the builder catalog, each render record replaying the right solve, and the ground
  truth (format, clock, ball, platen and foam against the cache).
- `tools/publish_suite.py --publish` builds in `<native>/suite_staging`, checks it and then replaces the published
  suite (`--target`); `--export-prompts` writes the builder's prompts into a suite (by default `renders/silicone_block_chain/suite_build/pcve_silicone_block_chain_suite/`; the published suite only
  when its path is given with `--out-root`).

## Outputs

- Solves: `renders/silicone_block_chain/rebuild/physics/<case>/`.
- Renders: `renders/silicone_block_chain/rebuild/realism/<case>/` (frames, `video.mp4`, `realism_provenance.json`, and
  `native/` with the copied solve, `packed.blend` and `bake_report.json` when `--native-dir` is used);
  `rebuild/delivered/<case>/` for the delivered look.
- Stored delivery: `renders/silicone_block_chain/accepted/` (`delivery_manifest.json`, `physics_audit.json`, step and
  mesh controls, delivered movies at the recorded paths).
- The published suite is `renders/pcve_suites/pcve_silicone_block_chain_suite/` (pointer in `scene_manifest.json`
  `canonical_suites`); only `tools/publish_suite.py --publish` and `--export-prompts` with this path as `--out-root` write it.
- Ground truth (`pcve_ground_truth/1`, written by `tools/export_ground_truth.py` for a suite being assembled): 96
  frames at t = (i - 1)/24, the fixed camera of the packed scene, the ball (rigid, with its spin), the guided platen
  (bottom centre of the cup object), the flag (hinge axis point, rotation about +y) and the foam block as the centroid
  of its FEM surface nodes (`present: false` in `edit_remove_foam`). For the four whole-clip edits the rigid poses are
  the world matrices of the stored packed scenes, checked against the cache every frame; for the source and the timed
  edit they are computed from the re-solve the way `appearance/scene.py` bakes them, with the hinge point and camera of
  the stored source scene (formulas checked against that scene to 6.5e-7). The frames of the published videos are not
  kept; the suite holds the videos.

## Code layout

- `build_pcve_silicone_block_chain.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`) and `--stage verify`.
- `simulate_silicone_block_chain.py`: CPU solve of one case.
- `render_silicone_block_chain.py`: `--look realism` (default) or `--look delivered`; `--native-dir` renders a solve of
  its own through the bake.
- `edit_vocab.py`: re-exports the DSL vocabulary and bindings of `physics/config.py`.
- `scene_paths.py`: inputs, stored delivery, suite pointer, solves of the published videos, output guard;
  `scene_manifest.json`: suite pointer, camera, video hashes.
- `physics/physics.py`: solver.
- `physics/rig.py`: fixed geometry.
- `physics/config.py`: baseline, edits, timed schedule.
- `appearance/realism.py`: published look (overlay and per-frame cache checks).
- `appearance/bake_native.py`: bake of a cache into the workshop template.
- `appearance/scene.py`: bake into the workshop model and the delivered look.
- `tools/export_ground_truth.py`: ground truth of a suite being assembled.
- `tools/publish_suite.py`: suite assembly in staging and swap.
- `tools/worker.py`: GPU lease (with `scripts/pcve_gpu_reservations.py`) for the delivered look.

## Limitations

- Material, friction and contact values are nominal, not calibrated against a physical rig.
- The L-BFGS-B solve is not bit-reproducible across machines; a timed edit must be paired with a source solved on the
  same machine.
- `appearance/bake_native.py` imports `appearance/scene.py` for its bake and saved-scene audit; baking and rendering
  the published look run on any Linux machine with Blender 4.3.2.
- The stored caches were solved on another machine; the four whole-clip edits were rendered on a GPU with OptiX and
  the source and timed edit on a 48-thread CPU. Bitwise reproduction elsewhere is not verified.
