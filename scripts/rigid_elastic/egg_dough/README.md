# egg_dough

A whole brown egg is dropped off-centre from about 13 cm onto a piece of freshly kneaded dough on a
kitchen counter; it sinks in, tips over and settles in the dent. This is a rigid–elastic scene: the
dough is a finite-strain viscoelastic FEM body solved with Taichi and the egg is a rigid body with its
real shape and full inertia, coupled both ways. The source video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Units and axes: SI (m, kg, s, Pa), Z up, gravity −9.81 m/s².
- Egg: a scanned egg mesh scaled uniformly to 60 × 44.49 × 44.49 mm, 0.065 kg, centre at
  (0.002, 0.001, 0.1855) m, at rest, rotated 32° about the axis (0.48, 0.83, 0.28). A rigid whole egg:
  no shell cracking or contents. The rendered egg is the same mesh as the contact geometry.
- Dough: 3591 nodes, 16704 tetrahedra (mesh spacing 4.8 mm, 7 vertical layers, a domed pad), resting on
  a flat pastry board at z = 0. The source starts from the dough's fully relaxed gravity equilibrium.
- Room: a closed kitchen (walls, ceiling, wall cabinets) with a 1.05 × 1.18 m window in the left wall,
  1.2 m from the dough. The only light is an overcast sky HDRI (`residential_garden`, strength 8) seen
  through that opening; a Cycles portal on the opening only guides sampling. None of the room is in
  frame; it shows in reflections and in the soft side light from the left.
- Worktop: honed light grey engineered quartz with sparse 1–2 mm aggregate flecks; roughness 0.24–0.46
  driven by the scanned `SurfaceImperfections018` wear map (0.40 m span).
- Backsplash: per-tile glaze tint, up to about 0.6° set-in tilt per tile and glaze ripple; grout fills
  the 2 mm joints to 1.5 mm behind the tile face; tiles past the side walls are removed.
- Pastry board: edge-glued maple, 38–58 mm staves along the long axis, each stave a different part of
  the scanned `white_maple_veneer` map (1 m span) with a slight tone change and a fine glue line. Flour
  around the dough and toward the bowl uses the scanned `macro_flour` map (0.30 m span) for colour,
  grain and relief (shading only; the support stays flat).
- Flour bowl: a loose, scooped flour surface just below the rim, shaded with `macro_flour`.
- Towel: a folded two-layer linen tea towel (soft creases, rounded edges down to the worktop) shaded
  with the scanned `rough_linen` weave. Walls and ceiling use the scanned `beige_wall_001` plaster.
- Dough look: creamy colour (linear 0.70/0.565/0.36), subsurface weight 0.3 with a 3 mm radius,
  roughness 0.36–0.50, about 1 cm hand-shaped unevenness, gathered tucks around the base, small pits and
  patches of flour dust. Every field is evaluated in the FEM rest coordinates (`rest_position_m`), so the
  detail stretches with the deformation and never swims; the rendered boundary is the exact FEM
  boundary (no displacement, no subdivision).
- Egg look: the source UV maps keep their specks, roughness and normal; the colour is re-graded to a tan
  brown with object-space mottling, pigment specks, pores and a slight sheen (`egg_shell_treatment`).
- Camera and render: 38 mm lens, f/8 focused at the target (0.75 m); Cycles 256 samples (adaptive,
  threshold 0.01), OpenImageDenoise, fixed seed, indirect clamp 10, AgX Medium High Contrast, exposure
  +1.5; H.264 CRF 17, yuv420p. The egg is keyframed on every cached frame so Cycles motion blur (shutter
  0.25 frame, centred) blurs the fall; the dough mesh is set per whole frame without motion blur.
  Persistent data is off whenever motion blur is on.

## Physics

- Solver: Taichi in float64 (CUDA, or the CPU with `--gpu cpu`), symplectic Euler, 4096 substeps per
  video frame in the builder (dt = 1/98304 s; the simulate entry defaults to 2048).
- Dough: finite-strain Hencky standard linear solid (isochoric Maxwell branch, parallel equilibrium
  shear spring, elastic bulk), E = 6000 Pa, ν = 0.49, 1100 kg/m³, relaxation time 0.006 s, equilibrium
  shear fraction 0.15, shear viscosity 12 Pa·s.
- Egg: rigid body; centre of mass and the full inertia tensor are integrated from the closed mesh, and
  the solver integrates world angular momentum with the rotating inertia.
- Contact: the egg shape (1986 vertices, 3968 triangles) as a 129³ signed-distance grid (largest
  interpolation error over 20,000 surface samples 0.0189 mm); curved normals, off-centre forces and
  friction produce real torques. Penalty contact with 3 Gauss points per boundary triangle: egg–dough
  friction 0.40 (5×10⁸ Pa/m), dough–table friction 0.45 (2×10⁹ Pa/m), egg–table friction 0.30; no
  adhesion.
