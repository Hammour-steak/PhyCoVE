# toy_car_float_bathtub

A 2 kg silver toy sports car drops onto a 0.15 kg purple inflatable float on 31 cm of water in a
freestanding bathtub, pushes it under, and rides it as it bobs back up and rocks. This is a
rigid–fluid scene with two-way coupling: the float and the car are rigid bodies coupled to the
water. The source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Bathtub: the simulated interior is the rendered ceramic shell (`geometry/tub_shell.npz`, rings
  of the fitted shell of `appearance/bathroom_finish.py`): floor at z = 0.1125 m, rim at
  z = 0.60 m, outline 0.86 × 1.83 m, sloped walls.
- Water: 998 kg/m³, kinematic viscosity 1e-6 m²/s, surface tension 0.072 N/m, still surface
  0.42 m above the room floor.
- Float: made by `tools/make_float.py`: 46 × 28 cm, six welded tubes, 5.06 L, 0.15 kg (Archimedes
  draft 3.8 mm alone). Its centre is (0.06, −0.22) m from the tub's centre, off the drain.
- Car: 23 × 9.8 × 5.1 cm, 2.0 kg, CoACD collider, released at z = 1.0522 m (its underside 0.55 m
  above the float), (−0.02, 0.035) m from the float's centre, with 0.35 rad/s of roll.
- Lighting: a virtual window at y ≈ −1 m lights the room with a soft area light (90 W) and a sun
  beam (150 W, 16° spread); AgX Medium High Contrast, exposure −2.3. Light that bounces off the
  ceramic passes the water surface (refractive caustic paths on), so the water reads as bright as
  the wall around it.
- Rendering: Cycles, 128 samples, denoising, 180° motion blur.

## Physics

- Solver: Genesis 1.4.3 SPH with the DFSPH pressure solver, 6 mm particles (1.38 M), Akinci
  surface tension γ = 0.02 (0.072 N/m scaled to 6 mm).
- Time step: 96 frames at 24 fps, 10 steps per frame of 8 substeps each (the car lands at
  3.3 m/s; 0.4 particle sizes per substep at 4.6 m/s); particle speeds are capped at 7 m/s.
- Coupling: the bathtub, the float and the car are ghost-particle shells that carry their own
  pressure (`physics/coupling_toy_car_float_bathtub.py`), with a split density solve (ghost
  pressure and a warm-started momentum part). The 0.15 kg float holds about 11 kg of added mass,
  so the pressure iterations also relax the float's and car's velocities (strong coupling); the
  rigid solver holds the float at 1 kg in contacts, while its weight stays 0.15 kg.
- Tub contact: a ring of 72 tilted boxes on the ceramic's slope and a floor box keep the rigid
  bodies 12 mm (two particle sizes) off the ceramic; the render puts a body that rests there back
  on the ceramic. Water squeezed under a body that comes within 1.5 particle sizes of the ceramic,
  and water that leaves over the rim, is removed.
- Gravity: Genesis 1.4.3's DFSPH applies gravity twice per substep;
  `scripts/pcve_dfsph_patches.py` removes the second call.
- Start: the water and float start from an accepted settled state (`settled/` in the scene's
  assets); without it the builder settles them itself (`simulate_toy_car_float_bathtub.py relax`,
  30 frames). A newly settled state is not bit-identical to the accepted one, so the videos then
  differ in detail.
- Timed edit: continues from the source run's state at frame 49 (`--checkpoint-frames 49` on the
  source, `--resume-from` and `--resume-frame` on the edit); a density edit sets
  `--density-after` and `--density-time`. The builder copies the source's rendered frames 1–48
  into the edit; the published edit video renders all 96 frames from the continued run.
- Water surface for rendering (`surface_toy_car_float_bathtub.py`): the bulk is a height field of
  the top particle layer (Gaussian over 2.4 particle sizes in still water, 1.3 in fast water,
  averaged over three frames) with a meniscus on the ceramic and the float; clusters above it are
  joined in one implicit field and meshed by marching cubes, and lone fast particles become
  droplets. It also writes per frame the light pattern the sun beam makes through the height
  field on the tub floor (`caustic_####.npy`, rendered as added light on the ceramic), where the
  water has been (`wet_####.npy`: glossier, slightly darker ceramic with flat bead highlights),
  and beads on the float and car where particles touched them.
- Droplets and beads use the water's surface without its volume absorption: with absorption the
  six overlapping spheres of each torn-off particle confuse Cycles' inside/outside tracking and
  the splash turns teal. The car's beads are drawn as wet paint (slightly darker, full clear coat,
  sparse beads of a pixel or two in the coat normal) where `car_wet_local` marks the car wet,
  because glass-sphere beads at about 1.3 mm per pixel shimmer from frame to frame. Water resting
  on the car (within 1.2 particle spacings and moving with it) does not become droplets. Surfaces
  without `car_wet_local` are rendered with sphere beads and no wet paint.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | the car lands at 3.3 m/s about 0.35 s in and pushes the float 6 cm down; the float bobs (period about 0.65 s), rocks and still carries the car at 4 s |
