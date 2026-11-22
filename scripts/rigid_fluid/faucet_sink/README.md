# faucet_sink

A continuous stream of water leaves a bathroom faucet, strikes the closed sink basin, spreads
along it and collects for four seconds with the drain blocked. This is a rigid–fluid scene: the
liquid is simulated against a static basin. The source video is 4 s at 24 fps (96 frames),
1280×720.

## Scene

- Guest bathroom with a wall-mounted sink; Z-up metric scene from the template
  `assets/scenes/faucet_sink/` (see Assets).
- Faucet: inner outlet radius 3.3 mm (6.6 mm diameter); water leaves vertically downward at
  0.6 m/s.
- Water: kinematic viscosity 1e-6 m²/s.
- Basin: a hidden collision proxy that follows the basin surface, separate from the detailed
  visual mesh. The central drain is closed, so water accumulates. In every case the proxy's
  96-triangle centre pole under the drain is replaced by a flat cap (a change of at most
  0.39 mm that removes a sub-voxel singularity).
- Camera, lighting, outlet size, drain and collision geometry are the same in every case.
- Rendering: Blender EEVEE Next, 128 TAA samples, 1280×720, frames 1–96 at 24 fps.

## Physics

- Solver: Blender 4.3.2 Mantaflow FLIP liquid, domain resolution 144, FLIP ratio 0.5, mesh
  scale 2, diffusion-based viscosity (base 1.0, exponent 6, i.e. 1e-6 m²/s).
- The faucet is an `INFLOW` flow object with initial velocity; the basin proxy is a static
  collision object.
- High-viscosity edit: Blender's dedicated viscosity solver (diffusion off) with a planar
  6.6 mm outlet, no source dilation, resolution 192, four particles per cell, mesh particle
  radius 1.0, CFL 1.0, adaptive steps 4–20 and fractional basin boundaries. Viscosity, outlet,
  inflow, gravity and collision surface are otherwise unchanged.
- Low-flow edit: the hidden inlet source is 2.5 mm in radius with no source dilation (3.3 mm
  with 1.5 voxels in the source), so that the delivered volume follows the lower speed; the
  visible outlet is unchanged.
- Timed stop: the inlet is switched off with constant animation keys, because velocity alone
  does not stop an `INFLOW` object from adding volume. The evaluated timing is saved in
  `<out-root>/cases/edit_stop_flow_at_2s/work/inflow_schedule.json`.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | 0.6 m/s inflow, 1e-6 m²/s |
| `edit_low_flow` | `SET faucet.inflow_velocity TIMES 0.333333` | inflow 0.6 → 0.2 m/s, less water delivered |
| `edit_high_flow` | `SET faucet.inflow_velocity TIMES 2.5` | inflow 0.6 → 1.5 m/s |
| `edit_high_viscosity` | `SET water.viscosity TIMES 20000` | viscosity 1e-6 → 0.02 m²/s |
| `edit_stop_flow_at_2s` | `SET faucet.inflow_velocity TIMES 0 AT FRAME 49` | frames 1–48 as the source; from frame 49 the inflow stops (velocity zero, inlet disabled) and the water already in the basin stays |

## Assets

- `scenes/faucet_sink` (derived): the scene template with the sink, faucet, basin proxy,
  lighting and camera. It is made by this project and has no public download.

```bash
python3 scripts/download_assets.py --scene faucet_sink          # download and check sha256
python3 scripts/download_assets.py --scene faucet_sink --check  # check only
```

Assets live in `assets/` at the repository root; set `PCVE_ASSETS_DIR` to use another location.

## Requirements

- System `python3` (standard library only) for the builder.
- Blender 4.3.2 (Mantaflow is built in), found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- An NVIDIA GPU for EEVEE rendering.
- `ffmpeg` and `ffprobe` for the video check.

## Commands

Run from the repository root.

```bash
python3 scripts/rigid_fluid/faucet_sink/build_pcve_faucet_sink.py --out-root renders/faucet_sink --dry-run
python3 scripts/rigid_fluid/faucet_sink/build_pcve_faucet_sink.py --out-root renders/faucet_sink \
  --cases source edit_low_flow edit_high_flow edit_high_viscosity edit_stop_flow_at_2s --threads 16
python3 scripts/rigid_fluid/faucet_sink/build_pcve_faucet_sink.py --out-root renders/faucet_sink \
  --stage verify --cases source
```

- Only `source` runs when `--cases` is not given. For each case the builder prepares the scene
  from the template (`appearance/prepare_faucet_sink.py`), bakes the liquid
  (`simulate_faucet_sink.py`), renders (`render_faucet_sink.py`) and checks the video.
- `--stage` runs one stage in a root created by the same plan; existing products are never
  overwritten. `--template <file>` selects another copy of the scene template.
- Each case keeps its own `work/fluid_cache`; caches are never shared between cases.

## Outputs

- `renders/faucet_sink/cases/<case>/output/video.mp4`: the rendered video.
- `renders/faucet_sink/cases/<case>/output/prompts.json`: edit DSL and prompts.
- `renders/faucet_sink/cases/<case>/work/`: the prepared scene, `scene_baked.blend` and the fluid
  cache.
- `renders/faucet_sink/pipeline_manifest.json`: the plan and per-stage logs.
- The published suite is `renders/pcve_suites/pcve_faucet_sink_suite/`; the builder does not
  write there.

## Code layout

- `build_pcve_faucet_sink.py`: prepare, simulate, render and verify the selected cases (entry point).
- `simulate_faucet_sink.py`: Mantaflow bake of one case (entry point, runs in Blender).
- `render_faucet_sink.py`: rendering and prompt record of one case (entry point, runs in Blender).
- `appearance/prepare_faucet_sink.py`: checks the template and applies a case's configuration.
- `edit_vocab.py`: edit DSL vocabulary with SI units.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases and video hashes of the published suite.

## Limitations

- Free-surface liquid against a static basin: no pipe pressure, faucet aeration,
  temperature-dependent viscosity or sink deformation.
- The collision proxy is separate from the detailed visual basin mesh.
