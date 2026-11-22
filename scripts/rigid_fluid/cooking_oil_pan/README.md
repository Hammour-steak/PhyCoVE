# cooking_oil_pan

A tilted bottle pours cooking oil over the lower rim of its mouth into a dark nonstick frying pan
on an induction hob, in a modern kitchen in daylight. The oil spreads into a puddle on the pan
floor. This is a rigid–fluid scene: the oil is simulated against the static pan. The source video
is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Frame: origin at the pan centre on its flat floor (world (1.1, 3.405, 1.18233) m). The floor
  is flat to r = 9 cm and rises into the wall; the rim is at r = 15 cm, 6 cm up
  (`geometry/pan_profile.npz`).
- Oil: 915 kg/m³, kinematic viscosity 1.4e-4 m²/s (olive oil at about 12 °C), surface tension
  0.032 N/m.
- Pour: 10 mL/s from frame 8, leaving the bottle mouth at (−0.0406, −0.00347, 0.2446) m in
  direction (0.035, 0.005, −0.15).
- Lighting: daylight from the open side of the room (sky, sun at azimuth 250° and elevation 28°,
  a weak under-cabinet strip).
- Rendering: Cycles, 64 samples, denoising, 180° motion blur from the oil's per-vertex velocity,
  in the kitchen template `assets/scenes/cooking_oil_pan/scene_template.blend`.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 0.5 mm particles.
- Time step: 96 frames at 24 fps, 10 steps per frame of 48 substeps each (the stream lands at
  about 2.3 m/s).
- Pan: a static ghost-particle boundary that carries its own pressure.
- Viscosity is solved implicitly, with a Navier-slip term for the wall shear of the first layer.
  Akinci surface tension is scaled to 0.032 N/m, set from the oscillation period of a 6 mm
  zero-gravity drop.
- Inflow: all oil particles are preallocated and activated layer by layer at the exit, so the
  volume flow is exactly the scheduled flow; oil in the last 1.5 mm before the exit moves at the
  inlet velocity, as in the bottle's neck. A flow change during the clip ramps linearly over
  0.2 s. Up to 30 mL/s a flow edit keeps the 4.6 mm stream and changes its speed; beyond that the
  bottle pours a thicker sheet over the lip (weir flow: speed ∝ Q^(1/3), cross-section ∝ Q^(2/3)).
- Gravity: Genesis 1.4.3's DFSPH applies gravity twice per substep;
  `scripts/pcve_dfsph_patches.py` removes the second call.
- Timed edits continue from the source run's state (`--resume-from`, `--resume-frame`).
- Oil surface for rendering: the oil is only a few particles thick, so `surface_cooking_oil_pan.py`
  rebuilds its surface from the particles' volume. The puddle is a volume-conserving height field
  over the pan (smoothed over 1.2 mm, pressed 0.15 mm into the pan), and the stream is a thread
  whose cross-section is the particle volume per unit height, averaged over 6 ms of fall. Both are
  one implicit field meshed by marching cubes, so the surface is closed where the stream enters
  the puddle. From 1e-3 m²/s on the oil lands in a coiling rope and `--rope` meshes it directly
  with pysplashsurf.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | 10 mL/s from frame 8, 1.4e-4 m²/s; 36.5 mL by 4 s, a smooth puddle about 11 cm across and 4 mm deep |
