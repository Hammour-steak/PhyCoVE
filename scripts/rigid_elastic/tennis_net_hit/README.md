# tennis_net_hit

A tennis ball flies in from the far side of a tensioned tennis net, hits the net 0.85 m beside the centre strap,
is thrown back and rolls away on the far court while the net sways and settles. The scene is a rigid–elastic
interaction (rigid ball, elastic net). Each source video is 4 s at 24 fps (96 frames, 1280×720), played at
normal speed: frame k shows the solver state at t = (k-1)/24 s.

## Scene

- Ball: 57.6 g, radius 33.5 mm, starting at (0.85, -1.80, 0.81) m with velocity (0.08, 8, 0.35) m/s.
- Net: 3.5 mm polyethylene strands on a 45 mm mesh (strand E = 25 MPa) with a pretensioned steel headline in the
  bound headband, bottom and laced side bindings, and a folded 45 mm PET centre strap anchored at the court
  socket.
- Set: a public hard court in a park on a clear afternoon (look `clear_afternoon_park_court`, packed court scene
  `scene.blend` with every image packed and no linked library).
  - Sky and sun: `pretoria_gardens` at 8k, sky strength 1. A sun lamp (0.53°, 4.5 W/m², warm white) follows the
    image's own sun (its brightest pixel), and the sky is rotated so the sun stands on the camera's right (world
    azimuth 155°): the park beyond the fence is sunlit and sharp, the net throws its shadow onto the far court
    and the ball its shadow onto the court.
  - Court: sun-faded blue acrylic (sRGB albedo 0.21-0.23 / 0.31-0.34 / 0.43-0.47) with a green surround
    (0.18-0.20 / 0.31-0.34 / 0.24-0.26); broad and fine fading patches (relative albedo variation 0.07 and
    0.035); sand-grain relief with normal-map strength 0.45 and fine bump 0.32; scanned microtexture, shader wear
    layers (chalking, dust bands, mineral film), pale ball rubs and leaves. Lines are off-white, albedo 0.80-0.88.
  - Court marks: soft, irregular rubber scuffs (sparse elongated blobs, up to 28 % darker and a little glossier,
    edges broken by noise) and occasional fuzzy yellow-green ball marks (at most 55 % opacity) on the blue court
    and, at half density, on the green surround; no hard thresholds, so no rings or contour lines. The packed
    scene's pivot-rubber decals, outsole decals and hairline-crack curves are hidden.
  - A racket lies at the sideline in plain paint without logo textures.
- Camera: the fixed observation camera of the packed court scene, 46 mm lens on a 36 mm sensor, f/11, focused at
  4.77 m, identical for all cases.
- Rendering (`appearance/realism.py` over `appearance/render.py`): Blender 4.3.2 Cycles, 192 samples,
  OpenImageDenoise (albedo + normal, accurate prefilter), indirect clamp 10, persistent data off (required with
  motion blur in Blender 4.3), AgX Medium High Contrast, exposure -0.5, lens vignette 0.10 and dispersion 0.002.
  Shutter 1/480 s centred on each frame with 5 motion steps for the deforming net; the 96 frame centres are true
  solver states and the shutter samples interpolate the dense deformation keys. Videos are H.264, crf 16, preset
  slow, yuv420p, 24 fps.

## Physics

- Net model: float64 tensile centreline beam network with finite bending stiffness and Kelvin-Voigt loss; the
  steel headline is a finite-compliance XPBD constraint. Strap axial and bending dissipation times are 0.0005 s
  and 0.025 s; contact friction 0.
- Contact: ball/strand and ball/band contacts are hard unilateral constraints solved in the same constrained
  Newton step.
- Time stepping: dt = 1/153600 s, recorded at 3840 Hz, CPU only.
- Inputs: the frozen contact library and the common gravity-prebalanced initial packet in
  `assets/scenes/tennis_net_hit/frozen/`, sha-pinned in `physics/common.py`.
- Cases: the source is solved 0-4 s from the common packet. Each edit keeps its own 0-3 s solve
  (`assets/scenes/tennis_net_hit/inputs/<case>/prefix_samples.npz`) and continues from the bit-exact float64 state
  at 3 s (`endpoint_0059.npz`) to 4 s; `physics/simulate.py` first replays 2.95-3.00 s and requires agreement
  within 1e-9. The DELETE case solves the free ball against the court and fence triangles
  (`assets/scenes/tennis_net_hit/court_collision/`). No retiming, interpolated frames or frozen tails.
- `physics/qualify.py` checks clocks, protected inputs, contact gaps on the shutter clock and court clearance,
  then writes the render cache and its qualification record.

## Measured motion

