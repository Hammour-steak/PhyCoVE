# metal_pendulum_horizontal_spring

A steel ball on a rigid pendulum arm is released from −30° and hits the pressure plate of a horizontal,
guided coil spring; the spring compresses, pushes the ball back and recovers before the next swing. This
is a rigid–elastic scene: the pendulum hinge, the plate's slide joint and the contact are solved together
in MuJoCo, so the contact acts on both the swing and the compression, and Blender renders the solved
states in a furnished room. The source video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Units and axes: SI, Z up.
- Pendulum: a steel ball 36 mm in diameter (7800 kg/m³, 0.19055 kg) and its rod form one rigid body on a
  hinge at (0, 0, 0.32) m, axis (0, −1, 0); ball centre 230 mm from the pivot; released at rest from −30°.
- Spring: mean coil diameter 22 mm, wire 0.9 mm, 8 active coils and 2 closed end coils, free length
  97.5 mm, 65 mm guided travel, on a fixed backing plate and spring seat. The coil mesh follows the solved
  compression with a fixed coil diameter and changing pitch.
- Room (`appearance/room.py`, `appearance/surfaces.py`, `appearance/joinery.py`, finished by
  `appearance/photo_finish.py` with the inputs in `appearance.finish` of `scene_config.py`): no lettering or
  labels, no plaque or engraved scale ticks; the book stack is turned so the printed spines face the wall
  and the camera sees the page edges.
- Wall: scanned matte painted plaster (`beige_wall_001`, 4k diffuse, roughness and normal) on metre-true
  planar UVs with a 3 m tile; the scan's mean albedo is rebalanced to a greige paint.
- Window: thin float glass (Fresnel reflection plus straight transmission), an opening casement sash with
  glazing beads and a handle; no coplanar faces at the frame corners. The view outside is the
  `residential_garden` HDRI on a backdrop only camera rays see. The daylight emitter (0.64 × 1.0 m,
  120 W) sits in the wall opening behind the glass, invisible to the camera. The sheer curtain is
  open-weave (45 % of the light passes the weave, the rest is translucent cloth).
- Light: window daylight is the key light; the rest of the room is the `small_empty_room_1` HDRI at
  strength 0.45; no hidden fill lights.
- Bob: a faint fingerprint haze fixed to the ball (roughness 0.10–0.24).
- Camera: 50 mm lens, f/5.6.
- Render: Cycles 256 samples (adaptive threshold 0.01), OpenImageDenoise, glossy filter 0.5, caustics off,
  AgX, seed 42, 8 bounces; H.264 CRF 17, yuv420p. 256 samples keep the rear halves of the 0.9 mm coil loops
  after denoising. Motion blur uses a 0.25-frame shutter centred on each frame, so persistent data is off
  (Blender 4.3 drops objects that come to rest from later frames when the two are combined).
  `keyframe_shutter` in `appearance/renderer.py` keys the frame centre to the cached state (checked at
  render time) and the shutter open and close to the native trace samples 32 of 256 per frame either side.
  The coil uses the cached per-frame meshes as absolute shape keys and is blended inside the shutter toward
  the neighbouring frame by the traced compression.

## Physics

- Solver: MuJoCo 3.15.0 on the CPU, 1024 substeps per video frame; traces recorded at 6144 Hz (256
  samples per frame).
- Joints and contact: native MuJoCo hinge (damping 0.00065 N·m·s) and slide joints, and a regularized
  contact between the ball and the plate's central face; a free-length end stop. No motors, timed impulses
  or scripted trajectories.
- Spring: E = 200 GPa, ν = 0.3, wire density 7850 kg/m³; stiffness k = G d⁴ / (8 D³ Nₐ) ≈ 74.06 N/m,
  energy U = k x² / 2. The moving mass is the plate, guide rod and stop ring plus a third of the active wire
  and the moving end coil. Guide and axial losses F = −c v with c = 1.0 N·s/m (a phenomenological guide
  loss, not derived from E).
- All inputs are in `scene_config.py`, split into `physics`, `simulation_quality`, `appearance` and
  `render`.

## Measured motion

| Case | Max compression |
|---|---|
| `source` | 29.5 mm at 0.328 s (first contact at 0.254 s) |
| `edit_soft_spring` | 54.2 mm at 0.407 s |
| `edit_stiff_spring` | 11.1 mm at 0.280 s |
| `edit_heavy_ball` | 42.4 mm at 0.353 s |
| `edit_delete_spring` | — (the pendulum swings freely) |

