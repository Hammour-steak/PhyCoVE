# flatbed_speed_bump

A loaded flatbed truck drives over a speed bump in a container terminal. The bump throws the sprung deck up, and the two cartons on it are tossed; at the source settings the near carton slides over the tail onto the road while the far one stays on the deck. PyBullet solves the truck, deck and cargo, and Blender renders the result. This is a rigid–rigid scene of PhyCoVE, the benchmark for physical counterfactual video editing (PCVE). The source video is 4 s at 24 fps, 96 frames, 1280×720.

## Scene

- **Axes:** the truck drives along world +X with the cab facing +X; +Y is the far kerb (yard side), −Y the near kerb facing the camera. Truck geometry is expressed in a vehicle frame whose origin is on the axle line at mid-wheelbase. All geometry and baseline values are in `scene_config.py`, which both the simulator and the renderer import.
- **Truck:** a three-axle flatbed model (`flatbed_unity3d.glb`) placed by one uniform factor, `TRUCK_SCALE` = 0.34 / 1.635 (front tyre radius 0.34 m). The deck surface sits 0.737 m above the road, the wheelbase is 3.068 m and the front track 1.413 m. Chassis 900 kg with its centre of mass 0.55 m above the ground contact line.
- **Deck:** a separate 350 kg body on a prismatic suspension (travel −0.09/+0.07 m), so it can overshoot the chassis and be pulled down at more than 1 g on the rebound, which is what throws loose cargo.
- **Cargo:** two cartons (`carton_box_05_closed.glb`) scaled to 0.635 × 0.805 × 0.52 m, 42 kg each, abreast across the deck with an 8 mm gap and staggered 0.90 m in X: the near (camera-side) carton's rear face is 0.65 m from the tail edge, the far carton sits 0.9 m further forward.
- **Bump and road:** a rounded sine-profile bump 0.17 m high and 1.34 m wide across the full road; road half-width 4 m, physics road 70 m each way. The truck starts at x = −7 m at 9 m/s.
- **Environment:** a container terminal at late afternoon. Container rows (long sides to the road, staggered joints) on the yard side and a block on the apron side, terminal stacks two to four high further out on the camera side and on the far stretch x ≥ 120 m of the yard side, fences on both kerbs, five unlit lamp masts on the yard side; the visual road and apron extend 300 m so their ends fall in the horizon haze. None of the scenery takes part in the physics.
- **Lighting:** the `industrial_sunset_02` panorama, rotated 300°, is the sky and the fill (sun disc clamped at 6.0; the camera sees the full panorama). A sun lamp (energy 4.2) takes its bearing from the sun in the panorama and stands at 12° elevation (the photographed sun is 2.2° high), so the road is not in the container wall's shadow.
- **Truck materials:** dark, nearly mirror-smooth opaque cab glass; paint roughness follows the texture brightness, so rust and grime are more matte.
- **Cameras:** fixed rigs, none follows the truck (`CAMERA_PRESETS` in `render_flatbed_speed_bump.py`). `clip4s` (default, 36 mm, 20.5 m back at (−21.0, −6.5, 2.2) m) holds the whole run; `wide` (44 mm, 8 m off the near kerb at the bump) is the three-quarter still rig; `static` (50 mm) and `survey` (26 mm) are other bump-side placements.
- **Rendering:** Cycles by default, half-frame (180°) shutter. `--device auto` stays on the CPU unless `PCVE_CYCLES_GPU=1` is set, which makes it try CUDA.

## Physics

- **Solver:** PyBullet, 60 substeps per frame (dt = 1/1440 s), 300 solver iterations, gravity −9.8 m/s².
- **Suspension:** 40 kN/m and 1.87 kN·s/m on the deck (1.70 Hz), with stiffer bump and droop stops (700 kN/m, 6 kN·s/m) past the travel limits and a force cap of 14× (up) / 4× (down) the deck weight that keeps the explicit integration stable on hard landings. Chassis angular damping 0.12.
- **Wheels:** cylinders fixed to the chassis without spinning axles, with near-frictionless road contact (0.02) so they carry the full normal load without dragging; the renderer spins the visible wheels at v/R.
- **Drive:** cruise control as a force at the chassis centre of mass, 200 kN per m/s of speed error, capped at 25 kN. A force there cannot torque the chassis, so all pitch comes from the bump.
- **Friction:** cargo–deck pair friction 0.20 (the edited control), deck 0.70, road 0.96.
- **Timed edits:** the builder writes a timed edit to `timed_edits.json` and passes `--timed-edits-json`; the simulator applies each entry at the top of its frame. For `edit_brake_before_bump` it lowers the cruise target at frame 8 and leaves the truck's current velocity alone, so the drive force slows the truck over the following frames. `run_status.json` records each write with the state on both sides.
- **Cache contract:** `physics/validate_flatbed_speed_bump.py` signs every cache with the simulation parameters and the hashes of the scene and shared `.py` files; the renderer refuses a cache whose signature does not match.

