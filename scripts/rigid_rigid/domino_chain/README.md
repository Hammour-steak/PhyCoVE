# domino_chain

Five ivory resin dominoes, D01–D05, stand in a row on the green baize of a home mahjong table. D01 starts tilted past its balance point and the chain falls by contact alone. Gravity is a quarter of normal so the fall is slow enough to follow; playback is real solver time. PyBullet solves the motion and Blender replays the solved poses. This is a rigid–rigid scene of PhyCoVE, the benchmark for physical counterfactual video editing (PCVE). The source video is 4 s at 24 fps, 96 frames, 1280×720.

## Scene

- **Units and axes:** SI, Z up, the row runs along +X from left to right. All inputs are in `scene_spec.json`, split into `physics`, `simulation_quality`, `appearance` and `render`; `simulate_domino_chain.py` loads it, and every case writes its exact inputs to its output folder.
- **Table:** playfield about 0.75 × 0.75 m with its surface at Z = 0.84 m, level with the window sill.
- **Dominoes:** 50 × 25 × 8 mm, 16 g each, on 35 mm upright slots. D01 starts tilted 12° about its front bottom edge (beyond the 9.09° stability limit), which moves its centre 5.3 mm forward and leaves about 16.6 mm clearance to D02. All initial velocities are zero. There are no joints, motors, hidden pushers or prescribed motion.
- **Tiles:** rounded resin meshes from the normalized domino asset with moulded pips only; the D01–D05 identity marks on the tile sides are removed.
- **Baize:** a photographed felted, napped wool at the provider's scale (0.274 m repeat), its luminance re-dyed baize green (linear 0.009, 0.070, 0.028), with its roughness map, its normal map (strength 0.45) and a 3 m⁻¹ dye-lot mottle (±8 %) that hides the repeat; sheen 0.12, specular level 0.15.
- **Room:** painted timber casement windows, linen curtains (static meshes from a separate cloth relaxation), a plant on the sill, a tea cup and saucer and wooden tile trays. No printed text is in the shot: the two face-up playing cards and the 50-card deck that the card layers build are deleted by the last appearance layer.
- **Lighting:** only sources that exist in the scene. The sunlit garden photograph is the world background with its sun clipped at 6.0, and a Cycles portal (no emission) spans the glazed opening. The room is lit by the analytic sun (strength 4.0, matching the energy clipped from the photograph's sun disc, 4.1–4.5 per channel) and the photographed sky, both through the casement. Exposure is 2.2 EV, as for a camera exposed for the interior.
- **Camera:** fixed 34 mm lens at f/8.
- **Rendering:** Cycles 128 samples, OpenImageDenoise, AgX, 0.25-frame shutter (10.4 ms), persistent data off (Blender 4.3 can drop objects that have come to rest when motion blur and persistent data are both on). The sampling seed is fixed; in the source video static regions change by less than 0.03 8-bit levels between frames on average, and no pixel changes by more than 3 levels once the tiles are at rest.

## Physics

- **Solver:** PyBullet 3.2.7, 800 substeps per frame at 24 fps (dt = 1/19200 s), 200 solver iterations, 20 µm collision margin, 0.1 mm contact breaking threshold, 1 µm contact slop, restitution velocity threshold 1 mm/s.
- **Gravity:** −2.4525 m/s² (0.25 g).
- **Contacts:** lateral friction 0.65 for tiles and table (Bullet multiplies the pair), restitution 0.08, linear and angular damping 0.01. Collisions use 50 × 25 × 8 mm box proxies; the detailed tile meshes are visual only.
- **Sampling:** poses are stored at 240 Hz, so motion blur uses solver subframes. Video frame i is the solver state at t = (i−1)/24 s.
- **Timed deletion:** for `DELETE D01 AT FRAME 13` the simulator advances the unchanged world to 0.500000 s (after the D01–D02 contact at 0.327083 s), removes D01 and continues without resetting D02's velocities. The collision ledger and the exact deletion time are kept. Blender hides the complete D01 hierarchy, including its shadow, with constant visibility keys.

## Measured motion

| Case | Measured outcome |
|---|---|
| `source` | D01→D02→D03→D04→D05; contacts at 0.327, 0.521, 0.648 and 0.757 s; motion ends after about 1.0 s (24 frames, below 2 mm/s); peak tile speed 0.37 m/s; all five fall into an overlapping pile |
| `edit_heavy_D03` | D03 rocks about 1.5° and returns upright; D01 rests at about 59°, D02 leans on D03 at about 33°; D04 and D05 stay up |
| `edit_remove_D03` | D01 and D02 fall; D02 stays about 11 mm short of D04; D04 and D05 stay up |
| `edit_remove_D01` | D02–D05 stay upright with no domino-to-domino contact |
| `edit_remove_D01_after_contact` | Frames 1–12 match the source exactly; D02 keeps its acquired motion and D02–D05 fall; the D04–D05 contact is at about 0.802 s instead of 0.757 s |
| `edit_heavy_D01` | All five fall; the D04–D05 contact advances to about 0.534 s |
| `edit_heavy_D04` | D04 rocks up to about 2.33° and supports the preceding tiles; D05 stays upright |

## Validation

The build stops when a case fails a check. The source is simulated and checked first; edits run only if it passes.

- **Physics, after each simulation:** zero initial velocities, no initial penetration, D01 (when present) past its stability limit with clearance to D02, no prescribed motion, forces or constraints, no tile tipping before it is hit, penetration below 0.1 mm, a still final half second (position range below 0.05 mm, tilt range below 0.05°), and base slip below 1 mm before 45° for the source and the blocking edits. Each case must show its expected contact order and outcome (the heavy D03 must rock and return below its critical angle; the mass edits must differ clearly from the source). The D01 removal must keep D02–D05 present and upright with no domino-to-domino contact and displacement below 0.05 mm. The timed removal must match the source exactly before frame 13 and remove D01 only after its first contact with D02.
- **Case-specific conditions:** the mass edits allow the physical contact sliding instead of the source's 1 mm pre-tip slip limit. The heavy D04 edit keeps slight supported rocking: its last-half-second position and tilt ranges meet the 0.05 mm / 0.05° limits, and its peak equivalent speed (about 0.576 mm/s) is reported without the source's 0.5 mm/s limit. Validation never changes solver settings, friction, damping or trajectories.
- **Video, in the `render` and `verify` stages:** `scripts/pcve_verify_video.py` checks full decode, resolution, frame rate and frame count.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | Source chain |
| `edit_heavy_D01` | `SET D01.mass TIMES 10` | D01 mass 16 → 160 g |
| `edit_heavy_D03` | `SET D03.mass TIMES 10` | D03 mass 16 → 160 g |
| `edit_heavy_D04` | `SET D04.mass TIMES 10` | D04 mass 16 → 160 g |
| `edit_remove_D01` | `DELETE D01` | D01 absent from frame 1 |
| `edit_remove_D01_after_contact` | `DELETE D01 AT FRAME 13` | D01 removed from frame 13 (t = 0.5 s) |
| `edit_remove_D03` | `DELETE D03` | D03 absent from frame 1 |

Mass edits keep the shape. `edit_vocab.py` defines the DSL objects D01–D05 (shown in prompts as "the first domino" … "the fifth domino", counted from the left) and the mass, friction and restitution properties; the builder derives each edit's prompts with `pcve_edit_dsl.make_prompts`, and the source prompts are written in `build_pcve_domino_chain.py`. The builder names the source case `domino_chain_baseline`; the edit IDs are the same as in the published suite (`--list-cases` prints them).

## Assets

| Key | Type | Use |
|---|---|---|
| `sketchfab/dominoes_render_at_night` | manual + derived | Domino meshes, normalized to 50 × 25 × 8 mm |
| `innerscene/mahjong_game_table` | url + derived | Mahjong table |
| `polyhaven/caban` | url + derived | Green baize (re-dyed felted wool) |
| `polyhaven/oak_veneer_01` | url + derived | Tile trays |
| `polyhaven/rough_linen` | url + manual + derived | Curtain fabric |
| `pcve/domino_chain_curtain_drape` | derived | Settled curtain shape |
| `blenderkit/modern_living_room_interior` | manual + derived | Curtain rod and window placement |
| `polyhaven/potted_plant_04` | url + derived | Plant on the window sill |
| `polyhaven/tea_set_01` | url + derived | Tea cup and saucer |
| `polyhaven/sunny_rose_garden` | url + derived | Garden and sky outside the window (world), matched to the sun |
| `ambientcg/Fabric034` | url + derived | Baize of the intermediate table layers; the final layer replaces it with `polyhaven/caban` |
| `polyhaven/brown_photostudio_05` | url + derived | World lighting of the intermediate layers; replaced by the garden sky |
| `polyhaven/suburban_field_01` | url + derived | Window exterior of the intermediate window layer; replaced by `polyhaven/sunny_rose_garden` |
| `pcve/domino_chain_cards` | derived | Card back artwork; the cards are built and then deleted from the shot |
| `pcve/domino_chain_natural` | derived | Card face textures; the cards are built and then deleted from the shot |
| `public_domain/byron_knoll_cards` | url + derived | Card face artwork; the cards are built and then deleted from the shot |
| `polyhaven/book_encyclopedia_set_01` | url + derived | Not loaded with the current `scene_spec.json` |
| `polyhaven/dining_chair_02` | url + derived | Not loaded with the current `scene_spec.json` (`background_chair_asset` is `none`) |
| `polyhaven/painted_wooden_chair_01` | url + derived | Not loaded with the current `scene_spec.json` (`background_chair_asset` is `none`) |

Assets are not in Git. They go into `assets/` at the repository root (set `PCVE_ASSETS_DIR` for another location). Manual files need a provider account; `download_assets.py` prints each page and the file names to save. Derived files are made by this project and have no public download, so `--check` reports them as missing until they are supplied; `assets.json` describes each one.

```bash
python3 scripts/download_assets.py --scene domino_chain          # download and check sha256
python3 scripts/download_assets.py --scene domino_chain --check  # check only
```

## Requirements

- Python environment `.venv-domino/` at the repository root with `requirements.txt` (`pybullet==3.2.7`, `numpy==1.26.4`, `pillow==11.3.0`); `entrypoints.json` points the entry scripts at it.
- Blender 4.3.2, found from `$BLENDER`, then `blender` on `PATH`, then `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- An NVIDIA GPU for rendering (`--device auto` uses OptiX, then CUDA); `--device cpu` works but is slow.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
B=scripts/rigid_rigid/domino_chain/build_pcve_domino_chain.py
.venv-domino/bin/python $B --list-cases
.venv-domino/bin/python $B --out-root renders/domino_chain/new_run --dry-run      # print the plan only
.venv-domino/bin/python $B --out-root renders/domino_chain/new_run --stage simulate --cases domino_chain_baseline
.venv-domino/bin/python $B --out-root renders/domino_chain/new_run --stage render
.venv-domino/bin/python $B --out-root renders/domino_chain/new_run --stage verify
.venv-domino/bin/python $B --out-root renders/domino_chain/new_run --stage all     # simulate, render and verify
.venv-domino/bin/python $B --out-root renders/domino_chain/graybox_run --stage graybox  # D03 mass and friction scans, no rendering

# selected frames of one solved case
tools/blender-4.3.2-linux-x64/blender -b --python-exit-code 1 --python scripts/rigid_rigid/domino_chain/render_domino_chain.py -- \
  --mode frames --keyframes 1 24 96 --device cpu \
  --out-dir renders/domino_chain/new_run/cases/domino_chain_baseline \
  --physics-json renders/domino_chain/new_run/cases/domino_chain_baseline/physics_transforms.json
```

- All seven cases run by default; `--cases` selects some of them. `--skip-existing` reuses finished cases in the same output root. `--device auto|cpu` and `--threads-native N` pass through to the renderer.
- `--physics-source-root <finished suite>` renders with the accepted solver outputs of a finished suite instead of simulating again; only appearance or one common support-height translation may differ.
- `render_domino_chain.py --mode frames` without `--keyframes` renders frames 1, 11, 17, 21, 24, 31, 60 and 96.
- Without `--out-root` the native builder writes to `renders/domino_chain/suite_build/pcve_domino_chain_suite`, never to the published suite.

## Outputs

Each case is written to `<out-root>/cases/<case>/`:

| File | Content |
|---|---|
| `video.mp4` | rendered video |
| `physics_transforms.json` | full simulation result: poses, contacts, tilt thresholds, quality metrics |
| `physics_validation.json` | result of every physics check |
| `ground_truth_transforms.json` | per-frame poses as replayed in Blender |
| `prompts.json` | edit DSL and prompts |
| `scenario_overrides.json` | physics override of an edit |
| `scenario_metadata.json` | exact inputs of the case |
| `render_report.json` | render device, backend and timing |
| `video_validation.json` | decode and format check of the video |

The output root also holds `suite_manifest.json` (cases and status) and `implementation_manifest.json` (configuration hash, runtime versions). The published suite is `renders/pcve_suites/pcve_domino_chain_suite/`; `scene_manifest.json` pins its video hashes and maps the builder's case IDs to the published ones. Do not write new runs into it.

## Code layout

- `build_pcve_domino_chain.py`: suite builder (physics checks, gray-box scans, simulate/render/verify stages, source prompts).
- `simulate_domino_chain.py`: PyBullet simulation; loads `scene_spec.json`.
- `render_domino_chain.py`: Blender replay, rendering and encoding.
- `scene_spec.json`: all physical, numerical, appearance and render inputs.
- `edit_vocab.py`: edit DSL vocabulary and solver bindings.
- `appearance/look_domino_chain.py`: tiles, materials and the base card-table room; the other appearance modules are applied after it in order.
- `appearance/card_table_environment.py`, `appearance/natural_card_table.py`, `appearance/daylight_card_table.py`, `appearance/mahjong_table_realism.py`: table, baize, tea set, trays and room context.
- `appearance/playing_card_finish.py`, `appearance/paper_support.py`, `appearance/loose_card_realism.py`: card stock, seating and curl of the card props.
- `appearance/window_realism.py`: painted timber casement and garden view.
- `appearance/furniture_textile_realism.py`, `appearance/gathered_linen.py`: the linen material and the static linen curtains.
- `appearance/sunlit_room_realism.py`: sun through the casement.
- `appearance/photographic_finish.py`: final layer (text removal, baize, scene-only lighting), configured by `scene_spec.json` under `appearance.finish`.
- `tools/make_card_back.py`: generates the card-back artwork in `assets/pcve/domino_chain_cards/`.
- `entrypoints.json`, `scene_manifest.json`, `requirements.txt`: entry-point description, scene manifest, Python dependencies.

## Limitations

- Quarter gravity slows the scene; it is not a real-world condition. Re-solving at 9.81 m/s² with all other inputs equal gives source contacts at 0.164, 0.261, 0.324 and 0.378 s, rest after 0.51 s and a peak tile speed of 0.73 m/s; the tiles stay in contact throughout (no flight or bounce), so quarter gravity reads as roughly 2× slow motion.
- Friction and restitution are effective solver parameters, not measured for resin on baize.
- The rounded tile meshes are visual; collisions use 50 × 25 × 8 mm boxes.
- Curtains are static meshes from a separate cloth relaxation, not simulated in the clip.
- Lighting, exposure and material values are set by visual review, not measured.
- The baize is a photographed felted coat wool re-dyed green, not a scan of mahjong-table cloth.
- Friction-scan sliding is sensitive at the floating-point level: changing how the same timestep is split into frames moves D03's final pose by about 1 mm.
- The appearance is built in layers; intermediate layers load assets and build card props that later layers replace or delete.
