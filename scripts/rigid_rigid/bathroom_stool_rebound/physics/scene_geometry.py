"""Bathroom geometry measured from assets/models/big_project.glb.

All static collision boxes are world-space boxes matched to the GLB's own
coordinates, so the renderer can import the model untouched and the replayed
poses line up with the visible furniture. The stool is the tall seat the GLB
ships stacked next to the bathtub (seat slab Cube.045 on three splayed
cylinder legs); physics approximates it with the same measured dimensions.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

SCENE = 'bathroom_stool_rebound'
KEYS = ('stool',)

# Floor slab of the GLB bathroom (Cube.029) tops out at this height.
FLOOR_Z = 0.042
SIM_HZ = 1440
GRAVITY = -9.81

# --- stool recipe (metres), measured from the GLB's stacked stool -----------
# Seat slab Cube.045: x 4.33..5.25, y 0.49..1.54, z 1.27..1.37 -> a rounded
# 0.92 x 1.05 x 0.10 slab centred at (4.79, 1.01, 1.32). Three black cylinder
# legs (r = 0.04, 1.30 long) splay from the seat underside down to floor
# feet at (4.08, 1.03), (5.07, 1.73) and (5.33, 0.31), z 0.04..1.34.
# Body origin = seat centre, so upright the origin sits 1.28 m above the
# floor slab. Each splayed leg is one box tilted along the leg axis
# (stool_boxes), with a foot pad on the GLB foot position.
SEAT_HALF = (0.46, 0.525, 0.05)          # 0.92 x 1.05 x 0.10 slab
STOOL_ORIGIN = (4.79, 1.015, 1.32)       # GLB seat-slab centre (body origin)
LEG_FEET = ((-0.71, 0.015, -1.28), (0.28, 0.715, -1.28), (0.54, -0.705, -1.28))
LEG_TOPS = ((-0.40, 0.055, 0.02), (0.07, 0.475, 0.02), (0.36, -0.445, 0.02))
LEG_RADIUS = 0.04
LEG_HALF = 0.045                          # collider half-width of one leg box
STOOL_COM_Z = 1.28                        # origin height above the floor, upright
STOOL_MASS = 10.35                        # oak slab (9.0) + three legs (0.45)
FRICTION = 0.35                           # wood on glazed tile
RESTITUTION = 0.60                        # wood on marble / cabinetry
# Bullet multiplies the two bodies' restitution, so the pair's real bounce is
# stool * static.
#
# A stool that comes down on its seat edge with three legs splayed carries its
# centre of mass almost directly over the contact line, so the gravity moment
# is near zero. With a much deader pair (about 0.25) the normal impulse eats
# most of the horizontal speed in two frames, the three legs and the seat edge
# pin the stool to the floor on a multi-point footprint, and it creeps over at
# 0.5 rad/s for more than a second. This restitution together with the 0.35
# friction lets it rebound off the footprint, keep one contact point, and
# tumble through in ~0.7 s; over all cases the longest freeze at any tilt is
# under 0.1 s.
STATIC_RESTITUTION = 0.55

# --- launch condition (canonical direction; the CLI scales its magnitude) ---
SPAWN_XY = (0.55, 0.75)                  # clear space between the two vanities
SPAWN_Z = 2.20                          # seat centre; feet start 0.878 m above the tile
LAUNCH_DIR = (0.75, 0.55, 0.18)          # near level throw: solid hits on the vanity, then slingshots east
SPIN_DIR = (0.18, -0.95, 0.26)           # unit vector: a slight backward pitch
LAUNCH_SPEED = 6.0                       # 6.0 m/s: the value the scene description
                                         # states; keeps the throw readable in the
                                         # 4 s clip and the *3 edit (18 m/s) inside
                                         # the locked camera frame (at 10.5 m/s the
                                         # *3 edit reaches the ceiling, out of shot)
LAUNCH_SPIN = 2.6

# --- bathtub collider: the marble's own triangles ---------------------------
# The tub is a tilted ellipse in plan whose skirt flares outward with height,
# and it is a hollow shell. A surrogate built from its bounding volume leaves
# a wall in empty air: a single box from the group bounding box overhangs the
# visible marble by 0.41 m to the west, so the stool would strike the bathtub
# 0.66 m from any visible surface, hit that invisible plane and stall in
# mid-air.
#
# So the collider IS the geometry. tools/export_bathtub_collider.py writes the
# GLB's marble shells to the OBJ below (Z-up, world space); the solver loads it
# with GEOM_FORCE_CONCAVE_TRIMESH, the flag that keeps the basin hollow instead
# of collapsing the tub into a filled convex hull. Contact happens on the
# marble, and a stool that clears the rim falls in and lands on the basin floor.
BATHTUB_MESH = 'scenes/bathroom_stool_rebound/bathtub_collision.obj'


def bathtub_mesh_path():
    """Absolute path of the exported marble collider mesh."""
    return _pcve_asset(BATHTUB_MESH)


# --- tub alcove collider: the chamfered corner, again from the marble's own
# triangles ------------------------------------------------------------------
# The four wall boxes are flat planes (wall_north inner face y=4.47, wall_east
# inner face x=11.10), but the GLB cuts the north-east corner at 45 degrees: a
# chamfered wall runs from about (6.8, 4.49) down to (10.4, 1.06), and a marble
# shelf (top z=2.49) fills the triangle behind it, carrying the towels, candles
# and vases. Without a collider there, anything entering the corner sinks
# 0.5-1.2 m into the visible wall. Measured with a per-frame silhouette test on
# edit_fast_throw: frames 17-23 put 26/46/79/65/66/85 % of the stool behind the
# visible surface, deepest 1.79 m, and the flight cuts tovel3.003's cloth and
# the shelf's candles in the triangle-pair overlap test.
#
# A diagonal wall cannot be approximated by axis-aligned boxes without either a
# ~0.4 m air wall along its whole run or a stair-stepped edge, so this is a
# second concave trimesh built the same way as the tub: the collider IS the
# geometry. Only 300-odd triangles are involved, so the cost is negligible.
ALCOVE_MESH = 'scenes/bathroom_stool_rebound/alcove_collision.obj'

# GLB objects that make up the chamfer + shelf + the skirting running along
# them. Everything else in the room shell is already covered by static_boxes.
ALCOVE_SOURCES = ('Cube_Wall pattern_0', 'Cube.047_Bathtub maarble_0')

# World-space crop (x0, x1, y0, y1, z0, z1). Chosen so every boundary lands
# inside solid geometry - the west edge sits where the chamfer meets the flat
# north wall, the east edge inside wall_east, the bottom under the floor slab -
# so the trimesh never ends in open air.
ALCOVE_CROP = (6.5, 10.9, 0.9, 4.75, -0.1, 3.15)


def alcove_mesh_path():
    """Absolute path of the exported chamfer/shelf collider mesh."""
    return _pcve_asset(ALCOVE_MESH)


# --- static boxes: (name, centre, half extents) in GLB world coordinates. ---
def _box(cx, cy, cz, hx, hy, hz):
    return ([cx, cy, cz], [hx, hy, hz])

def static_boxes():
    """Floor, four walls, washbasin cabinet + stone basin + mirror.

    The bathtub is NOT here: its visible outline is a tilted, outward-flaring
    shell, so it gets a concave mesh collider (bathtub_mesh_path) instead.
    """
    boxes = []
    # Floor slab and room shell (Cube.029 / Cube_Wall pattern).
    boxes.append(('floor', [1.5, -0.3, FLOOR_Z - .3], [12.0, 6.5, .3]))
    boxes.append(('wall_north', [1.5, 4.62, 3.0], [12.0, .15, 3.4]))
    boxes.append(('wall_south', [1.5, -5.35, 3.0], [12.0, .15, 3.4]))
    boxes.append(('wall_west', [-8.45, -0.3, 3.0], [.15, 6.5, 3.4]))
    boxes.append(('wall_east', [11.25, -0.3, 3.0], [.15, 6.5, 3.4]))
    # Ceiling slab (Cube.013): keeps the *3-speed edit inside the room.
    boxes.append(('ceiling', [1.5, -0.3, 6.26], [12.0, 6.5, .07]))
    # Washbasin: wooden vanity Cube.040 (0.378..1.618) + marble basin Cube.038
    # (1.618..1.807) + mirror Cube.021. Extended down to the floor slab.
    boxes.append(('vanity', [1.6065, 3.795, (FLOOR_Z + 1.618) / 2],
                  [2.2035, .698, (1.618 - FLOOR_Z) / 2]))
    boxes.append(('basin', [1.6065, 3.795, 1.7125], [2.2035, .698, .0945]))
    boxes.append(('mirror', [1.694, 4.3615, 3.484], [.803, .0265, 1.039]))
    return boxes

# Bodies reported as the washbasin in the event log.
SINK_BODIES = ('vanity', 'basin', 'mirror')

def fixed_constants():
    return dict(floor_z=FLOOR_Z, spawn_xy=list(SPAWN_XY), spawn_z=SPAWN_Z,
                stool_com_z=STOOL_COM_Z,
                launch_dir=list(LAUNCH_DIR), spin_dir=list(SPIN_DIR),
                stool_seat_half=list(SEAT_HALF),
                stool_leg_feet=[list(v) for v in LEG_FEET],
                stool_leg_tops=[list(v) for v in LEG_TOPS],
                stool_leg_radius=LEG_RADIUS, stool_leg_half=LEG_HALF,
                stool_leg_collider='one tilted box per leg',
                static_boxes=[dict(name=n, center=c, half_extents=h) for n, c, h in static_boxes()],
                bathtub_collider=dict(kind='concave_trimesh', mesh=BATHTUB_MESH),
                alcove_collider=dict(kind='concave_trimesh', mesh=ALCOVE_MESH,
                                     crop=list(ALCOVE_CROP), sources=list(ALCOVE_SOURCES)),
                restitution=RESTITUTION, static_restitution=STATIC_RESTITUTION,
                gravity_z=GRAVITY, sim_hz=SIM_HZ, solver_iterations=120,
                collision_margin_m=.0005)


def _quat_from_z(axis):
    """Quaternion (x, y, z, w) rotating the local +z onto axis."""
    norm = math.sqrt(sum(a * a for a in axis)) or 1.
    ax, ay, az = (a / norm for a in axis)
    c = max(-1., min(1., az))
    if c > 1. - 1e-9:
        return [0., 0., 0., 1.]
    if c < -1. + 1e-9:
        return [0., 1., 0., 0.]
    half = math.acos(c) / 2.
    s = math.sqrt(max(1e-12, ax * ax + ay * ay))
    k = math.sin(half) / s
    return [-ay * k, ax * k, 0., math.cos(half)]


def stool_boxes():
    """The stool as compound children: (half extents, position, quaternion).

    Seat slab, then one tilted box per splayed leg running exactly from its GLB
    foot to its seat attachment, plus a flat footprint pad at the foot.

    Child orientations inside a compound shape (collisionFrameOrientations)
    work in this pybullet build. A staircase of vertical boxes per leg would
    need 16 children instead of 7, and its segments would press on the same
    floor plane at slightly different angles, so the normal impulses cancel and
    a stool landing on three legs reads as landing on a sponge. One box per leg
    also puts the contact surface where the visible leg actually is, instead of
    ±3 cm off it at the segment ends.
    """
    parts = [(list(SEAT_HALF), [0., 0., 0.], [0., 0., 0., 1.])]
    for foot, top in zip(LEG_FEET, LEG_TOPS):
        axis = [top[i] - foot[i] for i in range(3)]
        length = math.sqrt(sum(a * a for a in axis))
        dz = abs(axis[2]) / length
        # A box with a tilted long axis drops its corner below the end face by
        # half-width * sin(tilt). Left full length, the leg tip starts ~12 mm
        # under the floor slab, and the settle step fires the stool up at
        # 1.5 m/s before the clip even begins. Shave the box so its
        # lowest corner sits on the foot plane; the pad below covers the gap.
        half_len = length / 2 - LEG_HALF * math.sqrt(max(0., 1. - dz * dz)) / dz
        centre = [(foot[i] + top[i]) / 2 for i in range(3)]
        parts.append(([LEG_HALF, LEG_HALF, half_len], centre, _quat_from_z(axis)))
        parts.append(([LEG_HALF + .012, LEG_HALF + .012, .012],
                      [foot[0], foot[1], foot[2] + .012], [0., 0., 0., 1.]))
    return parts