## Measured motion

Values read back from `run_status.json` of the runs that produced the published videos.

| Case | Outcome | First frame that differs from the source |
|---|---|---|
| `source` | Deck lift 0.446 m, carton clearance 0.240/0.059 m, 14 and 7 airborne frames, one carton off the deck at the end, truck at x = 28.594 m | — |
| `edit_fast_truck` | 18 m/s: deck lift 1.816 m, 21 and 22 airborne frames, both cartons thrown clear, truck ends at x = 64.14 m (71.1 m covered against 35.6 m) | 1 |
| `edit_low_bump` | 0.051 m bump: lift 0.034 m, clearance 0.029/0.027 m, 2 and 2 airborne frames; nothing visibly separates (`quality.visible` is false) | 14 |
| `edit_high_bump` | 0.255 m bump: lift 0.909 m, clearance 0.649/0.247 m, 14 and 15 airborne frames; both cartons thrown clear of the deck | 14 |
| `edit_slippery_cargo` | μ 0.05: deck lift 0.454 m as in the source, but the cartons slide while the deck moves under them (clearance 0.396/0.039 m) and both end off the deck | 2 |
| `edit_brake_before_bump` | Cruise target 9.0 → 3.6 m/s at frame 8: lift 0.085 m, clearance 0.006/0.007 m, no airborne frames, truck ends at x = 9.54 m instead of 28.59 m | 9 |

In the source the front axle meets the bump on frame 14 and the deck reaches its peak lift around frame 24. The low bump and the late brake both suppress the throw and end with `quality.visible = false`, which the builder accepts for an edit; the source must show the effect.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | Truck at 9 m/s over the 0.17 m bump, cargo friction 0.20 |
| `edit_fast_truck` | `SET flatbed_truck.initial_velocity TIMES 2` | Launch speed 9 → 18 m/s |
| `edit_low_bump` | `SET speed_bump.height TIMES 0.3` | Bump height 0.17 → 0.051 m |
| `edit_high_bump` | `SET speed_bump.height TIMES 1.5` | Bump height 0.17 → 0.255 m |
| `edit_slippery_cargo` | `SET cargo.friction TIMES 0.25` | Cargo–deck friction 0.20 → 0.05 |
| `edit_brake_before_bump` | `SET flatbed_truck.speed TIMES 0.4 AT FRAME 8` | From frame 8 (t = 0.292 s) the cruise target drops from 9.0 to 3.6 m/s; frames 1–8 match the source |
| `edit_delete_speed_bump` | `DELETE speed_bump` | Speed bump removed from frame 1 |

`edit_vocab.py` defines the objects and properties. `flatbed_truck.initial_velocity` and `flatbed_truck.speed` both bind to `truck_speed`: `initial_velocity` is an initial condition, so the DSL rejects `AT FRAME` on it, while `speed` is the cruise target the drive force follows every substep and can change during the clip. The builder derives each edit's prompts with `pcve_edit_dsl.make_prompts`; the source prompts are `DESCRIPTION` in `edit_vocab.py`. The builder names the source case `flatbed_speed_bump_baseline`; the edit IDs are the same as in the published suite (`--list-cases` prints them).

## Assets

| Key | Type | Use |
|---|---|---|
| `models` | manual | `flatbed_unity3d.glb` (truck), `carton_box_05_closed.glb` (cargo), `speed_bump.glb` (bump), `container_pack.glb` (containers), `lamppost.glb` (lamp masts) |
| `polyhaven/flatbed_speed_bump` | url + derived | Asphalt, concrete, corrugated iron, metal plate and shutter textures, the `industrial_sunset_02` panorama, and the credit and source records |

Assets go into `assets/` at the repository root (`PCVE_ASSETS_DIR` replaces the asset root).

```bash
python3 scripts/download_assets.py --scene flatbed_speed_bump
python3 scripts/download_assets.py --scene flatbed_speed_bump --check
```

## Requirements

