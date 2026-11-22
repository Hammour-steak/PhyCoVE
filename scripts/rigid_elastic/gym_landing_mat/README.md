# gym_landing_mat

A 4.54 kg (10 lb), 22.5 cm medicine ball drops at a slant onto a 1.2 m x 0.8 m x 14 cm gymnastics landing mat on a
school-gym floor, sinks into the foam, rebounds slightly and rolls a short way before settling. The scene is
rigid–elastic: a layered nonlinear FEM foam core and a thin loose cover exchange contact forces with independent
rigid bodies through libuipc IPC; recorded motion and deformation come from the native solve. The source video is
4 s at 24 fps (96 frames, 1280×720). The case number 1 is kept in `entrypoints.json` (`case_number`).

## Scene

- Medicine ball: radius 0.1125 m, mass 4.5359 kg, released with its centre at (-0.09, -0.035, 0.515) m at 0.8 m/s
  along (0.55, 0, -0.835), i.e. (0.44, 0, -0.668) m/s. Black molded rubber with a fine pebble grip (about 1.6 mm),
  satin rubber sheen (pebble tops roughness 0.45, valleys 0.55), two hairline (0.6 mm) mould lines and light wear.
  The contact mesh carries 2 mm channels of the basketball mesh it is derived from, so the ball is shaded with the
  smooth sphere normal (the silhouette moves by at most 2 mm, about one pixel).
- Landing mat: 1.2 x 0.8 x 0.14 m foam core with 45 mm corner radius inside a loose PVC cover; the mat top is at
  z = 0.14 m. Cover look: royal-blue 18 oz vinyl-coated polyester with the `leather_white` grain (0.16 m tile),
  roughness 0.42-0.66 with faint irregular gloss patches of ±0.07, broad grime darker towards the floor edge; stitched
  seams along the top and bottom of the side walls (a 3 mm pulled-in groove with 4 mm lock stitches every 6 mm),
  loose-vinyl creases within about 12 cm of each vertical corner and a faint low undulation of the top, all placed in
  the cover's rest coordinates (native `cloth_rest_positions`, attached as the `rest` attribute) so they ride on the
  simulated cloth; same-colour edge binding and black webbing handles.
- Floor: maple strip sports floor, 57 mm boards of random length (1-D Voronoi, mean 1.1 m) along the court, each cut
  from a different patch of the `white_maple_veneer` scan, honey tone, hairline joints, satin polyurethane coat with
  traffic wear and faint swirl marks, per-board level steps and sparse sneaker scuffs; white basketball lines and blue
  volleyball lines.
- Walls: plaster with mottling, padded blue-green wall protection with wear.
- Dressing far from the mat: a PE hula hoop lying flat back left of the mat and a receding drill line of three 23 cm
  training cones; each is checked to stay outside the swept volume of the mat, ball and bottle over every case and
  frame, and inside the frame.
- Light: overcast daylight through the windows (no sun lamp) and three rows of six overhead luminaires (luminaire body,
  diffuser and emitter repeated on the grid; 140 W each).
- Camera: position, lens (43 mm on a 36 mm sensor), focus distance (on the mat), resolution and every static matrix
  are those of `appearance/render_replay.py`, which asserts them every frame. The look adds depth of field at f/5.6 and
  a compositor lens finish (lens distortion with 0.0015 dispersion, 12 % soft vignette).
- Render: Blender 4.3.2 Cycles OptiX, 1280×720, 192 samples, adaptive threshold 0.004, max bounces 10 (transparent
  32), OpenImageDenoise, fixed seed, no motion blur, 24 fps, 96 frames, AgX Medium High Contrast, exposure 0.
  `appearance/realism.py` runs `appearance/render_replay.py` with one hook placed right after it records the camera
  and every static matrix; the hook only restyles materials, lights and static dressing.

## Physics

- Solver: libuipc CUDA IPC (`physics/simulate.py`), step 1/1200 s, 1.5 s preload (the source FEM state), 4.0 s
  recorded at 24 Hz.
