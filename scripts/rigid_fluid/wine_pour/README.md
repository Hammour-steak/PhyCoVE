# wine_pour

A tilted, uncapped wine bottle pours red wine into a stemless glass standing on a soapstone bar
top, with a stainless workstation, a walnut back bar, a mirror and lit shelves behind it. This is
a rigid–fluid scene: the wine enters from a prescribed inflow and collects in the static glass.
The source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Wine: 990 kg/m³, kinematic viscosity 1.7e-6 m²/s.
- Pour: 60 mL/s from 0.35 s to 3.35 s; outlet speed 0.45 m/s.
- Glass: a 125 mm stemless glass; visual glass and collision proxy are separate meshes.
- Bar set: from the template `assets/scenes/wine_pour/scene_template.blend`.
- Rendering: Cycles, 96 samples.

## Physics

- Solver: Blender 4.3.2 Mantaflow FLIP, domain resolution 144, 4 effector subframes.
- The inflow is prescribed and the glass is static (one-way: the wine does not push the glass or
  the bottle).
- Flow-rate edits recompute the emitter cross-section; outlet speed and timing stay.
- Timed stop: the outlet speed drops to zero from frame 25; the wine already poured keeps
  settling.
- `simulate_wine_pour.py` writes the expected per-frame volumes (an analytic volume balance)
  without Blender.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | 60 mL/s, 1.7e-6 m²/s |
| `edit_high_viscosity_wine` | `SET wine.viscosity TIMES 2000` | 0.0034 m²/s, thick and syrup-like |
| `edit_high_flow_rate` | `SET bottle.flow_rate TO 180` | 180 mL/s |
| `edit_low_flow_rate` | `SET bottle.flow_rate TO 20` | 20 mL/s |
| `edit_delete_wine` | `DELETE wine` | no wine from frame 1 |
| `edit_stop_flow_at_1s` | `SET bottle.flow_speed TO 0 AT FRAME 25` | frames 1–24 as the source; the outlet stops at 1.0 s and the wine already poured keeps settling |

`edit_vocab.py` maps the DSL onto the configuration.

## Assets

- `scenes/wine_pour` (derived): the bar scene template with bottle, glass, bar top, back bar,
  lighting and camera, built by `tools/prepare_scene_template.py`. It has no public download.

```bash
python3 scripts/download_assets.py --scene wine_pour          # download and check sha256
python3 scripts/download_assets.py --scene wine_pour --check  # check only
```

## Requirements

- System `python3` for the builder and the volume annotations.
- Blender 4.3.2 (Mantaflow is built in).
- An NVIDIA GPU for rendering.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
python3 scripts/rigid_fluid/wine_pour/build_pcve_wine_pour.py --out-root renders/wine_pour --dry-run
python3 scripts/rigid_fluid/wine_pour/build_pcve_wine_pour.py --out-root renders/wine_pour
python3 scripts/rigid_fluid/wine_pour/simulate_wine_pour.py --out renders/wine_pour/annotations.json
blender -b assets/scenes/wine_pour/scene_template.blend --python-exit-code 1 \
  --python scripts/rigid_fluid/wine_pour/render_wine_pour.py -- --out-dir renders/wine_pour/single_source
```

- `--cases` selects edit cases (the source is always included). Each case bakes into its own
  cache inside its output directory.
- `--skip-fluid-bake --skip-render` only writes the configured `.blend` files and metadata;
  rendering with `--skip-fluid-bake` needs a compatible non-empty `--cache-dir`.
- The Blender command configures, bakes and renders one case on its own (the source with the
  default options).

## Outputs

- `renders/wine_pour/cases/<case>/`: video, configured and baked scenes, cache and per-frame
  annotations.
- `renders/wine_pour/suite_manifest.json`: all cases.
- Without `--out-root` the builder writes to `renders/wine_pour/suite_build/`. The published suite
  is `renders/pcve_suites/pcve_wine_pour_suite/`; the builder does not write there.

## Code layout

- `build_pcve_wine_pour.py`: builds the source and edits, writes the suite manifest (entry point).
- `simulate_wine_pour.py`: per-frame volume annotations without Blender (entry point).
- `render_wine_pour.py`: configure, bake, render and encode one case (entry point, runs in Blender).
- `tools/prepare_scene_template.py`: builds the scene template.
- `edit_vocab.py`: edit DSL vocabulary.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: scene description, configuration, accepted videos and provenance.

## Limitations

- Prescribed inflow against a static glass: the wine does not push the glass or the bottle.
- The analytic fill height is a volume-balance diagnostic, not a measurement of the baked surface.
