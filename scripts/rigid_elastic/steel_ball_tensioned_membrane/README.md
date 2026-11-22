# steel_ball_tensioned_membrane

A controlled drop test in a university mechanics laboratory: an electromagnetic release head lets go of a
polished steel ball above a black latex membrane clamped between two precision rings, and the ball hits the
membrane centre and deforms it. The scene is a rigid–elastic interaction (rigid ball, elastic thin shell). Each
source video is 4 s at 24 fps (96 frames, 1280×720), played at normal speed: frame k shows the solver state at
t = (k-1)/24 s (the 97th state at t = 4 s stays in the cache).

## Scene

- Ball: polished steel, radius 0.04 m, 2.091 kg, centre 0.38 m above the membrane at 1.10 m height.
- Membrane: black latex sheet, clear diameter 0.76 m, thickness 0.8 mm, plane at 0.72 m, clamped between two
  precision rings with a replaceable clamp insert.
- Set: a laboratory workcell with a damped optical breadboard, a symmetric T-slot release gantry carrying the
  electromagnetic release head, a compact high-speed camera on an optical post, an LED backlight, a signal
  analyser, cables and a calibration scale, lit by the `university_workshop` HDRI. The base scene of each case is
  built by `appearance/render_native.py` and `appearance/upgrade_visuals.py` with the materials of
  `appearance/realism.py`.
- Camera: camera B of `appearance/render_native.py`, at (1.55, -2.05, 1.90) m aimed at (0, 0, 0.69) m, 60 mm lens
  on a 36 mm sensor, f/8, focused on the membrane, viewing the drop obliquely from above. The ground truth records
  the same camera.