- Edits: every edit starts from the source's exact settled state at t = 0 (vertices, velocities, Maxwell
  state) and changes one property from frame 1, so the softened dough also sags before the egg arrives.

## Measured motion

Local deformation is measured from the common t = 0 state.

| Case | First contact | Local deformation | Total egg rotation |
|---|---|---|---|
| `source` | 0.1606 s | 15.84 mm | 80.0° |
| `edit_soft_dough_e5` | 0.1628 s | 21.68 mm | 75.5° |
| `edit_light_egg` | 0.1606 s | 11.18 mm | 93.5° |
| `edit_heavy_egg` | 0.1606 s | 21.55 mm | 85.6° |
| `edit_delete_egg` | — | 0.00 mm | — |

In every case with an egg, the egg ends on the dough.

## Validation

- `physics/validate_egg_dough.py --suite-root <out-root>` checks conservation, positive volume (smallest
  tetrahedron J: 0.82 source, 0.59 soft dough), contact on the real egg geometry (largest penetration at
  a contact point 0.24 / 0.26 mm), the shared initial state, support, camera and prop clearances, and that
  each edit differs from the source only in its declared field.
- With 8192 instead of 4096 substeps the first 0.5 s of the soft-dough case changes by at most 0.004 mm
  (egg centre) and 0.005 mm (dough vertices).
- Over all 96 frames the mean frame-to-frame image change outside the dough and egg is 0.016/255 (source)
  and 0.017/255 (soft dough); the only larger change is the falling egg's soft window shadow crossing the
  board (frames 3–4, at most 20/255).

## Cases

The builder's native case ids are `source`, `soft_dough_e5`, `light_ball`, `heavy_ball` and `delete_egg`;
they map in this order to the published cases below.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | dough E = 6000 Pa, egg 0.065 kg |
| `edit_soft_dough_e5` | `SET dough.young_modulus TIMES 0.2` | dough E = 1200 Pa from frame 1 |
| `edit_light_egg` | `SET egg.mass TIMES 0.5` | egg 0.0325 kg from frame 1 |
| `edit_heavy_egg` | `SET egg.mass TIMES 2` | egg 0.13 kg from frame 1 |
| `edit_delete_egg` | `DELETE egg` | no egg |

## Assets

| assets.json key | Type | Use |
|---|---|---|
| `scenes/egg_dough` | mixed (13 url, 2 manual, 16 derived) | dough and egg geometry, template scenes, kitchen textures, accepted states |
| `polyhaven/macro_flour` | url | flour on the board, in the bowl and on the dough |
| `polyhaven/beige_wall_001` | url | wall and ceiling plaster |
| `polyhaven/rough_linen` | mixed (10 url, 1 manual, 4 derived) | tea towel weave |
| `polyhaven/residential_garden` | url | window sky HDRI |
| `ambientcg/SurfaceImperfections018` | url | worktop wear map |

```bash
python3 scripts/download_assets.py --scene egg_dough          # download and check sha256
python3 scripts/download_assets.py --scene egg_dough --check  # check only
```

Files are stored under `assets/` (`PCVE_ASSETS_DIR` moves the root); scene-only files are in
`assets/scenes/egg_dough/`. Manual files need a free provider account; `download_assets.py` prints each
asset page and the file names to save. The 16 derived files (template scenes, generated geometry,
accepted simulation states, prepared images) have no public download, so `--check` reports them missing.
The dough geometry `geometry.npz` can be rebuilt byte-identically with `tools/prepare_assets.py` (its
asset manifest differs only in the recorded command); the script refuses to overwrite an existing
directory, and the builder reads the result through `--asset-dir`. `tools/download_rigid_egg.py` and
`tools/prepare_rigid_egg.py` (inside Blender) rebuild the normalized egg from its source model; the saved
`.blend` can differ byte-wise between sessions, so each build records its actual hash.
`tools/prepare_visual_assets.py` and `tools/prepare_realism_assets.py` download and check the pinned wood
maps.

## Requirements

- Linux; an NVIDIA GPU for the default Taichi CUDA backend and Cycles GPU rendering (`--gpu cpu` runs
  both on the CPU). On one RTX 4090 a frame renders in about 7–9 s.
- Python environment `.venv-taichi-mpm/` at the repository root with `requirements.txt` (taichi 1.7.3,
  numpy 2.0.2, scipy 1.15.3, Pillow 11.3.0).
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then `~/.local/opt/blender-*/blender`;
  `--blender` overrides it.
- `ffmpeg` and `ffprobe`.

## Commands

Run from the repository root. Use a new output root for every run. `--gpu auto` picks an idle GPU;
`--gpu cpu` uses the CPU.

