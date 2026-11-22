# juice_dispenser_orange_cup

A countertop juice dispenser on a café counter pours orange juice continuously from the metal
outlet inside its transparent nozzle into a drinking glass, which fills to about 40% in four
seconds; three oranges lie beside it. This is a rigid–fluid scene: the liquid flows against
static rigid effectors. The source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Juice: 1040 kg/m³, kinematic viscosity 4e-6 m²/s.
- Outlet: a fixed 3.5 mm radius aperture with outlet velocity (0, 0, −1.20) m/s for the whole
  shot, about 46.18 mL/s.
- Glass: 451.94 mL capacity. Visible glass and collision geometry are separate meshes.
- Set: dispenser, glass and three oranges on the counter, from the template
  `assets/scenes/juice_dispenser_orange_cup/scene_template.blend`.
- Rendering: Cycles, 32 samples.

## Physics

- Solver: Blender 4.3.2 Mantaflow FLIP against static rigid effectors (one-way: the liquid does
  not move the glass), domain resolution 160, adaptive time steps 8–16 per frame.
- Inflow: the aperture covers 20 MAC faces at resolution 160 (area 3.8503e-5 m², 0.05% above the
  circle). Particles are born from the integrated supply `A·v·dt`, and the solver extension in
  `appearance/flux_boundary.py` corrects the level-set isovalue before pressure projection and in
  mesh reconstruction so the injected volume is preserved. Finished meshes and videos are never
  rescaled. The extension reads Blender 4.3.2's grid layout and is tied to that version.
- Paste-like edit: domain resolution 96, PIC transfer (FLIP ratio 0), a fractional inlet with the
  same area and an implicit coupled strain-rate viscosity operator
  (`physics/coupled_viscosity.py`, solving `(M + αBᵀB) u_new = M u_old` by conjugate gradients
  with relative tolerance 1e-7). Because of these quality settings it is not an equal-quality,
  viscosity-only pair with the source.
- Timed stop: the inlet integrator clips the substep that straddles t = 2.0 s, stops particle
  births and sets the outlet velocity to zero from Blender frame 49. Mantaflow's frame k holds the
  state at k/24 s, so the first video frame the stop affects is frame 48, which is the frame the
  edit's DSL and prompts name.

## Validation

All baked surfaces are closed, the volume in the glass grows monotonically, no liquid lies
outside the glass in the cup's height band, and the per-frame difference between mesh and
injected volume stays below 0.01%. In the paste-like edit all 1101 viscous steps converged and
dissipated energy; in the timed stop all 418 solver steps after the stop have zero inlet flux and
no new particles.

## Cases

Retained volume is measured from the closed baked surface inside the glass after 4 s (liquid
still falling above the lip is excluded).

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | outlet 1.20 m/s; 181.66 mL retained (40.2% of the glass) |
| `edit_high_flow_speed` | `SET dispenser.flow_speed TO 2.4` | outlet 1.20 → 2.40 m/s; 365.69 mL (2.01× source) |
| `edit_low_flow_speed` | `SET dispenser.flow_speed TO 0.60` | outlet 1.20 → 0.60 m/s; 90.00 mL (0.50× source) |
| `edit_high_viscosity` | `SET orange_juice.viscosity TO 0.0004` | viscosity × 100; 182.83 mL, same input with slower, thicker flow |
| `edit_paste_like_viscosity` | `SET orange_juice.viscosity TO 0.04` | viscosity × 10000; 182.04 mL, the strand folds and piles like a paste |
| `edit_delete_orange_juice` | `DELETE orange_juice` | all juice removed from frame 1; 0 mL, no bake |
| `edit_stop_flow_at_2s` | `SET dispenser.flow_speed TO 0 AT FRAME 48` | frames 1–47 as the source; the outlet stops at 2.0 s and the juice already poured keeps falling and settles; 92.14 mL |

The builder names the source `juice_dispenser_orange_cup_source`; the published suite stores it
as `source`. The builder writes each edit's prompts with `make_prompts` from `edit_vocab.py`; the
source description is `SOURCE_DESCRIPTION` in the builder.

## Assets

- `scenes/juice_dispenser_orange_cup` (derived): the scene template with the dispenser, glass,
  oranges, counter, lighting and camera. It is made by this project and has no public download.

