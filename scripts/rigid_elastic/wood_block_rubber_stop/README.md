# wood_block_rubber_stop

A 2 kg hardwood block slides 1.16 m across a sealed oak floor (mu = 0.20, 2.8 m/s at the start), strikes a
completely unrestrained yellow-and-green kitchen sponge and pushes it across an 8 mm gap into the fixed front leg
of a table; the block bounces back and slides to rest. The scene is a rigid–elastic interaction (rigid blocks,
elastic FEM sponge); every visible motion and deformation is replayed from the solver cache, nothing is keyframed
by hand. Each source video is 4 s at 24 fps (96 frames, 1280×720), played in real time: video frame i shows the
solver state at t = (i-1)/24 s (every 10th 240 Hz state).

## Scene

- Wooden block: 180 × 130 × 95 mm, 2 kg, start centre (-1.30, 0, 0.049) m, 2.8 m/s along the path. Exact collision
  box with a 3 mm render-only edge radius; `dark_wood` texture (2 m tile, toned down, oiled satin) with the grain
  along the block, growth rings and open pores on the saw-cut ends, worn arrises and dings. The added block uses
  the same wood.
- Sponge: 160 × 150 × 120 mm, centre x = 0.03 m, 2 mm above the floor, no constrained vertex. The render shows the
  solver's FEM surface (3 mm render-only edge radius) as yellow open-cell polyurethane foam with pore cells and a
  faint subsurface, with a green non-woven scouring layer.
- Table: a fixed 28 kg table assembly whose front-left leg (105 × 120 × 790 mm collision cuboid) is the contacted
  leg; the table model (`wooden_table_02`) is registered on it at x = 0.118 m.
- Room: a dining-room corner (shell 5.2 × 4.25 m, ceiling 2.6 m, back wall 1.05 m behind the path) with a sealed
  oak plank floor (`wood_floor`, 1.7 m tile, planks along the direction of travel, thin lacquer coat; bump only, the
  contact plane stays at z = 0), painted plaster walls with trowel undulation (`white_plaster_02` under an opaque
  off-white paint coat), 120 mm skirting and a 2.0 × 1.3 m window in the left wall. Props on the floor along the
  back wall, all clear of the swept volume of every case (`KEEPOUT`): `wooden_display_shelves_01`,
  `wooden_stool_02`, `wicker_basket_02` and a modelled stretched canvas leaning on the wall with its back to the
  room (0.60 × 0.45 m unbleached linen from `rough_linen` on 42 × 32 mm pine stretcher bars from `coated_pine` with
  a cross brace, stapled folds).
- Light: daylight only, through the window: sky `kloofendal_48d_partly_cloudy_puresky` (strength 4.5) and an
  afternoon sun lamp (0.53°, 4.5 W/m²); no hidden fill lights.
- Camera (`appearance/room.py` `CAMERA`, fixed): low tripod 0.42 m above the floor, 45 mm lens, 36 mm sensor,
  f/5.6, at (-0.59, -2.30, 0.42) m looking at (-0.59, 0, 0.14) m, focused at (-0.60, 0, 0.06) m. The whole path,
  from the block's start (x = -1.39 m) to the table leg (x = 0.22 m), is in frame with about 0.1 m to spare at each
  end; only the rebound of `edit_fast_block` leaves the frame.
- Rendering (`appearance/render.py`): Blender 4.3.2 Cycles, 256 samples (adaptive threshold 0.01),
  OpenImageDenoise, bounces 10 (diffuse 6, glossy 6), indirect clamp 10, seed 0, motion blur 1/96 s (2.5 solver
  states), persistent data off, AgX Base Contrast, exposure +1.0, mild vignette (0.10) and dispersion (0.002).
  Videos are H.264 yuv420p, CRF 16, constant 24 fps. The appearance code takes the z = 0 floor top, the table-leg
  registration and every moving body from the cache and `scene_spec.json`.

## Physics

- Solver: one frictional IPC scene in libuipc 0.0.28 (CUDA), `physics/simulate.py`.
- Bodies: a fixed z = 0 floor, the fixed table-leg cuboid, one or two affine-body wooden blocks, and the sponge
  meshed as 36,288 Stable Neo-Hookean tetrahedra (24 × 14 × 18 cells; E = 320 kPa, nu = 0.30, 48 kg/m³).
