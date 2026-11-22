# slingshot_domino

A tabletop slingshot clamped to a table edge: two flat rubber bands pull a leather pouch back and, released at 0.5 s,
launch a small plastic ball along the table towards a wooden domino about 29 cm away, which it knocks over. This is a
rigid–elastic scene: rigid ball, pouch and domino driven by extensible rubber strips. The source video is 4 s, 24 fps,
96 frames, 1280×720; frame k shows the native state at t = (k - 1)/24 s.

## Scene

- Slingshot: a hand-shaped laminated Y frame 19 mm thick (exact profile in `physics/fork_profile.py`,
  `physics/fork_geometry.py`), clamped to the table edge with a dark gunmetal desk clamp. Two flat bands
  9 cm × 4 mm × 0.18 mm, anchored at the fork tips (0, ±43 mm, 132 mm); a light rigid compound pouch cup (0.45 g,
  26 mm wide). Ball and pouch start drawn back at x = -0.113 m and -0.122 m, 132 mm above the table.
- Ball: plastic, r = 7.5 mm, 1.85 g. Domino: wooden, 12 × 35 × 75 mm, 16 g, standing at x = 0.18 m.
- Base look (`appearance/render_scene.py`, `appearance/realism.py`): the `wooden_table_02` table (4K, scaled to 1.1 m
  long); the Y frame with a measured pale plywood face (the photographs cover 0.5 m), 13-ply sawn and sanded edges as
  a shader and fine end grain; domino, mounting foot and props each with their own timber cut and UVs, the domino with
  ebony-inlaid pips; satin machined steel and the gunmetal clamp with directional machining marks; brass band clamps
  with slotted screws at the fork tips; a worn oxblood leather pouch; matte amber latex bands with slight subsurface; a
  moulded petrol-blue polymer ball; an off-white sketch sheet with faint graph lines, a sandpaper scrap and a small
  wooden ruler.
