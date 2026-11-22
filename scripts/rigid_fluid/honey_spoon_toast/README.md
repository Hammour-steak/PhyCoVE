# honey_spoon_toast

Honey runs over the front lip of a fixed spoon at a breakfast table, forms a bead, stretches into
a hanging drop, falls and lands on a slice of toast on a porcelain plate; a continuous thread
then keeps feeding a small mound of honey that slowly spreads. This is a rigid–fluid scene: the
liquid flows over static rigid objects (spoon, toast, plate). Every case plays in real time:
video frame i is the physical state at (i−1)/24 s. The source video is 4 s at 24 fps
(96 frames), 1280×720.

## Scene

- Spoon: fixed at 15° for the whole shot, holding 14.067 mL of honey at rest in its bowl.
- Honey: 1420 kg/m³, kinematic viscosity 0.008 m²/s.
- Set: toast on a porcelain plate on a wooden table, a linen napkin and a coffee cup, soft window
  light, 90 mm lens at f/11, from the packed scene template
  `assets/scenes/honey_spoon_toast/scene_template.blend`. The toast surface where honey lands is
  the contact plane z = 0.797 m.
- Rendering: Cycles, 32 samples with denoising, libx264 CRF 18.

## Physics

- Honey in the spoon: Genesis 1.4.3 SPH with the DFSPH pressure solver
  (`simulate_honey_reservoir.py`), 5210 particles at 1.5 mm spacing, surface tension 0.0005
  (solver units), 8 steps of 549 substeps per frame (substep 9.49 µs). Particles that cross the
  front lip leave the bulk.
- Thread: the volume that crosses the lip passes a meniscus buffer (0.2 s relaxation) and is
  extruded continuously from a 2.5 mm nozzle at the lowest point of the lip, so the thread is fed
  from the top and stays continuous, thick at the root and thin below. The thread is a 3D discrete
  viscous rope (after Bergou et al. 2010, Discrete Viscous Threads): lumped node masses and
  gravity, Trouton stretching viscosity 3μA and viscous bending 3μI, both implicit, with
  volume-preserving remeshing (edges 0.3–1.0 mm, time step 0.1 ms). Capillary tension is off
  (σ/μ ≈ 6 mm/s for honey, far below the thread speed).
- Puddle: thread segments that touch the toast or the puddle join a thin film (0.4 mm cells) that
  follows the lubrication equation `h_t = ∇·(ρ g h³ / (3μ) ∇h)`, so the mound grows and slowly
  spreads. The thread and the film take the receiving surface as the plane z = 0.7995 m
  (`--landing-height`).
- Coupling: volume is passed one way from the Genesis bulk to the thread and the puddle; the
  spoon, toast and plate are static.
- Low-viscosity edit: a full 3D DFSPH run (`edits/simulate_honey_reservoir.py`) at 1.0 mm spacing
  (32 steps × 137 substeps per frame); its toast contact uses the exported collision mesh and a
  0.5 mm height field (`edits/export_bread_contact.py`, `edits/receiver_surface.py`).
- Timed removal: the spoon, toast and plate have no state that the honey changes, so the first
  50 frames are the source's cache files and from frame 51 every honey component (spoon, thread,
  buffer and puddle) is empty; all 96 frames are rendered by
  `render_honey_spoon_toast.py --remove-honey-from-frame 51`.
- Surface: thread capsules, meniscus and puddle height field are joined with a smooth minimum
  (0.4 mm) and meshed by marching cubes on a 0.15 mm grid (`mesh_viscous_rope.py`). The honey
  still in the spoon is meshed with splashsurf (`surface_honey_spoon_toast.py --smoothing-iters 24
  --iso-threshold 0.4 --cube-size-factor 0.7 --mesh-subdir meshes_smooth`). The low-viscosity
  surface uses the toast height field (`edits/surface_honey_spoon_toast.py
  --calibrate-isolated-volume --toast-contact … --boundary-mirror`).

## Validation

