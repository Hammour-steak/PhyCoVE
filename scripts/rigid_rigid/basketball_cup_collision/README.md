# basketball_cup_collision

A rigid–rigid scene in PhyCoVE. In a studio apartment a metal insulated bottle stands on a desk;
a basketball thrown flat from the near side of the room hits it and knocks it over, and the
toppled bottle slides across the desk on its side until it stops at the foot of the wall behind
the desk. PyBullet solves the contacts and Blender replays the solved poses. The source video is
4 s, 24 fps, 96 frames, 1280×720.

## Scene

- **Units and axes:** SI, Z up, gravity 9.81 m/s².
- **Desk:** analytic box collider, top 0.80 × 1.44 m at z = 0.80 m, centred at (2.09, −0.53).
  The rendered desk (`appearance/studio_room.py`) is built on this box: its top face and the four
  edges of the top are the collider's, so where the ball rolls off the edge matches the picture.
- **Wall behind the desk:** a solid collider from the floor to 2.46 m whose x = 2.50 face is the
  studio's east wall; the desk stands flush against it.
- **Other static colliders** (`scene_geometry.SAFETY_WALLS` and `ROOM_PROPS`, created in table
  order): a flat carton (0.64 × 0.62 × 0.18 m), a coffee table, four safety walls whose inner faces
  are the west, south and north walls (x = −2.90, y = −3.385, y = 2.56), and five furniture boxes
  (bed, pillow, vent column, sofa, chair) that no case touches and that have no visible
  counterpart.
- **Bottle:** `models/water_bottle__plastic_bottle.glb` scaled to 22 cm, 0.45 kg (an empty
  stainless insulated bottle of this size). Its baked mesh is exported as a convex-hull collider
  with centre of mass and inertia (`assets/scenes/basketball_cup_collision/bottle_collision.json`, checked
  against the model's sha256), so look and physics share one geometry. It stands at x = 1.84,
  0.65 m from the wall, far enough to fall over completely before it reaches the wall.
- **Basketball:** `models/basketball.glb` scaled to radius 0.12 m, 0.62 kg. Ball and bottle use
  swept-sphere CCD, so fast edits do not tunnel.
- **Throw:** from (0.55, −0.53, 1.06) m along the desk's long axis, flat at chest height (the
  low-arc ballistic solution of `scene_geometry.throw_velocity` aimed at a fixed target), 5.2 m/s,
  with backspin about the horizontal axis perpendicular to the flight. It hits the bottle at
  0.22 s. Speed edits aim at the same target, so they do not lob the ball over the bottle.
- **Camera:** 16 mm lens at (−0.6, −3.0, 2.2) m looking at (1.9, −0.3, 0.45) m; every moving body
  stays inside a 2 % safe margin in all cases (smallest 0.040, `edit_heavy_bottle`), and the
  coffee-table corner the ball reaches in that case is in frame.
- **Room:** a ground-floor studio in afternoon sun, built on the simulator's planes: plastered
  east wall on the solid wall's face, the other walls on the safety-wall faces, floor at z = 0;
  an oak-veneer desk top on a black steel-tube frame built to the collider's size; a kraft carton
  with sealing tape on the `carton` box; a coffee table model on the `coffee_table` box.
- **Decor (not simulated):** a leather sofa under the north window, steel-and-wood shelves (the
  source model is scaled by 0.1 to 1.10 × 0.50 × 2.14 m), a desk lamp, a metal jug, a carved
  wooden elephant, a standing picture frame, laminate floor (2 m tile), a bouclé rug, sheer
  curtains (weave only), a white panel radiator, an abstract painting without text and sockets.
- **Light:** outdoor sources only: a sun lamp at 29.5° elevation and a physical sky through real
  window openings in the east and north walls, each with a portal; thin glass with a back-face
  IOR correction; a street HDRI seen through the windows by camera rays only, rotated so its sun
  matches the lamp's azimuth. AgX Base Contrast, exposure +1.5.
- **Moving-body looks:** at render time the bottle's printed artwork is replaced by a
  powder-coated steel material (cap and chrome ring kept); the basketball's logo and maker
  lettering are replaced in the shader by samples of the same leather shifted aside or of the
  neighbouring panel (colour, roughness and normal together); the ball mesh is subdivided and its
  vertices put back on the 0.12 m sphere, so its silhouette is the collision sphere.
- **Render:** Cycles, OIDN denoising, 0.25-frame motion blur with persistent data off. Full
  renders use 1280×720 and 256 samples; the builder defaults are 960×540 and 48 samples.

## Physics

- PyBullet in DIRECT mode at 1440 Hz (60 steps per frame), 120 solver iterations, restitution
  velocity threshold 0.015 m/s, contact breaking threshold 0.2 mm, deterministic overlapping
  pairs. The bottle settles for 240 steps before the ball is created. Frame i is the state at
  t = (i−1)/24 s.
