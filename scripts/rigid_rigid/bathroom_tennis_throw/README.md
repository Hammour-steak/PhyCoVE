# bathroom_tennis_throw

A rigid–rigid scene in PhyCoVE. In a bathroom a tennis ball is thrown hard from beside the camera:
it hits the west face of the shower's glass screen at chest height (z ≈ 1.31 m), rebounds into the
south wall 1.2 m up, bounces off the floor, and hits the east face of a low cabinet while still
rising (z ≈ 0.30 m), then bounces three more times and rolls to rest. PyBullet solves every
contact and Blender replays the solved poses. The source video is 4 s, 24 fps, 96 frames,
1280×720.

## Scene

- **Units and axes:** SI, Z up, in the world frame of `assets/models/big_project.glb`; the floor
  top is z = 0.042 m (`physics/scene_geometry.py::FLOOR_Z`). The model is built at about twice
  real size (shower glass 4.07 m, ceiling 5.9 m) and the physics runs at that scale.
- **Ball:** radius 0.050 m (10 cm across, about 1.5× a standard tennis ball, so it reads at
  7–40 px), mass 0.058 kg, rolling friction 0.003. It starts at (−1.60, −1.60, 0.95), aimed at
  (4.55, −4.50, 0.95) with 13° elevation at 14.0 m/s. `aim_shift` moves the throw line sideways.
- **Static colliders (20):** 13 fixtures, 4 walls and 3 skirting runs, exported by
  `tools/export_bathroom_colliders.py` from the model to
  `assets/scenes/bathroom_tennis_throw/bathroom_colliders.json` (with a model sha256 check).
  - Fixtures: the low cabinet (collider name `toilet_bowl`, model object `Cube.030/031`, a
    1.20 × 1.40 × 1.11 m box; the ball hits its +x east face), the west vanity unit and upstand,
    two poufs, the sliding glass door (`Cube.025 + Cube.014`, the two 3 cm leaves merged into one
    6.4 cm box), the south glass screen (`Cube.026 + Cube.019`), the two floor rails of the glass
    frame (faces at x 4.6436 and y −1.9155), the east bathtub, the shower stone bench, the
    south-east washbasin and the second north-wall counter.
  - Walls: inner faces are the mode of 120 probe rays (south −4.770, north +4.493,
    east +10.950); there is no visible wall to the west, and a synthetic wall is kept there as a
    backstop.
  - Skirting `Cube.047`: a marble base 45 mm proud of the wall up to z = 0.243, ray-measured
    (south −4.725, north +4.447, east +10.856); each box extends from the measured face back into
    the wall.
  - Shower base: an inner floor box at the measured basin floor (z = 0.0538) plus four stone-rim
    boxes (rim widths west 260, east 135, south 80, north 260 mm), thickened down to z = −0.05.
  - Floor box: x −8.60..11.66, y −5.23..4.72, reaching the west wall's collider face.
- **Stools (rigid bodies):** `stool_a` at (6.50, −2.37) on the recessed shower floor (set
  dressing that the chain never reaches) and `stool_b` at (2.20, −1.90) on the main floor.
  Axis-aligned boxes sized to the source meshes: 0.362 × 0.213 × 0.11 and
  0.326 × 0.274 × 0.11 m half extents, 2.5 kg each. A 58 g ball moves a 2.5 kg stool by less than
  0.1 mm.
- **Camera:** (−2.9, 0.2, 2.05) looking south-east at (2.6, −3.9, 0.30), 24 mm lens. Every case is
  in frame throughout (worst margin 0.091, `edit_aim_north`).
