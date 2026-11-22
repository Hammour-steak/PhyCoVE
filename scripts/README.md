# PhyCoVE scene code

There are 90 scenes, one directory each under `scripts/<category>/<scene>/`: `rigid_rigid` 40,
`rigid_elastic` 28, `rigid_fluid` 16, `elastic_fluid` 4, `elastic_elastic` 2.
`scene_registry.json` lists them and is authoritative. Each category folder has a README with one
line per scene.

## Scene directory

Each scene directory has `README.md`, `entrypoints.json`, `scene_manifest.json` and three public
entry points: `simulate_<scene>.py`, `render_<scene>.py` and `build_pcve_<scene>.py`. Nine fluid
scenes add `surface_<scene>.py`, a surface-reconstruction stage between simulation and rendering.
`entrypoints.json` lists each entry point's runtime and native options, the cases, the workflows
and the implementation files. `scene_manifest.json` records the supported cases and the published
suite with the sha256 of every case video. Scene modules live next to the entry points or in
subfolders, normally `physics/`, `appearance/` and `tools/`. Each scene README follows the same
outline: Scene, Physics, Cases, Assets, Requirements, Commands, Outputs, Code layout and
Limitations.

## Shared command line

The three entry points of every scene accept `--out-root`, `--dry-run`, `--describe`, `--python`,
`--blender`, `--gpu` and `--threads`; the builder also accepts `--cases`, `--list-cases`,
`--stage`, `--workflow` (where a scene has extra workflows) and the edit-catalog options
`--list-edits`, `--show-prompts` and `--export-prompts` (for builders that declare their edits in
`PCVE_*` literals; other builders do not offer them). `--dry-run` prints the plan as JSON without
importing a solver, starting Blender or writing files, and rejects forwarded option names that the
entry point does not list in `native_options`; `--describe` prints each entry point's own options.
`--export-prompts` rewrites the prompt files of an existing suite, by default
`renders/<scene>/suite_build/pcve_<scene>_suite/`; it touches the published suite only when that path
is passed with `--out-root`. Everything else (physics, inputs, caches, render settings) is scene-specific and
documented in the scene README.

The builders of the 30 scenes whose `entrypoints.json` sets `named_suite_output` write
`renders/<scene>/suite_build/pcve_<scene>_suite/` by default (next to the scene's native data,
never the published suite); `--out-parent DIR` selects another parent and `--out-root PATH` an
exact output path.

Commands that run a Python tool inside Blender are written
`blender -b --python-exit-code 1 --python <tool> -- ...`: without `--python-exit-code 1` Blender
exits with 0 even when the script raises.

## Suites and the dataset release

`renders/pcve_suites/pcve_<scene>_suite/` holds the internal suite of each scene:
`suite_manifest.json`, `README.txt`, `inputs/`, `native_manifests/` and one `cases/<case>/` folder
per case (`source` and `edit_<name>`) with `video.mp4`, `prompts.json` (`pcve_prompts/1`),
`ground_truth_transforms.json` (`pcve_ground_truth/1`), `provenance.json`,
`video_validation.json` and `native_metadata/`. Every video follows
`benchmark_media_contract.json`: 1280×720, 24 fps, 96 frames, 4.0 s. Published source and target
videos are distributed in the Hugging Face dataset release.

`release/build_benchmark.py` turns these suites into the Hugging Face dataset
[`ccmoony/PhyCoVE`](https://huggingface.co/datasets/ccmoony/PhyCoVE) (default output
`renders/phycove_release/`): `scenes/<scene>/cases/<case>/` with only `video.mp4`, a compact
`prompts.json` and `ground_truth_transforms.json`, plus `benchmark_manifest.json`,
`metadata.jsonl`, `metadata_viewer.jsonl`, `splits/` (`all`, `by_category`, `by_kind`,
`by_property`, `by_timing`), the dataset card `release/dataset_card.md`, `LICENSE` and
`assets.json`. The root README describes both layouts.

Assets come from the root `assets/` directory registered in `assets.json` (see the root README).

## Shared modules

