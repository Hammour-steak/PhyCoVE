# traditional_tea_pour

Tea pours from the spout of a tilted traditional porcelain teapot into a small matching cup on a
coaster at a tea table, fills it and splashes a little onto the table. This is a rigid–fluid
scene: the liquid enters through a prescribed inlet and flows against fixed rigid geometry. The
source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Tea: 1000 kg/m³, kinematic viscosity 1.05e-6 m²/s.
- Inflow: 0.5 m/s at the spout, 12.5 cm above the table, about 11.7 mL/s from 0.5 s to 3.5 s.
- Cup: rim 6.5 cm above the table, on a coaster; teapot, cup and coaster are fixed.
- Environment: the refined tea-table scene `scene_environment_refined.blend` with the tea set
  embedded.
- Rendering: Cycles, 128 samples, 180° velocity motion blur, the liquid surface loaded through a
  native Alembic cache.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver; 32 steps per frame with 4 substeps
  each. Fixed-mass particles are emitted only at the spout: one regular particle layer advances
  past the nozzle per solver step, so the particle size is the inflow speed times the step
  (about 0.65 mm in the source) and the nozzle diameter is nine particle sizes.
- Rigid geometry: the teapot, the repaired cup collider and the coaster are fixed; there is no
  freely moving rigid body and no two-way rigid/liquid coupling.
- Inputs: the solver reads `input_config.json`, `acceptance_plan.json` and the cup, coaster and
  cavity meshes (`cup_collider.obj`, `visible_solid_closed.obj`, `audit_cavity_closed.obj`,
  `actual_inner_open.obj`/`.npz`, `visual_cup_world.npz`, `collider_repair.json`,
  `coaster_world.obj`) from the contact input folder.
- Speed edits keep particle size, nozzle aperture, material and integration steps; in
  `speed_2x` the domain grows to ±2 m in x/y for the faster splash.
- Timed stop: `physics/simulate_tea_edits.py --resume-from <source> --resume-frame 49` copies the
  source's particles (and `physics/run_compute.py` its surfaces) for frames 1–48, loads the
  source's state after frame 48 (solver time 2.0 s: positions, velocities, active set and emitter
  position, checked bit for bit) and solves frames 49–96 with an empty inlet. All rigid geometry
  is fixed, so the particles are the whole state.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | inflow 0.5 m/s |
| `edit_speed_2x` | `SET tea.flow_speed TIMES 2` | inflow 1.0 m/s; mass and volume flux double |
| `edit_speed_0p5x` | `SET tea.flow_speed TIMES 0.5` | inflow 0.25 m/s |
| `edit_remove_tea` | `DELETE tea` | no liquid at any time (the dry decorative leaves stay) |
| `edit_stop_flow_at_2s` | `SET tea.flow_speed TO 0 AT FRAME 49` | frames 1–48 as the source; inflow and flux become zero at frame 49 and the tea already emitted keeps moving |

The edits workflow names the edits without the `edit_` prefix (`speed_2x`, `speed_0p5x`,
`remove_tea`, `stop_flow_at_2s`). `edit_vocab.py` states them in the edit DSL and gives their
prompts (`make_prompts`) and the source description.

## Assets

The scene has no `assets.json` entry and reads no files from `assets/`. The tea set (teapot, cup
and coaster) is a CC BY 4.0 Sketchfab model embedded in the refined environment scene;
`scene_manifest.json` records its source and attribution.

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`); the builders themselves run with system `python3`.
- An NVIDIA GPU for Genesis; the Genesis launchers pick an empty GPU themselves, and rendering
  falls back to the CPU.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.
- The solver inputs and the environment scene: by default they are read from the accepted cases
  kept in the published suite under `inputs/source/cases/`: `contact_inputs/` (solver inputs
  and meshes), `source_run/` (the accepted source solve and its table-cap geometry) and
  `environment_render/` (the refined environment scene the source video was rendered from);
  `--inputs`, `--input-blend` and `--baseline-caps` relocate them. The edits workflow reads the
  accepted source run and environment from the same place. The native runs of the published
  edits are kept under `inputs/edits/`, except the timed stop, which is in
  `renders/traditional_tea_pour/native/stop_flow_at_2s/`.

## Commands

Run from the repository root; each output root must be new.

```bash
python3 scripts/rigid_fluid/traditional_tea_pour/build_pcve_traditional_tea_pour.py \
  --out-root renders/traditional_tea_pour/source_run --dry-run
