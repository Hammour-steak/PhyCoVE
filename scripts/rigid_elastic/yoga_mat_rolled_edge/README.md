# yoga_mat_rolled_edge

A 5 kg medicine ball rolls without slipping across a parquet floor towards a yoga mat whose near end is curled up,
runs onto the curl and either crosses the mat or is rejected and rolls back. The scene is a rigid–elastic
interaction (rigid affine ball, nonlinear elastic shell mat). Each source video is 4 s at 24 fps (96 frames,
1280×720), played at normal speed: frame i shows the solver state at t = (i-1)/24 s.

## Scene

- Medicine ball: radius 0.12065 m (24.1 cm across), 5.0 kg, starts at x = -1.05 m and rolls without slipping at
  0.9 m/s along +x (ω_y = v / r). The render shows the exact ball collision surface (animated through shape keys)
  with a moulded-rubber grip material.
- Yoga mat: 1.8 × 0.66 m, 6 mm thick, 476.99 kg/m³ (3.4 kg); residual curl radius 0.06 m over 1.05 rad (arc
  0.063 m), curl tip about 3.35 cm above the floor. The render replays the shell vertices frame by frame.
- Room (`appearance/render_source_review.py`): a `rectangular_parquet` floor and an exercise nook with sage
  limewash walls, a recessed window, linen curtain folds, a woven basket and walnut cabinetry on a continuous
  plinth.
- Published look (`appearance/realism.py`): runs `appearance/render_source_review.py` with its
  `OVERLAY` hook set and, once room, lights and camera exist, replaces
  the studio lights by daylight through a side window (a 0.8° sun and the `residential_garden` HDR seen through a
  real window opening), closes the room, hangs sheer linen curtains, gives the cabinets an oiled walnut veneer,
  adds wall mottling and surface wear and places a wicker basket and a potted plant
  (`assets/scenes/yoga_mat_rolled_edge/room_dressing/`), all outside the strip the ball and mat use.
- Camera: a low contact view, 55 mm lens, 36 mm sensor (AUTO fit), no shift, at (-0.35, -2.65, 0.27) m aimed at
  (-0.35, 0, 0.045) m, depth of field focused on the ball at f/8.
- Rendering: Blender 4.3.2 Cycles, 96 samples (adaptive threshold 0.012), denoised, AgX Base Contrast at +2.8 EV,
  motion blur with a 0.5-frame shutter, indirect clamp 8, a mild lens finish (`pcve_realism_kit.lens_finish`).
  Frames are `contact_frame_0001..0096.png`; the video is encoded with libx264 crf 17, yuv420p, faststart at the
  cache's 24 fps. Blender only replays the solver states and does not amplify any deformation.

## Physics

libuipc CUDA IPC (`physics/simulate_source.py`), values from `edit_vocab.BASELINE` and `physics/scene_spec.json`:

| Body | Model | Main values |
| --- | --- | --- |
| Medicine ball | affine rigid body (icosphere, subdivision 3) | radius 0.12065 m, 5.0 kg, no-slip rolling at 0.9 m/s |
| Yoga mat | Neo-Hookean shell + discrete shell bending + viscosity extension | 1.8 × 0.66 m, 6 mm, 476.99 kg/m³, E 6 MPa, ν 0.46 |
| Floor and contacts | IPC half-space; one contact model for floor, mat and ball | friction 0.72, contact d̂ 0.5 mm |

- Mesh 97 × 25 shell vertices, dt 1/960 s, Newton velocity tolerance 1e-3 and at most 700 iterations, MAS
  preconditioner.
- Viscosity: surface shear 0.25 and bulk 0.5 Pa·s·m, hinge bending viscosity 8e-6, solved in the same Newton/IPC
  system by the plugin in `assets/scenes/yoga_mat_rolled_edge/native/` (`PCVE_VISCOSITY_PLUGIN`).
- Initial state: every case except `delete_mat` starts from the post-settle state of mat and ball
  (`assets/scenes/yoga_mat_rolled_edge/settled_state.npz`) with all velocities set to zero, then launches the ball.
- `DELETE mat` removes the shell from the world: the ball rolls on the rigid floor in closed form (no rolling
  resistance) from the same settled ball state; this branch runs on the CPU.