| File | Purpose |
| --- | --- |
| `pcve_scene_entry.py` | Shared command line of every entry point: read-only `--describe`, `--dry-run` and `--list-cases`, runtime overrides, and the builder's edit-catalog options. |
| `pcve_scene_runtime.py` | Shared command-line and output helpers for the scenes whose entry points use them, including the physics and render interpreter lookup (`PCVE_PHYSICS_PYTHON`, `PCVE_RENDER_PYTHON`). |
| `pcve_scene_pipeline.py` | Process runner for the builders that run their stages through it. |
| `pcve_batch_queue.py` | Randomized batch workflow behind `rigid_rigid/home_basketball_door/tools/render_queue.py` and `rigid_rigid/pot_lid_drop/tools/render_queue.py`. |
| `pcve_edit_dsl.py` | The edit DSL (`SET`, `DELETE`, `ADD`, timing), its parser and the bilingual prompt generator. |
| `pcve_edit_catalog.py` | Reads a builder's `PCVE_*` source/edit declarations without loading a solver; backs `--list-edits`, `--show-prompts` and `--export-prompts`. |
| `pcve_edit_policy.py` | Edit policy: physical SET, genuinely new ADD, or DELETE. |
| `pcve_timed_edits.py` | Plumbing for edits that take effect partway through a clip. |
| `pcve_ground_truth.py` | Writes and checks `ground_truth_transforms.json` in the `pcve_ground_truth/1` layout. |
| `pcve_case_metadata.py` | Reads scene case IDs from Python source without importing the implementation; `carried_provenance()` gives the provenance records (the `standardization` record) a rebuilt case keeps from the published one, for the `tools/publish_suite.py` of six rigid–elastic scenes. |
| `pcve_assets.py` | Asset and Blender paths without machine-specific locations (`asset()`, `scene_asset()`, `blender()`). |
| `pcve_project_paths.py` | Repository-relative path helpers and default suite output roots. |
| `pcve_media_contract.py` | Delivery contract checks on the MP4 sample table; the contract itself is `benchmark_media_contract.json`. |
| `pcve_verify_video.py` | Checks dimensions, timing, decoded frame count and full decoding of a video. |
| `pcve_render_quality.py` | Renderer and colour-management setup shared by some Blender renderers. |
| `pcve_blender_compat.py` | Small Blender 3.6/4.x API differences used by the renderers. |
| `pcve_realism_kit.py` | Shared appearance helpers used by several rigid–elastic and elastic–elastic scenes. |
| `pcve_door_asset.py` | Fits the `old_door.glb` leaf and frame into the doorway (Blender side) for `door_basketball_collision` and `home_basketball_door`. |
| `pcve_gpu_policy.py` | Optional GPU allocation checks from metadata queries only; never starts a job. Respects `CUDA_VISIBLE_DEVICES`, `--gpu`, and optional `PCVE_GPU_RESERVED` (empty by default). |
| `pcve_gpu_reservations.py` | Reads the GPU binding of live Blender/Python processes for the GPU launchers in `tools/` of several rigid–elastic scenes. |
| `pcve_worker_run.py` | GPU launcher behind `tools/worker_run.py` of eight rigid–elastic scenes: GPU and process preflight, a per-GPU lease, UUID binding and a holder process that keeps the CUDA context between stages. |
| `pcve_windows_dll_paths.py` | On Windows, puts the conda `Library/bin` on the DLL search path before PyBullet loads (imported by six PyBullet scenes; no effect elsewhere). |
| `pcve_fem_geometry.py` | Tetrahedral grids, exterior faces and material volumes for the libuipc FEM solves of `gym_landing_mat` and `picnic_ground_blanket`. |
| `pcve_native_viscosity.cu`, `pcve_native_viscosity_frontend.cpp` | Sources of the native libuipc metric and dihedral viscosity extension of `gym_landing_mat` and `picnic_ground_blanket`; `rigid_elastic/gym_landing_mat/tools/support/build_pool_native.py` compiles them and every solve copies them into its output. |
| `pcve_dfsph_patches.py` | Genesis 1.4.3 DFSPH patches (single gravity, XSPH smoothing, Akinci surface tension) for `cooking_oil_pan`, `milk_pitcher_glass`, `tilted_cup_table_pour` and `toy_car_float_bathtub`. |
| `pcve_config_diff.py` | Read-only audit of a report's before/after configuration snapshots against the declared changes (`traditional_tea_pour`, `toy_car_ramp_pool_genesis`). |
| `release/build_benchmark.py` | Builds the Hugging Face release from `renders/pcve_suites/` (`--out DIR`, default `renders/phycove_release/`). |
| `download_assets.py` | Fetches or checks the files registered in `assets.json`. |
| `check_scene_layout.py` | Checks every scene's public interface without starting a solver or Blender (`--strict` for manifests and published videos). |

