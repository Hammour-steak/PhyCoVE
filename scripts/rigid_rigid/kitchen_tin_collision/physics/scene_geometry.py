"""Meter-scale geometry of the two tins, the dining table and the room around it.

The tabletop is the world origin: the render lays a tablecloth whose flat top is
exactly the box below, on ``z = 0`` with the table centred on the X/Y axes, and
builds the bistro room from the floor and wall numbers at the end of this file.
The simulator never sees a render mesh, only these numbers, so both halves of
the scene agree on one number instead of two.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

KEYS = ('driver_can', 'receiver_can')

# --- the table -------------------------------------------------------------
# The flat top of the cloth spans 1.077 x 0.660 and the cloth then rolls over
# the edge and hangs.  The collision box is that flat top exactly -- not an
# inset of it -- so the surface the tins slide on is the surface the render
# draws, to the millimetre (render_kitchen_tin_collision.py ray-checks it).
TABLE_TOP_Z = 0.
TABLE_HALF_X = .5385
TABLE_HALF_Y = .330

# --- the driver: a tuna tin, standing flat on its base ---------------------
# The GLB is 206 x 206 x 69.8 units; scaling the diameter to a real 8 cm tin
# gives the height for free, so the visual model and the hull cannot drift.
# It travels base-down (axis along Z), so the contact patch is the whole disc
# and the tin slides instead of rolling.
DRIVER_RADIUS = .040
DRIVER_HEIGHT = .0271
DRIVER_COM_Z = DRIVER_HEIGHT / 2      # flat on its base, axis along Z
# The launch line sits 22 mm off the receiver's centre line, so the first
# contact lands on the flank of the 129 mm face instead of dead centre.  The
# offset arm is what turns the hit into a rotation rather than a pure shove.
DRIVER_START = (-.42, -.022, DRIVER_COM_Z)

# A rolled-rim profile, revolved into the convex hull the solver actually uses.
# The chamfer only touches the two end faces, so the running surface stays a
# clean cylinder and the tin does not catch on its own rim.
_H = DRIVER_HEIGHT / 2
PROFILE = ((.0362, -_H), (.0392, -_H * .90), (.0400, -_H * .62),
           (.0400, _H * .62), (.0392, _H * .90), (.0362, _H))

# --- the receiver: a sardine tin, lying flat, long face to the impact ------
# The GLB is already in metres (0.1291 x 0.0752 x 0.0363) and sits on z = 0.
# Half extents are the tin's own frame; the body is yawed 90 degrees at spawn so
# its 129 mm side faces the oncoming tin.  A hit on the long face is what makes
# the struck tin turn visibly instead of just sliding away.
RECEIVER_HALF = (.0645, .0375, .018)
RECEIVER_YAW_DEG = 90.
RECEIVER_COM_Z = RECEIVER_HALF[2]
RECEIVER_START = (.018, 0., RECEIVER_COM_Z)

SIM_HZ = 1440

# --- the room --------------------------------------------------------------
# The bistro corner the table stands in; appearance/bistro_room.py builds its
# floor, wainscoted back wall and shop-front window wall on these planes.  No
# tin leaves the cloth in any of the five cases, but an edit that did would land
# on this floor and stop at these walls, so the solver keeps them exactly where
# the render draws them.  The floor is a 0.7475 m table plus the cloth below the
# table-top origin.
FLOOR_Z = -.749
ROOM_X = (-2.60, 1.25)      # open dining room / inside face of the window wall
ROOM_Y = (-2.60, 1.30)      # open dining room / panelled back wall
ROOM_TOP_Z = FLOOR_Z + 3.0  # ceiling


def hull_vertices(segments=128):
    return [[r * math.cos(i * 2 * math.pi / segments), r * math.sin(i * 2 * math.pi / segments), z]
            for r, z in PROFILE for i in range(segments)]


def fixed_constants():
    return dict(table_top_z=TABLE_TOP_Z, table_half_extents=[TABLE_HALF_X, TABLE_HALF_Y],
                driver_radius=DRIVER_RADIUS, driver_height=DRIVER_HEIGHT, driver_profile=PROFILE,
                driver_start_position=list(DRIVER_START),
                receiver_half_extents=list(RECEIVER_HALF), receiver_start_position=list(RECEIVER_START),
                floor_z=FLOOR_Z, room_x=list(ROOM_X), room_y=list(ROOM_Y), room_top_z=ROOM_TOP_Z,
                gravity_z=-9.81, sim_hz=SIM_HZ, solver_iterations=140, collision_margin_m=.0001)
