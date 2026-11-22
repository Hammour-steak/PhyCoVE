# basketball_court_bounce

A rigid–rigid scene in PhyCoVE. An orange 24 cm basketball is released from rest with its bottom
1.50 m above the maple floor of an indoor practice gym. Gravity and rigid contact impulses produce
repeated vertical bounces with diminishing peaks and shorter contact intervals, seen by a fixed
side camera that keeps the whole path and the floor contact point in view. PyBullet solves the
motion and Blender replays it. The source video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- **Units and axes:** SI, Z up, gravity (0, 0, −9.81) m/s².
- **Ball (B01):** sphere, radius 0.12 m, mass 0.625 kg, hollow-sphere inertia 2mr²/3, centre at
  (0, −0.6, 1.62) m, zero linear and angular velocity.
- **Floor (F01):** fixed 18 × 32 × 0.12 m box with its top face at z = 0.
- **Room and scale cues:** 18 × 32 × 7 m gym with a 15 × 28 m marked court, 57.15 mm maple strips,
  a 3.05 m rim, 0.455 m bench seats and a full-size door.
- **Camera:** fixed 46 mm perspective camera (36 mm sensor) at (2.0, −6.15, 1.20) m looking at
  (0, −0.6, 1.0) m, f/16 focused on the ball and contact region; the ball is at least 64 px across.
- **Appearance:** a text-free school practice gym built by
  `appearance/look_basketball_court_bounce.py`.
  - Walls: painted concrete block (one 2.0 × 1.6 m relief tile of 5 × 8 blocks of 400 × 200 mm)
    under a 1.20 m washable dado, with joints, grime near the floor and ball marks in the paint
    response; window openings, a recessed glazed steel door with kick plate and push bar, conduit,
    a waste bin and a green exit sign with a plain white arrow.
  - Floor: sealed maple strips (`floor_surface_model` `strip_maple`) running baseline to baseline,
    each 57.15 mm strip a varied crop of a maple veneer scan, normal tilt 0.00015 rad and a clear
    coat (weight 0.72, roughness 0.12–0.22) with 0.12 mm swells. All court lines are white; the
    free-throw lanes are a stain over the grain. The geometric floor stays at z = 0.
  - Furniture: two empty 2.60 m maple-and-steel benches (four 32 mm seat slats at 455 mm, three
    raked back slats, eight rubber feet at z = 0) and a 630 mm grey HDPE bin with an empty liner,
    all authored in SI units. A broom and a wall clock are imported; their label and dial text are
    replaced in memory by the surrounding surface (all 60 clock ticks kept) and the cleaned copies
    are packed into the saved scene.
  - Backstop and bleachers: the glass board sits on a 50 mm steel frame and two welded truss arms
    (60 mm chords at z = 3.90 m and 3.02 m) anchored to the end wall; nine rows of closed
    telescopic bleachers with steel rails, 212 mm maple risers and 44 mm seat nosings in three 4 m
    sections.
  - Ball: an eight-panel basketball mesh normalized to 0.24 m, normal strength 0.75, roughness
    0.48–0.62, no ink stamp (`ball_print_text` is null). No other ball or orange object is in the
    room.
  - Light: an overcast garden HDRI through the windows (rotation 73°), a low sun (20° elevation,
    35° yaw) whose patch the ball stays inside, and hanging LED high-bays.
- **Render:** Cycles, 128 samples, adaptive threshold 0.008, CPU OIDN denoising, AgX High
  Contrast, 0.25-frame shutter centred on the solver time with three ball motion steps, persistent
  data off. A scene-linear compositor adds glow, vignette and slight dispersion, and deterministic
  per-frame sensor grain is written into each PNG. H.264 CRF 17, yuv420p.

## Physics

- PyBullet 3.2.7, free six-DOF sphere against the fixed floor box; one initialization sets the
  velocity and the loop only advances the solver and reads poses and contacts.
- Fixed step 1/1920 s (80 substeps per frame), 80 solver iterations, split impulse, contact ERP 0,
  restitution velocity threshold 0.08 m/s, poses stored at 480 Hz. Frame i samples t = (i−1)/24 s.
- Restitution: Bullet multiplies the body coefficients, B01 0.76 × F01 1.0 = 0.76 effective. F01
  only normalizes the pair coefficient. Friction 0.70 (ball) and 0.60 (floor), rolling and
  spinning friction 0.001, no air damping. Measured penetration stays below 3 mm.
