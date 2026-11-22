# spring_scale_weight_drop

A 100 g brass calibration weight is released at rest 85 mm above the felt pad of a pan that hangs from a guided
carriage under a 28-turn steel extension spring on a laboratory stand. The weight lands on the pad, the spring
stretches, and the carriage with its pointer oscillates along the scale and settles under the added load. The
scene is a rigid–elastic interaction (rigid weight and carriage, elastic distributed spring). Each source video
is 4 s at 24 fps (96 frames, 1280×720), played at normal speed: video frame i shows the solver state at
t = (i-1)/24 s.

## Scene

- Instrument: cast stand base with rubber feet, stainless upright and brackets, a guided carriage with a
  spun-aluminium pan (radius 72 mm, wall height 15 mm) and felt pad (pad top z = 0.550 m), an enamel scale with a
  red pointer, and the spring hanging from a coil top at z = 0.845 m. Blender rebuilds the instrument from the
  solver geometry; the spring is a tube along the solver's coil nodes, animated per frame from the cache.
- Weight: brass calibration weight, 0.100 kg, stamped "100 g", bottom at z = 0.635 m (85 mm above the pad), at
  rest at t = 0.
- Camera (fixed in every case; each render_report.json records its world matrix): at (0.74, -1.82, 0.94) m aimed
  at (0.025, 0, 0.50) m, 40 mm lens on a 36 mm sensor, f/9, focused at the pad (0, 0, 0.55) m.
- Base look (`appearance/render_spring.py` with `appearance/render_helpers.py`): a laboratory bench
  (`wood_table_001` and `fine_grained_wood` textures) with a pencil, a ruler and a notebook, lit by the
  `university_workshop` HDRI (strength 0.45) and three area lights; Blender 4.3.2 Cycles, AgX Medium High
  Contrast, exposure -0.65, denoising, no motion blur, 192 samples by default, OptiX on one GPU. It also writes
  per-frame instance-id masks (spring 1, weight 2, carriage and pan 3) from the IndexOB pass.
- Published look (`appearance/realism.py`): an overlay that runs the base renderer with
  a hook (`render_spring.OVERLAY`) after the base lights and compositor, so caches, camera, keyframes
  and instance masks stay those of the base look. It hides the flat backdrop wall and backboard and builds a
  daylit school physics room: a window wall on the left, mottled walls, an `old_linoleum_flooring_01` floor, a
  bench cabinet with plinth, a glazed tiled splashback with PVC cable trunking and outlets, handling wear on the
  bench and instrument materials, a retro multimeter and a magnifying glass outside the instrument's keep-out box,
  and fine bench dust. Light: the base area lights drop to 10 %, an afternoon sun (strength 12, 1° disc, warm)
  shines through the window with a sky-fill area light, world strength 0.55, exposure +0.25, AgX Medium High
  Contrast, lens finish (vignette 0.13, dispersion 0.003). The published videos use 128 samples and are encoded
  with libx264 preset medium, CRF 16, yuv420p, +faststart at 24 fps (encoding_receipt.json).

## Physics

`physics/simulate_spring.py` solves every case on the CPU with Numba and a fixed-step RK4 integrator,
dt = 1/48000 s, for 4 s. The baseline is `BASELINE` in `physics/scene.py`; the edits come from `edit_vocab.py`.

- The spring is distributed and massive: 28 axial turn segments, each with its own mass (total active spring mass
  23.0 g) and axial force. Open coils follow the helical-spring relation E → G → k (small-helix-angle torsion
  theory); closed coils carry the initial tension and coil contact. Internal segment damping acts on the segment
  rates.
- The carriage with its pan is one guided rigid mass at the lower end of the spring with viscous guide damping.
  The weight falls freely and meets the pad through a passive unilateral contact with compression-only damping.
  All contacts are equal and opposite; there is no authored motion.
- The common initial pose is the static equilibrium of the spring under the carriage and pan; it is identical in
  every case, and edits do not re-tare it (the soft-spring edit starts from the same pose and relaxes physically).
- The state vector y (28 turn displacements and velocities, the weight's drop and velocity, the dissipation
  integral) is cached at 24 Hz: 97 states at t = 0 to 4 s. A 1 kHz dense record keeps travel, weight drop, contact
  and stop forces, mechanical energy, dissipation and pad compression.

| Parameter (`BASELINE`) | Value |
| --- | --- |
| weight mass, drop height above the pad | 0.100 kg, 85 mm (pad top z = 0.550 m, weight bottom z = 0.635 m) |
| spring: Young's modulus, Poisson ratio, density | 200 GPa, 0.30, 7850 kg/m³ |
| spring: wire diameter, mean coil diameter, active turns | 1.1 mm, 35 mm, 28 |
| spring: initial tension, closed-turn contact stiffness, internal damping | 0 N, 50 kN/m, 0.40 N·s/m |
| derived: shear modulus, axial rate, active wire length | 76.9 GPa, 11.73 N/m, 3.08 m |
| carriage with pan, guide damping | 0.065 kg, 0.30 N·s/m |
| pad contact stiffness, pad compression damping | 12 kN/m, 22 N·s/m |
| pan radius, pan wall height, coil top z | 72 mm, 15 mm, 0.845 m |
| travel-stop collar | solver input of every case with `stop_present` false (no case adds it) |