- **Setting:** a Nordic family bathroom on a spring morning, built at 2× scale
  (`appearance/bathroom_room.py::K = 2`) so it reads as an ordinary-sized room. The model's room
  meshes are not drawn: every surface the ball can touch is a box face from
  `assets/scenes/bathroom_tennis_throw/bathroom_colliders.json`.

  | collider | what is in the picture |
  | --- | --- |
  | `wall_*`, `skirting_*` | white 15 cm glazed wall tiles with tiled skirting, split at window openings with real reveals |
  | floor, `shower_base`, `shower_rim_*` | light-grey hexagonal floor tile, shower tray floor, light stone kerbs |
  | `glass_screen_south` | a fixed glass panel and the sliding panel parked behind it; their outer faces are the collider's west and east faces |
  | `glass_shower_door` | two sliding leaves; the inner leaf's south face is the collider's south face |
  | `basin_southeast` | a tiled shower bench with stone top |
  | `toilet_bowl` | a white-oak low cabinet; the east side panel is a single floor-standing board on the collision face; push-to-open doors without knobs |
  | `pouf_left`, `pouf_right` | two grey felt storage baskets of rolled towels; the second basket is `pouf_right` minus the 14 cm overlap, so both west faces are real faces |
  | `stool_a` | an oiled-oak shower foot rest |
  | `stool_b` | a light felt tray with folded washcloths |

- **Props not in the simulation:** freestanding bathtub and filler, wall-hung basin and round
  mirror, a potted plant, towels, bath mat, shower fittings, downlights, window frames and sills.
- **Materials:** wall tiles, floor tiles, stone and ceiling are procedural (per-tile tilt and
  colour variation, rounded glazed edges, grout, floor mottling); white oak, cotton towels and
  felt use scanned textures.
- **Light:** outdoor light only: a warm sun lamp (azimuth 128°, elevation 31°) and a Nishita sky
  through three wooden windows with thin glass (back-face IOR correction, transparent to shadow
  rays) and a portal in each opening; the view outside is an HDRI visible only to camera rays,
  turned to the sun's azimuth. Indoor lamps are off. AgX Medium High Contrast, exposure +0.85.
- **Ball appearance:** fluorescent yellow-green (linear (0.45, 0.78, 0.02)) with the white seams
  taken from the ball model's felt texture, sheen and a fibre bump, and an emission of 0.18 in the
  same tint for the fluorescent dye.
- **Render:** Blender 4.3.2 Cycles, 256 samples for the source video and edits, OIDN, 32
  transparent bounces, caustics off, 0.25-frame motion blur with persistent data off
  (`--no-motion-blur` turns it off).

## Physics

- **Solver:** PyBullet 3.2.7 at 4320 Hz with a 400-step pre-roll that settles the stools before
  frame 1. Frame i is the state at t = (i−1)/24 s. At 4320 Hz the head-on hit on the thin glass
  leaves at most 0.86 mm of penetration (limit 4 mm); the step size, not the CCD radius, sets
  this.
- **Restitution:** ball 0.60, stools 0.40, fixtures 0.63; Bullet multiplies the pair, so the ball
  on a fixture has an effective restitution of 0.378. Gravity −9.81 m/s².
- **Timed edit:** a `timed_edits` schedule writes the new gravity into the running world at the
  frame boundary; frames before the start frame match the source.
- **Spawn check:** `quality.spawn_overlap_m` measures how deep any body starts inside a static
  collider; more than 1 mm makes the run invalid and `validate_cache` raises.

## Measured motion

| Case | Measured outcome |
| --- | --- |
| `source` | glass screen at 0.493 s ((4.483, −4.469, z 1.310), normal −x); south wall at 0.556 s (z 1.240, no floor contact in between); floor at 0.951 s ((2.286, −4.072), vz +2.2 m/s); cabinet east face at 1.100 s ((1.771, −3.868, z 0.295), still rising); apex 0.338 m, bounces at 1.46, 1.62 and 1.67 s; rests at (2.77, −0.63) |
| `edit_slow_ball` | does not reach the glass; lands at 0.61 s, bounces twice, rolls up to the glass screen (1.17 s, z 0.20, speed 5.66 → 1.98 m/s) and rolls back to rest at (2.62, −4.15); hits neither the south wall nor the cabinet |
| `edit_aim_south` | glass hit point 0.22 m further south, cabinet hit further north (z 0.289) |
| `edit_aim_north` | hits the glass further north at 0.457 s, rebounds off the south wall straight to the floor, hits the cabinet's east face in the air and stops at (2.87, −0.15) |
| `edit_bouncier_bathroom` | bounces between the glass screen, bathtub and glass door inside the shower area and ends at (5.33, −3.77), still moving at 2.81 m/s; only 1 of the 96 frames is on the floor |
| `edit_heavy_gravity_after_impact` | identical to the source up to the glass hit; with 3× gravity the ball hits `stool_b` at 2.93 s |

