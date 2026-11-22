# bathroom_stool_rebound

A rigid–rigid scene in PhyCoVE. In a spa bathroom at dusk a wooden stool is thrown towards the
washbasin with a little spin, hits the vanity, touches the floor and rebounds towards the marble
bathtub on the east side, then tumbles to rest on the floor. PyBullet solves every contact and
Blender replays the solved poses. The source video is 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- **Room:** `assets/models/big_project.glb` (vanity with basin and mirror, bathtub, walls, shower
  glass, decor). The render keeps its geometry and positions and replaces materials, light and
  dressing. The model is built at twice real size (counter top 1.81 m, shower glass 4.07 m, stool
  seat top 1.37 m); physics runs at the model's scale.
- **Stool:** the smaller, upper stool of the pair stacked beside the bathtub (assembly node
  `Cube.045`): a 0.92 × 1.05 × 0.10 m seat board and three splayed black cylindrical legs
  (r = 0.04 m, 1.30 m long), seat top 1.37 m above the floor, mass 10.35 kg. The render deletes
  the larger stool under it (`Cube.046`) and the cup and saucer on top. The rigid body's origin is
  the seat centre; the render hangs the `Cube.045` assembly under an empty at that origin and
  replays the poses on it (a rest-pose drift guard checks the rigging).
- **Initial state:** the stool starts in the air with its seat centre at (0.55, 0.75, 2.20), feet
  0.878 m above the floor when upright. On frame 1 it gets a launch velocity of 6.0 m/s along
  (0.75, 0.55, 0.18) and a spin of 2.6 rad/s about (0.18, −0.95, 0.26).
- **Camera:** at (−1.2, −4.5, 3.6) looking towards (2.2, 1.9, 0.5), 18 mm lens. Every case stays in
  frame; the tightest frame is `edit_fast_throw` frame 20 (normalised margin 0.035), the other
  cases are at 0.247–0.528.
- **Setting:** a hotel/spa bathroom at dusk. Outside the window a distant lake and hills in the
  evening light; inside, the room is lit by its own fittings. Textures and props are laid at
  `WORLD_SCALE = 2.0` so the picture reads at normal proportions.
- **Surfaces of the colliders:** the bathtub, vanity, counter, mirror, walls and chamfered alcove
  keep the model's geometry and only change material. The model's floor (2.4 m tiles with deep
  grooves) is hidden and replaced by a slab whose top face is exactly at the physics floor height
  `FLOOR_Z = 0.042 m`.
- **Materials:** walls of large limestone slabs, floor and splashback of honed travertine, oiled
  walnut vanity, oiled teak stool seat, black bronze stool legs, warm white solid-surface bathtub
  and counter, satin brass fittings, dark bronze shower and window frames; scanned textures are
  box-projected in world coordinates.
- **Window:** a real opening in the north wall left of the basin (x −3.45…−1.45 m,
  z 2.40…5.30 m), the one stretch of visible wall that no case's stool reaches (trajectories stay
  at x ≥ −0.22 m). It has a 0.33 m reveal, bronze frame, thin glass with a back-face IOR
  correction, a stone sill and a sky portal. The view outside is a dusk HDRI visible only to
  camera rays, turned to the azimuth of the Nishita sun (102°, 1.5° below the horizon).
- **Light:** only from fittings that exist: four ceiling downlights (emissive faces and a soft
  spot inside each can, 750 W each), two opal-glass wall lights beside the mirror, the LED glow
  behind the mirror, candle flames, and the dusk sky through the window. No hidden fill lights.
  AgX Medium High Contrast, exposure 0.
- **Removed from the model:** the black shelving tower 0.2 m left of the camera (`Cube.002`–`.007`
  with rails, towels, flowers and vases; the window and a lounge chair are there instead), a wall
  clock, and the emissive panel `Cube.013` above the ceiling. The candle tray from the shelves is
  moved to the side table. Decor without a rigid body that the stool's flight paths cross is
  deleted: the potted plant on the bathtub rim and the woven vase under it, the towel group on the
  north-east rail (`Towels.003`, `tovel1.002`, `tove2.001`, `tovel3.003`), the floating glass
  panel in the north-east corner (`Cube.043`, `Plane.006`, `Cube.044`), and one candle and the
  hibiscus arrangement on the east end of the counter.
- **North-east wall patch:** the model's east wall is open north of y ≈ 1.82, while the physics
  `wall_east` (inner face x = 11.10) spans the whole length. The render adds an `NE patch wall`
  (inner face x = 11.10, y 0.52→4.86, z 0→6.38) with the wall material.
- **New props:** a leather lounge chair under the window, a tall side table and a brass tooth mug
  on the counter, all out of the stool's reach.
- **Render:** Cycles with OIDN, 0.25-frame motion blur with persistent data off, fixed Cycles seed,
  1280×720, 24 fps, 96 frames. The source video and edits use 256 samples.

## Physics

- **Solver:** PyBullet, 1440 Hz (60 substeps per frame), 120 solver iterations, collision margin
  0.5 mm, gravity −9.81 m/s². Frame i is the state at t = (i−1)/24 s; there is no slow motion.