- Ball: affine rigid body.
- Foam core: two-layer compressible StableNeoHookean FEM, top-layer Young's modulus 10 kPa, base layer 1.8 times
  stiffer, Poisson ratio 0.22, density 32 kg/m³, volume shear / bulk viscosity 450 / 1100 Pa s, FEM grid
  73 x 49 x 13.
- Cover: Baraff-Witkin thin shell, thickness 0.55 mm, density 820 kg/m³, stretch modulus 8 MPa, shear modulus 3 kPa,
  bending stiffness 1e-4, surface shear / bulk viscosity 0.2 / 0.4, bending viscosity 4e-6.
- Viscosity: the native objective metric and dihedral viscosity extension (`scripts/pcve_native_viscosity.cu`,
  `scripts/pcve_native_viscosity_frontend.cpp`, loaded by `physics/viscosity.py` from `.runtime/gym_landing_mat/native_cuda12`;
  `PCVE_NATIVE_RUNTIME` overrides) is solved in the same Newton/IPC system.
- Contact: friction 0.55, IPC barrier distance 0.6 mm.
- Sports bottle (ADD only): radius 34 mm, length 0.19 m, 0.20 kg, friction 0.22 on the mat and 0.42 against the ball;
  settled on the mat for 0.18 s before the recorded clip. The solver runs the native statement
  `ADD gym_water_bottle AT PRESET roll_path` (`native_edit_dsl` in the builder).
- Every case starts from the source FEM state (`assets/scenes/gym_landing_mat/native/<case>/initial_state.npz`) and
  changes only its DSL-resolved parameter. The Young's-modulus edit starts from the exact source FEM state with
  byte-identical rest arrays loaded before FEM construction (no CPU-dependent rounding).
- Baseline values are in `physics/scene_specs.json` (key `gym_landing_mat`).

## Measured motion

From the published ground truth (ball centre in m; the ball centre sits at z = 0.2525 when it just touches the
undeformed mat; video frames of the 24 fps clock).

| case | deepest ball centre z (frame) | ball centre at frame 96 (x, z) |
|---|---|---|
| `source` | 0.208 (6) | 0.043, 0.231 |
| `edit_mass_double` | 0.186 (7) | 0.047, 0.217 |
| `edit_faster` | 0.207 (5) | 0.352, 0.230 |
| `edit_young_modulus_rebound` | 0.232 (6) | 0.353, 0.249 |
| `edit_add_path_obstacle` | 0.208 (6) | 0.038, 0.231; the bottle is pushed 94 mm along the mat |
| `edit_delete_actor` | - | the mat stays at rest |

## Validation

`--stage verify` (also `validate`) checks the accepted videos against the delivery audit records,
the native clocks (96 samples) and the edit parameters (`tools/retained_delivery.py`, `tools/validate_original.py`).
`tools/finalize.py` checks each encoded video with ffprobe (96 frames, 4.0 s).

## Cases

The builder's native case ids drop the `edit_` prefix of the published case directories (`edit_faster` is native case
`faster`). All viscosity coefficients, masses, velocities, geometry, initial poses and the camera match the source
except the edited field.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | - | ball 4.5359 kg at 0.8 m/s; foam top layer E = 10 kPa |
| `edit_mass_double` | `SET medicine_ball.mass TIMES 2` | ball 9.0718 kg |
| `edit_faster` | `SET medicine_ball.initial_velocity TIMES 3` | release speed 2.4 m/s |
| `edit_young_modulus_rebound` | `SET landing_mat.young_modulus TIMES 10` | top-layer E = 100 kPa (base layer still 1.8 times stiffer) |
| `edit_add_path_obstacle` | `ADD gym_water_bottle BETWEEN medicine_ball AND ball_heading_point AT 1/10 FROM ball_heading_point` | an independent dynamic 0.20 kg sports bottle lying across the ball's path on the mat |
| `edit_delete_actor` | `DELETE medicine_ball` | no ball |

