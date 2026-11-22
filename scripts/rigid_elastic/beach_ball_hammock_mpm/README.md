# beach_ball_hammock_mpm

A rigid beach ball drops into an elastic hammock strung between two posts on a beach, sinks into it
and settles. This is a rigid–elastic scene: the hammock is a Taichi MLS-MPM elastic body and the ball
is a rigid body that receives the opposite contact impulse from the MPM grid; Blender renders the
result (Blender cloth is not used). The source video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Hammock: elastic body with pinned ends; a 0.15 m thick numerical block of 7100 particles whose cached
  mid-surface drives the visible canvas. Before frame 1 it settles under gravity for a damped pre-roll
  (`--pre-roll-seconds`, 4 s by default, 12 s in the published cases).
- Ball: radius 0.16 m, mass 0.25 kg, dropped at XY (0.80, −8.92) m near the trough of the settled
  hammock with initial velocity (0, 0, −1.0) m/s. Sideways motion is free (in the source it moves at
  most 1.1 cm sideways).
- Base scene: only the hammock mesh, the ball and the camera are taken from
  `assets/scenes/beach_ball_hammock_mpm/beach_ball_hammock_base.blend`; `appearance/look_beach.py`
  with `appearance/appearance.json` builds everything else (`--appearance-json` names another file).
- Beach: the ground is the `aerial_sand` scan (trampled dry sand, 15 m tile, two rotated tilings blended
  by noise) with true displacement through Cycles adaptive subdivision within 30 m of the camera
  (`terrain.detail_max_distance_m`) and bump only beyond. The beach rises 0.45 m from the waterline over
  8 m; the sand under the hammock is at z ≈ 2.40 m, about 0.7 m below the hammock centre.
- Sea and background: the sea lies beyond the hammock (`terrain.sea_side = "away_from_camera"`) and is
  frozen at its frame-1 state (`sea.animate = false`). Nine coconut palms (one behind the camera, placed
  by where its crown's shadow lands, `shadow_target_xy`), three beach umbrellas, five striped and two
  wooden deck chairs, five coconuts, a dry stick and a straw hat stand on the sand (`appearance.props`,
  placed by world position `xy`). No prop enters `keep_out_xy`, the plan-view area around the hammock
  and the ball's fall; the look stops if a prop is still animated (the striped deck chair's folding
  cycle is held at frame 1 and removed). Nothing moves except the ball and the hammock.
- Hammock hardware: striped cotton canvas (0.45 m tile, 2.5 mm thick) whose ends are gathered into rope
  whippings; twisted ropes continue along the end tangent of the fabric to two weathered timber posts
  (15–16 cm diameter, 2.15 m above and 0.6 m in the sand), take three turns and end in a hanging tail.
  The pinned ends do not move, so this hardware is static.
- Ball look: the base scene's geometry and panel colours with a glossy PVC finish (coat, slight
  translucency).
- Light: only the `spiaggia_di_mondello` HDRI, its sun (25° elevation) rotated to azimuth 280°, behind
  and to the left of the camera; no hidden lights.
- Camera (`camera.override`): 2.2 m above the sand, 4° below level, 40 mm lens, 2.2 m closer to the
  hammock than the base scene's camera on the same heading, f/8 focused on the hammock. The look checks
  that the rendered camera equals this override.
- Render: Cycles, 384 samples (adaptive, threshold 0.008), OpenImageDenoise, AgX Medium High Contrast,
  exposure −0.45, motion blur with a 0.25-frame shutter, persistent data off, fixed sampling seed
  (`render.animated_seed = false`), 1280×720, 24 fps, 96 frames.
- Visible canvas: the solver's hammock is a 0.15 m block and the cache holds its mid-surface. The ball
  rests on the block's upper boundary, half the thickness (0.075 m) plus the grid contact margin
  (contact radius R + 0.6 dx). The resting distance between ball surface and mid-surface is 0.160 m at
  15 kPa and 1.5 kPa (margin 0.085 m) and 0.176 m at 70 kPa (margin 0.1006 m). The visible canvas is a
  finer open sheet bound to the cached shell with a Surface Deform modifier (the shell is invisible to
  all rays), offset along its normal by half the thickness plus that margin and faded as
  1 − (s/s_end)² towards the pinned ends. Where the offset surface would pass into the ball (up to 3.2 cm
  at the hardest impact) the canvas is laid onto the ball surface, blended over 1.6 cm. Ball surface to
  canvas mid-plane is about 4.5 mm at rest (0.6 mm at 1.5 kPa), under 1 mm at impact, and up to 2.5 cm
  (15 kPa) or 10 cm (70 kPa) while the ball rebounds; each case lists its per-frame values in
  output/appearance_report.json. Only the visible mesh is changed, not the simulation.