- Timed edit: frames 1-15 of `mass_x0p25_at_frame_16` are the source's own states. `physics/simulate_source.py
  --source-cache <source simulation.npz> --edit-frame 16 --ball-mass 1.25` builds the world with the edited mass,
  restores the complete source state of frame 16 (every shell vertex position and velocity, the ball's affine
  transform and velocity) and solves on to t = 95/24 s. The merged `simulation.npz` holds source frames 1-15 and
  the continuation; `continuation.npz` keeps the solved part.

## Measured motion

Ball centre x at 4 s, from the published caches.

| Case | Final x (m) | Largest x (m) | Outcome |
| --- | --- | --- | --- |
| `source` | 0.660 | 0.660 | crosses the curl and leaves the picture on the right after frame 61 |
| `edit_young_x4` | -1.627 | -0.402 | rejected by the curl, rolls back |
| `edit_mass_x0p25` | -1.555 | -0.413 | rejected, rolls back |
| `edit_speed_x0p5` | -0.866 | -0.433 | rejected, rolls back |
| `edit_delete_mat` | 2.513 | 2.513 | rolls on at 0.9 m/s |
| `edit_mass_x0p25_at_frame_16` | -1.553 | -0.412 | rejected after the mass change, rolls back |

## Validation

- `physics/audit_source.py` audits every cache (exact ball-floor gap, rigid strain of the ball, no teleporting,
  the no-slip launch before contact) and writes source_audit.json, which the render entry requires.
- Every rendered frame checks the ball-floor gap of the scene against the simulation report (1e-9 m).
- Timed edit: the hand-off is checked below 1e-8 (it is 0 in every quantity) and source frames 1-15 are checked
  bit-identical.
- Time-step control at 1/1920 s over the first 2.5 s: the source still crosses and the light-ball and stiff-mat
  balls still roll back, but the source end point moves by 128 mm.
- `--stage verify` checks the published suite: videos, prompts, solver caches and parameters, the timed hand-off
  and the ground truth (re-exported and compared).

## Cases

The builder's catalog keys (`PCVE_EDITS`) are the published case directories without `edit_`; the solver case ids
(`native_cli_case_id`, used by `--case` and `--cases`) differ: `mat_stiff` = `edit_young_x4`, `delete_mat` =
`edit_delete_mat`, `ball_mass_light` = `edit_mass_x0p25`, `ball_speed_slow` = `edit_speed_x0p5`,
`mass_x0p25_at_frame_16` = `edit_mass_x0p25_at_frame_16`. No edit moves an existing object.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | ball 5.0 kg at 0.9 m/s; mat E 6 MPa |
| `edit_young_x4` | `SET mat.young_modulus TIMES 4` | mat E 6 → 24 MPa |
| `edit_delete_mat` | `DELETE mat` | `mat_present` 1 → 0 |
| `edit_mass_x0p25` | `SET ball.mass TIMES 0.25` | ball mass 5.0 → 1.25 kg |
| `edit_speed_x0p5` | `SET ball.rolling_speed TIMES 0.5` | rolling speed 0.9 → 0.45 m/s (ω_y follows) |
| `edit_mass_x0p25_at_frame_16` | `SET ball.mass TIMES 0.25 AT FRAME 16` | ball mass 5.0 → 1.25 kg from frame 16 (t = 15/24 s) |

## Assets

- `scenes/yoga_mat_rolled_edge` (3 url, 16 manual, 16 derived): the settled initial state `settled_state.npz`, the
  viscosity plugin `native/`, the parquet textures and the `room_dressing/` sets of the published look (HDR, walnut
  veneer, basket, plant).

```bash
python3 scripts/download_assets.py --scene yoga_mat_rolled_edge
python3 scripts/download_assets.py --scene yoga_mat_rolled_edge --check
```

## Requirements

- Linux with an NVIDIA CUDA GPU for the libuipc solve, leased through `tools/worker_run.py`; `delete_mat` runs on
  the CPU.
- Runtimes: the libuipc runtime `tools/ipc_probe_deps` at the repository root (and `.runtime/gym_landing_mat` with
  `lib/libcudart.so.12`, searched when present), Blender 4.3.2 (`tools/blender-4.3.2-linux-x64`, else
  `pcve_assets.blender()`), ffmpeg.
- Rendering runs on a GPU (OptiX) or the CPU (`--device CPU`).

## Commands

Run from the repository root. All three entries accept the unified `--help`, `--describe`, `--dry-run`,
`--out-root`, `--python`, `--blender`, `--gpu` and `--threads`; `--native-help` shows the scene options.

```bash
S=scripts/rigid_elastic/yoga_mat_rolled_edge

# Verify the published suite (default stage); check the registered assets; catalog and prompts
python3 $S/build_pcve_yoga_mat_rolled_edge.py --stage verify
python3 $S/build_pcve_yoga_mat_rolled_edge.py --stage prepare
python3 $S/build_pcve_yoga_mat_rolled_edge.py --list-cases
python3 $S/build_pcve_yoga_mat_rolled_edge.py --list-edits
python3 $S/build_pcve_yoga_mat_rolled_edge.py --show-prompts mass_x0p25_at_frame_16

# Solve and audit one case (the timed edit continues the published source cache unless --source-cache is given)
python3 $S/simulate_yoga_mat_rolled_edge.py --case source --out renders/yoga_mat_rolled_edge/<run>/physics/source
python3 $S/simulate_yoga_mat_rolled_edge.py --case mass_x0p25_at_frame_16 \
    --out renders/yoga_mat_rolled_edge/<run>/physics/mass_x0p25_at_frame_16

