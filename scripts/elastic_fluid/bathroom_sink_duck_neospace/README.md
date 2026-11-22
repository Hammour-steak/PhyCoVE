# bathroom_sink_duck_neospace

A 12 cm rubber duck rests in a porcelain bathroom basin while the chrome faucet runs onto it for
four seconds. The water flows over and around the duck, which wobbles and deforms under the
stream. This is an elastic–fluid scene with two-way coupling between the elastic duck and the
water. The source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Duck: 12 cm, 91 g, density 200 kg/m³, Young's modulus 2 kPa, Poisson ratio 0.45. Its weight
  squashes it by about 7 mm in the basin.
- Water: kinematic viscosity 3e-4 m²/s; the faucet outlet runs at 0.57 m/s about 8 cm above the
  duck, emitting about 4.8 L/min (whole particle layers are released; nominal 4.5 L/min).
- Room: a bathroom model with window, ceiling downlight and vanity bar; 5400 K white balance.
- Rendering: Cycles (GPU), 128 samples with denoising, 180° motion blur from the water velocity.
  The visible duck mesh is skinned onto the MPM particles.

## Physics

- Solver: Genesis 1.4.3 with a neo-Hookean MPM duck (3 mm particles) and DFSPH water (1.5 mm
  particles), cohesion 5e-4, water–duck viscous coupling 0.5.
- Duck layers: particles deeper than 10 mm (`--skin-thickness`) form the core and use
  `--core-young`; skin and core are equal except in `edit_soft_core_duck`.
- Coupling: the simulator loads `create_boundary_solver()` from
  `../elastic_fluid_duck/simulate_elastic_fluid_duck.py` (`--pool-simulate` names another file):
  ghost SPH particles carried by the MPM duck through an affine material map, equal and opposite
  pressure impulses scattered back onto the MPM grid. The material map's stencil box is
  `--map-width` cells (default 20); the published source, stiff duck, high flow and timed stop
  use 12, the other cases 20.
- Time step: 0.5 s of settling, then 4 s of stream at 24 fps (96 frames), 100 steps per frame;
  MPM substeps follow the elastic wave speed (CFL 0.19, at least 16). Simulation record k is the
  state k/24 s after the faucet opens and is video frame k.
- Timed stop: the inlet closes after record 48 (2.00 s); no velocities are reset. With
  `--source-branch-out SOURCE.npz` the simulator copies the complete solver state (every MPM and
  SPH field, the emitter cursor and the step counters) at the start of frame 49, runs the source
  on, restores the copy bit for bit and runs the edit on, so records 1–48 are the same data in both
  caches. Before the branch it restores and re-runs frame 49 of the source `--branch-replay-frames`
  times (default 2) and records how far those replays differ from the live source and from each
  other (GPU float atomics make repeated runs differ slightly). The published source and timed
  stop come from one such run.

## Validation

The simulation log records, per frame, the worst neighbour-distance stretch of the duck (about
1.2–1.3 in the source, levelling off near 2.1 at twice the outlet speed) and the number of water
particles inside the duck (zero except for the soft core, which reaches 853 particles, about
3 mL, under its base by 4 s).

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | duck E = 2 kPa, outlet 0.57 m/s; the stream dents the head by about 3 mm and tilts it back by up to 18° |
| `edit_stiff_duck` | `SET duck.stiffness TIMES 30` | duck E = 60 kPa (skin and core; 25 MPM substeps); it barely deforms |
| `edit_soft_core_duck` | `SET duck.core_stiffness TIMES 0.1` | core E = 200 Pa under an unchanged 10 mm, 2 kPa skin; slumps from 95 mm to 88 mm high, 78 mm by 4 s |
| `edit_delete_duck` | `DELETE duck` | no duck (no MPM body, no ghost boundary) |
| `edit_delete_water` | `DELETE water` | no water; the duck settles and stays on the dry basin |
| `edit_high_flow` | `SET faucet.inflow_velocity TIMES 2` | outlet 0.57 → 1.13 m/s (about 8.4 L/min emitted); stronger stream |
| `edit_stop_flow_at_2s` | `SET faucet.inflow_velocity TO 0 AT FRAME 49` | frames 1–48 as the source; the inlet closes at 2.00 s and the water and the duck keep evolving |

The builder names the source `bathroom_sink_duck_baseline`; the published suite stores it as
`source`. The builder writes each case's bilingual prompts: the source text is in `SOURCE`, the
edit prompts come from `pcve_edit_dsl.make_prompts` with the builder's `vocabulary()`.

## Assets

- `sketchfab/bathroom_rev1_neospace` (manual): the bathroom room.
- `elastic_fluid/elastic_fluid_duck` (derived): the rubber duck (`scene.blend` and its geometry),
  shared with `elastic_fluid_duck`.

