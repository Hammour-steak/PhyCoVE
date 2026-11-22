# wind_flag

A ceremonial flag hangs from a flagpole on a rooftop and bends and flutters in a gusty wind. This
is an elastic–fluid scene: the flag is a thin elastic shell and the wind acts on it as a
prescribed airflow (one-way: the flag does not change the air). The source video is 4 s at
24 fps (96 frames), 1280×720.

## Scene

- Flag: an isotropic shell 1 mm thick, density 100 kg/m³, Young's modulus 1 MPa, Poisson ratio
  0.3. The hoist is fixed to the top of the shaft, its upper point at 3.63 m (2 cm under the
  3.65 m shaft top and finial).
- Wind: a deterministic, spatially non-uniform gust field in world coordinates, scaled by a
  reference speed of 2 m/s.
- Start: every case starts from the same stored warm state, the source after 3 s of pre-roll at
  1 MPa and 2 m/s (`--from-rest` computes a new one).
- Rendering: Blender EEVEE, 64 samples, rooftop environment.

## Physics

- Solver: Genesis FEM with libuipc IPC shell models (native `NeoHookeanShell` and
  `DiscreteShellBending`); plane-stress μ/λ and the bending stiffness
  `κ = E h³ / [24 (1 − ν²)]` follow from E. IPC contact radius h/2.
- Wind load: a relative-air force on every triangle that depends on the air velocity relative to
  the moving cloth, so the same law also gives passive drag in still air. The reference speed
  scales the whole gust field.
- Timed edit: restores the solver's full native state at 2 s (`World.dump/recover`), so all
  states up to 2 s are identical to the source; it is simulated together with the source
  (`--emit-timed-branch`).
- `wind_flag_config.py` and `scene_spec.json` hold the scene parameters; `edit_vocab.py` declares
  the edits in the edit DSL and generates their prompts.

## Validation

`physics/validate_wind_flag.py` checks the physics and media, asserting the solver's material
coefficients; `appearance/audit_contact_wind_flag.py` samples 381 points per case for contact
between flag and pole in the rendered geometry (thickness and subdivision included);
`appearance/audit_appearance_wind_flag.py` checks the fixed look. Recomputed videos stay marked
for visual review until their full motion is reviewed.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | wind reference 2 m/s, E = 1 MPa |
| `edit_wind_6mps` | `SET wind.speed TIMES 3` | wind reference 6 m/s |
| `edit_young_modulus_100mpa` | `SET flag.young_modulus TIMES 100` | E = 100 MPa |
| `edit_wind_drop_at_2s` | `SET wind.speed TIMES 0.25 AT FRAME 49` | frames 1–48 as the source; at 2 s the wind reference drops to 0.5 m/s |
| `edit_wind_0p5mps` | `SET wind.speed TIMES 0.25` | wind reference 0.5 m/s from frame 1 |
| `edit_wind_0mps` | `SET wind.speed TIMES 0` | no ambient wind from frame 1; the flag keeps its initial motion, sags and slows under drag |

The builder names the source `wind_flag_baseline`; the published suite stores it as `source`.
`simulate_wind_flag.py --case` uses native names: `source`, `flow_6mps`, `young_stiff`,
`wind_drop_at_2s`, `flow_0p5mps` and `flow_0mps`.

## Assets

- `blenderkit/un_ceremonial_flag` (manual, plus derived prepared files): the flag, pole and
  textures.
- `elastic_fluid/wind_flag_extended` (derived): the stored warm state and the accepted results of
  every case, read by `--import-approved`. It has no public download.

```bash
python3 scripts/download_assets.py --scene wind_flag          # download and check sha256
python3 scripts/download_assets.py --scene wind_flag --check  # check only
```

Manual files need a free BlenderKit account; the script prints the asset page and the file names
to save.

## Requirements

- Python 3.10 environment `.venv-genesis-mpm-sph/` at the repository root with the packages of
  `requirements.txt`: `genesis-world==1.4.3`, plus `pyuipc==0.0.29` and `polyscope==2.5.0` for
  IPC. The IPC packages are loaded from an isolated directory (`--ipc-deps` or `PCVE_IPC_DEPS`,
  default `.runtime/wind_flag_ipc_deps` in the repository root) so the shared environment stays
  unchanged.
- An NVIDIA GPU.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/wind_flag/build_pcve_wind_flag.py --list-cases
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/wind_flag/build_pcve_wind_flag.py --out-root renders/wind_flag --dry-run
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/wind_flag/build_pcve_wind_flag.py --out-root renders/wind_flag --gpu auto
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/wind_flag/build_pcve_wind_flag.py \
  --out-root renders/wind_flag/accepted --import-approved
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/wind_flag/simulate_wind_flag.py \
  --out-dir renders/wind_flag/young_stiff --case young_stiff
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/wind_flag/render_wind_flag.py \
  --simulation-dir renders/wind_flag/young_stiff --out-dir renders/wind_flag/young_stiff_render --gpu auto
```

- `--gpu auto` recomputes all six cases; `--import-approved` instead verifies every recorded hash
  of the stored inputs and accepted results (the `elastic_fluid/wind_flag_extended` asset) and
  lays them out as a suite, refusing conflicting content.
- `--stage prepare`, `simulate`, `render` or `validate` runs one step; `--skip-existing` resumes
  finished stages. A partial simulation or a different configuration needs a new output root.
- `--cases` selects edits; the source is always included.
- The last two commands simulate and render one case on their own (`--case` also takes
  `flow_6mps`, `flow_0p5mps` and `flow_0mps`).

## Outputs

- `renders/wind_flag/suite_manifest.json`: the source and five edits.
- `renders/wind_flag/cases/<case>/video.mp4`: the rendered video.
- `.../cases/<case>/simulation/genesis_flag_cache.npz`: float64 positions and velocities,
  triangle topology, rest positions and pinned vertices, with a ground-truth index into it.
- `.../cases/<case>/`: prompts, scenario overrides and metadata, the physics edit, and the packed
  rendered `scene.blend`.
- Without `--out-root` the builder writes to `renders/wind_flag/suite_build/`. The
  published suite is `renders/pcve_suites/pcve_wind_flag_suite/`; the builder does not write
  there.

## Code layout

- `build_pcve_wind_flag.py`: prepare, simulate, render, audit and import (entry point).
- `simulate_wind_flag.py`: Genesis FEM/IPC simulation (entry point).
- `render_wind_flag.py`: rendering, encoding and frame checks (entry point).
- `wind_flag_config.py`: paths, scene parameters and output safety helpers.
- `scene_spec.json`: scene parameters.
- `edit_vocab.py`: edit DSL vocabulary and prompts.
- `physics/validate_wind_flag.py`: physics and media checks.
- `appearance/scene_wind_flag.py`: Blender scene and cache playback.
- `appearance/audit_contact_wind_flag.py`, `appearance/audit_appearance_wind_flag.py`: contact and appearance audits.
- `requirements.txt`: Python packages, including the isolated IPC packages.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases and the published suite.

## Limitations

- The wind is a one-way prescribed airflow, not resolved CFD or two-way fluid–structure coupling.
- The flag is a hypothetical isotropic shell, not a calibrated woven fabric.
- Contact sampling is finite, not a continuous-time proof.
