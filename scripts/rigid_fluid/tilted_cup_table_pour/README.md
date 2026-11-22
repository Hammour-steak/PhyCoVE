# tilted_cup_table_pour

A white ceramic cup rests at a 58° tilt on a walnut block on a sunlit oak kitchen worktop, holding
81 mL of water whose surface starts 16 mm above the low inner rim. The water drains over the rim
in a clear stream and spreads across the worktop. This is a rigid–fluid scene: the water flows
against the fixed cup, block and table. The source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Geometry: cup 74 mm wide and 55 mm tall at 58°; support block 35 × 45 × 28 mm; tabletop at
  z = 0 (`physics/contact_geometry.py` keeps the cup, block and table tangent).
- Water: 81 mL, 998.2 kg/m³, kinematic viscosity 1.0e-6 m²/s, surface tension 0.072 N/m, at rest
  at the start. Glaze and oak are fully wetted (contact angle about 67°).
- Simulated table patch: x −0.06…0.42 m, y −0.17…0.17 m; `edit_delete_cup` simulates the whole
  worktop (x ±0.60 m, from the front edge at y = −0.42 m to the tiled wall at y = 0.296 m).
- Rendering: Cycles, 128 samples, 180° motion blur from the water's per-vertex velocity, sunlit
  kitchen with ceramic and wood details and a wet-wood map.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 101k particles of 1 mm on a 0.93 mm
  rest lattice.
- Time step: 96 frames at 24 fps, 10 steps per frame of 16 substeps each.
- Boundaries: the cup, the block and the tabletop are static ghost-particle boundaries that
  carry their own pressure; contact-line friction 1000/s on the oak.
- Density solve: split (new compression through the velocities, existing compression through
  the positions).
- Surface tension: Akinci γ = 1.5 (0.072 N/m at 1 mm, from the oscillation period of a
  zero-gravity blob).
- Viscosity: up to 2e-5 m²/s the explicit SPH viscosity; above that an implicit no-slip solve
  (conjugate gradients).
- Gravity: Genesis 1.4.3's DFSPH applies gravity twice per substep;
  `scripts/pcve_dfsph_patches.py` removes the second call.
- Water surface for rendering: the 1 mm particles land on the table in a sheet one or two
  particles thick, below the resolution at which SPH holds a film together. The table water is
  therefore meshed from a volume-conserving height field (0.5 mm grid, gaps up to about 2 cm
  bridged, depth levelled over 12 mm, rounded 1.5 mm edge,
  `physics/film_tilted_cup_table_pour.py`). Where the water has been and gone, the oak is only
  darkened and glossier (wet map). The cup water, stream and drops are a pysplashsurf surface,
  trimmed where they enter the film and sealed onto the cup's rolled lip, the block and the table.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | 998.2 kg/m³, 1.0e-6 m²/s, 0.072 N/m; a thin sheet up to about 25 cm long, 34.5 mL stays in the cup and 46.5 mL on the table |
| `edit_high_viscosity_water` | `SET water.viscosity TIMES 100` | 1.0e-4 m²/s (implicit viscosity); a compact, thicker puddle about 14 cm long, 37.2 mL stays in the cup |
| `edit_delete_water` | `DELETE water` | no liquid; the empty cup rests on its block and the worktop stays dry |
| `edit_delete_cup` | `DELETE cup` | `--no-cup`, whole worktop simulated; the water lands at once, runs up to the tiled wall and spreads 20–40 cm sideways |

The builder names the source `tilted_cup_table_pour_baseline`; the published suite stores it as
`source`. `edit_vocab.py` maps the DSL onto simulator flags.

## Assets

- `rigid_fluid/tilted_cup_environment` (url and derived): the kitchen environment with the cup
  set, cutting board and textures; its derived files are made by this project and have no public
  download. It is shared with `cup_water_drop`.

```bash
python3 scripts/download_assets.py --scene tilted_cup_table_pour          # download and check sha256
python3 scripts/download_assets.py --scene tilted_cup_table_pour --check  # check only
```

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`) and pysplashsurf.
- An NVIDIA GPU for Genesis and for Cycles. Simulation takes 12–16 s per frame on an RTX 3090
  (25 s with implicit viscosity, about 65 s on the whole worktop).
- Blender 4.3.2 (`--blender`, or `$BLENDER`, else `blender` on `PATH`).
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root with an idle GPU.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/tilted_cup_table_pour/build_pcve_tilted_cup_table_pour.py \
  --out-root renders/tilted_cup_table_pour --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/tilted_cup_table_pour/build_pcve_tilted_cup_table_pour.py \
  --suite-root renders/tilted_cup_table_pour
```

- For each case the builder simulates, reconstructs the water surface, the tabletop film and the
  wet-wood map, renders the kitchen and encodes; all four cases run by default (`--cases` selects
  some, by the builder names).
- Every step resumes from what exists in `renders/tilted_cup_table_pour/runs/<case>/`, and
  rendering only renders missing frames. To redo a look change, delete `render/` and `video.mp4`
  there (and `meshes_1mm/`, `wetmap/` and `runs/<case>/surface_log.json` if the surface step changed).

## Outputs

- `renders/tilted_cup_table_pour/cases/<case>/video.mp4`: the rendered video.
- `renders/tilted_cup_table_pour/cases/<case>/prompts.json`: bilingual prompts.
- `renders/tilted_cup_table_pour/runs/<case>/`: fp32 positions, fp16 velocities, `sim_log.json`,
  `simulation_report.json`, `meshes_1mm/`, `wetmap/` and render frames.
- `renders/tilted_cup_table_pour/suite_manifest.json`: physics, numerical settings, run summary
  and video hash of every case.
- The published suite is `renders/pcve_suites/pcve_tilted_cup_table_pour_suite/`; the builder
  does not write there.

## Code layout

- `build_pcve_tilted_cup_table_pour.py`: full suite: simulate, surface, render, manifest (entry point).
- `simulate_tilted_cup_table_pour.py`: Genesis DFSPH simulation (entry point).
- `surface_tilted_cup_table_pour.py`: per-frame water mesh and wet map.
- `render_tilted_cup_table_pour.py`: Blender rendering of the kitchen (entry point).
- `scripts/pcve_dfsph_patches.py`: Genesis DFSPH patches (single gravity, XSPH smoothing, Akinci surface tension).
- `physics/coupling_tilted_cup_table_pour.py`: DFSPH with static ghost-particle boundaries (split density solve, implicit viscosity).
- `physics/film_tilted_cup_table_pour.py`: tabletop water film as a height field.
- `physics/contact_geometry.py`: analytic cup, block and table placement.
- `appearance/appearance_kitchen.py`, `appearance/ceramic_wood_details.py`, `appearance/look_tilted_cup_table_pour.py`: kitchen, ceramic and wood details, sunlit look.
- `edit_vocab.py`: edit DSL vocabulary and simulator flag mapping.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases and video hashes of the published suite.

## Limitations

- The table film is a reconstruction from particle volume, not a resolved thin-film simulation.
- The cup and block are fixed; the water does not move them.