`physics/validate_viscous_rope.py` writes `technical_acceptance.json`: volume is conserved
(bulk + buffer + thread + puddle against the initial 14.067 mL, relative error below 1e-9), the
thread surfaces are closed and outward and their volume stays within 10% or 0.05 mL of the
simulated volume, the spoon is at 15° in all 96 frames, one continuous strand runs from the lip
to the puddle after landing, and the video is 1280×720, 24 fps, 96 frames, 4 s and decodes
completely. It also records the thread radius range, the top speed, the sideways drift and the
final mound. The timed removal checks that every post-event state and mesh is empty and that the
render shows the honey exactly on frames 1–50.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | honey starts over the lip at frame 20, stretches into a hanging thread and lands on the toast at frame 45 (1.83 s); a continuous thread then feeds a mound of 1.55 mL, 7.3 mm high and about 12 mm in radius at the end |
| `edit_remove_bread` | `DELETE bread` | the toast is removed; the thread lands on the plate (`--landing-height 0.7749954462051392`, measured by `edits/prepare_edits.py`) |
| `edit_remove_honey` | `DELETE honey` | no honey: bread and an empty spoon |
| `edit_lower_viscosity` | `SET honey.viscosity TIMES 0.0125` | 0.008 → 0.0001 m²/s, full 3D DFSPH; fast, runny flow |
| `edit_remove_honey_at_frame_51` | `DELETE honey AT FRAME 51` | frames 1–50 as the source (about 0.24 mL is on the toast at frame 50); from frame 51 there is no honey |

The builder names the edits without the `edit_` prefix (`remove_bread`, `remove_honey`,
`lower_viscosity`, `remove_honey_at_frame_51`). `edit_vocab.py` holds the vocabulary, each
edit's DSL (`EDIT_DSL`) and the source description (`SOURCE_PROMPTS`);
`pcve_edit_dsl.make_prompts(parse(EDIT_DSL[case], VOCAB), VOCAB)` gives the published edit
prompts.

## Assets

- `scenes/honey_spoon_toast` (derived): the packed scene template and its manifest. It has no
  public download. It was built with `tools/build_scene_honey_spoon_toast.py` (spoon, toast and
  plate around the reservoir geometry of `physics/spoon_reservoir_geometry.py`) and dressed by
  `tools/look_honey_spoon_toast.py` (render geometry, materials and lights).
- `blenderkit/toasted_bread` (manual): the toast model, read by `tools/look_honey_spoon_toast.py` when the template is dressed.

```bash
python3 scripts/download_assets.py --scene honey_spoon_toast          # download and check sha256
python3 scripts/download_assets.py --scene honey_spoon_toast --check  # check only
```

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`), pysplashsurf, scikit-image and numba.
- An NVIDIA GPU for the Genesis reservoir and for Cycles; the thread model runs on the CPU
  (about 35 s).
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.
- The accepted simulation caches: the builder reads the spoon reservoir run and the bulk surface
  read-only (`--reservoir-run`, `--bulk-run`). They are simulation results kept in the published
  suite (see Outputs), not assets.

## Commands

Run from the repository root.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/honey_spoon_toast/build_pcve_honey_spoon_toast.py \
  --out-root renders/honey_spoon_toast --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/honey_spoon_toast/build_pcve_honey_spoon_toast.py \
  --out-root renders/honey_spoon_toast --gpu 0
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/honey_spoon_toast/build_pcve_honey_spoon_toast.py \
  --out-root renders/honey_spoon_toast_with_edits --with-edits --gpu 0
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/honey_spoon_toast/simulate_honey_reservoir.py \
  --out renders/honey_spoon_toast/reservoir
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/honey_spoon_toast/edits/build_timed_remove_honey.py \
  --out-root renders/honey_spoon_toast/timed_remove_honey
bash scripts/rigid_fluid/honey_spoon_toast/tools/pipeline_viscous_rope.sh viscous_rope "0 1"
```

- The builder runs the thread model (`simulate_honey_spoon_toast.py`, which runs
  `simulate_viscous_rope.py`), checks that its bulk particles equal those of `--bulk-run` and links
  that run's bulk surface (`physics/prepare_honey_bulk.py`), meshes the thread
  (`mesh_viscous_rope.py`), renders with
  `--samples 32 --mesh-subdir meshes_smooth --extra-mesh-subdir filament_meshes --encode` and
  validates. `--reservoir-run` and `--bulk-run` default to the `reservoir_ts1` and `rope_source`
  runs in the published suite.
- `--with-edits` also runs `edits/reproduce.py --work-dir <out-root>/edits --gpu <id>`: it
  prepares the three edit scenes from the template (`edits/prepare_edits.py`), exports the plate
  and toast contacts, simulates `remove_bread` and `lower_viscosity`, renders the three edits on
  the CPU (`edits/render_edit.py`, `edits/render_sequence.py`), writes review sheets
  (`edits/make_review.py`) and builds the timed removal.