- Friction: block-floor 0.20, sponge-floor 0.64, every other contact (block-sponge, sponge-leg, block-leg) 0.68;
  contact d_hat 0.7 mm.
- Time stepping: dt = 1/1200 s with at most 300 Newton iterations (1/2400 s and 600 Newton iterations for
  `fast_block` and `soft_010`, set by `tools/run_selected.py`); states are saved at 240 Hz over 0-4.0 s.
- The ADD edit runs in the solver as `ADD secondary_wood_block AT PRESET path_midpoint`
  (`edit_vocab.CASE_DSL['add_mid_block']`, kept in the catalog entry's `native_edit_dsl`). The preset centre
  x = -0.635 m is the midpoint of the block and the sponge; in plan view the midpoint is exact, in height it is
  11.5 mm above the added block's centre (block centre z = 0.049 m and sponge centroid z = 0.062 m give 0.0555 m,
  while the shorter added block rests on the floor with its centre at z = 0.044 m).

## Measured motion

Contact time, speed at contact and the end of motion (last state with any block faster than 1 mm/s) are from the
solver reports; rest positions are from the published ground truth (the end-of-motion times agree with it on the
24 fps clock).

| Case | First contact t (s) | Block speed at contact (m/s) | Motion ends (s) | Peak sponge front-face compression (mm) | Block at rest at x (m) |
|---|---|---|---|---|---|
| `source` | 0.504 | 1.82 | 1.22 | 9.5 | -0.600 |
| `edit_fast_block` | 0.300 | 3.62 | 1.86 (the block leaves the frame at about 1.0 s) | 19.8 | -2.44 |
| `edit_heavy_block` | 0.504 | 1.82 | 1.39 | 32.5 | -0.764 |
| `edit_soft_010` | 0.504 | 1.82 | 1.36 | 31.6 | -0.729 |
| `edit_remove_bumper` | 0.600 (table leg) | 1.63 | 0.71 | - | 0.017 |
| `edit_add_mid_block` | 0.196 (added block) | 2.43 | 0.85 | 2.4 | -0.308 (added block -0.141) |

The remaining 2.1-3.3 s of each clip show the settled scene.

## Validation

- Every case was solved twice with the same code, `scene_spec.json` and GPU model. The CUDA solve is not bitwise
  repeatable: block positions differ by at most 0.0002 mm (0.37 mm for `heavy_block`, accumulated over the long
  rebound slide), sponge vertices by at most 0.08 mm (determinism_check.json). Run 1 is the cache the videos replay.
- `tools/audit_cache.py` and `tools/audit_contact_volume.py` pass on all six caches.
- Temporal stability at 480×270 in static regions (wall, shelf, canvas and basket, table legs, floor): mean
  frame-to-frame change 0.006-0.06 grey levels of 255, no flicker.
- `--stage verify` checks per case: video bytes = `scene_manifest.json` = suite_manifest.json = provenance.json,
  the media contract, prompts.json = the builder catalog (and the catalog = what `edit_vocab.py` derives), the
  ground truth (`pcve_ground_truth/1`, video length and clock), solver configuration = `scene_spec.json` = cache
  configuration, both audits passed and bound to the cache bytes, and that the video was rendered from that cache.

## Cases

Builder case ids drop the `edit_` prefix of the published case directories (`edit_soft_010` is `soft_010`).

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | 2 kg block, 2.8 m/s, sponge E = 320 kPa |
| `edit_fast_block` | `SET wood_block.initial_velocity TIMES 1.5` | 4.2 m/s |
| `edit_heavy_block` | `SET wood_block.mass TIMES 10` | 20 kg |
| `edit_soft_010` | `SET open_cell_sponge.young_modulus TIMES 0.1` | 32 kPa |
| `edit_remove_bumper` | `DELETE open_cell_sponge` | sponge absent |
| `edit_add_mid_block` | `ADD secondary_wood_block BETWEEN wood_block AND open_cell_sponge AT MIDPOINT` | 1.25 kg block, 140 × 120 × 85 mm, at rest on the path |

## Assets

- `scenes/wood_block_rubber_stop/native_cache` (derived, 12 files): the solver caches the videos
  replay (`simulation.npz`, simulation_config.json per case).
