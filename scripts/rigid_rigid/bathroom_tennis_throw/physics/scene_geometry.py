"""SI dimensions shared by collision geometry and imported visuals."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

SCENE_DIR = _PCVE_SCENE_ROOT

# Tennis ball, deliberately OVERSIZED: a regulation ITF ball (r = .0335) spans
# only 6.6-7.2 px at 720p once it is 8 m away, which reads as "no ball at all"
# in the wall-bounce beat. r = .050 (10 cm across) buys 1.5x the pixel footprint
# -- 10-11 px at the same depth -- while still clearing every fixture gap on the
# chain. Mass stays at the real .058 kg so the rebound heights are unchanged;
# only the contact lever arm (and therefore spin pickup) shifts slightly.
BALL_RADIUS = .050
BALL_MASS = .058
# Stool stand-ins reusing the bathroom's own low leather ottomans inside
# big_project.glb. Physics uses one axis-aligned box per stool, sized to the
# SOURCE MESH's own AABB -- the two source ottomans differ (0.724 x 0.426 vs
# 0.652 x 0.548 m), and a box smaller than the mesh lets the ball sink visibly
# into the leather (33 mm for a uniform 0.30 x 0.20 box). Z stays at 0.11 so a
# spawned stool rests exactly on the floor instead of starting a millimetre
# inside it.
STOOL_HALF_A = (.362, .213, .11)   # tag a: stool_a
STOOL_HALF_B = (.326, .274, .11)   # tag b: stool_b
STOOL_TAG = {'stool_a': 'a', 'stool_b': 'b'}
STOOL_HALF = STOOL_HALF_A          # renderer default (any stool tag a)
STOOL_HEIGHT = .22
STOOL_MASS = 2.5

# 4320 Hz: the OVERSIZED ball (r = .050) hitting the thin glass screen square-on
# is the one contact in this scene where a coarse step shows. At 2880 Hz the
# solver leaves 3.7 mm of the ball inside the glass on the steepest
# north-shifted aim (gate is 4 mm); at 4320 Hz the same contact measures 0.86 mm.
# CCD radius makes no difference at all -- step length is what dominates -- so
# the sub-step rate is where the margin comes from.
SIM_HZ = 4320
# Marble floor top, measured by ray probing big_project.glb.
FLOOR_Z = .042
# Shower-base slab: it is NOT flat. Downward rays hit z = .1357 on the marble
# curb that runs round the enclosure (and carries the glass door track) and
# z = .0538 across the recessed floor inside it. A single box at the curb
# height would bounce the ball 82 mm above the visible shower floor everywhere
# inside, so the collider is the floor plus four curb boxes.
SHOWER_BASE_TOP = .136       # curb top, what the glass track stands on
SHOWER_FLOOR_TOP = .0538     # recessed floor inside the curb
STOOL_REST_Z = FLOOR_Z + STOOL_HEIGHT / 2

KEYS = ('tennis_ball', 'stool_a', 'stool_b')

# The throw: from beside the camera across the room into the shower enclosure.
# The baseline line smashes the shower's west glass screen at chest height
# (z ~ 1.31), ricochets off the south wall while still 1.2 m up, drops to the
# floor, and the floor bounce (fixture restitution 0.63) lofts it into the
# marble box's east face -- the side facing the shower -- at z ~ 0.28 while
# still climbing, then it rebounds east and settles by the poufs.
# Measured with tools/search_flight.py (flight gates: glass >= 0.9 m, wall
# >= 0.55 m, airborne window >= 0.15 s, toilet hit >= 0.25 m).
THROW_ORIGIN = (-1.60, -1.60, .95)
AIM_POINT = (4.55, -4.50, .95)
THROW_ELEVATION = .2269  # 13 degrees above horizontal; baseline speed solves the arc
# The two stools, a and b.
# a stands inside the shower enclosure (three-tuple spots carry their own rest
# z) as shower-side scenery the glass->wall->floor->box chain can never reach;
# b is the mid-floor stool the ball rolls past on its way north.
#
# a is on the *recessed* shower floor, 82 mm below the curb top, at y -2.37:
# at y -2.35 its 0.426 m depth would put its north edge 8 mm inside the curb's
# inner face, and the box collider would settle on that knife edge at 11.6 deg
# and visibly lean.
STOOL_SPOTS = {'stool_a': (6.50, -2.37, SHOWER_FLOOR_TOP + STOOL_HEIGHT / 2), 'stool_b': (2.20, -1.90)}
# Physics containment box for a valid run: the visible room shell measured by
# raycasting big_project.glb (Cube_Wall pattern inner faces). The AABB of that
# shell is NOT the room -- it also holds interior partitions -- so these come
# from tools/export_bathroom_colliders.py, not from bounds().
#
# West is the exception. There is no visible west wall at all: rays fired west
# from anywhere inside miss for 6+ m, and the floor mesh stops at x = -8.35.
# What stops a runaway ball is the synthetic `wall_west` collider, whose inner
# face sits at -8.60. The bound follows the collider, not the mesh, or a ball
# that legitimately rolls up to that wall reads as "left the room" -- which is
# what a 1.5x speed run does (measured, not shipped: it rolls into that wall),
# and it is a real trajectory, not an escape.
BOUNDS_MIN = (-8.60, -4.77)
BOUNDS_MAX = (10.95, 4.493)


def presence_index(key):
    """Slot of each stool in the physics stool_presence mask."""
    return {'stool_a': 0, 'stool_b': 1}[key]


def present(ph, key):
    return key == 'tennis_ball' or bool(ph['stool_presence'][presence_index(key)])


def throw_line(ph):
    """Origin and aim of the throw, shifted laterally by ph['aim_shift']."""
    dx = AIM_POINT[0] - THROW_ORIGIN[0]
    dy = AIM_POINT[1] - THROW_ORIGIN[1]
    norm = math.hypot(dx, dy)
    nx, ny = dy / norm, -dx / norm
    off = ph['aim_shift']
    origin = [THROW_ORIGIN[0] + nx * off, THROW_ORIGIN[1] + ny * off, THROW_ORIGIN[2]]
    aim = [AIM_POINT[0] + nx * off, AIM_POINT[1] + ny * off, AIM_POINT[2]]
    return origin, aim


def launch_velocity(ph):
    """Launch vector for a throw of ph['initial_velocity'] at THROW_ELEVATION."""
    origin, aim = throw_line(ph)
    dx, dy = aim[0] - origin[0], aim[1] - origin[1]
    norm = math.hypot(dx, dy)
    speed = ph['initial_velocity']
    cos_e = math.cos(THROW_ELEVATION)
    return [speed * cos_e * dx / norm, speed * cos_e * dy / norm, speed * math.sin(THROW_ELEVATION)]


def stool_position(ph, key):
    """Rest position of one stool; three-tuple spots carry their own rest z."""
    spot = STOOL_SPOTS[key]
    x, y = spot[0], spot[1]
    z = spot[2] if len(spot) > 2 else STOOL_REST_Z
    return [x, y, z + .0001]


def layout(ph):
    out = {'tennis_ball': list(throw_line(ph)[0])}
    for key in KEYS[1:]:
        out[key] = stool_position(ph, key)
    return out
