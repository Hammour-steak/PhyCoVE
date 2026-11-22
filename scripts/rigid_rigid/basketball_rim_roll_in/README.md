# basketball_rim_roll_in

A rigid–rigid scene in PhyCoVE. In a school sports hall a basketball is thrown at an angle
into the backboard, banks into the rim, circles the inside of the rim for 1.71 turns and drops
through, then lands in front of the goal's ballast box. The ball is the only free body; PyBullet
solves every contact and Blender replays the solved poses. The source video is 4 s, 24 fps,
96 frames, 1280×720.

## Scene

- **Units and axes:** SI, Z up, gravity −9.81 m/s².
- **Goal (static colliders):** the collider numbers are measured from the game-model gym
  `indoor_basketball_court.glb`, which is not in the repository or in `assets.json` and is not loaded. The rim is lower
  than a regulation 3.05 m rim and close to a 2.60 m mini-basketball goal, so a regulation rim
  height would put the ball above the board.

  | quantity | value |
  | --- | --- |
  | backboard face | y = 6.4949, x ∈ ±0.642, z ∈ 2.5625..3.4253 (board slab 1.284 × 0.020 × 0.863 m) |
  | rim centre | (0.0, 6.1063), ring centreline radius 0.208 m, tube radius 0.0123 m |
  | rim plane | z = 2.7252, inner opening radius 0.1957 m |
  | floor | z = 0.1042 (top of the model's 104 mm floor slab) |
  | ballast box | wedge: front edge x ∈ ±0.30, top z = 0.145; rear edge x ∈ ±0.559, top z = 0.412; y ∈ 7.02..8.55 |

- **Rim collider:** PyBullet has no torus primitive, so the rim is 96 static spheres with radius
  equal to the tube radius, spaced half a tube radius apart. Their contact surface deviates from
  a true ring by at most 0.4 mm. A rim bracket box ties the ring to the board. There is no net in
  the simulation and none in the picture.
- **Ballast box:** a triangle mesh from the wedge's eight corners with a 10.7° top slope; a ball
  landing on it slides back down.
- **Ball:** `assets/models/basketball.glb`, normalised by its bounding sphere to radius 0.105 m,
  mass 0.62 kg. It is released at (−1.41097, 4.38749, 2.11899) m with a low arc, aimed at the
  board point x = −0.29915, z = 3.05076 m, at 6.357399 m/s, with spin 65.466 rad/s tilted −40.72°.
- **Camera:** (3.00, 2.60, 3.50) looking at (0.45, 6.15, 1.85), 24 mm lens, 36 mm sensor, no
  depth of field; a high three-quarter view from the open side of the court that sees into the
  ring.
- **Hall (`appearance/gym_hall.py`):** a school gym in the afternoon with a portable goal on one
  end of the court.
  - Floor: narrow-strip maple sports flooring from the `wooden_floor_01` scan (66 mm strips,
    1.19 m board bands offset at random), gloss coat with roughness 0.08–0.24, sole marks, and
    court markings at regulation dimensions referenced to this rim, with a navy restricted area.
  - Walls: navy vinyl impact padding from 0.10 to 2.00 m (1.2 m panels, 6 mm gaps), black rubber
    skirting, white-painted blockwork above; steel double doors with vision panels and push bars,
    a return-air grille, a fire alarm bell and a blue equipment box on the end wall.
  - Light: on each long wall a row of 3.0 × 3.2 m windows (sills 2.7 m up, 0.3 m reveals,
    aluminium frames); a sun lamp at 47.9° elevation through the left windows, a Nishita sky, one
    portal per window and a pure-sky photograph seen only by camera rays; 28 pendant high-bay
    lamps, each lit by a 0.42 m disc light at its shade. There are no hidden fill lights.
- **Goal appearance:** every surface the ball can touch coincides with a collider: the glass
  backboard with white border and 0.59 × 0.45 m target rectangle is the board box, the
  orange rim is a torus on the centreline of the 96 spheres, the bracket is the bracket box and
  the dark steel base is the wedge. The aluminium board frame, back frame, arms, post with navy
  padding, braces and rear wheels are props. The post stands at the rear of the base
  (y = 8.20 m) on a 1.65 m arm.
- **Ball appearance:** the ball mesh is subdivided with every vertex at the physical radius, so
  its silhouette is the solver's sphere. Printed lettering and marks on the ball texture are
  covered at render time by shifting their texture lookups onto adjacent plain-leather panels
  (`LOGO_PATCHES` in `appearance/look_basketball_rim_roll_in.py`).
- **Render:** Blender 4.3.2 Cycles, 1280×720, 24 fps, 96 frames, adaptive threshold 0.01, OIDN
  denoising, AgX Base Contrast, exposure +0.6, 0.25-frame motion blur with persistent data off.
  The source video and edits use 256 samples (`--samples 256`).

## Physics

- **Solver:** PyBullet 3.2.7, 60 substeps per frame (1440 Hz), 120 solver iterations. Frame i is
  the state at t = (i−1)/24 s.
- **Launch:** the release velocity is solved ballistically (`physics/launch.py`) from the release
  point, the aim point on the board and the speed, so an aim edit throws at a different place and
  a speed edit throws harder.
- **Coefficients:** ball restitution 0.60, friction 0.72, rolling friction 0.004, spinning
  friction 0.0002, linear and angular damping 0.006; board 0.55 / 0.3304; rim 0.05 / 1.20; floor
  0.60 / 0.62 (rolling friction 0.004); ballast box 0.34 / 0.45. The rim values are effective
  values that stand in for the compliance of a real rim and the damping of a net.
- **Timed edits:** `physics['timed_edits']` lists `{frame, params}` events. The solver runs the
  source parameters up to frame n−1 and writes the new value into the running world before
  frame n; only `gravity_z`, `ball_restitution` and `ball_friction` may change, and the ball's
  pose and velocity are checked to be unchanged by the write.
- **Sensitivity:** the release parameters are stored at full precision (17 digits) because the
  rim orbit is chaotic. Of 2600 random bank shots only 6 hit the board, orbit the rim more than
  once and drop through. Perturbing the source's nine release parameters by 0.1 % keeps an
  orbit of at least 1.2 turns in 1 of 14 samples, and by 0.5 % in none of 14. Rounding the aim
  point to 3 decimals drops the orbit from 1.71 to 0.67 turns (through at frame 23); rounding the
  speed to 6.357 gives 0.56 turns (frame 22); rounding the spin to 65.5 has no effect.

## Measured motion

| Case | Measured outcome |
| --- | --- |
| `source` | hits the board at frame 13, enters the rim zone at frame 17, 1.71 turns, drops through at frame 40, lands at frame 54 and stops in front of the ballast box at y = 6.93 m |
| `edit_fast_ball` | hits the board at frame 6, passes over the rim with 0 rim contacts, ends at x = 6.34 m, y = −0.54 m |
| `edit_aim_high` | touches the rim at frame 21, 0.64 turns, drops through at frame 24, lands behind the board, hits the ballast box slope and stops at (0.11, 6.71) |
| `edit_aim_left` | hits the outside of the front-left rim tube at frame 19, one rim contact, 0 turns, never enters the rim, lands at frame 41 at (−0.18, 5.04) |
| `edit_bouncier` | passes over the rim with 0 contacts, lands at frame 33, touches the floor again at frames 62 and 87 (peak height 2.07 m, then 1.48 m) and is 1.09 m in the air at frame 96 |
| `edit_gravity_midway` | frames 1–13 identical to the source; 0.26 turns, drops through at frame 21, lands at frame 28 |

Two runs of all six cases with PyBullet 3.2.7 on Linux give identical results.

## Validation

- The builder rejects a case with a non-finite state, a ball that penetrates the floor or board by
  more than 1 cm, or a ball that never moves more than 2 cm from the source path. For the timed
  edit, frames before the start frame must reproduce the source positions exactly.
- Before rendering, all 96 frames (plus 8 points between frames) are checked for the closest
  distance between the ball and every prop; under 2 cm fails. For every frame with the ball in
  view, rays from the camera to the ball must not hit a prop. All six cases pass; the closest prop
  is 7.8 cm away (the backboard back frame in `edit_aim_left`, behind the glass).
- `render_validation.json` records per frame whether the ball projects into the frame, whether
  the ray hits the ball first, and the closest prop. `scenario_metadata.json` records the device
  that rendered the image.
- `tools/audit_basketball_rim_roll_in.py` checks the recipe, the vocabulary and a built suite
  without simulating, including that `assets/scenes/basketball_rim_roll_in/scenario.json` equals
  `scene_config.defaults()`.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source shot |
| `edit_fast_ball` | `SET ball.initial_velocity TIMES 2` | Release speed 6.357 → 12.715 m/s; release and aim points unchanged |
| `edit_aim_high` | `SET ball.aim_z TO 3.14` | Board aim point height 3.051 → 3.14 m |
| `edit_aim_left` | `SET ball.aim_x TO -0.42` | Board aim point across the board −0.299 → −0.42 m (0.12 m to the left) |
| `edit_bouncier` | `SET world.restitution TIMES 1.5` | Restitution of ball, board, rim, floor and ballast box ×1.5 (ball 0.60 → 0.90, board 0.55 → 0.825, rim 0.05 → 0.075, floor 0.60 → 0.90, box 0.34 → 0.51) |
| `edit_gravity_midway` | `SET world.gravity TIMES 3 AT FRAME 14` | Gravity −9.81 → −29.43 m/s² from frame 14 (t = 0.542 s), one frame after the board impact |
| `edit_delete_backboard` | `DELETE backboard` | Backboard and rim removed from frame 1 |

The builder names the source case `basketball_rim_baseline`; the edit IDs are the same as the
published case names. `edit_vocab.py` declares the vocabulary and the cases; prompts are generated
by `pcve_edit_dsl.make_prompts`.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `models` (`basketball.glb`) | manual | ball mesh and textures |
| `polyhaven/basketball_rim_roll_in` | url | hall textures (floor, padding grain, blockwork), the sky photograph, pendant lamp and equipment box models |
| `scenes/basketball_rim_roll_in` | derived | `assets/scenes/basketball_rim_roll_in/scenario.json` (scene recipe, must equal `scene_config.defaults()`) and `assets/scenes/basketball_rim_roll_in/baseline_metrics.json` (source-run frame numbers quoted by the vocabulary) |

```bash
python3 scripts/download_assets.py --scene basketball_rim_roll_in
python3 scripts/download_assets.py --scene basketball_rim_roll_in --check
```

## Requirements

- Python with `pybullet==3.2.7` (`requirements.txt`; `numpy` is listed for shot-search tools).
  The repository's `.venv-domino/` environment has both.
- Blender 4.3.2 for rendering (`tools/blender-4.3.2-linux-x64/blender`, or `--blender`), or a
  Python with the `bpy` module via `--render-python`.
- A GPU is optional. `--device auto` uses a GPU when Cycles sees one; `--device gpu` fails instead
  of falling back to the CPU; `--gpu-backend` selects `optix` or `cuda`.

## Commands

Run from the repository root.

```bash
# case list
python3 scripts/rigid_rigid/basketball_rim_roll_in/build_pcve_basketball_rim_roll_in.py --list-cases

# physics for all six cases, then the read-only audit
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/basketball_rim_roll_in/build_pcve_basketball_rim_roll_in.py \
  --out-root renders/basketball_rim_roll_in/new_run --simulate-only
.venv-domino/bin/python scripts/rigid_rigid/basketball_rim_roll_in/tools/audit_basketball_rim_roll_in.py \
  --out-root renders/basketball_rim_roll_in/new_run

# physics and keyframes for every case
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/basketball_rim_roll_in/build_pcve_basketball_rim_roll_in.py \
  --out-root renders/basketball_rim_roll_in/new_run --mode keyframes \
  --samples 256 --device cpu --blender tools/blender-4.3.2-linux-x64/blender

# one case solved on its own
.venv-domino/bin/python scripts/rigid_rigid/basketball_rim_roll_in/simulate_basketball_rim_roll_in.py \
  --out renders/basketball_rim_roll_in/new_run/cases/basketball_rim_baseline/physics_transforms.json

# all 96 frames of one case as PNGs from its solved trajectory
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
  --python scripts/rigid_rigid/basketball_rim_roll_in/render_basketball_rim_roll_in.py -- \
  --out-dir renders/basketball_rim_roll_in/new_run/cases/basketball_rim_baseline \
  --physics-json renders/basketball_rim_roll_in/new_run/cases/basketball_rim_baseline/physics_transforms.json \
  --mode sequence --samples 256 --device auto
```

- Builder `--mode` is `build`, `preview`, `keyframes` (default) or `animation`; the render script
  also has `sequence`, which writes `frames/frame_####.png`, and `--frame-range FIRST LAST`
  renders a sub-range. `--only` takes a comma-separated list of edit IDs (the source is always
  included).
- Without `--physics-json` the render script runs the solver first. With it, the trajectory is
  accepted only if its physics block equals the case's scenario (including
  `--scenario-overrides-json`).