Two runs of all cases with PyBullet 3.2.7 on Linux are identical.

## Validation

- The render checks every case before rendering: for the ball centre on every frame (with 8
  sub-samples between frames) a BVH measures the closest distance to every prop and any frame under
  2 cm fails; rays from the camera to the ball centre and four edge points fail if a prop hides the
  ball (`check_clearance`, `check_occlusion` in `appearance/look_bathroom_tennis_throw.py`). All
  cases pass; the closest is 2.9 cm (the screen-edge profile in `edit_aim_south`).
- The renderer raises `Object behind camera` for the whole case if any frame has a body behind the
  camera plane.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source throw |
| `edit_slow_ball` | `SET tennis_ball.initial_velocity TIMES 0.5` | Throw speed 14 → 7 m/s |
| `edit_aim_south` | `SET tennis_ball.aim_shift TO 0.2` | Throw line shifted 0.2 m south |
| `edit_aim_north` | `SET tennis_ball.aim_shift TO -1.05` | Throw line shifted 1.05 m north |
| `edit_bouncier_bathroom` | `SET world.restitution TIMES 1.5` | All restitutions ×1.5: ball 0.60 → 0.90, stools 0.40 → 0.60, fixtures 0.63 → 0.945 |
| `edit_heavy_gravity_after_impact` | `SET world.gravity TIMES 3 AT FRAME 13` | Gravity −9.81 → −29.43 m/s² from frame 13 (t = 0.5 s), right after the glass hit |

The builder names the source case `bathroom_tennis_throw_baseline`; the edit IDs are the same as
the published case names.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `models` (`big_project.glb`, `tennis_ball.glb`) | manual | collider source for the room (hash-checked); ball mesh and felt texture |
| `polyhaven/bathroom_tennis_throw` | url | white oak, towel cotton and felt textures, the plant and clay pot models, the window-view HDRI |
| `scenes/bathroom_tennis_throw` | derived | `assets/scenes/bathroom_tennis_throw/bathroom_colliders.json`, the exported static colliders |

```bash
python3 scripts/download_assets.py --scene bathroom_tennis_throw
python3 scripts/download_assets.py --scene bathroom_tennis_throw --check
```

## Requirements

- Python with `pybullet==3.2.7` (`requirements.txt`); the repository's `.venv-domino/`
  environment has it. The builder runs the physics in-process.
- Blender 4.3.2 for rendering and for the collider export (`--blender`, or `--render-python` with
  the `bpy` module).
- A GPU is optional (`--device auto` or `cpu`).

## Commands

Run from the repository root.

```bash
# case list
python3 scripts/rigid_rigid/bathroom_tennis_throw/build_pcve_bathroom_tennis_throw.py --list-cases

# physics for the source
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/bathroom_tennis_throw/build_pcve_bathroom_tennis_throw.py \
  --out-root renders/bathroom_tennis_throw/new_run --simulate-only \
  --cases bathroom_tennis_throw_baseline

# physics and keyframes for all six cases
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/bathroom_tennis_throw/build_pcve_bathroom_tennis_throw.py \
  --out-root renders/bathroom_tennis_throw/new_run --mode keyframes \
  --blender tools/blender-4.3.2-linux-x64/blender

# all 96 frames of one solved case, then encode
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
  --python scripts/rigid_rigid/bathroom_tennis_throw/render_bathroom_tennis_throw.py -- \
  --physics-json renders/bathroom_tennis_throw/new_run/cases/bathroom_tennis_throw_baseline/physics_transforms.json \
  --out-dir renders/bathroom_tennis_throw/frames/source \
  --mode keyframes --keyframes $(seq -s ' ' 1 96) --samples 256 --resolution 1280 720
ffmpeg -framerate 24 -i renders/bathroom_tennis_throw/frames/source/frame_%04d.png \
  -c:v libx264 -preset medium -crf 20 -bf 0 -g 18 -keyint_min 1 -profile:v high -pix_fmt yuv420p \
  renders/bathroom_tennis_throw/frames/source.mp4

# re-export the static colliders after changing the room model or the wall measurement
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
  --python scripts/rigid_rigid/bathroom_tennis_throw/tools/export_bathroom_colliders.py
```