- Friction: floor and desk 0.8, safety walls 0.5, other static boxes 0.6, ball 0.5 (spinning
  0.002, angular damping 0.01), bottle 0.4 (spinning 0.001, angular damping 0.35).
- Restitution: PyBullet multiplies the two bodies' values, so each body value is chosen for the
  pairs it forms. The effective values are written to `solver.effective_restitution` in the cache.

  | Body | Restitution | Effective pairs |
  | --- | --- | --- |
  | basketball | 0.90 | ball–desk 0.72, ball–wall 0.765, ball–floor 0.765 |
  | bottle | 0.50 | ball–bottle 0.45, bottle–desk 0.40, bottle–wall 0.425, bottle–floor 0.425 |
  | desk top | 0.80 | — |
  | floor, walls | 0.85 | — |
  | other static boxes | 0.30 | ball–box 0.27 |

  The bottle is a thin-walled shell that loses most of its normal velocity to vibration, so its
  pairs sit near 0.40. With 0.70 (the value for a solid block), the bottle in `edit_fast_ball`
  would rebound from the wall at 6 m/s and swing back through upright within one frame; with
  0.50 it rebounds at 4.2 m/s, tumbles through 172° and settles on its side.
- Rolling resistance: Bullet's `rollingFriction` is a torsional constraint at the contact, not a
  drag, and can hold a resting body at a tilt. Measured on the bottle hull over 2 s (start tilt →
  end tilt, degrees):

  | rollingFriction | 5 | 10 | 20 | 30 | 46 | lying bottle |
  | --- | --- | --- | --- | --- | --- | --- |
  | 0.06 | 5 | 10 | 20 | 30 | 90 | stops at once |
  | 0.0018 | 0 | 1 | 20 | 90 | 90 | stops in < 1.5 s |
  | 0.0015 (used) | 0 | 0 | 8 | 90 | 90 | stops in < 1.5 s |
  | 0 | 2 | 2 | 11 | 90 | 90 | still rolling after 2 s |

  The critical angle is atan(r/com) = 20.6°. The bottle and the ball both use 0.0015; the rest of
  the bottle's rolling resistance comes from its angular damping. On the ball, 0.0015 gives a
  rolling deceleration of about 0.15 m/s² and keeps its spin after the first landing on the desk.
- The timed gravity edit changes the gravity of the live world at its start frame.

## Measured motion

- In every case the bottle is knocked over, slides to the foot of the wall and stays on the desk.
- `source`: first contact at 0.22 s (frame 6.3); the bottle slides about 0.6 m on its side and
  stops at the wall; the ball follows and comes to rest at the wall; the bottle is flat by frame 18.
- `edit_fast_ball`: the bottle reaches the wall at about 10 m/s and tumbles through 172°; the ball
  lands elsewhere on the floor.
- `edit_heavy_bottle`: the ball bounces back to the floor and rolls about 2 m into the coffee
  table (smallest decor clearance across the cases, 0.043 m).
- `edit_heavy_ball`: the ball rolls slowly to the south-west corner of the desk, drops off at
  2.5 s and is still rolling at the end.
- `edit_heavy_gravity_after_impact`: the bottle is flat by frame 13.
- Two runs with PyBullet 3.2.7 on Linux are byte-identical.

## Validation

- The simulator marks a run invalid when penetration reaches 1.2 cm.
- `physics/validate_basketball_cup_collision.py` checks a cache before rendering: the simulation
  signature (hash of the scenario and of the scene and shared code, so a cache from changed code
  must be re-solved), the frame clock, the frame count and per-frame presence.
- The renderer checks, for every frame plus four interpolated steps between frames, that every
  moving body keeps at least 2 cm from every decor bounding box and that camera rays to the ball
  and bottle centres are not blocked by decor; it fails instead of rendering otherwise.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Ball 0.62 kg thrown at 5.2 m/s, bottle 0.45 kg, gravity 9.81 m/s² |
| `edit_fast_ball` | `SET basketball.initial_velocity TIMES 3` | Throw speed 5.2 → 15.6 m/s |
| `edit_heavy_ball` | `SET basketball.mass TIMES 5` | Ball mass 0.62 → 3.1 kg |
| `edit_heavy_bottle` | `SET bottle.mass TIMES 10` | Bottle mass 0.45 → 4.5 kg |
| `edit_heavy_gravity_after_impact` | `SET world.gravity TIMES 5 AT FRAME 8` | Gravity 9.81 → 49.05 m/s² from frame 8 (t = 0.292 s), after the first contact |
| `edit_delete_bottle` | `DELETE bottle` | Green water bottle removed from frame 1 |
| `edit_delete_basketball` | `DELETE basketball` | Basketball removed from frame 1 |