```bash
python3 scripts/download_assets.py --scene juice_dispenser_orange_cup          # download and check sha256
python3 scripts/download_assets.py --scene juice_dispenser_orange_cup --check  # check only
```

## Requirements

- System `python3` for the builder, the volume annotations and the unit tests.
- Blender 4.3.2 (Mantaflow is built in); the flux extension depends on this exact version.
- An NVIDIA GPU for rendering.
- For `edit_paste_like_viscosity` only: SciPy 1.11.4 for Blender's Python 3.11
  (`requirements-solver.txt`), installed into `.runtime/juice_dispenser_orange_cup/solver_vendor/`
  by `tools/install_solver_dependency.py` (or pass `--solver-vendor` with an existing copy).
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
python3 scripts/rigid_fluid/juice_dispenser_orange_cup/tools/install_solver_dependency.py
python3 scripts/rigid_fluid/juice_dispenser_orange_cup/build_pcve_juice_dispenser_orange_cup.py \
  --out-root renders/juice_dispenser_orange_cup --dry-run
python3 scripts/rigid_fluid/juice_dispenser_orange_cup/build_pcve_juice_dispenser_orange_cup.py \
  --out-root renders/juice_dispenser_orange_cup
python3 scripts/rigid_fluid/juice_dispenser_orange_cup/build_pcve_juice_dispenser_orange_cup.py \
  --out-root renders/juice_dispenser_orange_cup/edits \
  --reuse-source renders/juice_dispenser_orange_cup/cases/juice_dispenser_orange_cup_source \
  --cases edit_stop_flow_at_2s
python3 scripts/rigid_fluid/juice_dispenser_orange_cup/simulate_juice_dispenser_orange_cup.py \
  --out renders/juice_dispenser_orange_cup/annotations.json
```

- `--cases` selects edit cases (the source is always included); `--skip-existing` verifies and
  reuses finished videos. `--reuse-source` adds edits to a finished source without re-baking it.
- Each case bakes into its own cache under its output directory; a new bake refuses a non-empty
  cache. `--skip-fluid-bake --skip-render` only writes the configured `.blend` files and metadata.
- `simulate_juice_dispenser_orange_cup.py` writes the expected per-frame volumes without Blender.
- The timed stop bake takes about 46 minutes.

## Outputs

- `renders/juice_dispenser_orange_cup/cases/<case>/video.mp4`: the rendered video.
- `.../cases/<case>/ground_truth.json`: per-frame injected and measured retained volumes.
- `.../cases/<case>/boundary_flux.json`: inflow budget, applied velocities and every volume correction.
- `.../cases/<case>/volume_measurements.json`: volume of each closed baked surface, clipped to the glass.
- `.../cases/<case>/parameter_audit.json`: before/after physics, solver velocity and viscosity flags.
- `.../cases/<case>/scene_baked_final.blend` and the cache: the baked scene (rendering reloads it
  without changing fluid settings).
- `renders/juice_dispenser_orange_cup/suite_manifest.json`: all cases.
- Without `--out-root` the builder writes to `renders/juice_dispenser_orange_cup/suite_build/`. The published
  suite is `renders/pcve_suites/pcve_juice_dispenser_orange_cup_suite/`; the builder does not
  write there.

## Code layout

- `build_pcve_juice_dispenser_orange_cup.py`: builds the source and edits, writes the suite manifest (entry point).
- `simulate_juice_dispenser_orange_cup.py`: per-frame volume annotations without Blender (entry point).
- `render_juice_dispenser_orange_cup.py`: configure, bake, render and encode one case (entry point, runs in Blender).
- `appearance/flux_boundary.py`: volume-conserving inflow extension.
- `physics/coupled_viscosity.py`: implicit strain-rate viscosity for the paste-like edit.
- `physics/liquid_measurements.py`: closed-surface volume measurements.
- `tools/install_solver_dependency.py`, `requirements-solver.txt`: install the pinned SciPy wheel.
- `edit_vocab.py`: edit DSL vocabulary (outlet speed, viscosity).
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: scene description, configuration, accepted videos and provenance.

## Limitations

- Prescribed inflow against static effectors: the liquid does not push the glass.
- The global volume constraint assumes nothing overflows; other setups need an explicit loss
  budget.
- The paste-like edit is a very viscous Newtonian approximation, not a calibrated paste (no yield
  stress or shear thinning).