| `edit_no_float` | `DELETE float` | no float; the car hits the water at 3.3 m/s, splashes more than 1 m high and reaches the tub floor 0.25 s later, upright |
| `edit_heavy_car` | `SET toy_car.mass TIMES 4` | car 8 kg; the float is pushed 20 cm under, the car slides off and lands upright on the floor by 0.9 s, the float shoots up, tumbles and floats again |
| `edit_low_density` | `SET water.density TIMES 0.1` | water 99.8 kg/m³; the float has sunk 2 cm deeper when the car lands, it is driven 25 cm down with a much bigger splash, the car stays on the floor and the float rises back |
| `edit_density_at_2s` | `SET water.density TIMES 0.1 AT FRAME 49` | frames 1–48 as the source; from 2.0 s the water is 99.8 kg/m³, float and car sink 22 cm within 0.6 s, the car tips off and rests upside down on the floor, the float rises back |
| `edit_no_car` | `DELETE toy_car` | no car; the float rides quietly at the surface and the water stays calm |

The builder names the source `toy_car_float_bathtub_baseline`; the published suite stores it as
`source`. `edit_vocab.py` maps the DSL onto simulator flags.

## Assets

- `scenes/toy_car_float_bathtub` (manual and derived): the toy car model and the bathroom model
  are manual Sketchfab downloads (CC BY 4.0, attribution recorded in `assets.json`); the car's
  CoACD collider and placement record, the procedural float (`tools/make_float.py` remakes it)
  and the accepted settled states are derived files made by this project with no public download.

```bash
python3 scripts/download_assets.py --scene toy_car_float_bathtub          # check sha256 and list what is missing
python3 scripts/download_assets.py --scene toy_car_float_bathtub --check  # check only
```

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with Genesis 1.4.3
  (`genesis-world==1.4.3`), numba, scikit-image, scipy and trimesh.
- An NVIDIA GPU for Genesis and for Cycles. A case takes 20–75 min to simulate and about 13 s per
  frame to render on an RTX 4090.
- Blender 4.3.2 (`--blender`, or `$BLENDER`, else `blender` on `PATH`).
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root with an idle GPU.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/toy_car_float_bathtub/build_pcve_toy_car_float_bathtub.py \
  --out-root renders/toy_car_float_bathtub --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/toy_car_float_bathtub/build_pcve_toy_car_float_bathtub.py \
  --suite-root renders/toy_car_float_bathtub
.venv-genesis-mpm-sph/bin/python scripts/rigid_fluid/toy_car_float_bathtub/tools/make_float.py \
  --out renders/toy_car_float_bathtub/procedural_float
```

- For each case the builder simulates, builds the water surface, renders and encodes; all six
  cases run by default (`--cases` selects some, by the builder names). The source must be built
  before the timed edit.
- Completed simulation and surface stages in `renders/toy_car_float_bathtub/runs/<case>/` are
  reused. An interrupted simulation restarts that case from its settled state or source
  checkpoint; rendering only renders missing frames. To redo a look change, delete
  `runs/<case>/frames` and `video.mp4` (and `surfaces/` if the surface step changed).

## Outputs

- `renders/toy_car_float_bathtub/cases/<case>/video.mp4`: the rendered video.
- `renders/toy_car_float_bathtub/cases/<case>/prompts.json`: bilingual prompts (a description for
  the source, the instruction for an edit).
- `renders/toy_car_float_bathtub/runs/<case>/`: water particle positions and velocities and body
  poses per frame (`particles/`), `sim_log.json`, `surfaces/`, `frames/` and logs.
- `renders/toy_car_float_bathtub/suite_manifest.json`: physics, numerical settings, run summary
  and video hash of every case.
- The published suite is `renders/pcve_suites/pcve_toy_car_float_bathtub_suite/`; the builder
  does not write there.

## Code layout

- `build_pcve_toy_car_float_bathtub.py`: full suite: simulate, surface, render, manifest (entry point).
- `simulate_toy_car_float_bathtub.py`: Genesis DFSPH simulation, `relax` settles water and float, `run` drops the car (entry point).
- `surface_toy_car_float_bathtub.py`: per-frame water mesh, droplets, light pattern and wet map.
- `render_toy_car_float_bathtub.py`: Blender rendering of the bathroom (entry point).
- `scripts/pcve_dfsph_patches.py`: Genesis DFSPH patches (single gravity).
- `physics/coupling_toy_car_float_bathtub.py`: ghost-shell coupling with split density solve and strong rigid coupling.
- `appearance/bathroom_appearance.py`, `appearance/bathroom_details.py`: bathroom materials and details.
- `appearance/bathroom_finish.py`: the fitted ceramic shell.
- `appearance/car_paint_appearance.py`: car paint and wet paint.
- `geometry/tub_shell.npz`: rings of the bathtub's interior shell, read by the simulator.
- `tools/make_float.py`, `tools/export_tub_shell.py`: make the float asset and the tub shell.
- `edit_vocab.py`: edit DSL vocabulary and simulator flag mapping.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: supported cases, configuration and the published suite with its video hashes.

## Limitations

- The float is rigid: it does not dent or flex under the car.
- The water surface is a reconstruction from the particles, not a simulated free surface; spray
  thinner than a particle is not resolved.