The builder calls the source case `basketball_cup_collision_baseline`; the edit IDs are the same
as the published case names. `edit_vocab.py` declares the DSL vocabulary and the case list.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `models` (`basketball.glb`, `water_bottle__plastic_bottle.glb`) | manual | Basketball and bottle models |
| `scenes/basketball_cup_collision` | derived | `assets/scenes/basketball_cup_collision/bottle_collision.json`: bottle hull, centre of mass and inertia |
| `polyhaven/basketball_cup_collision` | url | Furniture and decor models, floor, rug, curtain and veneer textures, street HDRI |

```bash
python3 scripts/download_assets.py --scene basketball_cup_collision
python3 scripts/download_assets.py --scene basketball_cup_collision --check
```

`PCVE_ASSETS_DIR` selects another asset root.

## Requirements

- Python environment `.venv-domino/` at the repository root with `pybullet==3.2.7`
  (`requirements.txt`).
- Blender 4.3.2 (`tools/blender-4.3.2-linux-x64/blender`, or `$BLENDER`, `blender` on `PATH`,
  `~/.local/opt/blender-*`).
- Physics runs on a CPU; rendering runs on CPU or a CUDA GPU (`--device auto`).

## Commands

Run from the repository root.

```bash
.venv-domino/bin/python scripts/rigid_rigid/basketball_cup_collision/build_pcve_basketball_cup_collision.py --list-cases

# physics for all five cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/basketball_cup_collision/build_pcve_basketball_cup_collision.py \
  --out-root renders/basketball_cup_collision/run --simulate-only

# all 96 frames of every case
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/basketball_cup_collision/build_pcve_basketball_cup_collision.py \
  --out-root renders/basketball_cup_collision/run --mode animation --resolution 1280 720 --samples 256 \
  --blender tools/blender-4.3.2-linux-x64/blender

# one case: solve, then render keyframes from the cache
.venv-domino/bin/python scripts/rigid_rigid/basketball_cup_collision/simulate_basketball_cup_collision.py \
  --out renders/basketball_cup_collision/single/physics_transforms.json
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
  --python scripts/rigid_rigid/basketball_cup_collision/render_basketball_cup_collision.py -- \
  --physics-json renders/basketball_cup_collision/single/physics_transforms.json \
  --out-dir renders/basketball_cup_collision/single --mode keyframes --resolution 640 360 --samples 16
```

The builder's `--mode` is `keyframes` (default), `preview`, `build` or `animation`; `--cases`
builds a subset and `--render-only` reuses existing physics caches. `tools/render_queue.py`
(workflow `batch_render`) samples throw speeds within `PHYSICS_LIMITS` and runs the builder once
per sample (`--count`, `--seed`, `--out-root`, `--simulate-only`).

## Outputs

Without `--out-root` the builder writes to
`renders/basketball_cup_collision/suite_build/pcve_basketball_cup_collision_suite/`. Each case
folder `cases/<case>/` receives the scenario input and overrides, `prompts.json`,
`physics_transforms.json`, `simulation_metrics.json`, and after rendering the frames or
`video.mp4`, `ground_truth_transforms.json`, `scenario_metadata.json` and
`render_validation.json`. The suite root holds `suite_manifest.json`. The published suite is
`renders/pcve_suites/pcve_basketball_cup_collision_suite/`; do not use it as an output root.

## Code layout

- `build_pcve_basketball_cup_collision.py`: suite builder (cases, prompts, render calls, manifest).
- `simulate_basketball_cup_collision.py`: PyBullet solve, restitution and rolling-friction
  settings, timed gravity.
- `render_basketball_cup_collision.py`: Blender replay, clearance and sightline checks, render.
- `scene_config.py`: physics limits, camera and render defaults, scenario loading and validation.
- `edit_vocab.py`: DSL vocabulary and the case list.
- `physics/scene_geometry.py`: desk, wall, prop and bottle geometry and the aimed throw.
- `physics/validate_basketball_cup_collision.py`: simulation signature and cache checks.
- `appearance/look_basketball_cup_collision.py`: ball and bottle looks, logo patches, exposure.
- `appearance/studio_room.py`: studio room, desk, carton, coffee table, decor and daylight.
- `tools/render_queue.py`: random batch over throw speeds.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry-point description, scene
  manifest and Python requirements.

## Limitations

- The bottle is a rigid convex hull; shell vibration is represented only through its low
  restitution.
- The five furniture colliders (bed, pillow, vent column, sofa, chair) have no visible
  counterpart; no case touches them.
- Decor is visual only and is kept clear of the moving bodies by the clearance check.
- The bottle model is shared with `office_desk_kettle_tip`.