- Published look (`appearance/realism_overlay.py`, the render entry's default): opens the saved scene of a case,
  checks its sha256 against the case's artifact manifest and changes only shaders, lights, colour settings and
  props that never touch the ball or the membrane. The membrane is a smooth glossy black latex sheet (roughness
  0.16, no speckle paint); the visible breadboard top is lapped stainless steel (roughness 0.42, albedo 0.60) with
  M6 tapped holes on a 25 mm grid; plain painted walls (albedo 0.62) behind and left of the table hide the busy
  workshop panorama; the safety shields, photogate and loose cables are hidden; the LED backlight sits on the
  high-speed camera's optical axis, opposite it across the membrane, and the DAQ in the back right corner of the
  table; the drop axis and the table area under the ring stay clear. World strength 0.32, exposure -0.25 EV, lens
  finish (vignette 0.10, dispersion 0.002), 256 samples (`--samples`), PNG frames. Blender only replays the solver
  states; it does not generate or alter any deformation.

## Physics

- Solver: libuipc (`physics/simulate_native.py`), two-way coupling of a rigid body and a nonlinear thin shell. The
  ball is an affine rigid body; the membrane is a Neo-Hookean thin shell with discrete-shell bending and IPC
  contact (d_hat 0.7 mm, friction 0.55).
- Membrane: E = 1.2 MPa, Poisson ratio 0.48, pretension 65 N/m. The mesh is a 40 × 160 radial Delaunay disk whose
  boundary ring is fixed; its rest radius is shrunk so that the clamped sheet carries the declared pretension.
- Time stepping: dt = 1/1920 s, Newton velocity tolerance 1 mm/s, real time 0-4 s, 97 stored states.
- Inputs: `assets/scenes/steel_ball_tensioned_membrane/scene_spec.json` (baseline, solver settings, the six cases;
  24 fps, 4 s) and `edit_vocab.py`.
- Output of a case: simulation.npz (ball and second-ball transforms and velocities, membrane positions and faces)
  with simulation_config.json and simulation_report.json.
- The ADD edit runs in the solver as `ADD second_ball AT PRESET impact_path_on_membrane` (`native_edit_dsl` in the
  builder catalog); the catalog `edit_dsl` uses display-only anchors in `edit_vocab.py`, and the 1/9 point is
  0.12 cm from the added ball's centre.

## Measured motion

Ball centre height from the published ground truth (ball starts at 1.10 m, membrane plane at 0.72 m; video
frames). The balls are still moving on the membrane at frame 96.

| Case | Lowest ball centre (m, frame) | Ball centre at frame 96 (m) |
|---|---|---|
| `source` | 0.520 (10) | 0.684 |
| `edit_ball_mass_heavy` | 0.429 (11) | 0.811 |
| `edit_membrane_soft` | 0.460 (11) | 0.774 |
| `edit_membrane_stiff` | 0.591 (26) | 0.807 |
| `edit_remove_membrane` | falls through the clamp onto the table (0.041, resting on it) | 0.041 |
| `edit_add_second_ball` | 0.559 (24); added ball 0.554 (10) | 0.696; added ball 0.698 |

## Validation

- Before rendering, the overlay proves that geometry, shape-key animation, modifiers, transforms and the camera
  are unchanged (`immutable_signature()` of `appearance/upgrade_visuals.py`) and replays all 96 states against
  simulation.npz (ball centre within 1e-6 m, membrane vertices within 1e-5 m).
- `--stage verify` (the default stage) checks the videos and solver caches of the published solves
  (accepted_case.json) against the case DSL and baseline.

## Cases

Builder case ids drop the `edit_` prefix of the published case directories (`edit_membrane_soft` is
`membrane_soft`). Material values are nominal, not calibrated.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | ball 2.091 kg; membrane E = 1.2 MPa |
| `edit_ball_mass_heavy` | `SET ball.mass TIMES 2` | ball 4.182 kg |
| `edit_membrane_soft` | `SET membrane.young_modulus TIMES 0.5` | E = 0.6 MPa |
| `edit_membrane_stiff` | `SET membrane.young_modulus TIMES 3` | E = 3.6 MPa |
| `edit_remove_membrane` | `DELETE membrane` | no membrane; the ball falls through the empty clamp |
| `edit_add_second_ball` | `ADD second_ball BETWEEN ball AND membrane_impact_point AT 1/9 FROM membrane_impact_point` | identical ball at rest at (0, 0, 0.761) m on the membrane centre, on the first ball's fall path |

## Assets

- `scenes/steel_ball_tensioned_membrane` (1 url, 1 derived): the `university_workshop` laboratory HDRI
  (`university_workshop_4k.hdr`) and `assets/scenes/steel_ball_tensioned_membrane/scene_spec.json`, read by `edit_vocab.py`, the solver, the renderer and
  `tools/finalize.py`.

```bash
python3 scripts/download_assets.py --scene steel_ball_tensioned_membrane
python3 scripts/download_assets.py --scene steel_ball_tensioned_membrane --check
```

`PCVE_ASSETS_DIR` moves the asset root. `--stage prepare` runs the `--check` form for the scene.

## Requirements

- Linux with an NVIDIA GPU: the solve (libuipc) and the renders run through `tools/worker_run.py`, which waits for
  a fully idle GPU ranked by the shared GPU policy and holds a per-GPU lease (`--gpu-uuid`, default `auto`).
- libuipc runtime, Blender 4.3.2 (`tools/blender-4.3.2-linux-x64`, else the shared Blender lookup) and FFmpeg.
- `--stage verify`, `--stage prepare` and the catalog commands need only Python.

## Commands

Run from the repository root.

```bash
S=scripts/rigid_elastic/steel_ball_tensioned_membrane

# Verify the published solves and videos; --accepted-root DIR verifies a copy kept elsewhere
python3 $S/build_pcve_steel_ball_tensioned_membrane.py --stage verify
python3 $S/build_pcve_steel_ball_tensioned_membrane.py --stage prepare
python3 $S/build_pcve_steel_ball_tensioned_membrane.py --list-cases
python3 $S/build_pcve_steel_ball_tensioned_membrane.py --list-edits
python3 $S/build_pcve_steel_ball_tensioned_membrane.py --show-prompts remove_membrane
python3 $S/build_pcve_steel_ball_tensioned_membrane.py --describe

# Rebuild: solve, replay in Blender, audit the saved scene, finalize per case, audit the set
python3 $S/build_pcve_steel_ball_tensioned_membrane.py --stage all --cases source \
    --out-root renders/steel_ball_tensioned_membrane/<run> --gpu-uuid <GPU UUID>
python3 $S/build_pcve_steel_ball_tensioned_membrane.py --stages simulate render --cases source \
    --out-root renders/steel_ball_tensioned_membrane/<run>

# Solve one case
python3 $S/simulate_steel_ball_tensioned_membrane.py --case <case> \
    --out renders/steel_ball_tensioned_membrane/<run>/cases/<case>

# Replay a solver cache in Blender (appearance/render_native.py)
python3 $S/render_steel_ball_tensioned_membrane.py --case <case> \
    --cache renders/steel_ball_tensioned_membrane/<run>/cases/<case>/simulation.npz \
    --out renders/steel_ball_tensioned_membrane/<run>/cases/<case> --samples <N> --camera B

# Published look of the saved scene of a case (output must be new and under .work/)
python3 $S/render_steel_ball_tensioned_membrane.py --case <case> \
    --out renders/steel_ball_tensioned_membrane/.work/<run>/<case> --frames 1-96 --gpu-uuid <GPU UUID>

# The same directly in Blender
<blender> -b --factory-startup --disable-autoexec --python-exit-code 1 \
    --python $S/appearance/realism_overlay.py -- \
    --case <case> --out renders/steel_ball_tensioned_membrane/.work/<run>/<case> --frames 1-96
```

`--preview-frame N` with `--cache` renders a single still; `--input <saved scene>` replays a saved four-second
scene with the appearance upgrade (`appearance/upgrade_visuals.py`); the overlay takes `--stills N ...` for single
frames. Every entry takes `--dry-run`.

## Outputs

- New solves, renders and launch records go to `renders/steel_ball_tensioned_membrane/` (`scene_paths.py`); the
  stages write each case to `<out>/cases/<case>/`, and the published-look render writes only under
  `renders/steel_ball_tensioned_membrane/.work/`.
- The published solves (accepted_case.json, per-case saved scenes and solver caches, the videos) are kept under
  `renders/steel_ball_tensioned_membrane/delivery/accepted/` and
  `renders/steel_ball_tensioned_membrane/outputs/accepted/cases/<case>/`; `--stage verify` and the
  published look read them.
- The published suite is `renders/pcve_suites/pcve_steel_ball_tensioned_membrane_suite/` (pointer in
  `scene_manifest.json`). Only `--export-prompts` with this path as `--out-root` writes into it.
- `tools/finalize.py` writes the solver's own per-case ground-truth layout next to a new solve (ball 4×4 transforms
  per frame); it is not the published layout. The published `ground_truth_transforms.json` files
  (`pcve_ground_truth/1`) hold the ball and second ball as rigid bodies, the membrane as a deformable body (centroid
  of its 3285 surface vertices) and camera B (60 mm).

