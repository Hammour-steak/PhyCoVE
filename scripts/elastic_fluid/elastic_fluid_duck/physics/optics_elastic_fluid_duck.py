"""Optics shared by render_elastic_fluid_duck.py and caustics_elastic_fluid_duck.py: the sun, the water's absorption, the fine
capillary ripples and the sunlight textures of the pool shell. render_elastic_fluid_duck.py tilts the water's shading
normal by the ripples; caustics_elastic_fluid_duck.py refracts sunlight through the same ripples, so the light on the
pool floor matches the surface you see."""
import math

import numpy as np

SUN_TO = (-.480, -.254, .840)   # direction to the scene's 'Afternoon Sun' lamp; render_elastic_fluid_duck.py checks it
IOR = 1.333
WATER_ABSORPTION = ((.40, .84, .90), 1.)  # Volume Absorption colour and density: 1 m transmits (.55, .85, .90)
GRAVITY, TENSION_OVER_DENSITY = 9.81, 7.2e-5
# Optional ripples on top of the simulated water, off (RIPPLE_RMS_SLOPE = 0): with the sun on the
# pool floor, the caustics come from the simulated splash waves alone and the rest of the water
# stays a calm mirror. RIPPLE_COUNT waves with wavelengths log-uniform in RIPPLE_WAVELENGTHS and
# directions spread around RIPPLE_WIND, all with the same slope and RIPPLE_RMS_SLOPE together; speeds
# follow capillary-gravity dispersion. Faint ripples, (.02, .2) m at 0.7 deg, only break the
# reflections into a whitish speckle. A bright caustic network needs a breezy pool, (.05, .5) m at
# 2.5 deg or (.08, .8) m at 4 deg, whose surface glitters and looks restless.
RIPPLE_COUNT = 48
RIPPLE_WAVELENGTHS = (.02, .2)      # m
RIPPLE_RMS_SLOPE = 0.               # deg
RIPPLE_WIND, RIPPLE_SPREAD = 30., 60.   # deg: mean direction and its standard deviation
RIPPLE_SEED = 7
SHELL_PIXEL = .01               # m per sunlight texture pixel on the pool shell
SHELL_TOP = .07                 # top of the pool walls (the coping sits behind them)
SHELL_INWARD = {'PoolFloor': (0, 0, 1), 'PoolBack': (0, -1, 0), 'PoolFront': (0, 1, 0),
                'PoolLeft': (1, 0, 0), 'PoolRight': (-1, 0, 0)}


def absorption():
    """Absorption coefficient (1/m) of the water volume for R, G, B, as Cycles' Volume Absorption."""
    colour, density = WATER_ABSORPTION
    return density*(1-np.asarray(colour))


def ripple_terms():
    """The ripples as (kx, ky, omega, phase, (cx, cy)). The height is sum(a sin(kx x + ky y - omega t
    + phase)), so they tilt a surface normal n by n_z * sum((cx, cy) cos(kx x + ky y - omega t + phase))."""
    if not (RIPPLE_COUNT and RIPPLE_RMS_SLOPE):
        return []
    rng = np.random.default_rng(RIPPLE_SEED)
    lowest, highest = (math.log(wavelength) for wavelength in RIPPLE_WAVELENGTHS)
    wavenumbers = 2*math.pi/np.exp(rng.uniform(lowest, highest, RIPPLE_COUNT))
    angles = np.radians(RIPPLE_WIND+rng.normal(0, RIPPLE_SPREAD, RIPPLE_COUNT))
    phases = rng.uniform(0, 2*math.pi, RIPPLE_COUNT)
    slope = math.radians(RIPPLE_RMS_SLOPE)/math.sqrt(RIPPLE_COUNT/2)   # amplitude times wavenumber
    return [(float(k*math.cos(angle)), float(k*math.sin(angle)), math.sqrt(GRAVITY*k+TENSION_OVER_DENSITY*k**3),
             float(phase), (-slope*math.cos(angle), -slope*math.sin(angle)))
            for k, angle, phase in zip(wavenumbers, angles, phases)]


def ripple_tilt(x, y, t):
    """(tilt x, tilt y) of the ripples at points x, y (m) and time t (s); add n_z times it to a normal."""
    tilt_x, tilt_y = np.zeros_like(x), np.zeros_like(x)
    for kx, ky, omega, phase, (cx, cy) in ripple_terms():
        wave = np.cos(kx*x+ky*y-omega*t+phase)
        tilt_x += cx*wave
        tilt_y += cy*wave
    return tilt_x, tilt_y


def shell_textures(lower, upper):
    """Sunlight texture layout of each pool shell object: (u axis, v axis, (u0, u1), (v0, v1), (rows, cols)).
    u, v are the axes of the object's TileUV map (world metres); rows run along v, columns along u."""
    x, y, z = (lower[0], upper[0]), (lower[1], upper[1]), (lower[2], SHELL_TOP)
    layout = {'PoolFloor': (0, 1, x, y), 'PoolBack': (0, 2, x, z), 'PoolFront': (0, 2, x, z),
              'PoolLeft': (1, 2, y, z), 'PoolRight': (1, 2, y, z)}
    def pixels(span):
        return int(math.ceil(round((span[1]-span[0])/SHELL_PIXEL, 6)))
    return {name: (u, v, ur, vr, (pixels(vr), pixels(ur))) for name, (u, v, ur, vr) in layout.items()}