## Validation

```bash
python3 scripts/check_scene_layout.py
python3 scripts/check_scene_layout.py --strict
```

The default check verifies the canonical files of every scene and runs `--help` and a read-only
`--dry-run` for every public entry point (plus case-list and output-root checks for the
`named_suite_output` scenes). `--strict` also checks, for every scene, that `scene_manifest.json`
exists, that its `supported_cases` equal the union of the builder's `--list-cases` over its
workflows (main first), that every `implementation_files` entry exists and that the current
suite's `case_video_sha256` matches the published videos. The keys of `case_video_sha256` are
mapped to suite case directories by `public_case_ids` first, then by the builder's `PCVE_*`
catalog (native and CLI case IDs to `catalog_case_id`), else used as they are. Neither starts a
solver or renders.

## Scenes

| Category | Scene | Documentation |
| --- | --- | --- |
| `rigid_rigid` | `ball_block_building` | [README](rigid_rigid/ball_block_building/README.md) |
| `rigid_rigid` | `ball_box_rebound` | [README](rigid_rigid/ball_box_rebound/README.md) |
| `rigid_rigid` | `basketball_corner_rebound` | [README](rigid_rigid/basketball_corner_rebound/README.md) |
| `rigid_rigid` | `basketball_court_bounce` | [README](rigid_rigid/basketball_court_bounce/README.md) |
| `rigid_rigid` | `basketball_cup_collision` | [README](rigid_rigid/basketball_cup_collision/README.md) |
| `rigid_rigid` | `basketball_rim_roll_in` | [README](rigid_rigid/basketball_rim_roll_in/README.md) |
| `rigid_rigid` | `bathroom_stool_rebound` | [README](rigid_rigid/bathroom_stool_rebound/README.md) |
| `rigid_rigid` | `bathroom_tennis_throw` | [README](rigid_rigid/bathroom_tennis_throw/README.md) |
| `rigid_rigid` | `bowling` | [README](rigid_rigid/bowling/README.md) |
| `rigid_rigid` | `chalk_box_stack` | [README](rigid_rigid/chalk_box_stack/README.md) |
| `rigid_rigid` | `curling_collision` | [README](rigid_rigid/curling_collision/README.md) |
| `rigid_rigid` | `domino_chain` | [README](rigid_rigid/domino_chain/README.md) |
| `rigid_rigid` | `door_basketball_collision` | [README](rigid_rigid/door_basketball_collision/README.md) |
| `rigid_rigid` | `flatbed_speed_bump` | [README](rigid_rigid/flatbed_speed_bump/README.md) |
| `rigid_rigid` | `home_basketball_door` | [README](rigid_rigid/home_basketball_door/README.md) |
| `rigid_rigid` | `kitchen_bowl_fall` | [README](rigid_rigid/kitchen_bowl_fall/README.md) |
| `rigid_rigid` | `kitchen_can_collision` | [README](rigid_rigid/kitchen_can_collision/README.md) |
| `rigid_rigid` | `kitchen_orange_collision` | [README](rigid_rigid/kitchen_orange_collision/README.md) |
| `rigid_rigid` | `kitchen_tableware_collision` | [README](rigid_rigid/kitchen_tableware_collision/README.md) |
| `rigid_rigid` | `kitchen_tin_collision` | [README](rigid_rigid/kitchen_tin_collision/README.md) |
| `rigid_rigid` | `newtons_cradle` | [README](rigid_rigid/newtons_cradle/README.md) |
| `rigid_rigid` | `office_desk_kettle_tip` | [README](rigid_rigid/office_desk_kettle_tip/README.md) |
| `rigid_rigid` | `opposing_pendulum_collision` | [README](rigid_rigid/opposing_pendulum_collision/README.md) |
| `rigid_rigid` | `pendulum_box_collision` | [README](rigid_rigid/pendulum_box_collision/README.md) |
| `rigid_rigid` | `pool_break` | [README](rigid_rigid/pool_break/README.md) |
| `rigid_rigid` | `pot_lid_drop` | [README](rigid_rigid/pot_lid_drop/README.md) |
| `rigid_rigid` | `ramp_car_ball_collision` | [README](rigid_rigid/ramp_car_ball_collision/README.md) |
| `rigid_rigid` | `soccer_ball_collision` | [README](rigid_rigid/soccer_ball_collision/README.md) |
| `rigid_rigid` | `soccer_step_collision` | [README](rigid_rigid/soccer_step_collision/README.md) |
| `rigid_rigid` | `stair_ball_bounce` | [README](rigid_rigid/stair_ball_bounce/README.md) |
| `rigid_rigid` | `tennis_bottle_collision` | [README](rigid_rigid/tennis_bottle_collision/README.md) |
| `rigid_rigid` | `toy_car_bottle` | [README](rigid_rigid/toy_car_bottle/README.md) |
| `rigid_rigid` | `toy_car_collision` | [README](rigid_rigid/toy_car_collision/README.md) |
| `rigid_rigid` | `toy_car_track_jump` | [README](rigid_rigid/toy_car_track_jump/README.md) |
| `rigid_rigid` | `twin_pendulum_collision` | [README](rigid_rigid/twin_pendulum_collision/README.md) |
| `rigid_rigid` | `twin_ramp_collision` | [README](rigid_rigid/twin_ramp_collision/README.md) |
| `rigid_rigid` | `u_track_ball` | [README](rigid_rigid/u_track_ball/README.md) |
| `rigid_rigid` | `uneven_ground_ball` | [README](rigid_rigid/uneven_ground_ball/README.md) |
| `rigid_rigid` | `volleyball_corner_rebound` | [README](rigid_rigid/volleyball_corner_rebound/README.md) |
| `rigid_rigid` | `wall_clock_drop` | [README](rigid_rigid/wall_clock_drop/README.md) |
| `rigid_elastic` | `beach_ball_hammock_mpm` | [README](rigid_elastic/beach_ball_hammock_mpm/README.md) |
| `rigid_elastic` | `book_pillow_bedroom` | [README](rigid_elastic/book_pillow_bedroom/README.md) |
| `rigid_elastic` | `cabinet_towel_pinch` | [README](rigid_elastic/cabinet_towel_pinch/README.md) |
| `rigid_elastic` | `curtain_doraemon_drape` | [README](rigid_elastic/curtain_doraemon_drape/README.md) |
| `rigid_elastic` | `egg_dough` | [README](rigid_elastic/egg_dough/README.md) |
| `rigid_elastic` | `elastic_key_strap` | [README](rigid_elastic/elastic_key_strap/README.md) |
| `rigid_elastic` | `football_goal_net` | [README](rigid_elastic/football_goal_net/README.md) |
| `rigid_elastic` | `gym_landing_mat` | [README](rigid_elastic/gym_landing_mat/README.md) |
| `rigid_elastic` | `metal_pendulum_horizontal_spring` | [README](rigid_elastic/metal_pendulum_horizontal_spring/README.md) |
| `rigid_elastic` | `metro_security_bag_curtain` | [README](rigid_elastic/metro_security_bag_curtain/README.md) |
| `rigid_elastic` | `passive_car_spring_return_ramp` | [README](rigid_elastic/passive_car_spring_return_ramp/README.md) |
| `rigid_elastic` | `phone_sofa_drop` | [README](rigid_elastic/phone_sofa_drop/README.md) |
| `rigid_elastic` | `picnic_ground_blanket` | [README](rigid_elastic/picnic_ground_blanket/README.md) |
| `rigid_elastic` | `plastic_ruler_coin` | [README](rigid_elastic/plastic_ruler_coin/README.md) |
| `rigid_elastic` | `rubber_band_wood_slider` | [README](rigid_elastic/rubber_band_wood_slider/README.md) |
| `rigid_elastic` | `scarf_chair_slip` | [README](rigid_elastic/scarf_chair_slip/README.md) |
| `rigid_elastic` | `silicone_bag_can` | [README](rigid_elastic/silicone_bag_can/README.md) |
| `rigid_elastic` | `silicone_block_chain` | [README](rigid_elastic/silicone_block_chain/README.md) |
| `rigid_elastic` | `slingshot_domino` | [README](rigid_elastic/slingshot_domino/README.md) |
| `rigid_elastic` | `spring_block_step` | [README](rigid_elastic/spring_block_step/README.md) |
| `rigid_elastic` | `spring_car_collision` | [README](rigid_elastic/spring_car_collision/README.md) |
| `rigid_elastic` | `spring_scale_weight_drop` | [README](rigid_elastic/spring_scale_weight_drop/README.md) |
| `rigid_elastic` | `steel_ball_tensioned_membrane` | [README](rigid_elastic/steel_ball_tensioned_membrane/README.md) |
| `rigid_elastic` | `tennis_net_hit` | [README](rigid_elastic/tennis_net_hit/README.md) |
| `rigid_elastic` | `thomas_dual_spring_train` | [README](rigid_elastic/thomas_dual_spring_train/README.md) |
| `rigid_elastic` | `toy_car_silicone_bridge` | [README](rigid_elastic/toy_car_silicone_bridge/README.md) |
| `rigid_elastic` | `wood_block_rubber_stop` | [README](rigid_elastic/wood_block_rubber_stop/README.md) |
| `rigid_elastic` | `yoga_mat_rolled_edge` | [README](rigid_elastic/yoga_mat_rolled_edge/README.md) |
| `rigid_fluid` | `apple_drop_kitchen_basin` | [README](rigid_fluid/apple_drop_kitchen_basin/README.md) |
| `rigid_fluid` | `bowling_ball_pool_drop` | [README](rigid_fluid/bowling_ball_pool_drop/README.md) |
| `rigid_fluid` | `coffee_ice_drop` | [README](rigid_fluid/coffee_ice_drop/README.md) |
| `rigid_fluid` | `cooking_oil_pan` | [README](rigid_fluid/cooking_oil_pan/README.md) |
| `rigid_fluid` | `cup_water_drop` | [README](rigid_fluid/cup_water_drop/README.md) |
| `rigid_fluid` | `faucet_sink` | [README](rigid_fluid/faucet_sink/README.md) |
| `rigid_fluid` | `fish_tank_toy` | [README](rigid_fluid/fish_tank_toy/README.md) |
| `rigid_fluid` | `honey_spoon_toast` | [README](rigid_fluid/honey_spoon_toast/README.md) |
| `rigid_fluid` | `juice_dispenser_orange_cup` | [README](rigid_fluid/juice_dispenser_orange_cup/README.md) |
| `rigid_fluid` | `milk_pitcher_glass` | [README](rigid_fluid/milk_pitcher_glass/README.md) |
| `rigid_fluid` | `tilted_cup_table_pour` | [README](rigid_fluid/tilted_cup_table_pour/README.md) |
| `rigid_fluid` | `toy_boat_pool_glide` | [README](rigid_fluid/toy_boat_pool_glide/README.md) |
| `rigid_fluid` | `toy_car_float_bathtub` | [README](rigid_fluid/toy_car_float_bathtub/README.md) |
| `rigid_fluid` | `toy_car_ramp_pool_genesis` | [README](rigid_fluid/toy_car_ramp_pool_genesis/README.md) |
| `rigid_fluid` | `traditional_tea_pour` | [README](rigid_fluid/traditional_tea_pour/README.md) |
| `rigid_fluid` | `wine_pour` | [README](rigid_fluid/wine_pour/README.md) |
| `elastic_fluid` | `bathroom_sink_duck_neospace` | [README](elastic_fluid/bathroom_sink_duck_neospace/README.md) |
| `elastic_fluid` | `elastic_fluid_duck` | [README](elastic_fluid/elastic_fluid_duck/README.md) |
| `elastic_fluid` | `glass_bottle_water_balloon_true_coupled` | [README](elastic_fluid/glass_bottle_water_balloon_true_coupled/README.md) |
| `elastic_fluid` | `wind_flag` | [README](elastic_fluid/wind_flag/README.md) |
| `elastic_elastic` | `cotton_tshirt_sofa` | [README](elastic_elastic/cotton_tshirt_sofa/README.md) |
| `elastic_elastic` | `entryway_eva_slippers` | [README](elastic_elastic/entryway_eva_slippers/README.md) |