In `edit_delete_spring`, at its turning point (+29.5°) the ball passes 2.9 mm from the fixed backing
plate and about 2.3 mm from the rim of the fixed spring seat; from the fixed
camera the ball overlaps the top of the bracket in projection but never touches it.

## Validation

- `validation/` checks physics and video and records the keyframe review.
  Contact windows are kept whole; small separations within one swing are merged into one encounter.
- Between impacts the spring must return within 1 mm of its free length before the next hit (the final
  interval cut by the clip end is only recorded).
- The mean RGB change between adjacent frames in the wall region is at most 0.035/255 (all cases).
- Rendering stops until a keyframe review for the current configuration, code and assets is recorded
  (`validation/static.py --accept-reviewed --note ...`).

## Cases

Native case ids are the published names without the `edit_` prefix (`source`, `soft_spring`,
`stiff_spring`, `heavy_ball`, `delete_spring`). Each edit changes one independent physical input in
`edits/presets.py`; derived G, k, mass and inertia are recomputed. Release angle, geometry, damping,
contact, camera and render settings match the source.

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | E = 200 GPa, k ≈ 74.06 N/m, 0.19055 kg ball |
| `edit_soft_spring` | `SET spring.young_modulus TIMES 0.1` | E ÷ 10 (G and k ÷ 10) |
| `edit_stiff_spring` | `SET spring.young_modulus TIMES 10` | E × 10 (G and k × 10) |
| `edit_heavy_ball` | `SET ball.mass TIMES 2` | ball mass × 2 (density, ball inertia, centre of mass and hinge inertia updated) |
| `edit_delete_spring` | `DELETE spring` | coil, plate, moving guide rod and stop ring removed from t = 0 |

E is a counterfactual parameter, not a real steel grade.

## Assets

| assets.json key | Type | Use |
|---|---|---|
| `scenes/metal_pendulum_horizontal_spring` | mixed (44 url, 23 derived) | room props, PBR scans, HDRIs, template scenes, generated geometry and accepted states |
| `polyhaven/book_encyclopedia_set_01` | mixed (8 url, 1 derived) | books |
| `polyhaven/wood_table_001` | mixed (6 url, 1 derived) | wood of the base and table |
| `polyhaven/beige_wall_001` | url | painted plaster wall |
| `polyhaven/residential_garden` | url | view through the window |

```bash
python3 scripts/download_assets.py --scene metal_pendulum_horizontal_spring          # download and check sha256
python3 scripts/download_assets.py --scene metal_pendulum_horizontal_spring --check  # check only
```

Files are stored under `assets/` (`PCVE_ASSETS_DIR` moves the root); scene-only files are in
`assets/scenes/metal_pendulum_horizontal_spring/`. The 23 derived files have no public download, so
`--check` reports them missing. `asset_manifest.json` lists the pinned catalogues in
`asset_tools/catalogs/`, which `asset_tools/prepare.py` downloads and verifies.

## Requirements

- Linux; MuJoCo runs on the CPU; an NVIDIA GPU speeds up rendering (`PCVE_RENDER_DEVICE=CPU` renders on
  the CPU).
- Python environment `.venv-genesis-mpm-sph/` at the repository root with `requirements.txt`
  (mujoco 3.15.0, numpy 2.2.6, matplotlib 3.10.8, Pillow 11.3.0); `entrypoints.json` points the simulator
  at it. `requirements-dev.txt` adds optional formatting and lint tools configured in `pyproject.toml`.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then `~/.local/opt/blender-*/blender`;
  `--blender` overrides it.
- `ffmpeg` and `ffprobe`.

## Commands

Run from the repository root; use a new output root for each experiment.

