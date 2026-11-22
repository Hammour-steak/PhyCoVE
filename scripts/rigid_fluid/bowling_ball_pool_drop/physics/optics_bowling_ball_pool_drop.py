"""Pool geometry and optics shared by the simulation, splash, caustics and render.

The visible pool is the opening in the authored deck. The scene maps the asset with the scale
(4 / 8.328, 5 / 8.328, 0.6) (scene_bowling_ball_pool_drop.py), and the authored pool is a rectangle
turned 45 degrees, so the opening is a parallelogram: sides 3.03 and 2.17 m, corners 77.3 / 102.7 deg.
The water and the tiled tank follow it. Its corners are straight lines fitted to the boundary edges of
the coping's inner lip, counter-clockwise from above.

The authored interior is baked for a shallower pool with painted static caustics, so the render
replaces it with its own tiled tank. The sun was fitted to the baked window patches by shadow rays
through the environment (Matthews correlation 0.78): a sunset sun 10 deg high, through the glazing.
"""
import math

import numpy as np

TO_SUN = (.9312, -.3206, .1736)     # unit vector towards the sun
IOR = 1.333
WATER_ABSORPTION = ((.40, .84, .90), 1.)  # Volume Absorption colour and density, as the duck look
FLOOR = -1.25
OPENING = ((-1.6323, .3553), (.2614, -2.0128), (1.6151, -.3214), (-.2747, 2.0516))
WALL_OUTSET = .003                  # tank walls tuck just under the coping lip
RIM_Z = -.141                       # coping lip's inner edge, the top of the tank walls
SHELL_PIXEL = .01                   # m per sunlight texture pixel on the tank
FACES = ('PoolFloor', 'PoolWall0', 'PoolWall1', 'PoolWall2', 'PoolWall3')  # wall k runs corner k -> k + 1


def planes(corners):
    """Outward unit normal n (x, y) and offset d of each wall, inside where n . p < d."""
    corners = np.asarray(corners, float)
    edge = np.roll(corners, -1, axis=0) - corners
    normal = np.column_stack([edge[:, 1], -edge[:, 0]]) / np.linalg.norm(edge, axis=1)[:, None]
    return normal, np.einsum('kd,kd->k', normal, corners)


def outset(corners, distance):
    """The polygon with every wall moved outwards by distance."""
    normal, offset = planes(corners)
    offset = offset + distance
    return np.array([np.linalg.solve(np.stack([normal[k - 1], normal[k]]), [offset[k - 1], offset[k]])
                     for k in range(len(normal))])


POOL = outset(OPENING, WALL_OUTSET)  # the simulation container and the tank


def container(info):
    """Corners (x, y) of a run's simulation container, from its simulation report's info."""
    return np.asarray(info['pool_corners_m'], float)


def wall_distance(points, corners):
    """Distance inside the nearest wall (negative outside), for points (..., >=2)."""
    normal, offset = planes(corners)
    return (offset - np.asarray(points)[..., :2] @ normal.T).min(axis=-1)


def mirror(points, velocity, corners, band):
    """Mirror images, across each wall, of the points within band inside it."""
    normal, offset = planes(corners)
    images, speeds = [], []
    for n, d in zip(normal, offset):
        gap = d - points[:, :2] @ n
        near = (gap >= 0) & (gap < band)
        image, speed = points[near].copy(), velocity[near].copy()
        image[:, :2] += 2 * gap[near, None] * n
        speed[:, :2] -= 2 * (speed[:, :2] @ n)[:, None] * n
        images.append(image)
        speeds.append(speed)
    return np.concatenate(images), np.concatenate(speeds)


def debris(centres):
    """Authored faces the tank replaces: below the coping lip and above the floor, inside the opening or
    within 5 cm outside it. These are the original basin walls, stretched by the deepened floor."""
    centres = np.asarray(centres)
    return ((wall_distance(centres, outset(OPENING, .05)) > 0) & (centres[:, 2] > FLOOR + .01)
            & (centres[:, 2] < RIM_Z - .002))


def tank_quads(corners=POOL):
    """The tank's faces in FACES order as vertex lists: the floor polygon just above the authored floor,
    then each wall from the floor up to the coping lip."""
    corners = np.asarray(corners, float)
    quads = [[(x, y, FLOOR + .003) for x, y in corners]]
    for k in range(len(corners)):
        (ax, ay), (bx, by) = corners[k], corners[(k + 1) % len(corners)]
        quads.append([(ax, ay, FLOOR), (bx, by, FLOOR), (bx, by, RIM_Z), (ax, ay, RIM_Z)])
    return quads


def faces(corners=POOL):
    """Per tank face: origin, u and v axes (3-vectors), size (U, V) in metres and texture (rows, cols).
    Rows run along v. The floor's texture spans the bounding box in x and y; wall k runs from corner k
    to corner k + 1 along u, and from the floor to the rim along v."""
    corners = np.asarray(corners, float)
    lower, upper = corners.min(axis=0), corners.max(axis=0)

    def pixels(span):
        return int(math.ceil(round(span / SHELL_PIXEL, 6)))
    layout = {'PoolFloor': (np.array([lower[0], lower[1], FLOOR]), np.array([1., 0, 0]), np.array([0, 1., 0]),
                            (upper[0] - lower[0], upper[1] - lower[1]))}
    for k in range(len(corners)):
        a, b = corners[k], corners[(k + 1) % len(corners)]
        length = float(np.linalg.norm(b - a))
        layout[FACES[k + 1]] = (np.array([a[0], a[1], FLOOR]), np.array([*(b - a) / length, 0.]), np.array([0, 0, 1.]),
                                (length, RIM_Z - FLOOR))
    return {name: (o, u, v, size, (pixels(size[1]), pixels(size[0]))) for name, (o, u, v, size) in layout.items()}


def inward(name, corners=POOL):
    """Inward unit normal of a tank face."""
    if name == 'PoolFloor':
        return np.array([0., 0., 1.])
    normal, _ = planes(corners)
    return np.array([*-normal[FACES.index(name) - 1], 0.])


def texel(points, face):
    """Texture row and column of points on a face."""
    o, u, v, _, (rows, cols) = face
    rel = np.asarray(points) - o
    return (np.clip(((rel @ v) / SHELL_PIXEL).astype(int), 0, rows - 1),
            np.clip(((rel @ u) / SHELL_PIXEL).astype(int), 0, cols - 1))


def land(start, direction, corners=POOL):
    """Distance along each ray from inside the tank to the floor or a wall, and that face's index in FACES."""
    normal, offset = planes(corners)
    hits = np.full((len(start), len(normal) + 1), np.inf)
    down = direction[:, 2] < 0
    hits[down, 0] = (FLOOR - start[down, 2]) / direction[down, 2]
    for k, (n, d) in enumerate(zip(normal, offset)):
        towards = direction[:, :2] @ n
        out = towards > 0
        hits[out, k + 1] = np.maximum(d - start[out, :2] @ n, 0) / towards[out]
    face = hits.argmin(axis=1)
    return hits[np.arange(len(start)), face], face


def absorption():
    """Absorption coefficient (1/m) of the water for R, G, B, as Cycles' Volume Absorption."""
    colour, density = WATER_ABSORPTION
    return density * (1 - np.asarray(colour))
