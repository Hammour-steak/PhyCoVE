"""SI dimensions of the open wall cupboard, the falling bowl, the tableware and the kitchen.

Everything here is measured, not guessed. The kitchen numbers come from the world
bounds of ``assets/models/modern_kitchen.glb`` after the same transform the
renderer applies (scale 0.5, rotate a quarter turn about Z, translate to centre
the island). The tableware numbers come from ``assets/models/bowl_and_chops.glb``
scaled to one bowl of the set's outer size on the counter; the asset's chopstick
pair is not used.

The cupboard above the hob is the one place the GLB cannot help: its wall units
are *door panels only* -- a single 0.69 x 0.85 m panel 56 mm thick at y ~ 2.91
with nothing behind it. A bowl cannot fall out of a panel, so the scene builds a
real carcass (sides, top, bottom, back, one shelf and one open door) in exactly
the volume that panel occupied, in both the renderer and the solver. The door is
swung open about its right hinge; the bowl sits askew on the bottom board and tips
out through the opening.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

SCENE = 'kitchen_bowl_fall'

# ----------------------------------------------------------------- the kitchen
# modern_kitchen.glb is authored at double scale; the renderer multiplies by
# 0.5 and rotates the long island into the physics X axis (quarter turn about Z),
# then translates by (-0.65, 0, 0) to centre it. These are the measured results:
COUNTER_Z = 0.946          # top surface of the island counter, after transform
FLOOR_Z = -0.092           # top surface of the floor slab, after transform
# The island counter the pendant lamps hang over (y ~ 0), after transform:
COUNTER_X_MIN, COUNTER_X_MAX = -1.517, 1.525
COUNTER_Y_MIN, COUNTER_Y_MAX = -0.498, 0.311
# The wall-side counter run holding the hob and the sink:
WALL_COUNTER_Y_MIN, WALL_COUNTER_Y_MAX = 2.509, 3.466
# The hob: a black glass cooktop on the wall counter, 11 mm proud of the quartz.
HOB_TOP_Z = 0.957
HOB_X_MIN, HOB_X_MAX = -0.821, 0.157
HOB_Y_MIN, HOB_Y_MAX = 2.685, 3.309
# The tiled splashback the cupboard hangs on:
TILE_WALL_Y = 3.450
CEILING_Z = 2.658
ROOM_X_MIN, ROOM_X_MAX = -2.878, 3.074
ROOM_Y_MIN, ROOM_Y_MAX = -3.242, 3.450

# ------------------------------------------------- the open wall cupboard
# Measured from the GLB's own door panel: x -0.494..0.197, z 1.828..2.678,
# front face y = 2.883 with the panel 56 mm thick. The carcass is built from the
# panel's back plane to the tiled wall, so the cupboard replaces the fake panel
# exactly instead of floating in front of it or sinking into the wall.
CABINET_X_MIN, CABINET_X_MAX = -0.494, 0.197
CABINET_Z_BOTTOM, CABINET_Z_TOP = 1.828, 2.678
CABINET_FRONT_Y = 2.939        # front plane of the carcass (back face of the panel)
CABINET_BACK_Y = TILE_WALL_Y - 0.010   # the carcase back sits against the tiles
PANEL_T = 0.018                # side / top / bottom board thickness
BOARD_TOP_Z = CABINET_Z_BOTTOM + PANEL_T   # top face of the bottom board, 1.846
SHELF_Z = 2.270                # fixed interior shelf, top face
SHELF_T = 0.016
DOOR_T = 0.020                 # the door leaf built by the scene
DOOR_OPEN_DEG = 104.           # swung out about the right hinge (vertical edge)
# Hinged on the right jamb so the swung leaf falls away from the camera side and
# the open interior stays readable from the left.
DOOR_HINGE_X = CABINET_X_MAX

# -------------------------------------------------------- the falling bowl
# A real ceramic serving bowl is ~0.16 m across; the collision shape is a
# cylinder (the closed convex hull of the bowl profile) of that diameter.
FALLING_BOWL_DIAMETER = 0.160
FALLING_BOWL_RADIUS = FALLING_BOWL_DIAMETER / 2
FALLING_BOWL_HEIGHT = 0.070       # rim to foot
FALLING_BOWL_MASS = 0.55          # a glazed stoneware serving bowl
# "Left in the cupboard at an angle": the bowl stands on the bottom board tilted
# forward, its rim already at the front lip, so the first thing the solver sees
# is it losing that balance and sliding out of the open door.
FALLING_BOWL_TILT_DEG = 16.       # forward lean about +x (tips the rim into the room)
FALLING_BOWL_START_XY = (-0.150, 2.930)   # on the bottom board, its rim at the lip
# The tilted cylinder's lowest point sits half a tilted body below its centre:
# (h/2)cos(t) + r sin(t). Starting exactly on the board means no initial overlap.
_TILT_RAD = math.radians(FALLING_BOWL_TILT_DEG)
_HALF_DROP = (FALLING_BOWL_HEIGHT / 2) * math.cos(_TILT_RAD) + FALLING_BOWL_RADIUS * math.sin(_TILT_RAD)
FALLING_BOWL_HANG = (FALLING_BOWL_START_XY[0], FALLING_BOWL_START_XY[1],
                     BOARD_TOP_Z + _HALF_DROP + 0.0015)
# It tips out of the cupboard on its own: the tilt above already puts the centre
# of mass past the front lip, so the spin is only a slow roll and there is no
# launch velocity at all. The drop does the work.
FALLING_BOWL_SPIN = 0.06          # rad/s about +x, tipping the rim into the room
FALLING_BOWL_PUSH = 0.00          # m/s towards the room (-y)
FALLING_BOWL_PUSH_X = 0.00

# --------------------------------------------------------- the tableware
# bowl_and_chops.glb is authored as four nested bowls plus one pair of
# chopsticks (~6.8 x 5.6 x 6.9 native units). The scene keeps a single bowl:
# one bowl on the cooktop is enough to read the hit, and it sidesteps the
# problem a stack has -- a stack sheds its top bowls and leaves the bottom one
# standing, which looks like nothing happened. The kept bowl is the outermost,
# largest one of the nested set, the one someone would actually leave out.
# The chopsticks are not used at all, so the body count is exactly 1.
TABLEWARE_COUNT = 1
TABLEWARE_BOWL_DIAMETER = 0.140
TABLEWARE_BOWL_RADIUS = TABLEWARE_BOWL_DIAMETER / 2
TABLEWARE_BOWL_HEIGHT = 0.072
TABLEWARE_MASS = 0.250           # one glazed stoneware bowl (~14 cm across)
TABLEWARE_BASE_Z = HOB_TOP_Z     # the bowl stands on the cooktop glass
TABLEWARE_CENTER_XY = (-0.040, 2.750)
TABLEWARE_PARTS = ('tableware_bowl',)
KEYS = ('falling_bowl',) + TABLEWARE_PARTS

TABLEWARE_TOP_Z = TABLEWARE_BASE_Z + TABLEWARE_COUNT * TABLEWARE_BOWL_HEIGHT

# ----------------------------------------------------------------- material
FALLING_BOWL_FRICTION = 0.32      # glazed stoneware on a melamine shelf board
TABLEWARE_FRICTION = 0.50         # the bowl on the hob glass
COUNTER_FRICTION = 0.55
FALLING_BOWL_RESTITUTION = 0.05
TABLEWARE_RESTITUTION = 0.05
# Contact-loss stand-ins. A bowl landing on its rim will otherwise rock on that
# rim for the whole clip; these are the damping the real ceramic gets from its
# own chatter against the cooktop and the other bowl.
FALLING_BOWL_LINEAR_DAMPING = 0.02
FALLING_BOWL_ANGULAR_DAMPING = 0.30
FALLING_BOWL_ROLLING_FRICTION = 0.020
TABLEWARE_ROLLING_FRICTION = 0.005
TABLEWARE_SPINNING_FRICTION = 0.006
TABLEWARE_ANGULAR_DAMPING = 0.08
COUNTER_RESTITUTION = 0.12        # the quartz countertop and the hob glass
CUPBOARD_RESTITUTION = 0.10       # the cupboard boards and the walls

SIM_HZ = 1440
GRAVITY_Z = -9.81
SOLVER_ITERATIONS = 150


def tableware_part_centers(ph):
    """Centres of the tableware bowls resting on the hob."""
    cx, cy = float(ph['tableware_center'][0]), float(ph['tableware_center'][1])
    out = []
    for i in range(TABLEWARE_COUNT):
        z = TABLEWARE_BASE_Z + i * TABLEWARE_BOWL_HEIGHT + TABLEWARE_BOWL_HEIGHT / 2
        out.append([cx, cy, z + .0002])
    return out


def falling_bowl_hang_center(ph):
    """Centre of the falling bowl at frame 1, in the pose it stands in the cupboard."""
    return [float(ph['falling_bowl_hang'][0]), float(ph['falling_bowl_hang'][1]),
            float(ph['falling_bowl_hang'][2])]


def layout(ph):
    out = {'falling_bowl': falling_bowl_hang_center(ph)}
    out.update(dict(zip(TABLEWARE_PARTS, tableware_part_centers(ph))))
    return out


def present(ph, key):
    """Whether a body exists in this scenario (DELETE turns the whole tableware off)."""
    if key == 'falling_bowl':
        return bool(ph.get('falling_bowl_active', [1])[0])
    return key in TABLEWARE_PARTS and bool(ph['tableware_active'][0])


def fixed_constants():
    """Solver constants recorded in the physics JSON for reproducibility."""
    return dict(counter_z=COUNTER_Z, hob_top_z=HOB_TOP_Z, floor_z=FLOOR_Z,
                cabinet_x=(CABINET_X_MIN, CABINET_X_MAX),
                cabinet_z=(CABINET_Z_BOTTOM, CABINET_Z_TOP),
                cabinet_front_y=CABINET_FRONT_Y, cabinet_back_y=CABINET_BACK_Y,
                board_top_z=BOARD_TOP_Z, shelf_z=SHELF_Z, door_open_deg=DOOR_OPEN_DEG,
                falling_bowl_diameter=FALLING_BOWL_DIAMETER,
                falling_bowl_height=FALLING_BOWL_HEIGHT,
                falling_bowl_tilt_deg=FALLING_BOWL_TILT_DEG,
                falling_bowl_hang=list(FALLING_BOWL_HANG),
                falling_bowl_spin=FALLING_BOWL_SPIN, falling_bowl_push=FALLING_BOWL_PUSH,
                tableware_bowl_diameter=TABLEWARE_BOWL_DIAMETER,
                tableware_bowl_height=TABLEWARE_BOWL_HEIGHT,
                tableware_parts=list(TABLEWARE_PARTS),
                tableware_center_xy=list(TABLEWARE_CENTER_XY),
                gravity_z=GRAVITY_Z, sim_hz=SIM_HZ, solver_iterations=SOLVER_ITERATIONS,
                collision_margin_m=.0005)