The whole-clip edits and the deletion are independent solves from the common initial pose
(`edit_vocab.CASE_DSL`). The timed edit (`edit_vocab.TIMED_DSL`) is solved natively: `solve_timed` restores the
complete state vector y of source frame 48 (t = 47/24 s, RK4 step 94000) from the source cache, sets the weight's
mass to 0.2 kg and integrates on with the same step to 4 s.

## Measured motion

| Case | Max pan travel | Pan travel at 4 s | First contact |
| --- | --- | --- | --- |
| `source` | 173.1 mm | 81.9 mm | 0.132 s |
| `edit_heavy` | 337.4 mm | 151.2 mm | 0.132 s |
| `edit_soft` | 400.7 mm | 236.5 mm | 0.164 s |
| `edit_damped` | 118.9 mm | 83.7 mm | 0.132 s |
| `edit_remove_weight` | 0 | 0 | - |
| `edit_heavy_at_frame_48` | 214.2 mm | 151.7 mm | 0.132 s |

Pan travel at frames 48/60/96: timed edit 105.6/214.0/148.8 mm, source 105.6/75.7/80.9 mm, whole-clip
`edit_heavy` 93.6/222.0/147.0 mm.

## Validation

- Energy balance error is below 2e-6 of the drop energy in every case (source 5.7e-7).
- Free-fall contact happens at 0.132 s against the analytic 0.1316 s.
- In the source, halving the time step changes the sampled pan and weight positions by at most 1.1e-5 m.
- Frames 1-47 of the timed edit are the source cache itself (asserted bit for bit); the hand-off error is 0.
- `simulate_spring_scale_weight_drop.py` without an output directory re-solves and compares with the cached
  states (difference below 1e-9 required).
- `--stage verify` checks the published suite (videos, prompts, ground truth) against the edit catalog,
  `scene_manifest.json` and the solver caches, and re-exports and compares the ground truth of every case.

## Cases

Builder case ids drop the `edit_` prefix of the published case directories (`edit_heavy_at_frame_48` is
`heavy_at_frame_48`).

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | weight 0.1 kg, spring E = 200 GPa, guide damping 0.3 N·s/m |
| `edit_heavy` | `SET weight.mass TIMES 2` | `weight_mass_kg` 0.1 → 0.2 |
| `edit_soft` | `SET spring.young_modulus TIMES 0.5` | `spring_young_modulus_pa` 200 → 100 GPa |
| `edit_damped` | `SET guide.damping TIMES 4` | `guide_damping_ns_m` 0.3 → 1.2 |
| `edit_remove_weight` | `DELETE weight` | `weight_present` 1 → 0 |
| `edit_heavy_at_frame_48` | `SET weight.mass TIMES 2 AT FRAME 48` | `weight_mass_kg` 0.1 → 0.2 from frame 48 (t = 47/24 s) |

The weight in the video keeps its "100 g" stamp, so a mass change is not visible.

## Assets

- `scenes/spring_scale_weight_drop/university_workshop` (url): HDRI of the base look.
- `scenes/spring_scale_weight_drop/wood_table_001` (url): bench top texture.
- `scenes/spring_scale_weight_drop/fine_grained_wood` (2 url, 1 manual): wood texture of the bench and stand.
- `scenes/spring_scale_weight_drop/props` (manual, 2 files): pencil and ruler props of the bench.
- `scenes/spring_scale_weight_drop/realism` (14 url, 1 derived): floor, multimeter and magnifying glass of the
  published look.

```bash
python3 scripts/download_assets.py --scene spring_scale_weight_drop
python3 scripts/download_assets.py --scene spring_scale_weight_drop --check
```

## Requirements

- Simulation: a Python 3.10 with NumPy and Numba, CPU only.
- Rendering: Linux, Blender 4.3.2, one idle NVIDIA GPU with OptiX (the render entry leases it through
  `tools/worker_run.py`).
- ffmpeg with libx264 for encoding.

## Commands

Run from the repository root with a Python that has NumPy and Numba.