## Physics

- Solver: Taichi MLS-MPM on the CPU, fixed-corotated elastic material, Young's modulus 15 kPa, Poisson
  ratio 0.30, density 6 kg/m³, 64³ grid, 100 substeps per frame (dt = 1/2400 s), 96 frames at 24 fps.
  Frame i of the cache and the video is the state at t = (i − 1)/24 s.
- Coupling: the ball is a rigid body; grid nodes within the contact radius R + 0.6 dx exchange impulse
  with it, and the ball receives the opposite impulse.
- Model settings shared by all published cases (`SHARED_FLAGS` in `edit_vocab.py`):
  `--ball-mass 0.25 --ball-vz -1.0 --visible-damping 0.9995 --strain-limit-min 0.80 --strain-limit-max 1.20 --inplane-tether-hz 4.0 --inplane-tether-damping-ratio 0.35 --end-transition-width 0.45 --end-tether-hz 8.0 --end-tether-damping-ratio 0.60 --pre-roll-seconds 12 --pre-roll-damping 0.998 --max-lateral-displacement 0.20`.
  The strain limits and the in-plane tether approximate a woven hammock's limited stretch and keep the
  MPM body from folding at high impact energy; the end tether smooths the first free particle rows next
  to the pinned ends.
- Threads: `--cpu-threads 0` (default) uses all cores; the particle-to-grid sums then use float atomics
  in a varying order, so two runs of one case differ by up to about 0.3 mm. `--cpu-threads 1` makes a
  run bit-reproducible.
- Timed edit: `--young-modulus-after` and `--young-modulus-change-time` change the stiffness at the given
  time and keep the current particle positions, velocities and deformation gradients. With
  `--source-branch-work-dir DIR` a timed edit also writes the unedited source: the simulator copies the
  complete state (particle positions, velocities, affine matrices, deformation gradients, ball position
  and velocity) at the start of the change frame, runs the edit on, restores the copy and runs the
  source on into `DIR`.
- Every run records its exact parameter values in edit_manifest.json and
  mpm_flat_drop_final_metrics.json.

## Measured motion

Deflection is the largest downward displacement of the hammock centre. The ball first touches the
hammock at frame 13 (frame 14 at 1.5 kPa).

| Case | Deflection | Settles |
|---|---|---|
| `source` | 0.030 m | frame 47 |
| `edit_hammock_young_1500pa` | 0.090 m | frame 70 |
| `edit_young_15000_to_1500pa_at_2_5s` | 0.177 m | still moving at frame 96 |
| `edit_young_70000pa_hard` | 0.014 m | frame 62 |

80 kPa and above is unstable at 100 substeps. Further runs with the same simulator, outside the
published suite:

- Without the shared flags: `--ball-vz -9.0 --max-lateral-displacement 0.10` gives a visibly deeper
  dip; `--ball-mass 0.05 --max-lateral-displacement 0.06` a much shallower dip;
  `--young-modulus 60000 --max-lateral-displacement 0.06` a shallower dip.
- With `--young-modulus 15000 --visible-damping 0.9995 --strain-limit-min 0.80 --strain-limit-max 1.20 --inplane-tether-hz 4.0 --inplane-tether-damping-ratio 0.35 --max-lateral-displacement 0.20`:
  1 m/s and 0.25 kg give 0.030 m; 20 m/s gives 0.119 m and settles by frame 33; 1.35 kg gives 0.119 m
  and settles by frame 44; 2 kg gives 0.167 m and settles by frame 36, but the first free particle row
  next to the pinned ends folds like a hinge. Adding the end tether flags to both runs gives 0.166 m at
  2 kg, settling by frame 48, 0.9 cm sideways motion. 2.2 kg and 2.4 kg fail the sideways-motion or
  settling checks.

## Validation

