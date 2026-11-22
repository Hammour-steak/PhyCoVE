"""SI dimensions of the wall clock, the pine crate and the room.

Everything here is measured, not guessed: the room numbers come from ray
probes of a game-level room model (futuristic_room.glb; the probes and boxes
are kept in ``assets/scenes/wall_clock_drop/room_colliders.json``, on which
``appearance/boot_room.py`` builds the rendered room), and the clock numbers come from the bounds of
``assets/models/wall_clock.glb`` scaled to a real 44 cm dial.
The crate is the one asset this scene builds itself
(``tools/make_crate_asset.py`` writes ``assets/models/wooden_crate.glb``), so its
numbers are the ones the generator is written to, not measurements.

Both the collision side and the imported visuals read this module, so the body
that tumbles on screen is the body that was solved.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

SCENE = 'wall_clock_drop'
KEYS = ('clock', 'crate')

# ------------------------------------------------------------------ the room
# The action happens in the sunken strip along the south wall: measured floor
# top z = 0.000 there, 0.050 on the raised platform that starts at STEP_Y.
FLOOR_Z = 0.0
STEP_Y = -1.120
UPPER_FLOOR_Z = 0.050
# Inner face of the south wall's decorative panels: the clock hangs on it.
WALL_Y = -2.579
# That wall also carries a 128 mm plinth whose face stands 79 mm proud of the
# panels. A clock that slides into the wall stops against the plinth, so the
# two faces are separate colliders instead of one plane.
PLINTH_Y = -2.500
PLINTH_TOP_Z = 0.1285
CEILING_Z = 2.5056
ROOM_MIN_X, ROOM_MAX_X = -5.000, 3.978

# --------------------------------------------------------------- the clock
# wall_clock.glb is authored 5.966 m across and 0.5728 m deep, back face at
# z = 0, dial facing +z. A real hall clock of this style is ~44 cm across, so
# the whole model is scaled by CLOCK_DIAMETER / 5.966 and re-centred on its
# bounding box; the collision shape is the disc that remains.
CLOCK_MODEL_DIAMETER = 5.966
CLOCK_MODEL_THICKNESS = 0.5728
CLOCK_DIAMETER = 0.440
CLOCK_RADIUS = CLOCK_DIAMETER / 2
CLOCK_THICKNESS = CLOCK_MODEL_THICKNESS * CLOCK_DIAMETER / CLOCK_MODEL_DIAMETER
CLOCK_HALF_THICKNESS = CLOCK_THICKNESS / 2
CLOCK_MASS = 1.35               # beech case, brass bezel, dial, movement, glass
# Centre of the disc with its back face on the wall, at ordinary eye height.
CLOCK_HANG = (-0.600, WALL_Y + CLOCK_HALF_THICKNESS + 0.0015, 1.530)
# The hanger gives way: the case rotates forward off the wall (`tip_spin`,
# rad/s about +x, negative tips the dial face down towards the room) while it
# is already drifting away from the wall (`push`, m/s along +y).
CLOCK_TIP_SPIN = -0.60
CLOCK_PUSH = 0.42

# --------------------------------------------------------------- the crate
# A nailed pine crate standing on the floor against the same wall, directly
# under the clock's fall line. It is the rigid answer to a question the first
# cut answered with a cardboard carton: corrugated board dents under a 1.4 kg
# clock, and a body that dents is not a body this benchmark can solve. A crate
# is the same box of air out of a material that really is rigid -- four corner
# posts, eight rails and three boards a side, nailing it together in
# ``tools/make_crate_asset.py`` so the asset is reproducible.
#
# The dimensions are the parcel's, which is what makes the fall read: a tall
# box (0.62 m) on a narrow footprint (0.30 m deep) is what lets a vertical blow
# on its top rear edge carry it over its own front bottom edge. It is also
# light -- 1.2 kg, because it is slatted and not panelled: four posts, eight
# rails and three boards a side -- so the clock (1.35 kg, ~5 m/s) has enough
# angular impulse to do it, which a 4 kg chair provably does not.
CRATE_WIDTH = 0.400            # x
CRATE_DEPTH = 0.300            # y, back face 0.050 m clear of the plinth
CRATE_HEIGHT = 0.620           # a tall crate, so the clock's rim lands high
CRATE_HALF_EXTENTS = (CRATE_WIDTH / 2, CRATE_DEPTH / 2, CRATE_HEIGHT / 2)
CRATE_MASS = 1.2               # slatted pine crate, 16 mm boards and air
CRATE_CENTER_XY = (-0.640, -2.300)
CRATE_CENTER_Z = FLOOR_Z + CRATE_HEIGHT / 2

# ----------------------------------------------------------------- material
CLOCK_FRICTION = 0.42           # brass and glass on painted panel / floor
CRATE_FRICTION = 0.55           # sanded pine on polished concrete
FLOOR_FRICTION = 0.52
CLOCK_RESTITUTION = 0.22
CRATE_RESTITUTION = 0.15
# Contact-loss stand-ins. A thin disc landing on its rim will otherwise roll on
# that rim for the whole clip; these are the damping the real case gets from
# its own chatter against the floor.
CLOCK_LINEAR_DAMPING = 0.02
CLOCK_ANGULAR_DAMPING = 0.25
CLOCK_ROLLING_FRICTION = 0.003
CRATE_ROLLING_FRICTION = 0.004
CRATE_SPINNING_FRICTION = 0.006
CRATE_ANGULAR_DAMPING = 0.06
FIXTURE_RESTITUTION = 0.18      # walls and furniture
SINK_RESTITUTION = 0.16         # the floor slab itself

SIM_HZ = 1440
GRAVITY_Z = -9.81
SOLVER_ITERATIONS = 150


def crate_center(ph):
    """Centre of the crate, resting on the floor."""
    return [float(ph['crate_center'][0]), float(ph['crate_center'][1]), CRATE_CENTER_Z + .0002]


def clock_hang_center(ph):
    """Centre of the clock disc at frame 1, in the pose it hangs in."""
    return [float(ph['clock_hang'][0]), float(ph['clock_hang'][1]), float(ph['clock_hang'][2])]


def layout(ph):
    return {'clock': clock_hang_center(ph), 'crate': crate_center(ph)}


def present(ph, key):
    """Whether a body exists in this scenario (DELETE turns the crate or the clock off)."""
    return bool(ph.get(key + '_active', [1])[0])


def fixed_constants():
    """Solver constants recorded in the physics JSON for reproducibility."""
    return dict(floor_z=FLOOR_Z, step_y=STEP_Y, upper_floor_z=UPPER_FLOOR_Z, wall_y=WALL_Y,
                plinth_y=PLINTH_Y, plinth_top_z=PLINTH_TOP_Z,
                clock_diameter=CLOCK_DIAMETER, clock_thickness=CLOCK_THICKNESS,
                clock_hang=list(CLOCK_HANG), clock_tip_spin=CLOCK_TIP_SPIN, clock_push=CLOCK_PUSH,
                crate_half_extents=list(CRATE_HALF_EXTENTS), crate_center_xy=list(CRATE_CENTER_XY),
                gravity_z=GRAVITY_Z, sim_hz=SIM_HZ, solver_iterations=SOLVER_ITERATIONS,
                collision_margin_m=.0005)