```bash
S=scripts/rigid_elastic/spring_scale_weight_drop

# Verify the published suite against the catalog, scene_manifest.json and the solver caches
python3 $S/build_pcve_spring_scale_weight_drop.py --stage verify

# Cases, edit catalog and prompts
python3 $S/build_pcve_spring_scale_weight_drop.py --list-cases
python3 $S/build_pcve_spring_scale_weight_drop.py --list-edits
python3 $S/build_pcve_spring_scale_weight_drop.py --show-prompts heavy_at_frame_48

# Re-solve the five whole-clip cases and compare with the cache, then the timed edit
python3 $S/simulate_spring_scale_weight_drop.py --case all
python3 $S/simulate_spring_scale_weight_drop.py --case heavy_at_frame_48

# Solve into a new directory (cases/<case>/native_dynamics.npz, physics.json, ...)
python3 $S/simulate_spring_scale_weight_drop.py --case heavy_at_frame_48 --out-root renders/spring_scale_weight_drop/rebuild/physics
python3 $S/build_pcve_spring_scale_weight_drop.py --stage simulate --cases source heavy --out-root renders/spring_scale_weight_drop/rebuild/physics

# Render one case in the published look (default) on one idle GPU; --look base renders the base look
python3 $S/render_spring_scale_weight_drop.py --case source --gpu <GPU UUID> --out-root renders/spring_scale_weight_drop/rebuild/render/source
python3 $S/render_spring_scale_weight_drop.py --case heavy_at_frame_48 --input-root renders/spring_scale_weight_drop/rebuild/physics \
    --out-root renders/spring_scale_weight_drop/rebuild/render/heavy_at_frame_48

# Ground truth of every case into a new directory
python3 $S/tools/export_ground_truth.py --out renders/spring_scale_weight_drop/rebuild/ground_truth

# Solver module directly, with the time-step convergence check
PYTHONPATH=scripts:$S python3 -m physics.simulate_spring --case source --convergence --out renders/spring_scale_weight_drop/rebuild/convergence
```

All three entries accept the unified `--help`, `--describe`, `--dry-run`, `--out-root`, `--python`, `--blender`,
`--gpu` and `--threads`; `--native-help` shows the scene options (`--out-root` maps to `--output-dir`, `--gpu` to
`--gpu-uuid`).

## Outputs

- Outputs must be new directories outside `scripts/`, the asset store and the published suite
  (`scene_paths.output_path` enforces this). The default parent is `renders/spring_scale_weight_drop/rebuild`;
  solver work files (the Numba cache) go to `renders/spring_scale_weight_drop/work`, GPU launch records and job
  logs to `renders/spring_scale_weight_drop/launches/<job>/`.
- Solves write `<out>/cases/<case>/` (native_dynamics.npz, physics.json, ...).
- Renders write frames, render_report.json, instance masks and the encoded video into the case directory.
- The solver caches of the whole-clip cases (native_dynamics.npz and physics.json per case; the source case also
  keeps its camera) are in `renders/spring_scale_weight_drop/delivery/accepted/cases/<case>/`.
  `physics.scene.OUT`, the root the solver writes and the base renderer reads, is that directory unless
  `PCVE_SPRING_SCALE_INPUT` names another root; the render entry sets it from `--input-root`.
- The published suite is `renders/pcve_suites/pcve_spring_scale_weight_drop_suite/`;
  `cases/edit_heavy_at_frame_48/native_metadata/` holds the timed solve (cache, solver report, state hand-off).
  `--export-prompts` with this path as `--out-root` writes the builder's prompts into it; no other command
  writes there.

## Code layout

- `build_pcve_spring_scale_weight_drop.py`: edit catalog (`PCVE_SOURCE` / `PCVE_EDITS`, equal to the published
  prompts.json; edit prompts are `pcve_edit_dsl.make_prompts` output for `edit_vocab.VOCAB`), verify and stage
  dispatch.
- `simulate_spring_scale_weight_drop.py`: reproduces and compares the cached solves, or solves into a new
  directory.
- `render_spring_scale_weight_drop.py`: renders one case on one leased GPU (published look by default).
- `edit_vocab.py`: edit vocabulary, DSL bindings, whole-clip and timed cases, `parameters(case)`.
- `scene_paths.py`: repository locations and the output guard.
- `scene_manifest.json`: published suite pointer and video hashes.
- `physics/scene.py`: baseline parameters, derived spring constants, data locations; `write_spec` writes the
  scene_spec.json of a solve.
- `physics/simulate_spring.py`: Numba RK4 solver, whole-clip and timed solves.
- `appearance/render_spring.py`, `appearance/render_helpers.py`: base-look reconstruction and render.
- `appearance/realism.py`: overlay of the published look.
- `tools/worker_run.py`: checks that the GPU is idle, takes a per-GPU lease, binds the GPU UUID and runs one
  render job detached with a launch record.
- `tools/export_ground_truth.py`: `pcve_ground_truth/1` from the solver caches. Frame i is solver state i-1; the
  weight (centre of its machined envelope, absent in `edit_remove_weight`) and the pan (centre of the felt-pad
  top) are rigid vertical translations; the spring is the centroid of the rendered helix tube (`coil_vertices` of
  `appearance/render_spring.py`, read without Blender) with its rest bounding box as dimensions; the camera is the
  fixed camera of the published source render report.

## Limitations

- Contact and damping values are effective parameters, not a calibrated instrument.
- `appearanc- `render_helpers.choose_gpu` asks the shared GPU policy; `appearance/realism.py` replaces that decision with the
  recorded GPU approval (`render_helpers.GPU_POLICY_OVERRIDE`). The render entry itself only requires Linux.
clip caches reproduce bit for bit on a Linux machine with Python 3.10, NumPy 1.26.4 and Numba 0.65.1.
  The published videos were rendered with OptiX on NVIDIA RTX 4090 and RTX 3090 GPUs; bitwise reproduction of the
  frames on other machines is not verified.