- The simulator rejects a run whose hammock surface drifts by 1 mm or more before contact, that moves
  sideways more than `--max-lateral-displacement`, that does not settle within the clip (12 still
  frames) or that produces non-finite values. The settling check applies only to runs without a timed
  stiffness change; the timed edit does not settle within 4 s (a 15 → 10 kPa timed edit settles by
  frame 84).
- The render stage checks the saved scene against the metrics (`appearance/validate_mpm_blend.py`).
- The verify stage checks the video format (1280×720, 24 fps, 96 frames) with
  `scripts/pcve_verify_video.py`.

## Cases

Each case is one output root; the simulator flags after `--simulation-args` (the shared flags above plus
the case flags below) select it.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | hammock Young's modulus 15 kPa (`--variant-id source_young_15000pa_preroll12 --young-modulus 15000`) |
| `edit_hammock_young_1500pa` | `SET hammock.young_modulus TIMES 0.1` | 1.5 kPa from frame 1 (`--variant-id edit_hammock_young_1500pa --young-modulus 1500`) |
| `edit_young_15000_to_1500pa_at_2_5s` | `SET hammock.young_modulus TIMES 0.1 AT FRAME 61` | 15 kPa, then 1.5 kPa from frame 61 (t = 2.5 s) (`--variant-id edit_young_15000_to_1500pa_at_2_5s --young-modulus 15000 --young-modulus-after 1500 --young-modulus-change-time 2.5`) |
| `edit_young_70000pa_hard` | `SET hammock.young_modulus TO 70000` | 70 kPa from frame 1 (`--variant-id edit_young_70000pa_hard --young-modulus 70000`) |

`source` and `edit_young_15000_to_1500pa_at_2_5s` come from one `--cpu-threads 1` run with
`--source-branch-work-dir`, so frames 1–61 of the two caches are identical; a separate single-thread run
of the source alone gives the same cache bit for bit. The 1.5 kPa and 70 kPa cases are separate runs on
all cores.

## Assets

| assets.json key | Type | Use |
|---|---|---|
| `scenes/beach_ball_hammock_mpm` | derived (1 file, not distributed) | base scene: hammock mesh, ball and camera |
| `polyhaven/spiaggia_di_mondello` | url | sky and sun HDRI |
| `polyhaven/aerial_sand` | url | beach sand colour, roughness, displacement |
| `ambientcg/Fabric071` | url | striped hammock canvas |
| `ambientcg/Rope001` | url | hammock ropes and end whipping |
| `ambientcg/Wood062` | url | timber posts |
| `polyhaven/dry_branches_medium_01` | mixed (4 url, 1 derived) | dry stick on the sand |
| `blenderkit/palm_tree_medium_dense` | manual (1 manual, 1 derived) | palm trunks and frond shadows |
| `blenderkit/blue_striped_beach_chair` | manual (1 manual, 1 derived) | striped deck chair |
| `blenderkit/scanned_coconut` | manual (1 manual, 1 derived) | coconuts |
| `blenderkit/straw_hat` | manual (1 manual, 1 derived) | straw hat by the left post |
| `blenderkit/beach_umbrella` | manual (1 manual, 1 derived) | beach umbrellas |
| `blenderkit/beach_folding_chair` | manual (1 manual, 1 derived) | wooden deck chairs |

```bash
python3 scripts/download_assets.py --scene beach_ball_hammock_mpm          # download and check sha256
python3 scripts/download_assets.py --scene beach_ball_hammock_mpm --check  # check only
```

Files are stored under `assets/` (`PCVE_ASSETS_DIR` moves the root); scene-only files are in
`assets/scenes/beach_ball_hammock_mpm/`. The base scene has no public download, so `--check` reports it
missing and the scene cannot be rebuilt without it. Licences are recorded per entry in `assets.json`.

## Requirements

- Linux. Taichi runs on the CPU; an NVIDIA GPU (OptiX or CUDA) speeds up rendering, the CPU also works.
- Python environment `.venv-taichi-mpm/` at the repository root (taichi 1.7.3, numpy 2.0.2):
  ```bash
  python3 -m venv .venv-taichi-mpm
  .venv-taichi-mpm/bin/pip install -r scripts/rigid_elastic/beach_ball_hammock_mpm/requirements.txt
  ```
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then `~/.local/opt/blender-*/blender`;
  `--blender` overrides it.
- `ffmpeg` and `ffprobe`.

## Commands