- Published look (`appearance/realism_overlay.py`): runs `appearance/render_scene.py` unchanged apart from one hook, so
  trajectories, band frames, camera and edits are those of the base renderer, and asserts that no base object moves.
  It hides the base background (shelf, brush pot, sketchbook, cork board with pinned plans) and room floor and adds a
  daylight room with a sage limewash wall, a tempered hardboard pegboard behind the bench (1-inch hole grid, 3.2 mm
  holes, on pine furring strips), a warmer oiled tone and surface wear on the table, a flathead screwdriver and a
  lidded box, and 700 maple dust flecks around the base. Every addition stays outside the motion of all six cases
  (including the `edit_delete_domino` ball's path to the floor) and the props sit wholly in frame.
- Light: a low afternoon sun through the left window (strength 13, 1.0 degree), a 1.7 × 1.4 m window sky fill
  (energy 9), world strength 0.45; the base studio area lights kept at 10 % as weak fill.
- Camera: the shared diagonal view of `appearance/render_scene.py`, at (-0.34, -0.52, 0.295) m aimed at
  (0.005, 0, 0.063) m, 53 mm lens on a 36 mm sensor, f/13, focused on the aim point.
- Render: Blender 4.3.2 Cycles on a CUDA GPU, 128 samples (`--samples`), adaptive threshold 0.018, denoising, AgX
  Medium High Contrast, exposure from `REALISM_EXPOSURE` (default 0.1 EV), lens finish (vignette 0.12, dispersion
  0.0025), 1280×720, 24 fps, PNG frames.

## Physics

- `physics/physics.py` (CPU, NumPy/Numba and PyBullet): the two bands are extensible neo-Hookean strips (40 segments,
  E = 1 MPa, 960 kg/m^3, Kelvin viscosity 160 Pa·s, weak strip bending) with finite-width contact against the exact
  Y-frame profile and the table; ball, pouch and domino are PyBullet rigid bodies with full 6-DOF contact. The pouch
  has no ball constraint and no launch kick.
- Friction: table 0.5, ball 0.25, domino 0.65; gravity 9.81 m/s^2; release at 0.5 s.
- 4800 substeps per frame (19200 for `heavy_ball`). The cache holds the 96 real-time states, the band centrelines and
  material frames, and a separate 72 Hz series used only for the labelled 3× slow replay.
- `physics/config.py` holds the baseline and the case DSL; `physics/vocabulary.py` resolves the DSL into solver fields.
- Timed edit: a native continuation inside one run. The solver starts from the source scenario and at frame 12
  (t = 11/24 s) multiplies the domino mass and inertia by 10 with PyBullet `changeDynamics`, then keeps integrating.
  Frames 1–11 are identical to the source.

## Measured motion

From the published ground truth. In every case the ball and pouch start to move at frame 14, the first sample after
the 0.5 s release.

| Case | Domino | Ball at the end |
| --- | --- | --- |
| `source` | hit, first moves at frame 17, lies flat from frame 22 (centre 37.5 mm -> 6 mm above the table) | at rest on the table, x = 0.149 m |
| `edit_soft_bands` | first moves at frame 19, slides 5 mm and stays standing | on the table, x = 0.203 m |
| `edit_heavy_ball` | stays standing (does not move) | on the table, x = -0.097 m, y = 0.172 m |
| `edit_heavy_domino` | hit, first moves at frame 17, lies flat from frame 24 | on the table, x = 0.093 m |
| `edit_heavy_domino_at_frame_12` | stays standing (moves less than 1 mm) | on the table, x = 0.035 m |
| `edit_delete_domino` | - | rolls off the table edge and comes to rest on the floor near x = 2.3 m |

## Cases

Native case ids are the case directory names without the `edit_` prefix.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | - | bands E = 1 MPa, ball 1.85 g, domino 16 g |
| `edit_soft_bands` | `SET bands.young_modulus TIMES 0.5` | band E 1 -> 0.5 MPa |
| `edit_heavy_ball` | `SET ball.mass TIMES 3` | ball 1.85 -> 5.55 g |
| `edit_heavy_domino` | `SET domino.mass TIMES 2` | domino 16 -> 32 g |
| `edit_heavy_domino_at_frame_12` | `SET domino.mass TIMES 10 AT FRAME 12` | domino 16 -> 160 g (mass and inertia ×10) from frame 12 (t = 11/24 s) |
| `edit_delete_domino` | `DELETE domino` | no domino |

Camera, lights, table and every other initial pose are shared by all cases.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `scenes/slingshot_domino` | mixed (25 url, 3 derived) | table, wood, leather and plywood textures, HDRI and the props of the published look |

```bash
python3 scripts/download_assets.py --scene slingshot_domino
python3 scripts/download_assets.py --scene slingshot_domino --check
```

`PCVE_ASSETS_DIR` moves the asset root.

## Requirements

- Solver: a Python with NumPy, Numba and PyBullet (`.venv-rigid-elastic`); CPU only.
- Rendering: Blender 4.3.2 (`tools/blender-4.3.2-linux-x64/blender`, else the shared lookup; `--blender-bin`
  overrides) on a CUDA GPU; the render entry goes through `tools/worker_run.py` (shared GPU policy, per-GPU lease).
- ffmpeg for encoding.

## Commands

```bash
S=scripts/rigid_elastic/slingshot_domino
PY=.venv-rigid-elastic/bin/python

# verify the stored delivery and the published timed edit
python3 $S/build_pcve_slingshot_domino.py --stage verify
python3 $S/build_pcve_slingshot_domino.py --list-edits
python3 $S/build_pcve_slingshot_domino.py --show-prompts heavy_domino_at_frame_12
python3 $S/build_pcve_slingshot_domino.py --export-prompts \
    --out-root renders/pcve_suites/pcve_slingshot_domino_suite --dry-run

# solve one case or all cases (CPU)
$PY $S/simulate_slingshot_domino.py --case heavy_domino_at_frame_12 --out renders/slingshot_domino/<new folder>/heavy_domino_at_frame_12
$PY $S/simulate_slingshot_domino.py --all --out renders/slingshot_domino/<new folder>

# render one non-timed case in the published look on a leased GPU and encode it (default input: the stored case)
python3 $S/render_slingshot_domino.py --case source --simulation <solve folder> --out renders/slingshot_domino/<new folder>/source --samples 128 --gpu-uuid <GPU UUID>

# the same look directly in Blender on a GPU (also for the timed edit's solve folder)
CUDA_VISIBLE_DEVICES=<GPU UUID> <blender 4.3.2> -b --factory-startup --disable-autoexec \
    --python-exit-code 1 --python scripts/rigid_elastic/slingshot_domino/appearance/realism_overlay.py -- \
    --assets assets/scenes/slingshot_domino --simulation <solve folder> --out renders/slingshot_domino/<new folder>/<case>
```

- A solve folder holds `scene_params.json` and `trajectory.npz` or `physics_cache.npz`. The render entry accepts the
  five non-timed cases; `--gpu-uuid` defaults to `auto`. `--slow` renders the separately labelled auxiliary 3× slow
  replay (physical time 0.4 + (k - 1)/72 s, played at 24 fps) instead of the real-time clip.
- `--stage verify` checks the strict edit policy, the five delivered videos and physics caches against the sha256 in
  their encoding receipts and their native 24 fps clocks, and for `heavy_domino_at_frame_12` the published video, its provenance and its
  native clock. `--accepted-root DIR` reads the stored delivery from another root; `--out DIR` also writes the report
  to DIR/verify_report.json. `--native-help` prints the builder's own options.
- `--export-prompts [--dry-run]` writes the builder's prompts into a suite (by default `renders/slingshot_domino/suite_build/pcve_slingshot_domino_suite/`; the published suite only
  when its path is given with `--out-root`).