- `scenes/wood_block_rubber_stop/polyhaven_wooden_table_02_4k` (manual, 5 files): the table.
- `scenes/wood_block_rubber_stop/white_plaster_02_4k` (manual, 4 files): wall plaster.
- `polyhaven/wood_floor` (8 url, 1 manual, 2 derived): floor.
- `polyhaven/dark_wood` (5 url, 1 manual): wooden blocks.
- `polyhaven/rough_linen` (10 url, 1 manual, 4 derived) and `polyhaven/coated_pine` (5 url, 1 manual): canvas.
- `polyhaven/wooden_display_shelves_01`, `polyhaven/wooden_stool_02`, `polyhaven/wicker_basket_02` (5 url, 1
  manual each): props along the back wall.
- `polyhaven/kloofendal_48d_partly_cloudy_puresky` (url): sky.

```bash
python3 scripts/download_assets.py --scene wood_block_rubber_stop
python3 scripts/download_assets.py --scene wood_block_rubber_stop --check
```

`PCVE_ASSETS_DIR` moves the asset root.

## Requirements

- Linux with an NVIDIA CUDA GPU for the solve; libuipc 0.0.28 from `tools/ipc_probe_deps`; Python
  `.venv-rigid-elastic/bin/python3.10` with NumPy, SciPy and trimesh (override `--python-runtime`).
- Blender 4.3.2 (`tools/blender-4.3.2-linux-x64/blender` when present, else `pcve_assets.blender()`; override
  `--blender-bin`) on a GPU or the CPU (`--device cpu`).
- FFmpeg from `PATH` or `PCVE_FFMPEG`.
- GPU binding: `scene_paths.launch` binds the GPU given by `--gpu-uuid` (index or UUID; `auto` = first idle) to
  `CUDA_VISIBLE_DEVICES` after checking that it is idle; `PCVE_ALLOW_SHARED_GPU=1` queues several of your own jobs
  on one GPU.

## Commands

Run from the repository root. All three entries also accept the unified options (`--help`, `--describe`,
`--dry-run`, `--out-root`, `--python`, `--blender`, `--gpu`, `--threads`).

```bash
S=scripts/rigid_elastic/wood_block_rubber_stop

# Verify the published suite; check the registered assets; catalog and prompts
python3 $S/build_pcve_wood_block_rubber_stop.py --stage verify
python3 $S/build_pcve_wood_block_rubber_stop.py --stage prepare
python3 $S/build_pcve_wood_block_rubber_stop.py --list-cases
python3 $S/build_pcve_wood_block_rubber_stop.py --list-edits
python3 $S/build_pcve_wood_block_rubber_stop.py --show-prompts add_mid_block
python3 $S/build_pcve_wood_block_rubber_stop.py --export-prompts \
    --out-root renders/pcve_suites/pcve_wood_block_rubber_stop_suite --dry-run

# 4.0 s solve of one case on one GPU
python3 $S/simulate_wood_block_rubber_stop.py --case source \
    --out renders/wood_block_rubber_stop/<run>/sim/source --gpu-uuid <GPU UUID>

# Audits of the new cache (CPU) and the two-run determinism check
.venv-rigid-elastic/bin/python $S/tools/audit_cache.py --case-dir renders/wood_block_rubber_stop/<run>/sim/source
.venv-rigid-elastic/bin/python $S/tools/audit_contact_volume.py --case-dir renders/wood_block_rubber_stop/<run>/sim/source
.venv-rigid-elastic/bin/python $S/tools/compare_native_prefix.py --new renders/wood_block_rubber_stop/<run>/sim/source \
    --old assets/scenes/wood_block_rubber_stop/native_cache/source
python3 $S/build_pcve_wood_block_rubber_stop.py --stage determinism --rerun <folder of the second solve>

# 96-frame render (default --cache: the registered cache of the case) on a GPU, or on the CPU
python3 $S/render_wood_block_rubber_stop.py --case source \
    --out renders/wood_block_rubber_stop/<run>/render/source --gpu-uuid <GPU UUID>
python3 $S/render_wood_block_rubber_stop.py --case source \
    --out renders/wood_block_rubber_stop/<run>/render/source_cpu --device cpu --render-threads <N>

# Build a new suite (pcve_* formats, ground truth) and verify it
python3 $S/build_pcve_wood_block_rubber_stop.py --stage publish \
    --suite-root renders/wood_block_rubber_stop/<run>/pcve_wood_block_rubber_stop_suite
```