`ball_heading_point` is a display-only anchor in `edit_vocab.py` (`DISPLAY_ADD_ANCHORS`): the point where the ball's
initial line of motion meets the mat top, (0.157, -0.035, 0.14) m; the 1/10 point of the line from it to the ball
lies 0.23 cm from the bottle centre at frame 1.

## Assets

- `scenes/gym_landing_mat` (derived, 21 files): native `initial_state.npz` and `cache.npz` of every case, packed render
  scenes `packed/<case>.blend`, the medicine-ball collision mesh `rigid_geometry.npz` and the render reference (camera
  and environment manifest) of the Young's-modulus case.
- `polyhaven/white_maple_veneer` (url): floor grain.
- `polyhaven/leather_white` (url): vinyl grain of the mat cover.

```bash
python3 scripts/download_assets.py --scene gym_landing_mat
python3 scripts/download_assets.py --scene gym_landing_mat --check
```

`PCVE_ASSETS_DIR` selects an external asset root.

## Requirements

- Linux with a CUDA GPU for solves and renders; `--stage verify` runs anywhere.
- libuipc with the native viscosity module in `.runtime/gym_landing_mat/native_cuda12/` (built against libuipc by
  `tools/support/build_pool_native.py`); it finds libuipc_backend_cuda.so and libcudart.so.12 through
  `LD_LIBRARY_PATH` (`tools/ipc_probe_deps/uipc/_native` and `.runtime/gym_landing_mat/lib`).
- Blender 4.3.2 (`tools/blender-4.3.2-linux-x64`).
- `tools/finalize.py`, `tools/export_ground_truth.py` and `tools/publish_suite.py` need a Python with numpy
  (`.venv-genesis-mpm-sph`); `tools/finalize.py` needs ffmpeg and ffprobe.
- Without `--gpu-uuid` (default `auto`) a GPU job goes through `tools/worker_run.py` (shared GPU policy, GPU/process
  preflight, per-GPU lease and UUID binding); with `--gpu-uuid <claimed GPU UUID>` it runs directly on that GPU.

## Commands

```bash
# verification and catalog
python3 scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py --stage verify
python3 scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py --list-cases
python3 scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py --list-edits
python3 scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py --show-prompts add_path_obstacle
python3 scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py --export-prompts \
    --out-root renders/pcve_suites/pcve_gym_landing_mat_suite --dry-run

# solve, render, finalize
python3 scripts/rigid_elastic/gym_landing_mat/simulate_gym_landing_mat.py --case-id source \
    --out renders/gym_landing_mat/rebuild/<run>/source/simulation --gpu-uuid <GPU UUID>
python3 scripts/rigid_elastic/gym_landing_mat/render_gym_landing_mat.py --case-id source \
    --out renders/gym_landing_mat/rebuild/<run>/source/render --gpu-uuid <GPU UUID> --samples 192
.venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/gym_landing_mat/tools/finalize.py \
    --render renders/gym_landing_mat/rebuild/<run>/source/render
python3 scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py --stage all --cases source \
    --out renders/gym_landing_mat/rebuild/<run> --gpu-uuid <GPU UUID>

# ground truth and a new suite
.venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/gym_landing_mat/tools/export_ground_truth.py --case source \
    --out renders/gym_landing_mat/rebuild/<run>/source_ground_truth.json
.venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/gym_landing_mat/tools/publish_suite.py \
    --renders renders/gym_landing_mat/rebuild/<run> --suite renders/gym_landing_mat/rebuild/<run>/pcve_gym_landing_mat_suite
```

Builder stages: `simulate` solves new states, `render` replays new states from the same output root, `finalize`
encodes and checks, `all` solves, renders and encodes, `replay` re-renders the stored native caches (`--reuse-native`
renders an explicitly retained cache). `--look realism` (default) renders the published look, `--look accepted` the
base renderer `appearance/render_replay.py`. The render entry also takes `--still-frame N` or `--frame-start A
--frame-end B`. `tools/export_ground_truth.py --all --suite DIR` writes every case into `DIR/cases/<case>/`;
`--simulation` and `--reference-main` point it at a new solve and its reference render.

