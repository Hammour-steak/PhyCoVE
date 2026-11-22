# office_desk_kettle_tip

A water bottle standing on an office desk tips over under gravity, strikes a thin plastic pen
cup, knocks the cup flat and levers the ballpoint pen out of it; everything comes to rest on the desk
within 0.9 s. Rigid–rigid scene of PhyCoVE. Source video: 4 s, 24 fps, 96 frames, 1280×720.

## Scene

- Desk: `office_desk.glb`, feet at z = 0, desk top at z = 0.860 m. The desk-top collider is the
  measured bounding box of the top (centre (−0.0255, 0.3465), half size 0.4275 × 0.7525 m).
- Static colliders on the desk are analytic boxes: `KEYBOARD_BOX`, `PHONE_BOX` and six `RACK_BOXES`
  for two drawer units and a file rack (measured sub-mesh bounding boxes of the desk model; the main
  frame box extends down to the desk top). The rendered desk keeps only the desk, keyboard, monitor and
  mouse of the GLB; a stack of cloth-bound notebooks occupies the `PHONE_BOX` volume, and the other
  boxes have no visible counterpart. The keyboard mesh and its box sit 3 cm towards the monitor, at
  least 5.8 cm from the toppled bottle.
- Bottle (`kettle` in the code): `water_bottle__plastic_bottle.glb` scaled uniformly by 1.4015 to
  17 cm and shaded as a powder-coated steel bottle with a flip-spout lid, mass 0.90 kg. The collider is a hull built from `KETTLE_PROFILE`, rings of
  `(radius, z, centre_y)` measured from the bottle in 2.5 mm height bands, so the off-axis body
  (26.6 mm on the +y side, 35.4 mm on the −y side) is reproduced; the flip spout and lid have their
  own rings. The visual mesh is clamped onto the hull by an inclusive projection (largest skin
  correction 0.37 mm on the body, 18% of the vertices moved, all above z = 0.05 m).
- Pen cup (`pen_holder`): `pen_holder.glb` at outer radius 42 mm, height 95 mm, wall 10 mm, floor
  6 mm, mass 0.080 kg; compound collider of a base disc and 14 wall segments.
- Pen: `the_pen.glb` at true size (143.4 × 9.6 mm), mass 0.012 kg, cylinder collider. It leans 35.5°
  in the cup, bottom on the inner floor and shaft on the rim, with its free end on the side the cup
  falls towards (`PEN_DRAPE_DIR`, opposite to the bottle → cup direction).
- Room: an upper-floor open-plan office (`appearance/open_office.py`) with a glass facade 0.46 m
  behind the desk. Overcast daylight only: a CIE overcast sky through the glazing with a sky portal,
  plus the ceiling LED panels above the frame. Camera rays through the glass see a street photograph
  (`potsdamer_platz_4k.hdr`) turned and tilted so that office buildings fill the window band.
- Camera: location (−1.13, 0.31, 1.24) looking at (−0.02, 0.62, 0.93), 60 mm lens, at the desk's
  front-left corner; the topple crosses the frame sideways. All bodies stay in frame in every case and
  frame; 8% of sampled sight lines are blocked, all by file boxes behind the action.
- Render: Cycles, 256 samples for the published suite, OpenImageDenoise.

## Physics

- Solver: PyBullet, 1440 Hz, 120 solver iterations, collision margin 0.1 mm. Gravity −9.81 m/s².
- Friction: desk 0.90, bottle 0.15, cup 0.90, pen 0.60. Pairwise restitution 0.30 (each body gets the
  square root).
- Launch: at frame 1 the bottle is tilted 16° about its base rim (below the 18.6° balance angle), rim
  touching the desk, after a 480-step (0.33 s) settling pre-roll. It then receives a pivot-consistent
  velocity field with 5.35 rad/s about the topple axis (rim velocity zero, no linear push,
  `KETTLE_KICK_VY = 0`) and topples under gravity. Start position (0.138, 0.469), cup at (0.000, 0.600).
- Settling damping is applied to the bottle 0.6 s after its first contact with the cup, and to the cup
  and pen once the cup lies flat (tilt ≥ 80°) or 0.6 s after the impact.
- The pen counts as released when it leaves the cup in the cup's own frame (radially beyond the inner
  wall or past the rim plane).
- `pen_holder_present` must start at `[1]`; the cup can only be deleted by a timed `DELETE`, which
  calls `p.removeBody` before the step of that frame. The renderer hides the cup and its children from
  the same frame with constant interpolation.

## Measured motion

- Source: first contact with the cup at 0.129 s, cup tips flat to 90°, pen released at 0.344 s
  (peak 1.44 m/s), everything at rest by 0.90 s, largest penetration 0.6 mm. The action spans
  frames 4–22; the remaining 3.1 s are still.
- Launch spin sweep with the fitted hull: 5.20 rad/s fails, 5.22 passes, 5.26 fails, every value from
  5.28 to 5.44 passes.