```bash
python3 scripts/download_assets.py --scene bathroom_sink_duck_neospace          # download and check sha256
python3 scripts/download_assets.py --scene bathroom_sink_duck_neospace --check  # check only
```

Manual files need a free Sketchfab account; the script prints the asset page and the file name to
save. Derived files are made by this project and have no public download.

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`) and pysplashsurf.
- An NVIDIA GPU with a driver for CUDA 12.3 or newer for Genesis, and for Cycles. Simulation
  takes about 70–85 s per frame on an RTX 3090.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root with an idle GPU. Two builder runs reproduce the seven cases with
the stencil widths they were published with; the first builds the timed stop and, in the same
run, the source.

```bash
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/bathroom_sink_duck_neospace/build_pcve_bathroom_sink_duck_neospace.py \
  --out-root renders/bathroom_sink_duck_neospace --dry-run
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/bathroom_sink_duck_neospace/build_pcve_bathroom_sink_duck_neospace.py \
  --suite-root renders/bathroom_sink_duck_neospace --map-width 12 \
  --cases edit_stop_flow_at_2s bathroom_sink_duck_baseline edit_stiff_duck edit_high_flow
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/bathroom_sink_duck_neospace/build_pcve_bathroom_sink_duck_neospace.py \
  --suite-root renders/bathroom_sink_duck_neospace --cases edit_soft_core_duck edit_delete_duck edit_delete_water
```

- The builder builds the room (`work/scene.blend`) if missing and prepares the duck geometry, then
  for each case simulates, reconstructs the water and the duck, renders and encodes. All cases
  run by default; `--cases` selects some. `--map-width` applies to every case simulated in that
  run.
- When the source has not been simulated yet and a timed edit is selected, the builder simulates
  the timed edit first with `--source-branch-out` for the source.
- Every step resumes from what exists in `runs/` and `work/`; to redo a look change, delete
  `runs/<case>/render` (and `surfaces` if the surface step changed).

The simulator can also be run on its own; the published source and timed stop came from this
command (duck geometry from the builder's `runs/duck/`):

```bash
.venv-genesis-mpm-sph/bin/python -u scripts/elastic_fluid/bathroom_sink_duck_neospace/simulate_bathroom_sink_duck_neospace.py \
  --duck-solid renders/bathroom_sink_duck_neospace/runs/duck/duck_solid_world.obj \
  --ghost-mesh renders/bathroom_sink_duck_neospace/runs/duck/duck_shell_world.obj --young 2000.0 \
  --inflow-velocity 0.5650471352374982 --map-width 12 --inflow-change-frame 49 --inflow-velocity-after 0.0 \
  --out renders/bathroom_sink_duck_neospace/runs/edit_stop_flow_at_2s/genesis_sim.npz \
  --source-branch-out renders/bathroom_sink_duck_neospace/runs/bathroom_sink_duck_baseline/genesis_sim.npz
```

## Outputs

- `renders/bathroom_sink_duck_neospace/cases/<case>/video.mp4`: the rendered video.
- `renders/bathroom_sink_duck_neospace/cases/<case>/prompts.json`: bilingual prompts.
- `renders/bathroom_sink_duck_neospace/runs/<case>/`: particles, simulation log (`stretch`,
  `inside`), surfaces and frames.
- `renders/bathroom_sink_duck_neospace/suite_manifest.json`: physics, numerical settings, run
  checks, emitted flow and video hash of every case.
- The published suite is `renders/pcve_suites/pcve_bathroom_sink_duck_neospace_suite/`; the
  builder does not write there.

## Code layout

- `build_pcve_bathroom_sink_duck_neospace.py`: room, duck geometry, every case, prompts and the suite manifest (entry point).
- `simulate_bathroom_sink_duck_neospace.py`: coupled MPM/DFSPH simulation and the same-run branch (entry point).
- `render_bathroom_sink_duck_neospace.py`: per-frame rendering in the room (entry point).
- `appearance/scene_bathroom_sink_duck_neospace.py`: builds the room with the camera and the resting duck.
- `appearance/duck_bathroom_sink_duck_neospace.py`: duck solid, ghost shell and rest vertices for the simulation.
- `appearance/surface_bathroom_sink_duck_neospace.py`: water surface meshes with per-vertex velocity and the skinned duck.
- `appearance/look_bathroom_sink_duck_neospace.py`: the render look.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases and published videos.

## Limitations

- The water is more viscous than real water, because a 1.5 mm particle stream cannot resolve
  surface tension; this keeps the stream and the film on the duck continuous but also drags the
  duck's surface.
- A uniformly very soft duck (500 Pa or less) is torn open by the stream within 0.2 s, which is
  why the soft edit softens only the core.
- The coupling operator is loaded from the `elastic_fluid_duck` scene, so a change to
  `../elastic_fluid_duck/simulate_elastic_fluid_duck.py` can change this scene too.