- The first impact is at 0.553646 s.
- `remove_ball` never creates the PyBullet ball and removes its visual object; all 96
  ground-truth frames declare B01 absent.
- `restitution_at_1s` stores `[{"frame": 25, "params": {"ball_restitution": 0.95}}]` under
  `physics.timed_edits`. The solver runs to t = 1 s (step 1920), changes only restitution with
  `changeDynamics`, records pose and velocity before and after the call, and continues the same
  world.
- PyBullet's `getDynamicsInfo` returns zero in the restitution slot for this body, so the event
  log separates the commanded coefficient from the raw query, and validation measures restitution
  from pre- and post-impact velocities.
- `heavy_ball` is an invariance case: with a fixed floor and no drag, poses and velocities equal
  the source while mass, inertia, impulses and mechanical energy double.

## Measured motion

| Case | Outcome |
| --- | --- |
| `source` | First impact at 0.553646 s; first complete rebound of the ball bottom 0.8674 m; second 0.502265 m |
| `edit_low_restitution` | First complete rebound 0.2156 m |
| `edit_high_restitution` | First complete rebound 1.3562 m |
| `edit_remove_ball` | Empty gym in every frame |
| `edit_heavy_ball` | Same trajectory as the source; impulses and energy doubled |
| `edit_restitution_at_1s` | First rebound unchanged; next impact at 1.3953125 s; second rebound 0.784787 m |

The restitution edits share the source states before the first impact.

## Validation

- Physics validation compares the first contact with analytic free fall and checks gravity
  residuals, multiple impacts, decreasing rebound peaks and energy, shortening contact intervals,
  fixed XY, penetration, measured restitution and actual mass and inertia. Camera bounds and
  projected contact points are checked at every frame.
- Video verification probes size, fps, frame count and duration and decodes the whole MP4.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Ball 0.625 kg released from rest, effective restitution 0.76 |
| `edit_heavy_ball` | `SET B01.mass TIMES 2` | `physics.ball.mass_kg` 0.625 → 1.25 kg, inertia doubled |
| `edit_high_restitution` | `SET B01.restitution TIMES 1.25` | `physics.ball.restitution` 0.76 → 0.95 |
| `edit_low_restitution` | `SET B01.restitution TIMES 0.5` | `physics.ball.restitution` 0.76 → 0.38 |
| `edit_remove_ball` | `DELETE B01` | `physics.ball.present` true → false; no mesh, collider, contact, shadow or reflection |
| `edit_restitution_at_1s` | `SET B01.restitution TIMES 1.25 AT FRAME 25` | Restitution 0.76 → 0.95 from frame 25 (t = 1.000 s) |

The builder's case IDs drop the `edit_` prefix (`low_restitution`, `high_restitution`,
`remove_ball`, `heavy_ball`, `restitution_at_1s`); `scene_manifest.json` records the mapping.
`edit_vocab.py` declares the DSL and the builder derives edit prompts with
`pcve_edit_dsl.make_prompts`; the source prompts are written in
`build_pcve_basketball_court_bounce.py`. All edits keep the source geometry, camera, lighting,
materials, numerical settings and render quality.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `innerscene/basketball` | url, derived | Ball mesh and panel cover |
| `bowling_documentary/white_maple_veneer` | url, derived | Floor strips and bleacher risers |
| `polyhaven/oak_veneer_01` | url, derived | Bleacher wood |
| `polyhaven/concrete_block_wall` | url | Wall relief |
| `polyhaven/residential_garden` | url | Exterior HDRI through the windows |
| `polyhaven/plastic_broom` | url | Broom prop |
| `polyhaven/wall_clock` | url | Wall clock prop |

```bash
python3 scripts/download_assets.py --scene basketball_court_bounce
python3 scripts/download_assets.py --scene basketball_court_bounce --check
```

`PCVE_ASSETS_DIR` selects another asset root. Every saved `.blend` packs its images.

## Requirements

- Python environment `.venv-domino/` at the repository root with `pybullet==3.2.7`,
  `numpy==1.26.4` and `Pillow==11.3.0` (`requirements.txt`).