```bash
.venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/metal_pendulum_horizontal_spring/build_pcve_metal_pendulum_horizontal_spring.py --list-cases
.venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/metal_pendulum_horizontal_spring/build_pcve_metal_pendulum_horizontal_spring.py \
    --out-root renders/metal_pendulum_horizontal_spring/<new folder> --dry-run
.venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/metal_pendulum_horizontal_spring/asset_tools/prepare.py \
    --verify-only --report renders/metal_pendulum_horizontal_spring/<new folder>/asset_validation.json

# 1. simulate the source, then the edits
.venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/metal_pendulum_horizontal_spring/build_pcve_metal_pendulum_horizontal_spring.py \
    --out-root renders/metal_pendulum_horizontal_spring/<new folder> --stage simulate --cases source
.venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/metal_pendulum_horizontal_spring/build_pcve_metal_pendulum_horizontal_spring.py \
    --out-root renders/metal_pendulum_horizontal_spring/<new folder> --stage simulate --cases soft_spring stiff_spring heavy_ball delete_spring

# 2. render full-quality keyframes of the source, look at them, then record the review
PCVE_RENDER_DEVICE=GPU .venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/metal_pendulum_horizontal_spring/build_pcve_metal_pendulum_horizontal_spring.py \
    --out-root renders/metal_pendulum_horizontal_spring/<new folder> --stage keyframes --cases source --gpu <GPU index or UUID>
.venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/metal_pendulum_horizontal_spring/validation/static.py \
    renders/metal_pendulum_horizontal_spring/<new folder> --accept-reviewed --note "<what you checked in the keyframes>"

# 3. render all cases and run the video checks
PCVE_RENDER_DEVICE=GPU .venv-genesis-mpm-sph/bin/python scripts/rigid_elastic/metal_pendulum_horizontal_spring/build_pcve_metal_pendulum_horizontal_spring.py \
    --out-root renders/metal_pendulum_horizontal_spring/<new folder> --stage render --gpu <GPU index or UUID> --threads 16
```

- `--stage all` runs asset preparation, the five simulations, the source keyframes and the renders, but
  stops before rendering until the keyframe review is recorded. `--stage prepare` downloads missing assets
  from their pinned URLs and checks their hashes; `--stage verify` runs the checks.
- A cache is never overwritten; the simulate entry's `--reuse-cache` reuses one only if configuration,
  physics code and every cache hash match.

## Outputs

New runs write to the chosen output root under `renders/metal_pendulum_horizontal_spring/`; each case
goes to `<run>/cases/<case>/`. The published suite is
`renders/pcve_suites/pcve_metal_pendulum_horizontal_spring_suite/`; no command writes into it by default.

| File in a case folder | Content |
|---|---|
| `video.mp4`, `frames/`, `keyframes/` | rendered video and frames |
| `scene.blend` | scene with the solved states, playable without re-simulating |
| `trajectory.npz` | 97 solved states, t = 0 to 4 s (the video uses the first 96) |
| `trace.npz`, `trace.csv` | 6144 Hz traces |
| metrics.json | first contact, peak axial compression, angular velocity after separation, recovery, later swing amplitudes |
| actual_config.json, `model_input.xml`, `model.xml`, `model.mjb` | exact inputs and the MuJoCo model |
| `*_validation.json` | physics and video checks |

The run root also holds `static_acceptance/acceptance.json` (the recorded keyframe review).

## Code layout

- `simulate_metal_pendulum_horizontal_spring.py`: simulation entry
- `render_metal_pendulum_horizontal_spring.py`: Blender rendering entry
- `build_pcve_metal_pendulum_horizontal_spring.py`: staged build entry
- `scene_config.py`: all physical, numerical, appearance and render inputs; the cache and edit checks compare them with the configuration stored next to each cache
- `edit_vocab.py`: edit DSL vocabulary and prompts
- `scene_paths.py`: paths, implementation fingerprint, cache checks
- `model/`: native dynamics, coil mesh, integration and recording
- `edits/`: edit presets and exact configuration differences
- `appearance/`: room, surfaces, joinery details, photographic finish (`appearance/photo_finish.py`), renderer
- `pipeline/`: stages, processes, locks, logs and products
- `asset_tools/`, `asset_manifest.json`: pinned asset catalogues, verification and restore
- `validation/`: physics and video checks and the keyframe review record
- `tools/`: playback export
- `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`: Python packages and lint configuration
- `entrypoints.json`, `scene_manifest.json`: entry-point options, runtimes, cases and the published suite

## Limitations

- The spring is a guided linear axial reduced model with two-way contact feedback; local wire vibration,
  lateral buckling, plasticity and coil-to-coil contact are not solved.
- The guide loss c is phenomenological, not measured on a real bushing.
- Nothing is fitted to a real experiment.
