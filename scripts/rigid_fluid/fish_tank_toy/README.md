# fish_tank_toy

A 90 mm die-cast rally car falls into a water-filled aquarium standing on a toy chest in a
children's bedroom. The car punches an air cavity into the surface, throws up a jet, sinks while
righting itself and settles on the glass bottom; the water then sloshes and calms down. This is a
rigid–fluid scene in which the car's trajectory drives the liquid as a moving obstacle. The
source video is 4 s at 24 fps (96 frames), 1280×720.

## Scene

- Car: 90.1 × 39.9 × 30.8 mm, closed-mesh volume 61.6 cm³, 85 g (mean density 1381 kg/m³, so it
  sinks). Released from rest at 0.25 s with its underside 22 cm above the water, nose 17° down,
  over the middle of the tank; it enters at frame 13 at 2.0 m/s.
- Water: 998 kg/m³, kinematic viscosity 1e-6 m²/s, surface at z = 0.758 m, 27.3 cm deep. A 275 g
  moss rock lies on the back right of the tank floor, clear of the car's path.
- Camera `front_eye` at (0.675, −1.20, 0.95) m looking at (1.575, −1.22, 0.68) m, 35 mm lens with
  depth of field on the drop point.
- Rendering: Cycles, 96 samples, refractive caustics on, motion blur on the car only. Trapped-air
  bubbles from the Mantaflow cache are rendered as 0.8–2.2 mm air spheres. For camera rays only,
  the front and back glass panes and the water's front and back faces do not reflect (no mirror
  image of the car and of the room).

## Physics

- Car model (`simulate_fish_tank_toy.py`): gravity, buoyancy from the displaced volume, added
  mass, quadratic drag, Stokes drag for viscosity edits, hydrostatic righting and contact with the
  glass bottom. Floating bodies get a free-surface heave damping ratio of 0.40 (only when
  positively buoyant and partly submerged). This trajectory is the ground truth and the obstacle
  path of the liquid (one-way coupling).
- Liquid: Blender 4.3.2 Mantaflow FLIP, domain resolution 160 (about 3 mm cells), mesh scale 2,
  mesh particle radius 2.0, FLIP ratio 0.90, 24 effector subframes, fractional obstacles off. The
  domain reaches 2.5 mm into the glass so the water/glass seam falls inside it.
- Density edits: density is not a Mantaflow input, so the car and rock follow the rigid-body
  model with the edited density and drive the liquid as obstacles; in those edits the rock gets a
  hidden obstacle and its own buoyant trajectory.
- Gel edit: the high-viscosity car response is rendered with a still translucent gel volume,
  because Blender 4.3's high-viscosity Mantaflow paths make the liquid climb the tank walls before
  impact.

## Validation

The renderer checks the physics constants against the built geometry and logs the liquid volume:
in the source it goes from 43.78 to 43.12 L (−1.2% at the impact, −0.3% over the remaining
72 frames), and the surface ends 3.7 mm lower.

## Cases

| Case | Edit (DSL) | Change |
|---|---|---|
| `source` | — | water contact at frame 13, bottom contact at frame 24.8; sinks and settles |
| `edit_light_toy_car` | `SET toy_car.mass TIMES 0.4` | 34 g, below the 61 g of water it displaces; dips under, bobs up and floats |
| `edit_dense_water_float_rock` | `SET water.density TIMES 3` | 2994 kg/m³; the car floats and the moss rock rises from the floor |
| `edit_gel_water` | `SET water.viscosity TIMES 500000` | 0.5 m²/s gel; a shallow, slowly deepening indentation, the car does not sink |
| `edit_dense_water_at_2s` | `SET water.density TIMES 3 AT FRAME 49` | frames 1–48 as the source; from frame 49 the car and rock rise back to the surface |

The builder names the source `fish_tank_toy_baseline`; the published suite stores it as `source`.

## Assets

- `blenderkit/rally_toy_car` (manual): the toy car.
- `blenderkit/aquarium_aquascape` (manual): the aquarium.
- `blenderkit/moss_rock_photoscan` (manual): the rock in the tank.
- `blenderkit/cosmic_kids_bedroom` (manual): the bedroom.
- `blenderkit/modern_cozy_living_room`, `blenderkit/books_stack` (manual): room dressing.
- `sketchfab/plant_pot_ae825dd0d3c5437a953b4236d6cef08b` (manual, plus derived prepared files):
  a plant pot.

```bash
python3 scripts/download_assets.py --scene fish_tank_toy          # download and check sha256
python3 scripts/download_assets.py --scene fish_tank_toy --check  # check only
```

Manual files need a free BlenderKit or Sketchfab account; the script prints each asset page and
the file names to save. Derived files are made by this project and have no public download.

## Requirements

- System `python3` (standard library only) for the builder and the car model; Blender runs the car model again inside the bake.
- Many CPU cores for the bake (64 threads: the source bake takes about 57 minutes) and an NVIDIA
  GPU for rendering (about 16 minutes).
- Blender 4.3.2 (Mantaflow is built in), found from `$BLENDER`, then `blender` on `PATH`, then
  `~/.local/opt/blender-*/blender`; `--blender` overrides it.
- `ffmpeg` and `ffprobe` for encoding and video checks.

## Commands

Run from the repository root.

```bash
python3 scripts/rigid_fluid/fish_tank_toy/build_pcve_fish_tank_toy.py --out-root renders/fish_tank_toy --dry-run
python3 scripts/rigid_fluid/fish_tank_toy/build_pcve_fish_tank_toy.py --out-root renders/fish_tank_toy \
  --keep-intermediates --gpus 0 1 --parallel 2 --threads 48
```

- All five cases run by default (`--cases` selects some, by the builder names). `--parallel`
  runs cases side by side on the GPUs listed in `--gpus`.
- `--skip-existing --source-video <finished source case>` extends an existing output root
  without re-rendering the source.
- `--keep-intermediates` keeps the Mantaflow cache and `.blend` files; `--rerender-baked` (on
  `render_fish_tank_toy.py`) re-renders a kept bake with the current materials.

## Outputs

- `renders/fish_tank_toy/cases/<case>/`: `video.mp4`, `prompts.json`, the car (and rock)
  trajectory used as ground truth, the liquid volume log and, with `--keep-intermediates`, the
  bake and `.blend` files.
- `renders/fish_tank_toy/suite_manifest.json`: all cases.
- Without `--out-root` the builder writes to `renders/fish_tank_toy/suite_build/`. The published
  suite is `renders/pcve_suites/pcve_fish_tank_toy_suite/`; the builder does not write there.

## Code layout

- `build_pcve_fish_tank_toy.py`: builds the source and the edits (entry point).
- `simulate_fish_tank_toy.py`: rigid-body car (and rock) trajectory in water (entry point).
- `render_fish_tank_toy.py`: room, aquarium and toy assembly, Mantaflow bake, rendering and encoding (entry point, runs in Blender).
- `edit_vocab.py`: edit DSL vocabulary.
- `entrypoints.json`: entry-point options and runtimes for the shared CLI.
- `scene_manifest.json`: cases, video hashes of the published suite, simulation, render and lighting settings.

## Limitations

- The car and rock follow a reduced-order rigid-body model; the liquid does not push back on them
  (one-way coupling).
- The gel edit is a rendered gel volume over the reduced-order car response, not a Mantaflow
  high-viscosity solve.
- The anti-reflection treatment of the glass applies only to camera rays.