- Bottle friction 0.15 tips the cup; at 0.80 the cup tilts at most 0.6°. Cup mass 0.05–0.12 kg gives the
  same topple. Pen friction 0.3–2.4: at 0.3 the pen of `edit_heavy_kettle` rolls off the desk, at ≥ 1.0
  it stays in the cup.

## Cases

The builder's native source case is `office_desk_kettle_tip_baseline`; it is published as `source`.

| Case | Edit (DSL) | Change |
| --- | --- | --- |
| `source` | — | Bottle tips over, knocks the cup flat and levers the pen out |
| `edit_heavy_kettle` | `SET kettle.mass TIMES 5` | Bottle mass 0.9 → 4.5 kg; cup tips to 92.0°, pen released at 0.313 s (peak 1.63 m/s) |
| `edit_heavy_pen_holder` | `SET pen_holder.mass TIMES 10` | Cup mass 0.08 → 0.8 kg; cup rocks to about 15° and stays upright |
| `edit_remove_pen` | `DELETE pen` | Pen absent from frame 1 |
| `edit_remove_pen_holder` | `DELETE pen_holder AT FRAME 8` | Cup removed at frame 8 (tilted 71.9°); bottle falls flat, pen lands at (−0.195, 0.681) on the desk; frames 1–7 match the source |
| `edit_remove_kettle` | `DELETE kettle` | Kettle on the desk removed from frame 1 |

## Assets

- `models` (manual): `office_desk.glb`, `water_bottle__plastic_bottle.glb`, `pen_holder.glb`,
  `the_pen.glb` and the office furniture models.
- `polyhaven/office_desk_kettle_tip` (url and manual files): floor, table, book-cloth and veneer
  textures and the environment maps used by the room.

Download and check them with `python3 scripts/download_assets.py --scene office_desk_kettle_tip`
(add `--check` to only report).

## Requirements

- Simulation: Python with `pybullet==3.2.5` (`requirements.txt`; the repository's `.venv-domino`
  has PyBullet). CPU only.
- Rendering: Blender 4.3 (`tools/blender-4.3.2-linux-x64`); Cycles on an NVIDIA GPU (CUDA or OptiX)
  for full-quality frames, CPU works for previews.

## Commands

Run from the repository root.

```bash
# Check the registered assets
python3 scripts/download_assets.py --scene office_desk_kettle_tip --check

# List the native case IDs
python3 scripts/rigid_rigid/office_desk_kettle_tip/build_pcve_office_desk_kettle_tip.py --list-cases

# Simulate all five cases on the CPU
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/office_desk_kettle_tip/build_pcve_office_desk_kettle_tip.py \
    --out-root renders/office_desk_kettle_tip/suite_build --simulate-only

# Render the simulated cases at the published settings
PCVE_PHYSICS_PYTHON=.venv-domino/bin/python .venv-domino/bin/python \
    scripts/rigid_rigid/office_desk_kettle_tip/build_pcve_office_desk_kettle_tip.py \
    --out-root renders/office_desk_kettle_tip/suite_build --render-only \
    --blender tools/blender-4.3.2-linux-x64/blender --mode animation --resolution 1280 720 --samples 256
```

`--slow-motion 2` keeps 4 s of physical time and plays it over 8 s. `tools/render_queue.py`
(workflow `batch_render`) samples bottle and cup masses from `--seed` and builds each sample with the
builder's `run_case`.

## Outputs

The commands above write to `renders/office_desk_kettle_tip/suite_build/`, one directory per case
under `cases/`. Without `--out-root` the builder writes to
`renders/office_desk_kettle_tip/suite_build/pcve_office_desk_kettle_tip_suite/`. The published suite
is `renders/pcve_suites/pcve_office_desk_kettle_tip_suite/`; do not pass it as `--out-root`.

## Code layout

- `build_pcve_office_desk_kettle_tip.py`: suite builder; runs the simulation and render for each case.
- `simulate_office_desk_kettle_tip.py`: PyBullet solve; writes the trajectories and events.
- `render_office_desk_kettle_tip.py`: Blender replay and render; writes the video, ground truth and
  checks.
- `scene_config.py`: editable physics, render and camera defaults and scenario validation.
- `edit_vocab.py`: edit DSL vocabulary and case list.
- `physics/scene_geometry.py`: desk, proxy boxes, bottle hull, cup and pen geometry, friction and
  launch constants.
- `physics/validate_office_desk_kettle_tip.py`: acceptance checks on a solved case.
- `physics/input_hashes.py`: asset hashes used by the `--skip-existing` fingerprint.
- `appearance/look_office_desk_kettle_tip.py`: bottle, cup and pen meshes and materials, and the
  imported desk.
- `appearance/open_office.py`: office room, facade, daylight, notebook stack and the per-frame
  clearance and occlusion checks.
- `tools/render_queue.py`: randomised batch builder.

## Limitations

- Furniture on the desk collides through boxes fitted to its bounding boxes; most of these boxes have
  no visible counterpart in the render.
- The pen is a plain cylinder collider.
- The action ends after about 0.9 s, so most of the clip is static.
