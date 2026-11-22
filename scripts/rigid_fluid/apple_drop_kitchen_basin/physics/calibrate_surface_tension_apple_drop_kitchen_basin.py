"""Calibrate the Genesis SPH cohesion coefficient (gamma) against water's surface tension.

A 2 x 2 x 4 cm block of water at the apple run's particle size floats without gravity and pulls itself
towards a sphere, overshooting into the n = 2 (Rayleigh) shape oscillation. With the true surface
tension its period is T = 2 pi sqrt(rho R^3 / (8 sigma)) (R the equal-volume radius); the gamma whose
oscillation has that period stands for water at this resolution.

python calibrate_surface_tension_apple_drop_kitchen_basin.py --gamma 3e-5 [--dx 0.003]   (one gamma per run; runs go side by side)
"""
import argparse
import json
import math

import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('--gamma', type=float, nargs='+', required=True)
parser.add_argument('--dx', type=float, default=0.003)
parser.add_argument('--seconds', type=float, default=1.2)
args = parser.parse_args()

import genesis as gs  # noqa: E402

gs.init(backend=gs.cuda, precision='32', logging_level='warning')
RHO, NU, SIGMA = 998.2, 1.004e-6, 0.072
SIZE = (0.02, 0.02, 0.04)
radius = (3 * np.prod(SIZE) / (4 * math.pi)) ** (1 / 3)
target = 2 * math.pi * math.sqrt(RHO * radius ** 3 / (8 * SIGMA))
print('TARGET period %.3f s (R %.4f m)' % (target, radius), flush=True)
fps, substeps = 240, 10
for gamma in args.gamma:
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=1 / fps, substeps=substeps, gravity=(0., 0., 0.)),
        sph_options=gs.options.SPHOptions(particle_size=args.dx, pressure_solver='DFSPH',
                                          lower_bound=(-.1, -.1, -.1), upper_bound=(.1, .1, .1)),
        show_viewer=False)
    water = scene.add_entity(morph=gs.morphs.Box(pos=(0., 0., 0.), size=SIZE),
                             material=gs.materials.SPH.Liquid(rho=RHO, mu=NU, gamma=gamma, sampler='regular'))
    scene.build()
    times, aspect = [], []
    for step in range(int(args.seconds * fps)):
        scene.step()
        x = water.get_particles_pos().cpu().numpy().reshape(-1, 3)
        spread = x.std(axis=0)
        times.append((step + 1) / fps)
        aspect.append(float(spread[2] / (0.5 * (spread[0] + spread[1]))))
    aspect = np.array(aspect)
    # Half periods from the crossings of the mean aspect (the oscillation centre).
    centre = np.median(aspect[len(aspect) // 3:])
    crossings = np.flatnonzero(np.diff(np.sign(aspect - centre)) != 0)
    half = np.diff(np.array(times)[crossings])
    period = 2 * float(np.median(half)) if len(half) else float('nan')
    print('GAMMA', json.dumps({'gamma': gamma, 'period_s': period, 'target_s': target,
                               'aspect_start': float(aspect[0]), 'aspect_min': float(aspect.min()),
                               'aspect_end': float(aspect[-1]), 'crossings': len(crossings),
                               'escaped': int((np.linalg.norm(x, axis=1) > 0.05).sum()), 'particles': len(x)}),
          flush=True)
