"""Baseline physics of the toy boat glide, standard library only.

edit_vocab.py hands these to the PCVE edit DSL, which scripts/release/build_benchmark.py imports without the
simulation's dependencies; the simulation's CLI defaults are the same values.
"""

FPS = 24
FRAMES = 96
# The mass that displaces a 52 mm draft of the hull in the baseline water (simulate_toy_boat_pool_glide.py
# derives it from --boat-draft 0.052; checked against it by the build script).
BOAT_MASS = 0.7176815672285165
BOAT_SPEED = 0.90
LIQUID_DENSITY = 998.0
LIQUID_NU = 1.004e-6

# Each key is one simulation flag (SIMULATION_FLAGS in the build script).
BASELINE_PHYSICS = {
    "boat_mass": BOAT_MASS,
    "boat_initial_speed": BOAT_SPEED,
    "liquid_density": LIQUID_DENSITY,
    "liquid_kinematic_viscosity": LIQUID_NU,
    "boat_presence": [1],
    "water_presence": [1],
}