Run from the repository root. Each case needs a fresh output root. The builder runs four stages:
`prepare` (Blender extracts the hammock surface from the base scene), `simulate` (Taichi), `render`
(Blender) and `verify` (video check); `--stage` runs one of them in a root created with the same
`--simulation-args`, and existing products are never overwritten. `--simulation-args` must be the last
option and cannot set `--work-dir` or `--reuse-cache`.

```bash
SHARED="--ball-mass 0.25 --ball-vz -1.0 --visible-damping 0.9995 --strain-limit-min 0.80 --strain-limit-max 1.20 --inplane-tether-hz 4.0 --inplane-tether-damping-ratio 0.35 --end-transition-width 0.45 --end-tether-hz 8.0 --end-tether-damping-ratio 0.60 --pre-roll-seconds 12 --pre-roll-damping 0.998 --max-lateral-displacement 0.20"

# plan, then run all four stages of one case
.venv-taichi-mpm/bin/python scripts/rigid_elastic/beach_ball_hammock_mpm/build_pcve_beach_ball_hammock_mpm.py \
    --source-blend assets/scenes/beach_ball_hammock_mpm/beach_ball_hammock_base.blend \
    --out-root renders/beach_ball_hammock_mpm/edit_young_70000pa_hard --dry-run \
    --simulation-args $SHARED --variant-id edit_young_70000pa_hard --young-modulus 70000
.venv-taichi-mpm/bin/python scripts/rigid_elastic/beach_ball_hammock_mpm/build_pcve_beach_ball_hammock_mpm.py \
    --source-blend assets/scenes/beach_ball_hammock_mpm/beach_ball_hammock_base.blend \
    --out-root renders/beach_ball_hammock_mpm/edit_young_70000pa_hard --gpu <GPU index or UUID> \
    --simulation-args $SHARED --variant-id edit_young_70000pa_hard --young-modulus 70000
```

The source and the timed edit come from one simulation that writes both work directories:

```bash
SRC="--variant-id source_young_15000pa_preroll12 --young-modulus 15000"
EDIT="--variant-id edit_young_15000_to_1500pa_at_2_5s --young-modulus 15000 --young-modulus-after 1500 --young-modulus-change-time 2.5"
.venv-taichi-mpm/bin/python scripts/rigid_elastic/beach_ball_hammock_mpm/build_pcve_beach_ball_hammock_mpm.py \
    --source-blend assets/scenes/beach_ball_hammock_mpm/beach_ball_hammock_base.blend \
    --out-root renders/beach_ball_hammock_mpm/source --stage prepare --simulation-args $SHARED $SRC
.venv-taichi-mpm/bin/python scripts/rigid_elastic/beach_ball_hammock_mpm/build_pcve_beach_ball_hammock_mpm.py \
    --source-blend assets/scenes/beach_ball_hammock_mpm/beach_ball_hammock_base.blend \
    --out-root renders/beach_ball_hammock_mpm/edit_young_15000_to_1500pa_at_2_5s --stage prepare --simulation-args $SHARED $EDIT
.venv-taichi-mpm/bin/python scripts/rigid_elastic/beach_ball_hammock_mpm/simulate_beach_ball_hammock_mpm.py \
    --work-dir renders/beach_ball_hammock_mpm/edit_young_15000_to_1500pa_at_2_5s/work $SHARED $EDIT --cpu-threads 1 \
    --source-branch-work-dir renders/beach_ball_hammock_mpm/source/work \
    --source-branch-variant-id source_young_15000pa_preroll12
for stage in render verify; do
  .venv-taichi-mpm/bin/python scripts/rigid_elastic/beach_ball_hammock_mpm/build_pcve_beach_ball_hammock_mpm.py \
      --source-blend assets/scenes/beach_ball_hammock_mpm/beach_ball_hammock_base.blend \
      --out-root renders/beach_ball_hammock_mpm/source --gpu <GPU index or UUID> --stage $stage --simulation-args $SHARED $SRC
  .venv-taichi-mpm/bin/python scripts/rigid_elastic/beach_ball_hammock_mpm/build_pcve_beach_ball_hammock_mpm.py \
      --source-blend assets/scenes/beach_ball_hammock_mpm/beach_ball_hammock_base.blend \
      --out-root renders/beach_ball_hammock_mpm/edit_young_15000_to_1500pa_at_2_5s --gpu <GPU index or UUID> --stage $stage --simulation-args $SHARED $EDIT
done
```

