"""Metre-scale orange geometry shared by the visual model and the Bullet bodies.

The room is built around the table numbers below: ``appearance/sunlit_dining_room.py``
generates the tablecloth's top on exactly this box and refuses to build if it
does not match.

Why the cut face points up
--------------------------
A whole orange rolling across a table has its centre one radius above it.  If
the sliced orange were set down on its cut face, its centre would sit only
``CUT_TOP`` above the table, the rolling one would arrive far above it and ride
straight over the shoulder: measured on this solver that transfers 0.02 N.s
where a level hit transfers 0.06 N.s.  Standing it on its dome with the slice
facing up puts both centres at the same height, the contact normal comes out
horizontal, and it is also the only pose a dome-down cut orange can hold still
in -- any tilt of it is a pendulum and would rock on its own before anything
touched it.

Why the slice is shallow
------------------------
Cutting a cap off moves the centre of mass away from the cut, so a deep slice
turns the orange into a roly-poly that rocks back instead of travelling.  At
``CUT_TOP`` the offset is about 1.7 mm, which rocks out in a little over a
second while still leaving a 5.3 cm face: a slice you can see, on a body that
still behaves like an orange.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

# --- the dining table: the simulator's table box -----------------------------
TABLE_TOP_Z = .742
TABLE_CENTER = (-.005, -.0025)
TABLE_HALF = (.905, .550)

# --- the fruit -------------------------------------------------------------
RADIUS = .0385                 # 7.7 cm navel orange
CUT_TOP = .0200                # the slice is taken off above this local height
FACE_RADIUS = math.sqrt(RADIUS ** 2 - CUT_TOP ** 2)
CUT_YAW_DEG = 24.              # the cut face is turned away from the driver
START_X = (-.55, .12)          # driver centre, struck orange centre
DRIVER_Y, CUT_Y = 0., .010     # the struck one sits a little off the line
REAR_CLEARANCE = .0006         # a hair of daylight between touching oranges
SIM_HZ = 1440
ROLLING_FRICTION = .0004

KEYS = ('driver_orange', 'cut_orange', 'rear_orange_1', 'rear_orange_2')


def _profile(rings):
    """Polar samples of a unit sphere from the north pole down, south pole included."""
    return [(math.sin(math.pi * j / rings), math.cos(math.pi * j / rings)) for j in range(rings + 1)]


def cut_vertices(rings=48, segments=96):
    """Hull points of the orange with the cap above ``z = CUT_TOP`` sliced off.

    The dome is sampled finely because this mesh is the struck body's collider
    and a coarse hull makes a rolling sphere bump over its own facets: at 28
    rings every bump lifts the centre 0.24 mm, which is a third of the energy a
    0.09 m/s nudge carries.
    """
    points = []
    for r, z in _profile(rings):
        if RADIUS * z > CUT_TOP + 1e-9:
            continue
        for i in range(segments):
            points.append([RADIUS * r * math.cos(i * 2 * math.pi / segments),
                           RADIUS * r * math.sin(i * 2 * math.pi / segments),
                           RADIUS * z])
    # The rim of the slice is a hard circle; sample it explicitly so the hull
    # and the rendered flesh face share one silhouette.
    for i in range(segments):
        a = i * 2 * math.pi / segments
        points.append([FACE_RADIUS * math.cos(a), FACE_RADIUS * math.sin(a), CUT_TOP])
    return points


def cut_mass_properties(density=1.):
    """Volume, centre of mass and inertia of the sliced solid, about its origin.

    Closed form for a solid of revolution: a disc of radius r at height z has
    ``dI_zz = rho*pi*r^4/2 dz`` and ``dI_xx = rho*pi*(r^4/4 + r^2 z^2) dz``.
    Integrating from the south pole up to the cut plane gives the body's real
    mass distribution instead of Bullet's bounding-box guess.
    """
    r, d = RADIUS, CUT_TOP
    vol = lambda lo, hi: math.pi * (r * r * (hi - lo) - (hi ** 3 - lo ** 3) / 3.)
    mom = lambda lo, hi: math.pi * (r * r * (hi ** 2 - lo ** 2) / 2. - (hi ** 4 - lo ** 4) / 4.)
    izz = lambda lo, hi: math.pi / 2. * (r ** 4 * (hi - lo) - 2. / 3. * r * r * (hi ** 3 - lo ** 3) + (hi ** 5 - lo ** 5) / 5.)
    ixx = lambda lo, hi: math.pi * ((r ** 4 * (hi - lo) - 2. / 3. * r * r * (hi ** 3 - lo ** 3) + (hi ** 5 - lo ** 5) / 5.) / 4.
                                    + (r * r * (hi ** 3 - lo ** 3) / 3. - (hi ** 5 - lo ** 5) / 5.))
    v = vol(-r, d)
    com = mom(-r, d) / v
    return dict(volume=density * v, center_of_mass_z=com,
                inertia_about_origin=[density * ixx(-r, d), density * ixx(-r, d), density * izz(-r, d)])


def cut_body_parameters(mass):
    """Bullet's inertia diagonal and inertial-frame offset for the sliced orange.

    ``localInertiaDiagonal`` is read about the centre of mass, not about the
    body origin, so the parallel-axis term is subtracted here rather than left
    to the solver.
    """
    p = cut_mass_properties(1.)
    scale = mass / p['volume']
    com = p['center_of_mass_z']
    ixx = p['inertia_about_origin'][0] * scale - mass * com * com
    izz = p['inertia_about_origin'][2] * scale
    return dict(inertial_frame_z=com, inertia=[ixx, ixx, izz],
                volume=p['volume'], center_of_mass_z=com)


def sphere_inertia(mass):
    i = .4 * mass * RADIUS * RADIUS
    return [i, i, i]


def rear_x(count):
    """Centres of the queued whole oranges, touching the struck one from behind."""
    return [START_X[1] + (i + 1) * (2 * RADIUS + REAR_CLEARANCE) for i in range(count)]


def fixed_constants():
    return dict(table_top_z=TABLE_TOP_Z, table_center=TABLE_CENTER, table_half=TABLE_HALF,
                radius=RADIUS, cut_top=CUT_TOP, face_radius=FACE_RADIUS,
                cut_yaw_deg=CUT_YAW_DEG,
                initial_x=START_X, driver_y=DRIVER_Y, cut_y=CUT_Y, rear_clearance=REAR_CLEARANCE,
                gravity_z=-9.81, sim_hz=SIM_HZ,
                table_friction=1., orange_lateral_friction=.72, rolling_friction=ROLLING_FRICTION,
                solver_iterations=120, collision_margin_m=.0002)