## Outputs

- New solves and renders go to `renders/gym_landing_mat/rebuild/` unless `--out` says otherwise; writing into the
  delivery, the published suite or the asset store is refused.
- `tools/finalize.py` encodes the 96 frames (libx264, CRF 17, yuv420p) and stores the instance masks.
- Accepted native delivery (solver states, audits, renders; internal layout kept so the relative paths in its own
  records resolve inside it): `renders/gym_landing_mat/accepted/`. It is not
  registered in `assets.json`.
- `.runtime/gym_landing_mat/` holds the native viscosity module, the CUDA runtime library and the launch records and
  GPU leases of `tools/worker_run.py`.
- Published suite: `renders/pcve_suites/pcve_gym_landing_mat_suite/` (`canonical_suites` in `scene_manifest.json`).
  `tools/publish_suite.py` copies the finalized videos and native metadata into a new suite folder (it must not exist)
  and writes ground truth, video validation (full decode), prompts, provenance, the suite manifest and the input
  locations. It never replaces the published suite and does not copy the published cases'
  `standardization` provenance records.
- Ground truth (`pcve_ground_truth/1`, through the shared module `scripts/pcve_ground_truth.py`): fixed camera, the
  medicine ball and the bottle as rigid bodies (recorded body centre and the nearest rotation), the landing mat as a
  deformable body (centroid of the simulated cover-shell vertices, bounding-box dimensions at the first frame). The
  tool reads the case's cache (body transforms and velocities, cover-shell vertices, obstacle transforms and
  velocities) and simulation config, with the fixed camera from the case's reference render, without resampling;
  static scenery that no edit names is left out.

## Code layout

```
simulate_gym_landing_mat.py      native libuipc solve of one case
render_gym_landing_mat.py        render one case's native state with the published look
build_pcve_gym_landing_mat.py    edit catalog (PCVE_SOURCE / PCVE_EDITS); --stage verify | validate | simulate | render | finalize | all | replay
scene_paths.py                   inputs, accepted delivery (data.accepted_delivery), published suite, outputs, launch rule
scene_inputs.py                  native inputs of every case
scene_manifest.json              published suite pointer (canonical_suites) and data locations
entrypoints.json                 unified entry declaration
edit_vocab.py                    public edit vocabulary (loads physics/edit_vocab.py) with the display-only ADD anchor
physics/simulate.py              libuipc solve
physics/geometry.py, scripts/pcve_fem_geometry.py  mat, cover and body geometry
physics/scene_specs.json         baseline parameters
physics/edit_vocab.py            DSL bindings of the native parameters
physics/viscosity.py             loader of the native viscosity module
scripts/pcve_native_viscosity.cu, scripts/pcve_native_viscosity_frontend.cpp  native viscosity sources
appearance/realism.py            published look (default of the render entry)
appearance/render_replay.py      Blender replay of native states into the packed scene (--look accepted)
tools/worker_run.py              GPU lease launcher (scripts/pcve_gpu_reservations.py)
tools/finalize.py                encode, probe, masks
tools/export_ground_truth.py     pcve_ground_truth/1 of one case or a suite
tools/publish_suite.py           assembles a new suite
tools/retained_delivery.py, tools/validate_original.py  delivery verification
tools/support/build_pool_native.py  builds the native viscosity module
```

`PCVE_SOURCE` / `PCVE_EDITS` in the builder equal the published `cases/<case>/prompts.json`; edit prompts are the output
of `pcve_edit_dsl.make_prompts` for `edit_vocab.py`. Objects are named as the video shows them (the medicine ball, the
landing mat, a sports water bottle); the ADD prompts name the ball's observable landing point on the mat.
`--export-prompts [--dry-run]` writes them into a suite (by default `renders/gym_landing_mat/suite_build/pcve_gym_landing_mat_suite/`; the published suite only
  when its path is given with `--out-root`).

## Limitations

- Material parameters are effective values, not fitted to a measured commercial mat.
- The published results were computed on other Linux GPU machines; determinism on other machines has not been
  verified.