- `simulate_honey_reservoir.py` runs the spoon reservoir alone (GPU);
  `surface_honey_spoon_toast.py --run <run>` meshes the bulk of a thread run with the options
  listed under Physics.
- `edits/build_timed_remove_honey.py` builds the timed removal alone (defaults:
  `DELETE honey AT FRAME 51`, the `rope_source` run and the scene template).
- `tools/pipeline_viscous_rope.sh RUN_NAME "GPU_IDS"` runs the source chain with the render split
  over several GPUs, into `renders/honey_spoon_toast/RUN_NAME`.

## Outputs

- `renders/honey_spoon_toast/source/honey_spoon_toast.mp4`: the rendered source video.
- `renders/honey_spoon_toast/runs/source/`: thread and puddle state, `meshes_smooth/`,
  `filament_meshes/`.
- `renders/honey_spoon_toast/technical_acceptance.json`: checks of
  `physics/validate_viscous_rope.py`.
- `<out-root>/edits/<case>/render/honey_spoon_toast.mp4`: the rendered edits (with `--with-edits`).
- `renders/honey_spoon_toast/pipeline_manifest.json`: the plan and per-stage logs.
- The published suite is `renders/pcve_suites/pcve_honey_spoon_toast_suite/`; the builder does
  not write there. Its `inputs/04_realtime_runs/` keeps the runs behind the videos:
  `reservoir_ts1` (Genesis spoon reservoir with the `simulate_honey_reservoir.py` defaults),
  `rope_source` (thread model of the source with `meshes_smooth/` and `filament_meshes/`),
  `rope_plate` (thread landing on the plate), `lowvisc_ts1` (the low-viscosity DFSPH run with its
  surface) and `timed_51` (the derived cache of the timed removal). The edit scene files and the
  toast contact height field are in `inputs/02_honey_spoon_toast_edits/<case>/`. Each case's
  `ground_truth_transforms.json` holds the fixed spoon, toast and plate; the honey is not tracked.

## Code layout

- `build_pcve_honey_spoon_toast.py`: thread simulation, meshing, rendering, validation, optional edits (entry point).
- `simulate_honey_spoon_toast.py`: thread model (entry point; runs `simulate_viscous_rope.py`).
- `render_honey_spoon_toast.py`: Blender rendering, including the timed removal (entry point).
- `simulate_honey_reservoir.py`: Genesis DFSPH spoon reservoir.
- `simulate_viscous_rope.py`: thread and puddle solver.
- `mesh_viscous_rope.py`: thread and puddle meshing.
- `surface_honey_spoon_toast.py`: bulk honey surface in the spoon.
- `physics/spoon_reservoir_geometry.py`: spoon reservoir geometry.
- `physics/prepare_honey_bulk.py`: bulk-surface reuse check.
- `physics/validate_viscous_rope.py`: technical acceptance checks.
- `edits/prepare_edits.py`, `edits/export_contact.py`, `edits/export_bread_contact.py`, `edits/receiver_surface.py`: edit scenes and plate and toast contacts.
- `edits/simulate_honey_reservoir.py`, `edits/surface_honey_spoon_toast.py`: the low-viscosity reservoir and its surface with toast contact.
- `edits/render_edit.py`, `edits/render_sequence.py`, `edits/make_review.py`: edit rendering and review sheets.
- `edits/build_timed_remove_honey.py`: the timed removal.
- `edits/reproduce.py`: runs all edits.
- `tools/build_scene_honey_spoon_toast.py`, `tools/look_honey_spoon_toast.py`: scene template builder and dressing.
- `tools/pipeline_viscous_rope.sh`: multi-GPU source pipeline.
- `edit_vocab.py`: edit vocabulary, edit DSL and source prompts.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases, configuration, data locations and published video hashes.

## Limitations

- Outside the spoon this is a reduced-order model, not a full 3D free-surface simulation: volume
  is taken one way from the Genesis bulk, with no momentum or capillary feedback.
- No rope coiling where the honey lands; the puddle has no surface tension, contact angle or
  absorption into the bread.
- The meniscus buffer and nozzle radius are modelling parameters, not calibrated.