## Code layout

- `build_pcve_steel_ball_tensioned_membrane.py`: edit catalog (`PCVE_SOURCE` / `PCVE_EDITS`, equal to the
  published prompts.json; edit prompts are `pcve_edit_dsl.make_prompts` output for `edit_vocab.py`); stages
  verify, prepare, simulate, render, finalize, audit, all.
- `simulate_steel_ball_tensioned_membrane.py`: solves one case through `tools/worker_run.py`.
- `render_steel_ball_tensioned_membrane.py`: published look of `--case` (default), `--cache` replay, or `--input`
  upgrade.
- `edit_vocab.py`: DSL vocabulary, case DSL, scenario overrides, display-only ADD anchors.
- `scene_paths.py`: published-solve location, output root, Blender runtime, launch.
- `scene_manifest.json`: published suite pointer and data locations.
- `physics/simulate_native.py`: libuipc rigid-ball and thin-shell solve.
- `appearance/render_native.py`: laboratory workcell built from a solver cache.
- `appearance/geometry.py`, `appearance/primitives.py`: geometry, material and animation helpers used by
  `appearance/render_native.py`.
- `appearance/realism.py`: materials of the workcell.
- `appearance/upgrade_visuals.py`: appearance upgrade of a saved four-second scene; its `immutable_signature()` is
  shared with the overlay.
- `appearance/realism_overlay.py`: the published look over the saved scene of a case (`--look lab`, the default;
  `--look base` renders the base look of the saved scene through the same path).
- `tools/audit_native_replay.py`: replays every frame of a saved scene against simulation.npz inside Blender.
- `tools/finalize.py`: per-case ground truth, deformation and environment manifests, artifact hashes.
- `tools/audit.py`, `tools/audit_real4s.py`: numerical, geometric, media and edit-policy audit of a set of cases.
- `tools/worker_run.py`: GPU launcher with preflight and lease (uses `scripts/pcve_gpu_reservations.py`).

## Limitations

- Material values are nominal, not calibrated on a real membrane.
- `appearance/upgrade_visuals.py` requires one bound GPU; `appearance/render_native.py` only requires Linux.
- Any code change in `appearance/` needs a render-equivalence check against the published frames.
- The published results were computed on another Linux GPU machine; bitwise reproduction elsewhere is not
  verified.
