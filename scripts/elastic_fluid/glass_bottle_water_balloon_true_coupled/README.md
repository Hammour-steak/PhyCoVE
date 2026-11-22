# glass_bottle_water_balloon_true_coupled

A rubber balloon is stretched over the mouth of a glass jar under a running kitchen tap. Water
fills the balloon, which stretches and swells inside and above the jar. This is an elastic–fluid
scene: the water load and the membrane shape are solved together at every step (hydrostatic
pressure on the wetted membrane, water level from the enclosed volume); the water has no velocity
field. The source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Balloon: a latex membrane whose neck is fixed to the jar mouth; edge stiffness 25 N/m.
- Water: tap flow 4.5 L/min from frame 2; the incoming stream is analytic free-fall geometry.
- Kitchen: the jar and tap in a kitchen room, `front_low` camera.
- Rendering: Cycles (GPU), 96 samples with adaptive sampling and denoising; the water is
  reconstructed inside the membrane.

## Physics

- Membrane: an XPBD triangle-edge network in NumPy with edge springs 25 N/m and bending springs
  6 N/m at relative modulus 1 (shear is implicit in the edge network; no absolute Young's modulus
  in Pa or continuum Poisson ratio is calibrated). The neck vertices are fixed to the jar mouth and
  the jar contacts stay active. The solver runs on the CPU.
- Water: hydrostatic water inside the deformed membrane.
- Retention: every case uses `--water-retention retain_all`: all water that enters stays in the
  balloon (poured = retained, nothing spills). When hydrostatic expansion alone cannot hold the
  water below the lip, a one-sided wet-volume constraint adds retention pressure and stretches
  the membrane further. This is an idealized no-discharge boundary, not a physically open mouth,
  and it does not trap the original air.
- At a fixed outlet area Q = A·v, so the flow multiplier is also the outlet-speed multiplier. With
  the same retained water, a stiffer membrane may first inflate less and need more retention
  pressure, so its final volume is not necessarily smaller.
- The simulator also offers `--water-retention spill_at_lip` (an overflow model that discharges
  water over the lip) and `--sealed`; the builder uses neither.
- Settings live in `balloon_config.py` (paths, presets, workflow helpers), `scene_spec.json`
  (scene description copied into every case) and `edit_vocab.py` (edits and prompts).

## Validation

`physics/validate_glass_bottle_water_balloon_true_coupled.py` checks the inputs, the water budget
(poured = retained), that the requested water fits the available geometry (an infeasible input is
rejected, never silently discarded), contacts, stability and the media.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | 4.5 L/min, relative modulus 1 |
| `edit_high_flow` | `SET tap.flow_rate TIMES 2` | 9 L/min, all water retained |
| `edit_tap_off_from_start` | `SET tap.flow_rate TO 0` | no water from frame 1 |
| `edit_hard_balloon` | `SET balloon.young_modulus_scale TIMES 5` | all elastic energies × 5 (125 and 30 N/m), all water retained |

The builder names the source `glass_jar_water_balloon_source`; the published suite stores it as
`source`.

## Assets

- `blenderkit/modern_living_kitchen` (manual): the kitchen room.

```bash
python3 scripts/download_assets.py --scene glass_bottle_water_balloon_true_coupled          # download and check sha256
python3 scripts/download_assets.py --scene glass_bottle_water_balloon_true_coupled --check  # check only
```

Manual files need a free BlenderKit account; the script prints the asset page and the file name
to save.

## Requirements

- Python environment `.venv-genesis-mpm-sph/` at the repository root with the packages of
  `requirements.txt` (`numpy==2.2.6`, `scipy==1.15.3`, `trimesh==5.1.1`, `libigl==2.6.3`,
  `scikit-image==0.25.2`; the surface step needs libigl, trimesh and scikit-image).
- The solver runs on the CPU; an NVIDIA GPU renders.
- Blender 5.1.2 (this scene is rendered with 5.1.2), found from `$BLENDER`, then
  `tools/blender-5.1.2-*/blender` in the repository root, then `~/.local/opt/blender-5.1.2-*/blender`
  (`pcve_assets.blender("5.1.2")`; no other version is picked); `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/glass_bottle_water_balloon_true_coupled/build_pcve_glass_bottle_water_balloon_true_coupled.py \
  --out-root renders/glass_bottle_water_balloon_true_coupled --dry-run
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/glass_bottle_water_balloon_true_coupled/build_pcve_glass_bottle_water_balloon_true_coupled.py \
  --out-root renders/glass_bottle_water_balloon_true_coupled --gpu auto \
  --cases edit_high_flow edit_tap_off_from_start edit_hard_balloon
.venv-genesis-mpm-sph/bin/python scripts/elastic_fluid/glass_bottle_water_balloon_true_coupled/build_pcve_glass_bottle_water_balloon_true_coupled.py \
  --out-root renders/glass_bottle_water_balloon_true_coupled --stage validate \
  --cases edit_high_flow edit_tap_off_from_start edit_hard_balloon
```

- The first command runs the CPU behaviour and regression tests.
- Stages: `prepare`, `simulate`, `surface`, `render`, `validate`, `all`. The source is always
  included in `--cases`; without `--cases` all three edits are built. Existing, partial or
  conflicting outputs are never overwritten, and the accepted outputs listed in
  `balloon_config.READ_ONLY_OUTPUTS` are refused as targets.
- Each case keeps copies of its settings (prompts, overrides, timed edits and `scene_spec.json`);
  a run on an existing case, for example with `--skip-existing`, refuses to continue when a copy
  differs from the current settings. The comparison leaves out `outputs.root` of
  `scene_spec.json`, which only records where accepted outputs are stored.

## Outputs

- `renders/glass_bottle_water_balloon_true_coupled/cases/<case>/`: membrane cache (`sim/`),
  reconstructed water (`surfaces/`), rendered frames and video, prompts, overrides and validation
  results (inputs, water accounting, capacity, contacts, stability and the video format).
- The published suite is `renders/pcve_suites/pcve_glass_bottle_water_balloon_true_coupled_suite/`;
  the builder does not write there.

## Code layout

- `build_pcve_glass_bottle_water_balloon_true_coupled.py`: staged source and edit pipeline (entry point).
- `simulate_glass_bottle_water_balloon_true_coupled.py`: membrane and water model (entry point).
- `surface_glass_bottle_water_balloon_true_coupled.py`: membrane cache and reconstructed water.
- `render_glass_bottle_water_balloon_true_coupled.py`: rendering, encoding, decode and format checks (entry point).
- `balloon_config.py`: paths, presets and workflow helpers.
- `scene_spec.json`: scene description copied into every case.
- `edit_vocab.py`: edits and prompts.
- `physics/validate_glass_bottle_water_balloon_true_coupled.py`: inputs, water accounting, capacity and media checks.
- `appearance/scene_glass_bottle_water_balloon_true_coupled.py`: Blender kitchen scene.
- `appearance/look_glass_bottle_water_balloon_true_coupled.py`: material helpers.
- `appearance/overflow_glass_bottle_water_balloon_true_coupled.py`: overflow visuals used with `spill_at_lip`.
- `requirements.txt`: Python packages of the solver and surface step.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases and the published suite.

## Limitations

- Not a resolved two-way fluid–structure simulation: there is no water velocity field, sloshing,
  impact splash, wetting or bursting.
- The retain-all boundary is an idealization; inputs beyond the jar's available space are
  infeasible.
- Membrane stiffness is a relative scale, not a calibrated rubber modulus.