- **Stool collider:** a compound of the seat box, one box tilted along each leg axis
  (`collisionFrameOrientations`) and one foot pad per leg at the model's foot positions (7 shapes).
  The tilted boxes are shortened so their lowest corner sits on the foot face.
- **Stool material:** friction 0.35, restitution 0.60. Static bodies: friction 0.75, restitution
  0.55. Bullet multiplies the two restitutions of a contact pair.
- **Static colliders:** floor, four walls, ceiling, vanity, marble basin and mirror are boxes from
  the model's measured bounding boxes in its world coordinates (`physics/scene_geometry.py`).
- **Bathtub collider:** `assets/scenes/bathroom_stool_rebound/bathtub_collision.obj`, exported by
  `tools/export_bathtub_collider.py` from the model's marble shell (Z-up, 19731 vertices,
  38656 triangles) and loaded as a concave triangle mesh (`GEOM_FORCE_CONCAVE_TRIMESH`). The tub's
  plan is a slanted ellipse whose skirt widens with height, so no box fits it; with the mesh the
  basin is open and a stool that clears the rim falls into the tub.
- **Alcove collider:** the model chamfers the north-east corner at 45° (a diagonal wall from about
  (6.8, 4.49) to (10.4, 1.06), with a marble shelf at z = 2.49 behind it).
  `assets/scenes/bathroom_stool_rebound/alcove_collision.obj` is exported by
  `tools/export_alcove_collider.py` from `Cube_Wall pattern` and `Cube.047` with the crop box
  (6.5, 10.9, 0.9, 4.75, −0.1, 3.15) (438 triangles) and loaded the same way. A triangle is kept
  when its bounding box intersects the crop box. The alcove belongs to the room and stays when the
  bathtub is deleted.
- **Delete:** `DELETE bathtub` removes the tub collider from frame 1; the render hides the tub
  shell (`bathtub` subtree) and the towel on its rim (`Plane.003`).
- **Timed edit:** the new friction is written into the running stool at the frame boundary, and
  the run continues from the state it has reached.

## Measured motion

| Case | Measured outcome |
| --- | --- |
| `source` | hits the washbasin at 0.357 s, first touches the floor at 0.681 s, hits the bathtub at 1.151 s, tumbles and comes to rest at (5.33, 3.13); no leg scrapes the floor before the basin hit |
| `edit_fast_spin` | basin at about 0.478 s, floor at 0.708 s, bathtub at 1.039 s |
| `edit_fast_throw` | basin 0.140 s, north wall 0.401 s, chamfered wall 0.526 s (pushed south), chamfered wall again 0.895 s, drops into the bathtub at 1.331 s; seat centre peaks at about 2.87 m |
| `edit_frictionless_floor_timed` | grazes the bathtub at 1.318 s and keeps sliding east along the chamfered wall; still sliding at the end (final speed 0.478 m/s) |

## Validation

- `quality.valid` requires maximum penetration < 15 mm, a real washbasin hit, and that the stool
  never leaves the room; the builder also requires the source to hit the bathtub. The event log is
  grouped by object (`sink`, `bathtub`, `alcove`, `floor`, `wall_*`).
- During the render, `spa_dressing.check_props` computes per frame the closest distance from the
  stool mesh to every prop that is not simulated and fails below 2 cm, and casts 160 camera rays at
  the stool to measure prop occlusion. Across the cases the closest prop is 0.188 m (the candle
  tray on the alcove shelf in `edit_fast_throw`), occlusion 0 %.

## Cases

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Source throw |
| `edit_fast_spin` | `SET stool.initial_angular_velocity TIMES 3` | Launch spin 2.6 → 7.8 rad/s |
| `edit_remove_bathtub` | `DELETE bathtub` | Bathtub removed from frame 1 |
| `edit_fast_throw` | `SET stool.initial_velocity TIMES 3` | Launch speed 6.0 → 18.0 m/s |
| `edit_frictionless_floor_timed` | `SET stool.friction TIMES 0 AT FRAME 12` | Stool friction 0.35 → 0 from frame 12 (t = 0.458 s), after the basin hit and before the first floor contact |

The builder names the source case `bathroom_stool_rebound_baseline`; the edit IDs are the same as
the published case names.

## Assets

| Key | Type | Use |
| --- | --- | --- |
| `models` (`big_project.glb`) | manual | bathroom, furniture, decor and the stool |
| `polyhaven/bathroom_stool_rebound` | url | wall, floor, walnut and teak textures, the dusk HDRI, and the lounge chair, side table and brass mug models |
| `scenes/bathroom_stool_rebound` | derived | `bathtub_collision.obj` and `alcove_collision.obj` concave colliders |

```bash
python3 scripts/download_assets.py --scene bathroom_stool_rebound
python3 scripts/download_assets.py --scene bathroom_stool_rebound --check
```

## Requirements

- Python with `pybullet` (`requirements.txt`); the repository's `.venv-domino/` environment
  (pybullet 3.2.7) works.