- `--threads` limits CPU rendering and is ignored on the GPU.

## Outputs

- A build writes `cases/<case>/` under `--out-root` (default
  `renders/basketball_rim_roll_in/suite_build/pcve_basketball_rim_roll_in_suite`):
  `scenario_overrides.json`, `scenario_input.json`, `prompts.json`, `physics_transforms.json`,
  `simulation_metrics.json`, `run_status.json`, and after rendering `ground_truth_transforms.json`,
  `render_validation.json`, `scenario_metadata.json`, `cases/<case>/keyframes.json`, the packed
  `basketball_rim_roll_in.blend` and frames or `video.mp4`; plus `suite_manifest.json`.
- The builder also writes the source run's frame numbers to
  `assets/scenes/basketball_rim_roll_in/baseline_metrics.json`.
- The published suite is `renders/pcve_suites/pcve_basketball_rim_roll_in_suite/`; do not use it
  as an output root.

## Code layout

- `simulate_basketball_rim_roll_in.py` — PyBullet solve of one case (public entry).
- `render_basketball_rim_roll_in.py` — Blender replay, checks and render (public entry).
- `build_pcve_basketball_rim_roll_in.py` — source and edit suite builder with per-case checks (public entry).
- `scene_config.py` — physics, camera, render and layout defaults; scenario loading and validation.
- `edit_vocab.py` — edit DSL vocabulary, edit cases and source prompts.
- `physics/scene_geometry.py` — static collider geometry (board, rim spheres, bracket, ballast box, floor).
- `physics/launch.py` — ballistic inverse solve for the release velocity.
- `appearance/look_basketball_rim_roll_in.py` — the goal built on the colliders, the ball, scene assembly.
- `appearance/gym_hall.py` — the sports hall, lighting, props and clearance/occlusion checks.
- `tools/audit_basketball_rim_roll_in.py` — read-only audit of recipe, vocabulary and a built suite.
- `requirements.txt`, `entrypoints.json`, `scene_manifest.json` — dependencies and entry metadata.

## Limitations

- The rim is a rigid ring of spheres; rim compliance and the net are represented only by the
  effective rim coefficients (restitution 0.05, friction 1.20).
- No net is drawn, because the ball leaves the rim sideways through where a net would hang.
- The source shot is sensitive at the level of the stored decimals; any change to the release
  parameters can remove the rim orbit.
- The goal dimensions follow the measured game model, not a regulation goal.