`--no-encode` on the render entry writes the 96 PNG frames only; `--stage encode --cases <case>` then encodes the
frames under the render root named in `scene_manifest.json` (`native_outputs.render_root`).

## Outputs

- Solves and renders go to the `--out` directory, which may not lie under `scripts/`; use
  `renders/wood_block_rubber_stop/<run>/`. Launch receipts and the encoder copy used inside Blender live in
  `.runtime/wood_block_rubber_stop/`.
- The solver configurations and audits behind the published videos are in
  `renders/wood_block_rubber_stop/accepted/sim/<case>/`, the render records (`render_report.json`) in
  `renders/wood_block_rubber_stop/accepted/render/<case>/`; they are not registered in `assets.json`.
- The published suite is `renders/pcve_suites/pcve_wood_block_rubber_stop_suite/` (`scene_manifest.json`
  `canonical_suites`). `--stage publish` builds a new suite at `--suite-root` (default:
  `renders/wood_block_rubber_stop/suite_build/pcve_wood_block_rubber_stop_suite/`; `tools/publish_suite.py build`
  never overwrites an existing suite) and does not copy the prompt history or the other provenance records of the
  published cases. `--stage prompts` writes the builder's prompts into the suite at
  `--suite-root` (default: the same `suite_build` folder); `--stage verify` reads the published suite unless
  `--suite-root` is given, and `--export-prompts` writes the prompts into a suite (by default `renders/wood_block_rubber_stop/suite_build/pcve_wood_block_rubber_stop_suite/`; the published suite only
  when its path is given with `--out-root`).

## Code layout

- `build_pcve_wood_block_rubber_stop.py`: edit catalog (`PCVE_SOURCE` with its `editable_objects` roster checked
  against `edit_vocab.py`, and `PCVE_EDITS`, equal to the published prompts.json); stages verify, prepare, encode,
  determinism, publish, prompts.
- `simulate_wood_block_rubber_stop.py`: libuipc solve of one case on one bound GPU.
- `render_wood_block_rubber_stop.py`: Blender replay of one cache.
- `edit_vocab.py`: edit DSL vocabulary and per-case parameters; SET and DELETE prompts come from the shared DSL
  renderer, the ADD prompts from the BETWEEN line.
- `scene_paths.py`: cache and runtime paths, output rule, runtimes, GPU launch.
- `scene_spec.json`: baseline physics, cases, timing.
- `scene_manifest.json`: published suite pointer, solver output locations, cache and video hashes.
- `physics/simulate.py`: libuipc FEM, ABD and frictional IPC solve.
- `appearance/render.py`: Blender replay of the cache (blocks, FEM sponge, materials, render settings, report).
- `appearance/room.py`: room shell, scanned materials and props, window daylight, fixed camera.
- `tools/run_selected.py`: per-job guard (fresh output, one GPU, execution record).
- `tools/audit_cache.py`: numerical cache audit, writes independent_physics_audit.json.
- `tools/audit_contact_volume.py`: penetration audit, writes contact_volume_audit.json.
- `tools/compare_native_prefix.py`: comparison of two caches.
- `tools/export_ground_truth.py`: per-frame ground truth of one case inside Blender, `pcve_ground_truth/1`
  through `scripts/pcve_ground_truth.py`. Video frame i is solver state 10*(i-1); the blocks are rigid bodies
  (recorded ABD centre, nearest rotation), the sponge a deformable body (centroid and bounding-box dimensions of
  its FEM surface), the camera comes from the case's `scene.blend`, no resampling; the table leg is left out.
- `tools/publish_suite.py`: encode, two-run determinism check, suite build, prompt export (shared export) and
  ground truth of a new suite (`ground-truth --suite DIR`).

## Limitations

- Material values are effective benchmark values, not a product calibration.
- The CUDA solve is not bitwise repeatable (see Validation).
- Each published case was rendered entirely on one device: `source` on the CPU (48 threads, about 2 h),
  `fast_block`, `heavy_block`, `soft_010` and `add_mid_block` on RTX 4090 GPUs (OptiX, 14-17 min each),
  `remove_bumper` on an RTX 3090 GPU (OptiX), all encoded with the same ffmpeg settings. The published results were
  computed on other Linux GPU machines; bitwise reproduction elsewhere is not verified.