## Outputs

- New solves default to `renders/slingshot_domino/physics/<case>`; renders, launch records and encodes go under
  `renders/slingshot_domino/`.
- Stored delivery of the five non-timed cases (real-time video, labelled 3× slow clip `slow_3x.mp4`, physics cache and
  report, scene parameters, scenario overrides, render and encoding receipts):
  `renders/slingshot_domino/delivery/accepted/`. It is a record, not registered in
  `assets.json`; the render entry replays its physics caches by default.
- Native run of the timed edit: `renders/slingshot_domino/timed_mass10_frame12/`.
- The published suite is `renders/pcve_suites/pcve_slingshot_domino_suite/` (pointer in `scene_manifest.json`); only
  `--export-prompts` with this path as `--out-root` writes it.
- Ground truth (`pcve_ground_truth/1`): generated from the native trajectory caches (the delivered physics caches, and
  for the timed edit its `native_metadata/trajectory.npz`); ball, pouch and domino are rigid bodies, the bands a
  deformable body, camera 53 mm on a 36 mm sensor. The scene has no exporter of its own.

## Code layout

- `build_pcve_slingshot_domino.py`: edit catalog (`PCVE_SOURCE`, `PCVE_EDITS`, equal to the published `prompts.json`;
  edit prompts are `pcve_edit_dsl.make_prompts` output for `edit_vocab.py`, source prompts written from the
  configuration and the source video); `--stage verify`.
- `simulate_slingshot_domino.py`: CPU solve of one case or all cases (runs `physics/simulate_cli.py`).
- `render_slingshot_domino.py`: Blender replay of one case in the published look on a leased GPU, then encode.
- `edit_vocab.py`: public DSL vocabulary (re-exported from `physics/vocabulary.py` and `physics/config.py`).
- `physics/physics.py`, `physics/ribbon_physics.py`: band strips and PyBullet coupling.
- `physics/fork_profile.py`, `physics/fork_geometry.py`: Y-frame profile and collision geometry.
- `physics/config.py`: baseline and case DSL.
- `physics/vocabulary.py`: resolves the DSL into solver fields.
- `physics/simulate_cli.py`: solve command line.
- `appearance/render_scene.py`: scene construction and native-state replay (Cycles CUDA).
- `appearance/realism.py`: measured-scale surface detail used by `appearance/render_scene.py`.
- `appearance/realism_overlay.py`: published look, applied to `appearance/render_scene.py` through one audited hook.
- `appearance/ribbon_frames.py`: band surface frames on the native centrelines.
- `tools/retained_delivery.py`: checks behind `--stage verify`.
- `tools/encode_on_worker.py`: encodes the 96 rendered frames (H.264, crf 16, yuv420p, 24 fps).
- `tools/worker_run.py`: GPU launcher with preflight and lease (with `scripts/pcve_gpu_reservations.py`).

## Limitations

- Materials are plausible SI values, not calibrated on a real specimen.
- The render entry does not take the timed case; its solve folder is rendered with the direct Blender command.
- The published results were computed on other Linux GPU machines; bitwise reproduction elsewhere is not verified.
