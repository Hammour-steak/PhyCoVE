"""Court geometry: the solver's static bodies, and what the renderer builds on them.

Every number in this file is read off a game-level gym model
(assets/models/indoor_basketball_court.glb), not off a spec sheet: its hoop
sits lower than a regulation 3.05 m (close to a 2.60 m mini-basketball goal),
so a "regulation" rim height here would put the ball above the backboard. The
renderer does not load that model: appearance/ builds the board, ring, bracket
and base exactly on the bodies below, so the surfaces the camera sees are the
ones the ball collides with.

  backboard face   y = 6.4949        x in +-0.642      z in 2.5625..3.4253
  rim centre       (0.0, 6.1063)     ring radius 0.208  tube 0.0123
  rim plane        z = 2.7252        inner opening radius 0.1957
  net              none (no net is collided and none is drawn)
  floor            z = 0.1042 (top of the floor slab)

The rim is a torus, and PyBullet has no torus primitive. It is collided as a
ring of ``RIM_SEGMENTS`` static spheres whose radius equals the tube radius and
whose spacing is half of it, so the polygon of contact surfaces stays within
0.4 mm of the real ring: a ball rolling round the rim sees a smooth rail rather
than a row of beads. The visual rim is a torus on the same centreline with
the same tube radius.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

SCENE = 'basketball_rim_roll_in'

# --- fixed court furniture (world metres, measured from the GLB) ------------
# The model's painted floor is a 104 mm slab sitting on z=0, so that is where a
# ball actually bounces. Every other constant below was measured in the same
# frame; keeping them together is what stops the ball sinking into the paint.
FLOOR_Z = 0.1042
CEILING_Z = 4.29
BOARD_FACE_Y = 6.4949
BOARD_HALF = (0.642, 0.010, 0.4314)      # half extents of the board slab
BOARD_CENTER = (0.0, BOARD_FACE_Y + BOARD_HALF[1], 2.9939)
RIM_CENTER_X = 0.0
RIM_CENTER_Y = 6.1063
RIM_RADIUS = 0.208                       # ring centreline
RIM_TUBE = 0.0123
RIM_Z = 2.7252
RIM_SEGMENTS = 96
# The bracket that ties the ring to the board: short, solid, and in the way of
# nothing except a ball trying to slip between ring and board.
BRACKET_HALF = (0.030, 0.100, 0.045)
BRACKET_CENTER = (0.0, 6.395, RIM_Z - 0.010)

GRAVITY = -9.81
SIM_HZ = 1440

# --- counterweight box under the pole -------------------------------------
# The wedge standing in front of the hall door. It is not a cuboid: the front
# face is narrow and low (x +-0.30 at z 0.145) and the back is full width and
# high (x +-0.559 at z 0.412), which is what the render shows as the ramp. The
# ball comes down on it at the end of the shot, and without a body here it fell
# straight through the box and disappeared inside -- invisible for the last
# second of the clip. Eight corners and twelve triangles are exactly the shape.
GOAL_BASE_VERTICES = [
    (-0.559, 7.020, -0.020), (0.559, 7.020, -0.020),
    (0.559, 8.553, -0.020), (-0.559, 8.553, -0.020),
    (-0.300, 7.030, 0.145), (0.300, 7.030, 0.145),
    (0.559, 8.500, 0.412), (-0.559, 8.500, 0.412),
]
GOAL_BASE_FACES = [
    (0, 2, 1), (0, 3, 2),          # bottom, on the floor slab
    (4, 5, 6), (4, 6, 7),          # the ramp the ball lands on
    (0, 1, 5), (0, 5, 4),          # narrow front face
    (3, 7, 6), (3, 6, 2),          # back face
    (0, 4, 7), (0, 7, 3),          # left flank
    (1, 2, 6), (1, 6, 5),          # right flank
]


def goal_base_mesh():
    """The counterweight box as (vertices, triangle indices), world coordinates."""
    return ([list(v) for v in GOAL_BASE_VERTICES],
            [index for face in GOAL_BASE_FACES for index in face])


def rim_ring_points(segments=RIM_SEGMENTS):
    """Centres of the collision spheres that stand in for the rim tube."""
    return [(RIM_CENTER_X + RIM_RADIUS * math.cos(2 * math.pi * i / segments),
             RIM_CENTER_Y + RIM_RADIUS * math.sin(2 * math.pi * i / segments),
             RIM_Z) for i in range(segments)]


def static_boxes():
    """Named boxes: the floor slab, the backboard, the ring bracket."""
    return [
        ('floor', [0.0, 0.0, FLOOR_Z - 0.25], [12.0, 12.0, 0.25]),
        ('backboard', list(BOARD_CENTER), list(BOARD_HALF)),
        ('rim_bracket', list(BRACKET_CENTER), list(BRACKET_HALF)),
    ]


def fixed_constants():
    return dict(floor_z=FLOOR_Z, ceiling_z=CEILING_Z, board_face_y=BOARD_FACE_Y,
                board_half=list(BOARD_HALF), board_center=list(BOARD_CENTER),
                rim_center=[RIM_CENTER_X, RIM_CENTER_Y, RIM_Z],
                rim_radius=RIM_RADIUS, rim_tube=RIM_TUBE, rim_z=RIM_Z,
                rim_segments=RIM_SEGMENTS,
                rim_inner_radius=RIM_RADIUS - RIM_TUBE,
                gravity_z=GRAVITY, sim_hz=SIM_HZ,
                collision_margin_m=0.0005)