- Blender 4.3.2 for rendering (`--blender`, or `--render-python` with the `bpy` module; otherwise
  `$BLENDER`, `blender` on `PATH` or `~/.local/opt/blender-*`).
- The collider export and the two visual audits need a Python with the `bpy` module
  (`PCVE_RENDER_PYTHON` below).
- A GPU is optional (`--device auto` or `cpu`).

## Commands

Run from the repository root.

```bash
# case list
python3 scripts/rigid_rigid/bathroom_stool_rebound/build_pcve_bathroom_stool_rebound.py --list-cases

# physics for the source
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/bathroom_stool_rebound/build_pcve_bathroom_stool_rebound.py \
  --out-root renders/bathroom_stool_rebound/new_run --simulate-only \
  --cases bathroom_stool_rebound_baseline

# physics for all five cases, then render them from the caches
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/bathroom_stool_rebound/build_pcve_bathroom_stool_rebound.py \
  --out-root renders/bathroom_stool_rebound/new_run --simulate-only
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
  scripts/rigid_rigid/bathroom_stool_rebound/build_pcve_bathroom_stool_rebound.py \
  --out-root renders/bathroom_stool_rebound/new_run --render-only --mode animation \
  --samples 256 --blender tools/blender-4.3.2-linux-x64/blender

# one case solved on its own
.venv-domino/bin/python scripts/rigid_rigid/bathroom_stool_rebound/simulate_bathroom_stool_rebound.py \
  --out renders/bathroom_stool_rebound/single/physics_transforms.json

# keyframes of one solved case
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 \
  --python scripts/rigid_rigid/bathroom_stool_rebound/render_bathroom_stool_rebound.py -- \
  --physics-json renders/bathroom_stool_rebound/single/physics_transforms.json \
  --out-dir renders/bathroom_stool_rebound/single --mode keyframes --resolution 640 360 --samples 16

# re-export the concave colliders after changing the room model (Python with bpy)
"$PCVE_RENDER_PYTHON" scripts/rigid_rigid/bathroom_stool_rebound/tools/export_bathtub_collider.py
"$PCVE_RENDER_PYTHON" scripts/rigid_rigid/bathroom_stool_rebound/tools/export_alcove_collider.py
```

- `--render-only` checks the cached simulation signature first; a cache from a different scenario
  or different collider meshes must be simulated again (drop `--render-only`). `--skip-existing`
  reuses a case only while its fingerprint holds.
- `--cases` builds a subset. `tools/render_queue.py` (workflow `batch_render`) samples randomised
  throws on top of the builder (`--count`, `--start-index`, `--seed-base`).
- `--physics-python` and `--render-python` (or `PCVE_PHYSICS_PYTHON`, `PCVE_RENDER_PYTHON`) select
  the interpreters.

## Outputs

- A build writes `cases/<case>/` under `--out-root` (default
  `renders/bathroom_stool_rebound/suite_build/pcve_bathroom_stool_rebound_suite`) with the physics
  cache `physics_transforms.json`, metrics and, after rendering, `render_validation.json`, the
  packed `bathroom_stool_rebound.blend` and frames or video, plus the suite manifest.
  `tools/render_queue.py` writes to `renders/batch_bathroom_stool_rebound` by default.
- The published suite is `renders/pcve_suites/pcve_bathroom_stool_rebound_suite/`; do not use it
  as an output root.

## Code layout

- `simulate_bathroom_stool_rebound.py` — PyBullet solve of one case (public entry).
- `render_bathroom_stool_rebound.py` — Blender replay and render (public entry).
- `build_pcve_bathroom_stool_rebound.py` — source and edit suite builder (public entry).
- `scene_config.py` — editable physics, camera and render defaults; scenario loading and validation.
- `edit_vocab.py` — edit DSL vocabulary and case list.
- `physics/scene_geometry.py` — measured room, stool and launch geometry; static boxes and mesh collider paths.
- `physics/validate_bathroom_stool_rebound.py` — simulation signature (code and collider meshes) and cache validation.
- `physics/input_hashes.py` — asset hashes used by the `--skip-existing` fingerprint.
- `appearance/look_bathroom_stool_rebound.py` — model import, decor removal, stool rigging, scene assembly.
- `appearance/spa_materials.py` — scanned stone and wood, metals, glass; world-box UVs.
- `appearance/spa_dressing.py` — window, lights, props and the per-frame prop check.
- `tools/export_bathtub_collider.py`, `tools/export_alcove_collider.py` — export the concave collider meshes (bpy).
- `tools/render_queue.py` — randomised batch throws (workflow `batch_render`).
- `requirements.txt`, `entrypoints.json`, `scene_manifest.json` — dependencies and entry metadata.

## Limitations

- The room is modelled at twice real size and the physics runs at that scale, so a fall looks
  slower than at real size (about 1/√2).
- Wall contacts may graze the wallpaper mesh visually by up to 10 mm.
- Thin decor on the flight paths is removed rather than given colliders.
- The stool's legs are boxes, not cylinders.