- Builder `--mode` is `keyframes` (default), `preview`, `animation` or `build`; `--cases` builds a
  subset; `--render-only` renders from existing caches.
- `tools/render_queue.py` (workflow `batch_render`) samples randomised throw speeds and stool
  masses and runs the builder once per sample (`--count`, `--seed`, `--out-root`,
  `--simulate-only`). Workflow `asset_export` is `tools/export_bathroom_colliders.py`.
- `tools/search_flight.py` is the sharded grid search over
  throw parameters (`--shard`, `--nshards`, `--out`; Python with pybullet). The flight criteria
  are glass hit ≥ 0.9 m, wall hit ≥ 0.55 m, airborne window ≥ 0.15 s, airborne apex ≥ 0.30 m and
  cabinet hit ≥ 0.25 m.

## Outputs

- A build writes `cases/<case>/` under `--out-root` (default
  `renders/bathroom_tennis_throw/suite_build/pcve_bathroom_tennis_throw_suite`) with
  `physics_transforms.json`, metrics, and after rendering the frames or video, render validation
  and the packed scene, plus the suite manifest. `tools/render_queue.py` writes to
  `renders/bathroom_tennis_batch` by default.
- The published suite is `renders/pcve_suites/pcve_bathroom_tennis_throw_suite/`; do not use it
  as an output root.

## Code layout

- `simulate_bathroom_tennis_throw.py` — PyBullet solve of one case, including the spawn-overlap check (public entry).
- `render_bathroom_tennis_throw.py` — Blender replay, prop checks and render (public entry).
- `build_pcve_bathroom_tennis_throw.py` — source and edit suite builder (public entry).
- `scene_config.py` — editable physics, camera and render defaults; scenario validation.
- `edit_vocab.py` — edit DSL vocabulary and case list.
- `physics/scene_geometry.py` — ball, stools, launch, floor and shower-base geometry; solver rate.
- `physics/bathroom_colliders.py` — loads `assets/scenes/bathroom_tennis_throw/bathroom_colliders.json` and checks the model hash.
- `physics/validate_bathroom_tennis_throw.py` — simulation signature and cache validation.
- `appearance/bathroom_room.py` — the room rebuilt on the collider faces at 2× scale.
- `appearance/look_bathroom_tennis_throw.py` — ball, stools and props, clearance and occlusion checks.
- `tools/export_bathroom_colliders.py` — exports the static colliders from the room model (Blender).
- `tools/render_queue.py` — randomised batch throws (workflow `batch_render`).
- `tools/search_flight.py` — throw-parameter grid search.
- `requirements.txt`, `entrypoints.json`, `scene_manifest.json` — dependencies and entry metadata.

## Limitations

- The cabinet hit happens on the far side of the cabinet from the camera, so the ball centre is
  behind the cabinet's silhouette for several frames: source 11 (frames 21–31), `edit_aim_north`
  15, `edit_aim_south` 9, `edit_bouncier_bathroom` 3, `edit_slow_ball` 19, gravity ×3 13.
- The ball is 1.5× the size of a standard tennis ball and keeps the real mass; at the picture's
  2× reading scale it looks about 5 cm across, and with real gravity at 2× scale falls and bounces
  look about 0.7× slow.
- The cabinet, washbasins, bathtub and glass door are axis-aligned boxes, not exact outlines. The
  colliders `vanity_counter`, `vanity_backsplash`, `bathtub_east` and `north_counter` are never
  touched in the cases and are not drawn as boxes.
- Throw speeds above about ×1.35 carry the ball behind the camera plane, and the renderer rejects
  such a case.
- The cabinet hit after the floor bounce is at most about 0.30 m high with an effective
  restitution of 0.378.