- A Python with `pybullet==3.2.7` (`requirements.txt`), for example `.venv-domino/`; the builder runs the simulator with `--physics-python` (default `$PCVE_PHYSICS_PYTHON`, else `.runtime/sim`, a link to `.venv-domino`).
- Blender 4.3.2 for rendering: `--blender`, or a Python with `bpy` through `--render-python` (`$PCVE_RENDER_PYTHON`); otherwise the Blender found by `pcve_assets.blender`.
- CPU rendering works; GPU rendering through `PCVE_CYCLES_GPU=1` uses CUDA.

## Commands

Run from the repository root.

```bash
S=scripts/rigid_rigid/flatbed_speed_bump
export PCVE_PHYSICS_PYTHON=.venv-domino/bin/python
.venv-domino/bin/python $S/build_pcve_flatbed_speed_bump.py --list-cases
.venv-domino/bin/python $S/build_pcve_flatbed_speed_bump.py --out-root renders/flatbed_speed_bump/new_run --dry-run

# physics only, all six cases
.venv-domino/bin/python $S/build_pcve_flatbed_speed_bump.py --out-root renders/flatbed_speed_bump/new_run --simulate-only

# full 1280x720 videos from the default clip4s rig
.venv-domino/bin/python $S/build_pcve_flatbed_speed_bump.py --out-root renders/flatbed_speed_bump/new_run \
  --mode animation --resolution 1280 720 --blender tools/blender-4.3.2-linux-x64/blender --skip-existing

# frame-24 stills of the source and the fast edit from the wide rig
.venv-domino/bin/python $S/build_pcve_flatbed_speed_bump.py --out-root renders/flatbed_speed_bump/stills \
  --mode preview --camera-mode wide --preview-frame 24 --resolution 960 540 \
  --cases flatbed_speed_bump_baseline edit_fast_truck --blender tools/blender-4.3.2-linux-x64/blender

# standalone solve of the source
.venv-domino/bin/python $S/simulate_flatbed_speed_bump.py --out renders/flatbed_speed_bump/sim/physics_transforms.json
```

- `--mode` is `animation` (default, writes `video.mp4`) or `preview` (one still at `--preview-frame`). The builder defaults are 960×540 and 32 samples; pass `--resolution 1280 720` for the benchmark format.
- `--cases` builds a subset, `--simulate-only` / `--render-only` run one half, `--skip-existing` reuses cases whose fingerprint still matches, `--clean-stale-cases` deletes case folders that are not in the current case list, and `--verbose-render` streams the child output to the console.
- `tools/render_queue.py` (workflow `batch_render`) samples seeded truck speeds, bump heights and cargo friction and runs the simulate and render entries directly (`--count`, `--start-index`, `--seed-base`).

## Outputs

Without `--out-root` the builder writes to `renders/flatbed_speed_bump/suite_build/pcve_flatbed_speed_bump_suite/`. Each case folder `<out-root>/cases/<case>/` holds `physics_transforms.json`, `scenario_input.json`, `prompts.json`, `run_status.json`, edits also `scenario_overrides.json` (and `timed_edits.json` for the timed edit), and after rendering `ground_truth_transforms.json`, `scenario_metadata.json`, `flatbed_speed_bump.blend` and `video.mp4` or `preview.png`; the root holds `suite_manifest.json`. The published suite is `renders/pcve_suites/pcve_flatbed_speed_bump_suite/`; do not write new runs into it.

## Code layout

- `build_pcve_flatbed_speed_bump.py`: suite builder (cases, timed-edit schedules, fingerprints, simulate and render calls, manifest).
- `simulate_flatbed_speed_bump.py`: PyBullet solve of chassis, sprung deck and cargo.
- `render_flatbed_speed_bump.py`: Blender scene (road, yard, truck, cargo, lighting, camera rigs) and replay.
- `scene_config.py`: shared geometry, baseline physics, camera and render defaults.
- `edit_vocab.py`: edit vocabulary, simulator bindings, edit list and source prompts.
- `physics/validate_flatbed_speed_bump.py`: cache schema and signature contract.
- `appearance/import_truck.py`: adapts the truck model to the chassis/deck rig and sets its materials.
- `appearance/import_props.py`: containers, terminal stacks, lamp masts and the speed hump model.
- `tools/render_queue.py`: seeded parameter samples (workflow `batch_render`).
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry-point description, scene manifest, Python dependency.

## Limitations

- The wheels have no axles or tyre model; they are near-frictionless cylinders fixed to the chassis.
- The deck suspension is a single prismatic spring–damper with stops, not a leaf-spring model.
- The sun lamp stands at 12°, higher than the 2.2° sun in the panorama.
- The render sample count of the published videos is not recorded in the published suite.