python3 scripts/rigid_fluid/traditional_tea_pour/build_pcve_traditional_tea_pour.py \
  --out-root renders/traditional_tea_pour/source_run
python3 scripts/rigid_fluid/traditional_tea_pour/build_traditional_tea_edits.py \
  --out-root renders/traditional_tea_pour/edits --dry-run
python3 scripts/rigid_fluid/traditional_tea_pour/build_traditional_tea_edits.py \
  --out-root renders/traditional_tea_pour/edits
```

- The source pipeline runs the contact solve, surface reconstruction, contact and numerical
  checks, native Alembic scene preparation, Cycles rendering, encoding and the video check, and
  writes `pipeline_manifest.json` and stage logs.
- `build_traditional_tea_edits.py` builds the four edits (also reachable as
  `--workflow edits` of the builder); `--resume` continues the same root.
- `tools/reproduce_tea_contact.sh INPUT_FOLDER NEW_CASE ENVIRONMENT_BLEND` runs the same source
  steps as one shell script.

## Outputs

- `renders/traditional_tea_pour/source_run/source/`: particles, surfaces, `scene_tea_fixed.blend`,
  the Alembic cache, `video_contact_fixed.mp4` and the acceptance checks.
- `renders/traditional_tea_pour/edits/<case>/`: each edit's particles, surfaces, scene and cache,
  before/after settings, audits, 96-frame checks and video.
- The published suite is `renders/pcve_suites/pcve_traditional_tea_pour_suite/`; the builders do
  not write there.

## Code layout

- `build_pcve_traditional_tea_pour.py`: complete source pipeline (entry point).
- `simulate_traditional_tea_pour.py`: Genesis contact solve of a case (entry point).
- `render_traditional_tea_pour.py`: Blender rendering of a prepared case (entry point; runs `appearance/render_tea_contact.py`).
- `build_traditional_tea_edits.py`: the four edits.
- `physics/prepare_tea_dynamic_case.py`: case preparation.
- `physics/simulate_tea_contact.py`, `physics/launch_tea_contact.py`: the Genesis contact solve and its GPU launcher.
- `physics/simulate_tea_edits.py`, `physics/run_compute.py`: the edit solve.
- `physics/surface_tea_dynamics.py`: surface reconstruction.
- `physics/audit_raw_liquid_cache.py`, `physics/measure_tea_dynamics.py`, `physics/measure_tea_table_caps.py`: cache measurements.
- `appearance/prepare_tea_contact_native.py`, `appearance/prepare_tea_edit_native.py`, `appearance/bind_contact_cache.py`: native Alembic scene preparation.
- `appearance/verify_tea_contact_scene.py`, `appearance/verify_genesis_blend.py`: scene checks.
- `appearance/render_tea_contact.py`, `appearance/render_tea_edit.py`, `appearance/render_tea_direct.py`: Blender rendering of the source and the edits.
- `appearance/launch_tea_render.py`, `appearance/run_render.py`, `appearance/render_tea_chunks.py`, `appearance/render_direct_chunks.py`: render launchers.
- `appearance/tea_environment_state.py`: read-only scene-state ledger.
- `tools/accept_tea_contact.py`, `tools/qa_tea_contact.py`, `tools/validate_genesis_tea.py`, `tools/validate_tea_edit.py`, `tools/summarize_accumulation.py`: contact and numerical acceptance.
- `tools/audit_genesis_actual_cup.py`, `tools/audit_tea_edit_cup.py`, `scripts/pcve_config_diff.py` (shared): cup and configuration audits.
- `tools/package_tea_contact.py`, `tools/package_tea_edits.py`: packaging.
- `tools/branch_cached_tea_delete.py`: the deletion edit from the cached source.
- `tools/reproduce_tea_contact.sh`: the source steps as one shell script.
- `edit_vocab.py`: edit DSL vocabulary, the edits' DSL and the source description.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: scene description, supported cases, configuration, the tea-set asset and the published suite with its video hashes.

## Limitations

- Prescribed rigid geometry and inflow; the liquid does not move the cup.
- In `edit_speed_2x` the landed splash is drawn as thin films with the same volume; this is a
  rendering treatment, not a resolved wetting or absorption model.