| `edit_increase_flow` | `SET bottle.flow_rate TIMES 4` | 40 mL/s, a 7.3 mm stream at 0.96 m/s; 146 mL, puddle about 19 cm across |
| `edit_decrease_flow` | `SET bottle.flow_rate TIMES 0.2` | 2 mL/s, a 4.6 mm stream at 0.13 m/s; 7.3 mL, puddle about 5.5 cm across |
| `edit_increase_at_2s` | `SET bottle.flow_rate TIMES 2.8 AT FRAME 49` | frames 1–48 as the source; 10 → 28 mL/s over 0.2 s from 2.0 s, the stream thickens and lands further out, 70 mL |
| `edit_decrease_at_1s` | `SET bottle.flow_rate TIMES 0.2 AT FRAME 25` | frames 1–24 as the source; 10 → 2 mL/s over 0.2 s from 1.0 s, the stream thins to a thread, 13.8 mL |
| `edit_increase_viscosity` | `SET oil.kinematic_viscosity TIMES 100` | 1.4e-2 m²/s, like honey; the stream coils where it lands into a mound about 6.5 cm across and 3–4 cm tall |

The builder names the source `cooking_oil_pan_baseline`; the published suite stores it as
`source`. `edit_vocab.py` maps the DSL onto simulator flags.

## Assets

- `scenes/cooking_oil_pan` (derived): the kitchen template `.blend` with the hob, pan, bottle,
  lighting and camera. It is made by this project and has no public download.

```bash
python3 scripts/download_assets.py --scene cooking_oil_pan          # download and check sha256
python3 scripts/download_assets.py --scene cooking_oil_pan --check  # check only
```

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`) and pysplashsurf.
- An NVIDIA GPU for Genesis and for Cycles.
- Blender 4.3.2 (`--blender`, or `$BLENDER`, else `blender` on `PATH`).
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root with an idle GPU.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/cooking_oil_pan/build_pcve_cooking_oil_pan.py \
  --out-root renders/cooking_oil_pan --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/cooking_oil_pan/build_pcve_cooking_oil_pan.py \
  --suite-root renders/cooking_oil_pan
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/cooking_oil_pan/build_pcve_cooking_oil_pan.py \
  --suite-root renders/cooking_oil_pan --cases cooking_oil_pan_baseline edit_increase_flow
```

- For each case the builder simulates, builds the oil surface, renders and encodes; all six cases
  run by default (`--cases` selects some, by the builder names).
- Every step resumes from what exists in `renders/cooking_oil_pan/runs/<case>/`, and rendering
  only renders missing frames. To redo a look change, delete `frames/` and `video.mp4` in that
  directory (and `meshes/` and `runs/<case>/surface_log.json` if the surface step changed).

## Outputs

- `renders/cooking_oil_pan/cases/<case>/video.mp4`: the rendered video.
- `renders/cooking_oil_pan/cases/<case>/prompts.json`: bilingual prompts (a description for the
  source, the instruction for an edit).
- `renders/cooking_oil_pan/runs/<case>/`: particle positions (float32) and velocities (float16),
  active count per frame, `sim_log.json`, `meshes/` and frames.
- `renders/cooking_oil_pan/suite_manifest.json`: physics, numerical settings, run summary and
  video hash of every case.
- The published suite is `renders/pcve_suites/pcve_cooking_oil_pan_suite/`; the builder does not
  write there.

## Code layout

- `build_pcve_cooking_oil_pan.py`: full suite: simulate, surface, render, manifest (entry point).
- `simulate_cooking_oil_pan.py`: Genesis DFSPH simulation (entry point).
- `surface_cooking_oil_pan.py`: per-frame oil mesh.
- `render_cooking_oil_pan.py`: Blender rendering of the kitchen template (entry point).
- `scripts/pcve_dfsph_patches.py`: Genesis DFSPH patches (single gravity, XSPH smoothing, Akinci surface tension).
- `physics/coupling_cooking_oil_pan.py`: DFSPH with the static ghost-particle pan boundary (split density solve, implicit viscosity).
- `appearance/look_cooking_oil_pan.py`: lighting and material finishes.
- `geometry/pan_profile.npz`: pan interior profile, read by the simulator.
- `edit_vocab.py`: edit DSL vocabulary and simulator flag mapping.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases and video hashes of the published suite.

## Limitations

- The pan is a static boundary; it does not move or heat.
- The oil surface is a reconstruction from particle volume, not a simulated free surface.