From the published ground truth (video frames). In the source the net starts to move at frame 7 and the centre
strap at frame 8; the impact spans frames 7-12, the first bounce is at frame 16, followed by a second bounce and
the roll-out.

| Case | Ball at frame 96, (x, y) m | Note |
|---|---|---|
| `source` | (0.88, -3.63) | thrown back, rolling on the far court |
| `edit_ball_speed_div5` | (1.20, -0.23) | barely presses the net (centroid shift 0.1 mm) and drops just short of it on the far side |
| `edit_ball_speed_x2` | (2.04, -7.95) | thrown back furthest; the strap dips 1.2 mm |
| `edit_net_young_div10` | (0.73, -3.56) | softer net, the deepest net sag of the edits |
| `edit_net_young_x10` | (0.85, -2.59) | stiffer net, shorter rebound |
| `edit_remove_entire_net` | (1.06, 15.25) | no net: the ball flies on across the court |

## Validation

- Replay checks: ball and video poses within 1 µm of the solver at frame centres, at most 2 µm at shutter offsets.
- Static regions change by less than 0.04/255 between consecutive frames (480×270-scale check).
- `--stage verify` checks the published solves and the published suite; `--stage prepare` checks that the
  registered assets are present.

## Cases

Builder case ids drop the `edit_` prefix of the published case directories (`edit_ball_speed_x2` is
`ball_speed_x2`). Camera, lights, scene and every initial pose are shared. A modulus edit scales the axial (EA)
and bending (EI) stiffness of the polyethylene strands only; masses, the steel headline and the PET centre strap
keep their source values.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | ball forward speed 8 m/s; net strand E = 25 MPa |
| `edit_ball_speed_div5` | `SET tennis_ball.initial_velocity TIMES 0.2` | forward speed 1.6 m/s |
| `edit_ball_speed_x2` | `SET tennis_ball.initial_velocity TIMES 2` | forward speed 16 m/s |
| `edit_net_young_div10` | `SET tennis_net.young_modulus TIMES 0.1` | strand E = 2.5 MPa |
| `edit_net_young_x10` | `SET tennis_net.young_modulus TIMES 10` | strand E = 250 MPa |
| `edit_remove_entire_net` | `DELETE tennis_net` | net, centre strap and anchors absent from frame 1 |

## Assets

- `scenes/tennis_net_hit` (derived, 63 files): frozen solver inputs, the packed court scene, per-edit restart
  checkpoints and court collision triangles.
- `polyhaven/pretoria_gardens` (url): sky and sun of the look.

```bash
python3 scripts/download_assets.py --scene tennis_net_hit
python3 scripts/download_assets.py --scene tennis_net_hit --check
```

## Requirements

- Solve: Linux, CPU only, a Python with NumPy (for example `.venv-genesis-mpm-sph`).
- Render: Blender 4.3.2 (`tools/blender-4.3.2-linux-x64`) on an NVIDIA GPU (OptiX or CUDA) or the CPU; one Blender
  process peaks near 20 GB of GPU memory. ffmpeg with libx264.

## Commands

Run from the repository root.

```bash
S=scripts/rigid_elastic/tennis_net_hit

# Verify the published solves and suite; check the registered assets
python3 $S/build_pcve_tennis_net_hit.py --stage verify
python3 $S/build_pcve_tennis_net_hit.py --stage prepare
python3 $S/build_pcve_tennis_net_hit.py --list-cases
python3 $S/build_pcve_tennis_net_hit.py --list-edits
python3 $S/build_pcve_tennis_net_hit.py --show-prompts source

# Solve and qualify one case
.venv-genesis-mpm-sph/bin/python $S/simulate_tennis_net_hit.py --case <case> \
    --out renders/tennis_net_hit/<run>/physics/<case> --threads 2

# Render one case from a qualified render cache (render_cache.npz with qualification.json beside it)
python3 $S/render_tennis_net_hit.py --case <case> --cache renders/tennis_net_hit/accepted/physics/<case>/render_cache.npz \
    --out renders/tennis_net_hit/<run>/<case> --gpu-uuid <GPU UUID> --device OPTIX
python3 $S/render_tennis_net_hit.py --case <case> --cache <dir>/render_cache.npz \
    --out renders/tennis_net_hit/<run>/<case>_audit --audit-only

# One case as parallel frame ranges on one device, merged and encoded
python3 $S/tools/render_split.py --case <case> --cache <dir>/render_cache.npz \
    --out renders/tennis_net_hit/<run>/<case> --parts 4 --gpu-uuid <GPU UUID>,<GPU UUID>

# Assemble a new suite from per-case render outputs, then write its ground truth
python3 $S/tools/publish_suite.py --renders renders/tennis_net_hit/<run> \
    --suite renders/tennis_net_hit/<run>/pcve_tennis_net_hit_suite
tools/blender-4.3.2-linux-x64/blender -b assets/scenes/tennis_net_hit/inputs/scene.blend --disable-autoexec \
    --python-exit-code 1 --python $S/tools/export_ground_truth.py -- \
    --suite renders/tennis_net_hit/<run>/pcve_tennis_net_hit_suite
```