- The simulation takes about 6 minutes on one thread (12 s pre-roll and the 4 s clip).
- `--python` and `--blender` choose the runtimes; `--threads` sets Blender and OpenMP threads; Taichi
  threads are the simulator's `--cpu-threads`.
- The simulator's `--reuse-cache` re-checks an existing cache and metrics pair and rewrites the reports
  without running Taichi.
- The render entry's `--device auto` (default) renders with OptiX or CUDA when `CUDA_VISIBLE_DEVICES` is
  set (the builder's `--gpu` sets it) and on the CPU otherwise. In the published suite the source and
  the timed edit are CPU renders and the 1.5 kPa and 70 kPa cases are OptiX renders with the same
  samples, denoiser and seed; CPU and GPU renders differ by sampling noise only (1–2 levels of 255 at
  the 99th percentile).
- The render entry's `--frames-only` renders `work/frames` and stops, so frames can be rendered on
  another machine; a later render stage with `SKIP_EXISTING=1` keeps them, encodes the video and records
  `frames_rendered_separately` in output/verification.json.

## Outputs

New runs write to the chosen output root under `renders/beach_ball_hammock_mpm/`. The published suite
is `renders/pcve_suites/pcve_beach_ball_hammock_mpm_suite/`; no command writes into it by default.

| Path in the output root | Content |
|---|---|
| `output/video.mp4` | rendered video |
| output/appearance_report.json, output/verification.json | look report (camera, canvas–ball gaps per frame) and video check |
| `output/scene_simulated.blend`, output/experiment.json | scene with the MPM cache applied, before the look |
| `work/scene.blend`, `work/mpm_hammock_surface.npz` | prepared scene and undeformed hammock surface |
| `work/mpm_flat_drop_final_cache.npz` and its metrics, simulation_report.json, edit_manifest.json, scene_spec.json | simulation cache (surface and ball per frame) and exact parameter values |
| `work/frames/` | rendered PNG frames |
| video_verification.json | decode and format check of the video |
| pipeline_manifest.json, `logs/` | the plan and what each stage ran |

## Code layout

- `simulate_beach_ball_hammock_mpm.py`: simulate entry; runs `physics/simulate_pcve_beach_ball_hammock_mpm.py`
- `render_beach_ball_hammock_mpm.py`: render entry (Blender script); runs `appearance/render_pcve_beach_ball_hammock_mpm.py`
- `build_pcve_beach_ball_hammock_mpm.py`: prepare, simulate, render and verify stages
- `edit_vocab.py`: edit DSL vocabulary, baseline physics, published cases with their DSL and simulator flags, source prompts; `pcve_edit_dsl.make_prompts(parse(edit_dsl, VOCAB), VOCAB)` gives the published edit prompts
- `physics/run_taichi_mpm_hammock.py`: Taichi MLS-MPM solver
- `physics/simulate_pcve_beach_ball_hammock_mpm.py`: simulation driver and acceptance checks
- `appearance/prepare_beach_ball_hammock_mpm.py`: extracts the hammock surface from the base scene
- `appearance/apply_mpm_cache_to_blender.py`: imports the MPM cache into the scene
- `appearance/validate_mpm_blend.py`: checks the saved scene against the metrics
- `appearance/render_mpm_full.py`, `appearance/render_pcve_beach_ball_hammock_mpm.py`: frame rendering
- `appearance/look_beach.py`, `appearance/appearance.json`: the beach look and its configuration
- `requirements.txt`: Python packages of `.venv-taichi-mpm`
- `entrypoints.json`, `scene_manifest.json`: entry-point options and runtimes for the shared CLI; cases and published videos

## Limitations

- The hammock is a thick MPM elastic body, not a woven fabric; strain limits and tethers stand in for
  the fabric's limited stretch.
- The visible canvas is offset from the simulated mid-surface by a fixed thickness and contact margin;
  the gap between ball and canvas reaches 2.5–10 cm during rebounds.
- Runs on all cores are not bit-reproducible (up to about 0.3 mm between runs).
- The base scene is a third-party diorama model; check its licence before redistributing renders. The
  coconut, straw hat, beach umbrella and wooden deck chair models are royalty-free with no
  redistribution: renders may use them, the model files must not be redistributed.