# Render a solved case in the published look and encode it, on a leased GPU or on the CPU
python3 $S/render_yoga_mat_rolled_edge.py --cache renders/yoga_mat_rolled_edge/<run>/physics/source/simulation.npz \
    --out renders/yoga_mat_rolled_edge/<run>/render/source --gpu-uuid auto
python3 $S/render_yoga_mat_rolled_edge.py --cache renders/yoga_mat_rolled_edge/<run>/physics/source/simulation.npz \
    --out renders/yoga_mat_rolled_edge/<run>/render/source_cpu --device CPU --gpu-uuid auto

# Ground truth from the suite's solver caches: write a copy, or compare with the published files
python3 $S/tools/export_ground_truth.py --out renders/yoga_mat_rolled_edge/<run>/ground_truth
python3 $S/tools/export_ground_truth.py --check
```

The simulate entry passes solver overrides (`--ball-mass`, `--ball-speed`, `--young`, `--dt`, `--duration`,
`--fps`, `--frames`, `--grid-x`, `--grid-y`, ...) to `physics/simulate_source.py` and fills the defaults above for
the rest. The render entry's `--look review` renders the base scene of `appearance/render_source_review.py`
without the overlay; `--single-frame-index N` renders one frame.

## Outputs

- Outputs may not be written into `scripts/`, the asset store or the published suite; the default is
  `renders/yoga_mat_rolled_edge/` (solves in `physics/<case>/`).
- A solve writes `simulation.npz` (plus `continuation.npz` for the timed edit), solver config and report and
  source_audit.json; a render writes the frames and the encoded video into its fresh `--out` directory.
- The published suite is `renders/pcve_suites/pcve_yoga_mat_rolled_edge_suite/` (`scene_manifest.json`
  `canonical_suites`). Each case's `native_metadata/` holds its 24 fps solver cache `simulation.npz` (and
  `continuation.npz` for the timed edit), solver config and report, audit, render report, realism provenance and
  encoding receipt. `--export-prompts` with this path as `--out-root` writes the builder's prompts into its prompts.json
  files (`pcve_prompts/1`); no other command writes there.
- The published ground_truth_transforms.json of every case is `pcve_ground_truth/1`: per frame (96, `time_sec` =
  (i-1)/24) the ball's affine transform (`kind: rigid`, radius 0.12065 m), the mat as the centroid of its shell
  vertices with identity rotation (`kind: deformable`, rest bounding box as `dimensions`; absent in
  `edit_delete_mat`), and the render camera. `tools/export_ground_truth.py` reproduces these files from the suite
  caches (identical except the `source` record of input paths).

## Code layout

- `build_pcve_yoga_mat_rolled_edge.py`: edit catalog (`PCVE_SOURCE` / `PCVE_EDITS`, equal to the published
  prompts.json); stages verify and prepare.
- `simulate_yoga_mat_rolled_edge.py`: solves and audits one case on a leased GPU (`delete_mat` on the CPU).
- `render_yoga_mat_rolled_edge.py`: replays an audited cache in Blender and encodes the video.
- `edit_vocab.py`: baseline values, DSL bindings, solver and timed cases.
- `scene_paths.py`: paths, output guard, Blender selection, GPU launcher.
- `scene_manifest.json`: published suite pointer.
- `physics/simulate_source.py`: libuipc solver, whole-clip and timed solves.
- `physics/prepare_mat.py`: mat mesh and curl.
- `physics/viscosity.py`: viscosity plugin loader.
- `physics/scene_spec.json`: scene specification.
- `physics/audit_source.py`: CPU audit of a solved cache.
- `appearance/render_source_review.py`: replay scene.
- `appearance/realism.py`: overlay of the published look.
- `tools/export_ground_truth.py`: ground truth of the suite cases.
- `tools/worker_run.py`: GPU lease and job launch (uses `scripts/pcve_gpu_reservations.py`).

## Limitations

- Material values are effective, not calibrated: a shell represents large bending and finite contact thickness
  but not the through-thickness compression of a real closed-cell PVC mat.
- Trajectories are qualitative (see the time-step control under Validation).
- The libuipc GPU solve is not bit-reproducible across runs; a 24 fps and a 30 fps run with the same settings on
  the same machine agree within 2.4e-5 m at their common times.
- `appearance/render_source_review.py` keeps its own host check when it is started directly (`--look review`):
  it runs only on a fixed list of render machines. `appearance/realism.py` drops that check through its audited
  substitution, so the published look runs on any Linux machine. The simulate and render entries and
  `scene_paths.launch` only require Linux.
- The libuipc caches were solved on an NVIDIA RTX 3090 (CUDA 12 build of the viscosity plugin); four videos were
  rendered on an RTX 3090 with OptiX and two (`edit_speed_x0p5` and the timed edit) on an AMD EPYC 7763 CPU
  (`--device CPU`) with the same scene and settings. Bitwise reproduction on other machines is not verified.