A full 1-96 render also encodes `video.mp4`; `--start-frame a --end-frame b` renders a range and `--samples N`
overrides the look's 192 samples. `--pool` launches through `tools/worker_run.py`, which waits for an idle GPU,
takes a lease and binds the job to its UUID. `tools/render_split.py` puts at most two parts on a 48 GB card (two
same-model GPU UUIDs for four parts).

## Outputs

- Solves and renders must go to fresh directories under `renders/tennis_net_hit/` (`PCVE_TENNIS_WORK` moves this
  root; `appearance/render.py` reads the same variable).
- The published solves (physics and pose reports, worker-tar indexes, render caches and solver ground truth) are
  in `renders/tennis_net_hit/accepted/` (`PCVE_TENNIS_DELIVERY` moves it); each case's render cache,
  qualification and solver ground truth are kept extracted under `physics/<case>/`, indexed by
  `worker_tars/<worker>/<case>_files.json`. `--stage verify` and the render entry need them in place.
- The published suite is `renders/pcve_suites/pcve_tennis_net_hit_suite/` (pointer in `scene_manifest.json`).
  `tools/publish_suite.py` only builds a new suite folder (default `--suite`:
  `renders/tennis_net_hit/suite_build/pcve_tennis_net_hit_suite/`) and never overwrites an existing one; it does not copy
  the prompt history or the other provenance records of the published cases. Only `--export-prompts`
  with the published suite's path as `--out-root` writes into it.
- `build_pcve_tennis_net_hit.py --out <dir>` also writes the verify report to `<dir>/verify_report.json` under
  `renders/tennis_net_hit/`.

## Code layout

- `build_pcve_tennis_net_hit.py`: edit catalog (`PCVE_SOURCE` / `PCVE_EDITS`, equal to the published prompts.json;
  edit prompts are `pcve_edit_dsl.make_prompts` output for `edit_vocab.py`; the source lists its
  `editable_objects`); stages verify and prepare.
- `simulate_tennis_net_hit.py`: CPU solve and qualification of one case.
- `render_tennis_net_hit.py`: replays one qualified render cache with the look and encodes the video.
- `edit_vocab.py`: DSL vocabulary (object and property names used in the prompts).
- `scene_paths.py`: output root, Blender runtime, GPU launch.
- `scene_manifest.json`: published suite pointer and data locations.
- `appearance/render.py`: replay renderer, solver states into the packed court scene, replay checks.
- `appearance/realism.py`: the look; it runs `appearance/render.py` with an `__overlay__` hook that applies `apply_look`
  after the replay checks; the look is recorded in the renderer's report (render_setup_*.json, key
  `appearance_overlay`). It reads and writes no solver state.
- `physics/simulate.py`: solver adapter and the restart from the 3 s state.
- `physics/common.py`: inputs, pins and data locations.
- `physics/owner_adapter.py`: path and packet adapter around the recorded solver modules.
- `physics/checkpoint_io.py`: exact complete-state restore.
- `physics/playback_math.py`: state interpolation from solver positions, velocities and skin topology for the
  shutter samples.
- `physics/qualify.py`: qualification and render cache.
- `physics/audit_contacts.py`, `physics/audit_court.py`: contact-gap and court-clearance audits.
- `tools/export_ground_truth.py`: per-case ground truth (`pcve_ground_truth/1`) inside Blender through
  `scripts/pcve_ground_truth.py`. It reads each case's solver `ground_truth_24fps.npz` (checked against the tar
  index and qualification.json) and the camera from the packed scene, and converts without resampling: the ball
  gets the recorded body centre and nearest rotation, the net and strap their vertex centroid, presence and
  bounding-box dimensions; static scenery is left out.
- `tools/publish_suite.py`: assembles a new suite from per-case render outputs.
- `tools/render_split.py`: one case as parallel frame ranges on one device, merged and encoded.
- `tools/worker_run.py`: GPU launcher with preflight and lease (uses `scripts/pcve_gpu_reservations.py`).

## Limitations

- Net materials are effective values, not calibrated on a real net (`material_calibrated: false`).
- The published videos were rendered with OptiX on GPUs of one model with the same device type and settings for
  every frame, each case split into parallel frame ranges (about 8 s per frame overall) on another Linux GPU
  machine; bitwise reproduction elsewhere is not verified.