- Blender 4.3.2 (`tools/blender-4.3.2-linux-x64/blender`).
- Physics runs on a CPU. Rendering defaults to `--device cpu`; `--device gpu` together with the
  unified `--gpu` option renders on an explicitly chosen idle GPU. `ffmpeg` is needed for encoding.

## Commands

Run from the repository root. Changed inputs need a fresh output root.

```bash
.venv-domino/bin/python scripts/rigid_rigid/basketball_court_bounce/build_pcve_basketball_court_bounce.py --list-cases
python3 scripts/rigid_rigid/basketball_court_bounce/build_pcve_basketball_court_bounce.py \
  --out-root renders/basketball_court_bounce/run --dry-run

# physics, eight preview frames, then the full render of all six cases
.venv-domino/bin/python scripts/rigid_rigid/basketball_court_bounce/build_pcve_basketball_court_bounce.py \
  --out-root renders/basketball_court_bounce/run --stage simulate --threads-native 32 --device cpu
.venv-domino/bin/python scripts/rigid_rigid/basketball_court_bounce/build_pcve_basketball_court_bounce.py \
  --out-root renders/basketball_court_bounce/run --stage preview --threads-native 32 --device cpu \
  --blender tools/blender-4.3.2-linux-x64/blender
.venv-domino/bin/python scripts/rigid_rigid/basketball_court_bounce/build_pcve_basketball_court_bounce.py \
  --out-root renders/basketball_court_bounce/run --stage render --threads-native 32 --device cpu \
  --blender tools/blender-4.3.2-linux-x64/blender --skip-existing
.venv-domino/bin/python scripts/rigid_rigid/basketball_court_bounce/build_pcve_basketball_court_bounce.py \
  --out-root renders/basketball_court_bounce/run --stage verify
```

`--stage all` runs simulation, full rendering, encoding and technical verification. `preview`
renders eight representative frames at the full pixel size, samples and materials, and
`render --skip-existing` reuses them. `--cases` selects a subset (`--cases source` for the source
only). `--config-json` merges explicit inputs into the four configuration groups.
`--reuse-physics-json <source physics_transforms.json>` reuses an accepted source trajectory with
matching inputs and frame times; edits are always solved. `tools/assemble_split_render.py
--case-dir <case> --worker-dirs <dir> ...` combines native frames rendered by separate workers
(render entry `--mode frames --keyframes ...`), checks that every worker built the same scene and
encodes with the render entry's ffmpeg settings.

## Outputs

`<out-root>/cases/<case>/` contains `video.mp4`, the packed `basketball_court_bounce.blend`, all
96 PNG frames, `physics_transforms.json`, `trajectory.csv`, `contacts.json`,
`ground_truth_transforms.json`, settings, prompts, physics and video validations, the scale ledger
and render timing reports; edits also contain `physics_diff.json` and `scenario_overrides.json`.
The suite and implementation manifests record each case, its DSL and prompts, effective inputs
and runtime. The published suite is
`renders/pcve_suites/pcve_basketball_court_bounce_suite/`; do not use it as an output root.

## Code layout

- `build_pcve_basketball_court_bounce.py`: suite builder with stages, source prompts and manifests.
- `simulate_basketball_court_bounce.py`: PyBullet solve of one case.
- `render_basketball_court_bounce.py`: Blender preparation, frames, animation and encoding.
- `scene_config.py`: physics, simulation quality, appearance (preset `gym_look`) and render inputs.
- `edit_vocab.py`: DSL vocabulary and the five edits.
- `physics/validate_basketball_court_bounce.py`: physics acceptance checks.
- `appearance/look_basketball_court_bounce.py`: gym, ball, lighting and camera response, built in
  layers; helpers suffixed with a layer name are the lower layers the final `gym()`,
  `build_ball()`, `lighting()` and `camera_response()` build on.
- `tools/assemble_split_render.py`: assembles frames rendered by separate workers.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry-point description, scene
  manifest and Python requirements.

## Limitations

- The ball is a rigid approximation of an inflated basketball; compression, pressure dynamics and
  sound are not modelled, and the scene is not calibrated against measured bounces. A real ball is
  in contact for about 10 ms, under a third of a frame interval.
- The floor coefficient of 1.0 is a pair normalization, not the restitution of an isolated wooden
  floor.
- The pebbled rubber and dark channels of the ball are shader detail; the collision sphere is a
  separate representation.
