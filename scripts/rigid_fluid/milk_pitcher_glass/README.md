# milk_pitcher_glass

An opaque 1 L milk carton, tipped to 135° above a clear handled glass on a sunlit oak kitchen
counter, pours whole milk from its open screw spout; the milk plunges, splashes and collects in
the glass. This is a rigid–fluid scene: the milk flows against the static glass and counter. The
source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Frame: counter top at z = 0.
- Glass: 126 mm wide, 103 mm tall, 4 mm walls (`geometry/glass_cup.npz`). Its base is only
  0.1 mm thick.
- Milk: 1030 kg/m³, kinematic viscosity 2.2e-6 m²/s, surface tension 0.046 N/m; glass and
  counter are wetted.
- Pour: from 0.25 s, at the spout exit (−0.0345, 0.005, 0.160) m, axis 45° below horizontal
  toward +x, at 0.37 m/s (75 mL/s).
- Rendering: Cycles, 64 samples, denoising, 180° motion blur from the milk's per-vertex
  velocity, daylight kitchen from the template `assets/scenes/milk_pitcher_glass/milk_carton_kitchen.blend`.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 1 mm particles (280k in the source).
- Time step: 96 frames at 24 fps, 10 steps per frame of 32 substeps each (the stream lands at
  1.8 m/s and spray reaches 2–4 m/s).
- Boundaries: the glass and the counter are static ghost-particle boundaries that carry their own
  pressure. The milk rests on the counter's ghosts, and a ring of ghosts seals the glass foot to
  the counter.
- Density solve: split (new compression through the velocities, existing compression through
  the positions), so a stream hitting a wall is not shot back off.
- Surface tension: Akinci model scaled to 0.046 N/m.
- Emitter: every 1/400 s a disc of 233 particles (8 mm radius, normal to the spout axis) is
  activated at the spout exit. All particles are preallocated, so the volume flow is exact.
- Gravity: Genesis 1.4.3's DFSPH applies gravity twice per substep;
  `scripts/pcve_dfsph_patches.py` removes the second call.
- Timed edit: continues the source run from its frame-48 state (`--resume-from`,
  `--resume-frame`).
- Milk surface for rendering: at 1 mm the free surface of the milk standing in the glass is a
  rough layer of single particles, so the milk in the glass is drawn from a volume-conserving
  height field over the glass floor (smoothed over 3 mm, closed against the glass); the stream,
  its plunge and the splash are a pysplashsurf surface of the remaining particles. Small clusters
  (6–60 particles) are drawn as drops of equal volume; drops of fewer than 40 particles stuck on
  the glass are not drawn.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | 0.37 m/s (75 mL/s) from 0.25 s; 277 mL poured by 4 s, 271 mL in the glass |
| `edit_high_flow_speed` | `SET milk.flow_speed TIMES 2` | 0.74 m/s (150 mL/s); longer arc, 553 mL poured, milk 6 cm deep |
| `edit_low_flow_speed` | `SET milk.flow_speed TIMES 0.5` | 0.19 m/s (37.5 mL/s); thinner, steeper stream, 138 mL |
| `edit_delete_milk` | `DELETE milk` | no milk; the tipped carton pours nothing and the glass stays empty |
| `edit_stop_after_2s` | `SET milk.flow_speed TO 0.0 AT FRAME 49` | frames 1–48 as the source; the pour stops at 2.0 s and the milk settles at 131 mL |

The builder names the source `milk_pitcher_glass_baseline`; the published suite stores it as
`source`. `edit_vocab.py` maps the DSL onto simulator flags.

## Assets

- `scenes/milk_pitcher_glass` (derived): the kitchen template `.blend` with the counter, carton,
  glass, lighting and camera. It is made by this project and has no public download.

```bash
python3 scripts/download_assets.py --scene milk_pitcher_glass          # download and check sha256
python3 scripts/download_assets.py --scene milk_pitcher_glass --check  # check only
```

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`) and pysplashsurf.
- An NVIDIA GPU for Genesis and for Cycles. The source takes about 47 s of simulation per frame
  with three cases sharing one RTX 3090.
- Blender 4.3.2 (`--blender`, or `$BLENDER`, else `blender` on `PATH`). Cycles renders with OptiX
  by default; where OptiX crashes Blender (seen with NVIDIA driver 550), pass `--device CUDA`.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root with an idle GPU.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/milk_pitcher_glass/build_pcve_milk_pitcher_glass.py \
  --out-root renders/milk_pitcher_glass --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/milk_pitcher_glass/build_pcve_milk_pitcher_glass.py \
  --suite-root renders/milk_pitcher_glass
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/milk_pitcher_glass/build_pcve_milk_pitcher_glass.py \
  --suite-root renders/milk_pitcher_glass --device CUDA
```

- For each case the builder simulates, builds the milk surface, renders the kitchen template and
  encodes; all five cases run by default (`--cases` selects some, by the builder names).
- `--device` is handed to `render_milk_pitcher_glass.py`, which takes the same option.
- Every step resumes from what exists in `renders/milk_pitcher_glass/runs/<case>/`, and rendering
  only renders missing frames. To redo a look change, delete `frames/` and `video.mp4` there (and
  `meshes/` and `runs/<case>/surface_log.json` if the surface step changed).

## Outputs

- `renders/milk_pitcher_glass/cases/<case>/video.mp4`: the rendered video.
- `renders/milk_pitcher_glass/cases/<case>/prompts.json`: bilingual prompts (a description for
  the source, the instruction for an edit).
- `renders/milk_pitcher_glass/runs/<case>/`: particle positions (float32) and velocities
  (float16), active count per frame, `sim_log.json`, `meshes/` and frames.
- `renders/milk_pitcher_glass/suite_manifest.json`: physics, numerical settings, run summary and
  video hash of every case.
- The published suite is `renders/pcve_suites/pcve_milk_pitcher_glass_suite/`; the builder does
  not write there.

## Code layout

- `build_pcve_milk_pitcher_glass.py`: full suite: simulate, surface, render, manifest (entry point).
- `simulate_milk_pitcher_glass.py`: Genesis DFSPH simulation (entry point).
- `surface_milk_pitcher_glass.py`: per-frame milk mesh.
- `render_milk_pitcher_glass.py`: Blender rendering of the kitchen template (entry point).
- `scripts/pcve_dfsph_patches.py`: Genesis DFSPH patches (single gravity, XSPH smoothing, Akinci surface tension).
- `physics/coupling_milk_pitcher_glass.py`: DFSPH with static ghost-particle boundaries (split density solve).
- `geometry/glass_cup.npz`: closed glass mesh, read by the simulator.
- `edit_vocab.py`: edit DSL vocabulary and simulator flag mapping.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: supported cases, configuration and the published suite with its video hashes.

## Limitations

- The first impact on the dry glass floor shatters about a third of the first 20 mL into spray,
  far more than a real pour (a 1 mm sheet cannot hold together).
- The carton is a static model; only the milk is simulated.
