"""Baseline physics of the bowling-ball pool drop, standard library only.

The simulation takes these values from here, and edit_vocab.py hands them to the PCVE edit DSL, which
scripts/release/build_benchmark.py imports without the simulation's dependencies.
"""

FPS = 24
FRAMES = 96
BALL_RADIUS = 0.075
BALL_MASS = 2.068702658637
BALL_START = (0.0, 0.0, 0.70)
BALL_VELOCITY = (0.0, 0.0, -4.0)
WATERLINE = -0.25
FLOOR = -1.25
LIQUID_DENSITY = 1000.0
LIQUID_NU = 1.0e-6

# Edits override ball_mass, liquid_density or liquid_kinematic_viscosity through the simulation's
# --ball-mass, --liquid-density and --liquid-nu.
BASELINE_PHYSICS = {'ball_radius': BALL_RADIUS, 'ball_mass': BALL_MASS, 'ball_initial_z': BALL_START[2],
                    'ball_initial_velocity_z': BALL_VELOCITY[2], 'liquid_surface_z': WATERLINE,
                    'liquid_density': LIQUID_DENSITY, 'liquid_kinematic_viscosity': LIQUID_NU,
                    'ball_present': [1], 'water_present': [1]}