```bash
# plan only, then simulate and render all five cases (the source first)
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/build_pcve_egg_dough.py --out-root renders/egg_dough/<new folder> --dry-run
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/build_pcve_egg_dough.py --out-root renders/egg_dough/<new folder> --gpu auto --threads 6

# one step or a subset of cases
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/build_pcve_egg_dough.py --out-root renders/egg_dough/<new folder> \
    --stage simulate --cases source soft_dough_e5

# one case with the simulate entry (edits start from the source's initial state)
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/simulate_egg_dough.py --case source \
    --out-dir renders/egg_dough/<new folder>/source --steps-per-frame 4096
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/simulate_egg_dough.py --case heavy_ball \
    --out-dir renders/egg_dough/<new folder>/heavy_ball --steps-per-frame 4096 \
    --initial-state-from renders/egg_dough/<new folder>/source/initial_state.npz

# re-render a finished simulation
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/render_egg_dough.py \
    --simulation-dir <out-root>/cases/<case>/simulation --out-dir renders/egg_dough/<new folder> --save-blend

# checks
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/physics/validate_egg_dough.py --suite-root <out-root>
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/build_pcve_egg_dough.py --out-root <out-root> --stage verify

# rebuild the dough geometry
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/tools/prepare_assets.py --out-dir <new dir> \
    --profile domed_pad --xy-scale 1 --spacing 0.0048 --layers 7

# write a case's prompts file
.venv-taichi-mpm/bin/python scripts/rigid_elastic/egg_dough/edit_vocab.py --case-dir <case dir> \
    --source-config <out-root>/cases/source/simulation/actual_config.json
```

- Without `--cases` the builder runs all five cases, the source first; the edits start from
  `cases/source/simulation/initial_state.npz` (or `--source-initial-state`).
  `--initial-state-mode own_equilibrium` lets each case settle on its own instead.
- `render_egg_dough.py` uses `appearance/appearance.json`; `--appearance-file` selects another file.
  Set `PCVE_CYCLES_GPU_BACKEND=CUDA` on machines where OptiX fails.

## Outputs

New runs write to the chosen output root under `renders/egg_dough/`; each case goes to
`<out-root>/cases/<case>/`. The published suite is `renders/pcve_suites/pcve_egg_dough_suite/`
(`cases/<published case>/`); no command writes into it by default.

| Path in a case folder | Content |
|---|---|
| `render/video.mp4`, `render/frames/` | rendered video and frames |
| `render/scene.blend` | playable scene with the solved animation and packed textures |
| `simulation/simulation_cache.npz` | 97 solved states (t = 0 to 4 s; the video uses the first 96) |
| `simulation/initial_state.npz` | starting state |
| simulation/actual_config.json, acceptance and receipts | exact inputs, metrics and checks |

simulation/actual_config.json stores the current `appearance/appearance.json` under `appearance`; its
key names differ from those in the published cases' configurations, so a new run's `appearance` entry
differs from the published one while physics, simulation quality, render settings and the preset are the
same. An edit started from a source state copies that source's `appearance` entry.

## Code layout

- `simulate_egg_dough.py`: FEM and rigid-egg simulation entry
- `render_egg_dough.py`: Blender rendering entry
- `build_pcve_egg_dough.py`: simulate, render and verify stages for the five cases
- `dough_config.py`: configuration (`SPEC`) and the five native cases
- `presets.json`: the named preset `kitchen_egg`, checked when an edit reuses the source state
- `edit_vocab.py`: edit DSL vocabulary and prompt writer
- `physics/fem_viscoelastic.py`: viscoelastic FEM solver and egg coupling
- `physics/rigid_geometry.py`: egg geometry and signed-distance contact
- `physics/equilibrate_dough.py`: dough gravity equilibrium
- `physics/source_initial_state.py`: reuse of the source state by the edits
- `physics/validate_egg_dough.py`: physical checks of a finished suite
- `appearance/scene_egg_dough.py`: scene build and render
- `appearance/baking_look.py`, `appearance/realism_look.py`, `appearance/realism_look_assets.py`, `appearance/material_helpers.py`: kitchen, bench, room, daylight and shaders, and the scanned maps they read
- `appearance/appearance.json`: look configuration
- `tools/`: asset and egg preparation, wood map download
- `requirements.txt`: Python packages of `.venv-taichi-mpm`
- `entrypoints.json`, `scene_manifest.json`: entry-point options, runtimes, cases and the published suite

Internal cache keys name the egg `ball` (shared format); prompts and ground-truth ids use `egg`.

## Limitations

- The egg is one rigid body; shell cracking and the liquid inside are not modelled.
- The dough model is phenomenological and not calibrated against real dough.
- In the soft-dough case part of the deformation is the dough sagging under its own weight after the
  softening, not only the impact.
